from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests.agent_test_support import build_test_agent
from vidbyte import tool
from vidbyte.agents import AgentRuntime
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareEvent, MiddlewareHook
from vidbyte.middleware.builtins import (
    AuditLogMiddleware,
    ModelRetryMiddleware,
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


class ParallelToolCallRunner:
    # Answers the first model call with three invoice calls in one response, the way parallel tool calling does.
    def __init__(self) -> None:
        self.calls = 0

    def run(self, prompt: str, **kwargs: object) -> SimpleNamespace:
        self.calls += 1
        calls = [("call_1", "acme"), ("call_2", "globex"), ("call_3", "initech")]
        tool_calls = [{"id": call_id, "type": "function", "function": {"name": "send_invoice", "arguments": f'{{"customer": "{customer}"}}'}} for call_id, customer in calls]
        return SimpleNamespace(text="", raw={"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": tool_calls}}]})


class FlakyThenAnswerRunner:
    # Fails with a 503 a fixed number of times, then answers through isDone.
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def run(self, prompt: str, **kwargs: object) -> SimpleNamespace:
        self.calls += 1
        if self.calls <= self.failures:
            raise ProviderRequestError("503 Service Unavailable", provider="openai", status_code=503)
        tool_calls = [{"id": "call_done", "type": "function", "function": {"name": "isDone", "arguments": '{"final_answer": "answer"}'}}]
        return SimpleNamespace(text="", raw={"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": tool_calls}}]})


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

    async def test_runtime_tool_limit_caps_calls_inside_one_model_response(self) -> None:
        # @intent runtime-tool-limit-caps-every-call
        # Three calls in one response under a cap of two must send two invoices, not three, like AgentLoopSettings.max_tool_calls.
        sent: list[str] = []

        @tool
        def send_invoice(customer: str) -> str:
            """Send the invoice."""
            sent.append(customer)
            return "sent"

        middleware = RuntimeLimitMiddleware(max_tool_calls=2)
        agent = build_test_agent(name="billing", system_prompt="Send invoices.", runner=ParallelToolCallRunner(), tools=[send_invoice], middleware=[middleware])
        with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
            reply = await agent.arun("invoice everyone")

        self.assertEqual(sent, ["acme", "globex"])
        self.assertEqual(reply.metadata["stop_reason"], "middleware_abort")
        self.assertEqual(reply.metadata["middleware_abort_reason"], "runtime_tool_call_limit")
        # The loop's own isDone at the cap is never blocked, since it does not spend the tool budget.
        is_done = await middleware.before_tool_call(
            MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="billing", tool_call=ToolCall("isDone"), tool_is_internal=True, tool_call_count=2)
        )
        self.assertEqual(is_done.action.value, "continue")


    async def test_runtime_model_call_limit_caps_retries_inside_one_iteration(self) -> None:
        # @intent runtime-model-call-limit-caps-every-call
        # Three 503s then an answer under max_model_calls=2 must send two requests, not four; a run that fits the cap still answers.
        for failures, expected_calls, expected_stop in ((3, 2, "middleware_abort"), (1, 2, "is_done")):
            runner = FlakyThenAnswerRunner(failures)
            middleware = [RuntimeLimitMiddleware(max_model_calls=2), ModelRetryMiddleware(max_attempts=4)]
            agent = build_test_agent(name="saver", system_prompt="Answer.", runner=runner, middleware=middleware)
            with patch.object(AgentRuntime, "_llm_trace_inputs", return_value={}):
                reply = await agent.arun("question")

            self.assertEqual(runner.calls, expected_calls)
            self.assertEqual(reply.metadata["stop_reason"], expected_stop)
            if expected_stop == "middleware_abort":
                self.assertEqual(reply.metadata["middleware_abort_reason"], "runtime_model_call_limit")
            else:
                self.assertEqual(reply.content, "answer")

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

    def test_tool_policy_rejects_bare_string_name_lists(self) -> None:
        # ("wipe_db") is a str, not a 1-tuple; a character set would let wipe_db run.
        with self.assertRaisesRegex(ValueError, "deny_tools must be an iterable of tool names, not a string"):
            ToolPolicyMiddleware(deny_tools=("wipe_db"))
        with self.assertRaisesRegex(ValueError, "allow_tools must be an iterable of tool names, not a string"):
            ToolPolicyMiddleware(allow_tools=("search"))

    async def test_tool_policy_one_item_tuple_and_list_still_apply(self) -> None:
        deny = ToolPolicyMiddleware(deny_tools=("wipe_db",))
        allow = ToolPolicyMiddleware(allow_tools=["search"])
        self.assertIsNone(ToolPolicyMiddleware().allow_tools)

        denied = await deny.before_tool_call(
            MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="worker", tool_call=ToolCall("wipe_db"))
        )
        allowed = await allow.before_tool_call(
            MiddlewareContext(hook=MiddlewareHook.BEFORE_TOOL_CALL, agent_name="worker", tool_call=ToolCall("search"))
        )

        self.assertEqual(denied.reason, "tool_denylisted")
        self.assertEqual(allowed.action.value, "continue")

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

    async def test_audit_log_single_hook_member_audits_only_that_hook(self) -> None:
        # A lone MiddlewareHook is a str; it must filter to that hook, not to its characters.
        events: list[MiddlewareEvent] = []
        middleware = AuditLogMiddleware(events, hooks=MiddlewareHook.AFTER_RUN)

        await middleware.before_run(MiddlewareContext(hook=MiddlewareHook.BEFORE_RUN, agent_name="worker"))
        await middleware.after_run(MiddlewareContext(hook=MiddlewareHook.AFTER_RUN, agent_name="worker"))

        self.assertEqual([event.hook for event in events], [MiddlewareHook.AFTER_RUN])

    def test_audit_log_rejects_bare_string_hooks(self) -> None:
        # "after_run" is a str, so a character set would silently audit nothing.
        with self.assertRaisesRegex(ValueError, "AuditLogMiddleware.hooks must be an iterable"):
            AuditLogMiddleware([], hooks="after_run")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "AuditLogMiddleware.hooks must be an iterable"):
            AuditLogMiddleware([], hooks=b"after_run")  # type: ignore[arg-type]

    async def test_audit_log_hook_list_still_filters(self) -> None:
        # Verifies the list form, including plain string values, keeps filtering exactly as before.
        for hooks in ([MiddlewareHook.AFTER_RUN], ["after_run"]):
            events: list[MiddlewareEvent] = []
            middleware = AuditLogMiddleware(events, hooks=hooks)  # type: ignore[arg-type]

            await middleware.before_run(MiddlewareContext(hook=MiddlewareHook.BEFORE_RUN, agent_name="worker"))
            await middleware.after_run(MiddlewareContext(hook=MiddlewareHook.AFTER_RUN, agent_name="worker"))

            self.assertEqual([event.hook for event in events], [MiddlewareHook.AFTER_RUN])


if __name__ == "__main__":
    unittest.main()
