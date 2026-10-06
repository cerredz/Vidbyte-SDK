"""FILE: tests/test_codex_usage_tracking.py

PURPOSE:
    Feature tests for Codex usage tracking: CodexMetricsTranslator's
    recordability gate and payload shaping, the CodexUsageResponse shim's
    validation, and CodexHarnessAgent's tracker lifecycle, get_usage(),
    get_cost_usd(), and metadata["usage_rollup"] wiring. Locks the behavior
    docs/design/codex-usage-tracking.md specifies: one native turn produces
    exactly one accounting record, always from the per-turn delta and never
    the thread cumulative.

ROLE IN CODEBASE:
    Exercises vidbyte/agents/codex/metrics.py (CodexMetricsTranslator),
    vidbyte/agents/codex/agent.py (tracker lifecycle and accessors),
    vidbyte/agents/codex/result.py (rollup metadata), and the usage
    dataclasses in vidbyte/lib/dataclasses/codex.py, against the real
    vidbyte/agents/pricing/tracker.py.

ARCHITECTURE NOTE:
    Every test runs offline. Only CodexTransport is faked; the real
    UsageTracker and the real pricing registry run, because the defect this
    guards against — a double-counted or cumulative record — only appears
    once those are wired together.

FUNCTION INVENTORY:
    No production functions. _usage() builds one CodexUsage snapshot,
    _run_result() builds one CodexRunResult, _request() builds one
    CodexUsageTranslationRequest, and _build_agent() builds an agent whose
    transport is a scripted recorder.

COMMON MODIFICATION PATTERNS:
    Add a recordability condition to CodexMetricsTranslator, then add its
    case to RecordUsageGateTests; add a payload key, then add its assertion
    to UsagePayloadShapeTests.

WHAT NOT TO DO IN THIS FILE:
    Do not import openai_codex, do not assert an exact dollar figure against
    the live pricing table, and do not record CodexRunResult.usage anywhere.

KNOWN EDGE CASES:
    An all-zero usage snapshot is recorded while an absent one is not; a
    turn on a custom thread model_provider records nothing at all.

RELATED DOCS: docs/design/codex-usage-tracking.md
TESTS: python -m pytest tests/test_codex_usage_tracking.py
"""

from __future__ import annotations

import unittest

from vidbyte.agents.codex.agent import CodexHarnessAgent
from vidbyte.agents.codex.metrics import CodexMetricsTranslator
from vidbyte.agents.pricing.records import UsageRecordingIntegrity
from vidbyte.agents.pricing.tracker import UsageTracker
from vidbyte.lib.constants.codex import CODEX_USAGE_ROLLUP_KEY
from vidbyte.lib.dataclasses.codex import (
    CodexAgentSettings,
    CodexHarnessAgentSettings,
    CodexRunInput,
    CodexRunResult,
    CodexThreadSettings,
    CodexTransportRunRequest,
    CodexTurnSettings,
    CodexUsage,
    CodexUsageResponse,
    CodexUsageTranslationRequest,
)
from vidbyte.lib.errors import ConfigurationError

FINAL_RESPONSE = "codex reply"
PRICED_MODEL = "gpt-4o"
UNPRICED_MODEL = "codex-house-model"


def _usage(
    input_tokens: int = 100,
    output_tokens: int = 20,
    total_tokens: int = 120,
    cached_input_tokens: int = 10,
    cache_write_input_tokens: int = 5,
    reasoning_output_tokens: int = 8,
) -> CodexUsage:
    # Builds one provider usage snapshot with every field distinct, so a mis-mapped
    # key cannot coincidentally match another field's value.
    return CodexUsage(
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        cache_write_input_tokens=cache_write_input_tokens,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_output_tokens,
        total_tokens=total_tokens,
        model_context_window=200_000,
    )


def _run_result(
    cumulative: CodexUsage | None = None,
    last: CodexUsage | None = None,
    usage_available: bool = True,
    thread_id: str = "th_1",
) -> CodexRunResult:
    # Builds a completed turn whose cumulative and last snapshots differ on purpose.
    return CodexRunResult(
        thread_id=thread_id,
        turn_id="tu_1",
        status="completed",
        final_response=FINAL_RESPONSE,
        duration_ms=12,
        usage=cumulative if cumulative is not None else _usage(),
        items=(),
        last_usage=last if last is not None else _usage(),
        usage_available=usage_available,
    )


