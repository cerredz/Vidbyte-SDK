"""FILE: vidbyte/lib/dataclasses/codex_host.py

PURPOSE: Defines the fifteen validated records CodexHost takes and returns: the spawn request and goal, turn handles and snapshots, readiness and rate limits, model and thread listings, usage, review targets and the problem record every failure carries.
ROLE IN CODEBASE: The data layer under vidbyte/harnesses/native/codex/ (the host and its translators) and vidbyte/tools/builtins/codex/ (the fifteen tools), which build and read these records; the Codex settings, input, result and usage records they hold come from vidbyte/lib/dataclasses/codex.py.
ARCHITECTURE NOTE: Every record is frozen with slots and checks itself in __post_init__, raising ConfigurationError that names the field; the one exception is a USER approvals reviewer, refused with the CodexAgentError the host's tools report (D-16). Behaviour that acts on these records lives in the host, never here, and every runtime import stays inside vidbyte.lib.
COMMON MODIFICATION PATTERNS: Add a field with its check in the same record's __post_init__, reusing the codex.py helpers; a new record is added here and to the alphabetical __all__.
KNOWN EDGE CASES: bool is an int, so every integer check refuses bool first; NaN and infinity fail the finite checks; vendor text such as plan types and reasoning efforts stays str because Codex owns those open sets.
RELATED DOCS: docs/spec/codex-host/spec.md (sections 8.5 and 9.1)
TESTS: tests/features/codex_host/test_codex_host_records.py
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from vidbyte.lib.constants.codex import (
    CODEX_HOST_MIN_EXCLUSIVE_SECONDS,
    CODEX_HOST_MIN_TOKEN_LIMIT,
    CODEX_HOST_USER_REVIEWER_TEXT,
)
from vidbyte.lib.dataclasses.codex import (
    CodexRunInput,
    CodexRunResult,
    CodexSubagentSettings,
    CodexThreadSettings,
    CodexTurnSettings,
    CodexUsage,
    _is_tool_shaped,
    _optional_text,
    _require_bool,
    _require_non_negative_int,
    _require_text,
)
from vidbyte.lib.dataclasses.security import PermissionPolicy
from vidbyte.lib.enums.codex import (
    CodexAccountKind,
    CodexApprovalMode,
    CodexApprovalPolicy,
    CodexApprovalsReviewer,
    CodexGoalStatus,
    CodexHostOperation,
    CodexReviewTargetKind,
    CodexSandboxReadiness,
    CodexThreadStatus,
    CodexTurnStatus,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError, ConfigurationError

if TYPE_CHECKING:
    from vidbyte.tools.adapters import ToolInput


def _reject_small_int(owner: str, field_name: str, value: object, minimum: int) -> None:
    # Accepts None or an integer at or above the minimum; bool is an int, so it is refused first.
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConfigurationError(f"{owner} {field_name} must be None or an integer of at least {minimum}.")


def _reject_bad_seconds(owner: str, field_name: str, value: object) -> None:
    # Accepts None or a finite number of seconds above the exclusive minimum; bool, NaN and infinity are refused first.
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= CODEX_HOST_MIN_EXCLUSIVE_SECONDS:
        raise ConfigurationError(f"{owner} {field_name} must be None or a finite number of seconds greater than {CODEX_HOST_MIN_EXCLUSIVE_SECONDS:g}.")


def _reject_non_str(owner: str, fields: Mapping[str, object]) -> None:
    # Vendor text may be empty, so only the type is checked.
    for field_name, value in fields.items():
        if not isinstance(value, str):
            raise ConfigurationError(f"{owner} {field_name} must be a string.")


def _reject_optional_count(owner: str, fields: Mapping[str, object]) -> None:
    # Timestamps and counts Codex may leave out are None or non-negative integers.
    for field_name, value in fields.items():
        if value is not None:
            _require_non_negative_int(owner, field_name, value)


def _reject_wrong_type(owner: str, field_name: str, value: object, expected: type, *, optional: bool = False) -> None:
    # One isinstance check with a message naming the field and the expected type.
    if optional and value is None:
        return
    if not isinstance(value, expected):
        suffix = " or None" if optional else ""
        raise ConfigurationError(f"{owner} {field_name} must be a {expected.__name__}{suffix}.")


def _reject_bad_tuple(owner: str, field_name: str, value: object, expected: type) -> None:
    # A tuple, never a list, so the frozen record cannot be changed through it.
    if not isinstance(value, tuple) or any(not isinstance(item, expected) for item in value):
        raise ConfigurationError(f"{owner} {field_name} must be a tuple of {expected.__name__}.")


@dataclass(frozen=True, slots=True)
class CodexGoal:
    """A Codex thread goal: an objective Codex keeps working toward, across turns, until it ends."""

    objective: str
    token_budget: int | None = None

    def __post_init__(self) -> None:
        _require_text("Codex goal", "objective", self.objective)
        _reject_small_int("Codex goal", "token_budget", self.token_budget, CODEX_HOST_MIN_TOKEN_LIMIT)


@dataclass(frozen=True, slots=True)
class CodexSpawnRequest:
    """Everything one CodexHost spawn needs: the prompt or goal, the thread and turn posture, tools and limits.

    ``max_output_tokens`` and ``timeout_seconds`` are not Codex settings:
    Vidbyte enforces each one by sending a single interrupt once the turn's
    own output passes the cap or the time runs out, and tokens Codex has
    already produced still count. Each ``tools`` entry runs in this process
    while Codex waits, and a running tool call blocks every other event and
    response on the same host, so keep tools short, or give tool-using
    threads their own ``CodexHost``.

    ``output_schema`` is sent to Codex with the turn, so Codex is asked to
    answer in that shape. A Pydantic model type is also validated against
    the completed answer. A mapping is checked only for being valid JSON
    and is not compared with the schema. An answer that is not valid JSON,
    or that the model type rejects, gets a schema problem and keeps its raw
    text. A type that is not a Pydantic model, or a mapping that cannot be
    serialized to JSON, is refused before any request.
    """

    prompt: str | CodexRunInput = ""
    thread: CodexThreadSettings = field(default_factory=CodexThreadSettings)
    turn: CodexTurnSettings = field(default_factory=CodexTurnSettings)
    subagents: CodexSubagentSettings | None = None
    developer_instructions: str = ""
    approval_policy: CodexApprovalPolicy = CodexApprovalPolicy.PROVIDER_DEFAULT
    approvals_reviewer: CodexApprovalsReviewer = CodexApprovalsReviewer.PROVIDER_DEFAULT
    tools: tuple[ToolInput, ...] = ()
    tool_permission_policy: PermissionPolicy = field(default_factory=PermissionPolicy)
    disabled_plugin_ids: tuple[str, ...] | None = None
    output_schema: type | Mapping[str, Any] | None = None
    goal: CodexGoal | None = None
    max_output_tokens: int | None = None
    timeout_seconds: float | None = None
    name: str = ""

    def __post_init__(self) -> None:
        # Check each group of fields in turn, so a bad request fails where
        # it is built and the error names the field that is wrong.
        self._reject_bad_prompt()
        self._reject_bad_settings()
        self._reject_bad_approvals()
        self._reject_bad_tools()
        self._reject_bad_goal()

        # The caps are Vidbyte's own interrupts, so they must be real
        # positive numbers rather than anything that compares oddly.
        _reject_small_int("Codex spawn request", "max_output_tokens", self.max_output_tokens, CODEX_HOST_MIN_TOKEN_LIMIT)
        _reject_bad_seconds("Codex spawn request", "timeout_seconds", self.timeout_seconds)

    def _reject_bad_prompt(self) -> None:
        # Only the input items are sent, so context that would be dropped is refused instead.
        if isinstance(self.prompt, str):
            return
        if not isinstance(self.prompt, CodexRunInput):
            raise ConfigurationError("Codex spawn request prompt must be a str or a CodexRunInput.")
        if self.prompt.context_items or self.prompt.context_manager is not None or self.prompt.context_placements:
            raise ConfigurationError("Codex spawn request prompt cannot carry context_items, a context_manager or context_placements.")

    def _reject_bad_settings(self) -> None:
        # The nested settings records validated themselves; only their types are checked here.
        _reject_wrong_type("Codex spawn request", "thread", self.thread, CodexThreadSettings)
        _reject_wrong_type("Codex spawn request", "turn", self.turn, CodexTurnSettings)
        _reject_wrong_type("Codex spawn request", "subagents", self.subagents, CodexSubagentSettings, optional=True)
        _optional_text("Codex spawn request", "developer_instructions", self.developer_instructions)
        _optional_text("Codex spawn request", "name", self.name)

    def _reject_bad_approvals(self) -> None:
        # @intent refuse-unanswerable-approvals
        # A USER reviewer sends approval requests to a human that nothing on
        # the host can answer, so the request is refused with the code and
        # next step the host's tools report. The explicit approval fields
        # replace approval_mode, so the two ways are never mixed.
        _reject_wrong_type("Codex spawn request", "approval_policy", self.approval_policy, CodexApprovalPolicy)
        _reject_wrong_type("Codex spawn request", "approvals_reviewer", self.approvals_reviewer, CodexApprovalsReviewer)
        if self.approvals_reviewer is CodexApprovalsReviewer.USER:
            raise CodexAgentError(
                "Codex spawn request approvals_reviewer=USER sends approval requests to a human, and nothing on a CodexHost can answer them.",
                failure_code=FailureCode.CONFIGURATION_UNSUPPORTED_COMBINATION.value,
                operation=CodexHostOperation.VALIDATE_SPAWN_REQUEST.value,
                next_step=CODEX_HOST_USER_REVIEWER_TEXT,
            )
        explicit = self.approval_policy is not CodexApprovalPolicy.PROVIDER_DEFAULT or self.approvals_reviewer is not CodexApprovalsReviewer.PROVIDER_DEFAULT
        modes = (self.thread.approval_mode, self.turn.approval_mode)
        if explicit and any(mode is not CodexApprovalMode.PROVIDER_DEFAULT for mode in modes):
            raise ConfigurationError("Codex spawn request approval_policy and approvals_reviewer cannot be combined with a thread or turn approval_mode.")

    def _reject_bad_tools(self) -> None:
        # @intent reject-non-tool-declarations-at-construction
        # Duck-typed because vidbyte.lib may not import BaseTool, the same
        # check CodexHarnessAgentSettings applies; the permission policy is
        # the allow-list every dynamic tool call runs under.
        if not isinstance(self.tools, tuple) or any(not callable(value) and not _is_tool_shaped(value) for value in self.tools):
            raise ConfigurationError("Codex spawn request tools must be a tuple of BaseTool instances or @tool functions.")
        _reject_wrong_type("Codex spawn request", "tool_permission_policy", self.tool_permission_policy, PermissionPolicy)
        plugin_ids = self.disabled_plugin_ids
        if plugin_ids is not None and (not isinstance(plugin_ids, tuple) or any(not isinstance(item, str) or not item.strip() for item in plugin_ids)):
            raise ConfigurationError("Codex spawn request disabled_plugin_ids must be None or a tuple of non-empty strings.")
        if self.output_schema is not None and not isinstance(self.output_schema, (type, Mapping)):
            raise ConfigurationError("Codex spawn request output_schema must be None, a type or a mapping.")

    def _reject_bad_goal(self) -> None:
        # A goal is its own run: it replaces the prompt, and Codex keeps goals only on stored threads.
        _reject_wrong_type("Codex spawn request", "goal", self.goal, CodexGoal, optional=True)
        if self.goal is None:
            return
        if isinstance(self.prompt, CodexRunInput) or self.prompt:
            raise ConfigurationError("Codex spawn request goal cannot be combined with a prompt; the goal objective is the prompt.")
        if self.thread.ephemeral:
            raise ConfigurationError("Codex spawn request goal needs a stored thread, so thread.ephemeral must be False.")


@dataclass(frozen=True, slots=True)
class CodexTurnHandle:
    """Names one turn a CodexHost started; a handle rebuilt from the same two ids is equal to it."""

    thread_id: str
    turn_id: str

    def __post_init__(self) -> None:
        _require_text("Codex turn handle", "thread_id", self.thread_id)
        _require_text("Codex turn handle", "turn_id", self.turn_id)


@dataclass(frozen=True, slots=True)
class CodexProblem:
    """One failure as data: its code, what happened, and the next step to take."""

    code: FailureCode
    message: str
    next_step: str

    def __post_init__(self) -> None:
        _reject_wrong_type("Codex problem", "code", self.code, FailureCode)
        _require_text("Codex problem", "message", self.message)
        _require_text("Codex problem", "next_step", self.next_step)


@dataclass(frozen=True, slots=True)
class CodexTurnSnapshot:
    """The state of one turn: running, or how it ended with its result and problem."""

    handle: CodexTurnHandle
    status: CodexTurnStatus
    result: CodexRunResult | None = None
    problem: CodexProblem | None = None
    goal_status: CodexGoalStatus = CodexGoalStatus.NONE

    def __post_init__(self) -> None:
        _reject_wrong_type("Codex turn snapshot", "handle", self.handle, CodexTurnHandle)
        _reject_wrong_type("Codex turn snapshot", "status", self.status, CodexTurnStatus)
        _reject_wrong_type("Codex turn snapshot", "result", self.result, CodexRunResult, optional=True)
        _reject_wrong_type("Codex turn snapshot", "problem", self.problem, CodexProblem, optional=True)
        _reject_wrong_type("Codex turn snapshot", "goal_status", self.goal_status, CodexGoalStatus)
        # A running turn has no outcome yet, a completed one always has its
        # result, and a failed one always says what went wrong.
        if self.status is CodexTurnStatus.RUNNING and (self.result is not None or self.problem is not None):
            raise ConfigurationError("Codex turn snapshot status RUNNING cannot carry a result or a problem.")
        if self.status is CodexTurnStatus.COMPLETED and self.result is None:
            raise ConfigurationError("Codex turn snapshot status COMPLETED requires a result.")
        if self.status is CodexTurnStatus.FAILED and self.problem is None:
            raise ConfigurationError("Codex turn snapshot status FAILED requires a problem.")


@dataclass(frozen=True, slots=True)
class CodexReadiness:
    """Whether Codex can run turns now: version, sign-in, Windows sandbox, and every problem found."""

    ready: bool
    version: str
    minimum_version: str
    signed_in: bool
    account: CodexAccountKind
    plan_type: str
    sandbox: CodexSandboxReadiness
    problems: tuple[CodexProblem, ...]

    def __post_init__(self) -> None:
        _reject_bad_tuple("Codex readiness", "problems", self.problems, CodexProblem)
        _require_bool("Codex readiness", "ready", self.ready)
        if self.ready != (not self.problems):
            raise ConfigurationError("Codex readiness ready must be True exactly when problems is empty.")
        _require_text("Codex readiness", "minimum_version", self.minimum_version)
        _reject_non_str("Codex readiness", {"version": self.version, "plan_type": self.plan_type})
        _require_bool("Codex readiness", "signed_in", self.signed_in)
        _reject_wrong_type("Codex readiness", "account", self.account, CodexAccountKind)
        _reject_wrong_type("Codex readiness", "sandbox", self.sandbox, CodexSandboxReadiness)


@dataclass(frozen=True, slots=True)
class CodexRateLimitWindow:
    """One Codex usage window: how much is used, and when and how long it resets."""

    used_percent: int
    resets_at: int | None
    window_minutes: int | None

    def __post_init__(self) -> None:
        _require_non_negative_int("Codex rate limit window", "used_percent", self.used_percent)
        _reject_optional_count("Codex rate limit window", {"resets_at": self.resets_at, "window_minutes": self.window_minutes})


@dataclass(frozen=True, slots=True)
class CodexRateLimits:
    """The signed-in account's Codex usage windows and whether ordinary usage is still allowed."""

    ordinary_usage_allowed: bool | None
    plan_type: str
    limit_reached: str
    primary: CodexRateLimitWindow | None
    secondary: CodexRateLimitWindow | None

    def __post_init__(self) -> None:
        if self.ordinary_usage_allowed is not None:
            _require_bool("Codex rate limits", "ordinary_usage_allowed", self.ordinary_usage_allowed)
        _reject_non_str("Codex rate limits", {"plan_type": self.plan_type, "limit_reached": self.limit_reached})
        _reject_wrong_type("Codex rate limits", "primary", self.primary, CodexRateLimitWindow, optional=True)
        _reject_wrong_type("Codex rate limits", "secondary", self.secondary, CodexRateLimitWindow, optional=True)


