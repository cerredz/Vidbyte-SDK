"""Tests for the five new prebuilt middleware: TokenBudgetMiddleware,
CostBudgetMiddleware, ExponentialBackoffRetryMiddleware,
LoopDetectionMiddleware, and CircuitBreakerMiddleware, plus the
per-instance run state of ToolErrorPolicyMiddleware and TokenRateLimitMiddleware."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from vidbyte.agents import AgentRuntime
from vidbyte.agents.settings import ToolErrorPolicy
from vidbyte.agents.settings.tool import ToolSettings
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.dataclasses.context import BaseContext
from vidbyte.lib.dataclasses.middleware import (
    MiddlewareAction,
    MiddlewareContext,
    MiddlewareHook,
)
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.dataclasses.tools import ToolCall, ToolResult, ToolStatus
from vidbyte.lib.errors import ToolExecutionError
from vidbyte.middleware.builtins import (
    CircuitBreakerMiddleware,
    CircuitState,
    CostBudgetMiddleware,
    ExponentialBackoffRetryMiddleware,
    LoopDetectionMiddleware,
    TokenBudgetMiddleware,
    TokenRateLimitMiddleware,
    ToolErrorPolicyMiddleware,
)
from vidbyte.middleware.builtins.loop_detection import REPEATED_OUTPUT_LOOP_NOTICE
from vidbyte.middleware.builtins.token_budget import TOKEN_BUDGET_FINAL_RESPONSE_NOTICE
from vidbyte.tools import BaseTool, ToolPermission, ToolSpec, Tools, tool
from vidbyte.tools.security import PermissionPolicy


def _ctx(**kwargs) -> MiddlewareContext:
    """Build a minimal MiddlewareContext for unit tests."""
    defaults = dict(hook=MiddlewareHook.BEFORE_ITERATION, agent_name="test-agent")
    defaults.update(kwargs)
    return MiddlewareContext(**defaults)


async def _model_calls_before_cost_abort(middleware: list[CostBudgetMiddleware], max_iterations: int = 12) -> int:
    """Drive cost budgets in pipeline order on one run (20 tokens per call) and count model calls before abort."""
    run_state: dict = {}
    for mw in middleware:
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN, run_state=run_state))
    for calls in range(max_iterations):
        for mw in middleware:
            decision = await mw.before_iteration(_ctx(tokens_used=calls * 20, run_state=run_state))
            if decision.action == MiddlewareAction.ABORT_RUN:
                return calls
        for mw in middleware:
            await mw.after_model_response(_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, tokens_used=(calls + 1) * 20, run_state=run_state))
    return max_iterations


async def _tool_calls_before_loop_abort(middleware: list[LoopDetectionMiddleware], max_calls: int = 12) -> int:
    """Drive loop detectors in pipeline order on one run of identical fetches and count executed calls before abort."""
    run_state: dict = {}
    for mw in middleware:
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN, run_state=run_state))
    call = ToolCall(tool_name="fetch", arguments={"url": "https://example.com"})
    for executed in range(max_calls):
        for mw in middleware:
            decision = await mw.before_tool_call(_ctx(hook=MiddlewareHook.BEFORE_TOOL_CALL, tool_call=call, run_state=run_state))
            if decision.action == MiddlewareAction.ABORT_RUN:
                return executed
    return max_calls


async def _failed_tool_calls_before_error_abort(middleware: list[ToolErrorPolicyMiddleware], max_calls: int = 12) -> int:
    """Drive tool error policies in pipeline order on one run of always-failing calls and count failures before abort."""
    run_state: dict = {}
    for mw in middleware:
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN, run_state=run_state))
    for failed in range(1, max_calls + 1):
        call = ToolCall(tool_name="fetch", arguments={"attempt": failed})
        result = ToolResult(tool_name="fetch", status=ToolStatus.ERROR, output="boom", metadata={"error": "execution_error"})
        for mw in middleware:
            decision = await mw.after_tool_call(_ctx(hook=MiddlewareHook.AFTER_TOOL_CALL, tool_call=call, tool_result=result, run_state=run_state))
            if decision.action == MiddlewareAction.ABORT_RUN:
                return failed
    return max_calls


class _SteppingClock:
    """Fake monotonic clock that only moves when the test advances it."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def _hourly_rate_limit_sleeps(middleware: list[TokenRateLimitMiddleware], clock: _SteppingClock) -> list[float]:
    """Drive rate limiters in pipeline order (25 s and 20 tokens per call) and record the hourly limiter's sleeps."""
    run_state: dict = {}
    for mw in middleware:
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN, run_state=run_state))
    sleeps: list[float] = []
    for calls in range(1, 13):
        clock.now += 25.0
        for mw in middleware:
            decision = await mw.before_iteration(_ctx(tokens_used=calls * 20, run_state=run_state))
            if decision.action == MiddlewareAction.SLEEP and mw.per_seconds == 3600:
                sleeps.append(decision.sleep_seconds)
    return sleeps


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

    async def test_second_soft_budget_does_not_spend_this_ones_final_call(self) -> None:
        # [Silent Failure] Two soft budgets exceeded in one step must each grant their own final-answer call.
        for order in ((60, 80), (80, 60)):
            budgets = [TokenBudgetMiddleware(max_tokens=cap, allow_final_response_over_budget=True) for cap in order]
            run_state: dict = {}
            for mw in budgets:
                await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN, run_state=run_state))
            decisions = [
                await mw.before_model_call(
                    _ctx(hook=MiddlewareHook.BEFORE_MODEL_CALL, tokens_used=90, system="base", run_state=run_state)
                )
                for mw in budgets
            ]
            self.assertEqual([d.action for d in decisions], [MiddlewareAction.CONTINUE] * 2, order)

    def test_raises_on_zero_max(self) -> None:
        # [Edge Case] Zero is not a meaningful ceiling.
        with self.assertRaises(ValueError):
            TokenBudgetMiddleware(max_tokens=0)

    def test_raises_on_negative_max(self) -> None:
        # [Edge Case] Negative values are not a meaningful ceiling.
        with self.assertRaises(ValueError):
            TokenBudgetMiddleware(max_tokens=-1)


