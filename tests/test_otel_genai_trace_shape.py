"""FILE: tests/test_otel_genai_trace_shape.py

PURPOSE: Verifies OpenTelemetry GenAI-shaped records produced from direct runtime trace calls.
ROLE IN CODEBASE: Protects the public Trace.otel_genai() facade, provider mappings, lifecycle updates, and agent integration.
ARCHITECTURE NOTE: Tests use plain dictionaries and a real test agent boundary; no exporter or endpoint is part of this contract.
COMMON MODIFICATION PATTERNS: Add assertions for a provider field or runtime input beside the mapping test that owns it.
KNOWN EDGE CASES: Optional fields, fallback names, foreign contexts, and caller-owned event lists are explicitly covered.
RELATED DOCS: docs/design/otel-genai-and-openinference-trace-shapes.md, vidbyte/trace/providers/README.md
TESTS: This module is the executable test suite and is also loaded by scripts/test-trace-shape-prebuilts.py.
"""

from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from typing import Any

from tests.agent_test_support import build_test_agent
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.tracing import SpanContext, TracerBase
from vidbyte.trace import Trace
from vidbyte.trace.providers import OTelGenAITrace


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


class OTelGenAITraceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.tracer = OTelGenAITrace(self.events)

    def test_agent_shape_contains_runtime_identity_fields(self) -> None:
        # [Silent Failure] The agent root must use the OTel invoke_agent naming and fields.
        context = self.tracer.start_trace(
            "agent.run",
            agent_name="researcher",
            provider="anthropic",
            run_id="run-123",
            prompt="hello",
        )
        self.tracer.end_trace(context, output="done")
        record = self.events[0]
        self.assertEqual(record["name"], "invoke_agent researcher")
        self.assertEqual(
            record["attributes"],
            {
                "gen_ai.operation.name": "invoke_agent",
                "gen_ai.agent.name": "researcher",
                "gen_ai.provider.name": "anthropic",
                "gen_ai.conversation.id": "run-123",
                "vidbyte.prompt": "hello",
            },
        )
        self.assertEqual(record["output"], "done")
        self.assertEqual(record["status"], "ok")

    def test_llm_shape_matches_the_requested_example(self) -> None:
        # [Silent Failure] Required and optional OTel GenAI keys must retain their exact names.
        context = self.tracer.start_span(
            "llm.call",
            provider="anthropic",
            model="claude-3-5-sonnet",
            input_messages="...",
            system="...",
            input_tokens=145,
            output_tokens=62,
            finish_reason=["stop"],
        )
        self.tracer.end_span(context, output="final answer")
        record = self.events[0]
        self.assertEqual(record["name"], "chat claude-3-5-sonnet")
        self.assertEqual(
            record["attributes"],
            {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "anthropic",
                "gen_ai.request.model": "claude-3-5-sonnet",
                "gen_ai.input.messages": "...",
                "gen_ai.system_instructions": "...",
                "gen_ai.usage.input_tokens": 145,
                "gen_ai.usage.output_tokens": 62,
                "gen_ai.response.finish_reasons": ["stop"],
            },
        )
        self.assertEqual(record["output"], "final answer")

    def test_tool_shape_preserves_structured_arguments_and_parent(self) -> None:
        # [Hidden Failure] Tool records must remain attached to the agent record and retain arguments.
        root = self.tracer.start_trace("agent.run", agent_name="researcher")
        tool = self.tracer.start_span(
            "tool.call",
            parent=root,
            tool_name="web_search",
            call_id="call-1",
            arguments={"query": "vidbyte"},
        )
        self.tracer.end_span(tool, output={"hits": 1})
        self.tracer.end_trace(root)
        record = self.events[1]
        self.assertEqual(record["name"], "execute_tool web_search")
        self.assertEqual(record["parent_id"], 1)
        self.assertEqual(record["attributes"]["gen_ai.tool.name"], "web_search")
        self.assertEqual(record["attributes"]["gen_ai.tool.call.id"], "call-1")
        self.assertEqual(record["attributes"]["gen_ai.tool.call.arguments"], {"query": "vidbyte"})
        self.assertEqual(record["output"], {"hits": 1})

    def test_optional_fields_are_omitted_and_unknown_fields_are_namespaced(self) -> None:
        # [Hidden Assumption] Missing response data must not be fabricated or emitted as None.
        attributes = {"provider": "openai", "model": "gpt-4.1", "metadata": {"request": "x"}}
        self.tracer.start_span("llm.call", **attributes)
        self.assertEqual(attributes, {"provider": "openai", "model": "gpt-4.1", "metadata": {"request": "x"}})
        shaped = self.events[0]["attributes"]
        self.assertNotIn("gen_ai.input.messages", shaped)
        self.assertNotIn("gen_ai.response.finish_reasons", shaped)
        self.assertEqual(shaped["vidbyte.metadata"], {"request": "x"})

    def test_missing_names_use_stable_fallbacks(self) -> None:
        # [Edge Case] A partial runtime call must still produce a useful record.
        self.tracer.start_trace("agent.run")
        self.tracer.start_span("llm.call")
        self.tracer.start_span("tool.call")
        self.assertEqual([row["name"] for row in self.events], ["invoke_agent agent", "chat unknown", "execute_tool unknown_tool"])

    def test_foreign_context_cannot_close_or_parent_a_record(self) -> None:
        # [Edge Case] Context ownership prevents accidental cross-tracer lifecycle mutation.
        other = OTelGenAITrace([])
        foreign = other.start_trace("agent.run", agent_name="other")
        child = self.tracer.start_span("llm.call", parent=foreign, model="m", provider="p")
        self.tracer.end_span(SpanContext(), output="ignored")
        self.tracer.end_span(child, error=RuntimeError("boom"))
        self.assertIsNone(self.events[0]["parent_id"])
        self.assertEqual(self.events[0]["error"], "boom")
        self.assertEqual(self.events[0]["status"], "error")


class OTelGenAIFacadeAndRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_facade_returns_direct_tracer_and_agent_populates_it(self) -> None:
        # [Hidden Failure] The real agent must call the provider directly, without TraceController.
        events: list[dict[str, Any]] = []
        tracer = Trace.otel_genai(events)
        self.assertIsInstance(tracer, OTelGenAITrace)
        self.assertIsInstance(tracer, TracerBase)
        agent = build_test_agent(
            name="researcher",
            system_prompt="Be concise.",
            runner=_TextRunner(),
            trace=tracer,
        )
        reply = await agent.arun("hello")
        self.assertIn("answer: hello", reply.content)
        self.assertEqual([record["name"] for record in events], ["invoke_agent researcher", "chat gpt-test"])
        self.assertEqual(events[1]["parent_id"], events[0]["id"])
        self.assertEqual(events[1]["attributes"]["gen_ai.provider.name"], "openai")
        self.assertEqual(events[1]["attributes"]["gen_ai.request.model"], "gpt-test")
        self.assertEqual(events[1]["attributes"]["gen_ai.input.messages"][-1], {"role": "user", "content": "hello"})
        self.assertEqual(events[0]["status"], "ok")
        self.assertEqual(events[1]["status"], "ok")
        self.assertEqual(events[1]["attributes"]["gen_ai.usage.input_tokens"], 145)
        self.assertEqual(events[1]["attributes"]["gen_ai.usage.output_tokens"], 62)
        self.assertEqual(events[1]["attributes"]["gen_ai.response.finish_reasons"], ["stop"])

    def test_facade_has_no_endpoint_or_export_configuration(self) -> None:
        # [Silent Failure] The new API is intentionally in-memory and cannot reintroduce endpoint setup.
        self.assertEqual(list(inspect.signature(Trace.otel_genai).parameters), ["events"])
        with self.assertRaises(TypeError):
            Trace.otel_genai(endpoint="http://collector.invalid")


if __name__ == "__main__":
    unittest.main()
