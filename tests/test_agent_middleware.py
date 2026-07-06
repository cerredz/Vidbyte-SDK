from __future__ import annotations

import unittest

from vidbyte.agents import AgentLoopSettings, AgentRuntime, BaseAgent, ToolErrorPolicy
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig
from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.middleware import AgentMiddleware
from vidbyte.middleware.builtins import ModelRetryMiddleware, ToolErrorPolicyMiddleware, ToolPolicyMiddleware
from vidbyte.lib.dataclasses.context import BaseContext as StrategyContext
from vidbyte.tools import BaseTool, ToolCall, ToolPermission, ToolResult, ToolSpec, Tools, tool
from vidbyte.tools.security import PermissionPolicy


class FakeResponse:
    def __init__(self, text: str, raw: dict | None = None, metadata: dict | None = None) -> None:
        self.text = text
        self.raw = raw or {}
        self.metadata = metadata or {}


class FakeRunner:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []


async def invoke_runner(runner: FakeRunner, prompt: str, **kwargs: object) -> FakeResponse:
    runner.calls.append({"prompt": prompt, "kwargs": kwargs})
    response = runner.responses.pop(0)
    if isinstance(response, Exception):
        raise response
    return response


def runner_output_text(response: object) -> str:
    return str(getattr(response, "text", response))


def runner_output_metadata(response: object) -> dict:
    return dict(getattr(response, "metadata", {}))


class ExecutableTool(BaseTool):
    def __init__(self) -> None:
        self.executed = False

    def spec(self) -> ToolSpec:
        return ToolSpec(name="lookup", description="Lookup a value.")

    async def execute(self, call: ToolCall) -> ToolResult:
        self.executed = True
        return ToolResult.success("lookup", "found")


class FlakyTool(BaseTool):
    def __init__(self, *, permission: ToolPermission = ToolPermission.READ) -> None:
        self.executions = 0
        self.permission = permission

    def spec(self) -> ToolSpec:
        return ToolSpec(name="lookup", description="Lookup a value.", permission=self.permission)

    async def execute(self, call: ToolCall) -> ToolResult:
        self.executions += 1
        if self.executions == 1:
            return ToolResult.error("lookup", "temporary upstream error", metadata={"error": "upstream_error", "retryable": True})
        return ToolResult.success("lookup", "found after retry")


class AlwaysFailingTool(BaseTool):
    def __init__(self, *, permission: ToolPermission = ToolPermission.READ) -> None:
        self.executions = 0
        self.permission = permission

    def spec(self) -> ToolSpec:
        return ToolSpec(name="lookup", description="Lookup a value.", permission=self.permission)

    async def execute(self, call: ToolCall) -> ToolResult:
        self.executions += 1
        return ToolResult.error("lookup", "temporary upstream error", metadata={"error": "upstream_error", "retryable": True})


class AbortBeforeRunMiddleware(AgentMiddleware):
    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        del ctx
        return MiddlewareDecision.abort("blocked_before_run")


class HookRecorderMiddleware(AgentMiddleware):
    def __init__(self) -> None:
        self.hooks: list[str] = []
        self.internal_flags: list[bool] = []

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        self.hooks.append(ctx.hook.value)
        return MiddlewareDecision.continue_()

    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        self.hooks.append(ctx.hook.value)
        return MiddlewareDecision.continue_()

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        self.hooks.append(ctx.hook.value)
        return MiddlewareDecision.continue_()

    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        self.hooks.append(ctx.hook.value)
        return MiddlewareDecision.continue_()

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        self.hooks.append(ctx.hook.value)
        self.internal_flags.append(ctx.tool_is_internal)
        return MiddlewareDecision.continue_()

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        self.hooks.append(ctx.hook.value)
        return MiddlewareDecision.continue_()

    async def after_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        self.hooks.append(ctx.hook.value)
        return MiddlewareDecision.continue_()

    async def after_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        self.hooks.append(ctx.hook.value)
        return MiddlewareDecision.continue_()


class ExplodingMiddleware(AgentMiddleware):
    def __init__(self, *, fail_closed: bool = True) -> None:
        self.fail_closed = fail_closed

    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        del ctx
        raise RuntimeError("boom")


class AgentMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    def _runtime(self, *, tools: Tools | None = None, middleware: tuple[AgentMiddleware, ...] = (), permission_policy: PermissionPolicy | None = None) -> AgentRuntime:
        return AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=tools or Tools(),
            permission_policy=permission_policy or PermissionPolicy(),
            middleware=middleware,
        )

    def _context(self, runtime: AgentRuntime):
        return runtime.build_context(
            "task",
            base_context=StrategyContext(),
            history=(),
            agent_history=(),
            agent_metadata={},
            existing_tool_calls=(),
        )

    async def test_custom_middleware_can_abort_before_run(self) -> None:
        runner = FakeRunner([FakeResponse("unused")])
        runtime = self._runtime(middleware=(AbortBeforeRunMiddleware(),))

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=self._context(runtime),
            metadata={"tenant_id": "tenant-a"},
        )

        self.assertEqual(result.metadata["stop_reason"], "middleware_abort")
        self.assertEqual(result.metadata["middleware_abort_reason"], "blocked_before_run")
        self.assertEqual(len(runner.calls), 0)

    async def test_hook_order_for_successful_tool_loop(self) -> None:
        @tool
        def lookup() -> str:
            return "found"

        recorder = HookRecorderMiddleware()
        runner = FakeRunner(
            [
                FakeResponse("", {"output": [{"type": "function_call", "name": "lookup", "arguments": "{}"}]}),
                FakeResponse(
                    "",
                    {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}'}]},
                ),
            ]
        )
        runtime = self._runtime(tools=Tools([lookup]), middleware=(recorder,))

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=self._context(runtime),
        )

        self.assertEqual(result.output, "done")
        self.assertEqual(
            recorder.hooks,
            [
                "before_run",
                "before_iteration",
                "before_model_call",
                "after_model_response",
                "before_tool_call",
                "after_tool_call",
                "after_iteration",
                "before_iteration",
                "before_model_call",
                "after_model_response",
                "before_tool_call",
                "after_tool_call",
                "after_iteration",
                "after_run",
            ],
        )
        self.assertEqual(recorder.internal_flags, [False, True])

    async def test_custom_middleware_denies_tool_before_execution(self) -> None:
        tool_instance = ExecutableTool()
        runner = FakeRunner(
            [
                FakeResponse("", {"output": [{"type": "function_call", "name": "lookup", "arguments": "{}"}]}),
                FakeResponse(
                    "",
                    {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}'}]},
                ),
            ]
        )
        runtime = self._runtime(
            tools=Tools([tool_instance]),
            middleware=(ToolPolicyMiddleware(deny_tools={"lookup"}),),
        )

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=self._context(runtime),
        )

        self.assertFalse(tool_instance.executed)
        self.assertEqual(result.metadata["tool_call_states"], ("denied", "succeeded"))

    async def test_model_retry_middleware_retries_runner_exception(self) -> None:
        runner = FakeRunner(
            [
                RuntimeError("temporary"),
                FakeResponse(
                    "",
                    {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}'}]},
                ),
            ]
        )
        runtime = self._runtime(middleware=(ModelRetryMiddleware(max_attempts=2),))

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=self._context(runtime),
        )

        self.assertEqual(result.output, "done")
        self.assertEqual(len(runner.calls), 2)
        self.assertEqual(result.metadata["middleware"]["events"][0]["action"], "retry")

    async def test_tool_error_policy_retries_idempotent_transient_tool_error(self) -> None:
        flaky = FlakyTool(permission=ToolPermission.READ)
        runner = FakeRunner(
            [
                FakeResponse("", {"output": [{"type": "function_call", "name": "lookup", "arguments": "{}", "call_id": "fc_lookup"}]}),
                FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}', "call_id": "fc_done"}]}),
            ]
        )
        middleware = ToolErrorPolicyMiddleware(ToolErrorPolicy(max_retries_per_tool_call=1, retry_backoff_base_seconds=0))
        runtime = self._runtime(tools=Tools([flaky]), middleware=(middleware,))

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=self._context(runtime),
        )

        self.assertEqual(result.output, "done")
        self.assertEqual(flaky.executions, 2)
        self.assertEqual(result.metadata["tool_call_states"], ("succeeded", "succeeded"))
        self.assertEqual(result.metadata["middleware"]["events"][0]["reason"], "tool_error_retry")

    async def test_tool_error_policy_does_not_retry_write_tool_when_idempotency_gate_enabled(self) -> None:
        failing = AlwaysFailingTool(permission=ToolPermission.WRITE)
        runner = FakeRunner(
            [
                FakeResponse("", {"output": [{"type": "function_call", "name": "lookup", "arguments": "{}", "call_id": "fc_lookup"}]}),
                FakeResponse("", {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}', "call_id": "fc_done"}]}),
            ]
        )
        middleware = ToolErrorPolicyMiddleware(ToolErrorPolicy(max_retries_per_tool_call=1, retry_backoff_base_seconds=0))
        runtime = self._runtime(tools=Tools([failing]), middleware=(middleware,), permission_policy=PermissionPolicy.allow_all())

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=self._context(runtime),
        )

        self.assertEqual(result.output, "done")
        self.assertEqual(failing.executions, 1)
        self.assertEqual(result.metadata["tool_call_states"], ("failed", "succeeded"))

    async def test_tool_error_policy_circuit_breaker_aborts_after_total_errors(self) -> None:
        failing = AlwaysFailingTool(permission=ToolPermission.READ)
        runner = FakeRunner(
            [FakeResponse("", {"output": [{"type": "function_call", "name": "lookup", "arguments": "{}", "call_id": "fc_lookup"}]})]
        )
        middleware = ToolErrorPolicyMiddleware(ToolErrorPolicy(max_total_tool_errors=1))
        runtime = self._runtime(tools=Tools([failing]), middleware=(middleware,))

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=self._context(runtime),
        )

        self.assertEqual(result.metadata["stop_reason"], "middleware_abort")
        self.assertEqual(result.metadata["middleware_abort_reason"], "tool_error_circuit_break")
        self.assertEqual(failing.executions, 1)

    async def test_agent_loop_settings_auto_registers_tool_error_policy_middleware(self) -> None:
        agent = BaseAgent(
            name="worker",
            system_prompt="Work.",
            runner=object(),
            agent_loop_settings=AgentLoopSettings(tool_error_policy=ToolErrorPolicy(max_retries_per_tool_call=1)),
        )

        self.assertTrue(any(isinstance(item, ToolErrorPolicyMiddleware) for item in agent._runtime_middleware()))

    async def test_fail_closed_middleware_exception_aborts(self) -> None:
        runner = FakeRunner([FakeResponse("unused")])
        runtime = self._runtime(middleware=(ExplodingMiddleware(),))

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=self._context(runtime),
        )

        self.assertEqual(result.metadata["stop_reason"], "middleware_abort")
        self.assertEqual(result.metadata["middleware_abort_reason"], "middleware_error")

    async def test_fail_open_middleware_exception_continues(self) -> None:
        runner = FakeRunner(
            [
                FakeResponse(
                    "",
                    {"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}'}]},
                )
            ]
        )
        runtime = self._runtime(middleware=(ExplodingMiddleware(fail_closed=False),))

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=self._context(runtime),
        )

        self.assertEqual(result.output, "done")
        self.assertEqual(result.metadata["stop_reason"], "is_done")
        self.assertEqual(result.metadata["middleware"]["events"][0]["reason"], "middleware_error_fail_open")

    async def test_runtime_limit_still_stops_with_middleware_metadata(self) -> None:
        @tool
        def lookup() -> str:
            return "again"

        runtime = AgentRuntime(
            agent_name="worker",
            system_prompt="Work.",
            tools=Tools([lookup]),
            permission_policy=PermissionPolicy(),
            config=AgentRuntimeConfig(max_iterations=1),
            middleware=(HookRecorderMiddleware(),),
        )
        runner = FakeRunner(
            [FakeResponse("", {"output": [{"type": "function_call", "name": "lookup", "arguments": "{}"}]})]
        )

        result = await runtime.arun(
            "task",
            handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata),
            context=self._context(runtime),
        )

        self.assertEqual(result.metadata["stop_reason"], "max_iterations")
        self.assertIn("middleware", result.metadata)


if __name__ == "__main__":
    unittest.main()

