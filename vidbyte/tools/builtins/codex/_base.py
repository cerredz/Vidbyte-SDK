"""FILE: vidbyte/tools/builtins/codex/_base.py

PURPOSE: The shared parts of the fifteen CodexHost tools: CodexToolScope, which holds one toolset's live-turn cap, the developer's spawn defaults and the turn handles the toolset created, and _CodexHostTool, the base that turns every failure into an error result, reads model-written arguments and writes records as JSON.
ROLE IN CODEBASE: The base layer of vidbyte/tools/builtins/codex/; every tool module subclasses _CodexHostTool, and CodexHostTools in vidbyte/tools/toolsets/codex.py builds one CodexToolScope for its tools.
ARCHITECTURE NOTE: CodexHost is imported under TYPE_CHECKING only, so importing the tools never needs openai-codex. The scope's cap check and its reservation run with no await between them, so two concurrent calls can never pass the cap together (INV-32). The argument readers are BaseTool resolve_ helpers: JSON null means the argument was omitted, and a wrong type is a ToolExecutionError.
COMMON MODIFICATION PATTERNS: A new argument type gets one _resolve_ helper here; a new tool calls the helpers in its own execute and returns through _run.
KNOWN EDGE CASES: A cap check reads each live handle's status through get_codex_turn_result, a local read that sends nothing to Codex. A structured answer parsed into a pydantic model is written as that model's JSON.
RELATED DOCS: docs/spec/codex-host/spec.md (section 9.2 Tools and Scope rules; INV-10 and INV-32 to INV-35)
TESTS: tests/features/codex_host/test_codex_host_tools.py
"""

from __future__ import annotations

import json
import math
from collections.abc import Awaitable, Iterable, Mapping
from dataclasses import asdict
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel

from vidbyte.lib.constants.codex import (
    CODEX_HOST_MIN_EXCLUSIVE_SECONDS,
    CODEX_HOST_MIN_LIVE_TURNS,
    CODEX_HOST_MIN_TOKEN_LIMIT,
    CODEX_NEXT_STEPS,
)
from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest, CodexTurnHandle
from vidbyte.lib.enums.codex import CodexHostOperation, CodexTurnStatus
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError, ConfigurationError, ToolExecutionError
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolResult

if TYPE_CHECKING:
    from vidbyte.harnesses.native.codex import CodexHost

ChoiceT = TypeVar("ChoiceT", bound=Enum)

SESSION_BUSY = FailureCode.CODEX_SESSION_BUSY.value
SESSION_NOT_FOUND = FailureCode.CODEX_SESSION_NOT_FOUND.value
INVALID_ARGUMENT = FailureCode.CONFIGURATION_INVALID_ARGUMENT.value
NOT_OWNED_MESSAGE = "This toolset did not start the turn with that handle, so it cannot wait on, read, steer or interrupt it."


class CodexToolScope:
    """One toolset's live-turn cap, the developer's spawn defaults, and the turn handles the toolset created."""

    def __init__(self, *, max_live_turns: int, spawn_defaults: CodexSpawnRequest | None = None) -> None:
        # The cap is a whole number of turns, at least one. The defaults
        # are the developer's posture, so they carry no prompt and no goal,
        # which the model supplies (D-11, EC-57).
        if isinstance(max_live_turns, bool) or not isinstance(max_live_turns, int) or max_live_turns < CODEX_HOST_MIN_LIVE_TURNS:
            raise ConfigurationError(f"CodexToolScope max_live_turns must be an int of at least {CODEX_HOST_MIN_LIVE_TURNS}.")
        if spawn_defaults is not None and not isinstance(spawn_defaults, CodexSpawnRequest):
            raise ConfigurationError("CodexToolScope spawn_defaults must be a CodexSpawnRequest or None.")
        defaults = spawn_defaults or CodexSpawnRequest()
        if defaults.goal is not None or defaults.prompt != "":
            raise ConfigurationError("CodexToolScope spawn_defaults cannot carry a prompt or a goal; the model supplies them.")
        self.max_live_turns = max_live_turns
        self.spawn_defaults = defaults
        # Every handle this scope created, the ones not yet seen ending,
        # and the slots held by calls still starting turns.
        self._owned: set[CodexTurnHandle] = set()
        self._live: set[CodexTurnHandle] = set()
        self._reserved = 0

    async def reserve(self, host: CodexHost, count: int, operation: CodexHostOperation) -> None:
        # @intent the-cap-counts-running-and-reserved-turns
        # Drop the live turns that ended, by a local read that sends
        # nothing to Codex, then check the cap and reserve the slots with
        # no await in between, so two calls can never pass it together
        # (INV-32). The caller releases the slots when its start ends.
        for handle in tuple(self._live):
            snapshot = await host.get_codex_turn_result(handle)
            if snapshot.status is not CodexTurnStatus.RUNNING:
                self._live.discard(handle)
        held = len(self._live) + self._reserved
        if held + count > self.max_live_turns:
            message = f"This toolset already holds {held} of its {self.max_live_turns} live turns, so {count} more cannot start."
            raise CodexAgentError(message, failure_code=SESSION_BUSY, operation=operation.value, next_step=CODEX_NEXT_STEPS[SESSION_BUSY])
        self._reserved += count

    def release(self, count: int) -> None:
        # The start ended, in success or failure, so its slots are free.
        self._reserved -= count

    def own(self, handles: Iterable[CodexTurnHandle]) -> None:
        # New turns count against the cap until a check sees them end, and
        # only this scope's handle tools accept them (INV-33).
        for handle in handles:
            self._owned.add(handle)
            self._live.add(handle)

    def require_owned(self, handle: CodexTurnHandle, operation: CodexHostOperation) -> None:
        # A handle from another scope, or one nobody created, is refused
        # before the host is called (INV-33).
        if handle not in self._owned:
            raise CodexAgentError(NOT_OWNED_MESSAGE, failure_code=SESSION_NOT_FOUND, operation=operation.value, next_step=CODEX_NEXT_STEPS[SESSION_NOT_FOUND])


