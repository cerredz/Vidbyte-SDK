"""FILE: vidbyte/lib/dataclasses/grok.py

PURPOSE: Defines the Grok host's records: the host settings, the live-turn and one-shot requests, the one-shot result, readiness, the model catalog, session listings and search results, and the inbound ACP records the host parses from Grok's frames (permission options and requests, session updates, and the session/prompt result).
ROLE IN CODEBASE: Built by callers and by vidbyte/tools/builtins/grok/ (requests, settings), by GrokHost (outputs) and by GrokWire in vidbyte/harnesses/native/grok/wire.py (inbound records); read by GrokTurnDriver and GrokCli.
ARCHITECTURE NOTE: Data only; every record is frozen and slotted and validates in __post_init__ through RecordFieldValidator and RecordFieldConverter. Inbound records mirror only the ACP members the host relies on, keep vendor vocabularies as verbatim strings (D-13), and are built only by GrokWire after it checked the frame's shape.
FUNCTION INVENTORY: GrokHostSettings, GrokTurnRequest, GrokOneShotRequest, GrokOneShotResult, GrokReadiness, GrokModel, GrokModelCatalog, GrokSession, GrokSessionPage, GrokSessionSearch, GrokPermissionOption, GrokPermissionRequest, GrokSessionUpdate, GrokPromptResult; each has only __post_init__.
COMMON MODIFICATION PATTERNS: A new request option adds a validated field here, its argv or ACP param in grok/cli.py or grok/wire.py, and its tool parameter in vidbyte/tools/builtins/grok/tools.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not add a model field to GrokHostSettings (lint C012); the model belongs to each request. 2. Do not add an approve-everything option; GrokPermissionMode has none (INV-9). 3. Do not let a one-shot rule start with "-" or hold a control character; rules go on argv.
KNOWN EDGE CASES: The one-shot prompt is capped at GROK_ARGV_PROMPT_MAX_CHARS because it travels on the command line. A missing or unknown ACP tool kind becomes AcpToolKind.OTHER in the wire parser before GrokPermissionRequest is built.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §9.1 (vidbyte.lib.dataclasses.grok), EC-23, EC-33
TESTS: tests/features/grok_host/test_grok_host_records.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from vidbyte.lib.constants.native_hosts import (
    GROK_ARGV_PROMPT_MAX_CHARS,
    GROK_MAX_RULES,
    GROK_MAX_TURNS_LIMIT,
    GROK_RULE_MAX_CHARS,
    NATIVE_CONTROL_TIMEOUT_MAX_SECONDS,
    NATIVE_CONTROL_TIMEOUT_SECONDS,
    NATIVE_ID_MAX_CHARS,
    NATIVE_MAX_LIVE_TURNS_DEFAULT,
    NATIVE_MAX_LIVE_TURNS_LIMIT,
    NATIVE_PROMPT_MAX_CHARS,
    NATIVE_TURN_DEFAULT_SECONDS,
    NATIVE_TURN_MAX_SECONDS,
    NATIVE_VENDOR_ID_PATTERN,
)
from vidbyte.lib.dataclasses.native_hosts import NativeTokenUsage
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.native_hosts import AcpToolKind, GrokPermissionMode
from vidbyte.lib.errors import ConfigurationError

_RULE_PATTERN = re.compile(r"^[^-\x00-\x1f\x7f][^\x00-\x1f\x7f]*$")


@dataclass(frozen=True, slots=True)
class GrokHostSettings:
    """Where a GrokHost works, how it launches Grok Build, and its control and live-turn bounds."""

    workspace: Path
    grok_command: tuple[str, ...] | None = None
    control_timeout_seconds: float = NATIVE_CONTROL_TIMEOUT_SECONDS
    max_live_turns: int = NATIVE_MAX_LIVE_TURNS_DEFAULT

    def __post_init__(self) -> None:
        RecordFieldValidator.require_directory(self.workspace, "GrokHostSettings.workspace")
        if self.grok_command is not None:
            RecordFieldValidator.require_argv(self.grok_command, "GrokHostSettings.grok_command")
        RecordFieldValidator.require_number(self.control_timeout_seconds, "GrokHostSettings.control_timeout_seconds", maximum=NATIVE_CONTROL_TIMEOUT_MAX_SECONDS)
        RecordFieldValidator.require_int(self.max_live_turns, "GrokHostSettings.max_live_turns", minimum=1, maximum=NATIVE_MAX_LIVE_TURNS_LIMIT)


@dataclass(frozen=True, slots=True)
class GrokTurnRequest:
    """One live Grok turn: the prompt, optional model and effort, the tool kinds to allow, and the turn ceiling."""

    prompt: str
    model: str | None = None
    reasoning_effort: str | None = None
    allowed_tool_kinds: frozenset[AcpToolKind] = frozenset()
    max_turn_seconds: float = NATIVE_TURN_DEFAULT_SECONDS

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.prompt, "GrokTurnRequest.prompt", max_chars=NATIVE_PROMPT_MAX_CHARS)
        RecordFieldValidator.require_optional_text(self.model, "GrokTurnRequest.model", max_chars=NATIVE_ID_MAX_CHARS, pattern=NATIVE_VENDOR_ID_PATTERN)
        RecordFieldValidator.require_optional_text(self.reasoning_effort, "GrokTurnRequest.reasoning_effort", max_chars=NATIVE_ID_MAX_CHARS, pattern=NATIVE_VENDOR_ID_PATTERN)
        object.__setattr__(self, "allowed_tool_kinds", RecordFieldValidator.require_enum_set(self.allowed_tool_kinds, AcpToolKind, "GrokTurnRequest.allowed_tool_kinds"))
        RecordFieldValidator.require_number(self.max_turn_seconds, "GrokTurnRequest.max_turn_seconds", maximum=NATIVE_TURN_MAX_SECONDS)


@dataclass(frozen=True, slots=True)
class GrokOneShotRequest:
    """One headless Grok run: the prompt, model and effort, permission mode, allow and deny rules, turn limit and ceiling."""

    prompt: str
    model: str | None = None
    reasoning_effort: str | None = None
    permission_mode: GrokPermissionMode = GrokPermissionMode.DEFAULT
    allow_rules: tuple[str, ...] = ()
    deny_rules: tuple[str, ...] = ()
    max_turns: int | None = None
    max_turn_seconds: float = NATIVE_TURN_DEFAULT_SECONDS

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.prompt, "GrokOneShotRequest.prompt", max_chars=GROK_ARGV_PROMPT_MAX_CHARS)
        RecordFieldValidator.require_optional_text(self.model, "GrokOneShotRequest.model", max_chars=NATIVE_ID_MAX_CHARS, pattern=NATIVE_VENDOR_ID_PATTERN)
        RecordFieldValidator.require_optional_text(self.reasoning_effort, "GrokOneShotRequest.reasoning_effort", max_chars=NATIVE_ID_MAX_CHARS, pattern=NATIVE_VENDOR_ID_PATTERN)
        RecordFieldValidator.require_enum(self.permission_mode, GrokPermissionMode, "GrokOneShotRequest.permission_mode")
        allow_rules = RecordFieldConverter.to_tuple(self.allow_rules, "GrokOneShotRequest.allow_rules", item_type=str)
        deny_rules = RecordFieldConverter.to_tuple(self.deny_rules, "GrokOneShotRequest.deny_rules", item_type=str)
        for rule in allow_rules:
            RecordFieldValidator.require_text(rule, "GrokOneShotRequest.allow_rules", max_chars=GROK_RULE_MAX_CHARS, pattern=_RULE_PATTERN.pattern)
        for rule in deny_rules:
            RecordFieldValidator.require_text(rule, "GrokOneShotRequest.deny_rules", max_chars=GROK_RULE_MAX_CHARS, pattern=_RULE_PATTERN.pattern)
        if len(allow_rules) + len(deny_rules) > GROK_MAX_RULES:
            raise ConfigurationError(f"GrokOneShotRequest.allow_rules and GrokOneShotRequest.deny_rules may hold at most {GROK_MAX_RULES} rules together.")
        object.__setattr__(self, "allow_rules", allow_rules)
        object.__setattr__(self, "deny_rules", deny_rules)
        if self.max_turns is not None:
            RecordFieldValidator.require_int(self.max_turns, "GrokOneShotRequest.max_turns", minimum=1, maximum=GROK_MAX_TURNS_LIMIT)
        RecordFieldValidator.require_number(self.max_turn_seconds, "GrokOneShotRequest.max_turn_seconds", maximum=NATIVE_TURN_MAX_SECONDS)


@dataclass(frozen=True, slots=True)
class GrokOneShotResult:
    """The answer of a one-shot or fork run, as the Grok CLI's JSON output reports it."""

    text: str
    text_truncated: bool
    stop_reason: str
    session_id: str
    request_id: str | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.text, "GrokOneShotResult.text", str)
        RecordFieldValidator.require_bool(self.text_truncated, "GrokOneShotResult.text_truncated")
        RecordFieldConverter.require_instance(self.stop_reason, "GrokOneShotResult.stop_reason", str)
        RecordFieldConverter.require_instance(self.session_id, "GrokOneShotResult.session_id", str)
        RecordFieldConverter.require_instance(self.request_id, "GrokOneShotResult.request_id", str, optional=True)