@dataclass(frozen=True, slots=True)
class CodexModelInfo:
    """One model Codex offers: its ids, labels, default and supported reasoning efforts."""

    model_id: str
    model: str
    display_name: str
    description: str
    hidden: bool
    is_default: bool
    default_effort: str
    efforts: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text("Codex model info", "model_id", self.model_id)
        _require_text("Codex model info", "model", self.model)
        _reject_non_str("Codex model info", {"display_name": self.display_name, "description": self.description, "default_effort": self.default_effort})
        _require_bool("Codex model info", "hidden", self.hidden)
        _require_bool("Codex model info", "is_default", self.is_default)
        _reject_bad_tuple("Codex model info", "efforts", self.efforts, str)


@dataclass(frozen=True, slots=True)
class CodexTurnSummary:
    """One stored turn of a thread: its status, final answer and timing, without its items."""

    turn_id: str
    status: CodexTurnStatus
    final_response: str
    error_message: str
    started_at: int | None
    completed_at: int | None

    def __post_init__(self) -> None:
        _require_text("Codex turn summary", "turn_id", self.turn_id)
        _reject_wrong_type("Codex turn summary", "status", self.status, CodexTurnStatus)
        _reject_non_str("Codex turn summary", {"final_response": self.final_response, "error_message": self.error_message})
        _reject_optional_count("Codex turn summary", {"started_at": self.started_at, "completed_at": self.completed_at})


