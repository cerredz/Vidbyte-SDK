"""FILE: vidbyte/lib/dataclasses/claude.py

PURPOSE: Defines ClaudeSpawnRequest, the validated record of every setting one Claude Code turn can start with, and the seven records it holds: ClaudeImage, ClaudeThinking, ClaudeSystemPrompt, ClaudeSandbox, ClaudeHookMatcher, ClaudeMcpServer and ClaudeAgentDefinition.
ROLE IN CODEBASE: Built by developers and by the Claude tools in vidbyte/tools/builtins/claude/, read by ClaudeHost (vidbyte/harnesses/native/claude/host.py) and translated into claude-agent-sdk options by ClaudeOptionsTranslator (options.py). _ClaudeFieldRules is also used by vidbyte/lib/dataclasses/claude_host.py and by ClaudeHost to check model-supplied arguments.
ARCHITECTURE NOTE: Every record validates itself in __post_init__ and raises ClaudeOperationError from operation validate_request, with configuration.invalid_argument for a bad value and configuration.unsupported_combination for settings that conflict. Enum fields accept raw wire values and store the enum member. _ClaudeFieldRules owns each shared check once, so every rule and its error text exist in one place.
COMMON MODIFICATION PATTERNS: A new request field adds one field in the section 9.2 mapping order, one entry in the matching field table or one check in a _check_ helper, and one row in ClaudeOptionsTranslator. Its bounds go in vidbyte/lib/constants/claude.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not put a prompt, image, system-prompt text, settings, env or headers value in an error reason; name the field or key instead. 2. Do not drop repr=False from env or headers. 3. Do not import vidbyte.tools or vidbyte.harnesses at run time; vidbyte/lib is the bottom layer, so tools are checked by shape.
KNOWN EDGE CASES: repr=False hides env and headers from a record's repr only. The SDK still writes each external MCP server's env and headers, and inline settings JSON, onto the claude command line, where other local users and process monitors can read them while the turn runs. url, args and settings keep their repr. A failing pytest assert that compares two records prints every field that differs, env and headers included. Tuple fields must be real tuples, so a bare string is never split into characters.
RELATED DOCS: https://platform.claude.com/docs/en/agent-sdk/python; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

import base64
import binascii
import math
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import NoneType
from typing import TYPE_CHECKING, Any, TypeVar

from vidbyte.lib.constants.claude import (
    CLAUDE_INVALID_ARGUMENT_NEXT_STEP,
    CLAUDE_MAX_AUTOCOMPACT_TOKENS,
    CLAUDE_MAX_FILE_SPECS,
    CLAUDE_MAX_OUTPUT_TOKENS_ENV,
    CLAUDE_MAX_PLUGIN_URLS,
    CLAUDE_MIN_AUTOCOMPACT_TOKENS,
    CLAUDE_MIN_COUNT,
    CLAUDE_MIN_EXCLUSIVE_AMOUNT,
    CLAUDE_PLUGIN_URL_MARKER,
    CLAUDE_TOOL_SERVER_NAME,
    CLAUDE_UNSUPPORTED_COMBINATION_NEXT_STEP,
)
from vidbyte.lib.enums.claude import (
    ClaudeBeta,
    ClaudeEffort,
    ClaudeHookEvent,
    ClaudeImageMediaType,
    ClaudeMcpTransport,
    ClaudeMemoryScope,
    ClaudePermissionMode,
    ClaudePermissionPrompts,
    ClaudeSettingSource,
    ClaudeSystemPromptMode,
    ClaudeThinkingDisplay,
    ClaudeThinkingMode,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import ClaudeOperationError

if TYPE_CHECKING:
    from vidbyte.tools.base import BaseTool

_VALIDATE_OPERATION = "validate_request"
_TEXT = (str,)
_FLAG = (bool,)
_ChoiceT = TypeVar("_ChoiceT", bound=Enum)


class _ClaudeFieldRules:
    """Owns each check the Claude records and ClaudeHost share, so every rule and its error text exist once."""

    @staticmethod
    def invalid(reason: str) -> ClaudeOperationError:
        """Return the error for one bad field or argument value."""
        return ClaudeOperationError(reason, failure_code=FailureCode.CONFIGURATION_INVALID_ARGUMENT.value, operation=_VALIDATE_OPERATION, next_step=CLAUDE_INVALID_ARGUMENT_NEXT_STEP)

    @staticmethod
    def conflict(reason: str) -> ClaudeOperationError:
        """Return the error for settings that cannot be used together."""
        return ClaudeOperationError(reason, failure_code=FailureCode.CONFIGURATION_UNSUPPORTED_COMBINATION.value, operation=_VALIDATE_OPERATION, next_step=CLAUDE_UNSUPPORTED_COMBINATION_NEXT_STEP)

    @staticmethod
    def shapes(record: object, table: tuple[tuple[str, tuple[type, ...]], ...]) -> None:
        """Reject the first field of the table whose value has none of its accepted types; the value itself is never shown."""
        for name, accepted in table:
            if not isinstance(getattr(record, name), accepted):
                expected = " or ".join(kind.__name__ for kind in accepted)
                raise _ClaudeFieldRules.invalid(f"{type(record).__name__}.{name} has the wrong type; expected {expected}.")

    @staticmethod
    def texts(value: object, name: str) -> None:
        """Reject a value that is not a tuple of non-empty text."""
        if not isinstance(value, tuple) or not all(isinstance(item, str) and item for item in value):
            raise _ClaudeFieldRules.invalid(f"{name} must be a tuple of non-empty text.")

    @staticmethod
    def records(value: object, record: type, name: str) -> None:
        """Reject a value that is not a tuple of the given record type."""
        if not isinstance(value, tuple) or not all(isinstance(item, record) for item in value):
            raise _ClaudeFieldRules.invalid(f"{name} must be a tuple of {record.__name__} records.")

    @staticmethod
    def mapping(value: object, name: str) -> None:
        """Reject a value that is not a mapping of text keys to text values, naming a bad key but never a value."""
        if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
            raise _ClaudeFieldRules.invalid(f"{name} must map text keys to text values.")
        for key, item in value.items():
            if not isinstance(item, str):
                raise _ClaudeFieldRules.invalid(f"{name} key {key!r} must map to a text value.")

    @staticmethod
    def flag(value: object, name: str) -> None:
        """Reject a value that is not a real bool, so 1 or "yes" never flips a switch."""
        if not isinstance(value, bool):
            raise _ClaudeFieldRules.invalid(f"{name} must be true or false.")

    @staticmethod
    def whole(value: object, name: str) -> None:
        """Reject a value that is not a whole number; a bool is not one."""
        if isinstance(value, bool) or not isinstance(value, int):
            raise _ClaudeFieldRules.invalid(f"{name} must be a whole number.")

    @staticmethod
    def count(value: object, name: str, *, low: int = CLAUDE_MIN_COUNT, high: int | None = None) -> None:
        """Reject a value that is not a whole number from low to high; a bool is not one."""
        if isinstance(value, bool) or not isinstance(value, int):
            raise _ClaudeFieldRules.invalid(f"{name} must be a whole number.")
        if value < low or (high is not None and value > high):
            bounds = f"from {low} to {high}" if high is not None else f"at least {low}"
            raise _ClaudeFieldRules.invalid(f"{name} must be {bounds}; got {value}.")

    @staticmethod
    def amount(value: object, name: str) -> None:
        """Reject a value that is not a finite number above the minimum amount; a bool is not one."""
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise _ClaudeFieldRules.invalid(f"{name} must be a finite number.")
        if value <= CLAUDE_MIN_EXCLUSIVE_AMOUNT:
            raise _ClaudeFieldRules.invalid(f"{name} must be above {CLAUDE_MIN_EXCLUSIVE_AMOUNT}; got {value}.")

    @staticmethod
    def identifier(value: str, name: str) -> None:
        """Reject non-empty text that does not parse as a UUID."""
        if not value:
            return
        try:
            uuid.UUID(value)
        except ValueError as exc:
            raise _ClaudeFieldRules.invalid(f"{name} must be a UUID; got {value!r}.") from exc

    @staticmethod
    def choice(value: object, choices: type[_ChoiceT], name: str) -> _ChoiceT:
        """Return the enum member for a member or its raw wire value, rejecting anything else."""
        try:
            return choices(value)
        except ValueError as exc:
            allowed = ", ".join(repr(member.value) for member in choices)
            raise _ClaudeFieldRules.invalid(f"{name} must be one of {allowed}; got {value!r}.") from exc

    @staticmethod
    def unique(names: tuple[str, ...], name: str) -> None:
        """Reject a list of names that holds the same name twice."""
        if len(set(names)) != len(names):
            raise _ClaudeFieldRules.invalid(f"{name} entries must have unique names.")

    @staticmethod
    def encoded(value: object, name: str) -> None:
        """Reject a value that is not non-empty base64 text; the text itself is never shown."""
        if not isinstance(value, str) or not value:
            raise _ClaudeFieldRules.invalid(f"{name} must be non-empty base64 text.")
        try:
            base64.b64decode(value, validate=True)
        except binascii.Error as exc:
            raise _ClaudeFieldRules.invalid(f"{name} must be valid base64 text.") from exc


@dataclass(frozen=True, slots=True)
class ClaudeImage:
    """One image attached to a prompt, as base64 data and its media type."""

    media_type: ClaudeImageMediaType
    data: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "media_type", _ClaudeFieldRules.choice(self.media_type, ClaudeImageMediaType, "media_type"))
        _ClaudeFieldRules.encoded(self.data, "data")


@dataclass(frozen=True, slots=True)
class ClaudeThinking:
    """The extended-thinking setting of a session: a mode, its token budget and how thinking is shown."""

    mode: ClaudeThinkingMode
    budget_tokens: int | None = None
    display: ClaudeThinkingDisplay = ClaudeThinkingDisplay.PROVIDER_DEFAULT

    def __post_init__(self) -> None:
        # @intent thinking-settings-apply-only-to-their-mode
        # A budget belongs to enabled mode only and a display choice cannot
        # apply when thinking is disabled. Claude Code would ignore either one
        # without an error, so a caller's mistaken setting fails here instead.
        mode = _ClaudeFieldRules.choice(self.mode, ClaudeThinkingMode, "mode")
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "display", _ClaudeFieldRules.choice(self.display, ClaudeThinkingDisplay, "display"))
        if self.budget_tokens is not None:
            _ClaudeFieldRules.count(self.budget_tokens, "budget_tokens")
        if mode is ClaudeThinkingMode.ENABLED and self.budget_tokens is None:
            raise _ClaudeFieldRules.invalid("Thinking mode enabled needs budget_tokens.")
        if mode is not ClaudeThinkingMode.ENABLED and self.budget_tokens is not None:
            raise _ClaudeFieldRules.conflict(f"budget_tokens applies only to thinking mode enabled, not {mode.value}.")
        if mode is ClaudeThinkingMode.DISABLED and self.display is not ClaudeThinkingDisplay.PROVIDER_DEFAULT:
            raise _ClaudeFieldRules.conflict("display does not apply when thinking mode is disabled.")


@dataclass(frozen=True, slots=True)
class ClaudeSystemPrompt:
    """The system prompt of a session: text appended to Claude Code's own prompt, a replacement, or a prompt file path."""

    mode: ClaudeSystemPromptMode = ClaudeSystemPromptMode.PRESET
    text: str = ""

    def __post_init__(self) -> None:
        mode = _ClaudeFieldRules.choice(self.mode, ClaudeSystemPromptMode, "mode")
        object.__setattr__(self, "mode", mode)
        _ClaudeFieldRules.shapes(self, (("text", _TEXT),))
        if mode is not ClaudeSystemPromptMode.PRESET and not self.text:
            raise _ClaudeFieldRules.invalid(f"System prompt mode {mode.value} needs text.")


