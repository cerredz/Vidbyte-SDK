"""FILE: vidbyte/lib/dataclasses/codex_host.py

PURPOSE: Defines the twenty-six validated records CodexHost takes and returns: the spawn request and goal, turn handles and snapshots, readiness and rate limits, model and thread listings with their service tiers, usage, review targets, the problem record every failure carries, the thread-helper records (thread summaries, the stored goal, skill listings, and stored turns with their page), and the approval and user-input requests an approval_handler receives with the answers it returns.
ROLE IN CODEBASE: The data layer under vidbyte/harnesses/native/codex/ (the host and its translators) and vidbyte/tools/builtins/codex/ (the twenty-six tools), which build and read these records; the Codex settings, input, result and usage records they hold come from vidbyte/lib/dataclasses/codex.py.
ARCHITECTURE NOTE: Every record is frozen with slots and checks itself in __post_init__, raising ConfigurationError that names the field. A USER approvals reviewer builds, because only the host knows whether an approval_handler can answer it; CodexPreflight refuses it on a host without one (hardening INV-20, D-5). Behaviour that acts on these records lives in the host, never here, and every runtime import stays inside vidbyte.lib.
COMMON MODIFICATION PATTERNS: Add a field with its check in the same record's __post_init__, reusing the codex.py helpers; a new record is added here and to the alphabetical __all__. A new routed server request adds one parse branch to CodexServerRequest.from_params; its wire encoding lives in CodexParamsTranslator, because a lib record exposes no dict encoder.
KNOWN EDGE CASES: bool is an int, so every integer check refuses bool first; NaN and infinity fail the finite checks; vendor text such as plan types, reasoning efforts and service tier ids stays str because Codex owns those open sets. CodexServerRequest.from_params reads an absent and a null optional field alike, and keeps only the string decisions Codex offers, so available_decisions is None when Codex sent no list and a tuple, maybe empty, when it sent one. A goal request refuses the first non-default field of CODEX_HOST_GOAL_REJECTED_FIELDS through _reject_goal_fields, which CodexGoalRunRequest shares; the sandbox-field checks run before it, so a goal request that sets network_access with a default turn is refused for the sandbox (hardening INV-34).
RELATED DOCS: docs/spec/codex-host/spec.md (sections 8.5 and 9.1); docs/spec/codex-host-thread-helpers/spec.md (sections 8.5 and 9.1); docs/spec/codex-host-hardening/spec.md (sections 8.5 and 9.1)
TESTS: tests/features/codex_host/test_codex_host_records.py, tests/features/codex_host/test_codex_host_helper_surface.py and tests/features/codex_host/test_codex_host_hardening_records.py
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from vidbyte.lib.constants.codex import (
    CODEX_HOST_MIN_EXCLUSIVE_SECONDS,
    CODEX_HOST_MIN_TOKEN_LIMIT,
    CODEX_THREAD_SUMMARY_HARNESS,
)
from vidbyte.lib.constants.codex_host import (
    CODEX_HOST_GOAL_FIELD_MESSAGE,
    CODEX_HOST_GOAL_REJECTED_FIELDS,
    CODEX_HOST_NETWORK_ACCESS_MESSAGE,
    CODEX_HOST_WRITABLE_ROOTS_MESSAGE,
)
from vidbyte.lib.dataclasses.codex import (
    CodexItem,
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
    CodexApprovalDecision,
    CodexApprovalMode,
    CodexApprovalPolicy,
    CodexApprovalsReviewer,
    CodexCommandApprovalKind,
    CodexGoalStatus,
    CodexReviewTargetKind,
    CodexSandbox,
    CodexSandboxReadiness,
    CodexServerRequestKind,
    CodexSkillScope,
    CodexThreadStatus,
    CodexTurnStatus,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.tools.adapters import ToolInput


def _reject_small_int(owner: str, field_name: str, value: object, minimum: int) -> None:
    # Accepts None or an integer at or above the minimum; bool is an
    # int, so it is refused first.
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConfigurationError(f"{owner} {field_name} must be None or an integer of at least {minimum}.", details={"field": field_name})


def _reject_bad_seconds(owner: str, field_name: str, value: object) -> None:
    # Accepts None or a finite number of seconds above the exclusive
    # minimum; bool, NaN and infinity are refused first.
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= CODEX_HOST_MIN_EXCLUSIVE_SECONDS:
        raise ConfigurationError(f"{owner} {field_name} must be None or a finite number of seconds greater than {CODEX_HOST_MIN_EXCLUSIVE_SECONDS:g}.", details={"field": field_name})


def _reject_non_str(owner: str, fields: Mapping[str, object]) -> None:
    # Vendor text may be empty, so only the type is checked.
    for field_name, value in fields.items():
        if not isinstance(value, str):
            raise ConfigurationError(f"{owner} {field_name} must be a string.")


def _reject_optional_count(owner: str, fields: Mapping[str, object]) -> None:
    # Timestamps and counts Codex may leave out are None or non-negative
    # integers.
    for field_name, value in fields.items():
        if value is not None:
            _require_non_negative_int(owner, field_name, value)


def _reject_wrong_type(owner: str, field_name: str, value: object, expected: type, *, optional: bool = False) -> None:
    # One isinstance check with a message naming the field and the
    # expected type.
    if optional and value is None:
        return
    if not isinstance(value, expected):
        suffix = " or None" if optional else ""
        raise ConfigurationError(f"{owner} {field_name} must be a {expected.__name__}{suffix}.")


def _reject_bad_tuple(owner: str, field_name: str, value: object, expected: type) -> None:
    # A tuple, never a list, so the frozen record cannot be changed
    # through it.
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

    ``turn_service_tier`` picks a service tier for this turn only, and the
    host checks it against the tiers ``list_codex_models`` reports for the
    model. ``network_access`` and ``writable_roots`` change the turn's
    sandbox: network access needs a READ_ONLY or WORKSPACE_WRITE
    ``turn.sandbox``, and the extra writable folders, each an absolute
    path, need WORKSPACE_WRITE.

    A ``goal`` run takes its posture from the thread settings alone,
    because Codex starts each goal turn itself with the thread's
    settings. A goal request therefore refuses ``turn``,
    ``output_schema``, ``disabled_plugin_ids``, ``turn_service_tier``,
    ``network_access`` and ``writable_roots``; Vidbyte's own caps,
    ``max_output_tokens`` and ``timeout_seconds``, still apply.
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
    turn_service_tier: str = ""
    network_access: bool | None = None
    writable_roots: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Check each group of fields in turn, so a bad request fails
        # where it is built and the error names the field that is wrong.
        self._reject_bad_prompt()
        self._reject_bad_settings()
        self._reject_bad_approvals()
        self._reject_bad_tools()
        self._reject_bad_sandbox_fields()
        self._reject_bad_goal()

        # The caps are Vidbyte's own interrupts, so they must be real
        # positive numbers rather than anything that compares oddly.
        _reject_small_int("Codex spawn request", "max_output_tokens", self.max_output_tokens, CODEX_HOST_MIN_TOKEN_LIMIT)
        _reject_bad_seconds("Codex spawn request", "timeout_seconds", self.timeout_seconds)

    def _reject_bad_prompt(self) -> None:
        # Only the input items are sent, so context that would be
        # dropped is refused instead.
        if isinstance(self.prompt, str):
            return
        if not isinstance(self.prompt, CodexRunInput):
            raise ConfigurationError("Codex spawn request prompt must be a str or a CodexRunInput.")
        if self.prompt.context_items or self.prompt.context_manager is not None or self.prompt.context_placements:
            raise ConfigurationError("Codex spawn request prompt cannot carry context_items, a context_manager or context_placements.")

    def _reject_bad_settings(self) -> None:
        # The nested settings records validated themselves; only their
        # types are checked here.
        _reject_wrong_type("Codex spawn request", "thread", self.thread, CodexThreadSettings)
        _reject_wrong_type("Codex spawn request", "turn", self.turn, CodexTurnSettings)
        _reject_wrong_type("Codex spawn request", "subagents", self.subagents, CodexSubagentSettings, optional=True)
        _optional_text("Codex spawn request", "developer_instructions", self.developer_instructions)
        _optional_text("Codex spawn request", "name", self.name)
        _optional_text("Codex spawn request", "turn_service_tier", self.turn_service_tier)

    def _reject_bad_approvals(self) -> None:
        # @intent approval-fields-are-never-mixed-with-approval-mode
        # The explicit approval fields replace approval_mode, so the two
        # ways are never mixed. A USER reviewer builds here; the host
        # refuses it only when it has no approval_handler to answer it
        # (hardening INV-20, D-5).
        _reject_wrong_type("Codex spawn request", "approval_policy", self.approval_policy, CodexApprovalPolicy)
        _reject_wrong_type("Codex spawn request", "approvals_reviewer", self.approvals_reviewer, CodexApprovalsReviewer)
        explicit = self.approval_policy is not CodexApprovalPolicy.PROVIDER_DEFAULT or self.approvals_reviewer is not CodexApprovalsReviewer.PROVIDER_DEFAULT
        modes = (self.thread.approval_mode, self.turn.approval_mode)
        if explicit and any(mode is not CodexApprovalMode.PROVIDER_DEFAULT for mode in modes):
            raise ConfigurationError("Codex spawn request approval_policy and approvals_reviewer cannot be combined with a thread or turn approval_mode.")

    def _reject_bad_tools(self) -> None:
        # @intent reject-non-tool-declarations-at-construction
        # Duck-typed because vidbyte.lib may not import BaseTool, the
        # same check CodexHarnessAgentSettings applies; the permission
        # policy is the allow-list every dynamic tool call runs under.
        if not isinstance(self.tools, tuple) or any(not callable(value) and not _is_tool_shaped(value) for value in self.tools):
            raise ConfigurationError("Codex spawn request tools must be a tuple of BaseTool instances or @tool functions.")
        _reject_wrong_type("Codex spawn request", "tool_permission_policy", self.tool_permission_policy, PermissionPolicy)
        plugin_ids = self.disabled_plugin_ids
        if plugin_ids is not None and (not isinstance(plugin_ids, tuple) or any(not isinstance(item, str) or not item.strip() for item in plugin_ids)):
            raise ConfigurationError("Codex spawn request disabled_plugin_ids must be None or a tuple of non-empty strings.")
        if self.output_schema is not None and not isinstance(self.output_schema, (type, Mapping)):
            raise ConfigurationError("Codex spawn request output_schema must be None, a type or a mapping.")

    def _reject_bad_sandbox_fields(self) -> None:
        # @intent sandbox-overrides-need-the-sandbox-they-change
        # Both fields are sent inside the turn's sandbox policy, and
        # only some policies have them, so a sandbox without the setting
        # is refused here rather than by Codex mid-run (INV-37).
        if self.network_access is not None:
            _require_bool("Codex spawn request", "network_access", self.network_access)
            if self.turn.sandbox not in (CodexSandbox.READ_ONLY, CodexSandbox.WORKSPACE_WRITE):
                raise ConfigurationError(CODEX_HOST_NETWORK_ACCESS_MESSAGE.format(sandbox=self.turn.sandbox.name), details={"field": "network_access"})
        roots = self.writable_roots
        if roots == ():
            return
        bad_roots = not isinstance(roots, tuple) or any(not isinstance(root, str) or not root or not os.path.isabs(root) for root in roots)
        if bad_roots or self.turn.sandbox is not CodexSandbox.WORKSPACE_WRITE:
            raise ConfigurationError(CODEX_HOST_WRITABLE_ROOTS_MESSAGE, details={"field": "writable_roots"})

    def _reject_bad_goal(self) -> None:
        # A goal is its own run: it replaces the prompt, and Codex keeps
        # goals only on stored threads.
        _reject_wrong_type("Codex spawn request", "goal", self.goal, CodexGoal, optional=True)
        if self.goal is None:
            return
        if isinstance(self.prompt, CodexRunInput) or self.prompt:
            raise ConfigurationError("Codex spawn request goal cannot be combined with a prompt; the goal objective is the prompt.")
        if self.thread.ephemeral:
            raise ConfigurationError("Codex spawn request goal needs a stored thread, so thread.ephemeral must be False.")
        _reject_goal_fields(self)


def _reject_goal_fields(request: CodexSpawnRequest) -> None:
    # @intent a-goal-run-takes-only-thread-settings
    # Codex starts a goal's turns itself with the thread's settings, so
    # a turn-only field would be dropped unapplied; the first one set,
    # in table order, is refused instead (hardening INV-34). A goal
    # spawn and CodexGoalRunRequest share this rule.
    default = CodexSpawnRequest()
    for name in CODEX_HOST_GOAL_REJECTED_FIELDS:
        if getattr(request, name) != getattr(default, name):
            raise ConfigurationError(CODEX_HOST_GOAL_FIELD_MESSAGE.format(name=name), details={"field": name})


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
        # A running turn has no outcome yet, a completed one always has
        # its result, and a failed one always says what went wrong.
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
class CodexServiceTier:
    """One service tier a Codex model offers, such as fast or flex, with its label and description."""

    tier_id: str
    name: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        _require_text("Codex service tier", "tier_id", self.tier_id)
        _reject_non_str("Codex service tier", {"name": self.name, "description": self.description})


@dataclass(frozen=True, slots=True)
class CodexModelInfo:
    """One model Codex offers: its ids, labels, default and supported reasoning efforts, and its service tiers."""

    model_id: str
    model: str
    display_name: str
    description: str
    hidden: bool
    is_default: bool
    default_effort: str
    efforts: tuple[str, ...]
    service_tiers: tuple[CodexServiceTier, ...] = ()
    default_service_tier: str = ""

    def __post_init__(self) -> None:
        _require_text("Codex model info", "model_id", self.model_id)
        _require_text("Codex model info", "model", self.model)
        text = {"display_name": self.display_name, "description": self.description, "default_effort": self.default_effort, "default_service_tier": self.default_service_tier}
        _reject_non_str("Codex model info", text)
        _require_bool("Codex model info", "hidden", self.hidden)
        _require_bool("Codex model info", "is_default", self.is_default)
        _reject_bad_tuple("Codex model info", "efforts", self.efforts, str)
        _reject_bad_tuple("Codex model info", "service_tiers", self.service_tiers, CodexServiceTier)


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
        # Each kind needs one field (COMMIT may also carry a title), and
        # a field the kind does not use would be silently ignored, so it
        # must stay empty.
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


@dataclass(frozen=True, slots=True)
class CodexThreadSummary:
    """One Codex thread in the cross-harness summary shape: ids, title, times, parent and model."""

    harness: str = field(default=CODEX_THREAD_SUMMARY_HARNESS, init=False)
    thread_id: str
    title: str | None
    created_at: int
    updated_at: int
    parent_thread_id: str | None
    model: str

    def __post_init__(self) -> None:
        _require_text("Codex thread summary", "thread_id", self.thread_id)
        _reject_wrong_type("Codex thread summary", "title", self.title, str, optional=True)
        _require_non_negative_int("Codex thread summary", "created_at", self.created_at)
        _require_non_negative_int("Codex thread summary", "updated_at", self.updated_at)
        _reject_wrong_type("Codex thread summary", "parent_thread_id", self.parent_thread_id, str, optional=True)
        _reject_non_str("Codex thread summary", {"model": self.model})


@dataclass(frozen=True, slots=True)
class CodexThreadGoal:
    """A thread's stored goal as Codex reports it: objective, status, budget and use so far."""

    thread_id: str
    objective: str
    status: CodexGoalStatus
    token_budget: int | None
    tokens_used: int
    time_used_seconds: int
    created_at: int
    updated_at: int

    def __post_init__(self) -> None:
        _require_text("Codex thread goal", "thread_id", self.thread_id)
        _require_text("Codex thread goal", "objective", self.objective)
        _reject_wrong_type("Codex thread goal", "status", self.status, CodexGoalStatus)
        # NONE means "no goal", which a stored goal can never be.
        if self.status is CodexGoalStatus.NONE:
            raise ConfigurationError("Codex thread goal status must be a goal status other than NONE.")
        _reject_optional_count("Codex thread goal", {"token_budget": self.token_budget})
        counts = {"tokens_used": self.tokens_used, "time_used_seconds": self.time_used_seconds, "created_at": self.created_at, "updated_at": self.updated_at}
        for field_name, value in counts.items():
            _require_non_negative_int("Codex thread goal", field_name, value)


