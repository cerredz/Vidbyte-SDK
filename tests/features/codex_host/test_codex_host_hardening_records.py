"""FILE: tests/features/codex_host/test_codex_host_hardening_records.py

PURPOSE: Proves the lib records and enums the codex-host-hardening slice adds: the three server-request enums and the new CodexReasoningEffort and CodexHostOperation members in their spec order; the six wire-mirroring records (CodexServiceTier, CodexUserInputOption, CodexUserInputQuestion, CodexServerRequest, CodexUserInputAnswer, CodexServerAnswer), frozen, slotted and refusing bad input; CodexServerRequest.from_params mapping the 0.163.0 wire, absent and null values included, and refusing what spec EC-4 calls a parse failure; the new CodexSpawnRequest fields with the network-access, writable-roots and goal rules; and the CodexModelInfo tier fields.
ROLE IN CODEBASE: Record layer of the hardening tests in tests/features/codex_host/ (docs/spec/codex-host-hardening/spec.md AC-29, AC-31, AC-32, INV-34 to INV-37, EC-4 to EC-6, EC-37, EC-38, D-4, D-15, sections 8.5 and 9.1). It needs no host and no openai-codex, so CI runs it.
ARCHITECTURE NOTE: Every feature name is imported inside the test that uses it, so before the slice lands each test fails on its own missing name while the module still collects. Each invalid row starts from a valid baseline and breaks one rule, so a failure names exactly the rule that did not hold. Expected values are the spec's literals, never read from the production module.
COMMON MODIFICATION PATTERNS: A new section 9.1 rule adds one row to the matching table; a new wire key adds one entry to the from_params tables with the record it must produce.
KNOWN EDGE CASES: A str-valued Enum equals its plain string, so wrong-type rows use values no member has. bool is an int subclass, so startedAtMs has a True row. The spec leaves open whether the goal rule or the sandbox rule refuses a goal request that sets network_access or writable_roots first, so those two rows assert only that the refusal names the field (S2 report, spec defects).
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-hardening/spec.md sections 6.1, 8.5 and 9.1.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_hardening_records.py
"""

from __future__ import annotations

import dataclasses
import os
import unittest
from collections.abc import Callable
from typing import Any

from tests.features.codex_host.codex_host_support import GOAL_FIELD_MESSAGE, GOAL_REJECTED_FIELDS, NETWORK_ACCESS_MESSAGE, WRITABLE_ROOTS_MESSAGE
from vidbyte.lib.errors import ConfigurationError

WORKSPACE = os.path.abspath(os.path.join(os.sep, "hardening-workspace"))
GRANT_ROOT = os.path.abspath(os.path.join(os.sep, "hardening-workspace", "src"))
STARTED_AT_MS = 1_760_000_000_123
# The part of CODEX_HOST_NETWORK_ACCESS_MESSAGE before its {sandbox} slot; the spec does not say whether the slot shows
# the member name or its wire value, so the rows check the prefix and that one of the two follows.
NETWORK_ACCESS_PREFIX = NETWORK_ACCESS_MESSAGE.split("{sandbox}")[0]

# docs/spec/codex-host-hardening/spec.md section 8.5, verbatim: members, values and order.
EXPECTED_NEW_ENUMS: dict[str, list[tuple[str, str]]] = {
    "CodexServerRequestKind": [
        ("COMMAND_EXECUTION", "item/commandExecution/requestApproval"),
        ("FILE_CHANGE", "item/fileChange/requestApproval"),
        ("USER_INPUT", "item/tool/requestUserInput"),
    ],
    "CodexApprovalDecision": [("ACCEPT", "accept"), ("ACCEPT_FOR_SESSION", "acceptForSession"), ("DECLINE", "decline"), ("CANCEL", "cancel")],
    "CodexCommandApprovalKind": [("COMMAND", "command"), ("WRITE_STDIN", "writeStdin")],
}
# INV-35: MAX and ULTRA follow XHIGH; every older member keeps its value and place.
EXPECTED_EFFORTS = [
    ("PROVIDER_DEFAULT", ""),
    ("NONE", "none"),
    ("MINIMAL", "minimal"),
    ("LOW", "low"),
    ("MEDIUM", "medium"),
    ("HIGH", "high"),
    ("XHIGH", "xhigh"),
    ("MAX", "max"),
    ("ULTRA", "ultra"),
]


