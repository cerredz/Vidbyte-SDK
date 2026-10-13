"""FILE: tests/features/codex_host/test_codex_host_records.py

PURPOSE: Proves the lib contracts CodexHost is built on: every new record rejects bad input with a ConfigurationError naming the field, the USER reviewer is refused with the D-16 CodexAgentError, the fifteen new failure codes sit where section 12.3 puts them with their classification rows and next steps, CodexAgentError gains next_step without changing old packets, and the enums carry openai-codex's wire values.
ROLE IN CODEBASE: Contract layer of tests/features/codex_host/ (spec AC-29, AC-35, INV-26, INV-40, INV-41, EC-38, EC-63; sections 8.5, 9.1, 9.3, 12.3 rows 1, 2, 4, 5, 6). It needs no host and no openai-codex, so CI runs it; one cross-check against the SDK's generated enums is gated.
ARCHITECTURE NOTE: Each invalid-record row starts from a valid baseline and breaks one rule, so a failure names exactly the rule that did not hold. The review-target and snapshot rules are small closed domains, so they are checked exhaustively instead of by sampling.
COMMON MODIFICATION PATTERNS: When section 9.1 adds a rule, add one row to INVALID_ROWS; when an enum gains a member, add it to EXPECTED_ENUMS from the spec, never from the production module.
KNOWN EDGE CASES: A str-valued Enum compares equal to its plain string, so the wrong-type rows use values no enum member has; bool is an int subclass, so every int field has a True row.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host/spec.md sections 8.5, 9.1, 9.2 and 9.3.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_records.py
"""

from __future__ import annotations

import dataclasses
import enum
import itertools
import math
import typing
import unittest
from typing import Any

from tests.features.codex_host.codex_host_support import (
    CLASSIFICATION_ROWS,
    EXPERIMENTAL_API_TEXT,
    MINIMUM_VERSION,
    NEW_FAILURE_CODES,
    NEXT_STEPS,
    TOOL_NAMES,
    UNREGISTERED_TOOL_TEXT,
    USER_REVIEWER_TEXT,
    make_echo_tool,
    requires_sdk,
)
from vidbyte.lib.errors import CodexAgentError, ConfigurationError

# Spec section 8.5, verbatim: every new enum's members and wire values.
EXPECTED_ENUMS: dict[str, dict[str, str]] = {
    "CodexApprovalPolicy": {"PROVIDER_DEFAULT": "", "UNTRUSTED": "untrusted", "ON_REQUEST": "on-request", "NEVER": "never"},
    "CodexApprovalsReviewer": {"PROVIDER_DEFAULT": "", "USER": "user", "AUTO_REVIEW": "auto_review", "GUARDIAN_SUBAGENT": "guardian_subagent"},
    "CodexTurnStatus": {"RUNNING": "inProgress", "COMPLETED": "completed", "INTERRUPTED": "interrupted", "FAILED": "failed"},
    "CodexSandboxReadiness": {"NOT_CHECKED": "", "READY": "ready", "NOT_CONFIGURED": "notConfigured", "UPDATE_REQUIRED": "updateRequired"},
    "CodexAccountKind": {"NONE": "", "API_KEY": "apiKey", "CHATGPT": "chatgpt", "AMAZON_BEDROCK": "amazonBedrock"},
    "CodexThreadStatus": {"NOT_LOADED": "notLoaded", "IDLE": "idle", "SYSTEM_ERROR": "systemError", "ACTIVE": "active"},
    "CodexThreadSortKey": {"PROVIDER_DEFAULT": "", "CREATED_AT": "created_at", "UPDATED_AT": "updated_at", "RECENCY_AT": "recency_at", "SECTION_POSITION": "section_position"},
    "CodexSortDirection": {"PROVIDER_DEFAULT": "", "ASC": "asc", "DESC": "desc"},
    "CodexThreadSourceKind": {
        "CLI": "cli",
        "VSCODE": "vscode",
        "EXEC": "exec",
        "APP_SERVER": "appServer",
        "SUB_AGENT": "subAgent",
        "SUB_AGENT_REVIEW": "subAgentReview",
        "SUB_AGENT_COMPACT": "subAgentCompact",
        "SUB_AGENT_THREAD_SPAWN": "subAgentThreadSpawn",
        "SUB_AGENT_OTHER": "subAgentOther",
        "UNKNOWN": "unknown",
    },
    "CodexReviewTargetKind": {"UNCOMMITTED_CHANGES": "uncommittedChanges", "BASE_BRANCH": "baseBranch", "COMMIT": "commit", "CUSTOM": "custom"},
    "CodexReviewDelivery": {"INLINE": "inline", "DETACHED": "detached"},
    "CodexGoalStatus": {"NONE": "", "ACTIVE": "active", "PAUSED": "paused", "BLOCKED": "blocked", "USAGE_LIMITED": "usageLimited", "BUDGET_LIMITED": "budgetLimited", "COMPLETE": "complete"},
    "CodexHostOperation": {"OPEN_HOST": "open_host", "VALIDATE_SPAWN_REQUEST": "validate_spawn_request", **{name.upper(): name for name in TOOL_NAMES}},
}