@dataclass(frozen=True, slots=True)
class CodexSkillInfo:
    """One skill Codex lists for a folder: its name, description, SKILL.md path, scope and switch."""

    name: str
    description: str
    path: str
    scope: CodexSkillScope
    enabled: bool

    def __post_init__(self) -> None:
        _require_text("Codex skill info", "name", self.name)
        _reject_non_str("Codex skill info", {"description": self.description})
        _require_text("Codex skill info", "path", self.path)
        _reject_wrong_type("Codex skill info", "scope", self.scope, CodexSkillScope)
        _require_bool("Codex skill info", "enabled", self.enabled)


@dataclass(frozen=True, slots=True)
class CodexStoredTurn:
    """One stored turn of a thread with every item Codex kept for it, in order."""

    turn_id: str
    status: CodexTurnStatus
    final_response: str
    error_message: str
    started_at: int | None
    completed_at: int | None
    items: tuple[CodexItem, ...]

    def __post_init__(self) -> None:
        _require_text("Codex stored turn", "turn_id", self.turn_id)
        _reject_wrong_type("Codex stored turn", "status", self.status, CodexTurnStatus)
        _reject_non_str("Codex stored turn", {"final_response": self.final_response, "error_message": self.error_message})
        _reject_optional_count("Codex stored turn", {"started_at": self.started_at, "completed_at": self.completed_at})
        _reject_bad_tuple("Codex stored turn", "items", self.items, CodexItem)


