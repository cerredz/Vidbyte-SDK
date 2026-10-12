"""FILE: vidbyte/lib/dataclasses/skills.py

PURPOSE: Defines the immutable data contracts for agent skills: the resolved `SkillDocument` (plain skill text JevAgent selects before its main loop), the declarative skill entries that say where a SKILL.md comes from (`SkillEntry` and its six subclasses, one per source), and the `SkillResolution` a loader returns for each entry (a document, or a reason with an explanation).
ROLE IN CODEBASE: JevAlignmentSettings accepts entries and documents and normalizes strings into documents; the agent-agnostic loader in vidbyte/agents/skills/ turns entries into resolutions; JevSkillsPreload sends document fields as decision state, injects selected text into one run's context, and reports unresolved entries with their reason.
ARCHITECTURE NOTE: Data and validation only. No record reads a file, an environment variable, or the network: `LocalSkill.path` and `SkillsShSkill.directory` are pinned to absolute paths with `Path.absolute()`, which reads only the working folder name. Each entry subclass fixes its read-only `type` with `field(init=False)` and validates its own fields in the `_validate_source` hook, which the base `__post_init__` calls after checking `name`.
FUNCTION INVENTORY:
    SkillDocument.__post_init__() -> None: validates required text and optional source while leaving every accepted string unchanged.
    SkillText.require / require_optional / require_segment: shared non-blank, optional, and one-path-segment text checks that name the failing Class.field.
    SkillText.require_version / require_folder: the vendor version check (text, with a hint for an integer) and the folder check that returns the folder pinned to an absolute Path; each has one owner here, shared by the two vendor entries and the two folder entries.
    SkillEntry.__post_init__() -> None: checks `name`, then calls `_validate_source()`; the base hook raises because only the six subclasses are usable entries.
    InlineSkill, LocalSkill, SkillsShSkill, GitHubSkill, AnthropicSkill, OpenAISkill._validate_source() -> None: per-source field checks (section 9.1 of the spec).
    SkillResolution.__post_init__() -> None: exactly one of a document, or a reason with a non-blank detail; `transient` is derived from the reason.
COMMON MODIFICATION PATTERNS: A new source adds its `SkillSourceType` member, one entry subclass here that redeclares `type` with `init=False` and its member as default and overrides `_validate_source`, its resolver module in vidbyte/agents/skills/, the loader map entry, and the exports. A new field on an entry validates in that entry's `_validate_source`.
WHAT NOT TO DO:
    1. Do not normalize, trim, or rewrite a SkillDocument body or an inline entry's text.
    2. Do not read files, environment variables, or the network from a record; resolution belongs to vidbyte/agents/skills/.
    3. Do not call `super().__post_init__()` from an entry subclass; use the `_validate_source` hook.
    4. Do not show a token or API key in a repr or an error message; secret fields are `repr=False`.
KNOWN EDGE CASES: Slotted dataclass subclasses are rebuilt as new classes, so a zero-argument `super()` inside them raises TypeError on Python 3.11 and 3.13; the template hook avoids it. Nonblank validation uses whitespace only to reject empty values; accepted strings are stored exactly. A name used as a folder must be one path segment: no `/`, `\\`, `:` (a Windows drive-relative name), or NUL, and not `.` or `..`. A GitHub `path` of `"."` (a SKILL.md at the repository root) is rejected. Secrets take part in equality and hashing, so two entries that differ only by token are different entries.
RELATED DOCS: `docs/design/jev-skills-preload.md`, `docs/spec/jev-skill-sources/spec.md`, `vidbyte/agents/skills/README.md`, and `tests/features/jev_skills_preload/FEATURE.md`.
TESTS: `tests/test_jev_skill_preload.py`; `tests/features/jev_skills_preload/test_skill_sources_entries.py`; `tests/features/jev_skills_preload/test_skill_sources_contract.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from vidbyte.lib.constants.skills import (
    GITHUB_REPO_PATTERN,
    SKILL_MARKDOWN_FILE_NAME,
    SKILL_NAME_FORBIDDEN_CHARACTERS,
    SKILL_PATH_SPECIAL_SEGMENTS,
    SKILL_TRANSIENT_REASONS,
    SKILL_VENDOR_LATEST_VERSION,
    SKILLS_SH_DEFAULT_DIRECTORY,
)
from vidbyte.lib.enums.skills import SkillSourceType, SkillUnavailableReason
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class SkillDocument:
    """One caller-supplied skill body and the metadata used to identify it."""

    name: str
    description: str
    text: str
    source: str | None = None

    def __post_init__(self) -> None:
        # @intent preserve-caller-skill-text
        # Relevance scoring and prompt injection must see the exact body the caller configured. Trimming may
        # silently change code blocks, indentation-sensitive examples, or meaningful leading/trailing text.
        """Validate metadata while retaining every supplied string exactly."""
        for field_name in ("name", "description", "text"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ConfigurationError(f"SkillDocument.{field_name} must be non-blank text.")
        if self.source is not None and (not isinstance(self.source, str) or not self.source.strip()):
            raise ConfigurationError("SkillDocument.source must be None or non-blank text.")


class SkillText:
    """Shared text checks for skill entries; every message names the failing Class.field."""

    @staticmethod
    def require(value: object, field_name: str) -> str:
        # Returns non-blank text unchanged, raising for anything else.
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"{field_name} must be non-blank text.")
        return value

    @staticmethod
    def require_optional(value: object, field_name: str) -> None:
        # Accepts None (use the default) or non-blank text.
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ConfigurationError(f"{field_name} must be None or non-blank text.")

    @staticmethod
    def require_segment(value: object, field_name: str) -> None:
        # A name that becomes a folder must be one path segment, so it
        # cannot climb out of the skills folder or, on Windows, name a
        # drive-relative path.
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"{field_name} must be non-blank text.")
        if value in SKILL_PATH_SPECIAL_SEGMENTS or any(character in value for character in SKILL_NAME_FORBIDDEN_CHARACTERS):
            raise ConfigurationError(f"{field_name} must be one folder name: no '/', '\\', ':', or NUL, and not '.' or '..'.")

    @staticmethod
    def require_version(value: object, field_name: str) -> None:
        # Versions are text in the vendor's URL; an integer, a common
        # slip, gets a hint to pass it as text.
        if type(value) is int:
            raise ConfigurationError(f'{field_name} must be text; pass "{value}".')
        SkillText.require(value, field_name)

    @staticmethod
    def require_folder(value: object, field_name: str) -> Path:
        # Pins a relative folder to the working folder now, so a later
        # chdir does not move the skill; nothing on disk is read here.
        if not isinstance(value, (str, Path)) or value == "":
            raise ConfigurationError(f"{field_name} must be a non-empty str or Path naming a folder.")
        return Path(value).absolute()


@dataclass(frozen=True, slots=True)
class SkillEntry:
    """Base of the declarative skill entries; construct one of its six subclasses instead."""

    name: str
    type: SkillSourceType = field(init=False)

    def __post_init__(self) -> None:
        # @intent skill-entry-template-hook
        # Slotted subclasses cannot call super().__post_init__(), so the
        # base checks the shared name and then hands over to the
        # subclass's own field checks.
        SkillText.require(self.name, f"{type(self).__name__}.name")
        self._validate_source()

    def _validate_source(self) -> None:
        # The base has no source, so it is never a usable entry.
        raise ConfigurationError("SkillEntry is a base class; use InlineSkill, LocalSkill, SkillsShSkill, GitHubSkill, AnthropicSkill, or OpenAISkill.")


@dataclass(frozen=True, slots=True)
class InlineSkill(SkillEntry):
    """A skill whose description and text are written in the settings."""

    description: str
    text: str
    type: SkillSourceType = field(default=SkillSourceType.INLINE, init=False)

    def _validate_source(self) -> None:
        # The text is kept exactly as written; only blank values are refused.
        SkillText.require(self.description, "InlineSkill.description")
        SkillText.require(self.text, "InlineSkill.text")


@dataclass(frozen=True, slots=True)
class LocalSkill(SkillEntry):
    """A skill folder on this machine; `path` names the folder that holds SKILL.md."""

    path: str | Path
    type: SkillSourceType = field(default=SkillSourceType.LOCAL, init=False)

    def _validate_source(self) -> None:
        # The folder is pinned to an absolute path, and it must be the
        # folder that holds SKILL.md, never the file itself.
        folder = SkillText.require_folder(self.path, "LocalSkill.path")
        if folder.name.lower() == SKILL_MARKDOWN_FILE_NAME.lower():
            raise ConfigurationError(f"LocalSkill.path must name the folder that holds {SKILL_MARKDOWN_FILE_NAME}, not the file itself.")
        object.__setattr__(self, "path", folder)


@dataclass(frozen=True, slots=True)
class SkillsShSkill(SkillEntry):
    """A skill installed with `npx skills add <source> --skill <name>` under `directory`."""

    source: str
    directory: str | Path = SKILLS_SH_DEFAULT_DIRECTORY
    type: SkillSourceType = field(default=SkillSourceType.SKILLS_SH, init=False)

    def _validate_source(self) -> None:
        # The name becomes a folder under directory, so it must be one
        # segment; the directory is pinned like LocalSkill.path.
        SkillText.require_segment(self.name, "SkillsShSkill.name")
        SkillText.require(self.source, "SkillsShSkill.source")
        object.__setattr__(self, "directory", SkillText.require_folder(self.directory, "SkillsShSkill.directory"))


@dataclass(frozen=True, slots=True)
class GitHubSkill(SkillEntry):
    """A skill folder in a GitHub repository, read at `ref` (default HEAD) with an optional token."""

    repo: str
    ref: str | None = None
    path: str | None = None
    token: str | None = field(default=None, repr=False)
    type: SkillSourceType = field(default=SkillSourceType.GITHUB, init=False)

    def _validate_source(self) -> None:
        # @intent github-entry-shape
        # repo must be a bare owner/repo so a pasted URL or credential
        # never reaches a request; path must stay below the repository
        # root and name a folder, never SKILL.md itself.
        SkillText.require_segment(self.name, "GitHubSkill.name")
        if not isinstance(self.repo, str) or GITHUB_REPO_PATTERN.fullmatch(self.repo) is None or self.repo.split("/")[1] in SKILL_PATH_SPECIAL_SEGMENTS:
            raise ConfigurationError("GitHubSkill.repo must be 'owner/repo' (letters, digits, '-', and in the repository also '.' and '_').")
        SkillText.require_optional(self.ref, "GitHubSkill.ref")
        SkillText.require_optional(self.token, "GitHubSkill.token")
        if self.path is None:
            return
        segments = self.path.split("/") if isinstance(self.path, str) else [""]
        if "\\" in str(self.path) or any(not segment or segment in SKILL_PATH_SPECIAL_SEGMENTS for segment in segments) or segments[-1].lower() == SKILL_MARKDOWN_FILE_NAME.lower():
            raise ConfigurationError("GitHubSkill.path must name a folder below the repository root, such as 'skills/pdf': '/'-separated, no leading '/', no '\\', '.', '..', or empty segments, and not SKILL.md itself.")


@dataclass(frozen=True, slots=True)
class AnthropicSkill(SkillEntry):
    """A skill uploaded to Anthropic's Skills API, read at `version` (default latest)."""

    skill_id: str
    version: str = SKILL_VENDOR_LATEST_VERSION
    api_key: str | None = field(default=None, repr=False)
    type: SkillSourceType = field(default=SkillSourceType.ANTHROPIC, init=False)

    def _validate_source(self) -> None:
        # Versions are text in the vendor's URL; an integer gets a hint.
        SkillText.require(self.skill_id, "AnthropicSkill.skill_id")
        SkillText.require_version(self.version, "AnthropicSkill.version")
        SkillText.require_optional(self.api_key, "AnthropicSkill.api_key")


