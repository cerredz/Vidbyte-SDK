from __future__ import annotations

import unittest

from vidbyte.lib.dataclasses.agents import AgentMessage
from vidbyte.lib.errors import PipelineExecutionError
from vidbyte.pipelines import (
    BasePipeline,
    ConditionalPipeline,
    MapReducePipeline,
    ParallelPipeline,
    SequentialPipeline,
)
from vidbyte.pipelines.parallel import PARALLEL_JOIN_SEPARATOR


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class EchoAgent:
    """Returns its input unchanged."""

    def __init__(self, name: str = "echo") -> None:
        self.name = name

    async def generate_reply(self, message: str, **_: object) -> AgentMessage:
        return AgentMessage(sender=self.name, recipient="pipeline", content=message)


class PrefixAgent:
    """Prepends a fixed string to its input."""

    def __init__(self, prefix: str, name: str = "prefix") -> None:
        self.name = name
        self._prefix = prefix

    async def generate_reply(self, message: str, **_: object) -> AgentMessage:
        return AgentMessage(
            sender=self.name,
            recipient="pipeline",
            content=f"{self._prefix}{message}",
        )


class FailingAgent:
    """Always raises."""

    name = "failing"

    async def generate_reply(self, message: str, **_: object) -> AgentMessage:
        raise RuntimeError("agent boom")


# ---------------------------------------------------------------------------
# SequentialPipeline
# ---------------------------------------------------------------------------

class SequentialPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_stage_returns_agent_output(self) -> None:
        pipeline = SequentialPipeline([PrefixAgent("A:")])
        result = await pipeline.run("hello")
        self.assertEqual(result, "A:hello")

    async def test_chains_output_to_input(self) -> None:
        pipeline = SequentialPipeline([PrefixAgent("A:"), PrefixAgent("B:")])
        result = await pipeline.run("x")
        self.assertEqual(result, "B:A:x")

    async def test_three_stages_threads_correctly(self) -> None:
        pipeline = SequentialPipeline([
            PrefixAgent("1:"),
            PrefixAgent("2:"),
            PrefixAgent("3:"),
        ])
        result = await pipeline.run("start")
        self.assertEqual(result, "3:2:1:start")

    def test_empty_stages_raises_at_construction(self) -> None:
        with self.assertRaises(PipelineExecutionError):
            SequentialPipeline([])

    async def test_agent_failure_propagates(self) -> None:
        pipeline = SequentialPipeline([PrefixAgent("ok:"), FailingAgent()])
        with self.assertRaises(RuntimeError):
            await pipeline.run("prompt")

    async def test_nested_parallel_pipeline_as_stage(self) -> None:
        inner = ParallelPipeline([PrefixAgent("A:"), PrefixAgent("B:")], separator="|")
        pipeline = SequentialPipeline([PrefixAgent("outer:"), inner])
        result = await pipeline.run("x")
        self.assertIn("A:outer:x", result)
        self.assertIn("B:outer:x", result)
        self.assertIn("|", result)


# ---------------------------------------------------------------------------
# ParallelPipeline
# ---------------------------------------------------------------------------

class ParallelPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_stage_returns_agent_output(self) -> None:
        pipeline = ParallelPipeline([PrefixAgent("A:")])
        result = await pipeline.run("x")
        self.assertEqual(result, "A:x")

    async def test_joins_outputs_with_default_separator(self) -> None:
        pipeline = ParallelPipeline([PrefixAgent("A:"), PrefixAgent("B:")])
        result = await pipeline.run("x")
        self.assertIn("A:x", result)
        self.assertIn("B:x", result)
        self.assertIn(PARALLEL_JOIN_SEPARATOR, result)

    async def test_all_stages_receive_same_input(self) -> None:
        received: list[str] = []

        class RecordingAgent:
            name = "recorder"

            async def generate_reply(self, message: str, **_: object) -> AgentMessage:
                received.append(message)
                return AgentMessage(sender="recorder", recipient="pipeline", content=message)

        pipeline = ParallelPipeline([RecordingAgent(), RecordingAgent(), RecordingAgent()])
        await pipeline.run("shared")
        self.assertEqual(received, ["shared", "shared", "shared"])

    def test_empty_stages_raises_at_construction(self) -> None:
        with self.assertRaises(PipelineExecutionError):
            ParallelPipeline([])

    async def test_custom_separator(self) -> None:
        pipeline = ParallelPipeline([PrefixAgent("A:"), PrefixAgent("B:")], separator=" | ")
        result = await pipeline.run("x")
        self.assertIn(" | ", result)

    async def test_agent_failure_propagates(self) -> None:
        pipeline = ParallelPipeline([PrefixAgent("ok:"), FailingAgent()])
        with self.assertRaises(RuntimeError):
            await pipeline.run("prompt")

    async def test_nested_sequential_pipeline_as_stage(self) -> None:
        inner = SequentialPipeline([PrefixAgent("X:"), PrefixAgent("Y:")])
        pipeline = ParallelPipeline([inner, PrefixAgent("Z:")])
        result = await pipeline.run("a")
        self.assertIn("Y:X:a", result)
        self.assertIn("Z:a", result)


