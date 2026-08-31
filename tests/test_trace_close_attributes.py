"""FILE: tests/test_trace_close_attributes.py

PURPOSE: Verifies the close-time attribute path added in trace-output-and-usage-attributes:
    translate_end on both trace shape translators, TraceController's wiring of it, and the
    widened end_span/end_trace contract on the tracers that actually carry it to the wire.
ROLE IN CODEBASE: Golden-fixture and integration test suite for the translate_end feature.
ARCHITECTURE NOTE: Mirrors tests/test_otel_genai_trace_shape.py and tests/test_openinference_trace_shape.py's
    conventions (hardcoded verified field-name constants, exact-match assertions) for the new close-time fields.
COMMON MODIFICATION PATTERNS: Add a new close-time field mapping test alongside its translate_end branch.
KNOWN EDGE CASES: A translator without translate_end (e.g. a pre-existing custom translator) must see zero
    behavior change; a suppressed/profile-filtered span must never reach a translator at all.
RELATED DOCS: docs/design/trace-output-and-usage-attributes.md
TESTS: This file is the test.
"""

from __future__ import annotations

import unittest

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from vidbyte.providers.tracing import OTelTracer
from vidbyte.providers.tracing.phoenix import PhoenixTracer
from vidbyte.trace.controller import TraceController
from vidbyte.trace.debug import DebugTracer
from vidbyte.trace.profiles import TraceProfile, safe_trace_value
from vidbyte.trace.providers import GenericProviderTranslator, OpenInferenceProviderTranslator, OTelGenAIProviderTranslator
from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail


def _otel_tracer() -> tuple[OTelTracer, InMemorySpanExporter]:
    # Builds an OTelTracer wired to a fresh in-memory exporter for assertion-friendly tests.
    exporter = InMemorySpanExporter()
    return OTelTracer(exporter=exporter), exporter


def _llm_spec(**attrs: object) -> SpanSpec:
    return SpanSpec("llm.call", SpanKind.LLM, "agents", TraceDetail.MINIMAL, ParentPolicy.CURRENT, attrs)


def _agent_spec(**attrs: object) -> SpanSpec:
    return SpanSpec("agent.run", SpanKind.CHAIN, "agents", TraceDetail.MINIMAL, ParentPolicy.ROOT, attrs)


def _generic_spec(**attrs: object) -> SpanSpec:
    return SpanSpec("algorithm.reflexion.trial", SpanKind.CHAIN, "algorithms", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attrs)


class OTelGenAITranslateEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.translator = OTelGenAIProviderTranslator()

    def test_llm_end_maps_output_messages_usage_and_finish_reason(self) -> None:
        # [Silent Failure] Every close-time field name must be exact, sourced from the same
        # gen-ai-spans.md fields already verified for open-time usage in PR #390.
        out = self.translator.translate_end(
            _llm_spec(model="m"),
            {"output_messages": ({"role": "assistant", "content": "hi"},), "input_tokens": 10, "output_tokens": 4, "finish_reason": "stop"},
        )
        self.assertEqual(out["gen_ai.output.messages"], ({"role": "assistant", "content": "hi"},))
        self.assertEqual(out["gen_ai.usage.input_tokens"], 10)
        self.assertEqual(out["gen_ai.usage.output_tokens"], 4)
        self.assertEqual(out["gen_ai.response.finish_reasons"], "stop")

    def test_llm_end_omits_fields_entirely_when_absent(self) -> None:
        # [Hidden Assumption] Absence must mean the key is missing, not a zero/empty default.
        out = self.translator.translate_end(_llm_spec(model="m"), {})
        self.assertNotIn("gen_ai.output.messages", out)
        self.assertNotIn("gen_ai.usage.input_tokens", out)
        self.assertNotIn("gen_ai.usage.output_tokens", out)
        self.assertNotIn("gen_ai.response.finish_reasons", out)

    def test_llm_end_namespaces_unrecognized_keys(self) -> None:
        # [Hidden Failure] Would silently invent a gen_ai.* field if this regressed.
        out = self.translator.translate_end(_llm_spec(model="m"), {"cached_input_tokens": 5})
        self.assertEqual(out["vidbyte.cached_input_tokens"], 5)
        self.assertNotIn("gen_ai.usage.cached_input_tokens", out)

    def test_agent_run_end_namespaces_whole_run_usage_under_vidbyte(self) -> None:
        # [Hidden Failure] gen_ai.usage.* is per-call scoped by spec; a whole-run rollup must
        # never reuse that field name at the invoke_agent span level.
        out = self.translator.translate_end(_agent_spec(), {"input_tokens": 100, "cost_usd": 0.02, "model_call_count": 3})
        self.assertEqual(out, {"vidbyte.usage.input_tokens": 100, "vidbyte.usage.cost_usd": 0.02, "vidbyte.usage.model_call_count": 3})
        self.assertNotIn("gen_ai.usage.input_tokens", out)

    def test_generic_end_namespaces_every_key(self) -> None:
        # [Silent Failure] Non-agent, non-LLM spans must never receive an invented gen_ai.* field.
        out = self.translator.translate_end(_generic_spec(), {"trial": 2, "verdict": "improved"})
        self.assertEqual(out, {"vidbyte.trial": 2, "vidbyte.verdict": "improved"})


class OpenInferenceTranslateEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.translator = OpenInferenceProviderTranslator()

    def test_llm_end_expands_output_messages_by_index(self) -> None:
        # [Edge Case] 0, 1, and multi-message tuples.
        empty = self.translator.translate_end(_llm_spec(), {"output_messages": ()})
        self.assertEqual(empty, {})
        one = self.translator.translate_end(_llm_spec(), {"output_messages": ({"role": "assistant", "content": "hi"},)})
        self.assertEqual(one["llm.output_messages.0.message.role"], "assistant")
        self.assertEqual(one["llm.output_messages.0.message.content"], "hi")
        many = self.translator.translate_end(
            _llm_spec(),
            {"output_messages": ({"role": "assistant", "content": "a"}, {"role": "tool", "content": "b"}, {"role": "assistant", "content": "c"})},
        )
        self.assertEqual(many["llm.output_messages.2.message.content"], "c")

    def test_llm_end_maps_completion_and_total_token_counts(self) -> None:
        # [Silent Failure] Field names must match llm.token_count.* exactly (cited in PR #390's design doc).
        out = self.translator.translate_end(_llm_spec(), {"output_tokens": 4, "total_tokens": 14})
        self.assertEqual(out["llm.token_count.completion"], 4)
        self.assertEqual(out["llm.token_count.total"], 14)
        self.assertNotIn("llm.token_count.prompt", out)

    def test_non_llm_end_namespaces_every_key(self) -> None:
        # [Hidden Failure] agent.run has SpanKind.CHAIN, not a dedicated OpenInference kind — must
        # fall back to the generic namespace, not silently drop or misattribute the data.
        out = self.translator.translate_end(_agent_spec(), {"input_tokens": 100})
        self.assertEqual(out, {"vidbyte.input_tokens": 100})


class TraceControllerCloseTranslationTests(unittest.TestCase):
    def test_attributes_reach_the_debug_tracer_through_translate_end(self) -> None:
        # [Silent Failure] Proves the full TraceController -> translator -> inner path, not just the translator in isolation.
        debug = DebugTracer()
        controller = TraceController(inner=debug, profile=TraceProfile.default(), translator=OTelGenAIProviderTranslator())
        ctx = controller.start_span("llm.call", model="m")
        controller.end_span(ctx, output="hi", output_messages=({"role": "assistant", "content": "hi"},), output_tokens=4)
        end_event = debug.events[-1]
        self.assertEqual(end_event["attributes"]["gen_ai.output.messages"], ({"role": "assistant", "content": "hi"},))
        self.assertEqual(end_event["attributes"]["gen_ai.usage.output_tokens"], 4)

    def test_translator_without_translate_end_forwards_nothing_extra(self) -> None:
        # [Hidden Assumption] A pre-existing custom translator with only translate_start must see zero behavior change.
        debug = DebugTracer()
        controller = TraceController(inner=debug, profile=TraceProfile.default(), translator=GenericProviderTranslator())
        ctx = controller.start_span("llm.call", model="m")
        controller.end_span(ctx, output="hi", output_tokens=4)
        end_event = debug.events[-1]
        self.assertEqual(end_event["attributes"], {})
        self.assertEqual(end_event["output"], "hi")

    def test_no_close_attributes_passed_forwards_nothing(self) -> None:
        # [Hidden Assumption] Regression guard: the overwhelming majority of spans pass no close-time attributes.
        debug = DebugTracer()
        controller = TraceController(inner=debug, profile=TraceProfile.default(), translator=OTelGenAIProviderTranslator())
        ctx = controller.start_span("llm.call", model="m")
        controller.end_span(ctx, output="hi")
        self.assertEqual(debug.events[-1]["attributes"], {})

    def test_translate_end_receives_the_same_spec_that_opened_the_span(self) -> None:
        # [Hidden Failure] Would silently lose kind/name context if a fresh empty spec were built instead.
        seen: list[SpanSpec] = []

        class RecordingTranslator:
            provider = "recording"

            def translate_start(self, spec: SpanSpec):
                from vidbyte.trace.providers.base import ProviderSpanPayload
                return ProviderSpanPayload(name=spec.name, attributes=dict(spec.attributes))

            def translate_end(self, spec: SpanSpec, attributes):
                seen.append(spec)
                return {}

        debug = DebugTracer()
        controller = TraceController(inner=debug, profile=TraceProfile.default(), translator=RecordingTranslator())
        ctx = controller.start_span("llm.call", model="m")
        controller.end_span(ctx, output="hi", output_tokens=4)
        self.assertEqual(seen[0].name, "llm.call")
        self.assertEqual(seen[0].kind, SpanKind.LLM)

    def test_close_attributes_are_redacted_before_reaching_the_translator(self) -> None:
        # [Hidden Failure] A secret-shaped close-time key must never survive to translate_end,
        # matching TraceController's existing open-time redaction guarantee.
        seen: list[dict] = []

        class RecordingTranslator:
            provider = "recording"

            def translate_start(self, spec: SpanSpec):
                from vidbyte.trace.providers.base import ProviderSpanPayload
                return ProviderSpanPayload(name=spec.name, attributes=dict(spec.attributes))

            def translate_end(self, spec: SpanSpec, attributes):
                seen.append(dict(attributes))
                return {}

        debug = DebugTracer()
        controller = TraceController(inner=debug, profile=TraceProfile.default(), translator=RecordingTranslator())
        ctx = controller.start_span("llm.call", model="m")
        controller.end_span(ctx, output="hi", api_key="sk-secret", output_tokens=4)
        self.assertNotIn("sk-secret", str(seen[0]))

    def test_suppressed_span_never_reaches_translate_end(self) -> None:
        # [Edge Case] A profile-filtered (suppressed) span must not call the translator at all.
        calls: list[object] = []

        class CountingTranslator(OTelGenAIProviderTranslator):
            def translate_end(self, spec: SpanSpec, attributes):
                calls.append(spec)
                return super().translate_end(spec, attributes)

        debug = DebugTracer()
        controller = TraceController(inner=debug, profile=TraceProfile.minimal(), translator=CountingTranslator())
        # "middleware.hook" resolves to TraceDetail.DIAGNOSTIC (see TraceController._spec_from_name),
        # which TraceProfile.minimal() suppresses entirely.
        ctx = controller.start_span("middleware.hook")
        controller.end_span(ctx, output="ok", output_tokens=4)
        self.assertEqual(calls, [])


