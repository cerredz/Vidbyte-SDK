"""FILE: vidbyte/agents/jev/scope_coverage/check.py

PURPOSE: Runs the scope-coverage done check: the pre-run breadth review and the per-finish-attempt coverage policy.
ROLE IN CODEBASE: JevRuntime calls ScopeBreadthReview once after the state is built and ScopeCoverageDoneCheck at each finish attempt.
ARCHITECTURE NOTE: Code computes required units, missing work, and listing gaps; Jev only labels cited work and the final answer.
COMMON MODIFICATION PATTERNS: Change thresholds in vidbyte/lib/constants/jev.py; change question wording in the prompt assets.
KNOWN EDGE CASES: Units with no cited work never reach Jev; open-ended scopes are checked only for named units and disclosure.
RELATED DOCS: docs/design/jev-scope-coverage-done-criteria.md and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_agent.py.
"""

from __future__ import annotations

from collections.abc import Callable

from vidbyte.agents.jev.done_checks import (
    JevDoneCheck,
    JevDoneCheckContext,
    JevDoneCheckResult,
)
from vidbyte.agents.jev.presets import JevPresets
from vidbyte.agents.jev.run_state import JevRunState
from vidbyte.agents.jev.scope_coverage.decision import (
    JevScopeCoverageDecision,
    JevScopeDimensionDecision,
)
from vidbyte.agents.jev.scope_coverage.enums import (
    JevScopeBreadth,
    JevScopeCoverageOutcome,
    JevScopeUniverse,
)
from vidbyte.agents.jev.scope_coverage.handoff import JevScopeDimensionHandoff
from vidbyte.agents.jev.scope_coverage.questions import (
    COVERAGE_STATEMENT_QUESTION,
    SCOPE_BREADTH_QUESTION,
    STATEMENT_CLAIMS_ALL,
    STATEMENT_REPORTS_PARTIAL,
    UNIT_APPLIED,
    UNIT_COVERAGE_QUESTION,
    ScopeCoverageQuestions,
)
from vidbyte.agents.jev.scope_coverage.state import JevScopeDimension, JevScopeSection
from vidbyte.lib.constants.jev import (
    JEV_SCOPE_BREADTH_UPGRADE_THRESHOLD,
    JEV_SCOPE_CLAIMS_ALL_THRESHOLD,
    JEV_SCOPE_COVERAGE_ATTEMPTS,
    JEV_SCOPE_DISCLOSED_THRESHOLD,
    JEV_SCOPE_NO_WORK_PROBABILITY,
    JEV_SCOPE_UNIT_APPLIED_THRESHOLD,
)
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest
from vidbyte.lib.errors import OutputSchemaViolationError, ProviderResponseError
from vidbyte.lib.runners.decision import DecisionModelRunner


async def _ask(runner: DecisionModelRunner, request: JevDecisionRequest, name: str) -> JevAnswer:
    # Sends one single-question request and requires a probability distribution back.
    result = await runner.arun(request)
    answer = result.answer(name)
    if answer is None or not answer.probabilities:
        raise ProviderResponseError(f"Jev returned no probabilities for the scope-coverage question {name!r}.", provider="typesafe")
    return answer


class ScopeBreadthReview:
    """Widens a scope dimension the state builder labeled as one example when Jev reads the wording as broader."""

    def __init__(self, decision_runner: Callable[[], DecisionModelRunner]) -> None:
        # Retains the lazy per-run decision runner so runs without narrow dimensions never resolve TypeSafe.
        self._decision_runner = decision_runner

    async def review(self, section: JevScopeSection) -> JevScopeSection:
        """Return the section with builder-narrowed dimensions widened when Jev disagrees."""
        # @intent guard-the-silent-false-negative
        # A group mislabeled as one example would never be checked, so each narrow label gets one cheap second reading.
        reviewed = []
        for dimension in section.dimensions:
            if dimension.breadth.is_checked() or dimension.partial_allowed_quote:
                reviewed.append(dimension)
                continue
            answer = await _ask(self._decision_runner(), ScopeCoverageQuestions.breadth_request(dimension), SCOPE_BREADTH_QUESTION)
            every = answer.probabilities.get(JevScopeBreadth.EVERY_MEMBER.value, 0.0)
            named = answer.probabilities.get(JevScopeBreadth.NAMED_LIST.value, 0.0)
            if every + named >= JEV_SCOPE_BREADTH_UPGRADE_THRESHOLD:
                reviewed.append(dimension.upgraded(JevScopeBreadth.EVERY_MEMBER if every >= named else JevScopeBreadth.NAMED_LIST))
            else:
                reviewed.append(dimension)
        return section.with_dimensions(reviewed)


