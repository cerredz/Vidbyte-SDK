from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from vidbyte import Trace as RootTrace
from vidbyte.lib.errors import ConfigurationError, TracerConfigurationError
from vidbyte.lib.tracing import NullTracer, SpanContext, TracerBase
from vidbyte.trace import ContinualTracer, DebugTracer, Trace


class RecordingTracer(TracerBase):
    """Minimal tracer used to verify Trace.custom behavior."""

    def start_trace(self, name: str, **attributes: Any) -> SpanContext:
        # Returns a context proving the tracer was invoked.
        return SpanContext(metadata={"name": name, "attributes": dict(attributes)})

    def end_trace(self, context: SpanContext, *, output: str | None = None, error: Exception | None = None) -> None:
        # Accepts trace completion calls without side effects.
        return None

    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SpanContext:
        # Returns a context proving span creation was invoked.
        return SpanContext(metadata={"name": name, "parent": parent, "attributes": dict(attributes)})

    def end_span(self, context: SpanContext, *, output: str | None = None, error: Exception | None = None) -> None:
        # Accepts span completion calls without side effects.
        return None


class CallableNotTracer:
    """Callable object that should still be rejected by Trace.custom."""

    def __call__(self) -> object:
        # Returns a non-tracer to catch callable-shape false positives.
        return object()


