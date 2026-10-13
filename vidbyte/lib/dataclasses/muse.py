"""FILE: vidbyte/lib/dataclasses/muse.py

PURPOSE: Defines the Muse host's records: the host settings, the turn request, the read results (readiness, model catalog, sessions, session pages, view events and view pages), and the inbound MSP records the host parses from Muse's frames (approval choices and requests, user-input requests, turn completions, turn acks and completed items).
ROLE IN CODEBASE: Built by callers and by vidbyte/tools/builtins/muse/ (settings and requests), by MuseHost and MuseWire in vidbyte/harnesses/native/muse/ (outputs and inbound records); read by MuseLauncher and MuseTurnDriver.
ARCHITECTURE NOTE: Data only; frozen, slotted, validated in __post_init__ through RecordFieldValidator and RecordFieldConverter. Inbound records mirror only the MSP 1.0.1 members the host relies on and keep the open vocabularies (session status, terminal, decision, scope, disposition, item kind) as verbatim strings (D-13).
FUNCTION INVENTORY: MuseHostSettings, MuseTurnRequest, MuseReadiness, MuseModel, MuseModelCatalog, MuseSession, MuseSessionPage, MuseViewEvent, MusePage, MuseApprovalChoice, MuseApprovalRequest, MuseUserInputRequest, MuseTurnCompleted, MuseTurnAck, MuseItemCompleted; each has only __post_init__.
COMMON MODIFICATION PATTERNS: A new request option adds a validated field here, its MSP param in muse/wire.py, and its tool parameter in vidbyte/tools/builtins/muse/tools.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not add an approval-mode, permission or bypass field to the settings or the request; the host always sends denyUnmatched (INV-9). 2. Do not set both wsl_distro and muse_command; they are two different launchers. 3. Do not import from a layer above vidbyte.lib.
KNOWN EDGE CASES: muse_path is a Linux path inside the distro, so it must start with "/" even on Windows. A failed MuseTurnCompleted always carries its error kind, message and retryable flag; the wire parser raises protocol_mismatch before construction when they are missing (EC-98).
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §9.1 (vidbyte.lib.dataclasses.muse), EC-106
TESTS: tests/features/muse_host/test_muse_host_records.py, tests/features/muse_host/test_muse_host_wire.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vidbyte.lib.constants.native_hosts import (
    MUSE_DEFAULT_PATH,
    NATIVE_CONTROL_TIMEOUT_MAX_SECONDS,
    NATIVE_CONTROL_TIMEOUT_SECONDS,
    NATIVE_ID_MAX_CHARS,
    NATIVE_MAX_LIVE_TURNS_DEFAULT,
    NATIVE_MAX_LIVE_TURNS_LIMIT,
    NATIVE_MIN_LIVE_TURNS,
    NATIVE_PROMPT_MAX_CHARS,
    NATIVE_TURN_DEFAULT_SECONDS,
    NATIVE_TURN_MAX_SECONDS,
)
from vidbyte.lib.dataclasses.native_hosts import NativeTokenUsage
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.native_hosts import MuseReasoningEffort
from vidbyte.lib.errors import ConfigurationError

_DISTRO_PATTERN = r"^[A-Za-z0-9._-]{1,64}$"
_DISTRO_MAX_CHARS = 64
_MUSE_PATH_PATTERN = r"^/[^\x00\r\n]*$"
_MUSE_PATH_MAX_CHARS = 4096
_MODEL_PATTERN = r"^\S+$"
_FAILED_TERMINAL = "failed"


@dataclass(frozen=True, slots=True)
class MuseHostSettings:
    """Where a MuseHost works, how it launches muse (WSL distro or a direct command), and its control and live-turn bounds."""

    workspace: Path
    wsl_distro: str | None = None
    muse_path: str = MUSE_DEFAULT_PATH
    muse_command: tuple[str, ...] | None = None
    control_timeout_seconds: float = NATIVE_CONTROL_TIMEOUT_SECONDS
    max_live_turns: int = NATIVE_MAX_LIVE_TURNS_DEFAULT

    def __post_init__(self) -> None:
        RecordFieldValidator.require_directory(self.workspace, "MuseHostSettings.workspace")
        RecordFieldValidator.require_optional_text(self.wsl_distro, "MuseHostSettings.wsl_distro", max_chars=_DISTRO_MAX_CHARS, pattern=_DISTRO_PATTERN)
        RecordFieldValidator.require_text(self.muse_path, "MuseHostSettings.muse_path", max_chars=_MUSE_PATH_MAX_CHARS, pattern=_MUSE_PATH_PATTERN)
        if self.muse_command is not None:
            RecordFieldValidator.require_argv(self.muse_command, "MuseHostSettings.muse_command")
        if self.wsl_distro is not None and self.muse_command is not None:
            raise ConfigurationError("MuseHostSettings.wsl_distro and MuseHostSettings.muse_command cannot both be set; pick one launcher.")
        RecordFieldValidator.require_number(self.control_timeout_seconds, "MuseHostSettings.control_timeout_seconds", maximum=NATIVE_CONTROL_TIMEOUT_MAX_SECONDS)
        RecordFieldValidator.require_int(self.max_live_turns, "MuseHostSettings.max_live_turns", minimum=NATIVE_MIN_LIVE_TURNS, maximum=NATIVE_MAX_LIVE_TURNS_LIMIT)


@dataclass(frozen=True, slots=True)
class MuseTurnRequest:
    """One Muse turn: the prompt, an optional model and reasoning effort, and the turn ceiling."""

    prompt: str
    model: str | None = None
    reasoning_effort: MuseReasoningEffort | None = None
    max_turn_seconds: float = NATIVE_TURN_DEFAULT_SECONDS

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.prompt, "MuseTurnRequest.prompt", max_chars=NATIVE_PROMPT_MAX_CHARS)
        RecordFieldValidator.require_optional_text(self.model, "MuseTurnRequest.model", max_chars=NATIVE_ID_MAX_CHARS, pattern=_MODEL_PATTERN)
        if self.reasoning_effort is not None:
            RecordFieldValidator.require_enum(self.reasoning_effort, MuseReasoningEffort, "MuseTurnRequest.reasoning_effort")
        RecordFieldValidator.require_number(self.max_turn_seconds, "MuseTurnRequest.max_turn_seconds", maximum=NATIVE_TURN_MAX_SECONDS)


@dataclass(frozen=True, slots=True)
class MuseReadiness:
    """What check_muse_ready found: the version, MSP schema version, sign-in state when known, launcher and distro."""

    version: str
    schema_version: int
    signed_in: bool | None
    launcher: tuple[str, ...]
    wsl_distro: str | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.version, "MuseReadiness.version", str)
        RecordFieldConverter.require_instance(self.schema_version, "MuseReadiness.schema_version", int)
        if self.signed_in is not None:
            RecordFieldValidator.require_bool(self.signed_in, "MuseReadiness.signed_in")
        object.__setattr__(self, "launcher", RecordFieldConverter.to_tuple(self.launcher, "MuseReadiness.launcher", item_type=str))
        RecordFieldConverter.require_instance(self.wsl_distro, "MuseReadiness.wsl_distro", str, optional=True)


@dataclass(frozen=True, slots=True)
class MuseModel:
    """One model Muse offers; display_name is the catalog's displayLabel."""

    model_id: str
    display_name: str | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.model_id, "MuseModel.model_id", str)
        RecordFieldConverter.require_instance(self.display_name, "MuseModel.display_name", str, optional=True)