@dataclass(frozen=True, slots=True)
class ClaudeSandbox:
    """The command sandbox of a session and the network domains it allows or denies."""

    enabled: bool = True
    auto_allow_bash: bool | None = None
    excluded_commands: tuple[str, ...] = ()
    allowed_domains: tuple[str, ...] = ()
    denied_domains: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _ClaudeFieldRules.shapes(self, (("enabled", _FLAG), ("auto_allow_bash", (bool, NoneType))))
        for name in ("excluded_commands", "allowed_domains", "denied_domains"):
            _ClaudeFieldRules.texts(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class ClaudeHookMatcher:
    """Hook callbacks for one event, optionally limited to the tools a matcher names."""

    event: ClaudeHookEvent
    callbacks: tuple[Callable[..., Awaitable[object]], ...]
    matcher: str = ""
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "event", _ClaudeFieldRules.choice(self.event, ClaudeHookEvent, "event"))
        if not isinstance(self.callbacks, tuple) or not all(callable(callback) for callback in self.callbacks):
            raise _ClaudeFieldRules.invalid("callbacks must be a tuple of async callables.")
        _ClaudeFieldRules.shapes(self, (("matcher", _TEXT),))
        if self.timeout_seconds is not None:
            _ClaudeFieldRules.amount(self.timeout_seconds, "timeout_seconds")


