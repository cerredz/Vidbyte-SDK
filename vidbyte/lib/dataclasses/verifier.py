"""Context Protocol Header

Description:
    Defines BudgetExhaustedAction and VerifierRuntimeBudgetParams.
Purpose:
    Verifier-runtime-specific budget configuration, kept separate from
    vidbyte.agents.runtimes.verifier.budget so the validated data contract
    lives alongside the SDK's other lib-level dataclasses rather than inside
    the behavior class that consumes it.
Architecture:
    - BudgetExhaustedAction: what happens once a VerifierRuntimeBudget is
      exhausted.
    - VerifierRuntimeBudgetParams: max_attempts, max_total_seconds,
      plateau_patience, max_flaky_flips, min_score_floor,
      max_consecutive_failures, on_exhausted.
Relations:
    Re-exported by vidbyte.agents.runtimes.verifier.types for backward
    compatibility with every existing import site in that package. Consumed
    by vidbyte.agents.runtimes.verifier.budget.VerifierRuntimeBudget.
Similar Files:
    - vidbyte/agents/settings/tool_error.py: ToolErrorPolicy, the nearest
      existing "budget plus terminal action" settings object in this repo.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from vidbyte.lib.errors import ConfigurationError


class BudgetExhaustedAction(str, Enum):
    """What happens once VerifierRuntimeBudget.exhausted is true."""

    FAIL = "fail"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    DOWNGRADE_TO_ADVISORY = "downgrade_to_advisory"


@dataclass(frozen=True, slots=True)
class VerifierRuntimeBudgetParams:
    """Validated configuration for one VerifierRuntimeBudget.

    Deliberately verifier-specific: cost ceilings are a general agent/loop
    concern (CostBudgetMiddleware) and are not duplicated here.
    """

    max_attempts: int
    max_total_seconds: float | None = None
    plateau_patience: int | None = None
    max_flaky_flips: int | None = None
    min_score_floor: float | None = None
    max_consecutive_failures: int | None = None
    on_exhausted: BudgetExhaustedAction = BudgetExhaustedAction.FAIL

    def __post_init__(self) -> None:
        # Every numeric ceiling must be strictly positive when provided.
        self._validate_max_attempts()
        self._validate_positive_if_present("max_total_seconds", self.max_total_seconds)
        self._validate_positive_if_present("plateau_patience", self.plateau_patience)
        self._validate_positive_if_present("max_flaky_flips", self.max_flaky_flips)
        self._validate_positive_if_present("max_consecutive_failures", self.max_consecutive_failures)
        self._validate_score_floor_range()

    def _validate_max_attempts(self) -> None:
        # A budget of zero or fewer attempts could never let the loop run once.
        if self.max_attempts <= 0:
            raise ConfigurationError("VerifierRuntimeBudgetParams.max_attempts must be greater than zero.")

    def _validate_score_floor_range(self) -> None:
        # A score floor outside [0, 1] can never be crossed or is always crossed — either way it is a mistake.
        if self.min_score_floor is not None and not (0.0 <= self.min_score_floor <= 1.0):
            raise ConfigurationError("VerifierRuntimeBudgetParams.min_score_floor must be within [0.0, 1.0] when provided.")

    @staticmethod
    def _validate_positive_if_present(name: str, value: float | int | None) -> None:
        # Mirrors ToolErrorPolicy's own "positive when provided" validation shape.
        if value is not None and value <= 0:
            raise ConfigurationError(f"VerifierRuntimeBudgetParams.{name} must be greater than zero when provided.")


__all__ = ["BudgetExhaustedAction", "VerifierRuntimeBudgetParams"]