@dataclass(frozen=True, slots=True)
class CodexTurnPage:
    """One page of a thread's stored turns, oldest first, and the cursor for the next page."""

    turns: tuple[CodexStoredTurn, ...]
    next_cursor: str

    def __post_init__(self) -> None:
        _reject_bad_tuple("Codex turn page", "turns", self.turns, CodexStoredTurn)
        _reject_non_str("Codex turn page", {"next_cursor": self.next_cursor})


@dataclass(frozen=True, slots=True)
class CodexUserInputOption:
    """One answer Codex offers for a user-input question: its label and what it means."""

    label: str
    description: str = ""

    def __post_init__(self) -> None:
        _require_text("Codex user input option", "label", self.label)
        _reject_non_str("Codex user input option", {"description": self.description})


@dataclass(frozen=True, slots=True)
class CodexUserInputQuestion:
    """One question Codex asks the user mid-turn, with the answers it offers, if any."""

    question_id: str
    header: str
    question: str
    options: tuple[CodexUserInputOption, ...] = ()
    is_other: bool = False
    is_secret: bool = False

    def __post_init__(self) -> None:
        # @intent a-secret-question-is-only-marked-here
        # is_secret tells the handler to hide what the user types; the
        # record only carries the flag and never logs the question.
        _require_text("Codex user input question", "question_id", self.question_id)
        _reject_non_str("Codex user input question", {"header": self.header, "question": self.question})
        _reject_bad_tuple("Codex user input question", "options", self.options, CodexUserInputOption)
        _require_bool("Codex user input question", "is_other", self.is_other)
        _require_bool("Codex user input question", "is_secret", self.is_secret)


