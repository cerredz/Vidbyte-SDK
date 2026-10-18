"""FILE: vidbyte/lib/dataclasses/codex_host_inputs.py

PURPOSE: Defines the thirty-four validated input records of CodexHost: the constructor's CodexHostSetup, which checks the settings and the approval_handler, and one record per public function, or per family of functions that share one shape, which checks every argument the caller passed before the host sends anything to Codex. The seventeen first-class-feature records cover thread and turn settings, plan runs, multi-turn waits, MCP servers, memories, side chats, worktrees, goal control, thread lifecycle, history injection, background terminals, content search and child threads.
ROLE IN CODEBASE: The input layer under vidbyte/harnesses/native/codex/; CodexHost.__init__ builds CodexHostSetup first, and each CodexHost method keeps its keyword signature, builds its record right after its guard, and hands the record's checked fields to its helpers and to CodexThreadHelpers and CodexSkillFunctions.
ARCHITECTURE NOTE: Every record is frozen with slots and checks itself in __post_init__ through RecordFieldValidator and RecordFieldConverter, and through the codex_host.py rules a turn already owns for seconds and counts, so each check keeps one owner. A field name in a message starts with the function the caller called, because callers never build these records themselves; a record that serves several functions carries that operation as its first field.
COMMON MODIFICATION PATTERNS: A new CodexHost method gets one record here, or reuses CodexThreadRef or CodexTurnRef, and builds it after its guard; a new per-operation field rule is one entry in CODEX_HOST_REJECTED_FIELDS (vidbyte/lib/constants/codex_host.py).
KNOWN EDGE CASES: A str prompt is stored as CodexRunInput.text(prompt), so the host reads one input type. Wait handles and injected items are stored as tuples, and each injected item as a JSON round-trip copy, so a later change by the caller changes nothing sent; a str is never a sequence of handles or items. A worktree repository is stored as a Path that already exists; one whose stat the system refuses gets the same refusal, raised from None so the path never reaches the caller. Its branch and base ref follow GIT_REF_PATTERN, so neither can reach git as an option. Launch prompts may arrive as a list and are stored as a tuple; one str is refused, because it is a sequence of characters, not of prompts. The listing limits, since and query keep the exact thread-helpers section 9.2 messages. An approval_handler counts as async when inspect.iscoroutinefunction is true of it or of its __call__, so a sync function that returns a coroutine is refused. A review's request is checked as given, so the host substitutes the default only for None.
RELATED DOCS: docs/spec/codex-host/spec.md (sections 8.5 and 9.2 per-operation field rules); docs/spec/codex-host-thread-helpers/spec.md (section 9.2); docs/spec/codex-host-hardening/spec.md (section 9.1); docs/spec/codex-host-first-class/spec.md (section 9.1, the 17 input records); vidbyte/lib/dataclasses/validation.py
TESTS: tests/features/codex_host/test_codex_host_inputs.py, tests/features/codex_host/test_codex_host_hardening_contract.py and tests/features/codex_host/test_codex_host_feature_records.py
"""

from __future__ import annotations

import inspect
import json
import operator
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vidbyte.lib.constants.codex import (
    CODEX_HOST_MIN_LIST_LIMIT,
    CODEX_HOST_MIN_LIVE_TURNS,
    CODEX_HOST_MIN_TOKEN_LIMIT,
    CODEX_HOST_THREAD_LIST_MAX_LIMIT,
)
from vidbyte.lib.constants.codex_host import (
    CODEX_HOST_APPROVAL_HANDLER_MESSAGE,
    CODEX_HOST_BUDGET_CLEAR_CONFLICT_MESSAGE,
    CODEX_HOST_EPHEMERAL_SKILL_MESSAGE,
    CODEX_HOST_FORK_POINTS_MESSAGE,
    CODEX_HOST_GOAL_EDIT_EMPTY_MESSAGE,
    CODEX_HOST_INJECT_ITEMS_MESSAGE,
    CODEX_HOST_INJECT_MAX_ITEMS,
    CODEX_HOST_LAUNCH_OVER_LIMIT_MESSAGE,
    CODEX_HOST_LAUNCH_PROMPTS_MESSAGE,
    CODEX_HOST_LIMIT_MESSAGE,
    CODEX_HOST_LISTING_OPERATION_MESSAGE,
    CODEX_HOST_MEMORY_MAX_CONSOLIDATED_THREADS,
    CODEX_HOST_MEMORY_MIN_CONSOLIDATED_THREADS,
    CODEX_HOST_OWN_INPUT_MESSAGE,
    CODEX_HOST_QUERY_MESSAGE,
    CODEX_HOST_REJECTED_FIELDS,
    CODEX_HOST_RUN_INPUT_MESSAGE,
    CODEX_HOST_SETTINGS_EMPTY_MESSAGE,
    CODEX_HOST_SINCE_MESSAGE,
    CODEX_HOST_SKILL_NAME_MESSAGE,
    CODEX_HOST_SKILL_OPERATION_MESSAGE,
    CODEX_HOST_TIER_CLEAR_CONFLICT_MESSAGE,
    CODEX_HOST_UNUSED_ARGUMENT_MESSAGE,
    CODEX_HOST_UNUSED_FIELD_MESSAGE,
    CODEX_HOST_WAIT_HANDLES_MESSAGE,
    CODEX_HOST_WAIT_MAX_HANDLES,
    CODEX_HOST_WORKTREE_REF_MESSAGE,
    CODEX_HOST_WORKTREE_REPOSITORY_MESSAGE,
)
from vidbyte.lib.constants.native_threads import GIT_REF_MAX_CHARS, GIT_REF_PATTERN
from vidbyte.lib.dataclasses.codex import CodexClientSettings, CodexRunInput
from vidbyte.lib.dataclasses.codex_host import (
    CodexGoal,
    CodexReviewTarget,
    CodexServerAnswer,
    CodexServerRequest,
    CodexSpawnRequest,
    CodexTurnHandle,
    _reject_bad_seconds,
    _reject_goal_fields,
    _reject_small_int,
)
from vidbyte.lib.dataclasses.codex_host_features import CodexThreadSettingsUpdate
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.codex import (
    CodexApprovalsReviewer,
    CodexHostOperation,
    CodexMcpServerDetail,
    CodexMemoryMode,
    CodexReasoningEffort,
    CodexReasoningSummary,
    CodexReviewDelivery,
    CodexSortDirection,
    CodexThreadSortKey,
    CodexThreadSourceKind,
    CodexTurnWaitMode,
)
from vidbyte.lib.errors import ConfigurationError


