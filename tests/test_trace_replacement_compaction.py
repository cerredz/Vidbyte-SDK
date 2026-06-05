from __future__ import annotations

import unittest

from vidbyte.lib.dataclasses.context import ContextMessage
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareHook
from vidbyte.middleware.compaction import CompactionMode, ReplaceWithTraceCompaction, TraceArtifactRenderer
from vidbyte.middleware.builtins import TraceReplacementCompactionMiddleware, TraceSummaryTailCompactionMiddleware


def _ctx(provider_messages, run_state=None):
    # Builds a minimal before-model-call middleware context for tests.
    return MiddlewareContext(hook=MiddlewareHook.BEFORE_MODEL_CALL, agent_name="t", provider_messages=tuple(provider_messages), run_state=dict(run_state or {}))


def _provider_history():
    # Returns a small provider-message history with a tool-call/result pair and a trailing user turn.
    return [
        {"role": "user", "content": "do X"},
        {"role": "assistant", "tool_calls": [{"id": "c1", "function": {"name": "lookup"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "RESULT"},
        {"role": "assistant", "content": "thinking"},
        {"role": "user", "content": "now Y"},
    ]


_ARTIFACT = {"goal": "ship it", "actions_taken": ["a", "b", "c"], "mistakes": [], "current_status": "in progress"}


class FakeSummarizer:
    async def summarize(self, messages):
        # Returns a deterministic summary exposing the summarized message count.
        return f"summary of {len(messages)} messages"


class TraceArtifactRendererTests(unittest.TestCase):
    def test_renders_scalar_and_array_fields(self) -> None:
        # [Edge Case] scalars render inline, arrays render as bullet lists.
        text = TraceArtifactRenderer().render(_ARTIFACT)
        self.assertIn("## goal\nship it", text)
        self.assertIn("- a", text)
        self.assertIn("- b", text)

    def test_field_subset_keeps_only_requested_fields_in_order(self) -> None:
        # [Silent Failure] wrong field selection or order would surface here.
        text = TraceArtifactRenderer(fields=["current_status", "goal"]).render(_ARTIFACT)
        self.assertLess(text.index("current_status"), text.index("goal"))
        self.assertNotIn("actions_taken", text)

    def test_field_subset_absent_key_does_not_crash(self) -> None:
        # [Hidden Assumption] a requested field missing from the artifact is skipped.
        text = TraceArtifactRenderer(fields=["nope", "goal"]).render(_ARTIFACT)
        self.assertIn("goal", text)

    def test_max_chars_never_exceeds_bound(self) -> None:
        # [Silent Failure] truncation including the marker must stay within max_chars.
        text = TraceArtifactRenderer(max_chars=30).render(_ARTIFACT)
        self.assertLessEqual(len(text), 30)

    def test_max_chars_smaller_than_marker_returns_bounded_text(self) -> None:
        # [Edge Case] no negative slice when max_chars is tiny.
        text = TraceArtifactRenderer(max_chars=5).render(_ARTIFACT)
        self.assertLessEqual(len(text), 5)

    def test_array_head_tail_elides_middle(self) -> None:
        # [Edge Case] long arrays keep head/tail with an omitted-count marker.
        artifact = {"actions_taken": [f"step{i}" for i in range(10)]}
        text = TraceArtifactRenderer(array_head=1, array_tail=1).render(artifact)
        self.assertIn("- step0", text)
        self.assertIn("- step9", text)
        self.assertIn("omitted", text)

    def test_max_tokens_drops_oldest_array_entries_first(self) -> None:
        # [Silent Failure] token trimming must drop the oldest (front) entries first.
        artifact = {"actions_taken": ["oldest", "mid", "newest"]}
        text = TraceArtifactRenderer(max_tokens=8, token_counter=lambda s: len(s.split())).render(artifact)
        self.assertIn("newest", text)
        self.assertNotIn("oldest", text)

    def test_is_empty_true_for_blank_artifacts(self) -> None:
        # [Hidden Assumption] None / {} / all-None / empty collections count as empty.
        for artifact in (None, {}, {"a": None, "b": []}, {"a": "  "}):
            self.assertTrue(TraceArtifactRenderer.is_empty(artifact))

    def test_is_empty_false_when_any_content(self) -> None:
        # [Edge Case] any populated field makes the artifact non-empty.
        self.assertFalse(TraceArtifactRenderer.is_empty({"a": None, "b": ["x"]}))


class ReplaceWithTraceCompactionTests(unittest.IsolatedAsyncioTestCase):
    def _messages(self):
        # Returns context messages with system, a tool group, and a trailing user turn.
        return [
            ContextMessage(role="system", content="SYS"),
            ContextMessage(role="user", content="do X"),
            ContextMessage(role="assistant", content="", kind="tool_call"),
            ContextMessage(role="tool", content="RESULT", kind="tool_result"),
            ContextMessage(role="assistant", content="thinking"),
            ContextMessage(role="user", content="now Y"),
        ]

    async def test_empty_trace_returns_unchanged(self) -> None:
        # [Hidden Assumption] an empty trace must never replace real history.
        out = await ReplaceWithTraceCompaction("   ").compact(self._messages())
        self.assertEqual(len(out), 6)

    async def test_all_non_system_injects_single_summary(self) -> None:
        # [Edge Case] system kept, all non-system collapsed to one trace summary.
        out = await ReplaceWithTraceCompaction("TRACE").compact(self._messages())
        self.assertEqual([(m.role, m.kind) for m in out], [("system", "message"), ("assistant", "summary")])

    async def test_system_suffix_places_trace_in_system_block(self) -> None:
        # [Edge Case] system_suffix appends the trace as a system message.
        out = await ReplaceWithTraceCompaction("TRACE", placement="system_suffix").compact(self._messages())
        self.assertEqual([m.role for m in out], ["system", "system"])

    async def test_synthetic_user_uses_user_role(self) -> None:
        # [Edge Case] synthetic_user injects the trace as a user message.
        out = await ReplaceWithTraceCompaction("TRACE", placement="synthetic_user").compact(self._messages())
        self.assertEqual(out[1].role, "user")

    async def test_keep_last_groups_preserves_tail_pair(self) -> None:
        # [Hidden Failure] keeping a tail must not orphan a tool_result from its tool_call.
        out = await ReplaceWithTraceCompaction("TRACE", keep_last_groups=3).compact(self._messages())
        kinds = [m.kind for m in out]
        self.assertEqual(kinds.count("tool_call"), kinds.count("tool_result"))

    async def test_oldest_n_groups_replaces_only_oldest(self) -> None:
        # [Edge Case] oldest_n_groups replaces the first group only.
        out = await ReplaceWithTraceCompaction("TRACE", scope="oldest_n_groups", n=1).compact(self._messages())
        self.assertEqual(out[1].kind, "summary")
        self.assertTrue(any(m.kind == "tool_result" for m in out))

    async def test_oldest_percentage_uses_ceil(self) -> None:
        # [Silent Failure] ceil rounding selects at least one group for any positive percentage.
        out = await ReplaceWithTraceCompaction("TRACE", scope="oldest_percentage", percentage=0.1).compact(self._messages())
        self.assertTrue(any(m.kind == "summary" for m in out))

    async def test_keep_pinned_protects_pinned_message(self) -> None:
        # [Edge Case] pinned messages survive replacement.
        messages = self._messages()
        messages[1] = ContextMessage(role="user", content="pinned ask", metadata={"pinned": True})
        out = await ReplaceWithTraceCompaction("TRACE", keep_pinned=True).compact(messages)
        self.assertTrue(any(m.content == "pinned ask" for m in out))

    async def test_keep_errors_protects_error_results(self) -> None:
        # [Edge Case] error tool results survive replacement.
        messages = self._messages()
        messages[3] = ContextMessage(role="tool", content="boom", kind="tool_result", metadata={"status": "error"})
        out = await ReplaceWithTraceCompaction("TRACE", keep_errors=True).compact(messages)
        self.assertTrue(any(m.content == "boom" for m in out))

    async def test_keep_active_branch_drops_sibling_only(self) -> None:
        # [Edge Case] active branch and unbranched messages survive; sibling branch is replaced.
        messages = [
            ContextMessage(role="system", content="SYS"),
            ContextMessage(role="user", content="sibling", metadata={"branch": "b2"}),
            ContextMessage(role="user", content="active", metadata={"branch": "b1"}),
        ]
        out = await ReplaceWithTraceCompaction("TRACE", keep_active_branch="b1").compact(messages)
        contents = [m.content for m in out]
        self.assertIn("active", contents)
        self.assertNotIn("sibling", contents)

    async def test_full_retention_returns_unchanged(self) -> None:
        # [Silent Failure] when retention protects everything, no trace is injected.
        messages = [ContextMessage(role="system", content="SYS"), ContextMessage(role="user", content="only")]
        out = await ReplaceWithTraceCompaction("TRACE", keep_last_groups=5).compact(messages)
        self.assertEqual([m.content for m in out], ["SYS", "only"])

    async def test_stale_trace_marker_is_replaced_not_stacked(self) -> None:
        # [Hidden Failure] a prior trace message is rebuilt, never duplicated.
        messages = [
            ContextMessage(role="system", content="SYS"),
            ContextMessage(role="assistant", content="OLD TRACE", kind="summary", metadata={"trace_marker": "continual_trace"}),
            ContextMessage(role="user", content="now Y"),
        ]
        out = await ReplaceWithTraceCompaction("NEW TRACE", keep_last_groups=1).compact(messages)
        summaries = [m.content for m in out if m.kind == "summary"]
        self.assertEqual(summaries, ["NEW TRACE"])

    async def test_no_non_system_still_injects_trace(self) -> None:
        # [Edge Case] an empty conversation still yields a valid system+trace window.
        out = await ReplaceWithTraceCompaction("TRACE").compact([ContextMessage(role="system", content="SYS")])
        self.assertEqual([(m.role, m.content) for m in out], [("system", "SYS"), ("assistant", "TRACE")])

    async def test_invalid_options_raise(self) -> None:
        # [Hidden Assumption] bad scope/placement/percentage fail loudly at construction.
        with self.assertRaises(ValueError):
            ReplaceWithTraceCompaction("T", scope="bogus")
        with self.assertRaises(ValueError):
            ReplaceWithTraceCompaction("T", placement="bogus")
        with self.assertRaises(ValueError):
            ReplaceWithTraceCompaction("T", percentage=2)


class TraceReplacementMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_artifact_from_run_state(self) -> None:
        # [Edge Case] artifact published in run_state drives the replacement.
        mw = TraceReplacementCompactionMiddleware.replace_all_with_trace(keep_last_user=False)
        ctx = _ctx(_provider_history(), run_state={"__result_metadata__": {"trace": _ARTIFACT}})
        decision = await mw.before_model_call(ctx)
        self.assertIsNotNone(decision.transform)
        self.assertEqual(len(decision.transform.provider_messages), 1)

    async def test_injected_artifact_overrides_run_state(self) -> None:
        # [Hidden Assumption] an injected artifact takes precedence over run_state.
        mw = TraceReplacementCompactionMiddleware(artifact=_ARTIFACT)
        decision = await mw.before_model_call(_ctx(_provider_history()))
        self.assertIsNotNone(decision.transform)

    async def test_empty_artifact_triggers_fallback(self) -> None:
        # [Hidden Assumption] an empty artifact must fall back, not replace with nothing.
        mw = TraceReplacementCompactionMiddleware.trace_fallback_to_mechanical(fallback_options={"n": 2})
        ctx = _ctx(_provider_history(), run_state={"__result_metadata__": {"trace": {"goal": None}}})
        decision = await mw.before_model_call(ctx)
        self.assertTrue(decision.transform.metadata.get("fallback_used"))
        self.assertEqual(len(decision.transform.provider_messages), 2)

    async def test_empty_artifact_without_fallback_is_noop(self) -> None:
        # [Silent Failure] no fallback and empty artifact leaves history untouched.
        mw = TraceReplacementCompactionMiddleware()
        decision = await mw.before_model_call(_ctx(_provider_history()))
        self.assertIsNone(decision.transform)

    async def test_no_provider_messages_is_noop(self) -> None:
        # [Edge Case] empty provider history is a no-op.
        mw = TraceReplacementCompactionMiddleware(artifact=_ARTIFACT)
        decision = await mw.before_model_call(_ctx([]))
        self.assertIsNone(decision.transform)

    async def test_refresh_callback_supplies_fresh_artifact(self) -> None:
        # [Edge Case] a refresh callback provides the artifact when configured.
        async def refresh(ctx):
            return _ARTIFACT
        mw = TraceReplacementCompactionMiddleware.with_refresh(refresh)
        decision = await mw.before_model_call(_ctx(_provider_history()))
        self.assertIsNotNone(decision.transform)

    async def test_refresh_callback_failure_falls_back_to_run_state(self) -> None:
        # [Hidden Failure] a raising refresh callback falls back to the stale run_state artifact.
        async def refresh(ctx):
            raise RuntimeError("boom")
        mw = TraceReplacementCompactionMiddleware.with_refresh(refresh, keep_last_user=False)
        ctx = _ctx(_provider_history(), run_state={"__result_metadata__": {"trace": _ARTIFACT}})
        decision = await mw.before_model_call(ctx)
        self.assertIsNotNone(decision.transform)

    async def test_artifact_provider_non_mapping_is_empty(self) -> None:
        # [Silent Failure] a provider returning a non-Mapping is treated as no artifact.
        mw = TraceReplacementCompactionMiddleware(artifact_provider=lambda ctx: ["not", "a", "map"])
        decision = await mw.before_model_call(_ctx(_provider_history()))
        self.assertIsNone(decision.transform)

    async def test_compose_after_strips_kept_tool_results(self) -> None:
        # [Edge Case] composition strips tool-result bodies in the kept tail.
        mw = TraceReplacementCompactionMiddleware.trace_plus_strip_tool_results(keep_last_groups=3, artifact=_ARTIFACT)
        decision = await mw.before_model_call(_ctx(_provider_history()))
        contents = [m.get("content") for m in decision.transform.provider_messages]
        self.assertIn("[tool result stripped by compaction]", contents)

    async def test_transform_metadata_reports_counts(self) -> None:
        # [Silent Failure] transform metadata exposes scope and before/after counts.
        mw = TraceReplacementCompactionMiddleware.replace_all_with_trace(keep_last_user=False, artifact=_ARTIFACT)
        decision = await mw.before_model_call(_ctx(_provider_history()))
        self.assertEqual(decision.transform.metadata["scope"], "all_non_system")
        self.assertEqual(decision.transform.metadata["before_count"], 5)

    async def test_family_presets_construct(self) -> None:
        # [Edge Case] every family preset constructs without error.
        TraceReplacementCompactionMiddleware.keep_recent_tail()
        TraceReplacementCompactionMiddleware.replace_oldest_n_iterations(2)
        TraceReplacementCompactionMiddleware.replace_oldest_percentage(0.5)
        TraceReplacementCompactionMiddleware.replace_middle_keep_bookends()
        TraceReplacementCompactionMiddleware.replace_keep_last_user()
        TraceReplacementCompactionMiddleware.trace_as_system_suffix()
        TraceReplacementCompactionMiddleware.trace_as_synthetic_user()
        TraceReplacementCompactionMiddleware.trace_truncated_chars(100)
        TraceReplacementCompactionMiddleware.trace_field_subset(["goal"])
        TraceReplacementCompactionMiddleware.replace_keep_pinned()
        TraceReplacementCompactionMiddleware.replace_keep_errors()
        TraceReplacementCompactionMiddleware.replace_keep_active_branch("b1")

    async def test_truncated_chars_bounds_injected_trace(self) -> None:
        # [Silent Failure] the injected trace message respects the char bound.
        mw = TraceReplacementCompactionMiddleware.trace_truncated_chars(40, keep_last_user=False, artifact=_ARTIFACT)
        decision = await mw.before_model_call(_ctx(_provider_history()))
        trace_msg = decision.transform.provider_messages[-1]["content"]
        self.assertLessEqual(len(trace_msg), 40)


class TraceSummaryTailMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_replaces_old_and_summarizes_tail(self) -> None:
        # [Edge Case] old history becomes the structured trace; the tail becomes a freeform summary.
        mw = TraceSummaryTailCompactionMiddleware.trace_then_summarize_tail(FakeSummarizer(), keep_last_groups=1, artifact=_ARTIFACT)
        decision = await mw.before_model_call(_ctx(_provider_history()))
        contents = [m.get("content") for m in decision.transform.provider_messages]
        self.assertTrue(any("summary of" in str(c) for c in contents))

    async def test_requires_summarizer(self) -> None:
        # [Hidden Assumption] a missing summarizer fails loudly.
        with self.assertRaises(ValueError):
            TraceSummaryTailCompactionMiddleware(summarizer=None)


class RunStateSharingIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_consumer_reads_producer_run_state(self) -> None:
        # [Hidden Failure] producer and consumer middleware share the same run_state dict.
        run_state: dict = {}
        run_state["__result_metadata__"] = {"trace": _ARTIFACT}  # stand-in for ContinualTraceMiddleware
        mw = TraceReplacementCompactionMiddleware.replace_all_with_trace(keep_last_user=False)
        decision = await mw.before_model_call(_ctx(_provider_history(), run_state=run_state))
        self.assertEqual(len(decision.transform.provider_messages), 1)

    async def test_cold_start_preserves_history(self) -> None:
        # [Hidden Assumption] before the producer writes, history is preserved.
        mw = TraceReplacementCompactionMiddleware.replace_all_with_trace()
        decision = await mw.before_model_call(_ctx(_provider_history(), run_state={}))
        self.assertIsNone(decision.transform)


if __name__ == "__main__":
    unittest.main()
