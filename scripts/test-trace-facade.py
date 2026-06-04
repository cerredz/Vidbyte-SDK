from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vidbyte import Agent, Trace as RootTrace
from vidbyte.lib.errors import ConfigurationError, TracerConfigurationError
from vidbyte.lib.tracing import NullTracer, SpanContext, TracerBase
from vidbyte.trace import ContinualTracer, DebugTracer, Trace


class RecordingTracer(TracerBase):
    """Small concrete tracer used by script test cases."""

    def start_trace(self, name: str, **attributes: Any) -> SpanContext:
        # Returns an identifiable trace context.
        return SpanContext(metadata={"name": name, "attributes": dict(attributes)})

    def end_trace(self, context: SpanContext, *, output: str | None = None, error: Exception | None = None) -> None:
        # Accepts trace completion without side effects.
        return None

    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SpanContext:
        # Returns an identifiable span context.
        return SpanContext(metadata={"name": name, "parent": parent, "attributes": dict(attributes)})

    def end_span(self, context: SpanContext, *, output: str | None = None, error: Exception | None = None) -> None:
        # Accepts span completion without side effects.
        return None


class CallableNotTracer:
    """Callable object that must not pass custom tracer validation."""

    def __call__(self) -> object:
        # Returns a non-tracer object to catch callable false positives.
        return object()


class FakeResponse:
    """Provider-like response object for agent integration checks."""

    def __init__(self, text: str, raw: dict[str, Any] | None = None) -> None:
        # Stores text and raw tool-call payloads for BaseAgent runtime parsing.
        self.text = text
        self.raw = raw or {}


class AlwaysDoneRunner:
    """Runner that immediately calls the internal isDone tool."""

    def run(self, prompt: str, **kwargs: object) -> FakeResponse:
        # Returns a minimal provider-like isDone tool-call response.
        return FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}'}]})


class FailingLangfuseTracer(RecordingTracer):
    """Fake provider tracer that raises the existing configuration error."""

    def __init__(self, **_: Any) -> None:
        # Simulates provider adapter construction failure.
        raise TracerConfigurationError("missing")


def assert_raises(expected: type[BaseException], callback: Callable[[], object]) -> None:
    # Executes callback and asserts that it raises the expected exception type.
    try:
        callback()
    except expected:
        return
    except Exception as exc:
        raise AssertionError(f"Expected {expected.__name__}, got {type(exc).__name__}") from exc
    raise AssertionError(f"Expected {expected.__name__} to be raised.")


def case_trace_off_returns_null_tracer() -> None:
    # [Edge Case] Trace.off returns NullTracer and accepts trace lifecycle calls.
    tracer = Trace.off()
    assert isinstance(tracer, NullTracer)
    ctx = tracer.start_trace("agent.run")
    tracer.end_trace(ctx)


def case_debug_owns_event_list() -> None:
    # [Edge Case] Trace.debug creates internal event storage when no list is supplied.
    tracer = Trace.debug()
    root = tracer.start_trace("agent.run")
    tracer.end_trace(root)
    assert len(tracer.events) == 2


def case_debug_uses_supplied_event_list() -> None:
    # [Edge Case] Trace.debug appends lifecycle records into a caller-supplied list.
    events: list[dict[str, Any]] = []
    tracer = Trace.debug(events)
    root = tracer.start_trace("agent.run")
    tracer.end_trace(root)
    assert events is tracer.events
    assert len(events) == 2


def case_debug_records_event_order() -> None:
    # [Silent Failure] DebugTracer records lifecycle events in the expected order.
    events: list[dict[str, Any]] = []
    tracer = Trace.debug(events)
    root = tracer.start_trace("agent.run")
    span = tracer.start_span("llm.call", parent=root)
    tracer.end_span(span)
    tracer.end_trace(root)
    assert [event["type"] for event in events] == ["start_trace", "start_span", "end_span", "end_trace"]


def case_debug_records_parent_context() -> None:
    # [Silent Failure] DebugTracer keeps parent linkage on started spans.
    tracer = Trace.debug()
    root = tracer.start_trace("agent.run")
    tracer.start_span("tool.call", parent=root)
    assert tracer.events[1]["parent"] is root


def case_debug_records_errors_without_raising() -> None:
    # [Hidden Failure] DebugTracer stores error text on end calls without raising.
    tracer = Trace.debug()
    span = tracer.start_span("tool.call")
    tracer.end_span(span, error=RuntimeError("boom"))
    root = tracer.start_trace("agent.run")
    tracer.end_trace(root, error=ValueError("bad"))
    assert tracer.events[1]["error"] == "boom"
    assert tracer.events[3]["error"] == "bad"


