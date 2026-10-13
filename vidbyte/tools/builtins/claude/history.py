"""FILE: vidbyte/tools/builtins/claude/history.py

PURPOSE: Defines the three READ tools that read Claude Code's saved sessions: ListClaudeSessionsTool, GetClaudeSessionInfoTool and GetClaudeSessionMessagesTool.
ROLE IN CODEBASE: Built by ClaudeTools (vidbyte/tools/toolsets/claude.py) and exported by vidbyte/tools/builtins/claude/__init__.py. Each tool calls one ClaudeHost method: list_claude_sessions, get_claude_session_info or get_claude_session_messages.
ARCHITECTURE NOTE: The host reads the session files in a worker thread and starts no Claude Code process, so these tools cost nothing. Each tool returns the records as JSON, or the INV-13 error result when the host raises ClaudeOperationError (_base.py).
COMMON MODIFICATION PATTERNS: A new paging or filter argument adds one schema property and one optional argument read, with its default matching the host method's.
KNOWN EDGE CASES: These tools can read the transcripts of every project on this machine, not only the base request's folder (T-2). JSON null for limit, offset, directory or include_worktrees means the argument was left out.
RELATED DOCS: vidbyte/tools/README.md; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

from dataclasses import asdict

from vidbyte.lib.errors import ClaudeOperationError
from vidbyte.tools.builtins.claude._base import _ClaudeBuiltinTool
from vidbyte.tools.builtins.claude.descriptions import (
    DIRECTORY_DESCRIPTION,
    GET_CLAUDE_SESSION_INFO_DESCRIPTION,
    GET_CLAUDE_SESSION_MESSAGES_DESCRIPTION,
    INCLUDE_WORKTREES_DESCRIPTION,
    LIST_CLAUDE_SESSIONS_DESCRIPTION,
    OFFSET_DESCRIPTION,
    PAGE_LIMIT_DESCRIPTION,
    SESSION_ID_DESCRIPTION,
)
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec


class ListClaudeSessionsTool(_ClaudeBuiltinTool):
    """Lists the saved Claude Code sessions, most recent first, one page at a time."""

    def spec(self) -> ToolSpec:
        properties = {
            "directory": {"type": "string", "description": DIRECTORY_DESCRIPTION},
            "limit": {"type": "integer", "description": PAGE_LIMIT_DESCRIPTION},
            "offset": {"type": "integer", "description": OFFSET_DESCRIPTION},
            "include_worktrees": {"type": "boolean", "description": INCLUDE_WORKTREES_DESCRIPTION},
        }
        return self._spec("list_claude_sessions", LIST_CLAUDE_SESSIONS_DESCRIPTION, ToolPermission.READ, properties, ())

    async def execute(self, call: ToolCall) -> ToolResult:
        directory = self._optional_argument(call, "directory", default="")
        limit = self._optional_argument(call, "limit", default=None)
        offset = self._optional_argument(call, "offset", default=0)
        include_worktrees = self._optional_argument(call, "include_worktrees", default=True)
        try:
            summaries = await self._host.list_claude_sessions(directory, limit, offset, include_worktrees)
        except ClaudeOperationError as error:
            return self._failed(self.name, error)
        return self._rendered(self.name, [asdict(summary) for summary in summaries])


class GetClaudeSessionInfoTool(_ClaudeBuiltinTool):
    """Returns the summary of one saved Claude Code session."""

    def spec(self) -> ToolSpec:
        properties = {"session_id": {"type": "string", "description": SESSION_ID_DESCRIPTION}}
        return self._spec("get_claude_session_info", GET_CLAUDE_SESSION_INFO_DESCRIPTION, ToolPermission.READ, properties, ("session_id",))

    async def execute(self, call: ToolCall) -> ToolResult:
        session_id = self._optional_argument(call, "session_id", default=None)
        try:
            summary = await self._host.get_claude_session_info(session_id)
        except ClaudeOperationError as error:
            return self._failed(self.name, error)
        return self._rendered(self.name, asdict(summary))


class GetClaudeSessionMessagesTool(_ClaudeBuiltinTool):
    """Returns one page of a saved session's transcript, each message rendered as text."""

    def spec(self) -> ToolSpec:
        properties = {
            "session_id": {"type": "string", "description": SESSION_ID_DESCRIPTION},
            "limit": {"type": "integer", "description": PAGE_LIMIT_DESCRIPTION},
            "offset": {"type": "integer", "description": OFFSET_DESCRIPTION},
        }
        return self._spec("get_claude_session_messages", GET_CLAUDE_SESSION_MESSAGES_DESCRIPTION, ToolPermission.READ, properties, ("session_id",))

    async def execute(self, call: ToolCall) -> ToolResult:
        session_id = self._optional_argument(call, "session_id", default=None)
        limit = self._optional_argument(call, "limit", default=None)
        offset = self._optional_argument(call, "offset", default=0)
        try:
            messages = await self._host.get_claude_session_messages(session_id, limit, offset)
        except ClaudeOperationError as error:
            return self._failed(self.name, error)
        return self._rendered(self.name, [asdict(message) for message in messages])


__all__ = ["GetClaudeSessionInfoTool", "GetClaudeSessionMessagesTool", "ListClaudeSessionsTool"]
