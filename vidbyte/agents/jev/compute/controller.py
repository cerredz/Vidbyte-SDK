"""FILE: vidbyte/agents/jev/compute/controller.py

PURPOSE: Implements JevComputeController, the owner of JevAgent's mid-run compute checkpoint: between the main agent's tool iterations it reads the run's exact facts, keeps the run brief current, asks Jev which compute situation the run is in after each verified refresh, acts on a recognized situation within the run's compute budget, and reports all of it through JevResponse.
ROLE IN CODEBASE: JevAgent builds one controller at construction when JevRuntimeSettings.compute is set; JevRuntime calls `begin` when the main agent is about to run and `checkpoint` from AgentRuntime's `_after_tool_iteration` hook with the loop's state and messages.
ARCHITECTURE NOTE: The runtime holds no compute logic; every step the checkpoint takes lives here and in the modules it composes. Recognition runs only right after a verified brief refresh, so Jev's cadence follows the brief's. A recognized situation is acted on by its own move module, after JevComputeBudget allows it; the move's result reaches the main agent as one appended message, and its helpers' work reaches the done checks as evidence in run order.
COMMON MODIFICATION PATTERNS: Add a move for a situation as its own module under this package and one case in `_act`; keep its prompt in vidbyte/prompts/prompts/jev_compute/ and report its outcome as a JevComputeMove.
KNOWN EDGE CASES: Like the JevAgent that owns it, one controller serves one run at a time. A writer outage or a rejected refresh asks Jev nothing; a Jev outage recognizes nothing. Situations with no move yet are recognized and recorded but not acted on. A failed helper is charged to the budget and recorded, and the main loop continues unchanged.
RELATED DOCS: docs/design/jev-compute-checkpoint.md, docs/design/jev-compute-situations.md, docs/design/jev-compute-reset.md, and docs/design/jev-run-brief.md.
TESTS: tests/test_jev_compute.py, tests/test_jev_compute_situations.py, and tests/test_jev_compute_reset.py.
"""

from __future__ import annotations

from typing import Any

from vidbyte.agents.jev.brief import JevRunBriefEvents, JevRunBriefKeeper
from vidbyte.agents.jev.compute.budget import JevComputeBudget
from vidbyte.agents.jev.compute.helpers import JevComputeHelpers
from vidbyte.agents.jev.compute.recognizer import JevComputeRecognizer
from vidbyte.agents.jev.compute.reset import JevComputeReset
from vidbyte.agents.jev.done import JevRunState
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings, JevComputeSettings
from vidbyte.agents.runtime import BaseAgentRuntimeLoopState
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.jev import (
    JevComputeDecision,
    JevComputeMove,
    JevRunBrief,
    JevRunBriefUpdate,
)
from vidbyte.lib.enums.jev import (
    JevComputeMoveStatus,
    JevComputeSituation,
    JevRunBriefUpdateStatus,
)
from vidbyte.lib.jev.compute import JevComputeRegistry

# The number of helper agents the reset move starts.
_RESET_HELPERS = 1


