"""FILE: vidbyte/agents/jev/response.py

PURPOSE: Implements JevResponse, the one writer of a JevAgent's JevAgentResponse: every opinionated feature reports what it decided through a method here instead of through result metadata.
ROLE IN CODEBASE: JevAgent builds one instance and exposes its record as `JevAgent.response`; JevPreflightGate writes preset outcomes and clarifications through it, and JevRuntime asks it for the result to return.
ARCHITECTURE NOTE: The record type lives in vidbyte/lib/dataclasses/jev.py; this class only owns how the record changes during a run, so a new feature adds one method here and one field there.
COMMON MODIFICATION PATTERNS: Add a method named for the event a feature reports (for example needs_clarification), write the matching JevAgentResponse field, and call it from the feature.
KNOWN EDGE CASES: start() replaces the record, so a caller holding the previous run's record keeps it unchanged; like the JevAgent that owns it, one instance serves one run at a time.
RELATED DOCS: docs/design/jev-preflight-clarity.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_preflight.py and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from dataclasses import replace

from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.constants.jev import (
    JEV_PREFLIGHT_STRATEGY_NAME,
    JEV_SECURITY_STOP_BLOCKED,
    JEV_SECURITY_STOP_REVIEW,
)
from vidbyte.lib.dataclasses.jev import (
    JevAgentResponse,
    JevClarification,
    JevPresetResult,
    JevSecurityResult,
)
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.enums.jev import JevSecurityAction


class JevResponse:
    """Writes what JevAgent's opinionated features decide into the JevAgentResponse the user reads after a run."""

    def __init__(self) -> None:
        # Starts with an empty record so JevAgent.response is readable before the first run.
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

    def security(self, result: JevSecurityResult) -> None:
        """Record the security classification without retaining the request text."""
        self.state.security = result

    def security_stopped(self, result: JevSecurityResult) -> None:
        """Set a safe user-facing message for a blocked or paused request."""
        detected = ", ".join(name.replace("_", " ") for name in result.detected())
        if detected and result.action is JevSecurityAction.BLOCK:
            self.state.output = f"This request appears to contain sensitive data in these categories: {detected}. The request was blocked before the agent started."
        elif detected:
            self.state.output = f"This request appears to contain sensitive data in these categories: {detected}. Review is required before the agent can continue."
        elif result.action is JevSecurityAction.BLOCK:
            self.state.output = "The request could not be checked for sensitive data, so it was blocked before the agent started."
        else:
            self.state.output = "The request could not be checked for sensitive data. Review it before starting the agent."

    def needs_clarification(self, clarification: JevClarification) -> None:
        """Record the questions the user must answer; their rendered text becomes the run's output."""
        self.state.clarification = clarification
        self.state.output = clarification.render()

    def stopped(self) -> AgentResult:
        """Return the result of a run the preflight gate stopped, carrying the clarification as its structured value."""
        if self.state.security is not None and self.state.clarification is None:
            reason = JEV_SECURITY_STOP_BLOCKED if self.state.security.action is JevSecurityAction.BLOCK else JEV_SECURITY_STOP_REVIEW
            return AgentResult(
                output=self.state.output or "",
                strategy_name=JEV_PREFLIGHT_STRATEGY_NAME,
                metadata={"jev_security": self.state.security, "stop_reason": reason},
            )
        return AgentResult(output=self.state.output or "", strategy_name=JEV_PREFLIGHT_STRATEGY_NAME, structured=self.state.clarification)

    def finished(self, result: AgentResult) -> AgentResult:
        """Record the generative agent's output and return its result unchanged."""
        self.state.output = result.output
        if self.state.security is None:
            return result
        return replace(result, metadata={**dict(result.metadata), "jev_security": self.state.security})


__all__ = ["JevResponse"]
