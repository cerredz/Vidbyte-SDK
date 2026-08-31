"""FILE: tests/test_usage_preview_and_trace_wiring.py

PURPOSE: Verifies UsageTracker.preview_call's no-double-billing guarantee and the runtime/BaseAgent
    wiring that feeds response text and usage data into the llm.call and agent.run trace spans.
ROLE IN CODEBASE: Unit and integration test suite for the trace-output-and-usage-attributes feature's
    capture side (the translate_end/end_span contract itself is covered in test_trace_close_attributes.py).
ARCHITECTURE NOTE: Integration tests wire a real TraceController + DebugTracer + OTelGenAIProviderTranslator
    through a BaseAgent with a fake text runner, so the assertions exercise the actual runtime.py/base.py
    call sites this feature modified, not a re-implementation of them.
COMMON MODIFICATION PATTERNS: Add a new usage-preview edge case near UsageTrackerPreviewTests; add a new
    end-to-end wiring assertion near AgentTraceUsageWiringTests.
KNOWN EDGE CASES: preview_call must never mutate UsageTracker state; a fallback mid-run model switch must
    price each call exactly once even though _invoke_with_middleware runs more than once per logical turn.
RELATED DOCS: docs/design/trace-output-and-usage-attributes.md
TESTS: This file is the test.
"""

from __future__ import annotations

import unittest

from tests.agent_test_support import build_test_agent
from vidbyte.agents.pricing import UsageTracker
from vidbyte.lib.config import ModelProvider
from vidbyte.lib.runners import TextModelResponse
from vidbyte.trace.controller import TraceController
from vidbyte.trace.debug import DebugTracer
from vidbyte.trace.profiles import TraceProfile
from vidbyte.trace.providers import OTelGenAIProviderTranslator


def _response(text: str, *, input_tokens: int = 10, output_tokens: int = 4) -> TextModelResponse:
    # Builds a fake model response shaped exactly like a real runner's, usage payload included.
    return TextModelResponse(
        provider=ModelProvider.OPENAI,
        model="gpt-4.1-mini",
        text=text,
        raw={},
        usage={"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": input_tokens + output_tokens},
    )


def _malformed_response(text: str) -> TextModelResponse:
    # A response whose usage payload cannot be parsed into any provider's usage class.
    return TextModelResponse(provider=ModelProvider.OPENAI, model="gpt-4.1-mini", text=text, raw={}, usage={"not_a_real_field": 1})


