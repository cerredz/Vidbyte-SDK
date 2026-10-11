"""FILE: vidbyte/agents/jev/brief/keeper.py

PURPOSE: Owns one run's aggregate brief, simple refresh cadence, and event pointer.
ROLE IN CODEBASE: A caller begins a run, calls `refresh_if_due` between main-agent iterations, and reads the current `brief`.
ARCHITECTURE NOTE: The first capture is due at iteration three; later captures are due after `every_iterations` new iterations. A verified delta, including an empty one, advances the pointer. Rejected or unavailable updates preserve the brief and pointer.
COMMON MODIFICATION PATTERNS: Update cadence and state together; a failed writer attempt must leave the verified brief and pointer unchanged.
KNOWN EDGE CASES: A failed attempt waits for the next cadence interval and then rereads the same fresh events.
TESTS: tests/test_jev_run_brief.py.
RELATED DOCS: skills/jev-agent/SKILL.md and vidbyte/agents/jev/README.md.
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.agents.jev.brief.writer import JevRunBriefWriter
from vidbyte.agents.jev.settings import JevAgentSettings, JevRunBriefSettings
from vidbyte.lib.constants.jev import (
    JEV_EVENT_LOG_FIRST_ID,
    JEV_RUN_BRIEF_FIRST_ITERATION,
)
from vidbyte.lib.dataclasses.jev import JevRunBrief, JevRunBriefVerification
from vidbyte.lib.dataclasses.tools import ToolCallContext


class JevRunBriefKeeper:
    """Owns the current brief and decides when its writer gets a fresh event window."""

    def __init__(self, settings: JevAgentSettings, brief: JevRunBriefSettings) -> None:
        self.settings = brief
        self.writer = JevRunBriefWriter(settings, brief)
        self.begin("")

    def begin(self, request: str) -> None:
        """Start a run with its original request and an empty brief."""
        # @intent run-start-resets-memory
        # A new task must not inherit notes, event progress, or cadence from a previous task.
        self.request = request
        self.brief: JevRunBrief | None = None
        self.last_update: JevRunBriefVerification | None = None
        self._through_event = JEV_EVENT_LOG_FIRST_ID
        self._last_attempt_iteration: int | None = None

    def due(self, iteration: int) -> bool:
        """Return whether this iteration reaches the first-capture or regular cadence boundary."""
        # @intent fixed-brief-cadence
        # The first brief is captured early; later work waits for a stable number of new iterations.
        if self._last_attempt_iteration is None:
            return self.brief is None and iteration >= JEV_RUN_BRIEF_FIRST_ITERATION
        return iteration - self._last_attempt_iteration >= self.settings.every_iterations

    async def refresh_if_due(
        self,
        responses: Sequence[str],
        calls: Sequence[ToolCallContext],
    ) -> JevRunBriefVerification | None:
        """Refresh the brief when due; keep the prior brief and pointer unless verification succeeds."""
        # @intent failed-refresh-keeps-previous-pointer
        # Rejected and unavailable deltas must not discard a verified brief or skip unseen events.
        iteration = len(responses)
        if not self.due(iteration):
            return None
        window = self.writer.window(self.request, responses, calls, after_event=self._through_event)
        if window is None:
            return None

        self._last_attempt_iteration = iteration
        verification = await self.writer.write(self.request, self.brief, window, iteration=iteration)
        self.last_update = verification
        if verification is not None and verification.brief is not None:
            self.brief = verification.brief
            self._through_event = verification.brief.through_event
        return verification


__all__ = ["JevRunBriefKeeper"]
