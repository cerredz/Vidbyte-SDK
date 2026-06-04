"""Context Protocol Header

Description:
    Defines immutable contracts for agent runtime middleware.
Purpose:
    Gives middleware implementations stable hook, context, decision, and event
    payloads without coupling policy code to AgentRuntime internals.
Architecture:
    - MiddlewareHook: Runtime lifecycle breakpoints.
    - MiddlewareAction: Structured effects middleware may request.
    - MiddlewareDecision: One hook decision with helper constructors.
    - MiddlewareContext: Read-only runtime facts visible to middleware.
    - MiddlewareEvent: Bounded metadata record emitted by the pipeline.
Relations:
    Used by vidbyte.middleware and vidbyte.agents.runtime.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.tools import ToolCall, ToolResult


class MiddlewareHook(str, Enum):
    """Lifecycle breakpoints exposed by the direct agent runtime."""

    BEFORE_RUN = "before_run"
    BEFORE_ITERATION = "before_iteration"
    BEFORE_MODEL_CALL = "before_model_call"
    AFTER_MODEL_RESPONSE = "after_model_response"
    ON_MODEL_ERROR = "on_model_error"
    BEFORE_TOOL_CALL = "before_tool_call"
    AFTER_TOOL_CALL = "after_tool_call"
    AFTER_ITERATION = "after_iteration"
    AFTER_RUN = "after_run"


class MiddlewareAction(str, Enum):
    """Structured effects a middleware hook may request."""

    CONTINUE = "continue"
    SLEEP = "sleep"
    ABORT_RUN = "abort_run"
    DENY_TOOL = "deny_tool"
    RETRY = "retry"


@dataclass(frozen=True, slots=True)
class MiddlewareTransform:
    """Model-visible runtime updates requested by middleware."""

    model_visible_tool_result: ToolResult | None = None
    provider_messages: Sequence[Mapping[str, Any]] | None = None
    system: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MiddlewareDecision:
    """Decision returned by one middleware hook."""

    action: MiddlewareAction = MiddlewareAction.CONTINUE
    reason: str | None = None
    sleep_seconds: float = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)
    transform: MiddlewareTransform | None = None

    def __post_init__(self) -> None:
        # Validates timing and transform constraints for middleware decisions.
        if self.sleep_seconds < 0:
            raise ValueError("sleep_seconds cannot be negative.")
        if self.transform is not None and self.action is not MiddlewareAction.CONTINUE:
            raise ValueError("Middleware transforms are only valid for continue decisions.")

    @classmethod
    def continue_(
        cls,
        *,
        metadata: Mapping[str, Any] | None = None,
        transform: MiddlewareTransform | None = None,
    ) -> "MiddlewareDecision":
        # Builds a continue decision with optional metadata and runtime transform.
        return cls(metadata=dict(metadata or {}), transform=transform)

    @classmethod
    def sleep(
        cls,
        seconds: float,
        *,
        reason: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "MiddlewareDecision":
        """Pause execution before continuing."""
        return cls(
            action=MiddlewareAction.SLEEP,
            reason=reason,
            sleep_seconds=seconds,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def abort(
        cls,
        reason: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> "MiddlewareDecision":
        """Stop the current agent run."""
        return cls(
            action=MiddlewareAction.ABORT_RUN,
            reason=reason,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def deny_tool(
        cls,
        reason: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> "MiddlewareDecision":
        """Deny the current tool call without executing the tool body."""
        return cls(
            action=MiddlewareAction.DENY_TOOL,
            reason=reason,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def retry(
        cls,
        reason: str,
        *,
        sleep_seconds: float = 0,
        metadata: Mapping[str, Any] | None = None,
    ) -> "MiddlewareDecision":
        """Retry the failed model call."""
        return cls(
            action=MiddlewareAction.RETRY,
            reason=reason,
            sleep_seconds=sleep_seconds,
            metadata=dict(metadata or {}),
        )


@dataclass(frozen=True, slots=True)
class MiddlewareContext:
    """Read-only runtime facts supplied to middleware hooks."""

    hook: MiddlewareHook
    agent_name: str
    run_id: str | None = None
    provider: str | None = None
    message: str = ""
    iteration_count: int = 0
    model_call_count: int = 0
    tool_call_count: int = 0
    elapsed_seconds: float = 0
    tokens_used: int | None = None
    agent_context: BaseAgentContext | None = None
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    model_response: object | None = None
    error: BaseException | None = None
    provider_messages: Sequence[Mapping[str, Any]] = ()
    system: str | None = None
    tool_is_internal: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)
    # Mutable per-run state dict; frozen prevents field reassignment but not dict mutation.
    run_state: dict[type, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MiddlewareEvent:
    """Metadata record for a middleware hook decision or exception."""

    middleware_name: str
    hook: MiddlewareHook
    action: MiddlewareAction
    reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


__all__ = [
    "MiddlewareAction",
    "MiddlewareContext",
    "MiddlewareDecision",
    "MiddlewareEvent",
    "MiddlewareHook",
    "MiddlewareTransform",
]