@dataclass(frozen=True, slots=True)
class CodexThreadInfo:
    """One Codex thread as Codex stores it, with turn summaries when they were asked for."""

    thread_id: str
    name: str
    preview: str
    cwd: str
    status: CodexThreadStatus
    model: str
    model_provider: str
    created_at: int
    updated_at: int
    forked_from_id: str
    ephemeral: bool
    turns: tuple[CodexTurnSummary, ...] = ()

    def __post_init__(self) -> None:
        # @intent thread-info-is-checked-where-it-is-built
        # Codex's thread record is checked field by field when it is
        # built, so a malformed answer fails at the wire edge with the
        # field named, not later in a caller.
        _require_text("Codex thread info", "thread_id", self.thread_id)
        text = {"name": self.name, "preview": self.preview, "cwd": self.cwd, "model": self.model, "model_provider": self.model_provider, "forked_from_id": self.forked_from_id}
        _reject_non_str("Codex thread info", text)
        _reject_wrong_type("Codex thread info", "status", self.status, CodexThreadStatus)
        _require_non_negative_int("Codex thread info", "created_at", self.created_at)
        _require_non_negative_int("Codex thread info", "updated_at", self.updated_at)
        _require_bool("Codex thread info", "ephemeral", self.ephemeral)
        _reject_bad_tuple("Codex thread info", "turns", self.turns, CodexTurnSummary)


