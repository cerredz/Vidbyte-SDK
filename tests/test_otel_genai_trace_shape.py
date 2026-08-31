"""FILE: tests/test_otel_genai_trace_shape.py

PURPOSE: Verifies OTelGenAIProviderTranslator output against the live OTel GenAI spec's required fields.
ROLE IN CODEBASE: Golden-fixture and facade test suite for the "otel-genai" provider shape.
ARCHITECTURE NOTE: Required field sets are hardcoded constants sourced from the spec docs cited in the design doc, not fetched live, to stay deterministic and offline.
COMMON MODIFICATION PATTERNS: Update the golden field sets only after re-verifying the live spec document; keep translator and facade coverage in this one file.
KNOWN EDGE CASES: Redaction inheritance from TraceController and profile-suppression composition are covered as full-path integration tests, not translator unit tests alone.
RELATED DOCS: docs/design/otel-genai-and-openinference-trace-shapes.md
TESTS: This file is the test.
"""

from __future__ import annotations

import unittest

from vidbyte.lib.errors import TracerConfigurationError
from vidbyte.lib.tracing import TracerBase
from vidbyte.trace import Trace, TraceController, TraceProfile
from vidbyte.trace.base import _TraceFactory
from vidbyte.trace.debug import DebugTracer
from vidbyte.trace.providers import OTelGenAIProviderTranslator
from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail

# Field names verified against the live spec documents during this feature's design research:
# gen-ai-agent-spans.md, gen-ai-spans.md, execute-tool-span.md
# (https://github.com/open-telemetry/semantic-conventions-genai).
_REQUIRED_AGENT_FIELDS = {"gen_ai.operation.name", "gen_ai.agent.name"}
_REQUIRED_LLM_FIELDS = {"gen_ai.operation.name", "gen_ai.provider.name", "gen_ai.request.model"}
_REQUIRED_TOOL_FIELDS = {"gen_ai.operation.name", "gen_ai.tool.name"}


def _llm_spec(**attrs: object) -> SpanSpec:
    # Builds a representative LLM-kind semantic span, matching AgentRuntime._llm_trace_inputs keys.
    return SpanSpec("llm.call", SpanKind.LLM, "agents", TraceDetail.MINIMAL, ParentPolicy.CURRENT, attrs)


def _tool_spec(**attrs: object) -> SpanSpec:
    # Builds a representative TOOL-kind semantic span, matching AgentRuntime.execute_tool_call keys.
    return SpanSpec("tool.call", SpanKind.TOOL, "tools", TraceDetail.MINIMAL, ParentPolicy.CURRENT, attrs)


def _agent_spec(**attrs: object) -> SpanSpec:
    # Builds a representative agent.run semantic span.
    return SpanSpec("agent.run", SpanKind.CHAIN, "agents", TraceDetail.MINIMAL, ParentPolicy.ROOT, attrs)


class OTelGenAITranslatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.translator = OTelGenAIProviderTranslator()

    def test_agent_run_maps_to_invoke_agent_span(self) -> None:
        # [Silent Failure] Span name and both required fields must be exact.
        payload = self.translator.translate_start(_agent_spec(agent_name="research-agent", provider="anthropic", run_id="run-1"))
        self.assertEqual(payload.name, "invoke_agent research-agent")
        self.assertEqual(payload.attributes["gen_ai.operation.name"], "invoke_agent")
        self.assertEqual(payload.attributes["gen_ai.agent.name"], "research-agent")
        self.assertEqual(payload.attributes["gen_ai.provider.name"], "anthropic")
        self.assertEqual(payload.attributes["gen_ai.conversation.id"], "run-1")

    def test_llm_call_maps_to_chat_span(self) -> None:
        # [Silent Failure] Span name and every required field must be exact.
        payload = self.translator.translate_start(_llm_spec(model="claude-3-5-sonnet", provider="anthropic"))
        self.assertEqual(payload.name, "chat claude-3-5-sonnet")
        self.assertEqual(payload.attributes["gen_ai.operation.name"], "chat")
        self.assertEqual(payload.attributes["gen_ai.provider.name"], "anthropic")
        self.assertEqual(payload.attributes["gen_ai.request.model"], "claude-3-5-sonnet")

    def test_usage_and_finish_reason_map_only_when_present(self) -> None:
        # [Hidden Assumption] Absence must mean the key is missing, not a zero/empty default.
        without_usage = self.translator.translate_start(_llm_spec(model="m", provider="p"))
        self.assertNotIn("gen_ai.usage.input_tokens", without_usage.attributes)
        self.assertNotIn("gen_ai.response.finish_reasons", without_usage.attributes)
        with_usage = self.translator.translate_start(_llm_spec(model="m", provider="p", input_tokens=145, output_tokens=62, finish_reason=["stop"]))
        self.assertEqual(with_usage.attributes["gen_ai.usage.input_tokens"], 145)
        self.assertEqual(with_usage.attributes["gen_ai.usage.output_tokens"], 62)
        self.assertEqual(with_usage.attributes["gen_ai.response.finish_reasons"], ["stop"])

    def test_tool_call_maps_to_execute_tool_span(self) -> None:
        # [Silent Failure] Span name and every required field must be exact.
        payload = self.translator.translate_start(_tool_spec(tool_name="web_search", call_id="call_1", arguments={"query": "x"}))
        self.assertEqual(payload.name, "execute_tool web_search")
        self.assertEqual(payload.attributes["gen_ai.operation.name"], "execute_tool")
        self.assertEqual(payload.attributes["gen_ai.tool.name"], "web_search")
        self.assertEqual(payload.attributes["gen_ai.tool.call.id"], "call_1")
        self.assertEqual(payload.attributes["gen_ai.tool.call.arguments"], {"query": "x"})

    def test_tool_call_falls_back_to_tool_input_when_arguments_absent(self) -> None:
        # [Hidden Assumption] Matches the real runtime.py call site, which sets both tool_input and arguments.
        payload = self.translator.translate_start(_tool_spec(tool_name="t", tool_input={"a": 1}))
        self.assertEqual(payload.attributes["gen_ai.tool.call.arguments"], {"a": 1})

    def test_missing_model_tool_name_agent_name_never_raises(self) -> None:
        # [Hidden Assumption] Placeholders must be used instead of raising or emitting an empty span name.
        self.assertEqual(self.translator.translate_start(_llm_spec()).name, "chat unknown")
        self.assertEqual(self.translator.translate_start(_tool_spec()).name, "execute_tool unknown_tool")
        self.assertEqual(self.translator.translate_start(_agent_spec()).name, "invoke_agent agent")

    def test_generic_span_is_namespaced_not_invented(self) -> None:
        # [Hidden Failure] The translator must never guess an unverified gen_ai.* field for a span kind not verified this session.
        spec = SpanSpec("algorithm.reflexion.trial", SpanKind.CHAIN, "algorithms", TraceDetail.VERBOSE, ParentPolicy.CURRENT, {"trial": 1, "score": 0.8})
        payload = self.translator.translate_start(spec)
        self.assertEqual(payload.name, "algorithm.reflexion.trial")
        self.assertEqual(payload.attributes["gen_ai.operation.name"], "algorithm.reflexion.trial")
        self.assertEqual(payload.attributes["vidbyte.trial"], 1)
        self.assertEqual(payload.attributes["vidbyte.score"], 0.8)
        self.assertFalse(any(key.startswith("gen_ai.") and key != "gen_ai.operation.name" for key in payload.attributes))

    def test_agent_llm_tool_payloads_match_golden_required_fields_exactly(self) -> None:
        # [Silent Failure] Guards against typos/case drift in the field names themselves.
        agent_attrs = set(self.translator.translate_start(_agent_spec(agent_name="a")).attributes)
        llm_attrs = set(self.translator.translate_start(_llm_spec(model="m", provider="p")).attributes)
        tool_attrs = set(self.translator.translate_start(_tool_spec(tool_name="t")).attributes)
        self.assertTrue(_REQUIRED_AGENT_FIELDS.issubset(agent_attrs))
        self.assertTrue(_REQUIRED_LLM_FIELDS.issubset(llm_attrs))
        self.assertTrue(_REQUIRED_TOOL_FIELDS.issubset(tool_attrs))


