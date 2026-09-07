"""FILE: tests/test_codex_speed_tracking.py

PURPOSE:
    Feature tests for Codex speed tracking: CodexSpeedTranslator's success,
    failure, and cancellation records, the CodexSpeedResponse and
    CodexSpeedTranslationRequest boundaries, and CodexHarnessAgent's run
    lifecycle through get_speed_stats() and get_speed_history(). Locks the
    behavior docs/design/codex-speed-tracking.md specifies: the interval is
    measured locally, first_token_at is absent rather than zero, and the run
    is closed on every exit path including cancellation.

ROLE IN CODEBASE:
    Exercises vidbyte/agents/codex/speed.py (CodexSpeedTranslator),
    vidbyte/agents/codex/agent.py (run boundaries and accessors),
    vidbyte/agents/codex/result.py (provider duration metadata), and the
    speed dataclasses in vidbyte/lib/dataclasses/codex.py, against the real
    vidbyte/agents/speed/tracker.py driven by an injected clock.

ARCHITECTURE NOTE:
    Every test runs offline. The agent's tracker is replaced with one built
    on _FakeClock so intervals are exact rather than timing-dependent, which
    is what lets the tests assert a specific total_duration_ms instead of a
    range.

FUNCTION INVENTORY:
    No production functions. _FakeClock advances on demand, _usage() and
    _run_result() build native snapshots, _request() builds one translation
    request, and _build_agent() wires an agent to a scripted transport.

COMMON MODIFICATION PATTERNS:
    Add a turn outcome to CodexSpeedTranslator, then add its case to
    RecordTurnTests and its lifecycle case to CodexHarnessAgentSpeedTests.

WHAT NOT TO DO IN THIS FILE:
    Do not import openai_codex, do not assert on wall-clock timing, and do
    not assert that first_token_at equals zero — absent is the contract.

KNOWN EDGE CASES:
    A turn with no reported usage records absent token denominators; a turn
    with no configured model records the "unknown" placeholder rather than
    losing the latency to a validation error.

RELATED DOCS: docs/design/codex-speed-tracking.md
TESTS: python -m pytest tests/test_codex_speed_tracking.py
"""

from __future__ import annotations

import asyncio
import unittest

from vidbyte.agents.codex.agent import CodexHarnessAgent
from vidbyte.agents.codex.speed import CodexSpeedTranslator
from vidbyte.agents.speed.tracker import AgentSpeedTracker
from vidbyte.lib.constants.codex import (
    CODEX_PROVIDER_DURATION_KEY,
    CODEX_PROVIDER_NAME,
    CODEX_UNKNOWN_MODEL,
)
from vidbyte.lib.dataclasses.codex import (
    CodexAgentSettings,
    CodexHarnessAgentSettings,
    CodexRunInput,
    CodexRunResult,
    CodexSpeedResponse,
    CodexSpeedTranslationRequest,
    CodexThreadSettings,
    CodexTransportRunRequest,
    CodexTurnSettings,
    CodexUsage,
)
from vidbyte.lib.errors import ConfigurationError

FINAL_RESPONSE = "codex reply"
TURN_MODEL = "gpt-5-codex"
PROVIDER_DURATION_MS = 40
TURN_ELAPSED = 2.5


class _FakeClock:
    """Advances only when asked, so measured intervals are exact."""

    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        # Returns the current reading without advancing it.
        return self.value

    def advance(self, seconds: float) -> None:
        # Moves the clock forward to simulate awaited work.
        self.value += seconds


def _usage(input_tokens: int = 100, output_tokens: int = 20) -> CodexUsage:
    # Builds one provider usage snapshot for the throughput denominators.
    return CodexUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


