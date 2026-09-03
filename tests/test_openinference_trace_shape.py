"""FILE: tests/test_openinference_trace_shape.py

PURPOSE: Verifies OpenInference-shaped records produced from direct runtime trace calls.
ROLE IN CODEBASE: Protects the public Trace.openinference() facade, provider mappings, lifecycle updates, and agent integration.
ARCHITECTURE NOTE: Tests use plain dictionaries and a real test agent boundary; no exporter or endpoint is part of this contract.
COMMON MODIFICATION PATTERNS: Add assertions for a provider field or runtime input beside the mapping test that owns it.
KNOWN EDGE CASES: Optional fields, fallback names, foreign contexts, and caller-owned event lists are explicitly covered.
RELATED DOCS: docs/design/otel-genai-and-openinference-trace-shapes.md, vidbyte/trace/providers/README.md
TESTS: This module is the executable test suite and is also loaded by scripts/test-trace-shape-prebuilts.py.
"""

from __future__ import annotations

import inspect
import json
import unittest
from types import SimpleNamespace
from typing import Any

from tests.agent_test_support import build_test_agent
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.tracing import SpanContext, TracerBase
from vidbyte.trace import Trace
from vidbyte.trace.providers import OpenInferenceTrace


class _TextRunner:
    """Offline model runner used to verify the real agent-to-tracer boundary."""

    _config = SimpleNamespace(provider="openai", model="gpt-test")

    def run(self, prompt: str, **_: Any) -> TextModelResponse:
        return TextModelResponse(
            provider="openai",
            model="gpt-test",
            text=f"answer: {prompt}",
            raw={"choices": [{"finish_reason": "stop"}]},
            usage={"prompt_tokens": 145, "completion_tokens": 62, "total_tokens": 207},
        )


class OpenInferenceTraceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.tracer = OpenInferenceTrace(self.events)

    def test_agent_shape_uses_the_agent_kind(self) -> None:
        # [Silent Failure] OpenInference has a first-class AGENT kind for the agent root.
        context = self.tracer.start_trace("agent.run", agent_name="researcher", run_id="run-1")
        self.tracer.end_trace(context, output="done")
        record = self.events[0]
        self.assertEqual(record["name"], "agent.run")
        self.assertEqual(record["attributes"]["openinference.span.kind"], "AGENT")
        self.assertEqual(record["attributes"]["agent.name"], "researcher")
        self.assertEqual(record["attributes"]["vidbyte.run_id"], "run-1")
        self.assertEqual(record["status"], "ok")

    def test_llm_shape_flattens_messages_and_maps_usage(self) -> None:
        # [Silent Failure] OpenInference uses indexed flattened message attributes.
        context = self.tracer.start_span(
            "llm.call",
            provider="anthropic",
            model="claude-3-5-sonnet",
            input_messages=(
                {"role": "system", "content": "be careful"},
                {"role": "user", "content": "hello"},
            ),
            input_tokens=145,
            output_tokens=62,
            total_tokens=207,
            finish_reason="stop",
        )
        self.tracer.end_span(context, output="answer")
        attributes = self.events[0]["attributes"]
        self.assertEqual(attributes["openinference.span.kind"], "LLM")
        self.assertEqual(attributes["llm.system"], "anthropic")
        self.assertEqual(attributes["llm.provider"], "anthropic")
        self.assertEqual(attributes["llm.model_name"], "claude-3-5-sonnet")
        self.assertEqual(attributes["llm.input_messages.0.message.role"], "system")
        self.assertEqual(attributes["llm.input_messages.0.message.content"], "be careful")
        self.assertEqual(attributes["llm.input_messages.1.message.role"], "user")
        self.assertEqual(attributes["llm.input_messages.1.message.content"], "hello")
        self.assertEqual(attributes["llm.token_count.prompt"], 145)
        self.assertEqual(attributes["llm.token_count.completion"], 62)
        self.assertEqual(attributes["llm.token_count.total"], 207)
        self.assertEqual(attributes["llm.finish_reason"], "stop")
        self.assertEqual(self.events[0]["output"], "answer")

    def test_tool_shape_uses_json_arguments(self) -> None:
        # [Silent Failure] OpenInference documents function arguments as a JSON string.
        context = self.tracer.start_span(
            "tool.call",
            tool_name="web_search",
            call_id="call-1",
            arguments={"query": "vidbyte", "limit": 3},
        )
        self.tracer.end_span(context, output="result")
        attributes = self.events[0]["attributes"]
        self.assertEqual(attributes["openinference.span.kind"], "TOOL")
        self.assertEqual(attributes["tool.name"], "web_search")
        self.assertEqual(attributes["tool_call.function.name"], "web_search")
        self.assertEqual(attributes["tool_call.id"], "call-1")
        self.assertEqual(json.loads(attributes["tool_call.function.arguments"]), {"query": "vidbyte", "limit": 3})

    def test_other_runtime_names_get_documented_kinds_or_chain(self) -> None:
        # [Hidden Assumption] Unmapped operations still have a valid OpenInference kind.
        for name, expected in (
            ("retriever.search", "RETRIEVER"),
            ("embedding.create", "EMBEDDING"),
            ("parser.tool_calls", "CHAIN"),
            ("runtime.iteration", "CHAIN"),
        ):
            tracer = OpenInferenceTrace([])
            tracer.start_span(name, custom="value")
            self.assertEqual(tracer.events[0]["attributes"]["openinference.span.kind"], expected)
            self.assertEqual(tracer.events[0]["attributes"]["vidbyte.custom"], "value")

    def test_optional_fields_are_omitted_and_input_is_not_mutated(self) -> None:
        # [Edge Case] A minimal call must not contain fabricated provider fields.
        attributes = {"model": "m", "provider": "p"}
        self.tracer.start_span("llm.call", **attributes)
        self.assertEqual(attributes, {"model": "m", "provider": "p"})
        shaped = self.events[0]["attributes"]
        self.assertNotIn("llm.input_messages.0.message.role", shaped)
        self.assertNotIn("llm.token_count.prompt", shaped)
        self.assertNotIn("llm.finish_reason", shaped)

    def test_foreign_context_cannot_close_or_parent_a_record(self) -> None:
        # [Hidden Failure] A context from another provider instance is not a valid parent.
        other = OpenInferenceTrace([])
        foreign = other.start_trace("agent.run", agent_name="other")
        child = self.tracer.start_span("llm.call", parent=foreign, model="m", provider="p")
        self.tracer.end_span(SpanContext(), output="ignored")
        self.tracer.end_span(child, error=RuntimeError("boom"))
        self.assertIsNone(self.events[0]["parent_id"])
        self.assertEqual(self.events[0]["error"], "boom")
        self.assertEqual(self.events[0]["status"], "error")


class OpenInferenceFacadeAndRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_facade_returns_direct_tracer_and_agent_populates_it(self) -> None:
        # [Hidden Failure] The real agent must call the provider directly, without TraceController.
        events: list[dict[str, Any]] = []
        tracer = Trace.openinference(events)
        self.assertIsInstance(tracer, OpenInferenceTrace)
        self.assertIsInstance(tracer, TracerBase)
        agent = build_test_agent(
            name="researcher",
            system_prompt="Be concise.",
            runner=_TextRunner(),
            trace=tracer,
        )
        reply = await agent.arun("hello")
        self.assertIn("answer: hello", reply.content)
        self.assertEqual([record["name"] for record in events], ["agent.run", "llm.call"])
        self.assertEqual(events[1]["parent_id"], events[0]["id"])
        self.assertEqual(events[1]["attributes"]["llm.system"], "openai")
        self.assertEqual(events[1]["attributes"]["llm.model_name"], "gpt-test")
        self.assertEqual(events[1]["attributes"]["llm.input_messages.0.message.role"], "system")
        self.assertEqual(events[0]["status"], "ok")
        self.assertEqual(events[1]["status"], "ok")
        self.assertEqual(events[1]["attributes"]["llm.token_count.prompt"], 145)
        self.assertEqual(events[1]["attributes"]["llm.token_count.completion"], 62)
        self.assertEqual(events[1]["attributes"]["llm.token_count.total"], 207)
        self.assertEqual(events[1]["attributes"]["llm.finish_reason"], "stop")

    def test_facade_has_no_endpoint_or_export_configuration(self) -> None:
        # [Silent Failure] The new API is intentionally in-memory and cannot reintroduce endpoint setup.
        self.assertEqual(list(inspect.signature(Trace.openinference).parameters), ["events"])
        with self.assertRaises(TypeError):
            Trace.openinference(endpoint="http://collector.invalid")


if __name__ == "__main__":
    unittest.main()