def _codex_host() -> Any:
    from vidbyte.lib.dataclasses import codex_host

    return codex_host


def _enums() -> Any:
    from vidbyte.lib.enums import codex

    return codex


def _command_params(**changes: Any) -> dict[str, Any]:
    """A command approval with every field the 0.163.0 wire sends, plus keys the record does not mirror."""
    params: dict[str, Any] = {
        "threadId": "thr-1",
        "turnId": "turn-1",
        "itemId": "item-1",
        "approvalId": "approval-1",
        "environmentId": "env-1",
        "kind": "writeStdin",
        "startedAtMs": STARTED_AT_MS,
        "reason": "The agent wants to type into the running shell.",
        "command": "git status",
        "cwd": WORKSPACE,
        "availableDecisions": ["accept", "acceptForSession", {"acceptWithExecpolicyAmendment": {"execpolicyAmendment": ["git", "status"]}}, "decline", "cancel"],
        "commandActions": [{"type": "unknown", "command": "git status"}],
        "networkApprovalContext": None,
        "someFutureKey": {"nested": True},
    }
    params.update(changes)
    return params


def _ids(**changes: Any) -> dict[str, Any]:
    params: dict[str, Any] = {"threadId": "thr-1", "turnId": "turn-1", "itemId": "item-1"}
    params.update(changes)
    return params


class CodexHardeningEnumTests(unittest.TestCase):
    """Section 8.5, INV-22 and INV-35: the new enums, members and their order."""

    def test_the_three_server_request_enums_have_exactly_the_spec_members_in_order(self) -> None:
        enums = _enums()
        for name, members in EXPECTED_NEW_ENUMS.items():
            with self.subTest(enum=name):
                enum_type = getattr(enums, name)
                self.assertEqual([(member.name, member.value) for member in enum_type], members)
                self.assertTrue(issubclass(enum_type, str))
                # Placement rule: every public enum is exported from vidbyte.lib.enums.
                from vidbyte.lib import enums as package

                self.assertIs(getattr(package, name), enum_type)

    def test_max_and_ultra_follow_xhigh_and_forget_follows_track_usage(self) -> None:
        from vidbyte.lib.enums.codex import CodexHostOperation, CodexReasoningEffort

        self.assertEqual([(member.name, member.value) for member in CodexReasoningEffort], EXPECTED_EFFORTS)
        operations = [member.name for member in CodexHostOperation]
        self.assertEqual(CodexHostOperation.FORGET_CODEX_TURNS.value, "forget_codex_turns")
        self.assertEqual(operations.index("FORGET_CODEX_TURNS"), operations.index("TRACK_CODEX_THREAD_USAGE") + 1)
        self.assertLess(operations.index("FORGET_CODEX_TURNS"), operations.index("START_CODEX_REVIEW"))


