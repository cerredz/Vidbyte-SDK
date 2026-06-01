"""Executable verification script for the context window template system.

Runs every scenario from the design doc testing plan and prints PASS/FAIL
per test. Exits with code 1 if any test fails.

Usage:
    python scripts/test-context-window-templates.py
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from vidbyte.agents.runtime import AgentRuntime
from vidbyte.context.algorithms import ReflexionAlgorithm
from vidbyte.context.algorithms.tool_results import ContextWindowAlgorithm
from vidbyte.context.templates import ContextWindowRecorder, NullRecorder, SlotEvent
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.templates import ContextWindowTemplate, ReflexionContextWindowTemplate, TemplateViolation
from vidbyte.strategies.types import BaseAgentContext
from vidbyte.tools import Tools
from vidbyte.tools.security import PermissionPolicy


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

_results: list[tuple[str, bool, str]] = []


def _report(name: str, passed: bool, detail: str = "") -> None:
    _results.append((name, passed, detail))
    status = "PASS" if passed else "FAIL"
    suffix = f" — {detail}" if detail and not passed else ""
    print(f"  [{status}] {name}{suffix}")


def _assert(name: str, condition: bool, detail: str = "") -> None:
    _report(name, condition, detail)


# ---------------------------------------------------------------------------
# Fake runner helpers
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, text: str, raw: dict | None = None) -> None:
        self.text = text
        self.raw = raw or {}


class FakeRunner:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)


async def _invoke_runner(runner: FakeRunner, prompt: str, **kwargs: Any) -> FakeResponse:
    return runner.responses.pop(0)


def _output_text(r: object) -> str:
    return str(getattr(r, "text", r))


def _output_metadata(r: object) -> dict:
    return {}


def _is_done() -> FakeResponse:
    return FakeResponse(
        "",
        {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}'}]},
    )


def _fails() -> FakeResponse:
    return FakeResponse("Could not finish.", {})


def _reflects() -> FakeResponse:
    return FakeResponse("I should try differently.", {})


def _base_context() -> BaseAgentContext:
    return BaseAgentContext(system_prompt="sys", history=(), file_paths=(), tools=(), budget=None)


def _make_reflexion_runtime(recorder: ContextWindowRecorder, max_trials: int) -> AgentRuntime:
    algorithm = ContextWindowAlgorithm(
        name="reflexion",
        reflexion=ReflexionAlgorithm(max_trials=max_trials),
    )
    return AgentRuntime(
        agent_name="test-agent",
        system_prompt="Work.",
        tools=Tools(),
        permission_policy=PermissionPolicy(),
        config=AgentRuntimeConfig(max_iterations=1),
        algorithm=algorithm,
        recorder=recorder,
    )


# ---------------------------------------------------------------------------
# Section 1: SlotEvent tests
# ---------------------------------------------------------------------------

def test_slot_event() -> None:
    print("\n[SlotEvent]")
    event = SlotEvent(slot_type="system_prompt", iteration=2, metadata={"k": "v"})
    _assert("stores slot_type", event.slot_type == "system_prompt")
    _assert("stores iteration", event.iteration == 2)
    _assert("stores metadata", event.metadata == {"k": "v"})
    try:
        event.slot_type = "mutated"  # type: ignore[misc]
        _assert("is frozen", False, "mutation did not raise")
    except (AttributeError, TypeError):
        _assert("is frozen", True)


# ---------------------------------------------------------------------------
# Section 2: ContextWindowRecorder tests
# ---------------------------------------------------------------------------

def test_recorder() -> None:
    print("\n[ContextWindowRecorder]")
    rec = ContextWindowRecorder()
    _assert("starts empty", rec.slots() == ())

    rec.append("A")
    rec.append("B")
    rec.append("C")
    _assert("insertion order preserved", rec.slots() == ("A", "B", "C"))

    rec2 = ContextWindowRecorder()
    rec2.append("x", iteration=5, extra_key="extra_val")
    events = rec2.events()
    _assert("events returns SlotEvent instances", isinstance(events[0], SlotEvent))
    _assert("iteration stored", events[0].iteration == 5)
    _assert("extra metadata stored", events[0].metadata.get("extra_key") == "extra_val")

    rec3 = ContextWindowRecorder()
    rec3.append("A", iteration=0, key=1)
    rec3.append("B", iteration=1, key=2)
    e = rec3.events()
    _assert("metadata not shared across events", e[0].metadata["key"] == 1 and e[1].metadata["key"] == 2)

    rec4 = ContextWindowRecorder()
    rec4.append("X")
    rec4.reset()
    _assert("reset clears events", rec4.slots() == ())


# ---------------------------------------------------------------------------
# Section 3: NullRecorder tests
# ---------------------------------------------------------------------------

def test_null_recorder() -> None:
    print("\n[NullRecorder]")
    null = NullRecorder()
    try:
        null.append("any_slot", iteration=0)
        _assert("append does not raise", True)
    except Exception as exc:
        _assert("append does not raise", False, str(exc))
    _assert("slots always empty", null.slots() == ())

    for _ in range(100):
        null.append("slot")
    _assert("slots empty after many appends", null.slots() == ())


# ---------------------------------------------------------------------------
# Section 4: ContextWindowTemplate tests
# ---------------------------------------------------------------------------

def _rec(*slots: str) -> ContextWindowRecorder:
    r = ContextWindowRecorder()
    for s in slots:
        r.append(s)
    return r


def test_template() -> None:
    print("\n[ContextWindowTemplate]")
    t = ContextWindowTemplate(["A", "B", "C"])
    _assert("expected_slots stored", t.expected_slots == ("A", "B", "C"))

    _assert("exact match -> no violations", t.validate(_rec("A", "B", "C")) == [])
    _assert("exact match -> passes", t.passes(_rec("A", "B", "C")))

    violations = t.validate(_rec("A", "X", "C"))
    _assert("mismatch at position 1 reported", len(violations) == 1 and violations[0].position == 1)
    _assert("mismatch expected correct", violations[0].expected == "B")
    _assert("mismatch actual correct", violations[0].actual == "X")

    short = t.validate(_rec("A"))
    _assert("trace-ended-early -> violations with None actual", all(v.actual is None for v in short[0:]))
    _assert("trace-ended-early -> 2 violations", len(short) == 2)

    long_ = ContextWindowTemplate(["A"]).validate(_rec("A", "B", "C"))
    _assert("extra slots -> violations with expected=<end>", all(v.expected == "<end>" for v in long_))
    _assert("extra slots -> 2 violations", len(long_) == 2)

    _assert("empty vs empty -> no violations", ContextWindowTemplate([]).validate(ContextWindowRecorder()) == [])
    _assert("passes returns False on violation", not t.passes(_rec("A", "X", "C")))


# ---------------------------------------------------------------------------
# Section 5: TemplateViolation tests
# ---------------------------------------------------------------------------

def test_violation() -> None:
    print("\n[TemplateViolation]")
    v = TemplateViolation(position=3, expected="A", actual=None, message="ended")
    _assert("stores none actual", v.actual is None)
    _assert("stores position", v.position == 3)
    try:
        v.position = 99  # type: ignore[misc]
        _assert("is frozen", False, "mutation did not raise")
    except (AttributeError, TypeError):
        _assert("is frozen", True)


# ---------------------------------------------------------------------------
# Section 6: ReflexionContextWindowTemplate tests
# ---------------------------------------------------------------------------

def test_reflexion_template() -> None:
    print("\n[ReflexionContextWindowTemplate]")
    t1 = ReflexionContextWindowTemplate(max_trials=1, failing_trials=0)
    _assert("1 trial 0 failures", t1.expected_slots == ("system_prompt", "reflexion_trial"))

    t2 = ReflexionContextWindowTemplate(max_trials=2, failing_trials=1)
    _assert(
        "2 trials 1 failure",
        t2.expected_slots == ("system_prompt", "reflexion_trial", "reflexion_reflection", "reflexion_trial"),
    )

    t3 = ReflexionContextWindowTemplate(max_trials=3)
    _assert(
        "3 trials default (2 failures)",
        t3.expected_slots == (
            "system_prompt",
            "reflexion_trial", "reflexion_reflection",
            "reflexion_trial", "reflexion_reflection",
            "reflexion_trial",
        ),
    )

    t_default = ReflexionContextWindowTemplate(max_trials=3)
    t_explicit = ReflexionContextWindowTemplate(max_trials=3, failing_trials=2)
    _assert("default failing_trials = max_trials - 1", t_default.expected_slots == t_explicit.expected_slots)

    t_zero = ReflexionContextWindowTemplate(max_trials=3, failing_trials=0)
    _assert(
        "zero failing trials -> system_prompt + one trial only",
        t_zero.expected_slots == ("system_prompt", "reflexion_trial"),
    )


# ---------------------------------------------------------------------------
# Section 7: AgentRuntime recorder param tests
# ---------------------------------------------------------------------------

def test_runtime_recorder_param() -> None:
    print("\n[AgentRuntime recorder param]")
    runtime_default = AgentRuntime(
        agent_name="a", system_prompt="s", tools=Tools(), permission_policy=PermissionPolicy()
    )
    _assert("defaults to NullRecorder", isinstance(runtime_default.recorder, NullRecorder))

    rec = ContextWindowRecorder()
    runtime_with = AgentRuntime(
        agent_name="a", system_prompt="s", tools=Tools(), permission_policy=PermissionPolicy(), recorder=rec
    )
    _assert("stores passed recorder instance", runtime_with.recorder is rec)


# ---------------------------------------------------------------------------
# Section 8: Reflexion instrumentation tests (async)
# ---------------------------------------------------------------------------

async def test_reflexion_instrumentation() -> None:
    print("\n[Reflexion instrumentation]")

    # system_prompt emitted once at start
    rec1 = ContextWindowRecorder()
    rt1 = _make_reflexion_runtime(rec1, max_trials=1)
    await rt1.arun("t", runner=FakeRunner([_is_done()]), context=_base_context(),
                   provider="openai", invoke_runner=_invoke_runner,
                   runner_output_text=_output_text, runner_output_metadata=_output_metadata)
    sp_slots = [s for s in rec1.slots() if s == "system_prompt"]
    _assert("system_prompt emitted exactly once", len(sp_slots) == 1)
    _assert("system_prompt is first slot", rec1.slots()[0] == "system_prompt")

    # reflexion_trial emitted per trial
    rec2 = ContextWindowRecorder()
    rt2 = _make_reflexion_runtime(rec2, max_trials=2)
    await rt2.arun("t", runner=FakeRunner([_fails(), _reflects(), _is_done()]),
                   context=_base_context(), provider="openai", invoke_runner=_invoke_runner,
                   runner_output_text=_output_text, runner_output_metadata=_output_metadata)
    trial_slots = [s for s in rec2.slots() if s == "reflexion_trial"]
    _assert("reflexion_trial emitted 2 times for 2-trial run", len(trial_slots) == 2)

    # reflexion_reflection emitted after failing trial
    reflection_slots = [s for s in rec2.slots() if s == "reflexion_reflection"]
    _assert("reflexion_reflection emitted 1 time for 1 failure", len(reflection_slots) == 1)

    # slot order matches template
    template_2 = ReflexionContextWindowTemplate(max_trials=2, failing_trials=1)
    violations_2 = template_2.validate(rec2)
    _assert("2-trial slot order matches template", violations_2 == [], str(violations_2))

    # early success -> no reflection slot
    rec3 = ContextWindowRecorder()
    rt3 = _make_reflexion_runtime(rec3, max_trials=3)
    await rt3.arun("t", runner=FakeRunner([_is_done()]), context=_base_context(),
                   provider="openai", invoke_runner=_invoke_runner,
                   runner_output_text=_output_text, runner_output_metadata=_output_metadata)
    _assert("early success -> no reflection slot", "reflexion_reflection" not in rec3.slots())

    # NullRecorder does not crash
    rt4 = _make_reflexion_runtime(ContextWindowRecorder(), max_trials=1)
    rt4.recorder = NullRecorder()
    result = await rt4.arun("t", runner=FakeRunner([_is_done()]), context=_base_context(),
                            provider="openai", invoke_runner=_invoke_runner,
                            runner_output_text=_output_text, runner_output_metadata=_output_metadata)
    _assert("NullRecorder does not crash", result is not None)

    # trial_index stored in SlotEvent
    rec5 = ContextWindowRecorder()
    rt5 = _make_reflexion_runtime(rec5, max_trials=2)
    await rt5.arun("t", runner=FakeRunner([_fails(), _reflects(), _is_done()]),
                   context=_base_context(), provider="openai", invoke_runner=_invoke_runner,
                   runner_output_text=_output_text, runner_output_metadata=_output_metadata)
    trial_events = [e for e in rec5.events() if e.slot_type == "reflexion_trial"]
    _assert("trial_index=0 stored in first trial event", trial_events[0].iteration == 0)
    _assert("trial_index=1 stored in second trial event", trial_events[1].iteration == 1)

    # Full 3-trial integration
    rec6 = ContextWindowRecorder()
    rt6 = _make_reflexion_runtime(rec6, max_trials=3)
    await rt6.arun("t",
                   runner=FakeRunner([_fails(), _reflects(), _fails(), _reflects(), _is_done()]),
                   context=_base_context(), provider="openai", invoke_runner=_invoke_runner,
                   runner_output_text=_output_text, runner_output_metadata=_output_metadata)
    template_3 = ReflexionContextWindowTemplate(max_trials=3, failing_trials=2)
    violations_3 = template_3.validate(rec6)
    _assert("3-trial full integration passes template", violations_3 == [], str(violations_3))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def _run_all() -> None:
    test_slot_event()
    test_recorder()
    test_null_recorder()
    test_template()
    test_violation()
    test_reflexion_template()
    test_runtime_recorder_param()
    await test_reflexion_instrumentation()

    passed = sum(1 for _, p, _ in _results if p)
    total = len(_results)
    print(f"\n{'=' * 60}")
    print(f"{passed}/{total} tests passed")
    if passed < total:
        print("\nFailed tests:")
        for name, p, detail in _results:
            if not p:
                print(f"  FAIL: {name}" + (f" — {detail}" if detail else ""))
        sys.exit(1)
    else:
        print("All tests passed.")


if __name__ == "__main__":
    asyncio.run(_run_all())
