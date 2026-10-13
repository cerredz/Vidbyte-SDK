"""FILE: vidbyte/lib/dataclasses/native_hosts.py

PURPOSE: Defines the records every native host shares: the turn handle a spawn returns, token usage, one recorded approval decision, a finished turn's result, an interrupt result, a Muse steer result, and per-message and per-session usage.
ROLE IN CODEBASE: Built by NativeTurnTable (vidbyte/harnesses/native/hostkit/turns.py) and the Grok, opencode and Muse turn drivers; returned by GrokHost, OpencodeHost and MuseHost; encoded to JSON by vidbyte/tools/builtins/native_host_tool.py.
ARCHITECTURE NOTE: Data only. Every record is frozen and slotted and validates in __post_init__ through RecordFieldValidator and RecordFieldConverter. Unknown usage is None, never 0. A result never carries RUNNING or FAILED: a wait raises at its deadline while a turn runs, and raises the recorded error for a failed turn.
FUNCTION INVENTORY: NativeTurnHandle, NativeTokenUsage, NativeApprovalDecision, NativeTurnResult, NativeInterruptResult, NativeSteerResult, NativeMessageUsage, NativeSessionUsage; each has only __post_init__.
COMMON MODIFICATION PATTERNS: Add a field with its default and its check in __post_init__ together; keep counts optional so unknown stays distinct from zero.
WHAT NOT TO DO IN THIS FILE: 1. Do not add host behaviour here. 2. Do not default a usage count to 0. 3. Do not accept a vendor status string where NativeTurnStatus is required.
KNOWN EDGE CASES: The handle's session id allows up to 160 characters because opencode ids are longer than UUIDs. turn_id is always uuid4().hex, 32 lower-case hexadecimal characters.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §9.1 (vidbyte.lib.dataclasses.native_hosts)
TESTS: tests/features/grok_host/test_grok_host_records.py
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from vidbyte.lib.constants.native_hosts import (
    NATIVE_APPROVAL_TITLE_MAX_CHARS,
    NATIVE_ID_MAX_CHARS,
    NATIVE_MAX_RECORDED_DECISIONS,
    NATIVE_RESULT_TEXT_MAX_CHARS,
    NATIVE_SESSION_ID_MAX_CHARS,
    NATIVE_STEER_STATUS_MAX_CHARS,
)
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.native_hosts import (
    ApprovalOutcome,
    InterruptSource,
    NativeHarness,
    NativeTurnStatus,
)
from vidbyte.lib.errors import ConfigurationError

_NO_WHITESPACE_PATTERN = r"^\S+$"
_TURN_ID_PATTERN = r"^[0-9a-f]{32}$"
_RESULT_STATUSES = frozenset({NativeTurnStatus.COMPLETED, NativeTurnStatus.INTERRUPTED})


@dataclass(frozen=True, slots=True)
class NativeTurnHandle:
    """Names one turn a host started: its harness, its vendor session and the host-issued turn id."""

    harness: NativeHarness
    session_id: str
    turn_id: str

    def __post_init__(self) -> None:
        RecordFieldValidator.require_enum(self.harness, NativeHarness, "NativeTurnHandle.harness")
        RecordFieldValidator.require_text(self.session_id, "NativeTurnHandle.session_id", max_chars=NATIVE_SESSION_ID_MAX_CHARS, pattern=_NO_WHITESPACE_PATTERN)
        RecordFieldValidator.require_text(self.turn_id, "NativeTurnHandle.turn_id", max_chars=NATIVE_ID_MAX_CHARS, pattern=_TURN_ID_PATTERN)


@dataclass(frozen=True, slots=True)
class NativeTokenUsage:
    """Token counts and cost for a turn or message; None means the vendor did not report it."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: Decimal | None = None

    def __post_init__(self) -> None:
        RecordFieldValidator.require_optional_count(self.input_tokens, "NativeTokenUsage.input_tokens")
        RecordFieldValidator.require_optional_count(self.output_tokens, "NativeTokenUsage.output_tokens")
        RecordFieldValidator.require_optional_count(self.reasoning_tokens, "NativeTokenUsage.reasoning_tokens")
        RecordFieldValidator.require_optional_count(self.cache_read_tokens, "NativeTokenUsage.cache_read_tokens")
        RecordFieldValidator.require_optional_count(self.cache_write_tokens, "NativeTokenUsage.cache_write_tokens")
        RecordFieldValidator.require_optional_count(self.total_tokens, "NativeTokenUsage.total_tokens")
        if self.cost_usd is not None:
            RecordFieldValidator.require_decimal(self.cost_usd, "NativeTokenUsage.cost_usd")


@dataclass(frozen=True, slots=True)
class NativeApprovalDecision:
    """One approval, permission or question request the host answered during a turn."""

    request_kind: str
    title: str
    outcome: ApprovalOutcome

    def __post_init__(self) -> None:
        # @intent approval-decision-record-is-bounded
        # Every decision a turn records reaches the caller and the
        # model, so the kind and the title are capped and the outcome is
        # a closed ApprovalOutcome. The title may be empty, because a
        # vendor need not send one.
        RecordFieldValidator.require_text(self.request_kind, "NativeApprovalDecision.request_kind", max_chars=NATIVE_ID_MAX_CHARS)
        RecordFieldValidator.require_text(self.title, "NativeApprovalDecision.title", max_chars=NATIVE_APPROVAL_TITLE_MAX_CHARS, allow_blank=True)
        RecordFieldValidator.require_enum(self.outcome, ApprovalOutcome, "NativeApprovalDecision.outcome")


