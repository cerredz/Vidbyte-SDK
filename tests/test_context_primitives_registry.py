from __future__ import annotations

import unittest

from vidbyte.context import ContextManager, PlanContextItem
from vidbyte.context.primitives import (
    DocumentContextItem,
    MemoryContextItem,
    ProgressContextItem,
    TaskContextItem,
    TextContextItem,
)
from vidbyte.lib.dataclasses import ContextItem, ContextResponse, ContextArtifact


class RegistryUpsertTests(unittest.TestCase):
    def test_upsert_stores_primitive_by_id(self) -> None:
        item = TextContextItem(primitive_id="note:1", title="Note", content="body")
        manager = ContextManager()

        manager.upsert(item)

        self.assertIs(manager.get_by_id("note:1"), item)

    def test_upsert_replaces_existing_primitive(self) -> None:
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="note:1", title="Old", content="old"))
        new_item = TextContextItem(primitive_id="note:1", title="New", content="new")

        manager.upsert(new_item)

        self.assertIs(manager.get_by_id("note:1"), new_item)

    def test_upsert_raises_when_primitive_id_is_empty(self) -> None:
        manager = ContextManager()
        item = TextContextItem(primitive_id="", title="X", content="y")

        with self.assertRaises(ValueError):
            manager.upsert(item)

    def test_upsert_raises_when_primitive_id_is_none(self) -> None:
        manager = ContextManager()
        item = TextContextItem(primitive_id=None, title="X", content="y")

        with self.assertRaises(ValueError):
            manager.upsert(item)

    def test_upsert_raises_on_frozen_primitive(self) -> None:
        manager = ContextManager()
        frozen = TextContextItem(primitive_id="locked", title="L", content="c", primitive_frozen=True)
        manager.upsert(frozen)

        with self.assertRaises(ValueError):
            manager.upsert(TextContextItem(primitive_id="locked", title="New", content="c2"))

    def test_upsert_frozen_primitive_with_itself_still_raises(self) -> None:
        manager = ContextManager()
        frozen = TextContextItem(primitive_id="locked", title="L", content="c", primitive_frozen=True)
        manager.upsert(frozen)

        with self.assertRaises(ValueError):
            manager.upsert(frozen)

    def test_get_by_id_returns_none_for_missing_id(self) -> None:
        manager = ContextManager()

        self.assertIsNone(manager.get_by_id("does:not:exist"))

    def test_remove_by_id_deletes_existing_primitive(self) -> None:
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="note:1", title="N", content="c"))

        manager.remove_by_id("note:1")

        self.assertIsNone(manager.get_by_id("note:1"))

    def test_remove_by_id_is_idempotent_for_missing_id(self) -> None:
        manager = ContextManager()

        manager.remove_by_id("ghost:id")

        self.assertIsNone(manager.get_by_id("ghost:id"))

    def test_clear_registry_removes_all_primitives(self) -> None:
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="a", title="A", content="x"))
        manager.upsert(TextContextItem(primitive_id="b", title="B", content="y"))

        manager.clear_registry()

        self.assertIsNone(manager.get_by_id("a"))
        self.assertIsNone(manager.get_by_id("b"))

    def test_clear_does_not_touch_registry(self) -> None:
        manager = ContextManager([TextContextItem(primitive_id=None, title="Unmanaged", content="u")])
        manager.upsert(TextContextItem(primitive_id="managed", title="M", content="m"))

        manager.clear()

        self.assertIsNotNone(manager.get_by_id("managed"))
        self.assertEqual(manager.items(), ())

    def test_registry_does_not_appear_in_items(self) -> None:
        unmanaged = TextContextItem(title="Unmanaged", content="u")
        managed = TextContextItem(primitive_id="managed:1", title="Managed", content="m")
        manager = ContextManager([unmanaged])
        manager.upsert(managed)

        self.assertIn(unmanaged, manager.items())
        self.assertNotIn(managed, manager.items())

    def test_registry_does_not_appear_in_to_context(self) -> None:
        managed = TextContextItem(primitive_id="plan:current", title="Plan", content="step 1")
        manager = ContextManager()
        manager.upsert(managed)

        context = manager.to_context()

        self.assertEqual(len(context.context_items), 0)
        self.assertEqual(len(context.artifacts), 0)