class TextUsageRunner:
    """Fake runner returning one queued response per call, in order."""

    def __init__(self, responses: list[TextModelResponse]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def run(self, prompt: str, *, system: str | None = None, **_: object) -> TextModelResponse:
        response = self.responses[self.calls]
        self.calls += 1
        return response


def _traced_agent(runner: TextUsageRunner, translator=None):
    # Builds a BaseAgent wired to a real TraceController over DebugTracer, so wiring assertions
    # exercise the actual runtime.py/base.py call sites, not a re-implementation of them.
    debug = DebugTracer()
    controller = TraceController(inner=debug, profile=TraceProfile.default(), translator=translator or OTelGenAIProviderTranslator())
    agent = build_test_agent(name="worker", system_prompt="Work carefully.", runner=runner, tracer=controller)
    return agent, debug


class UsageTrackerPreviewTests(unittest.TestCase):
    def test_preview_call_returns_same_shape_without_appending(self) -> None:
        # [Silent Failure] Must assert len(records) stays 0, not just that a value came back.
        tracker = UsageTracker()
        record = tracker.preview_call(_response("hi"))
        self.assertIsNotNone(record)
        self.assertEqual(record.usage.input_tokens, 10)
        self.assertEqual(len(tracker.records), 0)

    def test_preview_call_does_not_mark_recording_corrupted(self) -> None:
        # [Hidden Assumption] A preview parse failure is not a lost real record.
        tracker = UsageTracker()
        tracker.preview_call(_malformed_response("hi"))
        self.assertFalse(tracker.recording_corrupted)

    def test_multiple_previews_then_one_record_call_yields_exactly_one_record(self) -> None:
        # [Hidden Failure] The core no-double-billing guarantee, directly targeted.
        tracker = UsageTracker()
        response = _response("hi")
        tracker.preview_call(response)
        tracker.preview_call(response)
        tracker.preview_call(response)
        tracker.record_call(response)
        self.assertEqual(len(tracker.records), 1)
        self.assertEqual(tracker.rollup().input_tokens, 10)

    def test_record_call_behavior_is_unchanged_by_the_shared_helper_refactor(self) -> None:
        # [Hidden Assumption] Regression guard on extracting _price_call out of record_call.
        tracker = UsageTracker()
        record = tracker.record_call(_response("hi", input_tokens=7, output_tokens=3))
        self.assertIsNotNone(record)
        self.assertEqual(record.call_index, 1)
        self.assertEqual(len(tracker.records), 1)

    def test_preview_call_on_malformed_response_returns_none(self) -> None:
        # [Edge Case] Matches record_call's existing tolerant behavior for an unusable payload.
        tracker = UsageTracker()
        self.assertIsNone(tracker.preview_call(_malformed_response("hi")))


class AgentTraceUsageWiringTests(unittest.IsolatedAsyncioTestCase):
    async def test_llm_call_span_carries_output_messages_and_token_counts(self) -> None:
        # [Edge Case] The well-formed-response path: real close-time attributes reach the wire.
        agent, debug = _traced_agent(TextUsageRunner([_response("Final answer: OK", input_tokens=10, output_tokens=4)]))
        await agent.generate_reply("task")
        llm_end_events = [e for e in debug.events if e["type"] == "end_span" and "gen_ai.usage.output_tokens" in e["attributes"]]
        self.assertEqual(len(llm_end_events), 1)
        self.assertEqual(llm_end_events[0]["attributes"]["gen_ai.usage.output_tokens"], 4)
        self.assertEqual(llm_end_events[0]["attributes"]["gen_ai.usage.input_tokens"], 10)
        self.assertIn("gen_ai.output.messages", llm_end_events[0]["attributes"])

    async def test_llm_call_span_omits_usage_fields_when_provider_unrecognized(self) -> None:
        # [Silent Failure] Must omit entirely, never emit zero/None placeholders.
        agent, debug = _traced_agent(TextUsageRunner([_malformed_response("Final answer: OK")]))
        await agent.generate_reply("task")
        llm_end_events = [e for e in debug.events if e["type"] == "end_span" and "gen_ai.output.messages" in e["attributes"]]
        self.assertEqual(len(llm_end_events), 1)
        self.assertNotIn("gen_ai.usage.input_tokens", llm_end_events[0]["attributes"])
        self.assertNotIn("gen_ai.usage.output_tokens", llm_end_events[0]["attributes"])

    async def test_usage_tracker_records_exactly_one_call_per_successful_model_call(self) -> None:
        # [Hidden Failure] Integration-level version of the no-double-billing guarantee, across
        # the real call path this feature modified (preview_call at close, record_call in the loop).
        agent, _debug = _traced_agent(TextUsageRunner([_response("Final answer: OK")]))
        await agent.generate_reply("task")
        self.assertEqual(len(agent._usage_tracker.records), 1)

    async def test_agent_run_trace_carries_full_run_usage_rollup(self) -> None:
        # [Edge Case] The whole-run rollup lands on the root agent.run trace, namespaced under vidbyte.usage.
        agent, debug = _traced_agent(TextUsageRunner([_response("Final answer: OK", input_tokens=10, output_tokens=4)]))
        await agent.generate_reply("task")
        trace_end_events = [e for e in debug.events if e["type"] == "end_trace"]
        self.assertEqual(len(trace_end_events), 1)
        attrs = trace_end_events[0]["attributes"]
        self.assertEqual(attrs["vidbyte.usage.input_tokens"], 10)
        self.assertEqual(attrs["vidbyte.usage.output_tokens"], 4)
        self.assertEqual(attrs["vidbyte.usage.model_call_count"], 1)

    async def test_agent_run_trace_carries_no_usage_rollup_when_no_model_calls_made(self) -> None:
        # [Edge Case] BaseAgent._usage_trace_attributes must return {} rather than zero placeholders.
        agent = build_test_agent(name="worker", system_prompt="Work carefully.", runner=TextUsageRunner([_response("x")]))
        self.assertEqual(agent._usage_trace_attributes(), {})

    async def test_second_turn_rollup_reflects_only_the_second_turn(self) -> None:
        # [Hidden Assumption] UsageTracker.reset() at the start of generate_reply must prevent a
        # stale first-turn rollup from leaking into the second turn's agent.run trace.
        agent, debug = _traced_agent(
            TextUsageRunner(
                [
                    _response("Final answer: first", input_tokens=10, output_tokens=4),
                    _response("Final answer: second", input_tokens=50, output_tokens=20),
                ]
            )
        )
        await agent.generate_reply("first task")
        await agent.generate_reply("second task")
        trace_end_events = [e for e in debug.events if e["type"] == "end_trace"]
        self.assertEqual(len(trace_end_events), 2)
        self.assertEqual(trace_end_events[0]["attributes"]["vidbyte.usage.input_tokens"], 10)
        self.assertEqual(trace_end_events[1]["attributes"]["vidbyte.usage.input_tokens"], 50)

    async def test_failed_model_call_attaches_no_usage_attributes(self) -> None:
        # [Edge Case] The exception path must not compute or attach usage data.
        class RaisingRunner:
            def run(self, prompt: str, *, system: str | None = None, **_: object) -> object:
                raise RuntimeError("boom")

        agent, debug = _traced_agent(TextUsageRunner([_response("unused")]))
        agent._runner_cache.clear()
        from tests.agent_test_support import bind_test_runner

        bind_test_runner(agent, RaisingRunner())
        with self.assertRaises(Exception):
            await agent.generate_reply("task")
        error_events = [e for e in debug.events if e["type"] == "end_span" and e["error"] is not None]
        self.assertTrue(error_events)
        self.assertEqual(error_events[0]["attributes"], {})


if __name__ == "__main__":
    unittest.main()
