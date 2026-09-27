"""FILE: vidbyte/agents/jev/response.py

PURPOSE: Implements JevResponse, the only writer of a Jev coordinator's JevAgentResponse; every opinionated feature reports decisions here instead of through result metadata.
ROLE IN CODEBASE: `Jev` builds one instance and exposes `Jev.response`; `JevPreflightGate` writes preset outcomes and clarifications, `JevAgentRouter` writes the selected profile, and `JevRuntime` reads it when a gate closes or an agent completes.
ARCHITECTURE NOTE: The record type lives in vidbyte/lib/dataclasses/jev.py; this class only owns how the record changes during a run, so a new feature adds one method here and one field there.
COMMON MODIFICATION PATTERNS: Add a method named for the event a feature reports (for example needs_clarification), write the matching JevAgentResponse field, and call it from the feature.
KNOWN EDGE CASES: start() replaces the record, so a caller holding the previous run's record keeps it unchanged; the coordinator serializes its own runs because the response describes only the latest run.
RELATED DOCS: docs/design/jev-preflight-clarity.md, docs/design/jev-specialist-routing.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_preflight.py, tests/test_jev_agent.py, and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.constants.jev import JEV_PREFLIGHT_STRATEGY_NAME
from vidbyte.lib.dataclasses.jev import (
    JevAgentResponse,
    JevAgentSelection,
    JevClarification,
    JevPresetResult,
)
from vidbyte.lib.dataclasses.strategies import AgentResult


class JevResponse:
    """Writes what Jev's opinionated features decide into the response record read after a run."""

    def __init__(self) -> None:
        # Starts with an empty record so Jev.response is readable before the first run.
        self.state = JevAgentResponse()

    def start(self, message: str) -> None:
        """Begin a run: drop the previous run's record and remember the user's message."""
        self.state = JevAgentResponse(input=message)

    def preset(self, outcome: JevPresetResult) -> None:
        """Record what one enabled fixed-question preflight preset decided."""
        self.state.results[outcome.preset] = outcome

    def preflight_usage(self, usage: JevUsage | None) -> None:
        """Record the usage of the one preflight Jev call, or None when TypeSafe reported none."""
        self.state.usage = usage

    def needs_clarification(self, clarification: JevClarification) -> None:
        """Record the questions the user must answer; their rendered text becomes the run's output."""
        self.state.clarification = clarification
        self.state.output = clarification.render()

    def selected(self, selection: JevAgentSelection) -> None:
        # Records the selected profile and its probability ranking on the public response surface.
        self.state.selection = selection

    def stopped(self) -> AgentResult:
        """Return the result of a run the preflight gate stopped, carrying the clarification as its structured value."""
        return AgentResult(output=self.state.output or "", strategy_name=JEV_PREFLIGHT_STRATEGY_NAME, structured=self.state.clarification)

    def finished(self, result: AgentResult) -> AgentResult:
        """Record the generative agent's output and return its result unchanged."""
        self.state.output = result.output
        return result


__all__ = ["JevResponse"]
