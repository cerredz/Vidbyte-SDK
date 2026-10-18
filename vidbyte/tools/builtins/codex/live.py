"""FILE: vidbyte/tools/builtins/codex/live.py

PURPOSE: The six CodexHost tools about live turns and usage: wait_codex_turn, get_codex_turn_result, track_codex_thread_usage and wait_codex_turns, which only read, and steer_codex_turn and interrupt_codex_turn, which change paid Codex work in flight.
ROLE IN CODEBASE: Part of vidbyte/tools/builtins/codex/; CodexHostTools lists the first five after the thread tools, and wait_codex_turns among the sixteen first-class tools, in the order of the CodexHost functions.
ARCHITECTURE NOTE: The wait, get, steer, interrupt and multi-wait tools accept only handles their own CodexToolScope created, and refuse any other before the host is called (INV-33, first-class INV-43). The usage tool takes any thread id, since it reads only what the host recorded (D-12).
COMMON MODIFICATION PATTERNS: A new handle tool resolves the thread and turn ids, checks ownership with the scope, then calls the host once.
KNOWN EDGE CASES: A wait, single or multi, never runs longer than CODEX_HOST_TOOL_MAX_WAIT_SECONDS, which is also its default, so a model that waits on a long turn gets a RUNNING snapshot back before any bridge's own call bound (D-31, EC-71). Wait, get and the multi-wait leave result.items out of their JSON (INV-35, first-class INV-43). The multi-wait returns when the first turn ends unless the model asks for all of them.
RELATED DOCS: docs/spec/codex-host/spec.md (section 9.2 tool table, rows 9 to 13); docs/spec/codex-host-first-class/spec.md (section 9.2 tool table, row 30)
TESTS: tests/features/codex_host/test_codex_host_tools.py, tests/features/codex_host/test_codex_host_feature_tools.py
"""

from __future__ import annotations

from vidbyte.lib.constants.codex import (
    CODEX_HOST_MIN_EXCLUSIVE_SECONDS,
    CODEX_HOST_TOOL_MAX_WAIT_SECONDS,
)
from vidbyte.lib.constants.codex_host import CODEX_HOST_WAIT_MAX_HANDLES
from vidbyte.lib.dataclasses.codex_host import CodexTurnHandle
from vidbyte.lib.enums.codex import CodexHostOperation, CodexTurnWaitMode
from vidbyte.tools.builtins.codex._base import _CodexHostTool
from vidbyte.tools.builtins.codex.descriptions import (
    GET_CODEX_TURN_RESULT_DESCRIPTION,
    INTERRUPT_CODEX_TURN_DESCRIPTION,
    RETURN_WHEN_DESCRIPTION,
    STEER_CODEX_TURN_DESCRIPTION,
    STEER_PROMPT_DESCRIPTION,
    THREAD_ID_DESCRIPTION,
    TRACK_CODEX_THREAD_USAGE_DESCRIPTION,
    TURN_ID_DESCRIPTION,
    TURNS_WAIT_TIMEOUT_DESCRIPTION,
    WAIT_CODEX_TURN_DESCRIPTION,
    WAIT_CODEX_TURNS_DESCRIPTION,
    WAIT_TIMEOUT_DESCRIPTION,
    WAIT_TURNS_DESCRIPTION,
)
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

WAIT = CodexHostOperation.WAIT_CODEX_TURN
GET = CodexHostOperation.GET_CODEX_TURN_RESULT
STEER = CodexHostOperation.STEER_CODEX_TURN
INTERRUPT = CodexHostOperation.INTERRUPT_CODEX_TURN
TRACK = CodexHostOperation.TRACK_CODEX_THREAD_USAGE
WAIT_MANY = CodexHostOperation.WAIT_CODEX_TURNS
WAIT_MODES = [member.value for member in CodexTurnWaitMode]
HANDLE_PROPERTIES = {
    "thread_id": {"type": "string", "description": THREAD_ID_DESCRIPTION},
    "turn_id": {"type": "string", "description": TURN_ID_DESCRIPTION},
}
HANDLE_FIELDS = ["thread_id", "turn_id"]
MIN_HANDLES = 1


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


class WaitCodexTurnsTool(_CodexHostTool):
    """Waits, for a bounded time, for the first or all of several turns this toolset started to end."""

    def spec(self) -> ToolSpec:
        # The handles are required; when to return and the bound are
        # optional, and the bound is capped.
        return ToolSpec(
            name=WAIT_MANY.value,
            description=WAIT_CODEX_TURNS_DESCRIPTION,
            permission=ToolPermission.READ,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["turns"],
                "properties": {
                    "turns": {
                        "type": "array",
                        "minItems": MIN_HANDLES,
                        "maxItems": CODEX_HOST_WAIT_MAX_HANDLES,
                        "items": {"type": "object", "additionalProperties": False, "required": HANDLE_FIELDS, "properties": dict(HANDLE_PROPERTIES)},
                        "description": WAIT_TURNS_DESCRIPTION,
                    },
                    "return_when": {"type": "string", "enum": WAIT_MODES, "description": RETURN_WHEN_DESCRIPTION},
                    "timeout_seconds": {"type": "number", "exclusiveMinimum": CODEX_HOST_MIN_EXCLUSIVE_SECONDS, "description": TURNS_WAIT_TIMEOUT_DESCRIPTION},
                },
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Return one snapshot per handle as a JSON array, without items.
        return await self._run(WAIT_MANY.value, self._perform(call))

    async def _perform(self, call: ToolCall) -> str:
        # @intent a-tool-multi-wait-is-owned-and-capped
        # Read the handles, when to return and the bound.
        handles = self._resolve_handles(call, "turns", required=True)
        return_when = self._resolve_choice(call, "return_when", CodexTurnWaitMode)
        timeout_seconds = self._resolve_seconds(call, "timeout_seconds")
        # Only this scope's handles are waited on, and never longer than
        # the tool cap, which is also the default (D-31, first-class
        # INV-43).
        for handle in handles:
            self._scope.require_owned(handle, WAIT_MANY)
        bound = min(timeout_seconds, CODEX_HOST_TOOL_MAX_WAIT_SECONDS) if timeout_seconds is not None else CODEX_HOST_TOOL_MAX_WAIT_SECONDS
        mode = return_when if return_when is not None else CodexTurnWaitMode.FIRST_COMPLETED
        # Every snapshot leaves out result.items, as the single wait does.
        return self._json(await self._host.wait_codex_turns(handles, return_when=mode, timeout_seconds=bound), without_items=True)


__all__ = [
    "GetCodexTurnResultTool",
    "InterruptCodexTurnTool",
    "SteerCodexTurnTool",
    "TrackCodexThreadUsageTool",
    "WaitCodexTurnTool",
    "WaitCodexTurnsTool",
]
