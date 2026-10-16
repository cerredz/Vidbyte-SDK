"""FILE: tests/features/codex_host/test_codex_host_sdk_contract.py

PURPOSE: Pins the openai-codex surface CodexHost reaches past the package root for, so that a pin bump which moves or renames it fails here instead of in a live run: the openai_codex.client import path the connection module binds as its test seam, the parameters of every CodexClient method in the spec's section 12.4 call list, the private goal cursor and goal state CodexGoalFinishRule and the goal watcher rely on, and the required reviewer and policy fields D-32 reads.
ROLE IN CODEBASE: Contract layer of tests/features/codex_host/ (spec D-1, D-32, NFR-8 and section 13 "SDK surface outside the public API"). Each test also binds the host module that depends on the fact, so it fails until that module exists. The class needs the optional openai-codex extra, so CI skips it.
ARCHITECTURE NOTE: The scripted fake client subclasses the real CodexClient, so it cannot notice a pin bump that renames a parameter the host passes by keyword or a private goal hook the host calls. These tests read the installed SDK directly: signatures through inspect, response fields through the generated pydantic models, and one real _GoalOperationState. Nothing starts a process.
COMMON MODIFICATION PATTERNS: When the host starts calling another CodexClient method, add its row to CALL_LIST with the parameters the host passes. When the openai-codex pin moves, rerun this file before anything else.
KNOWN EDGE CASES: A parameter the host does not pass may be added by a later SDK release as long as it has a default, so the call-list check pins the host's own parameters, their order and kind, and that no other parameter is required.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host/spec.md sections 8.1 (D-1, D-32), 12.3 rows 11 to 13, 12.4 (the S012 call list) and 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_sdk_contract.py
"""

from __future__ import annotations

import inspect
import unittest
from collections.abc import Callable
from typing import Any

from tests.features.codex_host.codex_host_support import requires_sdk

# Every CodexClient method the host calls (section 12.4 and section 13), with the parameters it passes, in order.
CALL_LIST: dict[str, tuple[str, ...]] = {
    "__init__": ("config", "approval_handler"),
    "start": (),
    "close": (),
    "initialize": (),
    "account_read": ("params",),
    "thread_start": ("params",),
    "thread_resume": ("thread_id", "params"),
    "thread_fork": ("thread_id", "params"),
    "thread_list": ("params",),
    "thread_read": ("thread_id", "include_turns"),
    "thread_set_name": ("thread_id", "name"),
    "turn_start": ("thread_id", "input_items", "params"),
    "turn_steer": ("thread_id", "expected_turn_id", "input_items"),
    "turn_interrupt": ("thread_id", "turn_id"),
    "start_goal_operation": ("thread_id", "objective"),
    "cancel_goal_operation": ("state",),
    "unregister_goal_operation": ("state",),
    "next_goal_notification": ("state",),
    "next_notification": (),
    "register_turn_notifications": ("turn_id",),
    "unregister_turn_notifications": ("turn_id",),
    "next_turn_notification": ("turn_id",),
    "request_with_retry_on_overload": ("method", "params"),
    # docs/spec/codex-host-thread-helpers/spec.md section 9.2: compact is the one new typed call.
    "thread_compact": ("thread_id",),
}

# The raw path's keyword-only arguments: the generated response model, and the single attempt for spending calls.
RAW_CALL_KEYWORDS = ("response_model", "max_attempts")

POSITIONAL_KINDS = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)


def _parameters(function: Callable[..., Any]) -> list[inspect.Parameter]:
    """Return a method's parameters without self."""
    return list(inspect.signature(function).parameters.values())[1:]


@requires_sdk
class CodexHostSdkContractTests(unittest.TestCase):
    """D-1 and NFR-8: the SDK surface the host reaches for still has the shape the host uses."""

    def test_the_connection_binds_the_client_seam_and_every_call_it_makes_still_fits(self) -> None:
        # Section 12.3 row 12: module-level "from openai_codex.client import CodexClient, CodexConfig" is the test seam.
        import openai_codex.client

        from vidbyte.harnesses.native.codex import connection

        self.assertIs(connection.CodexClient, openai_codex.client.CodexClient)
        self.assertIs(connection.CodexConfig, openai_codex.client.CodexConfig)

        # Every method in the call list takes the host's parameters in the host's order, and requires nothing else.
        for name, expected in CALL_LIST.items():
            with self.subTest(method=name):
                parameters = _parameters(getattr(openai_codex.client.CodexClient, name))
                positional = [parameter for parameter in parameters if parameter.kind in POSITIONAL_KINDS]
                self.assertEqual(tuple(parameter.name for parameter in positional[: len(expected)]), expected)
                passed = expected + RAW_CALL_KEYWORDS
                required_extras = [parameter.name for parameter in parameters if parameter.name not in passed and parameter.default is inspect.Parameter.empty]
                self.assertEqual(required_extras, [])

        # The raw path takes the response model and the attempt count by keyword only; spending calls pass one attempt.
        raw = {parameter.name: parameter for parameter in _parameters(openai_codex.client.CodexClient.request_with_retry_on_overload)}
        for keyword in RAW_CALL_KEYWORDS:
            with self.subTest(keyword=keyword):
                self.assertIn(keyword, raw)
                self.assertIs(raw[keyword].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_the_private_goal_cursor_and_goal_state_still_offer_the_hooks_the_host_calls(self) -> None:
        # Section 12.3 row 13 and INV-25: CodexGoalFinishRule mirrors _GoalStreamCursor.process, and a goal watcher ends when its read raises.
        from openai_codex import _goal
        from openai_codex.errors import TransportClosedError

        from vidbyte.harnesses.native.codex import turns

        self.assertTrue(inspect.isclass(turns.CodexGoalFinishRule))
        self.assertEqual([parameter.name for parameter in _parameters(_goal._GoalStreamCursor.process)], ["notification"])

        # The goal-stream close the host runs: finish, then wake, after which the blocked read raises at once.
        closed = _goal._GoalOperationState(thread_id="thread-contract")
        closed.finish()
        closed.wake_notification_reader()
        self.assertTrue(closed.is_finished())
        with self.assertRaises(_goal._GoalStreamClosed):
            closed.next_notification()

        # A process death fails the state, which also ends the watcher's read rather than leaving it blocked.
        failed = _goal._GoalOperationState(thread_id="thread-contract")
        failed.fail(TransportClosedError("app-server exited"))
        with self.assertRaises(TransportClosedError):
            failed.next_notification()

    def test_thread_start_and_resume_responses_still_require_the_reviewer_and_policy(self) -> None:
        # D-32: the response translator reads both fields after thread/start and thread/resume, and needs them present.
        from openai_codex.generated.v2_all import ThreadResumeResponse, ThreadStartResponse

        from vidbyte.harnesses.native.codex import wire

        self.assertTrue(inspect.isclass(wire.CodexResponseTranslator))
        for model in (ThreadStartResponse, ThreadResumeResponse):
            for field_name, alias in (("approvals_reviewer", "approvalsReviewer"), ("approval_policy", "approvalPolicy")):
                with self.subTest(model=model.__name__, field=field_name):
                    field_info = model.model_fields[field_name]
                    self.assertTrue(field_info.is_required())
                    self.assertEqual(field_info.alias, alias)


if __name__ == "__main__":
    unittest.main()
