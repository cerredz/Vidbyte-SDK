"""Choice and label grader for multiple-choice and classification evals."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import ClassVar

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.types import EvalCase, GraderResult


class ChoiceMatchGrader(BaseGrader):
    """Grader that extracts one allowed choice and compares it to the expected label."""

    name: ClassVar[str] = "choice_match"

    def __init__(self, choices: Sequence[str], *, case_sensitive: bool = False) -> None:
        # Stores allowed choices and compiles extraction patterns.
        if not choices:
            raise ValueError("ChoiceMatchGrader requires at least one choice.")
        self.choices = tuple(str(choice) for choice in choices)
        self.case_sensitive = case_sensitive

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Extracts a single choice from output and compares it to expected.
        expected = "" if case.expected is None else str(case.expected)
        matches = self._extract_matches(actual)
        if len(matches) != 1:
            return GraderResult(score=0.0, passed=False, reason=f"Expected one choice, found {matches}.")
        passed = self._normalize(matches[0]) == self._normalize(expected)
        score = 1.0 if passed else 0.0
        reason = "Choice matched expected label." if passed else f"Expected choice '{expected}', got '{matches[0]}'."
        return GraderResult(score=score, passed=passed, reason=reason)

    def _extract_matches(self, actual: str) -> list[str]:
        # Returns all allowed choices found as standalone labels in the output.
        flags = 0 if self.case_sensitive else re.IGNORECASE
        matches = []
        for choice in self.choices:
            pattern = rf"(?<!\w)\(?{re.escape(choice)}\)?\.?(?!\w)"
            if re.search(pattern, actual.strip(), flags=flags):
                matches.append(choice)
        return matches

    def _normalize(self, value: str) -> str:
        # Applies the configured case sensitivity to a choice value.
        return value.strip() if self.case_sensitive else value.strip().lower()

