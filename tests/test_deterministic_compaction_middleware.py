from __future__ import annotations

import unittest
from collections.abc import Sequence

from vidbyte.context.compaction import CompactionMode, ContextCompactionEngine
from vidbyte.lib.dataclasses.context import ContextMessage
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareHook
from vidbyte.lib.dataclasses.tools import ToolCall as RuntimeToolCall
from vidbyte.lib.dataclasses.tools import ToolResult as RuntimeToolResult
from vidbyte.middleware.builtins import MessageHistoryCompactionMiddleware, ToolResultCompactionMiddleware
from vidbyte.tools.builtins.context import ContextCompactionTool
from vidbyte.tools.types import ToolCall


def msg(role: str, content: str, kind: str = "message", **metadata: object) -> ContextMessage:
    # Builds a compact ContextMessage for strategy tests.
    return ContextMessage(role=role, content=content, kind=kind, metadata=metadata)


class MemoryState:
    """In-memory context state for legacy compaction tool tests."""

    def __init__(self, messages: Sequence[ContextMessage]) -> None:
        # Stores the initial mutable message list.
        self._messages = list(messages)

    def messages(self) -> Sequence[ContextMessage]:
        # Returns the current context messages.
        return tuple(self._messages)

    def replace_messages(self, messages: Sequence[ContextMessage]) -> None:
        # Replaces the current context messages after successful compaction.
        self._messages = list(messages)


