"""FILE: vidbyte/tools/builtins/codex/thread_actions.py

PURPOSE: The seven CodexHost tools that act on stored threads: start_codex_side_chat, archive_codex_thread, unarchive_codex_thread and rename_codex_thread, which start or change paid Codex work, and list_codex_background_terminals, search_codex_thread_content and list_codex_child_threads, which only read.
ROLE IN CODEBASE: Part of vidbyte/tools/builtins/codex/; CodexHostTools lists these among the sixteen first-class tools, in the order of the CodexHost functions.
ARCHITECTURE NOTE: Each tool reads its arguments with the _CodexHostTool resolve_ helpers, calls its host function once and answers through _run, so it never raises (INV-10). The side-chat tool holds one cap slot while the host starts the fork's turn, releases it in finally and then owns the fork's handle, as the run tools do (codex-host INV-32 and INV-33). Its request is the developer's spawn_defaults narrowed to read-only sandboxes, no writable roots, no network setting, never-asking approvals and no approval policy or reviewer, so Codex's own commands in a side chat cannot write or ask; the parent thread's Vidbyte tools stay callable, because the fork inherits them (first-class INV-43, D-22).
COMMON MODIFICATION PATTERNS: A new thread action is one tool class here over its CodexHost function, with its texts in descriptions.py and its line in CodexHostTools. A posture field the side chat must narrow is one more replace() term in _side_chat_defaults.
KNOWN EDGE CASES: clean_codex_background_terminals has no tool, so no model can stop a developer's terminals (first-class INV-42). The archive and rename tools answer THREAD_ARCHIVED_TEXT and THREAD_RENAMED_TEXT, because their functions return nothing for _json to write. JSON null means omitted, so a null cursor reads the first page and a null limit lets Codex choose the page size.
RELATED DOCS: docs/spec/codex-host-first-class/spec.md (section 9.2 tool table, rows 34 and 37 to 42, and the tool rules; INV-41 to INV-44, D-21, D-22)
TESTS: tests/features/codex_host/test_codex_host_feature_tools.py, tests/features/codex_host/test_codex_host_tools.py, tests/features/codex_host/test_codex_host_tool_hardening.py
"""

from __future__ import annotations

from dataclasses import replace

from vidbyte.lib.constants.codex import (
    CODEX_HOST_MIN_LIST_LIMIT,
    CODEX_HOST_THREAD_LIST_MAX_LIMIT,
)
from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
from vidbyte.lib.enums.codex import (
    CodexApprovalMode,
    CodexApprovalPolicy,
    CodexApprovalsReviewer,
    CodexHostOperation,
    CodexSandbox,
)
from vidbyte.tools.builtins.codex._base import _CodexHostTool
from vidbyte.tools.builtins.codex.descriptions import (
    ARCHIVE_CODEX_THREAD_DESCRIPTION,
    CONTENT_ARCHIVED_DESCRIPTION,
    CONTENT_QUERY_DESCRIPTION,
    CURSOR_DESCRIPTION,
    DESCENDANTS_DESCRIPTION,
    LIST_CODEX_BACKGROUND_TERMINALS_DESCRIPTION,
    LIST_CODEX_CHILD_THREADS_DESCRIPTION,
    NEW_THREAD_NAME_DESCRIPTION,
    PAGE_LIMIT_DESCRIPTION,
    RENAME_CODEX_THREAD_DESCRIPTION,
    SEARCH_CODEX_THREAD_CONTENT_DESCRIPTION,
    SIDE_CHAT_PROMPT_DESCRIPTION,
    START_CODEX_SIDE_CHAT_DESCRIPTION,
    THREAD_ID_DESCRIPTION,
    UNARCHIVE_CODEX_THREAD_DESCRIPTION,
)
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

