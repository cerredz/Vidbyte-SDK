"""Context Protocol Header

Description:
    Tests structured tool error taxonomy and authorable tool error propagation.
Purpose:
    Verifies both execution pipelines preserve error kind, hint, and retryability metadata.
Architecture:
    - Fixture tools raise validation, structured, plain, and MCP failures.
    - ToolErrorTaxonomyTests checks ToolExecutor, AgentRuntime, FunctionTool, and ToolResult accessors.
Relations:
    Related to vidbyte.tools.errors, vidbyte.tools.executor, and vidbyte.agents.runtime.
"""

from __future__ import annotations

import unittest

from vidbyte.agents import AgentRuntime
from vidbyte.lib.errors import McpToolExecutionError
from vidbyte.tools import BaseTool, ToolCall, ToolError, ToolErrorKind, ToolExecutor, ToolParameter, ToolResult, ToolSpec, Tools
from vidbyte.tools.function_tool import FunctionTool
from vidbyte.tools.security import PermissionPolicy


class RequiredArgTool(BaseTool):
    """Tool with one required argument used to exercise validation."""

    def spec(self) -> ToolSpec:
        # Returns a spec with one required argument.
        return ToolSpec(name="required_arg", description="Requires a value.", parameters=(ToolParameter("value", "string", "Value."),))

    async def execute(self, call: ToolCall) -> ToolResult:
        # Returns success when validation allows execution.
        return ToolResult.success(self.name, str(call.arguments["value"]))


class StructuredFailureTool(BaseTool):
    """Tool that raises a tool-authored structured error."""

    def spec(self) -> ToolSpec:
        # Returns a spec with a fallback hint that should lose to ToolError.hint.
        return ToolSpec(name="structured_failure", description="Raises ToolError.", default_error_hint="fallback hint")

    async def execute(self, call: ToolCall) -> ToolResult:
        # Raises a structured rate-limit error with author-provided guidance.
        raise ToolError(
            "quota window is exhausted",
            kind=ToolErrorKind.RATE_LIMITED,
            hint="wait for the quota window to reset",
            retryable=True,
        )


class PlainFailureTool(BaseTool):
    """Tool that raises an ordinary exception."""

    def spec(self) -> ToolSpec:
        # Returns a spec with a default hint for bare exceptions.
        return ToolSpec(name="plain_failure", description="Raises ValueError.", default_error_hint="check the input environment")

    async def execute(self, call: ToolCall) -> ToolResult:
        # Raises a backward-compatible unstructured exception.
        raise ValueError("boom")


class McpFailureTool(BaseTool):
    """Tool that raises the MCP execution exception at runtime."""

    def spec(self) -> ToolSpec:
        # Returns a spec for the MCP failure fixture.
        return ToolSpec(name="mcp_failure", description="Raises an MCP execution error.")

    async def execute(self, call: ToolCall) -> ToolResult:
        # Raises the MCP runtime failure type that should map to upstream_error.
        raise McpToolExecutionError("remote tool failed")


class ToolErrorTaxonomyTests(unittest.IsolatedAsyncioTestCase):
    """Verifies the structured tool error taxonomy end to end."""

    def test_tool_result_error_accessors_read_metadata(self) -> None:
        # Confirms Docs 2 and 3 can consume typed accessors without new storage fields.
        result = ToolResult.error(
            "lookup",
            "failed",
            metadata={"error": ToolErrorKind.RATE_LIMITED.value, "hint": "try later", "retryable": True},
        )

        self.assertEqual(result.error_kind, ToolErrorKind.RATE_LIMITED)
        self.assertEqual(result.hint, "try later")
        self.assertTrue(result.retryable)

    async def test_executor_labels_validation_as_invalid_arguments(self) -> None:
        # Ensures the standalone executor no longer reports argument failures as validation_error.
        result = await ToolExecutor(Tools([RequiredArgTool()])).execute_call(ToolCall("required_arg", {}))

        self.assertEqual(result.error_kind, ToolErrorKind.INVALID_ARGUMENTS)
        self.assertEqual(result.metadata["error"], "invalid_arguments")

    async def test_runtime_labels_validation_as_invalid_arguments(self) -> None:
        # Ensures the agent runtime no longer rewrites validation failures to execution errors.
        runtime = AgentRuntime(agent_name="agent", system_prompt="Work.", tools=Tools([RequiredArgTool()]), permission_policy=PermissionPolicy())

        context, result = await runtime.execute_tool_call(ToolCall("required_arg", {}), provider="openai")

        self.assertEqual(context.state.value, "failed")
        self.assertEqual(result.error_kind, ToolErrorKind.INVALID_ARGUMENTS)
        self.assertEqual(result.metadata["error"], "invalid_arguments")

    async def test_runtime_preserves_tool_error_fields(self) -> None:
        # Verifies a tool-authored ToolError reaches ToolResult metadata without flattening.
        runtime = AgentRuntime(agent_name="agent", system_prompt="Work.", tools=Tools([StructuredFailureTool()]), permission_policy=PermissionPolicy())

        _, result = await runtime.execute_tool_call(ToolCall("structured_failure", {}), provider="openai")

        self.assertEqual(result.output, "quota window is exhausted")
        self.assertEqual(result.error_kind, ToolErrorKind.RATE_LIMITED)
        self.assertEqual(result.hint, "wait for the quota window to reset")
        self.assertTrue(result.retryable)

    async def test_runtime_plain_exception_uses_default_hint(self) -> None:
        # Verifies bare exceptions remain execution failures and pick up ToolSpec.default_error_hint.
        runtime = AgentRuntime(agent_name="agent", system_prompt="Work.", tools=Tools([PlainFailureTool()]), permission_policy=PermissionPolicy())

        _, result = await runtime.execute_tool_call(ToolCall("plain_failure", {}), provider="openai")

        self.assertEqual(result.error_kind, ToolErrorKind.EXECUTION_FAILED)
        self.assertEqual(result.hint, "check the input environment")
        self.assertEqual(result.metadata["error_type"], "ValueError")
        self.assertIn("Tool execution failed: boom", result.output)

    async def test_executor_maps_mcp_execution_failure_to_upstream_error(self) -> None:
        # Verifies runtime MCP execution errors keep an upstream, retryable classification.
        result = await ToolExecutor(Tools([McpFailureTool()])).execute_call(ToolCall("mcp_failure", {}))

        self.assertEqual(result.error_kind, ToolErrorKind.UPSTREAM_ERROR)
        self.assertTrue(result.retryable)
        self.assertEqual(result.metadata["error_type"], "McpToolExecutionError")

    async def test_function_tool_validation_uses_invalid_arguments(self) -> None:
        # Ensures direct FunctionTool execution aligns with the new argument taxonomy.
        def double(value: int) -> int:
            # Doubles a valid integer input for the FunctionTool fixture.
            return value * 2

        result = await FunctionTool(double).execute(ToolCall("double", {"value": "not-an-int"}))

        self.assertEqual(result.error_kind, ToolErrorKind.INVALID_ARGUMENTS)
        self.assertEqual(result.metadata["error_type"], "validation")


if __name__ == "__main__":
    unittest.main()