@dataclass(frozen=True, slots=True)
class ClaudeMcpServer:
    """One external MCP server a session connects to, started as a command or reached at a URL."""

    name: str
    transport: ClaudeMcpTransport
    command: str = ""
    args: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict, repr=False)
    url: str = ""
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        # @intent a-server-claude-cannot-start-fails-here
        # A stdio server needs a command and a URL server needs a url. Without
        # this check Claude Code would only report the server as failed after
        # the turn had started.
        transport = _ClaudeFieldRules.choice(self.transport, ClaudeMcpTransport, "transport")
        object.__setattr__(self, "transport", transport)
        _ClaudeFieldRules.shapes(self, (("name", _TEXT), ("command", _TEXT), ("url", _TEXT)))
        _ClaudeFieldRules.texts(self.args, "args")
        _ClaudeFieldRules.mapping(self.env, "env")
        _ClaudeFieldRules.mapping(self.headers, "headers")
        if transport is ClaudeMcpTransport.STDIO and not self.command:
            raise _ClaudeFieldRules.invalid(f"MCP server {self.name!r} uses stdio and needs a command.")
        if transport is not ClaudeMcpTransport.STDIO and not self.url:
            raise _ClaudeFieldRules.invalid(f"MCP server {self.name!r} uses {transport.value} and needs a url.")


