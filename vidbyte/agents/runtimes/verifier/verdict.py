"""Context Protocol Header

Description:
    Defines VerifierVerdictPolicy.
Purpose:
    Combines N verifier verdicts gathered for one attempt into a single
    pass/fail AggregatedVerdict, under one of five configurable strategies.
Architecture:
    - VerifierVerdictPolicy: aggregate() dispatches to one private method
      per strategy. VerifierVerdictPolicyParams (validated dataclass: which
      VerdictStrategy, and its required companion fields — score_threshold,
      weights, minimum_passing) lives in vidbyte.lib.dataclasses.verifier,
      not here, per review feedback on PR #349.
Relations:
    Consumes vidbyte.agents.runtimes.verifier.types.VerifierVerdict, produces
    AggregatedVerdict, consumed by VerifierRuntimeGate.decide().
Similar Files:
    - vidbyte/agents/contract.py: unmet()/exhausted() is the nearest existing
      "combine several checks into one decision" logic in this repo.
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.agents.runtimes.verifier.types import AggregatedVerdict, VerdictStrategy, VerifierVerdict
from vidbyte.lib.dataclasses.verifier import VerifierVerdictPolicyParams


class VerifierVerdictPolicy:
    """Combines N verifier verdicts into one pass/fail decision under the configured strategy."""

    def __init__(self, params: VerifierVerdictPolicyParams) -> None:
        # Stores the already-validated configuration for this policy instance.
        self.params = params

    def aggregate(self, verdicts: Sequence[VerifierVerdict]) -> AggregatedVerdict:
        """Combines verdicts into one AggregatedVerdict under the configured VerdictStrategy."""
        if not verdicts:
            return AggregatedVerdict(passed=True, verdicts=(), advisory=())
        strategy_handlers = {
            VerdictStrategy.ALL_BLOCKING_MUST_PASS: self._all_blocking_must_pass,
            VerdictStrategy.ANY_BLOCKING_PASSES: self._any_blocking_passes,
            VerdictStrategy.K_OF_N: self._k_of_n,
            VerdictStrategy.WEIGHTED_SCORE_THRESHOLD: self._weighted_score_threshold,
            VerdictStrategy.UNANIMOUS_ENSEMBLE: self._unanimous_ensemble,
        }
        return strategy_handlers[self.params.strategy](verdicts)

    def _all_blocking_must_pass(self, verdicts: Sequence[VerifierVerdict]) -> AggregatedVerdict:
        # Every blocking verdict must pass; failed non-blocking verdicts are surfaced as advisory only.
        blocking = [v for v in verdicts if v.blocking]
        advisory = tuple(v for v in verdicts if not v.blocking and not v.passed)
        return AggregatedVerdict(passed=all(v.passed for v in blocking), verdicts=tuple(verdicts), advisory=advisory)

    def _any_blocking_passes(self, verdicts: Sequence[VerifierVerdict]) -> AggregatedVerdict:
        # An OR-mode gate: at least one blocking verdict passing is enough.
        blocking = [v for v in verdicts if v.blocking]
        advisory = tuple(v for v in verdicts if not v.blocking and not v.passed)
        passed = any(v.passed for v in blocking) if blocking else True
        return AggregatedVerdict(passed=passed, verdicts=tuple(verdicts), advisory=advisory)

    def _k_of_n(self, verdicts: Sequence[VerifierVerdict]) -> AggregatedVerdict:
        # Passes once at least minimum_passing verdicts (blocking or not) have passed.
        passed_count = sum(1 for v in verdicts if v.passed)
        advisory = tuple(v for v in verdicts if not v.blocking and not v.passed)
        return AggregatedVerdict(passed=passed_count >= (self.params.minimum_passing or 0), verdicts=tuple(verdicts), advisory=advisory)

    def _weighted_score_threshold(self, verdicts: Sequence[VerifierVerdict]) -> AggregatedVerdict:
        # Falls back to a 1.0/0.0 score from plain pass/fail when a verifier reports no numeric score.
        weights = self.params.weights or {}
        weighted_sum = sum((weights.get(v.verifier_name, 1.0)) * (v.score if v.score is not None else float(v.passed)) for v in verdicts)
        total_weight = sum(weights.get(v.verifier_name, 1.0) for v in verdicts)
        mean_score = weighted_sum / total_weight if total_weight > 0 else 1.0
        advisory = tuple(v for v in verdicts if not v.blocking and not v.passed)
        return AggregatedVerdict(passed=mean_score >= (self.params.score_threshold or 0.0), verdicts=tuple(verdicts), advisory=advisory)

    def _unanimous_ensemble(self, verdicts: Sequence[VerifierVerdict]) -> AggregatedVerdict:
        # Requires cross-verifier agreement; a split vote always fails and is surfaced as its own verdict.
        if all(v.passed for v in verdicts):
            return AggregatedVerdict(passed=True, verdicts=tuple(verdicts), advisory=())
        if all(not v.passed for v in verdicts):
            return AggregatedVerdict(passed=False, verdicts=tuple(verdicts), advisory=())
        split = VerifierVerdict(
            verifier_name="ensemble_disagreement",
            tier=-1,
            blocking=True,
            passed=False,
            score=None,
            diagnostics=f"Ensemble verifiers disagree: {[(v.verifier_name, v.passed) for v in verdicts]}.",
            duration_seconds=0.0,
        )
        return AggregatedVerdict(passed=False, verdicts=(*verdicts, split), advisory=())


__all__ = ["VerifierVerdictPolicy", "VerifierVerdictPolicyParams"]
