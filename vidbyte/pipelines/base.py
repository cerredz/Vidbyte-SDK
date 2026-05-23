"""Context Protocol Header

Description:
    Defines BasePipeline, the abstract foundation for all agent pipeline topologies.
Purpose:
    Provides the shared _invoke dispatcher (BaseAgent vs nested BasePipeline) and
    the sync run_sync bridge, eliminating duplication across concrete pipeline types.
Architecture:
    - BasePipeline: Abstract class; subclasses implement run(prompt) -> str.
    - _invoke: Static helper dispatching to agent.generate_reply or pipeline.run.
    - run_sync: Bridges async run() for callers without an active event loop.
Relations:
    Inherited by SequentialPipeline, ParallelPipeline, and ConditionalPipeline.
    Accepts BaseAgent and BasePipeline instances as stages via _invoke.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from vidbyte.lib.errors import PipelineExecutionError

if TYPE_CHECKING:
    from vidbyte.pipelines.types import PipelineNode


class BasePipeline(ABC):
    """Abstract base for all pipeline topologies."""

    @abstractmethod
    async def run(self, prompt: str) -> str:
        raise NotImplementedError

    def run_sync(self, prompt: str) -> str:
        """Run this pipeline from synchronous code.

        Mirrors BaseStrategy.run(): raises if called from an active event loop.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.run(prompt))
        raise PipelineExecutionError(
            "BasePipeline.run_sync() cannot be called from an active event loop; use await run() instead."
        )

    @staticmethod
    async def _invoke(stage: PipelineNode, prompt: str, **options: Any) -> str:
        """Dispatch to agent.generate_reply or nested pipeline.run."""
        if isinstance(stage, BasePipeline):
            return await stage.run(prompt)
        reply = await stage.generate_reply(prompt, **options)
        return reply.content


__all__ = ["BasePipeline"]
