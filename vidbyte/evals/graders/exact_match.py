"""Context Protocol Header

Description:
    Implements a strict string comparison grader (ExactMatchGrader).
Purpose:
    Enables low-cost, zero-latency string equivalence checking with optional casing and whitespace controls.
Architecture:
    - ExactMatchGrader: Inherits from BaseGrader, matches expected and actual outputs exactly.
Relations:
    Related to vidbyte.evals.base (BaseGrader) and vidbyte.evals.types (EvalCase, GraderResult).
"""

from __future__ import annotations

from typing import ClassVar
from vidbyte.evals.base import BaseGrader
from vidbyte.evals.types import EvalCase, GraderResult


class ExactMatchGrader(BaseGrader):
    """Grader that checks if the evaluated response matches the expected text exactly."""

    name: ClassVar[str] = "exact_match"

    def __init__(self, *, strip: bool = True, case_sensitive: bool = False) -> None:
        # Initializes the grader with custom whitespace stripping and case sensitivity preferences.
        self.strip = strip
        self.case_sensitive = case_sensitive

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Asynchronously performs the exact match check and returns a GraderResult payload.
        expected = case.expected if case.expected is not None else ""
        a, e = actual, expected

        if self.strip:
            a = a.strip()
            e = e.strip()

        if not self.case_sensitive:
            a = a.lower()
            e = e.lower()

        passed = (a == e)
        score = 1.0 if passed else 0.0
        reason = "Matched exactly." if passed else f"Expected '{expected}', but got '{actual}'."
        return GraderResult(score=score, passed=passed, reason=reason)
