"""Session tracing wrappers for grouping multiple agent runs."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tracing import SpanContext, TracerBase
from vidbyte.trace.controller import TraceController
from vidbyte.trace.profiles import TraceProfile
from vidbyte.trace.providers import ProviderTraceTranslator
from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail


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

    def end_session(self, *, output: str | None = None, error: BaseException | None = None, **attributes: Any) -> None:
        # Closes the active session root for this execution context, when present.
        state = self._state.get()
        if state is None:
            return
        try:
            self._inner.end_trace(state.root_context, output=output, error=error, **attributes)
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

    def end_trace(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None, **attributes: Any) -> None:
        # Closes a root trace outside sessions, a session root, or a session child span.
        root = self.root_context
        if root is None:
            self._inner.end_trace(context, output=output, error=error, **attributes)
            return
        if context is root:
            self.end_session(output=output, error=error, **attributes)
            return
        self._inner.end_span(context, output=output, error=error, **attributes)

    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SpanContext:
        # Opens a child span, attaching parentless spans to the active session root.
        effective_parent = parent if parent is not None else self.root_context
        return self._inner.start_span(name, parent=effective_parent, **attributes)

    def end_span(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None, **attributes: Any) -> None:
        # Closes a child span on the wrapped tracer.
        self._inner.end_span(context, output=output, error=error, **attributes)

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


class SessionTraceController(TraceController):
    """Trace controller that groups multiple agent runs under one semantic session root."""

    def __init__(self, inner: TracerBase | None, profile: TraceProfile | None = None, translator: ProviderTraceTranslator | None = None, name: str | None = None) -> None:
        # Initializes the controller and optional default session name.
        super().__init__(inner, profile=profile, translator=translator)
        self.default_name = name or "session.run"
        self._session_root: ContextVar[SpanContext | None] = ContextVar(f"vidbyte_semantic_session_{id(self)}", default=None)

    @property
    def root_context(self) -> SpanContext | None:
        # Returns the active semantic session root for this execution context.
        return self._session_root.get()

    def begin_session(self, name: str | None = None, **attributes: Any) -> SpanContext:
        # Opens the shared session root trace.
        if self.root_context is not None:
            raise ConfigurationError("A trace session is already active on this controller.")
        spec = SpanSpec(
            name=name or self.default_name,
            kind=SpanKind.CHAIN,
            component="sessions",
            detail=TraceDetail.STANDARD,
            parent_policy=ParentPolicy.ROOT,
            attributes=attributes,
        )
        root = self.open_span(spec, as_trace=True)
        self._session_root.set(root)
        return root

    def end_session(self, *, output: str | None = None, error: BaseException | None = None) -> None:
        # Closes the active session root and clears session state.
        root = self.root_context
        if root is None:
            return
        try:
            self.end_trace(root, output=output, error=error)
        finally:
            self._session_root.set(None)

    def start_trace(self, name: str, **attributes: Any) -> SpanContext:
        # Converts child agent root traces into child spans while a session is active.
        root = self.root_context
        if root is not None and name == "agent.run":
            return self.start_span(name, parent=root, **attributes)
        return super().start_trace(name, **attributes)

    def end_trace(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None, **attributes: Any) -> None:
        # Ends child agent traces as spans while the session root remains open.
        root = self.root_context
        if root is None or context is root:
            return super().end_trace(context, output=output, error=error, **attributes)
        return super().end_span(context, output=output, error=error, **attributes)

    def session(self, name: str | None = None, **attributes: Any) -> _SessionContext:
        # Returns a sync context manager for one active session root.
        return _SessionContext(self, name=name, attributes=attributes)

    def async_session(self, name: str | None = None, **attributes: Any) -> _AsyncSessionContext:
        # Returns an async context manager for one active session root.
        return _AsyncSessionContext(self, name=name, attributes=attributes)


class _SessionContext(AbstractContextManager[SessionTraceController]):
    """Sync context manager for SessionTraceController."""

    def __init__(self, controller: SessionTraceController, *, name: str | None, attributes: dict[str, Any]) -> None:
        # Stores session construction data until context entry.
        self._controller = controller
        self._name = name
        self._attributes = attributes

    def __enter__(self) -> SessionTraceController:
        # Begins a session and returns its controller.
        self._controller.begin_session(self._name, **self._attributes)
        return self._controller

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: object | None) -> bool | None:
        # Ends the session with either success or the raised error.
        del exc_type, traceback
        self._controller.end_session(error=exc)
        return None


class _AsyncSessionContext(AbstractAsyncContextManager[SessionTraceController]):
    """Async context manager for SessionTraceController."""

    def __init__(self, controller: SessionTraceController, *, name: str | None, attributes: dict[str, Any]) -> None:
        # Stores session construction data until async context entry.
        self._controller = controller
        self._name = name
        self._attributes = attributes

    async def __aenter__(self) -> SessionTraceController:
        # Begins a session and returns its controller.
        self._controller.begin_session(self._name, **self._attributes)
        return self._controller

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: object | None) -> bool | None:
        # Ends the session with either success or the raised error.
        del exc_type, traceback
        self._controller.end_session(error=exc)
        return None


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


__all__ = ["SessionTraceController", "SessionTracer", "TraceSession"]
