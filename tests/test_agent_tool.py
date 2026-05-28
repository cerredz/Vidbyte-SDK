"""Tests for AgentTool and BaseAgent.as_tool()."""

from __future__ import annotations

import json
import unittest

from vidbyte.agents.base import BaseAgent
from vidbyte.lib.dataclasses.agents import AgentMetadata
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.agent_tool import AgentTool
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
    capabilities: tuple[str, ...] = (),
    agent_metadata: AgentMetadata | None = None,
) -> BaseAgent:
    meta = agent_metadata or AgentMetadata(
        name=name,
        description="A test agent.",
        use_cases="Testing agent delegation.",
    )
    return BaseAgent(
        name=name,
        system_prompt="You are a helpful assistant.",
        runner=FakeRunner(),
        description="A test agent.",
        capabilities=capabilities,
        agent_metadata=meta,
    )


class AgentToolInitTests(unittest.TestCase):
    def test_init_with_agent(self) -> None:
        agent = _make_agent("alpha")
        tool = AgentTool(agent)
        self.assertIsInstance(tool, AgentTool)

    def test_name_derived_from_agent_metadata(self) -> None:
        agent = _make_agent("alpha", agent_metadata=AgentMetadata(name="custom_tool_name", description="desc", use_cases="use"))
        tool = AgentTool(agent)
        self.assertEqual(tool.spec().name, "custom_tool_name")

    def test_description_derived_from_agent_metadata(self) -> None:
        meta = AgentMetadata(name="alpha", description="custom desc", use_cases="custom use cases")
        agent = _make_agent("alpha", agent_metadata=meta)
        tool = AgentTool(agent)
        self.assertIn("custom desc", tool.spec().description)
        self.assertIn("custom use cases", tool.spec().description)
        self.assertIn("alpha", tool.spec().description)


