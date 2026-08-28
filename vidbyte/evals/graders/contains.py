"""Context Protocol Header

Description:
    Implements a substring matching grader (ContainsGrader).
Purpose:
    Provides a low-cost validator to confirm whether a crucial keyword or phrase exists in the output.
Architecture:
    - ContainsGrader: Inherits from BaseGrader, checks for inclusion of case.expected in actual.
Relations:
    Related to vidbyte.evals.base (BaseGrader) and vidbyte.evals.types (EvalCase, GraderResult).
"""

from __future__ import annotations

from typing import ClassVar

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.types import EvalCase, GraderResult


class ContainsGrader(BaseGrader):
    """Grader that verifies if the expected phrase is contained anywhere in the evaluated response."""

    name: ClassVar[str] = "contains"

    def __init__(self, *, case_sensitive: bool = False) -> None:
        # Initializes the contains grader with case sensitivity options.
        self.case_sensitive = case_sensitive

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Asynchronously verifies the presence of the substring in the actual response.
        expected = case.expected if case.expected is not None else ""

        actual_text = str(actual)
        expected_text = str(expected)
        a = actual_text if self.case_sensitive else actual_text.lower()
        e = expected_text if self.case_sensitive else expected_text.lower()

        passed = (e in a)
        score = 1.0 if passed else 0.0
        reason = f"Response contains substring '{expected}'." if passed else f"Expected substring '{expected}' not found in output."
        return GraderResult(score=score, passed=passed, reason=reason)
