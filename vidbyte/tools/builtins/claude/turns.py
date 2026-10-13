"""FILE: vidbyte/tools/builtins/claude/turns.py

PURPOSE: Defines the five tools that act on a turn the host started, by its handle_id: WaitClaudeTurnTool, GetClaudeTurnResultTool and TrackClaudeSessionUsageTool (READ), and SteerClaudeSessionTool and InterruptClaudeTurnTool (WRITE).
ROLE IN CODEBASE: Built by ClaudeTools (vidbyte/tools/toolsets/claude.py) and exported by vidbyte/tools/builtins/claude/__init__.py. Each tool resolves its handle_id through ClaudeHost.get_handle, then calls one host method: wait_claude_turn, get_claude_turn_result, steer_claude_session, interrupt_claude_turn or track_claude_session_usage.
ARCHITECTURE NOTE: A handle crosses the model boundary as its handle_id text, and only the host that issued it can resolve it, so a handle_id from another host comes back as claude.session_not_found (D-14). Each tool returns the record as JSON, steer returns {"steered": true}, and a ClaudeOperationError becomes the INV-13 error result (_base.py).
COMMON MODIFICATION PATTERNS: A new per-turn action adds one tool here that resolves the handle first, inside its try, and calls one host method.
KNOWN EDGE CASES: Steer and interrupt also stop any background tasks the turn started, because the SDK's interrupt stops them (D-3). A wait that runs out of time returns the queued or running state as a success, never an error.
RELATED DOCS: vidbyte/tools/README.md; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

from dataclasses import asdict

from vidbyte.lib.errors import ClaudeOperationError
from vidbyte.tools.builtins.claude._base import _ClaudeBuiltinTool
from vidbyte.tools.builtins.claude.descriptions import (
    GET_CLAUDE_TURN_RESULT_DESCRIPTION,
    HANDLE_ID_DESCRIPTION,
    INTERRUPT_CLAUDE_TURN_DESCRIPTION,
    MESSAGE_DESCRIPTION,
    STEER_CLAUDE_SESSION_DESCRIPTION,
    TIMEOUT_SECONDS_DESCRIPTION,
    TRACK_CLAUDE_SESSION_USAGE_DESCRIPTION,
    WAIT_CLAUDE_TURN_DESCRIPTION,
)
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec


class WaitClaudeTurnTool(_ClaudeBuiltinTool):
    """Waits up to timeout_seconds for a turn to finish and returns its result or its current state."""

    def spec(self) -> ToolSpec:
        properties = {
            "handle_id": {"type": "string", "description": HANDLE_ID_DESCRIPTION},
            "timeout_seconds": {"type": "number", "description": TIMEOUT_SECONDS_DESCRIPTION},
        }
        return self._spec("wait_claude_turn", WAIT_CLAUDE_TURN_DESCRIPTION, ToolPermission.READ, properties, ("handle_id", "timeout_seconds"))

    async def execute(self, call: ToolCall) -> ToolResult:
        timeout_seconds = self._optional_argument(call, "timeout_seconds", default=None)
        try:
            result = await self._host.wait_claude_turn(self._handle(call), timeout_seconds=timeout_seconds)
        except ClaudeOperationError as error:
            return self._failed(self.name, error)
        return self._rendered(self.name, asdict(result))


class GetClaudeTurnResultTool(_ClaudeBuiltinTool):
    """Returns a turn's current state without waiting."""

    def spec(self) -> ToolSpec:
        properties = {"handle_id": {"type": "string", "description": HANDLE_ID_DESCRIPTION}}
        return self._spec("get_claude_turn_result", GET_CLAUDE_TURN_RESULT_DESCRIPTION, ToolPermission.READ, properties, ("handle_id",))

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            result = await self._host.get_claude_turn_result(self._handle(call))
        except ClaudeOperationError as error:
            return self._failed(self.name, error)
        return self._rendered(self.name, asdict(result))


class SteerClaudeSessionTool(_ClaudeBuiltinTool):
    """Redirects a running turn: stops its current step and runs the message as the next turn."""

    def spec(self) -> ToolSpec:
        properties = {
            "handle_id": {"type": "string", "description": HANDLE_ID_DESCRIPTION},
            "message": {"type": "string", "description": MESSAGE_DESCRIPTION},
        }
        return self._spec("steer_claude_session", STEER_CLAUDE_SESSION_DESCRIPTION, ToolPermission.WRITE, properties, ("handle_id", "message"))

    async def execute(self, call: ToolCall) -> ToolResult:
        message = self._optional_argument(call, "message", default=None)
        try:
            await self._host.steer_claude_session(self._handle(call), message)
        except ClaudeOperationError as error:
            return self._failed(self.name, error)
        return self._rendered(self.name, {"steered": True})


class InterruptClaudeTurnTool(_ClaudeBuiltinTool):
    """Stops a turn and returns its state at once."""

    def spec(self) -> ToolSpec:
        properties = {"handle_id": {"type": "string", "description": HANDLE_ID_DESCRIPTION}}
        return self._spec("interrupt_claude_turn", INTERRUPT_CLAUDE_TURN_DESCRIPTION, ToolPermission.WRITE, properties, ("handle_id",))

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            result = await self._host.interrupt_claude_turn(self._handle(call))
        except ClaudeOperationError as error:
            return self._failed(self.name, error)
        return self._rendered(self.name, asdict(result))


class TrackClaudeSessionUsageTool(_ClaudeBuiltinTool):
    """Returns a session's cost and token usage so far."""

    def spec(self) -> ToolSpec:
        properties = {"handle_id": {"type": "string", "description": HANDLE_ID_DESCRIPTION}}
        return self._spec("track_claude_session_usage", TRACK_CLAUDE_SESSION_USAGE_DESCRIPTION, ToolPermission.READ, properties, ("handle_id",))

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            usage = await self._host.track_claude_session_usage(self._handle(call))
        except ClaudeOperationError as error:
            return self._failed(self.name, error)
        return self._rendered(self.name, asdict(usage))


__all__ = ["GetClaudeTurnResultTool", "InterruptClaudeTurnTool", "SteerClaudeSessionTool", "TrackClaudeSessionUsageTool", "WaitClaudeTurnTool"]