def _run_input(value: object, field_name: str) -> CodexRunInput:
    # A str becomes one text item; a CodexRunInput must carry no
    # context, because only its input items are sent to Codex and the
    # context would be dropped silently.
    run_input = CodexRunInput.text(value) if isinstance(value, str) else value
    if not isinstance(run_input, CodexRunInput) or run_input.context_items or run_input.context_manager is not None or run_input.context_placements:
        raise ConfigurationError(CODEX_HOST_RUN_INPUT_MESSAGE.format(field=field_name, kind=type(value).__name__), details={"field": field_name})
    return run_input


def _reject_unused_fields(operation: CodexHostOperation, request: object) -> None:
    # The request must be a CodexSpawnRequest, and every field this
    # operation cannot apply must keep its default, so no setting is
    # ever dropped unapplied (INV-27).
    RecordFieldConverter.require_instance(request, f"{operation.value} request", CodexSpawnRequest)
    default = CodexSpawnRequest()
    for name in CODEX_HOST_REJECTED_FIELDS.get(operation, ()):
        read = operator.attrgetter(name)
        if read(request) != read(default):
            raise ConfigurationError(CODEX_HOST_UNUSED_FIELD_MESSAGE.format(operation=operation.value, name=name), details={"field": name})


def _reject_bad_list_limit(operation: CodexHostOperation, limit: object) -> None:
    # A thread listing's page size, refused with the thread-helpers
    # spec's own message rather than the canonical check's.
    try:
        RecordFieldValidator.require_int(limit, "limit", minimum=CODEX_HOST_MIN_LIST_LIMIT, maximum=CODEX_HOST_THREAD_LIST_MAX_LIMIT)
    except ConfigurationError:
        raise ConfigurationError(CODEX_HOST_LIMIT_MESSAGE.format(operation=operation.value, minimum=CODEX_HOST_MIN_LIST_LIMIT, maximum=CODEX_HOST_THREAD_LIST_MAX_LIMIT), details={"field": "limit"}) from None


@dataclass(frozen=True, slots=True)
class CodexHostSetup:
    """The input of the CodexHost constructor: the client settings, and the async approval_handler, if any."""

    settings: CodexClientSettings | None = None
    approval_handler: Callable[[CodexServerRequest], Awaitable[CodexServerAnswer]] | None = None

    def __post_init__(self) -> None:
        # @intent the-approval-handler-is-checked-when-the-host-is-built
        # The router awaits the handler on the host's loop, so only an
        # async function, or an object whose __call__ is one, can
        # answer; anything else is refused now rather than mid-turn
        # (INV-19).
        RecordFieldConverter.require_instance(self.settings, "CodexHost settings", CodexClientSettings, optional=True)
        handler = self.approval_handler
        if handler is not None and not (callable(handler) and (inspect.iscoroutinefunction(handler) or inspect.iscoroutinefunction(type(handler).__call__))):
            raise ConfigurationError(CODEX_HOST_APPROVAL_HANDLER_MESSAGE.format(kind=type(handler).__name__), details={"field": "approval_handler"})


@dataclass(frozen=True, slots=True)
class CodexModelListRequest:
    """The input of list_codex_models: whether hidden models are listed too."""

    include_hidden: bool = False

    def __post_init__(self) -> None:
        RecordFieldValidator.require_bool(self.include_hidden, "list_codex_models include_hidden")


@dataclass(frozen=True, slots=True)
class CodexThreadRef:
    """One stored thread named by id, for each CodexHost function whose only input is that thread."""

    operation: CodexHostOperation
    thread_id: str

    def __post_init__(self) -> None:
        RecordFieldValidator.require_enum(self.operation, CodexHostOperation, "CodexThreadRef.operation")
        RecordFieldValidator.require_text(self.thread_id, f"{self.operation.value} thread_id", one_line=True)


