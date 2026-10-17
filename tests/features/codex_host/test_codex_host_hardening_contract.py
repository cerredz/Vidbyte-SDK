"""FILE: tests/features/codex_host/test_codex_host_hardening_contract.py

PURPOSE: Proves the lib and error contracts of the codex-host-hardening slice that need no running host: CodexHostSetup's check of the constructor arguments; the fields appended to the fork, thread-list, review, skill-list and goal-run input records; CodexAgentError.retryable decided code by code and with_operation keeping every other field; CodexErrorMapper.relabel and its thread/read and turn/steer classification; ExceptionOrigin, a whitespace run in a file or function name included (spec r6, S5 R-12); LogToken's two rules and its exports (spec r5, S4 R-9); the section 9.2 and 9.3 constants, the r5 additions included, verbatim and in sorted __all__; no top-level constant under the native hosts (C021); the 0.163 pin; and the docstrings section 3 asks for.
ROLE IN CODEBASE: Contract layer of the hardening tests in tests/features/codex_host/ (docs/spec/codex-host-hardening/spec.md AC-5, AC-13, AC-34, AC-39, AC-40, AC-41 record half, INV-2, INV-4, INV-6, INV-19, INV-28 step 1, INV-29 to INV-32, INV-34, INV-47, INV-48, D-6, D-8, D-13, D-22, EC-54, EC-55, the spec r5 rows for S4 R-2, R-7 and R-9, and spec r6 row 9 for S5 R-12). Every class but the classification one runs on CI; that one needs openai-codex to build the SDK's JSON-RPC errors.
ARCHITECTURE NOTE: Feature names are imported inside each test, so a missing name fails that test while the module still collects. Expected texts and tables are the spec's literals from codex_host_support, never read back from the production constant they pin. The C021 check reads the native host sources with ast, the same scan lint/rules/c021_native_host_constants_in_lib.py runs.
COMMON MODIFICATION PATTERNS: A new section 9.2 or 9.3 constant adds one row to NEW_CONSTANTS; a new input field adds its valid and invalid rows beside the record's other rows.
KNOWN EDGE CASES: RecordFieldValidator puts the whole "<method> <field>" label in details["field"] while _reject_unused_fields puts the bare name, so the rows accept either by checking that the label ends with the field. The docstring checks are keyword-level, because section 3 fixes what each limitation says, not its wording.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-hardening/spec.md sections 6.1, 8.5, 9.1 to 9.3 and 12.3.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_hardening_contract.py
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import os
import tomllib
import unittest
from collections.abc import Callable
from typing import Any

from tests.features.codex_host.codex_host_support import (
    APPROVAL_HANDLER_MESSAGE,
    CHANGED_LIKELY_CAUSES,
    CONTINUE_GOAL_UNFINISHED_MESSAGE,
    DEFAULT_ANSWERS,
    EVENT_FAILED_MESSAGE,
    FORK_EXPERIMENTAL_MESSAGE,
    FORK_POINTS_MESSAGE,
    GOAL_FIELD_MESSAGE,
    GOAL_REJECTED_FIELDS,
    GOAL_RUN_OWNER,
    LIMIT_MESSAGE,
    LOST_EVENTS_MESSAGE,
    NETWORK_ACCESS_MESSAGE,
    RETRIED_METHODS,
    RETRYABLE_CODES,
    REVIEWER_MESSAGE,
    STEER_STOPPING_MESSAGE,
    UNKNOWN_TIER_MESSAGE,
    USER_REVIEWER_MESSAGE,
    WRITABLE_ROOTS_MESSAGE,
    requires_sdk,
)
from vidbyte.lib.errors import CodexAgentError, ConfigurationError

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
NATIVE_ROOT = os.path.join(REPO_ROOT, "vidbyte", "harnesses", "native")
CODEX_NATIVE = os.path.join(NATIVE_ROOT, "codex")
UNUSED_FIELD = "{operation} does not use the CodexSpawnRequest field {name}"
# Spec r5 section 9.2, verbatim: CODEX_HOST_GOAL_FIELD_MESSAGE for run_codex_goal with turn set (S4 R-7).
RUN_GOAL_TURN_TEXT = "run_codex_goal request does not use the field turn, because Codex starts goal turns itself with the thread's settings; leave turn at its default, or set the matching thread setting."

# Spec sections 9.2 and 9.3, verbatim: every new constant of vidbyte.lib.constants.codex_host and its value.
NEW_CONSTANTS: dict[str, Any] = {
    "CODEX_HOST_RETRIED_METHODS": RETRIED_METHODS,
    "CODEX_HOST_RETRYABLE_CODES": RETRYABLE_CODES,
    "CODEX_HOST_SERVER_REQUEST_DEFAULT_ANSWERS": DEFAULT_ANSWERS,
    "CODEX_CURRENT_TIME_READ_METHOD": "currentTime/read",
    "CODEX_TURN_ITEMS_VIEW_NOT_LOADED": "notLoaded",
    "CODEX_HOST_REVIEW_READ_BACK_LIMIT": 1,
    "CODEX_DEFAULT_SERVICE_TIER": "default",
    "CODEX_HOST_GOAL_REJECTED_FIELDS": GOAL_REJECTED_FIELDS,
    "CODEX_HOST_LOST_TURN_GRACE_SECONDS": 0.5,
    # Spec r5 (S4 R-2 and R-9): the fork twin of the goal rule's field tuple, and the longest logged value.
    "CODEX_HOST_FORK_EXPERIMENTAL_FIELDS": ("before_turn_id", "defer_goal_continuation"),
    "CODEX_HOST_LOG_TOKEN_MAX_CHARS": 128,
    "CODEX_HOST_APPROVAL_HANDLER_MESSAGE": APPROVAL_HANDLER_MESSAGE,
    "CODEX_HOST_STEER_STOPPING_MESSAGE": STEER_STOPPING_MESSAGE,
    "CODEX_HOST_FORK_POINTS_MESSAGE": FORK_POINTS_MESSAGE,
    "CODEX_HOST_EVENT_FAILED_MESSAGE": EVENT_FAILED_MESSAGE,
    "CODEX_HOST_LOST_EVENTS_MESSAGE": LOST_EVENTS_MESSAGE,
    "CODEX_HOST_USER_REVIEWER_MESSAGE": USER_REVIEWER_MESSAGE,
    "CODEX_HOST_GOAL_FIELD_MESSAGE": GOAL_FIELD_MESSAGE,
    "CODEX_HOST_UNKNOWN_TIER_MESSAGE": UNKNOWN_TIER_MESSAGE,
    # Spec r5 (S4 R-2): the {models} fragment of the tier refusal when no model is named.
    "CODEX_HOST_ANY_MODEL_TEXT": "any model",
    "CODEX_HOST_CONTINUE_GOAL_UNFINISHED_MESSAGE": CONTINUE_GOAL_UNFINISHED_MESSAGE,
    "CODEX_HOST_NETWORK_ACCESS_MESSAGE": NETWORK_ACCESS_MESSAGE,
    "CODEX_HOST_WRITABLE_ROOTS_MESSAGE": WRITABLE_ROOTS_MESSAGE,
    "CODEX_HOST_FORK_EXPERIMENTAL_MESSAGE": FORK_EXPERIMENTAL_MESSAGE,
}
# Spec r5 INV-10 (S4 R-9), verbatim: the LogToken.of example, its token, and the one character set a token keeps.
LOG_TOKEN_SPEC_VALUE = "item-1 handled_by=handler answer=accept\ncodex_host_server_request"
LOG_TOKEN_SPEC_TOKEN = "item-1_handled_by_handler_answer_accept_codex_host_server_request"
LOG_TOKEN_ALLOWED = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:/-"
# The FORK_CODEX_THREAD row before this slice; section 9.3 appends three fields to it.
FORK_ROW_BEFORE = ("prompt", "goal", "thread.personality", "thread.service_name", "thread.session_start_source", "turn", "tools", "disabled_plugin_ids", "output_schema", "max_output_tokens", "timeout_seconds")


def _raise_here() -> None:
    raise RuntimeError("origin-canary-3b9d")


def _raise_deeper() -> None:
    _raise_here()


def _compiled(source: str, filename: str) -> dict[str, Any]:
    """Run literal source under a made-up file name, so its frames name that file, and return its namespace; no file is written."""
    namespace: dict[str, Any] = {}
    exec(compile(source, filename, "exec"), namespace)  # noqa: S102 - the source is a literal of this module
    return namespace


async def _async_handler(request: Any) -> Any:
    return None


def _sync_handler(request: Any) -> Any:
    return None


class _AsyncCallable:
    async def __call__(self, request: Any) -> Any:
        return None

    async def method(self, request: Any) -> Any:
        return None


class _SyncCallable:
    def __call__(self, request: Any) -> Any:
        return None


def _field_named(case: unittest.TestCase, error: ConfigurationError, field_name: str) -> None:
    """details["field"] is set and names the field, bare or as "<method> <field>"."""
    label = str(error.details.get("field", ""))
    case.assertTrue(label.endswith(field_name), error.details)


class CodexHostSetupTests(unittest.TestCase):
    """INV-19, AC-13 and D-1: the constructor's record accepts only None or an async callable, and None or settings."""

    def test_none_an_async_function_and_an_async_callable_object_are_accepted(self) -> None:
        from vidbyte.lib.dataclasses.codex import CodexClientSettings
        from vidbyte.lib.dataclasses.codex_host_inputs import CodexHostSetup

        bare = CodexHostSetup()
        self.assertEqual((bare.settings, bare.approval_handler), (None, None))
        self.assertIn("CodexHostSetup", __import__("vidbyte.lib.dataclasses.codex_host_inputs", fromlist=["__all__"]).__all__)
        for label, handler in (("async function", _async_handler), ("async __call__", _AsyncCallable()), ("bound async method", _AsyncCallable().method)):
            with self.subTest(handler=label):
                setup = CodexHostSetup(settings=CodexClientSettings(), approval_handler=handler)
                self.assertIs(setup.approval_handler, handler)

    def test_a_sync_callable_a_lambda_a_value_or_bad_settings_is_refused_naming_the_field(self) -> None:
        from vidbyte.lib.dataclasses.codex_host_inputs import CodexHostSetup

        for label, handler, kind in (
            ("sync function", _sync_handler, "function"),
            ("lambda", lambda request: None, "function"),
            ("sync __call__", _SyncCallable(), "_SyncCallable"),
            ("an int", 5, "int"),
            ("text", "answer", "str"),
        ):
            with self.subTest(handler=label):
                with self.assertRaises(ConfigurationError) as caught:
                    CodexHostSetup(approval_handler=handler)
                self.assertEqual(str(caught.exception), APPROVAL_HANDLER_MESSAGE.format(kind=kind))
                self.assertEqual(caught.exception.details.get("field"), "approval_handler")
        with self.assertRaises(ConfigurationError) as caught:
            CodexHostSetup(settings="x")
        self.assertIn("CodexHost settings", str(caught.exception))
        _field_named(self, caught.exception, "settings")

    def test_the_constructor_builds_the_record_before_anything_starts(self) -> None:
        # INV-19 and section 9.4 item 10: a bad value is refused by CodexHost(...) itself, not later in __aenter__.
        from vidbyte.harnesses.native.codex import CodexHost

        parameters = inspect.signature(CodexHost.__init__).parameters
        self.assertEqual(parameters["approval_handler"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIsNone(parameters["approval_handler"].default)
        with self.assertRaises(ConfigurationError) as caught:
            CodexHost(approval_handler=_sync_handler)
        self.assertEqual(str(caught.exception), APPROVAL_HANDLER_MESSAGE.format(kind="function"))
        with self.assertRaises(ConfigurationError) as caught:
            CodexHost("x")
        self.assertIn("CodexHost settings", str(caught.exception))
        CodexHost(approval_handler=_async_handler)


class CodexHardeningInputRecordTests(unittest.TestCase):
    """INV-28 step 1, INV-29, INV-30, INV-32, INV-34, INV-48 and AC-41: the fields appended to #1178's input records."""

    def test_fork_takes_one_fork_point_and_refuses_both(self) -> None:
        from vidbyte.lib.dataclasses.codex_host_inputs import CodexForkRequest

        fork = CodexForkRequest(thread_id="thr-1", before_turn_id="turn-2", defer_goal_continuation=True)
        self.assertEqual((fork.before_turn_id, fork.defer_goal_continuation), ("turn-2", True))
        bare = CodexForkRequest(thread_id="thr-1")
        self.assertEqual((bare.before_turn_id, bare.defer_goal_continuation), ("", False))
        self.assertEqual([field.name for field in dataclasses.fields(bare)][-2:], ["before_turn_id", "defer_goal_continuation"])
        # EC-54: both points are refused when the record is built, naming before_turn_id.
        with self.assertRaises(ConfigurationError) as caught:
            CodexForkRequest(thread_id="thr-1", from_turn_id="turn-1", before_turn_id="turn-2")
        self.assertEqual(str(caught.exception), FORK_POINTS_MESSAGE)
        self.assertEqual(caught.exception.details.get("field"), "before_turn_id")
        for label, fields, field_name in (
            ("before_turn_id is an int", {"before_turn_id": 5}, "before_turn_id"),
            ("before_turn_id spans two lines", {"before_turn_id": "turn-1\nturn-2"}, "before_turn_id"),
            ("defer_goal_continuation is text", {"defer_goal_continuation": "yes"}, "defer_goal_continuation"),
            ("defer_goal_continuation is an int", {"defer_goal_continuation": 1}, "defer_goal_continuation"),
        ):
            with self.subTest(row=label):
                with self.assertRaises(ConfigurationError) as caught:
                    CodexForkRequest(thread_id="thr-1", **fields)
                self.assertIn(f"fork_codex_thread {field_name}", str(caught.exception))
                _field_named(self, caught.exception, field_name)

    def test_fork_overrides_refuse_the_three_new_turn_fields(self) -> None:
        # INV-37 and section 9.3: the FORK row gains turn_service_tier, network_access and writable_roots.
        from vidbyte.lib.dataclasses.codex import CodexTurnSettings
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
        from vidbyte.lib.dataclasses.codex_host_inputs import CodexForkRequest
        from vidbyte.lib.enums.codex import CodexSandbox

        with self.assertRaises(ConfigurationError) as caught:
            CodexForkRequest(thread_id="thr-1", overrides=CodexSpawnRequest(turn_service_tier="fast"))
        self.assertIn(UNUSED_FIELD.format(operation="fork_codex_thread", name="turn_service_tier"), str(caught.exception))
        workspace = CodexTurnSettings(sandbox=CodexSandbox.WORKSPACE_WRITE)
        for label, overrides in (
            ("network_access", CodexSpawnRequest(turn=workspace, network_access=True)),
            ("writable_roots", CodexSpawnRequest(turn=workspace, writable_roots=(os.path.abspath(os.sep),))),
        ):
            with self.subTest(field=label):
                with self.assertRaises(ConfigurationError):
                    CodexForkRequest(thread_id="thr-1", overrides=overrides)

    def test_the_thread_list_limit_is_none_or_an_int_in_range(self) -> None:
        from vidbyte.lib.dataclasses.codex_host_inputs import CodexThreadListRequest

        self.assertIsNone(CodexThreadListRequest().limit)
        self.assertEqual([field.name for field in dataclasses.fields(CodexThreadListRequest())][-1], "limit")
        for limit in (1, 5, 1000):
            self.assertEqual(CodexThreadListRequest(limit=limit).limit, limit)
        message = LIMIT_MESSAGE.format(operation="list_codex_threads", minimum=1, maximum=1000)
        for limit in (0, 1001, -1, True, "5", 2.5):
            with self.subTest(limit=limit):
                with self.assertRaises(ConfigurationError) as caught:
                    CodexThreadListRequest(limit=limit)
                self.assertEqual(str(caught.exception), message)
                _field_named(self, caught.exception, "limit")

    def test_a_review_request_takes_only_time_and_token_caps(self) -> None:
        # INV-30: _reject_unused_fields(START_CODEX_REVIEW, request) allows only timeout_seconds and max_output_tokens.
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings, CodexTurnSettings
        from vidbyte.lib.dataclasses.codex_host import CodexReviewTarget, CodexSpawnRequest
        from vidbyte.lib.dataclasses.codex_host_inputs import CodexReviewRequest
        from vidbyte.lib.enums.codex import CodexApprovalsReviewer, CodexReviewTargetKind

        target = CodexReviewTarget(kind=CodexReviewTargetKind.UNCOMMITTED_CHANGES)
        self.assertEqual(CodexReviewRequest(thread_id="thr-1", target=target).request, CodexSpawnRequest())
        capped = CodexReviewRequest(thread_id="thr-1", target=target, request=CodexSpawnRequest(timeout_seconds=1.0, max_output_tokens=50))
        self.assertEqual((capped.request.timeout_seconds, capped.request.max_output_tokens), (1.0, 50))
        with self.assertRaises(ConfigurationError) as caught:
            CodexReviewRequest(thread_id="thr-1", target=target, request={})
        self.assertIn("start_codex_review request", str(caught.exception))
        _field_named(self, caught.exception, "request")
        for name, request in (
            ("turn", CodexSpawnRequest(turn=CodexTurnSettings(model="x"))),
            ("thread", CodexSpawnRequest(thread=CodexThreadSettings(model="x"))),
            ("prompt", CodexSpawnRequest(prompt="Review it.")),
            ("name", CodexSpawnRequest(name="review")),
            ("approvals_reviewer", CodexSpawnRequest(approvals_reviewer=CodexApprovalsReviewer.AUTO_REVIEW)),
            ("turn_service_tier", CodexSpawnRequest(turn_service_tier="fast")),
        ):
            with self.subTest(field=name):
                with self.assertRaises(ConfigurationError) as caught:
                    CodexReviewRequest(thread_id="thr-1", target=target, request=request)
                self.assertIn(UNUSED_FIELD.format(operation="start_codex_review", name=name), str(caught.exception))
                _field_named(self, caught.exception, name)

    def test_skill_listing_takes_a_bool_force_reload(self) -> None:
        from vidbyte.lib.dataclasses.codex_host_inputs import CodexSkillListRequest

        self.assertIs(CodexSkillListRequest().force_reload, False)
        self.assertIs(CodexSkillListRequest(cwd="", force_reload=True).force_reload, True)
        for value in ("yes", 1, None):
            with self.subTest(force_reload=value):
                with self.assertRaises(ConfigurationError) as caught:
                    CodexSkillListRequest(force_reload=value)
                self.assertIn("list_codex_skills force_reload", str(caught.exception))
                _field_named(self, caught.exception, "force_reload")

    def test_a_goal_run_request_applies_the_goal_rule_to_its_request(self) -> None:
        # INV-34 and INV-48 (spec r5, S4 R-7): run_codex_goal refuses a turn-only field before any request, with the goal
        # spawn's text under its own owner, so the refusal names run_codex_goal.
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings, CodexTurnSettings
        from vidbyte.lib.dataclasses.codex_host import CodexGoal, CodexSpawnRequest
        from vidbyte.lib.dataclasses.codex_host_inputs import CodexGoalRunRequest
        from vidbyte.lib.enums.codex import CodexReasoningEffort

        goal = CodexGoal(objective="Ship the fix.")
        for name, request in (
            ("turn", CodexSpawnRequest(turn=CodexTurnSettings(effort=CodexReasoningEffort.HIGH))),
            ("output_schema", CodexSpawnRequest(output_schema={"type": "object"})),
            ("disabled_plugin_ids", CodexSpawnRequest(disabled_plugin_ids=("plugin-a",))),
            ("turn_service_tier", CodexSpawnRequest(turn_service_tier="fast")),
        ):
            with self.subTest(field=name):
                with self.assertRaises(ConfigurationError) as caught:
                    CodexGoalRunRequest(goal=goal, request=request)
                self.assertEqual(str(caught.exception), GOAL_FIELD_MESSAGE.format(owner=GOAL_RUN_OWNER, name=name))
                _field_named(self, caught.exception, name)
                if name == "turn":
                    # Section 9.2's whole text for this row, verbatim, so a wrong template cannot pass with a matching owner.
                    self.assertEqual(str(caught.exception), RUN_GOAL_TURN_TEXT)
        kept = CodexGoalRunRequest(goal=goal, request=CodexSpawnRequest(thread=CodexThreadSettings(model="gpt-5.5"), timeout_seconds=30.0))
        self.assertEqual(kept.request.thread.model, "gpt-5.5")


class CodexAgentErrorHardeningTests(unittest.TestCase):
    """INV-2, D-6, AC-5 and D-22: retryable is derived from the code, and with_operation keeps every other field."""

    def _error(self, code: str, **fields: Any) -> CodexAgentError:
        values: dict[str, Any] = {"failure_code": code, "operation": "spawn_codex_thread"}
        values.update(fields)
        return CodexAgentError(f"spawn_codex_thread failed with {code}. Something happened.", **values)

    def test_retryable_is_true_exactly_for_the_five_codes_and_never_in_details(self) -> None:
        from vidbyte.lib.constants.codex import CODEX_FAILURE_CLASSIFICATION

        self.assertIsInstance(inspect.getattr_static(CodexAgentError, "retryable"), property)
        codes = sorted(CODEX_FAILURE_CLASSIFICATION) + ["configuration.unsupported_combination", "configuration.invalid_argument"]
        self.assertTrue(RETRYABLE_CODES <= set(codes))
        for code in codes:
            with self.subTest(code=code):
                error = self._error(code)
                self.assertIs(error.retryable, code in RETRYABLE_CODES)
                self.assertNotIn("retryable", error.details)
                # Derived from the code, so it survives every re-raise that keeps the code.
                self.assertIs(error.with_sentence(" More.").retryable, code in RETRYABLE_CODES)
        # The three TRANSIENT codes the spec excludes.
        for code in ("codex.fork_failed", "codex.process_exited", "codex.turn_timed_out"):
            self.assertIs(self._error(code).retryable, False)
        with self.assertRaises(AttributeError):
            self._error("codex.api_error").retryable = False  # type: ignore[misc]

    def test_with_operation_changes_the_operation_and_message_and_keeps_the_rest(self) -> None:
        original = self._error(
            "codex.api_error",
            operation="get_codex_goal",
            error_type="InternalRpcError",
            next_step="Retry the call.",
            thread_id="thr-7",
            likely_cause="Codex failed.",
            method="thread/goal/get",
            related_docs=("doc-a",),
            relevant_tests=("test-a",),
        )
        copy = original.with_operation("run_codex_goal", "run_codex_goal failed with codex.api_error. Something happened.")
        self.assertIsInstance(copy, CodexAgentError)
        self.assertIsNot(copy, original)
        self.assertEqual((copy.operation, copy.message), ("run_codex_goal", "run_codex_goal failed with codex.api_error. Something happened."))
        kept = ("failure_code", "thread_id", "method", "next_step", "likely_cause", "likely_causes", "repair_approaches", "related_docs", "relevant_tests", "error_kind")
        self.assertEqual({name: getattr(copy, name) for name in kept}, {name: getattr(original, name) for name in kept})
        self.assertEqual(copy.safe_runtime_details, {"operation": "run_codex_goal", "error_type": "InternalRpcError", "method": "thread/goal/get"})
        self.assertIn("run_codex_goal", copy.expected)
        self.assertEqual(original.operation, "get_codex_goal")

    def test_relabel_rewrites_the_head_and_returns_an_error_already_carrying_the_operation(self) -> None:
        # INV-31, D-22 and EC-55. errors.py imports openai-codex only inside from_exception, so this runs on CI.
        from vidbyte.harnesses.native.codex.errors import CodexErrorMapper
        from vidbyte.lib.enums.codex import CodexHostOperation
        from vidbyte.lib.enums.failure import FailureCode

        inner = CodexErrorMapper.error(FailureCode.CODEX_API_ERROR, "Codex could not read the goal.", CodexHostOperation.GET_CODEX_GOAL, "thr-7", method="thread/goal/get", error_type="InternalRpcError")
        relabelled = CodexErrorMapper.relabel(inner.with_sentence(" The goal run was interrupted."), CodexHostOperation.RUN_CODEX_GOAL)
        head = "get_codex_goal failed with codex.api_error."
        self.assertTrue(inner.message.startswith(head))
        self.assertEqual(relabelled.message, "run_codex_goal failed with codex.api_error." + inner.message[len(head) :] + " The goal run was interrupted.")
        self.assertEqual(relabelled.operation, "run_codex_goal")
        self.assertEqual((relabelled.thread_id, relabelled.method, relabelled.failure_code, relabelled.next_step), (inner.thread_id, inner.method, inner.failure_code, inner.next_step))
        self.assertEqual(relabelled.safe_runtime_details["error_type"], "InternalRpcError")
        self.assertIn(" The thread id was thr-7.", relabelled.message)
        own = CodexErrorMapper.error(FailureCode.CODEX_SKILL_NOT_FOUND, "Codex lists no skill.", CodexHostOperation.RUN_CODEX_SKILL)
        self.assertIs(CodexErrorMapper.relabel(own, CodexHostOperation.RUN_CODEX_SKILL), own)


class CodexExceptionOriginTests(unittest.TestCase):
    """D-13 and INV-7: the innermost frame of a raised exception as file:function:line, never its text."""

    def test_a_raised_exception_names_its_innermost_frame_and_a_fresh_one_names_nothing(self) -> None:
        from vidbyte.lib import util
        from vidbyte.lib.util.exception_origin import ExceptionOrigin

        self.assertIs(util.ExceptionOrigin, ExceptionOrigin)
        self.assertIn("ExceptionOrigin", util.__all__)
        line = _raise_here.__code__.co_firstlineno + 1
        for label, raiser in (("direct", _raise_here), ("one call deeper", _raise_deeper)):
            with self.subTest(case=label):
                try:
                    raiser()
                except RuntimeError as exc:
                    origin = ExceptionOrigin.describe(exc)
                self.assertEqual(origin, f"test_codex_host_hardening_contract.py:_raise_here:{line}")
                self.assertNotIn("origin-canary-3b9d", origin)
        self.assertEqual(ExceptionOrigin.describe(RuntimeError("never raised")), "")

    def test_a_frame_in_a_file_whose_name_has_a_space_describes_as_one_token(self) -> None:
        # INV-7 and row 9 (spec r6, S5 R-12), the spec's own example. compile names the file, so nothing is written to
        # disk, and the answer is the same whether or not this build freezes the stdlib. <module> stays as it is.
        from vidbyte.lib.util.exception_origin import ExceptionOrigin

        try:
            _compiled("raise KeyError('k')", "my script.py")
        except KeyError as exc:
            origin = ExceptionOrigin.describe(exc)
        self.assertEqual(origin, "my_script.py:<module>:1")

    def test_each_run_of_whitespace_in_a_file_or_function_name_becomes_one_underscore(self) -> None:
        # Row 9: a run of spaces and tabs is one "_", in the file's basename and in the function's name alike.
        from vidbyte.lib.util.exception_origin import ExceptionOrigin

        renamed = _compiled("def read():\n    raise KeyError('k')\n", "plain.py")["read"]
        renamed.__code__ = renamed.__code__.replace(co_name="read  the\tsetting")
        rows = (
            ("a run in the file name", lambda: _compiled("raise KeyError('k')", "my \t  script.py"), "my_script.py:<module>:1"),
            ("runs in the function name", renamed, "plain.py:read_the_setting:2"),
        )
        for label, raiser, expected in rows:
            with self.subTest(case=label):
                try:
                    raiser()
                except KeyError as exc:
                    origin = ExceptionOrigin.describe(exc)
                self.assertEqual(origin, expected)


class CodexLogTokenTests(unittest.TestCase):
    """INV-10 and spec r5 rows 10 and 25 (S4 R-9): any text as one bounded, space-free log token, by two fixed rules."""

    def _log_token(self) -> Any:
        from vidbyte.lib.util import text

        self.assertTrue(hasattr(text, "LogToken"), "spec r5 row 25 adds the LogToken class to vidbyte.lib.util.text")
        return text.LogToken

    def test_the_spec_examples_hold_verbatim(self) -> None:
        of = self._log_token().of
        self.assertEqual(of(LOG_TOKEN_SPEC_VALUE, 128), LOG_TOKEN_SPEC_TOKEN)
        self.assertEqual(of("a" * 200, 128), "a" * 128 + "...")

    def test_every_character_outside_the_ascii_set_becomes_one_underscore(self) -> None:
        # Rule 1. The look-alike digits are str.isalnum() and str.isdigit() in Python but not ASCII, so they go too.
        of = self._log_token().of
        rows = (
            ("space", "a b", "a_b"),
            ("tab", "a\tb", "a_b"),
            ("carriage return", "a\rb", "a_b"),
            ("newline", "a\nb", "a_b"),
            ("CRLF", "a\r\nb", "a__b"),
            ("equals", "key=value", "key_value"),
            ("percent", "50%s", "50_s"),
            ("double quote", 'say "hi"', "say__hi_"),
            ("single quote", "it's", "it_s"),
            ("backslash", "a\\b", "a_b"),
            ("comma, semicolon and brackets", "a,b;c[d]", "a_b_c_d_"),
            ("NUL", "a\x00b", "a_b"),
            ("non-ASCII letter", "café", "caf_"),
            ("line separator", "a b", "a_b"),
            ("fullwidth and superscript digits", "１²", "__"),
            ("emoji", "ok\U0001f600", "ok_"),
        )
        for label, value, expected in rows:
            with self.subTest(case=label):
                self.assertEqual(of(value, 128), expected)

    def test_a_value_inside_the_set_and_the_limit_comes_back_unchanged(self) -> None:
        of = self._log_token().of
        for value in (LOG_TOKEN_ALLOWED, "019a3c1e-7b2f-7c43-9d1e-5f0a8b6c2d4e", "item/commandExecution/terminalInteraction", "turn-2", "client.py:_request_raw:384", ""):
            with self.subTest(value=value):
                self.assertEqual(of(value, 128), value)

    def test_a_longer_result_keeps_the_first_limit_characters_and_appends_three_dots(self) -> None:
        # Rule 2 runs after rule 1, so a token is never longer than limit + 3.
        of = self._log_token().of
        self.assertEqual(of("b" * 128, 128), "b" * 128)
        self.assertEqual(of("b" * 129, 128), "b" * 128 + "...")
        self.assertEqual(of(" " * 130, 128), "_" * 128 + "...")
        self.assertEqual(of("abcdef", 3), "abc...")
        self.assertEqual(of("abc", 3), "abc")
        self.assertEqual(of("x=" * 100_000, 128), "x_" * 64 + "...")

    def test_applying_it_twice_gives_the_same_token(self) -> None:
        of = self._log_token().of
        allowed = set(LOG_TOKEN_ALLOWED)
        for limit in (3, 128):
            for value in (LOG_TOKEN_SPEC_VALUE, "a" * 200, " " * 130, "café = %s\r\n", "", "abc"):
                with self.subTest(limit=limit, value=value[:20]):
                    token = of(value, limit)
                    self.assertEqual(of(token, limit), token)
                    self.assertLessEqual(len(token), limit + 3)
                    self.assertLessEqual(set(token), allowed)

    def test_it_is_a_static_method_exported_from_the_text_module_and_the_util_package(self) -> None:
        from vidbyte.lib import util
        from vidbyte.lib.util import text

        log_token = self._log_token()
        self.assertIsInstance(inspect.getattr_static(log_token, "of"), staticmethod)
        # Row 25: LogToken goes after TOKEN_ESTIMATE_CHARS_PER_TOKEN, before SubstringCounter.
        self.assertEqual(text.__all__, ["TOKEN_ESTIMATE_CHARS_PER_TOKEN", "LogToken", "SubstringCounter", "TokenEstimate"])
        # Row 10: the util package re-exports it in its alphabetical __all__.
        self.assertIs(getattr(util, "LogToken", None), log_token)
        self.assertIn("LogToken", util.__all__)
        self.assertEqual(list(util.__all__), sorted(util.__all__))


class CodexHardeningConstantTests(unittest.TestCase):
    """AC-40, INV-47, D-31 and sections 9.2 and 9.3: every fixed value lives in lib, verbatim, in sorted __all__."""

    def test_every_new_constant_holds_its_spec_value_and_is_exported_in_order(self) -> None:
        from vidbyte.lib.constants import codex_host

        exported = list(codex_host.__all__)
        self.assertEqual(exported, sorted(exported))
        for name, expected in NEW_CONSTANTS.items():
            with self.subTest(constant=name):
                # Checked before the read, so a constant the module lacks fails as a missing export, not an AttributeError.
                self.assertIn(name, exported)
                value = getattr(codex_host, name)
                if isinstance(expected, dict):
                    self.assertEqual({key: dict(answer) for key, answer in value.items()}, expected)
                else:
                    self.assertEqual(value, expected)
        self.assertIsInstance(codex_host.CODEX_HOST_RETRIED_METHODS, frozenset)
        self.assertIsInstance(codex_host.CODEX_HOST_RETRYABLE_CODES, frozenset)

    def test_the_changed_texts_and_rejected_field_rows_hold_their_new_values(self) -> None:
        from vidbyte.lib.constants import codex_host
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
        from vidbyte.lib.enums.codex import CodexHostOperation

        self.assertEqual(codex_host.CODEX_HOST_REVIEWER_MESSAGE, REVIEWER_MESSAGE)
        for code, cause in CHANGED_LIKELY_CAUSES.items():
            with self.subTest(likely_cause=code):
                self.assertEqual(codex_host.CODEX_HOST_LIKELY_CAUSES[code], cause)
        rejected = codex_host.CODEX_HOST_REJECTED_FIELDS
        every_field = {field.name for field in dataclasses.fields(CodexSpawnRequest)}
        self.assertEqual(set(rejected[CodexHostOperation.START_CODEX_REVIEW]), every_field - {"timeout_seconds", "max_output_tokens"})
        fork_row = tuple(rejected[CodexHostOperation.FORK_CODEX_THREAD])
        self.assertEqual(fork_row[: len(FORK_ROW_BEFORE)], FORK_ROW_BEFORE)
        # docs/spec/codex-host-first-class/spec.md section 9.3: the fork row's tail gains collaboration_mode (INV-10).
        self.assertEqual(set(fork_row[len(FORK_ROW_BEFORE) :]), {"turn_service_tier", "network_access", "writable_roots", "collaboration_mode"})

    def test_no_native_host_module_binds_a_top_level_constant(self) -> None:
        # C021 at baseline 0, over every module under vidbyte/harnesses/native/, the two new codex modules included.
        for name in ("turn_events.py", "reviews.py"):
            self.assertTrue(os.path.isfile(os.path.join(CODEX_NATIVE, name)), f"section 12.3 creates {name}")
        found: list[str] = []
        for folder, _, files in os.walk(NATIVE_ROOT):
            for file_name in files:
                if not file_name.endswith(".py"):
                    continue
                path = os.path.join(folder, file_name)
                with open(path, encoding="utf-8") as handle:
                    tree = ast.parse(handle.read())
                for node in tree.body:
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
                    for target in targets:
                        if isinstance(target, ast.Name) and target.id != "__all__" and target.id.lstrip("_")[:1].isupper() and target.id.upper() == target.id:
                            found.append(f"{os.path.relpath(path, REPO_ROOT)}:{target.id}")
        self.assertEqual(found, [])

    def test_the_two_new_codex_modules_export_one_class_and_import_no_sdk_at_module_level(self) -> None:
        # Section 12.3 rows 17 and 18, and INV-41: neither module imports openai-codex at module level.
        for file_name, exported in (("turn_events.py", ["CodexTurnEvents"]), ("reviews.py", ["CodexReviews"])):
            with self.subTest(module=file_name):
                with open(os.path.join(CODEX_NATIVE, file_name), encoding="utf-8") as handle:
                    tree = ast.parse(handle.read())
                sdk_imports = [
                    node.lineno
                    for node in tree.body
                    if (isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "openai_codex")
                    or (isinstance(node, ast.Import) and any(alias.name.split(".")[0] == "openai_codex" for alias in node.names))
                ]
                self.assertEqual(sdk_imports, [])
                assigned = [node for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets)]
                self.assertEqual(len(assigned), 1)
                self.assertEqual(ast.literal_eval(assigned[0].value), exported)


class CodexHardeningPinAndDocsTests(unittest.TestCase):
    """AC-34, INV-39, AC-39 and FR-35/FR-36: the 0.163 pin and the documented limitations."""

    def test_the_extra_pins_openai_codex_0_163_and_the_client_reports_it(self) -> None:
        from vidbyte.lib.dataclasses.codex import CodexClientSettings

        with open(os.path.join(REPO_ROOT, "pyproject.toml"), "rb") as handle:
            project = tomllib.load(handle)["project"]
        self.assertEqual(project["optional-dependencies"]["codex"], ["openai-codex>=0.163.0,<0.164.0"])
        self.assertEqual(CodexClientSettings().client_version, "0.163.0")

    def test_each_documented_limitation_is_named_in_its_docstring(self) -> None:
        # Keyword-level: each docstring must carry the section 3 limitation its row names; the words are the spec's own.
        from vidbyte.harnesses.native.codex import CodexHost
        from vidbyte.harnesses.native.codex import oneshot
        from vidbyte.lib.enums.codex import CodexPersonality, CodexReviewDelivery

        rows: tuple[tuple[str, Callable[[], str | None], tuple[str, ...]], ...] = (
            ("spawn_codex_thread (NG-20)", lambda: CodexHost.spawn_codex_thread.__doc__, ("preflight",)),
            ("wait_codex_turn (NG-18)", lambda: CodexHost.wait_codex_turn.__doc__, ("timeout",)),
            ("get_codex_turn_result (NG-5)", lambda: CodexHost.get_codex_turn_result.__doc__, ("list_codex_turns",)),
            ("interrupt_codex_turn (NG-6)", lambda: CodexHost.interrupt_codex_turn.__doc__, ("wait_codex_turn",)),
            ("track_codex_thread_usage (NG-7)", lambda: CodexHost.track_codex_thread_usage.__doc__, ("subagent",)),
            ("launch_codex_subagents (NG-8)", lambda: CodexHost.launch_codex_subagents.__doc__, ("limit",)),
            ("list_codex_threads (NG-10)", lambda: CodexHost.list_codex_threads.__doc__, ("title",)),
            ("compact_codex_thread (NG-11)", lambda: CodexHost.compact_codex_thread.__doc__, ("wait", "confirm")),
            ("delete_codex_thread (NG-12)", lambda: CodexHost.delete_codex_thread.__doc__, ("archive", "child")),
            ("read_codex_thread include_turns (S9)", lambda: CodexHost.read_codex_thread.__doc__, ("deprecat",)),
            ("CodexReviewDelivery DETACHED (S9)", lambda: CodexReviewDelivery.__doc__, ("deprecat",)),
            ("CodexPersonality (S9)", lambda: CodexPersonality.__doc__, ("0.163",)),
            ("CodexHost EC-1 and EC-2", lambda: CodexHost.__doc__, ("approval_handler",)),
        )
        for label, read, keywords in rows:
            with self.subTest(docstring=label):
                text = (read() or "").lower()
                self.assertTrue(any(keyword.lower() in text for keyword in keywords), f"{label} docstring names none of {keywords}: {text!r}")
        for name in oneshot.__all__:
            with self.subTest(one_shot=name):
                text = (getattr(oneshot, name).__doc__ or "").lower()
                self.assertIn("process", text)
                self.assertIn("loop", text)


@requires_sdk
class CodexHardeningClassificationTests(unittest.TestCase):
    """INV-4, INV-6, D-8 and D-23: which JSON-RPC errors on thread/read and turn/steer mean not found."""

    def test_thread_read_means_not_found_only_when_refused_and_steer_refusals_are_not_found(self) -> None:
        from openai_codex.errors import map_jsonrpc_error

        from vidbyte.harnesses.native.codex.errors import CodexErrorMapper
        from vidbyte.lib.enums.codex import CodexHostOperation

        overloaded = {"codexErrorInfo": "server_overloaded"}
        rows = (
            ("thread/read", -32600, None, "codex.session_not_found"),
            ("thread/read", -32602, None, "codex.session_not_found"),
            ("thread/read", -32603, None, "codex.api_error"),
            ("thread/read", -32001, overloaded, "codex.api_error"),
            ("thread/read", -32601, None, "codex.protocol_mismatch"),
            ("thread/read", -32700, None, "codex.protocol_mismatch"),
            ("turn/steer", -32600, None, "codex.session_not_found"),
            ("turn/steer", -32602, None, "codex.protocol_mismatch"),
            ("turn/steer", -32603, None, "codex.api_error"),
            # Unchanged: a refused fork point stays fork_failed (codex-host D-13).
            ("thread/fork", -32600, None, "codex.fork_failed"),
        )
        for method, code, data, expected in rows:
            with self.subTest(method=method, code=code):
                exc = map_jsonrpc_error(code, f"Codex said {code}.", data)
                error = CodexErrorMapper.from_exception(exc, CodexHostOperation.READ_CODEX_THREAD, method, dead=False, bound_seconds=300.0, thread_id="thr-1")
                self.assertEqual(error.failure_code, expected)
                self.assertEqual(error.thread_id, "thr-1")
                self.assertIs(error.retryable, expected in RETRYABLE_CODES)


if __name__ == "__main__":
    unittest.main()
