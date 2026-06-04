from __future__ import annotations

import unittest

from vidbyte.agents.runtime import AgentRuntime
from vidbyte.context import ContextWindowPlacement
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import TextContextItem
from vidbyte.lib.dataclasses.context import BaseContext as StrategyContext
from vidbyte.tools import BaseTool, ToolCall, ToolPermission, ToolResult, ToolSpec, Tools
from vidbyte.tools.security import PermissionPolicy


class BoundTool(BaseTool):
    """Stub tool that declares a binding to a primitive id."""

    def __init__(self, primitive_id: str) -> None:
        self._primitive_id = primitive_id

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="shell_read",
            description="Read a file via shell.",
            permission=ToolPermission.READ,
            binds_to_primitive=self._primitive_id,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult.success("shell_read", "file contents here")


class UnboundTool(BaseTool):
    """Stub tool with no primitive binding."""

    def spec(self) -> ToolSpec:
        return ToolSpec(name="echo", description="Echo input.", permission=ToolPermission.SAFE)

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult.success("echo", "hello")


def _make_runtime(tools: Tools, context_manager: ContextManager | None = None) -> AgentRuntime:
    return AgentRuntime(
        agent_name="tester",
        system_prompt="test",
        tools=tools,
        permission_policy=PermissionPolicy(),
        context_manager=context_manager,
    )


class PrimitiveBindingTests(unittest.TestCase):
    def test_bound_tool_success_routes_output_into_primitive(self) -> None:
        manager = ContextManager()
        tool = BoundTool("file:auth.py")
        runtime = _make_runtime(Tools([tool]), manager)
        call = ToolCall(tool_name="shell_read", arguments={})
        result = ToolResult.success("shell_read", "file contents here")

        returned = runtime._apply_primitive_binding(call, result)

        stored = manager.get_by_id("file:auth.py")
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertIn("file contents here", stored.to_context_text())

    def test_bound_tool_returns_acknowledgment_not_raw_output(self) -> None:
        manager = ContextManager()
        tool = BoundTool("file:auth.py")
        runtime = _make_runtime(Tools([tool]), manager)
        call = ToolCall(tool_name="shell_read", arguments={})
        result = ToolResult.success("shell_read", "raw file content")

        returned = runtime._apply_primitive_binding(call, result)

        self.assertIn("stored in primitive", returned.output)
        self.assertNotIn("raw file content", returned.output)

    def test_bound_tool_binding_uses_default_context_placement(self) -> None:
        manager = ContextManager()
        tool = BoundTool("file:auth.py")
        runtime = _make_runtime(Tools([tool]), manager)
        call = ToolCall(tool_name="shell_read", arguments={})
        result = ToolResult.success("shell_read", "raw file content")

        runtime._apply_primitive_binding(call, result)

        self.assertEqual(manager.placement_for("file:auth.py"), ContextWindowPlacement.END_OF_CONTEXT)

    def test_unbound_tool_passes_result_through_unchanged(self) -> None:
        manager = ContextManager()
        tool = UnboundTool()
        runtime = _make_runtime(Tools([tool]), manager)
        call = ToolCall(tool_name="echo", arguments={})
        result = ToolResult.success("echo", "hello")

        returned = runtime._apply_primitive_binding(call, result)

        self.assertIs(returned, result)

    def test_error_result_is_not_routed_into_primitive(self) -> None:
        manager = ContextManager()
        tool = BoundTool("file:auth.py")
        runtime = _make_runtime(Tools([tool]), manager)
        call = ToolCall(tool_name="shell_read", arguments={})
        result = ToolResult.error("shell_read", "permission denied")

        returned = runtime._apply_primitive_binding(call, result)

        self.assertIsNone(manager.get_by_id("file:auth.py"))
        self.assertIs(returned, result)

    def test_no_context_manager_passes_result_through(self) -> None:
        tool = BoundTool("file:auth.py")
        runtime = _make_runtime(Tools([tool]), context_manager=None)
        call = ToolCall(tool_name="shell_read", arguments={})
        result = ToolResult.success("shell_read", "content")

        returned = runtime._apply_primitive_binding(call, result)

        self.assertIs(returned, result)

    def test_binding_into_frozen_primitive_falls_back_to_raw(self) -> None:
        manager = ContextManager()
        frozen = TextContextItem(primitive_id="file:auth.py", title="Frozen", content="old", primitive_frozen=True)
        manager.upsert(frozen)
        tool = BoundTool("file:auth.py")
        runtime = _make_runtime(Tools([tool]), manager)
        call = ToolCall(tool_name="shell_read", arguments={})
        result = ToolResult.success("shell_read", "new content")

        returned = runtime._apply_primitive_binding(call, result)

        self.assertIs(returned, result)
        self.assertIs(manager.get_by_id("file:auth.py"), frozen)


class BuildSystemStringTests(unittest.TestCase):
    def test_system_string_includes_primitives_zone_between_fixed_and_body(self) -> None:
        manager = ContextManager()
        manager.upsert(TextContextItem(primitive_id="plan:current", title="My Plan", content="step A"))
        runtime = _make_runtime(Tools(), manager)
        ctx = StrategyContext(system_prompt="You are an agent.", memory="agent memory")

        system_string = runtime._build_system_string(ctx)

        fixed_idx = system_string.find("You are an agent.")
        primitives_idx = system_string.find("My Plan")
        body_idx = system_string.find("agent memory")
        self.assertGreater(primitives_idx, fixed_idx)
        self.assertGreater(body_idx, primitives_idx)

    def test_system_string_without_context_manager_skips_primitives_zone(self) -> None:
        runtime = _make_runtime(Tools(), context_manager=None)
        ctx = StrategyContext(system_prompt="sys", memory="mem")

        system_string = runtime._build_system_string(ctx)

        self.assertNotIn("## Context Window Primitives", system_string)

    def test_system_string_empty_registry_omits_primitives_header(self) -> None:
        manager = ContextManager()
        runtime = _make_runtime(Tools(), manager)
        ctx = StrategyContext(system_prompt="sys")

        system_string = runtime._build_system_string(ctx)

        self.assertNotIn("## Context Window Primitives", system_string)

    def test_tool_spec_binds_to_primitive_field_is_accessible(self) -> None:
        tool = BoundTool("plan:current")
        spec = tool.spec()

        self.assertEqual(spec.binds_to_primitive, "plan:current")

    def test_tool_spec_without_binding_has_none(self) -> None:
        tool = UnboundTool()
        spec = tool.spec()

        self.assertIsNone(spec.binds_to_primitive)


if __name__ == "__main__":
    unittest.main()

