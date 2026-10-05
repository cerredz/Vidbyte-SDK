"""FILE: vidbyte/agents/jev/compute/controller.py

PURPOSE: Implements JevComputeController, the owner of JevAgent's mid-run compute checkpoint: between the main agent's tool iterations it reads the run's exact facts, keeps the run brief current, asks Jev which compute situation the run is in after each verified refresh, and reports all of it through JevResponse.
ROLE IN CODEBASE: JevAgent builds one controller at construction when JevRuntimeSettings.compute is set; JevRuntime calls `begin` when the main agent is about to run and `checkpoint` from AgentRuntime's `_after_tool_iteration` hook.
ARCHITECTURE NOTE: The runtime holds no compute logic; every step the checkpoint takes lives here and in the modules it composes. Recognition runs only right after a verified brief refresh, so Jev's cadence follows the brief's, and it reads the same verified brief. The checkpoint observes and records only: acting on a recognized situation is a later step.
COMMON MODIFICATION PATTERNS: Add a checkpoint step as a method called from `checkpoint`, keep its policy in its own module under vidbyte/agents/jev/, and report its outcome through a JevResponse method.
KNOWN EDGE CASES: Like the JevAgent that owns it, one controller serves one run at a time. A writer outage or a rejected refresh asks Jev nothing. With no situation enabled, the checkpoint keeps the brief and asks Jev nothing.
RELATED DOCS: docs/design/jev-compute-checkpoint.md, docs/design/jev-compute-situations.md, and docs/design/jev-run-brief.md.
TESTS: tests/test_jev_compute.py and tests/test_jev_compute_situations.py.
"""

from __future__ import annotations

from vidbyte.agents.jev.brief import JevRunBriefEvents, JevRunBriefKeeper
from vidbyte.agents.jev.compute.recognizer import JevComputeRecognizer
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings, JevComputeSettings
from vidbyte.agents.runtime import BaseAgentRuntimeLoopState
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.jev import JevRunBriefUpdate
from vidbyte.lib.enums.jev import JevRunBriefUpdateStatus
from vidbyte.lib.jev.compute import JevComputeRegistry


class JevComputeController:
    """Runs JevAgent's mid-run compute checkpoint: keeps the run brief current and asks Jev which situation the run is in."""

    def __init__(self, settings: JevAgentSettings, compute: JevComputeSettings, decision: DecisionModelConfig, response: JevResponse) -> None:
        # Builds the run brief's keeper, and through it the separate writer agent, and the recognizer once at JevAgent construction.
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
        """Read the run's facts, refresh the brief when its cadence calls for it, recognize the run's situation after a verified refresh, and report each."""
        # @intent the-checkpoint-observes-without-changing-the-run
        # The checkpoint reads the loop state and never writes to it, and a writer or Jev outage only leaves the previous
        # brief standing or recognizes nothing, so enabling compute cannot change the main agent's messages, tools, or answer.
        update = await self.keeper.refresh_if_due(state.iteration_outputs, state.call_contexts, tokens_used=state.tokens_used)
        self.response.run_facts(self.keeper.facts)
        if update is None:
            return
        self.response.run_brief(update, self.keeper.brief)
        await self._recognize(update, state)

    async def _recognize(self, update: JevRunBriefUpdate, state: BaseAgentRuntimeLoopState) -> None:
        # Asks Jev which situation the run is in, only when this checkpoint produced a newly verified brief.
        # @intent jev-reads-only-a-freshly-verified-brief
        # Recognition follows the brief's cadence and reads the brief the refresh just verified, so Jev is never asked
        # twice about the same picture of the run and never judges a brief the latest events have already outdated.
        brief = self.keeper.brief
        if self.recognizer is None or brief is None or update.status is not JevRunBriefUpdateStatus.UPDATED:
            return
        events = JevRunBriefEvents.from_run(self.keeper.request, state.iteration_outputs, state.call_contexts)
        self.response.compute_decision(await self.recognizer.recognize(update.iteration, self.keeper.request, brief, events))


__all__ = ["JevComputeController"]