@dataclass(frozen=True, slots=True)
class CodexTurnRef:
    """One turn named by the handle a CodexHost returned, for each function whose only input is that handle."""

    operation: CodexHostOperation
    handle: CodexTurnHandle

    def __post_init__(self) -> None:
        RecordFieldValidator.require_enum(self.operation, CodexHostOperation, "CodexTurnRef.operation")
        RecordFieldConverter.require_instance(self.handle, f"{self.operation.value} handle", CodexTurnHandle)


@dataclass(frozen=True, slots=True)
class CodexThreadReadRequest:
    """The input of read_codex_thread: the thread, and whether its turn summaries come back."""

    thread_id: str
    include_turns: bool = False

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.thread_id, "read_codex_thread thread_id", one_line=True)
        RecordFieldValidator.require_bool(self.include_turns, "read_codex_thread include_turns")


@dataclass(frozen=True, slots=True)
class CodexContinueRequest:
    """The input of continue_codex_thread: the thread, the next turn's input, and the overrides continue can apply."""

    thread_id: str
    run_input: str | CodexRunInput
    overrides: CodexSpawnRequest = field(default_factory=CodexSpawnRequest)

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.thread_id, "continue_codex_thread thread_id", one_line=True)
        _reject_unused_fields(CodexHostOperation.CONTINUE_CODEX_THREAD, self.overrides)
        object.__setattr__(self, "run_input", _run_input(self.run_input, "continue_codex_thread input"))


@dataclass(frozen=True, slots=True)
class CodexForkRequest:
    """The input of fork_codex_thread: the thread, the turn to fork through or before, and the overrides a fork can apply."""

    thread_id: str
    from_turn_id: str = ""
    exclude_turns: bool = False
    overrides: CodexSpawnRequest = field(default_factory=CodexSpawnRequest)
    before_turn_id: str = ""
    defer_goal_continuation: bool = False

    def __post_init__(self) -> None:
        # An empty from_turn_id means the latest completed turn, and a
        # fork names at most one fork point (INV-28 step 1).
        RecordFieldValidator.require_text(self.thread_id, "fork_codex_thread thread_id", one_line=True)
        RecordFieldValidator.require_text(self.from_turn_id, "fork_codex_thread from_turn_id", allow_blank=True, one_line=True)
        RecordFieldValidator.require_bool(self.exclude_turns, "fork_codex_thread exclude_turns")
        RecordFieldValidator.require_text(self.before_turn_id, "fork_codex_thread before_turn_id", allow_blank=True, one_line=True)
        RecordFieldValidator.require_bool(self.defer_goal_continuation, "fork_codex_thread defer_goal_continuation")
        if self.from_turn_id and self.before_turn_id:
            raise ConfigurationError(CODEX_HOST_FORK_POINTS_MESSAGE, details={"field": "before_turn_id"})
        _reject_unused_fields(CodexHostOperation.FORK_CODEX_THREAD, self.overrides)


@dataclass(frozen=True, slots=True)
class CodexThreadListRequest:
    """The input of list_codex_threads: the filters, sort, cursor and size of one page; empty values keep Codex's defaults."""

    cwd: str = ""
    search: str = ""
    archived: bool = False
    source_kinds: tuple[CodexThreadSourceKind, ...] = ()
    sort: CodexThreadSortKey = CodexThreadSortKey.PROVIDER_DEFAULT
    sort_direction: CodexSortDirection = CodexSortDirection.PROVIDER_DEFAULT
    cursor: str = ""
    limit: int | None = None

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.cwd, "list_codex_threads cwd", allow_blank=True)
        RecordFieldValidator.require_text(self.search, "list_codex_threads search", allow_blank=True)
        RecordFieldValidator.require_bool(self.archived, "list_codex_threads archived")
        object.__setattr__(self, "source_kinds", RecordFieldConverter.to_tuple(self.source_kinds, "list_codex_threads source_kinds", item_type=CodexThreadSourceKind))
        RecordFieldValidator.require_enum(self.sort, CodexThreadSortKey, "list_codex_threads sort")
        RecordFieldValidator.require_enum(self.sort_direction, CodexSortDirection, "list_codex_threads sort_direction")
        RecordFieldValidator.require_text(self.cursor, "list_codex_threads cursor", allow_blank=True, one_line=True)
        if self.limit is not None:
            _reject_bad_list_limit(CodexHostOperation.LIST_CODEX_THREADS, self.limit)


@dataclass(frozen=True, slots=True)
class CodexTurnWaitRequest:
    """The input of wait_codex_turn: the turn, and at most how long to wait; None waits until it ends."""

    handle: CodexTurnHandle
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        # A wait takes exactly the timeouts a turn does, so the turn's
        # own seconds rule checks it.
        RecordFieldConverter.require_instance(self.handle, "wait_codex_turn handle", CodexTurnHandle)
        _reject_bad_seconds("wait_codex_turn", "timeout_seconds", self.timeout_seconds)


@dataclass(frozen=True, slots=True)
class CodexTurnSteerRequest:
    """The input of steer_codex_turn: the running turn, and the input added to it."""

    handle: CodexTurnHandle
    run_input: str | CodexRunInput

    def __post_init__(self) -> None:
        RecordFieldConverter.require_instance(self.handle, "steer_codex_turn handle", CodexTurnHandle)
        object.__setattr__(self, "run_input", _run_input(self.run_input, "steer_codex_turn input"))


