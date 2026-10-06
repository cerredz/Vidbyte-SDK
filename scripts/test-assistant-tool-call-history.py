"""Verification script for issue #144: assistant tool-call history.

Runs every test case from the design doc Section 10 and exits non-zero on failure.
"""
from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import Mapping
from typing import Any

from unittest.mock import patch

from vidbyte import Agent, tool
from vidbyte.agents import AgentRuntime
from vidbyte.lib.tools.formatter import ToolsFormatter


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


# ---------------------------------------------------------------------------
# Unit tests: format_assistant_tool_calls
# ---------------------------------------------------------------------------

def test_openai_chat_returns_assistant_message() -> None:
    raw = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}],
            }
        }]
    }
    result = ToolsFormatter.format_assistant_tool_calls(raw, "openai")
    ok = result is not None and result["role"] == "assistant" and isinstance(result.get("tool_calls"), list)
    _report("OpenAI chat: returns assistant message with tool_calls", ok)


def test_openai_chat_returns_none_for_text_only() -> None:
    raw = {"choices": [{"message": {"role": "assistant", "content": "Hello!"}}]}
    result = ToolsFormatter.format_assistant_tool_calls(raw, "openai")
    _report("OpenAI chat: returns None for text-only response", result is None)


def test_openai_chat_returns_none_for_null_tool_calls() -> None:
    raw = {"choices": [{"message": {"role": "assistant", "content": "text", "tool_calls": None}}]}
    result = ToolsFormatter.format_assistant_tool_calls(raw, "openai")
    _report("OpenAI chat: returns None when tool_calls is null", result is None)


def test_openai_responses_api_returns_none() -> None:
    raw = {"output": [{"type": "function_call", "name": "read", "arguments": "{}", "call_id": "fc_1"}]}
    result = ToolsFormatter.format_assistant_tool_calls(raw, "openai")
    _report("OpenAI Responses API: returns None (unsupported shape)", result is None)


def test_openai_empty_choices_returns_none() -> None:
    result = ToolsFormatter.format_assistant_tool_calls({"choices": []}, "openai")
    _report("OpenAI chat: returns None for empty choices", result is None)


def test_openai_multiple_tool_calls_single_message() -> None:
    raw = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "a", "arguments": "{}"}},
                    {"id": "c2", "type": "function", "function": {"name": "b", "arguments": "{}"}},
                ],
            }
        }]
    }
    result = ToolsFormatter.format_assistant_tool_calls(raw, "openai")
    ok = result is not None and len(result["tool_calls"]) == 2
    _report("OpenAI chat: multiple tool_calls preserved in single message", ok)


def test_anthropic_returns_assistant_message() -> None:
    raw = {"content": [{"type": "tool_use", "id": "tu_1", "name": "f", "input": {}}]}
    result = ToolsFormatter.format_assistant_tool_calls(raw, "anthropic")
    ok = result is not None and result["role"] == "assistant" and result["content"][0]["type"] == "tool_use"
    _report("Anthropic: returns assistant message with tool_use content", ok)


def test_anthropic_returns_none_for_text_only() -> None:
    raw = {"content": [{"type": "text", "text": "Hello!"}]}
    result = ToolsFormatter.format_assistant_tool_calls(raw, "anthropic")
    _report("Anthropic: returns None for text-only content", result is None)


def test_anthropic_preserves_text_alongside_tool_use() -> None:
    raw = {
        "content": [
            {"type": "text", "text": "I'll check."},
            {"type": "tool_use", "id": "tu_2", "name": "f", "input": {}},
        ]
    }
    result = ToolsFormatter.format_assistant_tool_calls(raw, "anthropic")
    ok = result is not None and len(result["content"]) == 2 and result["content"][0]["type"] == "text"
    _report("Anthropic: text blocks alongside tool_use are preserved in full content", ok)


def test_anthropic_empty_content_returns_none() -> None:
    result = ToolsFormatter.format_assistant_tool_calls({"content": []}, "anthropic")
    _report("Anthropic: returns None for empty content list", result is None)


