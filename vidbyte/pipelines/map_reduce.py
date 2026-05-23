"""Context Protocol Header

Description:
    Implements MapReducePipeline: runs map stages concurrently on the same prompt,
    joins their outputs, then feeds the combined result to a reduce stage.
Purpose:
    Enables the classic map-reduce pattern — fan-out to N agents, then fan-in
    through a synthesis/reduction agent — as a single named primitive.
Architecture:
    - MapReducePipeline: Uses asyncio.gather to run all map stages concurrently;
      joins outputs with a configurable separator; invokes the reduce stage with
      the combined string.
Relations:
    Inherits BasePipeline. Accepts BaseAgent or BasePipeline instances as both
    map stages and the reduce stage.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from vidbyte.lib.errors import PipelineExecutionError
from vidbyte.pipelines.base import BasePipeline
from vidbyte.pipelines.types import PipelineNode

MAP_REDUCE_JOIN_SEPARATOR = "\n\n---\n\n"


class MapReducePipeline(BasePipeline):
    """Fan-out map stages concurrently, then reduce the joined outputs."""

    def __init__(
        self,
        map_stages: Sequence[PipelineNode],
        reduce_stage: PipelineNode,
        *,
        separator: str = MAP_REDUCE_JOIN_SEPARATOR,
    ) -> None:
        if not map_stages:
            raise PipelineExecutionError("MapReducePipeline requires at least one map stage.")
        self._map_stages = tuple(map_stages)
        self._reduce_stage = reduce_stage
        self._separator = separator

    async def run(self, prompt: str) -> str:
        outputs: list[str] = await asyncio.gather(
            *[self._invoke(stage, prompt) for stage in self._map_stages]
        )
        combined = self._separator.join(outputs)
        return await self._invoke(self._reduce_stage, combined)


__all__ = ["MAP_REDUCE_JOIN_SEPARATOR", "MapReducePipeline"]
