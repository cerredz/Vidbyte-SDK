"""Own JevAgent's run-brief refresh and dynamic-compute recognition checkpoint."""

from __future__ import annotations

from vidbyte.agents.jev.brief import JevRunBriefKeeper
from vidbyte.agents.jev.compute.facts import JevRunFactsReader
from vidbyte.agents.jev.compute.recognizer import JevComputeRecognizer
from vidbyte.agents.jev.done.event_log import JevRunEventLog
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings, JevComputeSettings
from vidbyte.agents.runtime import BaseAgentRuntimeLoopState
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.jev import JevRunBriefUpdate
from vidbyte.lib.enums.jev import JevRunBriefUpdateStatus
from vidbyte.lib.jev.compute import JevComputeRegistry


class JevComputeController:
    """Refresh the verified run brief and recognize enabled options after successful updates."""

    def __init__(self, settings: JevAgentSettings, compute: JevComputeSettings, decision: DecisionModelConfig, response: JevResponse) -> None:
        self.keeper = JevRunBriefKeeper(settings, compute.brief)
        dynamic_compute = JevComputeRegistry.validate(compute.dynamic_compute)
        self.recognizer = JevComputeRecognizer(decision, dynamic_compute) if dynamic_compute else None
        self.response = response

    def begin(self, request: str) -> None:
        """Start a new run without carrying forward the previous run's brief."""
        self.keeper.begin(request)

    async def checkpoint(self, state: BaseAgentRuntimeLoopState) -> None:
        """Read and report facts, refresh the brief when due, then recognize only a verified update."""
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

        if status is not JevRunBriefUpdateStatus.UPDATED or self.recognizer is None or self.keeper.brief is None:
            return
        events = JevRunEventLog.from_run(self.keeper.request, state.iteration_outputs, state.call_contexts)
        decision = await self.recognizer.recognize(iteration, self.keeper.request, self.keeper.brief, facts, events)
        self.response.compute_decision(decision)


__all__ = ["JevComputeController"]