@dataclass(frozen=True, slots=True)
class CodexSubagentLaunchRequest:
    """The input of launch_codex_subagents: one prompt per new thread, the request they share, and the batch limit."""

    prompts: Sequence[str | CodexRunInput]
    request: CodexSpawnRequest = field(default_factory=CodexSpawnRequest)
    limit: int | None = None

    def __post_init__(self) -> None:
        # The request may carry no prompt or goal of its own. The
        # prompts are a non-empty sequence, never one str, that fits
        # the limit, and each becomes its own thread's input.
        _reject_unused_fields(CodexHostOperation.LAUNCH_CODEX_SUBAGENTS, self.request)
        if isinstance(self.prompts, str) or not isinstance(self.prompts, Sequence) or not self.prompts:
            received = f"an empty {type(self.prompts).__name__}" if isinstance(self.prompts, Sequence) and not self.prompts else f"a value of type {type(self.prompts).__name__}"
            raise ConfigurationError(CODEX_HOST_LAUNCH_PROMPTS_MESSAGE.format(received=received), details={"field": "prompts"})
        _reject_small_int("launch_codex_subagents", "limit", self.limit, CODEX_HOST_MIN_LIVE_TURNS)
        if self.limit is not None and len(self.prompts) > self.limit:
            raise ConfigurationError(CODEX_HOST_LAUNCH_OVER_LIMIT_MESSAGE.format(count=len(self.prompts), limit=self.limit), details={"field": "limit"})
        prompts = RecordFieldConverter.to_tuple(self.prompts, "launch_codex_subagents prompts", item_type=(str, CodexRunInput))
        object.__setattr__(self, "prompts", tuple(_run_input(prompt, f"launch_codex_subagents prompts[{index}]") for index, prompt in enumerate(prompts)))


@dataclass(frozen=True, slots=True)
class CodexReviewRequest:
    """The input of start_codex_review: the thread, what the review looks at, where its findings go, and its caps."""

    thread_id: str
    target: CodexReviewTarget
    delivery: CodexReviewDelivery = CodexReviewDelivery.INLINE
    request: CodexSpawnRequest = field(default_factory=CodexSpawnRequest)

    def __post_init__(self) -> None:
        # A review runs in its thread's own posture, so its request may
        # carry only Vidbyte's time and token caps (INV-30).
        RecordFieldValidator.require_text(self.thread_id, "start_codex_review thread_id", one_line=True)
        RecordFieldConverter.require_instance(self.target, "start_codex_review target", CodexReviewTarget)
        RecordFieldValidator.require_enum(self.delivery, CodexReviewDelivery, "start_codex_review delivery")
        _reject_unused_fields(CodexHostOperation.START_CODEX_REVIEW, self.request)


@dataclass(frozen=True, slots=True)
class CodexThreadListing:
    """The input of the recent, since and search thread listings, which share one bounded page walk."""

    operation: CodexHostOperation
    cwd: str
    limit: int
    query: str = ""
    since: int | None = None

    def __post_init__(self) -> None:
        # @intent every-listing-argument-is-sent-as-given
        # A falsy limit or query would be left out of the request, so
        # Codex would apply its own page size or list every thread,
        # and a float since would compare silently with integer times
        # (INV-6). The canonical checks own each rule; the messages are
        # the thread-helpers spec's own.
        operation = RecordFieldValidator.require_enum(self.operation, CodexHostOperation, "CodexThreadListing.operation")
        if operation not in (CodexHostOperation.LIST_RECENT_CODEX_THREADS, CodexHostOperation.LIST_CODEX_THREADS_SINCE, CodexHostOperation.SEARCH_CODEX_THREADS):
            raise ConfigurationError(CODEX_HOST_LISTING_OPERATION_MESSAGE.format(operation=operation.value), details={"field": "operation"})
        RecordFieldValidator.require_text(self.cwd, f"{operation.value} cwd", allow_blank=True)
        _reject_bad_list_limit(operation, self.limit)
        # The window and the query belong to one listing each.
        if operation is CodexHostOperation.LIST_CODEX_THREADS_SINCE:
            try:
                RecordFieldValidator.require_int(self.since, "since", minimum=0)
            except ConfigurationError:
                raise ConfigurationError(CODEX_HOST_SINCE_MESSAGE.format(operation=operation.value), details={"field": "since"}) from None
        elif self.since is not None:
            raise ConfigurationError(CODEX_HOST_UNUSED_ARGUMENT_MESSAGE.format(operation=operation.value, field="since", owner=CodexHostOperation.LIST_CODEX_THREADS_SINCE.value), details={"field": "since"})
        if operation is CodexHostOperation.SEARCH_CODEX_THREADS:
            try:
                RecordFieldValidator.require_text(self.query, "query")
            except ConfigurationError:
                raise ConfigurationError(CODEX_HOST_QUERY_MESSAGE.format(operation=operation.value), details={"field": "query"}) from None
        elif self.query:
            raise ConfigurationError(CODEX_HOST_UNUSED_ARGUMENT_MESSAGE.format(operation=operation.value, field="query", owner=CodexHostOperation.SEARCH_CODEX_THREADS.value), details={"field": "query"})


