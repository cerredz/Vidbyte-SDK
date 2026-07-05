"""Context Protocol Header

Description:
    Prebuilt tool that branches multiple new sessions from one checkpoint.
Purpose:
    Lets an agent fan out its own durable thread without also running the child
    branches, preserving explicit caller control over downstream cost.
Architecture:
    - BatchForkTool: _SessionBuiltinTool bound to a Session and SessionScope.
Relations:
    Uses Session.batch_fork() for the bound thread. Sibling tools: ForkTool,
    CheckpointTool, RewindTool, and Resume*Tool.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from vidbyte.tools.builtins.sessions._base import _SessionBuiltinTool
from vidbyte.tools.builtins.sessions.descriptions import BATCH_FORK_TOOL_DESCRIPTION, CHECKPOINT_ID_DESCRIPTION
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.sessions.session import ForkOutcome

_TOOL_NAME = "batch_fork"
_MAX_COUNT = 64


class BatchForkTool(_SessionBuiltinTool):
    """Builtin tool that forks multiple sessions from the bound session."""

    def spec(self) -> ToolSpec:
        # Declare the model-facing batch fork operation and bounded arguments.
        return ToolSpec(
            name=_TOOL_NAME,
            description=BATCH_FORK_TOOL_DESCRIPTION,
            permission=ToolPermission.SAFE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["count"],
                "properties": {
                    "count": {"type": "integer", "minimum": 1, "maximum": _MAX_COUNT, "description": "Number of child sessions to create from the same checkpoint."},
                    "checkpoint_id": {"type": "string", "description": CHECKPOINT_ID_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Create the requested branches and return a result instead of raising into the agent loop.
        try:
            return self._caught(_TOOL_NAME, lambda: self._perform(dict(call.arguments)))
        except Exception as exc:
            return ToolResult.error(_TOOL_NAME, f"{type(exc).__name__}: {exc}")

    def _perform(self, arguments: dict[str, Any]) -> ToolResult:
        # Validate arguments, resolve the bound session, and run the batch fork.
        count = self._parse_count(arguments.get("count"))
        if count is None:
            return ToolResult.error(_TOOL_NAME, f"count must be an integer between 1 and {_MAX_COUNT}.")
        session = self._require_bound(_TOOL_NAME)
        if session is None:
            return ToolResult.error(_TOOL_NAME, "No active session is bound to this tool.")
        checkpoint_id = str(arguments.get("checkpoint_id", "")).strip() or None
        outcomes = session.batch_fork(count, at=checkpoint_id)
        return self._format_outcomes(outcomes)

    def _parse_count(self, value: Any) -> int | None:
        # Return a valid bounded count, rejecting bools and out-of-range values.
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        if value < 1 or value > _MAX_COUNT:
            return None
        return value

    def _format_outcomes(self, outcomes: list[ForkOutcome]) -> ToolResult:
        # Grant created child sessions in scope and serialize the compact model-facing payload.
        created: list[str] = []
        failed = 0
        for outcome in outcomes:
            if outcome.session is None:
                failed += 1
                continue
            self._scope.allow(outcome.session.id)
            created.append(outcome.session.id)
        return ToolResult.success(_TOOL_NAME, json.dumps({"created": created, "failed": failed}))


__all__ = ["BatchForkTool"]
