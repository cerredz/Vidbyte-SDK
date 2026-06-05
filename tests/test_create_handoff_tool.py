from __future__ import annotations

import unittest

from vidbyte.agents import BaseAgent
from vidbyte.context import ContextManager
from vidbyte.context.handoff import EngineeringHandoff, Handoff, MinimalHandoff, ResearchHandoff
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
    """Stand-in agent that records specs and returns a deterministically filled handoff."""

    def __init__(self, *, extra_metadata: dict | None = None) -> None:
        self.handoffs: list[Handoff] = []
        self.last_handoff: Handoff | None = None
        self.context_manager = None
        self.received_specs: list[Handoff] = []
        self._extra_metadata = extra_metadata or {}

    async def handoff(self, spec: Handoff) -> Handoff:
        # Emulate HandoffAgent generation by filling every section with placeholder content.
        self.received_specs.append(spec)
        filled = spec.fill({title: f"content::{title}" for title in spec.section_titles()})
        filled.metadata.update(self._extra_metadata)
        return filled

    def record_handoff(self, handoff: Handoff) -> None:
        # Mirror BaseAgent.record_handoff growth so primitive id minting can increment.
        self.handoffs.append(handoff)
        self.last_handoff = handoff


def _call(**arguments: object) -> ToolCall:
    """Build a create_handoff ToolCall from keyword arguments."""
    return ToolCall(tool_name="create_handoff", arguments=dict(arguments))


class CreateHandoffToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_known_types_to_subclass(self) -> None:
        for handoff_type, cls in (("engineering", EngineeringHandoff), ("research", ResearchHandoff), ("minimal", MinimalHandoff)):
            agent = StubAgent()
            tool = CreateHandoffTool()
            tool.bind_agent(agent)
            result = await tool.execute(_call(handoff_type=handoff_type, objective="Do the thing"))
            self.assertEqual(result.status, ToolStatus.SUCCESS)
            self.assertEqual(result.metadata["handoff_type"], handoff_type)
            self.assertIsInstance(agent.received_specs[0], cls)
            self.assertEqual(set(result.metadata["sections"].keys()), set(cls().section_titles()))

    async def test_builds_custom_from_custom_sections(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        result = await tool.execute(_call(handoff_type="custom", objective="O", custom_sections={"Alpha": "guide a", "Beta": "guide b"}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        spec = agent.received_specs[0]
        self.assertIs(type(spec), Handoff)
        self.assertEqual(set(spec.section_titles()), {"Alpha", "Beta"})
        self.assertEqual(set(result.metadata["sections"].keys()), {"Alpha", "Beta"})

    async def test_error_unknown_type(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        result = await tool.execute(_call(handoff_type="bogus", objective="O"))
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("Unknown handoff_type", result.output)
        self.assertEqual(agent.handoffs, [])

    async def test_error_missing_objective(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        result = await tool.execute(_call(handoff_type="engineering", objective="   "))
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("objective", result.output)

    async def test_error_custom_without_sections(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        result = await tool.execute(_call(handoff_type="custom", objective="O"))
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("custom_sections", result.output)

    async def test_error_no_agent_bound(self) -> None:
        tool = CreateHandoffTool()
        result = await tool.execute(_call(handoff_type="minimal", objective="O"))
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("not bound", result.output)

    async def test_compose_intent_includes_only_present_fields(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        await tool.execute(_call(handoff_type="minimal", objective="Ship it", audience="Next engineer"))
        instructions = agent.received_specs[0].instructions
        self.assertIn("Objective: Ship it", instructions)
        self.assertIn("Audience: Next engineer", instructions)
        self.assertNotIn("Scope:", instructions)
        self.assertNotIn("Non-Goals:", instructions)

    async def test_title_override(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        await tool.execute(_call(handoff_type="minimal", objective="O", title="Custom Title"))
        self.assertEqual(agent.received_specs[0].title, "Custom Title")
        self.assertEqual(agent.handoffs[0].title, "Custom Title")

    async def test_primitive_id_increments_across_calls(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        first = await tool.execute(_call(handoff_type="minimal", objective="O1"))
        second = await tool.execute(_call(handoff_type="research", objective="O2"))
        self.assertEqual(first.metadata["primitive_id"], "handoff:1")
        self.assertEqual(second.metadata["primitive_id"], "handoff:2")
        self.assertEqual([h.primitive_id for h in agent.handoffs], ["handoff:1", "handoff:2"])

    async def test_appends_in_order_for_many_calls(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        self.assertEqual(agent.handoffs, [])
        for index in range(3):
            await tool.execute(_call(handoff_type="minimal", objective=f"O{index}"))
        self.assertEqual(len(agent.handoffs), 3)
        self.assertEqual([h.primitive_id for h in agent.handoffs], ["handoff:1", "handoff:2", "handoff:3"])

    async def test_does_not_mutate_caller_custom_sections_and_coerces_values(self) -> None:
        agent = StubAgent()
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        original = {"Alpha": "guide", "Beta": 5}
        await tool.execute(_call(handoff_type="custom", objective="O", custom_sections=original))
        self.assertEqual(original, {"Alpha": "guide", "Beta": 5})
        self.assertEqual(agent.received_specs[0].sections, {"Alpha": "guide", "Beta": "5"})

    async def test_surfaces_extra_sections_and_raw_output(self) -> None:
        agent = StubAgent(extra_metadata={"extra_sections": {"Bonus": "x"}, "raw_output": "raw"})
        tool = CreateHandoffTool()
        tool.bind_agent(agent)
        result = await tool.execute(_call(handoff_type="minimal", objective="O"))
        self.assertEqual(result.metadata["extra_sections"], {"Bonus": "x"})
        self.assertEqual(result.metadata["raw_output"], "raw")

    async def test_generation_failure_normalized_by_executor(self) -> None:
        class FailingAgent(StubAgent):
            async def handoff(self, spec: Handoff) -> Handoff:
                raise RuntimeError("boom")

        tool = CreateHandoffTool()
        tool.bind_agent(FailingAgent())
        executor = ToolExecutor(Tools([tool]))
        result = await executor.execute_call(_call(handoff_type="minimal", objective="O"))
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertEqual(result.metadata.get("error"), "execution_error")


class BaseAgentHandoffRecordingTests(unittest.IsolatedAsyncioTestCase):
    def _agent(self, *, context_manager: ContextManager | None = None, tools: list | None = None) -> BaseAgent:
        # Build a BaseAgent with a fake runner for synchronous recording/binding tests.
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
        child = agent.fork(name="child")
        self.assertEqual(child.handoffs, [])


class CreateHandoffIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_handoffs_visible_in_context_list(self) -> None:
        manager = ContextManager()
        agent = BaseAgent(name="worker", system_prompt="Work.", runner=FakeRunner(), context_manager=manager, tools=[CreateHandoffTool()])

        async def stub_handoff(spec: Handoff) -> Handoff:
            # Replace real model generation with a deterministic fill while keeping real recording/sync.
            return spec.fill({title: f"content::{title}" for title in spec.section_titles()})

        agent.handoff = stub_handoff  # type: ignore[assignment]
        tool = agent.tools._get("create_handoff")
        await tool.execute(_call(handoff_type="engineering", objective="First"))
        await tool.execute(_call(handoff_type="custom", objective="Second", custom_sections={"Note": "g"}))

        self.assertEqual(len(agent.handoffs), 2)
        listing = await ContextListTool(manager).execute(ToolCall(tool_name="context_list"))
        self.assertIn("handoff:1", listing.output)
        self.assertIn("handoff:2", listing.output)
        self.assertIn("(handoff)", listing.output)


if __name__ == "__main__":
    unittest.main()
