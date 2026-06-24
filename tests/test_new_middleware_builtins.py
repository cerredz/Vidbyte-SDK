"""Tests for the five new prebuilt middleware: TokenBudgetMiddleware,
CostBudgetMiddleware, ExponentialBackoffRetryMiddleware,
LoopDetectionMiddleware, and CircuitBreakerMiddleware."""

from __future__ import annotations

import unittest

from vidbyte.lib.dataclasses.middleware import (
    MiddlewareAction,
    MiddlewareContext,
    MiddlewareHook,
)
from vidbyte.lib.dataclasses.tools import ToolCall, ToolResult
from vidbyte.middleware.builtins import (
    CircuitBreakerMiddleware,
    CircuitState,
    CostBudgetMiddleware,
    ExponentialBackoffRetryMiddleware,
    LoopDetectionMiddleware,
    TokenBudgetMiddleware,
)
from vidbyte.middleware.builtins.loop_detection import REPEATED_OUTPUT_LOOP_NOTICE
from vidbyte.middleware.builtins.token_budget import TOKEN_BUDGET_FINAL_RESPONSE_NOTICE


def _ctx(**kwargs) -> MiddlewareContext:
    """Build a minimal MiddlewareContext for unit tests."""
    defaults = dict(hook=MiddlewareHook.BEFORE_ITERATION, agent_name="test-agent")
    defaults.update(kwargs)
    return MiddlewareContext(**defaults)


# ---------------------------------------------------------------------------
# TokenBudgetMiddleware
# ---------------------------------------------------------------------------


class TestTokenBudgetMiddleware(unittest.IsolatedAsyncioTestCase):
    async def test_aborts_when_tokens_at_limit(self) -> None:
        # [Edge Case] Exactly at limit triggers abort (inclusive boundary).
        mw = TokenBudgetMiddleware(max_tokens=100)
        ctx = _ctx(tokens_used=100)
        decision = await mw.before_iteration(ctx)
        self.assertEqual(decision.action, MiddlewareAction.ABORT_RUN)

    async def test_aborts_when_tokens_exceed_limit(self) -> None:
        # [Silent Failure] Tokens beyond limit must still abort.
        mw = TokenBudgetMiddleware(max_tokens=100)
        ctx = _ctx(tokens_used=101)
        decision = await mw.before_iteration(ctx)
        self.assertEqual(decision.action, MiddlewareAction.ABORT_RUN)

    async def test_continues_below_limit(self) -> None:
        # [Hidden Assumption] Below the limit the run must not be interrupted.
        mw = TokenBudgetMiddleware(max_tokens=100)
        ctx = _ctx(tokens_used=99)
        decision = await mw.before_iteration(ctx)
        self.assertEqual(decision.action, MiddlewareAction.CONTINUE)

    async def test_continues_when_tokens_none(self) -> None:
        # [Edge Case] Provider not reporting tokens must never abort.
        mw = TokenBudgetMiddleware(max_tokens=100)
        ctx = _ctx(tokens_used=None)
        decision = await mw.before_iteration(ctx)
        self.assertEqual(decision.action, MiddlewareAction.CONTINUE)

    async def test_custom_abort_reason(self) -> None:
        # [Silent Failure] Custom abort_reason must appear in the decision.
        mw = TokenBudgetMiddleware(max_tokens=10, abort_reason="my_custom_reason")
        ctx = _ctx(tokens_used=10)
        decision = await mw.before_iteration(ctx)
        self.assertEqual(decision.reason, "my_custom_reason")

    async def test_metadata_contains_max_and_used(self) -> None:
        # [Silent Failure] Abort metadata must surface both values for observability.
        mw = TokenBudgetMiddleware(max_tokens=50)
        ctx = _ctx(tokens_used=60)
        decision = await mw.before_iteration(ctx)
        self.assertEqual(decision.metadata["max_tokens"], 50)
        self.assertEqual(decision.metadata["tokens_used"], 60)

    async def test_soft_overrun_injects_final_response_notice_once(self) -> None:
        # [Hidden Failure] Soft overrun must request exactly one final model-visible answer.
        mw = TokenBudgetMiddleware(max_tokens=100, allow_final_response_over_budget=True)
        run_state: dict = {}
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN, run_state=run_state))
        decision = await mw.before_model_call(
            _ctx(
                hook=MiddlewareHook.BEFORE_MODEL_CALL,
                tokens_used=100,
                system="base system",
                run_state=run_state,
            )
        )
        self.assertEqual(decision.action, MiddlewareAction.CONTINUE)
        self.assertIsNotNone(decision.transform)
        self.assertIn("base system", decision.transform.system)
        self.assertIn(TOKEN_BUDGET_FINAL_RESPONSE_NOTICE, decision.transform.system)
        self.assertTrue(decision.metadata["final_response_requested"])
        self.assertTrue(run_state["__result_metadata__"]["token_budget"]["final_response_requested"])

    async def test_soft_overrun_aborts_after_notice_was_requested(self) -> None:
        # [Silent Failure] Soft overrun must not allow unlimited over-budget iterations.
        mw = TokenBudgetMiddleware(max_tokens=100, allow_final_response_over_budget=True)
        run_state: dict = {}
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN, run_state=run_state))
        first = await mw.before_iteration(_ctx(tokens_used=100, run_state=run_state))
        await mw.before_model_call(
            _ctx(
                hook=MiddlewareHook.BEFORE_MODEL_CALL,
                tokens_used=100,
                system="base system",
                run_state=run_state,
            )
        )
        second = await mw.before_iteration(_ctx(tokens_used=101, run_state=run_state))
        self.assertEqual(first.action, MiddlewareAction.CONTINUE)
        self.assertEqual(second.action, MiddlewareAction.ABORT_RUN)
        self.assertEqual(second.reason, "token_budget_exceeded")

    async def test_soft_overrun_aborts_second_model_call_attempt(self) -> None:
        # [Hidden Failure] Retry paths must not get a second over-budget model call.
        mw = TokenBudgetMiddleware(max_tokens=100, allow_final_response_over_budget=True)
        run_state: dict = {}
        await mw.before_model_call(
            _ctx(
                hook=MiddlewareHook.BEFORE_MODEL_CALL,
                tokens_used=100,
                system="base system",
                run_state=run_state,
            )
        )
        decision = await mw.before_model_call(
            _ctx(
                hook=MiddlewareHook.BEFORE_MODEL_CALL,
                tokens_used=100,
                system="base system",
                run_state=run_state,
            )
        )
        self.assertEqual(decision.action, MiddlewareAction.ABORT_RUN)
        self.assertEqual(decision.reason, "token_budget_exceeded")

    async def test_soft_overrun_continues_without_token_usage(self) -> None:
        # [Edge Case] Providers without token usage must preserve existing no-op behavior.
        mw = TokenBudgetMiddleware(max_tokens=100, allow_final_response_over_budget=True)
        decision = await mw.before_model_call(
            _ctx(hook=MiddlewareHook.BEFORE_MODEL_CALL, tokens_used=None, system="base system")
        )
        self.assertEqual(decision.action, MiddlewareAction.CONTINUE)
        self.assertIsNone(decision.transform)

    async def test_soft_overrun_lazy_state_injects_without_before_run(self) -> None:
        # [Hidden Assumption] Direct hook tests that skip before_run still get isolated run state.
        mw = TokenBudgetMiddleware(max_tokens=100, allow_final_response_over_budget=True)
        run_state: dict = {}
        decision = await mw.before_model_call(
            _ctx(
                hook=MiddlewareHook.BEFORE_MODEL_CALL,
                tokens_used=101,
                system=None,
                run_state=run_state,
            )
        )
        self.assertEqual(decision.action, MiddlewareAction.CONTINUE)
        self.assertEqual(decision.transform.system, TOKEN_BUDGET_FINAL_RESPONSE_NOTICE)
        self.assertTrue(run_state["__result_metadata__"]["token_budget"]["final_response_requested"])

    def test_raises_on_zero_max(self) -> None:
        # [Edge Case] Zero is not a meaningful ceiling.
        with self.assertRaises(ValueError):
            TokenBudgetMiddleware(max_tokens=0)

    def test_raises_on_negative_max(self) -> None:
        # [Edge Case] Negative values are not a meaningful ceiling.
        with self.assertRaises(ValueError):
            TokenBudgetMiddleware(max_tokens=-1)


