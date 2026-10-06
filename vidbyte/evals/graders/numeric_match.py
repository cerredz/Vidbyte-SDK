"""Numeric tolerance grader for math and measurement evals."""

from __future__ import annotations

import re
from typing import ClassVar

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.types import EvalCase, GraderResult


class NumericMatchGrader(BaseGrader):
    """Grader that compares numeric output against expected value within tolerance."""

    name: ClassVar[str] = "numeric_match"

    def __init__(self, *, tolerance: float = 0.0) -> None:
        # Stores the non-negative numeric tolerance.
        if tolerance < 0:
            raise ValueError("tolerance must be non-negative.")
        self.tolerance = tolerance

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Parses expected and actual numeric values and compares them.
        expected = self._parse_number(case.expected)
        observed = self._parse_number(actual)
        if expected is None:
            return GraderResult(score=0.0, passed=False, reason="Expected value is not numeric.")
        if observed is None:
            return GraderResult(score=0.0, passed=False, reason="Output does not contain a numeric value.")
        delta = abs(observed - expected)
        passed = delta <= self.tolerance
        score = 1.0 if passed else 0.0
        reason = f"Numeric delta {delta} within tolerance {self.tolerance}." if passed else f"Numeric delta {delta} exceeds tolerance {self.tolerance}."
        return GraderResult(score=score, passed=passed, reason=reason)

    def _parse_number(self, value: object) -> float | None:
        # Converts numeric objects or numeric text into a float value.
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", str(value))
        return float(match.group(0)) if match else None

