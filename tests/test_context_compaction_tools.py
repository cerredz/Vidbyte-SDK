"""Context Protocol Header

Description:
    Tests context compaction tools and strategies.
Purpose:
    Verifies history reduction modes preserve expected messages and metadata.
Architecture:
    - MemoryState: In-memory ContextState for tests.
    - FakeSummarizer: Deterministic summary provider.
    - ContextCompactionToolTests: Strategy-specific compaction tests.
Relations:
    Related to vidbyte.tools.builtins.context.compaction.
"""

from __future__ import annotations

import unittest
from collections.abc import Sequence

from vidbyte.tools.builtins.context import CompactionMode, ContextCompactionTool, ContextMessage
from vidbyte.tools.types import ToolCall


class MemoryState:
    """In-memory context state for tests."""

    def __init__(self, messages: Sequence[ContextMessage]) -> None:
        """Store an initial message list."""
        self._messages = list(messages)

    def messages(self) -> Sequence[ContextMessage]:
        """Return current messages."""
        return tuple(self._messages)

    def replace_messages(self, messages: Sequence[ContextMessage]) -> None:
        """Replace current messages."""
        self._messages = list(messages)


class FakeSummarizer:
    """Deterministic summarizer for tests."""

    async def summarize(self, messages: Sequence[ContextMessage]) -> str:
        """Return a count-based summary."""
        return f"summarized {len(messages)} messages"


class ContextCompactionToolTests(unittest.IsolatedAsyncioTestCase):
    """Verifies compaction strategies."""

    def _state(self) -> MemoryState:
        """Create a state with system, user, assistant, and tool messages."""
        return MemoryState(
            (
                ContextMessage("system", "rules"),
                ContextMessage("user", "question"),
                ContextMessage("assistant", "call", kind="tool_call"),
                ContextMessage("tool", "result", kind="tool_result"),
                ContextMessage("assistant", "answer"),
            )
        )

    async def test_clear_except_system_and_log(self) -> None:
        """Aggressive clearing preserves system plus structured summary."""
        state = self._state()
        result = await ContextCompactionTool(state).execute(
            ToolCall(
                "compact_context",
                {
                    "mode": CompactionMode.CLEAR_EXCEPT_SYSTEM_AND_LOG.value,
                    "progress_log": {"completed_tasks": ["searched code"]},
                },
            )
        )
        self.assertEqual(result.status.value, "success")
        self.assertEqual(len(state.messages()), 2)
        self.assertEqual(state.messages()[0].role, "system")
        self.assertIn("searched code", state.messages()[1].content)

    async def test_remove_all_tool_calls(self) -> None:
        """All tool traces are removed."""
        state = self._state()
        await ContextCompactionTool(state).execute(
            ToolCall("compact_context", {"mode": CompactionMode.REMOVE_ALL_TOOL_CALLS.value})
        )
        self.assertFalse(any(message.kind.startswith("tool") for message in state.messages()))

    async def test_remove_last_n_tool_calls(self) -> None:
        """Only the last requested tool trace is removed."""
        state = self._state()
        await ContextCompactionTool(state).execute(
            ToolCall(
                "compact_context",
                {"mode": CompactionMode.REMOVE_LAST_N_TOOL_CALLS.value, "n": 1},
            )
        )
        self.assertEqual(sum(message.kind == "tool_call" for message in state.messages()), 1)
        self.assertEqual(sum(message.kind == "tool_result" for message in state.messages()), 0)

    async def test_summarize_range(self) -> None:
        """Summarization replaces middle messages and keeps recent ones."""
        state = self._state()
        await ContextCompactionTool(state, summarizer=FakeSummarizer()).execute(
            ToolCall(
                "compact_context",
                {"mode": CompactionMode.SUMMARIZE_RANGE.value, "keep_last": 1},
            )
        )
        self.assertIn("summarized", state.messages()[1].content)
        self.assertEqual(state.messages()[-1].content, "answer")
