"""FILE: vidbyte/tools/builtins/native_host_tool.py

PURPOSE: Defines the shared base of the 43 native host tools: NativeHostTool (one tool over one host or backend function, which never raises anything but cancellation), NativeToolArguments (turns JSON arguments into typed values, naming the parameter on failure) and NativeResultEncoder (turns a result record into sorted-key JSON clipped to the output cap).
ROLE IN CODEBASE: Subclassed by the tool classes in vidbyte/tools/builtins/grok/, opencode/, muse/ and harness_backends/; those tools are bundled by the toolsets in vidbyte/tools/toolsets/. Imports only vidbyte.lib and vidbyte.tools, never a host package.
ARCHITECTURE NOTE: A thin-wrapper base (AGENTS.md principle 5): execute has one try around the subclass's _invoke, which parses the arguments and calls exactly one host function. NativeHostError becomes an error result carrying its code and next step (EC-139); a ConfigurationError from argument parsing or record construction becomes configuration.invalid_argument naming the parameter from details["field"] (EC-138); any other Exception becomes runtime.error naming only the class (EC-140); CancelledError passes through (EC-141).
FUNCTION INVENTORY: NativeHostTool.spec declares the tool; execute runs it; _failure renders an error result; _refusal and _defect build the error for a refused argument or a defect; _invoke is the per-tool call. NativeToolArguments: text, integer, number, seconds, choice and handle. NativeResultEncoder: encode and plain.
COMMON MODIFICATION PATTERNS: A new tool subclasses NativeHostTool, sets the five class attributes and implements _invoke with NativeToolArguments; a new JSON shape for results is one more branch in NativeResultEncoder.plain.
WHAT NOT TO DO IN THIS FILE: 1. Do not build a message from str(exc) or an f-string of a caught exception (S017); refusals name only the parameter and defects only the class. 2. Do not catch BaseException or CancelledError. 3. Do not encode a field declared repr=False; such fields hold secrets.
KNOWN EDGE CASES: A required parameter that is missing reaches execute only when execute is called directly; under ToolExecutor, validate_call reports it first as validation_error. A bool is refused where an integer or number is expected. Clipping cuts at a UTF-8 boundary, so the output may be a few bytes under the cap and is no longer valid JSON.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Tools), §9.2 (Tool results), EC-138 to EC-145; vidbyte/tools/README.md
TESTS: tests/features/grok_host/test_grok_host_tools.py, tests/features/opencode_host/test_opencode_host_tools.py, tests/features/muse_host/test_muse_host_tools.py, tests/features/native_backends/test_native_backends_tools.py
"""

from __future__ import annotations

import dataclasses
import json
from abc import abstractmethod
from collections.abc import Mapping
from decimal import Decimal
from enum import Enum
from pathlib import PurePath
from typing import Any, ClassVar, Generic, TypeVar

from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.native_hosts import NativeTurnHandle
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.enums.native_hosts import NativeHarness
from vidbyte.lib.errors import ConfigurationError, NativeHostError
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)

HostT = TypeVar("HostT")
EnumT = TypeVar("EnumT", bound=Enum)
_HANDLE_PARAMETER = "handle"
_HANDLE_FIELDS = ("harness", "session_id", "turn_id")
_UNNAMED_PARAMETER = "arguments"
_RETRYABLE_KEY = "retryable"


class NativeToolArguments:
    """Turns one tool call's JSON arguments into typed values; a failure raises ConfigurationError naming the parameter."""

    @staticmethod
    def text(call: ToolCall, name: str, *, required: bool = False) -> str | None:
        # A JSON string, or None when the parameter is optional and left out or null.
        value = call.arguments.get(name)
        if value is None and not required:
            return None
        return str(RecordFieldConverter.require_instance(value, name, str))

    @staticmethod
    def integer(call: ToolCall, name: str) -> int | None:
        # A JSON integer (never a bool or a float), or None when left out or null.
        value = call.arguments.get(name)
        if value is None:
            return None
        return int(RecordFieldConverter.require_instance(value, name, int))

    @staticmethod
    def number(call: ToolCall, name: str) -> float | None:
        # A JSON number (never a bool), or None when left out or null; ranges are the record's to check.
        value = call.arguments.get(name)
        if value is None:
            return None
        return float(RecordFieldConverter.require_instance(value, name, (int, float)))

    @staticmethod
    def seconds(call: ToolCall, name: str, *, default: float) -> float:
        # @intent native-tools-cap-blocking-waits
        # A tool call that blocks (a wait, or a one-shot run) may last at
        # most NATIVE_TOOL_WAIT_MAX_SECONDS, so it ends before the calling
        # agent's own tool cutoff (EC-144); left out or null means default.
        value = call.arguments.get(name)
        if value is None:
            return default
        return RecordFieldValidator.require_number(value, name, maximum=native_host_constants.NATIVE_TOOL_WAIT_MAX_SECONDS)

    @staticmethod
    def choice(call: ToolCall, name: str, enum_type: type[EnumT]) -> EnumT | None:
        # The enum member whose exact value the model sent, or None when left out or null.
        value = call.arguments.get(name)
        if value is None:
            return None
        return RecordFieldConverter.to_enum(value, enum_type, name)

    @staticmethod
    def handle(call: ToolCall) -> NativeTurnHandle:
        # The handle object {harness, session_id, turn_id} of strings (EC-145);
        # any other shape is refused as the handle parameter, whichever part is wrong.
        value = call.arguments.get(_HANDLE_PARAMETER)
        try:
            fields = RecordFieldConverter.require_instance(value, _HANDLE_PARAMETER, Mapping)
            parts = [RecordFieldConverter.require_instance(fields.get(key), _HANDLE_PARAMETER, str) for key in _HANDLE_FIELDS]
            harness = RecordFieldConverter.to_enum(parts[0], NativeHarness, _HANDLE_PARAMETER)
            return NativeTurnHandle(harness=harness, session_id=parts[1], turn_id=parts[2])
        except ConfigurationError as exc:
            raise ConfigurationError("handle must be an object with string harness, session_id and turn_id from a spawn or continue result.", details={"field": _HANDLE_PARAMETER}) from exc


