"""FILE: vidbyte/agents/agent_swarm/swarm.py

PURPOSE: Defines AgentSwarm, the developer's entry point: built once from AgentSwarmSettings, its arun(goal) creates the shared workplace folder and runs one swarm to its end, returning an AgentSwarmResult.
ROLE IN CODEBASE: The thin public front of the agent_swarm package. Each arun builds a fresh AgentSwarmRuntime (runtime.py) over the folder AgentSwarmWorkplace (workplace.py) prepares, so no state passes from one run to the next. Exported by vidbyte/agents/agent_swarm/__init__.py, vidbyte/agents/__init__.py, and the root vidbyte package.
ARCHITECTURE NOTE: AgentSwarm holds the settings and one flag only; every piece of run state lives in the runtime of that run. The flag is set and cleared inside try/finally, so a run that fails or is cancelled still leaves the swarm ready for its next run, and a second arun on the same object while one is in progress is refused instead of sharing a folder and callback with it.
FUNCTION INVENTORY: AgentSwarm.__init__ checks and keeps the settings; arun is the narrated main function of one run.
COMMON MODIFICATION PATTERNS: A new run-level option belongs in AgentSwarmSettings; this class stays a thin front that prepares the folder and hands over to AgentSwarmRuntime.
WHAT NOT TO DO IN THIS FILE: 1. Do not keep inboxes, events, agents, or results on this object. 2. Do not create the workplace in __init__. 3. Do not clear the running flag anywhere but the finally block.
KNOWN EDGE CASES: A goal that is not text, or is blank, is refused before the folder is created. Two AgentSwarm objects built from the same settings may run at once; they share the folder, which is not guarded.
RELATED DOCS: docs/spec/agent-swarm/spec.md (sections 6.1 INV-18 to INV-20, and 8.5); vidbyte/agents/agent_swarm/README.md
TESTS: tests/features/agent_swarm/test_agent_swarm_lifecycle.py and tests/features/agent_swarm/test_agent_swarm_workplace.py
"""

from __future__ import annotations

from pathlib import Path

from vidbyte.agents.agent_swarm.runtime import AgentSwarmRuntime
from vidbyte.agents.agent_swarm.settings import AgentSwarmSettings
from vidbyte.agents.agent_swarm.workplace import AgentSwarmWorkplace
from vidbyte.lib.dataclasses.agent_swarm import AgentSwarmResult
from vidbyte.lib.dataclasses.validation import RecordFieldValidator
from vidbyte.lib.errors import ConfigurationError


class AgentSwarm:
    """A group of agents that work on one goal in one shared folder and message each other until none has work left."""

    def __init__(self, settings: AgentSwarmSettings) -> None:
        # Only checked settings are accepted, so every run can trust them.
        if not isinstance(settings, AgentSwarmSettings):
            raise ConfigurationError(f"AgentSwarm requires an AgentSwarmSettings instance; got {type(settings).__name__}.", details={"field": "settings", "received_type": type(settings).__name__})
        self.settings = settings
        self._running = False

    async def arun(self, goal: str) -> AgentSwarmResult:
        """Run the swarm on the goal until no agent has work left, the turn budget is spent, every agent failed, or the time limit is reached."""
        # @intent one-run-at-a-time-per-swarm
        # A second run on the same swarm while one is in progress would
        # share its folder and callback, so it is refused before anything
        # happens, as is a goal that is not text.
        if self._running:
            raise ConfigurationError("This AgentSwarm is already running; wait for its arun to return before starting another run.", details={"field": "arun"})
        RecordFieldValidator.require_text(goal, "goal")

        # Mark the run as in progress until it returns, fails, or is
        # cancelled.
        self._running = True
        try:
            # Create the shared folder, keeping anything already in it.
            root = AgentSwarmWorkplace(Path(self.settings.workplace)).prepare()
            # Run one fresh swarm over it and return its result.
            return await AgentSwarmRuntime(self.settings, root).arun(goal)
        finally:
            self._running = False


__all__ = ["AgentSwarm"]
