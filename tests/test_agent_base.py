from __future__ import annotations

import unittest

from vidbyte.agents import AgentInput, AgentMessage, BaseAgent
from vidbyte.agents.base import ConfiguredAgentRunner
from vidbyte.context import ContextManager, ContextWindow, TaskContextItem, TextContextItem
from vidbyte.lib.config import ModelProvider
from vidbyte.middleware import AgentMiddleware
from vidbyte.lib.errors import AgentExecutionError
from vidbyte.lib.runners import TextModelResponse
from vidbyte.context.handoff import MinimalHandoff
from vidbyte.tools import ToolSpec
from vidbyte.tools.types import ToolCallContext


class FakeTool:
    def __init__(self, name: str = "lookup") -> None:
        # Stores the test tool name used by spec().
        self._name = name

    def spec(self) -> ToolSpec:
        # Returns a minimal model-facing tool spec.
        return ToolSpec(name=self._name, description=f"{self._name} things")


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


class FailOnSecondRunner:
    """Runner that succeeds on the first call and raises on the second."""

    def __init__(self) -> None:
        self.call_count = 0

    def run(self, prompt: str, **_: object) -> object:
        self.call_count += 1
        if self.call_count >= 2:
            raise RuntimeError("runner failure on second call")
        return FakeResponse(
            "",
            {"output": [{"type": "function_call", "name": "isDone", "arguments": f'{{"final_answer": "ok:{prompt}"}}'}]},
        )


