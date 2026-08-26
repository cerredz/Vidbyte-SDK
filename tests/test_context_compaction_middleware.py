from __future__ import annotations

import unittest

from vidbyte.agents import AgentRuntime
from vidbyte.context import ContextWindow
from vidbyte.context.compaction import CompactionMode, ContextCompactionEngine
from vidbyte.lib.dataclasses.context import BaseContext as StrategyContext, ContextMessage
from vidbyte.lib.dataclasses.middleware import MiddlewareAction, MiddlewareContext, MiddlewareDecision, MiddlewareHook, MiddlewareTransform
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.middleware import AgentMiddleware, MiddlewarePipeline
from vidbyte.middleware.builtins import MessageHistoryCompactionMiddleware, SummaryCompactionMiddleware, ToolResultCompactionMiddleware
from vidbyte.tools import ToolCall, ToolResult, Tools, tool
from vidbyte.tools.security import PermissionPolicy


class FakeResponse:
    def __init__(self, text: str = "", raw: dict | None = None) -> None:
        # Captures runner response text and raw tool-call payloads.
        self.text = text
        self.raw = raw or {}


class FakeRunner:
    def __init__(self, responses: list[FakeResponse]) -> None:
        # Stores queued fake responses and records runner invocation kwargs.
        self.responses = list(responses)
        self.calls: list[dict] = []


async def invoke_runner(runner: FakeRunner, prompt: str, **kwargs: object) -> FakeResponse:
    # Records one runner call and returns the next queued fake response.
    runner.calls.append({"prompt": prompt, "kwargs": kwargs})
    return runner.responses.pop(0)


def runner_output_text(response: object) -> str:
    # Extracts text from fake runner responses for AgentRuntime.
    return str(getattr(response, "text", response))


def runner_output_metadata(response: object) -> dict:
    # Extracts metadata from fake runner responses for AgentRuntime.
    return dict(getattr(response, "metadata", {}))


class FakeSummarizer:
    async def summarize(self, messages: tuple[ContextMessage, ...]) -> str:
        # Returns a deterministic summary that exposes the summarized count.
        return f"summarized {len(messages)} messages"


class TransformMiddleware(AgentMiddleware):
    def __init__(self, transform: MiddlewareTransform) -> None:
        # Stores the transform returned from before-model-call hooks.
        self.transform = transform

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Returns the stored transform without changing control flow.
        return MiddlewareDecision.continue_(transform=self.transform)


class ExplodingTransformMiddleware(AgentMiddleware):
    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Raises to exercise pipeline fail-open behavior for transform-capable hooks.
        raise RuntimeError("boom")


class ContextCompactionEngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_messages_remain_empty(self) -> None:
        # Verifies empty message history stays empty under keep-last compaction.
        engine = ContextCompactionEngine()
        messages, stats = await engine.compact_messages((), mode=CompactionMode.KEEP_LAST_N_MESSAGES, options={"n": 3})
        self.assertEqual(messages, ())
        self.assertEqual(stats.before_count, 0)
        self.assertEqual(stats.after_count, 0)

    async def test_remove_percentage_zero_removes_nothing(self) -> None:
        # Verifies zero-percent tool removal returns the original message tuple.
        engine = ContextCompactionEngine()
        before = (ContextMessage("tool", "a", kind="tool_result"), ContextMessage("assistant", "done"))
        after, stats = await engine.compact_messages(before, mode=CompactionMode.REMOVE_TOOL_CALL_PERCENTAGE, options={"percentage": 0})
        self.assertEqual(after, before)
        self.assertEqual(stats.removed_tool_messages, 0)

    async def test_truncate_tool_result_boundary_has_no_metadata(self) -> None:
        # Verifies exact-boundary tool results are not marked as compacted.
        engine = ContextCompactionEngine()
        result = ToolResult.success("lookup", "12345")
        visible, _ = engine.compact_tool_result(ToolCall("lookup"), result, mode=CompactionMode.TRUNCATE_TOOL_RESULTS, options={"max_chars": 5})
        self.assertEqual(visible.output, "12345")
        self.assertNotIn("compaction", visible.metadata)

    async def test_summary_requires_summarizer(self) -> None:
        # Verifies summary modes fail explicitly without an injected summarizer.
        engine = ContextCompactionEngine()
        with self.assertRaises(ValueError):
            await engine.compact_messages((ContextMessage("user", "a"),), mode=CompactionMode.SUMMARIZE_OLDEST_N, options={"n": 1})

    async def test_summary_uses_injected_summarizer(self) -> None:
        # Verifies summary modes delegate summary content to the injected summarizer.
        engine = ContextCompactionEngine(summarizer=FakeSummarizer())
        messages, _ = await engine.compact_messages((ContextMessage("user", "a"), ContextMessage("assistant", "b")), mode=CompactionMode.SUMMARIZE_OLDEST_N, options={"n": 1})
        self.assertEqual(messages[0].kind, "summary")
        self.assertEqual(messages[0].content, "summarized 1 messages")


class MiddlewareTransformTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_aggregates_transforms_with_later_values_winning(self) -> None:
        # Verifies pipeline transform merging preserves metadata and lets later values override.
        first = TransformMiddleware(MiddlewareTransform(provider_messages=({"role": "assistant", "content": "first"},), metadata={"a": 1}))
        second = TransformMiddleware(MiddlewareTransform(provider_messages=({"role": "assistant", "content": "second"},), system="sys", metadata={"b": 2}))
        decision = await MiddlewarePipeline((first, second)).before_model_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_MODEL_CALL, agent_name="worker"))
        self.assertEqual(decision.transform.system, "sys")
        self.assertEqual(tuple(decision.transform.provider_messages)[0]["content"], "second")
        self.assertEqual(decision.transform.metadata["a"], 1)
        self.assertEqual(decision.transform.metadata["b"], 2)

    async def test_transform_on_abort_is_rejected(self) -> None:
        # Verifies transforms cannot be attached to non-continue decisions.
        with self.assertRaises(ValueError):
            MiddlewareDecision(action=MiddlewareAction.ABORT_RUN, reason="stop", transform=MiddlewareTransform(system="bad"))

    async def test_fail_open_transform_exception_continues(self) -> None:
        # Verifies fail-open middleware exceptions still produce a continue decision.
        middleware = ExplodingTransformMiddleware()
        middleware.fail_closed = False
        decision = await MiddlewarePipeline((middleware,)).before_model_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_MODEL_CALL, agent_name="worker"))
        self.assertEqual(decision.action.value, "continue")

    async def test_pipeline_records_continue_hook_duration(self) -> None:
        # Verifies diagnostic invocation records retain ordinary continuations without expanding policy events.
        clock = iter((10.0, 10.025)).__next__
        pipeline = MiddlewarePipeline((TransformMiddleware(MiddlewareTransform(metadata={"rewritten": True})),), clock=clock)
        await pipeline.before_model_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_MODEL_CALL, agent_name="worker"))
        invocation = pipeline.hook_invocations[0]
        self.assertEqual(invocation.action, MiddlewareAction.CONTINUE)
        self.assertAlmostEqual(invocation.duration_seconds, 0.025)
        self.assertEqual(invocation.metadata, {})
        self.assertEqual(pipeline.events, ())

    async def test_pipeline_records_exception_type_without_error_text(self) -> None:
        # Verifies potentially sensitive exception text does not enter diagnostic hook metadata.
        middleware = ExplodingTransformMiddleware()
        middleware.fail_closed = False
        pipeline = MiddlewarePipeline((middleware,))
        await pipeline.before_model_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_MODEL_CALL, agent_name="worker"))
        invocation = pipeline.hook_invocations[0]
        self.assertEqual(invocation.error_type, "RuntimeError")
        self.assertEqual(invocation.reason, "middleware_error_fail_open")
        self.assertNotIn("error", invocation.metadata)


class CompactionMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_result_truncate_transforms_visible_result_only(self) -> None:
        # Verifies tool-result middleware transforms only the model-visible copy.
        middleware = ToolResultCompactionMiddleware.truncate(max_chars=5, truncation_indicator=" [truncated {count}]")
        raw = ToolResult.success("lookup", "1234567890")
        decision = await middleware.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="worker", tool_call=ToolCall("lookup"), tool_result=raw))
        self.assertEqual(decision.transform.model_visible_tool_result.output, "12345 [truncated 5]")
        self.assertEqual(raw.output, "1234567890")

    async def test_tool_result_compaction_skips_internal_tools(self) -> None:
        # Verifies internal runtime tools are skipped by default.
        middleware = ToolResultCompactionMiddleware.hide()
        decision = await middleware.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="worker", tool_call=ToolCall("isDone"), tool_result=ToolResult.success("isDone", "secret"), tool_is_internal=True))
        self.assertIsNone(decision.transform)

    async def test_message_history_keep_last_compacts_provider_messages(self) -> None:
        # Verifies before-model-call middleware rewrites provider message history.
        middleware = MessageHistoryCompactionMiddleware.keep_last(1)
        ctx = MiddlewareContext(hook=MiddlewareHook.BEFORE_MODEL_CALL, agent_name="worker", provider_messages=({"role": "assistant", "content": "old"}, {"role": "assistant", "content": "new"}))
        decision = await middleware.before_model_call(ctx)
        self.assertEqual(len(tuple(decision.transform.provider_messages)), 1)
        self.assertEqual(tuple(decision.transform.provider_messages)[0]["content"], "new")

    async def test_summary_middleware_requires_summarizer(self) -> None:
        # Verifies summary middleware requires explicit summarizer dependency injection.
        with self.assertRaises(ValueError):
            SummaryCompactionMiddleware(mode=CompactionMode.SUMMARIZE_OLDEST_N, summarizer=None)  # type: ignore[arg-type]


class RuntimeCompactionIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def _runtime(self, *, middleware: tuple[AgentMiddleware, ...] = (), algorithm=None) -> AgentRuntime:
        # Builds a runtime with one lookup tool and optional compaction settings.
        return AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools([self._lookup_tool()]), permission_policy=PermissionPolicy(), middleware=middleware, algorithm=algorithm)

    def _context(self, runtime: AgentRuntime):
        # Builds a minimal runtime context for integration tests.
        return runtime.build_context("task", base_context=StrategyContext(), history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())

    def _lookup_tool(self):
        # Returns a tool whose raw output should remain available in result metadata.
        @tool
        def lookup() -> str:
            # Provides deterministic raw content for visible-result compaction tests.
            return "raw secret result"
        return lookup

    async def test_runtime_truncates_model_visible_tool_result_but_keeps_raw_metadata(self) -> None:
        # Verifies runtime middleware changes provider messages without mutating raw metadata.
        runner = FakeRunner([FakeResponse(raw={"output": [{"type": "function_call", "name": "lookup", "arguments": "{}"}]}), FakeResponse(raw={"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}'}]})])
        runtime = self._runtime(middleware=(ToolResultCompactionMiddleware.truncate(max_chars=3),))
        result = await runtime.arun("task", handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata), context=self._context(runtime))
        visible = runner.calls[1]["kwargs"]["messages"][0]["content"]
        self.assertIn("raw", visible)
        self.assertNotIn("secret result", visible)
        self.assertEqual(result.metadata["tool_calls"][0].result.output, "raw secret result")

    async def test_context_window_no_raw_outputs_uses_compatibility_middleware(self) -> None:
        # Verifies legacy context-window presets still hide model-visible raw outputs.
        runner = FakeRunner([FakeResponse(raw={"output": [{"type": "function_call", "name": "lookup", "arguments": "{}"}]}), FakeResponse(raw={"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}'}]})])
        runtime = self._runtime(algorithm=ContextWindow.preset.no_raw_tool_outputs)
        result = await runtime.arun("task", handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata), context=self._context(runtime))
        visible = runner.calls[1]["kwargs"]["messages"][0]["content"]
        self.assertNotIn("raw secret result", visible)
        self.assertIn("Raw tool output was withheld", visible)
        self.assertEqual(result.metadata["tool_calls"][0].result.output, "raw secret result")


if __name__ == "__main__":
    unittest.main()