class CodexServerRecordTests(unittest.TestCase):
    """Section 9.1: the six wire-mirroring records construct frozen and slotted, and refuse bad input."""

    def _valid(self) -> dict[str, Callable[[], Any]]:
        records = _codex_host()
        enums = _enums()
        option = records.CodexUserInputOption(label="yes")
        question = records.CodexUserInputQuestion(question_id="q1", header="Deploy", question="Ship it?", options=(option,))
        return {
            "CodexServiceTier": lambda: records.CodexServiceTier(tier_id="fast"),
            "CodexUserInputOption": lambda: records.CodexUserInputOption(label="yes", description="Ship now."),
            "CodexUserInputQuestion": lambda: question,
            "CodexServerRequest": lambda: records.CodexServerRequest(kind=enums.CodexServerRequestKind.USER_INPUT, thread_id="thr-1", turn_id="turn-1", item_id="item-1", questions=(question,)),
            "CodexUserInputAnswer": lambda: records.CodexUserInputAnswer(question_id="q1", answers=("yes",)),
            "CodexServerAnswer": lambda: records.CodexServerAnswer(decision=enums.CodexApprovalDecision.ACCEPT, answers=(records.CodexUserInputAnswer(question_id="q1", answers=("yes",)),)),
        }

    def test_each_record_has_its_defaults_and_is_frozen_and_slotted(self) -> None:
        records = _codex_host()
        enums = _enums()
        for name, factory in self._valid().items():
            with self.subTest(record=name):
                record = factory()
                self.assertIn(name, records.__all__)
                self.assertTrue(type(record).__dataclass_params__.frozen)
                self.assertIn("__slots__", type(record).__dict__)
                first = dataclasses.fields(record)[0].name
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    setattr(record, first, getattr(record, first))
        self.assertEqual((records.CodexServiceTier(tier_id="fast").name, records.CodexServiceTier(tier_id="fast").description), ("", ""))
        self.assertEqual(records.CodexUserInputOption(label="yes").description, "")
        bare = records.CodexUserInputQuestion(question_id="q1", header="", question="")
        self.assertEqual((bare.options, bare.is_other, bare.is_secret), ((), False, False))
        request = records.CodexServerRequest(kind=enums.CodexServerRequestKind.COMMAND_EXECUTION, thread_id="thr-1", turn_id="turn-1", item_id="item-1")
        self.assertIs(request.approval_kind, enums.CodexCommandApprovalKind.COMMAND)
        defaults = (request.approval_id, request.environment_id, request.started_at_ms, request.reason, request.command, request.cwd, request.grant_root)
        self.assertEqual(defaults, ("", "", 0, "", "", "", ""))
        self.assertIsNone(request.available_decisions)
        self.assertEqual((request.questions, request.is_blocking), ((), False))
        self.assertEqual(records.CodexServerAnswer(decision=enums.CodexApprovalDecision.DECLINE).answers, ())

    def test_each_record_refuses_a_value_that_breaks_one_rule(self) -> None:
        records = _codex_host()
        enums = _enums()
        kind = enums.CodexServerRequestKind
        decision = enums.CodexApprovalDecision
        question = records.CodexUserInputQuestion(question_id="q1", header="Deploy", question="Ship it?")
        answer = records.CodexUserInputAnswer(question_id="q1", answers=("yes",))

        def server_request(**changes: Any) -> Any:
            fields: dict[str, Any] = {"kind": kind.COMMAND_EXECUTION, "thread_id": "thr-1", "turn_id": "turn-1", "item_id": "item-1"}
            fields.update(changes)
            return records.CodexServerRequest(**fields)

        # (label, factory, a word the refusal must name)
        rows: tuple[tuple[str, Callable[[], Any], str], ...] = (
            ("tier empty id", lambda: records.CodexServiceTier(tier_id=""), "tier_id"),
            ("tier id is an int", lambda: records.CodexServiceTier(tier_id=5), "tier_id"),
            ("tier name is None", lambda: records.CodexServiceTier(tier_id="fast", name=None), "name"),
            ("tier description is an int", lambda: records.CodexServiceTier(tier_id="fast", description=1), "description"),
            ("option empty label", lambda: records.CodexUserInputOption(label=""), "label"),
            ("option description is None", lambda: records.CodexUserInputOption(label="yes", description=None), "description"),
            ("question empty id", lambda: records.CodexUserInputQuestion(question_id="", header="h", question="q"), "question_id"),
            ("question header is an int", lambda: records.CodexUserInputQuestion(question_id="q1", header=3, question="q"), "header"),
            ("question options are a list", lambda: records.CodexUserInputQuestion(question_id="q1", header="h", question="q", options=[records.CodexUserInputOption(label="yes")]), "options"),
            ("question options hold text", lambda: records.CodexUserInputQuestion(question_id="q1", header="h", question="q", options=("yes",)), "options"),
            ("question is_other is an int", lambda: records.CodexUserInputQuestion(question_id="q1", header="h", question="q", is_other=1), "is_other"),
            ("question is_secret is text", lambda: records.CodexUserInputQuestion(question_id="q1", header="h", question="q", is_secret="no"), "is_secret"),
            ("request kind is not a member", lambda: server_request(kind="item/unknown/requestApproval"), "kind"),
            ("request empty thread id", lambda: server_request(thread_id=""), "thread_id"),
            ("request empty turn id", lambda: server_request(turn_id=""), "turn_id"),
            ("request empty item id", lambda: server_request(item_id=""), "item_id"),
            ("request approval kind is not a member", lambda: server_request(approval_kind="stdinWrite"), "approval_kind"),
            ("request approval id is None", lambda: server_request(approval_id=None), "approval_id"),
            ("request negative start", lambda: server_request(started_at_ms=-1), "started_at_ms"),
            ("request bool start", lambda: server_request(started_at_ms=True), "started_at_ms"),
            ("request command is an int", lambda: server_request(command=7), "command"),
            ("request decisions are a list", lambda: server_request(available_decisions=[decision.ACCEPT]), "available_decisions"),
            ("request decisions hold text", lambda: server_request(available_decisions=("maybe",)), "available_decisions"),
            ("request questions on an approval", lambda: server_request(questions=(question,)), "questions"),
            ("request questions are a list", lambda: server_request(kind=kind.USER_INPUT, questions=[question]), "questions"),
            ("request is_blocking is an int", lambda: server_request(is_blocking=1), "is_blocking"),
            ("answer empty question id", lambda: records.CodexUserInputAnswer(question_id="", answers=("yes",)), "question_id"),
            ("answer answers are a list", lambda: records.CodexUserInputAnswer(question_id="q1", answers=["yes"]), "answers"),
            ("answer answers hold an int", lambda: records.CodexUserInputAnswer(question_id="q1", answers=("yes", 3)), "answers"),
            ("server answer decision is not a member", lambda: records.CodexServerAnswer(decision="maybe"), "decision"),
            ("server answer answers are a list", lambda: records.CodexServerAnswer(decision=decision.ACCEPT, answers=[answer]), "answers"),
            ("server answer repeats a question", lambda: records.CodexServerAnswer(decision=decision.ACCEPT, answers=(answer, answer)), "answers"),
            ("server answer answers with decline", lambda: records.CodexServerAnswer(decision=decision.DECLINE, answers=(answer,)), "answers"),
        )
        for label, factory, field_name in rows:
            with self.subTest(row=label):
                with self.assertRaises(ConfigurationError) as caught:
                    factory()
                self.assertIn(field_name, str(caught.exception))


