from __future__ import annotations

import json
from collections.abc import Mapping

from vidbyte.tools.base import BaseTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


IS_DONE_TOOL_NAME = "isDone"


class IsDoneTool(BaseTool):
    """Internal loop-control tool used by agents to stop runtime execution."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=IS_DONE_TOOL_NAME,
            description="Call this when you are done with the problem; this is how you stop the loop.",
            parameters=(
                ToolParameter(
                    name="final_answer",
                    type="string",
                    description="Final answer or completion message to return from the agent loop.",
                    required=False,
                    default="",
                ),
            ),
            permission=ToolPermission.SAFE,
            metadata={"internal": True},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Read the final answer, accepting the older "answer" alias, and fall back to "Done." when neither is given.
        answer = call.arguments.get("final_answer") or call.arguments.get("answer") or "Done."
        # @intent isdone-structured-answer-stays-json
        # Models often send a structured answer as a JSON object or array instead of an encoded string;
        # keep it as JSON text (not a Python repr) so output-schema parsing and callers can read it.
        output = json.dumps(answer, ensure_ascii=False) if isinstance(answer, (Mapping, list)) else str(answer)
        return ToolResult.success(IS_DONE_TOOL_NAME, output, metadata={"done": True})


def with_internal_agent_tools(tools: Tools) -> Tools:
    """Return a runtime-only catalog with internal loop-control tools included."""
    return tools.add(IsDoneTool(), replace=True)


__all__ = [
    "IS_DONE_TOOL_NAME",
    "IsDoneTool",
    "with_internal_agent_tools",
]
