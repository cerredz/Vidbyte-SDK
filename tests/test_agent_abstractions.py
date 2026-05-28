"""Integration tests for Vidbyte SDK agentic abstractions (consolidated API)."""
from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest

from vidbyte.client import VidbyteSDK
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.errors import ToolRegistryError
from vidbyte.prompts import Prompts
from vidbyte.tools.builtins.calculator import CalculatorTool
from vidbyte.tools.builtins.code_execution import CodeExecutionTool
from vidbyte.tools.builtins.document_retrieval import DocumentRetrievalTool
from vidbyte.tools.executor import ToolExecutor
from vidbyte.tools.registry import ToolRegistry
from vidbyte.tools.types import ToolCall, ToolStatus


class TestTools(unittest.IsolatedAsyncioTestCase):
    """Verifies Tools, ToolRegistry, ToolExecutor, and builtin tools."""

    def setUp(self) -> None:
        self.registry = ToolRegistry()
        self.executor = ToolExecutor(self.registry)
        self.calculator = CalculatorTool()
        self.code_exec = CodeExecutionTool()
        self.doc_retrieval = DocumentRetrievalTool()
        self.registry.register(self.calculator)
        self.registry.register(self.code_exec)
        self.registry.register(self.doc_retrieval)

    def test_tool_registry_management(self) -> None:
        all_tools = self.registry.all()
        self.assertEqual(len(all_tools), 3)

        fetched = self.registry.get("calculator")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "calculator")

        with self.assertRaises(ToolRegistryError):
            self.registry.get("invalid_tool_name")

    def test_tool_specs_rendering(self) -> None:
        specs_prompt = self.registry.specs_as_prompt_str()
        self.assertIn("calculator", specs_prompt)
        self.assertIn("code_execution", specs_prompt)
        self.assertIn("document_retrieval", specs_prompt)

    async def test_calculator_safety(self) -> None:
        res_add = await self.calculator.execute(ToolCall("calculator", {"expression": "2 + 2"}))
        self.assertEqual(res_add.status, ToolStatus.SUCCESS)
        self.assertEqual(float(res_add.output.strip()), 4.0)

        res_complex = await self.calculator.execute(ToolCall("calculator", {"expression": "abs(-5) + min(10, 20) + round(3.456, 1)"}))
        self.assertEqual(res_complex.status, ToolStatus.SUCCESS)
        self.assertEqual(float(res_complex.output.strip()), 18.5)

        res_unsafe = await self.calculator.execute(ToolCall("calculator", {"expression": "__import__('os').system('dir')"}))
        self.assertEqual(res_unsafe.status, ToolStatus.ERROR)
        self.assertIn("double underscores", res_unsafe.output)

        res_chars = await self.calculator.execute(ToolCall("calculator", {"expression": "hello_world()"}))
        self.assertEqual(res_chars.status, ToolStatus.ERROR)
        self.assertIn("contains invalid math characters", res_chars.output)

    async def test_builtin_simulations(self) -> None:
        res_code = await self.code_exec.execute(ToolCall("code_execution", {"code": "print('hello from sandboxed runner')"}))
        self.assertEqual(res_code.status, ToolStatus.SUCCESS)
        self.assertIn("hello from sandboxed runner", res_code.output)

        res_doc = await self.doc_retrieval.execute(ToolCall("document_retrieval", {"query": "react"}))
        self.assertEqual(res_doc.status, ToolStatus.SUCCESS)
        self.assertIn("ReAct Design Architecture", res_doc.output)

    async def test_tool_executor_parser(self) -> None:
        text_block = (
            "Thought: I should calculate this first.\n"
            "Action: calculator\n"
            'Action Input: {"expression": "3 * 5"}\n'
        )
        res = await self.executor.execute(text_block)
        self.assertEqual(res.status, ToolStatus.SUCCESS)
        self.assertEqual(float(res.output.strip()), 15.0)

        invalid_text_block = (
            "Action: missing_tool\n"
            'Action Input: {"key": "val"}\n'
        )
        res_invalid = await self.executor.execute(invalid_text_block)
        self.assertEqual(res_invalid.status, ToolStatus.ERROR)
        self.assertIn("not found in registry", res_invalid.output)

        malformed_args_block = (
            "Action: calculator\n"
            "Action Input: {expression: 3 * 5}\n"
        )
        res_malformed = await self.executor.execute(malformed_args_block)
        self.assertEqual(res_malformed.status, ToolStatus.ERROR)
        self.assertIn("Missing required parameters", res_malformed.output)


class TestPrompts(unittest.TestCase):
    """Verifies JSON-backed prompt loading."""

    def setUp(self) -> None:
        self.prompts = Prompts()

    def test_default_prompt_loading(self) -> None:
        prompts = self.prompts.family("reflexion")
        self.assertIn("agent_system_prompt", prompts)

    def test_prompt_keys_include_core_assets(self) -> None:
        self.assertIn(Prompt.REFLEXION_AGENT_SYSTEM_PROMPT, self.prompts.keys())


class TestSdkClient(unittest.TestCase):
    """Verifies VidbyteSDK namespace bindings."""

    def setUp(self) -> None:
        self.sdk = VidbyteSDK()

    def test_sdk_namespace_bindings(self) -> None:
        self.assertIsNotNone(self.sdk.tools)
        self.assertIsNotNone(self.sdk.harnesses)
        self.assertIsNotNone(self.sdk.providers)
        self.assertIsNotNone(self.sdk.tools.registry)
        self.assertIsNotNone(self.sdk.tools.executor)


if __name__ == "__main__":
    unittest.main()
