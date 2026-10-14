"""FILE: vidbyte/tools/builtins/codex/readiness.py

PURPOSE: The three read-only CodexHost tools about the runtime itself: check_codex_ready, get_codex_rate_limits and list_codex_models.
ROLE IN CODEBASE: Part of vidbyte/tools/builtins/codex/; CodexHostTools lists these three first, in the order of the CodexHost functions.
ARCHITECTURE NOTE: Each tool is a _CodexHostTool: its spec names the CodexHost function it calls, and its execute reads the arguments, calls the host once and returns the record as JSON through _run, so it never raises.
COMMON MODIFICATION PATTERNS: A new runtime read becomes one more READ tool class here, with its text in descriptions.py.
KNOWN EDGE CASES: check_codex_ready reports setup problems inside its result rather than as an error result.
RELATED DOCS: docs/spec/codex-host/spec.md (section 9.2 tool table, rows 1 to 3)
TESTS: tests/features/codex_host/test_codex_host_tools.py
"""

from __future__ import annotations

from vidbyte.lib.enums.codex import CodexHostOperation
from vidbyte.tools.builtins.codex._base import _CodexHostTool
from vidbyte.tools.builtins.codex.descriptions import (
    CHECK_CODEX_READY_DESCRIPTION,
    GET_CODEX_RATE_LIMITS_DESCRIPTION,
    INCLUDE_HIDDEN_DESCRIPTION,
    LIST_CODEX_MODELS_DESCRIPTION,
)
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

CHECK = CodexHostOperation.CHECK_CODEX_READY.value
RATE_LIMITS = CodexHostOperation.GET_CODEX_RATE_LIMITS.value
MODELS = CodexHostOperation.LIST_CODEX_MODELS.value


class CheckCodexReadyTool(_CodexHostTool):
    """Reports whether the Codex runtime behind the host is ready to run turns."""

    def spec(self) -> ToolSpec:
        # A read with no arguments.
        return ToolSpec(
            name=CHECK,
            description=CHECK_CODEX_READY_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={"type": "object", "additionalProperties": False, "properties": {}},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the readiness record as JSON.
        return await self._run(CHECK, self._perform())

    async def _perform(self) -> str:
        # One readiness check through the host.
        return self._json(await self._host.check_codex_ready())


class GetCodexRateLimitsTool(_CodexHostTool):
    """Reports the usage windows of the Codex account behind the host."""

    def spec(self) -> ToolSpec:
        # A read with no arguments.
        return ToolSpec(
            name=RATE_LIMITS,
            description=GET_CODEX_RATE_LIMITS_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={"type": "object", "additionalProperties": False, "properties": {}},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the rate-limit record as JSON.
        return await self._run(RATE_LIMITS, self._perform())

    async def _perform(self) -> str:
        # One rate-limit read through the host.
        return self._json(await self._host.get_codex_rate_limits())


class ListCodexModelsTool(_CodexHostTool):
    """Lists the models the Codex runtime behind the host offers."""

    def spec(self) -> ToolSpec:
        # One optional switch for hidden models.
        return ToolSpec(
            name=MODELS,
            description=LIST_CODEX_MODELS_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {"include_hidden": {"type": "boolean", "description": INCLUDE_HIDDEN_DESCRIPTION}},
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return every listed model as a JSON array.
        return await self._run(MODELS, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Read the switch, then list every page of models.
        include_hidden = self._resolve_bool_argument(call, "include_hidden", default=False)
        return self._json(await self._host.list_codex_models(include_hidden))


__all__ = ["CheckCodexReadyTool", "GetCodexRateLimitsTool", "ListCodexModelsTool"]