@dataclass(frozen=True, slots=True)
class MuseModelCatalog:
    """The models Muse offers for its provider and profile."""

    provider_id: str
    profile_id: str | None
    source: str
    models: tuple[MuseModel, ...]

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.provider_id, "MuseModelCatalog.provider_id", str)
        RecordFieldConverter.require_instance(self.profile_id, "MuseModelCatalog.profile_id", str, optional=True)
        RecordFieldConverter.require_instance(self.source, "MuseModelCatalog.source", str)
        object.__setattr__(self, "models", RecordFieldConverter.to_tuple(self.models, "MuseModelCatalog.models", item_type=MuseModel))


@dataclass(frozen=True, slots=True)
class MuseSession:
    """One Muse session: workspace, verbatim status, active turn, model, fork source, turn count and times."""

    session_id: str
    workspace_root: str
    status: str
    active_turn_id: str | None
    model_id: str | None
    provider_id: str | None
    forked_from: str | None
    turn_count: int
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.session_id, "MuseSession.session_id", str)
        RecordFieldConverter.require_instance(self.workspace_root, "MuseSession.workspace_root", str)
        RecordFieldConverter.require_instance(self.status, "MuseSession.status", str)
        RecordFieldConverter.require_instance(self.active_turn_id, "MuseSession.active_turn_id", str, optional=True)
        RecordFieldConverter.require_instance(self.model_id, "MuseSession.model_id", str, optional=True)
        RecordFieldConverter.require_instance(self.provider_id, "MuseSession.provider_id", str, optional=True)
        RecordFieldConverter.require_instance(self.forked_from, "MuseSession.forked_from", str, optional=True)
        RecordFieldValidator.require_optional_count(self.turn_count, "MuseSession.turn_count")
        RecordFieldConverter.require_instance(self.turn_count, "MuseSession.turn_count", int)
        RecordFieldConverter.require_instance(self.created_at, "MuseSession.created_at", str)
        RecordFieldConverter.require_instance(self.updated_at, "MuseSession.updated_at", str)


