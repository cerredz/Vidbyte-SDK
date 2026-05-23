"""Context Protocol Header

Description:
    Implements ConditionalPipeline: applies a predicate to the incoming prompt to
    select a branch key, then runs the corresponding stage with that same prompt.
Purpose:
    Enables routing between agent paths without bespoke if/else orchestration —
    a predicate string maps to a named branch, each branch being any PipelineNode.
Architecture:
    - ConditionalPipeline: Calls predicate(prompt) -> key; looks up key in branches;
      invokes the selected stage with the original prompt.
Relations:
    Inherits BasePipeline. Accepts BaseAgent or BasePipeline instances as branch values.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from vidbyte.lib.errors import PipelineExecutionError
from vidbyte.pipelines.base import BasePipeline
from vidbyte.pipelines.types import PipelineNode


class ConditionalPipeline(BasePipeline):
    """Route to a branch based on a predicate applied to the prompt."""

    def __init__(
        self,
        predicate: Callable[[str], str],
        branches: Mapping[str, PipelineNode],
    ) -> None:
        if not branches:
            raise PipelineExecutionError("ConditionalPipeline requires at least one branch.")
        self._predicate = predicate
        self._branches = dict(branches)

    async def run(self, prompt: str) -> str:
        key = self._predicate(prompt)
        if key not in self._branches:
            available = list(self._branches)
            raise PipelineExecutionError(
                f"ConditionalPipeline: predicate returned key {key!r}; available: {available}."
            )
        return await self._invoke(self._branches[key], prompt)


__all__ = ["ConditionalPipeline"]
