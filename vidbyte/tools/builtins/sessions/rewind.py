"""Context Protocol Header

Description:
    Prebuilt tool that time-travels the bound session's head to an earlier checkpoint.
Purpose:
    Lets an agent rewind its own current thread to a prior checkpoint so the next
    run branches from there. Rewind is own-thread only: a foreign checkpoint id
    raises SessionError, which the tool surfaces as an error result.
Architecture:
    - RewindTool: _SessionBuiltinTool binding a SessionStore and optional SessionScope.
Relations:
    Uses Session.rewind(). For cross-thread incorporation use ResumeReplaceTool instead.
    Sibling tools: CheckpointTool, ForkTool, Resume*Tool.
"""

from __future__ import annotations

from typing import Any

from vidbyte.tools.builtins.sessions._base import _SessionBuiltinTool
from vidbyte.tools.builtins.sessions.descriptions import (
    CHECKPOINT_ID_DESCRIPTION,
    REWIND_TOOL_DESCRIPTION,
)
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

_TOOL_NAME = "rewind"


class RewindTool(_SessionBuiltinTool):
    """Builtin tool that moves the bound session's head to an ancestor checkpoint."""

    def spec(self) -> ToolSpec:
        # Declare the model-facing rewind operation and its required argument.
        return ToolSpec(
            name=_TOOL_NAME,
            description=REWIND_TOOL_DESCRIPTION,
            permission=ToolPermission.SAFE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["checkpoint_id"],
                "properties": {
                    "checkpoint_id": {"type": "string", "description": CHECKPOINT_ID_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Route the call to the rewind path, never raising.
        return self._caught(_TOOL_NAME, lambda: self._perform(call.arguments))

    def _perform(self, arguments: dict[str, Any]) -> ToolResult:
        # Rewind the bound session to the named checkpoint.
        checkpoint_id = str(arguments.get("checkpoint_id", "")).strip()
        if not checkpoint_id:
            return ToolResult.error(_TOOL_NAME, "rewind requires a checkpoint_id.")
        session = self._require_bound(_TOOL_NAME)
        if session is None:
            return ToolResult.error(_TOOL_NAME, "No active session is bound to this tool.")
        session.rewind(to=checkpoint_id)
        return ToolResult.success(_TOOL_NAME, session.head or checkpoint_id)


__all__ = ["RewindTool"]
