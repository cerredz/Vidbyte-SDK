"""Context Protocol Header

Description:
    Implements SequentialPipeline: runs stages one after another, threading each
    stage's string output as the next stage's string input.
Purpose:
    Enables the most common multi-agent pattern — planner → reasoner → solver —
    with a single constructor call and no bespoke orchestration code.
Architecture:
    - SequentialPipeline: Iterates over stages; passes output of stage N as the
      prompt to stage N+1; returns the final stage's output.
Relations:
    Inherits BasePipeline. Accepts BaseAgent or BasePipeline instances as stages.
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.lib.errors import PipelineExecutionError
from vidbyte.pipelines.base import BasePipeline
from vidbyte.pipelines.types import PipelineNode


class SequentialPipeline(BasePipeline):
    """Run stages in order, threading output to input."""

    def __init__(self, stages: Sequence[PipelineNode]) -> None:
        if not stages:
            raise PipelineExecutionError("SequentialPipeline requires at least one stage.")
        self._stages = tuple(stages)

    async def run(self, prompt: str) -> str:
        current = prompt
        for stage in self._stages:
            current = await self._invoke(stage, current)
        return current


__all__ = ["SequentialPipeline"]
