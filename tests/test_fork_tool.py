from __future__ import annotations

import unittest
from typing import Any

from tests.agent_test_support import build_test_agent
from vidbyte.agents import AgentForkSettings, AgentMessage, BaseAgent
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.context.handoff import EngineeringHandoff
from vidbyte.lib.config import ModelProvider
from vidbyte.lib.runners import TextModelResponse
from vidbyte.tools.base import BaseTool
from vidbyte.tools.builtins.fork import ForkConversationTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.types import ToolCall, ToolResult, ToolSpec, ToolStatus


class DoneRunner:
    """Runner that immediately terminates the agent loop."""

    def run(self, prompt: str, *, system: str | None = None, **_: object) -> TextModelResponse:
        # Returns an isDone call so the agent can complete without a provider.
        del system
        return TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="", raw={"output": [{"type": "function_call", "name": "isDone", "arguments": f'{{"final_answer": "child:{prompt}"}}'}]})


class NamedTool(BaseTool):
    """Minimal executable tool used for catalog and subset tests."""

    def __init__(self, name: str) -> None:
        # Stores the stable model-facing tool name.
        self._name = name

    def spec(self) -> ToolSpec:
        # Returns the tool declaration used by Tools.
        return ToolSpec(name=self._name, description=f"{self._name} tool")

    async def execute(self, call: ToolCall) -> ToolResult:
        # Returns a simple success result for completeness.
        return ToolResult.success(call.tool_name, "ok")


class StubChild:
    """Child agent returned by StubAgent.fork for fork tool unit tests."""

    def __init__(self) -> None:
        # Provides the fields ForkConversationTool includes in result metadata.
        self.name = "stub-child"
        self.runner_config = type("RunnerConfig", (), {"run_id": "child-run"})()
        self.metadata = {"forked_from": "parent-run", "fork_depth": 1}
        self.prompts: list[str] = []

    async def generate_reply(self, prompt: str) -> AgentMessage:
        # Records the prompt and returns a deterministic child answer.
        self.prompts.append(prompt)
        return AgentMessage(sender=self.name, recipient="parent", content=f"answer:{prompt}")


class StubAgent:
    """Parent-like object with the attributes ForkConversationTool needs."""

    def __init__(self) -> None:
        # Creates parent state and captures fork kwargs for assertions.
        self.history = [
            AgentMessage(sender="a", recipient="parent", content="one"),
            AgentMessage(sender="b", recipient="parent", content="two"),
            AgentMessage(sender="c", recipient="parent", content="three"),
        ]
        self.metadata = {"fork_depth": 0}
        self.agent_loop_settings = AgentLoopSettings(max_iterations=3)
        self.tools = Tools([NamedTool("alpha"), NamedTool("beta")])
        self.captured: AgentForkSettings | None = None
        self.child = StubChild()

    def fork(self, settings: AgentForkSettings) -> StubChild:
        # Captures the requested fork settings and returns a fake runnable child.
        self.captured = settings
        return self.child


def _call(**arguments: object) -> ToolCall:
    # Builds a fork_conversation ToolCall from keyword arguments.
    return ToolCall(tool_name="fork_conversation", arguments=dict(arguments))


class ToolsSubsetTests(unittest.TestCase):
    def test_subset_preserves_catalog_order_and_errors_on_unknown_names(self) -> None:
        # Tools.subset should return exactly requested known tools in existing catalog order.
        catalog = Tools([NamedTool("a"), NamedTool("b"), NamedTool("c")])
        self.assertEqual(catalog.subset(["c", "a"]).names(), ("a", "c"))
        with self.assertRaises(Exception) as ctx:
            catalog.subset(["missing"])
        self.assertIn("missing", str(ctx.exception))


class ForkConversationToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_runs_bound_agent_fork_successfully(self) -> None:
        # A real BaseAgent should bind the fork tool and return the child reply plus lineage metadata.
        tool = ForkConversationTool()
        agent = build_test_agent(name="parent", system_prompt="Work.", runner=DoneRunner(), tools=[tool], run_id="parent-run")
        agent.history.append(AgentMessage(sender="user", recipient="parent", content="context"))

        result = await tool.execute(_call(prompt="solve it", name="child", purpose="branch"))

        self.assertIs(tool._agent, agent)
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertIn("child:solve it", result.output)
        self.assertEqual(result.metadata["forked_from"], "parent-run")
        self.assertEqual(result.metadata["fork_depth"], 1)
        self.assertEqual(result.metadata["name"], "child")

    async def test_history_last_n_and_tool_names_translate_to_fork_kwargs(self) -> None:
        # The tool should slice history and resolve tool_names before calling parent.fork().
        agent = StubAgent()
        tool = ForkConversationTool(extra_toolsets={"extra": Tools([NamedTool("gamma")])})
        tool.bind_agent(agent)

        result = await tool.execute(_call(prompt="branch", history_mode="last_n", last_n=2, tool_names=["beta", "gamma"]))

        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual([msg.content for msg in agent.captured.history], ["two", "three"])
        self.assertEqual(agent.captured.tools.names(), ("beta", "gamma"))

    async def test_sdk_native_fork_options_translate_to_fork_kwargs(self) -> None:
        # The model-facing tool should expose Vidbyte-native fork knobs, not only generic prompt/tools/model.
        agent = StubAgent()
        tool = ForkConversationTool(allowed_models=("gpt-4.1-mini",), extra_toolsets={"extra": Tools([NamedTool("gamma")])})
        tool.bind_agent(agent)

        result = await tool.execute(_call(
            prompt="branch",
            context_window={
                "history_mode": "none",
                "algorithm": "compact_tool_outputs",
                "budget_tokens": 1000,
                "compaction_trigger_tokens": 900,
                "compaction_target_tokens": 400,
            },
            extra_toolset_names=["extra"],
            drop_tool_names=["beta"],
            model="gpt-4.1-mini",
            provider="openai",
            temperature=0.4,
            runtime="linear",
            loop_settings={"max_tool_calls": 2, "allowed_tools": ["alpha"]},
            handoff={"preset": "engineering", "title": "Child Handoff"},
            output_schema={"type": "object"},
            include_run_state=True,
            mcp=False,
            metadata={"branch": "sdk-native"},
            run_id="child-run-explicit",
        ))

        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(agent.captured.history, [])
        self.assertEqual(agent.captured.tools.names(), ("alpha", "gamma"))
        self.assertEqual(agent.captured.model_name, "gpt-4.1-mini")
        self.assertEqual(agent.captured.provider, "openai")
        self.assertEqual(agent.captured.temperature, 0.4)
        self.assertEqual(agent.captured.runtime, "linear")
        self.assertEqual(agent.captured.algorithm, "compact_tool_outputs")
        self.assertIsInstance(agent.captured.handoff, EngineeringHandoff)
        self.assertEqual(agent.captured.handoff.title, "Child Handoff")
        self.assertEqual(agent.captured.output_schema, {"type": "object"})
        self.assertTrue(agent.captured.include_run_state)
        self.assertFalse(agent.captured.mcp)
        self.assertEqual(agent.captured.metadata, {"branch": "sdk-native"})
        self.assertEqual(agent.captured.run_id, "child-run-explicit")
        settings = agent.captured.agent_loop_settings
        self.assertEqual(settings.max_iterations, 3)
        self.assertEqual(settings.max_tool_calls, 2)
        self.assertEqual(settings.allowed_tools, ("alpha",))
        self.assertEqual(settings.context_window_budget, 1000)
        self.assertEqual(settings.compaction_trigger_tokens, 900)
        self.assertEqual(settings.compaction_target_tokens, 400)

    async def test_unknown_context_algorithm_returns_tool_error(self) -> None:
        # SDK-native preset inputs should be constrained to names Vidbyte recognizes.
        agent = StubAgent()
        tool = ForkConversationTool()
        tool.bind_agent(agent)

        result = await tool.execute(_call(prompt="branch", context_algorithm="not-a-preset"))

        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("context_algorithm", result.output)

    async def test_disallowed_model_returns_tool_error(self) -> None:
        # Model overrides must be rejected unless explicitly allow-listed by the developer.
        agent = StubAgent()
        tool = ForkConversationTool(allowed_models=("allowed",))
        tool.bind_agent(agent)

        result = await tool.execute(_call(prompt="branch", model="blocked"))

        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("allowed_models", result.output)

    async def test_max_iterations_cannot_exceed_parent_cap(self) -> None:
        # The child loop budget must not exceed the parent's configured max_iterations.
        agent = StubAgent()
        tool = ForkConversationTool()
        tool.bind_agent(agent)

        result = await tool.execute(_call(prompt="branch", max_iterations=4))

        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("parent cap", result.output)

    async def test_depth_cap_prevents_recursive_fork_construction(self) -> None:
        # Depth cap should be checked before parent.fork is called.
        agent = StubAgent()
        agent.metadata["fork_depth"] = 2
        tool = ForkConversationTool(max_fork_depth=2)
        tool.bind_agent(agent)

        result = await tool.execute(_call(prompt="branch"))

        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("depth cap", result.output)
        self.assertIsNone(agent.captured)

    async def test_missing_prompt_returns_tool_error(self) -> None:
        # Required-argument validation should return ToolResult.error instead of raising.
        agent = StubAgent()
        tool = ForkConversationTool()
        tool.bind_agent(agent)

        result = await tool.execute(_call(prompt=" "))

        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("prompt", result.output)


if __name__ == "__main__":
    unittest.main()
