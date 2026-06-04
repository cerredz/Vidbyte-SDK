from __future__ import annotations

import json
import unittest

from vidbyte import (
    EngineeringHandoff,
    Handoff,
    HandoffAgent,
    MinimalHandoff,
    ResearchHandoff,
    VidbyteSDK,
)
from vidbyte.agents import BaseAgent
from vidbyte.context import ContextManager
from vidbyte.context.primitives import ContextItem
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts import Prompts


def _is_done_response(final_answer: str) -> "FakeResponse":
    # Build an OpenAI-shaped isDone tool call carrying the given final answer text.
    arguments = json.dumps({"final_answer": final_answer})
    return FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": arguments}]})


class FakeResponse:
    def __init__(self, text: str, raw: dict) -> None:
        self.text = text
        self.raw = raw


class HandoffRunner:
    """Fake runner that finishes by emitting a fixed body as the isDone final answer."""

    def __init__(self, body: str) -> None:
        self.body = body
        self.calls = 0
        self.last_response_format: object | None = None

    def run(self, prompt: str, *, system: str | None = None, **_: object) -> FakeResponse:
        self.calls += 1
        self.last_response_format = _.get("response_format")
        return _is_done_response(self.body)


class ExplodingRunner:
    """Fake runner that always raises, to exercise non-fatal auto-handoff handling."""

    def run(self, prompt: str, *, system: str | None = None, **_: object) -> FakeResponse:
        raise RuntimeError("runner boom")


_ENGINEERING_BODY = (
    "## Objective\nShip the feature.\n\n"
    "## Changes Made\nEdited base.py.\n\n"
    "## Verification Status\nTests pass.\n\n"
    "## Open Threads\nNone.\n\n"
    "## Risks & Gotchas\nWatch the cache.\n\n"
    "## Next Steps\nDeploy.\n"
)


class HandoffPrimitiveTests(unittest.TestCase):
    def test_to_context_text_renders_title_instructions_and_sections(self) -> None:
        handoff = Handoff(sections={"A": "alpha", "B": "beta"}, title="T", instructions="do it")
        text = handoff.to_context_text()
        self.assertIn("T", text)
        self.assertIn("do it", text)
        self.assertIn("## A", text)
        self.assertIn("beta", text)

    def test_empty_sections_render_title_only_and_empty_brief(self) -> None:
        handoff = Handoff(sections={}, title="Solo")
        self.assertEqual(handoff.to_context_text(), "Solo")
        self.assertEqual(handoff.render_section_brief(), "")

    def test_fill_preserves_concrete_subclass(self) -> None:
        filled = EngineeringHandoff().fill({"Objective": "x"})
        self.assertIsInstance(filled, EngineeringHandoff)

    def test_fill_sets_filled_metadata_and_is_filled(self) -> None:
        filled = MinimalHandoff().fill({"Summary": "s", "Next Steps": "n"})
        self.assertTrue(filled.metadata.get("filled"))
        self.assertTrue(filled.is_filled)

    def test_non_string_values_are_coerced(self) -> None:
        handoff = Handoff(sections={"Count": 5})  # type: ignore[dict-item]
        self.assertIn("5", handoff.to_context_text())
        self.assertIn("5", handoff.render_section_brief())

    def test_satisfies_context_item_protocol(self) -> None:
        self.assertIsInstance(EngineeringHandoff(), ContextItem)

    def test_accepted_by_context_manager(self) -> None:
        manager = ContextManager().add(EngineeringHandoff().fill({"Objective": "done"}))
        rendered = manager.to_context()
        joined = "\n".join(artifact.content for artifact in rendered.artifacts)
        self.assertIn("done", joined)

    def test_prebuilts_have_non_empty_distinct_section_maps(self) -> None:
        eng = EngineeringHandoff().sections
        res = ResearchHandoff().sections
        mini = MinimalHandoff().sections
        self.assertTrue(eng and res and mini)
        self.assertNotEqual(eng, res)
        self.assertNotEqual(eng, mini)
        self.assertNotEqual(res, mini)


