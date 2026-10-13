"""FILE: vidbyte/lib/dataclasses/claude_host.py

PURPOSE: Defines the records ClaudeHost keeps and returns: ClaudeHostSettings, ClaudeSessionHandle, ClaudeFailure, ClaudePermissionDenial, ClaudeTurnResult, ClaudeModelUsage, ClaudeTaskUsage, ClaudeUsageSnapshot, ClaudeRateLimitWindow, ClaudeReadiness, ClaudeModelInfo, ClaudeSessionSummary and ClaudeSessionMessage, plus ClaudeTurnOutcome, the facts one turn's pump collected, and ClaudeSdkTypes, the claude-agent-sdk names loaded at first use.
ROLE IN CODEBASE: Built by vidbyte/harnesses/native/claude/ (host.py, session.py, probe.py, history.py, failures.py and sdk.py) and rendered as JSON by the Claude tools in vidbyte/tools/builtins/claude/. ClaudeTurnOutcome is read only by ClaudeFailureMapper.classify_turn.
ARCHITECTURE NOTE: Every record is frozen and slotted and checks its field types in __post_init__ through _ClaudeFieldRules from vidbyte/lib/dataclasses/claude.py, raising ClaudeOperationError from operation validate_request like the request records. Output fields accept every value shape the SDK documents for their source, with an absent value becoming None or empty text, so converting a well-formed SDK message never fails here.
COMMON MODIFICATION PATTERNS: A new output field adds one field and one entry in its record's shape table. A new loaded SDK name adds one ClaudeSdkTypes field and one name in ClaudeSdkLoader.load (vidbyte/harnesses/native/claude/sdk.py).
KNOWN EDGE CASES: structured_output holds whatever JSON value Claude Code returned, so its type is not checked. Money and utilization fields accept an int as well as a float, because JSON writes zero as 0. Tuple fields of outputs are checked to be tuples, not item by item, because only the host's own converters build them.
RELATED DOCS: https://platform.claude.com/docs/en/agent-sdk/python; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
from types import NoneType
from typing import Any

from vidbyte.lib.dataclasses.claude import _ClaudeFieldRules
from vidbyte.lib.enums.claude import (
    ClaudeEffort,
    ClaudeMessageKind,
    ClaudeRateLimitStatus,
    ClaudeRateLimitType,
    ClaudeTurnStatus,
)
from vidbyte.lib.enums.failure import FailureCode

_TEXT = (str,)
_FLAG = (bool,)
_INT = (int,)
_TUPLE = (tuple,)
_REAL = (int, float)
_OPTIONAL_INT = (int, NoneType)
_OPTIONAL_REAL = (int, float, NoneType)
_OPTIONAL_FLAG = (bool, NoneType)


@dataclass(frozen=True, slots=True)
class ClaudeHostSettings:
    """The ClaudeHost constructor arguments: the CLI path to use and an optional cap on live sessions."""

    cli_path: str = ""
    max_live_sessions: int | None = None

    def __post_init__(self) -> None:
        _ClaudeFieldRules.shapes(self, (("cli_path", _TEXT),))
        if self.max_live_sessions is not None:
            _ClaudeFieldRules.count(self.max_live_sessions, "max_live_sessions")


@dataclass(frozen=True, slots=True)
class ClaudeSessionHandle:
    """The host's id for one spawned turn and the Claude Code session it runs in."""

    handle_id: str
    session_id: str

    def __post_init__(self) -> None:
        _ClaudeFieldRules.shapes(self, (("handle_id", _TEXT), ("session_id", _TEXT)))


@dataclass(frozen=True, slots=True)
class ClaudeFailure:
    """Why a turn or a check failed: a failure code, a reason and the next step to take."""

    code: FailureCode
    reason: str
    next_step: str

    def __post_init__(self) -> None:
        _ClaudeFieldRules.shapes(self, (("code", (FailureCode,)), ("reason", _TEXT), ("next_step", _TEXT)))


_OPTIONAL_FAILURE = (ClaudeFailure, NoneType)


@dataclass(frozen=True, slots=True)
class ClaudePermissionDenial:
    """One tool call Claude Code was not allowed to make during a turn."""

    tool_name: str
    tool_use_id: str

    def __post_init__(self) -> None:
        _ClaudeFieldRules.shapes(self, (("tool_name", _TEXT), ("tool_use_id", _TEXT)))


_TURN_RESULT_SHAPES = (
    ("handle_id", _TEXT),
    ("session_id", _TEXT),
    ("status", (ClaudeTurnStatus,)),
    ("result_text", _TEXT),
    ("failure", _OPTIONAL_FAILURE),
    ("num_turns", _OPTIONAL_INT),
    ("duration_ms", _OPTIONAL_INT),
    ("total_cost_usd", _OPTIONAL_REAL),
    ("stop_reason", _TEXT),
    ("terminal_reason", _TEXT),
    ("permission_denials", _TUPLE),
    ("hooks_applied", _OPTIONAL_FLAG),
)


