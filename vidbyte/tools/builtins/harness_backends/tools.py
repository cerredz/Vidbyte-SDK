"""FILE: vidbyte/tools/builtins/harness_backends/tools.py

PURPOSE: Defines HarnessBackendTool, the base of the backend tools, and the three READ tools over the backend functions: ListHarnessBackendsTool, CheckBackendReadyTool and GetDeepseekBalanceTool.
ROLE IN CODEBASE: Bundled by HarnessBackendTools in vidbyte/tools/toolsets/harness_backends.py; each tool calls one function of vidbyte.harnesses.native.backends. Exported by vidbyte/tools/builtins/harness_backends/__init__.py.
ARCHITECTURE NOTE: HarnessBackendTool is a NativeHostTool with no host (the backend functions are module functions) and reports its harness as "backend". Each subclass sets its name, permission, description and parameters and implements _invoke as one argument parse and one function call; the base turns failures into error results.
FUNCTION INVENTORY: HarnessBackendTool.__init__ takes no host; each tool's _invoke parses its arguments and calls its function.
COMMON MODIFICATION PATTERNS: A new public backend function gets one more subclass here, its description in descriptions.py, and its entry in HarnessBackendTools.
WHAT NOT TO DO IN THIS FILE: 1. Do not add a tool for build_claude_backend_env, check_backend_compat or build_opencode_backend_provider; they are internal. 2. Do not accept a key, model or endpoint as a tool argument.
KNOWN EDGE CASES: check_backend_ready accepts only the exact lower-case profile names; the backend function refuses any other text as configuration.invalid_argument naming backend.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Tools), §9.2 rows 41-43, EC-147
TESTS: tests/features/native_backends/test_native_backends_tools.py, tests/features/native_backends/test_native_backends_errors.py
"""

from __future__ import annotations

from typing import ClassVar

from vidbyte.harnesses.native.backends import HarnessBackends
from vidbyte.tools.builtins.harness_backends.descriptions import (
    BACKEND_PARAMETER_DESCRIPTION,
    CHECK_BACKEND_READY_DESCRIPTION,
    GET_DEEPSEEK_BALANCE_DESCRIPTION,
    LIST_HARNESS_BACKENDS_DESCRIPTION,
)
from vidbyte.tools.builtins.native_host_tool import NativeHostTool, NativeToolArguments
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission

_BACKEND_PARAMETER = "backend"


class HarnessBackendTool(NativeHostTool[None]):
    """A tool over one backend module function; it has no host and reports its harness as backend."""

    _HARNESS: ClassVar[str] = "backend"

    def __init__(self) -> None:
        super().__init__(None)


class ListHarnessBackendsTool(HarnessBackendTool):
    """Lists the declared backend profiles."""

    _TOOL_NAME: ClassVar[str] = "list_harness_backends"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = LIST_HARNESS_BACKENDS_DESCRIPTION

    async def _invoke(self, call: ToolCall) -> object:
        # No arguments: return the profiles in declaration order.
        return HarnessBackends.list_harness_backends()


class CheckBackendReadyTool(HarnessBackendTool):
    """Checks that one backend's key is set and, where possible, verified."""

    _TOOL_NAME: ClassVar[str] = "check_backend_ready"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = CHECK_BACKEND_READY_DESCRIPTION
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = (ToolParameter(name=_BACKEND_PARAMETER, type="string", description=BACKEND_PARAMETER_DESCRIPTION, required=True),)

    async def _invoke(self, call: ToolCall) -> object:
        # The backend must be a string; the function refuses any name
        # but the declared ones.
        backend = NativeToolArguments.text(call, _BACKEND_PARAMETER, required=True)
        return await HarnessBackends.check_backend_ready(str(backend))


class GetDeepseekBalanceTool(HarnessBackendTool):
    """Reads the DeepSeek account balance."""

    _TOOL_NAME: ClassVar[str] = "get_deepseek_balance"
    _PERMISSION: ClassVar[ToolPermission] = ToolPermission.READ
    _DESCRIPTION: ClassVar[str] = GET_DEEPSEEK_BALANCE_DESCRIPTION

    async def _invoke(self, call: ToolCall) -> object:
        # No arguments: one read-only balance request
        # with the DeepSeek key.
        return await HarnessBackends.get_deepseek_balance()


__all__ = ["CheckBackendReadyTool", "GetDeepseekBalanceTool", "HarnessBackendTool", "ListHarnessBackendsTool"]