def _run_result(
    last: CodexUsage | None = None,
    usage_available: bool = True,
    duration_ms: int | None = PROVIDER_DURATION_MS,
) -> CodexRunResult:
    # Builds a completed turn whose provider duration differs from the measured one.
    return CodexRunResult(
        thread_id="th_1",
        turn_id="tu_1",
        status="completed",
        final_response=FINAL_RESPONSE,
        duration_ms=duration_ms,
        usage=_usage(900, 180),
        items=(),
        last_usage=last if last is not None else _usage(),
        usage_available=usage_available,
    )


def _codex_settings(
    turn_model: str = TURN_MODEL, thread_model: str = ""
) -> CodexAgentSettings:
    # Builds provider settings whose model may be set at either lifecycle layer.
    return CodexAgentSettings(
        thread=CodexThreadSettings(model=thread_model),
        turn=CodexTurnSettings(model=turn_model),
    )


def _request(
    result: CodexRunResult | None = None,
    error: BaseException | None = None,
    settings: CodexAgentSettings | None = None,
) -> tuple[CodexSpeedTranslationRequest, AgentSpeedTracker, _FakeClock]:
    # Pairs one translation request with the tracker and clock it records against.
    clock = _FakeClock()
    tracker = AgentSpeedTracker(clock=clock)
    tracker.record_run_start()
    dispatched_at = tracker.now()
    clock.advance(TURN_ELAPSED)
    request = CodexSpeedTranslationRequest(
        settings=settings if settings is not None else _codex_settings(),
        tracker=tracker,
        dispatched_at=dispatched_at,
        result=result if error is None else None,
        error=error,
    )
    if result is None and error is None:
        request = CodexSpeedTranslationRequest(
            settings=settings if settings is not None else _codex_settings(),
            tracker=tracker,
            dispatched_at=dispatched_at,
            result=_run_result(),
        )
    return request, tracker, clock


class _ScriptedTransport:
    """Stands in for CodexTransport, advancing the clock then returning or raising."""

    def __init__(self, clock: _FakeClock, result: CodexRunResult | None = None) -> None:
        self.clock = clock
        self.result = result if result is not None else _run_result()
        self.failure: BaseException | None = None
        self.requests: list[CodexTransportRunRequest] = []

    async def run(self, request: CodexTransportRunRequest) -> CodexRunResult:
        # Simulates awaited provider work by advancing the injected clock.
        self.requests.append(request)
        self.clock.advance(TURN_ELAPSED)
        if self.failure is not None:
            raise self.failure
        return self.result


def _build_agent(
    codex: CodexAgentSettings | None = None,
) -> tuple[CodexHarnessAgent, _ScriptedTransport, _FakeClock]:
    # Builds an agent whose tracker uses a fake clock and whose transport is scripted.
    settings = CodexHarnessAgentSettings(
        name="codex-agent",
        system_prompt="You are a Codex harness agent.",
        codex=codex if codex is not None else _codex_settings(),
    )
    agent = CodexHarnessAgent(settings)
    clock = _FakeClock()
    agent._speed = AgentSpeedTracker(clock=clock)  # type: ignore[assignment]
    transport = _ScriptedTransport(clock)
    agent._transport = transport  # type: ignore[assignment]
    return agent, transport, clock


class _RaisingTracker:
    """A tracker whose recording raises, proving the agent's fail-open guard."""

    def __init__(self) -> None:
        self.corrupted = False
        self._clock = _FakeClock()

    def reset(self) -> None:
        # Matches AgentSpeedTracker's per-run lifecycle surface.
        return None

    def record_run_start(self) -> None:
        # Matches AgentSpeedTracker's per-run lifecycle surface.
        return None

    def record_run_end(self) -> None:
        # Matches AgentSpeedTracker's per-run lifecycle surface.
        return None

    def now(self) -> float:
        # Supplies a valid dispatch timestamp so the failure comes from recording.
        return self._clock()

    def record_call(self, call_input: object) -> None:
        # Simulates a metering bug at the successful-turn boundary.
        raise RuntimeError("metering exploded")

    def record_call_failure(self, failure_input: object) -> None:
        # Simulates a metering bug at the failed-turn boundary.
        raise RuntimeError("metering exploded")

    def mark_recording_corrupted(self) -> None:
        # Records that the agent reported the lost measurement rather than raising.
        self.corrupted = True


