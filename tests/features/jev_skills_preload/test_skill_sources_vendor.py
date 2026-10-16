"""FILE: tests/features/jev_skills_preload/test_skill_sources_vendor.py

PURPOSE: Pin AnthropicSkill and OpenAISkill loading: the version-content download read in memory as a zip or a bare SKILL.md, each vendor's headers and key rules, the "latest" fallback through the skill record, the status map, missing keys, size caps, and every malformed archive ending as data, including a seeded corruption sweep.
ROLE IN CODEBASE: Covers spec AC-8, AC-9, AC-19, AC-25, AC-26, AC-28, AC-29, FR-10, FR-11, D-19, D-20, D-21, D-29 and EC-75 to EC-91, EC-102, EC-112, EC-115 for vidbyte/agents/skills/vendor.py, anthropic.py, and openai.py through vidbyte/agents/skills/loader.py, plus one JevAgent run for AC-28.
ARCHITECTURE NOTE: Archives are built in memory with the real zipfile module and then damaged byte by byte where a case needs it; the conftest's URL-routed transport fake answers every request, so the real SkillFetch, the real zip reading, and SkillMarkdown all run.
FUNCTION INVENTORY: test_anthropic_archive_loads_only_its_skill_md_with_vendor_headers; test_openai_archive_with_a_root_skill_md_loads_with_a_bearer_key; test_latest_refused_downloads_the_version_the_skill_record_names; test_latest_falls_back_only_after_a_refusal; test_named_version_missing_says_the_content_route_was_not_found; test_unusable_skill_record_is_remembered; test_explicit_version_status_is_mapped; test_missing_key_is_auth_failed_without_a_request_and_remembered; test_key_precedence_and_stripping; test_bare_skill_md_body_loads; test_bare_skill_md_cap_is_inclusive; test_member_name_is_matched_case_insensitively_one_folder_deep; test_unreadable_archive_is_invalid_and_remembered; test_size_caps_refuse_bombs_and_huge_downloads; test_corrupt_archives_never_escape_a_run; test_mutated_archives_end_as_a_document_invalid_or_too_large.
COMMON MODIFICATION PATTERNS: A new archive problem adds a builder and a row to UNREADABLE_ARCHIVES; a new vendor adds a Vendor row and joins every vendor-parametrized test.
WHAT NOT TO DO IN THIS FILE: 1. Do not extract archives to disk or patch zipfile; the reader must survive real corrupt bytes. 2. Do not use real keys; every key here is an obvious fake.
KNOWN EDGE CASES: zipfile raises ValueError for a negative seek and UnicodeDecodeError for a UTF-8-flagged name over invalid bytes, both outside BadZipFile; a member that under-declares its size fails its CRC check. 529 is not retried by the transport, 409, 429, and 5xx statuses in its list are.
RELATED DOCS: docs/spec/jev-skill-sources/spec.md (sections 6.3 AnthropicSkill and OpenAISkill, 8.1 D-19 and D-20, 9.2 URLs and failure mapping, 13 archives)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_skills_preload/test_skill_sources_vendor.py
"""

from __future__ import annotations

import io
import json
import random
import struct
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import pytest

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte.agents.skills.loader import SkillLoader
    from vidbyte.lib.constants.skills import (
        SKILL_DOWNLOAD_MAX_BYTES,
        SKILL_MARKDOWN_MAX_BYTES,
    )

    from vidbyte import (
        AnthropicSkill,
        JevSkillStatus,
        OpenAISkill,
        SkillUnavailableReason,
    )
except ImportError as missing:  # red until the feature lands; the rest of the suite must still collect
    FEATURE_MISSING = missing

BOM = b"\xef\xbb\xbf"
BODY_MARKER = "UPSTREAM-BODY-MARKER-4e1d"
SKILL = b"---\nname: release-notes\ndescription: Writes release notes.\n---\nGroup changes by area.\n"
SKILL_TEXT = "Group changes by area.\n"


@pytest.fixture(autouse=True)
def _feature_present() -> None:
    # Fails every test at setup with the import error until the feature exists, instead of skipping it; the
    # traceback is reset so repeated raises of the one stored error do not grow its traceback test after test.
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