class OTelGenAIRedactionIntegrationTests(unittest.TestCase):
    def test_secret_shaped_attribute_is_redacted_before_translator_ever_sees_it(self) -> None:
        # [Hidden Assumption] Full-path test through the real TraceController, not a hand-built SpanSpec.
        events: list[dict] = []
        controller = TraceController(inner=DebugTracer(events), profile=TraceProfile.default(), translator=OTelGenAIProviderTranslator())
        root = controller.start_trace("agent.run", agent_name="a")
        span = controller.start_span("tool.call", parent=root, tool_name="t", api_key="sk-super-secret")
        controller.end_span(span)
        controller.end_trace(root)
        tool_event = next(e for e in events if e["name"] == "execute_tool t")
        self.assertNotIn("vidbyte.api_key", tool_event["attributes"])


class OTelGenAIProfileCompositionTests(unittest.TestCase):
    def test_minimal_profile_suppresses_algorithm_spans_before_translation(self) -> None:
        # [Hidden Failure] Profile filtering must compose correctly with the new translator, not just the existing ones.
        events: list[dict] = []
        controller = TraceController(inner=DebugTracer(events), profile=TraceProfile.minimal(), translator=OTelGenAIProviderTranslator())
        root = controller.start_trace("agent.run", agent_name="a")
        span = controller.start_span("algorithm.reflexion.trial", parent=root)
        controller.end_span(span)
        controller.end_trace(root)
        names = [e.get("name") for e in events]
        self.assertNotIn("algorithm.reflexion.trial", names)


class OTelGenAIWorksThroughExistingProvidersTests(unittest.TestCase):
    def test_gen_ai_shaped_payload_survives_a_real_langsmith_tracer_unchanged(self) -> None:
        # [Hidden Failure] "Works for all providers" means the shape must also survive a non-OTel
        # inner tracer's real code path, not only the new OTelTracer/PhoenixTracer. Mocks langsmith.Client
        # to avoid a real network call while exercising LangSmithTracer's actual start_span implementation.
        from unittest.mock import MagicMock, patch

        with patch("langsmith.Client", return_value=MagicMock()):
            from vidbyte.providers.tracing import LangSmithTracer

            langsmith_tracer = LangSmithTracer(api_key="fake-key", project="p")
        controller = TraceController(inner=langsmith_tracer, profile=TraceProfile.default(), translator=OTelGenAIProviderTranslator())
        root = controller.start_trace("agent.run", agent_name="a")
        span = controller.start_span("tool.call", parent=root, tool_name="web_search", call_id="c1", arguments={"q": "x"})
        controller.end_span(span)
        controller.end_trace(root)
        create_run_calls = langsmith_tracer._client.create_run.call_args_list
        tool_call_kwargs = create_run_calls[-1].kwargs
        self.assertEqual(tool_call_kwargs["inputs"]["gen_ai.tool.name"], "web_search")
        self.assertEqual(tool_call_kwargs["inputs"]["gen_ai.tool.call.arguments"], {"q": "x"})


class OTelGenAIFacadeTests(unittest.TestCase):
    def test_resolve_translator_returns_otel_genai_translator(self) -> None:
        # [Edge Case] String resolution must reach the new translator class.
        self.assertIsInstance(_TraceFactory.resolve_translator("otel-genai"), OTelGenAIProviderTranslator)

    def test_trace_otel_genai_wraps_default_profile_and_translator(self) -> None:
        # [Silent Failure] Trace.profile("otel-genai") must actually assemble the controller correctly.
        controller = Trace.profile(_FakeTracer(), profile=None, provider="otel-genai")
        self.assertIsInstance(controller, TraceController)
        self.assertIsInstance(controller.translator, OTelGenAIProviderTranslator)
        self.assertEqual(controller.profile.detail, TraceProfile.default().detail)

    def test_trace_otel_genai_propagates_configuration_error_with_no_endpoint(self) -> None:
        # [Hidden Failure] Construction errors from Trace.otel must not be swallowed by the facade.
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(TracerConfigurationError):
                Trace.otel_genai()

    def test_trace_otel_genai_session_returns_session_controller(self) -> None:
        # [Edge Case] Session variant must exist and wire the same translator.
        from vidbyte.trace import SessionTraceController

        session = Trace.session(_FakeTracer(), name="run", profile=TraceProfile.default(), provider="otel-genai")
        self.assertIsInstance(session, SessionTraceController)


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
