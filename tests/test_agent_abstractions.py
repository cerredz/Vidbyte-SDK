# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the unit and integration tests for Vidbyte SDK agentic abstractions.
# Purpose: Validates the functionality, safety, thread-safety, and execution of tools, prompt registry, prompts, strategies, and harnesses.
# Architecture & Functions:
#   - TestTools (IsolatedAsyncioTestCase): Validates tool specs, registry, executor, and builtin tools.
#   - TestPrompts (TestCase): Validates prompt registry singleton, rendering, and runtime overrides.
#   - TestStrategiesAndHarnesses (IsolatedAsyncioTestCase): Validates top-level SDK wiring and default loops compilation.
# Codebase Relation:
#   - Executed as part of the test suite to verify code correctness and safety in the agent-abstractions feature branch.
# Similar Files:
#   - None (this is the core test module for agentic abstractions).
# ==============================================================================

from __future__ import annotations

import os
import sys
# Dynamic path resolution to ensure 'vidbyte' is importable regardless of working directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import json
import unittest
from typing import Any

from vidbyte.client import VidbyteSDK
from vidbyte.prompts.base import PromptRenderError
from vidbyte.prompts.registry import PromptRegistry
from vidbyte.prompts.types import PromptKey
from vidbyte.tools.builtins.calculator import CalculatorTool
from vidbyte.tools.builtins.code_execution import CodeExecutionTool
from vidbyte.tools.builtins.document_retrieval import DocumentRetrievalTool
from vidbyte.tools.builtins.web_search import WebSearchTool
from vidbyte.tools.executor import ToolExecutor
from vidbyte.tools.registry import ToolRegistry
from vidbyte.tools.types import ToolCall, ToolStatus


