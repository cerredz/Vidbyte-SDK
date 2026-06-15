"""Phase-5 verification script for tool-call arguments in trace and context.

Runs every Section-10 test case from the design doc directly against the
implementation, printing PASS/FAIL per case and exiting non-zero on any failure.

Usage:
    python scripts/test_tool_call_arguments_in_trace_and_context.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vidbyte.agents import AgentRuntime
from vidbyte.agents.runtime import _args_fingerprint, _output_fingerprint
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.tools import ToolsFormatter
from vidbyte.lib.tracing import SpanContext, TracerBase
from vidbyte.tools import BaseTool, ToolCall, ToolResult, ToolSpec, Tools
from vidbyte.tools.security import PermissionPolicy


class RecordingTracer(TracerBase):
    """Captures every span open/close so trace inputs and metadata can be asserted."""

    def __init__(self) -> None:
        self.spans_started: list[dict[str, Any]] = []
        self.spans_ended: list[dict[str, Any]] = []

    def start_trace(self, name: str, **attributes: Any) -> SpanContext:
        return SpanContext()

    def end_trace(self, context: SpanContext, **_: Any) -> None:
        pass

    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SpanContext:
        ctx = SpanContext()
        self.spans_started.append({"name": name, "attributes": attributes})
        return ctx

    def end_span(self, context: SpanContext, *, output: str | None = None, error: Exception | None = None, metadata: Any = None) -> None:
        self.spans_ended.append({"output": output, "error": error, "metadata": metadata})


class OkTool(BaseTool):
    """A default-permission tool that succeeds, for context/trace integration runs."""

    def spec(self) -> ToolSpec:
        return ToolSpec(name="lookup", description="Looks up a topic.")

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult.success("lookup", f"found:{call.arguments.get('topic')}")


class FakeRunner:
    """Replays scripted provider responses and records the kwargs it was called with."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def run(self, prompt: str, **kwargs: object) -> Any:
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        raw = self.responses.pop(0)
        return type("R", (), {"text": "", "raw": raw})()


async def _invoke(runner: FakeRunner, prompt: str, **kwargs: object) -> Any:
    return runner.run(prompt, **kwargs)


def _text(r: object) -> str:
    return str(getattr(r, "text", ""))


def _meta(r: object) -> dict:
    return {}


