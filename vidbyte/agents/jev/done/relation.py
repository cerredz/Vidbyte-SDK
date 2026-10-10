"""FILE: vidbyte/agents/jev/done/relation.py

PURPOSE: Implements the opt-in JevRunState policy that retains a record for related requests and replaces it for unrelated requests.
ROLE IN CODEBASE: JevAgent constructs this subclass when RUN_STATE_RELATION is enabled; JevRuntime calls begin() before its main loop and begin_delegated() before an accepted request is sent to a specialist.
ARCHITECTURE NOTE: JevRunState continues to own record generation and done checks; this subclass uses the already-built preflight gate as the relation decision source.
COMMON MODIFICATION PATTERNS: Keep record retention here and pass only explicit record state through JevPreflightGate; do not inspect settings or mutate main-agent history.
KNOWN EDGE CASES: A missing record or explicit unrelated verdict uses the existing typed generation path; related or unavailable verdicts retain the existing record and report it on the fresh response.
RELATED DOCS: docs/design/jev-run-state-relation.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_run_state_relation.py and scripts/test-jev-run-state-relation.py.
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.agents.jev.done.run_state import JevRunState
from vidbyte.agents.jev.gate import JevPreflightGate
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings, JevRuntimeSettings


class JevRunStateRelation(JevRunState):
    """Retain an existing typed run-state record when preflight finds a substantive relationship."""

    def __init__(self, settings: JevAgentSettings, runtime_settings: JevRuntimeSettings, response: JevResponse, preflight: JevPreflightGate) -> None:
        # Holds the same gate JevAgent passes to runtime, so begin() consumes the current run's scored relation.
        # @intent relation-policy-is-fixed-with-the-agent
        # The gate is already validated and constructed once; the subclass does not read runtime settings or add a runtime preset branch.
        super().__init__(settings, runtime_settings, response)
        self.preflight = preflight

    async def begin(self, request: str, prior_user_turns: Sequence[str] = ()) -> None:
        # Clears only the previous handoff and keeps an existing record unless the current gate explicitly rejects it.
        # @intent related-request-preserves-existing-record
        # Done checks must read the request-derived baseline unchanged; merging a related request would silently rewrite that baseline.
        """Retain and report a related record, or use JevRunState's existing replacement generation path."""
        self.handoff = None
        self.review = None
        self.latest_results = ()
        self._observed_extent = {}
        self._evidence_segments.clear()
        self._main_response_cursor = 0
        self._main_call_cursor = 0
        self._main_segment_number = 0
        self._fresh_segment_number = 0
        self.history.clear()
        if self.record is None or self.preflight.run_state_related is False:
            await super().begin(request, prior_user_turns=prior_user_turns)
            return
        self.response.run_state(self.record)

    async def begin_delegated(self, message: str, prior_user_turns: Sequence[str] = ()) -> None:
        # Uses the same retain-or-replace behavior for work the gate routes to a specialist.
        """Apply the relation policy before a selected specialist handles the current message."""
        await self.begin(message, prior_user_turns=prior_user_turns)


__all__ = ["JevRunStateRelation"]