# ---------------------------------------------------------------------------
# CostBudgetMiddleware
# ---------------------------------------------------------------------------


class TestCostBudgetMiddleware(unittest.IsolatedAsyncioTestCase):
    async def test_aborts_after_spend_exceeded(self) -> None:
        # [Silent Failure] Accumulating past max_spend must abort before next iteration.
        mw = CostBudgetMiddleware(max_spend_usd=0.001, cost_per_million_tokens=1.0)
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN))
        # 1500 tokens at $1 / M = $0.0015 > $0.001
        await mw.after_model_response(_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, tokens_used=1500))
        decision = await mw.before_iteration(_ctx(tokens_used=1500))
        self.assertEqual(decision.action, MiddlewareAction.ABORT_RUN)
        self.assertEqual(decision.reason, "cost_budget_exceeded")

    async def test_continues_below_spend(self) -> None:
        # [Hidden Assumption] Partial spend must not abort.
        mw = CostBudgetMiddleware(max_spend_usd=1.0, cost_per_million_tokens=1.0)
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN))
        await mw.after_model_response(_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, tokens_used=100))
        decision = await mw.before_iteration(_ctx(tokens_used=100))
        self.assertEqual(decision.action, MiddlewareAction.CONTINUE)

    async def test_resets_state_on_before_run(self) -> None:
        # [Hidden Failure] Second run on same instance must start fresh.
        mw = CostBudgetMiddleware(max_spend_usd=0.001, cost_per_million_tokens=1.0)
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN))
        await mw.after_model_response(_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, tokens_used=2000))
        # Reset
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN))
        decision = await mw.before_iteration(_ctx(tokens_used=2000))
        self.assertEqual(decision.action, MiddlewareAction.CONTINUE)

    async def test_skips_none_tokens(self) -> None:
        # [Edge Case] Provider not reporting tokens must never trigger cost abort.
        mw = CostBudgetMiddleware(max_spend_usd=0.0001, cost_per_million_tokens=1.0)
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN))
        await mw.after_model_response(_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, tokens_used=None))
        decision = await mw.before_iteration(_ctx(tokens_used=None))
        self.assertEqual(decision.action, MiddlewareAction.CONTINUE)

    async def test_handles_token_count_decrease(self) -> None:
        # [Hidden Failure] Backwards token count must not produce negative delta.
        mw = CostBudgetMiddleware(max_spend_usd=1.0, cost_per_million_tokens=1.0)
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN))
        await mw.after_model_response(_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, tokens_used=500))
        await mw.after_model_response(_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, tokens_used=100))
        # Spend should only reflect the first 500 tokens.
        self.assertAlmostEqual(mw._estimated_spend_usd, 500 / 1_000_000 * 1.0)

    async def test_metadata_contains_spend_values(self) -> None:
        # [Silent Failure] Abort metadata must surface financial figures for debugging.
        mw = CostBudgetMiddleware(max_spend_usd=0.001, cost_per_million_tokens=1.0)
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN))
        await mw.after_model_response(_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, tokens_used=2000))
        decision = await mw.before_iteration(_ctx(tokens_used=2000))
        self.assertIn("max_spend_usd", decision.metadata)
        self.assertIn("estimated_spend_usd", decision.metadata)

    def test_raises_on_zero_spend(self) -> None:
        # [Edge Case] Zero budget is not meaningful.
        with self.assertRaises(ValueError):
            CostBudgetMiddleware(max_spend_usd=0, cost_per_million_tokens=1.0)

    def test_raises_on_zero_rate(self) -> None:
        # [Edge Case] Zero cost rate would never accumulate spend.
        with self.assertRaises(ValueError):
            CostBudgetMiddleware(max_spend_usd=1.0, cost_per_million_tokens=0)


