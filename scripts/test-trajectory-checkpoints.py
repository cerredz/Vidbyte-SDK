"""Run the trajectory checkpoint inner-loop context-window verification cases."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.test_context_primitives_registry import RenderPrimitivesZoneTests
from tests.test_context_primitives_binding import PrimitiveBindingTests
from tests.test_context_window_templates import TrajectoryCheckpointContextWindowTemplateTests
from tests.test_inner_context_window_algorithms import ContextWindowRunContextTests
from tests.test_agent_runtime import AgentRuntimeTests
from tests.test_trajectory_checkpoint_algorithm import TrajectoryCheckpointAlgorithmTests
from vidbyte import ContextWindow, TrajectoryCheckpointAlgorithm


class PassFailResult(unittest.TextTestResult):
    def addSuccess(self, test: unittest.case.TestCase) -> None:
        # Prints a compact PASS line for each explicit verification case.
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
        # Treats skipped design cases as explicit non-passing outcomes.
        super().addSkip(test, reason)
        print(f"[FAIL] {test.id().split('.')[-1]} skipped: {reason}")


class PassFailRunner(unittest.TextTestRunner):
    resultclass = PassFailResult


def _named_test(test_class: type[unittest.TestCase], method_name: str) -> unittest.TestCase:
    # Creates one named test instance and fails fast when the method is missing.
    if not hasattr(test_class, method_name):
        raise AttributeError(f"{test_class.__name__}.{method_name} is missing.")
    return test_class(method_name)


def _build_suite() -> unittest.TestSuite:
    # Builds the exact verification suite for trajectory checkpoint inner-loop context.
    suite = unittest.TestSuite()
    for method_name in (
        "test_place_after_tools_writes_to_context_manager",
        "test_place_after_system_prompt_sets_top_placement",
        "test_place_generates_stable_primitive_id",
        "test_run_context_remove_deletes_primitive",
        "test_run_context_record_delegates_to_recorder",
        "test_run_context_set_metadata_preserves_existing_keys",
        "test_inner_algorithm_default_hook_is_noop",
    ):
        suite.addTest(_named_test(ContextWindowRunContextTests, method_name))
    for method_name in (
        "test_upsert_default_placement_matches_existing_rendering",
        "test_top_of_context_renders_before_end_of_context",
        "test_replacing_primitive_updates_placement",
        "test_remove_by_id_removes_placement_metadata",
        "test_conversation_placement_does_not_render_in_primitives_zone",
        "test_conversation_messages_render_in_placement_order",
    ):
        suite.addTest(_named_test(RenderPrimitivesZoneTests, method_name))
    suite.addTest(_named_test(PrimitiveBindingTests, "test_bound_tool_binding_uses_default_context_placement"))
    suite.addTest(_named_test(AgentRuntimeTests, "test_inner_context_window_lifecycle_writes_to_next_system_context"))
    for method_name in (
        "test_preset_exposes_trajectory_checkpoint_algorithm",
        "test_resolve_algorithm_accepts_trajectory_checkpoints_string",
        "test_config_rejects_zero_interval",
        "test_config_rejects_empty_checkpoint_title",
        "test_config_rejects_non_string_metadata_key",
        "test_context_window_algorithm_rejects_multiple_runtime_algorithms",
        "test_checkpoint_item_outputs_required_sections_in_order",
        "test_checkpoint_item_bounds_rendered_text",
        "test_score_disabled_renders_na",
        "test_score_heuristic_penalizes_failed_tool_calls",
        "test_dispatcher_detects_inner_loop_algorithm",
        "test_runtime_writes_checkpoint_primitive_after_interval",
        "test_runtime_does_not_write_checkpoint_before_interval",
        "test_runtime_metadata_reports_zero_checkpoints_for_early_finish",
        "test_runtime_respects_max_checkpoints",
        "test_runtime_checkpoint_metadata_preserves_normal_metadata",
        "test_runtime_checkpoint_omits_raw_tool_output_by_default",
        "test_runtime_checkpoint_can_include_bounded_tool_output_when_enabled",
        "test_runtime_slots_match_template",
        "test_inner_context_window_private_manager_created_when_missing",
        "test_context_window_conversation_top_placement_visible_before_existing_messages",
        "test_after_tool_calls_hook_receives_tool_results",
    ):
        suite.addTest(_named_test(TrajectoryCheckpointAlgorithmTests, method_name))
    for method_name in (
        "test_trajectory_template_zero_iterations",
        "test_trajectory_template_interval_two",
        "test_trajectory_template_respects_max_checkpoints",
    ):
        suite.addTest(_named_test(TrajectoryCheckpointContextWindowTemplateTests, method_name))
    return suite


def main() -> int:
    # Instantiates public SDK APIs directly and runs every explicit verification case.
    preset = ContextWindow.preset.trajectory_checkpoints
    assert preset.trajectory_checkpoints is not None
    TrajectoryCheckpointAlgorithm(interval=1, max_checkpoints=1)
    result = PassFailRunner(verbosity=0).run(_build_suite())
    passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    print(f"{passed}/{result.testsRun} tests passed")
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
