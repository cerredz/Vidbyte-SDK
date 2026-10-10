"""Choice and label grader for multiple-choice and classification evals."""

from __future__ import annotations

import re
from typing import ClassVar, Sequence

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
        text = actual.strip()
        spans = [
            (index, found.span())
            for index, choice in enumerate(self.choices)
            for found in re.finditer(rf"(?<!\w)\(?{re.escape(choice)}\)?\.?(?!\w)", text, flags=flags)
        ]
        # @intent nested-label-counts-once
        # A label found inside a longer matched label ("spam" in "not spam") is part of that label, not a second answer.
        kept = {
            index
            for index, (start, end) in spans
            if not any(other != index and o_start <= start and end <= o_end and o_end - o_start > end - start for other, (o_start, o_end) in spans)
        }
        return [self.choices[index] for index in sorted(kept)]

    def _normalize(self, value: str) -> str:
        # Applies the configured case sensitivity to a choice value.
        return value.strip() if self.case_sensitive else value.strip().lower()