_AGENT_SHAPES = (("name", _TEXT), ("description", _TEXT), ("prompt", _TEXT), ("model", _TEXT), ("initial_prompt", _TEXT), ("background", (bool, NoneType)))


@dataclass(frozen=True, slots=True)
class ClaudeAgentDefinition:
    """One subagent Claude Code may delegate to inside a session."""

    name: str
    description: str
    prompt: str
    tools: tuple[str, ...] | None = None
    disallowed_tools: tuple[str, ...] = ()
    model: str = ""
    skills: tuple[str, ...] | None = None
    memory: ClaudeMemoryScope | None = None
    mcp_servers: tuple[str, ...] = ()
    initial_prompt: str = ""
    max_turns: int | None = None
    background: bool | None = None
    effort: ClaudeEffort = ClaudeEffort.PROVIDER_DEFAULT
    permission_mode: ClaudePermissionMode = ClaudePermissionMode.PROVIDER_DEFAULT

    def __post_init__(self) -> None:
        # @intent subagent-settings-are-wire-values
        # Effort, permission mode and memory are stored as enum members, so
        # the translator sends only values Claude Code accepts and an unknown
        # value fails here rather than inside the running subagent.
        _ClaudeFieldRules.shapes(self, _AGENT_SHAPES)
        for name in ("disallowed_tools", "mcp_servers"):
            _ClaudeFieldRules.texts(getattr(self, name), name)
        for name in ("tools", "skills"):
            if getattr(self, name) is not None:
                _ClaudeFieldRules.texts(getattr(self, name), name)
        if self.memory is not None:
            object.__setattr__(self, "memory", _ClaudeFieldRules.choice(self.memory, ClaudeMemoryScope, "memory"))
        if self.max_turns is not None:
            _ClaudeFieldRules.count(self.max_turns, "max_turns")
        object.__setattr__(self, "effort", _ClaudeFieldRules.choice(self.effort, ClaudeEffort, "effort"))
        object.__setattr__(self, "permission_mode", _ClaudeFieldRules.choice(self.permission_mode, ClaudePermissionMode, "permission_mode"))