# The openai-codex 0.162.1 generated type each spec enum mirrors, and how its wire values are read.
SDK_WIRE_SOURCES = {
    "CodexApprovalPolicy": ("AskForApprovalValue", "enum"),
    "CodexApprovalsReviewer": ("ApprovalsReviewer", "enum"),
    "CodexTurnStatus": ("TurnStatus", "enum"),
    "CodexSandboxReadiness": ("WindowsSandboxReadiness", "enum"),
    "CodexAccountKind": ("Account", "tags"),
    "CodexThreadStatus": ("ThreadStatus", "tags"),
    "CodexThreadSortKey": ("ThreadSortKey", "enum"),
    "CodexSortDirection": ("SortDirection", "enum"),
    "CodexThreadSourceKind": ("ThreadSourceKind", "enum"),
    "CodexReviewTargetKind": ("ReviewTarget", "tags"),
    "CodexReviewDelivery": ("ReviewDelivery", "enum"),
    "CodexGoalStatus": ("ThreadGoalStatus", "enum"),
}

RECORD_NAMES = (
    "CodexGoal",
    "CodexModelInfo",
    "CodexProblem",
    "CodexRateLimitWindow",
    "CodexRateLimits",
    "CodexReadiness",
    "CodexReviewTarget",
    "CodexSpawnRequest",
    "CodexThreadInfo",
    "CodexThreadPage",
    "CodexThreadUsage",
    "CodexTurnHandle",
    "CodexTurnSnapshot",
    "CodexTurnSummary",
    "CodexTurnUsage",
)

LEGACY_REPAIR = ("Inspect the operation and chained exception, then correct the matching Codex settings or runtime state.",)


class _ContextText:
    """A context item: CodexRunInput accepts it, and CodexSpawnRequest must refuse it (section 9.1)."""

    def to_context_text(self) -> str:
        return "Background the request must not carry."