@dataclass(frozen=True, slots=True)
class GrokReadiness:
    """What check_grok_ready found: the CLI version, the ACP protocol and agent versions, auth methods and the current model."""

    version: str
    protocol_version: int
    agent_version: str | None
    auth_method_ids: tuple[str, ...]
    current_model_id: str

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.version, "GrokReadiness.version", str)
        RecordFieldConverter.require_instance(self.protocol_version, "GrokReadiness.protocol_version", int)
        RecordFieldConverter.require_instance(self.agent_version, "GrokReadiness.agent_version", str, optional=True)
        object.__setattr__(self, "auth_method_ids", RecordFieldConverter.to_tuple(self.auth_method_ids, "GrokReadiness.auth_method_ids", item_type=str))
        RecordFieldConverter.require_instance(self.current_model_id, "GrokReadiness.current_model_id", str)


@dataclass(frozen=True, slots=True)
class GrokModel:
    """One model Grok offers, with the reasoning efforts it accepts."""

    model_id: str
    name: str | None = None
    description: str | None = None
    reasoning_efforts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.model_id, "GrokModel.model_id", str)
        RecordFieldConverter.require_instance(self.name, "GrokModel.name", str, optional=True)
        RecordFieldConverter.require_instance(self.description, "GrokModel.description", str, optional=True)
        object.__setattr__(self, "reasoning_efforts", RecordFieldConverter.to_tuple(self.reasoning_efforts, "GrokModel.reasoning_efforts", item_type=str))


