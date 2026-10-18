"""FILE: tests/features/codex_host/test_codex_host_feature_constants.py

PURPOSE: Pins every fixed value the first-class-features spec adds: the section 9.2 message, cause and next-step texts and the side-chat texts, the section 9.3 numbers, method names, method sets, the stream notification table, the goal status sets, the changed rejected-field rows, the git values and GitFlag, the export of the ten new enums, and the place of the twenty-five new CodexHostOperation members.
ROLE IN CODEBASE: Constants layer of the slice-2 tests in tests/features/codex_host/ (docs/spec/codex-host-first-class/spec.md sections 8.5, 9.2 and 9.3, D-13, D-28, D-29, INV-10, INV-18, INV-46, INV-50). Nothing here needs openai-codex, so these tests also run on CI.
ARCHITECTURE NOTE: The expected values are the spec's literals from codex_host_feature_support.py; each production module is imported inside the test that reads it, so a constant the feature has not added yet fails that test alone.
COMMON MODIFICATION PATTERNS: When the spec changes a text or a table, change the literal in codex_host_feature_support.py; the tables here pick it up by name.
KNOWN EDGE CASES: Section 9.3 (r4) names all fifteen new method-name constants, so each is pinned by its name, its wire string, its place in __all__ and its absence from vidbyte.lib.constants.codex. The pause, resume and edit message is CODEX_HOST_NO_STORED_GOAL_MESSAGE in r4, because CODEX_HOST_NO_GOAL_MESSAGE keeps the thread-helpers text pinned at test_codex_host_helper_surface.py:94; its text is pinned through pause_codex_goal's behaviour in test_codex_host_goal_control.py, and its cause and next step keep the NO_GOAL names pinned here.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-first-class/spec.md sections 8.5, 9.2, 9.3 and 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_feature_constants.py
"""

from __future__ import annotations

import asyncio
import dataclasses
import enum
import importlib
import operator
import unittest
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from tests.features.codex_host import codex_host_feature_support as spec
from tests.features.codex_host.codex_host_support import GOAL_REJECTED_FIELDS

# Section 9.2 "Messages" and section 9.3 "The side-chat texts": every new constant of vidbyte.lib.constants.codex_host
# that holds a text, by its spec name, mapped to the support literal of the same name without the CODEX_HOST_ prefix.
TEXT_NAMES = (
    "EXPERIMENTAL_FEATURE_MESSAGE",
    "MODE_KIND_MESSAGE",
    "MODE_CONFLICT_MESSAGE",
    "SETTINGS_MODE_MODEL_MESSAGE",
    "SETTINGS_EMPTY_MESSAGE",
    "TIER_CLEAR_CONFLICT_MESSAGE",
    "SETTINGS_NETWORK_ACCESS_MESSAGE",
    "SETTINGS_WRITABLE_ROOTS_MESSAGE",
    "WAIT_HANDLES_MESSAGE",
    "INJECT_ITEMS_MESSAGE",
    "GOAL_EDIT_EMPTY_MESSAGE",
    "BUDGET_CLEAR_CONFLICT_MESSAGE",
    "WORKTREE_REPOSITORY_MESSAGE",
    "WORKTREE_REF_MESSAGE",
    "NO_PLAN_MODE_MESSAGE",
    "MODE_MODEL_MISSING_MESSAGE",
    "MODE_MODEL_MISSING_CAUSE",
    "MODE_MODEL_MISSING_NEXT_STEP",
    "TURN_SETTINGS_FINISHED_MESSAGE",
    "NO_GOAL_CAUSE",
    "NO_GOAL_NEXT_STEP",
    "GOAL_NOT_RESUMABLE_MESSAGE",
    "GOAL_NOT_RESUMABLE_CAUSE",
    "GOAL_NOT_RESUMABLE_NEXT_STEP",
    "GOAL_BUDGET_SPENT_MESSAGE",
    "GOAL_BUDGET_SPENT_CAUSE",
    "GOAL_BUDGET_SPENT_NEXT_STEP",
    "THREAD_RUNNING_MESSAGE",
    "LOAD_GOAL_UNFINISHED_MESSAGE",
    "LOAD_GOAL_UNFINISHED_CAUSE",
    "LOAD_GOAL_UNFINISHED_NEXT_STEP",
    "WORKTREE_EXISTS_MESSAGE",
    "WORKTREE_EXISTS_CAUSE",
    "WORKTREE_EXISTS_NEXT_STEP",
    "WORKTREE_GIT_MISSING_MESSAGE",
    "WORKTREE_GIT_MISSING_CAUSE",
    "WORKTREE_GIT_MISSING_NEXT_STEP",
    "WORKTREE_TIMED_OUT_MESSAGE",
    "WORKTREE_TIMED_OUT_CAUSE",
    "WORKTREE_TIMED_OUT_NEXT_STEP",
    "WORKTREE_FAILED_MESSAGE",
    "WORKTREE_FAILED_CAUSE",
    "WORKTREE_FAILED_NEXT_STEP",
    "SIDE_CHAT_INSTRUCTIONS",
    "SIDE_CHAT_BOUNDARY",
)
# Section 9.3: the set and table constants of vidbyte.lib.constants.codex_host this slice adds.
SET_NAMES = (
    "CODEX_HOST_UNMODELED_RAW_METHODS",
    "CODEX_HOST_GOAL_START_CALLS",
    "CODEX_HOST_STREAM_NOTIFICATION_KINDS",
    "CODEX_HOST_GOAL_RESUME_FROM_STATUSES",
    "CODEX_HOST_LOAD_SAFE_GOAL_STATUSES",
)
# Section 8.5: the nine new Codex enums, exported from vidbyte.lib.enums with GitFlag.
NEW_CODEX_ENUMS = (
    "CodexCollaborationModeKind",
    "CodexMemoryMode",
    "CodexMcpAuthStatus",
    "CodexMcpConnectionStatus",
    "CodexMcpServerDetail",
    "CodexTurnSettingsStatus",
    "CodexTurnEventKind",
    "CodexPlanStepStatus",
    "CodexTurnWaitMode",
)