SIDE_CHAT = CodexHostOperation.START_CODEX_SIDE_CHAT
ARCHIVE = CodexHostOperation.ARCHIVE_CODEX_THREAD
UNARCHIVE = CodexHostOperation.UNARCHIVE_CODEX_THREAD
RENAME = CodexHostOperation.RENAME_CODEX_THREAD
TERMINALS = CodexHostOperation.LIST_CODEX_BACKGROUND_TERMINALS
SEARCH_CONTENT = CodexHostOperation.SEARCH_CODEX_THREAD_CONTENT
CHILD_THREADS = CodexHostOperation.LIST_CODEX_CHILD_THREADS
ONE_TURN = 1
THREAD_ARCHIVED_TEXT = "Codex archived thread {thread_id}; the unarchive tool brings it back."
THREAD_RENAMED_TEXT = "Codex renamed thread {thread_id}."
THREAD_PROPERTY = {"type": "string", "description": THREAD_ID_DESCRIPTION}
CURSOR_PROPERTY = {"type": "string", "description": CURSOR_DESCRIPTION}
LIMIT_PROPERTY = {"type": "integer", "minimum": CODEX_HOST_MIN_LIST_LIMIT, "maximum": CODEX_HOST_THREAD_LIST_MAX_LIMIT, "description": PAGE_LIMIT_DESCRIPTION}


