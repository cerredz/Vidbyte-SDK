"""FILE: vidbyte/lib/dataclasses/native_threads.py

PURPOSE: Defines the validated records of the harness thread functions: NativeThreadRequest, the checked arguments of one call; GrokThreadConfig, OpencodeThreadConfig and MuseThreadConfig, the per-harness settings a caller may pass; and NativeThreadResult, what a successful call returns.
ROLE IN CODEBASE: NativeThreadRequest is built by the nine public functions under vidbyte/harnesses/native/ (grok/threads.py, opencode/threads.py, muse/threads.py) and read by every step of their flows. The three config records and NativeThreadResult are re-exported from vidbyte.harnesses.native; callers build the configs, the functions return the result.
ARCHITECTURE NOTE: Every check lives in __post_init__ and goes through RecordFieldValidator and RecordFieldConverter (vidbyte/lib/dataclasses/validation.py), so a constructed record is always valid. A refused field raises ConfigurationError whose details["field"] is the public argument name (api_key, skills[2]); the thread functions turn it into a NativeThreadError naming that argument. The workspace and each skill path are checked as given, absolute and existing, and then stored resolved, so a relative path never passes because of the current folder.
FUNCTION INVENTORY: NativeThreadRequest.__post_init__ is the narrated main function; _checked_workspace checks and resolves the workspace; _checked_model checks the model for the harness; _checked_thread_id ties the thread id to the verb; _checked_skills checks, resolves and names each skill folder. GrokThreadConfig, OpencodeThreadConfig, MuseThreadConfig and NativeThreadResult have only __post_init__.
COMMON MODIFICATION PATTERNS: A new config field adds one field and one validator call to its record, and its bound or pattern to vidbyte/lib/constants/native_threads.py. A config record never gets a model field: the model is an argument of every call.
WHAT NOT TO DO IN THIS FILE: 1. Do not read keys from environment variables. 2. Do not put a key value in an error message or its details; name the parameter instead. 3. Do not drop repr=False from a key field. 4. Do not import from vidbyte.harnesses; vidbyte/lib is the bottom layer.
KNOWN EDGE CASES: The prompt cap is NATIVE_PROMPT_MAX_CHARS for opencode, which reads the prompt from stdin, and NATIVE_ARGV_PROMPT_MAX_CHARS for Grok and Muse, which take it on argv; on Windows the Grok and Muse prompt must also fit that cap once quoted and counted in UTF-16 units, the way CreateProcess counts it. A skill item that is not a path is refused naming skills[<i>], while a skill list that is a str or holds too many items is refused naming skills. Two skill folders with the same folder name are refused, because each harness finds a skill by its folder name.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_records.py, tests/features/harness_threads/test_harness_threads_arguments.py
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from vidbyte.lib.constants.native_threads import (
    MUSE_DEFAULT_PATH,
    MUSE_DISTRO_MAX_CHARS,
    MUSE_DISTRO_PATTERN,
    MUSE_PATH_MAX_CHARS,
    MUSE_PATH_PATTERN,
    NATIVE_API_KEY_MAX_CHARS,
    NATIVE_API_KEY_PATTERN,
    NATIVE_ARGV_PROMPT_MAX_CHARS,
    NATIVE_MODEL_MAX_CHARS,
    NATIVE_MODEL_PATTERN,
    NATIVE_NAME_MAX_CHARS,
    NATIVE_NAME_PATTERN,
    NATIVE_PROMPT_MAX_CHARS,
    NATIVE_PROMPT_PATTERN,
    NATIVE_SKILL_FILE_NAME,
    NATIVE_SKILL_NAME_MAX_CHARS,
    NATIVE_SKILL_NAME_PATTERN,
    NATIVE_THREAD_DEFAULT_SECONDS,
    NATIVE_THREAD_ID_MAX_CHARS,
    NATIVE_THREAD_ID_PATTERN,
    NATIVE_THREAD_MAX_SECONDS,
    NATIVE_THREAD_MAX_SKILLS,
    NATIVE_WINDOWS_PLATFORM,
    OPENCODE_MODEL_PATTERN,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.native_threads import (
    GrokPermissionMode,
    GrokReasoningEffort,
    MuseReasoningEffort,
    NativeHarness,
    NativeThreadVerb,
)
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class NativeThreadRequest:
    """The checked arguments of one thread function call; the key never shows in repr.

    workspace is typed Path | str and skills Sequence[str | Path]
    because the record must see the raw values: a relative path
    must be refused before it is resolved, and a bare string is a
    sequence of characters, not a list of skills. After
    __post_init__ workspace is always the resolved Path and skills
    a tuple of resolved Paths.
    """

    harness: NativeHarness
    verb: NativeThreadVerb
    prompt: str
    api_key: str = field(repr=False)
    workspace: Path | str
    model: str | None = None
    skills: Sequence[str | Path] = ()
    thread_id: str | None = None

    def __post_init__(self) -> None:
        # Pin the harness and the verb first, because the prompt cap,
        # the model rule and the thread id rule depend on them.
        object.__setattr__(self, "harness", RecordFieldConverter.to_enum(self.harness, NativeHarness, "harness"))
        object.__setattr__(self, "verb", RecordFieldConverter.to_enum(self.verb, NativeThreadVerb, "verb"))

        # Grok and Muse take the prompt on argv, so they get the
        # smaller cap; opencode reads it from stdin.
        prompt_cap = NATIVE_PROMPT_MAX_CHARS if self.harness is NativeHarness.OPENCODE else NATIVE_ARGV_PROMPT_MAX_CHARS
        RecordFieldValidator.require_text(self.prompt, "prompt", max_chars=prompt_cap, pattern=NATIVE_PROMPT_PATTERN)

        # @intent argv-prompt-fits-the-windows-command-line
        # On Windows a prompt of quotes or emoji within the cap can
        # double once quoted and counted in UTF-16 units, pass the
        # CreateProcess limit and fail as if the CLI were missing, so
        # the quoted argv prompt must fit the same cap (spec EC-3).
        if self.harness is not NativeHarness.OPENCODE and sys.platform == NATIVE_WINDOWS_PLATFORM:
            RecordFieldValidator.require_command_line_units(self.prompt, "prompt", max_units=NATIVE_ARGV_PROMPT_MAX_CHARS)

        # The key is checked under its public name, which the validator
        # never quotes, and the pattern keeps it printable ASCII.
        RecordFieldValidator.require_text(self.api_key, "api_key", max_chars=NATIVE_API_KEY_MAX_CHARS, pattern=NATIVE_API_KEY_PATTERN)

        # Check the paths as given, then store them resolved.
        object.__setattr__(self, "workspace", self._checked_workspace())
        self._checked_model()
        object.__setattr__(self, "skills", self._checked_skills())

        # A run starts a new thread; continue and fork need the one to use.
        self._checked_thread_id()

    def _checked_workspace(self) -> Path:
        # The workspace must be an absolute existing folder as given.
        workspace = RecordFieldConverter.to_path(self.workspace, "workspace")
        RecordFieldValidator.require_directory(workspace, "workspace")
        return workspace.resolve()

    def _checked_model(self) -> None:
        # opencode needs "<provider>/<model>"; Grok and Muse take an
        # optional bare model id.
        if self.harness is NativeHarness.OPENCODE:
            RecordFieldValidator.require_text(self.model, "model", max_chars=NATIVE_MODEL_MAX_CHARS, pattern=OPENCODE_MODEL_PATTERN)
        else:
            RecordFieldValidator.require_optional_text(self.model, "model", max_chars=NATIVE_MODEL_MAX_CHARS, pattern=NATIVE_MODEL_PATTERN)

    def _checked_thread_id(self) -> None:
        # thread_id is None exactly when the verb is run.
        if self.verb is NativeThreadVerb.RUN and self.thread_id is not None:
            raise ConfigurationError(f"thread_id must be None when the verb is {self.verb.value}.", details={"field": "thread_id"})
        if self.verb is not NativeThreadVerb.RUN:
            RecordFieldValidator.require_text(self.thread_id, "thread_id", max_chars=NATIVE_THREAD_ID_MAX_CHARS, pattern=NATIVE_THREAD_ID_PATTERN)

    def _checked_skills(self) -> tuple[Path, ...]:
        # Each skill is an absolute existing folder as given, holding a
        # SKILL.md file, with a unique lowercase-hyphenated folder name.
        items = RecordFieldConverter.to_tuple(self.skills, "skills", item_type=object, max_items=NATIVE_THREAD_MAX_SKILLS)
        folders: list[Path] = []
        for index, item in enumerate(items):
            name = f"skills[{index}]"
            given = RecordFieldConverter.to_path(item, name)
            RecordFieldValidator.require_directory(given, name)
            folder = given.resolve()
            if not (folder / NATIVE_SKILL_FILE_NAME).is_file():
                raise ConfigurationError(f"{name} must be a folder holding a {NATIVE_SKILL_FILE_NAME} file.", details={"field": name})
            RecordFieldValidator.require_text(folder.name, name, max_chars=NATIVE_SKILL_NAME_MAX_CHARS, pattern=NATIVE_SKILL_NAME_PATTERN)
            if any(earlier.name == folder.name for earlier in folders):
                raise ConfigurationError(f"{name} has the same folder name as an earlier skill; skill folder names must be unique.", details={"field": name})
            folders.append(folder)
        return tuple(folders)


@dataclass(frozen=True, slots=True)
class GrokThreadConfig:
    """Settings of the Grok thread functions: reasoning effort, permission mode, time limit and an explicit grok launcher."""

    reasoning_effort: GrokReasoningEffort | None = None
    permission_mode: GrokPermissionMode = GrokPermissionMode.DEFAULT
    timeout_seconds: float = NATIVE_THREAD_DEFAULT_SECONDS
    grok_command: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if self.reasoning_effort is not None:
            object.__setattr__(self, "reasoning_effort", RecordFieldConverter.to_enum(self.reasoning_effort, GrokReasoningEffort, "GrokThreadConfig.reasoning_effort"))
        object.__setattr__(self, "permission_mode", RecordFieldConverter.to_enum(self.permission_mode, GrokPermissionMode, "GrokThreadConfig.permission_mode"))
        RecordFieldValidator.require_number(self.timeout_seconds, "GrokThreadConfig.timeout_seconds", maximum=NATIVE_THREAD_MAX_SECONDS)
        if self.grok_command is not None:
            RecordFieldValidator.require_argv(self.grok_command, "GrokThreadConfig.grok_command")


@dataclass(frozen=True, slots=True)
class OpencodeThreadConfig:
    """Settings of the opencode thread functions: agent, model variant, time limit and an explicit opencode launcher."""

    agent: str | None = None
    variant: str | None = None
    timeout_seconds: float = NATIVE_THREAD_DEFAULT_SECONDS
    opencode_command: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        RecordFieldValidator.require_optional_text(self.agent, "OpencodeThreadConfig.agent", max_chars=NATIVE_NAME_MAX_CHARS, pattern=NATIVE_NAME_PATTERN)
        RecordFieldValidator.require_optional_text(self.variant, "OpencodeThreadConfig.variant", max_chars=NATIVE_NAME_MAX_CHARS, pattern=NATIVE_NAME_PATTERN)
        RecordFieldValidator.require_number(self.timeout_seconds, "OpencodeThreadConfig.timeout_seconds", maximum=NATIVE_THREAD_MAX_SECONDS)
        if self.opencode_command is not None:
            RecordFieldValidator.require_argv(self.opencode_command, "OpencodeThreadConfig.opencode_command")


@dataclass(frozen=True, slots=True)
class MuseThreadConfig:
    """Settings of the Muse thread functions: reasoning effort, time limit, an explicit muse launcher, or the WSL distro and the muse path inside it."""

    reasoning_effort: MuseReasoningEffort | None = None
    timeout_seconds: float = NATIVE_THREAD_DEFAULT_SECONDS
    muse_command: tuple[str, ...] | None = None
    wsl_distro: str | None = None
    muse_path: str = MUSE_DEFAULT_PATH

    def __post_init__(self) -> None:
        if self.reasoning_effort is not None:
            object.__setattr__(self, "reasoning_effort", RecordFieldConverter.to_enum(self.reasoning_effort, MuseReasoningEffort, "MuseThreadConfig.reasoning_effort"))
        RecordFieldValidator.require_number(self.timeout_seconds, "MuseThreadConfig.timeout_seconds", maximum=NATIVE_THREAD_MAX_SECONDS)
        if self.muse_command is not None:
            RecordFieldValidator.require_argv(self.muse_command, "MuseThreadConfig.muse_command")
        RecordFieldValidator.require_optional_text(self.wsl_distro, "MuseThreadConfig.wsl_distro", max_chars=MUSE_DISTRO_MAX_CHARS, pattern=MUSE_DISTRO_PATTERN)
        RecordFieldValidator.require_text(self.muse_path, "MuseThreadConfig.muse_path", max_chars=MUSE_PATH_MAX_CHARS, pattern=MUSE_PATH_PATTERN)


@dataclass(frozen=True, slots=True)
class NativeThreadResult:
    """What a successful thread function call returns: the harness, the thread id to continue or fork, the final answer text, and whether that text was cut at the cap."""

    harness: NativeHarness
    thread_id: str
    text: str
    text_truncated: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "harness", RecordFieldConverter.to_enum(self.harness, NativeHarness, "NativeThreadResult.harness"))
        RecordFieldValidator.require_text(self.thread_id, "NativeThreadResult.thread_id", max_chars=NATIVE_THREAD_ID_MAX_CHARS, pattern=NATIVE_THREAD_ID_PATTERN)
        RecordFieldConverter.require_instance(self.text, "NativeThreadResult.text", str)
        RecordFieldValidator.require_bool(self.text_truncated, "NativeThreadResult.text_truncated")


__all__ = ["GrokThreadConfig", "MuseThreadConfig", "NativeThreadRequest", "NativeThreadResult", "OpencodeThreadConfig"]