@dataclass(frozen=True, slots=True)
class NativeTurnResult:
    """A finished turn: completed or interrupted, with its capped text, usage and recorded decisions."""

    handle: NativeTurnHandle
    status: NativeTurnStatus
    stop_reason: str | None = None
    text: str = ""
    text_truncated: bool = False
    usage: NativeTokenUsage | None = None
    interrupt_source: InterruptSource | None = None
    decisions: tuple[NativeApprovalDecision, ...] = ()
    decisions_dropped: int = 0

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.handle, "NativeTurnResult.handle", NativeTurnHandle)
        RecordFieldValidator.require_enum(self.status, NativeTurnStatus, "NativeTurnResult.status")
        if self.status not in _RESULT_STATUSES:
            raise ConfigurationError("NativeTurnResult.status must be COMPLETED or INTERRUPTED; a running or failed turn has no result.", details={"field": "NativeTurnResult.status"})
        RecordFieldValidator.require_optional_text(self.stop_reason, "NativeTurnResult.stop_reason", max_chars=NATIVE_ID_MAX_CHARS)
        RecordFieldValidator.require_text(self.text, "NativeTurnResult.text", max_chars=NATIVE_RESULT_TEXT_MAX_CHARS, allow_blank=True)
        RecordFieldValidator.require_bool(self.text_truncated, "NativeTurnResult.text_truncated")
        RecordFieldConverter.require_instance(self.usage, "NativeTurnResult.usage", NativeTokenUsage, optional=True)
        if self.interrupt_source is not None:
            RecordFieldValidator.require_enum(self.interrupt_source, InterruptSource, "NativeTurnResult.interrupt_source")
        if (self.status is NativeTurnStatus.INTERRUPTED) != (self.interrupt_source is not None):
            raise ConfigurationError("NativeTurnResult.interrupt_source must be set exactly when status is INTERRUPTED.", details={"field": "NativeTurnResult.interrupt_source"})
        decisions = RecordFieldConverter.to_tuple(self.decisions, "NativeTurnResult.decisions", item_type=NativeApprovalDecision, max_items=NATIVE_MAX_RECORDED_DECISIONS)
        object.__setattr__(self, "decisions", decisions)
        RecordFieldValidator.require_optional_count(self.decisions_dropped, "NativeTurnResult.decisions_dropped")
        RecordFieldConverter.require_instance(self.decisions_dropped, "NativeTurnResult.decisions_dropped", int)


@dataclass(frozen=True, slots=True)
class NativeInterruptResult:
    """Whether an interrupt found the turn still running."""

    handle: NativeTurnHandle
    was_running: bool

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.handle, "NativeInterruptResult.handle", NativeTurnHandle)
        RecordFieldValidator.require_bool(self.was_running, "NativeInterruptResult.was_running")


@dataclass(frozen=True, slots=True)
class NativeSteerResult:
    """The verbatim MSP CommandStatus a Muse turn/steer returned."""

    handle: NativeTurnHandle
    status: str

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.handle, "NativeSteerResult.handle", NativeTurnHandle)
        RecordFieldValidator.require_text(self.status, "NativeSteerResult.status", max_chars=NATIVE_STEER_STATUS_MAX_CHARS)


@dataclass(frozen=True, slots=True)
class NativeMessageUsage:
    """The usage one vendor message reported."""

    message_id: str
    usage: NativeTokenUsage

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.message_id, "NativeMessageUsage.message_id", max_chars=NATIVE_SESSION_ID_MAX_CHARS)
        RecordFieldConverter.require_instance(self.usage, "NativeMessageUsage.usage", NativeTokenUsage)


@dataclass(frozen=True, slots=True)
class NativeSessionUsage:
    """A session's usage totals and per-message breakdown, as far as the vendor reports them."""

    harness: NativeHarness
    session_id: str
    totals: NativeTokenUsage | None = None
    per_message: tuple[NativeMessageUsage, ...] = ()
    truncated: bool = False

    def __post_init__(self) -> None:
        RecordFieldValidator.require_enum(self.harness, NativeHarness, "NativeSessionUsage.harness")
        RecordFieldValidator.require_text(self.session_id, "NativeSessionUsage.session_id", max_chars=NATIVE_SESSION_ID_MAX_CHARS)
        RecordFieldConverter.require_instance(self.totals, "NativeSessionUsage.totals", NativeTokenUsage, optional=True)
        object.__setattr__(self, "per_message", RecordFieldConverter.to_tuple(self.per_message, "NativeSessionUsage.per_message", item_type=NativeMessageUsage))
        RecordFieldValidator.require_bool(self.truncated, "NativeSessionUsage.truncated")


__all__ = [
    "NativeApprovalDecision",
    "NativeInterruptResult",
    "NativeMessageUsage",
    "NativeSessionUsage",
    "NativeSteerResult",
    "NativeTokenUsage",
    "NativeTurnHandle",
    "NativeTurnResult",
]
