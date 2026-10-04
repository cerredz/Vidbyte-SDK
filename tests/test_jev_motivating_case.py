"""FILE: tests/test_jev_motivating_case.py

PURPOSE: Verifies the motivating-case done check's public setting, request-derived scenario record, and blocking policy without provider calls.
ROLE IN CODEBASE: Exercises the request-state and handoff records used by JevRunState and JevHandoff before the main continuation checks user-named boundary scenarios.
ARCHITECTURE NOTE: The tests use production settings, registries, schemas, and immutable records while avoiding live model calls; runtime batching and continuation behavior are also pinned in tests/test_jev_done.py.
COMMON MODIFICATION PATTERNS: Add cases for request-named boundary metadata, scenario role, exercise mode, registry identity, and checks that implied scenarios do not block.
KNOWN EDGE CASES: Only user-motivating or explicitly requested scenarios block; implied scenarios remain available for context, and literal request evidence must stay attached to its scenario.
RELATED DOCS: docs/design/jev-motivating-case.md, skills/jev-agent/SKILL.md, skills/jev-continuation/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: python -m pytest tests/test_jev_motivating_case.py tests/test_jev_done.py.
"""

from __future__ import annotations

import unittest

from vidbyte.agents.jev.done.handoff import JevHandoff
from vidbyte.agents.jev.done.run_state import JevRunState
from vidbyte.agents.jev.settings import JevContinuationGateSettings
from vidbyte.lib.constants.jev import JEV_MOTIVATING_CASE_THRESHOLD
from vidbyte.lib.dataclasses.jev import (
    JevMotivatingCase,
    JevMotivatingScenario,
)
from vidbyte.lib.enums.jev import (
    JevBoundaryKind,
    JevContinuationGate,
    JevExerciseMode,
    JevScenarioRole,
)
from vidbyte.lib.jev import JevDoneRegistry


class MotivatingCaseContinuationGateTests(unittest.TestCase):
    """Pin the public continuation setting and the shared state/handoff schemas."""

    def test_check_is_registered_and_enabled_through_continual_settings(self) -> None:
        continual = JevContinuationGateSettings(enabled=(JevContinuationGate.MOTIVATING_CASE,))
        self.assertEqual(continual.enabled, (JevContinuationGate.MOTIVATING_CASE,))
        self.assertEqual(JevDoneRegistry.threshold(JevContinuationGate.MOTIVATING_CASE), JEV_MOTIVATING_CASE_THRESHOLD)
        self.assertEqual(JevDoneRegistry.question(JevContinuationGate.MOTIVATING_CASE).key.value, "motivating_case.exercised")

    def test_request_and_handoff_sections_join_by_scenario_id(self) -> None:
        self.assertIn(JevContinuationGate.MOTIVATING_CASE.value, JevRunState.schema((JevContinuationGate.MOTIVATING_CASE,)).model_fields)
        self.assertIn(JevContinuationGate.MOTIVATING_CASE.value, JevHandoff.schema((JevContinuationGate.MOTIVATING_CASE,)).model_fields)
        self.assertNotIn(JevContinuationGate.MOTIVATING_CASE.value, JevRunState.schema(()).model_fields)
        self.assertNotIn(JevContinuationGate.MOTIVATING_CASE.value, JevHandoff.schema(()).model_fields)

    def test_scenario_record_preserves_request_derived_boundary_definition(self) -> None:
        scenario = JevMotivatingScenario(
            id="empty_input",
            role=JevScenarioRole.MOTIVATING,
            kind=JevBoundaryKind.EMPTY_OR_MISSING,
            source_quote="empty input",
            target="the parser",
            condition="an empty list is passed to the parser",
            near_miss="a one-row list is passed to the parser",
            expected_behavior="return an empty result",
            literal_inputs=("[]",),
            exercise_mode=JevExerciseMode.RUN,
        )
        state = JevMotivatingCase(ordinary_flow="a list containing records", testing_restriction_quote=None, scenarios=(scenario,))
        self.assertEqual(state.ids(blocking_only=True), ("empty_input",))
        self.assertTrue(scenario.blocks_finish())

    def test_implied_scenarios_do_not_block(self) -> None:
        scenario = JevMotivatingScenario(
            id="other_failure",
            role=JevScenarioRole.IMPLIED,
            kind=JevBoundaryKind.FAILURE_PATH,
            source_quote="retry",
            target="the parser",
            condition="a retry occurs after a failure",
            near_miss="the first attempt succeeds",
            expected_behavior=None,
            literal_inputs=(),
            exercise_mode=JevExerciseMode.RUN_OR_INSPECT,
        )
        state = JevMotivatingCase(ordinary_flow="a successful first attempt", testing_restriction_quote=None, scenarios=(scenario,))
        self.assertEqual(state.ids(blocking_only=True), ())


if __name__ == "__main__":
    unittest.main()