class ScopeCoverageDoneCheck(JevDoneCheck):
    """Verifies that the run's cited work reaches every member of each checked scope group."""

    preset = JevPresets.ScopeCoverage

    def __init__(self) -> None:
        # Starts run-local memory: the disclosure request is sent at most once per run.
        self._disclosure_requested = False

    def needs_handoff(self, state: JevRunState) -> bool:
        """Return whether the state holds at least one checked scope dimension."""
        return state.scope is not None and bool(state.scope.checked_dimensions())

    async def evaluate(self, context: JevDoneCheckContext) -> JevDoneCheckResult:
        """Label cited work per unit, combine it in code, and choose continue, disclose, or accept."""
        # @intent code-owns-scope-policy
        # Jev labels single units and the final answer; counts, thresholds, and the continue/accept choice stay in code.
        section = context.state.scope
        if section is None or not self.needs_handoff(context.state):
            dimensions = tuple(JevScopeDimensionDecision(item, checked=False) for item in (section.dimensions if section else ()))
            return self._result(JevScopeCoverageDecision(JevScopeCoverageOutcome.NOT_CHECKED, dimensions))
        scope_handoff = context.handoff.scope if context.handoff is not None else None
        if scope_handoff is None:
            raise OutputSchemaViolationError("Jev scope-coverage check ran without a scope handoff section.", raw_output="", validation_error="handoff.scope missing")
        accounts = scope_handoff.by_id()
        decisions = []
        for dimension in section.dimensions:
            if not dimension.is_checked():
                decisions.append(JevScopeDimensionDecision(dimension, checked=False))
                continue
            decisions.append(await self._dimension(context, dimension, accounts[dimension.id]))
        frozen = tuple(decisions)
        return self._result(JevScopeCoverageDecision(self._outcome(frozen, context.attempt), frozen))

    async def _dimension(self, context: JevDoneCheckContext, dimension: JevScopeDimension, account: JevScopeDimensionHandoff) -> JevScopeDimensionDecision:
        # Computes required units in code, asks Jev only about units with cited work, and reads the final answer when incomplete.
        # @intent unit-labels-only-from-cited-work
        # Only units with cited work reach Jev; code marks a unit with no citation uncovered, so a missing citation is never classified as covered.
        probabilities: list[tuple[str, float]] = []
        covered: list[str] = []
        required = account.required_units(dimension)
        for record in required:
            if not record.work:
                probabilities.append((record.unit, JEV_SCOPE_NO_WORK_PROBABILITY))
                continue
            answer = await _ask(context.decision_runner(), ScopeCoverageQuestions.unit_request(dimension, record), UNIT_COVERAGE_QUESTION)
            applied = answer.probabilities.get(UNIT_APPLIED, 0.0)
            probabilities.append((record.unit, applied))
            if applied >= JEV_SCOPE_UNIT_APPLIED_THRESHOLD:
                covered.append(record.unit)
        needs_listing = dimension.breadth is JevScopeBreadth.EVERY_MEMBER and dimension.universe is JevScopeUniverse.FOUND_IN_WORKSPACE
        decision = JevScopeDimensionDecision(
            dimension=dimension,
            checked=True,
            required_units=tuple(record.unit for record in required),
            covered_units=tuple(covered),
            unit_probabilities=tuple(probabilities),
            universe_listed=bool(account.enumeration) if needs_listing else None,
        )
        if decision.complete:
            return decision
        statement = await _ask(context.decision_runner(), ScopeCoverageQuestions.statement_request(dimension, context.snapshot.final_output), COVERAGE_STATEMENT_QUESTION)
        return JevScopeDimensionDecision(
            dimension=dimension,
            checked=True,
            required_units=decision.required_units,
            covered_units=decision.covered_units,
            unit_probabilities=decision.unit_probabilities,
            universe_listed=decision.universe_listed,
            coverage_statement=statement.choice,
            claims_all=statement.probabilities.get(STATEMENT_CLAIMS_ALL, 0.0) >= JEV_SCOPE_CLAIMS_ALL_THRESHOLD,
            disclosed=statement.probabilities.get(STATEMENT_REPORTS_PARTIAL, 0.0) >= JEV_SCOPE_DISCLOSED_THRESHOLD,
        )

    def _outcome(self, decisions: tuple[JevScopeDimensionDecision, ...], attempt: int) -> JevScopeCoverageOutcome:
        # Continues while attempts remain, then accepts a disclosed gap, asks once for disclosure, and finally accepts.
        # @intent bounded-continuation-then-honest-partial
        # Coverage continuations stop after JEV_SCOPE_COVERAGE_ATTEMPTS and disclosure is requested once, so an unsatisfiable check never loops; output is never rewritten.
        incomplete = [item for item in decisions if not item.complete]
        if not incomplete:
            return JevScopeCoverageOutcome.COMPLETE
        if attempt <= JEV_SCOPE_COVERAGE_ATTEMPTS:
            return JevScopeCoverageOutcome.CONTINUED
        if all(item.disclosed for item in incomplete):
            return JevScopeCoverageOutcome.PARTIAL_DISCLOSED
        if not self._disclosure_requested:
            self._disclosure_requested = True
            return JevScopeCoverageOutcome.DISCLOSURE_REQUESTED
        return JevScopeCoverageOutcome.PARTIAL_UNDISCLOSED

    def _result(self, decision: JevScopeCoverageDecision) -> JevDoneCheckResult:
        # Wraps the decision in the runtime-facing result shared by every preset.
        return JevDoneCheckResult(preset=self.preset, complete=decision.complete, accepted=decision.accepted, feedback=decision.feedback(), metadata=decision.metadata())


__all__ = ["ScopeBreadthReview", "ScopeCoverageDoneCheck"]
