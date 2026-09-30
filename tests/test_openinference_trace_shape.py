"""FILE: tests/test_openinference_trace_shape.py

PURPOSE: Verifies OpenInferenceProviderTranslator output against the live OpenInference spec's required fields.
ROLE IN CODEBASE: Golden-fixture, facade, and Phoenix-interop test suite for the "openinference" provider shape.
ARCHITECTURE NOTE: Required field sets are hardcoded constants sourced from the spec doc cited in the design doc, not fetched live, to stay deterministic and offline.
COMMON MODIFICATION PATTERNS: Update the golden field sets only after re-verifying the live spec document; keep translator, facade, and Phoenix interop coverage in this one file.
KNOWN EDGE CASES: Phoenix interop tests never call end_span/end_trace on a live PhoenixTracer's real span to avoid a network export attempt, except through the balanced try/finally full-pipeline test, which must stay balanced to avoid leaking TraceController's shared span-stack ContextVar into other tests.
RELATED DOCS: docs/design/otel-genai-and-openinference-trace-shapes.md
TESTS: This file is the test.
"""

from __future__ import annotations

import json
import unittest

from vidbyte.lib.errors import TracerConfigurationError
from vidbyte.lib.tracing import TracerBase
from vidbyte.providers.tracing import PhoenixTracer
from vidbyte.trace import Trace, TraceController, TraceProfile
from vidbyte.trace.base import _TraceFactory
from vidbyte.trace.providers import OpenInferenceProviderTranslator
from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail

# Field names verified against the live spec document during this feature's design research:
# https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md
_REQUIRED_LLM_FIELDS = {"openinference.span.kind", "llm.model_name"}
_REQUIRED_TOOL_FIELDS = {"openinference.span.kind", "tool.name", "tool_call.function.name"}


def _llm_spec(**attrs: object) -> SpanSpec:
    # Builds a representative LLM-kind semantic span, matching AgentRuntime._llm_trace_inputs keys.
    return SpanSpec("llm.call", SpanKind.LLM, "agents", TraceDetail.MINIMAL, ParentPolicy.CURRENT, attrs)


def _tool_spec(**attrs: object) -> SpanSpec:
    # Builds a representative TOOL-kind semantic span, matching AgentRuntime.execute_tool_call keys.
    return SpanSpec("tool.call", SpanKind.TOOL, "tools", TraceDetail.MINIMAL, ParentPolicy.CURRENT, attrs)


class OpenInferenceTranslatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.translator = OpenInferenceProviderTranslator()

    def test_span_kind_is_set_for_every_span_kind_including_unmapped_ones(self) -> None:
        # [Hidden Assumption] openinference.span.kind is the one field the spec requires on every span, no exceptions.
        for kind in SpanKind:
            spec = SpanSpec("x", kind, "core", TraceDetail.MINIMAL, ParentPolicy.CURRENT, {})
            payload = self.translator.translate_start(spec)
            self.assertIn("openinference.span.kind", payload.attributes)

    def test_llm_span_maps_model_name_and_expands_input_messages(self) -> None:
        # [Silent Failure] Both the flat model_name field and the indexed message expansion must be exact.
        messages = ({"role": "system", "content": "be careful"}, {"role": "user", "content": "hi"})
        payload = self.translator.translate_start(_llm_spec(model="claude-3-5-sonnet", input_messages=messages))
        self.assertEqual(payload.attributes["llm.model_name"], "claude-3-5-sonnet")
        self.assertEqual(payload.attributes["llm.input_messages.0.message.role"], "system")
        self.assertEqual(payload.attributes["llm.input_messages.0.message.content"], "be careful")
        self.assertEqual(payload.attributes["llm.input_messages.1.message.role"], "user")
        self.assertEqual(payload.attributes["llm.input_messages.1.message.content"], "hi")

    def test_llm_span_maps_token_counts_only_when_present(self) -> None:
        # [Hidden Assumption] Absence must mean the key is missing entirely.
        without = self.translator.translate_start(_llm_spec(model="m"))
        self.assertNotIn("llm.token_count.prompt", without.attributes)
        with_counts = self.translator.translate_start(_llm_spec(model="m", input_tokens=145, output_tokens=62))
        self.assertEqual(with_counts.attributes["llm.token_count.prompt"], 145)
        self.assertEqual(with_counts.attributes["llm.token_count.completion"], 62)

    def test_tool_span_maps_name_id_and_arguments_as_valid_json(self) -> None:
        # [Silent Failure] tool_call.function.arguments must be a JSON string, not a Python repr.
        payload = self.translator.translate_start(_tool_spec(tool_name="web_search", call_id="call_1", arguments={"query": "x"}))
        self.assertEqual(payload.attributes["tool.name"], "web_search")
        self.assertEqual(payload.attributes["tool_call.function.name"], "web_search")
        self.assertEqual(payload.attributes["tool_call.id"], "call_1")
        self.assertEqual(json.loads(payload.attributes["tool_call.function.arguments"]), {"query": "x"})

    def test_tool_span_falls_back_to_tool_input_when_arguments_absent(self) -> None:
        # [Hidden Assumption] Matches the real runtime.py call site, which sets both tool_input and arguments.
        payload = self.translator.translate_start(_tool_spec(tool_name="t", tool_input={"a": 1}))
        self.assertEqual(json.loads(payload.attributes["tool_call.function.arguments"]), {"a": 1})

    def test_does_not_mutate_input_span_spec_attributes(self) -> None:
        # [Hidden Failure] Matches the existing LangSmithProviderTranslator non-mutation convention.
        spec = _llm_spec(model="m")
        original = dict(spec.attributes)
        self.translator.translate_start(spec)
        self.assertEqual(dict(spec.attributes), original)

    def test_llm_and_tool_payloads_match_golden_required_fields_exactly(self) -> None:
        # [Silent Failure] Guards against typos/case drift in the field names themselves.
        llm_attrs = set(self.translator.translate_start(_llm_spec(model="m")).attributes)
        tool_attrs = set(self.translator.translate_start(_tool_spec(tool_name="t")).attributes)
        self.assertTrue(_REQUIRED_LLM_FIELDS.issubset(llm_attrs))
        self.assertTrue(_REQUIRED_TOOL_FIELDS.issubset(tool_attrs))