# ---------------------------------------------------------------------------
# ToolErrorPolicyMiddleware
# ---------------------------------------------------------------------------


class TestToolErrorPolicyMiddleware(unittest.IsolatedAsyncioTestCase):
    async def test_second_instance_does_not_change_when_strict_breaker_fires(self) -> None:
        # [Silent Failure] A lenient org policy beside a strict team policy must not add to the team's error count.
        def team() -> ToolErrorPolicyMiddleware:
            return ToolErrorPolicyMiddleware(ToolErrorPolicy(max_total_tool_errors=3))

        def org() -> ToolErrorPolicyMiddleware:
            return ToolErrorPolicyMiddleware(ToolErrorPolicy(max_total_tool_errors=50))

        alone = await _failed_tool_calls_before_error_abort([team()])
        self.assertEqual(alone, 3)
        self.assertEqual(await _failed_tool_calls_before_error_abort([team(), org()]), alone)
        self.assertEqual(await _failed_tool_calls_before_error_abort([org(), team()]), alone)

    async def test_legacy_argument_error_kinds_retry_as_invalid_arguments(self) -> None:
        # [Silent Failure] The model sees kind=invalid_arguments for these names, so retry_on=("invalid_arguments",) must retry them.
        for legacy in ("argument_error", "arguments_error"):
            with self.subTest(legacy=legacy):
                middleware = ToolErrorPolicyMiddleware(
                    ToolErrorPolicy(retry_on=("invalid_arguments",), max_retries_per_tool_call=1, retry_backoff_base_seconds=0)
                )
                call = ToolCall(tool_name="fetch", arguments={}, call_id="fc_fetch")
                result = ToolResult(tool_name="fetch", status=ToolStatus.ERROR, output="bad args", metadata={"error": legacy})
                decision = await middleware.after_tool_call(
                    _ctx(hook=MiddlewareHook.AFTER_TOOL_CALL, tool_call=call, tool_result=result, metadata={"tool_permission": "read"}, run_state={})
                )
                self.assertEqual(decision.action, MiddlewareAction.RETRY)
                self.assertEqual(decision.metadata["error"], "invalid_arguments")

    async def test_rate_limited_function_tool_is_retried(self) -> None:
        # @intent function-tool-errors-share-the-runtime-error-kind
        # [Silent Failure] A @tool function that raises a rate_limited ToolExecutionError is retried like a BaseTool.
        executions: list[int] = []

        @tool(name="lookup", permission=ToolPermission.READ)
        def lookup() -> str:
            """Lookup a value."""
            executions.append(1)
            if len(executions) == 1:
                raise ToolExecutionError("quota hit", details={"error": "rate_limited", "error_type": "RateLimited"})
            return "42"

        retry = ToolErrorPolicyMiddleware(ToolErrorPolicy(max_retries_per_tool_call=1, retry_backoff_base_seconds=0))
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools([lookup]), permission_policy=PermissionPolicy(), middleware=(retry,))
        context = runtime.build_context("task", base_context=BaseContext(), history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())
        handle = RunnerHandle(runner=_ScriptedLookupRunner(1), provider="openai", invoke=_invoke_scripted_lookup, extract_text=lambda response: response.text, extract_metadata=lambda response: {"raw": response.raw})
        result = await runtime.arun("task", handle=handle, context=context)

        self.assertEqual(result.metadata["stop_reason"], "final_response")
        self.assertEqual(len(executions), 2)

    async def test_refused_calls_do_not_trip_error_budget_or_abort(self) -> None:
        # [Silent Failure] A refused call is not a tool error, so repeated denials must not trip the breaker or abort the run.
        for kind in ("permission_denied", "middleware_denied"):
            with self.subTest(kind=kind):
                middleware = ToolErrorPolicyMiddleware(ToolErrorPolicy(max_total_tool_errors=1, on_unrecoverable="abort_run"))
                run_state: dict = {}
                await middleware.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN, run_state=run_state))
                for attempt in range(3):
                    call = ToolCall(tool_name="write_file", arguments={"attempt": attempt})
                    result = ToolResult(tool_name="write_file", status=ToolStatus.ERROR, output="denied", metadata={"error": kind})
                    decision = await middleware.after_tool_call(
                        _ctx(hook=MiddlewareHook.AFTER_TOOL_CALL, tool_call=call, tool_result=result, run_state=run_state)
                    )
                    self.assertEqual(decision.action, MiddlewareAction.CONTINUE)