@dataclass(frozen=True, slots=True)
class GrokModelCatalog:
    """The models Grok offers and the one it uses by default."""

    current_model_id: str
    models: tuple[GrokModel, ...]

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.current_model_id, "GrokModelCatalog.current_model_id", str)
        object.__setattr__(self, "models", RecordFieldConverter.to_tuple(self.models, "GrokModelCatalog.models", item_type=GrokModel))


@dataclass(frozen=True, slots=True)
class GrokSession:
    """One Grok session listed for this host's workspace."""

    session_id: str
    cwd: str
    title: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.session_id, "GrokSession.session_id", str)
        RecordFieldConverter.require_instance(self.cwd, "GrokSession.cwd", str)
        RecordFieldConverter.require_instance(self.title, "GrokSession.title", str, optional=True)
        RecordFieldConverter.require_instance(self.updated_at, "GrokSession.updated_at", str, optional=True)


@dataclass(frozen=True, slots=True)
class GrokSessionPage:
    """One page of Grok sessions and the cursor of the next page."""

    sessions: tuple[GrokSession, ...]
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "sessions", RecordFieldConverter.to_tuple(self.sessions, "GrokSessionPage.sessions", item_type=GrokSession))
        RecordFieldConverter.require_instance(self.next_cursor, "GrokSessionPage.next_cursor", str, optional=True)