def _host_constants() -> Any:
    return importlib.import_module("vidbyte.lib.constants.codex_host")


def _enums() -> Any:
    return importlib.import_module("vidbyte.lib.enums.codex")


def _operation(name: str) -> Any:
    return getattr(_enums().CodexHostOperation, name.upper())


class CodexFeatureTextTests(unittest.TestCase):
    """Section 9.2 "Messages" and the section 9.3 side-chat texts, verbatim."""

    def test_every_new_message_cause_next_step_and_side_chat_text_holds_its_spec_value(self) -> None:
        constants = _host_constants()
        for name in TEXT_NAMES:
            with self.subTest(constant=f"CODEX_HOST_{name}"):
                self.assertEqual(getattr(constants, f"CODEX_HOST_{name}"), getattr(spec, name))
                self.assertIn(f"CODEX_HOST_{name}", constants.__all__)

    def test_the_export_list_stays_ascii_sorted_and_names_every_new_constant(self) -> None:
        # D-28: the module's __all__ stays sorted (test_codex_host_hardening_contract.py:519-520).
        constants = _host_constants()
        self.assertEqual(list(constants.__all__), sorted(constants.__all__))
        new_names = [*(f"CODEX_HOST_{name}" for name in TEXT_NAMES), *SET_NAMES, *spec.FEATURE_NUMBERS, *spec.FEATURE_METHOD_CONSTANTS]
        self.assertEqual([name for name in new_names if name not in constants.__all__], [])

    def test_no_new_name_goes_into_the_shared_codex_constants(self) -> None:
        # Section 12.4: "no new name goes into vidbyte/lib/constants/codex.py".
        shared = importlib.import_module("vidbyte.lib.constants.codex")
        added = [f"CODEX_HOST_{name}" for name in TEXT_NAMES] + list(SET_NAMES) + [*spec.FEATURE_METHOD_CONSTANTS, "CODEX_GOAL_RESUME_CALL"]
        self.assertEqual([name for name in added if hasattr(shared, name)], [])


