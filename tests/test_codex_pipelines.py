"""FILE: tests/test_codex_pipelines.py

PURPOSE:
    Feature tests for Codex pipeline composition: the VidbyteAgent protocol,
    CodexVidbyteTranslator.translate_input, CodexHarnessAgent.generate_reply
    and its option rejection, the per-agent turn lock, and all four pipeline
    topologies running Codex stages. Locks the behavior
    docs/design/codex-pipelines.md specifies: distinct agents fan out
    concurrently while one agent used twice serializes, and an unsupported
    run option fails rather than being dropped.

ROLE IN CODEBASE:
    Exercises vidbyte/lib/agents/protocol.py, the translation in
    vidbyte/agents/codex/config.py, the entry points and lock in
    vidbyte/agents/codex/agent.py, and vidbyte/pipelines/types.py, against
    the real SequentialPipeline, ParallelPipeline, MapReducePipeline, and
    ConditionalPipeline.

ARCHITECTURE NOTE:
    Every test runs offline. Concurrency is proven with an event-gated
    transport rather than sleeps, so "both turns were in flight" is a
    deterministic assertion and not a timing race.

FUNCTION INVENTORY:
    No production functions. _GatedTransport blocks until released,
    _EchoTransport returns a reply naming the prompt it saw, and
    _build_agent() wires an agent to whichever transport a test needs.

COMMON MODIFICATION PATTERNS:
    Add a pipeline topology, then add its Codex-stage case to
    PipelineTopologyTests; add a protocol member, then add its conformance
    case to AgentProtocolTests.

WHAT NOT TO DO IN THIS FILE:
    Do not use sleeps to prove concurrency, and do not assert that a dropped
    run option is acceptable — it must raise.

KNOWN EDGE CASES:
    A cancelled turn must release the lock, or every later turn on that agent
    would deadlock; the protocol has a non-method member, so isinstance works
    but issubclass does not.

RELATED DOCS: docs/design/codex-pipelines.md
TESTS: python -m pytest tests/test_codex_pipelines.py
"""

from __future__ import annotations

import asyncio
import unittest

from vidbyte.agents.codex.agent import CodexHarnessAgent
from vidbyte.agents.codex.config import CodexVidbyteTranslator
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives import TextContextItem
from vidbyte.lib.agents.protocol import VidbyteAgent
from vidbyte.lib.dataclasses.agents import AgentInput
from vidbyte.lib.dataclasses.codex import (
    CodexHarnessAgentSettings,
    CodexImageInput,
    CodexRunInput,
    CodexRunResult,
    CodexTextInput,
    CodexTransportRunRequest,
    CodexUsage,
)
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError, ConfigurationError
from vidbyte.pipelines.conditional import ConditionalPipeline
from vidbyte.pipelines.map_reduce import MapReducePipeline
from vidbyte.pipelines.parallel import ParallelPipeline
from vidbyte.pipelines.sequential import SequentialPipeline

THREAD_ID = "th_1"


def _run_result(text: str, thread_id: str = THREAD_ID) -> CodexRunResult:
    # Builds one completed turn whose response names the prompt it answered.
    return CodexRunResult(
        thread_id=thread_id,
        turn_id="tu_1",
        status="completed",
        final_response=text,
        duration_ms=1,
        usage=CodexUsage(),
        items=(),
    )


class _EchoTransport:
    """Returns a reply naming the prompt it received, recording every request."""

    def __init__(self, label: str = "echo") -> None:
        self.label = label
        self.requests: list[CodexTransportRunRequest] = []

    async def run(self, request: CodexTransportRunRequest) -> CodexRunResult:
        # Echoing the prompt is what lets a sequential test prove output threading.
        self.requests.append(request)
        return _run_result(f"{self.label}({request.prompt.user_prompt})")


