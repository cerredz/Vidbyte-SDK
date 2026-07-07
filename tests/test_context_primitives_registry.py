from __future__ import annotations

import unittest

from vidbyte.context import ContextManager, ContextWindowPlacement, PlanContextItem
from vidbyte.context.primitives import (
    ArtifactContextItem,
    DocumentContextItem,
    EnvironmentContextItem,
    GitDiffContextItem,
    MemoryContextItem,
    ProgressContextItem,
    TaskContextItem,
    TextContextItem,
)
from vidbyte.lib.dataclasses import ContextItem, ContextResponse, ContextArtifact
from vidbyte.tools.builtins.context_primitives import CREATE_TOOL_REGISTRY, CreateContextPrimitiveTool, context_window_tools
from vidbyte.tools.types import ToolCall


def _sample_args_for_key(key: str) -> dict[str, object]:
    """Return valid create-tool arguments for one primitive registry key."""
    samples: dict[str, dict[str, object]] = {
        "text": {"primitive_id": "text:1", "content": "hello", "source": "test"},
        "document": {"primitive_id": "document:1", "source": "spec.md", "content": "doc body", "document_id": "doc-1"},
        "memory": {"primitive_id": "memory:1", "content": "remember this", "source": "test"},
        "plan": {"primitive_id": "plan:1", "steps": ["research", "ship"], "current_step": 1, "status": "executing"},
        "task": {"primitive_id": "task:1", "goal": "finish", "status": "active", "completed": ["a"], "next_steps": ["b"], "deterministic_checks": ["python -m unittest"]},
        "progress": {"primitive_id": "progress:1", "completed_tasks": ["done"], "touched_files": ["a.py"], "decisions": ["keep"], "errors": [], "next_steps": ["next"]},
        "artifact": {"primitive_id": "artifact:1", "name": "report", "content": "artifact body", "artifact_type": "markdown"},
        "environment": {"primitive_id": "environment:1", "os_name": "Windows", "cwd": "C:/repo", "shell": "powershell"},
        "git_diff": {"primitive_id": "git_diff:1", "diff": "diff --git a/a.py b/a.py", "files": ["a.py"], "branch": "main"},
    }
    return dict(samples[key])


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

    def test_registry_items_returns_ordered_tuple(self) -> None:
        """Verify registry_items exposes ordered pairs without exposing the mutable dict."""
        manager = ContextManager()
        first = TextContextItem(primitive_id="a", title="A", content="a")
        second = TextContextItem(primitive_id="b", title="B", content="b")

        manager.upsert(first)
        manager.upsert(second)

        self.assertEqual(manager.registry_items(), (("a", first), ("b", second)))

    def test_set_placement_updates_existing_primitive(self) -> None:
        """Verify set_placement changes placement metadata for an existing primitive."""
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="x", title="X", content="x"))

        manager.set_placement("x", ContextWindowPlacement.TOP_OF_CONTEXT)

        self.assertEqual(manager.placement_for("x"), ContextWindowPlacement.TOP_OF_CONTEXT)

    def test_set_placement_rejects_missing_primitive(self) -> None:
        """Verify set_placement raises for ids not in the registry."""
        manager = ContextManager()

        with self.assertRaises(ValueError):
            manager.set_placement("missing", ContextWindowPlacement.TOP_OF_CONTEXT)

    def test_set_frozen_updates_existing_primitive(self) -> None:
        """Verify set_frozen replaces the registered dataclass with a frozen copy."""
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="x", title="X", content="x"))

        manager.set_frozen("x", True)

        stored = manager.get_by_id("x")
        assert stored is not None
        self.assertTrue(getattr(stored, "primitive_frozen", False))

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

    def test_upsert_default_placement_matches_existing_rendering(self) -> None:
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="x", title="X", content="c"))

        self.assertEqual(manager.placement_for("x"), ContextWindowPlacement.END_OF_CONTEXT)
        self.assertIn("X", manager.render_primitives_zone())

    def test_top_of_context_renders_before_end_of_context(self) -> None:
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="end", title="End", content="end"))
        manager.upsert(TextContextItem(primitive_id="top", title="Top", content="top"), placement=ContextWindowPlacement.TOP_OF_CONTEXT)

        zone = manager.render_primitives_zone()

        self.assertLess(zone.index("Top"), zone.index("End"))

    def test_replacing_primitive_updates_placement(self) -> None:
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="x", title="X", content="c"))

        manager.upsert(TextContextItem(primitive_id="x", title="X", content="c"), placement=ContextWindowPlacement.TOP_OF_CONTEXT)

        self.assertEqual(manager.placement_for("x"), ContextWindowPlacement.TOP_OF_CONTEXT)

    def test_remove_by_id_removes_placement_metadata(self) -> None:
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="x", title="X", content="c"), placement=ContextWindowPlacement.TOP_OF_CONTEXT)

        manager.remove_by_id("x")

        self.assertIsNone(manager.placement_for("x"))

    def test_conversation_placement_does_not_render_in_primitives_zone(self) -> None:
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="x", title="X", content="c"), placement=ContextWindowPlacement.TOP_OF_CONVERSATION)

        self.assertEqual(manager.render_primitives_zone(), "")

    def test_conversation_messages_render_in_placement_order(self) -> None:
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="top", title="Top", content="top"), placement=ContextWindowPlacement.TOP_OF_CONVERSATION)
        manager.upsert(TextContextItem(primitive_id="end", title="End", content="end"), placement=ContextWindowPlacement.END_OF_CONVERSATION)

        top = manager.render_conversation_messages(ContextWindowPlacement.TOP_OF_CONVERSATION)
        end = manager.render_conversation_messages(ContextWindowPlacement.END_OF_CONVERSATION)

        self.assertIn("top", top[0]["content"])
        self.assertIn("end", end[0]["content"])


class CreateToolRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_registry_key_creates_and_renders_a_primitive(self) -> None:
        """Verify every registry row builds a managed primitive visible in the zone."""
        expected_types = {
            "text": TextContextItem,
            "document": DocumentContextItem,
            "memory": MemoryContextItem,
            "plan": PlanContextItem,
            "task": TaskContextItem,
            "progress": ProgressContextItem,
            "artifact": ArtifactContextItem,
            "environment": EnvironmentContextItem,
            "git_diff": GitDiffContextItem,
        }
        self.assertEqual(set(CREATE_TOOL_REGISTRY), set(expected_types))
        for key, definition in CREATE_TOOL_REGISTRY.items():
            manager = ContextManager()
            tool = CreateContextPrimitiveTool(definition, manager)

            result = await tool.execute(ToolCall(tool_name=definition.tool_name, arguments=_sample_args_for_key(key)))

            self.assertEqual(result.status.value, "success")
            stored = manager.get_by_id(str(_sample_args_for_key(key)["primitive_id"]))
            self.assertIsInstance(stored, expected_types[key])
            self.assertIn(str(_sample_args_for_key(key)["primitive_id"]), manager.render_primitives_zone())

    async def test_create_tool_respects_requested_placement(self) -> None:
        """Verify create tools pass placement through to ContextManager.upsert."""
        manager = ContextManager()
        definition = CREATE_TOOL_REGISTRY["text"]
        tool = CreateContextPrimitiveTool(definition, manager)
        args = _sample_args_for_key("text")
        args["placement"] = "top_of_context"

        await tool.execute(ToolCall(tool_name=definition.tool_name, arguments=args))

        self.assertEqual(manager.placement_for("text:1"), ContextWindowPlacement.TOP_OF_CONTEXT)

    async def test_create_tool_rejects_invalid_placement(self) -> None:
        """Verify invalid placement strings return a tool error instead of raising."""
        manager = ContextManager()
        definition = CREATE_TOOL_REGISTRY["text"]
        tool = CreateContextPrimitiveTool(definition, manager)
        args = _sample_args_for_key("text")
        args["placement"] = "middle"

        result = await tool.execute(ToolCall(tool_name=definition.tool_name, arguments=args))

        self.assertEqual(result.status.value, "error")
        self.assertIn("Invalid placement", result.output)

    async def test_create_tool_rejects_unknown_arguments(self) -> None:
        """Verify create tools enforce additionalProperties false at execution time."""
        manager = ContextManager()
        definition = CREATE_TOOL_REGISTRY["text"]
        tool = CreateContextPrimitiveTool(definition, manager)
        args = _sample_args_for_key("text")
        args["unexpected"] = "nope"

        result = await tool.execute(ToolCall(tool_name=definition.tool_name, arguments=args))

        self.assertEqual(result.status.value, "error")
        self.assertIn("Unknown argument", result.output)

    async def test_create_tool_rejects_frozen_overwrite(self) -> None:
        """Verify ContextManager frozen conflicts are converted into tool errors."""
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="text:1", title="Locked", content="old", primitive_frozen=True))
        definition = CREATE_TOOL_REGISTRY["text"]
        tool = CreateContextPrimitiveTool(definition, manager)

        result = await tool.execute(ToolCall(tool_name=definition.tool_name, arguments=_sample_args_for_key("text")))

        self.assertEqual(result.status.value, "error")
        stored = manager.get_by_id("text:1")
        assert stored is not None
        self.assertIn("old", stored.to_context_text())

    def test_registry_tool_names_are_unique(self) -> None:
        """Verify every registry row produces exactly one unique create tool name."""
        names = [definition.tool_name for definition in CREATE_TOOL_REGISTRY.values()]

        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(name.startswith("context_create_") for name in names))

    def test_schema_required_names_match_flat_parameters(self) -> None:
        """Verify provider JSON schemas and flat ToolParameters agree on required args."""
        for definition in CREATE_TOOL_REGISTRY.values():
            schema_required = tuple(definition.input_schema["required"])
            parameter_required = tuple(parameter.name for parameter in definition.parameters if parameter.required)

            self.assertEqual(parameter_required, schema_required)

    def test_every_array_schema_declares_items(self) -> None:
        """Verify array fields include item schemas for strict providers."""
        for definition in CREATE_TOOL_REGISTRY.values():
            properties = definition.input_schema["properties"]
            for schema in properties.values():
                if schema.get("type") == "array":
                    self.assertEqual(schema.get("items"), {"type": "string"})

    def test_context_window_tools_filters_create_keys(self) -> None:
        """Verify the factory can mount selected create tools without management tools."""
        manager = ContextManager()

        tools = context_window_tools(manager, include=("text", "plan"), management=False)

        self.assertEqual(tuple(tool.name for tool in tools), ("context_create_text", "context_create_plan"))


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

