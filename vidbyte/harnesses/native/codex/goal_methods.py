"""FILE: vidbyte/harnesses/native/codex/goal_methods.py

PURPOSE: CodexGoalMethods, the CodexHost mixin for controlling a stored goal: pause_codex_goal pauses it, resume_codex_goal resumes it as a goal run this host tracks, edit_codex_goal changes its objective or token budget, and clear_codex_goal removes it from an idle thread.
ROLE IN CODEBASE: One of the four feature mixins of vidbyte/harnesses/native/codex/; CodexHost inherits its four public methods (first-class D-1). The stored goal is read through CodexThreadHelpers.goal, and the resume's spending start runs through CodexTurnStarts.resume_goal, the same collaborator run_codex_goal's start uses.
ARCHITECTURE NOTE: Imports no openai-codex module and none of the host's SDK-loading collaborators at module level, so importing this mixin, or CodexHost, still loads no SDK (first-class INV-45). Every goal change is one thread/goal/set or thread/goal/clear carrying the user origin, and every set is single-attempt because CODEX_GOAL_SET_METHOD spends (INV-7, INV-30). The resume never clears the goal and never sends its objective or budget, so its usage is kept (INV-31, D-17).
COMMON MODIFICATION PATTERNS: A new goal control is one public method here: guard, its record, _require_goal when it needs a stored goal, then one goal call whose params come from CodexFeatureParamsTranslator.goal_change or goal_clear. A refusal before the call adds its message, cause and next step to vidbyte/lib/constants/codex_host.py.
KNOWN EDGE CASES: A thread with no stored goal is refused after the goal read with codex.session_not_found and its own cause and next step (EC-40). A resume refuses a goal whose status is not paused, blocked, usage-limited or budget-limited, and a budget-limited goal whose budget is spent, before thread/resume (INV-31, EC-58); a thread this host is running is refused before any request (EC-39). An edit never sends a status, so it never starts a goal turn; an echoed budget that differs from the one sent is codex.protocol_mismatch (INV-32). A clear runs on an idle thread only (INV-33, INV-34).
RELATED DOCS: docs/spec/codex-host-first-class/spec.md (sections 8.5, 9.2 and 12.3 row 29, INV-1, INV-7, INV-30 to INV-34, D-16, D-17, D-38)
TESTS: tests/features/codex_host/test_codex_host_goal_control.py, tests/features/codex_host/test_codex_host_feature_contract.py, tests/features/codex_host/test_codex_host_feature_structure.py, tests/features/codex_host/test_codex_host_feature_docs.py
"""

from __future__ import annotations

from vidbyte.harnesses.native.codex.errors import CodexErrorMapper
from vidbyte.harnesses.native.codex.host_core import CodexHostCore
from vidbyte.lib.constants.codex import (
    CODEX_GOAL_SET_METHOD,
    CODEX_THREAD_RESUME_METHOD,
)
from vidbyte.lib.constants.codex_host import (
    CODEX_GOAL_CLEAR_METHOD,
    CODEX_HOST_BUDGET_ECHO_MESSAGE,
    CODEX_HOST_GOAL_BUDGET_SPENT_CAUSE,
    CODEX_HOST_GOAL_BUDGET_SPENT_MESSAGE,
    CODEX_HOST_GOAL_BUDGET_SPENT_NEXT_STEP,
    CODEX_HOST_GOAL_NOT_RESUMABLE_CAUSE,
    CODEX_HOST_GOAL_NOT_RESUMABLE_MESSAGE,
    CODEX_HOST_GOAL_NOT_RESUMABLE_NEXT_STEP,
    CODEX_HOST_GOAL_RESUME_FROM_STATUSES,
    CODEX_HOST_NO_GOAL_CAUSE,
    CODEX_HOST_NO_GOAL_NEXT_STEP,
    CODEX_HOST_NO_STORED_GOAL_MESSAGE,
)
from vidbyte.lib.dataclasses.codex_host import (
    CodexSpawnRequest,
    CodexThreadGoal,
    CodexTurnHandle,
)
from vidbyte.lib.dataclasses.codex_host_inputs import (
    CodexGoalEditRequest,
    CodexGoalResumeRequest,
    CodexThreadRef,
)
from vidbyte.lib.enums.codex import CodexGoalStatus, CodexHostOperation
from vidbyte.lib.enums.failure import FailureCode


