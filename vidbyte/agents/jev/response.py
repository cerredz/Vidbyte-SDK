"""FILE: vidbyte/agents/jev/response.py

PURPOSE: Implements JevResponse, the one writer of a JevAgent's JevAgentResponse: every opinionated feature reports what it decided through a method here instead of through result metadata.
ROLE IN CODEBASE: JevAgent builds one instance and exposes its record as `JevAgent.response`; JevPreflight writes preset outcomes and clarifications through it, and JevRuntime asks it for the result to return.
ARCHITECTURE NOTE: The record type lives in vidbyte/lib/dataclasses/jev.py; this class only owns how the record changes during a run, so a new feature adds one method here and one field there.
COMMON MODIFICATION PATTERNS: Add a method named for the event a feature reports (for example needs_clarification), write the matching JevAgentResponse field, and call it from the feature.
KNOWN EDGE CASES: start() replaces the record, so a caller holding the previous run's record keeps it unchanged; like the JevAgent that owns it, one instance serves one run at a time.
RELATED DOCS: docs/design/jev-preflight-clarity.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_preflight.py, tests/test_jev_tool_selector.py, and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.constants.jev import JEV_PREFLIGHT_STRATEGY_NAME
from vidbyte.lib.dataclasses.jev import (
    JevAgentResponse,
    JevClarification,
    JevPresetResult,
    JevToolSelection,
)
from vidbyte.lib.dataclasses.strategies import AgentResult


class JevResponse:
    """Writes what JevAgent's opinionated features decide into the JevAgentResponse the user reads after a run."""

    def __init__(self) -> None:
        # Starts with an empty record so JevAgent.response is readable before the first run.
        self.state = JevAgentResponse()

    def start(self, message: str) -> None:
        """Begin a run: drop the previous run's record and remember the user's message."""
        self.state = JevAgentResponse(input=message)

    def preset(self, outcome: JevPresetResult | JevToolSelection) -> None:
        """Record what one enabled preflight preset decided."""
        self.state.results[outcome.preset] = outcome

    def preflight_usage(self, usage: JevUsage | None) -> None:
        """Record the usage of the one preflight Jev call, or None when TypeSafe reported none."""
        self.state.usage = usage

    def needs_clarification(self, clarification: JevClarification) -> None:
        """Record the questions the user must answer; they become the run's output."""
        self.state.clarification = clarification
        self.state.output = clarification.questions

    def stopped(self) -> AgentResult:
        """Return the result of a run the preflight gate stopped before the generative agent ran."""
        return AgentResult(output=self.state.output or "", strategy_name=JEV_PREFLIGHT_STRATEGY_NAME)

    def finished(self, result: AgentResult) -> AgentResult:
        """Record the generative agent's output and return its result unchanged."""
        self.state.output = result.output
        return result


__all__ = ["JevResponse"]
