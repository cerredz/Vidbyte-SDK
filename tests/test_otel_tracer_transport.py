from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from vidbyte.lib.errors import TracerConfigurationError
from vidbyte.providers.tracing import OTelTracer
from vidbyte.providers.tracing.otel import OTelSpanContext


def _tracer(**kwargs: object) -> tuple[OTelTracer, InMemorySpanExporter]:
    # Builds an OTelTracer wired to a fresh in-memory exporter for assertion-friendly tests.
    exporter = InMemorySpanExporter()
    return OTelTracer(exporter=exporter, **kwargs), exporter


class OTelTracerConstructionTests(unittest.TestCase):
    def test_raises_when_opentelemetry_is_not_importable(self) -> None:
        # [Hidden Assumption] Construction must fail loud, not silently degrade to a no-op tracer.
        with patch.dict("sys.modules", {"opentelemetry": None}):
            with self.assertRaises(TracerConfigurationError):
                OTelTracer(exporter=InMemorySpanExporter())

    def test_raises_when_no_endpoint_or_env_var_and_no_exporter_override(self) -> None:
        # [Edge Case] No endpoint argument, no env var, no exporter override.
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(TracerConfigurationError):
                OTelTracer()

    def test_accepts_injected_exporter_and_skips_endpoint_resolution(self) -> None:
        # [Hidden Assumption] exporter= must bypass endpoint requirement entirely.
        with patch.dict("os.environ", {}, clear=True):
            tracer = OTelTracer(exporter=InMemorySpanExporter())
            self.assertIsInstance(tracer, OTelTracer)

    def test_reads_traces_endpoint_env_var_before_generic_endpoint_env_var(self) -> None:
        # [Edge Case] OTEL_EXPORTER_OTLP_TRACES_ENDPOINT takes priority.
        env = {
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://traces.example.com/v1/traces",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://generic.example.com",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter") as mock_exporter:
                OTelTracer()
                mock_exporter.assert_called_once_with(endpoint="http://traces.example.com/v1/traces", headers=None)

    def test_forwards_headers_to_exporter(self) -> None:
        # [Hidden Assumption] Auth headers must reach the real exporter unchanged.
        with patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter") as mock_exporter:
            OTelTracer(endpoint="http://collector.example.com/v1/traces", headers={"Authorization": "Bearer x"})
            mock_exporter.assert_called_once_with(endpoint="http://collector.example.com/v1/traces", headers={"Authorization": "Bearer x"})


class OTelTracerAttributeCoercionTests(unittest.TestCase):
    def test_dict_attribute_becomes_valid_json_not_python_repr(self) -> None:
        # [Silent Failure] A stringified Python dict repr is not valid JSON; downstream tools would fail to parse it.
        tracer, exporter = _tracer()
        ctx = tracer.start_span("execute_tool web_search", **{"gen_ai.tool.call.arguments": {"query": "x", "n": 3}})
        tracer.end_span(ctx)
        span = exporter.get_finished_spans()[0]
        parsed = json.loads(span.attributes["gen_ai.tool.call.arguments"])
        self.assertEqual(parsed, {"query": "x", "n": 3})

    def test_none_valued_attribute_is_skipped_not_stringified(self) -> None:
        # [Edge Case] "None" as a literal string is worse than omitting the key.
        tracer, exporter = _tracer()
        ctx = tracer.start_span("chat model", **{"gen_ai.system_instructions": None, "gen_ai.request.model": "m"})
        tracer.end_span(ctx)
        span = exporter.get_finished_spans()[0]
        self.assertNotIn("gen_ai.system_instructions", span.attributes)
        self.assertEqual(span.attributes["gen_ai.request.model"], "m")

    def test_primitive_values_pass_through_unwrapped(self) -> None:
        # [Hidden Assumption] str/bool/int/float must not be JSON-wrapped (no extra quoting).
        tracer, exporter = _tracer()
        ctx = tracer.start_span("chat m", **{"a": "text", "b": True, "c": 3, "d": 1.5})
        tracer.end_span(ctx)
        span = exporter.get_finished_spans()[0]
        self.assertEqual(span.attributes["a"], "text")
        self.assertEqual(span.attributes["b"], True)
        self.assertEqual(span.attributes["c"], 3)
        self.assertEqual(span.attributes["d"], 1.5)

    def test_non_json_serializable_value_falls_back_to_str(self) -> None:
        # [Hidden Failure] An object with no default JSON encoding must not raise out of _set_attributes.
        class Unserializable:
            def __repr__(self) -> str:
                return "<unserializable>"

        tracer, exporter = _tracer()
        ctx = tracer.start_span("chat m", weird=Unserializable())
        tracer.end_span(ctx)
        span = exporter.get_finished_spans()[0]
        self.assertIn("<unserializable>", span.attributes["weird"])

    def test_service_name_defaults_to_vidbyte_agent(self) -> None:
        # [Silent Failure] Must assert the actual resource attribute, not just that construction succeeded.
        tracer, exporter = _tracer()
        ctx = tracer.start_span("chat m")
        tracer.end_span(ctx)
        span = exporter.get_finished_spans()[0]
        self.assertEqual(span.resource.attributes["service.name"], "vidbyte-agent")

    def test_service_name_override_is_applied(self) -> None:
        # [Edge Case] Explicit service_name must win over the default.
        tracer, exporter = _tracer(service_name="research-harness")
        ctx = tracer.start_span("chat m")
        tracer.end_span(ctx)
        span = exporter.get_finished_spans()[0]
        self.assertEqual(span.resource.attributes["service.name"], "research-harness")


class OTelTracerLifecycleTests(unittest.TestCase):
    def test_nests_child_span_under_explicit_parent(self) -> None:
        # [Silent Failure] Parent/child linkage must hold in the real exported spans, not just in Python objects.
        tracer, exporter = _tracer()
        root = tracer.start_trace("invoke_agent a")
        child = tracer.start_span("execute_tool t", parent=root)
        tracer.end_span(child)
        tracer.end_trace(root)
        spans = exporter.get_finished_spans()
        child_span = next(s for s in spans if s.name == "execute_tool t")
        root_span = next(s for s in spans if s.name == "invoke_agent a")
        self.assertEqual(child_span.parent.span_id, root_span.context.span_id)

    def test_full_cycle_exports_exactly_the_expected_spans(self) -> None:
        # [Silent Failure] Real OTel round trip with no mocking of the SDK itself.
        tracer, exporter = _tracer()
        root = tracer.start_trace("invoke_agent research-agent")
        llm = tracer.start_span("chat claude", parent=root)
        tracer.end_span(llm, output="ok")
        tool = tracer.start_span("execute_tool web_search", parent=root)
        tracer.end_span(tool, output="done")
        tracer.end_trace(root, output="finished")
        names = sorted(s.name for s in exporter.get_finished_spans())
        self.assertEqual(names, ["chat claude", "execute_tool web_search", "invoke_agent research-agent"])

    def test_start_span_degrades_to_empty_context_when_underlying_tracer_throws(self) -> None:
        # [Hidden Failure] Tracing must never break agent execution.
        tracer, _ = _tracer()
        with patch.object(tracer, "_tracer") as broken:
            broken.start_span.side_effect = RuntimeError("boom")
            ctx = tracer.start_span("chat m")
        self.assertIsInstance(ctx, OTelSpanContext)
        self.assertIsNone(ctx.span)

    def test_end_span_on_context_with_no_span_is_a_safe_noop(self) -> None:
        # [Edge Case] A suppressed/empty context must be safe to end.
        tracer, _ = _tracer()
        tracer.end_span(OTelSpanContext())
        tracer.end_trace(OTelSpanContext())

    def test_end_span_records_error_without_raising(self) -> None:
        # [Hidden Failure] Error metadata capture must not itself raise.
        tracer, exporter = _tracer()
        ctx = tracer.start_span("chat m")
        tracer.end_span(ctx, error=RuntimeError("boom"))
        span = exporter.get_finished_spans()[0]
        self.assertEqual(span.attributes["error.message"], "boom")


if __name__ == "__main__":
    unittest.main()
