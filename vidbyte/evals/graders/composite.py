"""Composite grader implementations for bundling multiple evaluation checks."""

from __future__ import annotations

from typing import ClassVar, Sequence

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.types import EvalCase, GraderResult


class AllOfGrader(BaseGrader):
    """Grader that requires every child grader to pass."""

    name: ClassVar[str] = "all_of"

    def __init__(self, graders: Sequence[BaseGrader]) -> None:
        # Stores the ordered child graders and rejects empty composites.
        if not graders:
            raise ValueError("AllOfGrader requires at least one child grader.")
        self.graders = tuple(graders)

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Runs every child grader and returns the all-of aggregate result.
        results = [await grader.agrade(case, actual) for grader in self.graders]
        passed = all(result.passed for result in results)
        score = sum(result.score for result in results) / len(results)
        reason = self._format_reason(results)
        return GraderResult(score=score, passed=passed, reason=reason)

    def _format_reason(self, results: Sequence[GraderResult]) -> str:
        # Formats child pass/fail details into a compact diagnostic reason.
        parts = [f"{grader.name}:{'pass' if result.passed else 'fail'}" for grader, result in zip(self.graders, results)]
        return "AllOfGrader results: " + ", ".join(parts)


class AnyOfGrader(BaseGrader):
    """Grader that passes when at least one child grader passes."""

    name: ClassVar[str] = "any_of"

    def __init__(self, graders: Sequence[BaseGrader]) -> None:
        # Stores the ordered child graders and rejects empty composites.
        if not graders:
            raise ValueError("AnyOfGrader requires at least one child grader.")
        self.graders = tuple(graders)

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Runs every child grader and returns the any-of aggregate result.
        results = [await grader.agrade(case, actual) for grader in self.graders]
        passed = any(result.passed for result in results)
        score = max(result.score for result in results)
        reason = self._format_reason(results)
        return GraderResult(score=score, passed=passed, reason=reason)

    def _format_reason(self, results: Sequence[GraderResult]) -> str:
        # Formats child pass/fail details into a compact diagnostic reason.
        parts = [f"{grader.name}:{'pass' if result.passed else 'fail'}" for grader, result in zip(self.graders, results)]
        return "AnyOfGrader results: " + ", ".join(parts)


class WeightedGrader(BaseGrader):
    """Grader that scores child graders using configured weights."""

    name: ClassVar[str] = "weighted"

    def __init__(self, weighted_graders: Sequence[tuple[BaseGrader, float]], *, threshold: float = 0.5) -> None:
        # Validates and stores weighted child graders for deterministic scoring.
        if not weighted_graders:
            raise ValueError("WeightedGrader requires at least one child grader.")
        if any(weight < 0 for _, weight in weighted_graders):
            raise ValueError("WeightedGrader weights must be non-negative.")
        total_weight = sum(weight for _, weight in weighted_graders)
        if total_weight <= 0:
            raise ValueError("WeightedGrader total weight must be greater than zero.")
        self.weighted_graders = tuple((grader, weight / total_weight) for grader, weight in weighted_graders)
        self.threshold = threshold

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Runs child graders, computes a weighted score, and applies the threshold.
        weighted_results = [(grader, weight, await grader.agrade(case, actual)) for grader, weight in self.weighted_graders]
        score = sum(result.score * weight for _, weight, result in weighted_results)
        passed = score >= self.threshold
        reason = self._format_reason(weighted_results, score)
        return GraderResult(score=score, passed=passed, reason=reason)

    def _format_reason(self, weighted_results: Sequence[tuple[BaseGrader, float, GraderResult]], score: float) -> str:
        # Formats weighted child details and the final score into a diagnostic reason.
        parts = [f"{grader.name}:{result.score:.3f}@{weight:.3f}" for grader, weight, result in weighted_results]
        return f"WeightedGrader score {score:.3f} with " + ", ".join(parts)