def case_custom_accepts_instance() -> None:
    # [Hidden Assumption] Trace.custom accepts TracerBase instances.
    tracer = RecordingTracer()
    assert Trace.custom(tracer) is tracer


def case_custom_accepts_class() -> None:
    # [Hidden Assumption] Trace.custom accepts TracerBase classes.
    assert isinstance(Trace.custom(RecordingTracer), RecordingTracer)


def case_custom_rejects_none() -> None:
    # [Edge Case] Trace.custom rejects None.
    assert_raises(ConfigurationError, lambda: Trace.custom(None))  # type: ignore[arg-type]


def case_custom_rejects_callable_non_tracer() -> None:
    # [Hidden Failure] Trace.custom rejects callable objects that are not tracers.
    assert_raises(ConfigurationError, lambda: Trace.custom(CallableNotTracer()))  # type: ignore[arg-type]


def case_continual_rejects_empty_remember() -> None:
    # [Edge Case] Trace.continual rejects empty remember sequences.
    assert_raises(ConfigurationError, lambda: Trace.continual(()))


def case_continual_rejects_raw_string() -> None:
    # [Hidden Assumption] Trace.continual rejects ambiguous raw strings.
    assert_raises(ConfigurationError, lambda: Trace.continual("tool_calls"))  # type: ignore[arg-type]


def case_continual_deduplicates_remember() -> None:
    # [Silent Failure] Trace.continual deduplicates remember values while preserving order.
    tracer = Trace.continual(["tool_calls", "failures", "tool_calls"])
    assert tracer.remember == ("tool_calls", "failures")


def case_continual_rejects_unsupported_remember() -> None:
    # [Edge Case] Trace.continual rejects unsupported memory categories.
    assert_raises(ConfigurationError, lambda: Trace.continual(["unsupported"]))


def case_continual_rejects_zero_budget() -> None:
    # [Edge Case] Trace.continual rejects zero max_memory_chars.
    assert_raises(ConfigurationError, lambda: Trace.continual(["tool_calls"], max_memory_chars=0))


def case_continual_rejects_negative_budget() -> None:
    # [Edge Case] Trace.continual rejects negative max_memory_chars.
    assert_raises(ConfigurationError, lambda: Trace.continual(["tool_calls"], max_memory_chars=-1))


def case_continual_rejects_non_integer_budget() -> None:
    # [Hidden Assumption] Trace.continual rejects non-integer max_memory_chars.
    assert_raises(ConfigurationError, lambda: Trace.continual(["tool_calls"], max_memory_chars=1.5))  # type: ignore[arg-type]


def case_continual_stores_settings() -> None:
    # [Silent Failure] Trace.continual stores remember, max_memory_chars, and redact settings.
    tracer = Trace.continual(["outputs"], max_memory_chars=500, redact=False)
    assert isinstance(tracer, ContinualTracer)
    assert tracer.remember == ("outputs",)
    assert tracer.max_memory_chars == 500
    assert tracer.redact is False


def case_continual_records_lifecycle_events() -> None:
    # [Silent Failure] ContinualTracer records lifecycle events like DebugTracer.
    tracer = Trace.continual(["tool_calls"])
    root = tracer.start_trace("agent.run")
    tracer.end_trace(root, output="done")
    assert [event["type"] for event in tracer.events] == ["start_trace", "end_trace"]


def case_langfuse_forwards_arguments() -> None:
    # [Hidden Failure] Trace.langfuse forwards public_key, secret_key, and host.
    calls: list[dict[str, Any]] = []

    class FakeLangfuseTracer(RecordingTracer):
        def __init__(self, *, public_key: str | None = None, secret_key: str | None = None, host: str | None = None) -> None:
            # Captures forwarded Langfuse arguments.
            calls.append({"public_key": public_key, "secret_key": secret_key, "host": host})

    with patch("vidbyte.providers.tracing.LangfuseTracer", FakeLangfuseTracer):
        Trace.langfuse(public_key="pk", secret_key="sk", host="host")
    assert calls[0] == {"public_key": "pk", "secret_key": "sk", "host": "host"}


def case_langsmith_forwards_arguments() -> None:
    # [Hidden Failure] Trace.langsmith forwards api_key and project.
    calls: list[dict[str, Any]] = []

    class FakeLangSmithTracer(RecordingTracer):
        def __init__(self, *, api_key: str | None = None, project: str | None = None) -> None:
            # Captures forwarded LangSmith arguments.
            calls.append({"api_key": api_key, "project": project})

    with patch("vidbyte.providers.tracing.LangSmithTracer", FakeLangSmithTracer):
        Trace.langsmith(api_key="key", project="project")
    assert calls[0] == {"api_key": "key", "project": "project"}


