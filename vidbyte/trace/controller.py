"""Context Protocol Header

Description:
    Implements the composable semantic trace controller and span-name routing for Vidbyte subsystems.
Purpose:
    Filters semantic spans through profiles, preserves parent context, sanitizes attributes, and translates spans for an inner tracer.
Architecture:
    `TraceController` maps names to component factories, including `multi_agent.*`
    and diagnostic `middleware.hook` records, then delegates provider translation
    and tracer lifecycle calls.
Relations:
    Wraps `TracerBase`, consumes trace profiles/components, and is used by agents, runtimes, tools, sessions, and orchestration controllers.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from vidbyte.lib.tracing import NullTracer, SpanContext, TracerBase
from vidbyte.trace.profiles import TraceProfile, safe_trace_value
from vidbyte.trace.providers import GenericProviderTranslator, ProviderTraceTranslator
from vidbyte.trace.schema import (
    ParentPolicy,
    SemanticSpanContext,
    SpanKind,
    SpanSpec,
    TraceDetail,
)

_SPAN_STACK: ContextVar[tuple[SemanticSpanContext, ...]] = ContextVar("vidbyte_trace_span_stack", default=())


class TraceController(TracerBase):
    """TracerBase implementation that filters and translates semantic spans."""

    def __init__(self, inner: TracerBase | None, profile: TraceProfile | None = None, translator: ProviderTraceTranslator | None = None) -> None:
        # Stores the wrapped tracer, active profile, and provider translator.
        self.inner = inner or NullTracer()
        self.profile = profile or TraceProfile.default()
        self.translator = translator or GenericProviderTranslator()

    def start_trace(self, name: str, **attributes: Any) -> SemanticSpanContext:
        # Opens a root semantic trace or returns a suppressed root context.
        if name == "agent.run" and self._has_active_provider_parent():
            spec = self._spec_from_name(name, attributes=attributes, root=False)
            return self.open_span(spec, as_trace=False)
        spec = self._spec_from_name(name, attributes=attributes, root=True)
        return self.open_span(spec, parent=None, as_trace=True)

    def end_trace(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None:
        # Closes a root semantic trace and restores the context-local parent stack.
        semantic = self._coerce_context(context)
        if semantic is None or semantic.suppressed:
            self._pop_context(semantic)
            return
        if semantic.metadata.get("as_trace"):
            self.inner.end_trace(semantic.provider_context or SpanContext(), output=output, error=error)
        else:
            self.inner.end_span(semantic.provider_context or SpanContext(), output=output, error=error)
        self._pop_context(semantic)

    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SemanticSpanContext:
        # Opens a child semantic span under the explicit or current parent.
        spec = self._spec_from_name(name, attributes=attributes, root=False)
        return self.open_span(spec, parent=parent)

    def end_span(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None:
        # Closes a child semantic span and restores the context-local parent stack.
        semantic = self._coerce_context(context)
        if semantic is None or semantic.suppressed:
            self._pop_context(semantic)
            return
        self.inner.end_span(semantic.provider_context or SpanContext(), output=output, error=error)
        self._pop_context(semantic)

    def open_span(self, spec: SpanSpec, parent: SpanContext | None = None, *, as_trace: bool = False) -> SemanticSpanContext:
        # Applies the profile and opens the translated provider span when allowed.
        normalized = self._sanitize_spec(spec)
        if not self.profile.allows(normalized):
            return self._push_context(SemanticSpanContext(spec=normalized, suppressed=True, metadata={"as_trace": as_trace}))
        payload = self.translator.translate_start(normalized)
        provider_parent = self._provider_parent(parent, normalized.parent_policy)
        if as_trace:
            provider_context = self.inner.start_trace(payload.name, **payload.attributes)
        else:
            provider_context = self.inner.start_span(payload.name, parent=provider_parent, **payload.attributes)
        return self._push_context(SemanticSpanContext(provider_context=provider_context, spec=normalized, suppressed=False, metadata={"as_trace": as_trace}))

    def _spec_from_name(self, name: str, *, attributes: dict[str, Any], root: bool) -> SpanSpec:
        # Converts legacy low-level span names into semantic specs.
        detail = TraceDetail.MINIMAL
        kind = SpanKind.CHAIN
        component = "core"
        if name.startswith("llm."):
            kind = SpanKind.LLM
            component = "agents"
        elif name.startswith("tool."):
            kind = SpanKind.TOOL
            component = "tools"
        elif name.startswith("parser."):
            kind = SpanKind.PARSER
            detail = TraceDetail.STANDARD
            component = "parsers"
        elif name.startswith("context."):
            kind = SpanKind.PROMPT
            detail = TraceDetail.VERBOSE
            component = "context"
        elif name.startswith("algorithm."):
            detail = TraceDetail.VERBOSE
            component = "algorithms"
        elif name.startswith("runtime."):
            detail = TraceDetail.VERBOSE
            component = "runtimes"
        elif name.startswith("middleware."):
            detail = TraceDetail.DIAGNOSTIC if name == "middleware.hook" else TraceDetail.VERBOSE
            component = "middleware"
        elif name.startswith("aggregate."):
            detail = TraceDetail.VERBOSE
            component = "aggregate"
        elif name.startswith("multi_agent."):
            detail = TraceDetail.VERBOSE if name == "multi_agent.ledger_update" else TraceDetail.STANDARD
            component = "multi_agent"
        elif name.startswith("session."):
            detail = TraceDetail.STANDARD
            component = "sessions"
        elif name.startswith("agent."):
            component = "agents"
            detail = TraceDetail.STANDARD if name == "agent.stop" else TraceDetail.MINIMAL
        policy = ParentPolicy.ROOT if root else ParentPolicy.CURRENT
        return SpanSpec(name=name, kind=kind, component=component, detail=detail, parent_policy=policy, attributes=dict(attributes))

    def _sanitize_spec(self, spec: SpanSpec) -> SpanSpec:
        # Redacts and truncates semantic span attributes according to the profile.
        return SpanSpec(
            name=spec.name,
            kind=spec.kind,
            component=spec.component,
            detail=spec.detail,
            parent_policy=spec.parent_policy,
            attributes=safe_trace_value(dict(spec.attributes), max_chars=self.profile.max_chars, redact=self.profile.redact),
            metadata=dict(spec.metadata),
        )

    def _provider_parent(self, explicit: SpanContext | None, policy: ParentPolicy) -> SpanContext | None:
        # Resolves the provider parent from explicit context or context-local stack.
        if explicit is not None:
            return self._unwrap_provider_context(explicit)
        if policy is ParentPolicy.ROOT:
            return None
        stack = _SPAN_STACK.get()
        for context in reversed(stack):
            if not context.suppressed and context.provider_context is not None:
                return context.provider_context
        return None

    def _has_active_provider_parent(self) -> bool:
        # Returns whether the current async-local stack has an open provider parent.
        return any(not context.suppressed and context.provider_context is not None for context in _SPAN_STACK.get())

    def _push_context(self, context: SemanticSpanContext) -> SemanticSpanContext:
        # Pushes a semantic context onto the async-local stack.
        _SPAN_STACK.set((*_SPAN_STACK.get(), context))
        return context

    def _pop_context(self, context: SemanticSpanContext | None) -> None:
        # Removes the context from the async-local stack if it is present.
        if context is None:
            return
        stack = list(_SPAN_STACK.get())
        for index in range(len(stack) - 1, -1, -1):
            if stack[index] is context:
                del stack[index]
                _SPAN_STACK.set(tuple(stack))
                return

    @staticmethod
    def _unwrap_provider_context(context: SpanContext) -> SpanContext:
        # Returns provider context for semantic contexts and raw context otherwise.
        if isinstance(context, SemanticSpanContext) and context.provider_context is not None:
            return context.provider_context
        return context

    @staticmethod
    def _coerce_context(context: SpanContext) -> SemanticSpanContext | None:
        # Accepts only semantic contexts for controller-managed end calls.
        return context if isinstance(context, SemanticSpanContext) else None


__all__ = ["TraceController"]
