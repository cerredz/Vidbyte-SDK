from __future__ import annotations

import unittest

from vidbyte import ContextDefineTool as RootDefineTool
from vidbyte import CustomContextItem as RootCustomItem
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import CustomContextItem, _format_field_value
from vidbyte.tools.builtins import ContextDefineTool as BuiltinDefineTool
from vidbyte.tools.builtins.context_primitives.define import ContextDefineTool
from vidbyte.tools.types import ToolCall


# ---------------------------------------------------------------------------
# CustomContextItem rendering
# ---------------------------------------------------------------------------

class CustomContextItemRenderTests(unittest.TestCase):
    def test_renders_field_with_description_when_schema_present(self) -> None:
        item = CustomContextItem(
            primitive_id="t:1",
            title="T",
            fields={"objective": "fix auth"},
            schema={"objective": "high-level goal"},
        )

        text = item.to_context_text()

        self.assertIn("objective (high-level goal): fix auth", text)

    def test_renders_field_without_parens_when_schema_missing_for_key(self) -> None:
        item = CustomContextItem(
            primitive_id="t:1",
            title="T",
            fields={"status": "in progress"},
            schema={},
        )

        text = item.to_context_text()

        self.assertIn("  status: in progress", text)
        self.assertNotIn("(", text)

    def test_renders_list_value_as_comma_separated(self) -> None:
        item = CustomContextItem(
            primitive_id="t:1",
            title="T",
            fields={"files": ["auth.py", "middleware.py"]},
            schema={},
        )

        text = item.to_context_text()

        self.assertIn("auth.py, middleware.py", text)

    def test_renders_empty_list_as_bracket_pair(self) -> None:
        item = CustomContextItem(
            primitive_id="t:1",
            title="T",
            fields={"items": []},
            schema={},
        )

        text = item.to_context_text()

        self.assertIn("items: []", text)

    def test_renders_dict_value_as_compact_json(self) -> None:
        item = CustomContextItem(
            primitive_id="t:1",
            title="T",
            fields={"config": {"timeout": 30}},
            schema={},
        )

        text = item.to_context_text()

        self.assertIn('{"timeout":30}', text)

    def test_renders_none_value_as_none_string(self) -> None:
        item = CustomContextItem(
            primitive_id="t:1",
            title="T",
            fields={"error": None},
            schema={},
        )

        text = item.to_context_text()

        self.assertIn("error: None", text)

    def test_renders_no_fields_message_when_fields_empty(self) -> None:
        item = CustomContextItem(primitive_id="t:1", title="T", fields={})

        text = item.to_context_text()

        self.assertIn("(no fields defined)", text)

    def test_renders_header_with_title(self) -> None:
        item = CustomContextItem(primitive_id="t:1", title="My Custom Block", fields={"x": 1})

        text = item.to_context_text()

        self.assertTrue(text.startswith("Custom: My Custom Block"))

    def test_schema_keys_not_in_fields_are_ignored_at_render_time(self) -> None:
        item = CustomContextItem(
            primitive_id="t:1",
            title="T",
            fields={"a": "val"},
            schema={"a": "desc a", "ghost": "desc for missing key"},
        )

        text = item.to_context_text()

        self.assertNotIn("ghost", text)

    def test_kind_is_custom(self) -> None:
        item = CustomContextItem(primitive_id="t:1", title="T", fields={"x": 1})

        self.assertEqual(item.kind, "custom")


# ---------------------------------------------------------------------------
# _format_field_value helper
# ---------------------------------------------------------------------------

class FormatFieldValueTests(unittest.TestCase):
    def test_non_empty_list_joins_with_comma(self) -> None:
        self.assertEqual(_format_field_value(["a", "b", "c"]), "a, b, c")

    def test_empty_list_renders_brackets(self) -> None:
        self.assertEqual(_format_field_value([]), "[]")

    def test_dict_renders_as_compact_json(self) -> None:
        self.assertEqual(_format_field_value({"k": 1}), '{"k":1}')

    def test_none_renders_as_none_string(self) -> None:
        self.assertEqual(_format_field_value(None), "None")

    def test_integer_renders_as_string(self) -> None:
        self.assertEqual(_format_field_value(42), "42")

    def test_boolean_renders_as_string(self) -> None:
        self.assertEqual(_format_field_value(True), "True")


# ---------------------------------------------------------------------------
# ContextDefineTool — happy path
# ---------------------------------------------------------------------------

class ContextDefineToolHappyPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_call_creates_custom_primitive_in_registry(self) -> None:
        manager = ContextManager()
        tool = ContextDefineTool(manager)
        call = ToolCall(
            tool_name="context_define",
            arguments={
                "primitive_id": "coding_task:auth",
                "title": "Coding Task",
                "fields": '{"objective": "fix auth", "files": ["auth.py"]}',
                "schema": '{"objective": "high-level goal", "files": "files touched"}',
            },
        )

        result = await tool.execute(call)

        self.assertEqual(result.status.value, "success")
        stored = manager.get_by_id("coding_task:auth")
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertIsInstance(stored, CustomContextItem)

    async def test_success_message_references_primitive_id(self) -> None:
        manager = ContextManager()
        tool = ContextDefineTool(manager)
        call = ToolCall(
            tool_name="context_define",
            arguments={
                "primitive_id": "my:id",
                "title": "T",
                "fields": '{"x": 1}',
            },
        )

        result = await tool.execute(call)

        self.assertIn("my:id", result.output)

    async def test_success_message_includes_correct_field_count(self) -> None:
        manager = ContextManager()
        tool = ContextDefineTool(manager)
        call = ToolCall(
            tool_name="context_define",
            arguments={
                "primitive_id": "t:1",
                "title": "T",
                "fields": '{"a": 1, "b": 2, "c": 3}',
            },
        )

        result = await tool.execute(call)

        self.assertIn("3 fields", result.output)

    async def test_schema_default_empty_when_omitted(self) -> None:
        manager = ContextManager()
        tool = ContextDefineTool(manager)
        call = ToolCall(
            tool_name="context_define",
            arguments={"primitive_id": "t:1", "title": "T", "fields": '{"x": 1}'},
        )

        await tool.execute(call)

        stored = manager.get_by_id("t:1")
        assert isinstance(stored, CustomContextItem)
        self.assertEqual(dict(stored.schema), {})

    async def test_partial_schema_subset_of_fields_passes(self) -> None:
        manager = ContextManager()
        tool = ContextDefineTool(manager)
        call = ToolCall(
            tool_name="context_define",
            arguments={
                "primitive_id": "t:1",
                "title": "T",
                "fields": '{"a": 1, "b": 2}',
                "schema": '{"a": "only a has a desc"}',
            },
        )

        result = await tool.execute(call)

        self.assertEqual(result.status.value, "success")

    async def test_fields_with_nested_dict_value_accepted(self) -> None:
        manager = ContextManager()
        tool = ContextDefineTool(manager)
        call = ToolCall(
            tool_name="context_define",
            arguments={
                "primitive_id": "t:1",
                "title": "T",
                "fields": '{"config": {"timeout": 30, "retries": 3}}',
            },
        )

        result = await tool.execute(call)

        self.assertEqual(result.status.value, "success")


# ---------------------------------------------------------------------------
# ContextDefineTool — validation errors
# ---------------------------------------------------------------------------

class ContextDefineToolValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_error_when_primitive_id_empty(self) -> None:
        manager = ContextManager()
        tool = ContextDefineTool(manager)
        call = ToolCall(
            tool_name="context_define",
            arguments={"primitive_id": "   ", "title": "T", "fields": '{"x": 1}'},
        )

        result = await tool.execute(call)

        self.assertEqual(result.status.value, "error")
        self.assertIn("primitive_id", result.output)

    async def test_error_when_title_empty(self) -> None:
        manager = ContextManager()
        tool = ContextDefineTool(manager)
        call = ToolCall(
            tool_name="context_define",
            arguments={"primitive_id": "t:1", "title": "", "fields": '{"x": 1}'},
        )

        result = await tool.execute(call)

        self.assertEqual(result.status.value, "error")
        self.assertIn("title", result.output)

    async def test_error_when_fields_invalid_json(self) -> None:
        manager = ContextManager()
        tool = ContextDefineTool(manager)
        call = ToolCall(
            tool_name="context_define",
            arguments={"primitive_id": "t:1", "title": "T", "fields": "not json at all"},
        )

        result = await tool.execute(call)

        self.assertEqual(result.status.value, "error")
        self.assertIn("fields", result.output)

    async def test_error_when_fields_is_json_list(self) -> None:
        manager = ContextManager()
        tool = ContextDefineTool(manager)
        call = ToolCall(
            tool_name="context_define",
            arguments={"primitive_id": "t:1", "title": "T", "fields": '["a", "b"]'},
        )

        result = await tool.execute(call)

        self.assertEqual(result.status.value, "error")
        self.assertIn("fields", result.output)

    async def test_error_when_fields_empty_dict(self) -> None:
        manager = ContextManager()
        tool = ContextDefineTool(manager)
        call = ToolCall(
            tool_name="context_define",
            arguments={"primitive_id": "t:1", "title": "T", "fields": "{}"},
        )

        result = await tool.execute(call)

        self.assertEqual(result.status.value, "error")

    async def test_error_when_schema_invalid_json(self) -> None:
        manager = ContextManager()
        tool = ContextDefineTool(manager)
        call = ToolCall(
            tool_name="context_define",
            arguments={
                "primitive_id": "t:1",
                "title": "T",
                "fields": '{"x": 1}',
                "schema": "bad schema",
            },
        )

        result = await tool.execute(call)

        self.assertEqual(result.status.value, "error")
        self.assertIn("schema", result.output)

    async def test_error_when_schema_is_json_list(self) -> None:
        manager = ContextManager()
        tool = ContextDefineTool(manager)
        call = ToolCall(
            tool_name="context_define",
            arguments={
                "primitive_id": "t:1",
                "title": "T",
                "fields": '{"x": 1}',
                "schema": '["x"]',
            },
        )

        result = await tool.execute(call)

        self.assertEqual(result.status.value, "error")
        self.assertIn("schema", result.output)

    async def test_error_when_schema_key_not_in_fields(self) -> None:
        manager = ContextManager()
        tool = ContextDefineTool(manager)
        call = ToolCall(
            tool_name="context_define",
            arguments={
                "primitive_id": "t:1",
                "title": "T",
                "fields": '{"x": 1}',
                "schema": '{"x": "desc", "ghost_key": "has no field"}',
            },
        )

        result = await tool.execute(call)

        self.assertEqual(result.status.value, "error")
        self.assertIn("ghost_key", result.output)

    async def test_error_when_frozen_primitive_is_overwritten(self) -> None:
        manager = ContextManager()
        frozen = CustomContextItem(
            primitive_id="locked:1",
            title="Locked",
            fields={"status": "original"},
            primitive_frozen=True,
        )
        manager.upsert(frozen)
        tool = ContextDefineTool(manager)
        call = ToolCall(
            tool_name="context_define",
            arguments={"primitive_id": "locked:1", "title": "T", "fields": '{"status": "new"}'},
        )

        result = await tool.execute(call)

        self.assertEqual(result.status.value, "error")
        stored = manager.get_by_id("locked:1")
        assert isinstance(stored, CustomContextItem)
        self.assertEqual(stored.fields.get("status"), "original")


# ---------------------------------------------------------------------------
# Integration: full render path
# ---------------------------------------------------------------------------

class ContextDefineIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_defined_primitive_appears_in_render_primitives_zone(self) -> None:
        manager = ContextManager()
        tool = ContextDefineTool(manager)
        call = ToolCall(
            tool_name="context_define",
            arguments={
                "primitive_id": "coding_task:auth",
                "title": "Coding Task",
                "fields": '{"objective": "fix auth", "error": "AttributeError line 42"}',
                "schema": '{"objective": "high-level goal", "error": "current active error"}',
            },
        )

        await tool.execute(call)

        zone = manager.render_primitives_zone()
        self.assertIn("coding_task:auth", zone)
        self.assertIn("Coding Task", zone)
        self.assertIn("objective (high-level goal): fix auth", zone)
        self.assertIn("error (current active error): AttributeError line 42", zone)

    async def test_schema_descriptions_appear_in_zone_render(self) -> None:
        manager = ContextManager()
        tool = ContextDefineTool(manager)
        call = ToolCall(
            tool_name="context_define",
            arguments={
                "primitive_id": "research:plan",
                "title": "Research Plan",
                "fields": '{"sources": ["arxiv.org"], "findings": "none yet"}',
                "schema": '{"sources": "papers to review", "findings": "discoveries so far"}',
            },
        )

        await tool.execute(call)

        zone = manager.render_primitives_zone()
        self.assertIn("sources (papers to review)", zone)
        self.assertIn("findings (discoveries so far)", zone)


# ---------------------------------------------------------------------------
# Public import surface
# ---------------------------------------------------------------------------

class PublicImportTests(unittest.TestCase):
    def test_custom_context_item_importable_from_root(self) -> None:
        self.assertIs(RootCustomItem, CustomContextItem)

    def test_context_define_tool_importable_from_root(self) -> None:
        from vidbyte.tools.builtins.context_primitives.define import ContextDefineTool as DirectImport
        self.assertIs(RootDefineTool, DirectImport)

    def test_context_define_tool_importable_from_builtins(self) -> None:
        self.assertIs(BuiltinDefineTool, RootDefineTool)


if __name__ == "__main__":
    unittest.main()
