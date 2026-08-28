"""Context Protocol Header

Description:
    Defines the standardized BaseGrader contract for all evaluation assert blocks.
Purpose:
    Ensures a consistent API interface for deterministic (e.g. substring check) and
    stochastic (e.g. LLM judge) grading strategies in the evaluation module.
Architecture:
    - BaseGrader: Abstract base class offering both async and sync execution hooks.
Functions:
    - agrade: Subclass-defined asynchronous verification routine.
    - grade: Synchronous wrapper designed for legacy execution pipelines.
Relations:
    Acts as the parent contract for all grader types in vidbyte/evals/graders/.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from vidbyte.evals.types import EvalCase, GraderResult


class BaseGrader(ABC):
    """Abstract base class establishing the standard interface for all evaluation output graders."""

    name: ClassVar[str] = "base"

    @abstractmethod
    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Asynchronously grades a single model output against expected criteria.
        pass

    def grade(self, case: EvalCase, actual: str) -> GraderResult:
        # Synchronously grades a single model output against expected criteria.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.agrade(case, actual))
        if loop.is_running():
            raise RuntimeError("BaseGrader.grade() cannot be called from a running event loop; use await agrade() instead.")
        return loop.run_until_complete(self.agrade(case, actual))
