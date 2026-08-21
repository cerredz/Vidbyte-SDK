"""Context Protocol Header

Description:
    Defines VerifierRuntimeBudgetParams and VerifierRuntimeBudget.
Purpose:
    How much a verification-gated run is allowed to cost before giving up,
    and what giving up means. Cost figures are supplied by the caller (the
    linear runtime's own usage accounting), never computed here.
Architecture:
    - VerifierRuntimeBudgetParams: max_attempts, max_total_seconds,
      max_cost_usd, plateau_patience, on_exhausted.
    - VerifierRuntimeBudget: exhausted() combines four independent checks.
Relations:
    Reads vidbyte.agents.runtimes.verifier.types.VerificationAttempt via
    VerifierLedger by type only. Consumed by VerifierRuntimeGate.decide().
Similar Files:
    - vidbyte/agents/settings/tool_error.py: ToolErrorPolicy, the nearest
      existing "budget plus terminal action" settings object in this repo.
"""

from __future__ import annotations

from dataclasses import dataclass

from vidbyte.agents.runtimes.verifier.types import BudgetExhaustedAction, VerificationAttempt
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class VerifierRuntimeBudgetParams:
    """Validated configuration for one VerifierRuntimeBudget."""

    max_attempts: int
    max_total_seconds: float | None = None
    max_cost_usd: float | None = None
    plateau_patience: int | None = None
    on_exhausted: BudgetExhaustedAction = BudgetExhaustedAction.FAIL

    def __post_init__(self) -> None:
        # Every numeric ceiling must be strictly positive when provided.
        self._validate_max_attempts()
        self._validate_positive_if_present("max_total_seconds", self.max_total_seconds)
        self._validate_positive_if_present("max_cost_usd", self.max_cost_usd)
        self._validate_positive_if_present("plateau_patience", self.plateau_patience)

    def _validate_max_attempts(self) -> None:
        # A budget of zero or fewer attempts could never let the loop run once.
        if self.max_attempts <= 0:
            raise ConfigurationError("VerifierRuntimeBudgetParams.max_attempts must be greater than zero.")

    @staticmethod
    def _validate_positive_if_present(name: str, value: float | int | None) -> None:
        # Mirrors ToolErrorPolicy's own "positive when provided" validation shape.
        if value is not None and value <= 0:
            raise ConfigurationError(f"VerifierRuntimeBudgetParams.{name} must be greater than zero when provided.")


class VerifierRuntimeBudget:
    """How much this run is allowed to cost before giving up, and what giving up means."""

    def __init__(self, params: VerifierRuntimeBudgetParams) -> None:
        # Stores the already-validated configuration for this budget instance.
        self.params = params

    def exhausted(self, ledger: object) -> bool:
        """Returns True once any one of the four independent budget dimensions has been spent."""
        return (
            self._attempts_exhausted(ledger)
            or self._time_exhausted(ledger)
            or self._cost_exhausted(ledger)
            or self._plateaued(ledger)
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

    def _cost_exhausted(self, ledger: object) -> bool:
        # Reuses the caller-supplied cost figure already recorded on the latest attempt.
        if self.params.max_cost_usd is None:
            return False
        last = ledger.last()  # type: ignore[attr-defined]
        if last is None:
            return False
        return last.cost_spent_usd >= self.params.max_cost_usd

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

    @staticmethod
    def _pass_rate(attempt: VerificationAttempt) -> float:
        # Fraction of blocking verdicts that passed this attempt; an attempt with no blocking verdicts reads as 1.0.
        blocking = [v for v in attempt.aggregated.verdicts if v.blocking]
        if not blocking:
            return 1.0
        return sum(1 for v in blocking if v.passed) / len(blocking)


__all__ = ["VerifierRuntimeBudget", "VerifierRuntimeBudgetParams"]
