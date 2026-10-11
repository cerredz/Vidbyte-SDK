"""Context Protocol Header

Description:
    Defines BasePipeline, the abstract foundation for all agent pipeline topologies.
Purpose:
    Provides the shared _invoke dispatcher (BaseAgent vs nested BasePipeline) and
    the sync run_sync bridge, eliminating duplication across concrete pipeline types.
Architecture:
    - BasePipeline: Abstract class; subclasses implement run(prompt) -> str.
    - _invoke: Static helper dispatching to agent.generate_reply or pipeline.run.
    - run_sync: Bridges async run() for callers without an active event loop, and has
      every agent stage release its MCP servers before that loop closes.
Relations:
    Inherited by SequentialPipeline, ParallelPipeline, and ConditionalPipeline.
    Accepts BaseAgent and BasePipeline instances as stages via _invoke.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from vidbyte.lib.errors import PipelineExecutionError

if TYPE_CHECKING:
    from vidbyte.pipelines.types import PipelineNode

# True only while run_sync drives its own event loop; every stage task gathered in it inherits the flag.
_RELEASE_STAGE_MCP: ContextVar[bool] = ContextVar("_RELEASE_STAGE_MCP", default=False)


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
            # @intent sync-run-does-not-strand-mcp-on-closed-loop
            # asyncio.run closes its loop on return, so tell every agent stage run inside it
            # to release its MCP servers first; the new loop copies this flag when it starts.
            token = _RELEASE_STAGE_MCP.set(True)
            try:
                return asyncio.run(self.run(prompt))
            finally:
                # Leave the caller's context as it was, so async runs keep their connections.
                _RELEASE_STAGE_MCP.reset(token)
        raise PipelineExecutionError(
            "BasePipeline.run_sync() cannot be called from an active event loop; use await run() instead."
        )

    @staticmethod
    async def _invoke(stage: PipelineNode, prompt: str, **options: Any) -> str:
        """Dispatch to agent.generate_reply or nested pipeline.run."""
        if isinstance(stage, BasePipeline):
            return await stage.run(prompt)
        reply_run = stage.generate_reply(prompt, **options)
        # Under run_sync, close this agent's MCP servers while the loop is still running
        # and queue them to reconnect lazily on the next one, as agent.run() does.
        if _RELEASE_STAGE_MCP.get() and hasattr(stage, "_run_releasing_mcp"):
            reply_run = stage._run_releasing_mcp(reply_run)
        reply = await reply_run
        return reply.content


__all__ = ["BasePipeline"]