# ---------------------------------------------------------------------------
# ExponentialBackoffRetryMiddleware
# ---------------------------------------------------------------------------


class TestExponentialBackoffRetryMiddleware(unittest.IsolatedAsyncioTestCase):
    def _ctx_error(self, error: BaseException | None = None) -> MiddlewareContext:
        return _ctx(hook=MiddlewareHook.ON_MODEL_ERROR, error=error)

    async def test_retries_up_to_max_then_aborts(self) -> None:
        # [Edge Case] Three attempts: two retries then abort on the third error.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=3, base_seconds=0.001, jitter=False)
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d1 = await mw.on_model_error(self._ctx_error(RuntimeError("e")))
        d2 = await mw.on_model_error(self._ctx_error(RuntimeError("e")))
        d3 = await mw.on_model_error(self._ctx_error(RuntimeError("e")))
        self.assertEqual(d1.action, MiddlewareAction.RETRY)
        self.assertEqual(d2.action, MiddlewareAction.RETRY)
        self.assertEqual(d3.action, MiddlewareAction.ABORT_RUN)

    async def test_delay_is_exponential(self) -> None:
        # [Silent Failure] Delays must grow as base * 2^(attempt-1).
        mw = ExponentialBackoffRetryMiddleware(max_attempts=5, base_seconds=1.0, cap_seconds=100.0, jitter=False)
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d1 = await mw.on_model_error(self._ctx_error(RuntimeError()))  # attempt 1 → 1.0s
        d2 = await mw.on_model_error(self._ctx_error(RuntimeError()))  # attempt 2 → 2.0s
        d3 = await mw.on_model_error(self._ctx_error(RuntimeError()))  # attempt 3 → 4.0s
        self.assertAlmostEqual(d1.sleep_seconds, 1.0)
        self.assertAlmostEqual(d2.sleep_seconds, 2.0)
        self.assertAlmostEqual(d3.sleep_seconds, 4.0)

    async def test_jitter_reduces_delay(self) -> None:
        # [Hidden Assumption] Jitter must not produce a delay equal to or exceeding the cap.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=5, base_seconds=1.0, cap_seconds=100.0, jitter=True)
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d = await mw.on_model_error(self._ctx_error(RuntimeError()))
        self.assertLess(d.sleep_seconds, 1.0)
        self.assertGreaterEqual(d.sleep_seconds, 0.0)

    async def test_no_jitter_gives_exact_delay(self) -> None:
        # [Silent Failure] Without jitter the delay must be deterministic.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=3, base_seconds=2.0, cap_seconds=100.0, jitter=False)
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d = await mw.on_model_error(self._ctx_error(RuntimeError()))
        self.assertAlmostEqual(d.sleep_seconds, 2.0)

    async def test_delay_capped_at_cap_seconds(self) -> None:
        # [Edge Case] Very large attempt number must not exceed cap_seconds.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=100, base_seconds=1.0, cap_seconds=5.0, jitter=False)
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN))
        for _ in range(10):
            d = await mw.on_model_error(self._ctx_error(RuntimeError()))
            if d.action == MiddlewareAction.RETRY:
                self.assertLessEqual(d.sleep_seconds, 5.0)

    async def test_max_attempts_one_aborts_immediately(self) -> None:
        # [Edge Case] max_attempts=1 means the first error always aborts.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=1, base_seconds=1.0, jitter=False)
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d = await mw.on_model_error(self._ctx_error(RuntimeError()))
        self.assertEqual(d.action, MiddlewareAction.ABORT_RUN)

    async def test_retry_on_filters_error_type(self) -> None:
        # [Hidden Assumption] Non-matching error type must abort immediately without retry.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=5, retry_on=(ValueError,), jitter=False)
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d = await mw.on_model_error(self._ctx_error(RuntimeError("not a ValueError")))
        self.assertEqual(d.action, MiddlewareAction.ABORT_RUN)
        self.assertEqual(d.reason, "model_error_not_retryable")

    async def test_retry_on_none_retries_all_types(self) -> None:
        # [Hidden Assumption] retry_on=None must retry any error type.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=3, retry_on=None, jitter=False)
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d = await mw.on_model_error(self._ctx_error(TypeError("any")))
        self.assertEqual(d.action, MiddlewareAction.RETRY)

    async def test_retry_on_empty_tuple_aborts_all(self) -> None:
        # [Edge Case] Empty retry_on tuple means nothing is retryable.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=5, retry_on=(), jitter=False)
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d = await mw.on_model_error(self._ctx_error(ValueError()))
        self.assertEqual(d.action, MiddlewareAction.ABORT_RUN)

    async def test_resets_on_before_run(self) -> None:
        # [Hidden Failure] Attempt counter must reset between runs.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=2, base_seconds=0.001, jitter=False)
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN))
        await mw.on_model_error(self._ctx_error(RuntimeError()))
        await mw.on_model_error(self._ctx_error(RuntimeError()))
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d = await mw.on_model_error(self._ctx_error(RuntimeError()))
        self.assertEqual(d.action, MiddlewareAction.RETRY)

    async def test_metadata_contains_attempt_and_delay(self) -> None:
        # [Silent Failure] Retry decision metadata must include attempt and delay for observability.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=5, base_seconds=1.0, jitter=False)
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d = await mw.on_model_error(self._ctx_error(RuntimeError()))
        self.assertIn("attempt", d.metadata)
        self.assertIn("delay_seconds", d.metadata)
        self.assertIn("error_type", d.metadata)

    def test_raises_on_invalid_cap(self) -> None:
        # [Edge Case] cap_seconds below base_seconds is incoherent.
        with self.assertRaises(ValueError):
            ExponentialBackoffRetryMiddleware(base_seconds=5.0, cap_seconds=1.0)

    def test_raises_on_zero_max_attempts(self) -> None:
        # [Edge Case] Zero attempts means the middleware can never be used.
        with self.assertRaises(ValueError):
            ExponentialBackoffRetryMiddleware(max_attempts=0)


