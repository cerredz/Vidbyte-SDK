"""Context Protocol Header

Description:
    Tests the core Vidbyte tool contracts, registry, and executor.
Purpose:
    Verifies behavior that every built-in and bridged tool depends on.
Architecture:
    - EchoTool: Minimal test tool.
    - EchoActivity: Bounded activity annotation used by the binding tests.
    - ToolActivityTests: Binding, validation, and argument-separation tests.
    - ToolCustomizationTests: Immutable description overrides and wrapper composition.
    - ToolCoreTests: Registry, spec rendering, validation, and execution tests.
Relations:
    Related to vidbyte.tools.types, base, activity, customization, registry, and executor.
"""

from __future__ import annotations

import unittest

from pydantic import BaseModel, Field

from vidbyte.lib.errors import ToolRegistrationError, ToolRegistryError
from vidbyte.tools import (
    BaseTool,
    ToolActivity,
    ToolCall,
    ToolExecutor,
    ToolParameter,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    Tools,
    ToolsFormatter,
)
from vidbyte.tools.activity import ActivityToolFormatter


class EchoActivity(BaseModel):
    """Bounded annotation describing why the echo tool was called."""

    reason: str = Field(min_length=1, max_length=40)


class EchoTool(BaseTool):
    """Small tool that echoes a required value."""

    def __init__(self) -> None:
        """Record every argument mapping the tool actually executes against."""
        self.executed_arguments: list[dict] = []

    def spec(self) -> ToolSpec:
        """Return an echo tool spec."""
        return ToolSpec(
            name="echo",
            description="Echo input.",
            parameters=(ToolParameter("text", "string", "Text to echo."),),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Return the supplied text."""
        self.executed_arguments.append(dict(call.arguments))
        return ToolResult.success(self.name, str(call.arguments["text"]))


class ToolActivityTests(unittest.IsolatedAsyncioTestCase):
    """Verifies activity binding, validation, and argument separation."""

    def _bound_echo(self, *, required: bool = True) -> tuple[EchoTool, BaseTool]:
        """Return an echo tool and the same tool bound to a small echo activity."""
        tool = EchoTool()
        activity = ToolActivity(
            schema=EchoActivity,
            description="Explain the user-visible action this echo advances.",
            required=required,
            metadata={"schema_version": 1, "consumer": "tests"},
        )
        return tool, tool.with_activity(activity)

    def test_binding_preserves_tool_identity(self) -> None:
        """A bound tool keeps the wrapped name, description, permission, and original instance."""
        tool, bound = self._bound_echo()
        spec = bound.spec()

        self.assertEqual(spec.name, tool.spec().name)
        self.assertEqual(spec.description, tool.spec().description)
        self.assertEqual(spec.permission, tool.spec().permission)
        self.assertIsNotNone(spec.activity)
        self.assertIsNone(tool.spec().activity)
        self.assertIs(ActivityToolFormatter.unwrap(bound), tool)

    def test_double_binding_is_rejected(self) -> None:
        """A tool that already declares an activity cannot be bound again."""
        _, bound = self._bound_echo()

        with self.assertRaises(ToolRegistrationError):
            bound.with_activity(ToolActivity(schema=EchoActivity, description="Second binding."))

    def test_binding_rejects_conflicting_business_parameter(self) -> None:
        """A tool that already owns an 'activity' input cannot be silently shadowed."""

        class ActivityNamedTool(EchoTool):
            def spec(self) -> ToolSpec:
                return ToolSpec(
                    name="activity_named",
                    description="Owns an activity parameter.",
                    parameters=(ToolParameter("activity", "string", "A business argument."),),
                )

        with self.assertRaises(ToolRegistrationError):
            ActivityNamedTool().with_activity(ToolActivity(schema=EchoActivity, description="Conflicts."))

    def test_activity_schema_must_be_a_pydantic_model(self) -> None:
        """A non-BaseModel schema is rejected at declaration time."""
        with self.assertRaises(ValueError):
            ToolActivity(schema=dict, description="Not a model.")

    def test_prepared_call_separates_activity_from_arguments(self) -> None:
        """Preparation removes the reserved key and normalizes the annotation payload."""
        tool, bound = self._bound_echo()
        catalog = Tools([bound])

        prepared = catalog.prepare_call(ToolCall("echo", {"text": "hi", "activity": {"reason": "greet"}}))

        self.assertEqual(dict(prepared.arguments), {"text": "hi"})
        self.assertEqual(dict(prepared.activity.payload), {"reason": "greet"})
        self.assertEqual(dict(prepared.activity.metadata), {"schema_version": 1, "consumer": "tests"})
        self.assertIsNone(tool.spec().activity)

    async def test_underlying_tool_never_sees_the_activity_argument(self) -> None:
        """The wrapped tool executes against business arguments only."""
        tool, bound = self._bound_echo()
        catalog = Tools([bound])
        prepared = catalog.prepare_call(ToolCall("echo", {"text": "hi", "activity": {"reason": "greet"}}))

        result = await bound.execute(prepared)

        self.assertEqual(result.output, "hi")
        self.assertEqual(tool.executed_arguments, [{"text": "hi"}])

    async def test_missing_required_activity_fails_validation_without_execution(self) -> None:
        """A required annotation is a normal validation_error and the tool never runs."""
        tool, bound = self._bound_echo()
        executor = ToolExecutor(Tools([bound]))

        result = await executor.execute_call(ToolCall("echo", {"text": "hi"}))

        self.assertEqual(result.metadata["error"], "validation_error")
        self.assertIn("activity", result.output)
        self.assertEqual(tool.executed_arguments, [])

    async def test_invalid_activity_fails_validation_without_execution(self) -> None:
        """A schema-invalid annotation is rejected before the wrapped tool executes."""
        tool, bound = self._bound_echo()
        executor = ToolExecutor(Tools([bound]))

        result = await executor.execute_call(
            ToolCall("echo", {"text": "hi", "activity": {"reason": "x" * 100}})
        )

        self.assertEqual(result.metadata["error"], "validation_error")
        self.assertIn("reason", result.output)
        self.assertEqual(tool.executed_arguments, [])

    async def test_optional_activity_may_be_omitted(self) -> None:
        """An optional annotation leaves the call unannotated and still executes."""
        tool, bound = self._bound_echo(required=False)
        executor = ToolExecutor(Tools([bound]))

        result = await executor.execute_call(ToolCall("echo", {"text": "hi"}))

        self.assertEqual(result.output, "hi")
        self.assertEqual(tool.executed_arguments, [{"text": "hi"}])

    def test_preparation_is_idempotent(self) -> None:
        """Preparing an already-prepared call does not re-validate a stripped annotation."""
        _, bound = self._bound_echo()
        catalog = Tools([bound])
        prepared = catalog.prepare_call(ToolCall("echo", {"text": "hi", "activity": {"reason": "greet"}}))

        self.assertIs(catalog.prepare_call(prepared), prepared)

    async def test_direct_execution_never_leaks_a_malformed_annotation(self) -> None:
        """A caller that skips validation cannot pass the reserved key through as an argument."""
        tool, bound = self._bound_echo()

        await bound.execute(ToolCall("echo", {"text": "hi", "activity": {"reason": ""}}))

        self.assertEqual(tool.executed_arguments, [{"text": "hi"}])

    def test_captured_activity_payload_is_immutable(self) -> None:
        """A consumer cannot mutate a captured annotation through its payload mapping."""
        _, bound = self._bound_echo()
        prepared = Tools([bound]).prepare_call(
            ToolCall("echo", {"text": "hi", "activity": {"reason": "greet"}})
        )

        with self.assertRaises(TypeError):
            prepared.activity.payload["reason"] = "tampered"


class ToolCustomizationTests(unittest.IsolatedAsyncioTestCase):
    """Verifies immutable model-facing description customization."""

    def test_customization_preserves_original_tool_contract(self) -> None:
        """Customized text changes the returned spec without mutating the original tool."""
        tool = EchoTool()
        customized = tool.customize(
            description="Application-specific echo guidance.",
            parameter_descriptions={"text": "Application-specific text guidance."},
        )

        self.assertEqual(tool.spec().description, "Echo input.")
        self.assertEqual(tool.spec().parameters[0].description, "Text to echo.")
        self.assertEqual(customized.spec().description, "Application-specific echo guidance.")
        self.assertEqual(
            customized.spec().parameters[0].description,
            "Application-specific text guidance.",
        )
        self.assertEqual(customized.name, tool.name)

    def test_customization_rejects_unknown_or_blank_descriptions(self) -> None:
        """Invalid customization values fail before a wrapper can enter a catalog."""
        tool = EchoTool()

        with self.assertRaises(ValueError):
            tool.customize(parameter_descriptions={"missing": "Unknown parameter."})
        with self.assertRaises(ValueError):
            tool.customize(description=" ")
        with self.assertRaises(ValueError):
            tool.customize(parameter_descriptions={"text": " "})

    async def test_customization_delegates_execution_unchanged(self) -> None:
        """Customized tools execute the original implementation with unchanged arguments."""
        tool = EchoTool()
        customized = tool.customize(parameter_descriptions={"text": "Custom text."})

        result = await customized.execute(ToolCall("echo", {"text": "hello"}))

        self.assertEqual(result.output, "hello")
        self.assertEqual(tool.executed_arguments, [{"text": "hello"}])

    async def test_customization_composes_with_activity_in_both_orders(self) -> None:
        """Activity payloads remain separated when wrappers are composed either way."""
        tool = EchoTool()
        activity = ToolActivity(schema=EchoActivity, description="Explain this echo.")
        customized_then_activity = tool.customize(description="Custom echo.").with_activity(activity)
        activity_then_customized = tool.with_activity(activity).customize(description="Custom echo.")

        for wrapped in (customized_then_activity, activity_then_customized):
            prepared = Tools([wrapped]).prepare_call(
                ToolCall("echo", {"text": "hello", "activity": {"reason": "greet"}})
            )
            await wrapped.execute(prepared)
            self.assertIs(ActivityToolFormatter.unwrap(wrapped), tool)

        self.assertEqual(tool.executed_arguments, [{"text": "hello"}, {"text": "hello"}])


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
