"""FILE: vidbyte/agents/jev/compute/controller.py

PURPOSE: Read exact run facts, refresh the verified run brief, recognize enabled dynamic-compute options, run supported moves within a budget, and report checkpoint outcomes.
ROLE IN CODEBASE: JevAgent builds the controller when compute is enabled; the runtime begins each run and calls checkpoint after continuing tool iterations.
ARCHITECTURE NOTE: Recognition uses one shared evidence state and runs only after a verified brief refresh. The fresh-agent move receives that same state and adds helper work after the preceding main-agent evidence.
COMMON MODIFICATION PATTERNS: Keep refresh status reporting and recognition order in checkpoint; send decision and move records through JevResponse.
KNOWN EDGE CASES: Facts are reported at every checkpoint. Rejected or unavailable brief refreshes never trigger recognition. Other recognized options have no move yet.
RELATED DOCS: docs/design/jev-compute-situations.md, docs/design/jev-compute-reset.md, and docs/design/jev-run-brief.md.
TESTS: tests/test_jev_compute.py, tests/test_jev_compute_situations.py, and tests/test_jev_compute_reset.py.
"""

from __future__ import annotations

from typing import Any

from vidbyte.agents.jev.brief import JevRunBriefKeeper
from vidbyte.agents.jev.compute.budget import JevComputeBudget
from vidbyte.agents.jev.compute.facts import JevRunFactsReader
from vidbyte.agents.jev.compute.helpers import JevComputeHelpers
from vidbyte.agents.jev.compute.recognizer import JevComputeRecognizer
from vidbyte.agents.jev.compute.reset import JevComputeReset
from vidbyte.agents.jev.done import JevRunState
from vidbyte.agents.jev.done.event_log import JevRunEventLog
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings, JevComputeSettings
from vidbyte.agents.runtime import BaseAgentRuntimeLoopState
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.jev import (
    JevComputeDecision,
    JevComputeMove,
    JevRunBrief,
    JevRunBriefUpdate,
    JevRunFacts,
)
from vidbyte.lib.enums.jev import (
    JevComputeMoveStatus,
    JevDynamicComputeOption,
    JevRunBriefUpdateStatus,
)
from vidbyte.lib.jev.compute import JevComputeRegistry

_FRESH_AGENT_HELPERS = 1


class JevComputeController:
    """Refresh the verified run brief, recognize enabled options, and run supported moves."""

    def __init__(
        self,
        settings: JevAgentSettings,
        compute: JevComputeSettings,
        decision: DecisionModelConfig,
        response: JevResponse,
        run_state: JevRunState | None = None,
    ) -> None:
        self.keeper = JevRunBriefKeeper(settings, compute.brief)
        dynamic_compute = JevComputeRegistry.validate(compute.dynamic_compute)
        self.recognizer = JevComputeRecognizer(decision, dynamic_compute) if dynamic_compute else None
        self.budget = JevComputeBudget(compute)
        self.reset = JevComputeReset(JevComputeHelpers(settings, compute))
        self.response = response
        self.run_state = run_state

    def begin(self, request: str) -> None:
        """Start a new run without carrying forward the previous run's brief or spent budget."""
        # @intent every-run-starts-without-a-brief
        # The brief and budget are run-local, so neither event pointers nor spent moves carry over to another request.
        self.keeper.begin(request)
        self.budget.begin()

    async def checkpoint(self, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> None:
        """Read exact facts, refresh the brief when due, recognize a verified state, and act on a supported option."""
        # @intent checkpoint-only-adds-a-reported-helper-result
        # Recognition preserves #513's read-only checkpoint. The loop changes only when a completed fresh helper
        # returns a report, which is appended as one user message after the current tool iteration.
        facts = JevRunFactsReader.read(state.iteration_outputs, state.call_contexts, tokens_used=state.tokens_used)
        self.response.run_facts(facts)
        iteration = len(state.iteration_outputs)
        if not self.keeper.due(iteration):
            return

        verification = await self.keeper.refresh_if_due(state.iteration_outputs, state.call_contexts)
        if verification is None:
            status = JevRunBriefUpdateStatus.UNAVAILABLE
        elif verification.brief is None:
            status = JevRunBriefUpdateStatus.REJECTED
        else:
            status = JevRunBriefUpdateStatus.UPDATED
        update = JevRunBriefUpdate(status=status, iteration=iteration)
        self.response.run_brief(update, self.keeper.brief)

        brief = self.keeper.brief
        if status is not JevRunBriefUpdateStatus.UPDATED or self.recognizer is None or brief is None:
            return
        events = JevRunEventLog.from_run(self.keeper.request, state.iteration_outputs, state.call_contexts)
        decision = await self.recognizer.recognize(iteration, self.keeper.request, brief, facts, events)
        self.response.compute_decision(decision)
        if decision.option is JevDynamicComputeOption.FRESH_AGENT:
            await self._fresh_agent(decision, brief, facts, events, state, messages)

    async def _fresh_agent(
        self,
        decision: JevComputeDecision,
        brief: JevRunBrief,
        facts: JevRunFacts,
        events: JevRunEventLog,
        state: BaseAgentRuntimeLoopState,
        messages: list[dict[str, Any]],
    ) -> None:
        """Run one independent fresh agent when the run-local budget permits it."""
        # @intent fresh-agent-only-dispatch
        # Only the explicit fresh-agent option may spend helper budget; other recognized options remain report-only.
        blocked = self.budget.blocked(decision.iteration, _FRESH_AGENT_HELPERS)
        if blocked is not None:
            self.response.compute_move(JevComputeMove(
                option=JevDynamicComputeOption.FRESH_AGENT,
                iteration=decision.iteration,
                status=blocked,
            ))
            return

        # A helper start consumes budget even if the helper has an outage or returns no report.
        self.budget.spend(decision.iteration, _FRESH_AGENT_HELPERS)
        result = await self.reset.run(self.keeper.request, brief, facts, events)
        if result is None:
            self.response.compute_move(JevComputeMove(
                option=JevDynamicComputeOption.FRESH_AGENT,
                iteration=decision.iteration,
                status=JevComputeMoveStatus.FAILED,
                helpers=_FRESH_AGENT_HELPERS,
            ))
            return

        messages.append({"role": "user", "content": self.reset.message(result.output)})
        if self.run_state is not None:
            self.run_state.add_helper_evidence(state.iteration_outputs, state.call_contexts, result.evidence)
        self.response.compute_move(JevComputeMove(
            option=JevDynamicComputeOption.FRESH_AGENT,
            iteration=decision.iteration,
            status=JevComputeMoveStatus.COMPLETED,
            helpers=_FRESH_AGENT_HELPERS,
            output=result.output,
            usage=result.usage,
        ))


__all__ = ["JevComputeController"]
