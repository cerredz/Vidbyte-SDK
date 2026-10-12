"""FILE: vidbyte/lib/dataclasses/coding.py

PURPOSE: Defines CodingAgentSettings, the validated record of every CodingAgent constructor argument: the root folder, at most one web-fetch key, the verification command and its attempt limit, the caller's own tools, the permission policy, the read-only path patterns, the write_text rewrite limit, the context-section switches, and the setup commands; CodingVerification, the validated outcome so far of one run's verification command; and CodingContextSectionText, one section of the CodingAgent context window.
ROLE IN CODEBASE: CodingAgentSettings is built by vidbyte/agents/coding.py (CodingAgent.__init__), read by vidbyte/tools/toolsets/coding.py (CodingAgentTools) and by the section loaders in vidbyte/agents/coding_context/, feeds its readonly_paths to vidbyte/middleware/builtins/readonly_paths.py, and is exported by the root vidbyte package. CodingContextSectionText is returned by each section loader and read by CodingContextWindow (vidbyte/agents/coding_context/window.py). CodingVerification is built by vidbyte/middleware/builtins/verify_command.py (VerifyCommandMiddleware) once per verification and kept in the run's run_state.
ARCHITECTURE NOTE: Every check lives in __post_init__, so a constructed record is always valid and neither CodingAgent nor CodingAgentTools re-checks it. root_dir is stored as the resolved absolute Path, so a later change of the process working directory never moves the tools. Key fields are repr=False, so printing the record never shows a key.
FUNCTION INVENTORY: CodingAgentSettings.__post_init__ is the narrated main function; _resolved_root checks and resolves root_dir; _check_fetch_keys checks the four keys; _check_verification checks verify_command and max_verify_attempts; _check_tools_and_policy checks the caller's tools and the policy; _readonly_paths checks the patterns and returns them as a tuple; _check_context_switches checks the section switches; _checked_setup_commands checks the setup commands and returns them as a tuple; max_rewrite_lines is checked by OverwriteLineLimit (vidbyte/lib/dataclasses/filesystem.py), the same rule FileSystemToolConfig uses. CodingContextSectionText.__post_init__ checks the section kind and the text fields. CodingVerification.__post_init__ checks attempts and last_exit_code, and passed is derived from last_exit_code.
COMMON MODIFICATION PATTERNS: A new keyed fetch provider adds one key field here (repr=False), one row in _check_fetch_keys, and one row in CodingAgentTools.authenticate_tools. A context section with its own on/off switch adds one bool field here and one isinstance check in _check_context_switches. A new CodingAgent keyword adds one field and one check here, and its bounds go in vidbyte/lib/constants/coding.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not read keys from environment variables. 2. Do not put a key value in an error message or its details; name the parameter instead. 3. Do not drop repr=False from a key field. 4. Do not import from vidbyte.tools or vidbyte.agents; vidbyte/lib is the bottom layer.
KNOWN EDGE CASES: root_dir="" is rejected even though Path("") is the current folder, which is why root_dir keeps its raw type until __post_init__ checks it. readonly_paths keeps its raw type for the same reason: tuple("tests/**") would split a bare string into characters. Caller tools are only checked to be a tuple here; BaseAgent decides which items are tools. load_agents=1 is rejected even though 1 == True, so a stray int or string never flips a switch through truthiness. setup_commands="uv sync" is rejected rather than run one character at a time, which is why setup_commands keeps its raw type until __post_init__ checks it. CodingContextSectionText does not cap its content; each loader bounds its own text. max_verify_attempts is checked even when verify_command is None. Whether bash exists is checked by VerifyCommandMiddleware, not here, because vidbyte/lib cannot import the bash tool.
RELATED DOCS: docs/spec/coding-agent/spec.md; docs/design/coding-agent-verify-command.md; docs/design/coding-agent-readonly-paths.md; vidbyte/agents/README.md (Coding Agent)
TESTS: tests/features/coding_agent/test_coding_agent_contract.py, tests/features/coding_agent/test_coding_agent_web_fetch.py, tests/features/coding_agent/test_coding_agent_agents_md.py, tests/features/coding_agent/test_coding_agent_map_md.py, tests/features/coding_agent/test_coding_agent_setup_commands.py, tests/features/coding_agent/test_coding_agent_progress_notes.py, tests/features/coding_agent/test_coding_agent_readonly_paths.py, and tests/features/coding_agent/test_coding_agent_verify_command.py
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from vidbyte.lib.constants.coding import (
    CODING_DEFAULT_MAX_VERIFY_ATTEMPTS,
    CODING_MIN_VERIFY_ATTEMPTS,
)
from vidbyte.lib.dataclasses.filesystem import OverwriteLineLimit
from vidbyte.lib.dataclasses.security import PermissionPolicy
from vidbyte.lib.enums.coding import CodingContextSection
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class CodingAgentSettings:
    """Validated CodingAgent arguments: the root folder, at most one fetch key, the verification command, the caller's tools, the policy, the read-only patterns, the rewrite limit, and the section switches.

    root_dir is typed Path | str because the record must see the raw
    value: Path("") is the current folder, so converting first would
    accept an empty string. After __post_init__ it is always the
    resolved absolute Path. readonly_paths and setup_commands are typed
    Sequence[str] for the same reason: a bare string is itself a
    sequence of strings (tuple("tests/**") would split it into
    characters), so the record must see the raw value to refuse it.
    After __post_init__ each is always a tuple of str.
    """

    root_dir: Path | str
    permission_policy: PermissionPolicy
    max_rewrite_lines: int | None
    tools: tuple[object, ...] = ()
    firecrawl_api_key: str | None = field(default=None, repr=False)
    browserbase_api_key: str | None = field(default=None, repr=False)
    parallel_api_key: str | None = field(default=None, repr=False)
    tavily_api_key: str | None = field(default=None, repr=False)
    verify_command: str | None = None
    max_verify_attempts: int = CODING_DEFAULT_MAX_VERIFY_ATTEMPTS
    readonly_paths: Sequence[str] = ()
    load_agents: bool = True
    load_map: bool = True
    setup_commands: Sequence[str] = ()
    progress_notes: bool = True

    def __post_init__(self) -> None:
        # Check the root folder and keep its absolute path, so a later
        # change of the working directory never moves the tools.
        object.__setattr__(self, "root_dir", self._resolved_root())

        # Check the fetch keys: each one is non-blank text, and the
        # caller supplied no more than one.
        self._check_fetch_keys()

        # Check the verification command and how many times it may fail
        # before the run ends, so a bad value fails here, not mid-run.
        self._check_verification()

        # Check the caller's tools and the policy every call runs under.
        self._check_tools_and_policy()

        # Check the read-only patterns and keep them as a tuple.
        object.__setattr__(self, "readonly_paths", self._readonly_paths())

        # Check the rewrite limit with the same rule write_text's own
        # config uses: None turns it off, and a number is the most lines
        # an existing file may have and still be replaced whole.
        OverwriteLineLimit(self.max_rewrite_lines, "max_rewrite_lines")

        # Check the switches that turn context sections on or off: each
        # must be a real bool, so a string such as "no" cannot turn
        # loading on through truthiness.
        self._check_context_switches()

        # Check the setup commands and keep them as a tuple, so the
        # list a caller passed cannot change after the check.
        object.__setattr__(self, "setup_commands", self._checked_setup_commands())

    def _resolved_root(self) -> Path:
        """Return root_dir as an absolute path, or raise when it is not an existing directory."""
        # os.path.isdir, not Path.is_dir: Path("") is the current
        # folder, so an empty string would pass.
        root = self.root_dir
        if not isinstance(root, (str, os.PathLike)) or not os.path.isdir(root):
            raise ConfigurationError("CodingAgent root_dir must be an existing directory.", details={"root_dir": str(root)})
        return Path(root).resolve()

    def _check_fetch_keys(self) -> None:
        """Raise unless every supplied fetch key is non-blank text and at most one was supplied."""
        # @intent the-supplied-key-picks-one-fetch-provider
        # The key parameter the caller set picks the fetch provider. A
        # blank or non-string key would turn every fetch into a 401,
        # and two keys would bill one vendor while silently ignoring
        # the other, so both fail here. Errors name the parameter,
        # never the value, so a key cannot leak through an exception.
        keys = (
            ("firecrawl_api_key", self.firecrawl_api_key),
            ("browserbase_api_key", self.browserbase_api_key),
            ("parallel_api_key", self.parallel_api_key),
            ("tavily_api_key", self.tavily_api_key),
        )
        supplied = [name for name, key in keys if key is not None]
        blank = [name for name, key in keys if key is not None and (not isinstance(key, str) or not key.strip())]
        if blank:
            raise ConfigurationError(f"CodingAgent {', '.join(blank)} must be a non-blank string.", details={"parameters": blank})
        if len(supplied) > 1:
            raise ConfigurationError(f"CodingAgent accepts at most one fetch key, but got {', '.join(supplied)}.", details={"parameters": supplied})

    def _check_verification(self) -> None:
        """Raise unless verify_command is None or non-blank text and max_verify_attempts is a whole number of at least one."""
        # @intent verification-settings-fail-before-the-run
        # A blank command would fail every finish attempt, and a bool
        # or a fraction would make the attempt count meaningless, so
        # both fail at construction. bool is rejected first because True
        # is an int. The limit is checked even without a command, so a
        # bad argument never waits for a later change to surface.
        command = self.verify_command
        if command is not None and (not isinstance(command, str) or not command.strip()):
            raise ConfigurationError("CodingAgent verify_command must be None or a non-blank string.", details={"parameter": "verify_command", "verify_command_type": type(command).__name__})
        limit = self.max_verify_attempts
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < CODING_MIN_VERIFY_ATTEMPTS:
            raise ConfigurationError(f"CodingAgent max_verify_attempts must be a whole number of at least {CODING_MIN_VERIFY_ATTEMPTS}.", details={"parameter": "max_verify_attempts", "max_verify_attempts": repr(limit)})

    def _check_tools_and_policy(self) -> None:
        """Raise unless tools is a tuple and permission_policy is a PermissionPolicy."""
        # @intent policy-is-checked-before-any-tool-runs
        # The agent runs every tool call under this permission policy,
        # so anything that is not a PermissionPolicy fails here, at
        # construction, instead of on the first tool call of a run.
        if not isinstance(self.tools, tuple):
            raise ConfigurationError("CodingAgent tools must be a tuple.", details={"tools_type": type(self.tools).__name__})
        if not isinstance(self.permission_policy, PermissionPolicy):
            raise ConfigurationError("CodingAgent permission_policy must be a PermissionPolicy.", details={"permission_policy_type": type(self.permission_policy).__name__})

    def _check_context_switches(self) -> None:
        """Raise unless every context-section switch is a real bool, not a truthy stand-in such as 1 or "yes"."""
        if not isinstance(self.load_agents, bool):
            raise ConfigurationError("CodingAgent load_agents must be True or False.", details={"parameter": "load_agents", "load_agents_type": type(self.load_agents).__name__})
        if not isinstance(self.load_map, bool):
            raise ConfigurationError("CodingAgent load_map must be True or False.", details={"parameter": "load_map", "load_map_type": type(self.load_map).__name__})
        if not isinstance(self.progress_notes, bool):
            raise ConfigurationError("CodingAgent progress_notes must be True or False.", details={"parameter": "progress_notes", "progress_notes_type": type(self.progress_notes).__name__})

    def _readonly_paths(self) -> tuple[str, ...]:
        """Return readonly_paths as a tuple, or raise unless it is a list or tuple of non-blank strings."""
        # @intent readonly-paths-reject-a-bare-string
        # A bare string is a sequence of characters, so "tests/**"
        # would protect the files "t", "e", and so on, and the tests
        # would stay editable without any error.
        paths = self.readonly_paths
        if isinstance(paths, str) or not isinstance(paths, Sequence):
            raise ConfigurationError(f"CodingAgent readonly_paths must be a list or tuple of glob strings such as ['tests/**'], not a {type(paths).__name__}.", details={"readonly_paths_type": type(paths).__name__})
        bad = [repr(path) for path in paths if not isinstance(path, str) or not path.strip()]
        if bad:
            raise ConfigurationError("CodingAgent readonly_paths entries must be non-blank strings.", details={"bad_entries": bad})
        return tuple(paths)

    def _checked_setup_commands(self) -> tuple[str, ...]:
        """Return setup_commands as a tuple, or raise unless it is a list or tuple of non-blank command strings."""
        # @intent name-lists-reject-bare-strings
        # A bare string is itself a sequence, so tuple() would run
        # "uv sync" one character at a time; it is refused instead.
        commands = self.setup_commands
        if isinstance(commands, str) or not isinstance(commands, Sequence):
            raise ConfigurationError(f'CodingAgent setup_commands must be a list of command strings, such as ["uv sync"], not a {type(commands).__name__}.', details={"parameter": "setup_commands", "setup_commands_type": type(commands).__name__})
        bad = [index for index, command in enumerate(commands) if not isinstance(command, str) or not command.strip()]
        if bad:
            raise ConfigurationError(f"CodingAgent setup_commands items must be non-blank strings, but item {bad[0]} is not.", details={"parameter": "setup_commands", "items": bad})
        return tuple(commands)


@dataclass(frozen=True, slots=True)
class CodingVerification:
    """How many times one run's verification command has run, and the exit code of its latest run."""

    attempts: int
    last_exit_code: int | None

    def __post_init__(self) -> None:
        # @intent a-verification-record-is-always-a-real-outcome
        # The record exists only after the command ran at least once,
        # and a run that timed out or could not start has no exit code,
        # so last_exit_code is None then. bool is rejected first because
        # True is an int and would read as exit code 1.
        attempts = self.attempts
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < CODING_MIN_VERIFY_ATTEMPTS:
            raise ConfigurationError(f"CodingVerification attempts must be a whole number of at least {CODING_MIN_VERIFY_ATTEMPTS}.", details={"field": "attempts", "attempts": repr(attempts)})
        exit_code = self.last_exit_code
        if exit_code is not None and (isinstance(exit_code, bool) or not isinstance(exit_code, int)):
            raise ConfigurationError("CodingVerification last_exit_code must be None or a whole number.", details={"field": "last_exit_code", "last_exit_code": repr(exit_code)})

    @property
    def passed(self) -> bool:
        """Return True when the latest run of the command exited with code 0."""
        return self.last_exit_code == 0