@dataclass(frozen=True, slots=True)
class ClaudeTurnResult:
    """The state of one turn: live while it runs, then the fields of its own result and its failure, if any."""

    handle_id: str
    session_id: str
    status: ClaudeTurnStatus
    result_text: str = ""
    structured_output: object = None
    failure: ClaudeFailure | None = None
    num_turns: int | None = None
    duration_ms: int | None = None
    total_cost_usd: float | None = None
    stop_reason: str = ""
    terminal_reason: str = ""
    permission_denials: tuple[ClaudePermissionDenial, ...] = ()
    hooks_applied: bool | None = None

    def __post_init__(self) -> None:
        _ClaudeFieldRules.shapes(self, _TURN_RESULT_SHAPES)


_MODEL_USAGE_SHAPES = (
    ("model", _TEXT),
    ("input_tokens", _INT),
    ("output_tokens", _INT),
    ("cache_read_input_tokens", _INT),
    ("cache_creation_input_tokens", _INT),
    ("web_search_requests", _INT),
    ("cost_usd", _REAL),
)


@dataclass(frozen=True, slots=True)
class ClaudeModelUsage:
    """One model's cumulative token use and cost in a session, as the latest result reported it."""

    model: str
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    web_search_requests: int
    cost_usd: float

    def __post_init__(self) -> None:
        _ClaudeFieldRules.shapes(self, _MODEL_USAGE_SHAPES)


@dataclass(frozen=True, slots=True)
class ClaudeTaskUsage:
    """The latest figures of one background task a turn started."""

    task_id: str
    description: str
    total_tokens: int
    tool_uses: int
    duration_ms: int

    def __post_init__(self) -> None:
        _ClaudeFieldRules.shapes(self, (("task_id", _TEXT), ("description", _TEXT), ("total_tokens", _INT), ("tool_uses", _INT), ("duration_ms", _INT)))


@dataclass(frozen=True, slots=True)
class ClaudeUsageSnapshot:
    """A turn's latest cumulative cost, per-model usage and background-task figures."""

    handle_id: str
    session_id: str
    total_cost_usd: float | None
    models: tuple[ClaudeModelUsage, ...]
    tasks: tuple[ClaudeTaskUsage, ...]

    def __post_init__(self) -> None:
        _ClaudeFieldRules.shapes(self, (("handle_id", _TEXT), ("session_id", _TEXT), ("total_cost_usd", _OPTIONAL_REAL), ("models", _TUPLE), ("tasks", _TUPLE)))


_RATE_LIMIT_SHAPES = (
    ("rate_limit_type", (ClaudeRateLimitType,)),
    ("status", (ClaudeRateLimitStatus,)),
    ("resets_at", _OPTIONAL_INT),
    ("utilization", _OPTIONAL_REAL),
    ("overage_status", (ClaudeRateLimitStatus, NoneType)),
    ("overage_resets_at", _OPTIONAL_INT),
    ("overage_disabled_reason", _TEXT),
)


@dataclass(frozen=True, slots=True)
class ClaudeRateLimitWindow:
    """The latest state Claude Code reported for one rate-limit window."""

    rate_limit_type: ClaudeRateLimitType
    status: ClaudeRateLimitStatus
    resets_at: int | None
    utilization: float | None
    overage_status: ClaudeRateLimitStatus | None
    overage_resets_at: int | None
    overage_disabled_reason: str

    def __post_init__(self) -> None:
        _ClaudeFieldRules.shapes(self, _RATE_LIMIT_SHAPES)


@dataclass(frozen=True, slots=True)
class ClaudeReadiness:
    """Whether this machine can run Claude Code: the CLI found, its version, the sign-in, and the first failure."""

    cli_path: str
    cli_version: str
    signed_in: bool
    failure: ClaudeFailure | None

    def __post_init__(self) -> None:
        _ClaudeFieldRules.shapes(self, (("cli_path", _TEXT), ("cli_version", _TEXT), ("signed_in", _FLAG), ("failure", _OPTIONAL_FAILURE)))


_MODEL_INFO_SHAPES = (
    ("value", _TEXT),
    ("display_name", _TEXT),
    ("description", _TEXT),
    ("resolved_model", _TEXT),
    ("supports_effort", _OPTIONAL_FLAG),
    ("supported_effort_levels", _TUPLE),
    ("supports_adaptive_thinking", _OPTIONAL_FLAG),
    ("supports_fast_mode", _OPTIONAL_FLAG),
    ("supports_auto_mode", _OPTIONAL_FLAG),
)


