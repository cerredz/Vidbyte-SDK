from __future__ import annotations

import unittest

from vidbyte.agents import AgentInput, BaseAgent
from vidbyte.agents.base import ConfiguredAgentRunner
from vidbyte.context import ContextManager, ContextWindow, TaskContextItem, TextContextItem
from vidbyte.lib.config import ModelProvider
from vidbyte.middleware import AgentMiddleware
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError
from vidbyte.lib.runners import TextModelResponse
from vidbyte.strategies import BaseAgentContext, BaseStrategy, ChainOfThoughtStrategy, StrategyChain, StrategyContext, StrategyResult
from vidbyte.tools import ToolSpec


class FakeTool:
    def spec(self) -> ToolSpec:
        return ToolSpec(name="lookup", description="Lookup things")


class EchoStrategy(BaseStrategy):
    name = "echo"

    def __init__(self) -> None:
        self.last_tools = ()
        self.last_context: StrategyContext | None = None

    async def arun(self, prompt: str, **kwargs: object) -> StrategyResult:
        self.last_tools = tuple(kwargs.get("tools", ()))
        self.last_context = kwargs.get("context")  # type: ignore[assignment]
        return StrategyResult(output=f"reply:{prompt}", strategy_name=self.name)


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


class AppendStrategy(BaseStrategy):
    def __init__(self, name: str, suffix: str) -> None:
        self.name = name
        self.suffix = suffix
        self.seen_prompts: list[str] = []

    async def arun(self, prompt: str, **kwargs: object) -> StrategyResult:
        self.seen_prompts.append(prompt)
        context = kwargs.get("context")
        self.last_context = context
        return StrategyResult(output=f"{prompt}{self.suffix}", strategy_name=self.name)


class TextRunner:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.systems: list[str | None] = []

    def run(self, prompt: str, *, system: str | None = None, **_: object) -> TextModelResponse:
        self.prompts.append(prompt)
        self.systems.append(system)
        return TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="Final answer: OK", raw={})


class AgentBaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_card_and_generate_reply_pass_tools_and_context(self) -> None:
        strategy = EchoStrategy()
        tool = FakeTool()
        agent = BaseAgent(
            name="worker",
            system_prompt="Work carefully.",
            strategy=strategy,
            runner=object(),
            tools=[tool],
            capabilities=["search"],
        )

        card = agent.card()
        self.assertEqual(card.name, "worker")
        self.assertEqual(card.tool_names, ("lookup",))
        self.assertEqual(card.capabilities, ("search",))

        reply = await agent.generate_reply("task")
        self.assertEqual(reply.content, "reply:task")
        self.assertEqual(reply.metadata["modality"], "text")
        self.assertEqual(strategy.last_tools, (tool,))
        self.assertIsNotNone(strategy.last_context)
        self.assertIsInstance(strategy.last_context, BaseAgentContext)
        self.assertEqual(strategy.last_context.agent_name, None)
        self.assertEqual(strategy.last_context.strategy_metadata, {})
        self.assertEqual(tuple(tool.name for tool in strategy.last_context.tools), ("lookup",))
        self.assertIn("Work carefully.", strategy.last_context.system_prompt)
        self.assertNotIn("agentic loop", strategy.last_context.system_prompt)

    async def test_agent_accepts_strategies_sequence_and_returns_chain_result(self) -> None:
        first = AppendStrategy("first", "-a")
        second = AppendStrategy("second", "-b")
        agent = BaseAgent(name="worker", system_prompt="Work.", strategies=[first, second])

        reply = await agent.arun("task")

        self.assertIsInstance(agent.strategy, StrategyChain)
        self.assertEqual(reply.content, "task-a-b")
        self.assertEqual(reply.metadata["strategy"], "strategy_chain")
        self.assertEqual(reply.metadata["stage_names"], ("first", "second"))
        self.assertEqual(first.seen_prompts, ["task"])
        self.assertEqual(second.seen_prompts, ["task-a"])

    async def test_agent_uses_single_strategy_from_strategies_sequence(self) -> None:
        strategy = EchoStrategy()
        agent = BaseAgent(name="worker", system_prompt="Work.", strategies=[strategy])

        reply = await agent.arun("task")

        self.assertIs(agent.strategy, strategy)
        self.assertEqual(reply.content, "reply:task")

    async def test_agent_rejects_strategy_and_strategies_together(self) -> None:
        with self.assertRaises(ConfigurationError):
            BaseAgent(
                name="worker",
                system_prompt="Work.",
                strategy=EchoStrategy(),
                strategies=[EchoStrategy()],
            )

    async def test_agent_rejects_empty_strategies(self) -> None:
        with self.assertRaises(ConfigurationError):
            BaseAgent(name="worker", system_prompt="Work.", strategies=[])

    async def test_agent_default_context_items_reach_strategy_context(self) -> None:
        strategy = EchoStrategy()
        task = TaskContextItem(goal="Fix failing tests")
        agent = BaseAgent(
            name="worker",
            system_prompt="Work carefully.",
            strategy=strategy,
            runner=object(),
            context_items=[task],
        )

        await agent.generate_reply("task")

        self.assertIsNotNone(strategy.last_context)
        self.assertEqual(strategy.last_context.context_items, (task,))
        self.assertTrue(any(artifact.artifact_type == "task" for artifact in strategy.last_context.artifacts))

    async def test_agent_input_context_items_are_per_call_only(self) -> None:
        strategy = EchoStrategy()
        default_item = TaskContextItem(goal="Default")
        call_item = TextContextItem(title="Call", content="call body")
        agent = BaseAgent(
            name="worker",
            system_prompt="Work carefully.",
            strategy=strategy,
            runner=object(),
            context_items=[default_item],
        )

        await agent.generate_reply(AgentInput("task", context_items=(call_item,)))

        self.assertIsNotNone(strategy.last_context)
        self.assertEqual(strategy.last_context.context_items, (default_item, call_item))
        self.assertEqual(agent.context_items, (default_item,))

    async def test_agent_context_managers_merge_without_mutating_defaults(self) -> None:
        strategy = EchoStrategy()
        default_manager = ContextManager([TaskContextItem(goal="Default")])
        call_manager = ContextManager([TextContextItem(title="Call", content="body")])
        agent = BaseAgent(
            name="worker",
            system_prompt="Work carefully.",
            strategy=strategy,
            runner=object(),
            context_manager=default_manager,
        )

        await agent.generate_reply(AgentInput("task", context_manager=call_manager))

        self.assertIsNotNone(strategy.last_context)
        self.assertEqual(len(strategy.last_context.context_items), 2)
        self.assertEqual(len(default_manager.items()), 1)

    async def test_runner_config_tool_helpers_and_fork(self) -> None:
        strategy = EchoStrategy()
        tool = FakeTool()
        agent = BaseAgent.from_run_id(
            "run-123",
            name="researcher",
            system_prompt="Research carefully.",
            strategy=strategy,
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

        self.assertEqual(reply.content, "direct:task")
        self.assertEqual(reply.metadata["strategy"], "direct_runner")
        self.assertEqual(reply.metadata["modality"], "text")
        self.assertIn("Direct system.", runner.system)
        self.assertIn("agentic loop", runner.system)

    async def test_sync_strategy_runs_through_agent_async_path_without_agentic_prompt(self) -> None:
        runner = TextRunner()
        agent = BaseAgent(
            name="reasoner",
            system_prompt="Reason directly.",
            strategy=ChainOfThoughtStrategy(),
            runner=runner,
        )

        reply = await agent.arun("task")

        self.assertEqual(reply.metadata["strategy"], "chain_of_thought")
        self.assertEqual(reply.content, "Final answer: OK")
        self.assertEqual(len(runner.prompts), 1)
        self.assertTrue(runner.systems)
        self.assertIsNone(runner.systems[0])

    async def test_no_strategy_still_requires_executable_runner(self) -> None:
        agent = BaseAgent(name="direct", system_prompt="Direct system.")

        with self.assertRaises(AgentExecutionError):
            await agent.generate_reply("task")


if __name__ == "__main__":
    unittest.main()
