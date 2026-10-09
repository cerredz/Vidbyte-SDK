"""FILE: tests/test_algorithm_side_call_usage.py

PURPOSE: Regression tests that model calls made by context-window algorithms reach the run's usage ledger.
ROLE IN CODEBASE: Guards AgentRuntime.usage_tracker against missing reflection and inner-loop explorer calls, which understated get_usage() and get_cost_usd().
ARCHITECTURE NOTE: Offline fake runner whose responses carry provider, model, and token usage; each test compares recorded model calls with runner invocations.
COMMON MODIFICATION PATTERNS: Add a case here when a new algorithm makes its own model call outside the main loop.
KNOWN EDGE CASES: Middleware AgentResult aborts are not provider responses and are never recorded.
RELATED DOCS: docs/design/algorithm-side-call-usage.md.
TESTS: python -m pytest tests/test_algorithm_side_call_usage.py.
"""

from __future__ import annotations

import unittest
from typing import Any

from vidbyte import ContextWindow, ContextWindowAlgorithm, ProblemSpaceSearchAlgorithm
from vidbyte.agents.runtime import AgentRuntime
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.tools import Tools, tool
from vidbyte.tools.security import PermissionPolicy

_EXPLORER_JSON = '{"unconsidered": ["alt"], "blind_spots": ["gap"], "next_directions": ["check"]}'


class UsageResponse:
    # An offline provider response that reports usage the way a real adapter does.
    def __init__(self, text: str, raw: dict | None = None) -> None:
        self.text = text
        self.raw = raw or {}
        self.provider = "openai"
        self.model = "gpt-4o-mini"
        self.usage = {"input_tokens": 1000, "output_tokens": 10, "total_tokens": 1010}


class FakeRunner:
    # Returns queued responses in order and remembers every invocation.
    def __init__(self, responses: list[UsageResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[str] = []


async def invoke_runner(runner: FakeRunner, prompt: str, **kwargs: Any) -> UsageResponse:
    runner.calls.append(prompt)
    return runner.responses.pop(0)


def handle_for(runner: FakeRunner) -> RunnerHandle:
    return RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=lambda r: str(getattr(r, "text", r)), extract_metadata=lambda r: {})


def tool_call(name: str = "lookup") -> UsageResponse:
    return UsageResponse("", {"output": [{"type": "function_call", "name": name, "arguments": "{}"}]})


def is_done(answer: str = "done") -> UsageResponse:
    return UsageResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": f'{{"final_answer": "{answer}"}}'}]})


@tool
def lookup() -> str:
    """Look up information."""
    return "not enough"


class AlgorithmSideCallUsageTests(unittest.IsolatedAsyncioTestCase):
    async def test_reflexion_reflection_call_is_recorded(self) -> None:
        # [Silent Failure] The reflection call between trials is billed, so it must be counted.
        runner = FakeRunner([tool_call(), UsageResponse("Use the lookup result."), is_done("fixed")])
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools([lookup]), permission_policy=PermissionPolicy(), config=AgentRuntimeConfig(max_iterations=1), algorithm=ContextWindow.preset.reflexion)
        context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())
        result = await runtime.arun("task", handle=handle_for(runner), context=context)
        self.assertEqual(result.output, "fixed")
        self.assertEqual(len(runner.calls), 3)
        self.assertEqual(runtime.usage_tracker.rollup().model_call_count, len(runner.calls))

    async def test_problem_space_search_explorer_call_is_recorded(self) -> None:
        # [Silent Failure] The inner-loop explorer call is billed, so it must be counted.
        runner = FakeRunner([tool_call(), tool_call(), UsageResponse(_EXPLORER_JSON), is_done()])
        algorithm = ContextWindowAlgorithm(name="problem_space_search", problem_space_search=ProblemSpaceSearchAlgorithm(interval=2))
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools([lookup]), permission_policy=PermissionPolicy(), algorithm=algorithm)
        context = BaseAgentContext(system_prompt="sys", history=(), file_paths=(), tools=(), budget=None)
        result = await runtime.arun("task", handle=handle_for(runner), context=context)
        self.assertEqual(result.metadata["problem_space_search"]["note_count"], 1)
        self.assertEqual(len(runner.calls), 4)
        self.assertEqual(runtime.usage_tracker.rollup().model_call_count, len(runner.calls))


if __name__ == "__main__":
    unittest.main()