@dataclass(frozen=True, slots=True)
class MuseSessionPage:
    """One page of Muse sessions and the cursor of the next page."""

    sessions: tuple[MuseSession, ...]
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "sessions", RecordFieldConverter.to_tuple(self.sessions, "MuseSessionPage.sessions", item_type=MuseSession))
        RecordFieldConverter.require_instance(self.next_cursor, "MuseSessionPage.next_cursor", str, optional=True)


@dataclass(frozen=True, slots=True)
class MuseViewEvent:
    """One view event: its method and the event as compact sorted JSON, capped."""

    kind: str | None
    event_json: str
    truncated: bool

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.kind, "MuseViewEvent.kind", str, optional=True)
        RecordFieldConverter.require_instance(self.event_json, "MuseViewEvent.event_json", str)
        RecordFieldValidator.require_bool(self.truncated, "MuseViewEvent.truncated")


@dataclass(frozen=True, slots=True)
class MusePage:
    """One page of a session's view events and the cursor of the next page."""

    session_id: str
    events: tuple[MuseViewEvent, ...]
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.session_id, "MusePage.session_id", str)
        object.__setattr__(self, "events", RecordFieldConverter.to_tuple(self.events, "MusePage.events", item_type=MuseViewEvent))
        RecordFieldConverter.require_instance(self.next_cursor, "MusePage.next_cursor", str, optional=True)


@dataclass(frozen=True, slots=True)
class MuseApprovalChoice:
    """Inbound: one ApprovalChoice; decision and scope verbatim from open sets."""

    choice_id: str
    decision: str
    scope: str

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.choice_id, "MuseApprovalChoice.choice_id", str)
        RecordFieldConverter.require_instance(self.decision, "MuseApprovalChoice.decision", str)
        RecordFieldConverter.require_instance(self.scope, "MuseApprovalChoice.scope", str)


@dataclass(frozen=True, slots=True)
class MuseApprovalRequest:
    """Inbound: approval/requested or approval/updated, with the current requirement the decide must echo."""

    session_id: str
    approval_id: str
    requirement_approval_id: str
    requirement_source_index: int
    choices: tuple[MuseApprovalChoice, ...]
    turn_id: str | None = None
    tool_name: str | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.session_id, "MuseApprovalRequest.session_id", str)
        RecordFieldConverter.require_instance(self.approval_id, "MuseApprovalRequest.approval_id", str)
        RecordFieldConverter.require_instance(self.requirement_approval_id, "MuseApprovalRequest.requirement_approval_id", str)
        RecordFieldValidator.require_optional_count(self.requirement_source_index, "MuseApprovalRequest.requirement_source_index")
        RecordFieldConverter.require_instance(self.requirement_source_index, "MuseApprovalRequest.requirement_source_index", int)
        object.__setattr__(self, "choices", RecordFieldConverter.to_tuple(self.choices, "MuseApprovalRequest.choices", item_type=MuseApprovalChoice))
        RecordFieldConverter.require_instance(self.turn_id, "MuseApprovalRequest.turn_id", str, optional=True)
        RecordFieldConverter.require_instance(self.tool_name, "MuseApprovalRequest.tool_name", str, optional=True)