# ---------------------------------------------------------------------------
# TokenRateLimitMiddleware
# ---------------------------------------------------------------------------


class TestTokenRateLimitMiddleware(unittest.IsolatedAsyncioTestCase):
    async def test_per_minute_limiter_does_not_weaken_per_hour_limiter(self) -> None:
        # [Silent Failure] A plan with per-minute and per-hour quotas must still throttle on the hourly cap.
        def stack(*windows: int) -> tuple[list[TokenRateLimitMiddleware], _SteppingClock]:
            clock = _SteppingClock()
            caps = {60: 1000, 3600: 50}
            return [TokenRateLimitMiddleware(max_tokens=caps[w], per_seconds=w, clock=clock) for w in windows], clock

        alone = await _hourly_rate_limit_sleeps(*stack(3600))
        self.assertTrue(alone)
        self.assertEqual(await _hourly_rate_limit_sleeps(*stack(60, 3600)), alone)
        self.assertEqual(await _hourly_rate_limit_sleeps(*stack(3600, 60)), alone)


# ---------------------------------------------------------------------------
# CostBudgetMiddleware
# ---------------------------------------------------------------------------


class TestCostBudgetMiddleware(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # One run_state dict per test models one agent run sharing state across hooks.
        self.run_state: dict = {}

    def _run_ctx(self, **kwargs) -> MiddlewareContext:
        return _ctx(run_state=self.run_state, **kwargs)

    async def test_aborts_after_spend_exceeded(self) -> None:
        # [Silent Failure] Accumulating past max_spend must abort before next iteration.
        mw = CostBudgetMiddleware(max_spend_usd=0.001, cost_per_million_tokens=1.0)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        # 1500 tokens at $1 / M = $0.0015 > $0.001
        await mw.after_model_response(self._run_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, tokens_used=1500))
        decision = await mw.before_iteration(self._run_ctx(tokens_used=1500))
        self.assertEqual(decision.action, MiddlewareAction.ABORT_RUN)
        self.assertEqual(decision.reason, "cost_budget_exceeded")

    async def test_continues_below_spend(self) -> None:
        # [Hidden Assumption] Partial spend must not abort.
        mw = CostBudgetMiddleware(max_spend_usd=1.0, cost_per_million_tokens=1.0)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        await mw.after_model_response(self._run_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, tokens_used=100))
        decision = await mw.before_iteration(self._run_ctx(tokens_used=100))
        self.assertEqual(decision.action, MiddlewareAction.CONTINUE)

    async def test_resets_state_on_before_run(self) -> None:
        # [Hidden Failure] Second run on same instance must start fresh.
        mw = CostBudgetMiddleware(max_spend_usd=0.001, cost_per_million_tokens=1.0)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        await mw.after_model_response(self._run_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, tokens_used=2000))
        # Reset
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        decision = await mw.before_iteration(self._run_ctx(tokens_used=2000))
        self.assertEqual(decision.action, MiddlewareAction.CONTINUE)

    async def test_skips_none_tokens(self) -> None:
        # [Edge Case] Provider not reporting tokens must never trigger cost abort.
        mw = CostBudgetMiddleware(max_spend_usd=0.0001, cost_per_million_tokens=1.0)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        await mw.after_model_response(self._run_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, tokens_used=None))
        decision = await mw.before_iteration(self._run_ctx(tokens_used=None))
        self.assertEqual(decision.action, MiddlewareAction.CONTINUE)

    async def test_handles_token_count_decrease(self) -> None:
        # [Hidden Failure] Backwards token count must not produce negative delta.
        mw = CostBudgetMiddleware(max_spend_usd=1.0, cost_per_million_tokens=1.0)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        await mw.after_model_response(self._run_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, tokens_used=500))
        await mw.after_model_response(self._run_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, tokens_used=100))
        # Spend should only reflect the first 500 tokens.
        self.assertAlmostEqual(mw._estimated_spend_usd, 500 / 1_000_000 * 1.0)

    async def test_metadata_contains_spend_values(self) -> None:
        # [Silent Failure] Abort metadata must surface financial figures for debugging.
        mw = CostBudgetMiddleware(max_spend_usd=0.001, cost_per_million_tokens=1.0)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        await mw.after_model_response(self._run_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, tokens_used=2000))
        decision = await mw.before_iteration(self._run_ctx(tokens_used=2000))
        self.assertIn("max_spend_usd", decision.metadata)
        self.assertIn("estimated_spend_usd", decision.metadata)

    async def test_nested_run_does_not_reset_parent_spend(self) -> None:
        # [Silent Failure] A forked child run shares this instance; its before_run must not zero the parent's spend.
        mw = CostBudgetMiddleware(max_spend_usd=0.002, cost_per_million_tokens=1.0)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        await mw.after_model_response(self._run_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, tokens_used=2000))
        child_state: dict = {}
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN, run_state=child_state))
        await mw.after_model_response(_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, tokens_used=100, run_state=child_state))
        decision = await mw.before_iteration(self._run_ctx(tokens_used=2000))
        self.assertEqual(decision.action, MiddlewareAction.ABORT_RUN)
        self.assertAlmostEqual(decision.metadata["estimated_spend_usd"], 0.002)
        self.assertAlmostEqual(mw.estimated_spend_usd_for(self.run_state), 0.002)
        self.assertAlmostEqual(mw.estimated_spend_usd_for(child_state), 0.0001)

    async def test_estimated_spend_property_mirrors_latest_update(self) -> None:
        # [Hidden Assumption] The public property still reports the most recent run's estimate.
        mw = CostBudgetMiddleware(max_spend_usd=1.0, cost_per_million_tokens=2.0)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        await mw.after_model_response(self._run_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE, tokens_used=1000))
        self.assertAlmostEqual(mw.estimated_spend_usd, 0.002)

    async def test_second_instance_does_not_change_when_strict_budget_fires(self) -> None:
        # [Silent Failure] A lenient org budget beside a strict team budget must not overwrite the team's spend.
        def team() -> CostBudgetMiddleware:
            return CostBudgetMiddleware(max_spend_usd=0.0005, cost_per_million_tokens=10.0)

        def org() -> CostBudgetMiddleware:
            return CostBudgetMiddleware(max_spend_usd=100.0, cost_per_million_tokens=1.0)

        alone = await _model_calls_before_cost_abort([team()])
        self.assertEqual(alone, 3)
        self.assertEqual(await _model_calls_before_cost_abort([team(), org()]), alone)
        self.assertEqual(await _model_calls_before_cost_abort([org(), team()]), alone)

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
    def setUp(self) -> None:
        # One run_state dict per test models one agent run sharing state across hooks.
        self.run_state: dict = {}

    def _run_ctx(self, **kwargs) -> MiddlewareContext:
        return _ctx(run_state=self.run_state, **kwargs)

    def _ctx_error(self, error: BaseException | None = None) -> MiddlewareContext:
        return self._run_ctx(hook=MiddlewareHook.ON_MODEL_ERROR, error=error)

    async def test_retries_up_to_max_then_aborts(self) -> None:
        # [Edge Case] Three attempts: two retries then abort on the third error.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=3, base_seconds=0.001, jitter=False)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d1 = await mw.on_model_error(self._ctx_error(RuntimeError("e")))
        d2 = await mw.on_model_error(self._ctx_error(RuntimeError("e")))
        d3 = await mw.on_model_error(self._ctx_error(RuntimeError("e")))
        self.assertEqual(d1.action, MiddlewareAction.RETRY)
        self.assertEqual(d2.action, MiddlewareAction.RETRY)
        self.assertEqual(d3.action, MiddlewareAction.ABORT_RUN)

    async def test_delay_is_exponential(self) -> None:
        # [Silent Failure] Delays must grow as base * 2^(attempt-1).
        mw = ExponentialBackoffRetryMiddleware(max_attempts=5, base_seconds=1.0, cap_seconds=100.0, jitter=False)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d1 = await mw.on_model_error(self._ctx_error(RuntimeError()))  # attempt 1 → 1.0s
        d2 = await mw.on_model_error(self._ctx_error(RuntimeError()))  # attempt 2 → 2.0s
        d3 = await mw.on_model_error(self._ctx_error(RuntimeError()))  # attempt 3 → 4.0s
        self.assertAlmostEqual(d1.sleep_seconds, 1.0)
        self.assertAlmostEqual(d2.sleep_seconds, 2.0)
        self.assertAlmostEqual(d3.sleep_seconds, 4.0)

    async def test_jitter_reduces_delay(self) -> None:
        # [Hidden Assumption] Jitter must not produce a delay equal to or exceeding the cap.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=5, base_seconds=1.0, cap_seconds=100.0, jitter=True)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d = await mw.on_model_error(self._ctx_error(RuntimeError()))
        self.assertLess(d.sleep_seconds, 1.0)
        self.assertGreaterEqual(d.sleep_seconds, 0.0)

    async def test_no_jitter_gives_exact_delay(self) -> None:
        # [Silent Failure] Without jitter the delay must be deterministic.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=3, base_seconds=2.0, cap_seconds=100.0, jitter=False)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d = await mw.on_model_error(self._ctx_error(RuntimeError()))
        self.assertAlmostEqual(d.sleep_seconds, 2.0)

    async def test_delay_capped_at_cap_seconds(self) -> None:
        # [Edge Case] Very large attempt number must not exceed cap_seconds.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=100, base_seconds=1.0, cap_seconds=5.0, jitter=False)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        for _ in range(10):
            d = await mw.on_model_error(self._ctx_error(RuntimeError()))
            if d.action == MiddlewareAction.RETRY:
                self.assertLessEqual(d.sleep_seconds, 5.0)

    async def test_max_attempts_one_aborts_immediately(self) -> None:
        # [Edge Case] max_attempts=1 means the first error always aborts.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=1, base_seconds=1.0, jitter=False)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d = await mw.on_model_error(self._ctx_error(RuntimeError()))
        self.assertEqual(d.action, MiddlewareAction.ABORT_RUN)

    async def test_retry_on_filters_error_type(self) -> None:
        # [Hidden Assumption] Non-matching error type must abort immediately without retry.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=5, retry_on=(ValueError,), jitter=False)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d = await mw.on_model_error(self._ctx_error(RuntimeError("not a ValueError")))
        self.assertEqual(d.action, MiddlewareAction.ABORT_RUN)
        self.assertEqual(d.reason, "model_error_not_retryable")

    async def test_retry_on_none_retries_all_types(self) -> None:
        # [Hidden Assumption] retry_on=None must retry any error type.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=3, retry_on=None, jitter=False)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d = await mw.on_model_error(self._ctx_error(TypeError("any")))
        self.assertEqual(d.action, MiddlewareAction.RETRY)

    async def test_retry_on_empty_tuple_aborts_all(self) -> None:
        # [Edge Case] Empty retry_on tuple means nothing is retryable.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=5, retry_on=(), jitter=False)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d = await mw.on_model_error(self._ctx_error(ValueError()))
        self.assertEqual(d.action, MiddlewareAction.ABORT_RUN)

    async def test_retry_on_accepts_list_and_bare_class_and_rejects_non_exceptions(self) -> None:
        # [Silent Failure] A list used to raise TypeError inside on_model_error and abort the run.
        for retry_on in ([ValueError], (ValueError,), ValueError):
            mw = ExponentialBackoffRetryMiddleware(max_attempts=3, retry_on=retry_on, jitter=False)
            await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
            retried = await mw.on_model_error(self._ctx_error(ValueError("transient")))
            skipped = await mw.on_model_error(self._ctx_error(RuntimeError("other")))
            self.assertEqual(retried.action, MiddlewareAction.RETRY, retry_on)
            self.assertEqual(skipped.reason, "model_error_not_retryable", retry_on)
        for bad in (["ValueError"], [ValueError, int], "ValueError"):
            with self.assertRaisesRegex(ValueError, "retry_on entries must be exception classes"):
                ExponentialBackoffRetryMiddleware(retry_on=bad)

    async def test_resets_on_before_run(self) -> None:
        # [Hidden Failure] Attempt counter must reset between runs.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=2, base_seconds=0.001, jitter=False)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        await mw.on_model_error(self._ctx_error(RuntimeError()))
        await mw.on_model_error(self._ctx_error(RuntimeError()))
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d = await mw.on_model_error(self._ctx_error(RuntimeError()))
        self.assertEqual(d.action, MiddlewareAction.RETRY)

    async def test_metadata_contains_attempt_and_delay(self) -> None:
        # [Silent Failure] Retry decision metadata must include attempt and delay for observability.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=5, base_seconds=1.0, jitter=False)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        d = await mw.on_model_error(self._ctx_error(RuntimeError()))
        self.assertIn("attempt", d.metadata)
        self.assertIn("delay_seconds", d.metadata)
        self.assertIn("error_type", d.metadata)

    async def test_nested_run_does_not_reset_parent_attempts(self) -> None:
        # [Silent Failure] A nested run's before_run must not reset the parent's attempt counter.
        mw = ExponentialBackoffRetryMiddleware(max_attempts=2, base_seconds=0.001, jitter=False)
        await mw.before_run(self._run_ctx(hook=MiddlewareHook.BEFORE_RUN))
        first = await mw.on_model_error(self._ctx_error(RuntimeError()))
        child_state: dict = {}
        await mw.before_run(_ctx(hook=MiddlewareHook.BEFORE_RUN, run_state=child_state))
        second = await mw.on_model_error(self._ctx_error(RuntimeError()))
        child = await mw.on_model_error(_ctx(hook=MiddlewareHook.ON_MODEL_ERROR, error=RuntimeError(), run_state=child_state))
        self.assertEqual(first.action, MiddlewareAction.RETRY)
        self.assertEqual(second.action, MiddlewareAction.ABORT_RUN)
        self.assertEqual(second.reason, "model_retry_exhausted")
        self.assertEqual(child.action, MiddlewareAction.RETRY)

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

    async def test_second_instance_does_not_change_when_strict_detector_fires(self) -> None:
        # [Silent Failure] A second detector must not double-count the strict detector's calls.
        def team() -> LoopDetectionMiddleware:
            return LoopDetectionMiddleware(max_repeated_calls=4, window=10)

        def org() -> LoopDetectionMiddleware:
            return LoopDetectionMiddleware(max_repeated_calls=6, window=10)

        alone = await _tool_calls_before_loop_abort([team()])
        self.assertEqual(alone, 3)
        self.assertEqual(await _tool_calls_before_loop_abort([team(), org()]), alone)
        self.assertEqual(await _tool_calls_before_loop_abort([org(), team()]), alone)

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

    async def test_soft_notice_survives_tool_result_truncation(self) -> None:
        # @intent appended-middleware-notes-survive-truncation
        # [Silent Failure] A result_max_chars cap shorter than the tool output must not cut the notice off.
        @tool
        def lookup() -> str:
            # Returns the same long page on every call so the soft threshold fires on the second.
            return "same page " * 40

        config = AgentRuntimeConfig(tool_settings=ToolSettings(result_max_chars=120))
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools([lookup]), permission_policy=PermissionPolicy(), config=config, middleware=(LoopDetectionMiddleware(soft_max_repeated_outputs=2),))
        context = runtime.build_context("task", base_context=BaseContext(), history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())
        runner = _RepeatingLookupRunner()
        handle = RunnerHandle(runner=runner, provider="openai", invoke=_invoke_repeating_lookup, extract_text=lambda response: response.text, extract_metadata=lambda response: {"raw": response.raw})
        await runtime.arun("task", handle=handle, context=context)
        self.assertIn("tool output truncated by ToolSettings", runner.seen_tool_output)
        self.assertIn(REPEATED_OUTPUT_LOOP_NOTICE, runner.seen_tool_output)


    async def test_hidden_tool_retries_count_as_one_output(self) -> None:
        # @intent hidden-retries-count-once
        # [Hidden Failure] One model call retried silently is one output, in either middleware order; three model calls still abort.
        async def run(lookups: int, loop_first: bool) -> tuple[str, int]:
            failing = _UpstreamErrorLookup()
            loop = LoopDetectionMiddleware(hard_max_repeated_outputs=3)
            retry = ToolErrorPolicyMiddleware(ToolErrorPolicy(max_retries_per_tool_call=2, retry_backoff_base_seconds=0))
            runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools([failing]), permission_policy=PermissionPolicy(), middleware=(loop, retry) if loop_first else (retry, loop))
            context = runtime.build_context("task", base_context=BaseContext(), history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())
            handle = RunnerHandle(runner=_ScriptedLookupRunner(lookups), provider="openai", invoke=_invoke_scripted_lookup, extract_text=lambda response: response.text, extract_metadata=lambda response: {"raw": response.raw})
            result = await runtime.arun("task", handle=handle, context=context)
            return result.metadata["stop_reason"], failing.executions

        for loop_first in (True, False):
            with self.subTest(loop_first=loop_first):
                self.assertEqual(await run(1, loop_first), ("final_response", 3))
                stop_reason, _ = await run(3, loop_first)
                self.assertEqual(stop_reason, "middleware_abort")