class RecordTurnTests(unittest.TestCase):
    """Covers the records CodexSpeedTranslator files for each turn outcome."""

    def test_records_one_successful_call_for_a_completed_turn(self) -> None:
        request, tracker, _ = _request(_run_result())

        CodexSpeedTranslator.record_turn(request)

        self.assertEqual(len(tracker.calls), 1)
        self.assertTrue(tracker.calls[0].succeeded)

    def test_leaves_first_token_at_absent_not_zero(self) -> None:
        request, tracker, _ = _request(_run_result())

        CodexSpeedTranslator.record_turn(request)

        self.assertIsNone(tracker.calls[0].first_token_at)

    def test_names_the_provider_codex(self) -> None:
        request, tracker, _ = _request(_run_result())

        CodexSpeedTranslator.record_turn(request)

        self.assertEqual(tracker.calls[0].provider, CODEX_PROVIDER_NAME)

    def test_prefers_the_turn_model_over_the_thread_model(self) -> None:
        request, tracker, _ = _request(
            _run_result(), settings=_codex_settings("turn-model", "thread-model")
        )

        CodexSpeedTranslator.record_turn(request)

        self.assertEqual(tracker.calls[0].model, "turn-model")

    def test_falls_back_to_the_unknown_model(self) -> None:
        request, tracker, _ = _request(_run_result(), settings=_codex_settings("", ""))

        CodexSpeedTranslator.record_turn(request)

        self.assertEqual(tracker.calls[0].model, CODEX_UNKNOWN_MODEL)

    def test_carries_token_denominators_from_the_per_turn_delta(self) -> None:
        request, tracker, _ = _request(_run_result(last=_usage(250, 50)))

        CodexSpeedTranslator.record_turn(request)

        self.assertEqual(tracker.calls[0].input_tokens, 250)
        self.assertEqual(tracker.calls[0].output_tokens, 50)

    def test_leaves_token_denominators_absent_without_usage(self) -> None:
        request, tracker, _ = _request(_run_result(usage_available=False))

        CodexSpeedTranslator.record_turn(request)

        self.assertIsNone(tracker.calls[0].input_tokens)
        self.assertIsNone(tracker.calls[0].output_tokens)

    def test_records_a_failed_call_with_the_exception_type_name(self) -> None:
        request, tracker, _ = _request(error=TimeoutError("too slow"))

        CodexSpeedTranslator.record_turn(request)

        record = tracker.calls[0]
        self.assertFalse(record.succeeded)
        self.assertEqual(record.error_type, "TimeoutError")
        self.assertFalse(record.cancelled)

    def test_marks_a_cancelled_error_record_as_cancelled(self) -> None:
        request, tracker, _ = _request(error=asyncio.CancelledError())

        CodexSpeedTranslator.record_turn(request)

        self.assertTrue(tracker.calls[0].cancelled)


