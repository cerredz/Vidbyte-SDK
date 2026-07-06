from __future__ import annotations

import unittest

from vidbyte.agents import AgentForkSettings, BaseAgent
from vidbyte.context import ContextManager
from vidbyte.context.handoff import Handoff, MinimalHandoff
from vidbyte.lib.config import ModelProvider
from vidbyte.lib.runners import TextModelResponse
from vidbyte.tools.builtins.context_primitives import ContextListTool
from vidbyte.tools.builtins.handoff import CreateHandoffTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.executor import ToolExecutor
from vidbyte.tools.types import ToolCall, ToolStatus


class FakeRunner:
    """Minimal runner so BaseAgent can be constructed without a real provider."""

    def run(self, prompt: str, *, system: str | None = None, **_: object) -> TextModelResponse:
        return TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="Final answer: OK", raw={})


class StubAgent:
    """Stand-in agent that records handoffs without running a real model."""

    def __init__(self) -> None:
        self.handoffs: list[Handoff] = []
        self.last_handoff: Handoff | None = None
        self.context_manager = None

    def record_handoff(self, handoff: Handoff) -> None:
        self.handoffs.append(handoff)
        self.last_handoff = handoff


def _call(**arguments: object) -> ToolCall:
    """Build a create_handoff ToolCall from keyword arguments."""
    return ToolCall(tool_name="create_handoff", arguments=dict(arguments))


class CreateHandoffToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_creates_handoff_from_arbitrary_sections(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        result = await tool.execute(_call(title="My Report", sections={"Summary": "All done.", "Next Steps": "Deploy it."}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(len(agent.handoffs), 1)
        self.assertEqual(agent.handoffs[0].title, "My Report")
        self.assertEqual(agent.handoffs[0].sections, {"Summary": "All done.", "Next Steps": "Deploy it."})

    async def test_error_missing_title(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        result = await tool.execute(_call(title="  ", sections={"A": "content"}))
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("title", result.output)
        self.assertEqual(agent.handoffs, [])

    async def test_error_missing_sections(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        result = await tool.execute(_call(title="Handoff"))
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("sections", result.output)

    async def test_error_empty_sections(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        result = await tool.execute(_call(title="Handoff", sections={}))
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("sections", result.output)

    async def test_error_no_agent_bound(self) -> None:
        tool = CreateHandoffTool()
        result = await tool.execute(_call(title="H", sections={"A": "x"}))
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("not bound", result.output)

    async def test_audience_and_instructions_attached_to_handoff(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        await tool.execute(_call(title="H", sections={"A": "v"}, audience="Next engineer", instructions="Be concise"))
        handoff = agent.handoffs[0]
        self.assertIn("Audience: Next engineer", handoff.instructions)
        self.assertIn("Instructions: Be concise", handoff.instructions)

    async def test_no_extra_fields_in_instructions_when_absent(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        await tool.execute(_call(title="H", sections={"A": "v"}))
        # Handoff coerces instructions=None to "" via DEFAULT_INSTRUCTIONS
        self.assertEqual(agent.handoffs[0].instructions, "")

    async def test_primitive_id_increments_across_calls(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        first = await tool.execute(_call(title="First", sections={"A": "x"}))
        second = await tool.execute(_call(title="Second", sections={"B": "y"}))
        self.assertEqual(first.metadata["primitive_id"], "handoff:1")
        self.assertEqual(second.metadata["primitive_id"], "handoff:2")
        self.assertEqual([h.primitive_id for h in agent.handoffs], ["handoff:1", "handoff:2"])

    async def test_appends_in_order_across_many_calls(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        for i in range(3):
            await tool.execute(_call(title=f"H{i}", sections={"S": f"v{i}"}))
        self.assertEqual(len(agent.handoffs), 3)
        self.assertEqual([h.primitive_id for h in agent.handoffs], ["handoff:1", "handoff:2", "handoff:3"])

    async def test_coerces_non_string_section_values(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        result = await tool.execute(_call(title="H", sections={"Count": 42, "Flag": True}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(agent.handoffs[0].sections, {"Count": "42", "Flag": "True"})

    async def test_result_metadata_contains_primitive_id_and_sections(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        result = await tool.execute(_call(title="H", sections={"Alpha": "content a"}))
        self.assertIn("primitive_id", result.metadata)
        self.assertIn("sections", result.metadata)
        self.assertEqual(result.metadata["sections"], {"Alpha": "content a"})

    async def test_result_output_is_rendered_markdown(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        result = await tool.execute(_call(title="My Handoff", sections={"Summary": "Done."}))
        self.assertIn("My Handoff", result.output)
        self.assertIn("Summary", result.output)
        self.assertIn("Done.", result.output)

    async def test_description_includes_past_handoffs_as_context(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        await tool.execute(_call(title="First Handoff", sections={"A": "x"}))
        spec = tool.spec()
        self.assertIn("First Handoff", spec.description)
        self.assertIn("A", spec.description)

    async def test_description_empty_when_no_past_handoffs(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        spec = tool.spec()
        self.assertNotIn("Handoffs authored so far", spec.description)

    async def test_description_length_in_token_range(self) -> None:
        # Rough check: description should be between 500 and 1500 tokens.
        # Estimate: 1 token ≈ 4 chars. With one past handoff present.
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        await tool.execute(_call(title="Prior Handoff", sections={"Work Done": "x", "Next": "y"}))
        spec = tool.spec()
        approx_tokens = len(spec.description) // 4
        self.assertGreaterEqual(approx_tokens, 500, "Description is shorter than 500 tokens")
        self.assertLessEqual(approx_tokens, 1500, "Description exceeds 1500 tokens")


class BaseAgentHandoffRecordingTests(unittest.IsolatedAsyncioTestCase):
    def _agent(self, *, context_manager: ContextManager | None = None, tools: list | None = None) -> BaseAgent:
        return BaseAgent(name="worker", system_prompt="Work.", runner=FakeRunner(), context_manager=context_manager, tools=tools or [])

    def test_record_handoff_appends_updates_last_and_upserts(self) -> None:
        manager = ContextManager()
        agent = self._agent(context_manager=manager)
        handoff = MinimalHandoff(primitive_id="handoff:1")
        agent.record_handoff(handoff)
        self.assertEqual(agent.handoffs, [handoff])
        self.assertIs(agent.last_handoff, handoff)
        self.assertIs(manager.get_by_id("handoff:1"), handoff)

    def test_record_handoff_without_context_manager(self) -> None:
        agent = self._agent(context_manager=None)
        handoff = MinimalHandoff(primitive_id="handoff:1")
        agent.record_handoff(handoff)
        self.assertEqual(agent.handoffs, [handoff])
        self.assertIs(agent.last_handoff, handoff)

    def test_record_handoff_skips_frozen_primitive(self) -> None:
        manager = ContextManager()
        frozen = Handoff(sections={"S": "x"}, primitive_id="handoff:1", primitive_frozen=True)
        manager.upsert(frozen)
        agent = self._agent(context_manager=manager)
        replacement = MinimalHandoff(primitive_id="handoff:1")
        agent.record_handoff(replacement)
        self.assertIn(replacement, agent.handoffs)
        self.assertIs(agent.last_handoff, replacement)
        self.assertIs(manager.get_by_id("handoff:1"), frozen)

    def test_tool_bound_at_construction_and_via_add_tool(self) -> None:
        constructed = CreateHandoffTool()
        agent = self._agent(tools=[constructed])
        self.assertIs(constructed._agent, agent)
        other = self._agent()
        added = CreateHandoffTool()
        other.add_tool(added)
        self.assertIs(added._agent, other)

    def test_forked_agent_starts_with_empty_handoffs(self) -> None:
        agent = self._agent()
        agent.record_handoff(MinimalHandoff(primitive_id="handoff:1"))
        child = agent.fork(AgentForkSettings(name="child"))
        self.assertEqual(child.handoffs, [])


class CreateHandoffIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_handoffs_visible_in_context_list(self) -> None:
        manager = ContextManager()
        agent = BaseAgent(
            name="worker",
            system_prompt="Work.",
            runner=FakeRunner(),
            context_manager=manager,
            tools=[CreateHandoffTool(), ContextListTool(manager)],
        )
        tool = agent.tools._get("create_handoff")
        await tool.execute(_call(title="Engineering Handoff", sections={"Changes Made": "Added auth middleware.", "Next Steps": "Run tests."}))
        await tool.execute(_call(title="Research Summary", sections={"Findings": "Rate limiting is already present.", "Sources": "backend/middleware/api/"}))

        self.assertEqual(len(agent.handoffs), 2)
        listing = await ContextListTool(manager).execute(ToolCall(tool_name="context_list"))
        self.assertIn("handoff:1", listing.output)
        self.assertIn("handoff:2", listing.output)
        self.assertIn("(handoff)", listing.output)


if __name__ == "__main__":
    unittest.main()