class TraceFacadeTests(unittest.TestCase):
    def test_off_returns_null_tracer(self) -> None:
        # Verifies the disabled tracing preset maps to the existing no-op tracer.
        tracer = Trace.off()
        self.assertIsInstance(tracer, NullTracer)
        ctx = tracer.start_trace("agent.run")
        tracer.end_trace(ctx)

    def test_debug_records_ordered_events_and_parent_linkage(self) -> None:
        # Verifies debug tracing captures ordered lifecycle records and parent spans.
        events: list[dict[str, Any]] = []
        tracer = Trace.debug(events)
        root = tracer.start_trace("agent.run", agent_name="agent")
        span = tracer.start_span("llm.call", parent=root, iteration=1)
        tracer.end_span(span, output="ok")
        tracer.end_trace(root, output="done")
        self.assertEqual([event["type"] for event in events], ["start_trace", "start_span", "end_span", "end_trace"])
        self.assertIs(events[1]["parent"], root)
        self.assertEqual(events[0]["attributes"]["agent_name"], "agent")

    def test_debug_owns_event_list_when_none_is_supplied(self) -> None:
        # Verifies Trace.debug creates usable internal event storage by default.
        tracer = Trace.debug()
        root = tracer.start_trace("agent.run")
        tracer.end_trace(root)
        self.assertEqual(len(tracer.events), 2)

    def test_debug_records_error_text_without_raising(self) -> None:
        # Verifies end calls store error text instead of propagating event errors.
        tracer = Trace.debug()
        span = tracer.start_span("tool.call")
        tracer.end_span(span, error=RuntimeError("boom"))
        root = tracer.start_trace("agent.run")
        tracer.end_trace(root, error=ValueError("bad"))
        self.assertEqual(tracer.events[1]["error"], "boom")
        self.assertEqual(tracer.events[3]["error"], "bad")

    def test_custom_accepts_instance_and_class(self) -> None:
        # Verifies Trace.custom supports both existing tracer instances and classes.
        instance = RecordingTracer()
        self.assertIs(Trace.custom(instance), instance)
        self.assertIsInstance(Trace.custom(RecordingTracer), RecordingTracer)

    def test_custom_rejects_invalid_values(self) -> None:
        # Verifies invalid custom tracer values fail at construction time.
        with self.assertRaises(ConfigurationError):
            Trace.custom(None)  # type: ignore[arg-type]
        with self.assertRaises(ConfigurationError):
            Trace.custom(CallableNotTracer())  # type: ignore[arg-type]

    def test_continual_validates_remember_and_memory_budget(self) -> None:
        # Verifies continual tracing rejects empty, string, unsupported, and invalid budget inputs.
        invalid_inputs = ((), "tool_calls", ("bad",))
        for remember in invalid_inputs:
            with self.assertRaises(ConfigurationError):
                Trace.continual(remember)  # type: ignore[arg-type]
        for value in (0, -1, 1.5, True):
            with self.assertRaises(ConfigurationError):
                Trace.continual(["tool_calls"], max_memory_chars=value)  # type: ignore[arg-type]

    def test_continual_stores_settings_and_deduplicates_remember(self) -> None:
        # Verifies continual tracing stores normalized settings exactly.
        tracer = Trace.continual(["tool_calls", "failures", "tool_calls"], max_memory_chars=500, redact=False)
        self.assertIsInstance(tracer, ContinualTracer)
        self.assertEqual(tracer.remember, ("tool_calls", "failures"))
        self.assertEqual(tracer.max_memory_chars, 500)
        self.assertFalse(tracer.redact)

    def test_continual_records_debug_lifecycle_events(self) -> None:
        # Verifies continual tracing currently records events like DebugTracer.
        tracer = Trace.continual(["tool_calls"])
        root = tracer.start_trace("agent.run")
        tracer.end_trace(root, output="done")
        self.assertEqual([event["type"] for event in tracer.events], ["start_trace", "end_trace"])

    def test_provider_helpers_forward_arguments(self) -> None:
        # Verifies provider helpers delegate to existing provider adapter constructors.
        langfuse_calls: list[dict[str, Any]] = []
        langsmith_calls: list[dict[str, Any]] = []
        phoenix_calls: list[dict[str, Any]] = []

        class FakeLangfuseTracer(RecordingTracer):
            def __init__(self, *, public_key: str | None = None, secret_key: str | None = None, host: str | None = None) -> None:
                # Captures forwarded Langfuse constructor arguments.
                langfuse_calls.append({"public_key": public_key, "secret_key": secret_key, "host": host})

        class FakeLangSmithTracer(RecordingTracer):
            def __init__(self, *, api_key: str | None = None, project: str | None = None) -> None:
                # Captures forwarded LangSmith constructor arguments.
                langsmith_calls.append({"api_key": api_key, "project": project})

        class FakePhoenixTracer(RecordingTracer):
            def __init__(self, *, endpoint: str | None = None) -> None:
                # Captures forwarded Phoenix constructor arguments.
                phoenix_calls.append({"endpoint": endpoint})

        with patch("vidbyte.providers.tracing.LangfuseTracer", FakeLangfuseTracer):
            self.assertIsInstance(Trace.langfuse(public_key="pk", secret_key="sk", host="host"), FakeLangfuseTracer)
        with patch("vidbyte.providers.tracing.LangSmithTracer", FakeLangSmithTracer):
            self.assertIsInstance(Trace.langsmith(api_key="key", project="project"), FakeLangSmithTracer)
        with patch("vidbyte.providers.tracing.PhoenixTracer", FakePhoenixTracer):
            self.assertIsInstance(Trace.phoenix(endpoint="endpoint"), FakePhoenixTracer)
        self.assertEqual(langfuse_calls[0], {"public_key": "pk", "secret_key": "sk", "host": "host"})
        self.assertEqual(langsmith_calls[0], {"api_key": "key", "project": "project"})
        self.assertEqual(phoenix_calls[0], {"endpoint": "endpoint"})

    def test_provider_helpers_propagate_configuration_errors(self) -> None:
        # Verifies provider construction failures are not swallowed by facade helpers.
        class FailingLangfuseTracer(RecordingTracer):
            def __init__(self, **_: Any) -> None:
                # Raises the existing tracing configuration error.
                raise TracerConfigurationError("missing")

        with patch("vidbyte.providers.tracing.LangfuseTracer", FailingLangfuseTracer):
            with self.assertRaises(TracerConfigurationError):
                Trace.langfuse(public_key="pk", secret_key="sk")

    def test_root_and_package_exports(self) -> None:
        # Verifies root and package exports point at the same public classes.
        import vidbyte.trace as trace_package
        self.assertIs(RootTrace, Trace)
        self.assertIn("Trace", trace_package.__all__)
        self.assertIn("DebugTracer", trace_package.__all__)
        self.assertIn("ContinualTracer", trace_package.__all__)

    def test_tracer_implementations_live_in_dedicated_modules(self) -> None:
        # Verifies base.py stays the facade while implementations live in split modules.
        from vidbyte.trace.continual import ContinualTracer as ContinualModuleTracer
        from vidbyte.trace.debug import DebugTracer as DebugModuleTracer

        self.assertIs(DebugTracer, DebugModuleTracer)
        self.assertIs(ContinualTracer, ContinualModuleTracer)


if __name__ == "__main__":
    unittest.main()