@dataclass(frozen=True, slots=True)
class CodexTurnListRequest:
    """The input of list_codex_turns: the thread, the page cursor, and the page size; None keeps Codex's own."""

    thread_id: str
    cursor: str = ""
    limit: int | None = None

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.thread_id, "list_codex_turns thread_id", one_line=True)
        RecordFieldValidator.require_text(self.cursor, "list_codex_turns cursor", allow_blank=True, one_line=True)
        _reject_small_int("list_codex_turns", "limit", self.limit, CODEX_HOST_MIN_LIST_LIMIT)


@dataclass(frozen=True, slots=True)
class CodexGoalRunRequest:
    """The input of run_codex_goal: the goal, and the caller's request for the new thread."""

    goal: CodexGoal
    request: CodexSpawnRequest = field(default_factory=CodexSpawnRequest)

    def __post_init__(self) -> None:
        # The run sets the goal itself, so a request that carries its
        # own prompt or goal would be ambiguous (INV-6, EC-37). Codex
        # starts goal turns with the thread's settings, so the turn-only
        # fields a goal spawn refuses are refused here too (hardening
        # INV-34).
        RecordFieldConverter.require_instance(self.goal, "run_codex_goal goal", CodexGoal)
        RecordFieldConverter.require_instance(self.request, "run_codex_goal request", CodexSpawnRequest)
        if isinstance(self.request.prompt, CodexRunInput) or self.request.prompt or self.request.goal is not None:
            raise ConfigurationError(CODEX_HOST_OWN_INPUT_MESSAGE.format(operation=CodexHostOperation.RUN_CODEX_GOAL.value), details={"field": "request"})
        _reject_goal_fields("run_codex_goal request", self.request)


@dataclass(frozen=True, slots=True)
class CodexSkillListRequest:
    """The input of list_codex_skills: the folder whose skills are listed, empty for the app-server's own, and whether Codex rescans."""

    cwd: str = ""
    force_reload: bool = False

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.cwd, "list_codex_skills cwd", allow_blank=True)
        RecordFieldValidator.require_bool(self.force_reload, "list_codex_skills force_reload")


@dataclass(frozen=True, slots=True)
class CodexSkillRunRequest:
    """The input of run_codex_skill and run_codex_openai_docs: the skill, the caller's text, and the request for the new thread."""

    operation: CodexHostOperation
    skill: str
    prompt: str
    request: CodexSpawnRequest = field(default_factory=CodexSpawnRequest)

    def __post_init__(self) -> None:
        # The run sets the prompt itself, and an ephemeral thread keeps
        # no history, so its skill run could never be confirmed and
        # would only spend (INV-6, EC-37, EC-48).
        operation = RecordFieldValidator.require_enum(self.operation, CodexHostOperation, "CodexSkillRunRequest.operation")
        if operation not in (CodexHostOperation.RUN_CODEX_SKILL, CodexHostOperation.RUN_CODEX_OPENAI_DOCS):
            raise ConfigurationError(CODEX_HOST_SKILL_OPERATION_MESSAGE.format(operation=operation.value), details={"field": "operation"})
        RecordFieldConverter.require_instance(self.request, f"{operation.value} request", CodexSpawnRequest)
        if isinstance(self.request.prompt, CodexRunInput) or self.request.prompt or self.request.goal is not None:
            raise ConfigurationError(CODEX_HOST_OWN_INPUT_MESSAGE.format(operation=operation.value), details={"field": "request"})
        if self.request.thread.ephemeral:
            raise ConfigurationError(CODEX_HOST_EPHEMERAL_SKILL_MESSAGE.format(operation=operation.value), details={"field": "request"})
        if not isinstance(self.skill, str) or not self.skill.strip():
            raise ConfigurationError(CODEX_HOST_SKILL_NAME_MESSAGE.format(operation=operation.value), details={"field": "skill"})
        label = "question" if operation is CodexHostOperation.RUN_CODEX_OPENAI_DOCS else "prompt"
        RecordFieldValidator.require_text(self.prompt, f"{operation.value} {label}")


@dataclass(frozen=True, slots=True)
class CodexThreadSettingsRequest:
    """The input of update_codex_thread_settings: the thread, and the settings update to send."""

    thread_id: str
    settings: CodexThreadSettingsUpdate

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.thread_id, "update_codex_thread_settings thread_id", one_line=True)
        RecordFieldConverter.require_instance(self.settings, "update_codex_thread_settings settings", CodexThreadSettingsUpdate)


@dataclass(frozen=True, slots=True)
class CodexPlanRunRequest:
    """The input of run_codex_plan: the prompt, and the caller's request for the new thread."""

    prompt: str | CodexRunInput
    request: CodexSpawnRequest = field(default_factory=CodexSpawnRequest)

    def __post_init__(self) -> None:
        # The run takes its prompt as an argument and its mode from
        # Codex's plan preset, so the request may carry neither
        # (first-class INV-16).
        _reject_unused_fields(CodexHostOperation.RUN_CODEX_PLAN, self.request)
        object.__setattr__(self, "prompt", _run_input(self.prompt, "run_codex_plan prompt"))