class SecretKeyRedactionTokenWordBoundaryTests(unittest.TestCase):
    """Regression coverage for a pre-existing bug this feature's own tests uncovered: _is_secret_key's
    raw substring match on "TOKEN" also matched "TOKENS", silently redacting input_tokens/output_tokens/
    total_tokens/cached_input_tokens before they ever reached a translator. Fixed to a word-boundary match."""

    def test_token_count_keys_are_not_redacted(self) -> None:
        # [Silent Failure] This is exactly the bug that made translate_end's usage fields disappear.
        out = safe_trace_value({"input_tokens": 10, "output_tokens": 4, "total_tokens": 14, "cached_input_tokens": 2}, redact=True)
        self.assertEqual(out, {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14, "cached_input_tokens": 2})

    def test_real_credential_shaped_keys_are_still_redacted(self) -> None:
        # [Hidden Assumption] The word-boundary fix must not weaken the actual security property.
        out = safe_trace_value({"api_key": "sk-x", "auth_token": "y", "token": "z", "access_token": "w", "password": "p"}, redact=True)
        self.assertEqual(out, {})


class OTelTracerCloseAttributeTransportTests(unittest.TestCase):
    def test_close_attributes_reach_the_real_otel_span(self) -> None:
        # [Silent Failure] Proves the widened end_span contract actually reaches the wire, not just an intermediate dict.
        tracer, exporter = _otel_tracer()
        ctx = tracer.start_span("chat m")
        tracer.end_span(ctx, output="hi", **{"gen_ai.usage.output_tokens": 4})
        span = exporter.get_finished_spans()[0]
        self.assertEqual(span.attributes["gen_ai.usage.output_tokens"], 4)
        self.assertEqual(span.attributes["output.value"], "hi")

    def test_structured_close_attribute_is_json_not_python_repr(self) -> None:
        # [Silent Failure] A tuple of dicts (output_messages) must serialize as JSON, matching start-time coercion.
        import json

        tracer, exporter = _otel_tracer()
        ctx = tracer.start_span("chat m")
        tracer.end_span(ctx, **{"gen_ai.output.messages": ({"role": "assistant", "content": "hi"},)})
        span = exporter.get_finished_spans()[0]
        parsed = json.loads(span.attributes["gen_ai.output.messages"])
        self.assertEqual(parsed, [{"role": "assistant", "content": "hi"}])

    def test_end_span_with_no_attributes_is_unaffected(self) -> None:
        # [Hidden Assumption] Regression guard on the widened signature's default behavior.
        tracer, exporter = _otel_tracer()
        ctx = tracer.start_span("chat m")
        tracer.end_span(ctx, output="hi")
        span = exporter.get_finished_spans()[0]
        self.assertEqual(span.attributes["output.value"], "hi")


class PhoenixTracerCloseAttributeCoercionTests(unittest.TestCase):
    def test_structured_close_attribute_uses_json_not_str(self) -> None:
        # [Silent Failure] The pre-existing start_span coercion uses str(value); close-time attributes
        # need the richer JSON coercion since output_messages is a tuple of dicts, not a string.
        class RecordingSpan:
            def __init__(self) -> None:
                self.recorded: dict[str, object] = {}

            def set_attribute(self, key: str, value: object) -> None:
                self.recorded[key] = value

        span = RecordingSpan()
        PhoenixTracer._set_close_attribute(span, "llm.output_messages.0.message.content", {"nested": True})
        self.assertEqual(span.recorded["llm.output_messages.0.message.content"], '{"nested": true}')


if __name__ == "__main__":
    unittest.main()
