"""FILE: tests/features/codex_host/test_codex_host_helper_surface.py

PURPOSE: Proves the lib and host surface the thread-helpers spec commits to, without a host or openai-codex: the five new records and their validation, CodexSkillScope, the twelve new CodexHostOperation members in method order, the four new failure codes between CODEX_TURN_TIMED_OUT and INPUT_EMPTY, the section 9.3 constants, the section 9.2 message and tool texts in the modules the spec names, and the twelve CodexHost methods with their section 8.5 signatures and order.
ROLE IN CODEBASE: Contract layer of the thread-helpers additions to tests/features/codex_host/ (docs/spec/codex-host-thread-helpers/spec.md AC-36, INV-1, INV-3, INV-15, FR-13; sections 8.5, 9.1, 9.2, 9.3 and 12.3 rows 1 to 5). It needs no host and no openai-codex, so CI runs it.
ARCHITECTURE NOTE: Every expected value is the spec's literal, written here or in codex_host_support.py, never read from the production module. Each invalid-record row starts from a valid baseline and breaks one rule, so a failure names the rule that did not hold. The host's methods are read with inspect, which needs no SDK because the host imports openai-codex only when a host opens.
COMMON MODIFICATION PATTERNS: When section 9.1 adds a rule, add one row to _invalid_rows; when section 9.3 adds a constant, add it to NEW_CONSTANTS with its spec value.
KNOWN EDGE CASES: A str-valued Enum compares equal to its plain string, so the wrong-type rows use values no member has (3, "global"); bool is an int subclass, so every int field has a True row. CodexThreadSummary.harness is init=False, so passing it is a TypeError, not a ConfigurationError.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-thread-helpers/spec.md sections 6.1, 8.5, 9.1, 9.2, 9.3 and 12.3.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_helper_surface.py
"""

from __future__ import annotations

import dataclasses
import enum
import importlib
import inspect
import unittest
from typing import Any

from tests.features.codex_host.codex_host_support import (
    BUDGET_DIFFERS_MESSAGE,
    COMPACT_STARTED_TEXT,
    EPHEMERAL_SKILL_MESSAGE,
    GOAL_UNCHECKED_MESSAGE,
    GOAL_UNFINISHED_MESSAGE,
    HELPER_METHODS,
    INPUT_NOT_RECORDED_MESSAGE,
    LIMIT_MESSAGE,
    NO_GOAL_MESSAGE,
    NO_GOAL_TEXT,
    OBJECTIVE_DIFFERS_MESSAGE,
    OWN_INPUT_MESSAGE,
    QUERY_MESSAGE,
    RUNNING_THREAD_MESSAGE,
    SINCE_MESSAGE,
    SKILL_DISABLED_MESSAGE,
    SKILL_DROPPED_MESSAGE,
    SKILL_NAME_MESSAGE,
    SKILL_NOT_FOUND_MESSAGE,
    SKILL_UNCHECKED_MESSAGE,
)
from vidbyte.lib.errors import ConfigurationError

BASE_TIME = 1_760_000_000

# Spec section 8.5: the field order of each new record (CodexThreadSummary mirrors NativeThreadSummary, FR-13).
RECORD_FIELDS = {
    "CodexThreadSummary": ("harness", "thread_id", "title", "created_at", "updated_at", "parent_thread_id", "model"),
    "CodexThreadGoal": ("thread_id", "objective", "status", "token_budget", "tokens_used", "time_used_seconds", "created_at", "updated_at"),
    "CodexSkillInfo": ("name", "description", "path", "scope", "enabled"),
    "CodexStoredTurn": ("turn_id", "status", "final_response", "error_message", "started_at", "completed_at", "items"),
    "CodexTurnPage": ("turns", "next_cursor"),
}

