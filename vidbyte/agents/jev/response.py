"""FILE: vidbyte/agents/jev/response.py

PURPOSE: Implements JevResponse, the one writer of a JevAgent's JevAgentResponse: every opinionated feature reports what it decided through a method here instead of through result metadata.
ROLE IN CODEBASE: JevAgent builds one instance and exposes its record as `JevAgent.response`; JevPreflightGate writes preset outcomes, clarifications, and the chosen specialist through it, JevRunState writes the run state, the self-review, the handoff, and every done-check result through it, and JevRuntime asks it for the result to return. JevComputeController writes the run facts and run-brief refreshes of the mid-run compute checkpoint.
ARCHITECTURE NOTE: The record type lives in vidbyte/lib/dataclasses/jev.py; this class only owns how the record changes during a run, so a new feature adds one method here and one field there.
COMMON MODIFICATION PATTERNS: Add a method named for the event a feature reports (for example needs_clarification), write the matching JevAgentResponse field, and call it from the feature.
KNOWN EDGE CASES: start() replaces the record, so a caller holding the previous run's record keeps it unchanged; like the JevAgent that owns it, one instance serves one run at a time.
RELATED DOCS: docs/design/jev-preflight-clarity.md, docs/design/jev-specialist-routing.md, docs/design/jev-multipart-done-criteria.md, docs/design/jev-self-review-done-criteria.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_preflight.py, tests/test_jev_done.py, tests/test_jev_compute.py, and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.constants.jev import (
    JEV_CONTINUATION_BUDGET_INITIAL,
    JEV_PREFLIGHT_STRATEGY_NAME,
)
from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.dataclasses.jev import (
    JevAgentResponse,
    JevClarification,
    JevDoneResult,
    JevHandoffRecord,
    JevPresetResult,
    JevReviewRecord,
    JevRunBrief,
    JevRunBriefUpdate,
    JevRunFacts,
    JevRunStateRecord,
    JevSpecialist,
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

    def specialist(self, chosen: JevSpecialist | None) -> None:
        """Record the title of the specialist Jev chose to run the task, or None when the main JevAgent keeps it."""
        self.state.specialist = None if chosen is None else chosen.title

    def run_state(self, record: JevRunStateRecord | None) -> None:
        """Record the run state JevRunState wrote before the main agent started, or None when it wrote none."""
        self.state.run_state = record

    def review(self, record: JevReviewRecord | None) -> None:
        """Record what JevReviewer would reject at the latest finish attempt, or None when it wrote no review."""
        self.state.review = record

    def handoff(self, record: JevHandoffRecord | None) -> None:
        """Record the evidence JevHandoff compiled at the latest finish attempt, or None when it compiled none."""
        self.state.handoff = record

    def done(self, result: JevDoneResult) -> None:
        """Record what one enabled done check decided at the latest finish attempt."""
        self.state.done[result.check] = result

    def continued(self) -> None:
        """Record that a failed done check sent the main agent back to work."""
        self.state.continuations += 1

    def continuation_budget(self, extension: dict[str, int]) -> None:
        """Record the cumulative extra loop budget JevAgent granted to failed faithful-scope continuations."""
        for name, amount in extension.items():
            self.state.continuation_budget[name] = self.state.continuation_budget.get(name, JEV_CONTINUATION_BUDGET_INITIAL) + amount

    def run_facts(self, facts: JevRunFacts | None) -> None:
        """Record the exact run facts the compute checkpoint read most recently."""
        self.state.run_facts = facts

    def run_brief(self, update: JevRunBriefUpdate, brief: JevRunBrief | None) -> None:
        """Record one attempt to refresh the run brief and the verified brief that stands after it."""
        self.state.run_brief_updates.append(update)
        self.state.run_brief = brief

    def delegated(self, reply: AgentMessage) -> AgentResult:
        """Record the chosen specialist's reply and return it as this run's result, keeping the specialist's own metadata."""
        self.state.output = reply.content
        return AgentResult(output=reply.content, strategy_name=str(reply.metadata.get("strategy", "direct")), metadata=reply.metadata, structured=reply.structured)

    def stopped(self) -> AgentResult:
        """Return the result of a run the preflight gate stopped, carrying the clarification as its structured value."""
        return AgentResult(output=self.state.output or "", strategy_name=JEV_PREFLIGHT_STRATEGY_NAME, structured=self.state.clarification)

    def finished(self, result: AgentResult) -> AgentResult:
        """Record the generative agent's output and return its result unchanged."""
        self.state.output = result.output
        return result


__all__ = ["JevResponse"]
