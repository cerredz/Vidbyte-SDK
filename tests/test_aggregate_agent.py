"""Context Protocol Header

Description:
    Tests for the Multi-Provider Aggregator (Mixture-of-Agents) engine, the
    AggregateAgent class, and BaseAgent's explicit non-aggregation boundary.
Purpose:
    Validates concurrent fan-out, resilient partial failure, synthesis (not
    selection), same-provider labeling, as_tool exposure, and BaseAgent rejection
    of the removed transparent aggregation configuration.
Architecture:
    - Fake agent-likes (generate_reply only) stand in for real provider runners.
Relations:
    Exercises vidbyte/agents/aggregation.py and vidbyte/agents/base.py.
Similar Files:
    - tests/test_pipelines.py: fake-agent duck-typing pattern reused here.
    - tests/test_multi_provider_agentic_grader.py: the select-a-winner sibling.
"""

from __future__ import annotations

import asyncio
import unittest

from vidbyte import (
    AggregateAgent,
    AggregateConfig,
    BaseAgent,
    MultiProviderAggregator,
    ProposerSpec,
    Trace,
    TraceProfile,
)
from vidbyte.lib.dataclasses.agents import AgentForkSettings, AgentMessage, AgentMetadata
from vidbyte.lib.errors import AggregateExecutionError, ConfigurationError
from vidbyte.tools.types import ToolCall, ToolStatus

_TEMPLATE = "REQUEST:\n{request}\n\nCANDIDATES:\n{candidates}"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeAgent:
    """Returns a fixed output and records every prompt it received."""

    def __init__(self, name: str, output: str) -> None:
        self.name = name
        self._output = output
        self.received: list[str] = []

    async def generate_reply(self, message: str, **_: object) -> AgentMessage:
        self.received.append(message)
        return AgentMessage(sender=self.name, recipient="agg", content=self._output)


class SlowAgent:
    """Sleeps before responding, used to exercise per-proposer timeouts."""

    def __init__(self, name: str, output: str, delay: float) -> None:
        self.name = name
        self._output = output
        self._delay = delay

    async def generate_reply(self, message: str, **_: object) -> AgentMessage:
        await asyncio.sleep(self._delay)
        return AgentMessage(sender=self.name, recipient="agg", content=self._output)


class FailingAgent:
    """Always raises."""

    def __init__(self, name: str = "boom") -> None:
        self.name = name

    async def generate_reply(self, message: str, **_: object) -> AgentMessage:
        raise RuntimeError("agent boom")


class BlankAgent:
    """Returns whitespace-only output (a silent failure)."""

    def __init__(self, name: str = "blank") -> None:
        self.name = name

    async def generate_reply(self, message: str, **_: object) -> AgentMessage:
        return AgentMessage(sender=self.name, recipient="agg", content="   ")


class EchoAggregator:
    """Aggregator that echoes its synthesis message so candidate inclusion can be asserted."""

    name = "aggregator"

    def __init__(self) -> None:
        self.last_message: str | None = None

    async def generate_reply(self, message: str, **_: object) -> AgentMessage:
        self.last_message = message
        return AgentMessage(sender="aggregator", recipient="caller", content=f"SYNTH::{message}")


def _engine(proposers, aggregator=None, config=None, template=_TEMPLATE):
    # Builds a MultiProviderAggregator from labeled fake proposers for engine-level tests.
    return MultiProviderAggregator(proposers, aggregator or EchoAggregator(), config or AggregateConfig(), template)


# ---------------------------------------------------------------------------
# MultiProviderAggregator engine
# ---------------------------------------------------------------------------

class MultiProviderAggregatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_synthesizes_from_multiple_candidates(self) -> None:
        # [Edge Case] All candidate outputs and the request reach the aggregator.
        engine = _engine([("a", FakeAgent("a", "alpha-out")), ("b", FakeAgent("b", "beta-out"))])
        result = await engine.aggregate("the-question")
        self.assertTrue(result.content.startswith("SYNTH::"))
        self.assertIn("alpha-out", result.content)
        self.assertIn("beta-out", result.content)
        self.assertIn("the-question", result.content)

    async def test_runs_with_single_proposer(self) -> None:
        # [Edge Case] A single-proposer list still synthesizes.
        engine = _engine([("only", FakeAgent("only", "solo"))])
        result = await engine.aggregate("q")
        self.assertIn("solo", result.content)
        self.assertEqual(list(result.candidates), ["only"])

    async def test_same_prompt_to_every_proposer(self) -> None:
        # [Silent Failure] Every proposer must receive the identical original prompt.
        a, b, c = FakeAgent("a", "1"), FakeAgent("b", "2"), FakeAgent("c", "3")
        await _engine([("a", a), ("b", b), ("c", c)]).aggregate("shared")
        self.assertEqual((a.received, b.received, c.received), (["shared"], ["shared"], ["shared"]))

    async def test_drops_failing_proposer_and_still_synthesizes(self) -> None:
        # [Hidden Failure] A raising proposer is dropped; the survivor is synthesized.
        engine = _engine([("ok", FakeAgent("ok", "good")), ("bad", FailingAgent("bad"))])
        result = await engine.aggregate("q")
        self.assertIn("good", result.content)
        self.assertEqual(result.metadata["aggregate"]["failed_labels"], ["bad"])
        self.assertEqual(result.metadata["aggregate"]["successful_labels"], ["ok"])

    async def test_engine_records_aggregate_spans_with_semantic_tracer(self) -> None:
        # [Silent Failure] Aggregate prebuilt tracing should expose run/proposer/synthesis phases.
        events: list[dict[str, object]] = []
        tracer = Trace.profile(Trace.debug(events), TraceProfile.verbose())
        engine = MultiProviderAggregator([("a", FakeAgent("a", "alpha"))], EchoAggregator(), AggregateConfig(), _TEMPLATE, tracer=tracer)
        await engine.aggregate("q")
        names = [event.get("name") for event in events if event["type"] == "start_span"]
        self.assertIn("aggregate.run", names)
        self.assertIn("aggregate.proposer", names)
        self.assertIn("aggregate.synthesis", names)

    async def test_all_proposers_failing_raises(self) -> None:
        # [Edge Case] When every proposer fails, AggregateExecutionError is raised.
        engine = _engine([("x", FailingAgent("x")), ("y", FailingAgent("y"))])
        with self.assertRaises(AggregateExecutionError):
            await engine.aggregate("q")

    async def test_below_min_successful_raises(self) -> None:
        # [Hidden Assumption] Fewer successes than min_successful aborts the run.
        engine = _engine(
            [("ok", FakeAgent("ok", "good")), ("bad", FailingAgent("bad"))],
            config=AggregateConfig(min_successful=2),
        )
        with self.assertRaises(AggregateExecutionError):
            await engine.aggregate("q")

    async def test_blank_output_treated_as_failure(self) -> None:
        # [Silent Failure] Whitespace-only proposer output is dropped, not synthesized.
        engine = _engine([("ok", FakeAgent("ok", "good")), ("blank", BlankAgent("blank"))])
        result = await engine.aggregate("q")
        self.assertEqual(list(result.candidates), ["ok"])
        self.assertIn("blank", result.metadata["aggregate"]["failed_labels"])

    async def test_truncates_candidate_text(self) -> None:
        # [Silent Failure] Candidate text is capped at max_candidate_chars in the synthesis block.
        aggregator = EchoAggregator()
        engine = _engine(
            [("a", FakeAgent("a", "x" * 500))],
            aggregator=aggregator,
            config=AggregateConfig(max_candidate_chars=10),
        )
        await engine.aggregate("q")
        self.assertIsNotNone(aggregator.last_message)
        self.assertNotIn("x" * 50, aggregator.last_message)
        self.assertIn("[truncated]", aggregator.last_message)

    async def test_honors_per_proposer_timeout(self) -> None:
        # [Hidden Failure] A proposer exceeding the timeout is dropped, not awaited forever.
        engine = _engine(
            [("fast", FakeAgent("fast", "quick")), ("slow", SlowAgent("slow", "late", 0.5))],
            config=AggregateConfig(per_proposer_timeout=0.05),
        )
        result = await engine.aggregate("q")
        self.assertEqual(list(result.candidates), ["fast"])
        self.assertIn("slow", result.metadata["aggregate"]["failed_labels"])

    async def test_max_concurrency_one_still_synthesizes(self) -> None:
        # [Edge Case] Bounding concurrency to 1 serializes proposers but preserves output.
        engine = _engine(
            [("a", FakeAgent("a", "one")), ("b", FakeAgent("b", "two"))],
            config=AggregateConfig(max_concurrency=1),
        )
        result = await engine.aggregate("q")
        self.assertEqual(len(result.candidates), 2)

    def test_template_missing_placeholders_raises(self) -> None:
        # [Hidden Assumption] A synthesis template without {request}/{candidates} is rejected.
        with self.assertRaises(ConfigurationError):
            MultiProviderAggregator([("a", FakeAgent("a", "x"))], EchoAggregator(), AggregateConfig(), "no placeholders")

    def test_empty_proposers_raises(self) -> None:
        # [Edge Case] The engine requires at least one proposer.
        with self.assertRaises(ConfigurationError):
            MultiProviderAggregator([], EchoAggregator(), AggregateConfig(), _TEMPLATE)