class _GatedTransport:
    """Blocks each turn until released, so concurrency is deterministic."""

    def __init__(self, label: str = "gated") -> None:
        self.label = label
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.concurrent = 0
        self.max_concurrent = 0
        self.requests: list[CodexTransportRunRequest] = []

    async def run(self, request: CodexTransportRunRequest) -> CodexRunResult:
        # Tracks peak concurrency, which is what proves serialization or its absence.
        self.requests.append(request)
        self.concurrent += 1
        self.max_concurrent = max(self.max_concurrent, self.concurrent)
        self.entered.set()
        await self.release.wait()
        self.concurrent -= 1
        return _run_result(f"{self.label}({request.prompt.user_prompt})")


class _FailingTransport:
    """Raises a classified adapter failure on every turn."""

    async def run(self, request: CodexTransportRunRequest) -> CodexRunResult:
        # Simulates a provider failure reaching the pipeline.
        del request
        raise CodexAgentError(
            "Codex failed the requested turn.",
            failure_code=FailureCode.CODEX_TURN_FAILED.value,
            operation="turn_run",
        )


def _build_agent(transport: object | None = None, name: str = "codex-agent") -> CodexHarnessAgent:
    # Builds an agent whose transport is a fake, so no Codex process is started.
    agent = CodexHarnessAgent(
        CodexHarnessAgentSettings(name=name, system_prompt="You are a Codex agent.")
    )
    agent._transport = transport if transport is not None else _EchoTransport()  # type: ignore[assignment]
    return agent


class _DirectAnswerRunner:
    """Minimal offline runner: answers immediately through the isDone tool call."""

    def run(self, prompt: str, *, system: str | None = None, **_: object) -> object:
        # Mirrors tests/test_agent_base.py's EchoRunner, the repo's offline fixture shape.
        del system
        return _FakeResponse(
            {
                "output": [
                    {
                        "type": "function_call",
                        "name": "isDone",
                        "arguments": '{"final_answer": "base:%s"}' % prompt,
                    }
                ]
            }
        )


class _FakeResponse:
    """Shapes a provider response the direct runtime can read."""

    def __init__(self, raw: dict) -> None:
        self.text = ""
        self.raw = raw


def _build_base_agent(name: str = "base-agent") -> object:
    # Builds a real BaseAgent bound to an offline runner, for protocol and mixed-pipeline tests.
    from tests.agent_test_support import build_test_agent

    return build_test_agent(
        name=name, system_prompt="Answer directly.", runner=_DirectAnswerRunner()
    )


class AgentProtocolTests(unittest.TestCase):
    """Covers which objects satisfy the shared agent call contract."""

    def test_codex_harness_agent_satisfies_the_protocol(self) -> None:
        self.assertIsInstance(_build_agent(), VidbyteAgent)

    def test_base_agent_satisfies_the_protocol(self) -> None:
        self.assertIsInstance(_build_base_agent(), VidbyteAgent)

    def test_an_object_missing_generate_reply_does_not_satisfy_it(self) -> None:
        class Partial:
            name = "partial"

            async def arun(self, message: object, **options: object) -> object:
                return message

        self.assertNotIsInstance(Partial(), VidbyteAgent)


class TranslateInputTests(unittest.TestCase):
    """Covers the conversion from any caller shape into one native request."""

    def setUp(self) -> None:
        self.translator = CodexVidbyteTranslator()

    def test_returns_the_identical_codex_run_input_object(self) -> None:
        request = CodexRunInput(
            items=(CodexTextInput("a"), CodexImageInput("data:image/png;base64,AA"))
        )

        self.assertIs(self.translator.translate_input(request), request)

    def test_converts_a_string_into_one_text_item_for_the_user(self) -> None:
        request = self.translator.translate_input("hello")

        self.assertEqual(request.items, (CodexTextInput("hello"),))
        self.assertEqual(request.recipient, "user")

    def test_maps_every_agent_input_field(self) -> None:
        item = TextContextItem(title="Doc", content="body")

        request = self.translator.translate_input(
            AgentInput(prompt="p", metadata={"trace": "x"}, context_items=(item,))
        )

        self.assertEqual(request.items, (CodexTextInput("p"),))
        self.assertEqual(request.metadata, {"trace": "x"})
        self.assertEqual(request.context_items, (item,))

    def test_preserves_context_manager_identity(self) -> None:
        manager = ContextManager()

        request = self.translator.translate_input(
            AgentInput(prompt="p", context_manager=manager)
        )

        self.assertIs(request.context_manager, manager)

    def test_rejects_unsupported_input_types(self) -> None:
        for value in (None, 7, [CodexTextInput("a")]):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(ConfigurationError):
                    self.translator.translate_input(value)  # type: ignore[arg-type]

    def test_rejects_an_empty_prompt(self) -> None:
        with self.assertRaises(ConfigurationError):
            self.translator.translate_input("")