class CodexServerRequestParseTests(unittest.TestCase):
    """Section 9.1 "How from_params maps the wire", D-4, EC-4 to EC-6 and EC-51."""

    def test_a_full_command_approval_maps_every_mirrored_field_and_drops_object_decisions(self) -> None:
        records = _codex_host()
        enums = _enums()
        parsed = records.CodexServerRequest.from_params(enums.CodexServerRequestKind.COMMAND_EXECUTION, _command_params())
        expected = records.CodexServerRequest(
            kind=enums.CodexServerRequestKind.COMMAND_EXECUTION,
            thread_id="thr-1",
            turn_id="turn-1",
            item_id="item-1",
            approval_kind=enums.CodexCommandApprovalKind.WRITE_STDIN,
            approval_id="approval-1",
            environment_id="env-1",
            started_at_ms=STARTED_AT_MS,
            reason="The agent wants to type into the running shell.",
            command="git status",
            cwd=WORKSPACE,
            available_decisions=(enums.CodexApprovalDecision.ACCEPT, enums.CodexApprovalDecision.ACCEPT_FOR_SESSION, enums.CodexApprovalDecision.DECLINE, enums.CodexApprovalDecision.CANCEL),
        )
        self.assertEqual(parsed, expected)
        # EC-51: a plain command approval is told apart from terminal input by approval_kind alone.
        plain = records.CodexServerRequest.from_params(enums.CodexServerRequestKind.COMMAND_EXECUTION, _command_params(kind="command"))
        self.assertIs(plain.approval_kind, enums.CodexCommandApprovalKind.COMMAND)

    def test_absent_and_null_values_map_to_the_record_defaults(self) -> None:
        records = _codex_host()
        enums = _enums()
        kind = enums.CodexServerRequestKind.COMMAND_EXECUTION
        baseline = records.CodexServerRequest(kind=kind, thread_id="thr-1", turn_id="turn-1", item_id="item-1")
        nulls = {key: None for key in ("approvalId", "environmentId", "kind", "startedAtMs", "reason", "command", "cwd", "grantRoot", "availableDecisions")}
        for label, params in (("absent", _ids()), ("null", _ids(**nulls))):
            with self.subTest(values=label):
                self.assertEqual(records.CodexServerRequest.from_params(kind, params), baseline)

    def test_available_decisions_keep_absent_apart_from_present(self) -> None:
        # EC-5 and EC-6: absent or null is None; a present list keeps its known string values only, so a list of object
        # decisions or of decisions this release does not know becomes the empty tuple.
        records = _codex_host()
        enums = _enums()
        decision = enums.CodexApprovalDecision
        rows = (
            ("absent", _ids(), None),
            ("null", _ids(availableDecisions=None), None),
            ("empty", _ids(availableDecisions=[]), ()),
            ("object decisions only", _ids(availableDecisions=[{"acceptWithExecpolicyAmendment": {"execpolicyAmendment": ["ls"]}}, {"applyNetworkPolicyAmendment": {"host": "example.invalid"}}]), ()),
            ("an unknown string", _ids(availableDecisions=["accept", "acceptForever", "cancel"]), (decision.ACCEPT, decision.CANCEL)),
            ("wire order kept", _ids(availableDecisions=["cancel", "decline", "accept"]), (decision.CANCEL, decision.DECLINE, decision.ACCEPT)),
        )
        for label, params, expected in rows:
            with self.subTest(decisions=label):
                parsed = records.CodexServerRequest.from_params(enums.CodexServerRequestKind.COMMAND_EXECUTION, params)
                self.assertEqual(parsed.available_decisions, expected)

    def test_a_file_change_and_a_user_input_request_map_their_own_fields(self) -> None:
        records = _codex_host()
        enums = _enums()
        file_change = records.CodexServerRequest.from_params(
            enums.CodexServerRequestKind.FILE_CHANGE,
            _ids(reason="Edit the release config.", grantRoot=GRANT_ROOT, startedAtMs=5, availableDecisions=["accept", "decline"]),
        )
        self.assertEqual(
            file_change,
            records.CodexServerRequest(
                kind=enums.CodexServerRequestKind.FILE_CHANGE,
                thread_id="thr-1",
                turn_id="turn-1",
                item_id="item-1",
                started_at_ms=5,
                reason="Edit the release config.",
                grant_root=GRANT_ROOT,
                available_decisions=(enums.CodexApprovalDecision.ACCEPT, enums.CodexApprovalDecision.DECLINE),
            ),
        )
        questions = [
            {"id": "q1", "header": "Deploy", "question": "Ship it?", "options": [{"label": "yes", "description": "Ship now."}, {"label": "no", "description": None}], "isOther": True, "isSecret": False},
            # AC-11: options null and no isOther or isSecret reach the handler as () and False.
            {"id": "q2", "header": "Token", "question": "Paste the deploy token.", "options": None},
            {"id": "q3", "header": "Secret", "question": "Paste the key.", "isSecret": True, "isOther": None},
        ]
        user_input = records.CodexServerRequest.from_params(enums.CodexServerRequestKind.USER_INPUT, _ids(questions=questions, isBlocking=True))
        option = records.CodexUserInputOption
        question = records.CodexUserInputQuestion
        self.assertEqual(
            user_input.questions,
            (
                question(question_id="q1", header="Deploy", question="Ship it?", options=(option(label="yes", description="Ship now."), option(label="no")), is_other=True, is_secret=False),
                question(question_id="q2", header="Token", question="Paste the deploy token."),
                question(question_id="q3", header="Secret", question="Paste the key.", is_secret=True),
            ),
        )
        self.assertIs(user_input.is_blocking, True)
        self.assertIs(user_input.kind, enums.CodexServerRequestKind.USER_INPUT)
        self.assertIs(records.CodexServerRequest.from_params(enums.CodexServerRequestKind.USER_INPUT, _ids(questions=[], isBlocking=None)).is_blocking, False)

    def test_a_missing_id_a_wrong_type_or_an_unknown_kind_is_a_parse_failure(self) -> None:
        # EC-4: each of these raises ConfigurationError, which the router turns into the default answer.
        records = _codex_host()
        enums = _enums()
        command = enums.CodexServerRequestKind.COMMAND_EXECUTION
        user_input = enums.CodexServerRequestKind.USER_INPUT
        rows: tuple[tuple[str, Any, Any], ...] = (
            ("params are None", command, None),
            ("no threadId", command, {"turnId": "turn-1", "itemId": "item-1"}),
            ("no turnId", command, {"threadId": "thr-1", "itemId": "item-1"}),
            ("no itemId", command, {"threadId": "thr-1", "turnId": "turn-1"}),
            ("null threadId", command, _ids(threadId=None)),
            ("threadId is an int", command, _ids(threadId=7)),
            ("unknown approval kind", command, _ids(kind="sudo")),
            ("startedAtMs is text", command, _ids(startedAtMs="soon")),
            ("startedAtMs is a bool", command, _ids(startedAtMs=True)),
            ("availableDecisions is text", command, _ids(availableDecisions="accept")),
            ("questions is not a list", user_input, _ids(questions="q1")),
            ("a question without an id", user_input, _ids(questions=[{"header": "h", "question": "q"}])),
            ("an option without a label", user_input, _ids(questions=[{"id": "q1", "header": "h", "question": "q", "options": [{"description": "d"}]}])),
        )
        for label, kind, params in rows:
            with self.subTest(row=label):
                with self.assertRaises(ConfigurationError):
                    records.CodexServerRequest.from_params(kind, params)


