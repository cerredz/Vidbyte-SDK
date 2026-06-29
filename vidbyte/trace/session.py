"""Context Protocol Header

Description:
    Implements session-aware tracer wrapping for grouping many agent runs.
Purpose:
    Lets callers place multiple BaseAgent traces under one parent trace without
    changing the provider-neutral TracerBase runtime contract.
Architecture:
    - SessionTracer: TracerBase wrapper that stores an active root in ContextVar state.
    - TraceSession: Sync/async context manager for session lifecycle.
Relations:
    Used by vidbyte.trace.Trace session helpers and any Agent(trace=...) caller.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tracing import SpanContext, TracerBase


@dataclass(frozen=True, slots=True)
class _TraceSessionState:
    """Active trace-session state for the current execution context."""

    root_context: SpanContext


class SessionTracer(TracerBase):
    """Tracer wrapper that groups agent root traces under one session root."""

    def __init__(self, inner: type[TracerBase] | TracerBase, *, default_name: str = "session.run", default_attributes: Mapping[str, Any] | None = None) -> None:
        # Stores a validated inner tracer and default root trace attributes.
        if not default_name:
            raise ConfigurationError("SessionTracer default_name cannot be empty.")
        self._inner = _SessionTracerFactory.resolve_inner(inner)
        self._default_name = default_name
        self._default_attributes = dict(default_attributes or {})
        self._state: ContextVar[_TraceSessionState | None] = ContextVar(f"vidbyte_session_tracer_{id(self)}", default=None)

    @property
    def inner(self) -> TracerBase:
        # Returns the wrapped tracer instance used for all trace operations.
        return self._inner

    @property
    def in_session(self) -> bool:
        # Reports whether this execution context currently has a session root.
        return self._state.get() is not None

    @property
    def root_context(self) -> SpanContext | None:
        # Returns the active session root for this execution context, if any.
        state = self._state.get()
        return state.root_context if state is not None else None

    def begin_session(self, name: str | None = None, **attributes: Any) -> SpanContext:
        # Opens one root trace for this execution context and records it as session state.
        if self._state.get() is not None:
            raise ConfigurationError("SessionTracer cannot begin a nested session in the same execution context.")
        root = self._inner.start_trace(name or self._default_name, **self._session_attributes(attributes))
        self._state.set(_TraceSessionState(root_context=root))
        return root

    def end_session(self, *, output: str | None = None, error: BaseException | None = None) -> None:
        # Closes the active session root for this execution context, when present.
        state = self._state.get()
        if state is None:
            return
        try:
            self._inner.end_trace(state.root_context, output=output, error=error)
        finally:
            self._state.set(None)

    def session(self, name: str | None = None, **attributes: Any) -> TraceSession:
        # Returns a sync/async context manager that opens and closes a session root.
        return TraceSession(self, name=name, attributes=attributes)

    def start_trace(self, name: str, **attributes: Any) -> SpanContext:
        # Opens a root trace outside sessions, or a child span under the active session root.
        root = self.root_context
        if root is None:
            return self._inner.start_trace(name, **attributes)
        return self._inner.start_span(name, parent=root, **attributes)

    def end_trace(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None:
        # Closes a root trace outside sessions, a session root, or a session child span.
        root = self.root_context
        if root is None:
            self._inner.end_trace(context, output=output, error=error)
            return
        if context is root:
            self.end_session(output=output, error=error)
            return
        self._inner.end_span(context, output=output, error=error)

    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SpanContext:
        # Opens a child span, attaching parentless spans to the active session root.
        effective_parent = parent if parent is not None else self.root_context
        return self._inner.start_span(name, parent=effective_parent, **attributes)

    def end_span(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None:
        # Closes a child span on the wrapped tracer.
        self._inner.end_span(context, output=output, error=error)

    def _session_attributes(self, attributes: Mapping[str, Any]) -> dict[str, Any]:
        # Merges default root attributes with call-specific attributes.
        return {**self._default_attributes, **dict(attributes)}


class TraceSession:
    """Sync and async context manager for a SessionTracer root trace."""

    def __init__(self, tracer: SessionTracer, *, name: str | None = None, attributes: Mapping[str, Any] | None = None) -> None:
        # Stores the session tracer and root trace inputs for enter/exit lifecycle.
        self._tracer = tracer
        self._name = name
        self._attributes = dict(attributes or {})

    def __enter__(self) -> SessionTracer:
        # Opens the session root and returns the owning SessionTracer.
        self._tracer.begin_session(self._name, **self._attributes)
        return self._tracer

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: Any) -> bool:
        # Closes the session root and preserves any exception from the managed block.
        del exc_type, traceback
        self._tracer.end_session(error=exc)
        return False

    async def __aenter__(self) -> SessionTracer:
        # Opens the session root in async context-manager use.
        self._tracer.begin_session(self._name, **self._attributes)
        return self._tracer

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: Any) -> bool:
        # Closes the session root in async context-manager use.
        del exc_type, traceback
        self._tracer.end_session(error=exc)
        return False


class _SessionTracerFactory:
    """Validation helper for session tracer construction."""

    @staticmethod
    def resolve_inner(inner: type[TracerBase] | TracerBase) -> TracerBase:
        # Normalizes tracer classes or instances into a concrete TracerBase.
        if inner is None:
            raise ConfigurationError("SessionTracer requires a TracerBase class or instance.")
        if isinstance(inner, type):
            if not issubclass(inner, TracerBase):
                raise ConfigurationError("SessionTracer requires a TracerBase class or instance.")
            resolved = inner()
        else:
            resolved = inner
        if not isinstance(resolved, TracerBase):
            raise ConfigurationError("SessionTracer requires a TracerBase class or instance.")
        return resolved


__all__ = ["SessionTracer", "TraceSession"]