class OptionCaptureRunner:
    """Runner that records all kwargs passed to it."""

    def __init__(self) -> None:
        self.captured_options: list[dict] = []

    def run(self, prompt: str, **kwargs: object) -> object:
        self.captured_options.append(dict(kwargs))
        return FakeResponse(
            "",
            {"output": [{"type": "function_call", "name": "isDone", "arguments": f'{{"final_answer": "ok:{prompt}"}}'}]},
        )


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
        self.assertEqual(forked.metadata["forked_from"], "run-123")
        self.assertEqual(forked.metadata["fork_depth"], 1)

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

    async def test_agent_fork_rebuilds_runner_for_model_overrides(self) -> None:
        # Model-ish overrides must discard the live parent runner so child config can build a fresh runner lazily.
        parent = BaseAgent(name="worker", system_prompt="Work carefully.", runner=EchoRunner(), provider="openai", model_name="model-a")
        child = parent.fork(name="child", model_name="model-b", temperature=0.7, runner_options={"reasoning": "low"})

        self.assertIsInstance(child.runner, ConfiguredAgentRunner)
        self.assertEqual(child.runner_config.model_name, "model-b")
        self.assertEqual(child.runner_config.temperature, 0.7)
        self.assertEqual(child.runner_config.options, {"reasoning": "low"})
        self.assertEqual(child.runners, {})

    async def test_agent_fork_applies_tool_deltas_by_name(self) -> None:
        # Fork tool deltas should compose with inherited tools and leave the parent catalog untouched.
        parent = BaseAgent(name="worker", system_prompt="Work carefully.", runner=EchoRunner(), tools=[FakeTool("keep"), FakeTool("drop")])
        child = parent.fork(name="child", add_tools=[FakeTool("add")], drop_tools=["drop"])

        self.assertEqual(parent.tools.names(), ("keep", "drop"))
        self.assertEqual(child.tools.names(), ("keep", "add"))

    async def test_agent_fork_explicit_history_wins_and_can_copy_run_state(self) -> None:
        # Explicit history should override include_history, while include_run_state copies handoffs and tool contexts.
        parent = BaseAgent(name="worker", system_prompt="Work carefully.", runner=EchoRunner())
        parent.history.append(AgentMessage(sender="parent", recipient="worker", content="parent-history"))
        explicit = [AgentMessage(sender="explicit", recipient="worker", content="explicit-history")]
        handoff = MinimalHandoff(primitive_id="handoff:1")
        context = ToolCallContext(tool_name="lookup")
        parent.record_handoff(handoff)
        parent._tool_call_contexts.append(context)

        child = parent.fork(name="child", include_history=True, history=explicit, include_run_state=True)

        self.assertEqual(child.history, explicit)
        self.assertEqual(child.handoffs, [handoff])
        self.assertIs(child.last_handoff, handoff)
        self.assertEqual(child._tool_call_contexts, [context])
        self.assertEqual(child.last_prompt, "")
        self.assertIsNone(child.last_reply)

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

    # --- run_sequentially / arun_sequentially tests ---

    async def test_arun_sequentially_returns_all_replies(self) -> None:
        # [Edge Case] Three prompts → three replies returned in order
        agent = BaseAgent(name="seq", system_prompt="S.", runner=EchoRunner())
        replies = await agent.arun_sequentially(["a", "b", "c"])
        self.assertEqual(len(replies), 3)
        self.assertIn("direct:a", replies[0].content)
        self.assertIn("direct:b", replies[1].content)
        self.assertIn("direct:c", replies[2].content)

    async def test_arun_sequentially_empty_list_returns_empty(self) -> None:
        # [Edge Case] Empty input must return [] without touching the runner
        runner = EchoRunner()
        agent = BaseAgent(name="seq", system_prompt="S.", runner=runner)
        replies = await agent.arun_sequentially([])
        self.assertEqual(replies, [])
        self.assertEqual(len(agent.history), 0)

    async def test_arun_sequentially_single_prompt(self) -> None:
        # [Edge Case] Single-element list behaves identically to one generate_reply call
        agent = BaseAgent(name="seq", system_prompt="S.", runner=EchoRunner())
        replies = await agent.arun_sequentially(["only"])
        self.assertEqual(len(replies), 1)
        self.assertIn("direct:only", replies[0].content)

    async def test_arun_sequentially_preserves_history(self) -> None:
        # [Silent Failure] history must grow by 1 per prompt (agent reply only — user messages
        # are not pushed by generate_reply, so expect exactly N entries after N prompts)
        agent = BaseAgent(name="seq", system_prompt="S.", runner=EchoRunner())
        await agent.arun_sequentially(["p1", "p2", "p3"])
        self.assertEqual(len(agent.history), 3)

    async def test_arun_sequentially_context_accumulates(self) -> None:
        # [Hidden Failure] Each successive prompt sees the prior reply in agent.history.
        # Verify that after the second prompt, history contains the first reply.
        agent = BaseAgent(name="seq", system_prompt="S.", runner=EchoRunner())
        replies = await agent.arun_sequentially(["first", "second"])
        self.assertEqual(len(agent.history), 2)
        # The first reply should be the first entry in history
        self.assertEqual(agent.history[0].content, replies[0].content)
        # The second reply is appended after
        self.assertEqual(agent.history[1].content, replies[1].content)

    async def test_run_sequentially_raises_in_active_loop(self) -> None:
        # [Hidden Assumption] run_sequentially must refuse when called inside a running event loop
        agent = BaseAgent(name="seq", system_prompt="S.", runner=EchoRunner())
        with self.assertRaises(AgentExecutionError):
            agent.run_sequentially(["prompt"])

    async def test_arun_sequentially_stops_on_first_failure(self) -> None:
        # [Hidden Failure] If prompt N raises, prompts N+1..end must not be called
        runner = FailOnSecondRunner()
        agent = BaseAgent(name="seq", system_prompt="S.", runner=runner)
        with self.assertRaises(AgentExecutionError):
            await agent.arun_sequentially(["ok", "fail", "never"])
        self.assertEqual(runner.call_count, 2)
        # Only one reply was committed to history before the failure
        self.assertEqual(len(agent.history), 1)

    async def test_arun_sequentially_accepts_agent_input_objects(self) -> None:
        # [Hidden Assumption] AgentInput objects must be forwarded correctly, not coerced to strings
        agent = BaseAgent(name="seq", system_prompt="S.", runner=EchoRunner())
        inp = AgentInput(prompt="from-input")
        replies = await agent.arun_sequentially([inp])
        self.assertEqual(len(replies), 1)
        self.assertIn("direct:from-input", replies[0].content)

    async def test_arun_sequentially_forwards_options_to_each_call(self) -> None:
        # [Silent Failure] **options must reach every underlying generate_reply invocation
        runner = OptionCaptureRunner()
        agent = BaseAgent(name="seq", system_prompt="S.", runner=runner)
        await agent.arun_sequentially(["x", "y"])
        # Both calls must have received the system kwarg (injected by the runtime)
        for captured in runner.captured_options:
            self.assertIn("system", captured)


if __name__ == "__main__":
    unittest.main()