class CodexSpeedBoundaryValidationTests(unittest.TestCase):
    """Covers the construction-time guarantees of the speed records."""

    def test_response_rejects_an_empty_model(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexSpeedResponse(provider=CODEX_PROVIDER_NAME, model="")

    def test_request_rejects_both_a_result_and_an_error(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexSpeedTranslationRequest(
                settings=_codex_settings(),
                tracker=AgentSpeedTracker(),
                dispatched_at=1.0,
                result=_run_result(),
                error=TimeoutError(),
            )

    def test_request_rejects_neither_a_result_nor_an_error(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexSpeedTranslationRequest(
                settings=_codex_settings(),
                tracker=AgentSpeedTracker(),
                dispatched_at=1.0,
            )

    def test_request_rejects_a_tracker_missing_record_call_failure(self) -> None:
        class _PartialTracker:
            def record_call(self, call_input: object) -> None:
                return None

        with self.assertRaises(ConfigurationError):
            CodexSpeedTranslationRequest(
                settings=_codex_settings(),
                tracker=_PartialTracker(),
                dispatched_at=1.0,
                result=_run_result(),
            )

    def test_request_rejects_a_negative_dispatched_at(self) -> None:
        with self.assertRaises(ConfigurationError):
            CodexSpeedTranslationRequest(
                settings=_codex_settings(),
                tracker=AgentSpeedTracker(),
                dispatched_at=-1.0,
                result=_run_result(),
            )


class CodexHarnessAgentSpeedTests(unittest.IsolatedAsyncioTestCase):
    """Covers the agent's run lifecycle across every turn outcome."""

    async def test_a_successful_turn_measures_the_local_interval(self) -> None:
        agent, _, _ = _build_agent()

        await agent.arun(CodexRunInput.text("prompt"))

        rollup = agent.get_speed_stats()
        self.assertEqual(len(rollup.calls), 1)
        self.assertEqual(rollup.run_stats.total_duration_ms, TURN_ELAPSED * 1000)

    async def test_a_failing_turn_still_closes_the_run(self) -> None:
        agent, transport, _ = _build_agent()
        transport.failure = RuntimeError("connection lost")

        with self.assertRaises(Exception):
            await agent.arun(CodexRunInput.text("prompt"))

        rollup = agent.get_speed_stats()
        self.assertEqual(len(rollup.calls), 1)
        self.assertFalse(rollup.calls[0].succeeded)
        self.assertIsNotNone(rollup.run_stats.total_duration_ms)

    async def test_a_cancelled_turn_propagates_and_records_cancellation(self) -> None:
        agent, transport, _ = _build_agent()
        transport.failure = asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            await agent.arun(CodexRunInput.text("prompt"))

        self.assertTrue(agent.get_speed_stats().calls[0].cancelled)

    async def test_history_survives_the_per_turn_reset(self) -> None:
        agent, _, _ = _build_agent()

        await agent.arun(CodexRunInput.text("one"))
        await agent.arun(CodexRunInput.text("two"))

        self.assertEqual(len(agent.get_speed_stats().calls), 1)
        self.assertEqual(agent.get_speed_history().run_count, 2)

    async def test_provider_duration_is_published_apart_from_the_measurement(
        self,
    ) -> None:
        agent, _, _ = _build_agent()

        reply = await agent.arun(CodexRunInput.text("prompt"))

        published = reply.metadata[CODEX_PROVIDER_DURATION_KEY]
        measured = agent.get_speed_stats().run_stats.total_duration_ms
        self.assertEqual(published, PROVIDER_DURATION_MS)
        self.assertNotEqual(published, measured)

    async def test_a_raising_translator_never_replaces_the_turn_result(self) -> None:
        agent, _, _ = _build_agent()
        agent._speed = _RaisingTracker()  # type: ignore[assignment]

        reply = await agent.arun(CodexRunInput.text("prompt"))

        self.assertEqual(reply.content, FINAL_RESPONSE)
        self.assertTrue(agent._speed.corrupted)  # type: ignore[attr-defined]

    async def test_a_raising_translator_never_replaces_the_real_exception(self) -> None:
        agent, transport, _ = _build_agent()
        transport.failure = TimeoutError("too slow")
        agent._speed = _RaisingTracker()  # type: ignore[assignment]

        with self.assertRaises(TimeoutError):
            await agent.arun(CodexRunInput.text("prompt"))

        self.assertTrue(agent._speed.corrupted)  # type: ignore[attr-defined]

    async def test_absent_provider_duration_omits_the_metadata_key(self) -> None:
        agent, transport, _ = _build_agent()
        transport.result = _run_result(duration_ms=None)

        reply = await agent.arun(CodexRunInput.text("prompt"))

        self.assertNotIn(CODEX_PROVIDER_DURATION_KEY, reply.metadata)


if __name__ == "__main__":
    unittest.main()
