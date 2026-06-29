"""Session tracing controller for multi-agent trace grouping."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Any

from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tracing import SpanContext, TracerBase
from vidbyte.trace.controller import TraceController
from vidbyte.trace.profiles import TraceProfile
from vidbyte.trace.providers import ProviderTraceTranslator
from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail


class SessionTraceController(TraceController):
    """Trace controller that groups multiple agent runs under one session root."""

    def __init__(self, inner: TracerBase | None, profile: TraceProfile | None = None, translator: ProviderTraceTranslator | None = None, name: str | None = None) -> None:
        # Initializes the controller and optional default session name.
        super().__init__(inner, profile=profile, translator=translator)
        self.default_name = name or "session.run"
        self._session_root: SpanContext | None = None

    def begin_session(self, name: str | None = None, **attributes: Any) -> SpanContext:
        # Opens the shared session root trace.
        if self._session_root is not None:
            raise ConfigurationError("A trace session is already active on this controller.")
        spec = SpanSpec(
            name=name or self.default_name,
            kind=SpanKind.CHAIN,
            component="sessions",
            detail=TraceDetail.STANDARD,
            parent_policy=ParentPolicy.ROOT,
            attributes=attributes,
        )
        self._session_root = self.open_span(spec, as_trace=True)
        return self._session_root

    def end_session(self, *, output: str | None = None, error: BaseException | None = None) -> None:
        # Closes the active session root and clears session state.
        if self._session_root is None:
            return
        root = self._session_root
        self._session_root = None
        self.end_trace(root, output=output, error=error)

    def start_trace(self, name: str, **attributes: Any) -> SpanContext:
        # Converts child agent root traces into child spans while a session is active.
        if self._session_root is not None and name == "agent.run":
            return self.start_span(name, parent=self._session_root, **attributes)
        return super().start_trace(name, **attributes)

    def end_trace(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None:
        # Ends child agent spans as spans and root sessions as traces.
        if context is self._session_root:
            return super().end_trace(context, output=output, error=error)
        return super().end_span(context, output=output, error=error)

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
        self._controller.end_session(error=exc)
        return None


__all__ = ["SessionTraceController"]