class TestTools(unittest.IsolatedAsyncioTestCase):
    """Verifies all Tools, ToolRegistry, ToolExecutor, and sandboxed safe environments."""

    def setUp(self) -> None:
        self.registry = ToolRegistry()
        self.executor = ToolExecutor(self.registry)

        # Instantiate builtin tools
        self.calculator = CalculatorTool()
        self.search = WebSearchTool()
        self.code_exec = CodeExecutionTool()
        self.doc_retrieval = DocumentRetrievalTool()

        # Register them
        self.registry.register(self.calculator)
        self.registry.register(self.search)
        self.registry.register(self.code_exec)
        self.registry.register(self.doc_retrieval)

    def test_tool_registry_management(self) -> None:
        """Tests tool registration, counts, and listing."""
        all_tools = self.registry.all()
        self.assertEqual(len(all_tools), 4)

        # Lookup by name
        fetched = self.registry.get("calculator")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "calculator")

        # Non-existent tool lookup
        self.assertIsNone(self.registry.get("invalid_tool_name"))

    def test_tool_specs_rendering(self) -> None:
        """Tests rendering tool specifications as standard prompt injection string."""
        specs_prompt = self.registry.specs_as_prompt_str()
        self.assertIn("calculator", specs_prompt)
        self.assertIn("web_search", specs_prompt)
        self.assertIn("code_execution", specs_prompt)
        self.assertIn("document_retrieval", specs_prompt)

    async def test_calculator_safety(self) -> None:
        """Tests that CalculatorTool executes safe math expressions and restricts unsafe imports or builtins."""
        # Safe executions
        res_add = await self.calculator.execute(ToolCall("calculator", {"expression": "2 + 2"}, ""))
        self.assertEqual(res_add.status, ToolStatus.SUCCESS)
        self.assertEqual(float(res_add.output.strip()), 4.0)

        res_complex = await self.calculator.execute(ToolCall("calculator", {"expression": "abs(-5) + min(10, 20) + round(3.456, 1)"}, ""))
        self.assertEqual(res_complex.status, ToolStatus.SUCCESS)
        self.assertEqual(float(res_complex.output.strip()), 18.5)

        # Unsafe executions (Blocked)
        res_unsafe_builtin = await self.calculator.execute(ToolCall("calculator", {"expression": "__import__('os').system('dir')"}, ""))
        self.assertEqual(res_unsafe_builtin.status, ToolStatus.ERROR)
        self.assertIn("double underscores", res_unsafe_builtin.error)

        res_unsafe_attrib = await self.calculator.execute(ToolCall("calculator", {"expression": "compile('2+2', '', 'eval')"}, ""))
        self.assertEqual(res_unsafe_attrib.status, ToolStatus.ERROR)
        self.assertIn("contains invalid math characters", res_unsafe_attrib.error)

        res_chars = await self.calculator.execute(ToolCall("calculator", {"expression": "hello_world()"}, ""))
        self.assertEqual(res_chars.status, ToolStatus.ERROR)
        self.assertIn("contains invalid math characters", res_chars.error)

    async def test_builtin_simulations(self) -> None:
        """Verifies simulated execution results of web search, code execution, and doc retrieval."""
        # Web Search
        res_search = await self.search.execute(ToolCall("web_search", {"query": "python"}, ""))
        self.assertEqual(res_search.status, ToolStatus.SUCCESS)
        self.assertIn("Python is a high-level", res_search.output)

        # Code Execution
        res_code = await self.code_exec.execute(ToolCall("code_execution", {"code": "print('hello from sandboxed runner')"}, ""))
        self.assertEqual(res_code.status, ToolStatus.SUCCESS)
        self.assertIn("hello from sandboxed runner", res_code.output)

        # Document Retrieval
        res_doc = await self.doc_retrieval.execute(ToolCall("document_retrieval", {"query": "react"}, ""))
        self.assertEqual(res_doc.status, ToolStatus.SUCCESS)
        self.assertIn("ReAct Design Architecture", res_doc.output)

    async def test_tool_executor_parser(self) -> None:
        """Tests parsing of Action blocks inside the ToolExecutor."""
        # Successful parse and run
        text_block = (
            "Thought: I should calculate this first.\n"
            "Action: calculator\n"
            "Action Input: {\"expression\": \"3 * 5\"}\n"
        )
        res = await self.executor.execute(text_block)
        self.assertEqual(res.status, ToolStatus.SUCCESS)
        self.assertEqual(float(res.output.strip()), 15.0)

        # Non-existent tool parse
        invalid_text_block = (
            "Action: missing_tool\n"
            "Action Input: {\"key\": \"val\"}\n"
        )
        res_invalid = await self.executor.execute(invalid_text_block)
        self.assertEqual(res_invalid.status, ToolStatus.ERROR)
        self.assertIn("not found in registry", res_invalid.error)

        # Malformed JSON args block
        malformed_args_block = (
            "Action: calculator\n"
            "Action Input: {expression: 3 * 5}\n"
        )
        res_malformed = await self.executor.execute(malformed_args_block)
        self.assertEqual(res_malformed.status, ToolStatus.ERROR)
        self.assertIn("Missing required parameters", res_malformed.error)


class TestPrompts(unittest.TestCase):
    """Verifies PromptRegistry thread-safety, singleton instantiations, rendering and developer overrides."""

    def setUp(self) -> None:
        self.registry = PromptRegistry()

    def test_singleton_behavior(self) -> None:
        """Ensures PromptRegistry functions strictly as a thread-safe singleton."""
        another_registry = PromptRegistry()
        self.assertIs(self.registry, another_registry)

    def test_default_prompt_loading(self) -> None:
        """Ensures built-in system translations are pre-registered on singleton construction."""
        key = PromptKey("strategies.react", "system")
        prompt = self.registry.get_raw(key)
        self.assertIsNotNone(prompt)
        self.assertIn("You are an autonomous ReAct agent", prompt.template)

    def test_prompt_rendering_validation(self) -> None:
        """Ensures variable bounds checks are correctly validated on prompt rendering."""
        key = PromptKey("strategies.react", "system")

        # Correct variables
        rendered = self.registry.get(key, tools="- Calculator: executes expressions.")
        self.assertIsNotNone(rendered)
        self.assertIn("- Calculator: executes expressions.", rendered.text)

        # Missing expected variables
        with self.assertRaises(PromptRenderError):
            self.registry.get(key)  # Missing 'tools' variable

    def test_developer_prompt_overrides(self) -> None:
        """Verifies runtime overriding mechanism works transparently and takes precedence."""
        key = PromptKey("strategies.react", "system")

        # Save previous raw
        original_prompt = self.registry.get_raw(key)

        # Override with custom prompt template
        override_template = "This is a custom ReAct override with {tools}."
        self.registry.override(key, override_template)

        # Verify override resolves
        rendered = self.registry.get(key, tools="custom_calculator")
        self.assertEqual(rendered.text, "This is a custom ReAct override with custom_calculator.")

        # Clean up / Restore original
        self.registry.override(key, original_prompt.template)
        restored = self.registry.get(key, tools="restored")
        self.assertIn("You are an autonomous ReAct agent", restored.text)