class CodexGoalMethods(CodexHostCore):
    """The goal pause, resume, edit and clear functions CodexHost inherits."""

    async def pause_codex_goal(self, thread_id: str) -> CodexThreadGoal:
        """Pause a thread's stored goal and return it as Codex stored it.

        A goal run this host tracks on the thread ends once any turn
        already running finishes. resume_codex_goal continues it.
        """
        # @intent a-pause-is-one-user-status-set
        # The thread must hold a goal; then one single-attempt set of
        # the paused status, as the user (first-class INV-30).
        operation = CodexHostOperation.PAUSE_CODEX_GOAL
        self._guard(operation, talks=True)
        ref = CodexThreadRef(operation=operation, thread_id=thread_id)
        await self._require_goal(ref)
        connection = self._connection
        pause = connection.raw(CODEX_GOAL_SET_METHOD, self._feature_params.goal_change(ref.thread_id, status=CodexGoalStatus.PAUSED), parse=self._feature_responses.goal)
        return await connection.call(operation, CODEX_GOAL_SET_METHOD, pause, thread_id=ref.thread_id)

    async def resume_codex_goal(self, thread_id: str, request: CodexSpawnRequest | None = None) -> CodexTurnHandle:
        """Resume a thread's paused, blocked, usage-limited or budget-limited goal as a goal run this host tracks, and return its handle.

        The goal keeps its objective, budget and usage; it is never
        cleared or started again. A budget-limited goal whose budget is
        spent is refused: raise or remove the budget with edit_codex_goal
        first. A complete goal cannot be resumed, and an active goal that
        nothing runs is paused first. Every spending check runs, as for a
        spawn.
        """
        # @intent a-resume-continues-the-stored-goal
        # Reserve the thread, run the spending checks, check the stored
        # goal can continue, then load the thread and set the goal
        # active inside one owned start (first-class INV-31, D-17). Only
        # a missing request means the default, so any other value
        # reaches the record.
        operation = CodexHostOperation.RESUME_CODEX_GOAL
        self._guard(operation, talks=True)
        resuming = CodexGoalResumeRequest(thread_id=thread_id, request=CodexSpawnRequest() if request is None else request)
        thread_id, spawn = resuming.thread_id, resuming.request
        # Reserve the thread before the first await, so a second start
        # on it is refused rather than racing this one.
        self._preflight.require_idle(operation, thread_id)
        self._registry.reserve(thread_id)
        try:
            # Check the reviewer, account, usage, sandbox and models,
            # then that the stored goal exists and can continue.
            await self._preflight.run(operation, spawn)
            goal = await self._require_goal(CodexThreadRef(operation=operation, thread_id=thread_id))
            self._refuse_unresumable(operation, thread_id, goal)
            # Load the thread as continue does, and stop if its
            # approvals would go to a person nothing here answers.
            connection = self._connection
            resume = self._params.thread_resume(thread_id, spawn)
            resumed = await connection.call(operation, CODEX_THREAD_RESUME_METHOD, connection.client.thread_resume, thread_id, resume, thread_id=thread_id)
            self._preflight.reject_routed_reviewer(operation, thread_id, self._responses.routes_to_user(resumed))
            # Set the goal active and own the run it starts, priced as
            # the model the thread resumed with.
            pricing = self._responses.pricing(resumed.model, resumed.model_provider, self._params.turn_model(spawn))
            turn = await self._starts.resume_goal(operation, thread_id, spawn, pricing)
        finally:
            self._registry.release(thread_id)
        return self._starts.accept(operation, turn)

    async def edit_codex_goal(self, thread_id: str, objective: str = "", token_budget: int | None = None, clear_token_budget: bool = False) -> CodexThreadGoal:
        """Change a stored goal's objective or token budget, or remove its budget, and return it as Codex stored it.

        The status never changes, so an edit never starts a goal turn; a
        budget-limited goal stays budget-limited until resume_codex_goal.
        """
        # @intent an-edit-changes-objective-and-budget-never-status
        # The thread must hold a goal; then one single-attempt set of
        # what changed, and a budget Codex echoes back differently is
        # reported (first-class INV-32).
        operation = CodexHostOperation.EDIT_CODEX_GOAL
        self._guard(operation, talks=True)
        edit = CodexGoalEditRequest(thread_id=thread_id, objective=objective, token_budget=token_budget, clear_token_budget=clear_token_budget)
        await self._require_goal(CodexThreadRef(operation=operation, thread_id=edit.thread_id))
        connection = self._connection
        params = self._feature_params.goal_change(edit.thread_id, objective=edit.objective, token_budget=edit.token_budget, clear_token_budget=edit.clear_token_budget)
        echoed = await connection.call(operation, CODEX_GOAL_SET_METHOD, connection.raw(CODEX_GOAL_SET_METHOD, params, parse=self._feature_responses.goal), thread_id=edit.thread_id)
        budget_sent = edit.token_budget is not None or edit.clear_token_budget
        if budget_sent and echoed.token_budget != edit.token_budget:
            echo = CODEX_HOST_BUDGET_ECHO_MESSAGE.format(stored=echoed.token_budget, sent=edit.token_budget)
            raise CodexErrorMapper.error(FailureCode.CODEX_PROTOCOL_MISMATCH, echo, operation, edit.thread_id)
        return echoed

    async def clear_codex_goal(self, thread_id: str) -> bool:
        """Remove a thread's stored goal, with its usage, and return whether Codex had one; it cannot be undone.

        A thread any client is running is refused. run_codex_goal sets a
        new goal with fresh usage.
        """
        operation = CodexHostOperation.CLEAR_CODEX_GOAL
        self._guard(operation, talks=True)
        ref = CodexThreadRef(operation=operation, thread_id=thread_id)
        clear = self._connection.raw(CODEX_GOAL_CLEAR_METHOD, self._feature_params.goal_clear(ref.thread_id), parse=self._feature_responses.cleared)
        return await self._change_idle(operation, ref.thread_id, CODEX_GOAL_CLEAR_METHOD, clear, loads=False)

    async def _require_goal(self, ref: CodexThreadRef) -> CodexThreadGoal:
        # The thread must exist and hold a stored goal; none is refused
        # with its own cause and next step (first-class INV-30, EC-40).
        goal = await self._threads.goal(ref)
        if goal is None:
            message = CODEX_HOST_NO_STORED_GOAL_MESSAGE.format(operation=ref.operation.value)
            raise CodexErrorMapper.error(FailureCode.CODEX_SESSION_NOT_FOUND, message, ref.operation, ref.thread_id, likely_cause=CODEX_HOST_NO_GOAL_CAUSE, next_step=CODEX_HOST_NO_GOAL_NEXT_STEP)
        return goal

    @staticmethod
    def _refuse_unresumable(operation: CodexHostOperation, thread_id: str, goal: CodexThreadGoal) -> None:
        # @intent resume-only-a-goal-codex-would-not-stop-again
        # Only a paused, blocked or limited goal resumes, and a
        # budget-limited one only once its budget was raised above its
        # use, because Codex would stop it again at once (first-class
        # INV-31, D-38).
        if goal.status not in CODEX_HOST_GOAL_RESUME_FROM_STATUSES:
            message = CODEX_HOST_GOAL_NOT_RESUMABLE_MESSAGE.format(status=goal.status.value)
            raise CodexErrorMapper.error(FailureCode.CONFIGURATION_INVALID_ARGUMENT, message, operation, thread_id, likely_cause=CODEX_HOST_GOAL_NOT_RESUMABLE_CAUSE, next_step=CODEX_HOST_GOAL_NOT_RESUMABLE_NEXT_STEP)
        spent = goal.token_budget is not None and goal.token_budget <= goal.tokens_used
        if goal.status is CodexGoalStatus.BUDGET_LIMITED and spent:
            message = CODEX_HOST_GOAL_BUDGET_SPENT_MESSAGE.format(used=goal.tokens_used, budget=goal.token_budget)
            raise CodexErrorMapper.error(FailureCode.CONFIGURATION_INVALID_ARGUMENT, message, operation, thread_id, likely_cause=CODEX_HOST_GOAL_BUDGET_SPENT_CAUSE, next_step=CODEX_HOST_GOAL_BUDGET_SPENT_NEXT_STEP)


__all__ = ["CodexGoalMethods"]
