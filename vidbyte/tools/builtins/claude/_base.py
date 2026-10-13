"""FILE: vidbyte/tools/builtins/claude/_base.py

PURPOSE: Defines _ClaudeBuiltinTool, the shared base of the fifteen Claude tools: the host and base request each tool holds, the closed input schema of its spec, and the success and error results every tool returns.
ROLE IN CODEBASE: Subclassed by every tool in readiness.py, sessions.py, history.py and turns.py. The tools reach Claude Code only through the ClaudeHost (vidbyte/harnesses/native/claude/host.py) they hold, and ClaudeTools (vidbyte/tools/toolsets/claude.py) builds them all over one host.
ARCHITECTURE NOTE: A tool never raises for a ClaudeOperationError: _failed turns it into an error result built from its failure_code, reason and next_step (INV-13). A success is the JSON of the host's records, with enums as their values. ClaudeHost is imported only for type checking, so importing the tools never loads the harness or claude_agent_sdk (INV-1).
COMMON MODIFICATION PATTERNS: A new tool subclasses _ClaudeBuiltinTool, declares its spec through _spec, calls one host method inside execute's try, and returns _rendered or _failed.
WHAT NOT TO DO IN THIS FILE: 1. Do not put str(error) or any other exception text in a result; use the error's failure_code, reason and next_step. 2. Do not add bind_session or bind_agent; a tool holds one host, and nothing binds it to an agent's session (D-14).
KNOWN EDGE CASES: JSON null for an optional argument means the argument was left out (BaseTool._optional_argument). An argument of the wrong JSON type is passed on unchanged, so the host or the request record refuses it with configuration.invalid_argument.
RELATED DOCS: vidbyte/tools/README.md; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest
from vidbyte.lib.dataclasses.claude_host import ClaudeSessionHandle
from vidbyte.lib.errors import ClaudeOperationError
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.harnesses.native.claude.host import ClaudeHost

# The error_type every Claude tool's error result carries in its metadata (INV-13).
_ERROR_TYPE = "ClaudeOperationError"


class _ClaudeBuiltinTool(BaseTool):
    """Holds the host and base request a Claude tool acts through, and builds the results every Claude tool returns."""

    def __init__(self, host: ClaudeHost, request: ClaudeSpawnRequest) -> None:
        # @intent the-developer-fixes-every-spawn-setting
        # The tool keeps the developer's base request, and a model's call adds
        # at most a prompt to it, so no call can change the permissions, sandbox,
        # budget or CLI path the developer chose (D-13, T-2).
        self._host = host
        self._request = request

    @staticmethod
    def _spec(name: str, description: str, permission: ToolPermission, properties: Mapping[str, Any], required: tuple[str, ...]) -> ToolSpec:
        """Return a tool's spec with a closed input schema, so the model can pass no argument the tool does not name."""
        # @intent every-tool-states-its-permission
        # The permission is what the agent's PermissionPolicy checks before a
        # call runs: the tools that start, fork, steer or stop work are WRITE,
        # so the default policy refuses them until the developer opts in, and the
        # rest are READ (INV-14). The closed schema keeps every other spawn
        # setting out of the model's reach (D-13).
        schema ={"type": "object", "properties": dict(properties), "required": list(required), "additionalProperties": False}
        return ToolSpec(name=name, description=description, permission=permission, input_schema=schema)

    def _handle(self, call: ToolCall) -> ClaudeSessionHandle:
        """Resolve the call's handle_id to the handle the host issued; the host refuses an unknown or mistyped id."""
        return self._host.get_handle(self._optional_argument(call, "handle_id", default=None))

    @staticmethod
    def _failed(tool_name: str, error: ClaudeOperationError) -> ToolResult:
        """Return the error result for a refused or failed host call, built from the error's code, reason and next step (INV-13)."""
        output = f"{error.failure_code}: {error.reason} Next step: {error.next_step}"
        return ToolResult.error(tool_name, output, metadata={"error": error.failure_code, "error_type": _ERROR_TYPE})

    @staticmethod
    def _rendered(tool_name: str, payload: object) -> ToolResult:
        """Return a success whose output is the payload as JSON; a record arrives here as dataclasses.asdict made it."""
        return ToolResult.success(tool_name, json.dumps(payload))


__all__ = ["_ClaudeBuiltinTool"]