class GenerateReplyTests(unittest.IsolatedAsyncioTestCase):
    """Covers the pipeline-facing entry point and its option policy."""

    async def test_returns_the_same_reply_arun_returns(self) -> None:
        agent = _build_agent()

        reply = await agent.generate_reply("hello")

        self.assertEqual(reply.content, "echo(hello)")

    async def test_accepts_no_options(self) -> None:
        agent = _build_agent()

        self.assertEqual((await agent.generate_reply("hi")).content, "echo(hi)")

    async def test_rejects_an_unsupported_option_naming_it(self) -> None:
        agent = _build_agent()

        with self.assertRaises(CodexAgentError) as caught:
            await agent.generate_reply("hi", context="extra")

        self.assertEqual(
            caught.exception.failure_code,
            FailureCode.CODEX_RUN_OPTION_UNSUPPORTED.value,
        )
        self.assertIn("context", str(caught.exception))

    async def test_names_every_unsupported_option_at_once(self) -> None:
        agent = _build_agent()

        with self.assertRaises(CodexAgentError) as caught:
            await agent.generate_reply("hi", context="a", history=[])

        message = str(caught.exception)
        self.assertIn("context", message)
        self.assertIn("history", message)

    async def test_an_invalid_input_is_classified_before_the_transport(self) -> None:
        transport = _EchoTransport()
        agent = _build_agent(transport)

        with self.assertRaises(CodexAgentError) as caught:
            await agent.generate_reply("")

        self.assertEqual(caught.exception.operation, "translate_input")
        self.assertEqual(transport.requests, [])


class TurnSerializationTests(unittest.IsolatedAsyncioTestCase):
    """Covers the per-agent lock that makes fan-out safe."""

    async def test_two_distinct_agents_run_concurrently(self) -> None:
        first, second = _GatedTransport("a"), _GatedTransport("b")
        agent_one = _build_agent(first, name="one")
        agent_two = _build_agent(second, name="two")

        task = asyncio.gather(agent_one.arun("p"), agent_two.arun("p"))
        await asyncio.wait_for(first.entered.wait(), timeout=1)
        await asyncio.wait_for(second.entered.wait(), timeout=1)
        first.release.set()
        second.release.set()
        await task

        self.assertEqual(first.max_concurrent, 1)
        self.assertEqual(second.max_concurrent, 1)

    async def test_one_agent_used_twice_serializes_its_turns(self) -> None:
        transport = _GatedTransport()
        agent = _build_agent(transport)

        task = asyncio.gather(agent.arun("first"), agent.arun("second"))
        await asyncio.wait_for(transport.entered.wait(), timeout=1)
        transport.release.set()
        await task

        self.assertEqual(transport.max_concurrent, 1)
        self.assertEqual(len(agent.history), 2)

    async def test_the_second_serialized_turn_resumes_the_first_thread(self) -> None:
        transport = _GatedTransport()
        agent = _build_agent(transport)
        transport.release.set()

        await asyncio.gather(agent.arun("first"), agent.arun("second"))

        self.assertEqual(transport.requests[0].thread_id, "")
        self.assertEqual(transport.requests[1].thread_id, THREAD_ID)

    async def test_the_usage_rollup_describes_the_last_completed_turn(self) -> None:
        transport = _GatedTransport()
        agent = _build_agent(transport)
        transport.release.set()

        await asyncio.gather(agent.arun("first"), agent.arun("second"))

        # Per-turn reset means one record, not two accumulated across the fan-out.
        self.assertEqual(agent.get_usage().model_call_count, 0)
        self.assertEqual(len(agent.history), 2)

    async def test_a_cancelled_turn_releases_the_lock(self) -> None:
        transport = _GatedTransport()
        agent = _build_agent(transport)
        cancelled = asyncio.create_task(agent.arun("first"))
        await asyncio.wait_for(transport.entered.wait(), timeout=1)

        cancelled.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await cancelled
        transport.release.set()
        reply = await asyncio.wait_for(agent.arun("second"), timeout=1)

        self.assertIn("second", reply.content)


