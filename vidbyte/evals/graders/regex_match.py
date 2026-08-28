"""Context Protocol Header

Description:
    Implements a regular expression pattern grader (RegexMatchGrader).
Purpose:
    Validates model responses against complex textual formats or search templates.
Architecture:
    - RegexMatchGrader: Inherits from BaseGrader, verifies pattern matching using python re library.
Relations:
    Related to vidbyte.evals.base (BaseGrader) and vidbyte.evals.types (EvalCase, GraderResult).
"""

from __future__ import annotations

import re
from typing import ClassVar

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.types import EvalCase, GraderResult


class RegexMatchGrader(BaseGrader):
    """Grader that evaluates responses using custom regular expression pattern matching."""

    name: ClassVar[str] = "regex_match"

    def __init__(self, *, pattern: str) -> None:
        # Compiles the regular expression pattern at grader initialization time.
        self.pattern = re.compile(pattern)

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Asynchronously executes the regular expression search and reports results.
        match = self.pattern.search(actual)
        passed = (match is not None)
        score = 1.0 if passed else 0.0
        reason = f"Regex pattern matches output successfully." if passed else f"Regex pattern '{self.pattern.pattern}' failed to match."
        return GraderResult(score=score, passed=passed, reason=reason)