def _codex_settings(
    turn_model: str = "", thread_model: str = "", model_provider: str = ""
) -> CodexAgentSettings:
    # Builds provider settings whose model may be set at either lifecycle layer.
    return CodexAgentSettings(
        thread=CodexThreadSettings(model=thread_model, model_provider=model_provider),
        turn=CodexTurnSettings(model=turn_model),
    )


def _request(
    result: CodexRunResult | None = None,
    settings: CodexAgentSettings | None = None,
    tracker: UsageTracker | None = None,
) -> tuple[CodexUsageTranslationRequest, UsageTracker]:
    # Pairs one translation request with the tracker it will record into.
    live_tracker = tracker if tracker is not None else UsageTracker()
    request = CodexUsageTranslationRequest(
        result=result if result is not None else _run_result(),
        settings=settings if settings is not None else _codex_settings(PRICED_MODEL),
        tracker=live_tracker,
    )
    return request, live_tracker


class _ScriptedTransport:
    """Stands in for CodexTransport, returning queued results or raising."""

    def __init__(self, results: list[CodexRunResult] | None = None) -> None:
        self.results = list(results or [])
        self.requests: list[CodexTransportRunRequest] = []
        self.failure: Exception | None = None

    async def run(self, request: CodexTransportRunRequest) -> CodexRunResult:
        # Records the request, then raises the scripted failure or pops the next result.
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return self.results.pop(0) if self.results else _run_result()


def _build_agent(
    codex: CodexAgentSettings | None = None,
    results: list[CodexRunResult] | None = None,
) -> tuple[CodexHarnessAgent, _ScriptedTransport]:
    # Builds an agent whose transport is scripted, so no Codex process is started.
    settings = CodexHarnessAgentSettings(
        name="codex-agent",
        system_prompt="You are a Codex harness agent.",
        codex=codex if codex is not None else _codex_settings(PRICED_MODEL),
    )
    agent = CodexHarnessAgent(settings)
    transport = _ScriptedTransport(results)
    agent._transport = transport  # type: ignore[assignment]
    return agent, transport


class RecordUsageGateTests(unittest.TestCase):
    """Covers which turns CodexMetricsTranslator will and will not record."""

    def test_records_the_per_turn_delta_not_the_thread_cumulative(self) -> None:
        request, tracker = _request(
            _run_result(
                cumulative=_usage(input_tokens=750, output_tokens=150, total_tokens=900),
                last=_usage(input_tokens=250, output_tokens=50, total_tokens=300),
            )
        )

        CodexMetricsTranslator.record_usage(request)

        self.assertEqual(tracker.rollup().total_tokens, 300)

    def test_records_nothing_when_usage_is_unavailable(self) -> None:
        request, tracker = _request(_run_result(usage_available=False))

        self.assertIsNone(CodexMetricsTranslator.record_usage(request))
        self.assertEqual(tracker.rollup().model_call_count, 0)

    def test_records_a_genuine_all_zero_usage_snapshot(self) -> None:
        zero = _usage(0, 0, 0, 0, 0, 0)
        request, tracker = _request(_run_result(cumulative=zero, last=zero))

        CodexMetricsTranslator.record_usage(request)

        self.assertEqual(tracker.rollup().model_call_count, 1)
        self.assertEqual(tracker.rollup().total_tokens, 0)

    def test_records_nothing_for_a_custom_model_provider(self) -> None:
        request, tracker = _request(
            settings=_codex_settings(PRICED_MODEL, model_provider="my-gateway")
        )

        self.assertIsNone(CodexMetricsTranslator.record_usage(request))
        self.assertEqual(tracker.rollup().model_call_count, 0)

    def test_prefers_the_turn_model_over_the_thread_model(self) -> None:
        request, tracker = _request(
            settings=_codex_settings(turn_model="turn-model", thread_model="thread-model")
        )

        CodexMetricsTranslator.record_usage(request)

        self.assertEqual(tracker.rollup().calls[0].model, "turn-model")

    def test_records_an_empty_model_when_neither_layer_sets_one(self) -> None:
        request, tracker = _request(settings=_codex_settings())

        CodexMetricsTranslator.record_usage(request)

        self.assertEqual(tracker.rollup().calls[0].model, "")

    def test_records_nothing_for_non_numeric_token_counts(self) -> None:
        tracker = UsageTracker()

        record = tracker.record_call(
            CodexUsageResponse(
                provider="openai",
                model=PRICED_MODEL,
                usage={"input_tokens": "many", "output_tokens": None},
            )
        )

        self.assertIsNone(record)
        self.assertEqual(tracker.rollup().model_call_count, 0)
        self.assertEqual(
            tracker.rollup().recording_integrity, UsageRecordingIntegrity.INTACT
        )


