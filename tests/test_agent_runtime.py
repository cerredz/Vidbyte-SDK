from __future__ import annotations

import unittest

from vidbyte.agents.runtime import AgentRuntime
from vidbyte.agents.types import AgentMessage
from vidbyte.context import ContextArtifact, ContextPermissions, ContextResponse, ContextToolCall, ContextWindow, TaskContextItem
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.enums import ModelModality
from vidbyte.strategies import StrategyContext
from vidbyte.tools import BaseTool, ToolCall, ToolCallContext, ToolPermission, ToolResult, ToolSpec, Tools, tool
from vidbyte.tools.security import PermissionPolicy


class FakeResponse:
    def __init__(self, text: str, raw: dict) -> None:
        self.text = text
        self.raw = raw


class FakeRunner:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []


class WriteTool(BaseTool):
    def __init__(self) -> None:
        self.executed = False

    def spec(self) -> ToolSpec:
        return ToolSpec(name="write", description="Write data.", permission=ToolPermission.WRITE)

    async def execute(self, call: ToolCall) -> ToolResult:
        self.executed = True
        return ToolResult.success("write", "wrote")


async def invoke_runner(runner: FakeRunner, prompt: str, **kwargs: object) -> FakeResponse:
    runner.calls.append({"prompt": prompt, "kwargs": kwargs})
    return runner.responses.pop(0)


def runner_output_text(response: object) -> str:
    return str(getattr(response, "text", response))


def runner_output_metadata(response: object) -> dict:
    return dict(getattr(response, "metadata", {}))


class AgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def test_runtime_builds_context_with_agent_history_and_metadata(self) -> None:
        existing_call = ToolCallContext(
            tool_name="lookup",
            result=ToolResult.success("lookup", "ok"),
        )
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Agent system.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
        )
        context = runtime.build_context(
            "task",
            base_context=StrategyContext(
                metadata={"caller": "yes"},
                strategy_metadata={"phase": "draft"},
                tool_calls=[ContextToolCall(name="base_tool", output="base")],
                responses=[ContextResponse(content="response body")],
                artifacts=[ContextArtifact(name="artifact", content="artifact body")],
                memory="prior summary",
                permissions=ContextPermissions(can_read_files=True),
                context_items=[TaskContextItem(goal="preserve context")],
            ),
            history=[AgentMessage(sender="user", recipient="worker", content="external")],
            agent_history=[AgentMessage(sender="worker", recipient="user", content="prior")],
            agent_metadata={"agent": "meta"},
            existing_tool_calls=[existing_call],
            input_metadata={"input": "meta"},
            modality=ModelModality.TEXT,
        )

        self.assertIn("Agent system.", context.system_prompt)
        self.assertIn("agentic loop", context.system_prompt)
        self.assertEqual([message.content for message in context.history], ["external", "prior"])
        self.assertEqual(context.metadata["caller"], "yes")
        self.assertEqual(context.metadata["agent"], "meta")
        self.assertEqual(context.metadata["input"], "meta")
        self.assertEqual(context.metadata["modality"], "text")
        self.assertEqual(context.strategy_metadata, {"phase": "draft"})
        self.assertEqual(tuple(call.name for call in context.tool_calls), ("base_tool", "lookup"))
        self.assertEqual(context.responses[0].content, "response body")
        self.assertEqual(context.artifacts[0].content, "artifact body")
        self.assertEqual(context.memory, "prior summary")
        self.assertTrue(context.permissions.can_read_files)
        self.assertEqual(context.context_items[0].goal, "preserve context")
        self.assertEqual(tuple(tool.name for tool in context.tools), ("isDone",))

    def test_runtime_builds_non_agentic_context_without_internal_tools(self) -> None:
        @tool
        def lookup() -> str:
            return "ok"

        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Agent system.",
            tools=Tools([lookup]),
            permission_policy=PermissionPolicy(),
        )
        context = runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
            agentic_loop=False,
        )

        self.assertEqual(context.system_prompt, "Agent system.")
        self.assertNotIn("agentic loop", context.system_prompt)
        self.assertEqual(tuple(tool.name for tool in context.tools), ("lookup",))

    async def test_runtime_executes_tool_call_and_continues_to_final_response(self) -> None:
        @tool
        def lookup(topic: str) -> str:
            """Look up a topic."""
            return f"found:{topic}"

        runner = FakeRunner(
            [
                FakeResponse(
                    "",
                    {
                        "output": [
                            {
                                "type": "function_call",
                                "name": "lookup",
                                "arguments": '{"topic": "sdk"}',
                                "call_id": "call_1",
                            }
                        ]
                    },
                ),
                FakeResponse(
                    "",
                    {
                        "output": [
                            {
                                "type": "function_call",
                                "name": "isDone",
                                "arguments": '{"final_answer": "final answer"}',
                                "call_id": "call_2",
                            }
                        ]
                    },
                ),
            ]
        )
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools([lookup]),
            permission_policy=PermissionPolicy(),
        )
        context = runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        result = await runtime.arun(
            "task",
            runner=runner,
            context=context,
            provider="openai",
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
        )

        self.assertEqual(result.output, "final answer")
        self.assertEqual(result.metadata["stop_reason"], "is_done")
        self.assertEqual(result.metadata["iteration_count"], 2)
        self.assertEqual(result.metadata["tool_call_count"], 2)
        self.assertEqual(result.metadata["tool_call_states"], ("succeeded", "succeeded"))
        self.assertIn("middleware", result.metadata)
        self.assertIn("tools", runner.calls[0]["kwargs"])
        self.assertIn("messages", runner.calls[1]["kwargs"])

    async def test_runtime_context_algorithm_hides_raw_tool_output_from_messages(self) -> None:
        @tool
        def lookup(topic: str) -> str:
            """Look up a topic."""
            return f"raw secret result for {topic}"

        runner = FakeRunner(
            [
                FakeResponse(
                    "",
                    {
                        "output": [
                            {
                                "type": "function_call",
                                "name": "lookup",
                                "arguments": '{"topic": "sdk"}',
                                "call_id": "call_1",
                            }
                        ]
                    },
                ),
                FakeResponse(
                    "",
                    {
                        "output": [
                            {
                                "type": "function_call",
                                "name": "isDone",
                                "arguments": '{"final_answer": "final answer"}',
                                "call_id": "call_2",
                            }
                        ]
                    },
                ),
            ]
        )
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools([lookup]),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindow.preset.no_raw_tool_outputs,
        )
        context = runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        result = await runtime.arun(
            "task",
            runner=runner,
            context=context,
            provider="openai",
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
        )

        visible_tool_message = runner.calls[1]["kwargs"]["messages"][0]
        self.assertNotIn("raw secret result", visible_tool_message["content"])
        self.assertIn("Raw tool output was withheld", visible_tool_message["content"])
        raw_context = result.metadata["tool_calls"][0]
        self.assertEqual(raw_context.result.output, "raw secret result for sdk")

    async def test_runtime_denies_write_tool_by_default(self) -> None:
        write_tool = WriteTool()
        runner = FakeRunner(
            [
                FakeResponse(
                    "",
                    {"output": [{"type": "function_call", "name": "write", "arguments": "{}"}]},
                ),
                FakeResponse(
                    "",
                    {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "handled"}'}]},
                ),
            ]
        )
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools([write_tool]),
            permission_policy=PermissionPolicy(),
        )
        context = runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        result = await runtime.arun(
            "task",
            runner=runner,
            context=context,
            provider="openai",
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
        )

        self.assertFalse(write_tool.executed)
        self.assertEqual(result.metadata["tool_call_states"], ("denied", "succeeded"))

    async def test_runtime_records_unknown_tool_as_failed_context(self) -> None:
        runner = FakeRunner(
            [
                FakeResponse(
                    "",
                    {"output": [{"type": "function_call", "name": "missing", "arguments": "{}"}]},
                ),
                FakeResponse(
                    "",
                    {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "handled"}'}]},
                ),
            ]
        )
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
        )
        context = runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        result = await runtime.arun(
            "task",
            runner=runner,
            context=context,
            provider="openai",
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
        )

        self.assertEqual(result.metadata["tool_call_states"], ("failed", "succeeded"))

    async def test_runtime_stops_at_max_iterations(self) -> None:
        @tool
        def lookup() -> str:
            return "again"

        runner = FakeRunner(
            [
                FakeResponse("", {"output": [{"type": "function_call", "name": "lookup", "arguments": "{}"}]}),
                FakeResponse("should not be used", {"output_text": "should not be used"}),
            ]
        )
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools([lookup]),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(max_iterations=1),
        )
        context = runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        result = await runtime.arun(
            "task",
            runner=runner,
            context=context,
            provider="openai",
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
        )

        self.assertEqual(result.metadata["stop_reason"], "max_iterations")
        self.assertEqual(result.metadata["iteration_count"], 1)
        self.assertEqual(len(runner.calls), 1)

    async def test_runtime_stops_at_max_tokens_from_provider_usage(self) -> None:
        runner = FakeRunner([FakeResponse("working", {"usage": {"total_tokens": 4}})])
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(max_tokens=1),
        )
        context = runtime.build_context(
            "long task that exceeds the tiny token estimate",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        result = await runtime.arun(
            "long task that exceeds the tiny token estimate",
            runner=runner,
            context=context,
            provider="openai",
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
        )

        self.assertEqual(result.metadata["stop_reason"], "max_tokens")
        self.assertEqual(result.metadata["iteration_count"], 1)
        self.assertEqual(result.metadata["tokens_used"], 4)
        self.assertEqual(len(runner.calls), 1)

    async def test_runtime_without_limits_continues_until_final_response(self) -> None:
        @tool
        def lookup() -> str:
            return "again"

        runner = FakeRunner(
            [
                FakeResponse("", {"output": [{"type": "function_call", "name": "lookup", "arguments": "{}"}]}),
                FakeResponse("", {"output": [{"type": "function_call", "name": "lookup", "arguments": "{}"}]}),
                FakeResponse(
                    "",
                    {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}'}]},
                ),
            ]
        )
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools([lookup]),
            permission_policy=PermissionPolicy(),
        )
        context = runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        result = await runtime.arun(
            "task",
            runner=runner,
            context=context,
            provider="openai",
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
        )

        self.assertEqual(result.output, "done")
        self.assertEqual(result.metadata["iteration_count"], 3)
        self.assertEqual(result.metadata["tool_call_count"], 3)

    async def test_runtime_continues_when_response_has_no_tool_calls(self) -> None:
        runner = FakeRunner(
            [
                FakeResponse("partial work", {"output_text": "partial work"}),
                FakeResponse(
                    "",
                    {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}'}]},
                ),
            ]
        )
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
        )
        context = runtime.build_context(
            "task",
            base_context=None,
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

        result = await runtime.arun(
            "task",
            runner=runner,
            context=context,
            provider="openai",
            invoke_runner=invoke_runner,
            runner_output_text=runner_output_text,
            runner_output_metadata=runner_output_metadata,
        )

        self.assertEqual(result.output, "done")
        self.assertEqual(result.metadata["iteration_count"], 2)
        self.assertEqual(runner.calls[1]["kwargs"]["messages"][0]["content"], "partial work")


if __name__ == "__main__":
    unittest.main()
