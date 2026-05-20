"""Context Protocol Header

Description:
    Defines the BaseHarness class, which combines StrategyMixin and McpAttachableMixin.
Purpose:
    Provides an execution wrapper (harness) that can delegate to a strategy and support
    Model Context Protocol (MCP) server attachments and tool management.
Architecture:
    - BaseHarness: Core harness class inheriting from McpAttachableMixin and StrategyMixin.
Relations:
    - vidbyte/agents/mixins.py (McpAttachableMixin)
    - vidbyte/strategies/mixins.py (StrategyMixin)
    - vidbyte/harnesses/__init__.py (exposes BaseHarness)
"""

from __future__ import annotations

import asyncio
from typing import Any, Sequence

from vidbyte.agents.mixins import McpAttachableMixin
from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.strategies.mixins import StrategyMixin
from vidbyte.strategies.types import StrategyContext, StrategyResult


class BaseHarness(McpAttachableMixin, StrategyMixin):
    """Minimal harness that delegates execution to a composed strategy."""

    def __init__(self) -> None:
        super().__init__()
        self.tools: list[Any] = []
        self._mcp_handles: list[Any] = []
        self._pending_mcp_configs: list[Any] = []

    async def arun(
        self,
        prompt: str,
        *,
        runner: object | None = None,
        context: StrategyContext | None = None,
        tools: Sequence[object] = (),
        **options: Any,
    ) -> StrategyResult:
        if self._strategy is None:
            raise StrategyExecutionError("No strategy has been attached to this harness.")
        await self._ensure_mcp_connected()

        combined_tools = list(tools)
        for t in self.tools:
            if t not in combined_tools:
                combined_tools.append(t)

        return await self._strategy.arun(
            prompt,
            runner=runner,
            context=context,
            tools=combined_tools,
            **options,
        )

    def run(self, prompt: str, **options: Any) -> StrategyResult:
        if self._strategy is None:
            raise StrategyExecutionError("No strategy has been attached to this harness.")
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun(prompt, **options))
        raise StrategyExecutionError(
            "BaseHarness.run() cannot be called from an active event loop; use await arun()."
        )