# The fields whose check is only their type, in declaration order.
_SPAWN_SHAPES = (
    ("prompt", _TEXT),
    ("cwd", _TEXT),
    ("model", _TEXT),
    ("betas", (tuple,)),
    ("system_prompt", (ClaudeSystemPrompt,)),
    ("thinking", (ClaudeThinking, NoneType)),
    ("exclude_dynamic_system_prompt_sections", _FLAG),
    ("system_prompt_snapshot", (bool, NoneType)),
    ("restricted", _FLAG),
    ("sandbox", (ClaudeSandbox, NoneType)),
    ("tools", (tuple,)),
    ("strict_mcp_config", _FLAG),
    ("main_agent", _TEXT),
    ("setting_sources", (tuple, NoneType)),
    ("settings", _TEXT),
    ("bare", _FLAG),
    ("safe_mode", _FLAG),
    ("session_id", _TEXT),
    ("name", _TEXT),
    ("resume", _TEXT),
    ("continue_conversation", _FLAG),
    ("fork_session", _FLAG),
    ("resume_session_at", _TEXT),
    ("resume_drops_turn", _TEXT),
    ("persist_session", _FLAG),
    ("enable_file_checkpointing", _FLAG),
    ("worktree", (str, NoneType)),
    ("output_schema", (Mapping, NoneType)),
    ("include_partial_messages", _FLAG),
    ("include_hook_events", _FLAG),
    ("forward_subagent_text", _FLAG),
    ("cli_path", _TEXT),
    ("user", _TEXT),
)
_SPAWN_TEXTS = ("files", "add_dirs", "fallback_model", "allowed_tools", "disallowed_tools", "plugins")
_SPAWN_OPTIONAL_TEXTS = ("builtin_tools", "skills")
_SPAWN_RECORDS = (("images", ClaudeImage), ("hooks", ClaudeHookMatcher), ("mcp_servers", ClaudeMcpServer), ("agents", ClaudeAgentDefinition))
_SPAWN_IDENTIFIERS = ("session_id", "resume", "resume_session_at", "resume_drops_turn")
_SPAWN_CHOICES = (("effort", ClaudeEffort), ("permission_mode", ClaudePermissionMode), ("permission_prompts", ClaudePermissionPrompts))
_SPAWN_COUNTS = ("max_turns", "task_budget", "max_output_tokens", "load_timeout_ms")
_SPAWN_AMOUNTS = ("max_budget_usd", "timeout_seconds")


