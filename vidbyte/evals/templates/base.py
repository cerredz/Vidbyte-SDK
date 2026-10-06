"""Base contract for reusable eval template bundles."""

from __future__ import annotations

from typing import ClassVar

from vidbyte.evals.base import BaseGrader


class EvalTemplate:
    """Base class for reusable eval templates that build concrete graders."""

    name: ClassVar[str] = "template"
    description: ClassVar[str] = ""

    def build_grader(self) -> BaseGrader:
        # Builds the concrete grader used to score an eval case.
        raise NotImplementedError("EvalTemplate subclasses must implement build_grader().")

