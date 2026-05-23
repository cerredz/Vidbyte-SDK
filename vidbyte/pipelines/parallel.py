"""Context Protocol Header

Description:
    Implements ParallelPipeline: runs all stages concurrently with the same input
    and joins their outputs into a single string.
Purpose:
    Enables fan-out patterns — one prompt distributed to N agents simultaneously —
    and merges the results so the next pipeline stage receives a unified string.
Architecture:
    - ParallelPipeline: Uses asyncio.gather to run all stages concurrently; joins
      outputs with a configurable separator (default: newline + --- + newline).
Relations:
    Inherits BasePipeline. Accepts BaseAgent or BasePipeline instances as stages.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from vidbyte.lib.errors import PipelineExecutionError
from vidbyte.pipelines.base import BasePipeline
from vidbyte.pipelines.types import PipelineNode

PARALLEL_JOIN_SEPARATOR = "\n\n---\n\n"


class ParallelPipeline(BasePipeline):
    """Run all stages concurrently with the same input; join outputs."""

    def __init__(
        self,
        stages: Sequence[PipelineNode],
        *,
        separator: str = PARALLEL_JOIN_SEPARATOR,
    ) -> None:
        if not stages:
            raise PipelineExecutionError("ParallelPipeline requires at least one stage.")
        self._stages = tuple(stages)
        self._separator = separator

    async def run(self, prompt: str) -> str:
        outputs: list[str] = await asyncio.gather(
            *[self._invoke(stage, prompt) for stage in self._stages]
        )
        return self._separator.join(outputs)


__all__ = ["PARALLEL_JOIN_SEPARATOR", "ParallelPipeline"]
