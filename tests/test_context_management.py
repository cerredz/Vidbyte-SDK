from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vidbyte import ContextManager as RootContextManager
from vidbyte import ContextWindow as RootContextWindow
from vidbyte import FileContextItem as RootFileContextItem
from vidbyte.context import (
    ContextManager,
    ContextWindow,
    DocumentContextItem,
    FileContextItem,
    MemoryContextItem,
    ResponseContextItem,
    TaskContextItem,
    TextContextItem,
    ToolCallContextItem,
)
from vidbyte.context.primitives import TextContextItem as PrimitiveTextContextItem
from vidbyte.lib.dataclasses import ContextItem, ContextResponse, StrategyContext
from vidbyte.lib.dataclasses.context_items import TextContextItem as LegacyTextContextItem


class ContextManagementTests(unittest.TestCase):
    def test_text_context_item_renders_plain_text(self) -> None:
        item = TextContextItem(title="Note", content="body", source="user")

        rendered = item.to_context_text()

        self.assertIn("Note", rendered)
        self.assertIn("Source: user", rendered)
        self.assertIn("body", rendered)

    def test_file_context_item_from_path_without_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.py"
            path.write_text("print('ok')", encoding="utf-8")

            item = FileContextItem.from_path(path)

        self.assertEqual(item.path, str(path))
        self.assertEqual(item.size_bytes, len("print('ok')"))
        self.assertEqual(item.language, "py")
        self.assertIsNone(item.content)
        self.assertTrue(Path(item.absolute_path).is_absolute())

    def test_file_context_item_from_path_with_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.txt"
            path.write_text("file body", encoding="utf-8")

            item = FileContextItem.from_path(path, include_content=True)

        self.assertEqual(item.content, "file body")
        self.assertIn("file body", item.to_context_text())

    def test_context_manager_preserves_order(self) -> None:
        first = TextContextItem(title="First", content="one")
        second = TaskContextItem(goal="two")

        manager = ContextManager([first]).add(second)

        self.assertEqual(manager.items(), (first, second))

    def test_context_manager_filters_by_kind(self) -> None:
        task = TaskContextItem(goal="ship")
        note = TextContextItem(title="Note", content="body")
        manager = ContextManager([task, note])

        self.assertEqual(manager.by_kind("task"), (task,))

    def test_context_manager_to_context_bridges_standard_items(self) -> None:
        manager = ContextManager(
            [
                TaskContextItem(goal="finish", deterministic_checks=("python -m unittest",)),
                DocumentContextItem(source="spec.md", content="spec body"),
                MemoryContextItem(content="prior summary"),
                ResponseContextItem(content="previous answer", sender="assistant"),
                ToolCallContextItem(name="lookup", arguments={"q": "sdk"}, output="result"),
            ],
            metadata={"manager": "yes"},
        )

        context = manager.to_context()

        self.assertIsInstance(context, StrategyContext)
        self.assertEqual(len(context.context_items), 5)
        self.assertIn("prior summary", context.memory)
        self.assertTrue(any(artifact.artifact_type == "task" for artifact in context.artifacts))
        self.assertTrue(any(artifact.artifact_type == "document" for artifact in context.artifacts))
        self.assertEqual(context.responses, (ContextResponse("previous answer", "assistant"),))
        self.assertEqual(context.tool_calls[0].name, "lookup")
        self.assertEqual(context.metadata["manager"], "yes")

    def test_context_manager_merges_base_context(self) -> None:
        base = StrategyContext(
            system_prompt="system",
            memory="base memory",
            responses=[ContextResponse(content="base response")],
            metadata={"base": "yes"},
        )
        manager = ContextManager([MemoryContextItem(content="new memory")], metadata={"manager": "yes"})

        context = manager.to_context(base)

        self.assertEqual(context.system_prompt, "system")
        self.assertIn("base memory", context.memory)
        self.assertIn("new memory", context.memory)
        self.assertEqual(len(context.responses), 1)
        self.assertEqual(context.metadata, {"base": "yes", "manager": "yes"})

    def test_public_imports(self) -> None:
        self.assertIs(RootContextManager, ContextManager)
        self.assertIs(RootContextWindow, ContextWindow)
        self.assertIs(RootFileContextItem, FileContextItem)
        self.assertIs(PrimitiveTextContextItem, TextContextItem)
        self.assertIs(LegacyTextContextItem, TextContextItem)
        self.assertTrue(isinstance(TextContextItem(title="x", content="y"), ContextItem))

    def test_context_window_presets_are_named_algorithms(self) -> None:
        self.assertEqual(ContextWindow.preset.default.name, "default")
        self.assertEqual(ContextWindow.preset.no_raw_tool_outputs.name, "hide_tool_outputs")
        self.assertEqual(ContextWindow.resolve_algorithm("compact_tool_outputs").name, "compact_tool_outputs")

    def test_lifecycle_context_window_presets_are_named_algorithms(self) -> None:
        self.assertEqual(ContextWindow.preset.reasoning_trace_small.name, "reasoning_trace_small")
        self.assertEqual(ContextWindow.preset.reasoning_trace_medium.name, "reasoning_trace_medium")
        self.assertEqual(ContextWindow.preset.reasoning_trace_large.name, "reasoning_trace_large")
        self.assertEqual(ContextWindow.preset.plan_then_implement.name, "plan_then_implement")

    def test_reasoning_trace_factory_returns_algorithm(self) -> None:
        from vidbyte.context.algorithms import ContextWindowAlgorithm

        algo = ContextWindow.preset.reasoning_trace(size="large")
        self.assertIsInstance(algo, ContextWindowAlgorithm)
        self.assertEqual(algo.reasoning_trace.size.value, "large")

    def test_plan_then_implement_factory_returns_algorithm(self) -> None:
        from vidbyte.context.algorithms import ContextWindowAlgorithm

        algo = ContextWindow.preset.plan_then_implement_with(artifact_name="Strategy")
        self.assertIsInstance(algo, ContextWindowAlgorithm)
        self.assertEqual(algo.plan_then_implement.artifact_name, "Strategy")

    def test_resolve_reasoning_trace_preset_by_string(self) -> None:
        algo = ContextWindow.resolve_algorithm("reasoning_trace_small")
        self.assertEqual(algo.name, "reasoning_trace_small")
        self.assertIsNotNone(algo.reasoning_trace)

    def test_resolve_plan_then_implement_preset_by_string(self) -> None:
        algo = ContextWindow.resolve_algorithm("plan_then_implement")
        self.assertEqual(algo.name, "plan_then_implement")
        self.assertIsNotNone(algo.plan_then_implement)


if __name__ == "__main__":
    unittest.main()
