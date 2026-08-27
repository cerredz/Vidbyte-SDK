"""Context Protocol Header

Description:
    Defines VerifierRuntimeBudget.
Purpose:
    How many verification attempts a run is allowed before giving up, and
    what giving up means. Deliberately verifier-specific: cost ceilings are
    a general agent/loop concern (CostBudgetMiddleware) and are not
    duplicated here.
Architecture note:
    - VerifierRuntimeBudget: exhausted() combines six independent checks
      against its VerifierRuntimeBudgetParams (defined in
      vidbyte.lib.dataclasses.verifier, not this file).
Relations:
    Reads vidbyte.agents.runtimes.verifier.types.VerificationAttempt, and
    vidbyte.agents.runtimes.verifier.ledger.VerifierLedgerStatistics's
    flaky_verifiers() by type only. Consumed by VerifierRuntimeGate.decide().
Similar Files:
    - vidbyte/agents/settings/tool_error.py: ToolErrorPolicy, the nearest
      existing "budget plus terminal action" settings object in this repo.
Role in codebase:
    Centralizes verifier-specific attempt, score, trend, and flakiness limits.
Common modification patterns:
    Add policy to VerifierRuntimeBudgetParams and keep exhaustion deterministic.
Known edge cases:
    Missing ledger history must not be treated as a failed verification.
Related docs:
    docs/design/verifier-runtime.md
Tests:
    Covered by verifier budget tests and the full SDK suite.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.verifier import VerificationAttempt, VerifierRuntimeBudgetParams


class VerifierRuntimeBudget:
    """How many verification attempts this run is allowed before giving up, and what giving up means."""

    def __init__(self, params: VerifierRuntimeBudgetParams) -> None:
        # Stores the already-validated configuration for this budget instance.
        self.params = params

    def exhausted(self, ledger: object) -> bool:
        """Returns True once any one of the six independent budget dimensions has been spent."""
        return (
            self._attempts_exhausted(ledger)
            or self._time_exhausted(ledger)
            or self._plateaued(ledger)
            or self._flaky_exhausted(ledger)
            or self._score_floor_exhausted(ledger)
            or self._consecutive_failures_exhausted(ledger)
        )

    def remaining_attempts(self, ledger: object) -> int:
        """Returns how many verification attempts remain before max_attempts is reached."""
        return max(0, self.params.max_attempts - len(ledger.history()))  # type: ignore[attr-defined]

    def _attempts_exhausted(self, ledger: object) -> bool:
        # The one ceiling that always applies, regardless of what else is configured.
        return len(ledger.history()) >= self.params.max_attempts  # type: ignore[attr-defined]

    def _time_exhausted(self, ledger: object) -> bool:
        # Wall-clock span from the first attempt's start to the latest attempt's completion.
        if self.params.max_total_seconds is None:
            return False
        history = ledger.history()  # type: ignore[attr-defined]
        if not history:
            return False
        elapsed = history[-1].completed_at - history[0].started_at
        return elapsed >= self.params.max_total_seconds

    # @intent score-plateau
    def _plateaued(self, ledger: object) -> bool:
        # First-pass rule: the last plateau_patience attempts' blocking pass rate is non-increasing.
        if self.params.plateau_patience is None:
            return False
        history: list[VerificationAttempt] = ledger.history()  # type: ignore[attr-defined]
        if len(history) < self.params.plateau_patience:
            return False
        recent = history[-self.params.plateau_patience :]
        pass_rates = [self._pass_rate(attempt) for attempt in recent]
        return all(pass_rates[i] <= pass_rates[i - 1] for i in range(1, len(pass_rates)))

    # @intent pass-rate-budget
    @staticmethod
    def _pass_rate(attempt: VerificationAttempt) -> float:
        # Fraction of blocking verdicts that passed this attempt; an attempt with no blocking verdicts reads as 1.0.
        blocking = [v for v in attempt.aggregated.verdicts if v.blocking]
        if not blocking:
            return 1.0
        return sum(1 for v in blocking if v.passed) / len(blocking)

    def _flaky_exhausted(self, ledger: object) -> bool:
        # A verifier that keeps flipping pass/fail won't be fixed by burning through more attempts.
        if self.params.max_flaky_flips is None:
            return False
        return bool(ledger.flaky_verifiers(min_flips=self.params.max_flaky_flips))  # type: ignore[attr-defined]

    def _score_floor_exhausted(self, ledger: object) -> bool:
        # Distinct from plateau_patience: this looks at one attempt's lowest numeric score, not the aggregate pass rate.
        if self.params.min_score_floor is None:
            return False
        last: VerificationAttempt | None = ledger.last()  # type: ignore[attr-defined]
        if last is None:
            return False
        scores = [v.score for v in last.aggregated.verdicts if v.score is not None]
        if not scores:
            return False
        return min(scores) < self.params.min_score_floor

    # @intent failure-streak-budget
    def _consecutive_failures_exhausted(self, ledger: object) -> bool:
        # Catches one specific check stuck failing N times in a row while others pass, which plateau_patience can mask.
        if self.params.max_consecutive_failures is None:
            return False
        per_verifier: dict[str, list[bool]] = {}
        for attempt in ledger.history():  # type: ignore[attr-defined]
            for verdict in attempt.aggregated.verdicts:
                per_verifier.setdefault(verdict.verifier_name, []).append(verdict.passed)
        return any(self._trailing_failure_streak(sequence) >= self.params.max_consecutive_failures for sequence in per_verifier.values())

    @staticmethod
    def _trailing_failure_streak(sequence: list[bool]) -> int:
        # Counts how many of the most recent attempts a single verifier has failed, back to its last pass (or the start).
        streak = 0
        for passed in reversed(sequence):
            if passed:
                break
            streak += 1
        return streak


__all__ = ["VerifierRuntimeBudget"]
