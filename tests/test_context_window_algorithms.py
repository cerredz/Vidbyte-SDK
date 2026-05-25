from __future__ import annotations

import unittest

from vidbyte.context.algorithms import (
    ContextWindowAlgorithm,
    PlanThenImplementConfig,
    ReasoningTraceConfig,
    ReasoningTraceSize,
    ToolResultAdmission,
    build_plan_prompt,
    fallback_plan,
    plan_artifact_from_text,
    render_reasoning_trace,
)
from vidbyte.context.algorithms.types import (
    ContextWindowIterationEvent,
    ContextWindowMessage,
)


class ContextWindowAlgorithmConfigTests(unittest.TestCase):
    def test_context_window_algorithm_defaults_still_valid(self) -> None:
        algo = ContextWindowAlgorithm(name="test")
        self.assertEqual(algo.name, "test")
        self.assertEqual(algo.tool_result_admission, ToolResultAdmission.RAW)
        self.assertIsNone(algo.reasoning_trace)
        self.assertIsNone(algo.plan_then_implement)

    def test_context_window_algorithm_with_reasoning_trace(self) -> None:
        algo = ContextWindowAlgorithm(
            name="trace",
            reasoning_trace=ReasoningTraceConfig(size=ReasoningTraceSize.LARGE),
        )
        self.assertIsNotNone(algo.reasoning_trace)
        self.assertEqual(algo.reasoning_trace.size, ReasoningTraceSize.LARGE)

    def test_context_window_algorithm_with_plan_then_implement(self) -> None:
        algo = ContextWindowAlgorithm(
            name="plan",
            plan_then_implement=PlanThenImplementConfig(artifact_name="Strategy"),
        )
        self.assertIsNotNone(algo.plan_then_implement)
        self.assertEqual(algo.plan_then_implement.artifact_name, "Strategy")

    def test_reasoning_trace_config_defaults(self) -> None:
        config = ReasoningTraceConfig()
        self.assertEqual(config.size, ReasoningTraceSize.MEDIUM)
        self.assertIsNone(config.system_prompt)
        self.assertEqual(config.role, "user")

    def test_plan_then_implement_config_defaults(self) -> None:
        config = PlanThenImplementConfig()
        self.assertEqual(config.artifact_name, "Plan")
        self.assertEqual(config.max_plan_chars, 4000)
        self.assertTrue(config.fallback_on_empty)


class ReasoningTraceRenderingTests(unittest.TestCase):
    def test_reasoning_trace_small_renders_bounded_operational_note(self) -> None:
        config = ReasoningTraceConfig(size=ReasoningTraceSize.SMALL)
        event = ContextWindowIterationEvent(
            request="Fix the build.",
            iteration_count=1,
            assistant_output="I looked at the config.",
        )
        result = render_reasoning_trace(config, event)
        self.assertIsInstance(result, ContextWindowMessage)
        self.assertEqual(result.role, "user")
        self.assertIn("Context window reasoning trace", result.content)
        self.assertIn("Iteration: 1", result.content)
        self.assertIn("Request:", result.content)
        self.assertIn("Fix the build.", result.content)
        self.assertIn("last assistant output", result.content.lower())
        self.assertIn("Next action:", result.content)
        self.assertIn("Finish check:", result.content)
        self.assertNotIn("Constraints:", result.content)
        self.assertNotIn("Alternate routes:", result.content)

    def test_reasoning_trace_large_includes_routes_risks_and_finish_criteria(self) -> None:
        config = ReasoningTraceConfig(size=ReasoningTraceSize.LARGE)
        event = ContextWindowIterationEvent(
            request="Audit repository.",
            iteration_count=2,
        )
        result = render_reasoning_trace(config, event)
        self.assertIn("Alternate routes:", result.content)
        self.assertIn("Risk check:", result.content)
        self.assertIn("Validation check:", result.content)
        self.assertIn("Route tradeoffs:", result.content)

    def test_reasoning_trace_does_not_include_tool_result_output(self) -> None:
        from vidbyte.tools.types import ToolCall, ToolCallContext, ToolCallState, ToolResult

        ctx = ToolCallContext(
            tool_name="lookup",
            arguments={"q": "classified"},
            state=ToolCallState.SUCCEEDED,
            result=ToolResult.success("lookup", "top secret value"),
        )
        config = ReasoningTraceConfig(size=ReasoningTraceSize.MEDIUM)
        event = ContextWindowIterationEvent(
            request="Lookup information.",
            iteration_count=1,
            tool_contexts=(ctx,),
        )
        result = render_reasoning_trace(config, event)
        self.assertIn("lookup", result.content)
        self.assertNotIn("top secret", result.content)

    def test_reasoning_trace_with_no_assistant_output(self) -> None:
        config = ReasoningTraceConfig(size=ReasoningTraceSize.SMALL)
        event = ContextWindowIterationEvent(
            request="Continue.",
            iteration_count=3,
        )
        result = render_reasoning_trace(config, event)
        self.assertNotIn("Last assistant output", result.content)

    def test_reasoning_trace_with_failed_tool(self) -> None:
        from vidbyte.tools.types import ToolCall, ToolCallContext, ToolCallState, ToolResult

        ctx = ToolCallContext(
            tool_name="write",
            arguments={},
            state=ToolCallState.FAILED,
            result=ToolResult.error("write", "permission denied", metadata={"error": "permission_denied"}),
        )
        config = ReasoningTraceConfig(size=ReasoningTraceSize.SMALL)
        event = ContextWindowIterationEvent(
            request="Write file.",
            iteration_count=2,
            tool_contexts=(ctx,),
        )
        result = render_reasoning_trace(config, event)
        self.assertIn("write", result.content)
        self.assertIn("failed", result.content)
        self.assertNotIn("permission denie", result.content)


