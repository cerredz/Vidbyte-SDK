"""FILE: vidbyte/agents/skills/vendor.py

PURPOSE: Defines VendorSkillResolver, the shared base for skills uploaded to a model vendor's Skills API (Anthropic and OpenAI): it picks the key, downloads the skill's version content, falls back from "latest" to the version the skill record names, maps vendor statuses to explained resolutions, and takes the SKILL.md out of the body, which is either the bare file or a zip archive read in memory.
ROLE IN CODEBASE: Subclassed by AnthropicSkillResolver (anthropic.py) and OpenAISkillResolver (openai.py), which set the provider, the source type, and the request headers. Requests go through SkillFetch (fetch.py); the file is parsed by SkillMarkdown (markdown.py).
ARCHITECTURE NOTE: resolve is the one narrated main and calls only leaf helpers and other classes. Keys come from the entry, else ProviderModelRegistry.resolve_api_key, which strips both; the provider's fixed default endpoint is the only host a key is sent to. Archives are read with zipfile over an in-memory buffer and nothing is extracted to disk.
FUNCTION INVENTORY: VendorSkillResolver.resolve(entries) -> tuple[SkillResolution, ...]; _headers(key) (each vendor sets it); _key(entry); _content_url(entry, version); _record_url(entry); _refused_latest(entry, answer); _classify(answer, entry, version, step); _record_version(record, entry); _skill_markdown(body).
COMMON MODIFICATION PATTERNS: A new vendor is a subclass in its own module that sets PROVIDER and SOURCE_TYPE and overrides _headers, plus its entry class, enum member, and loader map entry; its entry class also joins the constrained VendorSkillT below, or mypy (lint S009) rejects the subclass. A status the vendor starts using joins the dict in _classify.
WHAT NOT TO DO IN THIS FILE: 1. Do not follow redirects; x-api-key would reach another origin. 2. Do not send a key that starts with the Vidbyte key prefix or holds a character outside printable ASCII; a header cannot carry it, and httpx would raise outside every catch. 3. Do not extract an archive or read any member but the one SKILL.md. 4. Do not let the bzip2 or lzma decoders see untrusted bytes; only stored and deflate members are read. 5. Do not call HTTPStatus(status) or echo a body.
KNOWN EDGE CASES: "latest" refused with 400, 404, or 422 triggers one skill-record read (latest_version, else latest_version_id; an integer becomes decimal text, a bool is not a version), then one download of that version; a 404 for it says the skill exists but its content route was not found. A missing key, a Vidbyte key, and a key a header cannot carry are AUTH_FAILED with no request and are remembered. A vendor 3xx is FETCH_FAILED (transient). A body starting with `---` after an optional byte-order mark is a bare SKILL.md; anything else must be a zip with exactly one SKILL.md (any case) at the root or one folder deep. A member declaring more than the SKILL.md cap is TOO_LARGE before it is read. Corrupt archives raise BadZipFile, zlib.error, EOFError, NotImplementedError, or ValueError (which includes UnicodeDecodeError), and all become INVALID_SKILL.
RELATED DOCS: vidbyte/agents/skills/README.md; docs/spec/jev-skill-sources/spec.md (D-10, D-11, D-19, D-20, D-21, D-29, D-30, section 9.2)
TESTS: tests/features/jev_skills_preload/test_skill_sources_vendor.py; tests/features/jev_skills_preload/test_skill_sources_security.py
"""

from __future__ import annotations

import codecs
import io
import json
import zipfile
import zlib
from http import HTTPStatus
from pathlib import PurePosixPath
from typing import ClassVar, TypeVar
from urllib.parse import quote, urlsplit