class JevComputeController:
    """Runs JevAgent's mid-run compute checkpoint: keeps the run brief current, asks Jev which situation the run is in, and acts on it."""

    def __init__(self, settings: JevAgentSettings, compute: JevComputeSettings, decision: DecisionModelConfig, response: JevResponse, run_state: JevRunState | None = None) -> None:
        # Builds the brief's keeper and writer, the recognizer, the budget, and every move once, at JevAgent construction.
        self.keeper = JevRunBriefKeeper(settings, compute.brief)
        situations = JevComputeRegistry.validate(compute.situations)
        self.recognizer = JevComputeRecognizer(decision, situations) if situations else None
        self.budget = JevComputeBudget(compute)
        self.reset = JevComputeReset(JevComputeHelpers(settings, compute))
        self.response = response
        self.run_state = run_state

    def begin(self, request: str) -> None:
        """Start the checkpoint for a new run of the main agent on this request."""
        # @intent every-run-starts-without-a-brief
        # The brief and the budget describe one run, so a new run must never inherit the previous run's brief, facts,
        # event pointer, or spent moves, which would cite events that no longer exist or block moves it never made.
        self.keeper.begin(request)
        self.budget.begin()

    async def checkpoint(self, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> None:
        """Read the run's facts, refresh the brief on its cadence, recognize the run's situation after a verified refresh, act on it, and report each step."""
        # @intent only-a-completed-move-changes-the-run
        # The checkpoint reads the loop state and writes to the loop only by appending one message after a helper
        # reports, so outages, rejected refreshes, unrecognized situations, and blocked or failed moves all leave the
        # main agent's messages, tools, and answer exactly as they would be without compute.
        update = await self.keeper.refresh_if_due(state.iteration_outputs, state.call_contexts, tokens_used=state.tokens_used)
        self.response.run_facts(self.keeper.facts)
        if update is None:
            return
        self.response.run_brief(update, self.keeper.brief)
        decision = await self._recognize(update, state)
        if decision is not None and decision.situation is not None:
            await self._act(decision, state, messages)

    async def _recognize(self, update: JevRunBriefUpdate, state: BaseAgentRuntimeLoopState) -> JevComputeDecision | None:
        # Asks Jev which situation the run is in, only when this checkpoint produced a newly verified brief.
        # @intent jev-reads-only-a-freshly-verified-brief
        # Recognition follows the brief's cadence and reads the brief the refresh just verified, so Jev is never asked
        # twice about the same picture of the run and never judges a brief the latest events have already outdated.
        brief = self.keeper.brief
        if self.recognizer is None or brief is None or update.status is not JevRunBriefUpdateStatus.UPDATED:
            return None
        events = JevRunBriefEvents.from_run(self.keeper.request, state.iteration_outputs, state.call_contexts)
        decision = await self.recognizer.recognize(update.iteration, self.keeper.request, brief, events)
        self.response.compute_decision(decision)
        return decision

    async def _act(self, decision: JevComputeDecision, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> None:
        # Runs the recognized situation's move when the budget allows it, and records what happened.
        situation, iteration, brief = decision.situation, decision.iteration, self.keeper.brief
        if situation is None or brief is None:
            return
        match situation:
            case JevComputeSituation.REPEATING:
                # The main agent keeps retrying a failed approach: a fresh helper takes the problem.
                blocked = self.budget.blocked(iteration, _RESET_HELPERS)
                move = JevComputeMove(situation, iteration, blocked) if blocked is not None else await self._reset(iteration, brief, state, messages)
            case _:
                # Recognized and recorded; this situation has no move yet.
                return
        self.response.compute_move(move)

    async def _reset(self, iteration: int, brief: JevRunBrief, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> JevComputeMove:
        # Hands the stuck problem to a fresh helper, then brings its report back to the main agent and its work to the done checks.
        # @intent a-move-is-charged-once-its-helper-starts
        # The budget is spent as soon as a helper runs, even if it fails, because its compute is spent either way; only a
        # report is appended to the loop, and the helper's run reaches the done checks after the main work that preceded it.
        outcome = await self.reset.run(self.keeper.request, brief)
        if outcome is None:
            return JevComputeMove(JevComputeSituation.REPEATING, iteration, JevComputeMoveStatus.FAILED)
        self.budget.spend(iteration, _RESET_HELPERS)
        problem, result = outcome
        if result is None:
            return JevComputeMove(JevComputeSituation.REPEATING, iteration, JevComputeMoveStatus.FAILED, helpers=_RESET_HELPERS)
        messages.append({"role": "user", "content": self.reset.message(problem, result.output)})
        if self.run_state is not None:
            self.run_state.add_helper_evidence(state.iteration_outputs, state.call_contexts, result.evidence)
        return JevComputeMove(JevComputeSituation.REPEATING, iteration, JevComputeMoveStatus.COMPLETED, helpers=_RESET_HELPERS, output=result.output, usage=result.usage)


__all__ = ["JevComputeController"]