def _valid_kwargs() -> dict[str, dict[str, Any]]:
    """One valid baseline per record; each invalid row below breaks exactly one rule of one baseline."""
    from vidbyte.lib.dataclasses.codex import CodexUsage
    from vidbyte.lib.dataclasses.codex_host import CodexRateLimitWindow, CodexThreadInfo, CodexTurnHandle, CodexTurnSummary, CodexTurnUsage
    from vidbyte.lib.enums.codex import CodexAccountKind, CodexReviewTargetKind, CodexSandboxReadiness, CodexThreadStatus, CodexTurnStatus
    from vidbyte.lib.enums.failure import FailureCode

    handle = CodexTurnHandle(thread_id="thr-1", turn_id="turn-1")
    window = CodexRateLimitWindow(used_percent=42, resets_at=1_760_003_600, window_minutes=300)
    summary = CodexTurnSummary(turn_id="turn-1", status=CodexTurnStatus.COMPLETED, final_response="Done.", error_message="", started_at=1_760_000_000, completed_at=1_760_000_005)
    info = CodexThreadInfo(
        thread_id="thr-1",
        name="",
        preview="Summarize the readme.",
        cwd="workspace",
        status=CodexThreadStatus.IDLE,
        model="gpt-5.5",
        model_provider="openai",
        created_at=1_760_000_000,
        updated_at=1_760_000_060,
        forked_from_id="",
        ephemeral=False,
        turns=(summary,),
    )
    usage = CodexUsage(input_tokens=300, output_tokens=60, total_tokens=360)
    turn_usage = CodexTurnUsage(turn_id="turn-1", status=CodexTurnStatus.COMPLETED, usage=usage, usage_available=True)
    return {
        "CodexGoal": {"objective": "Ship the fix.", "token_budget": 5000},
        "CodexSpawnRequest": {"prompt": "Summarize the readme."},
        "CodexTurnHandle": {"thread_id": "thr-1", "turn_id": "turn-1"},
        "CodexProblem": {"code": FailureCode.CODEX_FORK_FAILED, "message": "The thread has no completed turn.", "next_step": NEXT_STEPS["codex.fork_failed"]},
        "CodexTurnSnapshot": {"handle": handle, "status": CodexTurnStatus.RUNNING},
        "CodexReadiness": {
            "ready": True,
            "version": "0.162.1",
            "minimum_version": MINIMUM_VERSION,
            "signed_in": True,
            "account": CodexAccountKind.CHATGPT,
            "plan_type": "plus",
            "sandbox": CodexSandboxReadiness.READY,
            "problems": (),
        },
        "CodexRateLimitWindow": {"used_percent": 42, "resets_at": 1_760_003_600, "window_minutes": 300},
        "CodexRateLimits": {"ordinary_usage_allowed": True, "plan_type": "plus", "limit_reached": "", "primary": window, "secondary": None},
        "CodexModelInfo": {
            "model_id": "gpt-5.5",
            "model": "gpt-5.5",
            "display_name": "GPT-5.5",
            "description": "Frontier model.",
            "hidden": False,
            "is_default": True,
            "default_effort": "medium",
            "efforts": ("low", "medium", "max"),
        },
        "CodexTurnSummary": {"turn_id": "turn-1", "status": CodexTurnStatus.COMPLETED, "final_response": "Done.", "error_message": "", "started_at": 1_760_000_000, "completed_at": 1_760_000_005},
        "CodexThreadInfo": {field.name: getattr(info, field.name) for field in dataclasses.fields(info)},
        "CodexThreadPage": {"threads": (info,), "next_cursor": ""},
        "CodexTurnUsage": {"turn_id": "turn-1", "status": CodexTurnStatus.COMPLETED, "usage": usage, "usage_available": True},
        "CodexThreadUsage": {"thread_id": "thr-1", "total": usage, "turns": (turn_usage,), "cost_usd": 0.0033, "cost_complete": True},
        "CodexReviewTarget": {"kind": CodexReviewTargetKind.COMMIT, "sha": "abc1234"},
    }


