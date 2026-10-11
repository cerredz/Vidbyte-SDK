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


def _sequential_tool_history() -> tuple[dict, ...]:
    # Returns an OpenAI-chat tool loop of four sequential single tool calls.
    history: list[dict] = [{"role": "system", "content": "sys"}, {"role": "user", "content": "go"}]
    for index in range(1, 5):
        history.append({"role": "assistant", "content": None, "tool_calls": [{"id": f"c{index}", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}]})
        history.append({"role": "tool", "tool_call_id": f"c{index}", "content": f"r{index}"})
    return tuple(history)


def _parallel_tool_history() -> tuple[dict, ...]:
    # Returns an OpenAI-chat tool loop whose turns issue parallel calls.
    def call(*ids: str) -> dict:
        return {"role": "assistant", "content": None, "tool_calls": [{"id": i, "type": "function", "function": {"name": "lookup", "arguments": "{}"}} for i in ids]}

    def result(call_id: str) -> dict:
        return {"role": "tool", "tool_call_id": call_id, "content": call_id}

    return ({"role": "system", "content": "sys"}, {"role": "user", "content": "go"}, call("c1", "c2"), result("c1"), result("c2"), call("c3", "c4", "c5"), result("c3"), result("c4"), result("c5"), call("c6"), result("c6"))