class TestStrategiesAndHarnesses(unittest.IsolatedAsyncioTestCase):
    """Verifies SDK-wide wiring and execution compile checks for all strategy and harness classes."""

    def setUp(self) -> None:
        self.sdk = VidbyteSDK()

    def test_sdk_namespace_bindings(self) -> None:
        """Validates that all major namespaces are instantiated and bound to the SDK client."""
        self.assertIsNotNone(self.sdk.tools)
        self.assertIsNotNone(self.sdk.prompts)
        self.assertIsNotNone(self.sdk.strategies)
        self.assertIsNotNone(self.sdk.harnesses)

        # Exposes the registries correctly
        self.assertIsNotNone(self.sdk.tools.registry)
        self.assertIsNotNone(self.sdk.tools.executor)

    async def test_react_strategy_compiles(self) -> None:
        """Ensures ReAct strategy compiles and resolves registries correctly."""
        res = await self.sdk.strategies.react.run("Double check the speed of sound in water.")
        self.assertEqual(res["strategy"], "react")
        self.assertEqual(res["status"], "ready")
        self.assertIn("calculator", res["tools_loaded"])
        self.assertIn("You are an autonomous ReAct agent", res["system_prompt"])

    async def test_tree_of_thoughts_strategy_compiles(self) -> None:
        """Ensures Tree of Thoughts strategy compiles and renders prompts correctly."""
        res = await self.sdk.strategies.tree_of_thoughts.run("Solve x^2 + 5x + 6 = 0")
        self.assertEqual(res["strategy"], "tree_of_thoughts")
        self.assertEqual(res["status"], "ready")
        self.assertIn("branching factor", res["branch_prompt"])
        self.assertIn("Branch 1", res["score_prompt"])

    async def test_reflexion_strategy_compiles(self) -> None:
        """Ensures Reflexion strategy compiles and renders prompts correctly."""
        res = await self.sdk.strategies.reflexion.run("Optimize this database query.")
        self.assertEqual(res["strategy"], "reflexion")
        self.assertEqual(res["status"], "ready")
        self.assertIn("Optimize this database query.", res["actor_prompt"])
        self.assertIn("Proposed solution text.", res["evaluator_prompt"])
        self.assertIn("The solver missed the bounds check.", res["reflector_prompt"])

    async def test_self_consistency_strategy_compiles(self) -> None:
        """Ensures Self-Consistency strategy compiles and renders prompts correctly."""
        res = await self.sdk.strategies.self_consistency.run("Is 103 prime?")
        self.assertEqual(res["strategy"], "self_consistency")
        self.assertEqual(res["status"], "ready")
        self.assertIn("Is 103 prime?", res["system_prompt"])

    async def test_step_back_strategy_compiles(self) -> None:
        """Ensures Step-Back strategy compiles and renders prompts correctly."""
        res = await self.sdk.strategies.step_back.run("Explain how planes fly.")
        self.assertEqual(res["strategy"], "step_back")
        self.assertEqual(res["status"], "ready")
        self.assertIn("Explain how planes fly.", res["abstraction_prompt"])
        self.assertIn("Newton's laws are invariant", res["reasoning_prompt"])

    async def test_conditional_harnesses_compile(self) -> None:
        """Ensures Conditional Loop Agent and stopping conditions run correct prompt bindings."""
        loop_res = await self.sdk.harnesses.conditional_loop.run("Analyze the transcript.")
        self.assertEqual(loop_res["harness"], "conditional_loop_agent")
        self.assertIn("Analyze the transcript.", loop_res["loop_prompt"])

        stop_res = await self.sdk.harnesses.stopping_evaluator.run("Is the work complete?")
        self.assertEqual(stop_res["harness"], "conditional_stopping_evaluator")
        self.assertIn("Is the work complete?", stop_res["evaluator_prompt"])


if __name__ == "__main__":
    unittest.main()