@dataclass(frozen=True, slots=True)
class MuseUserInputRequest:
    """Inbound: userInput/requested, which the host always cancels."""

    session_id: str
    turn_id: str
    user_input_id: str
    tool_name: str

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.session_id, "MuseUserInputRequest.session_id", str)
        RecordFieldConverter.require_instance(self.turn_id, "MuseUserInputRequest.turn_id", str)
        RecordFieldConverter.require_instance(self.user_input_id, "MuseUserInputRequest.user_input_id", str)
        RecordFieldConverter.require_instance(self.tool_name, "MuseUserInputRequest.tool_name", str)


@dataclass(frozen=True, slots=True)
class MuseTurnCompleted:
    """Inbound: turn/completed; the error fields are set exactly when terminal is failed."""

    session_id: str
    turn_id: str
    terminal: str
    error_kind: str | None = None
    error_message: str | None = None
    error_retryable: bool | None = None
    usage: NativeTokenUsage | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.session_id, "MuseTurnCompleted.session_id", str)
        RecordFieldConverter.require_instance(self.turn_id, "MuseTurnCompleted.turn_id", str)
        RecordFieldConverter.require_instance(self.terminal, "MuseTurnCompleted.terminal", str)
        RecordFieldConverter.require_instance(self.error_kind, "MuseTurnCompleted.error_kind", str, optional=True)
        RecordFieldConverter.require_instance(self.error_message, "MuseTurnCompleted.error_message", str, optional=True)
        if self.error_retryable is not None:
            RecordFieldValidator.require_bool(self.error_retryable, "MuseTurnCompleted.error_retryable")
        failed = self.terminal == _FAILED_TERMINAL
        error_fields = (self.error_kind, self.error_message, self.error_retryable)
        if failed != all(item is not None for item in error_fields) or (not failed and any(item is not None for item in error_fields)):
            raise ConfigurationError("MuseTurnCompleted.error_kind, MuseTurnCompleted.error_message and MuseTurnCompleted.error_retryable must be set exactly when MuseTurnCompleted.terminal is failed.")
        RecordFieldConverter.require_instance(self.usage, "MuseTurnCompleted.usage", NativeTokenUsage, optional=True)


@dataclass(frozen=True, slots=True)
class MuseTurnAck:
    """Inbound: the turn/start or turn/steer result; turn_id is authoritative for steer, interrupt and completion matching."""

    command_id: str
    turn_id: str
    status: str
    disposition: str | None = None

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.command_id, "MuseTurnAck.command_id", str)
        RecordFieldConverter.require_instance(self.turn_id, "MuseTurnAck.turn_id", str)
        RecordFieldConverter.require_instance(self.status, "MuseTurnAck.status", str)
        RecordFieldConverter.require_instance(self.disposition, "MuseTurnAck.disposition", str, optional=True)


@dataclass(frozen=True, slots=True)
class MuseItemCompleted:
    """Inbound: item/completed, read from its item; text is the accumulated reply for an agentMessage."""

    session_id: str
    item_id: str
    kind: str
    turn_id: str | None = None
    text: str | None = None
    truncated: bool = False

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.session_id, "MuseItemCompleted.session_id", str)
        RecordFieldConverter.require_instance(self.item_id, "MuseItemCompleted.item_id", str)
        RecordFieldConverter.require_instance(self.kind, "MuseItemCompleted.kind", str)
        RecordFieldConverter.require_instance(self.turn_id, "MuseItemCompleted.turn_id", str, optional=True)
        RecordFieldConverter.require_instance(self.text, "MuseItemCompleted.text", str, optional=True)
        RecordFieldValidator.require_bool(self.truncated, "MuseItemCompleted.truncated")


__all__ = [
    "MuseApprovalChoice",
    "MuseApprovalRequest",
    "MuseHostSettings",
    "MuseItemCompleted",
    "MuseModel",
    "MuseModelCatalog",
    "MusePage",
    "MuseReadiness",
    "MuseSession",
    "MuseSessionPage",
    "MuseTurnAck",
    "MuseTurnCompleted",
    "MuseTurnRequest",
    "MuseUserInputRequest",
    "MuseViewEvent",
]
