"""Context Protocol Header

Description:
    Tests permission enforcement in the tool executor.
Purpose:
    Ensures risky tools are denied before their execute methods run unless a
    caller explicitly opts into broader permissions.
Architecture:
    - WriteTool: Test tool requiring WRITE permission.
    - SecurityExecutorTests: Default-deny and allow-all scenarios.
Relations:
    Related to vidbyte.tools.executor and vidbyte.tools.security.permissions.
"""

from __future__ import annotations

import unittest

from vidbyte.tools import BaseTool, ToolCall, ToolPermission, ToolRegistry, ToolResult, ToolSpec
from vidbyte.tools.executor import ToolExecutor
from vidbyte.tools.security import PermissionPolicy


class WriteTool(BaseTool):
    """Test tool that records whether execution happened."""

    def __init__(self) -> None:
        """Initialize execution tracking."""
        self.executed = False

    def spec(self) -> ToolSpec:
        """Return a WRITE-permission spec."""
        return ToolSpec(name="write", description="Write.", permission=ToolPermission.WRITE)

    async def execute(self, call: ToolCall) -> ToolResult:
        """Mark execution and return success."""
        del call
        self.executed = True
        return ToolResult.success(self.name, "ok")


class SecurityExecutorTests(unittest.IsolatedAsyncioTestCase):
    """Verifies permission policy behavior."""

    async def test_default_policy_denies_write_without_execution(self) -> None:
        """WRITE tools are denied by default and not executed."""
        tool = WriteTool()
        registry = ToolRegistry()
        registry.register(tool)
        result = await ToolExecutor(registry).execute_call(ToolCall("write", {}))
        self.assertEqual(result.status.value, "error")
        self.assertFalse(tool.executed)

    async def test_allow_all_policy_executes_write(self) -> None:
        """Explicit allow-all policy permits WRITE tools."""
        tool = WriteTool()
        registry = ToolRegistry()
        registry.register(tool)
        result = await ToolExecutor(
            registry,
            permission_policy=PermissionPolicy.allow_all(),
        ).execute_call(ToolCall("write", {}))
        self.assertEqual(result.status.value, "success")
        self.assertTrue(tool.executed)