class _UpstreamErrorLookup(BaseTool):
    """Read-only lookup that always fails with a retryable upstream error."""

    def __init__(self) -> None:
        self.executions = 0

    def spec(self) -> ToolSpec:
        return ToolSpec(name="lookup", description="Lookup a value.", permission=ToolPermission.READ)

    async def execute(self, call: ToolCall) -> ToolResult:
        self.executions += 1
        return ToolResult.error("lookup", "upstream unavailable", metadata={"error": "upstream_error"})


class _ScriptedLookupRunner:
    """Fake model that makes `lookups` separate lookup calls, one per turn, then answers."""

    def __init__(self, lookups: int) -> None:
        self.lookups = lookups
        self.turns = 0


async def _invoke_scripted_lookup(runner: _ScriptedLookupRunner, prompt: str, **kwargs: object) -> SimpleNamespace:
    # Each lookup turn carries its own call_id, as a real provider's separate tool calls would.
    del prompt, kwargs
    runner.turns += 1
    if runner.turns > runner.lookups:
        return SimpleNamespace(text="Done.", raw={})
    call = {"type": "function_call", "name": "lookup", "arguments": "{}", "call_id": f"fc_{runner.turns}"}
    return SimpleNamespace(text="", raw={"output": [call]})


class _RepeatingLookupRunner:
    """Fake model that calls lookup twice, then answers, keeping the last tool result it saw."""

    def __init__(self) -> None:
        self.turns = 0
        self.seen_tool_output = ""