@dataclass(frozen=True, slots=True)
class GrokSessionSearch:
    """The sessions whose title or id contains a query, and whether the scan stopped early."""

    query: str
    sessions: tuple[GrokSession, ...]
    truncated: bool

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.query, "GrokSessionSearch.query", str)
        object.__setattr__(self, "sessions", RecordFieldConverter.to_tuple(self.sessions, "GrokSessionSearch.sessions", item_type=GrokSession))
        RecordFieldValidator.require_bool(self.truncated, "GrokSessionSearch.truncated")


@dataclass(frozen=True, slots=True)
class GrokPermissionOption:
    """Inbound: one ACP PermissionOption; kind is verbatim (allow_once, allow_always, reject_once, reject_always, open set)."""

    option_id: str
    kind: str

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.option_id, "GrokPermissionOption.option_id", str)
        RecordFieldConverter.require_instance(self.kind, "GrokPermissionOption.kind", str)


@dataclass(frozen=True, slots=True)
class GrokPermissionRequest:
    """Inbound: one session/request_permission server request, with the JSON-RPC id the answer must echo."""

    request_id: int | str
    session_id: str
    tool_kind: AcpToolKind
    title: str
    options: tuple[GrokPermissionOption, ...]

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.request_id, "GrokPermissionRequest.request_id", (int, str))
        RecordFieldConverter.require_instance(self.session_id, "GrokPermissionRequest.session_id", str)
        RecordFieldValidator.require_enum(self.tool_kind, AcpToolKind, "GrokPermissionRequest.tool_kind")
        RecordFieldConverter.require_instance(self.title, "GrokPermissionRequest.title", str)
        object.__setattr__(self, "options", RecordFieldConverter.to_tuple(self.options, "GrokPermissionRequest.options", item_type=GrokPermissionOption))


@dataclass(frozen=True, slots=True)
class GrokSessionUpdate:
    """Inbound: one session/update notification; text only for an agent_message_chunk, cost only for a usage_update."""

    session_id: str
    kind: str
    text: str = ""
    cost_amount: Decimal | None = None
    cost_currency: str | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.session_id, "GrokSessionUpdate.session_id", str)
        RecordFieldConverter.require_instance(self.kind, "GrokSessionUpdate.kind", str)
        RecordFieldConverter.require_instance(self.text, "GrokSessionUpdate.text", str)
        if self.cost_amount is not None:
            RecordFieldValidator.require_decimal(self.cost_amount, "GrokSessionUpdate.cost_amount")
        RecordFieldConverter.require_instance(self.cost_currency, "GrokSessionUpdate.cost_currency", str, optional=True)


@dataclass(frozen=True, slots=True)
class GrokPromptResult:
    """Inbound: the session/prompt result, its verbatim stopReason and the usage when Grok sent one."""

    stop_reason: str
    usage: NativeTokenUsage | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.stop_reason, "GrokPromptResult.stop_reason", str)
        RecordFieldConverter.require_instance(self.usage, "GrokPromptResult.usage", NativeTokenUsage, optional=True)


__all__ = [
    "GrokHostSettings",
    "GrokModel",
    "GrokModelCatalog",
    "GrokOneShotRequest",
    "GrokOneShotResult",
    "GrokPermissionOption",
    "GrokPermissionRequest",
    "GrokPromptResult",
    "GrokReadiness",
    "GrokSession",
    "GrokSessionPage",
    "GrokSessionSearch",
    "GrokSessionUpdate",
    "GrokTurnRequest",
]