# Spec section 9.3, verbatim, except the two enum-valued constants checked on their own.
NEW_CONSTANTS: dict[str, Any] = {
    "CODEX_THREAD_COMPACT_METHOD": "thread/compact/start",
    "CODEX_THREAD_DELETE_METHOD": "thread/delete",
    "CODEX_GOAL_GET_METHOD": "thread/goal/get",
    "CODEX_SKILLS_LIST_METHOD": "skills/list",
    "CODEX_THREAD_TURNS_LIST_METHOD": "thread/turns/list",
    "CODEX_HOST_THREAD_LIST_DEFAULT_LIMIT": 20,
    "CODEX_HOST_THREAD_LIST_MAX_LIMIT": 1000,
    "CODEX_HOST_THREAD_LIST_MAX_PAGES": 1000,
    "CODEX_HOST_MIN_LIST_LIMIT": 1,
    "CODEX_HOST_LINEAGE_MAX_DEPTH": 100,
    "CODEX_HOST_SKILL_NAMES_IN_ERROR": 50,
    "CODEX_THREAD_SUMMARY_HARNESS": "codex",
    "CODEX_OPENAI_DOCS_SKILL_NAME": "openai-docs",
    "CODEX_TURN_ITEMS_VIEW_FULL": "full",
    "CODEX_HOST_TURNS_TOOL_DEFAULT_LIMIT": 3,
    "CODEX_HOST_INPUT_CHECK_ATTEMPTS": 10,
    "CODEX_HOST_INPUT_CHECK_INTERVAL_SECONDS": 0.5,
    "CODEX_HOST_INPUT_CHECK_DEADLINE_SECONDS": 10.0,
    "CODEX_HOST_INPUT_CHECK_TURN_LIMIT": 1,
}
ENUM_CONSTANTS = ("CODEX_HOST_HELPER_SOURCE_KINDS", "CODEX_HOST_RESUMABLE_GOAL_STATUSES")

# Spec section 9.2 "Message constants": the module each text lives in, and its exact value.
MESSAGE_CONSTANTS = {
    "vidbyte.harnesses.native.codex.thread_helpers": {
        "RUNNING_THREAD_MESSAGE": RUNNING_THREAD_MESSAGE,
        "LIMIT_MESSAGE": LIMIT_MESSAGE,
        "SINCE_MESSAGE": SINCE_MESSAGE,
        "QUERY_MESSAGE": QUERY_MESSAGE,
        "GOAL_UNFINISHED_MESSAGE": GOAL_UNFINISHED_MESSAGE,
    },
    "vidbyte.harnesses.native.codex.skill_functions": {
        "OWN_INPUT_MESSAGE": OWN_INPUT_MESSAGE,
        "EPHEMERAL_SKILL_MESSAGE": EPHEMERAL_SKILL_MESSAGE,
        "SKILL_NAME_MESSAGE": SKILL_NAME_MESSAGE,
        "SKILL_NOT_FOUND_MESSAGE": SKILL_NOT_FOUND_MESSAGE,
        "SKILL_DISABLED_MESSAGE": SKILL_DISABLED_MESSAGE,
        "NO_GOAL_MESSAGE": NO_GOAL_MESSAGE,
        "OBJECTIVE_DIFFERS_MESSAGE": OBJECTIVE_DIFFERS_MESSAGE,
        "BUDGET_DIFFERS_MESSAGE": BUDGET_DIFFERS_MESSAGE,
        "GOAL_UNCHECKED_MESSAGE": GOAL_UNCHECKED_MESSAGE,
        "INPUT_NOT_RECORDED_MESSAGE": INPUT_NOT_RECORDED_MESSAGE,
        "SKILL_DROPPED_MESSAGE": SKILL_DROPPED_MESSAGE,
        "SKILL_UNCHECKED_MESSAGE": SKILL_UNCHECKED_MESSAGE,
    },
    "vidbyte.tools.builtins.codex.thread_helpers": {"COMPACT_STARTED_TEXT": COMPACT_STARTED_TEXT},
    "vidbyte.tools.builtins.codex.skill_functions": {"NO_GOAL_TEXT": NO_GOAL_TEXT},
}

# Spec section 8.5: (parameter name, default) after self, for each new method; _REQUIRED marks no default.
_REQUIRED = inspect.Parameter.empty
HOST_SIGNATURES: dict[str, tuple[tuple[str, Any], ...]] = {
    "list_recent_codex_threads": (("cwd", _REQUIRED), ("limit", 20)),
    "list_codex_threads_since": (("cwd", _REQUIRED), ("since", _REQUIRED), ("limit", 20)),
    "search_codex_threads": (("cwd", _REQUIRED), ("query", _REQUIRED), ("limit", 20)),
    "get_codex_thread_lineage": (("thread_id", _REQUIRED),),
    "list_codex_turns": (("thread_id", _REQUIRED), ("cursor", ""), ("limit", None)),
    "compact_codex_thread": (("thread_id", _REQUIRED),),
    "delete_codex_thread": (("thread_id", _REQUIRED),),
    "get_codex_goal": (("thread_id", _REQUIRED),),
    "run_codex_goal": (("objective", _REQUIRED), ("token_budget", None), ("request", None)),
    "list_codex_skills": (("cwd", ""),),
    "run_codex_skill": (("skill", _REQUIRED), ("prompt", _REQUIRED), ("request", None)),
    "run_codex_openai_docs": (("question", _REQUIRED), ("request", None)),
}