def _invalid_rows() -> list[tuple[str, dict[str, Any], tuple[str, ...]]]:
    """(record, fields that break one rule, field names the message may name)."""
    from vidbyte.lib.dataclasses.codex import CodexRunInput, CodexTextInput, CodexThreadSettings, CodexTurnSettings, CodexUsage
    from vidbyte.lib.dataclasses.codex_host import CodexGoal, CodexProblem, CodexTurnHandle, CodexTurnSummary
    from vidbyte.lib.enums.codex import CodexApprovalMode, CodexApprovalPolicy, CodexApprovalsReviewer, CodexThreadStatus, CodexTurnStatus
    from vidbyte.lib.enums.failure import FailureCode

    problem = CodexProblem(code=FailureCode.CODEX_FORK_FAILED, message="No completed turn.", next_step=NEXT_STEPS["codex.fork_failed"])
    summary = CodexTurnSummary(turn_id="turn-1", status=CodexTurnStatus.COMPLETED, final_response="Done.", error_message="", started_at=None, completed_at=None)
    context_prompt = CodexRunInput(items=(CodexTextInput(text="hi"),), context_items=(_ContextText(),))
    approvals = ("approval_mode", "approval_policy", "approvals_reviewer")
    return [
        ("CodexGoal", {"objective": ""}, ("objective",)),
        ("CodexGoal", {"objective": 7}, ("objective",)),
        ("CodexGoal", {"token_budget": 0}, ("token_budget",)),
        ("CodexGoal", {"token_budget": True}, ("token_budget",)),
        ("CodexGoal", {"token_budget": 10.0}, ("token_budget",)),
        ("CodexGoal", {"token_budget": math.nan}, ("token_budget",)),
        ("CodexSpawnRequest", {"prompt": 42}, ("prompt",)),
        ("CodexSpawnRequest", {"prompt": context_prompt}, ("prompt",)),
        ("CodexSpawnRequest", {"thread": "read-only"}, ("thread",)),
        ("CodexSpawnRequest", {"turn": {}}, ("turn",)),
        ("CodexSpawnRequest", {"subagents": "on"}, ("subagents",)),
        ("CodexSpawnRequest", {"developer_instructions": 3}, ("developer_instructions",)),
        ("CodexSpawnRequest", {"name": 3}, ("name",)),
        ("CodexSpawnRequest", {"approval_policy": "sometimes"}, ("approval_policy",)),
        ("CodexSpawnRequest", {"approvals_reviewer": "someone"}, ("approvals_reviewer",)),
        ("CodexSpawnRequest", {"approval_policy": CodexApprovalPolicy.ON_REQUEST, "thread": CodexThreadSettings(approval_mode=CodexApprovalMode.AUTO_REVIEW)}, approvals),
        ("CodexSpawnRequest", {"approvals_reviewer": CodexApprovalsReviewer.AUTO_REVIEW, "turn": CodexTurnSettings(approval_mode=CodexApprovalMode.DENY_ALL)}, approvals),
        ("CodexSpawnRequest", {"tools": ("not a tool",)}, ("tools",)),
        ("CodexSpawnRequest", {"tools": [make_echo_tool()]}, ("tools",)),
        ("CodexSpawnRequest", {"tool_permission_policy": "read"}, ("tool_permission_policy",)),
        ("CodexSpawnRequest", {"disabled_plugin_ids": ("",)}, ("disabled_plugin_ids",)),
        ("CodexSpawnRequest", {"disabled_plugin_ids": ["plugin-a"]}, ("disabled_plugin_ids",)),
        ("CodexSpawnRequest", {"output_schema": 5}, ("output_schema",)),
        ("CodexSpawnRequest", {"goal": "Ship the fix."}, ("goal",)),
        ("CodexSpawnRequest", {"prompt": "Fix it.", "goal": CodexGoal(objective="Ship the fix.")}, ("goal", "prompt")),
        # EC-38: a goal on an ephemeral thread fails at construction, naming goal.
        ("CodexSpawnRequest", {"prompt": "", "goal": CodexGoal(objective="Ship the fix."), "thread": CodexThreadSettings(ephemeral=True)}, ("goal",)),
        ("CodexSpawnRequest", {"max_output_tokens": 0}, ("max_output_tokens",)),
        ("CodexSpawnRequest", {"max_output_tokens": True}, ("max_output_tokens",)),
        ("CodexSpawnRequest", {"max_output_tokens": 2.5}, ("max_output_tokens",)),
        ("CodexSpawnRequest", {"timeout_seconds": 0}, ("timeout_seconds",)),
        ("CodexSpawnRequest", {"timeout_seconds": -1.0}, ("timeout_seconds",)),
        ("CodexSpawnRequest", {"timeout_seconds": math.nan}, ("timeout_seconds",)),
        ("CodexSpawnRequest", {"timeout_seconds": math.inf}, ("timeout_seconds",)),
        ("CodexSpawnRequest", {"timeout_seconds": True}, ("timeout_seconds",)),
        ("CodexSpawnRequest", {"timeout_seconds": "30"}, ("timeout_seconds",)),
        ("CodexTurnHandle", {"thread_id": ""}, ("thread_id",)),
        ("CodexTurnHandle", {"turn_id": "   "}, ("turn_id",)),
        ("CodexTurnHandle", {"thread_id": 5}, ("thread_id",)),
        ("CodexProblem", {"code": "not.a.code"}, ("code",)),
        ("CodexProblem", {"message": ""}, ("message",)),
        ("CodexProblem", {"next_step": ""}, ("next_step",)),
        ("CodexTurnSnapshot", {"handle": "thr-1/turn-1"}, ("handle",)),
        ("CodexTurnSnapshot", {"status": 3}, ("status",)),
        ("CodexTurnSnapshot", {"goal_status": "done"}, ("goal_status",)),
        ("CodexTurnSnapshot", {"problem": "busy"}, ("problem", "status")),
        ("CodexReadiness", {"ready": False}, ("ready", "problems")),
        ("CodexReadiness", {"problems": (problem,)}, ("ready", "problems")),
        ("CodexReadiness", {"ready": False, "problems": [problem]}, ("problems",)),
        ("CodexReadiness", {"minimum_version": ""}, ("minimum_version",)),
        ("CodexReadiness", {"version": 5}, ("version",)),
        ("CodexReadiness", {"signed_in": "yes"}, ("signed_in",)),
        ("CodexReadiness", {"account": 1}, ("account",)),
        ("CodexReadiness", {"sandbox": 1}, ("sandbox",)),
        ("CodexRateLimitWindow", {"used_percent": -1}, ("used_percent",)),
        ("CodexRateLimitWindow", {"used_percent": True}, ("used_percent",)),
        ("CodexRateLimitWindow", {"used_percent": 4.2}, ("used_percent",)),
        ("CodexRateLimitWindow", {"resets_at": -1}, ("resets_at",)),
        ("CodexRateLimitWindow", {"window_minutes": True}, ("window_minutes",)),
        ("CodexRateLimits", {"ordinary_usage_allowed": "yes"}, ("ordinary_usage_allowed",)),
        ("CodexRateLimits", {"plan_type": None}, ("plan_type",)),
        ("CodexRateLimits", {"limit_reached": 5}, ("limit_reached",)),
        ("CodexRateLimits", {"primary": {"used_percent": 1}}, ("primary",)),
        ("CodexRateLimits", {"secondary": "weekly"}, ("secondary",)),
        ("CodexModelInfo", {"model_id": ""}, ("model_id",)),
        ("CodexModelInfo", {"model": ""}, ("model",)),
        ("CodexModelInfo", {"display_name": None}, ("display_name",)),
        ("CodexModelInfo", {"hidden": "no"}, ("hidden",)),
        ("CodexModelInfo", {"is_default": 1}, ("is_default",)),
        ("CodexModelInfo", {"efforts": ["low"]}, ("efforts",)),
        ("CodexModelInfo", {"efforts": ("low", 5)}, ("efforts",)),
        ("CodexTurnSummary", {"turn_id": ""}, ("turn_id",)),
        ("CodexTurnSummary", {"status": 2}, ("status",)),
        ("CodexTurnSummary", {"final_response": None}, ("final_response",)),
        ("CodexTurnSummary", {"started_at": -1}, ("started_at",)),
        ("CodexTurnSummary", {"completed_at": True}, ("completed_at",)),
        ("CodexThreadInfo", {"thread_id": ""}, ("thread_id",)),
        ("CodexThreadInfo", {"status": 0}, ("status",)),
        ("CodexThreadInfo", {"created_at": -5}, ("created_at",)),
        ("CodexThreadInfo", {"updated_at": True}, ("updated_at",)),
        ("CodexThreadInfo", {"ephemeral": "no"}, ("ephemeral",)),
        ("CodexThreadInfo", {"turns": [summary]}, ("turns",)),
        ("CodexThreadInfo", {"turns": ("turn-1",)}, ("turns",)),
        ("CodexThreadPage", {"threads": ["thr-1"]}, ("threads",)),
        ("CodexThreadPage", {"threads": ("thr-1",)}, ("threads",)),
        ("CodexThreadPage", {"next_cursor": None}, ("next_cursor",)),
        ("CodexTurnUsage", {"turn_id": ""}, ("turn_id",)),
        ("CodexTurnUsage", {"status": 1}, ("status",)),
        ("CodexTurnUsage", {"usage": {"input_tokens": 1}}, ("usage",)),
        ("CodexTurnUsage", {"usage_available": 1}, ("usage_available",)),
        ("CodexThreadUsage", {"thread_id": ""}, ("thread_id",)),
        ("CodexThreadUsage", {"total": None}, ("total",)),
        ("CodexThreadUsage", {"turns": [CodexUsage()]}, ("turns",)),
        ("CodexThreadUsage", {"cost_usd": -0.01}, ("cost_usd",)),
        ("CodexThreadUsage", {"cost_usd": math.nan}, ("cost_usd",)),
        ("CodexThreadUsage", {"cost_usd": math.inf}, ("cost_usd",)),
        ("CodexThreadUsage", {"cost_usd": True}, ("cost_usd",)),
        ("CodexThreadUsage", {"cost_complete": "yes"}, ("cost_complete",)),
        ("CodexReviewTarget", {"kind": 3}, ("kind",)),
        ("CodexTurnSnapshot", {"handle": CodexTurnHandle(thread_id="thr-1", turn_id="turn-1"), "status": CodexThreadStatus.IDLE}, ("status",)),
    ]


