"""Context Protocol Header

Description:
    Defines the abstract base contract for Vidbyte paradigm harnesses.
Purpose:
    Gives future high-level paradigm harnesses a shared run/arun surface without
    implementing any concrete paradigm orchestration in this scaffolding layer.
Architecture:
    - ParadigmHarness: Abstract runnable harness contract with an async method
      for concrete implementations and a sync bridge for script callers.
Relations:
    Related to vidbyte.paradigms.client, vidbyte.client, and future concrete
    paradigm packages that compose agents, tools, context, middleware, prompts,
    trace artifacts, and evals.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from vidbyte.lib.errors import PipelineExecutionError


class ParadigmHarness(ABC):
    """Abstract base for thin runnable paradigm harnesses."""

    @abstractmethod
    async def arun(self, prompt: str, **options: Any) -> Any:
        # Runs a concrete paradigm harness asynchronously for the given prompt.
        raise NotImplementedError

    def run(self, prompt: str, **options: Any) -> Any:
        # Bridges asynchronous paradigm execution for synchronous scripts.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun(prompt, **options))
        raise PipelineExecutionError(
            "ParadigmHarness.run() cannot be called from an active event loop; use await arun() instead."
        )


__all__ = ["ParadigmHarness"]