def case_phoenix_forwards_arguments() -> None:
    # [Hidden Failure] Trace.phoenix forwards endpoint.
    calls: list[dict[str, Any]] = []

    class FakePhoenixTracer(RecordingTracer):
        def __init__(self, *, endpoint: str | None = None) -> None:
            # Captures forwarded Phoenix arguments.
            calls.append({"endpoint": endpoint})

    with patch("vidbyte.providers.tracing.PhoenixTracer", FakePhoenixTracer):
        Trace.phoenix(endpoint="endpoint")
    assert calls[0] == {"endpoint": "endpoint"}


def case_provider_helpers_propagate_errors() -> None:
    # [Hidden Assumption] Provider helper construction errors remain visible.
    with patch("vidbyte.providers.tracing.LangfuseTracer", FailingLangfuseTracer):
        assert_raises(TracerConfigurationError, lambda: Trace.langfuse(public_key="pk", secret_key="sk"))


def case_root_export_matches_package_export() -> None:
    # [Silent Failure] Root Trace export points at the package Trace class.
    assert RootTrace is Trace


def case_package_all_exports_public_names() -> None:
    # [Silent Failure] vidbyte.trace exports the expected public names.
    import vidbyte.trace as trace_package
    assert "Trace" in trace_package.__all__
    assert "DebugTracer" in trace_package.__all__
    assert "ContinualTracer" in trace_package.__all__


def case_tracer_implementations_live_in_dedicated_modules() -> None:
    # [Silent Failure] implementation tracers live outside the Trace tracer client module.
    from vidbyte.trace.continual import ContinualTracer as ContinualModuleTracer
    from vidbyte.trace.debug import DebugTracer as DebugModuleTracer

    assert DebugTracer is DebugModuleTracer
    assert ContinualTracer is ContinualModuleTracer


def case_agent_trace_off_stores_null_tracer() -> None:
    # [Edge Case] BaseAgent stores NullTracer when trace=Trace.off() is supplied.
    agent = Agent(name="test-agent", system_prompt="Be helpful.", runner=AlwaysDoneRunner(), trace=Trace.off())
    assert isinstance(agent._tracer, NullTracer)


def case_agent_trace_class_instantiates() -> None:
    # [Hidden Assumption] BaseAgent trace= accepts tracer classes.
    agent = Agent(name="test-agent", system_prompt="Be helpful.", runner=AlwaysDoneRunner(), trace=RecordingTracer)
    assert isinstance(agent._tracer, RecordingTracer)


def case_agent_trace_instance_used_directly() -> None:
    # [Hidden Assumption] BaseAgent trace= accepts tracer instances.
    tracer = RecordingTracer()
    agent = Agent(name="test-agent", system_prompt="Be helpful.", runner=AlwaysDoneRunner(), trace=tracer)
    assert agent._tracer is tracer


def case_agent_rejects_trace_and_tracer() -> None:
    # [Edge Case] BaseAgent rejects simultaneous trace= and tracer=.
    assert_raises(ConfigurationError, lambda: Agent(name="test-agent", system_prompt="Be helpful.", runner=AlwaysDoneRunner(), trace=Trace.off(), tracer=RecordingTracer()))


def case_agent_fork_preserves_trace_alias_tracer() -> None:
    # [Silent Failure] BaseAgent.fork preserves the resolved trace alias tracer.
    tracer = RecordingTracer()
    parent = Agent(name="test-agent", system_prompt="Be helpful.", runner=AlwaysDoneRunner(), trace=tracer)
    child = parent.fork(name="child-agent")
    assert child._tracer is tracer


def case_existing_tracer_behavior_still_works() -> None:
    # [Hidden Failure] Existing tracer= behavior still uses caller instances directly.
    tracer = RecordingTracer()
    agent = Agent(name="test-agent", system_prompt="Be helpful.", runner=AlwaysDoneRunner(), tracer=tracer)
    assert agent._tracer is tracer


def case_debug_agent_run_records_runtime_events() -> None:
    # [Hidden Failure] Agent runs with Trace.debug record root and runtime span events.
    events: list[dict[str, Any]] = []
    agent = Agent(name="debug-agent", system_prompt="Be helpful.", runner=AlwaysDoneRunner(), trace=Trace.debug(events))
    reply = agent.run("hello")
    event_types = [event["type"] for event in events]
    assert reply.content == "done"
    assert "start_trace" in event_types
    assert "start_span" in event_types
    assert "end_span" in event_types
    assert "end_trace" in event_types