@dataclass(frozen=True)
class Vendor:
    """One vendor's fixed host, key variable, and entry class, so tests can run against both."""

    kind: str
    base: str
    env: str

    def entry(self, **fields: Any) -> Any:
        return (AnthropicSkill if self.kind == "anthropic" else OpenAISkill)(**fields)

    def content(self, skill_id: str, version: str) -> str:
        return f"{self.base}/skills/{quote(skill_id, safe='')}/versions/{quote(version, safe='')}/content"

    def metadata(self, skill_id: str) -> str:
        return f"{self.base}/skills/{quote(skill_id, safe='')}"

    def sent_key(self, headers: dict[str, str]) -> str | None:
        # The key as the vendor receives it: x-api-key for Anthropic, a bearer token for OpenAI.
        if self.kind == "anthropic":
            return headers.get("x-api-key")
        return headers["authorization"].removeprefix("Bearer ") if "authorization" in headers else None


VENDORS = {
    "anthropic": Vendor("anthropic", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY"),
    "openai": Vendor("openai", "https://api.openai.com/v1", "OPENAI_API_KEY"),
}
BOTH = pytest.mark.parametrize("kind", sorted(VENDORS))


def make_zip(members: dict[str, bytes], compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    # A fixed timestamp keeps the bytes, and so the seeded corruption sweep, identical on every run.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = compression
            info.external_attr = 0o600 << 16
            archive.writestr(info, data)
    return buffer.getvalue()


def _headers(data: bytes | bytearray) -> list[tuple[int, int, int, bytes]]:
    # (position, flag offset, name offset, name) for every local and central header.
    found = []
    for signature, flag_at, length_at, name_at in ((b"PK\x03\x04", 6, 26, 30), (b"PK\x01\x02", 8, 28, 46)):
        position = data.find(signature)
        while position != -1:
            length = struct.unpack_from("<H", data, position + length_at)[0]
            found.append((position, flag_at, name_at, bytes(data[position + name_at : position + name_at + length])))
            position = data.find(signature, position + 4)
    return found


def set_flag(data: bytes, member: str, bit: int) -> bytes:
    # zipfile clears flag bits it does not own when writing, so the bit is set in the written headers.
    patched = bytearray(data)
    for position, flag_at, _, name in _headers(patched):
        if name == member.encode():
            struct.pack_into("<H", patched, position + flag_at, struct.unpack_from("<H", patched, position + flag_at)[0] | bit)
    return bytes(patched)


def utf8_flag_over_invalid_name(data: bytes, member: str) -> bytes:
    # Replaces a member's name bytes with invalid UTF-8 of the same length and claims UTF-8 with flag 0x800.
    patched = bytearray(set_flag(data, member, 0x800))
    invalid = member.encode()[:-4] + b"\xff\xfe\xfd\xfc"
    for position, _, name_at, name in _headers(patched):
        if name == member.encode():
            patched[position + name_at : position + name_at + len(invalid)] = invalid
    return bytes(patched)


def negative_offset(data: bytes) -> bytes:
    # Moves the central directory's recorded start past its real start, so every member offset goes negative.
    patched = bytearray(data)
    end = patched.rfind(b"PK\x05\x06")
    struct.pack_into("<I", patched, end + 16, struct.unpack_from("<I", patched, end + 16)[0] + 1000)
    return bytes(patched)


def under_declared_size(data: bytes, shrink: int = 5) -> bytes:
    # The member claims to be smaller than it is; the stdlib reads only the claimed bytes and fails the CRC check.
    patched = bytearray(data)
    for position, flag_at, _, _ in _headers(patched):
        size_at = position + (22 if flag_at == 6 else 24)
        struct.pack_into("<I", patched, size_at, struct.unpack_from("<I", patched, size_at)[0] - shrink)
    return bytes(patched)


def corrupt_deflate(data: bytes, member: str) -> bytes:
    patched = bytearray(data)
    start = patched.find(b"PK\x03\x04") + 30 + len(member)
    patched[start : start + 4] = b"\xff\xff\xff\xff"
    return bytes(patched)


@pytest.mark.asyncio
async def test_anthropic_archive_loads_only_its_skill_md_with_vendor_headers(fake_http: Any) -> None:
    # AC-8, D-19, D-20: a bundled reference file is never read, and the key travels only as x-api-key.
    vendor = VENDORS["anthropic"]
    archive = make_zip({"release-notes/SKILL.md": SKILL, "release-notes/references/style.md": b"REFERENCE-TEXT"})
    fake_http.answer(vendor.content("skill_01AbCd", "latest"), fake_http.reply(200, archive))
    (resolution,) = await SkillLoader((AnthropicSkill(name="release-notes", skill_id="skill_01AbCd", api_key="sk-ant-api03-FAKE-KEY"),)).load()
    assert resolution.document is not None, resolution
    assert resolution.document.text == SKILL_TEXT and "REFERENCE-TEXT" not in resolution.document.text
    assert (resolution.document.name, resolution.document.description, resolution.document.source) == ("release-notes", "Writes release notes.", "anthropic:skill_01AbCd@latest")
    (request,) = fake_http.sent
    assert request.headers["x-api-key"] == "sk-ant-api03-FAKE-KEY"
    assert (request.headers["anthropic-version"], request.headers["anthropic-beta"]) == ("2023-06-01", "skills-2025-10-02")
    assert "authorization" not in request.headers
    assert request.max_response_bytes == SKILL_DOWNLOAD_MAX_BYTES


@pytest.mark.asyncio
async def test_openai_archive_with_a_root_skill_md_loads_with_a_bearer_key(fake_http: Any) -> None:
    # AC-9, D-19: OpenAI bundles may hold the file at the archive root, in lowercase.
    vendor = VENDORS["openai"]
    fake_http.answer(vendor.content("skill_abc", "latest"), fake_http.reply(200, make_zip({"skill.md": SKILL, "notes.txt": b"other"})))
    (resolution,) = await SkillLoader((OpenAISkill(name="release-notes", skill_id="skill_abc", api_key="sk-proj-FAKE-KEY"),)).load()
    assert resolution.document is not None and resolution.document.text == SKILL_TEXT
    assert resolution.document.source == "openai:skill_abc@latest"
    (request,) = fake_http.sent
    assert request.headers["authorization"] == "Bearer sk-proj-FAKE-KEY"
    assert "x-api-key" not in request.headers


# (case, refusal status, skill record, version the resolver must download)
FALLBACK_ROWS = [
    ("404 then latest_version", 404, {"id": "skill_01AbCd", "latest_version": "1759178010641129"}, "1759178010641129"),
    ("400 then latest_version", 400, {"latest_version": "1759178010641129"}, "1759178010641129"),
    ("422 then latest_version", 422, {"latest_version": "1759178010641129"}, "1759178010641129"),
    ("latest_version_id only", 404, {"latest_version_id": "skillver_9"}, "skillver_9"),
    ("latest_version wins over latest_version_id", 404, {"latest_version": "7", "latest_version_id": "skillver_9"}, "7"),
    ("integer version", 404, {"latest_version": 1759178010641129}, "1759178010641129"),
]


@BOTH
@pytest.mark.parametrize(("case", "refusal", "record", "version"), FALLBACK_ROWS, ids=[row[0] for row in FALLBACK_ROWS])
@pytest.mark.asyncio
async def test_latest_refused_downloads_the_version_the_skill_record_names(fake_http: Any, kind: str, case: str, refusal: int, record: dict[str, Any], version: str) -> None:
    # AC-19, EC-80, D-19, A-2: one metadata request, then one download of the named version, labelled with it.
    vendor = VENDORS[kind]
    fake_http.answer(vendor.content("skill_01AbCd", "latest"), fake_http.reply(refusal, BODY_MARKER))
    fake_http.answer(vendor.metadata("skill_01AbCd"), fake_http.reply(200, json.dumps(record)))
    fake_http.answer(vendor.content("skill_01AbCd", version), fake_http.reply(200, make_zip({"release-notes/SKILL.md": SKILL})))
    (resolution,) = await SkillLoader((vendor.entry(name="release-notes", skill_id="skill_01AbCd", api_key="sk-FAKE-KEY"),)).load()
    assert resolution.document is not None, resolution
    assert resolution.document.source == f"{kind}:skill_01AbCd@{version}"
    assert fake_http.urls() == [vendor.content("skill_01AbCd", "latest"), vendor.metadata("skill_01AbCd"), vendor.content("skill_01AbCd", version)]
    assert {vendor.sent_key(dict(request.headers)) for request in fake_http.sent} == {"sk-FAKE-KEY"}


@BOTH
@pytest.mark.parametrize(("status", "reason", "attempts"), [(401, "AUTH_FAILED", 1), (503, "FETCH_FAILED", 2), (429, "RATE_LIMITED", 2)])
@pytest.mark.asyncio
async def test_latest_falls_back_only_after_a_refusal(fake_http: Any, kind: str, status: int, reason: str, attempts: int) -> None:
    # D-19: only 400, 404, and 422 mean "latest is not a version here"; the fake raises on an unexpected metadata request.
    vendor = VENDORS[kind]
    fake_http.answer(vendor.content("skill_x", "latest"), fake_http.reply(status, BODY_MARKER))
    (resolution,) = await SkillLoader((vendor.entry(name="x", skill_id="skill_x", api_key="sk-FAKE-KEY"),)).load()
    assert resolution.reason is SkillUnavailableReason[reason]
    assert fake_http.urls() == [vendor.content("skill_x", "latest")] * attempts


@BOTH
@pytest.mark.asyncio
async def test_named_version_missing_says_the_content_route_was_not_found(fake_http: Any, kind: str) -> None:
    # AC-25, A-1: a wrong content-route assumption must read differently from a bad skill id.
    vendor = VENDORS[kind]
    fake_http.answer(vendor.content("skill_01AbCd", "latest"), fake_http.reply(404, BODY_MARKER))
    fake_http.answer(vendor.metadata("skill_01AbCd"), fake_http.reply(200, json.dumps({"id": "skill_01AbCd", "latest_version_id": "skillver_9"})))
    fake_http.answer(vendor.content("skill_01AbCd", "skillver_9"), fake_http.reply(404, BODY_MARKER))
    loader = SkillLoader((vendor.entry(name="release-notes", skill_id="skill_01AbCd", api_key="sk-FAKE-KEY"),))
    (resolution,) = await loader.load()
    assert resolution.reason is SkillUnavailableReason.NOT_FOUND
    assert "content route" in resolution.detail.lower() and "exists" in resolution.detail.lower()
    assert BODY_MARKER not in resolution.detail
    assert fake_http.count(vendor.metadata("skill_01AbCd")) == 1
    await loader.load()
    assert len(fake_http.sent) == 3


# (case, metadata answer status, metadata body, reason)
RECORD_ROWS = [
    ("version is a bool", 200, json.dumps({"latest_version": True}), "INVALID_SKILL"),
    ("version is empty", 200, json.dumps({"latest_version": ""}), "INVALID_SKILL"),
    ("version is blank", 200, json.dumps({"latest_version": "   "}), "INVALID_SKILL"),
    ("version is a float", 200, json.dumps({"latest_version": 1.5}), "INVALID_SKILL"),
    ("version is a list", 200, json.dumps({"latest_version": ["7"]}), "INVALID_SKILL"),
    ("both versions null", 200, json.dumps({"latest_version": None, "latest_version_id": None}), "INVALID_SKILL"),
    ("no version fields", 200, json.dumps({"id": "skill_x"}), "INVALID_SKILL"),
    ("record is a list", 200, json.dumps(["7"]), "INVALID_SKILL"),
    ("record is not json", 200, f"<html>{BODY_MARKER}</html>", "INVALID_SKILL"),
    ("record nests 2000 levels", 200, '{"latest_version": ' + "[" * 2000 + "]" * 2000 + "}", "INVALID_SKILL"),
    ("record not found", 404, BODY_MARKER, "NOT_FOUND"),
]


@BOTH
@pytest.mark.parametrize(("case", "status", "body", "reason"), RECORD_ROWS, ids=[row[0] for row in RECORD_ROWS])
@pytest.mark.asyncio
async def test_unusable_skill_record_is_remembered(fake_http: Any, kind: str, case: str, status: int, body: str, reason: str) -> None:
    # EC-80, EC-112, D-29: a record without a usable version is the vendor's permanent answer, and must never crash the run.
    vendor = VENDORS[kind]
    fake_http.answer(vendor.content("skill_x", "latest"), fake_http.reply(404, BODY_MARKER))
    fake_http.answer(vendor.metadata("skill_x"), fake_http.reply(status, body))
    loader = SkillLoader((vendor.entry(name="x", skill_id="skill_x", api_key="sk-FAKE-KEY"),))
    (resolution,) = await loader.load()
    assert resolution.reason is SkillUnavailableReason[reason]
    assert resolution.detail.strip() and BODY_MARKER not in resolution.detail
    if reason == "INVALID_SKILL":
        assert "unexpected" in resolution.detail.lower(), resolution.detail
    assert fake_http.urls() == [vendor.content("skill_x", "latest"), vendor.metadata("skill_x")]
    await loader.load()
    assert len(fake_http.sent) == 2


# (case, status, response headers, reason, remembered, attempts, words the detail must hold; "{env}" is the key variable)
VENDOR_STATUS_ROWS = [
    ("400", 400, {}, "NOT_FOUND", True, 1, ("skill_x", "2")),
    ("404", 404, {}, "NOT_FOUND", True, 1, ("skill_x", "2", "content route")),
    ("422", 422, {}, "NOT_FOUND", True, 1, ("skill_x", "2")),
    ("401", 401, {}, "AUTH_FAILED", True, 1, ("{env}",)),
    ("403", 403, {}, "AUTH_FAILED", True, 1, ("{env}",)),
    ("403 with retry-after", 403, {"Retry-After": "30"}, "AUTH_FAILED", True, 1, ()),
    ("429", 429, {}, "RATE_LIMITED", False, 2, ("next run",)),
    ("409 retried", 409, {}, "FETCH_FAILED", False, 2, ("409",)),
    ("500", 500, {}, "FETCH_FAILED", False, 2, ("500",)),
    ("503", 503, {}, "FETCH_FAILED", False, 2, ("503",)),
    ("529 overloaded", 529, {}, "FETCH_FAILED", False, 1, ("529",)),
    ("418", 418, {}, "FETCH_FAILED", False, 1, ("418",)),
    ("301", 301, {"Location": "https://example.invalid/"}, "FETCH_FAILED", False, 1, ("301",)),
    ("302", 302, {"Location": "https://example.invalid/"}, "FETCH_FAILED", False, 1, ("302",)),
    ("307", 307, {"Location": "https://example.invalid/"}, "FETCH_FAILED", False, 1, ("307",)),
    ("308", 308, {"Location": "https://example.invalid/"}, "FETCH_FAILED", False, 1, ("308",)),
]


@BOTH
@pytest.mark.parametrize(("case", "status", "headers", "reason", "remembered", "attempts", "hints"), VENDOR_STATUS_ROWS, ids=[row[0] for row in VENDOR_STATUS_ROWS])
@pytest.mark.asyncio
async def test_explicit_version_status_is_mapped(monkeypatch: pytest.MonkeyPatch, fake_http: Any, kind: str, case: str, status: int, headers: dict[str, str], reason: str, remembered: bool, attempts: int, hints: tuple[str, ...]) -> None:
    # EC-78, EC-79, EC-81, EC-82, EC-91, D-10, D-11: an explicit version never triggers the latest fallback.
    vendor = VENDORS[kind]
    monkeypatch.setenv(vendor.env, "sk-FAKE-ENV-KEY")
    fake_http.answer(vendor.content("skill_x", "2"), fake_http.reply(status, f"<html>{BODY_MARKER}</html>", headers))
    loader = SkillLoader((vendor.entry(name="x", skill_id="skill_x", version="2"),))
    (resolution,) = await loader.load()
    assert resolution.reason is SkillUnavailableReason[reason]
    assert fake_http.urls() == [vendor.content("skill_x", "2")] * attempts
    for hint in hints:
        assert hint.replace("{env}", vendor.env).lower() in resolution.detail.lower(), resolution.detail
    assert BODY_MARKER not in resolution.detail
    await loader.load()
    assert (len(fake_http.sent) == attempts) is remembered


@BOTH
@pytest.mark.parametrize("env_value", [None, "   "], ids=["unset", "blank"])
@pytest.mark.asyncio
async def test_missing_key_is_auth_failed_without_a_request_and_remembered(monkeypatch: pytest.MonkeyPatch, fake_http: Any, kind: str, env_value: str | None) -> None:
    # EC-76, EC-102, Q-1: no request without a key, and a key added later needs a new agent.
    vendor = VENDORS[kind]
    if env_value is not None:
        monkeypatch.setenv(vendor.env, env_value)
    loader = SkillLoader((vendor.entry(name="x", skill_id="skill_x"),))
    (resolution,) = await loader.load()
    assert resolution.reason is SkillUnavailableReason.AUTH_FAILED
    assert "api_key=" in resolution.detail and vendor.env in resolution.detail
    monkeypatch.setenv(vendor.env, "sk-FAKE-LATE-KEY")
    assert (await loader.load())[0].reason is SkillUnavailableReason.AUTH_FAILED
    assert fake_http.sent == []


@BOTH
@pytest.mark.parametrize(
    ("entry_key", "env_key", "sent"),
    [("  sk-FAKE-ENTRY  ", "sk-FAKE-ENV", "sk-FAKE-ENTRY"), (None, "\tsk-FAKE-ENV\n", "sk-FAKE-ENV")],
    ids=["entry key wins and is stripped", "env key is stripped"],
)
@pytest.mark.asyncio
async def test_key_precedence_and_stripping(monkeypatch: pytest.MonkeyPatch, fake_http: Any, kind: str, entry_key: str | None, env_key: str, sent: str) -> None:
    # D-19, D-30: the entry's key, else the provider variable; the stripped value is the one sent.
    vendor = VENDORS[kind]
    monkeypatch.setenv(vendor.env, env_key)
    fake_http.answer(vendor.content("skill_x", "1"), fake_http.reply(200, make_zip({"x/SKILL.md": SKILL})))
    (resolution,) = await SkillLoader((vendor.entry(name="x", skill_id="skill_x", version="1", api_key=entry_key),)).load()
    assert resolution.document is not None, resolution
    (request,) = fake_http.sent
    assert vendor.sent_key(dict(request.headers)) == sent


@BOTH
@pytest.mark.parametrize("body", [BOM + SKILL, SKILL, SKILL.replace(b"\n", b"\r\n")], ids=["bom", "plain", "crlf"])
@pytest.mark.asyncio
async def test_bare_skill_md_body_loads(fake_http: Any, kind: str, body: bytes) -> None:
    # AC-26, EC-83, D-20, A-4: a content answer that is the SKILL.md itself is parsed directly.
    vendor = VENDORS[kind]
    fake_http.answer(vendor.content("skill_x", "1"), fake_http.reply(200, body))
    (resolution,) = await SkillLoader((vendor.entry(name="x", skill_id="skill_x", version="1", api_key="sk-FAKE-KEY"),)).load()
    assert resolution.document is not None, resolution
    assert resolution.document.text == SKILL_TEXT.replace("\n", "\r\n" if b"\r\n" in body else "\n")
    assert resolution.document.source == f"{kind}:skill_x@1"


@BOTH
@pytest.mark.asyncio
async def test_bare_skill_md_cap_is_inclusive(fake_http: Any, kind: str) -> None:
    # AC-29, R-19: a bare body over the SKILL.md cap is remembered as too_large, naming that cap.
    vendor = VENDORS[kind]
    head = b"---\nname: big\ndescription: Big.\n---\n"
    fake_http.answer(vendor.content("skill_at", "1"), fake_http.reply(200, head + b"x" * (SKILL_MARKDOWN_MAX_BYTES - len(head))))
    fake_http.answer(vendor.content("skill_over", "1"), fake_http.reply(200, head + b"x" * (SKILL_MARKDOWN_MAX_BYTES + 1 - len(head))))
    loader = SkillLoader((vendor.entry(name="at", skill_id="skill_at", version="1", api_key="sk-FAKE-KEY"), vendor.entry(name="over", skill_id="skill_over", version="1", api_key="sk-FAKE-KEY")))
    at_cap, over_cap = await loader.load()
    assert at_cap.document is not None
    assert over_cap.reason is SkillUnavailableReason.TOO_LARGE
    assert str(SKILL_MARKDOWN_MAX_BYTES) in over_cap.detail.replace(",", "").replace("_", "") or "SKILL_MARKDOWN_MAX_BYTES" in over_cap.detail, over_cap.detail
    await loader.load()
    assert len(fake_http.sent) == 2


@pytest.mark.parametrize("member", ["SKILL.md", "skill.md", "Folder/Skill.md", "release-notes/SKILL.MD"])
@pytest.mark.asyncio
async def test_member_name_is_matched_case_insensitively_one_folder_deep(fake_http: Any, member: str) -> None:
    # D-20, A-5: exactly one SKILL.md, any case, at the root or one folder deep; other members are ignored.
    vendor = VENDORS["anthropic"]
    fake_http.answer(vendor.content("skill_x", "1"), fake_http.reply(200, make_zip({"Folder/README.md": b"readme", member: SKILL, "Folder/deep/SKILL.txt": b"x"})))
    (resolution,) = await SkillLoader((vendor.entry(name="x", skill_id="skill_x", version="1", api_key="sk-FAKE-KEY"),)).load()
    assert resolution.document is not None and resolution.document.text == SKILL_TEXT


def _encrypted() -> bytes:
    return set_flag(make_zip({"x/SKILL.md": SKILL}, zipfile.ZIP_STORED), "x/SKILL.md", 0x1)


# (case, body, words of which the detail must hold at least one; empty means no wording is pinned)
UNREADABLE_ARCHIVES: list[tuple[str, Callable[[], bytes], tuple[str, ...]]] = [
    ("json body", lambda: json.dumps({"type": "skill_version", "id": BODY_MARKER}).encode(), ("zip",)),
    ("html body", lambda: f"<html>{BODY_MARKER}</html>".encode(), ("zip",)),
    ("empty body", lambda: b"", ("zip",)),
    ("space before the frontmatter", lambda: b" " + SKILL, ("zip",)),
    ("no SKILL.md", lambda: make_zip({"x/README.md": SKILL}), ("0", "no ", "none")),
    ("two SKILL.md", lambda: make_zip({"SKILL.md": SKILL, "x/SKILL.md": SKILL}), ("2", "two")),
    ("SKILL.md two folders deep", lambda: make_zip({"a/b/SKILL.md": SKILL}), ("0", "no ", "none")),
    ("encrypted member", _encrypted, ()),
    ("under-declared size", lambda: under_declared_size(make_zip({"x/SKILL.md": SKILL}, zipfile.ZIP_STORED)), ()),
    ("truncated archive", lambda: make_zip({"x/SKILL.md": SKILL})[:60], ()),
    ("corrupt deflate stream", lambda: corrupt_deflate(make_zip({"x/SKILL.md": SKILL * 20}), "x/SKILL.md"), ()),
    ("lzma member", lambda: make_zip({"x/SKILL.md": SKILL}, zipfile.ZIP_LZMA), ()),
    ("bzip2 member", lambda: make_zip({"x/SKILL.md": SKILL}, zipfile.ZIP_BZIP2), ()),
    ("member is not a SKILL.md", lambda: make_zip({"x/SKILL.md": f"no frontmatter {BODY_MARKER}".encode()}), ()),
    ("member is not utf-8", lambda: make_zip({"x/SKILL.md": SKILL + b"\xff\xfe"}), ()),
]


@pytest.mark.parametrize(("case", "build", "hints"), UNREADABLE_ARCHIVES, ids=[row[0] for row in UNREADABLE_ARCHIVES])
@pytest.mark.asyncio
async def test_unreadable_archive_is_invalid_and_remembered(fake_http: Any, case: str, build: Callable[[], bytes], hints: tuple[str, ...]) -> None:
    # EC-83, EC-85, EC-86, EC-87, EC-88, D-20: the vendor's answer is permanent; an escaping RuntimeError would crash every run.
    vendor = VENDORS["anthropic"]
    fake_http.answer(vendor.content("skill_x", "1"), fake_http.reply(200, build()))
    loader = SkillLoader((vendor.entry(name="x", skill_id="skill_x", version="1", api_key="sk-FAKE-KEY"),))
    (resolution,) = await loader.load()
    assert resolution.reason is SkillUnavailableReason.INVALID_SKILL, resolution
    assert resolution.detail.strip() and BODY_MARKER not in resolution.detail
    assert not hints or any(hint.lower() in resolution.detail.lower() for hint in hints), resolution.detail
    await loader.load()
    assert len(fake_http.sent) == 1


@pytest.mark.asyncio
async def test_size_caps_refuse_bombs_and_huge_downloads(fake_http: Any) -> None:
    # EC-84, EC-87, INV-12: a member declaring more than the SKILL.md cap is refused before it is inflated, and a download over its cap is never held.
    vendor = VENDORS["anthropic"]
    bomb = make_zip({"x/SKILL.md": SKILL + b"x" * SKILL_MARKDOWN_MAX_BYTES})
    assert len(bomb) < 10_000
    fake_http.answer(vendor.content("skill_bomb", "1"), fake_http.reply(200, bomb))
    fake_http.answer(vendor.content("skill_huge", "1"), fake_http.oversized(SKILL_DOWNLOAD_MAX_BYTES + 1))
    loader = SkillLoader((vendor.entry(name="bomb", skill_id="skill_bomb", version="1", api_key="sk-FAKE-KEY"), vendor.entry(name="huge", skill_id="skill_huge", version="1", api_key="sk-FAKE-KEY")))
    bombed, huge = await loader.load()
    assert bombed.reason is SkillUnavailableReason.TOO_LARGE
    assert huge.reason is SkillUnavailableReason.TOO_LARGE
    await loader.load()
    assert len(fake_http.sent) == 2


@pytest.mark.asyncio
async def test_corrupt_archives_never_escape_a_run(fake_http: Any, make_agent: Callable[..., Any], jev: Callable[..., Any]) -> None:
    # AC-28, EC-85, R-16: three archives that make the stdlib raise outside BadZipFile, or reach a decoder the SDK refuses.
    vendor = VENDORS["anthropic"]
    archives = {
        "bzip2-member": make_zip({"x/SKILL.md": SKILL}, zipfile.ZIP_BZIP2),
        "bad-name-bytes": utf8_flag_over_invalid_name(make_zip({"x/SKILL.md": SKILL, "x/XXXX.txt": b"notes"}, zipfile.ZIP_STORED), "x/XXXX.txt"),
        "negative-offset": negative_offset(make_zip({"x/SKILL.md": SKILL}, zipfile.ZIP_STORED)),
    }
    # Non-vacuity: the damaged archives really do make the stdlib raise ValueError subclasses.
    for name in ("bad-name-bytes", "negative-offset"):
        with pytest.raises(ValueError):
            with zipfile.ZipFile(io.BytesIO(archives[name])) as archive:
                archive.read(archive.infolist()[0])
    for name, archive in archives.items():
        fake_http.answer(vendor.content(f"skill_{name}", "1"), fake_http.reply(200, archive))
    jev()
    agent, _ = make_agent([vendor.entry(name=name, skill_id=f"skill_{name}", version="1", api_key="sk-ant-FAKE-KEY") for name in archives])
    reply = await agent.arun("Draft the release notes.")
    assert reply.content == "completed"
    assert [(result.status, result.reason) for result in agent.response.skills.results] == [(JevSkillStatus.UNAVAILABLE, SkillUnavailableReason.INVALID_SKILL)] * 3
    await agent.arun("Draft them again.")
    assert len(fake_http.sent) == 3


def _mutations(compression: int, count: int) -> list[bytes]:
    # The same seeded corruption the spec's fuzz used: one to eight random bytes replaced anywhere in the archive.
    base = make_zip({"fuzz-skill/SKILL.md": b"---\nname: fuzz-skill\ndescription: Survives corruption.\n---\n" + b"Follow the checklist.\n" * 40, "fuzz-skill/references/notes.md": b"extra notes\n" * 20}, compression)
    rng = random.Random(20261012 + compression)
    mutated = []
    for _ in range(count):
        data = bytearray(base)
        for _ in range(rng.randint(1, 8)):
            data[rng.randrange(len(data))] = rng.randrange(256)
        mutated.append(bytes(data))
    return mutated


@pytest.mark.parametrize("compression", [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED], ids=["stored", "deflated"])
@pytest.mark.asyncio
async def test_mutated_archives_end_as_a_document_invalid_or_too_large(fake_http: Any, compression: int) -> None:
    # EC-115, D-20: no corrupted archive may raise out of the load; every one ends as data.
    vendor = VENDORS["anthropic"]
    archives = _mutations(compression, 120)
    for index, archive in enumerate(archives):
        fake_http.answer(vendor.content(f"skill_{index}", "1"), fake_http.reply(200, archive))
    entries = tuple(vendor.entry(name=f"fuzz-{index}", skill_id=f"skill_{index}", version="1", api_key="sk-FAKE-KEY") for index in range(len(archives)))
    resolutions = await SkillLoader(entries).load()
    outcomes = {resolution.reason for resolution in resolutions}
    assert outcomes <= {None, SkillUnavailableReason.INVALID_SKILL, SkillUnavailableReason.TOO_LARGE}, outcomes
    assert SkillUnavailableReason.INVALID_SKILL in outcomes
