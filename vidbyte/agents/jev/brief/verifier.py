"""FILE: vidbyte/agents/jev/brief/verifier.py

PURPOSE: Implements JevRunBriefVerifier, which turns the writer's reply into a JevRunBrief holding only what the run proves: every quote must appear in the event it cites, entries left without evidence are dropped, and a reply with too many unverifiable quotes is rejected.
ROLE IN CODEBASE: JevRunBriefKeeper builds one verifier per refresh attempt over that attempt's JevRunBriefEvents and keeps the previous brief whenever verification returns no brief.
ARCHITECTURE NOTE: The writer may be a cheap model, so nothing it writes is trusted as is. Caps are applied by trimming in the writer's own order rather than by rejecting the reply, so one extra item never discards a whole refresh, while the share of unverifiable quotes decides whether the writer was reliable this time.
COMMON MODIFICATION PATTERNS: Change the rejection share through JEV_RUN_BRIEF_MAX_DROP_SHARE and the caps through the JEV_RUN_BRIEF_* constants; keep new evidence rules here rather than in the writer's prompt alone.
KNOWN EDGE CASES: Only quotes inside the caps are checked, so entries trimmed away never count against the writer. A quote longer than its cap is cut to the cap, which keeps it verbatim. Duplicate item or approach ids keep their first entry. A reply with no quotes at all is accepted, since an early run may give the writer nothing to quote.
RELATED DOCS: docs/design/jev-run-brief.md.
TESTS: tests/test_jev_run_brief.py.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TypeVar

from vidbyte.agents.jev.brief.events import JevRunBriefEvents
from vidbyte.lib.constants.jev import (
    JEV_RUN_BRIEF_APPROACHES_MAX,
    JEV_RUN_BRIEF_EVIDENCE_MAX,
    JEV_RUN_BRIEF_FAILURES_MAX,
    JEV_RUN_BRIEF_ITEMS_MAX,
    JEV_RUN_BRIEF_MAX_DROP_SHARE,
    JEV_RUN_BRIEF_NEXT_STEPS_MAX,
    JEV_RUN_BRIEF_QUOTE_MAX_CHARS,
    JEV_RUN_BRIEF_TEXT_MAX_CHARS,
)
from vidbyte.lib.dataclasses.jev import (
    JevRunBrief,
    JevRunBriefApproach,
    JevRunBriefApproachPayload,
    JevRunBriefItem,
    JevRunBriefItemPayload,
    JevRunBriefPayload,
    JevRunBriefQuote,
    JevRunBriefQuotePayload,
    JevRunBriefVerification,
)
from vidbyte.lib.errors import ConfigurationError

_Entry = TypeVar("_Entry", JevRunBriefItem, JevRunBriefApproach)


class JevRunBriefVerifier:
    """Keeps only what the writer can prove: every quote must appear in the run event it cites."""

    def __init__(self, events: JevRunBriefEvents) -> None:
        # Checks quotes against one refresh attempt's events and counts how many it checked and how many held.
        self.events = events
        self.checked = 0
        self.verified = 0

    def verify(self, payload: JevRunBriefPayload, *, iteration: int, through_event: int) -> JevRunBriefVerification:
        """Return the brief built from the reply's verified quotes, or no brief when the reply is unreliable or invalid."""
        goal = self._text(payload.goal)
        goal_evidence = self._quotes(payload.goal_evidence, JEV_RUN_BRIEF_EVIDENCE_MAX)
        current_step = self._quote(payload.current_step)
        next_steps = self._quotes(payload.next_steps, JEV_RUN_BRIEF_NEXT_STEPS_MAX)
        items = self._unique(self._item(item) for item in payload.items[:JEV_RUN_BRIEF_ITEMS_MAX])
        approaches = self._unique(self._approach(approach) for approach in payload.approaches[:JEV_RUN_BRIEF_APPROACHES_MAX])
        open_failures = self._quotes(payload.open_failures, JEV_RUN_BRIEF_FAILURES_MAX)
        dropped = self.checked - self.verified
        if not goal or (self.checked and dropped / self.checked > JEV_RUN_BRIEF_MAX_DROP_SHARE):
            # @intent an-unreliable-reply-changes-nothing
            # When most of what the writer quoted cannot be found, the parts that happen to verify are not a
            # trustworthy picture either, so the whole reply is set aside and the previous brief stays.
            return JevRunBriefVerification(brief=None, kept=self.verified, dropped=dropped)
        try:
            brief = JevRunBrief(
                goal=goal,
                iteration=iteration,
                through_event=through_event,
                goal_evidence=goal_evidence,
                current_step=current_step,
                next_steps=next_steps,
                items=items,
                approaches=approaches,
                open_failures=open_failures,
            )
        except ConfigurationError:
            return JevRunBriefVerification(brief=None, kept=self.verified, dropped=dropped)
        return JevRunBriefVerification(brief=brief, kept=self.verified, dropped=dropped)

    def _quote(self, payload: JevRunBriefQuotePayload | None) -> JevRunBriefQuote | None:
        # Returns the quote, cut to its cap, when the cited event contains it; counts every quote it checks.
        if payload is None:
            return None
        self.checked += 1
        text = payload.quote[:JEV_RUN_BRIEF_QUOTE_MAX_CHARS].strip()
        if not self.events.contains(payload.event, text):
            return None
        self.verified += 1
        return JevRunBriefQuote(event=payload.event, quote=text)

    def _quotes(self, payloads: Sequence[JevRunBriefQuotePayload], cap: int) -> tuple[JevRunBriefQuote, ...]:
        # Verifies the first `cap` quotes in the writer's order and keeps those that hold.
        return tuple(quote for quote in (self._quote(payload) for payload in payloads[:cap]) if quote is not None)

    def _item(self, payload: JevRunBriefItemPayload) -> JevRunBriefItem | None:
        # Keeps an item only when its name and group are non-blank and at least one quote shows it.
        evidence = self._quotes(payload.evidence, JEV_RUN_BRIEF_EVIDENCE_MAX)
        name, group = self._text(payload.name), self._text(payload.group)
        if not evidence or not name or not group:
            return None
        return JevRunBriefItem(id=payload.id, name=name, group=group, status=payload.status, evidence=evidence)

    def _approach(self, payload: JevRunBriefApproachPayload) -> JevRunBriefApproach | None:
        # Keeps an approach only when its target and actions are non-blank and at least one quote shows it.
        evidence = self._quotes(payload.evidence, JEV_RUN_BRIEF_EVIDENCE_MAX)
        target, approach = self._text(payload.target), self._text(payload.approach)
        if not evidence or not target or not approach:
            return None
        return JevRunBriefApproach(id=payload.id, target=target, approach=approach, outcome=payload.outcome, evidence=evidence)

    @staticmethod
    def _unique(entries: Iterable[_Entry | None]) -> tuple[_Entry, ...]:
        # Keeps the first entry for each id and drops entries that did not survive verification.
        kept: dict[str, _Entry] = {}
        for entry in entries:
            if entry is not None and entry.id not in kept:
                kept[entry.id] = entry
        return tuple(kept.values())

    @staticmethod
    def _text(value: str) -> str:
        # Cuts a model-written phrase to the brief's text cap without leaving edge whitespace.
        return value.strip()[:JEV_RUN_BRIEF_TEXT_MAX_CHARS].strip()


__all__ = ["JevRunBriefVerifier"]
