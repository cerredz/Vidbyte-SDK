from __future__ import annotations

import unittest

from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import (
    DocumentContextItem,
    MemoryContextItem,
    PlanContextItem,
    ProgressContextItem,
    TaskContextItem,
    TextContextItem,
)
from vidbyte.tools.builtins.context_primitives import ContextListTool, ContextRemoveTool, ContextUpsertTool
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
        from vidbyte import ContextRemoveTool as RootRemove
        from vidbyte import ContextUpsertTool as RootUpsert

        self.assertIs(RootList, ContextListTool)
        self.assertIs(RootRemove, ContextRemoveTool)
        self.assertIs(RootUpsert, ContextUpsertTool)


if __name__ == "__main__":
    unittest.main()