from vidbyte.agents.skills.fetch import SkillFetch
from vidbyte.agents.skills.markdown import SkillMarkdown
from vidbyte.agents.skills.resolver import SkillResolver
from vidbyte.lib.constants.jev import VIDBYTE_API_KEY_PREFIX
from vidbyte.lib.constants.skills import (
    SKILL_ARCHIVE_ENCRYPTED_FLAG,
    SKILL_ARCHIVE_MAGIC,
    SKILL_ARCHIVE_MAX_DEPTH,
    SKILL_DOWNLOAD_MAX_BYTES,
    SKILL_MARKDOWN_DELIMITER,
    SKILL_MARKDOWN_FILE_NAME,
    SKILL_MARKDOWN_MAX_BYTES,
    SKILL_VENDOR_LATEST_VERSION,
    SKILL_VENDOR_LATEST_VERSION_FIELDS,
)
from vidbyte.lib.dataclasses.skills import AnthropicSkill, OpenAISkill, SkillResolution
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.enums.skills import (
    SkillFetchStep,
    SkillSourceType,
    SkillUnavailableReason,
)
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.http.transport import HttpResponse
from vidbyte.lib.registries.models import ProviderModelRegistry

VendorSkillT = TypeVar("VendorSkillT", AnthropicSkill, OpenAISkill)