class AgentToolSpecTests(unittest.TestCase):
    def test_spec_has_zero_parameters(self) -> None:
        tool = AgentTool(_make_agent())
        self.assertEqual(tool.spec().parameters, ())

    def test_spec_name_defaults_to_metadata_name(self) -> None:
        tool = AgentTool(_make_agent("alpha"))
        self.assertEqual(tool.spec().name, "alpha")

    def test_spec_description_contains_agent_metadata_name(self) -> None:
        meta = AgentMetadata(name="my_agent", description="desc", use_cases="use")
        tool = AgentTool(_make_agent(agent_metadata=meta))
        self.assertIn("my_agent", tool.spec().description)

    def test_spec_description_contains_metadata_description(self) -> None:
        meta = AgentMetadata(name="my_agent", description="A test agent.", use_cases="use")
        tool = AgentTool(_make_agent(agent_metadata=meta))
        self.assertIn("A test agent.", tool.spec().description)

    def test_spec_description_contains_use_cases(self) -> None:
        meta = AgentMetadata(name="name", description="desc", use_cases="search, summarize")
        tool = AgentTool(_make_agent(agent_metadata=meta))
        self.assertIn("search, summarize", tool.spec().description)

    def test_spec_permission_is_safe(self) -> None:
        tool = AgentTool(_make_agent())
        self.assertEqual(tool.spec().permission, ToolPermission.SAFE)

    def test_spec_metadata_contains_agent_name(self) -> None:
        meta = AgentMetadata(name="named", description="desc", use_cases="use")
        tool = AgentTool(_make_agent(agent_metadata=meta))
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
        tool = AgentTool(_make_agent())
        result = await tool.execute(ToolCall("worker", {}))
        self.assertEqual(result.status.value, "success")
        self.assertIn("conversation_context", result.output)

    async def test_execute_with_context_getter_serializes_prompt(self) -> None:
        tool = AgentTool(_make_agent())
        tool.bind_context_getter(lambda: ("my request", []))
        result = await tool.execute(ToolCall("worker", {}))
        self.assertEqual(result.status.value, "success")
        self.assertIn("my request", result.output)

    async def test_execute_returns_error_on_agent_failure(self) -> None:
        class BrokenRunner:
            async def arun(self, *args: object, **kwargs: object) -> object:
                raise RuntimeError("runner failed")

        meta = AgentMetadata(name="broken", description="desc", use_cases="use")
        agent = BaseAgent(
            name="broken",
            system_prompt="broken",
            runner=BrokenRunner(),
            agent_metadata=meta,
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

        self.assertEqual(len(agent.history), initial_history_len)

    async def test_execute_metadata_contains_agent_name(self) -> None:
        meta = AgentMetadata(name="named_agent", description="desc", use_cases="use")
        tool = AgentTool(_make_agent(agent_metadata=meta))
        result = await tool.execute(ToolCall("named_agent", {}))
        self.assertEqual(result.metadata.get("agent_name"), "named_agent")

    async def test_static_serialize_context_empty(self) -> None:
        result = AgentTool._serialize_context("", [])
        self.assertIn("<conversation_context>", result)
        self.assertIn("</conversation_context>", result)
        self.assertNotIn("<current_request>", result)

    async def test_static_serialize_context_with_prompt(self) -> None:
        result = AgentTool._serialize_context("do the thing", [])
        self.assertIn("<current_request>", result)
        self.assertIn("do the thing", result)

    async def test_static_serialize_context_with_history(self) -> None:
        from vidbyte.agents.types import AgentMessage

        history = [
            AgentMessage(sender="user", recipient="worker", content="hello"),
            AgentMessage(sender="worker", recipient="user", content="world"),
        ]
        result = AgentTool._serialize_context("", history)
        self.assertIn("[user]: hello", result)
        self.assertIn("[worker]: world", result)


class BaseAgentAsToolTests(unittest.TestCase):
    def test_as_tool_returns_agent_tool_instance(self) -> None:
        agent = _make_agent()
        tool = agent.as_tool()
        self.assertIsInstance(tool, AgentTool)

    def test_as_tool_name_defaults_to_metadata_name(self) -> None:
        meta = AgentMetadata(name="my_agent", description="desc", use_cases="use")
        agent = _make_agent(agent_metadata=meta)
        tool = agent.as_tool()
        self.assertEqual(tool.spec().name, "my_agent")

    def test_as_tool_wraps_same_agent(self) -> None:
        agent = _make_agent()
        tool = agent.as_tool()
        self.assertIs(tool._agent, agent)

    def test_as_tool_raises_when_metadata_name_missing(self) -> None:
        meta = AgentMetadata(name="", description="desc", use_cases="use")
        agent = _make_agent(agent_metadata=meta)
        with self.assertRaises(ConfigurationError):
            agent.as_tool()

    def test_as_tool_raises_when_metadata_description_missing(self) -> None:
        meta = AgentMetadata(name="name", description="", use_cases="use")
        agent = _make_agent(agent_metadata=meta)
        with self.assertRaises(ConfigurationError):
            agent.as_tool()

    def test_as_tool_raises_when_metadata_use_cases_missing(self) -> None:
        meta = AgentMetadata(name="name", description="desc", use_cases="")
        agent = _make_agent(agent_metadata=meta)
        with self.assertRaises(ConfigurationError):
            agent.as_tool()

    def test_as_tool_raises_when_all_metadata_missing(self) -> None:
        agent = _make_agent(agent_metadata=AgentMetadata())
        with self.assertRaises(ConfigurationError):
            agent.as_tool()


class ContextGetterBindingTests(unittest.TestCase):
    def test_context_getter_bound_via_add_tool(self) -> None:
        parent = _make_agent("parent")
        child_tool = AgentTool(_make_agent("child"))
        parent.add_tool(child_tool)
        self.assertIsNotNone(child_tool._context_getter)

    def test_context_getter_bound_at_construction(self) -> None:
        child_tool = AgentTool(_make_agent("child"))
        parent = BaseAgent(
            name="parent",
            system_prompt="parent system",
            runner=FakeRunner(),
            tools=(child_tool,),
        )
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