# ---------------------------------------------------------------------------
# ConditionalPipeline
# ---------------------------------------------------------------------------

class ConditionalPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_routes_to_correct_branch(self) -> None:
        pipeline = ConditionalPipeline(
            predicate=lambda p: "code" if "code" in p else "prose",
            branches={
                "code": PrefixAgent("CODE:"),
                "prose": PrefixAgent("PROSE:"),
            },
        )
        result = await pipeline.run("write some code please")
        self.assertEqual(result, "CODE:write some code please")

    async def test_routes_to_fallback_branch(self) -> None:
        pipeline = ConditionalPipeline(
            predicate=lambda p: "code" if "code" in p else "prose",
            branches={
                "code": PrefixAgent("CODE:"),
                "prose": PrefixAgent("PROSE:"),
            },
        )
        result = await pipeline.run("tell me a story")
        self.assertEqual(result, "PROSE:tell me a story")

    async def test_unknown_key_raises(self) -> None:
        pipeline = ConditionalPipeline(
            predicate=lambda _: "unknown",
            branches={"code": EchoAgent()},
        )
        with self.assertRaises(PipelineExecutionError) as ctx:
            await pipeline.run("anything")
        self.assertIn("unknown", str(ctx.exception))
        self.assertIn("code", str(ctx.exception))

    def test_empty_branches_raises_at_construction(self) -> None:
        with self.assertRaises(PipelineExecutionError):
            ConditionalPipeline(predicate=lambda _: "x", branches={})

    async def test_predicate_receives_original_prompt(self) -> None:
        received: list[str] = []

        def pred(p: str) -> str:
            received.append(p)
            return "a"

        pipeline = ConditionalPipeline(pred, branches={"a": EchoAgent()})
        await pipeline.run("the-prompt")
        self.assertEqual(received, ["the-prompt"])

    async def test_branch_receives_original_prompt(self) -> None:
        pipeline = ConditionalPipeline(
            predicate=lambda _: "branch",
            branches={"branch": EchoAgent()},
        )
        result = await pipeline.run("original")
        self.assertEqual(result, "original")


# ---------------------------------------------------------------------------
# MapReducePipeline
# ---------------------------------------------------------------------------

class MapReducePipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_map_stage_produces_reduced_output(self) -> None:
        pipeline = MapReducePipeline(
            map_stages=[PrefixAgent("map:")],
            reduce_stage=PrefixAgent("reduce:"),
        )
        result = await pipeline.run("x")
        self.assertEqual(result, "reduce:map:x")

    async def test_multiple_map_stages_converge_to_reducer(self) -> None:
        pipeline = MapReducePipeline(
            map_stages=[PrefixAgent("A:"), PrefixAgent("B:")],
            reduce_stage=PrefixAgent("reduce:"),
        )
        result = await pipeline.run("x")
        self.assertIn("A:x", result)
        self.assertIn("B:x", result)
        self.assertTrue(result.startswith("reduce:"))

    async def test_map_stages_receive_same_input(self) -> None:
        received: list[str] = []

        class RecordingAgent:
            name = "recorder"

            async def generate_reply(self, message: str, **_: object) -> AgentMessage:
                received.append(message)
                return AgentMessage(sender="recorder", recipient="pipeline", content=message)

        pipeline = MapReducePipeline(
            map_stages=[RecordingAgent(), RecordingAgent(), RecordingAgent()],
            reduce_stage=EchoAgent(),
        )
        await pipeline.run("shared")
        self.assertEqual(received, ["shared", "shared", "shared"])

    def test_empty_map_stages_raises_at_construction(self) -> None:
        with self.assertRaises(PipelineExecutionError):
            MapReducePipeline(map_stages=[], reduce_stage=EchoAgent())

    async def test_map_stage_failure_propagates(self) -> None:
        pipeline = MapReducePipeline(
            map_stages=[PrefixAgent("ok:"), FailingAgent()],
            reduce_stage=EchoAgent(),
        )
        with self.assertRaises(RuntimeError):
            await pipeline.run("prompt")

    async def test_reduce_stage_failure_propagates(self) -> None:
        pipeline = MapReducePipeline(
            map_stages=[PrefixAgent("A:")],
            reduce_stage=FailingAgent(),
        )
        with self.assertRaises(RuntimeError):
            await pipeline.run("prompt")

    async def test_custom_separator(self) -> None:
        pipeline = MapReducePipeline(
            map_stages=[PrefixAgent("A:"), PrefixAgent("B:")],
            reduce_stage=EchoAgent(),
            separator=" | ",
        )
        result = await pipeline.run("x")
        self.assertIn(" | ", result)

    async def test_nested_pipeline_as_map_stage(self) -> None:
        inner = SequentialPipeline([PrefixAgent("inner:")])
        pipeline = MapReducePipeline(
            map_stages=[inner, PrefixAgent("direct:")],
            reduce_stage=EchoAgent(),
        )
        result = await pipeline.run("x")
        self.assertIn("inner:x", result)
        self.assertIn("direct:x", result)

    async def test_nested_pipeline_as_reduce_stage(self) -> None:
        reduce_stage = ParallelPipeline([PrefixAgent("X:"), PrefixAgent("Y:")], separator="|")
        pipeline = MapReducePipeline(
            map_stages=[PrefixAgent("map:")],
            reduce_stage=reduce_stage,
        )
        result = await pipeline.run("x")
        self.assertIn("X:map:x", result)
        self.assertIn("Y:map:x", result)

    async def test_is_base_pipeline_instance(self) -> None:
        pipeline = MapReducePipeline(map_stages=[EchoAgent()], reduce_stage=EchoAgent())
        self.assertIsInstance(pipeline, BasePipeline)


# ---------------------------------------------------------------------------
# run_sync
# ---------------------------------------------------------------------------

class RunSyncTests(unittest.TestCase):
    def test_run_sync_sequential(self) -> None:
        pipeline = SequentialPipeline([PrefixAgent("sync:")])
        result = pipeline.run_sync("hello")
        self.assertEqual(result, "sync:hello")

    def test_run_sync_parallel(self) -> None:
        pipeline = ParallelPipeline([PrefixAgent("A:"), PrefixAgent("B:")], separator="|")
        result = pipeline.run_sync("x")
        self.assertIn("A:x", result)
        self.assertIn("B:x", result)

    def test_run_sync_map_reduce(self) -> None:
        pipeline = MapReducePipeline(
            map_stages=[PrefixAgent("map:")],
            reduce_stage=PrefixAgent("reduce:"),
        )
        result = pipeline.run_sync("x")
        self.assertEqual(result, "reduce:map:x")


# ---------------------------------------------------------------------------
# Composability
# ---------------------------------------------------------------------------

class ComposabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_sequential_wraps_parallel(self) -> None:
        pipeline = SequentialPipeline([
            PrefixAgent("first:"),
            ParallelPipeline([PrefixAgent("A:"), PrefixAgent("B:")], separator="|"),
        ])
        result = await pipeline.run("x")
        self.assertIn("A:first:x", result)
        self.assertIn("B:first:x", result)

    async def test_parallel_wraps_sequential(self) -> None:
        inner = SequentialPipeline([PrefixAgent("p:"), PrefixAgent("q:")])
        pipeline = ParallelPipeline([inner, PrefixAgent("Z:")], separator="|")
        result = await pipeline.run("x")
        self.assertIn("q:p:x", result)
        self.assertIn("Z:x", result)

    async def test_three_level_nesting(self) -> None:
        level1 = SequentialPipeline([PrefixAgent("L1:")])
        level2 = ParallelPipeline([level1, PrefixAgent("L2:")], separator="|")
        level3 = SequentialPipeline([PrefixAgent("outer:"), level2])
        result = await level3.run("x")
        self.assertIn("L1:outer:x", result)
        self.assertIn("L2:outer:x", result)

    async def test_pipeline_is_base_pipeline_instance(self) -> None:
        for cls in (SequentialPipeline, ParallelPipeline):
            pipeline = cls([EchoAgent()])
            self.assertIsInstance(pipeline, BasePipeline)


if __name__ == "__main__":
    unittest.main()