@dataclass(frozen=True, slots=True)
class ClaudeModelInfo:
    """One model the signed-in account can use, with the options it supports."""

    value: str
    display_name: str
    description: str
    resolved_model: str
    supports_effort: bool | None
    supported_effort_levels: tuple[ClaudeEffort, ...]
    supports_adaptive_thinking: bool | None
    supports_fast_mode: bool | None
    supports_auto_mode: bool | None

    def __post_init__(self) -> None:
        _ClaudeFieldRules.shapes(self, _MODEL_INFO_SHAPES)


_SESSION_SUMMARY_SHAPES = (
    ("session_id", _TEXT),
    ("summary", _TEXT),
    ("last_modified", _INT),
    ("file_size", _OPTIONAL_INT),
    ("custom_title", _TEXT),
    ("first_prompt", _TEXT),
    ("git_branch", _TEXT),
    ("cwd", _TEXT),
    ("tag", _TEXT),
    ("created_at", _OPTIONAL_INT),
)


@dataclass(frozen=True, slots=True)
class ClaudeSessionSummary:
    """What Claude Code's session files say about one stored session."""

    session_id: str
    summary: str
    last_modified: int
    file_size: int | None
    custom_title: str
    first_prompt: str
    git_branch: str
    cwd: str
    tag: str
    created_at: int | None

    def __post_init__(self) -> None:
        _ClaudeFieldRules.shapes(self, _SESSION_SUMMARY_SHAPES)


@dataclass(frozen=True, slots=True)
class ClaudeSessionMessage:
    """One stored message of a session, with its content rendered as text."""

    uuid: str
    session_id: str
    kind: ClaudeMessageKind
    text: str

    def __post_init__(self) -> None:
        _ClaudeFieldRules.shapes(self, (("uuid", _TEXT), ("session_id", _TEXT), ("kind", (ClaudeMessageKind,)), ("text", _TEXT)))


_TURN_OUTCOME_SHAPES = (
    ("result_seen", _FLAG),
    ("is_error", _FLAG),
    ("subtype", _TEXT),
    ("terminal_reason", _TEXT),
    ("api_error_status", _OPTIONAL_INT),
    ("structured_output_missing", _FLAG),
    ("permission_denials", _TUPLE),
    ("assistant_errors", _TUPLE),
    ("rate_limit_rejected", _FLAG),
    ("interrupted", _FLAG),
    ("budget_expired", _FLAG),
    ("precondition_failure", _OPTIONAL_FAILURE),
    ("stream_failure", _OPTIONAL_FAILURE),
)


@dataclass(frozen=True, slots=True)
class ClaudeTurnOutcome:
    """What one turn's pump saw: its own latest result, assistant errors, stop flags and failures; the only input of classify_turn."""

    result_seen: bool
    is_error: bool
    subtype: str
    terminal_reason: str
    api_error_status: int | None
    structured_output_missing: bool
    permission_denials: tuple[ClaudePermissionDenial, ...]
    assistant_errors: tuple[str, ...]
    rate_limit_rejected: bool
    interrupted: bool
    budget_expired: bool
    precondition_failure: ClaudeFailure | None
    stream_failure: ClaudeFailure | None

    def __post_init__(self) -> None:
        _ClaudeFieldRules.shapes(self, _TURN_OUTCOME_SHAPES)


@dataclass(frozen=True, slots=True)
class ClaudeSdkTypes:
    """The claude-agent-sdk classes and functions the host uses, loaded on first use by ClaudeSdkLoader."""

    client_class: type
    options_class: type
    agent_definition_class: type
    hook_matcher_class: type
    create_sdk_mcp_server: Callable[..., Any]
    tool: Callable[..., Any]
    list_sessions: Callable[..., Any]
    get_session_info: Callable[..., Any]
    get_session_messages: Callable[..., Any]
    fork_session: Callable[..., Any]
    assistant_message: type
    result_message: type
    rate_limit_event: type
    task_progress_message: type
    task_notification_message: type
    sdk_error: type
    cli_not_found_error: type
    cli_connection_error: type
    process_error: type
    result_error: type
    cli_json_decode_error: type

    def __post_init__(self) -> None:
        for item in fields(self):
            if not callable(getattr(self, item.name)):
                raise _ClaudeFieldRules.invalid(f"ClaudeSdkTypes.{item.name} must be a claude_agent_sdk class or function.")


__all__ = [
    "ClaudeFailure",
    "ClaudeHostSettings",
    "ClaudeModelInfo",
    "ClaudeModelUsage",
    "ClaudePermissionDenial",
    "ClaudeRateLimitWindow",
    "ClaudeReadiness",
    "ClaudeSdkTypes",
    "ClaudeSessionHandle",
    "ClaudeSessionMessage",
    "ClaudeSessionSummary",
    "ClaudeTaskUsage",
    "ClaudeTurnOutcome",
    "ClaudeTurnResult",
    "ClaudeUsageSnapshot",
]