@dataclass(frozen=True, slots=True)
class CodexServerRequest:
    """One approval or user-input request Codex sends mid-turn, as an approval_handler receives it.

    ``available_decisions`` is None when Codex sent no list, and otherwise
    holds the decisions Codex offers that this release knows, in Codex's
    order, so an empty tuple means only decline or cancel can answer it.
    ``questions`` is filled only for a USER_INPUT request.
    """

    kind: CodexServerRequestKind
    thread_id: str
    turn_id: str
    item_id: str
    approval_kind: CodexCommandApprovalKind = CodexCommandApprovalKind.COMMAND
    approval_id: str = ""
    environment_id: str = ""
    started_at_ms: int = 0
    reason: str = ""
    command: str = ""
    cwd: str = ""
    grant_root: str = ""
    available_decisions: tuple[CodexApprovalDecision, ...] | None = None
    questions: tuple[CodexUserInputQuestion, ...] = ()
    is_blocking: bool = False

    def __post_init__(self) -> None:
        _reject_wrong_type("Codex server request", "kind", self.kind, CodexServerRequestKind)
        for field_name, value in {"thread_id": self.thread_id, "turn_id": self.turn_id, "item_id": self.item_id}.items():
            _require_text("Codex server request", field_name, value)
        _reject_wrong_type("Codex server request", "approval_kind", self.approval_kind, CodexCommandApprovalKind)
        text = {"approval_id": self.approval_id, "environment_id": self.environment_id, "reason": self.reason, "command": self.command, "cwd": self.cwd, "grant_root": self.grant_root}
        _reject_non_str("Codex server request", text)
        _require_non_negative_int("Codex server request", "started_at_ms", self.started_at_ms)
        if self.available_decisions is not None:
            _reject_bad_tuple("Codex server request", "available_decisions", self.available_decisions, CodexApprovalDecision)
        _reject_bad_tuple("Codex server request", "questions", self.questions, CodexUserInputQuestion)
        if self.questions and self.kind is not CodexServerRequestKind.USER_INPUT:
            raise ConfigurationError("Codex server request questions belong only to a USER_INPUT request.")
        _require_bool("Codex server request", "is_blocking", self.is_blocking)

    @classmethod
    def from_params(cls, kind: CodexServerRequestKind, params: Mapping[str, Any] | None) -> CodexServerRequest:
        """Read one routed server request from Codex's camelCase wire params; a malformed one raises ConfigurationError."""
        # @intent read-a-server-request-as-codex-sends-it
        # Codex leaves a key out and sends null to mean the same thing,
        # so both read as the record's default, and unknown keys are
        # ignored. The record's own checks then refuse a missing id or a
        # value of the wrong type, which the router answers by default.
        if not isinstance(params, Mapping):
            raise ConfigurationError("Codex server request params must be a mapping.")
        sent = {key: value for key, value in params.items() if value is not None}

        # Keep only the decisions this release can answer with, and read
        # each question with its options.
        decisions = cls._wire_decisions(sent.get("availableDecisions"))
        questions = sent.get("questions", [])
        if not isinstance(questions, list):
            raise ConfigurationError("Codex server request questions must be a list.")
        return cls(
            kind=kind,
            thread_id=sent.get("threadId", ""),
            turn_id=sent.get("turnId", ""),
            item_id=sent.get("itemId", ""),
            approval_kind=cls._wire_approval_kind(sent.get("kind", CodexCommandApprovalKind.COMMAND)),
            approval_id=sent.get("approvalId", ""),
            environment_id=sent.get("environmentId", ""),
            started_at_ms=sent.get("startedAtMs", 0),
            reason=sent.get("reason", ""),
            command=sent.get("command", ""),
            cwd=sent.get("cwd", ""),
            grant_root=sent.get("grantRoot", ""),
            available_decisions=decisions,
            questions=tuple(cls._wire_question(raw) for raw in questions),
            is_blocking=sent.get("isBlocking", False),
        )

    @staticmethod
    def _wire_approval_kind(value: object) -> CodexCommandApprovalKind:
        # An unknown kind is a parse failure, so the request is declined
        # rather than read as a plain command (EC-4).
        try:
            return CodexCommandApprovalKind(value)
        except ValueError:
            raise ConfigurationError("Codex server request approval_kind must be command or writeStdin.") from None

    @staticmethod
    def _wire_decisions(value: object) -> tuple[CodexApprovalDecision, ...] | None:
        # No list stays None; a list keeps its known string decisions in
        # Codex's order and drops object and unknown ones (EC-5).
        if value is None:
            return None
        if not isinstance(value, list):
            raise ConfigurationError("Codex server request available_decisions must be a list.")
        known = {member.value: member for member in CodexApprovalDecision}
        return tuple(known[item] for item in value if isinstance(item, str) and item in known)

    @staticmethod
    def _wire_question(raw: object) -> CodexUserInputQuestion:
        # A question and its options read absent and null values
        # as the record defaults; a missing id or label fails the
        # record checks.
        if not isinstance(raw, Mapping):
            raise ConfigurationError("Codex server request questions must hold objects.")
        sent = {key: value for key, value in raw.items() if value is not None}
        options = sent.get("options", [])
        if not isinstance(options, list) or any(not isinstance(option, Mapping) for option in options):
            raise ConfigurationError("Codex user input question options must be a list of objects.")
        choices = [{key: value for key, value in option.items() if value is not None} for option in options]
        return CodexUserInputQuestion(
            question_id=sent.get("id", ""),
            header=sent.get("header", ""),
            question=sent.get("question", ""),
            options=tuple(CodexUserInputOption(label=choice.get("label", ""), description=choice.get("description", "")) for choice in choices),
            is_other=sent.get("isOther", False),
            is_secret=sent.get("isSecret", False),
        )


