"""FILE: tests/features/claude_host/test_claude_host_history.py

PURPOSE: Proves the offline history functions: fork copies a session file and returns the new id, list, info and messages convert the SDK's records into ClaudeSessionSummary and ClaudeSessionMessage with the spec's text rendering, unknown sessions map to claude.session_not_found, and none of them starts a claude process or runs its file work on the event loop thread.
ROLE IN CODEBASE: History layer of tests/features/claude_host/ (spec AC-8, AC-14, INV-16, D-19, NFR-8, EC-29, EC-30, section 9.1 "Session messages"). Exercises vidbyte/harnesses/native/claude/history.py through ClaudeHost.
ARCHITECTURE NOTE: The fake history functions are plain synchronous functions that record threading.get_ident() before doing anything, so a test compares that id with the event loop thread's id to prove asyncio.to_thread ran them, without mocking asyncio.to_thread.
COMMON MODIFICATION PATTERNS: When the SDK adds a SessionMessage content block kind, add it to the rendering test with the text the spec gives it. When a history function gains an argument, extend the recorded-arguments assertion for it.
WHAT NOT TO DO IN THIS FILE: 1. Do not mock asyncio.to_thread; it is a real seam. 2. Do not read real session files under the user's Claude config folder. 3. Do not import feature symbols at module level.
KNOWN EDGE CASES: The SDK cannot tell an invalid id, a sidechain and a session with no summary apart, so every None from get_session_info maps to claude.session_not_found (EC-29). An empty transcript is () for a known session and session_not_found for an unknown one (EC-30).
RELATED DOCS: tests/features/claude_host/FEATURE.md; docs/spec/claude-host/spec.md sections 6.2, 9.1 and 9.2 (fork and history rows).
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/claude_host/test_claude_host_history.py
"""

from __future__ import annotations

import asyncio
import threading
import unittest
import uuid
from pathlib import Path

from tests.features.claude_host.claude_host_fixtures import (
    CLAUDE_NEXT_STEPS,
    DEFAULT_PROMPT,
    ERROR_MARKER,
    HANG_GUARD_SECONDS,
    INVALID_ARGUMENT,
    INVALID_ARGUMENT_NEXT_STEP,
    OTHER_DIR,
    WORK_DIR,
    ClaudeHostCase,
    session_message,
)


class HistoryCase(ClaudeHostCase):
    """Adds a check that a recorded history call ran off the event loop thread."""

    def assert_off_loop(self, function: str) -> None:
        calls = self.fake.history.calls_to(function)
        self.assertTrue(calls, f"{function} was never called")
        loop_thread = threading.get_ident()
        for call in calls:
            self.assertNotEqual(call.thread_id, loop_thread, f"{function} ran on the event loop thread")


class ForkTests(HistoryCase):
    """AC-8 and D-19: fork is an offline file copy in a worker thread, allowed while the source is live."""

    async def test_fork_copies_the_session_offline(self) -> None:
        host = await self.open_host()
        session = self.fake.history.add_session()
        up_to = str(uuid.uuid4())
        forked = await asyncio.wait_for(host.fork_claude_session(session, up_to, "Try the other fix"), HANG_GUARD_SECONDS)
        self.assertEqual(forked, self.fake.history.forks[-1])
        (call,) = self.fake.history.calls_to("fork_session")
        self.assertEqual(call.arguments, {"session_id": session, "directory": None, "up_to_message_id": up_to, "title": "Try the other fix"})
        self.assert_off_loop("fork_session")
        self.assertEqual(self.fake.clients, [])

    async def test_fork_passes_none_for_empty_optional_arguments(self) -> None:
        host = await self.open_host()
        session = self.fake.history.add_session()
        await asyncio.wait_for(host.fork_claude_session(session), HANG_GUARD_SECONDS)
        (call,) = self.fake.history.calls_to("fork_session")
        self.assertEqual(call.arguments, {"session_id": session, "directory": None, "up_to_message_id": None, "title": None})

    async def test_fork_errors_map_without_their_text(self) -> None:
        host = await self.open_host()
        session = self.fake.history.add_session()
        cases = (
            ("FileNotFoundError", lambda: FileNotFoundError(f"no transcript {ERROR_MARKER}"), "claude.session_not_found", CLAUDE_NEXT_STEPS["claude.session_not_found"]),
            ("ValueError", lambda: ValueError(f"invalid session id {ERROR_MARKER}"), INVALID_ARGUMENT, INVALID_ARGUMENT_NEXT_STEP),
        )
        for label, factory, code, next_step in cases:
            with self.subTest(exception=label):
                self.fake.history.fork_error = factory
                error = await self.raises(host.fork_claude_session(session), code)
                self.assertEqual(error.next_step, next_step)
                self.assertNotIn(ERROR_MARKER, error.reason)
                self.assertNotIn(ERROR_MARKER, str(error))
        self.assertEqual(self.fake.clients, [])

    async def test_a_live_session_can_be_forked(self) -> None:
        host = await self.open_host()
        self.fake.hold(DEFAULT_PROMPT)
        live = await self.spawn(host)
        await self.client_for(live)
        self.fake.history.add_session(live.session_id)
        forked = await asyncio.wait_for(host.fork_claude_session(live.session_id), HANG_GUARD_SECONDS)
        self.assertNotEqual(forked, live.session_id)
        self.assertEqual((await self.snapshot(host, live)).status.value, "running")
        self.assertEqual(len(self.fake.clients), 1)


