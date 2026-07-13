"""FILE: vidbyte/workflows/detection.py
PURPOSE: Detects five normalized agent-loop signatures and aborts at safe boundaries.
ROLE IN CODEBASE: AgentStage injects this middleware; machine.py turns evidence into ERROR.

ARCHITECTURE NOTE:
    Detection is per agent invocation and deterministic. Fingerprints normalize volatile
    timestamps and identity fields while retaining tool names and semantic content. Numeric
    counters are redacted only for context-window errors. The middleware reports evidence;
    only machine.py changes lifecycle.

PUBLIC API INVENTORY:
    StuckPattern / StuckDetection: Stable typed evidence.
    StuckDetectionPolicy: Thresholds and bounded history size.
    StuckDetectorMiddleware: Five-pattern AgentMiddleware implementation.

COMMON MODIFICATION PATTERNS:
    Add a signature by recording bounded normalized history, emitting StuckDetection,
    and keeping thresholds explicit in StuckDetectionPolicy.

WHAT NOT TO DO IN THIS FILE:
    1. Do not compare timestamps, call IDs, or token counters literally.
    2. Do not mutate workflow lifecycle or choose a recovery route.
    3. Do not retain unbounded prompts, outputs, or exception text.

KNOWN EDGE CASES:
    Provider-specific error wording can prevent a repeated-error match. Global model-call,
    token, cost, and super-step caps remain the deterministic fallback.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-harness-state-machine-runtime.md

TESTS:
    No new test file by approved design; inline smoke exercises all five signatures.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.lib.dataclasses.tools import ToolStatus
from vidbyte.middleware.base import AgentMiddleware


class StuckPattern(str, Enum):
    """Supported normalized loop signatures."""

    IDENTICAL_ACTION_OBSERVATION = "identical_action_observation"
    IDENTICAL_ACTION_ERROR = "identical_action_error"
    REPEATED_MONOLOGUE = "repeated_monologue"
    ACTION_PING_PONG = "action_ping_pong"
    CONTEXT_WINDOW_ERROR = "context_window_error"


@dataclass(frozen=True, slots=True)
class StuckDetection:
    """Bounded evidence for one threshold-crossing signature."""

    pattern: StuckPattern
    fingerprint: str
    count: int
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalizes evidence into safe metadata suitable for event persistence.
        object.__setattr__(self, "pattern", self.pattern if isinstance(self.pattern, StuckPattern) else StuckPattern(self.pattern))
        fingerprint = str(self.fingerprint).strip()
        if not fingerprint or self.count <= 0:
            raise ValueError("StuckDetection requires a fingerprint and positive count.")
        object.__setattr__(self, "fingerprint", fingerprint)
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))

    def to_metadata(self) -> dict[str, Any]:
        # Converts evidence to the bounded middleware/event metadata shape.
        return {"pattern": self.pattern.value, "fingerprint": self.fingerprint, "count": self.count, "details": dict(self.details)}


@dataclass(frozen=True, slots=True)
class StuckDetectionPolicy:
    """Thresholds for the five stuck signatures and retained action history."""

    identical_action_observation: int = 4
    identical_action_error: int = 3
    repeated_monologue: int = 3
    ping_pong_actions: int = 6
    context_window_errors: int = 3
    history_size: int = 24

    def __post_init__(self) -> None:
        # Requires useful thresholds while ensuring history can contain a ping-pong window.
        for name in ("identical_action_observation", "identical_action_error", "repeated_monologue", "context_window_errors"):
            if not isinstance(getattr(self, name), int) or isinstance(getattr(self, name), bool) or getattr(self, name) < 2:
                raise ValueError(f"StuckDetectionPolicy.{name} must be an integer of at least 2.")
        if not isinstance(self.ping_pong_actions, int) or isinstance(self.ping_pong_actions, bool) or self.ping_pong_actions < 4 or self.ping_pong_actions % 2:
            raise ValueError("StuckDetectionPolicy.ping_pong_actions must be an even integer of at least 4.")
        if not isinstance(self.history_size, int) or isinstance(self.history_size, bool) or self.history_size < self.ping_pong_actions:
            raise ValueError("StuckDetectionPolicy.history_size must cover ping_pong_actions.")


@dataclass
class _DetectionRunState:
    # Bounded semantic histories keep detection memory independent of run length.
    action_observations: deque[str]
    action_errors: deque[str]
    actions: deque[str]
    monologues: deque[str]
    context_errors: deque[str]
    last_detection: StuckDetection | None = None


class StuckDetectorMiddleware(AgentMiddleware):
    """Abort an agent invocation after any configured stuck signature is observed."""

    name = "workflow_stuck_detector"

    def __init__(self, policy: StuckDetectionPolicy | None = None) -> None:
        # Stores immutable thresholds; per-run history is initialized by before_run.
        self.policy = policy or StuckDetectionPolicy()

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Initializes isolated bounded histories for this direct agent invocation.
        size = self.policy.history_size
        ctx.run_state[self.__class__] = _DetectionRunState(
            action_observations=deque(maxlen=size),
            action_errors=deque(maxlen=size),
            actions=deque(maxlen=size),
            monologues=deque(maxlen=size),
            context_errors=deque(maxlen=size),
        )
        return MiddlewareDecision.continue_()

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Checks repeated success/error cycles and alternating semantic actions.
        if ctx.tool_call is None or ctx.tool_result is None or ctx.tool_is_internal:
            return MiddlewareDecision.continue_()
        state = self._state(ctx)
        action = _fingerprint({"tool": ctx.tool_call.tool_name, "arguments": ctx.tool_call.arguments})
        observation = _fingerprint({"tool": ctx.tool_result.tool_name, "output": ctx.tool_result.output})
        pair = _fingerprint({"action": action, "observation": observation})
        state.actions.append(action)
        if ctx.tool_result.status is ToolStatus.ERROR:
            state.action_errors.append(pair)
            detection = _tail_detection(state.action_errors, pair, self.policy.identical_action_error, StuckPattern.IDENTICAL_ACTION_ERROR, tool=ctx.tool_call.tool_name)
        else:
            state.action_observations.append(pair)
            detection = _tail_detection(state.action_observations, pair, self.policy.identical_action_observation, StuckPattern.IDENTICAL_ACTION_OBSERVATION, tool=ctx.tool_call.tool_name)
        if detection is None:
            detection = self._ping_pong(state.actions)
        return self._decision(state, detection)

    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Detects repeated assistant monologues only when the response has no tool call.
        if _response_has_tool_calls(ctx.model_response):
            return MiddlewareDecision.continue_()
        text = _response_text(ctx.model_response)
        if not text.strip():
            return MiddlewareDecision.continue_()
        state = self._state(ctx)
        fingerprint = _fingerprint(text)
        state.monologues.append(fingerprint)
        detection = _tail_detection(state.monologues, fingerprint, self.policy.repeated_monologue, StuckPattern.REPEATED_MONOLOGUE)
        return self._decision(state, detection)

    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Detects recurring context-window failures while ignoring unrelated model errors.
        message = str(ctx.error or "")
        if not _is_context_window_error(message):
            return MiddlewareDecision.continue_()
        state = self._state(ctx)
        fingerprint = _fingerprint(message, redact_numbers=True)
        state.context_errors.append(fingerprint)
        detection = _tail_detection(state.context_errors, fingerprint, self.policy.context_window_errors, StuckPattern.CONTEXT_WINDOW_ERROR)
        return self._decision(state, detection)

    def _ping_pong(self, actions: deque[str]) -> StuckDetection | None:
        # Recognizes an ABAB sequence with two distinct normalized actions.
        size = self.policy.ping_pong_actions
        if len(actions) < size:
            return None
        tail = tuple(actions)[-size:]
        if tail[0] == tail[1] or any(value != tail[index % 2] for index, value in enumerate(tail)):
            return None
        return StuckDetection(StuckPattern.ACTION_PING_PONG, _fingerprint(tail), size, {"alternations": size - 1})

    def _state(self, ctx: MiddlewareContext) -> _DetectionRunState:
        # Recovers state defensively for runtimes that invoke a hook without before_run.
        state = ctx.run_state.get(self.__class__)
        if isinstance(state, _DetectionRunState):
            return state
        size = self.policy.history_size
        state = _DetectionRunState(
            action_observations=deque(maxlen=size),
            action_errors=deque(maxlen=size),
            actions=deque(maxlen=size),
            monologues=deque(maxlen=size),
            context_errors=deque(maxlen=size),
        )
        ctx.run_state[self.__class__] = state
        return state

    @staticmethod
    def _decision(state: _DetectionRunState, detection: StuckDetection | None) -> MiddlewareDecision:
        # Publishes typed evidence through the standard controlled-abort channel.
        if detection is None:
            return MiddlewareDecision.continue_()
        state.last_detection = detection
        return MiddlewareDecision.abort("stuck_detected", metadata=detection.to_metadata())


_TIMESTAMP = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ][0-9:.+\-Z]+\b", re.IGNORECASE)
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.IGNORECASE)
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")
_CONTEXT_ERROR = re.compile(r"context(?: length| window)?|maximum context|too many tokens|token limit", re.IGNORECASE)
_VOLATILE_FIELDS = frozenset({"timestamp", "time", "call_id", "request_id", "event_id", "run_id", "sequence", "super_step", "elapsed_ms", "iteration_count"})


def _normalized(value: Any, *, redact_numbers: bool = False) -> Any:
    # Canonicalizes nested values while removing only explicitly volatile fields.
    if isinstance(value, Mapping):
        return {
            str(key): _normalized(item, redact_numbers=redact_numbers)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key).lower() not in _VOLATILE_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [_normalized(item, redact_numbers=redact_numbers) for item in value]
    if isinstance(value, str):
        text = _TIMESTAMP.sub("<timestamp>", value)
        text = _UUID.sub("<uuid>", text)
        compact = " ".join(text.split())
        return (_NUMBER.sub("<number>", compact) if redact_numbers else compact).casefold()
    if redact_numbers and isinstance(value, (int, float)) and not isinstance(value, bool):
        return "<number>"
    return value


def _fingerprint(value: Any, *, redact_numbers: bool = False) -> str:
    # Produces a short non-reversible semantic key for diagnostics and comparisons.
    serialized = json.dumps(_normalized(value, redact_numbers=redact_numbers), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:20]


def _tail_detection(history: deque[str], fingerprint: str, threshold: int, pattern: StuckPattern, **details: Any) -> StuckDetection | None:
    # Counts only the consecutive tail so intervening progress resets a signature.
    count = 0
    for item in reversed(history):
        if item != fingerprint:
            break
        count += 1
    return StuckDetection(pattern, fingerprint, count, details) if count >= threshold else None


def _response_text(response: object | None) -> str:
    # Extracts text from supported provider-independent result shapes without repr noise.
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    for field_name in ("output", "content", "text", "assistant_output"):
        value = getattr(response, field_name, None)
        if isinstance(value, str):
            return value
    if isinstance(response, Mapping):
        for field_name in ("output", "content", "text", "assistant_output"):
            value = response.get(field_name)
            if isinstance(value, str):
                return value
    return ""


def _response_has_tool_calls(response: object | None) -> bool:
    # Recognizes common provider-independent tool-call containers.
    if response is None:
        return False
    for field_name in ("tool_calls", "calls"):
        value = response.get(field_name) if isinstance(response, Mapping) else getattr(response, field_name, None)
        if value:
            return True
    return False


def _is_context_window_error(message: str) -> bool:
    # Keeps context-window detection narrow enough to avoid ordinary token discussion.
    return bool(_CONTEXT_ERROR.search(message)) and any(term in message.casefold() for term in ("error", "exceed", "maximum", "too many", "limit"))


__all__ = ["StuckDetection", "StuckDetectionPolicy", "StuckDetectorMiddleware", "StuckPattern"]
