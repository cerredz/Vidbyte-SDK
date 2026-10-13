"""FILE: vidbyte/tools/builtins/claude/readiness.py

PURPOSE: Defines the three READ tools that tell a model whether Claude Code can run and how much it may use: CheckClaudeReadyTool, ListClaudeModelsTool and GetClaudeRateLimitsTool.
ROLE IN CODEBASE: Built by ClaudeTools (vidbyte/tools/toolsets/claude.py) and exported by vidbyte/tools/builtins/claude/__init__.py. Each tool calls one ClaudeHost method: check_claude_ready, list_claude_models or get_claude_rate_limits.
ARCHITECTURE NOTE: Each tool takes no arguments, calls its host method, and returns the record or records as JSON, or the INV-13 error result when the host raises ClaudeOperationError (_base.py).
COMMON MODIFICATION PATTERNS: A new readiness fact needs no change here; it appears in the ClaudeReadiness record the check tool already renders.
KNOWN EDGE CASES: check_claude_ready reports a missing extra, CLI, version or login inside its record, so its tool returns a success that carries the failure; only a host used outside its async with block makes it an error result.
RELATED DOCS: vidbyte/tools/README.md; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

from dataclasses import asdict

from vidbyte.lib.errors import ClaudeOperationError
from vidbyte.tools.builtins.claude._base import _ClaudeBuiltinTool
from vidbyte.tools.builtins.claude.descriptions import (
    CHECK_CLAUDE_READY_DESCRIPTION,
    GET_CLAUDE_RATE_LIMITS_DESCRIPTION,
    LIST_CLAUDE_MODELS_DESCRIPTION,
)
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec


class CheckClaudeReadyTool(_ClaudeBuiltinTool):
    """Reports whether Claude Code can run on this machine, with the first problem and its next step."""

    def spec(self) -> ToolSpec:
        return self._spec("check_claude_ready", CHECK_CLAUDE_READY_DESCRIPTION, ToolPermission.READ, {}, ())

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            readiness = await self._host.check_claude_ready()
        except ClaudeOperationError as error:
            return self._failed(self.name, error)
        return self._rendered(self.name, asdict(readiness))


class ListClaudeModelsTool(_ClaudeBuiltinTool):
    """Lists the models Claude Code offers the signed-in account."""

    def spec(self) -> ToolSpec:
        return self._spec("list_claude_models", LIST_CLAUDE_MODELS_DESCRIPTION, ToolPermission.READ, {}, ())

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            models = await self._host.list_claude_models()
        except ClaudeOperationError as error:
            return self._failed(self.name, error)
        return self._rendered(self.name, [asdict(model) for model in models])


class GetClaudeRateLimitsTool(_ClaudeBuiltinTool):
    """Returns the latest rate-limit window of each kind this host's sessions reported."""

    def spec(self) -> ToolSpec:
        return self._spec("get_claude_rate_limits", GET_CLAUDE_RATE_LIMITS_DESCRIPTION, ToolPermission.READ, {}, ())

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            windows = await self._host.get_claude_rate_limits()
        except ClaudeOperationError as error:
            return self._failed(self.name, error)
        return self._rendered(self.name, [asdict(window) for window in windows])


__all__ = ["CheckClaudeReadyTool", "GetClaudeRateLimitsTool", "ListClaudeModelsTool"]
