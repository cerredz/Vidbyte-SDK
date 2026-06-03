from __future__ import annotations

import unittest

from vidbyte.context import ContextManager, ContextWindowLifecycleEvent, ContextWindowPlacement, ContextWindowRunContext, InnerContextWindowAlgorithm, TextContextItem
from vidbyte.context.templates import ContextWindowRecorder
from vidbyte.lib.dataclasses.agents import AgentIterationSnapshot


def _ctx(iteration: AgentIterationSnapshot | None = None) -> ContextWindowRunContext:
    return ContextWindowRunContext(
        event=ContextWindowLifecycleEvent.AFTER_ITERATION,
        context_manager=ContextManager(),
        recorder=ContextWindowRecorder(),
        metadata={},
        message="task",
        provider="openai",
        iteration=iteration,
    )


class ContextWindowRunContextTests(unittest.TestCase):
    def test_run_context_upsert_writes_to_context_manager(self) -> None:
        ctx = _ctx()
        item = TextContextItem(primitive_id="note:1", title="Note", content="body")

        ctx.upsert(item)

        self.assertIs(ctx.context_manager.get_by_id("note:1"), item)

    def test_run_context_append_generates_stable_primitive_id(self) -> None:
        ctx = _ctx()

        primitive_id = ctx.append(TextContextItem(title="Note", content="body"))

        self.assertEqual(primitive_id, "text:1")
        self.assertIsNotNone(ctx.context_manager.get_by_id("text:1"))

    def test_run_context_remove_deletes_primitive(self) -> None:
        ctx = _ctx()
        ctx.upsert(TextContextItem(primitive_id="note:1", title="Note", content="body"))

        ctx.remove("note:1")

        self.assertIsNone(ctx.context_manager.get_by_id("note:1"))

    def test_run_context_record_delegates_to_recorder(self) -> None:
        ctx = _ctx()

        ctx.record("slot", iteration=2)

        self.assertEqual(ctx.recorder.slots(), ("slot",))

    def test_run_context_set_metadata_preserves_existing_keys(self) -> None:
        ctx = _ctx()
        ctx.set_metadata("a", 1)

        ctx.set_metadata("b", 2)

        self.assertEqual(ctx.metadata["a"], 1)
        self.assertEqual(ctx.metadata["b"], 2)

    def test_run_context_every_rejects_zero_iterations(self) -> None:
        ctx = _ctx(AgentIterationSnapshot(iteration_count=2, message="task", provider="openai"))

        with self.assertRaises(ValueError):
            ctx.every(iterations=0)

    def test_run_context_every_false_without_iteration_snapshot(self) -> None:
        ctx = _ctx()

        self.assertFalse(ctx.every(iterations=1))

    def test_inner_algorithm_default_hooks_are_noops(self) -> None:
        algorithm = InnerContextWindowAlgorithm()
        ctx = _ctx()

        algorithm.on_run_start(ctx)
        algorithm.before_model_call(ctx)
        algorithm.after_model_response(ctx)
        algorithm.after_tool_call(ctx)
        algorithm.after_iteration(ctx)
        algorithm.on_run_end(ctx)

        self.assertEqual(ctx.metadata, {})

    def test_run_context_upsert_records_placement(self) -> None:
        ctx = _ctx()
        item = TextContextItem(primitive_id="note:top", title="Note", content="body")

        ctx.upsert(item, placement=ContextWindowPlacement.TOP_OF_CONTEXT)

        self.assertEqual(ctx.context_manager.placement_for("note:top"), ContextWindowPlacement.TOP_OF_CONTEXT)


if __name__ == "__main__":
    unittest.main()