class CodexFeatureTableTests(unittest.TestCase):
    """Section 9.3 "Configuration and flags": numbers, method names and sets."""

    def test_every_new_number_and_fixed_value_holds_its_spec_value(self) -> None:
        constants = _host_constants()
        for name, value in spec.FEATURE_NUMBERS.items():
            with self.subTest(constant=name):
                self.assertEqual(getattr(constants, name), value)

    def test_the_fifteen_method_names_are_named_constants_that_hold_their_wire_strings(self) -> None:
        # Section 9.3 (r4) names all fifteen; a constant that is missing, unexported or holding another string is listed.
        constants = _host_constants()
        wrong = [name for name, value in spec.FEATURE_METHOD_CONSTANTS.items() if getattr(constants, name, None) != value or name not in constants.__all__]
        self.assertEqual(wrong, [])

    def test_the_unmodeled_methods_are_the_nine_raw_rows_without_a_response_model(self) -> None:
        # D-3: these use the passthrough response class; the four modeled raw rows join the model table.
        constants = _host_constants()
        self.assertEqual(frozenset(constants.CODEX_HOST_UNMODELED_RAW_METHODS), spec.UNMODELED_METHODS)
        models = constants.CODEX_HOST_RAW_RESPONSE_MODELS
        for method, model in spec.NEW_RAW_RESPONSE_MODELS.items():
            with self.subTest(method=method):
                self.assertEqual(models[method], model)
        self.assertEqual(sorted(spec.UNMODELED_METHODS & set(models)), [])

    def test_both_goal_start_calls_map_their_window_to_an_api_error(self) -> None:
        constants = _host_constants()
        self.assertEqual(frozenset(constants.CODEX_HOST_GOAL_START_CALLS), frozenset({"start_goal_operation", "resume_goal_operation"}))
        self.assertEqual(constants.CODEX_GOAL_RESUME_CALL, "resume_goal_operation")

    def test_the_stream_table_is_read_only_and_never_streams_raw_reasoning(self) -> None:
        # INV-18, D-12: ten notification methods, each mapped to its CodexTurnEventKind member.
        constants = _host_constants()
        kinds = constants.CODEX_HOST_STREAM_NOTIFICATION_KINDS
        self.assertIsInstance(kinds, Mapping)
        self.assertEqual({method: kind.value for method, kind in kinds.items()}, spec.STREAM_KINDS)
        self.assertTrue(all(isinstance(kind, _enums().CodexTurnEventKind) for kind in kinds.values()))
        self.assertNotIn("item/reasoning/textDelta", kinds)
        with self.assertRaises(TypeError):
            kinds["item/reasoning/textDelta"] = _enums().CodexTurnEventKind.MESSAGE_DELTA  # type: ignore[index]

    def test_the_goal_status_sets_are_the_resumable_and_the_load_safe_statuses(self) -> None:
        # INV-31, D-38 and INV-12, D-14: ACTIVE is in neither; COMPLETE is load-safe but never resumable.
        constants = _host_constants()
        status = _enums().CodexGoalStatus
        resumable = constants.CODEX_HOST_GOAL_RESUME_FROM_STATUSES
        load_safe = constants.CODEX_HOST_LOAD_SAFE_GOAL_STATUSES
        self.assertTrue(all(isinstance(member, status) for member in (*resumable, *load_safe)))
        self.assertEqual(frozenset(member.value for member in resumable), spec.GOAL_RESUME_FROM_STATUSES)
        self.assertEqual(frozenset(member.value for member in load_safe), spec.LOAD_SAFE_GOAL_STATUSES)
        self.assertNotIn(status.ACTIVE, load_safe)


class CodexFeatureRejectedFieldTests(unittest.TestCase):
    """INV-10 and section 9.3 "These existing tables change"."""

    def test_the_plan_side_chat_and_resume_rows_hold_their_spec_fields(self) -> None:
        rows = _host_constants().CODEX_HOST_REJECTED_FIELDS
        self.assertEqual(tuple(rows[_operation("run_codex_plan")]), spec.PLAN_REJECTED_FIELDS)
        self.assertEqual(tuple(rows[_operation("start_codex_side_chat")]), spec.SIDE_CHAT_REJECTED_FIELDS)
        self.assertEqual(tuple(rows[_operation("resume_codex_goal")]), tuple(rows[_operation("continue_codex_thread")]))

    def test_the_fork_and_review_rows_end_with_collaboration_mode_and_the_goal_rule_gains_it(self) -> None:
        constants = _host_constants()
        rows = constants.CODEX_HOST_REJECTED_FIELDS
        self.assertEqual(rows[_operation("fork_codex_thread")][-1], "collaboration_mode")
        self.assertEqual(rows[_operation("start_codex_review")][-1], "collaboration_mode")
        self.assertEqual(tuple(constants.CODEX_HOST_GOAL_REJECTED_FIELDS), GOAL_REJECTED_FIELDS)

    def test_every_field_path_of_every_row_names_a_field_of_the_spawn_request(self) -> None:
        # A path that does not resolve would make the row refuse every request, or none.
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        default = CodexSpawnRequest()
        names = {field.name for field in dataclasses.fields(CodexSpawnRequest)}
        self.assertIn("collaboration_mode", names)
        for operation, row in _host_constants().CODEX_HOST_REJECTED_FIELDS.items():
            for path in row:
                with self.subTest(operation=operation.value, path=path):
                    self.assertIn(path.split(".")[0], names)
                    operator.attrgetter(path)(default)