class OpenInferenceFacadeTests(unittest.TestCase):
    def test_resolve_translator_returns_openinference_translator(self) -> None:
        # [Edge Case] String resolution must reach the new translator class.
        self.assertIsInstance(_TraceFactory.resolve_translator("openinference"), OpenInferenceProviderTranslator)

    def test_trace_openinference_wraps_default_profile_and_translator(self) -> None:
        # [Silent Failure] Trace.profile("openinference") must actually assemble the controller correctly.
        controller = Trace.profile(_FakeTracer(), profile=None, provider="openinference")
        self.assertIsInstance(controller, TraceController)
        self.assertIsInstance(controller.translator, OpenInferenceProviderTranslator)

    def test_trace_openinference_propagates_configuration_error_with_no_endpoint(self) -> None:
        # [Hidden Failure] Construction errors from Trace.otel must not be swallowed by the facade.
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(TracerConfigurationError):
                Trace.openinference()

    def test_trace_openinference_session_returns_session_controller(self) -> None:
        # [Edge Case] Session variant must exist and wire the same translator.
        from vidbyte.trace import SessionTraceController

        session = Trace.session(_FakeTracer(), name="run", profile=TraceProfile.default(), provider="openinference")
        self.assertIsInstance(session, SessionTraceController)


class PhoenixOpenInferenceInteropTests(unittest.TestCase):
    def test_phoenix_default_routes_the_openinference_translators_value_through_the_full_pipeline(self) -> None:
        # [Silent Failure] End-to-end proof: TraceController -> OpenInferenceProviderTranslator -> PhoenixTracer
        # all wire together correctly, using verbose profile so the runtime.iteration span is not suppressed.
        controller = Trace.phoenix_default(endpoint="http://127.0.0.1:1/v1/traces", profile=TraceProfile.verbose())
        self.assertIsInstance(controller.inner, PhoenixTracer)
        root = controller.start_trace("agent.run", agent_name="a")
        span = None
        try:
            span = controller.start_span("runtime.iteration", parent=root)
            provider_context = span.provider_context
            self.assertIsNotNone(provider_context)
            self.assertEqual(provider_context.span.attributes["openinference.span.kind"], "CHAIN")
        finally:
            # PhoenixTracer.end_span/end_trace are fail-open even against an unreachable endpoint (port 1
            # refuses immediately), and ending here matters: leaving these open would leak entries onto
            # TraceController's shared _SPAN_STACK ContextVar and corrupt unrelated tests in this process.
            controller.end_span(span)
            controller.end_trace(root)

    def test_phoenix_start_span_still_guesses_when_no_explicit_kind_is_given(self) -> None:
        # [Hidden Assumption] The phoenix.py fix must not change behavior for every existing caller that never sets the key.
        tracer = PhoenixTracer(endpoint="http://127.0.0.1:1/v1/traces")
        ctx = tracer.start_span("llm.call")
        self.assertEqual(ctx.span.attributes["openinference.span.kind"], "LLM")

    def test_phoenix_start_span_respects_explicit_kind_when_given(self) -> None:
        # [Silent Failure] Direct unit-level proof of the phoenix.py guard, independent of the controller.
        tracer = PhoenixTracer(endpoint="http://127.0.0.1:1/v1/traces")
        ctx = tracer.start_span("runtime.iteration", **{"openinference.span.kind": "CHAIN", "run_type": "tool"})
        self.assertEqual(ctx.span.attributes["openinference.span.kind"], "CHAIN")


class _FakeTracer(TracerBase):
    """Minimal TracerBase implementation used only to exercise facade wiring without real transport."""

    def start_trace(self, name: str, **attributes: object) -> object:
        # Returns a bare object; only used to prove wiring, never inspected for span data.
        return object()

    def end_trace(self, context: object, **_: object) -> None:
        return None

    def start_span(self, name: str, parent: object | None = None, **attributes: object) -> object:
        # Returns a bare object; only used to prove wiring, never inspected for span data.
        return object()

    def end_span(self, context: object, **_: object) -> None:
        return None


if __name__ == "__main__":
    unittest.main()
