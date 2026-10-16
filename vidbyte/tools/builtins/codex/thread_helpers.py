"""FILE: vidbyte/tools/builtins/codex/thread_helpers.py

PURPOSE: The six CodexHost tools over stored threads: list_recent_codex_threads, list_codex_threads_since, search_codex_threads, get_codex_thread_lineage and list_codex_turns, which only read, and compact_codex_thread, which changes the stored thread and uses paid Codex model work.
ROLE IN CODEBASE: Part of vidbyte/tools/builtins/codex/; CodexHostTools lists these after start_codex_review, in the order of the CodexHost functions.
ARCHITECTURE NOTE: Each tool reads its arguments with the _CodexHostTool resolve_ helpers, calls the host once and returns the records as JSON through _run, so it never raises. The host checks the listing limit's upper bound, and a breach becomes a configuration.invalid_argument result. delete_codex_thread has no tool, here or anywhere, so no model can delete a thread (INV-2).
COMMON MODIFICATION PATTERNS: A new thread read becomes one more READ tool class here, with its texts in descriptions.py and its line in CodexHostTools.
KNOWN EDGE CASES: JSON null means omitted, so a null limit uses the default. list_codex_turns asks for CODEX_HOST_TURNS_TOOL_DEFAULT_LIMIT turns when the model gives no limit, so one answer never carries a whole long transcript (D-25).
RELATED DOCS: docs/spec/codex-host-thread-helpers/spec.md (section 9.2 tool table, rows 16 to 21)
TESTS: tests/features/codex_host/test_codex_host_helper_tools.py
"""

from __future__ import annotations

from vidbyte.lib.constants.codex import (
    CODEX_HOST_THREAD_LIST_DEFAULT_LIMIT,
    CODEX_HOST_TURNS_TOOL_DEFAULT_LIMIT,
)
from vidbyte.lib.enums.codex import CodexHostOperation
from vidbyte.tools.builtins.codex._base import _CodexHostTool
from vidbyte.tools.builtins.codex.descriptions import (
    COMPACT_CODEX_THREAD_DESCRIPTION,
    CWD_DESCRIPTION,
    GET_CODEX_THREAD_LINEAGE_DESCRIPTION,
    LIMIT_DESCRIPTION,
    LIST_CODEX_THREADS_SINCE_DESCRIPTION,
    LIST_CODEX_TURNS_DESCRIPTION,
    LIST_RECENT_CODEX_THREADS_DESCRIPTION,
    QUERY_DESCRIPTION,
    SEARCH_CODEX_THREADS_DESCRIPTION,
    SINCE_DESCRIPTION,
    THREAD_ID_DESCRIPTION,
    TURN_CURSOR_DESCRIPTION,
    TURN_LIMIT_DESCRIPTION,
)
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

RECENT = CodexHostOperation.LIST_RECENT_CODEX_THREADS
SINCE = CodexHostOperation.LIST_CODEX_THREADS_SINCE
SEARCH = CodexHostOperation.SEARCH_CODEX_THREADS
LINEAGE = CodexHostOperation.GET_CODEX_THREAD_LINEAGE
TURNS = CodexHostOperation.LIST_CODEX_TURNS
COMPACT = CodexHostOperation.COMPACT_CODEX_THREAD
COMPACT_STARTED_TEXT = "Compaction started on thread {thread_id}; Codex compacts its history in the background and finishes only while this host stays open."


