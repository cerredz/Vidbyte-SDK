"""FILE: vidbyte/agents/jev/compute/controller.py

PURPOSE: Implements JevComputeController, the owner of JevAgent's mid-run compute checkpoint: between the main agent's tool iterations it reads exact run facts, refreshes the run brief, recognizes enabled situations after a verified refresh, and reports all outcomes through JevResponse.
ROLE IN CODEBASE: JevAgent builds one controller at construction when JevRuntimeSettings.compute is set; JevRuntime calls `begin` when the main agent is about to run and `checkpoint` from AgentRuntime's `_after_tool_iteration` hook.
ARCHITECTURE NOTE: The runtime holds no compute logic; every step the checkpoint takes lives here and in the modules it composes. Recognition runs only after a verified brief refresh. The checkpoint observes and records only: acting on a recognized situation is a later step.
COMMON MODIFICATION PATTERNS: Add a checkpoint step as a method called from `checkpoint`, keep its policy in its own module under vidbyte/agents/jev/, and report its outcome through a JevResponse method.
KNOWN EDGE CASES: Like the JevAgent that owns it, one controller serves one run at a time. A writer outage or rejected refresh asks Jev nothing; Jev failures recognize no situation. Facts are recorded at every checkpoint.
RELATED DOCS: docs/design/jev-compute-checkpoint.md, docs/design/jev-compute-situations.md, and docs/design/jev-run-brief.md.
TESTS: tests/test_jev_compute.py and tests/test_jev_compute_situations.py.
"""

from __future__ import annotations

from vidbyte.agents.jev.brief import JevRunBriefKeeper
from vidbyte.agents.jev.compute.facts import JevRunFactsReader
from vidbyte.agents.jev.done.event_log import JevRunEventLog
from vidbyte.agents.jev.compute.recognizer import JevComputeRecognizer
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings, JevComputeSettings
from vidbyte.agents.runtime import BaseAgentRuntimeLoopState
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.jev import JevRunBriefUpdate
from vidbyte.lib.enums import JevRunBriefUpdateStatus
from vidbyte.lib.jev.compute import JevComputeRegistry


class JevComputeController:
    """Keeps the run brief and facts current, then recognizes enabled situations after verified updates."""

    def __init__(self, settings: JevAgentSettings, compute: JevComputeSettings, decision: DecisionModelConfig, response: JevResponse) -> None:
        # Builds the brief keeper and optional recognizer once at JevAgent construction.
        self.keeper = JevRunBriefKeeper(settings, compute.brief)
        situations = JevComputeRegistry.validate(compute.situations)
        self.recognizer = JevComputeRecognizer(decision, situations) if situations else None
        self.response = response

    def begin(self, request: str) -> None:
        """Start the checkpoint for a new run of the main agent on this request."""
        # @intent every-run-starts-without-a-brief
        # The brief describes one run's work, so a new run must never inherit the previous run's brief, facts, or
        # event pointer, which would cite events that no longer exist.
        self.keeper.begin(request)

    async def checkpoint(self, state: BaseAgentRuntimeLoopState) -> None:
        """Read exact facts, refresh the brief when due, and recognize situations after verified updates."""
        # @intent the-checkpoint-observes-without-changing-the-run
        # The checkpoint reads the loop state and never writes to it. Writer and Jev outages leave the run unchanged.
        facts = JevRunFactsReader.read(state.iteration_outputs, state.call_contexts, tokens_used=state.tokens_used)
        self.response.run_facts(facts)
        iteration = len(state.iteration_outputs)
        if not self.keeper.due(iteration):
            return
        result = await self.keeper.refresh_if_due(state.iteration_outputs, state.call_contexts)
        if result is None:
            status = JevRunBriefUpdateStatus.UNAVAILABLE
        elif result.brief is None:
            status = JevRunBriefUpdateStatus.REJECTED
        else:
            status = JevRunBriefUpdateStatus.UPDATED
        update = JevRunBriefUpdate(status=status, iteration=iteration)
        self.response.run_brief(update, self.keeper.brief)
        if status is JevRunBriefUpdateStatus.UPDATED and self.recognizer is not None and self.keeper.brief is not None:
            events = JevRunEventLog.from_run(self.keeper.request, state.iteration_outputs, state.call_contexts)
            decision = await self.recognizer.recognize(iteration, self.keeper.request, self.keeper.brief, facts, events)
            self.response.compute_decision(decision)


__all__ = ["JevComputeController"]
