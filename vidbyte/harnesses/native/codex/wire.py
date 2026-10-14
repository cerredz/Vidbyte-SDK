"""FILE: vidbyte/harnesses/native/codex/wire.py

PURPOSE: Translates between CodexHost and the openai-codex wire: the JSON params of every app-server call the host sends, and the records, snapshots and results it builds from what Codex answers.
ROLE IN CODEBASE: The wire layer of vidbyte/harnesses/native/codex/; CodexHost and CodexPreflight build every params object with CodexParamsTranslator and read every answer through CodexResponseTranslator.
ARCHITECTURE NOTE: openai-codex's generated models are imported at module level, so only CodexHost.__aenter__ imports this module (D-21). Thread and turn params reuse CodexContentTranslator's settings translation, are validated with the generated params model and dumped by alias, so their wire shape comes from openai-codex itself.
COMMON MODIFICATION PATTERNS: A new params field goes through its settings record and CodexContentTranslator first; a new record gets one CodexResponseTranslator method that reads the generated model's typed fields, never the account email.
KNOWN EDGE CASES: CodexContentTranslator always writes config["agents"], so unless subagents are set the caller's own agents entry is put back or the key dropped (INV-30); a granular approval policy has no plain value, so it never counts as never (D-32); a goal run's result spans every physical turn it ran.
RELATED DOCS: docs/spec/codex-host/spec.md (sections 8.1 D-17, D-20, D-29, D-32 and D-34, and 9.2 wire translation and goal table)
TESTS: tests/features/codex_host/test_codex_host_turns.py, tests/features/codex_host/test_codex_host_threads.py, tests/features/codex_host/test_codex_host_review_goals.py
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from typing import Any

from openai_codex import (
    ApprovalMode,
    AsyncCodex,
    CodexConfig,
    ImageInput,
    LocalImageInput,
    MentionInput,
    Sandbox,
    SkillInput,
    TextInput,
    TurnResult,
)
from openai_codex.generated.v2_all import (
    AgentMessageThreadItem,
    ChatgptAccount,
    GetAccountRateLimitsResponse,
    GetAccountResponse,
    MessagePhase,
    Model,
    Personality,
    RateLimitWindow,
    ReasoningEffort,
    ReasoningSummary,
    Thread,
    ThreadForkParams,
    ThreadItem,
    ThreadListResponse,
    ThreadResumeParams,
    ThreadResumeResponse,
    ThreadSource,
    ThreadStartParams,
    ThreadStartResponse,
    ThreadStartSource,
    Turn,
    TurnStartParams,
    TurnStatus,
)
from openai_codex.models import InitializeResponse

from vidbyte.agents.codex.config import CodexContentTranslator, CodexVidbyteTranslator
from vidbyte.agents.codex.result import CodexResultSerializer
from vidbyte.harnesses.native.codex.errors import CodexErrorMapper
from vidbyte.harnesses.native.codex.turns import CodexGoalTurn, CodexLiveTurn
from vidbyte.lib.constants.codex import (
    CODEX_APPROVAL_MODE_WIRE,
    CODEX_DYNAMIC_TOOLS_PARAM,
    CODEX_HOST_DEFAULT_APPROVAL_MODE,
    CODEX_HOST_MINIMUM_VERSION,
    CODEX_SANDBOX_THREAD_MODE,
    CODEX_SANDBOX_TURN_POLICY,
    CODEX_USAGE_PROVIDER,
)
from vidbyte.lib.dataclasses.codex import (
    CodexAgentSettings,
    CodexClientSettings,
    CodexRunInput,
    CodexSdkTypes,
    CodexSubagentSettings,
    CodexThreadSettings,
    CodexTurnSettings,
)
from vidbyte.lib.dataclasses.codex_host import (
    CodexModelInfo,
    CodexProblem,
    CodexRateLimits,
    CodexRateLimitWindow,
    CodexReadiness,
    CodexReviewTarget,
    CodexSpawnRequest,
    CodexThreadInfo,
    CodexThreadPage,
    CodexTurnHandle,
    CodexTurnSnapshot,
    CodexTurnSummary,
)
from vidbyte.lib.enums.codex import (
    CodexAccountKind,
    CodexApprovalPolicy,
    CodexApprovalsReviewer,
    CodexGoalStatus,
    CodexReviewDelivery,
    CodexSandboxReadiness,
    CodexSortDirection,
    CodexThreadSortKey,
    CodexThreadSourceKind,
    CodexThreadStatus,
    CodexTurnStatus,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError, ConfigurationError
from vidbyte.providers.output_schema import OutputSchemaFormatter

# A runtime version is three dot-separated numbers; anything else is
# unreadable and refused (INV-4, D-5).
VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)")
MINIMUM_VERSION = tuple(int(part) for part in CODEX_HOST_MINIMUM_VERSION.split("."))
# The two wire approval fields, in the order CODEX_APPROVAL_MODE_WIRE
# lists their values.
APPROVAL_FIELDS = ("approval_policy", "approvals_reviewer")
# The Windows sandbox states that keep turns from running (D-28).
SANDBOX_NOT_READY = frozenset({CodexSandboxReadiness.NOT_CONFIGURED, CodexSandboxReadiness.UPDATE_REQUIRED})
# The fixed messages of problems the translator finds in Codex's answers.
SIGNED_OUT_MESSAGE = "Codex has no signed-in account, and this runtime requires one."
NO_FINAL_ANSWER_MESSAGE = "Codex completed the turn without a final answer."
SCHEMA_MESSAGE = "Codex's final answer is not JSON that matches output_schema."
NO_GOAL_MODE_MESSAGE = "The Codex runtime completed a goal turn without activating goal mode."
NO_COMPLETION_MESSAGE = "Codex ended the turn without reporting its completion."
EXITED_MESSAGE = "CodexHost closed, or its Codex app-server exited, while the turn was running."


def final_answer(items: Sequence[ThreadItem]) -> str | None:
    # openai-codex's own rule: the last final-answer message wins, else
    # the last message without a phase, else there is no answer.
    unphased: str | None = None
    for item in reversed(items):
        message = item.root
        if not isinstance(message, AgentMessageThreadItem):
            continue
        if message.phase == MessagePhase.final_answer:
            return message.text
        if message.phase is None and unphased is None:
            unphased = message.text
    return unphased


class CodexParamsTranslator:
    """Builds the JSON params of every app-server call CodexHost sends."""

    def __init__(self, settings: CodexClientSettings) -> None:
        # The client settings apply to every thread; the SDK types let
        # CodexContentTranslator build its enum and summary values.
        self._settings = settings
        self._sdk = CodexSdkTypes(
            async_codex=AsyncCodex,
            codex_config=CodexConfig,
            approval_mode=ApprovalMode,
            sandbox=Sandbox,
            personality=Personality,
            reasoning_effort=ReasoningEffort,
            reasoning_summary=ReasoningSummary,
            thread_source=ThreadSource,
            thread_start_source=ThreadStartSource,
            text_input=TextInput,
            image_input=ImageInput,
            local_image_input=LocalImageInput,
            skill_input=SkillInput,
            mention_input=MentionInput,
        )
        self._schemas = CodexVidbyteTranslator()

    def client_config(self, codex_bin: str) -> CodexConfig:
        # The process settings, launching the binary found on PATH when
        # the host resolved one (D-4).
        values = CodexContentTranslator.client_kwargs(CodexAgentSettings(client=self._settings))
        if codex_bin:
            values["codex_bin"] = codex_bin
        return CodexConfig(**values)

    def thread_start(self, request: CodexSpawnRequest, dynamic_tools: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        # @intent new-threads-always-carry-an-approval-posture
        # A new thread gets the explicit approval fields as given, else
        # its approval_mode, else on-request with the auto reviewer, so no
        # approval request ever waits on a person (INV-28). Dynamic tools
        # are added after validation, because the params model lacks them.
        values = CodexContentTranslator.thread_start_kwargs(request.developer_instructions, self._agent(request), self._sdk)
        self._approvals(values, self._explicit(request), CODEX_HOST_DEFAULT_APPROVAL_MODE)
        self._thread_sandbox(values)
        self._agents_config(values, request)
        params = ThreadStartParams.model_validate(values).model_dump(by_alias=True, exclude_none=True, mode="json")
        if dynamic_tools:
            params[CODEX_DYNAMIC_TOOLS_PARAM] = [dict(tool) for tool in dynamic_tools]
        return params

    def thread_resume(self, thread_id: str, request: CodexSpawnRequest) -> dict[str, Any]:
        # @intent resume-keeps-the-threads-own-approvals
        # Resume sends approval fields only when the caller set them, so a
        # thread keeps its own posture, and never asks for earlier turns.
        values = CodexContentTranslator.thread_resume_kwargs(request.developer_instructions, self._agent(request), self._sdk)
        self._approvals(values, self._explicit(request), "")
        self._thread_sandbox(values)
        self._agents_config(values, request)
        values.update(thread_id=thread_id, exclude_turns=True)
        return ThreadResumeParams.model_validate(values).model_dump(by_alias=True, exclude_none=True, mode="json")

    def thread_fork(self, thread_id: str, last_turn_id: str, exclude_turns: bool, request: CodexSpawnRequest) -> dict[str, Any]:
        # @intent fork-through-one-completed-turn
        # A fork copies the thread through last_turn_id; excludeTurns is
        # sent only when asked for, and only shapes Codex's answer (D-29).
        values = CodexContentTranslator.thread_fork_kwargs(request.developer_instructions, self._agent(request), self._sdk)
        self._approvals(values, self._explicit(request), "")
        self._thread_sandbox(values)
        self._agents_config(values, request)
        values.update(thread_id=thread_id, last_turn_id=last_turn_id)
        if exclude_turns:
            values["exclude_turns"] = True
        return ThreadForkParams.model_validate(values).model_dump(by_alias=True, exclude_none=True, mode="json")

    def turn_start(self, thread_id: str, request: CodexSpawnRequest) -> dict[str, Any]:
        # @intent a-turn-sends-only-its-own-posture
        # The turn's approval_mode, sandbox, plugins and output schema go
        # on the turn. The explicit approval fields belong to the thread,
        # so a turn never repeats them (INV-28). The input items are set
        # by openai-codex's turn_start, so an empty list stands in here.
        output_schema = self._schemas.output_schema(request.output_schema)
        values = CodexContentTranslator.turn_kwargs(self._agent(request), output_schema, self._sdk)
        self._approvals(values, {}, "")
        sandbox = values.pop("sandbox", None)
        if sandbox is not None:
            values["sandbox_policy"] = {"type": CODEX_SANDBOX_TURN_POLICY[sandbox.value]}
        if request.disabled_plugin_ids is not None:
            values["disabled_plugin_ids"] = list(request.disabled_plugin_ids)
        values.update(thread_id=thread_id, input=[])
        return TurnStartParams.model_validate(values).model_dump(by_alias=True, exclude_none=True, mode="json")

    @staticmethod
    def input_items(prompt: str | CodexRunInput) -> list[dict[str, Any]]:
        # Only the input items are sent, as the wire's typed inputs: text
        # becomes one text item, and context that would be dropped is
        # refused (section 9.1).
        run_input = CodexRunInput.text(prompt) if isinstance(prompt, str) else prompt
        if not isinstance(run_input, CodexRunInput) or run_input.context_items or run_input.context_manager is not None or run_input.context_placements:
            raise ConfigurationError("A Codex prompt must be a str or a CodexRunInput without context_items, a context_manager or context_placements.")
        return [{**asdict(item), "type": item.type.value} for item in run_input.items]

    @staticmethod
    def thread_list(
        cwd: str,
        search: str,
        archived: bool,
        source_kinds: tuple[CodexThreadSourceKind, ...],
        sort: CodexThreadSortKey,
        sort_direction: CodexSortDirection,
        cursor: str,
    ) -> dict[str, Any]:
        # Every set argument goes under its wire name; empty ones, and
        # archived when False, are left out (section 9.2).
        values = {
            "cwd": cwd,
            "searchTerm": search,
            "archived": archived,
            "sourceKinds": [kind.value for kind in source_kinds],
            "sortKey": sort.value,
            "sortDirection": sort_direction.value,
            "cursor": cursor,
        }
        return {key: value for key, value in values.items() if value}

    @staticmethod
    def review(thread_id: str, target: CodexReviewTarget, delivery: CodexReviewDelivery) -> dict[str, Any]:
        # The review target carries its kind and only the fields it set.
        fields = {"branch": target.branch, "sha": target.sha, "title": target.title, "instructions": target.instructions}
        wire_target = {"type": target.kind.value, **{key: value for key, value in fields.items() if value}}
        return {"threadId": thread_id, "target": wire_target, "delivery": delivery.value}

    @staticmethod
    def goal_budget(thread_id: str, budget: int) -> dict[str, Any]:
        # The goal's token budget is set on its own, after the goal starts (INV-25).
        return {"threadId": thread_id, "tokenBudget": budget}

    @staticmethod
    def model_page(include_hidden: bool, cursor: str) -> dict[str, Any]:
        # One page of the model list; the first page has no cursor (D-20).
        return {"includeHidden": include_hidden, **({"cursor": cursor} if cursor else {})}

    def _agent(self, request: CodexSpawnRequest) -> CodexAgentSettings:
        # @intent one-settings-record-per-request
        # CodexContentTranslator reads one agent settings record; unset
        # subagents mean its defaults, which _agents_config then removes.
        return CodexAgentSettings(
            client=self._settings,
            thread=request.thread,
            turn=request.turn,
            subagents=request.subagents or CodexSubagentSettings(),
        )

    @staticmethod
    def _explicit(request: CodexSpawnRequest) -> dict[str, str]:
        # @intent explicit-approvals-are-sent-as-given
        # The caller's explicit approval fields, by wire field name.
        return {"approval_policy": request.approval_policy.value, "approvals_reviewer": request.approvals_reviewer.value}

    @staticmethod
    def _approvals(values: dict[str, Any], explicit: Mapping[str, str], default_mode: str) -> None:
        # Explicit fields replace approval_mode; otherwise the mode, or the
        # default mode of a new thread, maps to the wire pair, and an empty
        # reviewer stays unsent (INV-28).
        mode = values.pop("approval_mode", None)
        chosen = {key: value for key, value in explicit.items() if value}
        if not chosen:
            pair = CODEX_APPROVAL_MODE_WIRE.get(mode.value if mode is not None else default_mode, ("", ""))
            chosen = {key: value for key, value in zip(APPROVAL_FIELDS, pair, strict=True) if value}
        values.update(chosen)

    @staticmethod
    def _thread_sandbox(values: dict[str, Any]) -> None:
        # The SDK's sandbox preset becomes the thread's wire sandbox mode.
        sandbox = values.pop("sandbox", None)
        if sandbox is not None:
            values["sandbox"] = CODEX_SANDBOX_THREAD_MODE[sandbox.value]

    @staticmethod
    def _agents_config(values: dict[str, Any], request: CodexSpawnRequest) -> None:
        # @intent agents-config-only-for-subagents
        # CodexContentTranslator always writes config["agents"]. Without
        # subagents, the caller's own agents entry is put back or the key
        # is dropped, and a config left empty is not sent (INV-30, D-17).
        if request.subagents is not None:
            return
        config = dict(values.pop("config", {}))
        config.pop("agents", None)
        if "agents" in request.thread.config:
            config["agents"] = request.thread.config["agents"]
        if config:
            values["config"] = config


class CodexResponseTranslator:
    """Turns openai-codex answers into CodexHost records, snapshots and results."""

    def __init__(self) -> None:
        # Structured output is checked with the repo's own schema formatter.
        self._schemas = OutputSchemaFormatter()

    @staticmethod
    def version(response: InitializeResponse) -> tuple[str, bool]:
        # The server's version, or the one in its user agent, and whether
        # it reaches the SDK's floor; an unreadable version is refused
        # (INV-4, D-5).
        info = response.serverInfo
        raw = (info.version if info is not None else None) or response.userAgent or ""
        match = VERSION_PATTERN.search(raw)
        if match is None:
            return raw, False
        return match.group(), tuple(int(part) for part in match.groups()) >= MINIMUM_VERSION

    @staticmethod
    def routes_to_user(response: ThreadStartResponse | ThreadResumeResponse) -> bool:
        # D-32: a user reviewer with any policy but never would send
        # approval requests to a person nothing on the host answers; a
        # granular policy has no plain value, so it is not never.
        policy = getattr(response.approval_policy.root, "value", None)
        return response.approvals_reviewer.value == CodexApprovalsReviewer.USER.value and policy != CodexApprovalPolicy.NEVER.value

    @staticmethod
    def sign_in_problem(response: GetAccountResponse) -> CodexProblem | None:
        # No account while the runtime requires one means not signed in.
        if response.account is None and response.requires_openai_auth:
            return CodexErrorMapper.problem(FailureCode.CODEX_NOT_SIGNED_IN, SIGNED_OUT_MESSAGE)
        return None

    @staticmethod
    def sandbox_problem(status: str) -> CodexProblem | None:
        # A Windows sandbox that is not configured or needs an update
        # keeps turns from running (D-28).
        readiness = CodexSandboxReadiness(status)
        if readiness in SANDBOX_NOT_READY:
            return CodexErrorMapper.problem(FailureCode.CODEX_SANDBOX_NOT_READY, f"The Codex Windows sandbox reports {readiness.value}.")
        return None

    def readiness(self, version: str, response: GetAccountResponse, sandbox_status: str) -> CodexReadiness:
        # The account maps to its kind and ChatGPT plan only; the email is
        # never read (INV-9). Each problem found is reported, not raised.
        account = response.account.root if response.account is not None else None
        problems = tuple(problem for problem in (self.sign_in_problem(response), self.sandbox_problem(sandbox_status)) if problem is not None)
        return CodexReadiness(
            ready=not problems,
            version=version,
            minimum_version=CODEX_HOST_MINIMUM_VERSION,
            signed_in=account is not None,
            account=CodexAccountKind(account.type) if account is not None else CodexAccountKind.NONE,
            plan_type=account.plan_type.value if isinstance(account, ChatgptAccount) else "",
            sandbox=CodexSandboxReadiness(sandbox_status),
            problems=problems,
        )

    def rate_limits(self, response: GetAccountRateLimitsResponse) -> CodexRateLimits:
        # The single-bucket view; a missing allowance stays None and a
        # missing limit type is "" (D-34).
        snapshot = response.rate_limits
        return CodexRateLimits(
            ordinary_usage_allowed=response.ordinary_usage_allowed,
            plan_type=snapshot.plan_type.value if snapshot.plan_type is not None else "",
            limit_reached=snapshot.rate_limit_reached_type.value if snapshot.rate_limit_reached_type is not None else "",
            primary=self._window(snapshot.primary),
            secondary=self._window(snapshot.secondary),
        )

    @staticmethod
    def _window(window: RateLimitWindow | None) -> CodexRateLimitWindow | None:
        # One usage window, or None when Codex reported none.
        if window is None:
            return None
        return CodexRateLimitWindow(used_percent=window.used_percent, resets_at=window.resets_at, window_minutes=window.window_duration_mins)

    @staticmethod
    def model_info(model: Model) -> CodexModelInfo:
        # One listed model with its reasoning efforts by wire value.
        return CodexModelInfo(
            model_id=model.id,
            model=model.model,
            display_name=model.display_name,
            description=model.description,
            hidden=model.hidden,
            is_default=model.is_default,
            default_effort=model.default_reasoning_effort.value,
            efforts=tuple(option.reasoning_effort.value for option in model.supported_reasoning_efforts),
        )

    @staticmethod
    def thread_info(thread: Thread) -> CodexThreadInfo:
        # @intent thread-records-name-the-codex-provider
        # A thread and the turns Codex included, each summarized by its
        # status, final answer and error message.
        turns = tuple(
            CodexTurnSummary(
                turn_id=turn.id,
                status=CodexTurnStatus(turn.status.value),
                final_response=final_answer(turn.items) or "",
                error_message=turn.error.message if turn.error is not None else "",
                started_at=turn.started_at,
                completed_at=turn.completed_at,
            )
            for turn in thread.turns
        )
        return CodexThreadInfo(
            thread_id=thread.id,
            name=thread.name or "",
            preview=thread.preview,
            cwd=thread.cwd.root,
            status=CodexThreadStatus(thread.status.root.type),
            model=thread.model or "",
            model_provider=thread.model_provider,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
            forked_from_id=thread.forked_from_id or "",
            ephemeral=thread.ephemeral,
            turns=turns,
        )

    def page(self, response: ThreadListResponse) -> CodexThreadPage:
        # One page of threads and the cursor of the next one ("" at the end).
        return CodexThreadPage(threads=tuple(self.thread_info(thread) for thread in response.data), next_cursor=response.next_cursor or "")

    @staticmethod
    def fork_point(thread: Thread, from_turn_id: str) -> str:
        # D-29: a fork goes through a completed turn; an empty from_turn_id
        # means the last completed one, and "" means there is none.
        completed = [turn.id for turn in thread.turns if turn.status.value == CodexTurnStatus.COMPLETED.value]
        if from_turn_id:
            return from_turn_id if from_turn_id in completed else ""
        return next(reversed(completed), "")

    @staticmethod
    def stored_turn(thread: Thread, turn_id: str) -> Turn | None:
        # The turn a read-back found, if Codex stored it already (D-23).
        return next((turn for turn in thread.turns if turn.id == turn_id), None)

    @staticmethod
    def pricing(model: str, provider: str, turn_model: str) -> CodexAgentSettings:
        # @intent price-as-the-model-codex-resolved
        # Usage is priced as the model Codex reported for the thread, or
        # the turn's own model; a provider other than OpenAI leaves the
        # thread unpriced, so its cost is never guessed (D-19).
        own_provider = "" if provider in ("", CODEX_USAGE_PROVIDER) else provider
        return CodexAgentSettings(
            thread=CodexThreadSettings(model=model, model_provider=own_provider),
            turn=CodexTurnSettings(model=turn_model),
        )

    @staticmethod
    def running(handle: CodexTurnHandle) -> CodexTurnSnapshot:
        # A turn that has not ended yet.
        return CodexTurnSnapshot(handle=handle, status=CodexTurnStatus.RUNNING)

    @staticmethod
    def exited(handle: CodexTurnHandle) -> CodexTurnSnapshot:
        # A turn still running when the host closed or its process died.
        return CodexTurnSnapshot(handle=handle, status=CodexTurnStatus.FAILED, problem=CodexErrorMapper.problem(FailureCode.CODEX_PROCESS_EXITED, EXITED_MESSAGE))

    def turn_snapshot(self, turn: CodexLiveTurn, items: Sequence[ThreadItem], reported: Turn | None) -> CodexTurnSnapshot:
        # A plain or review turn ends with Codex's own status; Vidbyte's
        # stop reason labels it only when Codex reports it interrupted
        # (INV-18, INV-19).
        if reported is None:
            return CodexTurnSnapshot(handle=turn.handle, status=CodexTurnStatus.FAILED, problem=CodexErrorMapper.problem(FailureCode.CODEX_PROTOCOL_MISMATCH, NO_COMPLETION_MESSAGE))
        status = CodexTurnStatus(reported.status.value)
        reason = turn.stop_reason if status is CodexTurnStatus.INTERRUPTED else None
        problem = CodexErrorMapper.stop_problem(reason) if reason is not None else None
        return self._snapshot(turn, reported, status, problem, items)

    def goal_snapshot(self, turn: CodexGoalTurn) -> CodexTurnSnapshot:
        # Section 9.2 goal table: how the goal ended decides the run's
        # status, goal status and problem; the result covers every item
        # and token of every physical turn the run had.
        rule = turn.rule
        reported = rule.failed or rule.last_completed
        if rule.mismatch or reported is None:
            return CodexTurnSnapshot(handle=turn.handle, status=CodexTurnStatus.FAILED, problem=CodexErrorMapper.problem(FailureCode.CODEX_PROTOCOL_MISMATCH, NO_GOAL_MODE_MESSAGE))
        status, problem = self._goal_outcome(turn, reported)
        snapshot = self._snapshot(turn, reported, status, problem, turn.items)
        return replace(snapshot, goal_status=CodexGoalStatus.NONE if rule.cleared else CodexGoalStatus(rule.status))

    @staticmethod
    def _goal_outcome(turn: CodexGoalTurn, reported: Turn) -> tuple[CodexTurnStatus, CodexProblem | None]:
        # The goal table's rows in order: a cleared goal ends as its last
        # turn, a remembered failure fails the run, an interrupted turn
        # or a paused goal carries Vidbyte's stop reason if it sent one,
        # and the two limit statuses are failures of their own.
        rule = turn.rule
        last = CodexTurnStatus(reported.status.value)
        stop = CodexErrorMapper.stop_problem(turn.stop_reason) if turn.stop_reason is not None else None
        if rule.cleared:
            return last, stop if last is CodexTurnStatus.INTERRUPTED else None
        if rule.failed is not None:
            return CodexTurnStatus.FAILED, None
        if last is CodexTurnStatus.INTERRUPTED:
            return last, stop
        if rule.status == CodexGoalStatus.COMPLETE.value:
            return CodexTurnStatus.COMPLETED, None
        limit = CodexErrorMapper.goal_problem(rule.status)
        if limit is not None or rule.status == CodexGoalStatus.BLOCKED.value:
            return CodexTurnStatus.INTERRUPTED, limit
        return CodexTurnStatus.INTERRUPTED, stop

    def _snapshot(self, turn: CodexLiveTurn, reported: Turn, status: CodexTurnStatus, problem: CodexProblem | None, items: Sequence[ThreadItem]) -> CodexTurnSnapshot:
        # @intent results-follow-the-sdk-result-contract
        # The result is built as openai-codex builds a TurnResult, then
        # copied by the repo's own serializer with this turn's own token
        # delta. A completed turn without a final answer has no result
        # (INV-20); a failed one maps its error (INV-22); an answer that
        # misses output_schema stays COMPLETED with its raw text (INV-21).
        collected = TurnResult(
            id=turn.handle.turn_id,
            status=TurnStatus(status.value),
            error=reported.error,
            started_at=reported.started_at,
            completed_at=reported.completed_at,
            duration_ms=reported.duration_ms,
            final_response=final_answer(items),
            items=list(items),
            usage=turn.latest_usage,
        )
        try:
            result = replace(CodexResultSerializer.from_sdk(turn.handle.thread_id, collected), last_usage=turn.usage_delta())
        except CodexAgentError:
            return CodexTurnSnapshot(handle=turn.handle, status=CodexTurnStatus.FAILED, problem=CodexErrorMapper.problem(FailureCode.CODEX_RESPONSE_INVALID, NO_FINAL_ANSWER_MESSAGE))
        if status is CodexTurnStatus.FAILED and problem is None:
            problem = CodexErrorMapper.turn_problem(result.error)
        schema = turn.request.output_schema
        if status is CodexTurnStatus.COMPLETED and schema is not None:
            parsed, error = self._schemas.validate(result.final_response or "", schema)
            if error is not None:
                problem = CodexErrorMapper.problem(FailureCode.CODEX_SCHEMA_VIOLATION, SCHEMA_MESSAGE)
            else:
                result = replace(result, structured=parsed)
        return CodexTurnSnapshot(handle=turn.handle, status=status, result=result, problem=problem)


__all__ = ["CodexParamsTranslator", "CodexResponseTranslator"]