class CodexSpawnRequestHardeningTests(unittest.TestCase):
    """INV-34, INV-36, INV-37, EC-37, EC-38 and D-15: the three new fields and the goal rule, checked when the request is built."""

    def _spawn(self, **fields: Any) -> Any:
        return _codex_host().CodexSpawnRequest(**fields)

    def _turn(self, sandbox_name: str) -> Any:
        from vidbyte.lib.dataclasses.codex import CodexTurnSettings
        from vidbyte.lib.enums.codex import CodexSandbox

        return CodexTurnSettings(sandbox=CodexSandbox[sandbox_name])

    def test_the_new_fields_default_to_unset_and_build_with_the_sandbox_they_need(self) -> None:
        request = self._spawn(prompt="Fix it.")
        self.assertEqual((request.turn_service_tier, request.network_access, request.writable_roots), ("", None, ()))
        names = [field.name for field in dataclasses.fields(request)]
        # NFR-8: new fields are appended after name, so every positional and keyword call keeps working.
        self.assertEqual(names[names.index("name") + 1 :], ["turn_service_tier", "network_access", "writable_roots"])
        for sandbox in ("READ_ONLY", "WORKSPACE_WRITE"):
            with self.subTest(network_sandbox=sandbox):
                self.assertIs(self._spawn(prompt="Fix it.", turn=self._turn(sandbox), network_access=True).network_access, True)
        writable = self._spawn(prompt="Fix it.", turn=self._turn("WORKSPACE_WRITE"), network_access=False, writable_roots=(WORKSPACE, GRANT_ROOT), turn_service_tier="fast")
        self.assertEqual((writable.writable_roots, writable.turn_service_tier, writable.network_access), ((WORKSPACE, GRANT_ROOT), "fast", False))

    def test_network_access_needs_a_read_only_or_workspace_write_turn_sandbox(self) -> None:
        # EC-38: the refusal is the whole CODEX_HOST_NETWORK_ACCESS_MESSAGE, naming the sandbox it got.
        for sandbox, value in (("FULL_ACCESS", True), ("PROVIDER_DEFAULT", True), ("PROVIDER_DEFAULT", False)):
            with self.subTest(sandbox=sandbox, network_access=value):
                with self.assertRaises(ConfigurationError) as caught:
                    self._spawn(prompt="Fix it.", turn=self._turn(sandbox), network_access=value)
                message = str(caught.exception)
                self.assertTrue(message.startswith(NETWORK_ACCESS_PREFIX), message)
                from vidbyte.lib.enums.codex import CodexSandbox

                member = CodexSandbox[sandbox]
                self.assertTrue(message in {NETWORK_ACCESS_MESSAGE.format(sandbox=member.name), NETWORK_ACCESS_MESSAGE.format(sandbox=member.value)}, message)
        with self.assertRaises(ConfigurationError) as caught:
            self._spawn(prompt="Fix it.", turn=self._turn("READ_ONLY"), network_access="yes")
        self.assertIn("network_access", str(caught.exception))

    def test_writable_roots_need_workspace_write_and_absolute_paths(self) -> None:
        # EC-37 and INV-37: every refusal is CODEX_HOST_WRITABLE_ROOTS_MESSAGE.
        rows = (
            ("a relative root", "WORKSPACE_WRITE", ("src",)),
            ("an empty root", "WORKSPACE_WRITE", ("",)),
            ("one good and one relative root", "WORKSPACE_WRITE", (WORKSPACE, "build")),
            ("a read-only sandbox", "READ_ONLY", (WORKSPACE,)),
            ("the provider's sandbox", "PROVIDER_DEFAULT", (WORKSPACE,)),
        )
        for label, sandbox, roots in rows:
            with self.subTest(row=label):
                with self.assertRaises(ConfigurationError) as caught:
                    self._spawn(prompt="Fix it.", turn=self._turn(sandbox), writable_roots=roots)
                self.assertEqual(str(caught.exception), WRITABLE_ROOTS_MESSAGE)
        for label, roots in (("a list", [WORKSPACE]), ("an int root", (5,))):
            with self.subTest(row=label):
                with self.assertRaises(ConfigurationError) as caught:
                    self._spawn(prompt="Fix it.", turn=self._turn("WORKSPACE_WRITE"), writable_roots=roots)
                self.assertIn("writable_roots", str(caught.exception))
        with self.assertRaises(ConfigurationError) as caught:
            self._spawn(prompt="Fix it.", turn_service_tier=5)
        self.assertIn("turn_service_tier", str(caught.exception))

    def test_a_goal_request_refuses_each_turn_only_field_naming_the_first_one_set(self) -> None:
        # INV-34, D-15: CODEX_HOST_GOAL_FIELD_MESSAGE with details["field"], for the first non-default field of
        # CODEX_HOST_GOAL_REJECTED_FIELDS, when the request is built.
        from vidbyte.lib.dataclasses.codex import CodexTurnSettings
        from vidbyte.lib.enums.codex import CodexReasoningEffort

        goal = _codex_host().CodexGoal(objective="Ship the fix.")
        exact_rows: tuple[tuple[str, dict[str, Any]], ...] = (
            ("turn", {"turn": CodexTurnSettings(effort=CodexReasoningEffort.LOW)}),
            ("output_schema", {"output_schema": {"type": "object"}}),
            ("disabled_plugin_ids", {"disabled_plugin_ids": ("plugin-a",)}),
            ("turn_service_tier", {"turn_service_tier": "fast"}),
            # The first field of the table wins when several are set.
            ("turn", {"turn": CodexTurnSettings(model="gpt-5.5"), "output_schema": {"type": "object"}, "turn_service_tier": "fast"}),
            ("output_schema", {"output_schema": {"type": "object"}, "disabled_plugin_ids": ("plugin-a",), "turn_service_tier": "fast"}),
        )
        for name, fields in exact_rows:
            with self.subTest(fields=sorted(fields)):
                with self.assertRaises(ConfigurationError) as caught:
                    self._spawn(goal=goal, **fields)
                self.assertEqual(str(caught.exception), GOAL_FIELD_MESSAGE.format(name=name))
                self.assertTrue(str(caught.exception.details.get("field", "")).endswith(name), caught.exception.details)
        # The sandbox fields are refused too; whether the goal rule or the sandbox rule speaks first is open (spec defect).
        for name, fields in (("network_access", {"network_access": True}), ("writable_roots", {"writable_roots": (WORKSPACE,)})):
            with self.subTest(field=name):
                with self.assertRaises(ConfigurationError) as caught:
                    self._spawn(goal=goal, **fields)
                self.assertIn(name, str(caught.exception))
        self.assertEqual(GOAL_REJECTED_FIELDS, ("turn", "output_schema", "disabled_plugin_ids", "turn_service_tier", "network_access", "writable_roots"))

    def test_a_goal_request_with_thread_settings_and_vidbyte_caps_still_builds(self) -> None:
        # AC-29: only turn-only fields are refused; the thread posture and Vidbyte's own caps stay allowed.
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings
        from vidbyte.lib.enums.codex import CodexApprovalsReviewer, CodexSandbox

        goal = _codex_host().CodexGoal(objective="Ship the fix.", token_budget=500)
        thread = CodexThreadSettings(model="gpt-5.5", sandbox=CodexSandbox.READ_ONLY, cwd=WORKSPACE, service_tier="fast")
        request = self._spawn(goal=goal, thread=thread, max_output_tokens=900, timeout_seconds=60.0, name="goal-run", approvals_reviewer=CodexApprovalsReviewer.AUTO_REVIEW)
        self.assertEqual((request.goal, request.thread, request.timeout_seconds), (goal, thread, 60.0))