class VerificationSuite:
    """Runs all design-doc test cases and tallies pass/fail results."""

    def __init__(self) -> None:
        self.results: list[tuple[str, bool, str]] = []

    def run(self) -> int:
        # Executes every check group and returns a process exit code.
        self.check_serializer_round_trips()
        self.check_multi_call_and_pairing()
        self.check_argument_policy_split()
        self.check_serializer_edge_cases()
        self.check_fingerprints()
        asyncio.run(self.check_trace_surface())
        asyncio.run(self.check_context_surface())
        return self.summarize()

    def _record(self, name: str, passed: bool, detail: str = "") -> None:
        # Stores one case outcome and prints its label immediately.
        self.results.append((name, passed, detail))
        print(f"{'PASS' if passed else 'FAIL'}  {name}{('  -> ' + detail) if detail and not passed else ''}")

    def _openai_raw(self, msg: dict) -> object:
        # Wraps an OpenAI assistant message as a parseable chat-completions payload.
        return type("R", (), {"raw": {"choices": [{"message": {"tool_calls": msg["tool_calls"]}}]}})()

    def check_serializer_round_trips(self) -> None:
        # Verifies each provider serializer is the exact inverse of parse_tool_calls.
        call = ToolCall("read_file", {"path": "a.py", "start": 1}, call_id="c1")
        omsg = ToolsFormatter.format_assistant_tool_calls([call], "draft", "openai")
        oparsed = ToolsFormatter.parse_tool_calls(self._openai_raw(omsg), "openai")
        self._record("[Silent] openai round-trip preserves args", dict(oparsed[0].arguments) == {"path": "a.py", "start": 1})

        amsg = ToolsFormatter.format_assistant_tool_calls([call], "", "anthropic")
        araw = type("R", (), {"raw": {"content": amsg["content"]}})()
        aparsed = ToolsFormatter.parse_tool_calls(araw, "anthropic")
        self._record("[Silent] anthropic round-trip preserves args", dict(aparsed[0].arguments) == {"path": "a.py", "start": 1})

        gmsg = ToolsFormatter.format_assistant_tool_calls([ToolCall("glob", {"pattern": "**/*.py"})], "", "gemini")
        graw = type("R", (), {"raw": {"candidates": [{"content": {"parts": gmsg["parts"]}}]}})()
        gparsed = ToolsFormatter.parse_tool_calls(graw, "gemini")
        self._record("[Silent] gemini round-trip preserves args", dict(gparsed[0].arguments) == {"pattern": "**/*.py"})

    def check_multi_call_and_pairing(self) -> None:
        # Verifies a multi-tool turn becomes one assistant message with N ordered calls.
        calls = [ToolCall("a", {"x": 1}, call_id="c1"), ToolCall("b", {"y": 2}, call_id="c2")]
        omsg = ToolsFormatter.format_assistant_tool_calls(calls, "", "openai")
        self._record("[Hidden Assumption] multi-call openai is one msg with 2 calls", omsg["role"] == "assistant" and len(omsg["tool_calls"]) == 2)
        amsg = ToolsFormatter.format_assistant_tool_calls(calls, "", "anthropic")
        ids = [b["id"] for b in amsg["content"] if b["type"] == "tool_use"]
        self._record("[Hidden Failure] anthropic tool_use ids align/order", ids == ["c1", "c2"])

    def check_argument_policy_split(self) -> None:
        # Verifies context truncates oversized values but never redacts secret keys.
        big = ToolCall("write", {"body": "x" * 50_000, "api_key": "xai-secret"}, call_id="c1")
        msg = ToolsFormatter.format_assistant_tool_calls([big], "", "anthropic", max_arg_chars=10)
        inp = msg["content"][0]["input"]
        self._record("[Edge] context truncates oversized arg, keeps key", inp["body"].endswith("...[truncated]") and "api_key" in inp)
        self._record("[Hidden Assumption] context does NOT redact secret value", inp["api_key"] == "xai-secret")

    def check_serializer_edge_cases(self) -> None:
        # Verifies empty text, missing call id, and non-serializable values are handled.
        self._record("[Edge] openai empty text -> content None", ToolsFormatter.format_assistant_tool_calls([ToolCall("a", {})], "", "openai")["content"] is None)
        self._record("[Edge] missing call_id falls back to tool name", ToolsFormatter.format_assistant_tool_calls([ToolCall("lookup", {})], "", "openai")["tool_calls"][0]["id"] == "lookup")
        try:
            nm = ToolsFormatter.format_assistant_tool_calls([ToolCall("a", {"s": {1, 2}})], "", "openai")
            json.loads(nm["tool_calls"][0]["function"]["arguments"])
            ok = True
        except Exception:
            ok = False
        self._record("[Hidden Failure] non-serializable arg coerces, no raise", ok)

    def check_fingerprints(self) -> None:
        # Verifies fingerprint stability, order-independence, and discrimination.
        self._record("[Silent] args fingerprint key-order-independent", _args_fingerprint({"a": 1, "b": 2}) == _args_fingerprint({"b": 2, "a": 1}))
        self._record("[Edge] args fingerprint differs on different args", _args_fingerprint({"a": 1}) != _args_fingerprint({"a": 2}))
        self._record("[Edge] empty-args fingerprint stable+nonempty", bool(_args_fingerprint({})) and _args_fingerprint({}) == _args_fingerprint({}))
        self._record("[Silent] output fingerprint matches identical output", _output_fingerprint("same") == _output_fingerprint("same"))

    async def check_trace_surface(self) -> None:
        # Verifies the tool.call span carries args/call_id/fingerprint, redacts secrets, and records close state.
        tracer = RecordingTracer()
        runtime = AgentRuntime(agent_name="rt", system_prompt="sys", tools=Tools().add(OkTool()), permission_policy=PermissionPolicy(), tracer=tracer)
        await runtime.execute_tool_call(ToolCall("lookup", {"topic": "sdk", "api_token": "secret"}, call_id="call_9"), provider="openai")
        attrs = next(s for s in tracer.spans_started if s["name"] == "tool.call")["attributes"]
        self._record("[Silent] #141: span input has arguments", attrs.get("arguments", {}).get("topic") == "sdk")
        self._record("[Silent] #141: span input has call_id + fingerprint", attrs.get("call_id") == "call_9" and bool(attrs.get("arguments_fingerprint")))
        self._record("[Hidden Assumption] trace redacts secret arg key", "api_token" not in attrs.get("arguments", {}))
        meta = tracer.spans_ended[0]["metadata"]
        self._record("[Silent] span close records state + output fingerprint", meta.get("state") == "succeeded" and bool(meta.get("output_fingerprint")))

    async def check_context_surface(self) -> None:
        # Verifies the assistant tool-call turn (with args) is echoed into the next-turn history.
        runner = FakeRunner([
            {"output": [{"type": "function_call", "name": "lookup", "arguments": '{"topic": "sdk"}', "call_id": "c1"}]},
            {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "ok"}'}]},
        ])
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools().add(OkTool()), permission_policy=PermissionPolicy())
        context = BaseAgentContext(system_prompt="Work.", history=(), file_paths=(), tools=(), budget=None)
        await runtime.arun("task", handle=RunnerHandle(runner=runner, provider="openai", invoke=_invoke, extract_text=_text, extract_metadata=_meta), context=context)
        sent = runner.calls[1]["kwargs"]["messages"]
        assistant_calls = [m for m in sent if m.get("role") == "assistant" and m.get("tool_calls")]
        self._record("[Silent] context echoes assistant tool-call turn", len(assistant_calls) == 1)
        self._record("[Silent] echoed turn carries the requested arguments", bool(assistant_calls) and "sdk" in assistant_calls[0]["tool_calls"][0]["function"]["arguments"])
        echoed_names = [tc["function"]["name"] for m in assistant_calls for tc in m["tool_calls"]]
        self._record("[Hidden Assumption] isDone is not echoed (no dangling tool_use)", "isDone" not in echoed_names)
        tool_msgs = [m for m in sent if m.get("role") == "tool"]
        self._record("[Hidden Failure] tool result still paired after echo", len(tool_msgs) >= 1)

    def summarize(self) -> int:
        # Prints the final tally and returns 0 only when every case passed.
        passed = sum(1 for _, ok, _ in self.results if ok)
        total = len(self.results)
        print(f"\n{passed}/{total} tests passed")
        return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(VerificationSuite().run())
