"""FILE: vidbyte/tools/builtins/codex/live.py

PURPOSE: The five CodexHost tools about live turns and usage: wait_codex_turn, get_codex_turn_result and track_codex_thread_usage, which only read, and steer_codex_turn and interrupt_codex_turn, which change paid Codex work in flight.
ROLE IN CODEBASE: Part of vidbyte/tools/builtins/codex/; CodexHostTools lists these after the thread tools, in the order of the CodexHost functions.
ARCHITECTURE NOTE: The wait, get, steer and interrupt tools accept only handles their own CodexToolScope created, and refuse any other before the host is called (INV-33). The usage tool takes any thread id, since it reads only what the host recorded (D-12).
COMMON MODIFICATION PATTERNS: A new handle tool resolves the thread and turn ids, checks ownership with the scope, then calls the host once.
KNOWN EDGE CASES: A wait never runs longer than CODEX_HOST_TOOL_MAX_WAIT_SECONDS, which is also its default, so a model that waits on a long turn gets a RUNNING snapshot back before any bridge's own call bound (D-31, EC-71). Wait and get leave result.items out of their JSON (INV-35).
RELATED DOCS: docs/spec/codex-host/spec.md (section 9.2 tool table, rows 9 to 13)
TESTS: tests/features/codex_host/test_codex_host_tools.py
"""

from __future__ import annotations

from vidbyte.lib.constants.codex import (
    CODEX_HOST_MIN_EXCLUSIVE_SECONDS,
    CODEX_HOST_TOOL_MAX_WAIT_SECONDS,
)
from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle
from vidbyte.lib.enums.codex import CodexHostOperation
from vidbyte.tools.builtins.codex._base import _CodexHostTool
from vidbyte.tools.builtins.codex.descriptions import (
    GET_CODEX_TURN_RESULT_DESCRIPTION,
    INTERRUPT_CODEX_TURN_DESCRIPTION,
    STEER_CODEX_TURN_DESCRIPTION,
    STEER_PROMPT_DESCRIPTION,
    THREAD_ID_DESCRIPTION,
    TRACK_CODEX_THREAD_USAGE_DESCRIPTION,
    TURN_ID_DESCRIPTION,
    WAIT_CODEX_TURN_DESCRIPTION,
    WAIT_TIMEOUT_DESCRIPTION,
)
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

WAIT = CodexHostOperation.WAIT_CODEX_TURN
GET = CodexHostOperation.GET_CODEX_TURN_RESULT
STEER = CodexHostOperation.STEER_CODEX_TURN
INTERRUPT = CodexHostOperation.INTERRUPT_CODEX_TURN
TRACK = CodexHostOperation.TRACK_CODEX_THREAD_USAGE
HANDLE_PROPERTIES = {
    "thread_id": {"type": "string", "description": THREAD_ID_DESCRIPTION},
    "turn_id": {"type": "string", "description": TURN_ID_DESCRIPTION},
}
HANDLE_FIELDS = ["thread_id", "turn_id"]


