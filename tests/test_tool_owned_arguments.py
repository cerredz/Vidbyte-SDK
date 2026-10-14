"""FILE: tests/test_tool_owned_arguments.py

PURPOSE: Regression tests proving tool code gets its own copy of a call's arguments.
ROLE IN CODEBASE: Guards the runtime boundary where BaseAgentRuntime hands a ToolCall to tool.execute(),
    so a tool that pops or edits its arguments cannot change what the runtime retries, records or evaluates.
ARCHITECTURE NOTE: Drives AgentRuntime offline with a scripted fake runner (the same pattern as
    tests/test_agent_middleware.py) and a ToolErrorPolicyMiddleware that retries a transient tool error.
FUNCTION INVENTORY: ConsumingTool pops "path" and sorts "pages" in place, failing once with rate_limited;
    UncopyableArgumentTool receives a value deepcopy rejects. ToolOwnedArgumentsTests checks the retry,
    the recorded call and the shallow-copy fallback.
COMMON MODIFICATION PATTERNS: Add a case per way user tool code can edit its arguments in place.
WHAT NOT TO DO: Do not call real provider endpoints, require API keys, or sleep for real backoff.
KNOWN EDGE CASES: Values deepcopy cannot copy fall back to a shallow dict copy, which still protects pop.
RELATED DOCS: vidbyte/agents/README.md
TESTS: Run with python -m pytest -q tests/test_tool_owned_arguments.py.
"""

from __future__ import annotations

import unittest
from typing import Any

from vidbyte.agents import AgentRuntime, ToolErrorPolicy
from vidbyte.lib.dataclasses.context import BaseContext as StrategyContext
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.middleware.builtins import ToolErrorPolicyMiddleware
from vidbyte.tools import BaseTool, ToolCall, ToolPermission, ToolResult, ToolSpec, Tools
from vidbyte.tools.security import PermissionPolicy

MODEL_ARGUMENTS = {"path": "q3.pdf", "pages": [3, 1, 2]}
REPORT_SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string"}, "pages": {"type": "array", "items": {"type": "integer"}}},
    "required": ["path"],
}


class FakeResponse:
    def __init__(self, raw: dict[str, Any]) -> None:
        self.text = ""
        self.raw = raw
        self.metadata: dict[str, Any] = {}


class FakeRunner:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []


async def invoke_runner(runner: FakeRunner, prompt: str, **kwargs: object) -> FakeResponse:
    runner.calls.append({"prompt": prompt, "kwargs": kwargs})
    return runner.responses.pop(0)


def runner_output_text(response: object) -> str:
    return str(getattr(response, "text", response))


def runner_output_metadata(response: object) -> dict[str, Any]:
    return dict(getattr(response, "metadata", {}))


class ConsumingTool(BaseTool):
    """Uses the everyday idiom of popping and sorting its own arguments, and fails once transiently."""

    def __init__(self) -> None:
        self.seen_paths: list[object] = []

    def spec(self) -> ToolSpec:
        return ToolSpec(name="fetch_report", description="Fetch a report.", permission=ToolPermission.READ, input_schema=REPORT_SCHEMA)

    async def execute(self, call: ToolCall) -> ToolResult:
        args = call.arguments
        path = args.pop("path", None)
        args["pages"].sort()
        self.seen_paths.append(path)
        if len(self.seen_paths) == 1:
            return ToolResult.error("fetch_report", "slow down", metadata={"error": "rate_limited"})
        return ToolResult.success("fetch_report", f"revenue for {path} pages {args['pages']}")


class Uncopyable:
    def __deepcopy__(self, memo: dict[int, object]) -> Uncopyable:
        raise TypeError("cannot deepcopy a live handle")


class UncopyableArgumentTool(BaseTool):
    def spec(self) -> ToolSpec:
        return ToolSpec(name="use_handle", description="Use a live handle.", permission=ToolPermission.READ, input_schema={"type": "object", "required": ["path"]})

    async def execute(self, call: ToolCall) -> ToolResult:
        path = call.arguments.pop("path")
        return ToolResult.success("use_handle", f"{path} via {type(call.arguments['handle']).__name__}")


class ToolOwnedArgumentsTests(unittest.IsolatedAsyncioTestCase):
    def _runtime(self, tools: Tools, middleware: tuple[ToolErrorPolicyMiddleware, ...] = ()) -> AgentRuntime:
        return AgentRuntime(agent_name="worker", system_prompt="Work.", tools=tools, permission_policy=PermissionPolicy(), middleware=middleware)

    def _context(self, runtime: AgentRuntime):
        return runtime.build_context("task", base_context=StrategyContext(), history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())

    async def test_retry_and_record_see_the_models_arguments_after_the_tool_consumed_them(self) -> None:
        tool = ConsumingTool()
        runner = FakeRunner(
            [
                FakeResponse({"output": [{"type": "function_call", "name": "fetch_report", "arguments": '{"path": "q3.pdf", "pages": [3, 1, 2]}', "call_id": "fc_report"}]}),
                FakeResponse({"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}', "call_id": "fc_done"}]}),
            ]
        )
        middleware = ToolErrorPolicyMiddleware(ToolErrorPolicy(max_retries_per_tool_call=1, retry_backoff_base_seconds=0))
        runtime = self._runtime(Tools([tool]), (middleware,))

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=self._context(runtime),
        )

        self.assertEqual(result.output, "done")
        self.assertEqual(tool.seen_paths, ["q3.pdf", "q3.pdf"])
        recorded = [dict(context.arguments) for context in result.metadata["tool_calls"] if context.tool_name == "fetch_report"]
        self.assertEqual(recorded, [MODEL_ARGUMENTS])
        model_saw = str(runner.calls[1]["kwargs"]["messages"])
        self.assertIn("revenue for q3.pdf pages [1, 2, 3]", model_saw)
        self.assertNotIn("invalid_arguments", model_saw)

    async def test_call_holding_a_value_deepcopy_rejects_still_executes(self) -> None:
        runtime = self._runtime(Tools([UncopyableArgumentTool()]))
        call = ToolCall("use_handle", {"path": "q3.pdf", "handle": Uncopyable()})

        _, result = await runtime.execute_tool_call(call, provider="openai")

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.output, "q3.pdf via Uncopyable")
        self.assertEqual(call.arguments["path"], "q3.pdf")


if __name__ == "__main__":
    unittest.main()
