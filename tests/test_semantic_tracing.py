from __future__ import annotations

import asyncio
import types
import unittest
from typing import Any
from unittest.mock import patch

from tests.agent_test_support import build_test_agent
from vidbyte import Agent, AggregateAgent, ProposerSpec, Trace, TraceController, TraceProfile
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tracing import SpanContext, TracerBase
from vidbyte.trace.providers import GenericProviderTranslator, LangSmithProviderTranslator
from vidbyte.trace.registry import TraceComponentRegistry
from vidbyte.trace.schema import SpanKind, SpanSpec, TraceDetail


class RecordingTracer(TracerBase):
    """Tracer double used by semantic tracing tests."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._counter = 0

    def start_trace(self, name: str, **attributes: Any) -> SpanContext:
        # Records root trace starts and returns an identifiable context.
        context = self._context("trace", name)
        self.events.append({"type": "start_trace", "name": name, "attributes": dict(attributes), "parent": None, "context": context})
        return context

    def end_trace(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None:
        # Records root trace completion.
        self.events.append({"type": "end_trace", "context": context, "output": output, "error": error})

    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SpanContext:
        # Records child span starts and returns an identifiable context.
        context = self._context("span", name)
        self.events.append({"type": "start_span", "name": name, "attributes": dict(attributes), "parent": parent, "context": context})
        return context

    def end_span(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None:
        # Records child span completion.
        self.events.append({"type": "end_span", "context": context, "output": output, "error": error})

    def _context(self, kind: str, name: str) -> SpanContext:
        # Builds a unique span context.
        self._counter += 1
        return SpanContext(metadata={"id": self._counter, "kind": kind, "name": name})


class DoneRunner:
    """Runner that immediately returns the SDK internal isDone tool call."""

    def __init__(self, final_answer: str = "done") -> None:
        self._config = types.SimpleNamespace(provider="xai", model="grok-test")
        self.final_answer = final_answer

    def run(self, prompt: str, **kwargs: object) -> object:
        # Returns a minimal OpenAI-compatible tool-call response.
        raw = {"output": [{"type": "function_call", "name": "isDone", "arguments": f'{{"final_answer": "{self.final_answer}"}}'}]}
        return types.SimpleNamespace(text="", raw=raw, metadata={})


class EchoAgent:
    """Tiny agent-like object used for aggregate external proposer tests."""

    name = "echo"

    async def generate_reply(self, prompt: str) -> AgentMessage:
        # Returns an AgentMessage without supporting tracer mutation.
        return AgentMessage(sender="echo", recipient="orchestrator", content=f"echo:{prompt}")


class SemanticTraceProfileTests(unittest.TestCase):
    def test_profile_minimal_allows_only_core_spans(self) -> None:
        # Verifies minimal profile keeps only core agent, LLM, and tool spans.
        profile = TraceProfile.minimal()
        self.assertTrue(profile.allows(SpanSpec("agent.run", component="agents", detail=TraceDetail.MINIMAL)))
        self.assertTrue(profile.allows(SpanSpec("llm.call", kind=SpanKind.LLM, component="agents", detail=TraceDetail.MINIMAL)))
        self.assertTrue(profile.allows(SpanSpec("tool.call", kind=SpanKind.TOOL, component="tools", detail=TraceDetail.MINIMAL)))
        self.assertFalse(profile.allows(SpanSpec("runtime.iteration", component="runtimes", detail=TraceDetail.VERBOSE)))

    def test_profile_rejects_unknown_components_and_bad_values(self) -> None:
        # Verifies profile overrides fail loudly for unknown component names and values.
        with self.assertRaises(ConfigurationError):
            TraceProfile.default().with_components(nope="verbose")
        with self.assertRaises(ConfigurationError):
            TraceProfile.default().with_components(tools="chatty")
        with self.assertRaises(ConfigurationError):
            TraceProfile(max_chars=0)

    def test_profile_decisions_only_enables_middleware_decisions(self) -> None:
        # Verifies the middleware decisions_only preset includes decision spans.
        profile = TraceProfile.default().with_components(middleware="decisions_only")
        decision = SpanSpec("middleware.decision", component="middleware", detail=TraceDetail.VERBOSE)
        hook = SpanSpec("middleware.hook", component="middleware", detail=TraceDetail.DIAGNOSTIC)
        self.assertTrue(profile.allows(decision))
        self.assertFalse(profile.allows(hook))

    def test_registry_rejects_duplicate_and_unknown_specs(self) -> None:
        # Verifies component registry catches duplicate and missing span specs.
        registry = TraceComponentRegistry()
        spec = SpanSpec("agent.run")
        registry.register(spec)
        with self.assertRaises(ConfigurationError):
            registry.register(spec)
        with self.assertRaises(ConfigurationError):
            registry.get("missing")


class ProviderTranslatorTests(unittest.TestCase):
    def test_generic_translator_preserves_name_and_attributes(self) -> None:
        # Verifies generic provider translation is pass-through.
        payload = GenericProviderTranslator().translate_start(SpanSpec("x", attributes={"a": 1}))
        self.assertEqual(payload.name, "x")
        self.assertEqual(payload.attributes, {"a": 1})

    def test_langsmith_translator_maps_every_kind_to_run_type(self) -> None:
        # Verifies LangSmith run_type values for all semantic span kinds.
        translator = LangSmithProviderTranslator()
        for kind in SpanKind:
            payload = translator.translate_start(SpanSpec("span", kind=kind))
            self.assertEqual(payload.attributes["run_type"], kind.value)

    def test_langsmith_translator_does_not_mutate_attributes(self) -> None:
        # Verifies caller-owned attributes remain unchanged.
        attrs = {"input": "value"}
        translator = LangSmithProviderTranslator()
        translator.translate_start(SpanSpec("span", kind=SpanKind.LLM, attributes=attrs))
        self.assertEqual(attrs, {"input": "value"})


class TraceControllerTests(unittest.TestCase):
    def test_profile_wraps_debug_and_suppresses_verbose_spans_in_minimal(self) -> None:
        # Verifies suppressed spans do not reach the inner tracer.
        inner = RecordingTracer()
        tracer = Trace.profile(inner, TraceProfile.minimal())
        root = tracer.start_trace("agent.run")
        span = tracer.start_span("runtime.iteration", parent=root)
        tracer.end_span(span, output="hidden")
        tracer.end_trace(root, output="done")
        self.assertNotIn("runtime.iteration", [event.get("name") for event in inner.events])

    def test_verbose_profile_allows_runtime_iteration(self) -> None:
        # Verifies verbose spans are delegated when enabled.
        inner = RecordingTracer()
        tracer = Trace.profile(inner, TraceProfile.verbose())
        root = tracer.start_trace("agent.run")
        span = tracer.start_span("runtime.iteration", parent=root)
        tracer.end_span(span, output="shown")
        tracer.end_trace(root, output="done")
        self.assertIn("runtime.iteration", [event.get("name") for event in inner.events])

    def test_explicit_parent_beats_current_stack(self) -> None:
        # Verifies explicit parent contexts are passed through to the inner tracer.
        inner = RecordingTracer()
        tracer = Trace.profile(inner, TraceProfile.verbose())
        root = tracer.start_trace("agent.run")
        external_parent = SpanContext(metadata={"external": True})
        child = tracer.start_span("llm.call", parent=external_parent)
        tracer.end_span(child, output="ok")
        tracer.end_trace(root, output="done")
        llm_event = next(event for event in inner.events if event.get("name") == "llm.call")
        self.assertIs(llm_event["parent"], external_parent)

    def test_contextvars_isolate_concurrent_traces(self) -> None:
        # Verifies two async traces do not cross parent stacks.
        async def run_one(label: str) -> SpanContext:
            tracer = Trace.profile(inner, TraceProfile.verbose())
            root = tracer.start_trace(f"agent.run.{label}")
            await asyncio.sleep(0)
            child = tracer.start_span("llm.call")
            tracer.end_span(child, output=label)
            tracer.end_trace(root, output=label)
            return root.provider_context  # type: ignore[attr-defined]

        inner = RecordingTracer()
        roots = asyncio.run(asyncio.gather(run_one("a"), run_one("b"))) if False else asyncio.run(_gather(run_one("a"), run_one("b")))
        parents = [event["parent"] for event in inner.events if event.get("name") == "llm.call"]
        self.assertEqual(set(id(parent) for parent in parents), set(id(root) for root in roots))

    def test_nested_agent_run_becomes_child_span(self) -> None:
        # Verifies SDK-built nested agents can stay inside one semantic tree.
        inner = RecordingTracer()
        tracer = Trace.profile(inner, TraceProfile.verbose())
        root = tracer.start_trace("agent.run", agent_name="root")
        aggregate = tracer.start_span("aggregate.proposer", parent=root)
        child = tracer.start_trace("agent.run", agent_name="child")
        tracer.end_trace(child, output="child")
        tracer.end_span(aggregate, output="aggregate")
        tracer.end_trace(root, output="root")
        starts = [(event["type"], event.get("name")) for event in inner.events if event["type"].startswith("start")]
        self.assertEqual(starts, [("start_trace", "agent.run"), ("start_span", "aggregate.proposer"), ("start_span", "agent.run")])


async def _gather(*coroutines: Any) -> tuple[Any, ...]:
    # Runs coroutines through asyncio.gather for Python versions that reject direct gather in run().
    return tuple(await asyncio.gather(*coroutines))


class SessionTraceTests(unittest.TestCase):
    def test_session_maps_child_agent_run_to_span(self) -> None:
        # Verifies session roots contain child agent runs as spans.
        inner = RecordingTracer()
        tracer = Trace.session(inner, profile=TraceProfile.default())
        with tracer.session("workflow"):
            child = tracer.start_trace("agent.run", agent_name="a")
            tracer.end_trace(child, output="ok")
        start_types = [(event["type"], event.get("name")) for event in inner.events if event["type"].startswith("start")]
        self.assertEqual(start_types, [("start_trace", "workflow"), ("start_span", "agent.run")])

    def test_session_rejects_nested_active_session(self) -> None:
        # Verifies nested sessions on one controller fail loudly.
        tracer = Trace.session(RecordingTracer(), profile=TraceProfile.default())
        with tracer.session("workflow"):
            with self.assertRaises(ConfigurationError):
                tracer.begin_session("nested")

    def test_session_controller_without_active_session_closes_root_trace(self) -> None:
        # Verifies session-capable controllers still behave like normal tracers outside sessions.
        inner = RecordingTracer()
        tracer = Trace.session(inner, profile=TraceProfile.default())
        root = tracer.start_trace("agent.run", agent_name="solo")
        tracer.end_trace(root, output="ok")
        self.assertEqual([event["type"] for event in inner.events], ["start_trace", "end_trace"])


class SemanticRuntimeIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_default_profile_records_core_and_default_spans(self) -> None:
        # Verifies default semantic agent tracing emits core spans and parser/stop spans.
        events: list[dict[str, Any]] = []
        tracer = Trace.profile(Trace.debug(events), TraceProfile.default())
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=DoneRunner(), trace=tracer)
        await agent.generate_reply("hello")
        names = [event.get("name") for event in events if event["type"].startswith("start")]
        self.assertIn("agent.run", names)
        self.assertIn("llm.call", names)
        self.assertIn("tool.call", names)
        self.assertIn("parser.tool_calls", names)
        self.assertIn("agent.stop", names)
        self.assertNotIn("runtime.iteration", names)

    async def test_agent_verbose_profile_records_runtime_and_context_spans(self) -> None:
        # Verifies verbose profile adds runtime and context-window spans.
        events: list[dict[str, Any]] = []
        tracer = Trace.profile(Trace.debug(events), TraceProfile.verbose())
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=DoneRunner(), trace=tracer)
        await agent.generate_reply("hello")
        names = [event.get("name") for event in events if event["type"].startswith("start")]
        self.assertIn("runtime.iteration", names)
        self.assertIn("context.window.build", names)

    async def test_tool_call_attributes_include_arguments(self) -> None:
        # Verifies tool.call exposes tool name, input, and output-ready metadata.
        events: list[dict[str, Any]] = []
        tracer = Trace.profile(Trace.debug(events), TraceProfile.default())
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=DoneRunner(), trace=tracer)
        await agent.generate_reply("hello")
        tool_event = next(event for event in events if event.get("name") == "tool.call")
        self.assertEqual(tool_event["attributes"]["tool_name"], "isDone")
        self.assertEqual(tool_event["attributes"]["tool_input"], {"final_answer": "done"})

    async def test_aggregate_agent_propagates_tracer_to_sdk_children(self) -> None:
        # Verifies SDK-built aggregate children share the aggregate tracer.
        events: list[dict[str, Any]] = []
        tracer = Trace.profile(Trace.debug(events), TraceProfile.verbose())
        agent = AggregateAgent(
            name="agg",
            system_prompt="Synthesize.",
            proposers=[ProposerSpec("xai", "model-a"), ProposerSpec("xai", "model-b")],
            aggregator=ProposerSpec("xai", "model-c"),
            trace=tracer,
        )
        for _label, child in agent._engine._proposers:
            self.assertIs(child._tracer, tracer)
        self.assertIs(agent._engine._aggregator._tracer, tracer)

    async def test_aggregate_external_agent_like_objects_are_not_mutated(self) -> None:
        # Verifies external proposer objects are not assigned tracer state.
        proposer = EchoAgent()
        aggregator = EchoAgent()
        agent = AggregateAgent(name="agg", system_prompt="Synthesize.", proposers=[proposer], aggregator=aggregator, trace=Trace.profile(Trace.debug([]), TraceProfile.verbose()))
        await agent.generate_reply("hello")
        self.assertFalse(hasattr(proposer, "_tracer"))


class LangSmithFacadeTests(unittest.TestCase):
    def test_langsmith_default_wraps_langsmith_with_translator(self) -> None:
        # Verifies LangSmith default helper returns a semantic controller.
        calls: list[dict[str, Any]] = []

        class FakeLangSmithTracer(RecordingTracer):
            def __init__(self, **kwargs: Any) -> None:
                calls.append(dict(kwargs))
                super().__init__()

        with patch("vidbyte.providers.tracing.LangSmithTracer", FakeLangSmithTracer):
            tracer = Trace.langsmith_default(api_key="key", project="project", endpoint="endpoint", strict=True, include_runtime_info=True)
        self.assertIsInstance(tracer, TraceController)
        self.assertEqual(tracer.translator.provider, "langsmith")
        self.assertEqual(calls[0]["project"], "project")


if __name__ == "__main__":
    unittest.main()