class DeterministicStrategyTests(unittest.IsolatedAsyncioTestCase):
    """Covers deterministic compaction strategies added to middleware."""

    async def test_trim_to_token_budget_edge_empty(self) -> None:
        # [Edge Case] Empty message history remains empty.
        after, stats = await ContextCompactionEngine().compact_messages((), mode=CompactionMode.TRIM_TO_TOKEN_BUDGET, options={"max_tokens": 10})
        self.assertEqual(after, ())
        self.assertEqual(stats.after_count, 0)

    async def test_trim_to_token_budget_exact_budget(self) -> None:
        # [Edge Case] Exact budget keeps all messages.
        messages = (msg("user", "a"), msg("assistant", "b"))
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.TRIM_TO_TOKEN_BUDGET, options={"max_tokens": 2, "token_counter": lambda text: 1})
        self.assertEqual(after, messages)

    async def test_trim_to_token_budget_preserves_system_when_tiny(self) -> None:
        # [Hidden Failure] System messages remain even when they exceed the budget.
        messages = (msg("system", "rules rules"), msg("user", "drop me"))
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.TRIM_TO_TOKEN_BUDGET, options={"max_tokens": 0})
        self.assertEqual(tuple(m.role for m in after), ("system",))

    async def test_trim_to_token_budget_original_order_and_counter(self) -> None:
        # [Silent Failure] Injected token counters are used and kept messages stay chronological.
        messages = (msg("system", "sys"), msg("user", "old"), msg("assistant", "new"))
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.TRIM_TO_TOKEN_BUDGET, options={"max_tokens": 2, "token_counter": lambda text: 1})
        self.assertEqual(tuple(m.content for m in after), ("sys", "new"))

    async def test_trim_with_provider_boundaries_without_tools(self) -> None:
        # [Edge Case] No-tool histories behave like keep-last trimming.
        messages = (msg("user", "a"), msg("assistant", "b"), msg("user", "c"))
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.TRIM_WITH_PROVIDER_BOUNDARIES, options={"max_messages": 2})
        self.assertEqual(tuple(m.content for m in after), ("b", "c"))

    async def test_trim_with_provider_boundaries_repairs_orphans(self) -> None:
        # [Hidden Failure] A retained tool_result pulls in its adjacent tool_call.
        messages = (msg("assistant", "call", "tool_call"), msg("tool", "result", "tool_result"))
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.TRIM_WITH_PROVIDER_BOUNDARIES, options={"max_messages": 1})
        self.assertEqual(tuple(m.kind for m in after), ("tool_call", "tool_result"))

    async def test_trim_with_provider_boundaries_keeps_newer_group(self) -> None:
        # [Silent Failure] Newer tool groups are preferred over older groups.
        messages = (msg("assistant", "old call", "tool_call"), msg("tool", "old result", "tool_result"), msg("assistant", "new call", "tool_call"), msg("tool", "new result", "tool_result"))
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.TRIM_WITH_PROVIDER_BOUNDARIES, options={"max_messages": 2})
        self.assertEqual(tuple(m.content for m in after), ("new call", "new result"))

    async def test_trim_with_provider_boundaries_provider_dicts(self) -> None:
        # [Hidden Assumption] Unknown provider dictionaries survive conversion and trimming.
        provider = ({"role": "assistant", "content": "old", "unknown": True}, {"role": "assistant", "content": "new"})
        after, _ = await ContextCompactionEngine().compact_provider_messages(provider, mode=CompactionMode.TRIM_WITH_PROVIDER_BOUNDARIES, options={"max_messages": 1})
        self.assertEqual(after[0]["content"], "new")

    async def test_delete_messages_empty_keeps_all(self) -> None:
        # [Edge Case] No IDs and no range leaves messages unchanged.
        messages = (msg("user", "a"), msg("assistant", "b"))
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.DELETE_MESSAGES_BY_ID_OR_RANGE)
        self.assertEqual(after, messages)

    async def test_delete_messages_missing_ids_ignore_unrelated(self) -> None:
        # [Hidden Failure] Missing IDs do not delete unrelated records.
        messages = (msg("user", "a", id="one"), msg("assistant", "b", id="two"))
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.DELETE_MESSAGES_BY_ID_OR_RANGE, options={"message_ids": ("missing",)})
        self.assertEqual(after, messages)

    async def test_delete_messages_range_is_inclusive_and_provider_index_supported(self) -> None:
        # [Silent Failure] End index is inclusive and provider_index can be targeted.
        messages = (msg("user", "a", provider_index=10), msg("assistant", "b"), msg("user", "c"))
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.DELETE_MESSAGES_BY_ID_OR_RANGE, options={"start": 1, "end": 2})
        self.assertEqual(tuple(m.content for m in after), ("a",))
        after2, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.DELETE_MESSAGES_BY_ID_OR_RANGE, options={"message_ids": ("10",)})
        self.assertEqual(tuple(m.content for m in after2), ("b", "c"))

    async def test_tool_output_sliding_window_compacts_all_with_zero(self) -> None:
        # [Edge Case] keep_recent=0 compacts every tool result.
        messages = (msg("tool", "123456", "tool_result", tool_name="lookup"),)
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.TOOL_OUTPUT_SLIDING_WINDOW, options={"keep_recent": 0, "max_chars": 3})
        self.assertIn("truncated", after[0].content)

    async def test_tool_output_sliding_window_preserves_non_tool_and_newest(self) -> None:
        # [Silent Failure] Non-tool messages stay raw and newest tool output is preserved.
        messages = (msg("user", "keep"), msg("tool", "old-output", "tool_result", tool_name="lookup"), msg("tool", "new-output", "tool_result", tool_name="lookup"))
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.TOOL_OUTPUT_SLIDING_WINDOW, options={"keep_recent": 1, "max_chars": 3})
        self.assertEqual(after[0].content, "keep")
        self.assertIn("truncated", after[1].content)
        self.assertEqual(after[2].content, "new-output")

    async def test_tool_output_sliding_window_rejects_bad_submode(self) -> None:
        # [Hidden Assumption] Unsupported window sub-modes fail during strategy construction.
        with self.assertRaises(ValueError):
            await ContextCompactionEngine().compact_messages((msg("tool", "x", "tool_result"),), mode=CompactionMode.TOOL_OUTPUT_SLIDING_WINDOW, options={"window_mode": "not_a_mode"})

    async def test_clear_tool_results_exclusions_and_metadata(self) -> None:
        # [Edge Case] Empty exclusions clear all results and record original size.
        messages = (msg("tool", "secret", "tool_result"),)
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.TOOL_RESULT_CLEARING_WITH_EXCLUSIONS)
        self.assertEqual(after[0].content, "[tool result cleared by compaction]")
        self.assertEqual(after[0].metadata["original_chars"], 6)

    async def test_clear_tool_results_preserves_excluded_names(self) -> None:
        # [Hidden Failure] Excluded tool names remain visible.
        messages = (msg("tool", "safe", "tool_result", tool_name="audit"), msg("tool", "hide", "tool_result"))
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.TOOL_RESULT_CLEARING_WITH_EXCLUSIONS, options={"exclude_tools": ("audit",)})
        self.assertEqual(tuple(m.content for m in after), ("safe", "[tool result cleared by compaction]"))

    async def test_head_tail_preview_short_content_and_counts(self) -> None:
        # [Edge Case] Short content is unchanged and long content gets the correct omitted count.
        messages = (msg("tool", "short", "tool_result"), msg("tool", "abcdefghi", "tool_result"))
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.HEAD_TAIL_TOOL_PREVIEW, options={"head_chars": 3, "tail_chars": 2})
        self.assertEqual(after[0].content, "short")
        self.assertIn("abc", after[1].content)
        self.assertIn("hi", after[1].content)
        self.assertEqual(after[1].metadata["omitted_chars"], 4)

    async def test_head_tail_preview_head_zero_and_validation(self) -> None:
        # [Hidden Failure] head=0 keeps the tail and negative sizes are rejected.
        after, _ = await ContextCompactionEngine().compact_messages((msg("tool", "abcdef", "tool_result"),), mode=CompactionMode.HEAD_TAIL_TOOL_PREVIEW, options={"head_chars": 0, "tail_chars": 2})
        self.assertTrue(after[0].content.endswith("ef"))
        with self.assertRaises(ValueError):
            await ContextCompactionEngine().compact_messages((msg("tool", "abcdef", "tool_result"),), mode=CompactionMode.HEAD_TAIL_TOOL_PREVIEW, options={"head_chars": -1})

    async def test_mechanical_bloat_scrubber_variants(self) -> None:
        # [Hidden Failure] ANSI, base64-like spans, and repeated lines are scrubbed deterministically.
        blob = "A" * 90
        content = "\x1b[31mred\x1b[0m\n" + blob + "\nline\nline\nline"
        after, _ = await ContextCompactionEngine().compact_messages((msg("tool", content, "tool_result"),), mode=CompactionMode.MECHANICAL_BLOAT_SCRUBBER, options={"max_repeated_lines": 1})
        self.assertNotIn("\x1b", after[0].content)
        self.assertIn("[scrubbed base64: 90 chars]", after[0].content)
        self.assertEqual(after[0].content.count("line"), 1)

    async def test_mechanical_bloat_scrubber_no_bloat_unchanged(self) -> None:
        # [Edge Case] Content without mechanical bloat remains byte-for-byte unchanged.
        messages = (msg("assistant", "normal text"),)
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.MECHANICAL_BLOAT_SCRUBBER)
        self.assertEqual(after, messages)

    async def test_summary_with_backrefs_range_metadata_and_excerpt(self) -> None:
        # [Hidden Failure] Summary metadata records source IDs and excerpts are bounded.
        messages = (msg("user", "keep", id="a"), msg("assistant", "long-message-body", id="b"))
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.SUMMARY_WITH_BACKREFS, options={"start": 1, "end": 1, "excerpt_chars": 4})
        self.assertEqual(after[1].kind, "summary")
        self.assertEqual(after[1].metadata["source_ids"], ("b",))
        self.assertIn("long", after[1].content)
        self.assertNotIn("message-body", after[1].content)

    async def test_summary_with_backrefs_empty_range_keeps_messages(self) -> None:
        # [Edge Case] Empty selected ranges keep the original history.
        messages = (msg("user", "a"),)
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.SUMMARY_WITH_BACKREFS, options={"start": 1, "end": 0})
        self.assertEqual(after, messages)

    async def test_selective_pruning_preserves_first_system_and_patterns(self) -> None:
        # [Hidden Assumption] Duplicate, empty, and boilerplate messages are pruned but system remains.
        messages = (msg("system", "boilerplate"), msg("user", ""), msg("assistant", "dup"), msg("assistant", "dup"), msg("assistant", "remove me"))
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.SELECTIVE_CONTEXT_PRUNING, options={"boilerplate_patterns": ("remove",)})
        self.assertEqual(tuple(m.content for m in after), ("boilerplate", "dup"))

    async def test_selective_pruning_single_message_and_unique_terms(self) -> None:
        # [Edge Case] A single useful message is preserved when it meets term thresholds.
        messages = (msg("assistant", "alpha beta"), msg("assistant", "alpha"))
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.SELECTIVE_CONTEXT_PRUNING, options={"min_unique_terms": 2})
        self.assertEqual(tuple(m.content for m in after), ("alpha beta",))

    async def test_salience_eviction_pinned_error_and_chronology(self) -> None:
        # [Hidden Failure] Pinned metadata and tool errors outrank ordinary messages, returned chronologically.
        messages = (msg("assistant", "ordinary"), msg("tool", "success", "tool_result", status="success"), msg("tool", "error", "tool_result", status="error"), msg("assistant", "pinned", pinned=True))
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.SALIENCE_SCORE_EVICTION, options={"max_messages": 2})
        self.assertEqual(tuple(m.content for m in after), ("error", "pinned"))

    async def test_salience_eviction_large_cap_keeps_all(self) -> None:
        # [Edge Case] A cap larger than the history count keeps all messages.
        messages = (msg("user", "a"), msg("assistant", "b"))
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.SALIENCE_SCORE_EVICTION, options={"max_messages": 5})
        self.assertEqual(after, messages)

    async def test_query_relevance_empty_query_and_lexical_matching(self) -> None:
        # [Hidden Assumption] Empty queries keep system/recent only, and punctuation/case tokenization is stable.
        messages = (msg("system", "rules"), msg("user", "Billing, invoice!"), msg("assistant", "shipping"), msg("assistant", "recent"))
        empty, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.QUERY_RELEVANCE_FILTER, options={"query": "", "keep_recent": 1})
        self.assertEqual(tuple(m.content for m in empty), ("rules", "recent"))
        relevant, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.QUERY_RELEVANCE_FILTER, options={"query": "billing invoice", "min_score": 2})
        self.assertEqual(tuple(m.content for m in relevant), ("rules", "Billing, invoice!"))

    async def test_context_snapshot_branch_trim(self) -> None:
        # [Silent Failure] Active and ancestor branch messages are kept while sibling branches are removed.
        messages = (msg("system", "rules"), msg("assistant", "root", branch_id="root"), msg("assistant", "sibling", branch_id="sibling"), msg("assistant", "active", branch_id="active", parent_branch_id="root"), msg("assistant", "untagged"))
        after, _ = await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.CONTEXT_SNAPSHOT_BRANCH_TRIM, options={"active_branch": "active"})
        self.assertEqual(tuple(m.content for m in after), ("rules", "root", "active", "untagged"))
        with self.assertRaises(ValueError):
            await ContextCompactionEngine().compact_messages(messages, mode=CompactionMode.CONTEXT_SNAPSHOT_BRANCH_TRIM, options={"active_branch": ""})


class DeterministicMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    """Covers deterministic middleware factories and compatibility hooks."""

    async def test_tool_result_head_tail_skips_internal_tools(self) -> None:
        # [Edge Case] Tool-result preview skips internal tools by default.
        middleware = ToolResultCompactionMiddleware.head_tail_preview(head_chars=2, tail_chars=2)
        decision = await middleware.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="agent", tool_call=RuntimeToolCall("isDone"), tool_result=RuntimeToolResult.success("isDone", "abcdef"), tool_is_internal=True))
        self.assertIsNone(decision.transform)

    async def test_tool_result_clear_except_preserves_excluded_tool(self) -> None:
        # [Hidden Failure] Excluded tool raw output is preserved in the visible result.
        middleware = ToolResultCompactionMiddleware.clear_except(exclude_tools=("audit",))
        raw = RuntimeToolResult.success("audit", "keep me")
        decision = await middleware.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="agent", tool_call=RuntimeToolCall("audit"), tool_result=raw))
        self.assertEqual(decision.transform.model_visible_tool_result.output, "keep me")

    async def test_tool_result_scrub_bloat_leaves_raw_unchanged(self) -> None:
        # [Silent Failure] The transformed visible result changes while the raw result object is unchanged.
        middleware = ToolResultCompactionMiddleware.scrub_bloat(base64_min_chars=10)
        raw = RuntimeToolResult.success("lookup", "x " + ("A" * 20) + " y")
        decision = await middleware.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="agent", tool_call=RuntimeToolCall("lookup"), tool_result=raw))
        self.assertIn("[scrubbed base64: 20 chars]", decision.transform.model_visible_tool_result.output)
        self.assertEqual(raw.output, "x " + ("A" * 20) + " y")

    async def test_query_relevance_factory_uses_current_message(self) -> None:
        # [Hidden Assumption] query=None injects ctx.message during before_model_call.
        middleware = MessageHistoryCompactionMiddleware.query_relevance_filter(query=None)
        provider_messages = ({"role": "system", "content": "rules"}, {"role": "assistant", "content": "billing invoice"}, {"role": "assistant", "content": "shipping"})
        decision = await middleware.before_model_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_MODEL_CALL, agent_name="agent", message="billing invoice", provider_messages=provider_messages))
        self.assertEqual(tuple(m["content"] for m in decision.transform.provider_messages), ("rules", "billing invoice"))

    async def test_new_factories_validate_constructor_values(self) -> None:
        # [Hidden Assumption] Invalid public factory bounds fail before runtime.
        with self.assertRaises(ValueError):
            ToolResultCompactionMiddleware.head_tail_preview(head_chars=-1)
        with self.assertRaises(ValueError):
            MessageHistoryCompactionMiddleware.trim_to_token_budget(max_tokens=-1)
        with self.assertRaises(ValueError):
            MessageHistoryCompactionMiddleware.context_snapshot_branch_trim(active_branch="")

    async def test_legacy_tool_supports_head_tail_preview(self) -> None:
        # [Edge Case] ContextCompactionTool delegates new head/tail preview mode.
        state = MemoryState((msg("tool", "abcdefghi", "tool_result"),))
        result = await ContextCompactionTool(state).execute(ToolCall("compact_context", {"mode": CompactionMode.HEAD_TAIL_TOOL_PREVIEW.value, "head_chars": 3, "tail_chars": 2}))
        self.assertEqual(result.status.value, "success")
        self.assertIn("abc", state.messages()[0].content)
        self.assertIn("hi", state.messages()[0].content)

    async def test_legacy_tool_invalid_max_tokens_returns_error(self) -> None:
        # [Hidden Failure] Invalid token budgets are reported as tool errors.
        state = MemoryState((msg("user", "a"),))
        result = await ContextCompactionTool(state).execute(ToolCall("compact_context", {"mode": CompactionMode.TRIM_TO_TOKEN_BUDGET.value, "max_tokens": -1}))
        self.assertEqual(result.status.value, "error")

    async def test_legacy_tool_summary_counts_and_bad_mode(self) -> None:
        # [Silent Failure] Summary mode reports before/after counts and bad modes still map to bad_mode.
        state = MemoryState((msg("user", "a"), msg("assistant", "b")))
        result = await ContextCompactionTool(state).execute(ToolCall("compact_context", {"mode": CompactionMode.SUMMARY_WITH_BACKREFS.value, "start": 0, "end": 1}))
        self.assertEqual(result.metadata["before_count"], 2)
        self.assertEqual(result.metadata["after_count"], 1)
        bad = await ContextCompactionTool(state).execute(ToolCall("compact_context", {"mode": "query_relevance_filter_typo"}))
        self.assertEqual(bad.metadata["error"], "bad_mode")


if __name__ == "__main__":
    unittest.main()