def case_continual_agent_run_records_settings_and_events() -> None:
    # [Silent Failure] Agent runs with Trace.continual keep settings and lifecycle events.
    tracer = Trace.continual(["tool_calls"], max_memory_chars=500)
    agent = Agent(name="continual-agent", system_prompt="Be helpful.", runner=AlwaysDoneRunner(), trace=tracer)
    reply = agent.run("hello")
    assert reply.content == "done"
    assert tracer.remember == ("tool_calls",)
    assert tracer.max_memory_chars == 500
    assert tracer.events


def case_provider_patch_does_not_require_optional_sdks() -> None:
    # [Hidden Assumption] Patched provider helpers do not require real optional SDK imports.
    class FakeLangfuseTracer(RecordingTracer):
        def __init__(self, **_: Any) -> None:
            # Accepts any patched provider arguments without optional dependencies.
            return None

    with patch("vidbyte.providers.tracing.LangfuseTracer", FakeLangfuseTracer):
        assert isinstance(Trace.langfuse(public_key="pk", secret_key="sk"), FakeLangfuseTracer)


CASES: list[tuple[str, Callable[[], None]]] = [
    ("Trace.off returns NullTracer", case_trace_off_returns_null_tracer),
    ("Trace.debug owns event list", case_debug_owns_event_list),
    ("Trace.debug uses supplied event list", case_debug_uses_supplied_event_list),
    ("DebugTracer records event order", case_debug_records_event_order),
    ("DebugTracer records parent context", case_debug_records_parent_context),
    ("DebugTracer records errors without raising", case_debug_records_errors_without_raising),
    ("Trace.custom accepts instance", case_custom_accepts_instance),
    ("Trace.custom accepts class", case_custom_accepts_class),
    ("Trace.custom rejects None", case_custom_rejects_none),
    ("Trace.custom rejects callable non-tracer", case_custom_rejects_callable_non_tracer),
    ("Trace.continual rejects empty remember", case_continual_rejects_empty_remember),
    ("Trace.continual rejects raw string", case_continual_rejects_raw_string),
    ("Trace.continual deduplicates remember", case_continual_deduplicates_remember),
    ("Trace.continual rejects unsupported remember", case_continual_rejects_unsupported_remember),
    ("Trace.continual rejects zero budget", case_continual_rejects_zero_budget),
    ("Trace.continual rejects negative budget", case_continual_rejects_negative_budget),
    ("Trace.continual rejects non-integer budget", case_continual_rejects_non_integer_budget),
    ("Trace.continual stores settings", case_continual_stores_settings),
    ("Trace.continual records lifecycle events", case_continual_records_lifecycle_events),
    ("Trace.langfuse forwards arguments", case_langfuse_forwards_arguments),
    ("Trace.langsmith forwards arguments", case_langsmith_forwards_arguments),
    ("Trace.phoenix forwards arguments", case_phoenix_forwards_arguments),
    ("Provider helpers propagate errors", case_provider_helpers_propagate_errors),
    ("Root Trace export matches package export", case_root_export_matches_package_export),
    ("Package __all__ exports public names", case_package_all_exports_public_names),
    ("Tracer implementations live in dedicated modules", case_tracer_implementations_live_in_dedicated_modules),
    ("BaseAgent trace off stores NullTracer", case_agent_trace_off_stores_null_tracer),
    ("BaseAgent trace class instantiates", case_agent_trace_class_instantiates),
    ("BaseAgent trace instance used directly", case_agent_trace_instance_used_directly),
    ("BaseAgent rejects trace and tracer", case_agent_rejects_trace_and_tracer),
    ("BaseAgent fork preserves trace alias tracer", case_agent_fork_preserves_trace_alias_tracer),
    ("Existing tracer behavior still works", case_existing_tracer_behavior_still_works),
    ("Debug agent run records runtime events", case_debug_agent_run_records_runtime_events),
    ("Continual agent run records settings and events", case_continual_agent_run_records_settings_and_events),
    ("Provider patch avoids optional SDK requirements", case_provider_patch_does_not_require_optional_sdks),
]


def main() -> int:
    # Runs every verification case and prints a compact PASS/FAIL summary.
    passed = 0
    for name, case in CASES:
        try:
            case()
        except Exception as exc:
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"PASS {name}")
    print(f"{passed}/{len(CASES)} tests passed")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
