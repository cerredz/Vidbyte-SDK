"""FILE: vidbyte/agents/browser/response.py

PURPOSE: Defines BrowserResponse, the one writer of a BrowserAgent's BrowserAgentResponse: the run's message and answer, the goal card as it stands, every episode card, every recheck, the rebuild count, the stop reason, the usage rollup, and the sink errors.
ROLE IN CODEBASE: BrowserAgent builds one per agent and reads its state as agent.response (vidbyte/agents/browser/agent.py). The runtime, the episode tool, and the goal card report through its methods, and finished() returns the loop's AgentResult with the usage rollup in its metadata.
ARCHITECTURE NOTE: The same split as JevResponse and JevAgentResponse (vidbyte/agents/jev/response.py): the record lives in vidbyte/lib/dataclasses/browser.py, and this class is its only writer. start() replaces the record, so a record returned for an earlier run is never changed afterwards (spec INV-24).
FUNCTION INVENTORY: start begins a fresh record; goal, episode, recheck, and rebuilt record what happened; finished closes the record and returns the result with its usage rollup.
COMMON MODIFICATION PATTERNS: A new field on BrowserAgentResponse gets one method here, called by the code that decides it.
WHAT NOT TO DO IN THIS FILE: 1. Do not let any other class assign to the record's fields. 2. Do not copy a key or a typed value into the record; the episode recipe is the documented exception (spec EC-31).
KNOWN EDGE CASES: A cancelled or failed run leaves the record as it stood, with the episodes recorded so far and no output, stop reason, or usage. Two overlapping runs on one agent overwrite each other's record (spec EC-21).
RELATED DOCS: docs/spec/browser-agent/spec.md (sections 8.1 D-20 and 8.5); vidbyte/agents/jev/response.py
TESTS: tests/features/browser_agent/test_browser_agent_observability.py and tests/features/browser_agent/test_browser_agent_rebuild.py
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from vidbyte.agents.pricing import UsageRollup
from vidbyte.lib.dataclasses.browser import (
    BrowserAgentResponse,
    BrowserEpisodeResult,
    BrowserGoalCard,
    BrowserRecheckResult,
)
from vidbyte.lib.dataclasses.strategies import AgentResult


class BrowserResponse:
    """The one writer of a BrowserAgent's BrowserAgentResponse."""

    def __init__(self) -> None:
        # An empty record until the first run starts.
        self.state = BrowserAgentResponse()

    def start(self, message: str) -> None:
        """Begin a fresh record for a run of `message`."""
        self.state = BrowserAgentResponse(input=message)

    def goal(self, card: BrowserGoalCard) -> None:
        """Record the goal card as it stands now."""
        self.state.goal = card

    def episode(self, result: BrowserEpisodeResult) -> None:
        """Record one finished episode's card."""
        self.state.episodes.append(result)

    def recheck(self, result: BrowserRecheckResult) -> None:
        """Record one recheck that returned a verdict."""
        self.state.rechecks.append(result)

    def rebuilt(self) -> None:
        """Count one orchestrator context rebuild that removed messages."""
        self.state.rebuilds += 1

    def finished(self, result: AgentResult, usage: UsageRollup, event_errors: Sequence[str]) -> AgentResult:
        """Close the record with the loop's answer, stop reason, usage, and sink errors, and return the result carrying the same rollup."""
        # @intent one-usage-rollup-everywhere
        # result.metadata["usage_rollup"], agent.response.usage, and
        # agent.get_usage() must be the same rollup of every agent of
        # the run, so the settled ledger replaces the loop's own.
        self.state.output = result.output
        self.state.stop_reason = str(result.metadata.get("stop_reason") or "") or None
        self.state.usage = usage
        self.state.event_errors = list(event_errors)
        return replace(result, metadata={**dict(result.metadata), "usage_rollup": usage})


__all__ = ["BrowserResponse"]