def test_gemini_returns_model_content() -> None:
    raw = {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": "f", "args": {}}}]}}]}
    result = ToolsFormatter.format_assistant_tool_calls(raw, "gemini")
    ok = result is not None and result["role"] == "model" and "functionCall" in result["parts"][0]
    _report("Gemini: returns model content with functionCall", ok)


def test_gemini_returns_none_for_text_only() -> None:
    raw = {"candidates": [{"content": {"role": "model", "parts": [{"text": "Hello!"}]}}]}
    result = ToolsFormatter.format_assistant_tool_calls(raw, "gemini")
    _report("Gemini: returns None for text-only parts", result is None)


def test_gemini_empty_candidates_returns_none() -> None:
    result = ToolsFormatter.format_assistant_tool_calls({"candidates": []}, "gemini")
    _report("Gemini: returns None for empty candidates", result is None)


def test_non_mapping_raw_returns_none() -> None:
    _report("Non-Mapping raw (string): returns None", ToolsFormatter.format_assistant_tool_calls("bad", "openai") is None)


def test_none_raw_returns_none() -> None:
    _report("None raw: returns None", ToolsFormatter.format_assistant_tool_calls(None, "openai") is None)


def test_role_is_assistant_for_openai() -> None:
    raw = {"choices": [{"message": {"role": "assistant", "tool_calls": [{"id": "x", "type": "function", "function": {"name": "f", "arguments": "{}"}}]}}]}
    result = ToolsFormatter.format_assistant_tool_calls(raw, "openai")
    _report("Role is 'assistant' for OpenAI", result is not None and result["role"] == "assistant")


def test_role_is_model_for_gemini() -> None:
    raw = {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": "f", "args": {}}}]}}]}
    result = ToolsFormatter.format_assistant_tool_calls(raw, "gemini")
    _report("Role is 'model' for Gemini", result is not None and result["role"] == "model")


def test_raw_object_with_raw_attribute_is_unwrapped() -> None:
    class FakeResponse:
        raw: dict[str, Any] = {
            "choices": [{"message": {"role": "assistant", "tool_calls": [{"id": "y", "type": "function", "function": {"name": "g", "arguments": "{}"}}]}}]
        }
    result = ToolsFormatter.format_assistant_tool_calls(FakeResponse(), "openai")
    ok = result is not None and result["tool_calls"][0]["id"] == "y"
    _report("Object with .raw attribute is unwrapped correctly", ok)


# ---------------------------------------------------------------------------
# Integration tests: _arun_once message ordering
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, text: str, raw: dict) -> None:
        self.text = text
        self.raw = raw


class ToolCallingRunner:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def run(self, prompt: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return self.responses.pop(0)


async def test_openai_chat_assistant_turn_before_tool_result() -> None:
    @tool
    def read(path: str) -> str:
        """Read a file."""
        return "file content"

    runner = ToolCallingRunner([
        FakeResponse("", {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read", "arguments": '{"path": "f.py"}'}}]}}]}),
        FakeResponse("", {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{"id": "c2", "type": "function", "function": {"name": "isDone", "arguments": '{"final_answer": "done"}'}}]}}]}),
    ])
    agent = Agent(name="w", system_prompt="Work.", runner=runner, tools=[read])
    with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
        await agent.arun("task")

    msgs = runner.calls[1]["kwargs"].get("messages", [])
    asst_idx = next((i for i, m in enumerate(msgs) if isinstance(m.get("tool_calls"), list)), None)
    tool_idx = next((i for i, m in enumerate(msgs) if m.get("role") == "tool"), None)
    ok = asst_idx is not None and tool_idx is not None and asst_idx < tool_idx
    _report(
        "OpenAI chat: assistant tool-call turn precedes tool result in messages",
        ok,
        f"asst_idx={asst_idx}, tool_idx={tool_idx}",
    )


async def test_anthropic_assistant_turn_before_tool_result() -> None:
    @tool
    def read(path: str) -> str:
        """Read a file."""
        return "file content"

    runner = ToolCallingRunner([
        FakeResponse("", {"content": [{"type": "tool_use", "id": "tu_1", "name": "read", "input": {"path": "f.py"}}]}),
        FakeResponse("", {"content": [{"type": "tool_use", "id": "tu_2", "name": "isDone", "input": {"final_answer": "done"}}]}),
    ])
    agent = Agent(name="w", system_prompt="Work.", runner=runner, tools=[read])
    with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
        await agent.arun("task", provider="anthropic")

    msgs = runner.calls[1]["kwargs"].get("messages", [])
    asst_idx = next((i for i, m in enumerate(msgs) if m.get("role") == "assistant"), None)
    tool_res_idx = next(
        (i for i, m in enumerate(msgs)
         if m.get("role") == "user" and isinstance(m.get("content"), list)
         and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in m["content"])),
        None,
    )
    ok = asst_idx is not None and tool_res_idx is not None and asst_idx < tool_res_idx
    _report(
        "Anthropic: assistant turn precedes tool_result in messages",
        ok,
        f"asst_idx={asst_idx}, tool_res_idx={tool_res_idx}",
    )