class RenderPrimitivesZoneTests(unittest.TestCase):
    def test_empty_registry_renders_empty_string(self) -> None:
        manager = ContextManager()

        self.assertEqual(manager.render_primitives_zone(), "")

    def test_single_primitive_renders_id_and_title(self) -> None:
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="note:1", title="My Note", content="body text"))

        zone = manager.render_primitives_zone()

        self.assertIn("note:1", zone)
        self.assertIn("My Note", zone)
        self.assertIn("body text", zone)

    def test_multiple_primitives_all_appear_in_zone(self) -> None:
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="a", title="Alpha", content="alpha content"))
        manager.upsert(PlanContextItem(primitive_id="b", title="Beta Plan", steps=("step 1",)))

        zone = manager.render_primitives_zone()

        self.assertIn("[a]", zone)
        self.assertIn("[b]", zone)
        self.assertIn("Alpha", zone)
        self.assertIn("Beta Plan", zone)

    def test_render_contains_section_header(self) -> None:
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="x", title="X", content="c"))

        zone = manager.render_primitives_zone()

        self.assertIn("## Context Window Primitives", zone)


class PlanContextItemTests(unittest.TestCase):
    def test_plan_renders_steps_with_arrow_on_current(self) -> None:
        plan = PlanContextItem(
            primitive_id="plan:1",
            steps=("Research", "Design", "Implement"),
            current_step=1,
        )

        text = plan.to_context_text()

        self.assertIn("→ 2. Design", text)
        self.assertNotIn("→ 1. Research", text)
        self.assertNotIn("→ 3. Implement", text)

    def test_plan_renders_no_steps_message_when_empty(self) -> None:
        plan = PlanContextItem(primitive_id="plan:empty", steps=())

        text = plan.to_context_text()

        self.assertIn("No steps defined.", text)

    def test_plan_status_appears_in_render(self) -> None:
        plan = PlanContextItem(primitive_id="plan:x", status="executing", steps=("do it",))

        text = plan.to_context_text()

        self.assertIn("executing", text)

    def test_plan_can_be_upserted_and_retrieved(self) -> None:
        manager = ContextManager()
        plan = PlanContextItem(primitive_id="plan:current", steps=("step 1", "step 2"))

        manager.upsert(plan)

        self.assertIs(manager.get_by_id("plan:current"), plan)

    def test_plan_public_import_matches_primitive(self) -> None:
        from vidbyte import PlanContextItem as RootPlan
        from vidbyte.context.primitives import PlanContextItem as PrimitivePlan

        self.assertIs(RootPlan, PrimitivePlan)


class SplitContextRenderingTests(unittest.TestCase):
    def test_build_context_fixed_contains_system_prompt(self) -> None:
        from vidbyte.lib.dataclasses.context import BaseContext as StrategyContext

        ctx = StrategyContext(system_prompt="You are an agent.", tools=())

        fixed = ctx.build_context_fixed()

        self.assertIn("You are an agent.", fixed)

    def test_build_context_body_does_not_contain_system_prompt(self) -> None:
        from vidbyte.lib.dataclasses.context import BaseContext as StrategyContext

        ctx = StrategyContext(system_prompt="SECRET", memory="mem summary")

        body = ctx.build_context_body()

        self.assertNotIn("SECRET", body)
        self.assertIn("mem summary", body)

    def test_build_context_combines_fixed_and_body(self) -> None:
        from vidbyte.lib.dataclasses.context import BaseContext as StrategyContext

        ctx = StrategyContext(system_prompt="sys", memory="agent memory")

        full = ctx.build_context()

        self.assertIn("sys", full)
        self.assertIn("agent memory", full)


if __name__ == "__main__":
    unittest.main()

