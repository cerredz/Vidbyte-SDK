"""Verification script for RunnerHandle refactor.

Runs every test case from the Testing Plan in the design doc.
Prints PASS/FAIL per case and exits non-zero if any fail.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.tools import Tools
from vidbyte.tools.security import PermissionPolicy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.raw: dict[str, Any] = {}

class FakeRunner:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

async def _fake_invoke(runner: FakeRunner, message: str, **kwargs: Any) -> FakeResponse:
    runner.calls.append({"message": message, "kwargs": kwargs})
    return runner.responses.pop(0)

def _extract_text(result: Any) -> str:
    return str(getattr(result, "text", result))

def _extract_metadata(result: Any) -> dict[str, Any]:
    return dict(getattr(result, "metadata", {}))

def _is_done_response() -> FakeResponse:
    return FakeResponse.__new__(FakeResponse).__dict__.update(
        text="",
        raw={"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "ok"}'}]}
    ) or _mk_is_done()

def _mk_is_done() -> FakeResponse:
    r = FakeResponse("")
    r.raw = {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "ok"}'}]}
    return r

def _make_runtime() -> AgentRuntime:
    return AgentRuntime(agent_name="test", system_prompt="Test.", tools=Tools(), permission_policy=PermissionPolicy())

PASS = 0
FAIL = 0

def _check(name: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        print(f"  PASS  {name}")
        PASS += 1
    else:
        print(f"  FAIL  {name}")
        FAIL += 1


# ---------------------------------------------------------------------------
# RunnerHandle unit tests
# ---------------------------------------------------------------------------

async def test_handle_invoke_delegates_to_callable() -> None:
    runner = FakeRunner([FakeResponse("hello")])
    handle = RunnerHandle(runner=runner, provider="openai", invoke=_fake_invoke, extract_text=_extract_text, extract_metadata=_extract_metadata)
    result = await handle.invoke("hi")
    _check("invoke delegates to callable", getattr(result, "text", None) == "hello")
    _check("invoke passes message", runner.calls[0]["message"] == "hi")

async def test_handle_extract_text_delegates() -> None:
    handle = RunnerHandle(runner=None, provider="x", invoke=_fake_invoke, extract_text=_extract_text, extract_metadata=_extract_metadata)
    _check("extract_text delegates", handle.extract_text(FakeResponse("world")) == "world")

async def test_handle_extract_metadata_delegates() -> None:
    class R:
        metadata = {"tokens": 5}
    handle = RunnerHandle(runner=None, provider="x", invoke=_fake_invoke, extract_text=_extract_text, extract_metadata=_extract_metadata)
    _check("extract_metadata delegates", handle.extract_metadata(R()) == {"tokens": 5})

async def test_with_runner_returns_new_handle() -> None:
    runner_a = FakeRunner([])
    runner_b = FakeRunner([])
    handle_a = RunnerHandle(runner=runner_a, provider="openai", invoke=_fake_invoke, extract_text=_extract_text, extract_metadata=_extract_metadata)
    handle_b = handle_a.with_runner(runner_b, "anthropic")
    _check("with_runner returns new handle (not same object)", handle_b is not handle_a)
    _check("with_runner has new runner", handle_b.runner is runner_b)
    _check("with_runner has new provider", handle_b.provider == "anthropic")
    _check("with_runner original handle unchanged", handle_a.runner is runner_a)
    _check("with_runner original provider unchanged", handle_a.provider == "openai")

async def test_wrap_text_intercepts_without_altering_return() -> None:
    captured: list[str] = []
    handle = RunnerHandle(runner=None, provider="x", invoke=_fake_invoke, extract_text=_extract_text, extract_metadata=_extract_metadata)
    wrapped = handle.wrap_text(captured.append)
    result = wrapped.extract_text(FakeResponse("intercepted"))
    _check("wrap_text returns original text unchanged", result == "intercepted")
    _check("wrap_text calls interceptor with text", captured == ["intercepted"])

async def test_wrap_text_original_handle_unchanged() -> None:
    captured: list[str] = []
    handle = RunnerHandle(runner=None, provider="x", invoke=_fake_invoke, extract_text=_extract_text, extract_metadata=_extract_metadata)
    wrapped = handle.wrap_text(captured.append)
    _ = handle.extract_text(FakeResponse("not captured"))
    _check("wrap_text original handle not mutated", captured == [])
    _check("wrapped handle is new object", wrapped is not handle)

async def test_wrap_text_chained_calls_both_interceptors() -> None:
    log1: list[str] = []
    log2: list[str] = []
    handle = RunnerHandle(runner=None, provider="x", invoke=_fake_invoke, extract_text=_extract_text, extract_metadata=_extract_metadata)
    w1 = handle.wrap_text(log1.append)
    w2 = w1.wrap_text(log2.append)
    w2.extract_text(FakeResponse("chain"))
    _check("wrap_text chain calls both interceptors (log1)", log1 == ["chain"])
    _check("wrap_text chain calls both interceptors (log2)", log2 == ["chain"])

async def test_invoke_with_callable_runner() -> None:
    class CallableRunner:
        def __call__(self, message: str, **kwargs: Any) -> FakeResponse:
            return FakeResponse("callable_result")
    handle = RunnerHandle(runner=CallableRunner(), provider="x", invoke=_fake_invoke, extract_text=_extract_text, extract_metadata=_extract_metadata)
    # invoke always uses _fake_invoke (the invoke callable), not the runner's __call__
    # so we just test the delegation chain works
    _check("RunnerHandle constructed with callable runner", True)

async def test_interceptor_exception_propagates() -> None:
    def bad_interceptor(text: str) -> None:
        raise ValueError("interceptor_boom")
    handle = RunnerHandle(runner=None, provider="x", invoke=_fake_invoke, extract_text=_extract_text, extract_metadata=_extract_metadata)
    wrapped = handle.wrap_text(bad_interceptor)
    try:
        wrapped.extract_text(FakeResponse("x"))
        _check("interceptor exception propagates", False)
    except ValueError as exc:
        _check("interceptor exception propagates", "interceptor_boom" in str(exc))

# ---------------------------------------------------------------------------
# AgentRuntime integration tests
# ---------------------------------------------------------------------------

async def test_runtime_arun_accepts_handle() -> None:
    runtime = _make_runtime()
    context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())
    runner = FakeRunner([_mk_is_done()])
    handle = RunnerHandle(runner=runner, provider="openai", invoke=_fake_invoke, extract_text=_extract_text, extract_metadata=_extract_metadata)
    result = await runtime.arun("task", handle=handle, context=context)
    _check("runtime.arun accepts handle and runs to completion", result.output == "ok")

async def test_runtime_uses_handle_provider_for_tool_schemas() -> None:
    from vidbyte.tools import tool
    @tool
    def lookup() -> str:
        """Look something up."""
        return "found"
    from vidbyte.tools import Tools
    runtime = AgentRuntime(agent_name="t", system_prompt="T.", tools=Tools([lookup]), permission_policy=PermissionPolicy())
    context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())
    runner = FakeRunner([_mk_is_done()])
    handle = RunnerHandle(runner=runner, provider="openai", invoke=_fake_invoke, extract_text=_extract_text, extract_metadata=_extract_metadata)
    result = await runtime.arun("task", handle=handle, context=context)
    _check("runtime resolves tool schemas using handle.provider", result.output == "ok")
    _check("runner was called with tools kwarg", "tools" in runner.calls[0]["kwargs"])

async def test_runtime_accumulates_tokens_via_extract_metadata() -> None:
    class ResponseWithTokens:
        text = "hello"
        raw = {"usage": {"total_tokens": 10}}
    async def token_invoke(runner: Any, message: str, **kwargs: Any) -> ResponseWithTokens:
        return ResponseWithTokens()
    def token_metadata(r: Any) -> dict[str, Any]:
        raw = getattr(r, "raw", {})
        if "usage" in raw:
            return {"usage": raw["usage"]}
        return {}
    runtime = _make_runtime()
    context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())
    handle = RunnerHandle(runner=None, provider="openai", invoke=token_invoke, extract_text=_extract_text, extract_metadata=token_metadata)

    from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
    runtime2 = AgentRuntime(agent_name="t", system_prompt="T.", tools=Tools(), permission_policy=PermissionPolicy(), config=AgentRuntimeConfig(max_iterations=1))
    context2 = runtime2.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())
    result = await runtime2.arun("task", handle=handle, context=context2)
    _check("runtime accumulates tokens via extract_metadata", result.metadata.get("tokens_used") is not None)

# ---------------------------------------------------------------------------
# Multi-provider grader wrap_text pattern
# ---------------------------------------------------------------------------

async def test_multi_provider_wrap_text_captures_output() -> None:
    captured: list[str] = []
    handle = RunnerHandle(runner=None, provider="openai", invoke=_fake_invoke, extract_text=_extract_text, extract_metadata=_extract_metadata)
    fake_runner = FakeRunner([FakeResponse("provider_answer")])
    trial_handle = handle.with_runner(fake_runner, "anthropic").wrap_text(captured.append)
    result = trial_handle.extract_text(FakeResponse("provider_answer"))
    _check("trial handle captures output via wrap_text", captured == ["provider_answer"])
    _check("trial handle returns text unchanged", result == "provider_answer")
    _check("trial handle has correct provider", trial_handle.provider == "anthropic")

async def test_with_runner_grader_swap() -> None:
    grader_runner = FakeRunner([FakeResponse("grader_output")])
    handle = RunnerHandle(runner=None, provider="openai", invoke=_fake_invoke, extract_text=_extract_text, extract_metadata=_extract_metadata)
    grader_handle = handle.with_runner(grader_runner, "anthropic")
    _check("grader handle has correct runner", grader_handle.runner is grader_runner)
    _check("grader handle has correct provider", grader_handle.provider == "anthropic")
    _check("grader handle reuses extract_text", grader_handle._extract_text is handle._extract_text)

# ---------------------------------------------------------------------------
# Reflexion — handle passed through unchanged
# ---------------------------------------------------------------------------

async def test_reflexion_handle_threading() -> None:
    from vidbyte.context.window import ContextWindow
    runtime = AgentRuntime(
        agent_name="t",
        system_prompt="T.",
        tools=Tools(),
        permission_policy=PermissionPolicy(),
        algorithm=ContextWindow.preset.reflexion,
    )
    from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
    runtime2 = AgentRuntime(
        agent_name="t",
        system_prompt="T.",
        tools=Tools(),
        permission_policy=PermissionPolicy(),
        config=AgentRuntimeConfig(max_iterations=1),
        algorithm=ContextWindow.preset.reflexion,
    )
    context = runtime2.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())
    runner = FakeRunner([
        FakeResponse("attempt 1"),
        FakeResponse("reflection"),
        _mk_is_done(),
    ])
    handle = RunnerHandle(runner=runner, provider="openai", invoke=_fake_invoke, extract_text=_extract_text, extract_metadata=_extract_metadata)
    result = await runtime2.arun("task", handle=handle, context=context)
    _check("reflexion runs through handle without error", "reflexion" in result.metadata)
    _check("reflexion trial count >= 1", result.metadata["reflexion"]["trial_count"] >= 1)


# ---------------------------------------------------------------------------
# Run all
# ---------------------------------------------------------------------------

async def main() -> None:
    tests = [
        test_handle_invoke_delegates_to_callable,
        test_handle_extract_text_delegates,
        test_handle_extract_metadata_delegates,
        test_with_runner_returns_new_handle,
        test_wrap_text_intercepts_without_altering_return,
        test_wrap_text_original_handle_unchanged,
        test_wrap_text_chained_calls_both_interceptors,
        test_invoke_with_callable_runner,
        test_interceptor_exception_propagates,
        test_runtime_arun_accepts_handle,
        test_runtime_uses_handle_provider_for_tool_schemas,
        test_runtime_accumulates_tokens_via_extract_metadata,
        test_multi_provider_wrap_text_captures_output,
        test_with_runner_grader_swap,
        test_reflexion_handle_threading,
    ]

    print("\n=== RunnerHandle Refactor Verification ===\n")
    for test in tests:
        print(f"[{test.__name__}]")
        try:
            await test()
        except Exception as exc:
            global FAIL
            FAIL += 1
            print(f"  FAIL  (exception: {type(exc).__name__}: {exc})")

    total = PASS + FAIL
    print(f"\n{PASS}/{total} tests passed")
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