def _valid_kwargs() -> dict[str, dict[str, Any]]:
    """One valid baseline per new record, using the edge values the spec allows (None, "", empty tuples)."""
    from vidbyte.lib.dataclasses.codex import CodexItem
    from vidbyte.lib.dataclasses.codex_host import CodexStoredTurn
    from vidbyte.lib.enums.codex import CodexGoalStatus, CodexSkillScope, CodexTurnStatus

    item = CodexItem(id="item-1", type="agentMessage", fields={"text": "Done.", "phase": "final_answer"})
    running = {"turn_id": "turn-2", "status": CodexTurnStatus.RUNNING, "final_response": "", "error_message": "", "started_at": BASE_TIME, "completed_at": None, "items": ()}
    return {
        "CodexThreadSummary": {"thread_id": "thr-1", "title": None, "created_at": BASE_TIME, "updated_at": BASE_TIME + 60, "parent_thread_id": None, "model": ""},
        "CodexThreadGoal": {
            "thread_id": "thr-1",
            "objective": "Ship the fix.",
            "status": CodexGoalStatus.PAUSED,
            "token_budget": None,
            "tokens_used": 0,
            "time_used_seconds": 0,
            "created_at": BASE_TIME,
            "updated_at": BASE_TIME,
        },
        "CodexSkillInfo": {"name": "openai-docs", "description": "", "path": "skills/openai-docs/SKILL.md", "scope": CodexSkillScope.SYSTEM, "enabled": False},
        "CodexStoredTurn": {"turn_id": "turn-1", "status": CodexTurnStatus.COMPLETED, "final_response": "Done.", "error_message": "", "started_at": BASE_TIME, "completed_at": BASE_TIME + 5, "items": (item,)},
        "CodexTurnPage": {"turns": (CodexStoredTurn(**running),), "next_cursor": ""},
    }


def _invalid_rows() -> list[tuple[str, dict[str, Any], str]]:
    """(record, fields that break one section 9.1 rule, the field name the message must name)."""
    from vidbyte.lib.dataclasses.codex import CodexItem
    from vidbyte.lib.enums.codex import CodexGoalStatus, CodexThreadStatus

    return [
        ("CodexThreadSummary", {"thread_id": ""}, "thread_id"),
        ("CodexThreadSummary", {"thread_id": 7}, "thread_id"),
        ("CodexThreadSummary", {"title": 7}, "title"),
        ("CodexThreadSummary", {"created_at": -1}, "created_at"),
        ("CodexThreadSummary", {"created_at": True}, "created_at"),
        ("CodexThreadSummary", {"updated_at": "1760000060"}, "updated_at"),
        ("CodexThreadSummary", {"updated_at": 1.5}, "updated_at"),
        ("CodexThreadSummary", {"parent_thread_id": 7}, "parent_thread_id"),
        ("CodexThreadSummary", {"model": None}, "model"),
        ("CodexThreadGoal", {"thread_id": ""}, "thread_id"),
        ("CodexThreadGoal", {"objective": ""}, "objective"),
        ("CodexThreadGoal", {"status": CodexGoalStatus.NONE}, "status"),
        ("CodexThreadGoal", {"status": 3}, "status"),
        ("CodexThreadGoal", {"token_budget": -1}, "token_budget"),
        ("CodexThreadGoal", {"token_budget": True}, "token_budget"),
        ("CodexThreadGoal", {"tokens_used": -1}, "tokens_used"),
        ("CodexThreadGoal", {"time_used_seconds": True}, "time_used_seconds"),
        ("CodexThreadGoal", {"created_at": None}, "created_at"),
        ("CodexThreadGoal", {"updated_at": -5}, "updated_at"),
        ("CodexSkillInfo", {"name": ""}, "name"),
        ("CodexSkillInfo", {"path": ""}, "path"),
        ("CodexSkillInfo", {"description": None}, "description"),
        ("CodexSkillInfo", {"scope": 3}, "scope"),
        ("CodexSkillInfo", {"scope": "global"}, "scope"),
        ("CodexSkillInfo", {"enabled": "yes"}, "enabled"),
        ("CodexSkillInfo", {"enabled": 1}, "enabled"),
        ("CodexStoredTurn", {"turn_id": ""}, "turn_id"),
        ("CodexStoredTurn", {"status": CodexThreadStatus.IDLE}, "status"),
        ("CodexStoredTurn", {"status": 3}, "status"),
        ("CodexStoredTurn", {"final_response": None}, "final_response"),
        ("CodexStoredTurn", {"error_message": 7}, "error_message"),
        ("CodexStoredTurn", {"started_at": -1}, "started_at"),
        ("CodexStoredTurn", {"completed_at": True}, "completed_at"),
        ("CodexStoredTurn", {"items": [CodexItem(id="item-1", type="agentMessage")]}, "items"),
        ("CodexStoredTurn", {"items": ("not an item",)}, "items"),
        ("CodexTurnPage", {"turns": []}, "turns"),
        ("CodexTurnPage", {"turns": ("not a turn",)}, "turns"),
        ("CodexTurnPage", {"next_cursor": None}, "next_cursor"),
    ]


