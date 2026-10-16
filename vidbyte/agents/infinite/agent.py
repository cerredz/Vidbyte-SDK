"""FILE: vidbyte/agents/infinite/agent.py

PURPOSE: Exposes InfiniteMemoryAgent, a root agent that ruthlessly delegates work to generator and verifier subagent pairs and keeps its memory in one guarded workspace folder, built from one validated InfiniteMemoryAgentSettings; its resume/aresume, which continue an interrupted run from its journal; and run_handoff, which builds a run's nine-section InfiniteHandoff from its journal and the workspace without a model and saves it beside the journal.
ROLE IN CODEBASE: Maps the settings into BaseAgent with AgentRuntimeType.INFINITE_MEMORY, which RuntimeRegistry resolves to InfiniteMemoryRuntime (runtime.py). Builds the InfiniteWorkspace (workspace.py) once, and passes it, the settings, and a resumed run's journal (journal.py) to each run-local runtime through _runtime_extension_kwargs.
ARCHITECTURE NOTE: A closed construction surface like JevAgent: callers pass only the settings object, and the runtime, the preset tools, and the history trim are fixed here. The root holds bash, grep, and read_lines from InfiniteMemoryAgentTools plus the developer's extras; the runtime adds the run-bound tools for each run. Durable sessions are not supported, because a restored agent would be a plain BaseAgent that the runtime refuses; the run journal is the resume path instead.
FUNCTION INVENTORY: __init__ and run_handoff are the narrated main functions; _runtime_extension_kwargs hands the run-time objects to the runtime; resume and aresume find an unfinished run and continue it; _resume_prompt writes the resumed root's first message; _section makes one handoff body UTF-8 encodable and cuts it to its cap.
COMMON MODIFICATION PATTERNS: A new agent-level capability is a validated field on InfiniteMemoryAgentSettings (settings.py) used here or passed to the runtime through _runtime_extension_kwargs.
WHAT NOT TO DO IN THIS FILE: 1. Do not accept BaseAgent keyword arguments; everything comes from the settings. 2. Do not start a run in resume before the journal checks pass. 3. Do not share one middleware instance between agents; each agent builds its own.
KNOWN EDGE CASES: Building the agent creates the workspace folder and copies the seeds, and refuses a workspace already over a cap. A resumed root starts with a fresh conversation: its first message holds the original task, one short line per finished root-level pair, and the names of interrupted ones. resume() cannot run inside an active event loop; use aresume() there. run_handoff with no run id takes the newest run in any state, so a run still going in another process gets an unfinished handoff of what is on disk now (spec EC-18). A malformed entries.jsonl line or a hand-edited run_finished record raises before the handoff file is written (EC-19, EC-20). A journal written before answers were stored gives the no-answer placeholder and no root files (EC-21); a resumed run lists only the finishing session's root files (EC-22). Two calls for one run each swap in the same whole file (EC-23). A lone surrogate becomes "?" in the handoff only (EC-17), and an Outcome over 239,000 characters or any other section over 15,900 is cut with the marker, while the journal keeps the full answer (EC-24, EC-33).
RELATED DOCS: docs/spec/infinite-memory-agent/spec.md (sections 4, 6.1 INV-1, INV-2, INV-23, INV-27, INV-28, and 8.5); docs/spec/infinite-memory-events/spec.md (sections 6.1 INV-22 to INV-24 and INV-37, and 9.2); vidbyte/agents/infinite/README.md; vidbyte/agents/jev/agent.py (the pattern this follows)
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_contract.py, tests/features/infinite_memory_agent/test_infinite_memory_acceptance.py, tests/features/infinite_memory_agent/test_infinite_memory_resume.py, tests/features/infinite_memory_agent/test_infinite_memory_context.py, and tests/features/infinite_memory_agent/test_infinite_memory_handoff.py
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
from vidbyte.context.handoff.infinite import InfiniteHandoff
from vidbyte.lib.constants.infinite import (
    INFINITE_HANDOFF_OUTCOME_MAX_CHARS,
    INFINITE_HANDOFF_SECTION_MAX_CHARS,
    INFINITE_HANDOFF_SUFFIX,
    INFINITE_HISTORY_MAX_TOKENS,
    INFINITE_ROOT_DEPTH,
    INFINITE_ROOT_KEY,
    INFINITE_TRUNCATION_MARKER,
)
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.enums import AgentRuntimeType
from vidbyte.lib.enums.infinite import InfiniteEntryKind
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.outputs.text import OutputText
from vidbyte.middleware import (
    DelegationLimitsMiddleware,
    MessageHistoryCompactionMiddleware,
)
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
        # rules, the preset tools plus the developer's extras, its own
        # history trim, so old tool results drop out past the cap while
        # the task, the rules, and the map stay, and the delegation caps.
        # @intent limits-in-code-behavior-in-the-prompt
        # The rules describe how to delegate; the depth and batch caps
        # are enforced by DelegationLimitsMiddleware, so the prompt holds
        # no numbers the code could contradict.
        rules = Prompts().get(Prompt.INFINITE_MEMORY_ROOT_SYSTEM_PROMPT)
        super().__init__(
            name=settings.name,
            system_prompt=f"{settings.system_prompt}\n\n{rules}",
            runtime=AgentRuntimeType.INFINITE_MEMORY,
            tools=(*InfiniteMemoryAgentTools(Path(settings.root_dir), self.workspace.root, settings.workspace.max_tokens).all(), *settings.tools),
            permission_policy=settings.permission_policy,
            agent_loop_settings=settings.loop,
            middleware=(MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_tokens=INFINITE_HISTORY_MAX_TOKENS), DelegationLimitsMiddleware(settings.delegation_limits, depth=INFINITE_ROOT_DEPTH)),
            api_keys=settings.api_keys,
            model_mode=settings.model_mode,
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

    def run_handoff(self, run_id: str | None = None) -> InfiniteHandoff:
        """Build the handoff of the named run, or of the newest run in any state, save it as .runs/<run_id>.handoff.md, and return it; no model is called."""
        # Load the run in any state, since a stopped run needs a handoff
        # too; its id is checked against the run-id pattern before it
        # becomes a path.
        workspace = self.workspace
        journal = InfiniteRunJournal.find(workspace.root, run_id, unfinished=False)

        # Read this run's live entries and the notes' descriptions; a
        # malformed entries line raises here, before anything is saved.
        entries = workspace.run_entries(journal.run_id)
        described = {workspace.relative(path): text for path, text in workspace.descriptions().items()}
        created = tuple(workspace.descriptions(journal.run_id))

        # @intent one-note-is-listed-once-by-its-relative-path
        # List the notes this run created, then the files on its cards,
        # then the files the root wrote, each once by its
        # workspace-relative path, however the model spelled it.
        cards = journal.cards
        paths = tuple(dict.fromkeys(workspace.relative(path) for path in (*created, *(path for card in cards for path in card.files), *journal.root_files)))
        pointers = tuple(entry for entry in entries if entry.draft.kind is InfiniteEntryKind.POINTER)

        # Render the nine sections in their fixed order: the outcome,
        # the cards, the four kinds of entries, the files, the work that
        # needs a second look, and how to go on.
        outcome, *titles = InfiniteHandoff().default_sections()
        bodies = (
            InfiniteHandoff.work_done(cards),
            *(InfiniteHandoff.entries(entries, kind) for kind in (InfiniteEntryKind.DECISION, InfiniteEntryKind.FACT, InfiniteEntryKind.LESSON, InfiniteEntryKind.OPEN_QUESTION)),
            InfiniteHandoff.files(paths, described, pointers),
            InfiniteHandoff.unverified(cards, journal.interrupted),
            InfiniteHandoff.how_to_continue(journal.run_id, journal.stop_reason is not None),
        )
        # @intent the-handoff-fits-the-backends-sections
        # The Outcome gets the most room, because the final answer
        # matters most; every other section is cut to its own cap, so
        # the saved text always fits the backend's handoff sections.
        sections = {outcome: self._section(InfiniteHandoff.outcome(journal.task, journal.stop_reason, journal.answer), INFINITE_HANDOFF_OUTCOME_MAX_CHARS)}
        sections.update((title, self._section(body, INFINITE_HANDOFF_SECTION_MAX_CHARS)) for title, body in zip(titles, bodies, strict=True))
        handoff = InfiniteHandoff(sections=sections, title=InfiniteHandoff.TITLE.format(run_id=journal.run_id), metadata={"filled": True, "run_id": journal.run_id})

        # @intent the-handoff-file-is-whole-and-identical-everywhere
        # Save the text beside the journal through an atomic swap, with
        # \n line ends on every platform, so a reader never sees half a
        # file and its bytes equal to_context_text().
        target = journal.path.with_name(f"{journal.run_id}{INFINITE_HANDOFF_SUFFIX}")
        workspace.backend.write_text(target, handoff.to_context_text(), encoding="utf-8", create_parents=True, newline="\n", atomic=True)
        return handoff

    @staticmethod
    def _section(body: str, cap: int) -> str:
        # One handoff body, with a lone surrogate made "?" so the file
        # write cannot fail, cut to its cap with the infinite marker.
        return OutputText.truncate(body.encode("utf-8", errors="replace").decode("utf-8"), cap, marker=INFINITE_TRUNCATION_MARKER)

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