class _CodexHostTool(BaseTool):
    """A CodexHost tool: one host function behind a model-facing spec, answering with a result and never raising."""

    def __init__(self, host: CodexHost, scope: CodexToolScope) -> None:
        # Every tool of one toolset shares its host and its scope.
        self._host = host
        self._scope = scope

    async def _run(self, name: str, work: Awaitable[str]) -> ToolResult:
        # @intent tools-never-raise
        # A tool always answers with a result. A host failure keeps its
        # code and next step, and a bad argument or setup becomes
        # configuration.invalid_argument, so the model can recover from
        # either; only cancellation propagates (INV-10).
        try:
            output = await work
        except CodexAgentError as exc:
            return self._failure(name, exc.failure_code, exc.message, exc.next_step)
        except (ConfigurationError, ToolExecutionError) as exc:
            return self._failure(name, INVALID_ARGUMENT, exc.message, CODEX_NEXT_STEPS[INVALID_ARGUMENT])
        return ToolResult.success(name, output)

    @staticmethod
    def _failure(name: str, code: str, message: str, next_step: str) -> ToolResult:
        # The error text leads with the code and ends with the next step.
        return ToolResult.error(name, f"{code}: {message} Next step: {next_step}", metadata={"code": code, "next_step": next_step})

    @staticmethod
    def _resolve_text(call: ToolCall, name: str, *, required: bool = False) -> str:
        # Optional text defaults to ""; required text must be non-empty.
        value = call.arguments.get(name)
        if value is None and not required:
            return ""
        if not isinstance(value, str) or (required and not value.strip()):
            raise ToolExecutionError(f"'{name}' must be a {'non-empty ' if required else ''}string.", details={"parameter": name})
        return value

    @staticmethod
    def _resolve_count(call: ToolCall, name: str) -> int | None:
        # A whole number of at least one, or None when omitted.
        value = call.arguments.get(name)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < CODEX_HOST_MIN_TOKEN_LIMIT:
            raise ToolExecutionError(f"'{name}' must be a whole number of at least {CODEX_HOST_MIN_TOKEN_LIMIT}.", details={"parameter": name})
        return value

    @staticmethod
    def _resolve_seconds(call: ToolCall, name: str) -> float | None:
        # A finite number of seconds above zero, or None when omitted.
        value = call.arguments.get(name)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= CODEX_HOST_MIN_EXCLUSIVE_SECONDS:
            raise ToolExecutionError(f"'{name}' must be a finite number of seconds greater than {CODEX_HOST_MIN_EXCLUSIVE_SECONDS:g}.", details={"parameter": name})
        return float(value)

    @staticmethod
    def _resolve_choice(call: ToolCall, name: str, choices: type[ChoiceT]) -> ChoiceT | None:
        # One wire value of the enum, or None when omitted.
        value = call.arguments.get(name)
        if value is None:
            return None
        allowed = {member.value: member for member in choices}
        if not isinstance(value, str) or value not in allowed:
            raise ToolExecutionError(f"'{name}' must be one of: {', '.join(key for key in allowed if key)}.", details={"parameter": name})
        return allowed[value]

    @staticmethod
    def _resolve_choices(call: ToolCall, name: str, choices: type[ChoiceT]) -> tuple[ChoiceT, ...]:
        # A list of wire values of the enum, or () when omitted.
        value = call.arguments.get(name)
        if value is None:
            return ()
        allowed = {member.value: member for member in choices}
        if not isinstance(value, list) or not all(isinstance(item, str) and item in allowed for item in value):
            raise ToolExecutionError(f"'{name}' must be a list of: {', '.join(key for key in allowed if key)}.", details={"parameter": name})
        return tuple(allowed[item] for item in value)

    @staticmethod
    def _resolve_texts(call: ToolCall, name: str) -> tuple[str, ...]:
        # A required, non-empty list of non-empty strings.
        value = call.arguments.get(name)
        if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
            raise ToolExecutionError(f"'{name}' must be a non-empty list of non-empty strings.", details={"parameter": name})
        return tuple(value)

    @staticmethod
    def _resolve_schema(call: ToolCall, name: str) -> Mapping[str, Any] | None:
        # A JSON Schema object, or None when omitted.
        value = call.arguments.get(name)
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ToolExecutionError(f"'{name}' must be a JSON Schema object.", details={"parameter": name})
        return value

    @staticmethod
    def _json(record: Any, *, without_items: bool = False) -> str:
        # @intent tool-output-is-the-record-json
        # A record, or a tuple of records, becomes its JSON: enums as their
        # values and nested records as objects (INV-35). Wait and get leave
        # out result.items, which the final answer already sums up.
        data: Any = [asdict(item) for item in record] if isinstance(record, tuple) else asdict(record)
        if without_items and isinstance(data, dict) and isinstance(data.get("result"), dict):
            data["result"].pop("items", None)
        return json.dumps(data, default=_CodexHostTool._model_json)

    @staticmethod
    def _model_json(value: object) -> object:
        # A structured answer parsed into a pydantic model is written as
        # that model's JSON; nothing else in a record lacks a JSON form.
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        raise ToolExecutionError(f"A Codex record holds a {type(value).__name__} value with no JSON form.")


__all__ = ["CodexToolScope", "_CodexHostTool"]