@dataclass(frozen=True, slots=True)
class CodexTurnsWaitRequest:
    """The input of wait_codex_turns: the turns, when to return, and at most how long to wait; None waits."""

    handles: Sequence[CodexTurnHandle]
    return_when: CodexTurnWaitMode = CodexTurnWaitMode.FIRST_COMPLETED
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        # @intent a-wait-takes-distinct-handles-never-one-string
        # A str is a sequence of characters, not of handles, and a
        # repeated handle would be waited on twice, so both are refused
        # with the cap; the mode may be given as its value, which equals
        # asyncio's own constant (first-class D-13, AC-18).
        handles = self.handles
        valid = isinstance(handles, Sequence) and not isinstance(handles, str) and all(isinstance(handle, CodexTurnHandle) for handle in handles)
        if not valid or not 1 <= len(handles) <= CODEX_HOST_WAIT_MAX_HANDLES or len(set(handles)) != len(handles):
            raise ConfigurationError(CODEX_HOST_WAIT_HANDLES_MESSAGE.format(maximum=CODEX_HOST_WAIT_MAX_HANDLES), details={"field": "wait_codex_turns handles"})
        object.__setattr__(self, "handles", tuple(handles))
        object.__setattr__(self, "return_when", RecordFieldConverter.to_enum(self.return_when, CodexTurnWaitMode, "wait_codex_turns return_when"))
        _reject_bad_seconds("wait_codex_turns", "timeout_seconds", self.timeout_seconds)


@dataclass(frozen=True, slots=True)
class CodexMcpServerListRequest:
    """The input of list_codex_mcp_servers: the optional thread and server filters, the detail, and one page."""

    thread_id: str = ""
    server_name: str = ""
    detail: CodexMcpServerDetail = CodexMcpServerDetail.FULL
    cursor: str = ""
    limit: int | None = None

    def __post_init__(self) -> None:
        operation = CodexHostOperation.LIST_CODEX_MCP_SERVERS
        RecordFieldValidator.require_text(self.thread_id, f"{operation.value} thread_id", allow_blank=True, one_line=True)
        RecordFieldValidator.require_text(self.server_name, f"{operation.value} server_name", allow_blank=True, one_line=True)
        RecordFieldValidator.require_enum(self.detail, CodexMcpServerDetail, f"{operation.value} detail")
        RecordFieldValidator.require_text(self.cursor, f"{operation.value} cursor", allow_blank=True, one_line=True)
        if self.limit is not None:
            _reject_bad_list_limit(operation, self.limit)


@dataclass(frozen=True, slots=True)
class CodexTurnSettingsRequest:
    """The input of update_codex_turn_settings: the running turn, and the settings it should take from now on."""

    handle: CodexTurnHandle
    model: str = ""
    effort: CodexReasoningEffort = CodexReasoningEffort.PROVIDER_DEFAULT
    summary: CodexReasoningSummary = CodexReasoningSummary.PROVIDER_DEFAULT
    service_tier: str = ""
    clear_service_tier: bool = False
    approvals_reviewer: CodexApprovalsReviewer = CodexApprovalsReviewer.PROVIDER_DEFAULT

    def __post_init__(self) -> None:
        # Check each field's type first, then refuse an update that
        # changes nothing and a tier that is set and cleared at once.
        self._reject_bad_types()
        operation = CodexHostOperation.UPDATE_CODEX_TURN_SETTINGS.value
        settings = (self.model, self.effort, self.summary, self.service_tier, self.clear_service_tier, self.approvals_reviewer)
        defaults = ("", CodexReasoningEffort.PROVIDER_DEFAULT, CodexReasoningSummary.PROVIDER_DEFAULT, "", False, CodexApprovalsReviewer.PROVIDER_DEFAULT)
        if settings == defaults:
            raise ConfigurationError(CODEX_HOST_SETTINGS_EMPTY_MESSAGE.format(operation=operation), details={"field": "settings"})
        if self.service_tier and self.clear_service_tier:
            raise ConfigurationError(CODEX_HOST_TIER_CLEAR_CONFLICT_MESSAGE.format(operation=operation), details={"field": "clear_service_tier"})

    def _reject_bad_types(self) -> None:
        operation = CodexHostOperation.UPDATE_CODEX_TURN_SETTINGS.value
        RecordFieldConverter.require_instance(self.handle, f"{operation} handle", CodexTurnHandle)
        RecordFieldValidator.require_text(self.model, f"{operation} model", allow_blank=True, one_line=True)
        RecordFieldValidator.require_enum(self.effort, CodexReasoningEffort, f"{operation} effort")
        RecordFieldValidator.require_enum(self.summary, CodexReasoningSummary, f"{operation} summary")
        RecordFieldValidator.require_text(self.service_tier, f"{operation} service_tier", allow_blank=True, one_line=True)
        RecordFieldValidator.require_bool(self.clear_service_tier, f"{operation} clear_service_tier")
        RecordFieldValidator.require_enum(self.approvals_reviewer, CodexApprovalsReviewer, f"{operation} approvals_reviewer")


@dataclass(frozen=True, slots=True)
class CodexMemoryModeRequest:
    """The input of set_codex_thread_memory_mode: the thread, and whether Codex may use memories on it."""

    thread_id: str
    mode: CodexMemoryMode

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.thread_id, "set_codex_thread_memory_mode thread_id", one_line=True)
        RecordFieldValidator.require_enum(self.mode, CodexMemoryMode, "set_codex_thread_memory_mode mode")


