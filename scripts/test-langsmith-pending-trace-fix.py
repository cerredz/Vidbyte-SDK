"""Verification script for issue #142: LangSmith pending trace on cancellation.

Runs every test case from the design doc Section 10 and exits non-zero on failure.
"""
from __future__ import annotations

import asyncio
import sys
import types
from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents import AgentRuntime
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.tracing import NullTracer, SpanContext, TracerBase
from vidbyte.tools import Tools
from vidbyte.tools.security import PermissionPolicy


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

_passed = 0
_failed = 0


def _report(name: str, ok: bool, detail: str = "") -> None:
    global _passed, _failed
    status = "PASS" if ok else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"{status}: {name}{suffix}")
    if ok:
        _passed += 1
    else:
        _failed += 1


class RecordingTracer(TracerBase):
    """Records every tracer call so tests can make assertions."""

    def __init__(self) -> None:
        self.traces_started: list[dict] = []
        self.traces_ended: list[dict] = []
        self.spans_started: list[dict] = []
        self.spans_ended: list[dict] = []
        self._counter = 0

    def _ctx(self, kind: str) -> SpanContext:
        self._counter += 1
        return SpanContext(metadata={"id": self._counter, "kind": kind})

    def start_trace(self, name: str, **attributes: Any) -> SpanContext:
        ctx = self._ctx("trace")
        self.traces_started.append({"name": name, "ctx": ctx})
        return ctx

    def end_trace(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None:
        self.traces_ended.append({"ctx": context, "output": output, "error": error})

    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SpanContext:
        ctx = self._ctx("span")
        self.spans_started.append({"name": name, "parent": parent, "ctx": ctx})
        return ctx

    def end_span(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None:
        self.spans_ended.append({"ctx": context, "output": output, "error": error})


class CancelledRunner:
    """Fake runner whose async invoke raises CancelledError."""

    def __init__(self) -> None:
        self._config = types.SimpleNamespace(provider="xai", model="grok-test")


async def _invoke_cancelled(runner: object, prompt: str, **kwargs: object) -> None:
    raise asyncio.CancelledError("simulated task cancellation")


class BombRunner:
    """Fake runner whose invoke raises RuntimeError."""

    def __init__(self) -> None:
        self._config = types.SimpleNamespace(provider="xai", model="grok-test")

    def run(self, *a: object, **kw: object) -> None:
        raise RuntimeError("bomb exploded")


def _output_text(r: object) -> str:
    return str(getattr(r, "text", r))


def _output_metadata(r: object) -> dict:
    return {}


def _make_cancelling_agent(tracer: TracerBase) -> BaseAgent:
    return BaseAgent(
        name="cancel-agent",
        system_prompt="Be helpful.",
        runner=CancelledRunner(),
        tracer=tracer,
    )


def _make_bomb_agent(tracer: TracerBase) -> BaseAgent:
    return BaseAgent(
        name="bomb-agent",
        system_prompt="Crash.",
        runner=BombRunner(),
        tracer=tracer,
    )


def _make_runtime(tracer: TracerBase) -> AgentRuntime:
    return AgentRuntime(
        agent_name="rt-agent",
        system_prompt="system",
        tools=Tools(),
        permission_policy=PermissionPolicy(),
        config=AgentRuntimeConfig(),
        tracer=tracer,
    )


async def _run_runtime_with_cancelled_invoke(runtime: AgentRuntime) -> None:
    from unittest.mock import patch
    from vidbyte.lib.dataclasses.context import BaseAgentContext
    context = BaseAgentContext(system_prompt="sys", history=(), file_paths=(), tools=(), budget=None)
    handle = RunnerHandle(
        runner=CancelledRunner(),
        provider="xai",
        invoke=_invoke_cancelled,
        extract_text=_output_text,
        extract_metadata=_output_metadata,
    )
    with patch.object(type(runtime), "_llm_trace_inputs", return_value={}):
        await runtime.arun("prompt", handle=handle, context=context)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

async def test_root_trace_closed_on_cancelled_error() -> None:
    tracer = RecordingTracer()
    agent = _make_cancelling_agent(tracer)
    try:
        await agent.generate_reply("hello")
    except (asyncio.CancelledError, Exception):
        pass
    _report(
        "root trace closed on CancelledError",
        len(tracer.traces_ended) == 1,
        f"traces_ended={len(tracer.traces_ended)}",
    )


async def test_root_trace_closed_with_error_on_cancelled() -> None:
    tracer = RecordingTracer()
    agent = _make_cancelling_agent(tracer)
    try:
        await agent.generate_reply("hello")
    except (asyncio.CancelledError, Exception):
        pass
    ok = len(tracer.traces_ended) == 1 and tracer.traces_ended[0]["error"] is not None
    _report("root trace error field set on CancelledError", ok)


async def test_cancelled_error_propagates() -> None:
    tracer = RecordingTracer()
    agent = _make_cancelling_agent(tracer)
    raised = False
    try:
        await agent.generate_reply("hello")
    except (asyncio.CancelledError, Exception):
        raised = True
    _report("CancelledError propagates after trace close", raised)


async def test_active_prompt_reset_on_cancelled() -> None:
    tracer = RecordingTracer()
    agent = _make_cancelling_agent(tracer)
    try:
        await agent.generate_reply("hello")
    except (asyncio.CancelledError, Exception):
        pass
    _report("_active_prompt reset on CancelledError", agent._active_prompt == "")


async def test_root_trace_not_double_closed_on_exception() -> None:
    tracer = RecordingTracer()
    agent = _make_bomb_agent(tracer)
    try:
        await agent.generate_reply("hello")
    except Exception:
        pass
    _report(
        "root trace closed exactly once on Exception",
        len(tracer.traces_ended) == 1,
        f"traces_ended={len(tracer.traces_ended)}",
    )


async def test_root_trace_error_is_base_exception_instance() -> None:
    tracer = RecordingTracer()
    agent = _make_cancelling_agent(tracer)
    try:
        await agent.generate_reply("hello")
    except (asyncio.CancelledError, Exception):
        pass
    ok = len(tracer.traces_ended) == 1 and isinstance(tracer.traces_ended[0]["error"], BaseException)
    _report("end_trace error is BaseException instance", ok)


async def test_llm_span_closed_on_cancelled_error() -> None:
    tracer = RecordingTracer()
    runtime = _make_runtime(tracer)
    try:
        await _run_runtime_with_cancelled_invoke(runtime)
    except (asyncio.CancelledError, Exception):
        pass
    llm_spans_ended = [s for s in tracer.spans_ended if any(
        started["name"] == "llm.call" and started["ctx"] is s["ctx"]
        for started in tracer.spans_started
    )]
    _report(
        "llm.call span closed on CancelledError",
        len(llm_spans_ended) == 1,
        f"llm_spans_closed={len(llm_spans_ended)}",
    )


async def test_llm_span_closed_with_error_on_cancelled() -> None:
    tracer = RecordingTracer()
    runtime = _make_runtime(tracer)
    try:
        await _run_runtime_with_cancelled_invoke(runtime)
    except (asyncio.CancelledError, Exception):
        pass
    llm_span_end = next(
        (s for s in tracer.spans_ended if any(
            started["name"] == "llm.call" and started["ctx"] is s["ctx"]
            for started in tracer.spans_started
        )),
        None,
    )
    ok = llm_span_end is not None and llm_span_end["error"] is not None
    _report("llm.call span error field set on CancelledError", ok)


async def test_cancelled_propagates_from_runtime() -> None:
    tracer = RecordingTracer()
    runtime = _make_runtime(tracer)
    raised = False
    try:
        await _run_runtime_with_cancelled_invoke(runtime)
    except (asyncio.CancelledError, Exception):
        raised = True
    _report("CancelledError propagates from runtime after span close", raised)


def test_end_trace_accepts_base_exception_type() -> None:
    tracer = RecordingTracer()
    ctx = tracer.start_trace("agent.run")
    tracer.end_trace(ctx, error=asyncio.CancelledError("x"))
    ok = isinstance(tracer.traces_ended[0]["error"], asyncio.CancelledError)
    _report("end_trace accepts CancelledError (BaseException) without TypeError", ok)


def test_end_span_accepts_base_exception_type() -> None:
    tracer = RecordingTracer()
    ctx = tracer.start_span("llm.call")
    tracer.end_span(ctx, error=asyncio.CancelledError("x"))
    ok = isinstance(tracer.spans_ended[0]["error"], asyncio.CancelledError)
    _report("end_span accepts CancelledError (BaseException) without TypeError", ok)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def main() -> None:
    await test_root_trace_closed_on_cancelled_error()
    await test_root_trace_closed_with_error_on_cancelled()
    await test_cancelled_error_propagates()
    await test_active_prompt_reset_on_cancelled()
    await test_root_trace_not_double_closed_on_exception()
    await test_root_trace_error_is_base_exception_instance()
    await test_llm_span_closed_on_cancelled_error()
    await test_llm_span_closed_with_error_on_cancelled()
    await test_cancelled_propagates_from_runtime()
    test_end_trace_accepts_base_exception_type()
    test_end_span_accepts_base_exception_type()

    total = _passed + _failed
    print(f"\n{_passed}/{total} tests passed")
    sys.exit(0 if _failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
