"""FILE: vidbyte/agents/jev/compute/controller.py

PURPOSE: Implements JevComputeController, the owner of JevAgent's mid-run compute checkpoint: between the main agent's tool iterations it reads the run's exact facts and keeps the run brief current, and reports both through JevResponse.
ROLE IN CODEBASE: JevAgent builds one controller at construction when JevRuntimeSettings.compute is set; JevRuntime calls `begin` when the main agent is about to run and `checkpoint` from AgentRuntime's `_after_tool_iteration` hook.
ARCHITECTURE NOTE: The runtime holds no compute logic; every step the checkpoint takes lives here and in the modules it composes. The checkpoint observes and records only: deciding with Jev and acting on the decision are later steps that build on the brief and facts this controller keeps.
COMMON MODIFICATION PATTERNS: Add a checkpoint step as a method called from `checkpoint`, keep its policy in its own module under vidbyte/agents/jev/, and report its outcome through a JevResponse method.
KNOWN EDGE CASES: Like the JevAgent that owns it, one controller serves one run at a time. A writer outage leaves the previous brief in place and never stops the run. Facts are recorded at every checkpoint; a refresh attempt is recorded only when one ran.
RELATED DOCS: docs/design/jev-compute-checkpoint.md and docs/design/jev-run-brief.md.
TESTS: tests/test_jev_compute.py.
"""

from __future__ import annotations

from vidbyte.agents.jev.brief import JevRunBriefKeeper
from vidbyte.agents.jev.compute.facts import JevRunFactsReader
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings, JevComputeSettings
from vidbyte.agents.runtime import BaseAgentRuntimeLoopState
from vidbyte.lib.dataclasses.jev import JevRunBriefUpdate
from vidbyte.lib.enums import JevRunBriefUpdateStatus


class JevComputeController:
    """Runs JevAgent's mid-run compute checkpoint: keeps the run brief and facts current between tool iterations."""

    def __init__(self, settings: JevAgentSettings, compute: JevComputeSettings, response: JevResponse) -> None:
        # Builds the run brief's keeper, and through it the separate writer agent, once at JevAgent construction.
        self.keeper = JevRunBriefKeeper(settings, compute.brief)
        self.response = response

    def begin(self, request: str) -> None:
        """Start the checkpoint for a new run of the main agent on this request."""
        # @intent every-run-starts-without-a-brief
        # The brief describes one run's work, so a new run must never inherit the previous run's brief, facts, or
        # event pointer, which would cite events that no longer exist.
        self.keeper.begin(request)

    async def checkpoint(self, state: BaseAgentRuntimeLoopState) -> None:
        """Read the run's facts, refresh the brief when its cadence calls for it, and report both."""
        # @intent the-checkpoint-observes-without-changing-the-run
        # The checkpoint reads the loop state and never writes to it, and a writer outage only leaves the previous
        # brief standing, so enabling compute cannot change the main agent's messages, tools, or answer.
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
        self.response.run_brief(JevRunBriefUpdate(status=status, iteration=iteration), self.keeper.brief)


__all__ = ["JevComputeController"]