@dataclass(frozen=True, slots=True)
class CodexUserInputAnswer:
    """The user's answers to one question, named by the question's id."""

    question_id: str
    answers: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text("Codex user input answer", "question_id", self.question_id)
        _reject_bad_tuple("Codex user input answer", "answers", self.answers, str)


@dataclass(frozen=True, slots=True)
class CodexServerAnswer:
    """An approval_handler's answer to one server request: a decision, and for user input its answers."""

    decision: CodexApprovalDecision
    answers: tuple[CodexUserInputAnswer, ...] = ()

    def __post_init__(self) -> None:
        _reject_wrong_type("Codex server answer", "decision", self.decision, CodexApprovalDecision)
        _reject_bad_tuple("Codex server answer", "answers", self.answers, CodexUserInputAnswer)
        # Each question is answered at most once, and answers only go
        # with ACCEPT, because declining or cancelling sends none.
        question_ids = [answer.question_id for answer in self.answers]
        if len(set(question_ids)) != len(question_ids):
            raise ConfigurationError("Codex server answer answers must answer each question at most once.")
        if self.answers and self.decision is not CodexApprovalDecision.ACCEPT:
            raise ConfigurationError("Codex server answer answers go only with the ACCEPT decision.")


__all__ = [
    "CodexGoal",
    "CodexModelInfo",
    "CodexProblem",
    "CodexRateLimitWindow",
    "CodexRateLimits",
    "CodexReadiness",
    "CodexReviewTarget",
    "CodexServerAnswer",
    "CodexServerRequest",
    "CodexServiceTier",
    "CodexSkillInfo",
    "CodexSpawnRequest",
    "CodexStoredTurn",
    "CodexThreadGoal",
    "CodexThreadInfo",
    "CodexThreadPage",
    "CodexThreadSummary",
    "CodexThreadUsage",
    "CodexTurnHandle",
    "CodexTurnPage",
    "CodexTurnSnapshot",
    "CodexTurnSummary",
    "CodexTurnUsage",
    "CodexUserInputAnswer",
    "CodexUserInputOption",
    "CodexUserInputQuestion",
]
