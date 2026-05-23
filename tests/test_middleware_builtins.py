from __future__ import annotations

import unittest

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareEvent, MiddlewareHook
from vidbyte.middleware.builtins import (
    AuditLogMiddleware,
    RuntimeLimitMiddleware,
    TokenRateLimitMiddleware,
    ToolPolicyMiddleware,
)
from vidbyte.tools import ToolCall


class FakeClock:
    def __init__(self, value: float = 0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class MiddlewareBuiltinsTests(unittest.IsolatedAsyncioTestCase):
    async def test_token_rate_limit_sleeps_when_provider_tokens_exceed_window(self) -> None:
        clock = FakeClock()
        middleware = TokenRateLimitMiddleware(max_tokens=3, per_seconds=10, clock=clock)

        decision = await middleware.before_iteration(
            MiddlewareContext(
                hook=MiddlewareHook.BEFORE_ITERATION,
                agent_name="worker",
                tokens_used=4,
            )
        )

        self.assertEqual(decision.action.value, "sleep")
        self.assertEqual(decision.reason, "token_rate_limit")
        self.assertEqual(decision.sleep_seconds, 10)

    async def test_token_rate_limit_continues_without_token_usage(self) -> None:
        middleware = TokenRateLimitMiddleware(max_tokens=3, per_seconds=10, clock=FakeClock())

        decision = await middleware.before_iteration(
            MiddlewareContext(hook=MiddlewareHook.BEFORE_ITERATION, agent_name="worker")
        )

        self.assertEqual(decision.action.value, "continue")

    async def test_runtime_limit_aborts_on_elapsed_seconds(self) -> None:
        middleware = RuntimeLimitMiddleware(max_elapsed_seconds=5)

        decision = await middleware.before_iteration(
            MiddlewareContext(
                hook=MiddlewareHook.BEFORE_ITERATION,
                agent_name="worker",
                elapsed_seconds=5,
            )
        )

        self.assertEqual(decision.action.value, "abort_run")
        self.assertEqual(decision.reason, "runtime_elapsed_limit")

    async def test_tool_policy_denies_denylisted_tool(self) -> None:
        middleware = ToolPolicyMiddleware(deny_tools={"danger"})

        decision = await middleware.before_tool_call(
            MiddlewareContext(
                hook=MiddlewareHook.BEFORE_TOOL_CALL,
                agent_name="worker",
                tool_call=ToolCall("danger"),
            )
        )

        self.assertEqual(decision.action.value, "deny_tool")
        self.assertEqual(decision.reason, "tool_denylisted")

    async def test_tool_policy_allows_internal_tool_by_default(self) -> None:
        middleware = ToolPolicyMiddleware(allow_tools={"lookup"})

        decision = await middleware.before_tool_call(
            MiddlewareContext(
                hook=MiddlewareHook.BEFORE_TOOL_CALL,
                agent_name="worker",
                tool_call=ToolCall("isDone"),
                tool_is_internal=True,
            )
        )

        self.assertEqual(decision.action.value, "continue")

    async def test_audit_log_appends_events(self) -> None:
        events: list[MiddlewareEvent] = []
        middleware = AuditLogMiddleware(events)

        decision = await middleware.before_run(
            MiddlewareContext(hook=MiddlewareHook.BEFORE_RUN, agent_name="worker")
        )

        self.assertEqual(decision.action.value, "continue")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].hook, MiddlewareHook.BEFORE_RUN)


if __name__ == "__main__":
    unittest.main()
