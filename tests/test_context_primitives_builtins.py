from __future__ import annotations

import unittest

from vidbyte.context import ContextWindowPlacement
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import (
    DocumentContextItem,
    MemoryContextItem,
    PlanContextItem,
    ProgressContextItem,
    TaskContextItem,
    TextContextItem,
)
from vidbyte.tools.builtins.context_primitives import (
    ContextEditTool,
    ContextListTool,
    ContextMoveTool,
    ContextRemoveTool,
    ContextStatsTool,
    ContextUpsertTool,
    ContextViewTool,
    context_window_tools,
)
from vidbyte.tools.types import ToolCall


class ContextListToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_registry_returns_no_primitives_message(self) -> None:
        manager = ContextManager()
        tool = ContextListTool(manager)
        call = ToolCall(tool_name="context_list", arguments={})

        result = await tool.execute(call)

        self.assertIn("No active context window primitives", result.output)

    async def test_populated_registry_lists_all_primitives(self) -> None:
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="note:1", title="Note One", content="body"))
        manager.upsert(PlanContextItem(primitive_id="plan:current", title="My Plan", steps=("step A",)))
        tool = ContextListTool(manager)
        call = ToolCall(tool_name="context_list", arguments={})

        result = await tool.execute(call)

        self.assertIn("note:1", result.output)
        self.assertIn("plan:current", result.output)
        self.assertIn("Note One", result.output)
        self.assertIn("My Plan", result.output)

    async def test_list_shows_frozen_marker_for_frozen_primitives(self) -> None:
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="locked", title="Locked", content="c", primitive_frozen=True))
        tool = ContextListTool(manager)
        call = ToolCall(tool_name="context_list", arguments={})

        result = await tool.execute(call)

        self.assertIn("[frozen]", result.output)

    async def test_list_shows_char_count(self) -> None:
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="x", title="X", content="abc"))
        tool = ContextListTool(manager)
        call = ToolCall(tool_name="context_list", arguments={})

        result = await tool.execute(call)

        self.assertIn("chars", result.output)


class ContextRemoveToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_remove_deletes_existing_primitive(self) -> None:
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="note:1", title="N", content="c"))
        tool = ContextRemoveTool(manager)
        call = ToolCall(tool_name="context_remove", arguments={"primitive_id": "note:1"})

        await tool.execute(call)

        self.assertIsNone(manager.get_by_id("note:1"))

    async def test_remove_is_idempotent_for_missing_id(self) -> None:
        manager = ContextManager()
        tool = ContextRemoveTool(manager)
        call = ToolCall(tool_name="context_remove", arguments={"primitive_id": "ghost:id"})

        result = await tool.execute(call)

        self.assertIn("ghost:id", result.output)

    async def test_remove_refuses_frozen_primitive(self) -> None:
        """Verify the agent-facing remove tool cannot delete developer-owned primitives."""
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="locked", title="L", content="c", primitive_frozen=True))
        tool = ContextRemoveTool(manager)
        call = ToolCall(tool_name="context_remove", arguments={"primitive_id": "locked"})

        result = await tool.execute(call)

        self.assertEqual(result.status.value, "error")
        self.assertIsNotNone(manager.get_by_id("locked"))


class ContextManagementToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_view_returns_rendered_primitive_text(self) -> None:
        """Verify context_view returns the target primitive's rendered text."""
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="note:1", title="Note", content="body"))
        tool = ContextViewTool(manager)

        result = await tool.execute(ToolCall(tool_name="context_view", arguments={"primitive_id": "note:1"}))

        self.assertIn("body", result.output)
        self.assertEqual(result.metadata["primitive_id"], "note:1")

    async def test_view_errors_for_missing_primitive(self) -> None:
        """Verify context_view gives an actionable error for an unknown id."""
        manager = ContextManager()
        tool = ContextViewTool(manager)

        result = await tool.execute(ToolCall(tool_name="context_view", arguments={"primitive_id": "missing"}))

        self.assertEqual(result.status.value, "error")
        self.assertIn("does not exist", result.output)

    async def test_stats_lists_placement_frozen_and_char_count(self) -> None:
        """Verify context_stats includes placement, frozen status, and rendered size."""
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="note:1", title="Note", content="body", primitive_frozen=True), placement=ContextWindowPlacement.TOP_OF_CONTEXT)
        tool = ContextStatsTool(manager)

        result = await tool.execute(ToolCall(tool_name="context_stats", arguments={}))

        self.assertIn("note:1", result.output)
        self.assertIn("placement=top_of_context", result.output)
        self.assertIn("frozen=true", result.output)
        self.assertIn("chars=", result.output)

    async def test_edit_replaces_unique_content_string(self) -> None:
        """Verify context_edit performs one exact replacement on content fields."""
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="note:1", title="Note", content="old body"), placement=ContextWindowPlacement.TOP_OF_CONTEXT)
        tool = ContextEditTool(manager)

        result = await tool.execute(ToolCall(tool_name="context_edit", arguments={"primitive_id": "note:1", "old_string": "old", "new_string": "new"}))

        self.assertEqual(result.status.value, "success")
        stored = manager.get_by_id("note:1")
        assert stored is not None
        self.assertIn("new body", stored.to_context_text())
        self.assertEqual(manager.placement_for("note:1"), ContextWindowPlacement.TOP_OF_CONTEXT)

    async def test_edit_errors_when_old_string_is_absent(self) -> None:
        """Verify context_edit refuses a patch when the old string is not present."""
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="note:1", title="Note", content="body"))
        tool = ContextEditTool(manager)

        result = await tool.execute(ToolCall(tool_name="context_edit", arguments={"primitive_id": "note:1", "old_string": "missing", "new_string": "new"}))

        self.assertEqual(result.status.value, "error")
        self.assertIn("not found", result.output)

    async def test_edit_errors_when_old_string_is_ambiguous(self) -> None:
        """Verify context_edit refuses a patch when the old string appears multiple times."""
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="note:1", title="Note", content="same same"))
        tool = ContextEditTool(manager)

        result = await tool.execute(ToolCall(tool_name="context_edit", arguments={"primitive_id": "note:1", "old_string": "same", "new_string": "new"}))

        self.assertEqual(result.status.value, "error")
        self.assertIn("appears 2 times", result.output)

    async def test_edit_errors_for_primitive_without_content_field(self) -> None:
        """Verify context_edit does not pretend non-content primitives are editable."""
        manager = ContextManager()
        manager.upsert(PlanContextItem(primitive_id="plan:1", steps=("a",)))
        tool = ContextEditTool(manager)

        result = await tool.execute(ToolCall(tool_name="context_edit", arguments={"primitive_id": "plan:1", "old_string": "a", "new_string": "b"}))

        self.assertEqual(result.status.value, "error")
        self.assertIn("no editable string content", result.output)

    async def test_edit_refuses_frozen_primitive(self) -> None:
        """Verify context_edit cannot modify frozen primitives."""
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="locked", title="Locked", content="body", primitive_frozen=True))
        tool = ContextEditTool(manager)

        result = await tool.execute(ToolCall(tool_name="context_edit", arguments={"primitive_id": "locked", "old_string": "body", "new_string": "new"}))

        self.assertEqual(result.status.value, "error")
        self.assertIn("frozen", result.output)

    async def test_move_updates_placement(self) -> None:
        """Verify context_move changes placement without touching content."""
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="note:1", title="Note", content="body"))
        tool = ContextMoveTool(manager)

        result = await tool.execute(ToolCall(tool_name="context_move", arguments={"primitive_id": "note:1", "placement": "top_of_context"}))

        self.assertEqual(result.status.value, "success")
        self.assertEqual(manager.placement_for("note:1"), ContextWindowPlacement.TOP_OF_CONTEXT)

    async def test_move_refuses_frozen_primitive(self) -> None:
        """Verify context_move cannot move frozen primitives."""
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="locked", title="Locked", content="body", primitive_frozen=True))
        tool = ContextMoveTool(manager)

        result = await tool.execute(ToolCall(tool_name="context_move", arguments={"primitive_id": "locked", "placement": "top_of_context"}))

        self.assertEqual(result.status.value, "error")
        self.assertIn("frozen", result.output)

    async def test_move_rejects_invalid_placement(self) -> None:
        """Verify context_move rejects unknown placement strings."""
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="note:1", title="Note", content="body"))
        tool = ContextMoveTool(manager)

        result = await tool.execute(ToolCall(tool_name="context_move", arguments={"primitive_id": "note:1", "placement": "middle"}))

        self.assertEqual(result.status.value, "error")
        self.assertIn("Invalid placement", result.output)

    async def test_context_window_tools_returns_create_and_management_tools(self) -> None:
        """Verify the factory returns generated create tools plus management tools."""
        manager = ContextManager()

        tools = context_window_tools(manager, include=("text",))

        self.assertEqual(
            tuple(tool.name for tool in tools),
            ("context_create_text", "context_list", "context_remove", "context_view", "context_stats", "context_edit", "context_move"),
        )

    async def test_context_window_tools_rejects_unknown_include_key(self) -> None:
        """Verify the factory reports unknown primitive include keys."""
        manager = ContextManager()

        with self.assertRaises(ValueError):
            context_window_tools(manager, include=("missing",))


class ContextUpsertToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_upsert_text_primitive(self) -> None:
        manager = ContextManager()
        tool = ContextUpsertTool(manager)
        call = ToolCall(
            tool_name="context_upsert",
            arguments={"primitive_id": "note:1", "content": "body text", "primitive_type": "text"},
        )

        await tool.execute(call)

        stored = manager.get_by_id("note:1")
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertIn("body text", stored.to_context_text())

    async def test_upsert_plan_splits_content_by_line(self) -> None:
        manager = ContextManager()
        tool = ContextUpsertTool(manager)
        call = ToolCall(
            tool_name="context_upsert",
            arguments={
                "primitive_id": "plan:current",
                "content": "Step one\nStep two\nStep three",
                "primitive_type": "plan",
            },
        )

        await tool.execute(call)

        stored = manager.get_by_id("plan:current")
        self.assertIsInstance(stored, PlanContextItem)
        assert isinstance(stored, PlanContextItem)
        self.assertEqual(len(stored.steps), 3)

    async def test_upsert_unknown_type_returns_error(self) -> None:
        manager = ContextManager()
        tool = ContextUpsertTool(manager)
        call = ToolCall(
            tool_name="context_upsert",
            arguments={"primitive_id": "x:1", "content": "c", "primitive_type": "bogus_type"},
        )

        result = await tool.execute(call)

        self.assertEqual(result.status.value, "error")
        self.assertIsNone(manager.get_by_id("x:1"))

    async def test_upsert_frozen_primitive_returns_error(self) -> None:
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="locked", title="L", content="c", primitive_frozen=True))
        tool = ContextUpsertTool(manager)
        call = ToolCall(
            tool_name="context_upsert",
            arguments={"primitive_id": "locked", "content": "new content", "primitive_type": "text"},
        )

        result = await tool.execute(call)

        self.assertEqual(result.status.value, "error")
        stored = manager.get_by_id("locked")
        assert stored is not None
        self.assertIn("c", stored.to_context_text())

    async def test_upsert_replaces_existing_primitive(self) -> None:
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="note:1", title="Old", content="old body"))
        tool = ContextUpsertTool(manager)
        call = ToolCall(
            tool_name="context_upsert",
            arguments={"primitive_id": "note:1", "content": "new body", "primitive_type": "text"},
        )

        await tool.execute(call)

        stored = manager.get_by_id("note:1")
        assert stored is not None
        self.assertIn("new body", stored.to_context_text())
        self.assertNotIn("old body", stored.to_context_text())

    async def test_public_imports_accessible_from_root(self) -> None:
        from vidbyte import ContextListTool as RootList
        from vidbyte import ContextMoveTool as RootMove
        from vidbyte import ContextRemoveTool as RootRemove
        from vidbyte import ContextStatsTool as RootStats
        from vidbyte import ContextUpsertTool as RootUpsert
        from vidbyte import ContextViewTool as RootView
        from vidbyte import context_window_tools as root_context_window_tools

        self.assertIs(RootList, ContextListTool)
        self.assertIs(RootMove, ContextMoveTool)
        self.assertIs(RootRemove, ContextRemoveTool)
        self.assertIs(RootStats, ContextStatsTool)
        self.assertIs(RootUpsert, ContextUpsertTool)
        self.assertIs(RootView, ContextViewTool)
        self.assertIs(root_context_window_tools, context_window_tools)


if __name__ == "__main__":
    unittest.main()
