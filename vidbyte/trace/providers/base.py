"""FILE: vidbyte/trace/providers/base.py

PURPOSE: Defines legacy semantic translation contracts and shared in-memory shape lifecycle bookkeeping.
ROLE IN CODEBASE: Supports the existing SpanSpec provider adapters and the direct OTel/OpenInference shape providers.
ARCHITECTURE NOTE: ProviderSpanPayload and ProviderTraceTranslator remain the legacy adapter seam; _InMemoryShapeTrace stores plain records in the caller-owned event list.
COMMON MODIFICATION PATTERNS: Keep legacy translation behavior stable; extend shape lifecycle handling only when every direct provider needs the same rule.
KNOWN EDGE CASES: Foreign or empty contexts are ignored, and optional runtime fields are omitted rather than invented.
RELATED DOCS: docs/design/otel-genai-and-openinference-trace-shapes.md
TESTS: tests/test_otel_genai_trace_shape.py, tests/test_openinference_trace_shape.py, tests/test_semantic_tracing.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from vidbyte.lib.tracing import SpanContext, TracerBase
from vidbyte.trace.schema import SpanSpec


@dataclass(frozen=True, slots=True)
class ProviderSpanPayload:
    """Provider-facing name and attributes derived from a semantic span."""

    name: str
    attributes: dict[str, Any] = field(default_factory=dict)


class ProviderTraceTranslator(Protocol):
    """Protocol implemented by provider-specific semantic translators."""

    provider: str

    def translate_start(self, spec: SpanSpec) -> ProviderSpanPayload:
        # Converts a semantic span spec into provider-facing start payload.
        ...


class _InMemoryShapeTrace(TracerBase):
    """Shared lifecycle bookkeeping for direct, in-memory provider shapes."""

    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        # Keep the caller's list so the generated records remain directly observable.
        self.events = events if events is not None else []
        self._counter = 0

    def start_trace(self, name: str, **attributes: Any) -> SpanContext:
        # Builds a provider-shaped root record from the runtime's raw trace call.
        return self._start_record("trace", name, None, attributes)

    def end_trace(
        self,
        context: SpanContext,
        *,
        output: str | None = None,
        error: BaseException | None = None,
    ) -> None:
        # Completes only records created by this tracer instance.
        self._end_record(context, output=output, error=error)

    def start_span(
        self,
        name: str,
        parent: SpanContext | None = None,
        **attributes: Any,
    ) -> SpanContext:
        # Builds a provider-shaped child record and preserves the direct parent ID.
        parent_record = self._record_for(parent)
        parent_id = parent_record.get("id") if parent_record is not None else None
        return self._start_record("span", name, parent_id, attributes)

    def end_span(
        self,
        context: SpanContext,
        *,
        output: str | None = None,
        error: BaseException | None = None,
    ) -> None:
        # Completes only records created by this tracer instance.
        self._end_record(context, output=output, error=error)

    def update_span(self, context: SpanContext, **attributes: Any) -> None:
        # Maps response-derived runtime values into the same final provider shape.
        record = self._record_for(context)
        operation = context.metadata.get("operation") if isinstance(context, SpanContext) else None
        if record is None or not isinstance(operation, str):
            return
        shaped_attributes = self._shape_update(operation, dict(attributes))
        record["attributes"].update(shaped_attributes)

    def _start_record(
        self,
        record_type: str,
        name: str,
        parent_id: int | None,
        attributes: dict[str, Any],
    ) -> SpanContext:
        # Provider classes return the final shape; this helper adds only lifecycle fields.
        shaped_name, shaped_attributes = self._shape(name, dict(attributes))
        self._counter += 1
        record: dict[str, Any] = {
            "id": self._counter,
            "type": record_type,
            "name": shaped_name,
            "attributes": shaped_attributes,
            "parent_id": parent_id,
            "output": None,
            "error": None,
            "status": "open",
        }
        self.events.append(record)
        return SpanContext(metadata={"owner": self, "record": record, "operation": name})

    def _end_record(
        self,
        context: SpanContext,
        *,
        output: str | None,
        error: BaseException | None,
    ) -> None:
        # A foreign or empty context is intentionally a safe no-op.
        record = self._record_for(context)
        if record is None:
            return
        if error is not None:
            record["error"] = str(error)
            record["status"] = "error"
        else:
            if output is not None:
                record["output"] = output
            record["status"] = "ok"

    def _record_for(self, context: SpanContext | None) -> dict[str, Any] | None:
        # Validates ownership so IDs from another tracer cannot accidentally link records.
        if not isinstance(context, SpanContext) or context.metadata.get("owner") is not self:
            return None
        record = context.metadata.get("record")
        return record if isinstance(record, dict) else None

    def _shape(self, name: str, attributes: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        # Subclasses turn the raw runtime call into the provider-specific final shape.
        raise NotImplementedError

    def _shape_update(self, name: str, attributes: dict[str, Any]) -> dict[str, Any]:
        # Subclasses may map partial response data without replacing start-time fields.
        return self._shape(name, attributes)[1]


__all__ = ["ProviderSpanPayload", "ProviderTraceTranslator"]