class NativeResultEncoder:
    """Turns a host result into JSON text with sorted keys, clipped at NATIVE_TOOL_OUTPUT_MAX_BYTES on a UTF-8 boundary."""

    @staticmethod
    def encode(value: object) -> tuple[str, bool]:
        # Returns the JSON text and whether it was clipped (EC-143).
        text = json.dumps(NativeResultEncoder.plain(value), sort_keys=True, ensure_ascii=False)
        encoded = text.encode("utf-8")
        limit = native_host_constants.NATIVE_TOOL_OUTPUT_MAX_BYTES
        if len(encoded) <= limit:
            return text, False
        return encoded[:limit].decode("utf-8", errors="ignore"), True

    @staticmethod
    def plain(value: object) -> Any:
        # Enums as values, Decimal as text, tuples as lists, frozensets as lists
        # sorted by value, mappings as objects and records as objects of their
        # shown fields; a repr=False field holds a secret and is left out.
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, Decimal | PurePath):
            return str(value)
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return {item.name: NativeResultEncoder.plain(getattr(value, item.name)) for item in dataclasses.fields(value) if item.repr}
        if isinstance(value, Mapping):
            return {str(key): NativeResultEncoder.plain(item) for key, item in value.items()}
        if isinstance(value, frozenset | set):
            return sorted((NativeResultEncoder.plain(item) for item in value), key=str)
        if isinstance(value, tuple | list):
            return [NativeResultEncoder.plain(item) for item in value]
        return value


class NativeHostTool(BaseTool, Generic[HostT]):
    """One model-facing tool over exactly one host or backend function; it returns errors as results and never raises them."""

    _TOOL_NAME: ClassVar[str]
    _PERMISSION: ClassVar[ToolPermission]
    _HARNESS: ClassVar[str]
    _DESCRIPTION: ClassVar[str]
    _PARAMETERS: ClassVar[tuple[ToolParameter, ...]] = ()

    def __init__(self, host: HostT) -> None:
        self._host = host

    def spec(self) -> ToolSpec:
        # @intent native-tools-declare-catalog-permission
        # The permission is the catalog's READ or WRITE tag, so the default
        # PermissionPolicy denies every WRITE tool before execute (EC-142).
        return ToolSpec(name=self._TOOL_NAME, description=self._DESCRIPTION, parameters=self._PARAMETERS, permission=self._PERMISSION)

    async def execute(self, call: ToolCall) -> ToolResult:
        # Parse the arguments and call the one host function this tool wraps.
        # Every failure becomes an error result the model can act on; only
        # cancellation passes through, so a cancelled caller stops at once.
        try:
            value = await self._invoke(call)
        except NativeHostError as exc:
            return self._failure(exc)
        except ConfigurationError as exc:
            return self._failure(self._refusal(exc))
        except Exception as exc:
            return self._failure(self._defect(exc))

        # Encode the record as sorted-key JSON, clipped to the output cap.
        output, truncated = NativeResultEncoder.encode(value)
        return ToolResult.success(self._TOOL_NAME, output, metadata={"harness": self._HARNESS, "operation": self._TOOL_NAME, "truncated": truncated})

    def _failure(self, error: NativeHostError) -> ToolResult:
        # @intent native-tools-error-shape
        # INV-7: "<code>: <message> Next step: <next_step>", with the code,
        # the next step (also as hint), the operation and the harness in the
        # metadata, and retryable only when the error knows it. Metadata
        # never carries vendor text.
        code = error.failure_code.value
        metadata: dict[str, Any] = {"error": code, "next_step": error.next_step, "hint": error.next_step, "operation": self._TOOL_NAME, "harness": self._HARNESS}
        if _RETRYABLE_KEY in error.context:
            metadata[_RETRYABLE_KEY] = error.context[_RETRYABLE_KEY] == native_host_constants.NATIVE_TRUE_TEXT
        return ToolResult.error(self._TOOL_NAME, f"{code}: {error.message} Next step: {error.next_step}", metadata=metadata)

    def _refusal(self, exc: ConfigurationError) -> NativeHostError:
        # A refused argument names its parameter from details["field"]
        # ("GrokTurnRequest.model" names "model"); its text is not copied.
        field = str(exc.details.get("field", "")).rsplit(".", 1)[-1] or _UNNAMED_PARAMETER
        step = native_host_constants.NATIVE_INVALID_ARGUMENT_NEXT_STEP.format(field=field)
        message = f"The {field} argument of {self._TOOL_NAME} is not valid; check its type and range in the parameter description."
        return NativeHostError(message, failure_code=FailureCode.CONFIGURATION_INVALID_ARGUMENT, operation=self._TOOL_NAME, next_step=step, context={"field": field})

    def _defect(self, exc: Exception) -> NativeHostError:
        # A defect names only the exception class; its text may hold paths or secrets.
        error_type = type(exc).__name__
        message = f"{self._TOOL_NAME} failed with an unexpected {error_type}."
        return NativeHostError(message, failure_code=FailureCode.RUNTIME_ERROR, operation=self._TOOL_NAME, error_type=error_type, context={"error_type": error_type})

    @abstractmethod
    async def _invoke(self, call: ToolCall) -> object:
        """Parse the call's arguments and call exactly one host function."""


__all__ = ["NativeHostTool", "NativeResultEncoder", "NativeToolArguments"]