# ---------------------------------------------------------------------------
# LoopDetectionMiddleware
# ---------------------------------------------------------------------------


class TestLoopDetectionMiddleware(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # Each test gets its own fresh run_state dict so hooks share state within one test.
        self._run_state: dict = {}

    def _tool_ctx(self, name: str, args: dict | None = None, internal: bool = False) -> MiddlewareContext:
        return _ctx(
            hook=MiddlewareHook.BEFORE_TOOL_CALL,
            tool_call=ToolCall(tool_name=name, arguments=args or {}),
            tool_is_internal=internal,
            run_state=self._run_state,
        )

    def _run_ctx(self) -> MiddlewareContext:
        return _ctx(hook=MiddlewareHook.BEFORE_RUN, run_state=self._run_state)

    async def test_aborts_on_consecutive_identical_calls(self) -> None:
        # [Hidden Failure] Three identical (name, args) calls must abort.
        mw = LoopDetectionMiddleware(max_repeated_calls=3)
        await mw.before_run(self._run_ctx())
        await mw.before_tool_call(self._tool_ctx("search", {"q": "x"}))
        await mw.before_tool_call(self._tool_ctx("search", {"q": "x"}))
        d = await mw.before_tool_call(self._tool_ctx("search", {"q": "x"}))
        self.assertEqual(d.action, MiddlewareAction.ABORT_RUN)
        self.assertEqual(d.reason, "tool_loop_detected")

    async def test_continues_below_threshold(self) -> None:
        # [Edge Case] Two calls with threshold=3 must not abort.
        mw = LoopDetectionMiddleware(max_repeated_calls=3)
        await mw.before_run(self._run_ctx())
        await mw.before_tool_call(self._tool_ctx("search", {"q": "x"}))
        d = await mw.before_tool_call(self._tool_ctx("search", {"q": "x"}))
        self.assertEqual(d.action, MiddlewareAction.CONTINUE)

    async def test_resets_consecutive_count_on_different_tool(self) -> None:
        # [Silent Failure] A different call in the middle must break the consecutive streak.
        mw = LoopDetectionMiddleware(max_repeated_calls=3)
        await mw.before_run(self._run_ctx())
        await mw.before_tool_call(self._tool_ctx("search"))
        await mw.before_tool_call(self._tool_ctx("search"))
        await mw.before_tool_call(self._tool_ctx("other"))
        await mw.before_tool_call(self._tool_ctx("search"))
        d = await mw.before_tool_call(self._tool_ctx("search"))
        self.assertEqual(d.action, MiddlewareAction.CONTINUE)

    async def test_skips_internal_tools_by_default(self) -> None:
        # [Hidden Assumption] Internal tools must not be tracked when skip_internal_tools=True.
        mw = LoopDetectionMiddleware(max_repeated_calls=2, skip_internal_tools=True)
        await mw.before_run(self._run_ctx())
        await mw.before_tool_call(self._tool_ctx("isDone", internal=True))
        d = await mw.before_tool_call(self._tool_ctx("isDone", internal=True))
        self.assertEqual(d.action, MiddlewareAction.CONTINUE)

    async def test_tracks_internal_tools_when_not_skipping(self) -> None:
        # [Hidden Assumption] Internal tools must be tracked when skip_internal_tools=False.
        mw = LoopDetectionMiddleware(max_repeated_calls=2, skip_internal_tools=False)
        await mw.before_run(self._run_ctx())
        await mw.before_tool_call(self._tool_ctx("isDone", internal=True))
        d = await mw.before_tool_call(self._tool_ctx("isDone", internal=True))
        self.assertEqual(d.action, MiddlewareAction.ABORT_RUN)

    async def test_different_args_not_detected_as_loop(self) -> None:
        # [Silent Failure] Same tool name with different arguments must not trigger detection.
        mw = LoopDetectionMiddleware(max_repeated_calls=2)
        await mw.before_run(self._run_ctx())
        await mw.before_tool_call(self._tool_ctx("search", {"q": "apple"}))
        d = await mw.before_tool_call(self._tool_ctx("search", {"q": "orange"}))
        self.assertEqual(d.action, MiddlewareAction.CONTINUE)

    async def test_resets_on_before_run(self) -> None:
        # [Hidden Failure] Loop history must clear between runs (each run gets its own run_state).
        mw = LoopDetectionMiddleware(max_repeated_calls=2)
        rs_a: dict = {}
        rs_b: dict = {}
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN, run_state=rs_a))
        await mw.before_tool_call(_ctx(
            hook=MiddlewareHook.BEFORE_TOOL_CALL,
            tool_call=ToolCall(tool_name="search", arguments={}),
            run_state=rs_a,
        ))
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN, run_state=rs_b))
        d = await mw.before_tool_call(_ctx(
            hook=MiddlewareHook.BEFORE_TOOL_CALL,
            tool_call=ToolCall(tool_name="search", arguments={}),
            run_state=rs_b,
        ))
        self.assertEqual(d.action, MiddlewareAction.CONTINUE)

    async def test_window_bounds_history(self) -> None:
        # [Edge Case] window=3 means only the last 3 calls are considered.
        mw = LoopDetectionMiddleware(max_repeated_calls=3, window=3)
        await mw.before_run(self._run_ctx())
        await mw.before_tool_call(self._tool_ctx("search"))
        await mw.before_tool_call(self._tool_ctx("search"))
        # Third different call evicts the first "search" from the window.
        await mw.before_tool_call(self._tool_ctx("other"))
        # Now only "other" and "search" x2 remain; the third "search" doesn't make 3 consecutive.
        d = await mw.before_tool_call(self._tool_ctx("search"))
        # We only have "other", "search" in history now (window=3, added "search" makes 3 in window)
        # consecutive tail of "search" = 1; no abort.
        self.assertEqual(d.action, MiddlewareAction.CONTINUE)

    async def test_none_tool_call_skipped(self) -> None:
        # [Edge Case] ctx.tool_call is None must not be tracked and must not raise.
        mw = LoopDetectionMiddleware(max_repeated_calls=2)
        await mw.before_run(self._run_ctx())
        d = await mw.before_tool_call(_ctx(
            hook=MiddlewareHook.BEFORE_TOOL_CALL, tool_call=None, run_state=self._run_state
        ))
        self.assertEqual(d.action, MiddlewareAction.CONTINUE)

    async def test_metadata_contains_tool_name_and_count(self) -> None:
        # [Silent Failure] Abort metadata must identify the looping tool.
        mw = LoopDetectionMiddleware(max_repeated_calls=2)
        await mw.before_run(self._run_ctx())
        await mw.before_tool_call(self._tool_ctx("search"))
        d = await mw.before_tool_call(self._tool_ctx("search"))
        self.assertEqual(d.metadata["tool_name"], "search")
        self.assertEqual(d.metadata["repeated_count"], 2)

    def test_raises_on_max_repeated_calls_one(self) -> None:
        # [Edge Case] A threshold of 1 is meaningless (every call would be a loop).
        with self.assertRaises(ValueError):
            LoopDetectionMiddleware(max_repeated_calls=1)

    def test_raises_on_window_smaller_than_threshold(self) -> None:
        # [Edge Case] window < max_repeated_calls makes detection impossible.
        with self.assertRaises(ValueError):
            LoopDetectionMiddleware(max_repeated_calls=5, window=3)

    # --- repeated-output detection (soft / hard thresholds) ---

    def _result_ctx(self, tool_name: str, output: str, internal: bool = False) -> MiddlewareContext:
        return _ctx(
            hook=MiddlewareHook.AFTER_TOOL_CALL,
            tool_result=ToolResult.success(tool_name, output),
            tool_is_internal=internal,
            run_state=self._run_state,
        )

    async def test_output_hard_aborts_when_threshold_reached(self) -> None:
        # [Hidden Failure] Identical output seen hard_max_repeated_outputs times must abort.
        mw = LoopDetectionMiddleware(hard_max_repeated_outputs=3)
        await mw.before_run(self._run_ctx())
        await mw.after_tool_call(self._result_ctx("read_file", "content"))
        await mw.after_tool_call(self._result_ctx("read_file", "content"))
        d = await mw.after_tool_call(self._result_ctx("read_file", "content"))
        self.assertEqual(d.action, MiddlewareAction.ABORT_RUN)
        self.assertEqual(d.reason, "tool_output_loop_detected")

    async def test_output_disabled_by_default(self) -> None:
        # [Edge Case] Default middleware must neither abort nor nudge on repeated outputs.
        mw = LoopDetectionMiddleware()
        await mw.before_run(self._run_ctx())
        for _ in range(50):
            d = await mw.after_tool_call(self._result_ctx("read_file", "same content"))
        self.assertEqual(d.action, MiddlewareAction.CONTINUE)
        self.assertIsNone(d.transform)

    async def test_output_continues_below_hard_threshold(self) -> None:
        # [Edge Case] Count below the hard threshold must not abort.
        mw = LoopDetectionMiddleware(hard_max_repeated_outputs=4)
        await mw.before_run(self._run_ctx())
        await mw.after_tool_call(self._result_ctx("read_file", "content"))
        await mw.after_tool_call(self._result_ctx("read_file", "content"))
        d = await mw.after_tool_call(self._result_ctx("read_file", "content"))
        self.assertEqual(d.action, MiddlewareAction.CONTINUE)

    async def test_output_soft_injects_notice_and_continues(self) -> None:
        # [Hidden Failure] Soft threshold must inject the notice into the context window, not abort.
        mw = LoopDetectionMiddleware(soft_max_repeated_outputs=2)
        await mw.before_run(self._run_ctx())
        first = await mw.after_tool_call(self._result_ctx("read_file", "content"))
        # Below threshold: plain continue, no transform.
        self.assertEqual(first.action, MiddlewareAction.CONTINUE)
        self.assertIsNone(first.transform)
        d = await mw.after_tool_call(self._result_ctx("read_file", "content"))
        self.assertEqual(d.action, MiddlewareAction.CONTINUE)
        self.assertIsNotNone(d.transform)
        visible = d.transform.model_visible_tool_result
        self.assertIsNotNone(visible)
        # Original output preserved and the constant notice appended.
        self.assertIn("content", visible.output)
        self.assertIn(REPEATED_OUTPUT_LOOP_NOTICE, visible.output)
        self.assertTrue(visible.metadata["loop_detection_notice"])

    async def test_output_soft_never_aborts(self) -> None:
        # [Silent Failure] With only a soft threshold the run must never abort, however long the loop.
        mw = LoopDetectionMiddleware(soft_max_repeated_outputs=2)
        await mw.before_run(self._run_ctx())
        d = None
        for _ in range(20):
            d = await mw.after_tool_call(self._result_ctx("read_file", "content"))
        self.assertEqual(d.action, MiddlewareAction.CONTINUE)

    async def test_output_soft_then_hard(self) -> None:
        # [Hidden Failure] Soft nudges in the band, hard aborts at the hard threshold.
        mw = LoopDetectionMiddleware(soft_max_repeated_outputs=2, hard_max_repeated_outputs=4)
        await mw.before_run(self._run_ctx())
        d1 = await mw.after_tool_call(self._result_ctx("read_file", "x"))  # count 1
        d2 = await mw.after_tool_call(self._result_ctx("read_file", "x"))  # count 2 (soft)
        d3 = await mw.after_tool_call(self._result_ctx("read_file", "x"))  # count 3 (soft)
        d4 = await mw.after_tool_call(self._result_ctx("read_file", "x"))  # count 4 (hard)
        self.assertEqual(d1.action, MiddlewareAction.CONTINUE)
        self.assertIsNone(d1.transform)
        self.assertEqual(d2.action, MiddlewareAction.CONTINUE)
        self.assertIsNotNone(d2.transform)
        self.assertEqual(d3.action, MiddlewareAction.CONTINUE)
        self.assertIsNotNone(d3.transform)
        self.assertEqual(d4.action, MiddlewareAction.ABORT_RUN)
        self.assertEqual(d4.reason, "tool_output_loop_detected")

    async def test_output_counts_tools_independently(self) -> None:
        # [Silent Failure] Tool A hitting threshold must not abort tool B.
        mw = LoopDetectionMiddleware(hard_max_repeated_outputs=2)
        await mw.before_run(self._run_ctx())
        await mw.after_tool_call(self._result_ctx("read_file", "content"))
        await mw.after_tool_call(self._result_ctx("read_file", "content"))
        # read_file hit threshold; now glob with same string should NOT abort
        d = await mw.after_tool_call(self._result_ctx("glob", "content"))
        self.assertEqual(d.action, MiddlewareAction.CONTINUE)

    async def test_output_counts_non_consecutive_calls(self) -> None:
        # [Hidden Failure] The key use-case: A-B-A-B where A always returns same output.
        mw = LoopDetectionMiddleware(hard_max_repeated_outputs=3)
        await mw.before_run(self._run_ctx())
        await mw.after_tool_call(self._result_ctx("read_file", "no change"))
        await mw.after_tool_call(self._result_ctx("glob", "[]"))
        await mw.after_tool_call(self._result_ctx("read_file", "no change"))
        await mw.after_tool_call(self._result_ctx("glob", "[]"))
        d = await mw.after_tool_call(self._result_ctx("read_file", "no change"))
        self.assertEqual(d.action, MiddlewareAction.ABORT_RUN)
        self.assertEqual(d.reason, "tool_output_loop_detected")

    async def test_output_skips_internal_tools_when_configured(self) -> None:
        # [Hidden Assumption] Internal tool outputs must not count when skip_internal_tools=True.
        mw = LoopDetectionMiddleware(hard_max_repeated_outputs=2, skip_internal_tools=True)
        await mw.before_run(self._run_ctx())
        await mw.after_tool_call(self._result_ctx("isDone", "done", internal=True))
        d = await mw.after_tool_call(self._result_ctx("isDone", "done", internal=True))
        self.assertEqual(d.action, MiddlewareAction.CONTINUE)

    async def test_output_tracks_internal_tools_when_not_skipping(self) -> None:
        # [Hidden Assumption] Internal tools must be tracked when skip_internal_tools=False.
        mw = LoopDetectionMiddleware(hard_max_repeated_outputs=2, skip_internal_tools=False)
        await mw.before_run(self._run_ctx())
        await mw.after_tool_call(self._result_ctx("isDone", "done", internal=True))
        d = await mw.after_tool_call(self._result_ctx("isDone", "done", internal=True))
        self.assertEqual(d.action, MiddlewareAction.ABORT_RUN)

    async def test_output_skips_none_tool_result(self) -> None:
        # [Edge Case] ctx.tool_result is None (denied call) must not raise or count.
        mw = LoopDetectionMiddleware(hard_max_repeated_outputs=2)
        await mw.before_run(self._run_ctx())
        d = await mw.after_tool_call(_ctx(
            hook=MiddlewareHook.AFTER_TOOL_CALL, tool_result=None, run_state=self._run_state
        ))
        self.assertEqual(d.action, MiddlewareAction.CONTINUE)

    async def test_output_counts_empty_string(self) -> None:
        # [Edge Case] Empty string output is valid and must be counted.
        mw = LoopDetectionMiddleware(hard_max_repeated_outputs=2)
        await mw.before_run(self._run_ctx())
        await mw.after_tool_call(self._result_ctx("grep", ""))
        d = await mw.after_tool_call(self._result_ctx("grep", ""))
        self.assertEqual(d.action, MiddlewareAction.ABORT_RUN)

    async def test_output_metadata_contains_tool_name_hash_and_count(self) -> None:
        # [Silent Failure] Abort metadata must be complete for observability.
        mw = LoopDetectionMiddleware(hard_max_repeated_outputs=2)
        await mw.before_run(self._run_ctx())
        await mw.after_tool_call(self._result_ctx("read_file", "same"))
        d = await mw.after_tool_call(self._result_ctx("read_file", "same"))
        self.assertIn("tool_name", d.metadata)
        self.assertIn("output_hash", d.metadata)
        self.assertIn("repeated_count", d.metadata)
        self.assertIn("description", d.metadata)
        self.assertEqual(d.metadata["tool_name"], "read_file")
        self.assertEqual(d.metadata["repeated_count"], 2)
        self.assertEqual(d.metadata["description"], REPEATED_OUTPUT_LOOP_NOTICE)

    def test_output_raises_on_soft_max_one(self) -> None:
        # [Edge Case] soft_max_repeated_outputs=1 is meaningless; must raise ValueError.
        with self.assertRaises(ValueError):
            LoopDetectionMiddleware(soft_max_repeated_outputs=1)

    def test_output_raises_on_hard_max_one(self) -> None:
        # [Edge Case] hard_max_repeated_outputs=1 is meaningless; must raise ValueError.
        with self.assertRaises(ValueError):
            LoopDetectionMiddleware(hard_max_repeated_outputs=1)

    def test_output_raises_when_soft_not_below_hard(self) -> None:
        # [Edge Case] soft must fire before hard; soft >= hard is a misconfiguration.
        with self.assertRaises(ValueError):
            LoopDetectionMiddleware(soft_max_repeated_outputs=4, hard_max_repeated_outputs=3)
        with self.assertRaises(ValueError):
            LoopDetectionMiddleware(soft_max_repeated_outputs=3, hard_max_repeated_outputs=3)

    async def test_output_resets_on_new_run(self) -> None:
        # [Hidden Failure] Output counts must not persist across separate run_state dicts.
        mw = LoopDetectionMiddleware(hard_max_repeated_outputs=2)
        rs_a: dict = {}
        rs_b: dict = {}
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN, run_state=rs_a))
        await mw.after_tool_call(_ctx(
            hook=MiddlewareHook.AFTER_TOOL_CALL,
            tool_result=ToolResult.success("read_file", "content"),
            run_state=rs_a,
        ))
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN, run_state=rs_b))
        d = await mw.after_tool_call(_ctx(
            hook=MiddlewareHook.AFTER_TOOL_CALL,
            tool_result=ToolResult.success("read_file", "content"),
            run_state=rs_b,
        ))
        self.assertEqual(d.action, MiddlewareAction.CONTINUE)

    async def test_input_and_output_detection_coexist(self) -> None:
        # [Hidden Assumption] Both thresholds can be active; input abort fires first on consecutive.
        mw = LoopDetectionMiddleware(max_repeated_calls=2, hard_max_repeated_outputs=5)
        await mw.before_run(self._run_ctx())
        # Two identical input calls → input loop triggers
        await mw.before_tool_call(self._tool_ctx("search", {"q": "x"}))
        d = await mw.before_tool_call(self._tool_ctx("search", {"q": "x"}))
        self.assertEqual(d.reason, "tool_loop_detected")