class CodexHelperRecordTests(unittest.TestCase):
    """Section 9.1: the five new records are frozen, slotted, ordered as section 8.5 says, and validate themselves."""

    def test_valid_records_construct_in_section_8_5_field_order(self) -> None:
        from vidbyte.lib.dataclasses import codex_host

        for name, kwargs in _valid_kwargs().items():
            with self.subTest(record=name):
                record_type = getattr(codex_host, name)
                record = record_type(**kwargs)
                self.assertTrue(record_type.__dataclass_params__.frozen)
                self.assertIn("__slots__", record_type.__dict__)
                self.assertEqual(tuple(field.name for field in dataclasses.fields(record)), RECORD_FIELDS[name])
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    setattr(record, RECORD_FIELDS[name][-1], None)

    def test_the_summary_harness_is_fixed_to_codex(self) -> None:
        # FR-13, INV-15: harness is init=False with the CODEX_THREAD_SUMMARY_HARNESS default, so no caller sets it.
        from vidbyte.lib.dataclasses.codex_host import CodexThreadSummary

        summary = CodexThreadSummary(**_valid_kwargs()["CodexThreadSummary"])
        self.assertEqual(summary.harness, "codex")
        with self.assertRaises(TypeError):
            CodexThreadSummary(harness="grok", **_valid_kwargs()["CodexThreadSummary"])

    def test_each_invalid_record_raises_configuration_error_naming_the_field(self) -> None:
        from vidbyte.lib.dataclasses import codex_host

        baselines = _valid_kwargs()
        for name, broken, field_name in _invalid_rows():
            with self.subTest(record=name, broken=broken):
                with self.assertRaises(ConfigurationError) as caught:
                    getattr(codex_host, name)(**{**baselines[name], **broken})
                self.assertIn(field_name, caught.exception.message)


class CodexHelperEnumTests(unittest.TestCase):
    """Sections 8.5 and 12.3 rows 1 and 2: CodexSkillScope, the twelve operations and the four failure codes."""

    def test_skill_scope_has_the_four_wire_values_and_is_exported(self) -> None:
        import vidbyte.lib.enums as enums
        from vidbyte.lib.enums.codex import CodexSkillScope

        self.assertTrue(issubclass(CodexSkillScope, str) and issubclass(CodexSkillScope, enum.Enum))
        self.assertEqual({member.name: member.value for member in CodexSkillScope}, {"USER": "user", "REPO": "repo", "SYSTEM": "system", "ADMIN": "admin"})
        self.assertIs(enums.CodexSkillScope, CodexSkillScope)

    def test_the_twelve_operations_follow_start_codex_review_in_method_order(self) -> None:
        # INV-3: one operation per new method, value = method name; DELETE_CODEX_THREAD included although it has no tool.
        from vidbyte.lib.enums.codex import CodexHostOperation

        members = list(CodexHostOperation)
        start = [member.name for member in members].index("START_CODEX_REVIEW") + 1
        self.assertEqual([(member.name, member.value) for member in members[start:]], [(name.upper(), name) for name in HELPER_METHODS])

    def test_the_four_codes_sit_between_turn_timed_out_and_input_empty(self) -> None:
        # AC-36, section 12.3 row 1: nothing else moves.
        from vidbyte.lib.enums.failure import FailureCode

        members = list(FailureCode)
        start = members.index(FailureCode.CODEX_TURN_TIMED_OUT) + 1
        end = members.index(FailureCode.INPUT_EMPTY)
        expected = [
            ("CODEX_COMMAND_NOT_RUN", "codex.command_not_run"),
            ("CODEX_SKILL_NOT_FOUND", "codex.skill_not_found"),
            ("CODEX_SKILL_DISABLED", "codex.skill_disabled"),
            ("CODEX_GOAL_UNFINISHED", "codex.goal_unfinished"),
        ]
        self.assertEqual([(member.name, member.value) for member in members[start:end]], expected)