def _sdk_wire_values(type_name: str, mode: str) -> set[str]:
    """The wire values openai-codex 0.162.1 declares for one generated enum or tagged union."""
    import openai_codex.generated.v2_all as generated

    declared = getattr(generated, type_name)
    if mode == "enum":
        return {member.value for member in declared}
    tags: set[str] = set()
    for arm in typing.get_args(declared.model_fields["root"].annotation):
        tags.update(typing.get_args(arm.model_fields["type"].annotation))
    return tags


class CodexHostRecordValidationTests(unittest.TestCase):
    """Section 9.1: each record validates itself, with ConfigurationError naming the field."""

    def test_valid_baselines_construct_frozen_slotted_records(self) -> None:
        from vidbyte.lib.dataclasses import codex_host

        for name, kwargs in _valid_kwargs().items():
            with self.subTest(record=name):
                record_type = getattr(codex_host, name)
                record = record_type(**kwargs)
                self.assertTrue(dataclasses.is_dataclass(record))
                self.assertTrue(record_type.__dataclass_params__.frozen)
                self.assertIn("__slots__", record_type.__dict__)
        self.assertEqual(set(_valid_kwargs()), set(RECORD_NAMES))

    # AC-35, INV-26: one broken rule at a time; the message names the field.
    def test_each_invalid_record_raises_configuration_error_naming_the_field(self) -> None:
        from vidbyte.lib.dataclasses import codex_host

        baselines = _valid_kwargs()
        for name, broken, fields in _invalid_rows():
            with self.subTest(record=name, broken=broken):
                kwargs = {**baselines[name], **broken}
                with self.assertRaises(ConfigurationError) as caught:
                    getattr(codex_host, name)(**kwargs)
                message = caught.exception.message
                self.assertTrue(any(field in message for field in fields), f"{message!r} names none of {fields}")

    # AC-35, EC-63, D-16: the one exception to the error type.
    def test_user_reviewer_is_refused_when_any_spawn_request_is_built(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
        from vidbyte.lib.enums.codex import CodexApprovalsReviewer

        # A request, and the empty-prompt shape that overrides and spawn_defaults use.
        for prompt in ("Fix the failing test.", ""):
            with self.subTest(prompt=prompt):
                with self.assertRaises(CodexAgentError) as caught:
                    CodexSpawnRequest(prompt=prompt, approvals_reviewer=CodexApprovalsReviewer.USER)
                error = caught.exception
                self.assertEqual(error.failure_code, "configuration.unsupported_combination")
                self.assertEqual(error.operation, "validate_spawn_request")
                self.assertEqual(error.next_step, USER_REVIEWER_TEXT)
                self.assertIn("approvals_reviewer", error.message)

    def test_review_target_fields_follow_their_kind_exhaustively(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexReviewTarget
        from vidbyte.lib.enums.codex import CodexReviewTargetKind as Kind

        allowed = {
            Kind.UNCOMMITTED_CHANGES: {frozenset()},
            Kind.BASE_BRANCH: {frozenset({"branch"})},
            Kind.COMMIT: {frozenset({"sha"}), frozenset({"sha", "title"})},
            Kind.CUSTOM: {frozenset({"instructions"})},
        }
        names = ("branch", "sha", "title", "instructions")
        for kind in Kind:
            for size in range(len(names) + 1):
                for chosen in itertools.combinations(names, size):
                    values = {name: f"{name}-value" for name in chosen}
                    with self.subTest(kind=kind.value, fields=chosen):
                        if frozenset(chosen) in allowed[kind]:
                            self.assertEqual(CodexReviewTarget(kind=kind, **values).kind, kind)
                        else:
                            with self.assertRaises(ConfigurationError):
                                CodexReviewTarget(kind=kind, **values)

    def test_snapshot_status_result_and_problem_rule_exhaustively(self) -> None:
        from vidbyte.lib.dataclasses.codex import CodexRunResult, CodexUsage
        from vidbyte.lib.dataclasses.codex_host import CodexProblem, CodexTurnHandle, CodexTurnSnapshot
        from vidbyte.lib.enums.codex import CodexTurnStatus as Status
        from vidbyte.lib.enums.failure import FailureCode

        handle = CodexTurnHandle(thread_id="thr-1", turn_id="turn-1")
        problem = CodexProblem(code=FailureCode.CODEX_API_ERROR, message="Codex failed.", next_step=NEXT_STEPS["codex.api_error"])
        # RUNNING has neither; COMPLETED needs a result; FAILED needs a problem; INTERRUPTED takes any.
        valid = {
            Status.RUNNING: {(False, False)},
            Status.COMPLETED: {(True, False), (True, True)},
            Status.FAILED: {(False, True), (True, True)},
            Status.INTERRUPTED: {(False, False), (True, False), (False, True), (True, True)},
        }
        for status in Status:
            result = CodexRunResult(thread_id="thr-1", turn_id="turn-1", status=status.value, final_response="Done.", duration_ms=10, usage=CodexUsage(), items=())
            for has_result, has_problem in itertools.product((False, True), repeat=2):
                fields = {"result": result if has_result else None, "problem": problem if has_problem else None}
                with self.subTest(status=status.value, result=has_result, problem=has_problem):
                    if (has_result, has_problem) in valid[status]:
                        self.assertEqual(CodexTurnSnapshot(handle=handle, status=status, **fields).status, status)
                    else:
                        with self.assertRaises(ConfigurationError):
                            CodexTurnSnapshot(handle=handle, status=status, **fields)


class CodexHostErrorContractTests(unittest.TestCase):
    """Sections 9.2, 9.3 and 12.3 rows 1, 4 and 5: codes, rows, next steps and constants."""

    # AC-29: 15 members, in order, right after CODEX_RUN_OPTION_UNSUPPORTED.
    def test_new_failure_codes_sit_right_after_run_option_unsupported(self) -> None:
        from vidbyte.lib.enums.failure import FailureCode

        members = list(FailureCode)
        start = members.index(FailureCode.CODEX_RUN_OPTION_UNSUPPORTED) + 1
        placed = [(member.name, member.value) for member in members[start : start + len(NEW_FAILURE_CODES)]]
        self.assertEqual(placed, list(NEW_FAILURE_CODES))

    # AC-29, INV-40: one classification row each, and the exact next-step table.
    def test_each_new_code_has_its_classification_row_and_next_step(self) -> None:
        from vidbyte.lib.constants.codex import CODEX_FAILURE_CLASSIFICATION, CODEX_NEXT_STEPS

        for value, row in CLASSIFICATION_ROWS.items():
            with self.subTest(code=value):
                self.assertEqual(tuple(CODEX_FAILURE_CLASSIFICATION[value]), row)
        self.assertEqual(dict(CODEX_NEXT_STEPS), NEXT_STEPS)

    def test_section_9_3_constants_hold_their_spec_values(self) -> None:
        from vidbyte.lib.constants import codex as constants

        expected = {
            "CODEX_HOST_REQUEST_TIMEOUT_SECONDS": 300.0,
            "CODEX_HOST_TOOL_MAX_WAIT_SECONDS": 240.0,
            "CODEX_HOST_WORKER_THREADS": 32,
            "CODEX_HOST_CLOSE_INTERRUPT_SECONDS": 5.0,
            "CODEX_HOST_CLOSE_WAIT_SECONDS": 10.0,
            "CODEX_HOST_EXPERIMENTAL_API_TEXT": EXPERIMENTAL_API_TEXT,
            "CODEX_HOST_USER_REVIEWER_TEXT": USER_REVIEWER_TEXT,
            "CODEX_HOST_MINIMUM_VERSION": MINIMUM_VERSION,
            "CODEX_HOST_BINARY_NAME": "codex",
            "CODEX_HOST_SINGLE_ATTEMPT": 1,
            "CODEX_HOST_MIN_LIVE_TURNS": 1,
            "CODEX_HOST_MIN_TOKEN_LIMIT": 1,
            "CODEX_HOST_MIN_EXCLUSIVE_SECONDS": 0.0,
            "CODEX_HOST_DEFAULT_APPROVAL_MODE": "auto_review",
            "CODEX_RATE_LIMITS_READ_METHOD": "account/rateLimits/read",
            "CODEX_SANDBOX_READINESS_METHOD": "windowsSandbox/readiness",
            "CODEX_REVIEW_START_METHOD": "review/start",
            "CODEX_GOAL_SET_METHOD": "thread/goal/set",
            "CODEX_MODEL_LIST_METHOD": "model/list",
            "CODEX_TURN_STARTED_NOTIFICATION": "turn/started",
            "CODEX_TURN_COMPLETED_NOTIFICATION": "turn/completed",
            "CODEX_ITEM_COMPLETED_NOTIFICATION": "item/completed",
            "CODEX_USAGE_UPDATED_NOTIFICATION": "thread/tokenUsage/updated",
            "CODEX_GOAL_UPDATED_NOTIFICATION": "thread/goal/updated",
            "CODEX_GOAL_CLEARED_NOTIFICATION": "thread/goal/cleared",
            "CODEX_APPROVAL_ACCEPT_DECISION": "accept",
            "CODEX_UNREGISTERED_TOOL_TEXT": UNREGISTERED_TOOL_TEXT,
        }
        for name, value in expected.items():
            with self.subTest(constant=name):
                self.assertEqual(getattr(constants, name), value)
                self.assertIn(name, constants.__all__)
        self.assertEqual(
            {key: tuple(pair) for key, pair in constants.CODEX_APPROVAL_MODE_WIRE.items()},
            {"auto_review": ("on-request", "auto_review"), "deny_all": ("never", "")},
        )
        self.assertEqual(set(constants.CODEX_ACCEPTED_APPROVAL_METHODS), {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"})
        # D-3 and D-31: the request bound is the bridge bound, and the tool wait clamp stays strictly below it.
        self.assertEqual(constants.CODEX_HOST_REQUEST_TIMEOUT_SECONDS, constants.CODEX_TOOL_CALL_TIMEOUT_SECONDS)
        self.assertLess(constants.CODEX_HOST_TOOL_MAX_WAIT_SECONDS, constants.CODEX_TOOL_CALL_TIMEOUT_SECONDS)

    # INV-41, D-14: next_step becomes the single repair approach; old calls keep their packet.
    def test_next_step_is_the_repair_approach_and_old_calls_keep_their_packet(self) -> None:
        busy = NEXT_STEPS["codex.session_busy"]
        error = CodexAgentError("Thread thr-1 is running a turn.", failure_code="codex.session_busy", operation="continue_codex_thread", next_step=busy)
        self.assertEqual(error.next_step, busy)
        self.assertEqual(tuple(error.repair_approaches), (busy,))
        self.assertEqual(tuple(error.details["repair_approaches"]), (busy,))

        legacy = CodexAgentError("Turn failed.", failure_code="codex.turn_failed", operation="run")
        self.assertEqual(legacy.next_step, "")
        self.assertEqual(
            legacy.details,
            {
                "error_kind": "codex.turn_failed",
                "expected": "Codex adapter operation 'run' completing successfully",
                "actual": "Turn failed.",
                "safe_runtime_details": {"operation": "run", "error_type": ""},
                "likely_causes": ("The Codex SDK rejected input, failed a lifecycle operation, or returned an invalid result.",),
                "repair_approaches": LEGACY_REPAIR,
                "related_docs": ("https://developers.openai.com/codex/sdk", "https://developers.openai.com/codex/app-server"),
                "relevant_tests": ("python scripts/run_ci.py",),
            },
        )
        self.assertEqual(
            CodexAgentError.DIAGNOSTIC_FIELDS,
            ("error_kind", "expected", "actual", "safe_runtime_details", "likely_causes", "repair_approaches", "related_docs", "relevant_tests"),
        )


class CodexHostEnumTests(unittest.TestCase):
    """Section 8.5 and 9.1: the thirteen new enums are str enums with wire-exact values."""

    def test_new_enums_have_exactly_the_spec_members_and_values(self) -> None:
        from vidbyte.lib.enums import codex as codex_enums

        for name, members in EXPECTED_ENUMS.items():
            with self.subTest(enum=name):
                declared = getattr(codex_enums, name)
                self.assertTrue(issubclass(declared, str) and issubclass(declared, enum.Enum))
                self.assertEqual({member.name: member.value for member in declared}, members)

    @requires_sdk
    def test_wire_values_match_openai_codex(self) -> None:
        from vidbyte.lib.enums import codex as codex_enums

        for name, (type_name, mode) in SDK_WIRE_SOURCES.items():
            with self.subTest(enum=name, sdk_type=type_name):
                ours = {member.value for member in getattr(codex_enums, name)} - {""}
                self.assertEqual(ours, _sdk_wire_values(type_name, mode))


if __name__ == "__main__":
    unittest.main()