class ListRecentCodexThreadsTool(_CodexHostTool):
    """Lists the most recently updated Codex threads of every source."""

    def spec(self) -> ToolSpec:
        # Both arguments are optional.
        return ToolSpec(
            name=RECENT.value,
            description=LIST_RECENT_CODEX_THREADS_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "cwd": {"type": "string", "description": CWD_DESCRIPTION},
                    "limit": {"type": "integer", "description": LIMIT_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the threads as a JSON array.
        return await self._run(RECENT.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # An omitted limit lists the default number of threads.
        cwd = self._resolve_text(call, "cwd")
        limit = self._resolve_count(call, "limit") or CODEX_HOST_THREAD_LIST_DEFAULT_LIMIT
        return self._json(await self._host.list_recent_codex_threads(cwd, limit))


class ListCodexThreadsSinceTool(_CodexHostTool):
    """Lists the Codex threads updated at or after a moment in Unix seconds."""

    def spec(self) -> ToolSpec:
        # The moment is required; the folder and limit are optional.
        return ToolSpec(
            name=SINCE.value,
            description=LIST_CODEX_THREADS_SINCE_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["since"],
                "properties": {
                    "since": {"type": "integer", "description": SINCE_DESCRIPTION},
                    "cwd": {"type": "string", "description": CWD_DESCRIPTION},
                    "limit": {"type": "integer", "description": LIMIT_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the threads as a JSON array.
        return await self._run(SINCE.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # An omitted limit lists the default number of threads.
        since = self._resolve_timestamp(call, "since")
        cwd = self._resolve_text(call, "cwd")
        limit = self._resolve_count(call, "limit") or CODEX_HOST_THREAD_LIST_DEFAULT_LIMIT
        return self._json(await self._host.list_codex_threads_since(cwd, since, limit))


class SearchCodexThreadsTool(_CodexHostTool):
    """Finds the Codex threads whose title Codex matches with a query."""

    def spec(self) -> ToolSpec:
        # The query is required; the folder and limit are optional.
        return ToolSpec(
            name=SEARCH.value,
            description=SEARCH_CODEX_THREADS_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": QUERY_DESCRIPTION},
                    "cwd": {"type": "string", "description": CWD_DESCRIPTION},
                    "limit": {"type": "integer", "description": LIMIT_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the matching threads as a JSON array.
        return await self._run(SEARCH.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # An omitted limit lists the default number of threads.
        query = self._resolve_text(call, "query", required=True)
        cwd = self._resolve_text(call, "cwd")
        limit = self._resolve_count(call, "limit") or CODEX_HOST_THREAD_LIST_DEFAULT_LIMIT
        return self._json(await self._host.search_codex_threads(cwd, query, limit))


class GetCodexThreadLineageTool(_CodexHostTool):
    """Reads a Codex thread and the threads it was forked or spawned from."""

    def spec(self) -> ToolSpec:
        # Any thread id.
        return ToolSpec(
            name=LINEAGE.value,
            description=GET_CODEX_THREAD_LINEAGE_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["thread_id"],
                "properties": {"thread_id": {"type": "string", "description": THREAD_ID_DESCRIPTION}},
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the chain, child first, as a JSON array.
        return await self._run(LINEAGE.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Read the thread id, then the chain.
        thread_id = self._resolve_text(call, "thread_id", required=True)
        return self._json(await self._host.get_codex_thread_lineage(thread_id))


class ListCodexTurnsTool(_CodexHostTool):
    """Reads one page of a stored Codex thread's full transcript."""

    def spec(self) -> ToolSpec:
        # Any thread id, with an optional cursor and page size.
        return ToolSpec(
            name=TURNS.value,
            description=LIST_CODEX_TURNS_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["thread_id"],
                "properties": {
                    "thread_id": {"type": "string", "description": THREAD_ID_DESCRIPTION},
                    "cursor": {"type": "string", "description": TURN_CURSOR_DESCRIPTION},
                    "limit": {"type": "integer", "description": TURN_LIMIT_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the page as JSON.
        return await self._run(TURNS.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # An omitted limit asks for a small page, so one answer never
        # carries a whole long transcript (D-25).
        thread_id = self._resolve_text(call, "thread_id", required=True)
        cursor = self._resolve_text(call, "cursor")
        limit = self._resolve_count(call, "limit") or CODEX_HOST_TURNS_TOOL_DEFAULT_LIMIT
        return self._json(await self._host.list_codex_turns(thread_id, cursor, limit))


class CompactCodexThreadTool(_CodexHostTool):
    """Starts Codex's compaction of a stored thread's history."""

    def spec(self) -> ToolSpec:
        # Any thread id.
        return ToolSpec(
            name=COMPACT.value,
            description=COMPACT_CODEX_THREAD_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["thread_id"],
                "properties": {"thread_id": {"type": "string", "description": THREAD_ID_DESCRIPTION}},
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Say that the compaction started.
        return await self._run(COMPACT.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Start the compaction; it finishes in the background.
        thread_id = self._resolve_text(call, "thread_id", required=True)
        await self._host.compact_codex_thread(thread_id)
        return COMPACT_STARTED_TEXT.format(thread_id=thread_id)


__all__ = [
    "CompactCodexThreadTool",
    "GetCodexThreadLineageTool",
    "ListCodexThreadsSinceTool",
    "ListCodexTurnsTool",
    "ListRecentCodexThreadsTool",
    "SearchCodexThreadsTool",
]