class UsagePayloadShapeTests(unittest.TestCase):
    """Covers the OpenAI-shaped payload the tracker's parser reads."""

    def setUp(self) -> None:
        request, self.tracker = _request()
        CodexMetricsTranslator.record_usage(request)
        self.parsed = self.tracker.rollup().calls[0].usage

    def test_maps_cached_tokens_into_input_tokens_details(self) -> None:
        self.assertEqual(self.parsed.cached_input_tokens, 10)

    def test_maps_reasoning_tokens_into_output_tokens_details(self) -> None:
        self.assertEqual(self.parsed.reasoning_tokens, 8)

    def test_preserves_cache_write_tokens_on_the_raw_payload(self) -> None:
        self.assertEqual(self.parsed.raw["cache_write_input_tokens"], 5)

    def test_carries_the_plain_token_counts(self) -> None:
        self.assertEqual(self.parsed.input_tokens, 100)
        self.assertEqual(self.parsed.output_tokens, 20)
        self.assertEqual(self.parsed.total_tokens, 120)


class CodexUsageResponseValidationTests(unittest.TestCase):
    """Covers the shim's construction-time guarantees."""

    def test_rejects_a_non_mapping_usage_payload(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexUsageResponse(provider="openai", model=PRICED_MODEL, usage=[])  # type: ignore[arg-type]

    def test_rejects_an_empty_provider(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexUsageResponse(provider="", model=PRICED_MODEL, usage={})

    def test_accepts_an_empty_model_name(self) -> None:
        response = CodexUsageResponse(provider="openai", model="", usage={})

        self.assertEqual(response.model, "")


class CodexUsageTranslationRequestValidationTests(unittest.TestCase):
    """Covers the request record's typed boundary."""

    def test_rejects_a_tracker_without_record_call(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexUsageTranslationRequest(
                result=_run_result(), settings=_codex_settings(), tracker=object()
            )


class CodexHarnessAgentUsageIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Covers the agent's tracker lifecycle through real turns."""

    async def test_one_turn_produces_exactly_one_accounting_record(self) -> None:
        agent, _ = _build_agent()

        await agent.arun(CodexRunInput.text("prompt"))

        self.assertEqual(agent.get_usage().model_call_count, 1)

    async def test_message_metadata_carries_the_same_rollup_as_the_accessor(self) -> None:
        agent, _ = _build_agent()

        reply = await agent.arun(CodexRunInput.text("prompt"))

        published = reply.metadata[CODEX_USAGE_ROLLUP_KEY]
        self.assertEqual(published.model_call_count, agent.get_usage().model_call_count)
        self.assertEqual(published.total_tokens, agent.get_usage().total_tokens)

    async def test_three_turns_report_only_the_last_turn_delta(self) -> None:
        results = [
            _run_result(
                cumulative=_usage(input_tokens=100 * turn, total_tokens=120 * turn),
                last=_usage(input_tokens=100, total_tokens=120),
            )
            for turn in (1, 2, 3)
        ]
        agent, _ = _build_agent(results=results)

        for _ in range(3):
            await agent.arun(CodexRunInput.text("prompt"))

        self.assertEqual(agent.get_usage().model_call_count, 1)
        self.assertEqual(agent.get_usage().total_tokens, 120)

    async def test_a_failed_transport_leaves_an_empty_rollup(self) -> None:
        agent, transport = _build_agent()
        await agent.arun(CodexRunInput.text("first"))
        transport.failure = RuntimeError("connection lost")

        with self.assertRaises(Exception):
            await agent.arun(CodexRunInput.text("second"))

        self.assertEqual(agent.get_usage().model_call_count, 0)

    async def test_an_unpriced_model_reports_no_cost(self) -> None:
        agent, _ = _build_agent(codex=_codex_settings(UNPRICED_MODEL))

        await agent.arun(CodexRunInput.text("prompt"))

        self.assertIsNone(agent.get_cost_usd())
        self.assertFalse(agent.get_usage().cost_complete)

    async def test_a_custom_backend_publishes_a_rollup_with_no_calls(self) -> None:
        agent, _ = _build_agent(
            codex=_codex_settings(PRICED_MODEL, model_provider="my-gateway")
        )

        reply = await agent.arun(CodexRunInput.text("prompt"))

        self.assertEqual(reply.metadata[CODEX_USAGE_ROLLUP_KEY].model_call_count, 0)
        self.assertIsNone(agent.get_cost_usd())


if __name__ == "__main__":
    unittest.main()
