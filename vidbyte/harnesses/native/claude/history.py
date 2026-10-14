"""FILE: vidbyte/harnesses/native/claude/history.py

PURPOSE: Lists, reads and forks Claude Code's saved sessions offline, converting the SDK's records into ClaudeSessionSummary and ClaudeSessionMessage.
ROLE IN CODEBASE: Called by ClaudeHost (host.py) for list_claude_sessions, get_claude_session_info, get_claude_session_messages and fork_claude_session, and by continue_claude_session to look up the session it resumes. None of these starts a claude process.
ARCHITECTURE NOTE: The SDK's history functions read and write session files with blocking calls, so each runs in a worker thread through asyncio.to_thread. Each function maps what the SDK raised, and any failure to convert its records, through ClaudeFailureMapper, so a caller only ever sees a ClaudeOperationError.
COMMON MODIFICATION PATTERNS: A new history function adds one static method that calls the SDK through asyncio.to_thread inside one guarded try. A new content block kind gets its rendering in message.
KNOWN EDGE CASES: The converters read each field the pinned SDK's session records declare by name, never through vars() with empty defaults, so a record from a release that renamed or dropped a field reports claude.protocol_mismatch instead of empty text. The SDK returns None from get_session_info for an unknown id, a subagent transcript and a session without a summary alike, so all three report claude.session_not_found. An empty transcript cannot tell an unknown session from a known empty one, so the host asks session_info to decide. Fork writes a new session file and is allowed while the source session is live.
RELATED DOCS: https://platform.claude.com/docs/en/agent-sdk/python; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

import asyncio
from typing import Any

from vidbyte.harnesses.native.claude.failures import ClaudeFailureMapper
from vidbyte.lib.constants.claude import (
    CLAUDE_FAILURE_NEXT_STEPS,
    CLAUDE_FORK_OPERATION,
    CLAUDE_INFO_OPERATION,
    CLAUDE_LIST_OPERATION,
    CLAUDE_MESSAGES_OPERATION,
)
from vidbyte.lib.dataclasses.claude_host import (
    ClaudeSdkTypes,
    ClaudeSessionMessage,
    ClaudeSessionSummary,
)
from vidbyte.lib.enums.claude import ClaudeMessageKind
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import ClaudeOperationError


class ClaudeHistory:
    """Reads and forks Claude Code's session files in a worker thread, without starting Claude Code."""

    @staticmethod
    async def list_sessions(sdk: ClaudeSdkTypes, directory: str, limit: int | None, offset: int, include_worktrees: bool) -> tuple[ClaudeSessionSummary, ...]:
        """Return the sessions of one project folder, or of every project when directory is empty, most recent first."""
        try:
            infos = await asyncio.to_thread(sdk.list_sessions, directory=directory or None, limit=limit, offset=offset, include_worktrees=include_worktrees)
            return tuple(ClaudeHistory.summary(info) for info in infos)
        except Exception as exc:
            raise ClaudeFailureMapper.from_exception(exc, operation=CLAUDE_LIST_OPERATION, sdk=sdk) from exc

    @staticmethod
    async def session_info(sdk: ClaudeSdkTypes, session_id: str) -> ClaudeSessionSummary:
        """Return one session's summary, or raise claude.session_not_found when the SDK finds none."""
        try:
            info = await asyncio.to_thread(sdk.get_session_info, session_id)
            found = None if info is None else ClaudeHistory.summary(info)
        except Exception as exc:
            raise ClaudeFailureMapper.from_exception(exc, operation=CLAUDE_INFO_OPERATION, sdk=sdk) from exc
        if found is None:
            raise ClaudeOperationError(
                f"get_session_info found no session {session_id}; the id is unknown, belongs to a subagent, or the session has no summary yet.",
                failure_code=FailureCode.CLAUDE_SESSION_NOT_FOUND.value,
                operation=CLAUDE_INFO_OPERATION,
                next_step=CLAUDE_FAILURE_NEXT_STEPS[FailureCode.CLAUDE_SESSION_NOT_FOUND.value],
            )
        return found

    @staticmethod
    async def session_messages(sdk: ClaudeSdkTypes, session_id: str, limit: int | None, offset: int) -> tuple[ClaudeSessionMessage, ...]:
        """Return one page of a session's transcript, oldest first, with each message rendered as text."""
        try:
            raws = await asyncio.to_thread(sdk.get_session_messages, session_id, limit=limit, offset=offset)
            return tuple(ClaudeHistory.message(raw) for raw in raws)
        except Exception as exc:
            raise ClaudeFailureMapper.from_exception(exc, operation=CLAUDE_MESSAGES_OPERATION, sdk=sdk) from exc

    @staticmethod
    async def fork(sdk: ClaudeSdkTypes, session_id: str, up_to_message_id: str, title: str) -> str:
        """Copy a session into a new one, up to one message when given, and return the new session's id."""
        try:
            result = await asyncio.to_thread(sdk.fork_session, session_id, directory=None, up_to_message_id=up_to_message_id or None, title=title or None)
            forked: str = result.session_id
        except Exception as exc:
            raise ClaudeFailureMapper.from_exception(exc, operation=CLAUDE_FORK_OPERATION, sdk=sdk) from exc
        return forked

    @staticmethod
    def summary(info: Any) -> ClaudeSessionSummary:
        """Return the host's record of one SDKSessionInfo, reading each field it declares, with an absent optional text as empty text."""
        return ClaudeSessionSummary(
            session_id=info.session_id,
            summary=info.summary,
            last_modified=info.last_modified,
            file_size=info.file_size,
            custom_title=info.custom_title or "",
            first_prompt=info.first_prompt or "",
            git_branch=info.git_branch or "",
            cwd=info.cwd or "",
            tag=info.tag or "",
            created_at=info.created_at,
        )

    @staticmethod
    def message(raw: Any) -> ClaudeSessionMessage:
        """Return one transcript message as text: text blocks verbatim, tool calls and results as short tags, other blocks by type."""
        # The SessionMessage fields are read directly; its message is
        # the raw API message dict, so its keys are looked up.
        content = raw.message.get("content", "")
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
        parts: list[str] = []
        for block in blocks:
            kind = block.get("type", "")
            if kind == "text":
                parts.append(block.get("text", ""))
            elif kind == "tool_use":
                parts.append(f"[tool call: {block.get('name', '')}]")
            elif kind == "tool_result":
                parts.append("[tool result]")
            else:
                parts.append(f"[{kind}]")
        return ClaudeSessionMessage(uuid=raw.uuid, session_id=raw.session_id, kind=ClaudeMessageKind(raw.type), text="\n".join(parts))


__all__ = ["ClaudeHistory"]
