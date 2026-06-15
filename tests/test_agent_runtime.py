"""Context Protocol Header

Description:
    Unit tests for all agent runtime execution loops (Linear and non-linear).
Purpose:
    Verifies correct runtime behavior, dispatch, fail-fast gating, and parameter validation.
Architecture:
    - FakeRunner & FakeResponse: Mocks model interaction for checking agent decision cycles.
    - AgentRuntimeTests: TestCase verifying token budgeting, rate limiting, and algorithm execution.
Key Functions:
    - test_inner_context_window_lifecycle_writes_to_next_system_context: Validates trajectory algorithm integration.
    - test_runtime_denies_write_tool_by_default: Validates security middleware defaults.
Relations:
    Tests `AgentRuntime` in `vidbyte/agents/runtime.py` and its interaction with context algorithms.
Similar Files:
    - `tests/test_trajectory_checkpoint_algorithm.py`
"""

from __future__ import annotations

import unittest

from vidbyte.agents import AgentRuntime
from vidbyte.agents.types import AgentMessage
from vidbyte.context import ContextArtifact, ContextPermissions, ContextResponse, ContextToolCall, ContextWindow, ContextWindowAlgorithm, TaskContextItem, TrajectoryCheckpointAlgorithm
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.enums import ModelModality
from vidbyte.lib.dataclasses.context import BaseContext as StrategyContext
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
                run_metadata={"phase": "draft"},
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
        self.assertEqual(context.run_metadata, {"phase": "draft"})
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
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=context,
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
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=context,
        )

        sent_messages = runner.calls[1]["kwargs"]["messages"]
        visible_tool_message = next(m for m in sent_messages if m.get("role") == "tool")
        self.assertNotIn("raw secret result", visible_tool_message["content"])
        self.assertIn("Raw tool output was withheld", visible_tool_message["content"])
        raw_context = result.metadata["tool_calls"][0]
        self.assertEqual(raw_context.result.output, "raw secret result for sdk")

    async def test_inner_context_window_lifecycle_writes_to_next_system_context(self) -> None:
        json_output = '{"reasoning_summary": "res", "trajectory": "traj", "output": "out", "score": 0.85, "feedback": "feed"}'
        runner = FakeRunner(
            [
                FakeResponse("draft", {}),
                FakeResponse(json_output, {}),
                FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}'}]}),
            ]
        )
        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools(),
            permission_policy=PermissionPolicy(),
            algorithm=ContextWindowAlgorithm(name="trajectory_checkpoints", trajectory_checkpoints=TrajectoryCheckpointAlgorithm(interval=1)),
        )
        context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=context,
        )

        self.assertIn("Runtime Checkpoint", runner.calls[2]["kwargs"]["system"])
        self.assertEqual(runner.calls[2]["kwargs"]["messages"][0]["content"], "draft")
        self.assertEqual(result.metadata["trajectory_checkpoints"]["checkpoint_count"], 1)

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
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=context,
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
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=context,
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
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=context,
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
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=context,
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
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=context,
        )

        self.assertEqual(result.output, "done")
        self.assertEqual(result.metadata["iteration_count"], 3)
        self.assertEqual(result.metadata["tool_call_count"], 3)

    async def test_runtime_finishes_when_response_has_no_tool_calls(self) -> None:
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
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=context,
        )

        self.assertEqual(result.output, "partial work")
        self.assertEqual(result.metadata["stop_reason"], "final_response")
        self.assertEqual(result.metadata["iteration_count"], 1)
        self.assertEqual(len(runner.calls), 1)


    def test_agent_runtime_fail_fast(self) -> None:
        # [Edge Case] Ensure non-linear runtimes instantiate successfully with default settings.
        from vidbyte.agents.base import BaseAgent
        from vidbyte.lib.enums import AgentRuntimeType
        from vidbyte.lib.errors import ConfigurationError

        agent = BaseAgent(
            name="searcher",
            system_prompt="Heuristic finder.",
            runtime=AgentRuntimeType.MCTS_SEARCH,
        )
        self.assertEqual(agent.runtime_type, AgentRuntimeType.MCTS_SEARCH)

        # [Hidden Failure] Ensure passing active middleware list raises ConfigurationError immediately.
        class DummyMiddleware:
            pass

        with self.assertRaises(ConfigurationError) as ctx:
            BaseAgent(
                name="bad_searcher",
                system_prompt="Fail fast.",
                runtime="mcts_search",
                middleware=[DummyMiddleware()],
            )
        self.assertIn("does not support middleware", str(ctx.exception))

        # [Silent Failure] Ensure passing non-default context algorithm preset raises ConfigurationError immediately.
        from vidbyte.context.presets import ContextWindowPresets
        with self.assertRaises(ConfigurationError) as ctx:
            BaseAgent(
                name="bad_actor",
                system_prompt="Fail fast.",
                runtime=AgentRuntimeType.ACTOR_MODEL,
                algorithm=ContextWindowPresets().compact_tool_outputs,
            )
        self.assertIn("does not support in-context learning algorithms", str(ctx.exception))

        # [Hidden Assumption] Ensure a string "actor_model" is correctly coerced and validates.
        with self.assertRaises(ConfigurationError) as ctx:
            BaseAgent(
                name="bad_actor_str",
                system_prompt="Fail fast.",
                runtime="actor_model",
                algorithm=ContextWindowPresets().compact_tool_outputs,
            )
        self.assertIn("does not support in-context learning algorithms", str(ctx.exception))

    def test_runtime_dispatch(self) -> None:
        # [Edge Case] Ensure the correct runtime component classes are instantiated dynamically.
        from vidbyte.agents.base import BaseAgent
        from vidbyte.lib.enums import AgentRuntimeType
        from vidbyte.agents.runtimes.linear import AgentRuntime as LinearAgentRuntime
        from vidbyte.agents.runtimes.search import SearchTreeRuntimeComponent
        from vidbyte.agents.runtimes.actor.broker import PointToPointActorRuntime

        linear_agent = BaseAgent(name="l", system_prompt="L", runtime=AgentRuntimeType.LINEAR)
        self.assertIsInstance(linear_agent._runtime(), LinearAgentRuntime)

        search_agent = BaseAgent(name="s", system_prompt="S", runtime=AgentRuntimeType.MCTS_SEARCH)
        self.assertIsInstance(search_agent._runtime(), SearchTreeRuntimeComponent)

        actor_agent = BaseAgent(name="a", system_prompt="A", runtime=AgentRuntimeType.ACTOR_MODEL)
        self.assertIsInstance(actor_agent._runtime(), PointToPointActorRuntime)


if __name__ == "__main__":
    unittest.main()

