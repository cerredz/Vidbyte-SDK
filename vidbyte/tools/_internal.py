from __future__ import annotations

from vidbyte.tools.base import BaseTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.types import ToolActivity, ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


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
        output = str(call.arguments.get("final_answer") or call.arguments.get("answer") or "Done.")
        return ToolResult.success(IS_DONE_TOOL_NAME, output, metadata={"done": True})


def with_internal_agent_tools(tools: Tools, *, is_done_activity: ToolActivity | None = None) -> Tools:
    """Return a runtime-only catalog with internal loop-control tools included."""
    done_tool = IsDoneTool()
    if is_done_activity is not None:
        done_tool = done_tool.with_activity(is_done_activity)
    return tools.add(done_tool, replace=True)


__all__ = [
    "IS_DONE_TOOL_NAME",
    "IsDoneTool",
    "with_internal_agent_tools",
]