@dataclass(frozen=True, slots=True)
class CodexMemoryStatusRequest:
    """The input of get_codex_memory_status: the optional consolidated-thread count Codex reports readiness against."""

    min_consolidated_threads: int | None = None

    def __post_init__(self) -> None:
        if self.min_consolidated_threads is not None:
            name = "get_codex_memory_status min_consolidated_threads"
            RecordFieldValidator.require_int(self.min_consolidated_threads, name, minimum=CODEX_HOST_MEMORY_MIN_CONSOLIDATED_THREADS, maximum=CODEX_HOST_MEMORY_MAX_CONSOLIDATED_THREADS)


@dataclass(frozen=True, slots=True)
class CodexSideChatRequest:
    """The input of start_codex_side_chat: the parent thread, the side question, and the request for the side turn."""

    thread_id: str
    prompt: str | CodexRunInput
    request: CodexSpawnRequest = field(default_factory=CodexSpawnRequest)

    def __post_init__(self) -> None:
        # A side chat is always an ephemeral fork that shares the
        # parent's tools, so the fields it could not apply are refused
        # (first-class INV-27).
        RecordFieldValidator.require_text(self.thread_id, "start_codex_side_chat thread_id", one_line=True)
        _reject_unused_fields(CodexHostOperation.START_CODEX_SIDE_CHAT, self.request)
        object.__setattr__(self, "prompt", _run_input(self.prompt, "start_codex_side_chat prompt"))


@dataclass(frozen=True, slots=True)
class CodexWorktreeRequest:
    """The input of create_codex_worktree: the repository folder, the new branch, and the ref it starts from."""

    repository: str | Path
    branch: str
    base_ref: str = ""

    def __post_init__(self) -> None:
        # @intent worktree-refs-can-never-be-git-options
        # The folder must already exist, and the branch and base ref
        # follow git's ref shape, which never starts with a dash, so
        # neither can reach git as an option (first-class T-5).
        try:
            repository = RecordFieldValidator.require_directory(RecordFieldConverter.to_path(self.repository, "repository"), "repository")
        except (ConfigurationError, OSError):
            # A folder the system will not let this process inspect is
            # refused the same way, without the error's text, which
            # holds the absolute path (first-class INV-2).
            raise ConfigurationError(CODEX_HOST_WORKTREE_REPOSITORY_MESSAGE, details={"field": "repository"}) from None
        object.__setattr__(self, "repository", repository)
        refs = (("branch", self.branch), ("base_ref", self.base_ref)) if self.base_ref != "" else (("branch", self.branch),)
        for name, value in refs:
            try:
                RecordFieldValidator.require_text(value, name, max_chars=GIT_REF_MAX_CHARS, pattern=GIT_REF_PATTERN)
            except ConfigurationError:
                raise ConfigurationError(CODEX_HOST_WORKTREE_REF_MESSAGE.format(field=name, maximum=GIT_REF_MAX_CHARS), details={"field": name}) from None


@dataclass(frozen=True, slots=True)
class CodexGoalResumeRequest:
    """The input of resume_codex_goal: the thread, and the caller's request for the resumed goal run."""

    thread_id: str
    request: CodexSpawnRequest = field(default_factory=CodexSpawnRequest)

    def __post_init__(self) -> None:
        # A resume continues the stored thread, so it refuses what
        # continue refuses, and Codex starts the goal's turns itself,
        # so the goal rule applies too (first-class INV-31).
        RecordFieldValidator.require_text(self.thread_id, "resume_codex_goal thread_id", one_line=True)
        _reject_unused_fields(CodexHostOperation.RESUME_CODEX_GOAL, self.request)
        _reject_goal_fields("resume_codex_goal request", self.request)


@dataclass(frozen=True, slots=True)
class CodexGoalEditRequest:
    """The input of edit_codex_goal: the thread, and a new objective, a new token budget, or the budget removed."""

    thread_id: str
    objective: str = ""
    token_budget: int | None = None
    clear_token_budget: bool = False

    def __post_init__(self) -> None:
        # The objective and budget follow CodexGoal's own rules when
        # set; an edit must change something, and a budget cannot be
        # set and removed at once (first-class EC-41).
        RecordFieldValidator.require_text(self.thread_id, "edit_codex_goal thread_id", one_line=True)
        if self.objective != "":
            RecordFieldValidator.require_text(self.objective, "edit_codex_goal objective")
        _reject_small_int("edit_codex_goal", "token_budget", self.token_budget, CODEX_HOST_MIN_TOKEN_LIMIT)
        RecordFieldValidator.require_bool(self.clear_token_budget, "edit_codex_goal clear_token_budget")
        if not self.objective and self.token_budget is None and not self.clear_token_budget:
            raise ConfigurationError(CODEX_HOST_GOAL_EDIT_EMPTY_MESSAGE, details={"field": "objective"})
        if self.token_budget is not None and self.clear_token_budget:
            raise ConfigurationError(CODEX_HOST_BUDGET_CLEAR_CONFLICT_MESSAGE, details={"field": "clear_token_budget"})


@dataclass(frozen=True, slots=True)
class CodexThreadRevertRequest:
    """The input of revert_codex_thread: the thread, and the turn whose start the history goes back to."""

    thread_id: str
    before_turn_id: str

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.thread_id, "revert_codex_thread thread_id", one_line=True)
        RecordFieldValidator.require_text(self.before_turn_id, "revert_codex_thread before_turn_id", one_line=True)


