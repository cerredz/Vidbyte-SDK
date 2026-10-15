"""FILE: vidbyte/agents/infinite/agent.py

PURPOSE: Exposes InfiniteMemoryAgent, a root agent that ruthlessly delegates work to generator and verifier subagent pairs and keeps its memory in one guarded workspace folder, built from one validated InfiniteMemoryAgentSettings; and its resume/aresume, which continue an interrupted run from its journal.
ROLE IN CODEBASE: Maps the settings into BaseAgent with AgentRuntimeType.INFINITE_MEMORY, which RuntimeRegistry resolves to InfiniteMemoryRuntime (runtime.py). Builds the InfiniteWorkspace (workspace.py) once, and passes it, the settings, and a resumed run's journal (journal.py) to each run-local runtime through _runtime_extension_kwargs.
ARCHITECTURE NOTE: A closed construction surface like JevAgent: callers pass only the settings object, and the runtime, the preset tools, and the history trim are fixed here. The root holds bash, grep, and read_lines from InfiniteMemoryAgentTools plus the developer's extras; the runtime adds the run-bound tools for each run. Durable sessions are not supported, because a restored agent would be a plain BaseAgent that the runtime refuses; the run journal is the resume path instead.
FUNCTION INVENTORY: __init__ is the narrated main function; _runtime_extension_kwargs hands the run-time objects to the runtime; resume and aresume find an unfinished run and continue it; _resume_prompt writes the resumed root's first message.
COMMON MODIFICATION PATTERNS: A new agent-level capability is a validated field on InfiniteMemoryAgentSettings (settings.py) used here or passed to the runtime through _runtime_extension_kwargs.
WHAT NOT TO DO IN THIS FILE: 1. Do not accept BaseAgent keyword arguments; everything comes from the settings. 2. Do not start a run in resume before the journal checks pass. 3. Do not share one middleware instance between agents; each agent builds its own.
KNOWN EDGE CASES: Building the agent creates the workspace folder and copies the seeds, and refuses a workspace already over a cap. A resumed root starts with a fresh conversation: its first message holds the original task, one short line per finished root-level pair, and the names of interrupted ones. resume() cannot run inside an active event loop; use aresume() there.
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (sections 4, 6.1 INV-1, INV-2, INV-23, INV-27, INV-28, and 8.5); vidbyte/agents/infinite/README.md; vidbyte/agents/jev/agent.py (the pattern this follows)
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_contract.py, tests/features/infinite_memory_agent/test_infinite_memory_acceptance.py, tests/features/infinite_memory_agent/test_infinite_memory_resume.py, and tests/features/infinite_memory_agent/test_infinite_memory_context.py
"""

from __future__ import annotations

import contextvars
from pathlib import Path
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.infinite.journal import InfiniteRunJournal
from vidbyte.agents.infinite.launch import InfinitePair
from vidbyte.agents.infinite.settings import InfiniteMemoryAgentSettings
from vidbyte.agents.infinite.workspace import InfiniteWorkspace
from vidbyte.lib.constants.infinite import (
    INFINITE_HISTORY_MAX_TOKENS,
    INFINITE_ROOT_KEY,
)
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.enums import AgentRuntimeType
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError
from vidbyte.middleware import MessageHistoryCompactionMiddleware
from vidbyte.prompts.catalog import Prompts
from vidbyte.tools.toolsets import InfiniteMemoryAgentTools


class InfiniteMemoryAgent(BaseAgent):
    """A root agent that delegates work to verified subagent pairs and keeps memory in one guarded workspace folder."""

    session_persistence_supported = False

    def __init__(self, settings: InfiniteMemoryAgentSettings) -> None:
        # @intent closed-infinite-construction-surface
        # Only the validated settings object configures this agent, so
        # the runtime, the preset tools, the provider settings, and the
        # permission policy stay owned by this package.
        if not isinstance(settings, InfiniteMemoryAgentSettings):
            raise ConfigurationError(f"InfiniteMemoryAgent requires an InfiniteMemoryAgentSettings instance; got {type(settings).__name__}.", details={"settings": type(settings).__name__})
        self.settings = settings

        # Set up the shared workspace once: the folder, the bookkeeping
        # files, the seeds, and the cap check.
        self.workspace = InfiniteWorkspace(settings.workspace)

        # A resumed run hands its journal to the runtime through this
        # variable, which each call sets and resets for itself.
        self._resuming_var: contextvars.ContextVar[InfiniteRunJournal | None] = contextvars.ContextVar(f"vidbyte_infinite_resuming_{id(self)}", default=None)

        # Build the root: the developer's prompt plus the delegation
        # rules, the preset tools plus the developer's extras, and its
        # own history trim, so old tool results drop out past the cap
        # while the task, the rules, and the map stay.
        rules = Prompts().get(Prompt.INFINITE_MEMORY_ROOT_SYSTEM_PROMPT).format(max_parallel=settings.max_parallel, max_depth=settings.max_depth)
        super().__init__(
            name=settings.name,
            system_prompt=f"{settings.system_prompt}\n\n{rules}",
            runtime=AgentRuntimeType.INFINITE_MEMORY,
            tools=(*InfiniteMemoryAgentTools(Path(settings.root_dir), self.workspace.root, settings.workspace.max_tokens).all(), *settings.tools),
            permission_policy=settings.permission_policy,
            agent_loop_settings=settings.loop,
            middleware=(MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_tokens=INFINITE_HISTORY_MAX_TOKENS),),
            api_key=settings.api_key,
            provider=settings.provider,
            model_name=settings.model_name,
            temperature=settings.temperature,
            timeout_seconds=settings.timeout_seconds,
        )

    def _runtime_extension_kwargs(self) -> dict[str, Any]:
        # Hands the settings, the workspace, and a resumed run's journal
        # to each run-local InfiniteMemoryRuntime.
        return {"settings": self.settings, "workspace": self.workspace, "resuming": self._resuming_var.get()}

    def resume(self, run_id: str | None = None) -> AgentMessage:
        """Continue the newest unfinished run, or the one named, without running its finished pairs again."""
        journal = InfiniteRunJournal.find(self.workspace.root, run_id)
        mark = self._resuming_var.set(journal)
        try:
            return self.run(self._resume_prompt(journal))
        finally:
            self._resuming_var.reset(mark)

    async def aresume(self, run_id: str | None = None) -> AgentMessage:
        """Async resume(): continue the newest unfinished run, or the one named, without running its finished pairs again."""
        journal = InfiniteRunJournal.find(self.workspace.root, run_id)
        mark = self._resuming_var.set(journal)
        try:
            return await self.arun(self._resume_prompt(journal))
        finally:
            self._resuming_var.reset(mark)

    @staticmethod
    def _resume_prompt(journal: InfiniteRunJournal) -> str:
        # @intent a-resumed-root-is-briefed-not-replayed
        # The resumed root starts with a fresh conversation, so it is
        # told the task, one short line per finished pair, and which
        # pairs were cut off; relaunching a finished name replays it.
        interrupted = "\n".join(f"- {name}" for name in journal.interrupted_children(INFINITE_ROOT_KEY)) or "-"
        finished = InfinitePair.finished_lines(journal.finished_children(INFINITE_ROOT_KEY))
        return Prompts().get(Prompt.INFINITE_MEMORY_RESUME_PROMPT).format(task=journal.task, finished=finished, interrupted=interrupted)


__all__ = ["InfiniteMemoryAgent"]