class CodexFeatureGitValueTests(unittest.TestCase):
    """D-19, D-28, T-5: the git values live with the process-helper values, and GitFlag with the process enums."""

    def test_every_git_value_holds_its_spec_value_and_the_environment_is_read_only(self) -> None:
        values = importlib.import_module("vidbyte.lib.constants.native_threads")
        for name, value in spec.GIT_VALUES.items():
            with self.subTest(constant=name):
                self.assertEqual(getattr(values, name), value)
        self.assertIsInstance(values.GIT_NO_PROMPT_ENV, MappingProxyType)
        self.assertEqual(dict(values.GIT_NO_PROMPT_ENV), spec.GIT_NO_PROMPT_ENV)

    def test_git_flag_is_a_str_enum_with_the_two_flags_and_is_exported(self) -> None:
        process = importlib.import_module("vidbyte.lib.enums.process")
        flag = process.GitFlag
        self.assertTrue(issubclass(flag, enum.StrEnum))
        self.assertEqual([(member.name, member.value) for member in flag], [("REPOSITORY", "-C"), ("NEW_BRANCH", "-b")])
        self.assertIn("GitFlag", process.__all__)
        package = importlib.import_module("vidbyte.lib.enums")
        self.assertIs(package.GitFlag, flag)
        self.assertIn("GitFlag", package.__all__)

    def test_the_process_package_export_list_does_not_gain_the_git_helper(self) -> None:
        # D-19, INV-53: GitWorktrees is imported from its own module.
        process = importlib.import_module("vidbyte.lib.process")
        helper = importlib.import_module("vidbyte.lib.process.git_worktree")
        self.assertNotIn("GitWorktrees", process.__all__)
        self.assertTrue(callable(helper.GitWorktrees.add))


class CodexFeatureEnumExportTests(unittest.TestCase):
    """Section 12.3 rows 1 and 3, D-13 and D-29."""

    def test_the_nine_new_codex_enums_are_str_enums_exported_from_the_enum_package(self) -> None:
        enums = _enums()
        package = importlib.import_module("vidbyte.lib.enums")
        for name in NEW_CODEX_ENUMS:
            with self.subTest(enum=name):
                member_type = getattr(enums, name)
                self.assertTrue(issubclass(member_type, str) and issubclass(member_type, enum.Enum))
                self.assertIs(getattr(package, name), member_type)
                self.assertIn(name, package.__all__)
                self.assertIn(name, enums.__all__)

    def test_the_wait_modes_equal_asyncios_constants(self) -> None:
        modes = _enums().CodexTurnWaitMode
        self.assertEqual(modes.FIRST_COMPLETED.value, asyncio.FIRST_COMPLETED)
        self.assertEqual(modes.ALL_COMPLETED.value, asyncio.ALL_COMPLETED)
        self.assertEqual(modes(asyncio.ALL_COMPLETED), modes.ALL_COMPLETED)

    def test_the_twenty_five_operations_sit_between_forget_and_launch_in_function_order(self) -> None:
        operations = list(_enums().CodexHostOperation)
        names = [member.name for member in operations]
        start = names.index("FORGET_CODEX_TURNS") + 1
        end = names.index("LAUNCH_CODEX_SUBAGENTS")
        self.assertEqual([member.value for member in operations[start:end]], list(spec.FEATURE_METHODS))
        self.assertEqual([member.name for member in operations[start:end]], [method.upper() for method in spec.FEATURE_METHODS])


if __name__ == "__main__":
    unittest.main()