@dataclass(frozen=True, slots=True)
class ClaudeSpawnRequest:
    """Every setting one Claude Code turn starts with, in the order of the section 9.2 field mapping."""

    prompt: str = ""
    images: tuple[ClaudeImage, ...] = ()
    files: tuple[str, ...] = ()
    cwd: str = ""
    add_dirs: tuple[str, ...] = ()
    model: str = ""
    fallback_model: tuple[str, ...] = ()
    effort: ClaudeEffort = ClaudeEffort.PROVIDER_DEFAULT
    thinking: ClaudeThinking | None = None
    betas: tuple[ClaudeBeta, ...] = ()
    system_prompt: ClaudeSystemPrompt = field(default_factory=ClaudeSystemPrompt)
    exclude_dynamic_system_prompt_sections: bool = False
    system_prompt_snapshot: bool | None = None
    builtin_tools: tuple[str, ...] | None = None
    allowed_tools: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()
    permission_mode: ClaudePermissionMode = ClaudePermissionMode.PROVIDER_DEFAULT
    permission_prompts: ClaudePermissionPrompts = ClaudePermissionPrompts.NONE
    restricted: bool = False
    sandbox: ClaudeSandbox | None = None
    can_use_tool: Callable[..., Awaitable[object]] | None = None
    hooks: tuple[ClaudeHookMatcher, ...] = ()
    tools: tuple[BaseTool, ...] = ()
    mcp_servers: tuple[ClaudeMcpServer, ...] = ()
    strict_mcp_config: bool = False
    skills: tuple[str, ...] | None = None
    plugins: tuple[str, ...] = ()
    agents: tuple[ClaudeAgentDefinition, ...] = ()
    main_agent: str = ""
    setting_sources: tuple[ClaudeSettingSource, ...] | None = None
    settings: str = ""
    bare: bool = False
    safe_mode: bool = False
    max_turns: int | None = None
    max_budget_usd: float | None = None
    task_budget: int | None = None
    autocompact: int | None = None
    max_output_tokens: int | None = None
    session_id: str = ""
    name: str = ""
    resume: str = ""
    continue_conversation: bool = False
    fork_session: bool = False
    resume_session_at: str = ""
    resume_drops_turn: str = ""
    persist_session: bool = True
    enable_file_checkpointing: bool = False
    session_store: object | None = None
    worktree: str | None = None
    output_schema: Mapping[str, Any] | None = None
    include_partial_messages: bool = False
    include_hook_events: bool = False
    forward_subagent_text: bool = False
    cli_path: str = ""
    env: Mapping[str, str] = field(default_factory=dict, repr=False)
    user: str = ""
    load_timeout_ms: int | None = None
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        # Check each field on its own first, so that the rules relating
        # several fields can trust every type they read.
        self._check_fields()
        # Turn raw wire values such as "high" into enum members, and
        # reject values that no member has.
        self._coerce_choices()
        # Check the counts and amounts against their bounds.
        self._check_numbers()
        # Check the rules that relate several settings: how a session is
        # chosen, how the prompt and permission prompts fit together, and
        # what reaches the claude command line.
        self._check_sessions()
        self._check_prompting()
        self._check_inputs()
        self._check_extensions()

    def _check_fields(self) -> None:
        # Types first, then tuples of text and records, UUIDs and the env mapping.
        _ClaudeFieldRules.shapes(self, _SPAWN_SHAPES)
        for name in _SPAWN_TEXTS:
            _ClaudeFieldRules.texts(getattr(self, name), name)
        for name in _SPAWN_OPTIONAL_TEXTS:
            if getattr(self, name) is not None:
                _ClaudeFieldRules.texts(getattr(self, name), name)
        for name, record in _SPAWN_RECORDS:
            _ClaudeFieldRules.records(getattr(self, name), record, name)
        for name in _SPAWN_IDENTIFIERS:
            _ClaudeFieldRules.identifier(getattr(self, name), name)
        _ClaudeFieldRules.mapping(self.env, "env")
        if self.can_use_tool is not None and not callable(self.can_use_tool):
            raise _ClaudeFieldRules.invalid("can_use_tool must be an async callable.")

    def _coerce_choices(self) -> None:
        # Store enum members, so a raw value such as "plan" works like ClaudePermissionMode.PLAN.
        for name, choices in _SPAWN_CHOICES:
            object.__setattr__(self, name, _ClaudeFieldRules.choice(getattr(self, name), choices, name))
        object.__setattr__(self, "betas", tuple(_ClaudeFieldRules.choice(beta, ClaudeBeta, "betas") for beta in self.betas))
        if self.setting_sources is not None:
            sources = tuple(_ClaudeFieldRules.choice(source, ClaudeSettingSource, "setting_sources") for source in self.setting_sources)
            object.__setattr__(self, "setting_sources", sources)

    def _check_numbers(self) -> None:
        # Unset numbers stay at the SDK default, so only set ones are checked.
        for name in _SPAWN_COUNTS:
            if getattr(self, name) is not None:
                _ClaudeFieldRules.count(getattr(self, name), name)
        for name in _SPAWN_AMOUNTS:
            if getattr(self, name) is not None:
                _ClaudeFieldRules.amount(getattr(self, name), name)
        if self.autocompact is not None:
            _ClaudeFieldRules.count(self.autocompact, "autocompact", low=CLAUDE_MIN_AUTOCOMPACT_TOKENS, high=CLAUDE_MAX_AUTOCOMPACT_TOKENS)

    def _check_sessions(self) -> None:
        # The SDK refuses a chosen session id on a resumed or continued session unless that session is forked.
        if self.session_id and (self.resume or self.continue_conversation) and not self.fork_session:
            raise _ClaudeFieldRules.conflict("session_id needs fork_session when resume or continue_conversation is set.")
        if self.resume and self.continue_conversation:
            raise _ClaudeFieldRules.conflict("resume and continue_conversation cannot be used together.")
        if self.fork_session and not (self.resume or self.continue_conversation):
            raise _ClaudeFieldRules.invalid("fork_session needs resume or continue_conversation.")
        if self.resume_session_at and not self.resume:
            raise _ClaudeFieldRules.invalid("resume_session_at needs resume.")
        if self.resume_drops_turn and not self.resume_session_at:
            raise _ClaudeFieldRules.invalid("resume_drops_turn needs resume_session_at.")

    def _check_prompting(self) -> None:
        # @intent permission-prompts-have-exactly-one-answerer
        # With NONE the CLI denies every prompt itself, so a callback would
        # never be asked; with HOST and no callback a prompt would wait for an
        # answer nobody sends. The system prompt options and images must fit too.
        mode = self.system_prompt.mode
        if self.exclude_dynamic_system_prompt_sections and mode is not ClaudeSystemPromptMode.PRESET:
            raise _ClaudeFieldRules.conflict(f"exclude_dynamic_system_prompt_sections applies only to the preset system prompt, not {mode.value}.")
        if self.system_prompt_snapshot is not None and mode is ClaudeSystemPromptMode.FILE:
            raise _ClaudeFieldRules.conflict("system_prompt_snapshot does not apply to a system prompt file.")
        hosted = self.permission_prompts is ClaudePermissionPrompts.HOST
        if hosted and self.can_use_tool is None:
            raise _ClaudeFieldRules.invalid("permission_prompts host needs a can_use_tool callback.")
        if not hosted and self.can_use_tool is not None:
            raise _ClaudeFieldRules.conflict("can_use_tool needs permission_prompts host.")
        if self.images and not self.prompt:
            raise _ClaudeFieldRules.invalid("images need a non-empty prompt.")

    def _check_inputs(self) -> None:
        # @intent one-value-per-cli-flag
        # --file and --plugin-url go through extra_args, which holds one value
        # per flag, and fallback_model is sent comma-joined. A second entry or a
        # comma inside a model name would be lost or split without an error.
        if len(self.files) > CLAUDE_MAX_FILE_SPECS:
            raise _ClaudeFieldRules.invalid(f"files takes at most {CLAUDE_MAX_FILE_SPECS} entry.")
        if any(not file_id or not path for file_id, _, path in (spec.partition(":") for spec in self.files)):
            raise _ClaudeFieldRules.invalid("files entries must have the form file_id:path.")
        if sum(CLAUDE_PLUGIN_URL_MARKER in plugin for plugin in self.plugins) > CLAUDE_MAX_PLUGIN_URLS:
            raise _ClaudeFieldRules.invalid(f"plugins takes at most {CLAUDE_MAX_PLUGIN_URLS} URL.")
        if any("," in model for model in self.fallback_model):
            raise _ClaudeFieldRules.invalid("fallback_model entries must not contain a comma.")
        if self.max_output_tokens is not None and CLAUDE_MAX_OUTPUT_TOKENS_ENV in self.env:
            raise _ClaudeFieldRules.conflict(f"max_output_tokens and the env key {CLAUDE_MAX_OUTPUT_TOKENS_ENV} both set the output cap.")

    def _check_extensions(self) -> None:
        # @intent the-vidbyte-mcp-server-name-is-reserved
        # The request's own tools travel on the in-process MCP server named
        # vidbyte, so an external server of that name would replace them. Tools
        # are checked by shape, because vidbyte/lib cannot import vidbyte.tools.
        if not all(callable(getattr(tool, "spec", None)) for tool in self.tools):
            raise _ClaudeFieldRules.invalid("tools must hold vidbyte tools, each with a spec() method.")
        _ClaudeFieldRules.unique(tuple(tool.spec().name for tool in self.tools), "tools")
        server_names = tuple(server.name for server in self.mcp_servers)
        _ClaudeFieldRules.unique(server_names, "mcp_servers")
        if self.tools and CLAUDE_TOOL_SERVER_NAME in server_names:
            raise _ClaudeFieldRules.invalid(f"mcp_servers cannot use the name {CLAUDE_TOOL_SERVER_NAME!r}, which carries the request's tools.")
        _ClaudeFieldRules.unique(tuple(agent.name for agent in self.agents), "agents")
        store = self.session_store
        if store is not None and not (callable(getattr(store, "append", None)) and callable(getattr(store, "load", None))):
            raise _ClaudeFieldRules.invalid("session_store must have append and load methods.")


__all__ = [
    "ClaudeAgentDefinition",
    "ClaudeHookMatcher",
    "ClaudeImage",
    "ClaudeMcpServer",
    "ClaudeSandbox",
    "ClaudeSpawnRequest",
    "ClaudeSystemPrompt",
    "ClaudeThinking",
]