class SessionListTests(HistoryCase):
    """AC-14 and EC-31: list and info convert SDKSessionInfo into ClaudeSessionSummary in a worker thread."""

    async def test_list_returns_summaries_most_recent_first(self) -> None:
        from vidbyte.lib.dataclasses.claude_host import ClaudeSessionSummary

        older = self.fake.history.add_session(
            summary="Fix the parser bug",
            last_modified=1_760_000_000_000,
            cwd=WORK_DIR,
            file_size=2048,
            custom_title="Parser fix",
            first_prompt="Fix the parser",
            git_branch="main",
            tag="bug",
            created_at=1_759_000_000_000,
        )
        newer = self.fake.history.add_session(summary="Add tests", last_modified=1_760_000_500_000, cwd=None)
        host = await self.open_host()
        summaries = await asyncio.wait_for(host.list_claude_sessions(), HANG_GUARD_SECONDS)
        expected = (
            ClaudeSessionSummary(session_id=newer, summary="Add tests", last_modified=1_760_000_500_000, file_size=None, custom_title="", first_prompt="", git_branch="", cwd="", tag="", created_at=None),
            ClaudeSessionSummary(
                session_id=older,
                summary="Fix the parser bug",
                last_modified=1_760_000_000_000,
                file_size=2048,
                custom_title="Parser fix",
                first_prompt="Fix the parser",
                git_branch="main",
                cwd=WORK_DIR,
                tag="bug",
                created_at=1_759_000_000_000,
            ),
        )
        self.assertEqual(summaries, expected)
        (call,) = self.fake.history.calls_to("list_sessions")
        # An empty directory means every project, which the SDK spells as None.
        self.assertEqual(call.arguments, {"directory": None, "limit": None, "offset": 0, "include_worktrees": True})
        self.assert_off_loop("list_sessions")
        self.assertEqual(self.fake.clients, [])

    async def test_list_passes_its_directory_and_paging(self) -> None:
        for _ in range(3):
            self.fake.history.add_session(cwd=OTHER_DIR)
        host = await self.open_host()
        summaries = await asyncio.wait_for(host.list_claude_sessions(directory=OTHER_DIR, limit=1, offset=1, include_worktrees=False), HANG_GUARD_SECONDS)
        self.assertEqual(len(summaries), 1)
        (call,) = self.fake.history.calls_to("list_sessions")
        self.assertEqual(Path(call.arguments["directory"]), Path(OTHER_DIR))
        self.assertEqual((call.arguments["limit"], call.arguments["offset"], call.arguments["include_worktrees"]), (1, 1, False))

    async def test_info_returns_one_summary_or_session_not_found(self) -> None:
        from vidbyte.lib.dataclasses.claude_host import ClaudeSessionSummary

        session = self.fake.history.add_session(summary="Fix the parser bug", last_modified=1_760_000_000_000, cwd=WORK_DIR)
        host = await self.open_host()
        info = await asyncio.wait_for(host.get_claude_session_info(session), HANG_GUARD_SECONDS)
        self.assertEqual(info, ClaudeSessionSummary(session_id=session, summary="Fix the parser bug", last_modified=1_760_000_000_000, file_size=None, custom_title="", first_prompt="", git_branch="", cwd=WORK_DIR, tag="", created_at=None))
        self.assert_off_loop("get_session_info")
        # EC-29: the SDK returns None for an unknown id, a sidechain or a session with no summary.
        unknown = str(uuid.uuid4())
        error = await self.raises(host.get_claude_session_info(unknown), "claude.session_not_found")
        self.assertEqual(error.next_step, CLAUDE_NEXT_STEPS["claude.session_not_found"])
        self.assertEqual([call.arguments["session_id"] for call in self.fake.history.calls_to("get_session_info")], [session, unknown])
        self.assertEqual(self.fake.clients, [])