async def _invoke_repeating_lookup(runner: _RepeatingLookupRunner, prompt: str, **kwargs: object) -> SimpleNamespace:
    # Calls lookup on the first two turns and records the newest tool result on every later turn.
    del prompt
    runner.turns += 1
    if runner.turns > 1:
        runner.seen_tool_output = str(kwargs["messages"][-1]["content"])
    if runner.turns > 2:
        return SimpleNamespace(text="Done.", raw={})
    return SimpleNamespace(text="", raw={"output": [{"type": "function_call", "name": "lookup", "arguments": "{}"}]})


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

    async def test_abandoned_half_open_probe_expires_after_recovery_timeout(self) -> None:
        # [Hidden Failure] A granted probe that never reports back must not wedge HALF_OPEN forever.
        now, clock = self._controlled_clock()
        mw = CircuitBreakerMiddleware(failure_threshold=1, recovery_timeout=5.0, half_open_max_calls=1, clock=clock)
        await mw.on_model_error(_ctx(hook=MiddlewareHook.ON_MODEL_ERROR))
        now[0] = 5.0
        probe = await mw.before_model_call(_ctx(hook=MiddlewareHook.BEFORE_MODEL_CALL))
        self.assertEqual(probe.action, MiddlewareAction.CONTINUE)
        self.assertEqual(mw.state, CircuitState.HALF_OPEN)
        # The probe is abandoned: no after_model_response and no on_model_error ever arrive.
        now[0] = 9.9
        blocked = await mw.before_model_call(_ctx(hook=MiddlewareHook.BEFORE_MODEL_CALL))
        self.assertEqual(blocked.action, MiddlewareAction.ABORT_RUN)
        self.assertEqual(blocked.reason, "circuit_half_open_limit")
        now[0] = 10.0
        fresh = await mw.before_model_call(_ctx(hook=MiddlewareHook.BEFORE_MODEL_CALL))
        self.assertEqual(fresh.action, MiddlewareAction.CONTINUE)
        self.assertEqual(mw.state, CircuitState.HALF_OPEN)
        # The fresh probe window is bounded again until it also expires.
        again = await mw.before_model_call(_ctx(hook=MiddlewareHook.BEFORE_MODEL_CALL))
        self.assertEqual(again.reason, "circuit_half_open_limit")
        await mw.after_model_response(_ctx(hook=MiddlewareHook.AFTER_MODEL_RESPONSE))
        self.assertEqual(mw.state, CircuitState.CLOSED)

    async def test_reopened_circuit_does_not_reuse_stale_probe_window(self) -> None:
        # [Edge Case] After a failed probe re-opens the circuit, OPEN timing applies, not the old probe window.
        now, clock = self._controlled_clock()
        mw = CircuitBreakerMiddleware(failure_threshold=1, recovery_timeout=5.0, clock=clock)
        await mw.on_model_error(_ctx(hook=MiddlewareHook.ON_MODEL_ERROR))
        now[0] = 5.0
        await mw.before_model_call(_ctx(hook=MiddlewareHook.BEFORE_MODEL_CALL))
        now[0] = 6.0
        await mw.on_model_error(_ctx(hook=MiddlewareHook.ON_MODEL_ERROR))
        self.assertEqual(mw.state, CircuitState.OPEN)
        now[0] = 10.5
        d = await mw.before_model_call(_ctx(hook=MiddlewareHook.BEFORE_MODEL_CALL))
        self.assertEqual(d.reason, "circuit_open")

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
