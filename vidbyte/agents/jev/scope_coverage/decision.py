"""FILE: vidbyte/agents/jev/scope_coverage/decision.py

PURPOSE: Owns the scope-coverage decision records, their public metadata, and the code-authored continuation feedback.
ROLE IN CODEBASE: ScopeCoverageDoneCheck builds these records; JevRuntime publishes the metadata and appends the feedback to the live loop.
ARCHITECTURE NOTE: Feedback text is composed in code from facts and labels; Jev never writes text the agent reads.
COMMON MODIFICATION PATTERNS: Add a metadata field here and in the design doc together; keep feedback naming concrete uncovered units.
KNOWN EDGE CASES: Unchecked dimensions are reported but never make the decision incomplete.
RELATED DOCS: docs/design/jev-scope-coverage-done-criteria.md.
TESTS: tests/test_jev_agent.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from vidbyte.agents.jev.scope_coverage.enums import JevScopeCoverageOutcome
from vidbyte.agents.jev.scope_coverage.state import JevScopeDimension

ACCEPTED_OUTCOMES: frozenset[JevScopeCoverageOutcome] = frozenset(
    {
        JevScopeCoverageOutcome.COMPLETE,
        JevScopeCoverageOutcome.NOT_CHECKED,
        JevScopeCoverageOutcome.PARTIAL_DISCLOSED,
        JevScopeCoverageOutcome.PARTIAL_UNDISCLOSED,
    }
)


@dataclass(frozen=True, slots=True)
class JevScopeDimensionDecision:
    """Code facts and Jev labels for one scope dimension at one finish attempt."""

    dimension: JevScopeDimension
    checked: bool
    required_units: tuple[str, ...] = ()
    covered_units: tuple[str, ...] = ()
    unit_probabilities: tuple[tuple[str, float], ...] = ()
    universe_listed: bool | None = None
    coverage_statement: str | None = None
    claims_all: bool = False
    disclosed: bool | None = None

    @property
    def uncovered_units(self) -> tuple[str, ...]:
        """Return required units whose change the run does not show."""
        return tuple(unit for unit in self.required_units if unit not in self.covered_units)

    @property
    def complete(self) -> bool:
        """Return whether this dimension needs no further work."""
        return not self.checked or (not self.uncovered_units and self.universe_listed is not False)

    def metadata(self) -> dict[str, Any]:
        """Return the public, credential-free facts for this dimension."""
        return {
            "checked": self.checked,
            "complete": self.complete,
            "breadth": self.dimension.breadth.value,
            "universe": self.dimension.universe.value,
            "breadth_upgraded": self.dimension.breadth_upgraded,
            "required_units": list(self.required_units),
            "covered_units": list(self.covered_units),
            "uncovered_units": list(self.uncovered_units),
            "unit_probabilities": dict(self.unit_probabilities),
            "universe_listed": self.universe_listed,
            "coverage_statement": self.coverage_statement,
            "disclosed": self.disclosed,
        }

    def gap_lines(self) -> list[str]:
        """Describe this dimension's concrete gaps for the main agent."""
        # @intent feedback-names-concrete-units
        # Feedback names the exact uncovered units and listing gap in code-authored text; vague feedback lets the agent repeat the same narrow finish.
        noun = self.dimension.unit_noun
        lines = [f"- {noun} (you were asked: \"{self.dimension.request_quote}\"):"]
        if self.uncovered_units:
            lines.append(f"  The run does not show the change finished for: {', '.join(self.uncovered_units)}.")
        if self.universe_listed is False:
            lines.append(f"  The run never listed every {noun}. List them all, then apply the change to each one.")
        if self.claims_all:
            lines.append(f"  Your final answer says the change reached every {noun}, but the run does not show that.")
        return lines


@dataclass(frozen=True, slots=True)
class JevScopeCoverageDecision:
    """The combined scope-coverage outcome of one finish attempt."""

    outcome: JevScopeCoverageOutcome
    dimensions: tuple[JevScopeDimensionDecision, ...]

    @property
    def complete(self) -> bool:
        """Return whether every checked dimension is covered."""
        return all(item.complete for item in self.dimensions)

    @property
    def accepted(self) -> bool:
        """Return whether the runtime may end the run on this attempt."""
        return self.outcome in ACCEPTED_OUTCOMES

    def metadata(self) -> dict[str, Any]:
        """Return the public, credential-free scope-coverage report."""
        return {
            "complete": self.complete,
            "outcome": self.outcome.value,
            "dimensions": {item.dimension.id: item.metadata() for item in self.dimensions},
        }

    def feedback(self) -> str | None:
        """Return the code-authored message that continues the run, or None when the run may end."""
        incomplete = [item for item in self.dimensions if not item.complete]
        if self.outcome is JevScopeCoverageOutcome.CONTINUED:
            lines = ["The scope check found requested coverage that the run does not show yet."]
            for item in incomplete:
                lines.extend(item.gap_lines())
            lines.append("Continue the existing task and cover these. If some cannot be done, say plainly in your final answer which ones were left out and why.")
            return "\n".join(lines)
        if self.outcome is JevScopeCoverageOutcome.DISCLOSURE_REQUESTED:
            lines = ["The scope check still finds requested coverage that the run does not show."]
            for item in incomplete:
                lines.extend(item.gap_lines())
            lines.append("Before you finish, state plainly in your final answer which of these were not changed.")
            return "\n".join(lines)
        return None


__all__ = ["JevScopeCoverageDecision", "JevScopeDimensionDecision"]