class PipelineTopologyTests(unittest.IsolatedAsyncioTestCase):
    """Covers a Codex agent as a stage in each pipeline topology."""

    async def test_sequential_threads_output_into_the_next_prompt(self) -> None:
        first = _build_agent(_EchoTransport("first"), name="one")
        second_transport = _EchoTransport("second")
        second = _build_agent(second_transport, name="two")

        output = await SequentialPipeline((first, second)).run("start")

        self.assertEqual(output, "second(first(start))")
        self.assertIn("first(start)", second_transport.requests[0].prompt.user_prompt)

    async def test_parallel_joins_two_distinct_codex_agents(self) -> None:
        pipeline = ParallelPipeline(
            (
                _build_agent(_EchoTransport("a"), name="one"),
                _build_agent(_EchoTransport("b"), name="two"),
            )
        )

        output = await pipeline.run("go")

        self.assertIn("a(go)", output)
        self.assertIn("b(go)", output)

    async def test_parallel_with_the_same_agent_twice_completes(self) -> None:
        agent = _build_agent()

        output = await ParallelPipeline((agent, agent)).run("go")

        self.assertEqual(output.count("echo(go)"), 2)
        self.assertEqual(len(agent.history), 2)

    async def test_map_reduce_feeds_joined_output_to_a_codex_reducer(self) -> None:
        reduce_transport = _EchoTransport("reduce")
        pipeline = MapReducePipeline(
            (
                _build_agent(_EchoTransport("m1"), name="one"),
                _build_agent(_EchoTransport("m2"), name="two"),
            ),
            _build_agent(reduce_transport, name="reducer"),
        )

        output = await pipeline.run("go")

        joined = reduce_transport.requests[0].prompt.user_prompt
        self.assertIn("m1(go)", joined)
        self.assertIn("m2(go)", joined)
        self.assertTrue(output.startswith("reduce("))

    async def test_conditional_routes_to_a_codex_branch(self) -> None:
        pipeline = ConditionalPipeline(
            lambda prompt: "short" if len(prompt) < 5 else "long",
            {
                "short": _build_agent(_EchoTransport("short"), name="one"),
                "long": _build_agent(_EchoTransport("long"), name="two"),
            },
        )

        self.assertEqual(await pipeline.run("hi"), "short(hi)")
        self.assertEqual(await pipeline.run("a longer prompt"), "long(a longer prompt)")

    async def test_a_mixed_pipeline_runs_both_agent_kinds(self) -> None:
        pipeline = SequentialPipeline((_build_base_agent(), _build_agent()))

        output = await pipeline.run("start")

        self.assertIn("echo(", output)
        self.assertIn("base:start", output)

    async def test_a_failing_codex_stage_propagates_out_of_the_pipeline(self) -> None:
        pipeline = ParallelPipeline(
            (
                _build_agent(_EchoTransport("ok"), name="one"),
                _build_agent(_FailingTransport(), name="two"),
            )
        )

        with self.assertRaises(CodexAgentError):
            await pipeline.run("go")


if __name__ == "__main__":
    unittest.main()
