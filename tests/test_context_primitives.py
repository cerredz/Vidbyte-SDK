from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vidbyte.context import (
    ContextManager,
    ContextPrimitivePlacement,
    ContextPrimitiveUpdate,
    ContextPrimitiveVisibility,
    ContextWindow,
    FileContextItem,
    IdentityContextItem,
    PlanContextItem,
    TaskContextItem,
    TextContextItem,
)
from vidbyte.context.primitives import context_primitive_id
from vidbyte.strategies import StrategyContext


class ContextPrimitiveTests(unittest.TestCase):
    def test_identity_context_item_defaults_to_sticky_model_visible(self) -> None:
        item = IdentityContextItem(role="SDK engineer")

        self.assertEqual(item.id, "identity:agent")
        self.assertEqual(item.placement, ContextPrimitivePlacement.STICKY)
        self.assertEqual(item.visibility, ContextPrimitiveVisibility.MODEL)
        self.assertIn("lower authority", item.to_context_text())

    def test_plan_context_item_renders_steps_risks_and_verification(self) -> None:
        item = PlanContextItem(
            objective="Ship primitives.",
            steps=("Add data model", "Wire runtime"),
            current_step="Wire runtime",
            risks=("Duplicate rendering",),
            verification=("python -m unittest",),
        )

        rendered = item.to_context_text()

        self.assertIn("Ship primitives.", rendered)
        self.assertIn("Wire runtime", rendered)
        self.assertIn("Duplicate rendering", rendered)
        self.assertIn("python -m unittest", rendered)

    def test_context_primitive_id_uses_explicit_id(self) -> None:
        item = TaskContextItem(id="task:custom", goal="Do work")

        self.assertEqual(context_primitive_id(item), "task:custom")

    def test_context_primitive_id_derives_file_id_from_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.py"
            path.write_text("print('ok')", encoding="utf-8")
            item = FileContextItem.from_path(path)

        self.assertEqual(context_primitive_id(item), f"file:{path}")

    def test_hidden_and_metadata_only_primitives_are_not_model_visible(self) -> None:
        hidden = TextContextItem(title="Secret", content="do not show", visibility="hidden")
        metadata_only = TextContextItem(title="Metadata", content="do not show", visibility="metadata_only")
        visible = TextContextItem(title="Visible", content="show")

        rendered = StrategyContext(context_items=(hidden, metadata_only, visible)).build_context()

        self.assertIn("show", rendered)
        self.assertNotIn("do not show", rendered)

    def test_context_window_algorithm_sorts_sticky_primitives_first_by_priority(self) -> None:
        normal = TextContextItem(id="normal", title="Normal", content="n", priority=0)
        sticky_late = TaskContextItem(id="task:late", goal="late", priority=20)
        sticky_first = IdentityContextItem(role="first", priority=0)

        visible = ContextWindow.preset.default.model_visible_context_primitives(
            (normal, sticky_late, sticky_first)
        )

        self.assertEqual(tuple(context_primitive_id(item) for item in visible), ("identity:agent", "task:late", "normal"))

    def test_context_primitive_update_upsert_and_remove_helpers(self) -> None:
        item = TaskContextItem(id="task:test", goal="Test")

        upsert = ContextPrimitiveUpdate.upsert(item)
        remove = ContextPrimitiveUpdate.remove("task:test")

        self.assertEqual(upsert.item, item)
        self.assertEqual(upsert.item_id, "task:test")
        self.assertEqual(remove.item_id, "task:test")

    def test_context_manager_upsert_replaces_existing_item_with_same_id(self) -> None:
        first = TaskContextItem(id="task:test", goal="Old")
        second = TaskContextItem(id="task:test", goal="New", status="done")
        manager = ContextManager([first])

        manager.upsert(second)

        self.assertEqual(manager.items(), (second,))

    def test_context_manager_apply_updates_upserts_and_removes(self) -> None:
        first = TaskContextItem(id="task:one", goal="One")
        second = TaskContextItem(id="task:two", goal="Two")
        manager = ContextManager([first])

        manager.apply_updates([
            ContextPrimitiveUpdate.upsert(second),
            ContextPrimitiveUpdate.remove("task:one"),
        ])

        self.assertEqual(manager.items(), (second,))

    def test_base_context_renders_primitives_after_system_prompt(self) -> None:
        context = StrategyContext(
            system_prompt="System.",
            context_items=(TaskContextItem(id="task:test", goal="Do work"),),
            memory="Memory.",
        )

        rendered = context.build_context()

        self.assertLess(rendered.index("System prompt:"), rendered.index("Context primitives:"))
        self.assertLess(rendered.index("Context primitives:"), rendered.index("Memory summary:"))


if __name__ == "__main__":
    unittest.main()
