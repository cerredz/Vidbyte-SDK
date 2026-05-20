"""Context Protocol Header

Description:
    Tests the core Vidbyte tool contracts, registry, and executor.
Purpose:
    Verifies behavior that every built-in and bridged tool depends on.
Architecture:
    - EchoTool: Minimal test tool.
    - ToolCoreTests: Registry, spec rendering, validation, and execution tests.
Relations:
    Related to vidbyte.tools.types, base, registry, and executor.
"""

from __future__ import annotations

import unittest

from vidbyte.lib.errors import ToolRegistryError
from vidbyte.tools import (
    BaseTool,
    ToolCall,
    ToolParameter,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    ToolsFormatter,
)


class EchoTool(BaseTool):
    """Small tool that echoes a required value."""

    def spec(self) -> ToolSpec:
        """Return an echo tool spec."""
        return ToolSpec(
            name="echo",
            description="Echo input.",
            parameters=(ToolParameter("text", "string", "Text to echo."),),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Return the supplied text."""
        return ToolResult.success(self.name, str(call.arguments["text"]))


class ToolCoreTests(unittest.IsolatedAsyncioTestCase):
    """Verifies core tool infrastructure."""

    async def test_registry_and_executor_success(self) -> None:
        """Registered tools execute through the default executor."""
        registry = ToolRegistry()
        tool = EchoTool()
        registry.register(tool)
        result = await __import__("vidbyte.tools.executor", fromlist=["ToolExecutor"]).ToolExecutor(
            registry
        ).execute_call(ToolCall("echo", {"text": "hello"}))
        self.assertEqual(result.output, "hello")

    def test_duplicate_registration_fails(self) -> None:
        """Duplicate tool names are rejected."""
        registry = ToolRegistry()
        registry.register(EchoTool())
        with self.assertRaises(ToolRegistryError):
            registry.register(EchoTool())

    async def test_missing_required_parameter_returns_error(self) -> None:
        """Executor returns validation errors before tool execution."""
        registry = ToolRegistry()
        registry.register(EchoTool())
        executor = __import__("vidbyte.tools.executor", fromlist=["ToolExecutor"]).ToolExecutor(
            registry
        )
        result = await executor.execute_call(ToolCall("echo", {}))
        self.assertEqual(result.status.value, "error")
        self.assertIn("Missing required", result.output)

    def test_spec_prompt_rendering(self) -> None:
        """Tool specs render prompt-safe metadata."""
        rendered = EchoTool().spec().to_prompt_str()
        self.assertTrue(rendered.startswith("<tool>"))
        self.assertIn("Tool: echo", rendered)
        self.assertIn("text", rendered)
        self.assertTrue(rendered.endswith("</tool>"))

    def test_tools_formatter_converts_provider_tool_shapes(self) -> None:
        """Tool specs convert into supported provider declaration formats."""
        spec = EchoTool().spec()
        openai_tool = ToolsFormatter.to_openai_tool(spec)
        anthropic_tool = ToolsFormatter.to_anthropic_tool(spec)
        grok_tool = ToolsFormatter.to_grok_tool(spec)
        gemini_tool = ToolsFormatter.to_gemini_tool(spec)

        self.assertEqual(openai_tool["function"]["name"], "echo")
        self.assertEqual(anthropic_tool["name"], "echo")
        self.assertEqual(grok_tool["function"]["parameters"]["required"], ["text"])
        self.assertEqual(gemini_tool["function_declarations"][0]["name"], "echo")

    def test_tools_formatter_parses_provider_tool_calls(self) -> None:
        """Provider tool-call payloads normalize into ToolCall objects."""
        openai_call = ToolsFormatter.parse_openai_tool_call(
            {"function": {"name": "echo", "arguments": '{"text": "hello"}'}}
        )
        anthropic_call = ToolsFormatter.parse_anthropic_tool_call(
            {"type": "tool_use", "name": "echo", "input": {"text": "hello"}}
        )
        gemini_call = ToolsFormatter.parse_gemini_tool_call(
            {"functionCall": {"name": "echo", "args": {"text": "hello"}}}
        )

        self.assertEqual(openai_call, ToolCall("echo", {"text": "hello"}))
        self.assertEqual(anthropic_call, ToolCall("echo", {"text": "hello"}))
        self.assertEqual(gemini_call, ToolCall("echo", {"text": "hello"}))
