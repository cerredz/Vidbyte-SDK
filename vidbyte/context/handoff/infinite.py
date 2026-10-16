"""FILE: vidbyte/context/handoff/infinite.py

PURPOSE: Defines InfiniteHandoff, the handoff of one InfiniteMemory run: a Handoff with nine fixed sections (Outcome, Work done, Decisions, Facts, Lessons, Open questions, Files, Unverified or failed work, How to continue), the wording of every line in them, and six renderers that turn the run's journal, entries, and notes into those section bodies without a model.
ROLE IN CODEBASE: Built only by InfiniteMemoryAgent.run_handoff (vidbyte/agents/infinite/agent.py), which reads the journal and the workspace, calls the renderers here, cuts each body to its cap, and saves to_context_text() as .runs/<run_id>.handoff.md. Exported from vidbyte.context.handoff, vidbyte.context, vidbyte.agents.infinite, vidbyte.agents, and vidbyte, beside the other prebuilt handoffs (engineering.py, research.py, minimal.py).
ARCHITECTURE NOTE: A Handoff subclass that keeps the base keyword constructor, so fill() returns another InfiniteHandoff and the object works anywhere a Handoff does. The wording lives here as class attributes, not in the constants module, because it is developer-facing document text, not a cap or a model-facing prompt. Each renderer is a static method that formats its lines with that wording and hands them to _lines, which collapses each line, cuts it to INFINITE_HANDOFF_LINE_MAX_CHARS with the infinite marker, and joins them, or returns EMPTY when there are none. This module imports only the base Handoff and vidbyte.lib, never vidbyte.agents.
FUNCTION INVENTORY: default_sections returns the nine titles with a one-line description each; outcome, work_done, entries, files, unverified, and how_to_continue render one section body each; _lines collapses, cuts, and joins list lines.
COMMON MODIFICATION PATTERNS: A new section adds its title and description to default_sections in contract order, one renderer here, and one line in InfiniteMemoryAgent.run_handoff that calls it; its cap stays INFINITE_HANDOFF_SECTION_MAX_CHARS unless the spec's chunk arithmetic changes. Changing a sentence changes its class attribute only.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte.agents; the agent passes plain records in. 2. Do not call a model or read a file here; the handoff must be deterministic. 3. Do not leave a list line multi-line or longer than INFINITE_HANDOFF_LINE_MAX_CHARS. 4. Do not change the base constructor's keywords; fill() rebuilds this class through them.
KNOWN EDGE CASES: A card with an empty summary or review renders without a trailing space, because every list line is collapsed. A finished run without a recorded answer (a journal written before answers were stored) renders NO_ANSWER in place of the answer. An unfinished run's Outcome is UNFINISHED, with no stop reason. A note without a description in files.jsonl renders INFINITE_NO_DESCRIPTION.
RELATED DOCS: docs/spec/infinite-memory-events/spec.md (sections 6.1 INV-22 to INV-24 and INV-37, 8.5, and 9.1); vidbyte/agents/infinite/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_handoff.py, tests/features/infinite_memory_agent/test_infinite_memory_events_lifecycle.py, and tests/features/infinite_memory_agent/test_infinite_memory_events_pairs.py
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from vidbyte.context.handoff.base import Handoff
from vidbyte.lib.constants.infinite import (
    INFINITE_HANDOFF_LINE_MAX_CHARS,
    INFINITE_NO_DESCRIPTION,
    INFINITE_TRUNCATION_MARKER,
)
from vidbyte.lib.dataclasses.infinite import InfiniteEntry, InfiniteResultCard
from vidbyte.lib.enums.infinite import (
    InfiniteEntryKind,
    InfiniteResultStatus,
    InfiniteVerdict,
)
from vidbyte.lib.outputs.text import OutputText


class InfiniteHandoff(Handoff):
    """The deterministic handoff of one InfiniteMemory run: nine fixed sections built from its journal, entries, and notes."""

    DEFAULT_TITLE = "InfiniteMemory handoff"
    TITLE = "InfiniteMemory handoff: run {run_id}"
    EMPTY = "(none)"
    OUTCOME = "Task: {task}\nStop reason: {stop_reason}\n\n{answer}"
    UNFINISHED = "Task: {task}\nThis run has not finished, so it has no final answer yet."
    NO_ANSWER = "(no final answer was recorded for this run)"
    CARD_LINE = "- {key}: {status}, verdict {verdict}. {text}"
    INTERRUPTED_LINE = "- {key}: started but never finished; it runs again on resume"
    ENTRY_LINE = "- #{id} {text}"
    FILE_LINE = "- {path}: {description}"
    RESUME = 'This run has not finished. Continue it with agent.resume("{run_id}"): finished tasks are reused and interrupted ones run again.'
    NEW_RUN = "This run finished. Start a new run on the same workspace with agent.run(task); its memory entries and notes carry over."

    def default_sections(self) -> dict[str, str]:
        """Return the nine section titles in their fixed order, each with a one-line description of what it holds."""
        return {
            "Outcome": "The task, how the run stopped, and the root's final answer, or a note that the run has not finished.",
            "Work done": "One line per finished subagent pair at every depth, in finishing order, with its status, verdict, and summary.",
            "Decisions": "The decision entries this run committed to memory and that are still live, in id order.",
            "Facts": "The fact entries this run committed to memory and that are still live, in id order.",
            "Lessons": "The lesson entries this run committed to memory and that are still live, in id order.",
            "Open questions": "The open-question entries this run committed to memory and that are still live, in id order.",
            "Files": "The notes this run created, then the files its pairs and its root wrote, each once with its description, then its pointer entries.",
            "Unverified or failed work": "Pairs that failed or whose work no verifier passed, with their reviews, then pairs that started and never finished.",
            "How to continue": "How to resume this run if it has not finished, or how to start the next run on the same workspace.",
        }

    @staticmethod
    def outcome(task: str, stop_reason: str | None, answer: str | None) -> str:
        """Return the Outcome body: the task, the stop reason, and the answer, or the not-finished statement when the run has no stop reason."""
        if stop_reason is None:
            return InfiniteHandoff.UNFINISHED.format(task=task)
        return InfiniteHandoff.OUTCOME.format(task=task, stop_reason=stop_reason, answer=InfiniteHandoff.NO_ANSWER if answer is None else answer)

    @staticmethod
    def work_done(cards: tuple[InfiniteResultCard, ...]) -> str:
        """Return the Work done body: one line per finished card, in the order given, with its summary."""
        return InfiniteHandoff._lines(InfiniteHandoff.CARD_LINE.format(key=card.key, status=card.status.value, verdict=card.verdict.value, text=card.summary) for card in cards)

    @staticmethod
    def entries(entries: tuple[InfiniteEntry, ...], kind: InfiniteEntryKind) -> str:
        """Return one kind's section body: one line per entry of that kind, in the order given."""
        return InfiniteHandoff._lines(InfiniteHandoff.ENTRY_LINE.format(id=entry.id, text=entry.draft.text) for entry in entries if entry.draft.kind is kind)

    @staticmethod
    def files(paths: tuple[str, ...], descriptions: Mapping[str, str], pointers: tuple[InfiniteEntry, ...]) -> str:
        """Return the Files body: one line per path with its description, then one line per pointer entry."""
        listed = (InfiniteHandoff.FILE_LINE.format(path=path, description=descriptions.get(path, INFINITE_NO_DESCRIPTION)) for path in paths)
        return InfiniteHandoff._lines((*listed, *(InfiniteHandoff.ENTRY_LINE.format(id=entry.id, text=entry.draft.text) for entry in pointers)))

    @staticmethod
    def unverified(cards: tuple[InfiniteResultCard, ...], interrupted: tuple[str, ...]) -> str:
        """Return the Unverified or failed work body: each failed or unpassed card with its review, then each interrupted pair key."""
        # A card needs a second look when its pair failed, or when its
        # verifier failed the work or never gave a verdict.
        flagged = (card for card in cards if card.status is InfiniteResultStatus.FAILED or card.verdict in (InfiniteVerdict.FAILED, InfiniteVerdict.UNCHECKED))
        lines = (InfiniteHandoff.CARD_LINE.format(key=card.key, status=card.status.value, verdict=card.verdict.value, text=card.review) for card in flagged)
        return InfiniteHandoff._lines((*lines, *(InfiniteHandoff.INTERRUPTED_LINE.format(key=key) for key in interrupted)))

    @staticmethod
    def how_to_continue(run_id: str, finished: bool) -> str:
        """Return the How to continue body: the new-run advice for a finished run, or the resume call for an unfinished one."""
        return InfiniteHandoff.NEW_RUN if finished else InfiniteHandoff.RESUME.format(run_id=run_id)

    @staticmethod
    def _lines(lines: Iterable[str]) -> str:
        # @intent every-handoff-line-is-one-bounded-line
        # A model's summary or review can hold line breaks and any
        # length, so each line is collapsed to one line and cut to its
        # cap with the marker the events use; no lines means EMPTY.
        shown = [OutputText.truncate(" ".join(line.split()), INFINITE_HANDOFF_LINE_MAX_CHARS, marker=INFINITE_TRUNCATION_MARKER) for line in lines]
        return "\n".join(shown) or InfiniteHandoff.EMPTY


__all__ = ["InfiniteHandoff"]