# ---------------------------------------------------------------------------
# AggregateAgent
# ---------------------------------------------------------------------------

class AggregateAgentTests(unittest.IsolatedAsyncioTestCase):
    def _agent(self, **overrides):
        # Builds an AggregateAgent over fake proposers and a fake aggregator unless overridden.
        kwargs = dict(
            name="agg",
            system_prompt="synthesize",
            proposers=[FakeAgent("a", "alpha"), FakeAgent("b", "beta")],
            aggregator=EchoAggregator(),
            config=AggregateConfig(synthesis_prompt_template=_TEMPLATE),
        )
        kwargs.update(overrides)
        return AggregateAgent(**kwargs)

    def test_empty_proposers_raises(self) -> None:
        # [Edge Case] Construction rejects an empty proposer list.
        with self.assertRaises(ConfigurationError):
            AggregateAgent(name="agg", system_prompt="s", proposers=[], aggregator=EchoAggregator())

    def test_unresolvable_aggregator_raises(self) -> None:
        # [Hidden Assumption] No aggregator and no host model is a construction error.
        with self.assertRaises(ConfigurationError):
            AggregateAgent(name="agg", system_prompt="s", proposers=[ProposerSpec("openai", "gpt-4.1")])

    async def test_reply_metadata_carries_candidates(self) -> None:
        # [Edge Case] The synthesized reply exposes per-candidate detail in metadata.
        reply = await self._agent().generate_reply("q")
        self.assertTrue(reply.content.startswith("SYNTH::"))
        self.assertEqual(set(reply.metadata["aggregate"]["candidates"]), {"a", "b"})

    async def test_fork_preserves_aggregation(self) -> None:
        # [Hidden Assumption] A fork keeps aggregating rather than degrading to single-model.
        child = self._agent().fork()
        reply = await child.generate_reply("q")
        self.assertTrue(reply.content.startswith("SYNTH::"))

    def test_fork_rejects_unsupported_overrides(self) -> None:
        # [Hidden Failure] Unsupported AggregateAgent fork overrides must not be silently ignored.
        with self.assertRaises(ConfigurationError) as ctx:
            self._agent().fork(AgentForkSettings(system_prompt="different"))
        self.assertIn("system_prompt", str(ctx.exception))

    def test_as_tool_requires_metadata(self) -> None:
        # [Hidden Assumption] as_tool() refuses to expose an agent without agent_metadata.
        with self.assertRaises(ConfigurationError):
            self._agent().as_tool()

    def test_as_tool_returns_tool_with_metadata(self) -> None:
        # [Edge Case] With metadata filled, as_tool() returns a usable AgentTool.
        meta = AgentMetadata(name="aggregate_tool", description="d", use_cases="u")
        tool = self._agent(agent_metadata=meta).as_tool()
        self.assertEqual(tool.spec().name, "aggregate_tool")

    async def test_as_tool_execution_aggregates(self) -> None:
        # [Hidden Failure] Invoking the agent tool runs the full aggregation through a fork.
        meta = AgentMetadata(name="aggregate_tool", description="d", use_cases="u")
        tool = self._agent(agent_metadata=meta).as_tool()
        result = await tool.execute(ToolCall("aggregate_tool", {}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertIn("SYNTH::", result.output)

    def test_builds_distinct_child_agents_with_same_provider(self) -> None:
        # [Silent Failure] Two same-provider proposers get distinct labels.
        agent = AggregateAgent(
            name="agg",
            system_prompt="s",
            proposers=[ProposerSpec("openai", "gpt-4.1"), ProposerSpec("openai", "gpt-4.1")],
            aggregator=("openai", "gpt-4.1"),
        )
        labels = [label for label, _ in agent._engine._proposers]
        self.assertEqual(len(labels), 2)
        self.assertEqual(len(set(labels)), 2)


# ---------------------------------------------------------------------------
# BaseAgent aggregation removal
# ---------------------------------------------------------------------------

class BaseAgentAggregationRemovalTests(unittest.TestCase):
    def test_model_name_list_rejected(self) -> None:
        # [Edge Case] A model list no longer activates hidden aggregation.
        with self.assertRaises(ConfigurationError):
            BaseAgent(name="w", system_prompt="s", provider="openai", model_name=["gpt-4.1", "gpt-4.1-mini"])

    def test_single_element_model_name_list_rejected(self) -> None:
        # [Edge Case] Single-element model lists are rejected instead of unwrapped.
        with self.assertRaises(ConfigurationError):
            BaseAgent(name="w", system_prompt="s", provider="openai", model_name=["gpt-4.1"])

    def test_single_model_name_no_plan(self) -> None:
        # [Silent Failure] A single string model keeps the normal single-model path.
        agent = BaseAgent(name="w", system_prompt="s", provider="openai", model_name="gpt-4.1")
        self.assertFalse(hasattr(agent, "_aggregate_agent"))
        self.assertFalse(hasattr(agent, "_aggregate_plan"))
        self.assertEqual(agent.runner_config.model_name, "gpt-4.1")

    def test_proposers_keyword_rejected(self) -> None:
        # [Hidden Assumption] BaseAgent no longer accepts proposer configuration.
        with self.assertRaises(TypeError):
            BaseAgent(name="w", system_prompt="s", proposers=[FakeAgent("a", "alpha")])

    def test_aggregator_keyword_rejected(self) -> None:
        # [Hidden Assumption] BaseAgent no longer accepts aggregator configuration.
        with self.assertRaises(TypeError):
            BaseAgent(name="w", system_prompt="s", aggregator=EchoAggregator())

    def test_aggregate_keyword_rejected(self) -> None:
        # [Hidden Assumption] BaseAgent no longer accepts aggregate run configuration.
        with self.assertRaises(TypeError):
            BaseAgent(name="w", system_prompt="s", aggregate=AggregateConfig())


# ---------------------------------------------------------------------------
# Prompt catalog + exports
# ---------------------------------------------------------------------------

class PromptAndExportTests(unittest.TestCase):
    def test_aggregator_prompt_family_loads(self) -> None:
        # [Hidden Assumption] The catalog exposes both synthesis assets.
        from vidbyte.prompts import Prompts

        family = Prompts().family("multi_provider_aggregator")
        self.assertEqual(set(family), {"synthesis_system_prompt", "synthesis_prompt"})

    def test_synthesis_template_has_placeholders(self) -> None:
        # [Silent Failure] The default synthesis template exposes {request} and {candidates}.
        from vidbyte.prompts import Prompts
        from vidbyte.lib.enums.prompts import Prompt

        template = Prompts().get(Prompt.MULTI_PROVIDER_AGGREGATOR_SYNTHESIS_PROMPT)
        self.assertIn("{request}", template)
        self.assertIn("{candidates}", template)

    def test_public_exports_importable(self) -> None:
        # [Edge Case] All public aggregation symbols import from the package root.
        import vidbyte

        for name in ("AggregateAgent", "MultiProviderAggregator", "ProposerSpec", "AggregateConfig"):
            self.assertTrue(hasattr(vidbyte, name), name)


if __name__ == "__main__":
    unittest.main()