async def test_gemini_model_turn_before_function_result() -> None:
    @tool
    def read(path: str) -> str:
        """Read a file."""
        return "file content"

    runner = ToolCallingRunner([
        FakeResponse("", {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": "read", "args": {"path": "f.py"}}}]}}]}),
        FakeResponse("", {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": "isDone", "args": {"final_answer": "done"}}}]}}]}),
    ])
    agent = Agent(name="w", system_prompt="Work.", runner=runner, tools=[read])
    with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
        await agent.arun("task", provider="gemini")

    msgs = runner.calls[1]["kwargs"].get("messages", [])
    model_idx = next((i for i, m in enumerate(msgs) if m.get("role") == "model"), None)
    fn_idx = next((i for i, m in enumerate(msgs) if m.get("role") == "function"), None)
    ok = model_idx is not None and fn_idx is not None and model_idx < fn_idx
    _report(
        "Gemini: model turn precedes function result in messages",
        ok,
        f"model_idx={model_idx}, fn_idx={fn_idx}",
    )


async def test_responses_api_still_completes_successfully() -> None:
    @tool
    def read(path: str) -> str:
        """Read a file."""
        return "file content"

    runner = ToolCallingRunner([
        FakeResponse("", {"output": [{"type": "function_call", "name": "read", "arguments": '{"path": "f.py"}', "call_id": "fc_1"}]}),
        FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}', "call_id": "fc_2"}]}),
    ])
    agent = Agent(name="w", system_prompt="Work.", runner=runner, tools=[read])
    with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
        reply = await agent.arun("task")
    _report("Responses API: run completes without error (assistant turn skipped)", reply.content == "done")


async def test_text_only_response_no_phantom_assistant_turn() -> None:
    runner = ToolCallingRunner([
        FakeResponse("just text", {"choices": [{"message": {"role": "assistant", "content": "just text"}}]}),
    ])
    agent = Agent(name="w", system_prompt="Work.", runner=runner, tools=[])
    with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
        reply = await agent.arun("task")
    ok = reply.content == "just text" and len(runner.calls) == 1
    _report("Text-only response: no phantom assistant turn inserted (single call)", ok)


async def test_two_rounds_each_has_one_assistant_turn() -> None:
    @tool
    def read(path: str) -> str:
        """Read a file."""
        return "content"

    runner = ToolCallingRunner([
        FakeResponse("", {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read", "arguments": '{"path": "a.py"}'}}]}}]}),
        FakeResponse("", {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{"id": "c2", "type": "function", "function": {"name": "isDone", "arguments": '{"final_answer": "done"}'}}]}}]}),
    ])
    agent = Agent(name="w", system_prompt="Work.", runner=runner, tools=[read])
    with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
        await agent.arun("task")

    msgs = runner.calls[1]["kwargs"].get("messages", [])
    assistant_turns = [m for m in msgs if isinstance(m.get("tool_calls"), list)]
    ok = len(assistant_turns) == 1
    _report(
        "Two sequential rounds: exactly one assistant turn per round in accumulated messages",
        ok,
        f"found {len(assistant_turns)} assistant tool-call turn(s)",
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def main() -> None:
    # Unit tests
    test_openai_chat_returns_assistant_message()
    test_openai_chat_returns_none_for_text_only()
    test_openai_chat_returns_none_for_null_tool_calls()
    test_openai_responses_api_returns_none()
    test_openai_empty_choices_returns_none()
    test_openai_multiple_tool_calls_single_message()
    test_anthropic_returns_assistant_message()
    test_anthropic_returns_none_for_text_only()
    test_anthropic_preserves_text_alongside_tool_use()
    test_anthropic_empty_content_returns_none()
    test_gemini_returns_model_content()
    test_gemini_returns_none_for_text_only()
    test_gemini_empty_candidates_returns_none()
    test_non_mapping_raw_returns_none()
    test_none_raw_returns_none()
    test_role_is_assistant_for_openai()
    test_role_is_model_for_gemini()
    test_raw_object_with_raw_attribute_is_unwrapped()

    # Integration tests
    await test_openai_chat_assistant_turn_before_tool_result()
    await test_anthropic_assistant_turn_before_tool_result()
    await test_gemini_model_turn_before_function_result()
    await test_responses_api_still_completes_successfully()
    await test_text_only_response_no_phantom_assistant_turn()
    await test_two_rounds_each_has_one_assistant_turn()

    total = _passed + _failed
    print(f"\n{_passed}/{total} tests passed")
    sys.exit(0 if _failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