class SessionMessageTests(HistoryCase):
    """AC-14, EC-30 and section 9.1 "Session messages": transcripts render to text, and empty ones are told apart by info."""

    async def test_messages_render_each_content_block_kind(self) -> None:
        from vidbyte.lib.dataclasses.claude_host import ClaudeSessionMessage
        from vidbyte.lib.enums.claude import ClaudeMessageKind

        session = self.fake.history.add_session()
        transcript = (
            session_message("user", "Fix the parser bug.", session_id=session),
            session_message(
                "assistant",
                [{"type": "text", "text": "Looking at the parser."}, {"type": "tool_use", "id": "toolu_01", "name": "Grep", "input": {"pattern": "parse"}}],
                session_id=session,
            ),
            session_message("user", [{"type": "tool_result", "tool_use_id": "toolu_01", "content": "parser.py:12"}], session_id=session),
            session_message("assistant", [{"type": "thinking", "thinking": "Check the trailing comma."}, {"type": "text", "text": "Fixed it."}], session_id=session),
        )
        self.fake.history.add_messages(session, *transcript)
        host = await self.open_host()
        messages = await asyncio.wait_for(host.get_claude_session_messages(session), HANG_GUARD_SECONDS)
        texts = ("Fix the parser bug.", "Looking at the parser.\n[tool call: Grep]", "[tool result]", "[thinking]\nFixed it.")
        kinds = (ClaudeMessageKind.USER, ClaudeMessageKind.ASSISTANT, ClaudeMessageKind.USER, ClaudeMessageKind.ASSISTANT)
        expected = tuple(ClaudeSessionMessage(uuid=raw.uuid, session_id=session, kind=kind, text=text) for raw, kind, text in zip(transcript, kinds, texts, strict=True))
        self.assertEqual(messages, expected)
        self.assert_off_loop("get_session_messages")
        self.assertEqual(self.fake.clients, [])

    async def test_messages_pass_their_paging(self) -> None:
        session = self.fake.history.add_session()
        self.fake.history.add_messages(session, *(session_message("user", f"Step {index}.", session_id=session) for index in range(4)))
        host = await self.open_host()
        messages = await asyncio.wait_for(host.get_claude_session_messages(session, limit=2, offset=1), HANG_GUARD_SECONDS)
        self.assertEqual([message.text for message in messages], ["Step 1.", "Step 2."])
        (call,) = self.fake.history.calls_to("get_session_messages")
        self.assertEqual((call.arguments["session_id"], call.arguments["limit"], call.arguments["offset"]), (session, 2, 1))

    async def test_empty_messages_are_told_apart_by_info(self) -> None:
        known = self.fake.history.add_session()
        host = await self.open_host()
        self.assertEqual(await asyncio.wait_for(host.get_claude_session_messages(known), HANG_GUARD_SECONDS), ())
        unknown = str(uuid.uuid4())
        error = await self.raises(host.get_claude_session_messages(unknown), "claude.session_not_found")
        self.assertEqual(error.next_step, CLAUDE_NEXT_STEPS["claude.session_not_found"])
        self.assertIn(unknown, [call.arguments["session_id"] for call in self.fake.history.calls_to("get_session_info")])
        self.assert_off_loop("get_session_info")
        self.assertEqual(self.fake.clients, [])

    async def test_a_history_read_error_surfaces_as_a_claude_operation_error(self) -> None:
        # INV-2 and INV-12: the builtin error never escapes, and its text never reaches the reason.
        from vidbyte.lib.errors import ClaudeOperationError

        self.fake.history.read_error = lambda: OSError(f"session folder unreadable {ERROR_MARKER}")
        host = await self.open_host()
        with self.assertRaises(ClaudeOperationError) as caught:
            await asyncio.wait_for(host.list_claude_sessions(), HANG_GUARD_SECONDS)
        error = caught.exception
        self.assertTrue(error.failure_code)
        self.assertTrue(error.reason)
        self.assertTrue(error.next_step)
        self.assertNotIn(ERROR_MARKER, error.reason)
        self.assertNotIn(ERROR_MARKER, error.next_step)
        self.assertEqual(self.fake.clients, [])


if __name__ == "__main__":
    unittest.main()