class HandoffAgentTests(unittest.IsolatedAsyncioTestCase):
    def test_system_prompt_contains_asset_and_all_section_titles(self) -> None:
        agent = HandoffAgent(EngineeringHandoff(), runner=HandoffRunner(_ENGINEERING_BODY))
        prompt = agent.system_prompt
        self.assertIn(Prompts().get(Prompt.HANDOFF_SYSTEM_PROMPT)[:40], prompt)
        for title in EngineeringHandoff().section_titles():
            self.assertIn(title, prompt)

    def test_output_schema_contains_required_section_titles(self) -> None:
        agent = HandoffAgent(EngineeringHandoff(), runner=HandoffRunner(_ENGINEERING_BODY))
        section_schema = agent.output_schema["properties"]["sections"]
        self.assertEqual(section_schema["required"], list(EngineeringHandoff().section_titles()))
        self.assertIn("Objective", section_schema["properties"])

    async def test_generate_handoff_returns_filled_spec_subclass(self) -> None:
        agent = HandoffAgent(EngineeringHandoff(), runner=HandoffRunner(_ENGINEERING_BODY))
        doc = await agent.generate_handoff("the run digest")
        self.assertIsInstance(doc, EngineeringHandoff)
        self.assertTrue(doc.is_filled)
        self.assertEqual(doc.sections["Changes Made"], "Edited base.py.")

    async def test_generate_handoff_uses_structured_json_output_when_available(self) -> None:
        body = json.dumps({"sections": {"Summary": "done", "Next Steps": "ship"}})
        runner = HandoffRunner(body)
        agent = HandoffAgent(MinimalHandoff(), runner=runner)
        doc = await agent.generate_handoff("the run digest")
        self.assertEqual(doc.sections["Summary"], "done")
        self.assertIsNotNone(runner.last_response_format)

    async def test_parse_sections_is_case_insensitive(self) -> None:
        agent = HandoffAgent(MinimalHandoff(), runner=HandoffRunner("## summary\nhi\n## NEXT STEPS\ngo"))
        doc = await agent.generate_handoff("digest")
        self.assertEqual(doc.sections["Summary"], "hi")
        self.assertEqual(doc.sections["Next Steps"], "go")

    async def test_no_headers_stores_raw_output(self) -> None:
        agent = HandoffAgent(MinimalHandoff(), runner=HandoffRunner("just prose, no headers"))
        doc = await agent.generate_handoff("digest")
        self.assertEqual(doc.metadata.get("raw_output"), "just prose, no headers")

    async def test_extra_sections_retained_in_metadata(self) -> None:
        body = "## Summary\ns\n## Next Steps\nn\n## Bonus\nextra"
        agent = HandoffAgent(MinimalHandoff(), runner=HandoffRunner(body))
        doc = await agent.generate_handoff("digest")
        self.assertEqual(doc.metadata.get("extra_sections", {}).get("Bonus"), "extra")

    def test_defaults_to_minimal_handoff(self) -> None:
        agent = HandoffAgent(runner=HandoffRunner("x"))
        self.assertIsInstance(agent.spec, MinimalHandoff)

    def test_does_not_auto_trigger_its_own_handoff(self) -> None:
        agent = HandoffAgent(MinimalHandoff(), runner=HandoffRunner("x"))
        self.assertIsNone(agent._handoff_spec)


class BaseAgentHandoffIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def _agent(self, body: str, *, handoff: Handoff | None = None) -> BaseAgent:
        # Build a base agent wired to a fixed-body fake runner, optionally with an auto-handoff spec.
        return BaseAgent(name="worker", system_prompt="Work.", runner=HandoffRunner(body), handoff=handoff)

    def test_handoff_param_does_not_shadow_method(self) -> None:
        agent = self._agent("x", handoff=MinimalHandoff())
        self.assertIsInstance(agent._handoff_spec, MinimalHandoff)
        self.assertTrue(callable(agent.handoff))

    async def test_auto_handoff_attaches_document_and_sets_last_handoff(self) -> None:
        agent = self._agent(_ENGINEERING_BODY, handoff=EngineeringHandoff())
        reply = await agent.generate_reply("do the task")
        self.assertIsInstance(reply.metadata.get("handoff"), EngineeringHandoff)
        self.assertIsInstance(agent.last_handoff, EngineeringHandoff)
        self.assertEqual(reply.metadata["handoff"].sections["Next Steps"], "Deploy.")

    async def test_no_handoff_when_param_unset(self) -> None:
        agent = self._agent(_ENGINEERING_BODY)
        reply = await agent.generate_reply("do the task")
        self.assertNotIn("handoff", reply.metadata)
        self.assertIsNone(agent.last_handoff)

    async def test_auto_handoff_failure_is_non_fatal(self) -> None:
        agent = BaseAgent(name="w", system_prompt="Work.", runner=ExplodingRunner(), handoff=MinimalHandoff())
        with self.assertRaises(Exception):
            # The primary run itself fails here; ensure the agent surfaces it normally.
            await agent.generate_reply("task")

    async def test_auto_handoff_failure_records_error_without_breaking_reply(self) -> None:
        # Primary run succeeds; only the handoff generation fails.
        agent = self._agent(_ENGINEERING_BODY, handoff=MinimalHandoff())

        original = HandoffAgent.run_auto_handoff

        async def boom(cls: type[HandoffAgent], source_agent: BaseAgent, spec: Handoff | None) -> Handoff:
            raise RuntimeError("handoff boom")

        HandoffAgent.run_auto_handoff = classmethod(boom)  # type: ignore[method-assign]
        try:
            reply = await agent.generate_reply("task")
            self.assertIn("handoff_error", reply.metadata)
            self.assertIsNone(agent.last_handoff)
            self.assertTrue(reply.content)
        finally:
            HandoffAgent.run_auto_handoff = original  # type: ignore[method-assign]

    async def test_handoff_before_any_run_renders_sparse_digest(self) -> None:
        agent = self._agent(_ENGINEERING_BODY)
        digest = HandoffAgent.render_source_run(agent)
        self.assertIn("No completed run recorded.", digest)
        doc = await agent.handoff(MinimalHandoff())
        self.assertIsInstance(doc, MinimalHandoff)

    async def test_render_run_reports_no_tools_when_none_used(self) -> None:
        agent = self._agent(_ENGINEERING_BODY)
        # Before any run, no tool-call contexts exist, so the placeholder branch is exercised.
        self.assertEqual(HandoffAgent.render_tool_calls(agent._tool_call_contexts), "No tools were used.")
        await agent.generate_reply("task")
        digest = HandoffAgent.render_source_run(agent)
        self.assertIn("# Final Result", digest)

    async def test_handoff_by_uses_provided_generator(self) -> None:
        agent = self._agent("primary output")
        await agent.generate_reply("task")
        custom = HandoffAgent(ResearchHandoff(), runner=HandoffRunner("## Question\nq\n## Findings\nf"))
        doc = await agent.handoff(by=custom)
        self.assertIsInstance(doc, ResearchHandoff)
        self.assertEqual(doc.sections["Question"], "q")

    def test_fork_propagates_handoff_spec(self) -> None:
        agent = self._agent("x", handoff=EngineeringHandoff())
        child = agent.fork(name="child")
        self.assertIsInstance(child._handoff_spec, EngineeringHandoff)

    async def test_handoff_reuses_self_runner_by_default(self) -> None:
        runner = HandoffRunner(_ENGINEERING_BODY)
        agent = BaseAgent(name="w", system_prompt="Work.", runner=runner)
        await agent.generate_reply("task")
        before = runner.calls
        await agent.handoff(EngineeringHandoff())
        self.assertGreater(runner.calls, before)


class HandoffPromptCatalogTests(unittest.TestCase):
    def test_handoff_prompt_is_non_empty(self) -> None:
        self.assertTrue(Prompts().get(Prompt.HANDOFF_SYSTEM_PROMPT).strip())

    def test_prompt_enum_asset_sync_validates(self) -> None:
        # Constructing Prompts() runs the two-way enum/asset sync check without raising.
        self.assertIn(Prompt.HANDOFF_SYSTEM_PROMPT, Prompts().keys())


class HandoffExportTests(unittest.IsolatedAsyncioTestCase):
    def test_exports_resolve(self) -> None:
        from vidbyte.agents import HandoffAgent as AgentsHandoffAgent
        from vidbyte.context import Handoff as ContextHandoff

        self.assertIs(AgentsHandoffAgent, HandoffAgent)
        self.assertIs(ContextHandoff, Handoff)

    def test_sdk_agents_handoff_factory(self) -> None:
        sdk = VidbyteSDK()
        self.assertIsInstance(sdk.agents.handoff(), HandoffAgent)

    async def test_end_to_end_handoff_feeds_next_agent(self) -> None:
        producer = BaseAgent(name="p", system_prompt="Work.", runner=HandoffRunner(_ENGINEERING_BODY), handoff=EngineeringHandoff())
        reply = await producer.generate_reply("build it")
        doc = reply.metadata["handoff"]
        self.assertIsInstance(doc, EngineeringHandoff)
        self.assertEqual(doc.sections["Objective"], "Ship the feature.")
        # The produced handoff is a context primitive a fresh agent can ingest directly.
        self.assertIn("Ship the feature.", doc.to_context_text())
        consumer = BaseAgent(name="c", system_prompt="Continue.", runner=HandoffRunner("ok"), context_items=[doc])
        self.assertIn(doc, consumer.context_items)


if __name__ == "__main__":
    unittest.main()