class CodexModelInfoTierTests(unittest.TestCase):
    """INV-36 and section 9.1: CodexModelInfo carries the tiers model/list reports."""

    def _info(self, **changes: Any) -> Any:
        fields: dict[str, Any] = {
            "model_id": "gpt-5.5",
            "model": "gpt-5.5",
            "display_name": "GPT-5.5",
            "description": "A model.",
            "hidden": False,
            "is_default": True,
            "default_effort": "medium",
            "efforts": ("low", "medium"),
        }
        fields.update(changes)
        return _codex_host().CodexModelInfo(**fields)

    def test_the_tier_fields_are_appended_with_defaults_and_validated(self) -> None:
        records = _codex_host()
        info = self._info()
        self.assertEqual((info.service_tiers, info.default_service_tier), ((), ""))
        names = [field.name for field in dataclasses.fields(info)]
        self.assertEqual(names[-2:], ["service_tiers", "default_service_tier"])
        fast = records.CodexServiceTier(tier_id="fast", name="Fast", description="Lower latency.")
        tiered = self._info(service_tiers=(fast, records.CodexServiceTier(tier_id="flex")), default_service_tier="flex")
        self.assertEqual([tier.tier_id for tier in tiered.service_tiers], ["fast", "flex"])
        for label, changes, field_name in (
            ("tiers are a list", {"service_tiers": [fast]}, "service_tiers"),
            ("tiers hold text", {"service_tiers": ("fast",)}, "service_tiers"),
            ("default is None", {"default_service_tier": None}, "default_service_tier"),
        ):
            with self.subTest(row=label):
                with self.assertRaises(ConfigurationError) as caught:
                    self._info(**changes)
                self.assertIn(field_name, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