class WaitCodexTurnTool(_CodexHostTool):
    """Waits, for a bounded time, for a turn this toolset started to end."""

    def spec(self) -> ToolSpec:
        # The handle, and an optional bound that is capped.
        return ToolSpec(
            name=WAIT.value,
            description=WAIT_CODEX_TURN_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": HANDLE_FIELDS,
                "properties": {
                    **HANDLE_PROPERTIES,
                    "timeout_seconds": {"type": "number", "exclusiveMinimum": CODEX_HOST_MIN_EXCLUSIVE_SECONDS, "description": WAIT_TIMEOUT_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the snapshot as JSON, without its items.
        return await self._run(WAIT.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # @intent a-tool-wait-is-capped
        # Only this scope's handles are waited on, and never longer than
        # the tool cap, which is also the default (D-31).
        handle = CodexTurnHandle(thread_id=self._resolve_text(call, "thread_id", required=True), turn_id=self._resolve_text(call, "turn_id", required=True))
        timeout_seconds = self._resolve_seconds(call, "timeout_seconds")
        self._scope.require_owned(handle, WAIT)
        bound = min(timeout_seconds, CODEX_HOST_TOOL_MAX_WAIT_SECONDS) if timeout_seconds is not None else CODEX_HOST_TOOL_MAX_WAIT_SECONDS
        return self._json(await self._host.wait_codex_turn(handle, timeout_seconds=bound), without_items=True)


class GetCodexTurnResultTool(_CodexHostTool):
    """Returns the current snapshot of a turn this toolset started, without waiting."""

    def spec(self) -> ToolSpec:
        # The handle only.
        return ToolSpec(
            name=GET.value,
            description=GET_CODEX_TURN_RESULT_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={"type": "object", "additionalProperties": False, "required": HANDLE_FIELDS, "properties": dict(HANDLE_PROPERTIES)},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the snapshot as JSON, without its items.
        return await self._run(GET.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Only this scope's handles are read.
        handle = CodexTurnHandle(thread_id=self._resolve_text(call, "thread_id", required=True), turn_id=self._resolve_text(call, "turn_id", required=True))
        self._scope.require_owned(handle, GET)
        return self._json(await self._host.get_codex_turn_result(handle), without_items=True)


class SteerCodexTurnTool(_CodexHostTool):
    """Adds input to a running turn this toolset started."""

    def spec(self) -> ToolSpec:
        # The handle and the new input.
        return ToolSpec(
            name=STEER.value,
            description=STEER_CODEX_TURN_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": [*HANDLE_FIELDS, "prompt"],
                "properties": {**HANDLE_PROPERTIES, "prompt": {"type": "string", "description": STEER_PROMPT_DESCRIPTION}},
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the same handle as JSON.
        return await self._run(STEER.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Only this scope's handles are steered.
        handle = CodexTurnHandle(thread_id=self._resolve_text(call, "thread_id", required=True), turn_id=self._resolve_text(call, "turn_id", required=True))
        prompt = self._resolve_text(call, "prompt", required=True)
        self._scope.require_owned(handle, STEER)
        return self._json(await self._host.steer_codex_turn(handle, prompt))


class InterruptCodexTurnTool(_CodexHostTool):
    """Stops a running turn this toolset started."""

    def spec(self) -> ToolSpec:
        # The handle only.
        return ToolSpec(
            name=INTERRUPT.value,
            description=INTERRUPT_CODEX_TURN_DESCRIPTION,
            permission=ToolPermission.WRITE,
            input_schema={"type": "object", "additionalProperties": False, "required": HANDLE_FIELDS, "properties": dict(HANDLE_PROPERTIES)},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the fixed sentence of section 9.2.
        return await self._run(INTERRUPT.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Only this scope's handles are interrupted.
        handle = CodexTurnHandle(thread_id=self._resolve_text(call, "thread_id", required=True), turn_id=self._resolve_text(call, "turn_id", required=True))
        self._scope.require_owned(handle, INTERRUPT)
        await self._host.interrupt_codex_turn(handle)
        return f"Interrupt requested for turn {handle.turn_id}; call wait_codex_turn to collect its result."


class TrackCodexThreadUsageTool(_CodexHostTool):
    """Reports the token usage and cost of the turns the host saw end on a thread."""

    def spec(self) -> ToolSpec:
        # Any thread id.
        return ToolSpec(
            name=TRACK.value,
            description=TRACK_CODEX_THREAD_USAGE_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["thread_id"],
                "properties": {"thread_id": {"type": "string", "description": THREAD_ID_DESCRIPTION}},
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return the usage record as JSON.
        return await self._run(TRACK.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # Read the thread's recorded usage.
        thread_id = self._resolve_text(call, "thread_id", required=True)
        return self._json(await self._host.track_codex_thread_usage(thread_id))


__all__ = [
    "GetCodexTurnResultTool",
    "InterruptCodexTurnTool",
    "SteerCodexTurnTool",
    "TrackCodexThreadUsageTool",
    "WaitCodexTurnTool",
]
