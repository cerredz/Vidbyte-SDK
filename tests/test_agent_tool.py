"""Tests for AgentTool and BaseAgent.as_tool()."""

from __future__ import annotations

import json
import unittest

from vidbyte.agents.base import BaseAgent
from vidbyte.strategies.base import BaseStrategy
from vidbyte.tools.agent_tool import AgentTool, serialize_context
from vidbyte.tools.types import ToolCall, ToolPermission


class _FakeResponse:
    """Minimal model response that immediately calls isDone so AgentRuntime exits."""

    def __init__(self, final_answer: str) -> None:
        self.text = ""
        self.raw = {
            "output": [
                {
                    "type": "function_call",
                    "name": "isDone",
                    "arguments": json.dumps({"final_answer": final_answer}),
                }
            ]
        }


class FakeRunner:
    """Returns an isDone tool call carrying the full message as the final answer."""

    async def arun(self, message: str, **kwargs: object) -> _FakeResponse:
        return _FakeResponse(message)


def _make_agent(
    name: str = "worker",
    strategy: BaseStrategy | None = None,
    capabilities: tuple[str, ...] = (),
) -> BaseAgent:
    return BaseAgent(
        name=name,
        system_prompt="You are a helpful assistant.",
        runner=FakeRunner(),
        strategy=strategy,
        description="A test agent.",
        capabilities=capabilities,
    )


class SerializeContextTests(unittest.TestCase):
    def test_empty_history_and_prompt(self) -> None:
        result = serialize_context("", [])
        self.assertIn("<conversation_context>", result)
        self.assertIn("</conversation_context>", result)
        self.assertNotIn("<current_request>", result)

    def test_active_prompt_included(self) -> None:
        result = serialize_context("do the thing", [])
        self.assertIn("<current_request>", result)
        self.assertIn("do the thing", result)

    def test_history_messages_included(self) -> None:
        from vidbyte.agents.types import AgentMessage

        history = [
            AgentMessage(sender="user", recipient="worker", content="hello"),
            AgentMessage(sender="worker", recipient="user", content="world"),
        ]
        result = serialize_context("", history)
        self.assertIn("[user]: hello", result)
        self.assertIn("[worker]: world", result)


class AgentToolSpecTests(unittest.TestCase):
    def test_spec_has_zero_parameters(self) -> None:
        tool = AgentTool(_make_agent())
        self.assertEqual(tool.spec().parameters, ())

    def test_spec_name_defaults_to_agent_name(self) -> None:
        tool = AgentTool(_make_agent("alpha"))
        self.assertEqual(tool.spec().name, "alpha")

    def test_spec_name_override(self) -> None:
        tool = AgentTool(_make_agent("alpha"), name="custom_name")
        self.assertEqual(tool.spec().name, "custom_name")

    def test_spec_description_contains_agent_name(self) -> None:
        tool = AgentTool(_make_agent("my_agent"))
        self.assertIn("my_agent", tool.spec().description)

    def test_spec_description_contains_agent_description(self) -> None:
        tool = AgentTool(_make_agent())
        self.assertIn("A test agent.", tool.spec().description)

    def test_spec_description_contains_capabilities(self) -> None:
        tool = AgentTool(_make_agent(capabilities=("search", "summarize")))
        self.assertIn("search", tool.spec().description)
        self.assertIn("summarize", tool.spec().description)

    def test_spec_description_override(self) -> None:
        tool = AgentTool(_make_agent(), description="overridden")
        self.assertEqual(tool.spec().description, "overridden")

    def test_spec_permission_is_safe(self) -> None:
        tool = AgentTool(_make_agent())
        self.assertEqual(tool.spec().permission, ToolPermission.SAFE)

    def test_spec_metadata_contains_agent_name(self) -> None:
        tool = AgentTool(_make_agent("named"))
        self.assertEqual(tool.spec().metadata.get("agent_name"), "named")

    def test_name_property_matches_spec(self) -> None:
        tool = AgentTool(_make_agent("bravo"))
        self.assertEqual(tool.name, "bravo")


class AgentToolExecuteTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_returns_success_with_agent_reply(self) -> None:
        tool = AgentTool(_make_agent())
        result = await tool.execute(ToolCall("worker", {}))
        self.assertEqual(result.status.value, "success")

    async def test_execute_without_getter_uses_empty_context(self) -> None:
        # FakeRunner echoes the prompt back as final_answer, so reply.content
        # contains the serialized empty context.
        tool = AgentTool(_make_agent())
        result = await tool.execute(ToolCall("worker", {}))
        self.assertEqual(result.status.value, "success")
        self.assertIn("conversation_context", result.output)

    async def test_execute_with_context_getter_serializes_prompt(self) -> None:
        # FakeRunner echoes the prompt (serialized context) as the reply.
        tool = AgentTool(_make_agent())
        tool.bind_context_getter(lambda: ("my request", []))
        result = await tool.execute(ToolCall("worker", {}))
        self.assertEqual(result.status.value, "success")
        self.assertIn("my request", result.output)  # prompt appears in serialized context

    async def test_execute_returns_error_on_agent_failure(self) -> None:
        class BrokenRunner:
            async def arun(self, *args: object, **kwargs: object) -> object:
                raise RuntimeError("runner failed")

        agent = BaseAgent(
            name="broken",
            system_prompt="broken",
            runner=BrokenRunner(),
        )
        tool = AgentTool(agent)
        result = await tool.execute(ToolCall("broken", {}))
        self.assertEqual(result.status.value, "error")
        self.assertEqual(result.metadata.get("agent_name"), "broken")

    async def test_execute_isolates_history_across_calls(self) -> None:
        agent = _make_agent()
        tool = AgentTool(agent)
        initial_history_len = len(agent.history)

        await tool.execute(ToolCall("worker", {}))
        await tool.execute(ToolCall("worker", {}))

        # Original agent's history must not grow — fork() isolates each call
        self.assertEqual(len(agent.history), initial_history_len)

    async def test_execute_metadata_contains_agent_name(self) -> None:
        tool = AgentTool(_make_agent("named_agent"))
        result = await tool.execute(ToolCall("named_agent", {}))
        self.assertEqual(result.metadata.get("agent_name"), "named_agent")


class BaseAgentAsToolTests(unittest.TestCase):
    def test_as_tool_returns_agent_tool_instance(self) -> None:
        agent = _make_agent()
        tool = agent.as_tool()
        self.assertIsInstance(tool, AgentTool)

    def test_as_tool_name_defaults_to_agent_name(self) -> None:
        agent = _make_agent("my_agent")
        tool = agent.as_tool()
        self.assertEqual(tool.spec().name, "my_agent")  # type: ignore[union-attr]

    def test_as_tool_name_override(self) -> None:
        agent = _make_agent()
        tool = agent.as_tool(name="overridden_name")
        self.assertEqual(tool.spec().name, "overridden_name")  # type: ignore[union-attr]

    def test_as_tool_description_override(self) -> None:
        agent = _make_agent()
        tool = agent.as_tool(description="custom description")
        self.assertEqual(tool.spec().description, "custom description")  # type: ignore[union-attr]

    def test_as_tool_wraps_same_agent(self) -> None:
        agent = _make_agent()
        tool = agent.as_tool()
        self.assertIs(tool._agent, agent)  # type: ignore[union-attr]


class ContextGetterBindingTests(unittest.TestCase):
    def test_context_getter_bound_via_add_tool(self) -> None:
        parent = _make_agent("parent")
        child_tool = AgentTool(_make_agent("child"))
        parent.add_tool(child_tool)
        # After add_tool, the child_tool should have a context getter bound
        self.assertIsNotNone(child_tool._context_getter)

    def test_context_getter_bound_at_construction(self) -> None:
        child_tool = AgentTool(_make_agent("child"))
        parent = BaseAgent(
            name="parent",
            system_prompt="parent system",
            runner=FakeRunner(),
            tools=(child_tool,),
        )
        # Construction-time tools should also get a context getter
        self.assertIsNotNone(child_tool._context_getter)

    def test_context_getter_reads_active_prompt(self) -> None:
        parent = _make_agent("parent")
        child_tool = AgentTool(_make_agent("child"))
        parent.add_tool(child_tool)

        parent._active_prompt = "live prompt"
        active_prompt, _ = child_tool._context_getter()  # type: ignore[misc]
        self.assertEqual(active_prompt, "live prompt")

    def test_context_getter_reads_history(self) -> None:
        from vidbyte.agents.types import AgentMessage

        parent = _make_agent("parent")
        child_tool = AgentTool(_make_agent("child"))
        parent.add_tool(child_tool)

        parent.history.append(AgentMessage(sender="user", recipient="parent", content="ping"))
        _, history = child_tool._context_getter()  # type: ignore[misc]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].content, "ping")


if __name__ == "__main__":
    unittest.main()
