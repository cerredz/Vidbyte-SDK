from __future__ import annotations

import json
import re
from typing import Any, Sequence

from vidbyte.strategies.base import BaseStrategy
from vidbyte.strategies.types import StrategyContext, StrategyResult
from vidbyte.lib.registries.tools import ToolRegistry


class ReActStrategy(BaseStrategy):
    """Reasoning and Acting (ReAct) strategy with optional tool registry."""

    name = "react"

    def __init__(self, tool_registry: ToolRegistry | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.tool_registry: ToolRegistry = tool_registry or ToolRegistry()

    async def arun(
        self,
        prompt: str,
        *,
        runner: object | None = None,
        context: StrategyContext | None = None,
        tools: Sequence[object] = (),
        **options: Any,
    ) -> StrategyResult:
        for tool in tools:
            if hasattr(tool, "name") and tool.name not in self.tool_registry:
                self.tool_registry.register(tool)

        model_output: str = options.get("model_output", "")
        output = await self._execute_react_step(prompt, model_output)
        return StrategyResult(output=output, strategy_name=self.name)

    async def _execute_react_step(self, prompt: str, model_output: str) -> str:
        action_match = re.search(r"Action:\s*(\w+)", model_output)
        input_match = re.search(r"Action Input:\s*(\{.*\})", model_output, re.DOTALL)

        if not action_match:
            return model_output.strip() or prompt

        tool_name = action_match.group(1).strip()
        raw_input = input_match.group(1).strip() if input_match else "{}"

        try:
            tool = self.tool_registry.get(tool_name)
        except Exception:
            return f"Error: tool '{tool_name}' not found."

        try:
            arguments = json.loads(raw_input)
        except json.JSONDecodeError:
            arguments = {}

        from vidbyte.tools.types import ToolCall
        call = ToolCall(tool_name=tool_name, arguments=arguments)
        result = await tool.execute(call)
        return result.output