@dataclass(frozen=True, slots=True)
class CodexThreadRenameRequest:
    """The input of rename_codex_thread: the thread, and its new one-line name."""

    thread_id: str
    name: str

    def __post_init__(self) -> None:
        RecordFieldValidator.require_text(self.thread_id, "rename_codex_thread thread_id", one_line=True)
        RecordFieldValidator.require_text(self.name, "rename_codex_thread name", one_line=True)


@dataclass(frozen=True, slots=True)
class CodexItemsInjectRequest:
    """The input of inject_codex_items: the thread, and the raw history items Codex adds to it."""

    thread_id: str
    items: Sequence[Mapping[str, Any]]

    def __post_init__(self) -> None:
        # @intent injected-items-are-json-copies-taken-now
        # Each item is a JSON object with a non-empty string type, kept
        # as a JSON round-trip copy, so a later change by the caller
        # changes nothing sent; NaN and infinity are not JSON, and a str
        # or one mapping is not a sequence of items (first-class
        # INV-37).
        RecordFieldValidator.require_text(self.thread_id, "inject_codex_items thread_id", one_line=True)
        items = self.items
        sized = isinstance(items, Sequence) and not isinstance(items, str) and 1 <= len(items) <= CODEX_HOST_INJECT_MAX_ITEMS
        typed = sized and all(isinstance(item, Mapping) and isinstance(item.get("type"), str) and item.get("type") for item in items)
        try:
            copies = tuple(json.loads(json.dumps(dict(item), allow_nan=False)) for item in items) if typed else None
        except (TypeError, ValueError):
            copies = None
        if copies is None:
            raise ConfigurationError(CODEX_HOST_INJECT_ITEMS_MESSAGE.format(maximum=CODEX_HOST_INJECT_MAX_ITEMS), details={"field": "inject_codex_items items"})
        object.__setattr__(self, "items", copies)


@dataclass(frozen=True, slots=True)
class CodexTerminalListRequest:
    """The input of list_codex_background_terminals: the thread, and one page."""

    thread_id: str
    cursor: str = ""
    limit: int | None = None

    def __post_init__(self) -> None:
        operation = CodexHostOperation.LIST_CODEX_BACKGROUND_TERMINALS
        RecordFieldValidator.require_text(self.thread_id, f"{operation.value} thread_id", one_line=True)
        RecordFieldValidator.require_text(self.cursor, f"{operation.value} cursor", allow_blank=True, one_line=True)
        if self.limit is not None:
            _reject_bad_list_limit(operation, self.limit)


@dataclass(frozen=True, slots=True)
class CodexThreadSearchRequest:
    """The input of search_codex_thread_content: the text to find, whether archived threads are searched, and one page."""

    query: str
    archived: bool = False
    cursor: str = ""
    limit: int | None = None

    def __post_init__(self) -> None:
        operation = CodexHostOperation.SEARCH_CODEX_THREAD_CONTENT
        RecordFieldValidator.require_text(self.query, f"{operation.value} query")
        RecordFieldValidator.require_bool(self.archived, f"{operation.value} archived")
        RecordFieldValidator.require_text(self.cursor, f"{operation.value} cursor", allow_blank=True, one_line=True)
        if self.limit is not None:
            _reject_bad_list_limit(operation, self.limit)


@dataclass(frozen=True, slots=True)
class CodexChildThreadsRequest:
    """The input of list_codex_child_threads: the parent thread, whether every depth below it is listed, and one page."""

    thread_id: str
    descendants: bool = False
    cursor: str = ""
    limit: int | None = None

    def __post_init__(self) -> None:
        operation = CodexHostOperation.LIST_CODEX_CHILD_THREADS
        RecordFieldValidator.require_text(self.thread_id, f"{operation.value} thread_id", one_line=True)
        RecordFieldValidator.require_bool(self.descendants, f"{operation.value} descendants")
        RecordFieldValidator.require_text(self.cursor, f"{operation.value} cursor", allow_blank=True, one_line=True)
        if self.limit is not None:
            _reject_bad_list_limit(operation, self.limit)


__all__ = [
    "CodexChildThreadsRequest",
    "CodexContinueRequest",
    "CodexForkRequest",
    "CodexGoalEditRequest",
    "CodexGoalResumeRequest",
    "CodexGoalRunRequest",
    "CodexHostSetup",
    "CodexItemsInjectRequest",
    "CodexMcpServerListRequest",
    "CodexMemoryModeRequest",
    "CodexMemoryStatusRequest",
    "CodexModelListRequest",
    "CodexPlanRunRequest",
    "CodexReviewRequest",
    "CodexSideChatRequest",
    "CodexSkillListRequest",
    "CodexSkillRunRequest",
    "CodexSubagentLaunchRequest",
    "CodexTerminalListRequest",
    "CodexThreadListRequest",
    "CodexThreadListing",
    "CodexThreadReadRequest",
    "CodexThreadRef",
    "CodexThreadRenameRequest",
    "CodexThreadRevertRequest",
    "CodexThreadSearchRequest",
    "CodexThreadSettingsRequest",
    "CodexTurnListRequest",
    "CodexTurnRef",
    "CodexTurnSettingsRequest",
    "CodexTurnSteerRequest",
    "CodexTurnWaitRequest",
    "CodexTurnsWaitRequest",
    "CodexWorktreeRequest",
]
