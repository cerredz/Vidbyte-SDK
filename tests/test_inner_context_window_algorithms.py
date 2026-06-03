from __future__ import annotations

import unittest

from vidbyte.context import ContextManager, ContextWindowPlacement, ContextWindowRunContext, InnerContextWindowAlgorithm, TextContextItem
from vidbyte.context.templates import ContextWindowRecorder
from vidbyte.lib.dataclasses.agents import AgentIterationSnapshot


def _ctx(iteration: AgentIterationSnapshot | None = None) -> ContextWindowRunContext:
    return ContextWindowRunContext(
        context_manager=ContextManager(),
        recorder=ContextWindowRecorder(),
        state={},
        iteration=iteration,
    )


class ContextWindowRunContextTests(unittest.IsolatedAsyncioTestCase):
    def test_place_after_tools_writes_to_context_manager(self) -> None:
        ctx = _ctx()
        item = TextContextItem(primitive_id="note:1", title="Note", content="body")

        primitive_id = ctx.place_after_tools(item)

        self.assertEqual(primitive_id, "note:1")
        self.assertIs(ctx.context_manager.get_by_id("note:1"), item)
        self.assertEqual(ctx.context_manager.placement_for("note:1"), ContextWindowPlacement.END_OF_CONTEXT)

    def test_place_after_system_prompt_sets_top_placement(self) -> None:
        ctx = _ctx()
        item = TextContextItem(primitive_id="note:top", title="Note", content="body")

        ctx.place_after_system_prompt(item)

        self.assertEqual(ctx.context_manager.placement_for("note:top"), ContextWindowPlacement.TOP_OF_CONTEXT)

    def test_place_generates_stable_primitive_id(self) -> None:
        ctx = _ctx()

        primitive_id = ctx.place_after_tools(TextContextItem(title="Note", content="body"))

        self.assertEqual(primitive_id, "text:1")
        self.assertIsNotNone(ctx.context_manager.get_by_id("text:1"))

    def test_run_context_remove_deletes_primitive(self) -> None:
        ctx = _ctx()
        ctx.place_after_tools(TextContextItem(primitive_id="note:1", title="Note", content="body"))

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

        self.assertEqual(ctx.state["a"], 1)
        self.assertEqual(ctx.state["b"], 2)

    async def test_inner_algorithm_default_hook_is_noop(self) -> None:
        # [Edge Case] Verify default after_tool_calls is a no-op coroutine.
        algorithm = InnerContextWindowAlgorithm()
        ctx = _ctx()
        await algorithm.after_tool_calls(ctx)
        self.assertEqual(ctx.state, {})


if __name__ == "__main__":
    unittest.main()