@dataclass(frozen=True, slots=True)
class CodingContextSectionText:
    """One section of a CodingAgent context window: its kind, a title, the text the model sees, and where it came from.

    A section loader returns one of these, or None when it has nothing
    to add. CodingContextWindow places it after the system prompt under
    the primitive id section.value, in CodingContextSection order.
    """

    section: CodingContextSection
    title: str
    content: str
    source: str | None = None

    def __post_init__(self) -> None:
        # Check the section kind, which decides where the text renders
        # and which primitive id it is stored under.
        self._check_section()

        # Check the title and the text: a blank one would render an
        # empty heading or an empty section the model cannot use.
        self._check_text_fields()

    def _check_section(self) -> None:
        """Raise unless section is a CodingContextSection member."""
        if not isinstance(self.section, CodingContextSection):
            raise ConfigurationError("CodingContextSectionText section must be a CodingContextSection.", details={"field": "section", "section_type": type(self.section).__name__})

    def _check_text_fields(self) -> None:
        """Raise unless title and content are non-blank strings and source is None or a non-blank string."""
        texts = (("title", self.title), ("content", self.content))
        blank = [name for name, value in texts if not isinstance(value, str) or not value.strip()]
        if self.source is not None and (not isinstance(self.source, str) or not self.source.strip()):
            blank.append("source")
        if blank:
            raise ConfigurationError(f"CodingContextSectionText {', '.join(blank)} must be a non-blank string.", details={"fields": blank})


__all__ = ["CodingAgentSettings", "CodingContextSectionText", "CodingVerification"]
