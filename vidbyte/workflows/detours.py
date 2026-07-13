"""FILE: vidbyte/workflows/detours.py
PURPOSE: Defines deterministic side-condition signals, matchers, and detour return frames.
ROLE IN CODEBASE: AgentStage emits signals; graph.py compiles rules; machine.py owns the stack.

ARCHITECTURE NOTE:
    Detours are declared control flow, not arbitrary interrupts. Matchers inspect
    bounded data only, declaration order wins, and immutable frames preserve where
    execution must return after validation or remediation completes.

PUBLIC API INVENTORY:
    WorkflowSignal: Bounded side-condition fact from a stage or successful tool call.
    SignalMatcher / CallableSignalMatcher / SignalTypeMatcher / FileSignalMatcher:
        Stable deterministic rule predicates.
    DetourRule / DetourReturnMode / DetourFrame: Compiled detour and stack contracts.

COMMON MODIFICATION PATTERNS:
    Add matcher types here, give each a stable matcher_id/fingerprint, and keep route
    declaration and stack behavior in graph.py/machine.py.

WHAT NOT TO DO IN THIS FILE:
    1. Do not run models or embedding similarity inside a matcher.
    2. Do not choose undeclared targets from signal data.
    3. Do not mutate continuation frames after entry.

KNOWN EDGE CASES:
    Missing tool result paths do not match FileSignalMatcher. File globs use normalized
    forward-slash paths and do not imply filesystem sandboxing or rollback.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-harness-state-machine-runtime.md

TESTS:
    No new test file by approved design; inline smoke covers match order and nested return.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.lib.dataclasses.tools import ToolStatus
from vidbyte.middleware.base import AgentMiddleware


@dataclass(frozen=True, slots=True)
class WorkflowSignal:
    """Bounded deterministic side-condition emitted during workflow execution."""

    signal_type: str
    source: str
    data: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalizes routing identifiers and protects signal evidence from mutation.
        object.__setattr__(self, "signal_type", _required_text(self.signal_type, "WorkflowSignal.signal_type"))
        object.__setattr__(self, "source", _required_text(self.source, "WorkflowSignal.source"))
        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))


@runtime_checkable
class SignalMatcher(Protocol):
    """Pure deterministic predicate with stable definition fingerprint identity."""

    @property
    def matcher_id(self) -> str:
        # Returns the stable matcher/version identifier included in graph hashing.
        ...

    def matches(self, signal: WorkflowSignal) -> bool:
        # Returns whether the bounded signal triggers this rule.
        ...

    def fingerprint(self) -> Mapping[str, Any]:
        # Returns stable JSON-ready configuration excluding executable credentials.
        ...


@dataclass(frozen=True, slots=True)
class CallableSignalMatcher:
    """Wraps a caller-owned pure matcher under an explicit stable identity."""

    matcher_id: str
    callback: Callable[[WorkflowSignal], bool]

    def __post_init__(self) -> None:
        # Rejects anonymous or non-callable matcher declarations before compilation.
        object.__setattr__(self, "matcher_id", _required_text(self.matcher_id, "CallableSignalMatcher.matcher_id"))
        if not callable(self.callback):
            raise TypeError("CallableSignalMatcher.callback must be callable.")

    def matches(self, signal: WorkflowSignal) -> bool:
        # Evaluates the caller predicate and normalizes its result to bool.
        return bool(self.callback(signal))

    def fingerprint(self) -> Mapping[str, Any]:
        # Fingerprints only the caller-supplied stable ID, never callable bytecode.
        return {"matcher_id": self.matcher_id}


@dataclass(frozen=True, slots=True)
class SignalTypeMatcher:
    """Matches one signal type with optional exact source and data fields."""

    signal_type: str
    source: str | None = None
    data_equals: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalizes exact match values and freezes caller mappings.
        object.__setattr__(self, "signal_type", _required_text(self.signal_type, "SignalTypeMatcher.signal_type"))
        object.__setattr__(self, "source", self.source.strip() if isinstance(self.source, str) and self.source.strip() else None)
        object.__setattr__(self, "data_equals", MappingProxyType(dict(self.data_equals)))

    @property
    def matcher_id(self) -> str:
        # Identifies the built-in exact signal matcher contract.
        return "signal_type:v1"

    def matches(self, signal: WorkflowSignal) -> bool:
        # Requires the declared type/source and every configured exact data field.
        if signal.signal_type != self.signal_type or (self.source is not None and signal.source != self.source):
            return False
        return all(signal.data.get(key) == value for key, value in self.data_equals.items())

    def fingerprint(self) -> Mapping[str, Any]:
        # Returns stable exact-match configuration for definition hashing.
        return {"matcher_id": self.matcher_id, "signal_type": self.signal_type, "source": self.source, "data_equals": dict(self.data_equals)}


@dataclass(frozen=True, slots=True)
class FileSignalMatcher:
    """Matches normalized file-change signal paths against declared globs."""

    globs: tuple[str, ...]
    signal_type: str = "file.changed"
    path_field: str = "path"

    def __post_init__(self) -> None:
        # Validates non-empty glob rules and stable signal/path field identifiers.
        patterns = tuple(_required_text(item, "FileSignalMatcher.globs item") for item in self.globs)
        if not patterns:
            raise ValueError("FileSignalMatcher.globs must contain at least one pattern.")
        object.__setattr__(self, "globs", patterns)
        object.__setattr__(self, "signal_type", _required_text(self.signal_type, "FileSignalMatcher.signal_type"))
        object.__setattr__(self, "path_field", _required_text(self.path_field, "FileSignalMatcher.path_field"))

    @property
    def matcher_id(self) -> str:
        # Identifies the built-in normalized file glob matcher contract.
        return "file_signal:v1"

    def matches(self, signal: WorkflowSignal) -> bool:
        # Matches only present string paths after separator normalization.
        if signal.signal_type != self.signal_type:
            return False
        raw_path = signal.data.get(self.path_field)
        if not isinstance(raw_path, str) or not raw_path.strip():
            return False
        path = PurePosixPath(raw_path.replace("\\", "/").lstrip("./"))
        return any(path.match(pattern) for pattern in self.globs)

    def fingerprint(self) -> Mapping[str, Any]:
        # Returns stable path match configuration for definition hashing.
        return {"matcher_id": self.matcher_id, "globs": self.globs, "signal_type": self.signal_type, "path_field": self.path_field}


class DetourReturnMode(str, Enum):
    """Continuation behavior after a detour stage explicitly returns."""

    RETRY_SOURCE = "retry_source"
    RESUME_TARGET = "resume_target"


@dataclass(frozen=True, slots=True)
class DetourRule:
    """Stable named matcher used by a compiled graph detour declaration."""

    rule_id: str
    matcher: SignalMatcher

    def __post_init__(self) -> None:
        # Validates stable rule identity and the structural matcher protocol.
        object.__setattr__(self, "rule_id", _required_text(self.rule_id, "DetourRule.rule_id"))
        if not isinstance(self.matcher, SignalMatcher):
            raise TypeError("DetourRule.matcher must satisfy SignalMatcher.")


@dataclass(frozen=True, slots=True)
class DetourFrame:
    """Immutable return address and pending continuation for one active detour."""

    rule_id: str
    source_stage: str
    target_stage: str
    return_mode: DetourReturnMode
    signal: WorkflowSignal
    continuation: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalizes frame identity and freezes continuation data for checkpoints.
        for name in ("rule_id", "source_stage", "target_stage"):
            object.__setattr__(self, name, _required_text(getattr(self, name), f"DetourFrame.{name}"))
        mode = self.return_mode if isinstance(self.return_mode, DetourReturnMode) else DetourReturnMode(self.return_mode)
        object.__setattr__(self, "return_mode", mode)
        object.__setattr__(self, "continuation", MappingProxyType(dict(self.continuation)))


class _ToolDetourMiddleware(AgentMiddleware):
    """Aborts an agent immediately after a successful tool signal matches a detour."""

    name = "workflow_tool_detour"

    def __init__(self, rules: tuple[tuple[str, SignalMatcher], ...]) -> None:
        # Stores the compiled ordered matcher set without owning graph destinations.
        self.rules = tuple(rules)

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Converts a successful tool result to bounded signals and interrupts on first match.
        if ctx.tool_call is None or ctx.tool_result is None or ctx.tool_is_internal or ctx.tool_result.status is not ToolStatus.SUCCESS:
            return MiddlewareDecision.continue_()
        data = {key: value for key, value in ctx.tool_call.arguments.items() if key in {"path", "file", "file_path", "target", "cwd"}}
        for key in ("path", "file", "file_path"):
            if key in ctx.tool_result.metadata and key not in data:
                data[key] = ctx.tool_result.metadata[key]
        if "path" not in data:
            normalized_path = next((data[key] for key in ("file", "file_path", "target") if isinstance(data.get(key), str) and data[key]), None)
            if normalized_path is not None:
                data["path"] = normalized_path
        signals = [WorkflowSignal("tool.succeeded", ctx.tool_call.tool_name, data)]
        if ctx.tool_call.tool_name in {"patch_file", "replace_text", "write_text"} and any(key in data for key in ("path", "file", "file_path")):
            signals.append(WorkflowSignal("file.changed", ctx.tool_call.tool_name, data))
        matches = [(rule_id, signal) for rule_id, matcher in self.rules for signal in signals if matcher.matches(signal)]
        if not matches:
            return MiddlewareDecision.continue_()
        return MiddlewareDecision.abort(
            "workflow_detour_requested",
            metadata={
                "candidate_rule_ids": [rule_id for rule_id, _ in matches],
                "signals": [{"signal_type": signal.signal_type, "source": signal.source, "data": dict(signal.data)} for signal in signals],
            },
        )


def _required_text(value: str, field_name: str) -> str:
    # Normalizes stable identifiers and reports the precise empty field.
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty.")
    return text


__all__ = [
    "CallableSignalMatcher",
    "DetourFrame",
    "DetourReturnMode",
    "DetourRule",
    "FileSignalMatcher",
    "SignalMatcher",
    "SignalTypeMatcher",
    "WorkflowSignal",
]
