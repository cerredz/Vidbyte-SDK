"""Context Protocol Header

Description:
    Tests context compaction tools and strategies.
Purpose:
    Verifies history reduction modes preserve expected messages and metadata.
Architecture:
    - MemoryState: In-memory ContextState shim for testing.
    - FakeSummarizer: Stub summarizer that provides mock summarized counts.
    - ContextCompactionToolTests: Unit tests for existing and new compaction strategies.
Functions:
    - ContextCompactionToolTests.test_truncate_tool_results_basic: Verifies standard tool truncation behavior.
    - ContextCompactionToolTests.test_truncate_tool_results_zero_max_chars: Tests edge case with zero max character limit.
    - ContextCompactionToolTests.test_truncate_tool_results_non_tool_messages: Verifies non-tool results are bypassed.
    - ContextCompactionToolTests.test_truncate_tool_results_invalid_bounds: Tests handling of bad/negative bounds.
    - ContextCompactionToolTests.test_truncate_tool_results_boundary_length: Verifies exact boundary values are not mutated.
    - ContextCompactionToolTests.test_truncate_tool_results_no_placeholder: Tests indicators without dynamic placeholders.
Relations:
    Directly tests the implementation within vidbyte.tools.builtins.context.compaction.
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

    async def test_keep_last_n_messages(self) -> None:
        """System messages are preserved and only the last n non-system messages are kept."""
        state = self._state()
        await ContextCompactionTool(state).execute(
            ToolCall("compact_context", {"mode": CompactionMode.KEEP_LAST_N_MESSAGES.value, "n": 2})
        )
        messages = state.messages()
        self.assertEqual(messages[0].role, "system")
        non_system = [m for m in messages if m.role != "system"]
        self.assertEqual(len(non_system), 2)
        self.assertEqual(non_system[-1].content, "answer")

    async def test_strip_tool_result_bodies(self) -> None:
        """Tool result content is replaced with a placeholder; call records are preserved."""
        state = self._state()
        await ContextCompactionTool(state).execute(
            ToolCall("compact_context", {"mode": CompactionMode.STRIP_TOOL_RESULT_BODIES.value})
        )
        messages = state.messages()
        self.assertEqual(len(messages), 5)
        tool_results = [m for m in messages if m.kind == "tool_result"]
        self.assertEqual(len(tool_results), 1)
        self.assertEqual(tool_results[0].content, "[tool result stripped by compaction]")
        self.assertIn("original_chars", tool_results[0].metadata)

    async def test_deduplicate_tool_calls(self) -> None:
        """Duplicate tool-call/result pairs are removed, keeping only the first occurrence."""
        state = MemoryState(
            (
                ContextMessage("system", "rules"),
                ContextMessage("assistant", "lookup", kind="tool_call"),
                ContextMessage("tool", "data", kind="tool_result"),
                ContextMessage("assistant", "lookup", kind="tool_call"),
                ContextMessage("tool", "data", kind="tool_result"),
                ContextMessage("assistant", "done"),
            )
        )
        await ContextCompactionTool(state).execute(
            ToolCall("compact_context", {"mode": CompactionMode.DEDUPLICATE_TOOL_CALLS.value})
        )
        messages = state.messages()
        self.assertEqual(sum(m.kind == "tool_call" for m in messages), 1)
        self.assertEqual(sum(m.kind == "tool_result" for m in messages), 1)

    async def test_summarize_oldest_n(self) -> None:
        """Oldest n non-system messages are collapsed into a summary; the rest remain."""
        state = self._state()
        await ContextCompactionTool(state, summarizer=FakeSummarizer()).execute(
            ToolCall("compact_context", {"mode": CompactionMode.SUMMARIZE_OLDEST_N.value, "n": 2})
        )
        messages = state.messages()
        self.assertEqual(messages[0].role, "system")
        self.assertEqual(messages[1].kind, "summary")
        self.assertIn("summarized 2", messages[1].content)
        self.assertEqual(messages[-1].content, "answer")

    async def test_summarize_by_topic_blocks(self) -> None:
        """Non-system messages are split into blocks and each block is summarized."""
        state = self._state()
        await ContextCompactionTool(state, summarizer=FakeSummarizer()).execute(
            ToolCall("compact_context", {"mode": CompactionMode.SUMMARIZE_BY_TOPIC_BLOCKS.value, "block_size": 2})
        )
        messages = state.messages()
        self.assertEqual(messages[0].role, "system")
        summaries = [m for m in messages if m.kind == "summary"]
        self.assertEqual(len(summaries), 2)
        self.assertIn("block_index", summaries[0].metadata)

    async def test_summarize_oldest_n_without_summarizer_returns_error(self) -> None:
        """summarize_oldest_n without a summarizer returns an error result."""
        state = self._state()
        result = await ContextCompactionTool(state).execute(
            ToolCall("compact_context", {"mode": CompactionMode.SUMMARIZE_OLDEST_N.value, "n": 2})
        )
        self.assertEqual(result.status.value, "error")

    async def test_summarize_by_topic_blocks_without_summarizer_returns_error(self) -> None:
        """summarize_by_topic_blocks without a summarizer returns an error result."""
        state = self._state()
        result = await ContextCompactionTool(state).execute(
            ToolCall("compact_context", {"mode": CompactionMode.SUMMARIZE_BY_TOPIC_BLOCKS.value})
        )
        self.assertEqual(result.status.value, "error")

    async def test_truncate_tool_results_basic(self) -> None:
        # Verifies that tool-result messages exceeding max_chars are truncated and have metadata set correctly.
        state = MemoryState(
            (
                ContextMessage("system", "rules"),
                ContextMessage("tool", "1234567890", kind="tool_result"),
            )
        )
        await ContextCompactionTool(state).execute(
            ToolCall(
                "compact_context",
                {
                    "mode": CompactionMode.TRUNCATE_TOOL_RESULTS.value,
                    "max_chars": 5,
                    "truncation_indicator": " [truncated {count}]",
                },
            )
        )
        messages = state.messages()
        self.assertEqual(messages[1].content, "12345 [truncated 5]")
        self.assertEqual(messages[1].metadata["compaction"], "truncate_tool_results")
        self.assertEqual(messages[1].metadata["original_chars"], 10)
        self.assertEqual(messages[1].metadata["truncated_chars"], 5)

    async def test_truncate_tool_results_zero_max_chars(self) -> None:
        # [Edge Case] Verifies that max_chars=0 cuts the entire content and appends only the indicator.
        state = MemoryState(
            (
                ContextMessage("tool", "12345", kind="tool_result"),
            )
        )
        await ContextCompactionTool(state).execute(
            ToolCall(
                "compact_context",
                {
                    "mode": CompactionMode.TRUNCATE_TOOL_RESULTS.value,
                    "max_chars": 0,
                    "truncation_indicator": "[truncated]",
                },
            )
        )
        messages = state.messages()
        self.assertEqual(messages[0].content, "[truncated]")

    async def test_truncate_tool_results_non_tool_messages(self) -> None:
        # [Edge Case] Verifies that non-tool-result messages are not truncated even if they exceed max_chars.
        state = MemoryState(
            (
                ContextMessage("user", "1234567890"),
                ContextMessage("assistant", "1234567890"),
            )
        )
        await ContextCompactionTool(state).execute(
            ToolCall(
                "compact_context",
                {
                    "mode": CompactionMode.TRUNCATE_TOOL_RESULTS.value,
                    "max_chars": 5,
                },
            )
        )
        messages = state.messages()
        self.assertEqual(messages[0].content, "1234567890")
        self.assertEqual(messages[1].content, "1234567890")

    async def test_truncate_tool_results_invalid_bounds(self) -> None:
        # [Hidden Failure] Verifies that passing negative bounds or non-integers returns a clean error.
        state = self._state()
        result = await ContextCompactionTool(state).execute(
            ToolCall(
                "compact_context",
                {
                    "mode": CompactionMode.TRUNCATE_TOOL_RESULTS.value,
                    "max_chars": -5,
                },
            )
        )
        self.assertEqual(result.status.value, "error")

        result2 = await ContextCompactionTool(state).execute(
            ToolCall(
                "compact_context",
                {
                    "mode": CompactionMode.TRUNCATE_TOOL_RESULTS.value,
                    "max_chars": "abc",
                },
            )
        )
        self.assertEqual(result2.status.value, "error")

    async def test_truncate_tool_results_boundary_length(self) -> None:
        # [Silent Failure] Verifies that if tool result length exactly matches max_chars, it is not modified.
        state = MemoryState(
            (
                ContextMessage("tool", "12345", kind="tool_result"),
            )
        )
        await ContextCompactionTool(state).execute(
            ToolCall(
                "compact_context",
                {
                    "mode": CompactionMode.TRUNCATE_TOOL_RESULTS.value,
                    "max_chars": 5,
                },
            )
        )
        messages = state.messages()
        self.assertEqual(messages[0].content, "12345")
        self.assertNotIn("compaction", messages[0].metadata)

    async def test_truncate_tool_results_no_placeholder(self) -> None:
        # [Hidden Assumption] Verifies that if no {count} is present in the indicator, it is appended verbatim.
        state = MemoryState(
            (
                ContextMessage("tool", "1234567890", kind="tool_result"),
            )
        )
        await ContextCompactionTool(state).execute(
            ToolCall(
                "compact_context",
                {
                    "mode": CompactionMode.TRUNCATE_TOOL_RESULTS.value,
                    "max_chars": 5,
                    "truncation_indicator": " [truncated]",
                },
            )
        )
        messages = state.messages()
        self.assertEqual(messages[0].content, "12345 [truncated]")
