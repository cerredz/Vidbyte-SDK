"""Context Protocol Header

Description:
    Implements PredicateGrader — bridges behavior predicates into EvalRunner suites.
Purpose:
    Accepts a Callable[[RunProbe], bool] and grades agent behavior alongside
    existing text graders by implementing the agrade_with_probe hook.
Architecture:
    - PredicateGrader: subclasses BaseGrader, stores a predicate callable.
    - agrade_with_probe: called by EvalRunner when a RunProbe is available.
    - agrade: fallback that returns a descriptive failed result when no probe is passed.
Relations:
    Imported by vidbyte.evals.graders and detected by vidbyte.evals.runner via
    hasattr(grader, "agrade_with_probe").
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.types import EvalCase, GraderResult

if TYPE_CHECKING:
    from vidbyte.evals.behavior.probe import RunProbe


class PredicateGrader(BaseGrader):
    """Grader that evaluates a behavior predicate against a RunProbe."""

    name: ClassVar[str] = "predicate"

    def __init__(self, predicate: Callable[[RunProbe], bool], *, name: str = "predicate") -> None:
        # Stores the predicate callable and overrides the grader name.
        self._predicate = predicate
        self.name = name

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Fallback when called without a probe — returns a descriptive failed result.
        return GraderResult(0.0, False, "PredicateGrader requires a RunProbe; use EvalRunner.")

    async def agrade_with_probe(self, case: EvalCase, actual: str, probe: RunProbe) -> GraderResult:
        # Evaluates the predicate against the probe and returns a pass/fail result.
        try:
            passed = bool(self._predicate(probe))
        except Exception as exc:
            return GraderResult(0.0, False, f"Predicate error: {exc}")
        if passed:
            return GraderResult(1.0, True, self.name)
        return GraderResult(0.0, False, self.name)


__all__ = ["PredicateGrader"]