@dataclass(frozen=True, slots=True)
class CodexThreadPage:
    """One page of a thread listing and the cursor for the next page, empty on the last."""

    threads: tuple[CodexThreadInfo, ...]
    next_cursor: str

    def __post_init__(self) -> None:
        _reject_bad_tuple("Codex thread page", "threads", self.threads, CodexThreadInfo)
        _reject_non_str("Codex thread page", {"next_cursor": self.next_cursor})


@dataclass(frozen=True, slots=True)
class CodexTurnUsage:
    """One turn's own token use on a thread, and whether Codex reported it."""

    turn_id: str
    status: CodexTurnStatus
    usage: CodexUsage
    usage_available: bool

    def __post_init__(self) -> None:
        _require_text("Codex turn usage", "turn_id", self.turn_id)
        _reject_wrong_type("Codex turn usage", "status", self.status, CodexTurnStatus)
        _reject_wrong_type("Codex turn usage", "usage", self.usage, CodexUsage)
        _require_bool("Codex turn usage", "usage_available", self.usage_available)


@dataclass(frozen=True, slots=True)
class CodexThreadUsage:
    """The token use and estimated cost of every turn one host ran on a thread."""

    thread_id: str
    total: CodexUsage
    turns: tuple[CodexTurnUsage, ...]
    cost_usd: float | None
    cost_complete: bool

    def __post_init__(self) -> None:
        _require_text("Codex thread usage", "thread_id", self.thread_id)
        _reject_wrong_type("Codex thread usage", "total", self.total, CodexUsage)
        _reject_bad_tuple("Codex thread usage", "turns", self.turns, CodexTurnUsage)
        cost = self.cost_usd
        if cost is not None and (isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0):
            raise ConfigurationError("Codex thread usage cost_usd must be None or a finite number of at least 0.")
        _require_bool("Codex thread usage", "cost_complete", self.cost_complete)