@dataclass(frozen=True, slots=True)
class OpenAISkill(SkillEntry):
    """A skill uploaded to OpenAI's Skills API, read at `version` (default latest)."""

    skill_id: str
    version: str = SKILL_VENDOR_LATEST_VERSION
    api_key: str | None = field(default=None, repr=False)
    type: SkillSourceType = field(default=SkillSourceType.OPENAI, init=False)

    def _validate_source(self) -> None:
        # Versions are text in the vendor's URL; an integer gets a hint.
        SkillText.require(self.skill_id, "OpenAISkill.skill_id")
        SkillText.require_version(self.version, "OpenAISkill.version")
        SkillText.require_optional(self.api_key, "OpenAISkill.api_key")


@dataclass(frozen=True, slots=True)
class SkillResolution:
    """What loading one entry produced: a document, or a reason with an explanation."""

    document: SkillDocument | None = None
    reason: SkillUnavailableReason | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        # A loaded entry carries no reason; an unloaded one says why.
        if self.document is not None:
            if not isinstance(self.document, SkillDocument) or self.reason is not None or self.detail is not None:
                raise ConfigurationError("SkillResolution.document must be a SkillDocument, with reason and detail left None.")
            return
        if not isinstance(self.reason, SkillUnavailableReason):
            raise ConfigurationError("SkillResolution.reason must be a SkillUnavailableReason when document is None.")
        SkillText.require(self.detail, "SkillResolution.detail")

    @property
    def transient(self) -> bool:
        """Whether the reason may clear by itself, so the next run tries again."""
        return self.reason in SKILL_TRANSIENT_REASONS


__all__ = [
    "AnthropicSkill",
    "GitHubSkill",
    "InlineSkill",
    "LocalSkill",
    "OpenAISkill",
    "SkillDocument",
    "SkillEntry",
    "SkillResolution",
    "SkillText",
    "SkillsShSkill",
]
