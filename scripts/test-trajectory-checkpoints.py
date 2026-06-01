"""Run the trajectory checkpoint design-doc verification cases."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.test_agent_runtime import AgentRuntimeTests
from tests.test_context_window_templates import TrajectoryCheckpointContextWindowTemplateTests
from tests.test_trajectory_checkpoint_algorithm import TrajectoryCheckpointAlgorithmTests
from vidbyte import ContextWindow, TrajectoryCheckpointAlgorithm


class PassFailResult(unittest.TextTestResult):
    def addSuccess(self, test: unittest.case.TestCase) -> None:
        # Prints a compact PASS line for each design-doc test case.
        super().addSuccess(test)
        print(f"[PASS] {test.id().split('.')[-1]}")

    def addFailure(self, test: unittest.case.TestCase, err: object) -> None:
        # Prints a compact FAIL line for assertion failures.
        super().addFailure(test, err)
        print(f"[FAIL] {test.id().split('.')[-1]}")

    def addError(self, test: unittest.case.TestCase, err: object) -> None:
        # Prints a compact FAIL line for unexpected errors.
        super().addError(test, err)
        print(f"[FAIL] {test.id().split('.')[-1]}")

    def addSkip(self, test: unittest.case.TestCase, reason: str) -> None:
        # Treats skips as explicit non-passing outcomes in the final summary.
        super().addSkip(test, reason)
        print(f"[FAIL] {test.id().split('.')[-1]} skipped: {reason}")


class PassFailRunner(unittest.TextTestRunner):
    resultclass = PassFailResult


def _named_test(test_class: type[unittest.TestCase], method_name: str) -> unittest.TestCase:
    # Creates one explicit test instance so the script mirrors the design plan.
    if not hasattr(test_class, method_name):
        raise AttributeError(f"{test_class.__name__}.{method_name} is missing.")
    return test_class(method_name)


def _build_suite() -> unittest.TestSuite:
    # Builds the exact Section 10 test suite for trajectory checkpoints.
    suite = unittest.TestSuite()
    for method_name in (
        "test_preset_exposes_trajectory_checkpoint_algorithm",
        "test_resolve_algorithm_accepts_trajectory_checkpoints_string",
        "test_config_rejects_zero_interval",
        "test_config_rejects_empty_checkpoint_title",
        "test_config_rejects_non_string_metadata_key",
        "test_context_window_algorithm_rejects_multiple_runtime_algorithms",
        "test_checkpoint_renderer_outputs_required_sections_in_order",
        "test_checkpoint_renderer_bounds_long_fields",
        "test_score_disabled_renders_na",
        "test_score_heuristic_penalizes_failed_tool_calls",
        "test_dispatcher_detects_and_returns_runtime_algorithm",
        "test_runtime_injects_checkpoint_after_interval",
        "test_runtime_does_not_inject_before_interval",
        "test_runtime_metadata_reports_zero_checkpoints_for_early_finish",
        "test_runtime_respects_max_checkpoints",
        "test_runtime_checkpoint_metadata_preserves_normal_metadata",
        "test_runtime_checkpoint_omits_raw_tool_output_by_default",
        "test_runtime_checkpoint_can_include_bounded_tool_output_when_enabled",
        "test_runtime_slots_match_template",
    ):
        suite.addTest(_named_test(TrajectoryCheckpointAlgorithmTests, method_name))
    for method_name in (
        "test_trajectory_template_zero_iterations",
        "test_trajectory_template_interval_two",
        "test_trajectory_template_respects_max_checkpoints",
    ):
        suite.addTest(_named_test(TrajectoryCheckpointContextWindowTemplateTests, method_name))
    for method_name in (
        "test_iteration_observer_default_none_preserves_existing_behavior",
        "test_iteration_observer_appends_returned_message",
        "test_iteration_observer_not_called_after_is_done",
    ):
        suite.addTest(_named_test(AgentRuntimeTests, method_name))
    return suite


def main() -> int:
    # Instantiates public SDK APIs directly, then runs the design-doc test cases.
    preset = ContextWindow.preset.trajectory_checkpoints
    assert preset.trajectory_checkpoints is not None
    TrajectoryCheckpointAlgorithm(interval=1, max_checkpoints=1)
    result = PassFailRunner(verbosity=0).run(_build_suite())
    passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    print(f"{passed}/{result.testsRun} tests passed")
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