@dataclass(frozen=True, slots=True)
class CodexReviewTarget:
    """What a Codex review looks at; each kind uses only its own fields and leaves the rest empty."""

    kind: CodexReviewTargetKind
    branch: str = ""
    sha: str = ""
    title: str = ""
    instructions: str = ""

    def __post_init__(self) -> None:
        _reject_wrong_type("Codex review target", "kind", self.kind, CodexReviewTargetKind)
        values = {"branch": self.branch, "sha": self.sha, "title": self.title, "instructions": self.instructions}
        for field_name, value in values.items():
            _optional_text("Codex review target", field_name, value)
        # Each kind needs one field (COMMIT may also carry a title), and a
        # field the kind does not use would be silently ignored, so it must
        # stay empty.
        needed = {
            CodexReviewTargetKind.UNCOMMITTED_CHANGES: (),
            CodexReviewTargetKind.BASE_BRANCH: ("branch",),
            CodexReviewTargetKind.COMMIT: ("sha",),
            CodexReviewTargetKind.CUSTOM: ("instructions",),
        }[self.kind]
        allowed = (*needed, "title") if self.kind is CodexReviewTargetKind.COMMIT else needed
        missing = [name for name in needed if not values[name]]
        unused = [name for name, value in values.items() if value and name not in allowed]
        if missing or unused:
            raise ConfigurationError(f"Codex review target {self.kind.value} needs {', '.join(needed) or 'no fields'}; got empty {missing} and unused {unused}.")


__all__ = [
    "CodexGoal",
    "CodexModelInfo",
    "CodexProblem",
    "CodexRateLimitWindow",
    "CodexRateLimits",
    "CodexReadiness",
    "CodexReviewTarget",
    "CodexSpawnRequest",
    "CodexThreadInfo",
    "CodexThreadPage",
    "CodexThreadUsage",
    "CodexTurnHandle",
    "CodexTurnSnapshot",
    "CodexTurnSummary",
    "CodexTurnUsage",
]