class StartCodexSideChatTool(_CodexHostTool):
    """Starts a read-only, never-asking side conversation forked from a stored Codex thread."""

    def spec(self) -> ToolSpec:
        # The parent thread and the question are both required.
        return ToolSpec(
            name=SIDE_CHAT.value,
            description=START_CODEX_SIDE_CHAT_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["thread_id", "prompt"],
                "properties": {"thread_id": dict(THREAD_PROPERTY), "prompt": {"type": "string", "description": SIDE_CHAT_PROMPT_DESCRIPTION}},
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the side chat's own handle as JSON.
        return await self._run(SIDE_CHAT.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # @intent a-tool-side-chat-is-read-only-and-never-asks
        # Read the parent thread and the question.
        thread_id = self._resolve_text(call, "thread_id", required=True)
        prompt = self._resolve_text(call, "prompt", required=True)
        # The fork runs under the developer's posture narrowed so that
        # Codex's own commands can neither write nor ask (INV-43, D-22).
        request = self._side_chat_defaults(self._scope.spawn_defaults)
        # Hold one cap slot while the host starts the fork's turn, then
        # own the fork's handle (codex-host INV-32, INV-33).
        await self._scope.reserve(self._host, ONE_TURN, SIDE_CHAT)
        try:
            handle = await self._host.start_codex_side_chat(thread_id, prompt, request=request)
        finally:
            self._scope.release(ONE_TURN)
        self._scope.own((handle,))
        return self._json(handle)

    @staticmethod
    def _side_chat_defaults(defaults: CodexSpawnRequest) -> CodexSpawnRequest:
        # The developer's posture with only the sandboxes, writable
        # roots, network setting and approvals narrowed; everything else
        # is kept (first-class INV-43).
        thread = replace(defaults.thread, sandbox=CodexSandbox.READ_ONLY, approval_mode=CodexApprovalMode.DENY_ALL)
        turn = replace(defaults.turn, sandbox=CodexSandbox.READ_ONLY, approval_mode=CodexApprovalMode.DENY_ALL)
        return replace(
            defaults,
            thread=thread,
            turn=turn,
            writable_roots=(),
            network_access=None,
            approval_policy=CodexApprovalPolicy.PROVIDER_DEFAULT,
            approvals_reviewer=CodexApprovalsReviewer.PROVIDER_DEFAULT,
        )


class ArchiveCodexThreadTool(_CodexHostTool):
    """Archives a stored Codex thread, hiding it from the usual thread list."""

    def spec(self) -> ToolSpec:
        # Any thread id.
        return ToolSpec(
            name=ARCHIVE.value,
            description=ARCHIVE_CODEX_THREAD_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={"type": "object", "additionalProperties": False, "required": ["thread_id"], "properties": {"thread_id": dict(THREAD_PROPERTY)}},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the fixed confirmation; the function returns nothing.
        return await self._run(ARCHIVE.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Archive the thread.
        thread_id = self._resolve_text(call, "thread_id", required=True)
        await self._host.archive_codex_thread(thread_id)
        return THREAD_ARCHIVED_TEXT.format(thread_id=thread_id)


class UnarchiveCodexThreadTool(_CodexHostTool):
    """Brings an archived Codex thread back into the usual thread list."""

    def spec(self) -> ToolSpec:
        # Any thread id.
        return ToolSpec(
            name=UNARCHIVE.value,
            description=UNARCHIVE_CODEX_THREAD_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={"type": "object", "additionalProperties": False, "required": ["thread_id"], "properties": {"thread_id": dict(THREAD_PROPERTY)}},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the restored thread as JSON.
        return await self._run(UNARCHIVE.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Unarchive the thread.
        thread_id = self._resolve_text(call, "thread_id", required=True)
        return self._json(await self._host.unarchive_codex_thread(thread_id))


class RenameCodexThreadTool(_CodexHostTool):
    """Renames a stored Codex thread."""

    def spec(self) -> ToolSpec:
        # The thread and its new name are both required.
        return ToolSpec(
            name=RENAME.value,
            description=RENAME_CODEX_THREAD_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["thread_id", "name"],
                "properties": {"thread_id": dict(THREAD_PROPERTY), "name": {"type": "string", "description": NEW_THREAD_NAME_DESCRIPTION}},
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the fixed confirmation; the function returns nothing.
        return await self._run(RENAME.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Rename the thread.
        thread_id = self._resolve_text(call, "thread_id", required=True)
        name = self._resolve_text(call, "name", required=True)
        await self._host.rename_codex_thread(thread_id, name)
        return THREAD_RENAMED_TEXT.format(thread_id=thread_id)


class ListCodexBackgroundTerminalsTool(_CodexHostTool):
    """Lists one page of the background terminals a Codex thread left running."""

    def spec(self) -> ToolSpec:
        # The thread is required; the page arguments are optional.
        return ToolSpec(
            name=TERMINALS.value,
            description=LIST_CODEX_BACKGROUND_TERMINALS_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["thread_id"],
                "properties": {"thread_id": dict(THREAD_PROPERTY), "cursor": dict(CURSOR_PROPERTY), "limit": dict(LIMIT_PROPERTY)},
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the page as JSON.
        return await self._run(TERMINALS.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Read one page of the thread's terminals.
        thread_id = self._resolve_text(call, "thread_id", required=True)
        cursor = self._resolve_text(call, "cursor")
        limit = self._resolve_count(call, "limit")
        return self._json(await self._host.list_codex_background_terminals(thread_id, cursor=cursor, limit=limit))


class SearchCodexThreadContentTool(_CodexHostTool):
    """Searches the stored conversations of Codex threads for a piece of text."""

    def spec(self) -> ToolSpec:
        # The text is required; the archive switch and the page
        # arguments are optional.
        return ToolSpec(
            name=SEARCH_CONTENT.value,
            description=SEARCH_CODEX_THREAD_CONTENT_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": CONTENT_QUERY_DESCRIPTION},
                    "archived": {"type": "boolean", "description": CONTENT_ARCHIVED_DESCRIPTION},
                    "cursor": dict(CURSOR_PROPERTY),
                    "limit": dict(LIMIT_PROPERTY),
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the page of hits as JSON.
        return await self._run(SEARCH_CONTENT.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Read one page of hits.
        query = self._resolve_text(call, "query", required=True)
        archived = self._resolve_bool_argument(call, "archived", default=False)
        cursor = self._resolve_text(call, "cursor")
        limit = self._resolve_count(call, "limit")
        return self._json(await self._host.search_codex_thread_content(query, archived=archived, cursor=cursor, limit=limit))


class ListCodexChildThreadsTool(_CodexHostTool):
    """Lists one page of the threads Codex spawned from a stored thread."""

    def spec(self) -> ToolSpec:
        # The thread is required; the depth switch and the page
        # arguments are optional.
        return ToolSpec(
            name=CHILD_THREADS.value,
            description=LIST_CODEX_CHILD_THREADS_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["thread_id"],
                "properties": {
                    "thread_id": dict(THREAD_PROPERTY),
                    "descendants": {"type": "boolean", "description": DESCENDANTS_DESCRIPTION},
                    "cursor": dict(CURSOR_PROPERTY),
                    "limit": dict(LIMIT_PROPERTY),
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the page of threads as JSON.
        return await self._run(CHILD_THREADS.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Read one page of the thread's children.
        thread_id = self._resolve_text(call, "thread_id", required=True)
        descendants = self._resolve_bool_argument(call, "descendants", default=False)
        cursor = self._resolve_text(call, "cursor")
        limit = self._resolve_count(call, "limit")
        return self._json(await self._host.list_codex_child_threads(thread_id, descendants=descendants, cursor=cursor, limit=limit))


__all__ = [
    "ArchiveCodexThreadTool",
    "ListCodexBackgroundTerminalsTool",
    "ListCodexChildThreadsTool",
    "RenameCodexThreadTool",
    "SearchCodexThreadContentTool",
    "StartCodexSideChatTool",
    "UnarchiveCodexThreadTool",
]