class VendorSkillResolver(SkillResolver[VendorSkillT]):
    """Downloads one vendor-hosted skill version and reads its SKILL.md; subclasses set the vendor."""

    PROVIDER: ClassVar[ModelProvider]
    SOURCE_TYPE: ClassVar[SkillSourceType]

    def __init__(self) -> None:
        # The vendor's fixed default endpoint is the only host its key
        # is ever sent to.
        self.fetch = SkillFetch()
        self.base_url = ProviderModelRegistry.get_default_endpoint(self.PROVIDER)
        self.host = urlsplit(self.base_url).hostname or self.base_url
        self.env_var = ProviderModelRegistry.get_api_key_env_var(self.PROVIDER)

    def _headers(self, key: str) -> dict[str, str]:
        # Each vendor sends its key in its own header.
        raise NotImplementedError(f"{type(self).__name__} must define the request headers for its vendor.")

    async def resolve(self, entries: tuple[VendorSkillT, ...]) -> tuple[SkillResolution, ...]:
        # @intent vendor-skill-download
        # The key is checked before any request, and only the vendor's own
        # host ever receives it. "latest" falls back to the version the
        # skill record names, once, and only when the content route
        # refuses "latest" itself.
        (entry,) = entries
        # Pick the key: the entry's own, else the vendor's variable.
        key = self._key(entry)
        if isinstance(key, SkillResolution):
            return (key,)
        headers = self._headers(key)
        # Download the version the entry names.
        version = entry.version
        answer = await self.fetch.get(url=self._content_url(entry, version), headers=headers, max_bytes=SKILL_DOWNLOAD_MAX_BYTES, step=SkillFetchStep.VENDOR_CONTENT)
        # When the vendor does not accept "latest" as a version, read the
        # newest version from the skill record and download that one.
        if self._refused_latest(entry, answer):
            record_answer = await self.fetch.get(url=self._record_url(entry), headers=headers, max_bytes=SKILL_DOWNLOAD_MAX_BYTES, step=SkillFetchStep.VENDOR_METADATA)
            record = self._classify(record_answer, entry, version, SkillFetchStep.VENDOR_METADATA)
            if isinstance(record, SkillResolution):
                return (record,)
            named = self._record_version(record, entry)
            if isinstance(named, SkillResolution):
                return (named,)
            version = named
            answer = await self.fetch.get(url=self._content_url(entry, version), headers=headers, max_bytes=SKILL_DOWNLOAD_MAX_BYTES, step=SkillFetchStep.VENDOR_CONTENT)
        # Map the download's status to a reason with its fix.
        content = self._classify(answer, entry, version, SkillFetchStep.VENDOR_CONTENT)
        if isinstance(content, SkillResolution):
            return (content,)
        # Take the SKILL.md out of the body, then parse it under a label
        # naming the version that answered.
        raw = self._skill_markdown(content.raw_bytes or b"")
        if isinstance(raw, SkillResolution):
            return (raw,)
        return (SkillMarkdown.parse(raw, name=entry.name, source=f"{self.SOURCE_TYPE.value}:{entry.skill_id}@{version}"),)

    def _key(self, entry: VendorSkillT) -> str | SkillResolution:
        # @intent vendor-key-guard
        # The registry strips the entry key and the environment value, and
        # the stripped value is the one checked and sent. A Vidbyte key is
        # never sent to a vendor, even when it sits in the vendor variable.
        # A header carries only printable ASCII, so a key with any other
        # character is refused here instead of crashing the run.
        try:
            key = ProviderModelRegistry.resolve_api_key(self.PROVIDER, entry.api_key)
        except ConfigurationError:
            return SkillResolution(reason=SkillUnavailableReason.AUTH_FAILED, detail=f"No API key for {self.host}: pass api_key= on the entry or set {self.env_var}.")
        if key.startswith(VIDBYTE_API_KEY_PREFIX):
            return SkillResolution(reason=SkillUnavailableReason.AUTH_FAILED, detail=f"The key for {self.host} is a Vidbyte API key, and a Vidbyte key is never sent to a vendor; pass the vendor's own key as api_key= or in {self.env_var}.")
        if not (key.isascii() and key.isprintable()):
            return SkillResolution(reason=SkillUnavailableReason.AUTH_FAILED, detail=f"The key for {self.host} holds a character an HTTP header cannot carry (only printable ASCII is allowed); fix the entry's api_key= or {self.env_var}.")
        return key

    def _content_url(self, entry: VendorSkillT, version: str) -> str:
        # The id and version are each one encoded path segment.
        return f"{self.base_url}/skills/{quote(entry.skill_id, safe='')}/versions/{quote(version, safe='')}/content"

    def _record_url(self, entry: VendorSkillT) -> str:
        # The skill record names the newest version.
        return f"{self.base_url}/skills/{quote(entry.skill_id, safe='')}"

    @staticmethod
    def _refused_latest(entry: VendorSkillT, answer: HttpResponse | SkillResolution) -> bool:
        # @intent vendor-latest-fallback-trigger
        # Only these three answers mean "latest is not a version here"; an
        # auth, rate-limit, or server failure never triggers the fallback.
        refusals = (HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND, HTTPStatus.UNPROCESSABLE_ENTITY)
        return entry.version == SKILL_VENDOR_LATEST_VERSION and isinstance(answer, HttpResponse) and answer.status_code in refusals

    def _classify(self, answer: HttpResponse | SkillResolution, entry: VendorSkillT, version: str, step: SkillFetchStep) -> HttpResponse | SkillResolution:
        # @intent vendor-status-map
        # A 2xx answer passes through; every other status becomes a reason
        # that names its fix, looked up by the integer status because
        # HTTPStatus(529) raises. A version the skill record named that is
        # missing means the content route itself was not found (A-1).
        if isinstance(answer, SkillResolution):
            return answer
        status = answer.status_code
        if HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES:
            return answer
        named = step is SkillFetchStep.VENDOR_CONTENT and version != entry.version
        missing = {
            SkillFetchStep.VENDOR_METADATA: f"{self.host} has no skill {entry.skill_id} (HTTP {status} for its skill record); check skill_id= and that the key belongs to the workspace that owns it.",
            SkillFetchStep.VENDOR_CONTENT: f"Skill {entry.skill_id} exists on {self.host} and its record names version {version}, but its content route was not found (HTTP {status})." if named else f"Skill {entry.skill_id} version {version} was not found on {self.host} (HTTP {status}); check skill_id= and version=. If both are right, the content route itself may be the cause.",
        }[step]
        reasons: dict[int, tuple[SkillUnavailableReason, str]] = {
            HTTPStatus.BAD_REQUEST: (SkillUnavailableReason.NOT_FOUND, missing),
            HTTPStatus.NOT_FOUND: (SkillUnavailableReason.NOT_FOUND, missing),
            HTTPStatus.UNPROCESSABLE_ENTITY: (SkillUnavailableReason.NOT_FOUND, missing),
            HTTPStatus.UNAUTHORIZED: (SkillUnavailableReason.AUTH_FAILED, f"{self.host} refused the API key (HTTP 401); fix the entry's api_key= or {self.env_var}."),
            HTTPStatus.FORBIDDEN: (SkillUnavailableReason.AUTH_FAILED, f"{self.host} refused the API key for skill {entry.skill_id} (HTTP 403); fix the entry's api_key= or {self.env_var}."),
            HTTPStatus.TOO_MANY_REQUESTS: (SkillUnavailableReason.RATE_LIMITED, f"{self.host} rate-limited {step.value} for skill {entry.skill_id} (HTTP 429); retried on the next run."),
        }
        reason, detail = reasons.get(status, (SkillUnavailableReason.FETCH_FAILED, f"{self.host} answered {step.value} for skill {entry.skill_id} with HTTP {status}; retried on the next run."))
        return SkillResolution(reason=reason, detail=detail)

    def _record_version(self, record: HttpResponse, entry: VendorSkillT) -> str | SkillResolution:
        # @intent vendor-latest-fallback-record
        # latest_version wins over latest_version_id; an integer becomes
        # decimal text and a bool is not a version. A record without a
        # usable version is the vendor's permanent answer.
        try:
            data = json.loads(record.raw_bytes or b"")
        except (ValueError, RecursionError):
            data = None
        fields = data if isinstance(data, dict) else {}
        for field_name in SKILL_VENDOR_LATEST_VERSION_FIELDS:
            value = fields.get(field_name)
            if type(value) is int:
                return str(value)
            if isinstance(value, str) and value.strip():
                return value
        return SkillResolution(reason=SkillUnavailableReason.INVALID_SKILL, detail=f"{self.host} gave an unexpected answer for the skill record of {entry.skill_id}: it names no usable latest_version or latest_version_id.")

    def _skill_markdown(self, body: bytes) -> bytes | SkillResolution:
        # @intent vendor-archive-read
        # A bare SKILL.md is used as is (capped). A zip is read in memory:
        # exactly one SKILL.md at the root or one folder deep, not
        # encrypted, stored or deflated only (the bzip2 and lzma decoders
        # never see untrusted bytes), and its declared size checked before
        # it is inflated. Every corrupt-archive error becomes INVALID_SKILL.
        if body.removeprefix(codecs.BOM_UTF8).startswith(SKILL_MARKDOWN_DELIMITER.encode()):
            if len(body) > SKILL_MARKDOWN_MAX_BYTES:
                return SkillResolution(reason=SkillUnavailableReason.TOO_LARGE, detail=f"The SKILL.md from {self.host} is {len(body)} bytes, over the {SKILL_MARKDOWN_MAX_BYTES}-byte SKILL_MARKDOWN_MAX_BYTES cap.")
            return body
        if not body.startswith(SKILL_ARCHIVE_MAGIC):
            return SkillResolution(reason=SkillUnavailableReason.INVALID_SKILL, detail=f"The content answer from {self.host} is neither a SKILL.md file nor a zip archive.")
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                members = [info for info in archive.infolist() if PurePosixPath(info.filename).name.lower() == SKILL_MARKDOWN_FILE_NAME.lower() and len(PurePosixPath(info.filename).parent.parts) <= SKILL_ARCHIVE_MAX_DEPTH]
                match members:
                    case [member] if member.flag_bits & SKILL_ARCHIVE_ENCRYPTED_FLAG or member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                        return SkillResolution(reason=SkillUnavailableReason.INVALID_SKILL, detail=f"The SKILL.md in the zip archive from {self.host} is encrypted or compressed with a method other than stored or deflate.")
                    case [member] if member.file_size > SKILL_MARKDOWN_MAX_BYTES:
                        return SkillResolution(reason=SkillUnavailableReason.TOO_LARGE, detail=f"The SKILL.md in the zip archive from {self.host} declares {member.file_size} bytes, over the {SKILL_MARKDOWN_MAX_BYTES}-byte SKILL_MARKDOWN_MAX_BYTES cap.")
                    case [member]:
                        return archive.read(member)
                    case _:
                        return SkillResolution(reason=SkillUnavailableReason.INVALID_SKILL, detail=f"The zip archive from {self.host} holds {len(members)} SKILL.md files at its root or one folder deep; exactly one is required.")
        except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, ValueError):
            return SkillResolution(reason=SkillUnavailableReason.INVALID_SKILL, detail=f"The zip archive from {self.host} is damaged and could not be read.")


__all__ = ["VendorSkillResolver", "VendorSkillT"]