class CodexHelperConstantTests(unittest.TestCase):
    """Sections 9.2 and 9.3: the constants and the message texts, in the modules the spec names."""

    def test_section_9_3_constants_hold_their_values_and_are_appended_to_all(self) -> None:
        from vidbyte.lib.constants import codex as constants
        from vidbyte.lib.enums.codex import CodexGoalStatus, CodexThreadSourceKind

        for name, value in NEW_CONSTANTS.items():
            with self.subTest(constant=name):
                self.assertEqual(getattr(constants, name), value)
        sources = (CodexThreadSourceKind.CLI, CodexThreadSourceKind.VSCODE, CodexThreadSourceKind.EXEC, CodexThreadSourceKind.APP_SERVER, CodexThreadSourceKind.UNKNOWN)
        self.assertEqual(constants.CODEX_HOST_HELPER_SOURCE_KINDS, sources)
        self.assertIsInstance(constants.CODEX_HOST_HELPER_SOURCE_KINDS, tuple)
        self.assertEqual(constants.CODEX_HOST_RESUMABLE_GOAL_STATUSES, frozenset({CodexGoalStatus.COMPLETE}))
        self.assertIsInstance(constants.CODEX_HOST_RESUMABLE_GOAL_STATUSES, frozenset)
        # D-8: one walk may read at least as many pages as the largest limit needs.
        self.assertGreaterEqual(constants.CODEX_HOST_THREAD_LIST_MAX_PAGES, constants.CODEX_HOST_THREAD_LIST_MAX_LIMIT)
        # Section 9.3: every new name is appended at the end of __all__.
        new_names = {*NEW_CONSTANTS, *ENUM_CONSTANTS}
        self.assertEqual(set(constants.__all__[-len(new_names) :]), new_names)

    def test_message_and_tool_texts_live_in_their_modules_verbatim(self) -> None:
        for module_name, texts in MESSAGE_CONSTANTS.items():
            module = importlib.import_module(module_name)
            for name, value in texts.items():
                with self.subTest(module=module_name, constant=name):
                    self.assertEqual(getattr(module, name), value)


class CodexHelperHostSignatureTests(unittest.TestCase):
    """INV-1 and section 8.5: twelve async methods, named and placed as the spec says."""

    def test_the_twelve_methods_follow_start_codex_review_in_order(self) -> None:
        from vidbyte.harnesses.native.codex.host import CodexHost

        public = [name for name, value in vars(CodexHost).items() if not name.startswith("_") and inspect.isfunction(value)]
        start = public.index("start_codex_review") + 1
        self.assertEqual(tuple(public[start : start + len(HELPER_METHODS)]), HELPER_METHODS)

    def test_each_method_has_its_section_8_5_signature(self) -> None:
        from vidbyte.harnesses.native.codex.host import CodexHost

        for name, expected in HOST_SIGNATURES.items():
            with self.subTest(method=name):
                method = getattr(CodexHost, name)
                self.assertTrue(inspect.iscoroutinefunction(method))
                parameters = list(inspect.signature(method).parameters.values())[1:]
                self.assertEqual(tuple((parameter.name, parameter.default) for parameter in parameters), expected)
                self.assertTrue(all(parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD for parameter in parameters))


if __name__ == "__main__":
    unittest.main()
