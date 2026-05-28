from __future__ import annotations

import unittest

from vidbyte.agents import AgentInput, BaseAgent
from vidbyte.agents.base import ConfiguredAgentRunner
from vidbyte.context import ContextManager, ContextWindow, TaskContextItem, TextContextItem
from vidbyte.lib.config import ModelProvider
from vidbyte.middleware import AgentMiddleware
from vidbyte.lib.errors import AgentExecutionError
from vidbyte.lib.runners import TextModelResponse
from vidbyte.tools import ToolSpec


class FakeTool:
    def spec(self) -> ToolSpec:
        return ToolSpec(name="lookup", description="Lookup things")


class EchoRunner:
    def __init__(self) -> None:
        self.system = None

    def run(self, prompt: str, *, system: str | None = None, **_: object) -> object:
        self.system = system
        return FakeResponse(
            "",
            {"output": [{"type": "function_call", "name": "isDone", "arguments": f'{{"final_answer": "direct:{prompt}"}}'}]},
        )


class FakeResponse:
    def __init__(self, text: str, raw: dict) -> None:
        self.text = text
        self.raw = raw


class FakeMiddleware(AgentMiddleware):
    pass


class TextRunner:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.systems: list[str | None] = []

    def run(self, prompt: str, *, system: str | None = None, **_: object) -> TextModelResponse:
        self.prompts.append(prompt)
        self.systems.append(system)
        return TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="Final answer: OK", raw={})


class AgentBaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_card_and_generate_reply_pass_tools(self) -> None:
        tool = FakeTool()
        agent = BaseAgent(
            name="worker",
            system_prompt="Work carefully.",
            runner=EchoRunner(),
            tools=[tool],
            capabilities=["search"],
        )

        card = agent.card()
        self.assertEqual(card.name, "worker")
        self.assertEqual(card.tool_names, ("lookup",))
        self.assertEqual(card.capabilities, ("search",))

        reply = await agent.generate_reply("task")
        self.assertIn("direct:task", reply.content)
        self.assertEqual(reply.metadata["modality"], "text")

    async def test_runner_config_tool_helpers_and_fork(self) -> None:
        tool = FakeTool()
        agent = BaseAgent.from_run_id(
            "run-123",
            name="researcher",
            system_prompt="Research carefully.",
            model_name="model-a",
            temperature=0.2,
            tools=[tool],
            metadata={"role": "custom_researcher"},
        )

        self.assertIsInstance(agent.runner, ConfiguredAgentRunner)
        self.assertEqual(agent.tool_specs()[0].name, "lookup")
        agent.add_tool(object())
        self.assertEqual(agent.card().tool_names, ("lookup", "object"))

        forked = agent.fork(name="researcher-copy", metadata={"branch": "copy"})
        self.assertEqual(forked.name, "researcher-copy")
        self.assertEqual(forked.metadata["role"], "custom_researcher")
        self.assertEqual(forked.metadata["branch"], "copy")

    async def test_agent_fork_preserves_middleware(self) -> None:
        middleware = FakeMiddleware()
        replacement = FakeMiddleware()
        agent = BaseAgent(
            name="worker",
            system_prompt="Work carefully.",
            runner=EchoRunner(),
            middleware=[middleware],
        )

        forked = agent.fork(name="worker-copy")
        replaced = agent.fork(name="worker-replaced", middleware=[replacement])

        self.assertEqual(forked.middleware, (middleware,))
        self.assertEqual(replaced.middleware, (replacement,))

    async def test_agent_accepts_context_window_algorithm_preset(self) -> None:
        agent = BaseAgent(
            name="worker",
            system_prompt="Work carefully.",
            runner=EchoRunner(),
            algorithm=ContextWindow.preset.no_raw_tool_outputs,
        )

        forked = agent.fork(name="worker-copy")
        replaced = agent.fork(name="worker-compact", algorithm="compact_tool_outputs")

        self.assertEqual(agent.algorithm.name, "hide_tool_outputs")
        self.assertEqual(forked.algorithm.name, "hide_tool_outputs")
        self.assertEqual(replaced.algorithm.name, "compact_tool_outputs")

    async def test_agent_without_strategy_calls_runner_once(self) -> None:
        runner = EchoRunner()
        agent = BaseAgent(name="direct", system_prompt="Direct system.", runner=runner)

        reply = await agent.generate_reply("task")

        self.assertIn("direct:task", reply.content)
        self.assertEqual(reply.metadata["modality"], "text")
        self.assertIn("Direct system.", runner.system)
        self.assertIn("agentic loop", runner.system)

    async def test_no_runner_raises_agent_execution_error(self) -> None:
        agent = BaseAgent(name="direct", system_prompt="Direct system.")

        with self.assertRaises(AgentExecutionError):
            await agent.generate_reply("task")


if __name__ == "__main__":
    unittest.main()