# ---------------------------------------------------------------------------
# CircuitBreakerMiddleware
# ---------------------------------------------------------------------------


class TestCircuitBreakerMiddleware(unittest.IsolatedAsyncioTestCase):
    def _controlled_clock(self) -> tuple[list[float], callable]:
        """Return a mutable time store and a clock function that reads from it."""
        now = [0.0]

        def clock() -> float:
            return now[0]

        return now, clock

    async def test_starts_closed(self) -> None:
        # [Hidden Assumption] Circuit must begin in CLOSED state.
        mw = CircuitBreakerMiddleware(failure_threshold=3)
        self.assertEqual(mw.state, CircuitState.CLOSED)

    async def test_opens_after_threshold(self) -> None:
        # [Hidden Failure] Exactly failure_threshold errors must trip the circuit.
        now, clock = self._controlled_clock()
        mw = CircuitBreakerMiddleware(failure_threshold=3, window_seconds=60.0, clock=clock)
        ctx_err = _ctx(hook=MiddlewareHook.ON_MODEL_ERROR)
        await mw.on_model_error(ctx_err)
        await mw.on_model_error(ctx_err)
        self.assertEqual(mw.state, CircuitState.CLOSED)
        await mw.on_model_error(ctx_err)
        self.assertEqual(mw.state, CircuitState.OPEN)

    async def test_open_aborts_before_model_call(self) -> None:
        # [Silent Failure] An OPEN circuit must abort model calls immediately.
        now, clock = self._controlled_clock()
        mw = CircuitBreakerMiddleware(failure_threshold=1, recovery_timeout=30.0, clock=clock)
        await mw.on_model_error(_ctx(hook=MiddlewareHook.ON_MODEL_ERROR))
        d = await mw.before_model_call(_ctx(hook=MiddlewareHook.BEFORE_MODEL_CALL))
        self.assertEqual(d.action, MiddlewareAction.ABORT_RUN)
        self.assertEqual(d.reason, "circuit_open")

    async def test_transitions_to_half_open_after_timeout(self) -> None:
        # [Hidden Failure] After recovery_timeout the circuit must allow one probe.
        now, clock = self._controlled_clock()
        mw = CircuitBreakerMiddleware(failure_threshold=1, recovery_timeout=10.0, clock=clock)
        await mw.on_model_error(_ctx(hook=MiddlewareHook.ON_MODEL_ERROR))
        now[0] = 10.0
        d = await mw.before_model_call(_ctx(hook=MiddlewareHook.BEFORE_MODEL_CALL))
        self.assertEqual(mw.state, CircuitState.HALF_OPEN)
        self.assertEqual(d.action, MiddlewareAction.CONTINUE)

    async def test_half_open_allows_limited_calls(self) -> None:
        # [Edge Case] half_open_max_calls=1: second call must be blocked.
        now, clock = self._controlled_clock()
        mw = CircuitBreakerMiddleware(failure_threshold=1, recovery_timeout=5.0, half_open_max_calls=1, clock=clock)
        await mw.on_model_error(_ctx(hook=MiddlewareHook.ON_MODEL_ERROR))
        now[0] = 5.0
        d1 = await mw.before_model_call(_ctx(hook=MiddlewareHook.BEFORE_MODEL_CALL))
        d2 = await mw.before_model_call(_ctx(hook=MiddlewareHook.BEFORE_MODEL_CALL))
        self.assertEqual(d1.action, MiddlewareAction.CONTINUE)
        self.assertEqual(d2.action, MiddlewareAction.ABORT_RUN)
        self.assertEqual(d2.reason, "circuit_half_open_limit")

    async def test_half_open_closes_on_success(self) -> None:
        # [Hidden Assumption] A successful probe in HALF_OPEN must close the circuit.
        now, clock = self._controlled_clock()
        mw = CircuitBreakerMiddleware(failure_threshold=1, recovery_timeout=5.0, clock=clock)
        await mw.on_model_error(_ctx(hook=MiddlewareHook.ON_MODEL_ERROR))
        now[0] = 5.0
        await mw.before_model_call(_ctx(hook=MiddlewareHook.BEFORE_MODEL_CALL))
        await mw.after_model_response(_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE))
        self.assertEqual(mw.state, CircuitState.CLOSED)

    async def test_half_open_reopens_on_error(self) -> None:
        # [Hidden Failure] A failed probe in HALF_OPEN must re-open the circuit.
        now, clock = self._controlled_clock()
        mw = CircuitBreakerMiddleware(failure_threshold=1, recovery_timeout=5.0, clock=clock)
        await mw.on_model_error(_ctx(hook=MiddlewareHook.ON_MODEL_ERROR))
        now[0] = 5.0
        await mw.before_model_call(_ctx(hook=MiddlewareHook.BEFORE_MODEL_CALL))
        await mw.on_model_error(_ctx(hook=MiddlewareHook.ON_MODEL_ERROR))
        self.assertEqual(mw.state, CircuitState.OPEN)

    async def test_error_timestamps_pruned_outside_window(self) -> None:
        # [Silent Failure] Errors older than window_seconds must not count toward threshold.
        now, clock = self._controlled_clock()
        mw = CircuitBreakerMiddleware(failure_threshold=2, window_seconds=10.0, clock=clock)
        await mw.on_model_error(_ctx(hook=MiddlewareHook.ON_MODEL_ERROR))
        now[0] = 11.0  # advance past the window
        await mw.on_model_error(_ctx(hook=MiddlewareHook.ON_MODEL_ERROR))
        # Only one error is in the window; threshold=2 not yet met.
        self.assertEqual(mw.state, CircuitState.CLOSED)

    async def test_closed_continues_below_threshold(self) -> None:
        # [Edge Case] Fewer errors than threshold must leave circuit CLOSED.
        mw = CircuitBreakerMiddleware(failure_threshold=3)
        await mw.on_model_error(_ctx(hook=MiddlewareHook.ON_MODEL_ERROR))
        await mw.on_model_error(_ctx(hook=MiddlewareHook.ON_MODEL_ERROR))
        d = await mw.before_model_call(_ctx(hook=MiddlewareHook.BEFORE_MODEL_CALL))
        self.assertEqual(d.action, MiddlewareAction.CONTINUE)
        self.assertEqual(mw.state, CircuitState.CLOSED)

    async def test_abort_reason_is_circuit_open(self) -> None:
        # [Silent Failure] The abort reason must be identifiable for debugging.
        mw = CircuitBreakerMiddleware(failure_threshold=1)
        await mw.on_model_error(_ctx(hook=MiddlewareHook.ON_MODEL_ERROR))
        d = await mw.before_model_call(_ctx(hook=MiddlewareHook.BEFORE_MODEL_CALL))
        self.assertEqual(d.reason, "circuit_open")

    async def test_state_property_reflects_transitions(self) -> None:
        # [Hidden Assumption] .state must always match the internal state machine.
        now, clock = self._controlled_clock()
        mw = CircuitBreakerMiddleware(failure_threshold=1, recovery_timeout=5.0, clock=clock)
        self.assertEqual(mw.state, CircuitState.CLOSED)
        await mw.on_model_error(_ctx(hook=MiddlewareHook.ON_MODEL_ERROR))
        self.assertEqual(mw.state, CircuitState.OPEN)
        now[0] = 5.0
        await mw.before_model_call(_ctx(hook=MiddlewareHook.BEFORE_MODEL_CALL))
        self.assertEqual(mw.state, CircuitState.HALF_OPEN)
        await mw.after_model_response(_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE))
        self.assertEqual(mw.state, CircuitState.CLOSED)

    def test_raises_on_zero_threshold(self) -> None:
        # [Edge Case] A threshold of zero would open the circuit immediately.
        with self.assertRaises(ValueError):
            CircuitBreakerMiddleware(failure_threshold=0)

    def test_raises_on_zero_window_seconds(self) -> None:
        # [Edge Case] A zero-width window makes error tracking meaningless.
        with self.assertRaises(ValueError):
            CircuitBreakerMiddleware(window_seconds=0)

    def test_raises_on_zero_recovery_timeout(self) -> None:
        # [Edge Case] A zero timeout would transition immediately, defeating the purpose.
        with self.assertRaises(ValueError):
            CircuitBreakerMiddleware(recovery_timeout=0)

    def test_raises_on_zero_half_open_max_calls(self) -> None:
        # [Edge Case] Zero probe calls means the circuit can never close.
        with self.assertRaises(ValueError):
            CircuitBreakerMiddleware(half_open_max_calls=0)


if __name__ == "__main__":
    unittest.main()
