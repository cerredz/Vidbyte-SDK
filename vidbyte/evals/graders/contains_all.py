"""Required-term grader for deterministic checklist-style evals."""

from __future__ import annotations

from typing import ClassVar, Sequence

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.types import EvalCase, GraderResult


class ContainsAllGrader(BaseGrader):
    """Grader that requires every configured term to appear in the output."""

    name: ClassVar[str] = "contains_all"

    def __init__(self, required: Sequence[str] | None = None, *, case_sensitive: bool = False) -> None:
        # Stores required terms and case sensitivity preferences.
        self.required = tuple(required or ())
        self.case_sensitive = case_sensitive

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Checks all required terms against the evaluated output.
        required = self.required or self._expected_terms(case)
        haystack = actual if self.case_sensitive else actual.lower()
        missing = [term for term in required if self._normalize(term) not in haystack]
        passed = not missing
        score = 1.0 if passed else 0.0
        reason = "All required terms found." if passed else f"Missing required terms: {missing}"
        return GraderResult(score=score, passed=passed, reason=reason)

    def _expected_terms(self, case: EvalCase) -> tuple[str, ...]:
        # Converts EvalCase.expected into a tuple of required text terms.
        if case.expected is None:
            return ()
        if isinstance(case.expected, (list, tuple, set)):
            return tuple(str(value) for value in case.expected)
        return (str(case.expected),)

    def _normalize(self, term: str) -> str:
        # Applies the configured case sensitivity to a required term.
        return term if self.case_sensitive else term.lower()

