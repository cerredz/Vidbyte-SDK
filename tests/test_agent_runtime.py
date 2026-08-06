"""Context Protocol Header

Description:
    Unit tests for all agent runtime execution loops (Linear and non-linear).
Purpose:
    Verifies correct runtime behavior, dispatch, fail-fast gating, and parameter validation.
Architecture:
    - FakeRunner & FakeResponse: Mocks model interaction for checking agent decision cycles.
    - AgentRuntimeTests: TestCase verifying token budgeting, rate limiting, and algorithm execution.
    - CountingSearchTool & ActivityRecordingMiddleware: Priced tool and middleware probe
      used by ToolActivityRuntimeTests.
    - ToolActivityRuntimeTests: TestCase verifying activity capture, policy inputs, and metering.
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
from typing import Literal

from pydantic import BaseModel, Field

from vidbyte.agents import AgentRuntime
from vidbyte.agents.settings.tool import ToolSettings
from vidbyte.lib.dataclasses.middleware import MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware
from vidbyte.tools import ToolActivity, ToolParameter
from vidbyte.tools.builtins.operations.base import PricedOperationTool
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


class SearchActivity(BaseModel):
    """Bounded search annotation used by the tool-activity runtime tests."""

    kind: Literal["explore", "target_gap"]
    purpose: str = Field(min_length=1, max_length=60)


class CountingSearchTool(PricedOperationTool):
    """Priced search tool that records the business arguments it executed against."""

    operation = "search"
    provider = "brave"

    def __init__(self) -> None:
        """Start with an empty execution log and no provider client."""
        super().__init__(client=None)
        self.executed_arguments: list[dict] = []

    def spec(self) -> ToolSpec:
        """Return a single-argument search spec."""
        return ToolSpec(
            name="counting_search",
            description="Runs a counted search.",
            parameters=(ToolParameter("query", "string", "The search query."),),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Record the executed arguments and return one priced contract result."""
        self.executed_arguments.append(dict(call.arguments))
        return self._contract_result(f"searched: {call.arguments.get('query', '')}", units=1)


class ActivityRecordingMiddleware(AgentMiddleware):
    """Captures the prepared call each tool hook observes."""

    def __init__(self) -> None:
        """Start with empty capture logs for both tool hooks."""
        self.before_payloads: list[dict] = []
        self.after_payloads: list[dict] = []
        self.before_arguments: list[dict] = []

    async def before_tool_call(self, ctx) -> MiddlewareDecision:
        """Record the annotation and business arguments seen before execution."""
        if ctx.tool_call is not None and ctx.tool_call.activity is not None:
            self.before_payloads.append(dict(ctx.tool_call.activity.payload))
            self.before_arguments.append(dict(ctx.tool_call.arguments))
        return MiddlewareDecision.continue_()

    async def after_tool_call(self, ctx) -> MiddlewareDecision:
        """Record the annotation still attached to the call after execution."""
        if ctx.tool_call is not None and ctx.tool_call.activity is not None:
            self.after_payloads.append(dict(ctx.tool_call.activity.payload))
        return MiddlewareDecision.continue_()


class DenyingMiddleware(AgentMiddleware):
    """Denies every non-internal tool call so denied-context behavior can be asserted."""

    async def before_tool_call(self, ctx) -> MiddlewareDecision:
        """Deny the call unless it targets a runtime-internal tool."""
        if ctx.tool_is_internal:
            return MiddlewareDecision.continue_()
        return MiddlewareDecision.deny_tool("policy")


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

        visible_tool_message = runner.calls[1]["kwargs"]["messages"][0]
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


class ToolActivityRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Verifies runtime capture, policy inputs, and priced-tool preservation for activities."""

    def _annotated_search(self) -> tuple[CountingSearchTool, object]:
        """Return a priced counting search tool and the same tool bound to a search activity."""
        tool = CountingSearchTool()
        activity = ToolActivity(
            schema=SearchActivity,
            description="Classify the research action this search advances.",
            metadata={"schema_version": 1},
        )
        return tool, tool.with_activity(activity)

    def _runtime(self, bound_tool: object, middleware: list, *, tool_settings: object = None) -> AgentRuntime:
        """Build a linear runtime around one bound tool and the supplied middleware."""
        return AgentRuntime(
            agent_name="researcher",
            system_prompt="Research.",
            tools=Tools([bound_tool]),
            permission_policy=PermissionPolicy(),
            middleware=middleware,
            config=AgentRuntimeConfig(tool_settings=tool_settings) if tool_settings is not None else None,
        )

    async def _run(self, runtime: AgentRuntime, responses: list) -> object:
        """Execute the runtime against a scripted fake runner and return its result."""
        runner = FakeRunner(responses)
        context = runtime.build_context("task", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())
        return await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=context,
        )

    @staticmethod
    def _search_response(arguments: str) -> FakeResponse:
        """Script one provider tool call against the counting search tool."""
        return FakeResponse("", {"output": [{"type": "function_call", "name": "counting_search", "arguments": arguments}]})

    @staticmethod
    def _done_response() -> FakeResponse:
        """Script the runtime's internal completion tool call."""
        return FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}'}]})

    async def test_middleware_and_context_receive_the_normalized_activity(self) -> None:
        """Middleware sees the prepared call and the final context retains the annotation."""
        tool, bound = self._annotated_search()
        recorder = ActivityRecordingMiddleware()
        runtime = self._runtime(bound, [recorder])

        result = await self._run(
            runtime,
            [self._search_response('{"query": "spaced repetition", "activity": {"kind": "explore", "purpose": "survey"}}'), self._done_response()],
        )

        self.assertEqual(recorder.before_payloads, [{"kind": "explore", "purpose": "survey"}])
        self.assertEqual(recorder.after_payloads, [{"kind": "explore", "purpose": "survey"}])
        self.assertEqual(recorder.before_arguments, [{"query": "spaced repetition"}])
        self.assertEqual(tool.executed_arguments, [{"query": "spaced repetition"}])
        search_context = next(ctx for ctx in result.metadata["tool_calls"] if ctx.tool_name == "counting_search")
        self.assertEqual(dict(search_context.activity.payload), {"kind": "explore", "purpose": "survey"})
        self.assertEqual(dict(search_context.arguments), {"query": "spaced repetition"})

    async def test_identical_call_policy_ignores_the_activity(self) -> None:
        """Changing only the explanation cannot bypass the identical-call budget."""
        _, bound = self._annotated_search()
        runtime = self._runtime(bound, [], tool_settings=ToolSettings(max_identical_calls=1))

        result = await self._run(
            runtime,
            [
                self._search_response('{"query": "same", "activity": {"kind": "explore", "purpose": "first"}}'),
                self._search_response('{"query": "same", "activity": {"kind": "target_gap", "purpose": "second"}}'),
                self._done_response(),
            ],
        )

        self.assertEqual(result.metadata["tool_settings_budget"], "max_identical_calls")

    async def test_denied_call_retains_its_activity(self) -> None:
        """A middleware-denied call keeps the annotation so a product can say the action was blocked."""
        tool, bound = self._annotated_search()
        runtime = self._runtime(bound, [DenyingMiddleware()])

        result = await self._run(
            runtime,
            [self._search_response('{"query": "blocked", "activity": {"kind": "target_gap", "purpose": "fill gap"}}'), self._done_response()],
        )

        denied = next(ctx for ctx in result.metadata["tool_calls"] if ctx.tool_name == "counting_search")
        self.assertEqual(denied.state.value, "denied")
        self.assertEqual(dict(denied.activity.payload), {"kind": "target_gap", "purpose": "fill gap"})
        self.assertEqual(tool.executed_arguments, [])

    async def test_activity_bound_priced_tool_stays_metered(self) -> None:
        """A priced tool keeps its operation accounting behind an activity binding."""
        _, bound = self._annotated_search()
        runtime = self._runtime(bound, [])

        await self._run(
            runtime,
            [self._search_response('{"query": "retention", "activity": {"kind": "explore", "purpose": "survey"}}'), self._done_response()],
        )

        operations = runtime.usage_tracker.operations
        self.assertEqual(len(operations), 1)
        self.assertEqual((operations[0].operation, operations[0].provider), ("search", "brave"))

    async def test_invalid_activity_fails_before_the_priced_provider_runs(self) -> None:
        """A schema-invalid annotation produces a failed call without spending an operation."""
        tool, bound = self._annotated_search()
        runtime = self._runtime(bound, [])

        result = await self._run(
            runtime,
            [self._search_response('{"query": "retention", "activity": {"kind": "not_a_kind"}}'), self._done_response()],
        )

        self.assertEqual(tool.executed_arguments, [])
        self.assertEqual(runtime.usage_tracker.operations, ())
        self.assertEqual(result.metadata["tool_call_states"], ("failed", "succeeded"))


if __name__ == "__main__":
    unittest.main()