def _assert_valid_tool_transcript(test: unittest.TestCase, messages: tuple[dict, ...]) -> None:
    # Asserts every tool reply follows its call turn and every issued tool_call id is answered.
    pending: set[str] = set()
    for message in messages:
        if message["role"] == "tool":
            test.assertIn(message["tool_call_id"], pending, f"orphaned tool result: {message}")
            pending.discard(str(message["tool_call_id"]))
            continue
        test.assertEqual(pending, set(), f"unanswered tool_call ids before {message}")
        pending = {str(call["id"]) for call in message.get("tool_calls") or ()}
    test.assertEqual(pending, set(), "unanswered tool_call ids at end of transcript")


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

    async def test_summary_modes_never_split_tool_call_groups(self) -> None:
        # [Hidden Failure] Summary splits keep whole call/result groups so providers never see orphaned tool results.
        engine = ContextCompactionEngine(summarizer=FakeSummarizer())
        cases = ((CompactionMode.SUMMARIZE_RANGE, "keep_last"), (CompactionMode.SUMMARIZE_OLDEST_N, "n"))
        for history in (_sequential_tool_history(), _parallel_tool_history()):
            for mode, option in cases:
                for value in range(1, 5):
                    with self.subTest(mode=mode, option=value, size=len(history)):
                        after, _ = await engine.compact_provider_messages(history, mode=mode, options={option: value})
                        _assert_valid_tool_transcript(self, after)
                        self.assertEqual(after[0]["role"], "system")
                        self.assertTrue(any(str(m.get("content") or "").startswith("summarized") for m in after if m["role"] != "tool"))

    async def test_summarize_range_keeps_at_least_keep_last_whole_messages(self) -> None:
        # Verifies keep_last rounds up to the newest whole group rather than splitting it.
        engine = ContextCompactionEngine(summarizer=FakeSummarizer())
        after, _ = await engine.compact_provider_messages(_sequential_tool_history(), mode=CompactionMode.SUMMARIZE_RANGE, options={"keep_last": 3})
        self.assertEqual([m.get("tool_call_id") for m in after if m["role"] == "tool"], ["c3", "c4"])
        self.assertEqual(after[1]["content"], "summarized 5 messages")


    async def test_selection_strategies_never_emit_broken_tool_pairing(self) -> None:
        # [Hidden Failure] Message-selecting strategies must not leave orphaned tool results or unanswered tool_call ids.
        engine = ContextCompactionEngine()
        cases = [(CompactionMode.KEEP_LAST_N_MESSAGES, {"n": n}) for n in range(1, 8)]
        cases += [(CompactionMode.TRIM_TO_TOKEN_BUDGET, {"max_tokens": t}) for t in range(1, 40, 3)]
        cases += [(CompactionMode.REMOVE_LAST_N_TOOL_CALLS, {"n": n}) for n in range(1, 5)]
        for history in (_sequential_tool_history(), _parallel_tool_history()):
            for mode, options in cases:
                with self.subTest(mode=mode, options=options, size=len(history)):
                    after, stats = await engine.compact_provider_messages(history, mode=mode, options=options)
                    _assert_valid_tool_transcript(self, after)
                    self.assertEqual(stats.after_count, len(after))

    async def test_message_history_middleware_repairs_keep_last_tool_pairing(self) -> None:
        # Verifies the middleware hands the provider a valid transcript when keep_last cuts through a parallel call turn.
        middleware = MessageHistoryCompactionMiddleware.keep_last(3)
        decision = await middleware.before_model_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_MODEL_CALL, agent_name="worker", provider_messages=_parallel_tool_history()))
        _assert_valid_tool_transcript(self, decision.transform.provider_messages)
        self.assertEqual([m.get("tool_call_id") for m in decision.transform.provider_messages], [None, None, "c6"])

    async def test_tool_pairing_repair_leaves_valid_transcripts_unchanged(self) -> None:
        # Verifies the repair keeps every message of already-valid OpenAI, Anthropic, and Gemini tool transcripts.
        anthropic = ({"role": "user", "content": "go"}, {"role": "assistant", "content": [{"type": "text", "text": "x"}, {"type": "tool_use", "id": "t1", "name": "lookup", "input": {}}]}, {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "r1"}]}, {"role": "assistant", "content": "done", "tool_calls": None})
        gemini = ({"role": "user", "parts": [{"text": "go"}]}, {"role": "model", "parts": [{"functionCall": {"name": "lookup", "args": {}}}]}, {"role": "user", "parts": [{"functionResponse": {"name": "lookup", "response": {"output": "r1"}}}]})
        engine = ContextCompactionEngine()
        for history in (_sequential_tool_history(), _parallel_tool_history(), anthropic, gemini):
            with self.subTest(size=len(history)):
                after, _ = await engine.compact_provider_messages(history, mode=CompactionMode.KEEP_LAST_N_MESSAGES, options={"n": 100})
                self.assertEqual([(m["role"], m.get("tool_call_id")) for m in after], [(m["role"], m.get("tool_call_id")) for m in history])


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

    async def test_pipeline_composes_stacked_compaction_transforms(self) -> None:
        # Verifies each stacked middleware transforms the previous one's output, so no earlier effect is lost.
        messages = (
            {"role": "user", "content": "start"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "a", "content": "old output"},
            {"role": "assistant", "content": "mid", "tool_calls": [{"id": "b", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "b", "content": "new output"},
        )
        history = MiddlewarePipeline((MessageHistoryCompactionMiddleware.keep_last(2), MessageHistoryCompactionMiddleware.clear_tool_results_except()))
        decision = await history.before_model_call(MiddlewareContext(hook=MiddlewareHook.BEFORE_MODEL_CALL, agent_name="worker", provider_messages=messages))
        self.assertEqual([message["content"] for message in decision.transform.provider_messages], ["mid", "[tool result cleared by compaction]"])

        raw = ToolResult.success("lookup", "\x1b[31mred\x1b[0m " + "word " * 50)
        tools = MiddlewarePipeline((ToolResultCompactionMiddleware.scrub_bloat(), ToolResultCompactionMiddleware.truncate(max_chars=20)))
        decision = await tools.after_tool_call(MiddlewareContext(hook=MiddlewareHook.AFTER_TOOL_CALL, agent_name="worker", tool_call=ToolCall("lookup"), tool_result=raw))
        visible = decision.transform.model_visible_tool_result
        self.assertTrue(visible.output.startswith("red word"))
        self.assertNotIn("\x1b", visible.output)
        self.assertIn("[tool output compacted]", visible.output)
        self.assertEqual(visible.status, raw.status)

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
        visible = runner.calls[1]["kwargs"]["messages"][-1]["content"]
        self.assertIn("raw", visible)
        self.assertNotIn("secret result", visible)
        self.assertEqual(result.metadata["tool_calls"][0].result.output, "raw secret result")

    async def test_context_window_no_raw_outputs_uses_compatibility_middleware(self) -> None:
        # Verifies legacy context-window presets still hide model-visible raw outputs.
        runner = FakeRunner([FakeResponse(raw={"output": [{"type": "function_call", "name": "lookup", "arguments": "{}"}]}), FakeResponse(raw={"output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}'}]})])
        runtime = self._runtime(algorithm=ContextWindow.preset.no_raw_tool_outputs)
        result = await runtime.arun("task", handle=RunnerHandle(runner=runner, provider="openai", invoke=invoke_runner, extract_text=runner_output_text, extract_metadata=runner_output_metadata), context=self._context(runtime))
        visible = runner.calls[1]["kwargs"]["messages"][-1]["content"]
        self.assertNotIn("raw secret result", visible)
        self.assertIn("Raw tool output was withheld", visible)
        self.assertEqual(result.metadata["tool_calls"][0].result.output, "raw secret result")


if __name__ == "__main__":
    unittest.main()
