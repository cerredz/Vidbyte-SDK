"""FILE: vidbyte/agents/jev/compute/controller.py

PURPOSE: Read exact run facts, refresh the verified run brief, recognize enabled dynamic-compute options, launch CLONE when selected, and report checkpoint outcomes.
ROLE IN CODEBASE: JevAgent builds the controller when compute is enabled; the runtime begins each run and calls checkpoint after tool iterations.
ARCHITECTURE NOTE: Recognition uses one fresh brief and runs only after a verified refresh. FRESH_AGENT, FORK_AGENT, and SUBAGENT are observe-only; a CLONE selection runs the clones once per run and appends their results to the main loop's messages.
COMMON MODIFICATION PATTERNS: Keep refresh status reporting and recognition order in checkpoint; send records through JevResponse.
KNOWN EDGE CASES: Facts are reported at every checkpoint. A rejected or unavailable brief refresh never triggers recognition. A launch whose clones all fail records nothing and appends nothing.
RELATED DOCS: docs/design/jev-compute-situations.md, docs/design/jev-compute-clone.md, and docs/design/jev-run-brief.md.
TESTS: tests/test_jev_compute.py, tests/test_jev_compute_situations.py, and tests/test_jev_compute_clone.py.
"""

from __future__ import annotations

from typing import Any

from vidbyte.agents.jev.brief import JevRunBriefKeeper
from vidbyte.agents.jev.compute.clone import JevCloneAgent
from vidbyte.agents.jev.compute.facts import JevRunFactsReader
from vidbyte.agents.jev.compute.recognizer import JevComputeRecognizer
from vidbyte.agents.jev.done.event_log import JevRunEventLog
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings, JevComputeSettings
from vidbyte.agents.runtime import BaseAgentRuntimeLoopState
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.jev import JevCloneResult, JevRunBrief, JevRunBriefUpdate
from vidbyte.lib.enums.jev import JevDynamicComputeOption, JevRunBriefUpdateStatus
from vidbyte.lib.jev.compute import JevComputeRegistry


class JevComputeController:
    """Refresh the verified run brief, recognize enabled options after successful updates, and launch CLONE when selected."""

    def __init__(self, settings: JevAgentSettings, compute: JevComputeSettings, decision: DecisionModelConfig, response: JevResponse) -> None:
        self.settings = settings
        self.clones = compute.clones
        self.keeper = JevRunBriefKeeper(settings, compute.brief)
        dynamic_compute = JevComputeRegistry.validate(compute.dynamic_compute)
        self.recognizer = JevComputeRecognizer(decision, dynamic_compute) if dynamic_compute else None
        self.response = response
        self._cloned = False

    def begin(self, request: str) -> None:
        """Start a new run without carrying forward the previous run's brief."""
        # @intent every-run-starts-without-a-brief
        # A brief and its event pointer describe one request only; keeper.begin resets both before the next run.
        self.keeper.begin(request)
        self._cloned = False

    async def checkpoint(self, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> None:
        """Read and report facts, refresh the brief when due, recognize only a verified update, and act on a CLONE selection."""
        # @intent checkpoint-reports-facts-and-recognizes-only-updated-briefs
        # Facts are exact at every checkpoint, while recognition uses a brief only after the refresh status confirms it was updated.
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
        if decision.option is JevDynamicComputeOption.CLONE and not self._cloned:
            await self._clone(iteration, self.keeper.brief, messages)

    async def _clone(self, iteration: int, brief: JevRunBrief, messages: list[dict[str, Any]]) -> None:
        # @intent clone-launches-once-per-run
        # Each launch multiplies the run's cost, so one CLONE selection per run is acted on and later ones are only recorded.
        self._cloned = True
        outputs = await JevCloneAgent.attempt(self.settings, self.clones, self.keeper.request, brief)
        if not outputs:
            return
        self.response.clone(JevCloneResult(iteration=iteration, outputs=outputs))
        messages.append({"role": "user", "content": JevCloneAgent.results(outputs)})


__all__ = ["JevComputeController"]
