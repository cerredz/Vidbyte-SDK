"""FILE: vidbyte/agents/jev/brief/keeper.py

PURPOSE: Implements JevRunBriefKeeper, which owns one run's brief: it reads the run's facts between iterations, decides when a refresh is due, gives the writer only the events after the last verified brief, and replaces the brief only with what verification keeps.
ROLE IN CODEBASE: The single entry point of the run brief. A caller builds one keeper per JevAgent, calls `begin` at the start of each run and `refresh_if_due` between the main agent's iterations, and reads `brief`, `facts`, and `last_update`.
ARCHITECTURE NOTE: Cadence is code policy over exact facts: never sooner than `min_gap` iterations after the last attempt, a first brief once the run reaches JEV_RUN_BRIEF_FIRST_ITERATION, then every `every_iterations`, or early on an error streak, a repeated identical call, or token growth. A failed or rejected attempt keeps the previous brief and its event pointer, so the next attempt re-reads the same events.
COMMON MODIFICATION PATTERNS: Tune triggers through the JEV_RUN_BRIEF_* constants and cadence through JevRunBriefSettings; add new facts in JevRunFactsReader and new verification rules in JevRunBriefVerifier.
KNOWN EDGE CASES: Like the JevAgent that owns it, one keeper serves one run at a time. An attempt with no new events calls no model. Attempts, not only successes, reset the gap, so a writer outage is retried at the `min_gap` pace rather than at every iteration.
RELATED DOCS: docs/design/jev-run-brief.md.
TESTS: tests/test_jev_run_brief.py.
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.agents.jev.brief.events import JevRunBriefEvents
from vidbyte.agents.jev.brief.facts import JevRunFactsReader
from vidbyte.agents.jev.brief.verifier import JevRunBriefVerifier
from vidbyte.agents.jev.brief.writer import JevRunBriefWriter
from vidbyte.agents.jev.settings import JevAgentSettings, JevRunBriefSettings
from vidbyte.lib.constants.jev import (
    JEV_EVENT_LOG_FIRST_ID,
    JEV_RUN_BRIEF_ERROR_STREAK_TRIGGER,
    JEV_RUN_BRIEF_FIRST_ITERATION,
    JEV_RUN_BRIEF_REPEAT_TRIGGER,
    JEV_RUN_BRIEF_TOKEN_GROWTH_TRIGGER,
)
from vidbyte.lib.dataclasses.jev import (
    JevRunBrief,
    JevRunBriefUpdate,
    JevRunBriefVerification,
    JevRunBriefWindow,
    JevRunFacts,
)
from vidbyte.lib.dataclasses.tools import ToolCallContext
from vidbyte.lib.enums.jev import JevRunBriefUpdateStatus


class JevRunBriefKeeper:
    """Owns one run's brief: when it refreshes, what the writer reads, and which of the writer's claims survive."""

    def __init__(self, settings: JevAgentSettings, brief: JevRunBriefSettings) -> None:
        # Builds the writer once, at construction, and starts with an empty run.
        self.settings = brief
        self.writer = JevRunBriefWriter(settings, brief)
        self.begin("")

    def begin(self, request: str) -> None:
        """Start a new run: forget the previous run's brief, facts, and attempts, and remember the user's request."""
        self.request = request
        self.brief: JevRunBrief | None = None
        self.facts: JevRunFacts | None = None
        self.last_update: JevRunBriefUpdate | None = None
        self._through_event = JEV_EVENT_LOG_FIRST_ID
        self._attempted_at = 0
        self._tokens_at_attempt: int | None = None

    async def refresh_if_due(self, responses: Sequence[str], calls: Sequence[ToolCallContext], *, tokens_used: int | None) -> JevRunBriefUpdate | None:
        """Read the run's facts and refresh the brief when a refresh is due; return the attempt, or None when none ran."""
        facts = self.read_facts(responses, calls, tokens_used=tokens_used)
        if not self.due(facts):
            return None
        return await self._refresh(responses, calls, facts)

    def read_facts(self, responses: Sequence[str], calls: Sequence[ToolCallContext], *, tokens_used: int | None) -> JevRunFacts:
        """Return and keep the run's exact facts, counted since the last refresh attempt."""
        self.facts = JevRunFactsReader.read(responses, calls, tokens_used=tokens_used, since_iteration=self._attempted_at, tokens_at_refresh=self._tokens_at_attempt)
        return self.facts

    def due(self, facts: JevRunFacts) -> bool:
        """Return whether these facts call for a refresh under the brief's cadence and early triggers."""
        if facts.iterations_since_refresh < self.settings.min_gap:
            return False
        if self.brief is None and facts.iteration >= JEV_RUN_BRIEF_FIRST_ITERATION:
            # @intent the-opening-plan-is-captured-early
            # Agents state their plan in the first few responses; waiting a full cadence for the first brief would
            # leave the checkpoint blind to that plan for most of a short run.
            return True
        return facts.iterations_since_refresh >= self.settings.every_iterations or self._triggered(facts)

    async def _refresh(self, responses: Sequence[str], calls: Sequence[ToolCallContext], facts: JevRunFacts) -> JevRunBriefUpdate | None:
        # Shows the writer the events after the last verified brief, verifies its reply, and keeps the brief only when verification does.
        events = JevRunBriefEvents.from_run(self.request, responses, calls)
        window = events.window(after=self._through_event)
        self._attempted_at, self._tokens_at_attempt = facts.iteration, facts.tokens_used
        if window is None:
            return None
        payload = await self.writer.write(self.request, self.brief, window)
        verification = None if payload is None else JevRunBriefVerifier(events).verify(payload, iteration=facts.iteration, through_event=window.last_event)
        if verification is not None and verification.brief is not None:
            self.brief, self._through_event = verification.brief, window.last_event
        self.last_update = self._update(facts, window, verification)
        return self.last_update

    def _update(self, facts: JevRunFacts, window: JevRunBriefWindow, verification: JevRunBriefVerification | None) -> JevRunBriefUpdate:
        # Records what the attempt did: unavailable without a reply, rejected without a verified brief, updated otherwise.
        if verification is None:
            status, kept, dropped = JevRunBriefUpdateStatus.UNAVAILABLE, 0, 0
        else:
            status = JevRunBriefUpdateStatus.REJECTED if verification.brief is None else JevRunBriefUpdateStatus.UPDATED
            kept, dropped = verification.kept, verification.dropped
        return JevRunBriefUpdate(
            status=status,
            iteration=facts.iteration,
            first_event=window.first_event,
            last_event=window.last_event,
            kept=kept,
            dropped=dropped,
            usage=self.writer.get_usage(),
        )

    @staticmethod
    def _triggered(facts: JevRunFacts) -> bool:
        # Returns whether new activity since the last attempt warrants an early refresh.
        growth = facts.token_growth()
        return (
            facts.error_streak >= JEV_RUN_BRIEF_ERROR_STREAK_TRIGGER
            or facts.repeats_since_refresh >= JEV_RUN_BRIEF_REPEAT_TRIGGER
            or (growth is not None and growth >= JEV_RUN_BRIEF_TOKEN_GROWTH_TRIGGER)
        )


__all__ = ["JevRunBriefKeeper"]