class PlanThenImplementTests(unittest.TestCase):
    def test_plan_artifact_bounds_long_plan_text(self) -> None:
        config = PlanThenImplementConfig(max_plan_chars=50)
        long_text = "A" * 200
        artifact = plan_artifact_from_text(long_text, "request", config)
        self.assertIn("[plan text bounded]", artifact.content)
        self.assertTrue(len(artifact.content) <= 50 + len("\n...[plan text bounded]"))
        self.assertEqual(artifact.artifact_type, "plan")

    def test_plan_artifact_from_short_text_no_bounding(self) -> None:
        config = PlanThenImplementConfig(max_plan_chars=4000)
        short_text = "A short plan."
        artifact = plan_artifact_from_text(short_text, "request", config)
        self.assertEqual(artifact.content, short_text)
        self.assertNotIn("bounded", artifact.content)

    def test_plan_artifact_no_truncation_when_zero(self) -> None:
        config = PlanThenImplementConfig(max_plan_chars=0)
        long_text = "A" * 200
        artifact = plan_artifact_from_text(long_text, "request", config)
        self.assertEqual(artifact.content, long_text)

    def test_plan_fallback_is_deterministic(self) -> None:
        plan_a = fallback_plan("Fix the tests.")
        plan_b = fallback_plan("Fix the tests.")
        self.assertEqual(plan_a, plan_b)
        self.assertIn("Fix the tests.", plan_a)
        self.assertIn("Objective:", plan_a)
        self.assertIn("Steps:", plan_a)
        self.assertIn("Risks:", plan_a)
        self.assertIn("Verification:", plan_a)

    def test_build_plan_prompt_uses_default_when_none(self) -> None:
        config = PlanThenImplementConfig()
        prompt = build_plan_prompt("Do the task.", "", config)
        self.assertIn("Create a concise implementation plan", prompt)
        self.assertIn("Do the task.", prompt)

    def test_build_plan_prompt_uses_custom_when_provided(self) -> None:
        config = PlanThenImplementConfig(planner_prompt="Custom plan format.")
        prompt = build_plan_prompt("Build.", "context info", config)
        self.assertIn("Custom plan format.", prompt)
        self.assertIn("Build.", prompt)
        self.assertIn("context info", prompt)

    def test_plan_artifact_metadata_includes_plan_request(self) -> None:
        config = PlanThenImplementConfig()
        artifact = plan_artifact_from_text("plan content", "test request", config)
        self.assertEqual(artifact.metadata["plan_request"], "test request")


if __name__ == "__main__":
    unittest.main()
