"""Length grader for concise or minimum-detail evals."""

from __future__ import annotations

from typing import ClassVar

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.types import EvalCase, GraderResult


class LengthGrader(BaseGrader):
    """Grader that validates output character length boundaries."""

    name: ClassVar[str] = "length"

    def __init__(self, *, min_chars: int | None = None, max_chars: int | None = None) -> None:
        # Stores optional minimum and maximum character bounds.
        if min_chars is not None and min_chars < 0:
            raise ValueError("min_chars must be non-negative.")
        if max_chars is not None and max_chars < 0:
            raise ValueError("max_chars must be non-negative.")
        if min_chars is not None and max_chars is not None and min_chars > max_chars:
            raise ValueError("min_chars must be less than or equal to max_chars.")
        self.min_chars = min_chars
        self.max_chars = max_chars

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Checks the evaluated output length against configured bounds.
        length = len(actual)
        if self.min_chars is not None and length < self.min_chars:
            return GraderResult(score=0.0, passed=False, reason=f"Output length {length} is below minimum {self.min_chars}.")
        if self.max_chars is not None and length > self.max_chars:
            return GraderResult(score=0.0, passed=False, reason=f"Output length {length} exceeds maximum {self.max_chars}.")
        return GraderResult(score=1.0, passed=True, reason=f"Output length {length} is within bounds.")

