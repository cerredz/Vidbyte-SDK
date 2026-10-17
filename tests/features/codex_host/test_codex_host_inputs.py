"""FILE: tests/features/codex_host/test_codex_host_inputs.py

PURPOSE: Proves the PR #1055 review rule that every CodexHost function validates its input with a dataclass: each record in vidbyte/lib/dataclasses/codex_host_inputs.py refuses a bad value with a ConfigurationError that names the function and the field, and every public host method that takes input refuses a bad argument before it sends anything to Codex.
ROLE IN CODEBASE: Input layer of tests/features/codex_host/. The record tests need no host and no openai-codex, so CI runs them; the boundary test drives a real CodexHost over the in-memory app-server and needs the optional extra.
ARCHITECTURE NOTE: Each invalid row starts from a valid baseline and breaks one rule, so a failure names exactly the rule that did not hold. The boundary rows are checked against the host's own public coroutine methods, so a new method that takes input fails here until it has a row, and so a record.
COMMON MODIFICATION PATTERNS: A new record gets one VALID_RECORDS entry and its INVALID_ROWS; a new CodexHost method gets one boundary row.
KNOWN EDGE CASES: bool is an int subclass, so the limit rows include True; one str is a sequence of characters, so launch_codex_subagents refuses it as its prompts. A record turns a str prompt into a CodexRunInput, so the host reads one input type.
RELATED DOCS: tests/features/codex_host/FEATURE.md; vidbyte/lib/dataclasses/codex_host_inputs.py; vidbyte/lib/constants/codex_host.py
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_inputs.py
"""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
import unittest
from collections.abc import Callable
from typing import Any

from tests.features.codex_host.codex_host_support import WAIT_SECONDS, HostTestCase, requires_sdk
from vidbyte.lib.dataclasses import codex_host_inputs
from vidbyte.lib.dataclasses.codex import CodexRunInput, CodexTextInput, CodexThreadSettings
from vidbyte.lib.dataclasses.codex_host import CodexGoal, CodexReviewTarget, CodexSpawnRequest, CodexTurnHandle
from vidbyte.lib.dataclasses.codex_host_inputs import (
    CodexContinueRequest,
    CodexForkRequest,
    CodexGoalRunRequest,
    CodexModelListRequest,
    CodexReviewRequest,
    CodexSkillListRequest,
    CodexSkillRunRequest,
    CodexSubagentLaunchRequest,
    CodexThreadListing,
    CodexThreadListRequest,
    CodexThreadReadRequest,
    CodexThreadRef,
    CodexTurnListRequest,
    CodexTurnRef,
    CodexTurnSteerRequest,
    CodexTurnWaitRequest,
)
from vidbyte.lib.enums.codex import CodexHostOperation as Op
from vidbyte.lib.enums.codex import CodexReviewDelivery, CodexReviewTargetKind, CodexThreadSortKey, CodexThreadSourceKind
from vidbyte.lib.errors import ConfigurationError

HANDLE = CodexTurnHandle(thread_id="thr-1", turn_id="turn-1")
TARGET = CodexReviewTarget(kind=CodexReviewTargetKind.UNCOMMITTED_CHANGES)
GOAL = CodexGoal(objective="Ship the fix.")
EPHEMERAL = CodexSpawnRequest(thread=CodexThreadSettings(ephemeral=True))

# One valid instance of every record the module exports.
VALID_RECORDS: dict[str, Callable[[], Any]] = {
    "CodexModelListRequest": lambda: CodexModelListRequest(include_hidden=True),
    "CodexThreadRef": lambda: CodexThreadRef(operation=Op.GET_CODEX_GOAL, thread_id="thr-1"),
    "CodexTurnRef": lambda: CodexTurnRef(operation=Op.INTERRUPT_CODEX_TURN, handle=HANDLE),
    "CodexThreadReadRequest": lambda: CodexThreadReadRequest(thread_id="thr-1", include_turns=True),
    "CodexContinueRequest": lambda: CodexContinueRequest(thread_id="thr-1", run_input="Keep going."),
    "CodexForkRequest": lambda: CodexForkRequest(thread_id="thr-1", from_turn_id="turn-1", exclude_turns=True),
    "CodexThreadListRequest": lambda: CodexThreadListRequest(cwd="/work", source_kinds=[CodexThreadSourceKind.CLI], sort=CodexThreadSortKey.UPDATED_AT),
    "CodexTurnWaitRequest": lambda: CodexTurnWaitRequest(handle=HANDLE, timeout_seconds=1.5),
    "CodexTurnSteerRequest": lambda: CodexTurnSteerRequest(handle=HANDLE, run_input="Also check the tests."),
    "CodexSubagentLaunchRequest": lambda: CodexSubagentLaunchRequest(prompts=["One.", "Two."], limit=2),
    "CodexReviewRequest": lambda: CodexReviewRequest(thread_id="thr-1", target=TARGET, delivery=CodexReviewDelivery.DETACHED),
    "CodexThreadListing": lambda: CodexThreadListing(operation=Op.SEARCH_CODEX_THREADS, cwd="", limit=5, query="readme"),
    "CodexTurnListRequest": lambda: CodexTurnListRequest(thread_id="thr-1", cursor="c-1", limit=3),
    "CodexGoalRunRequest": lambda: CodexGoalRunRequest(goal=GOAL),
    "CodexSkillListRequest": lambda: CodexSkillListRequest(cwd="/work"),
    "CodexSkillRunRequest": lambda: CodexSkillRunRequest(operation=Op.RUN_CODEX_SKILL, skill="s", prompt="Do it."),
    # docs/spec/codex-host-hardening/spec.md INV-19 and D-33: the constructor's record. Read from the module at call time,
    # so this file still imports before the record exists.
    "CodexHostSetup": lambda: codex_host_inputs.CodexHostSetup(),
}

# (label, factory, text the refusal must contain): each row breaks one rule of a valid baseline.
INVALID_ROWS: tuple[tuple[str, Callable[[], Any], str], ...] = (
    ("models include_hidden is an int", lambda: CodexModelListRequest(include_hidden=1), "list_codex_models include_hidden"),
    ("thread ref empty id", lambda: CodexThreadRef(operation=Op.GET_CODEX_GOAL, thread_id=""), "get_codex_goal thread_id"),
    ("thread ref two-line id", lambda: CodexThreadRef(operation=Op.DELETE_CODEX_THREAD, thread_id="thr-1\nthr-2"), "delete_codex_thread thread_id"),
    ("thread ref operation is text", lambda: CodexThreadRef(operation="get_codex_goal", thread_id="thr-1"), "CodexThreadRef.operation"),
    ("turn ref handle is text", lambda: CodexTurnRef(operation=Op.INTERRUPT_CODEX_TURN, handle="turn-1"), "interrupt_codex_turn handle"),
    ("read empty id", lambda: CodexThreadReadRequest(thread_id=""), "read_codex_thread thread_id"),
    ("read include_turns is text", lambda: CodexThreadReadRequest(thread_id="thr-1", include_turns="yes"), "read_codex_thread include_turns"),
    ("continue blank id", lambda: CodexContinueRequest(thread_id="  ", run_input="go"), "continue_codex_thread thread_id"),
    ("continue input is an int", lambda: CodexContinueRequest(thread_id="thr-1", run_input=5), "continue_codex_thread input"),
    ("continue overrides is a dict", lambda: CodexContinueRequest(thread_id="thr-1", run_input="go", overrides={}), "continue_codex_thread request"),
    ("continue overrides set a name", lambda: CodexContinueRequest(thread_id="thr-1", run_input="go", overrides=CodexSpawnRequest(name="n")), "continue_codex_thread does not use the CodexSpawnRequest field name"),
    ("fork empty id", lambda: CodexForkRequest(thread_id=""), "fork_codex_thread thread_id"),
    ("fork from_turn_id is an int", lambda: CodexForkRequest(thread_id="thr-1", from_turn_id=3), "fork_codex_thread from_turn_id"),
    ("fork exclude_turns is an int", lambda: CodexForkRequest(thread_id="thr-1", exclude_turns=0), "fork_codex_thread exclude_turns"),
    ("fork overrides set a timeout", lambda: CodexForkRequest(thread_id="thr-1", overrides=CodexSpawnRequest(timeout_seconds=5)), "fork_codex_thread does not use the CodexSpawnRequest field timeout_seconds"),
    ("list cwd is None", lambda: CodexThreadListRequest(cwd=None), "list_codex_threads cwd"),
    ("list archived is text", lambda: CodexThreadListRequest(archived="no"), "list_codex_threads archived"),
    ("list source_kinds are text", lambda: CodexThreadListRequest(source_kinds=("cli",)), "list_codex_threads source_kinds"),
    ("list sort is text", lambda: CodexThreadListRequest(sort="created_at"), "list_codex_threads sort"),
    ("list cursor is an int", lambda: CodexThreadListRequest(cursor=2), "list_codex_threads cursor"),
    ("wait handle is text", lambda: CodexTurnWaitRequest(handle="turn-1"), "wait_codex_turn handle"),
    ("wait zero seconds", lambda: CodexTurnWaitRequest(handle=HANDLE, timeout_seconds=0), "wait_codex_turn timeout_seconds"),
    ("wait NaN seconds", lambda: CodexTurnWaitRequest(handle=HANDLE, timeout_seconds=float("nan")), "wait_codex_turn timeout_seconds"),
    ("steer handle is None", lambda: CodexTurnSteerRequest(handle=None, run_input="x"), "steer_codex_turn handle"),
    ("steer input is a list", lambda: CodexTurnSteerRequest(handle=HANDLE, run_input=["x"]), "steer_codex_turn input"),
    ("launch one string", lambda: CodexSubagentLaunchRequest(prompts="One prompt."), "not one string; got a value of type str"),
    ("launch no prompts", lambda: CodexSubagentLaunchRequest(prompts=[]), "got an empty list"),
    ("launch an int prompt", lambda: CodexSubagentLaunchRequest(prompts=["One.", 3]), "launch_codex_subagents prompts"),
    ("launch zero limit", lambda: CodexSubagentLaunchRequest(prompts=["One."], limit=0), "launch_codex_subagents limit"),
    ("launch bool limit", lambda: CodexSubagentLaunchRequest(prompts=["One."], limit=True), "launch_codex_subagents limit"),
    ("launch over its limit", lambda: CodexSubagentLaunchRequest(prompts=["One.", "Two."], limit=1), "launch_codex_subagents got 2 prompts, over its limit of 1"),
    ("launch request has a prompt", lambda: CodexSubagentLaunchRequest(prompts=["One."], request=CodexSpawnRequest(prompt="p")), "launch_codex_subagents does not use the CodexSpawnRequest field prompt"),
    ("review empty id", lambda: CodexReviewRequest(thread_id="", target=TARGET), "start_codex_review thread_id"),
    ("review target is a dict", lambda: CodexReviewRequest(thread_id="thr-1", target={}), "start_codex_review target"),
    ("review delivery is text", lambda: CodexReviewRequest(thread_id="thr-1", target=TARGET, delivery="inline"), "start_codex_review delivery"),
    ("listing of another operation", lambda: CodexThreadListing(operation=Op.LIST_CODEX_THREADS, cwd="", limit=5), "CodexThreadListing.operation"),
    ("listing zero limit", lambda: CodexThreadListing(operation=Op.LIST_RECENT_CODEX_THREADS, cwd="", limit=0), "list_recent_codex_threads limit must be an integer from 1 to 1000."),
    ("listing float since", lambda: CodexThreadListing(operation=Op.LIST_CODEX_THREADS_SINCE, cwd="", limit=5, since=1.5), "list_codex_threads_since since must be a non-negative integer number of Unix seconds."),
    ("listing since on a recent listing", lambda: CodexThreadListing(operation=Op.LIST_RECENT_CODEX_THREADS, cwd="", limit=5, since=5), "list_recent_codex_threads does not take since"),
    ("listing blank query", lambda: CodexThreadListing(operation=Op.SEARCH_CODEX_THREADS, cwd="", limit=5, query=" "), "search_codex_threads query must be a non-empty string."),
    ("listing query on a recent listing", lambda: CodexThreadListing(operation=Op.LIST_RECENT_CODEX_THREADS, cwd="", limit=5, query="x"), "list_recent_codex_threads does not take query"),
    ("turns empty id", lambda: CodexTurnListRequest(thread_id=""), "list_codex_turns thread_id"),
    ("turns zero limit", lambda: CodexTurnListRequest(thread_id="thr-1", limit=0), "list_codex_turns limit"),
    ("goal run goal is text", lambda: CodexGoalRunRequest(goal="Ship the fix."), "run_codex_goal goal"),
    ("goal run request has a prompt", lambda: CodexGoalRunRequest(goal=GOAL, request=CodexSpawnRequest(prompt="p")), "run_codex_goal takes its input as arguments"),
    ("skills cwd is an int", lambda: CodexSkillListRequest(cwd=3), "list_codex_skills cwd"),
    ("skill run of another operation", lambda: CodexSkillRunRequest(operation=Op.RUN_CODEX_GOAL, skill="s", prompt="p"), "CodexSkillRunRequest.operation"),
    ("skill run request has a goal", lambda: CodexSkillRunRequest(operation=Op.RUN_CODEX_SKILL, skill="s", prompt="p", request=CodexSpawnRequest(goal=GOAL)), "run_codex_skill takes its input as arguments"),
    ("skill run on an ephemeral thread", lambda: CodexSkillRunRequest(operation=Op.RUN_CODEX_SKILL, skill="s", prompt="p", request=EPHEMERAL), "run_codex_skill needs a stored thread"),
    ("skill run blank skill", lambda: CodexSkillRunRequest(operation=Op.RUN_CODEX_SKILL, skill=" ", prompt="p"), "run_codex_skill skill must be a non-empty string."),
    ("skill run empty prompt", lambda: CodexSkillRunRequest(operation=Op.RUN_CODEX_SKILL, skill="s", prompt=""), "run_codex_skill prompt"),
    ("docs run empty question", lambda: CodexSkillRunRequest(operation=Op.RUN_CODEX_OPENAI_DOCS, skill="openai-docs", prompt=""), "run_codex_openai_docs question"),
)


class CodexHostInputRecordTests(unittest.TestCase):
    """Each input record checks its own fields when it is built."""

    def test_every_exported_record_has_a_valid_baseline_that_is_frozen_and_slotted(self) -> None:
        self.assertEqual(set(VALID_RECORDS), set(codex_host_inputs.__all__))
        for name, factory in VALID_RECORDS.items():
            with self.subTest(record=name):
                record = factory()
                self.assertTrue(dataclasses.is_dataclass(record))
                self.assertTrue(hasattr(type(record), "__slots__"))
                field_name = dataclasses.fields(record)[0].name
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    setattr(record, field_name, None)

    def test_each_invalid_record_names_the_function_and_the_field(self) -> None:
        for label, factory, expected in INVALID_ROWS:
            with self.subTest(row=label):
                with self.assertRaises(ConfigurationError) as caught:
                    factory()
                self.assertIn(expected, str(caught.exception))
                self.assertIn("field", caught.exception.details)

    def test_text_prompts_are_stored_as_run_inputs_and_prompts_as_a_tuple(self) -> None:
        continued = CodexContinueRequest(thread_id="thr-1", run_input="Keep going.")
        self.assertEqual(continued.run_input, CodexRunInput(items=(CodexTextInput("Keep going."),)))
        given = CodexRunInput(items=(CodexTextInput("Check it."),))
        self.assertIs(CodexTurnSteerRequest(handle=HANDLE, run_input=given).run_input, given)
        launch = CodexSubagentLaunchRequest(prompts=["One.", given])
        self.assertEqual(launch.prompts, (CodexRunInput(items=(CodexTextInput("One."),)), given))
        listing = CodexThreadListRequest(source_kinds=[CodexThreadSourceKind.CLI])
        self.assertEqual(listing.source_kinds, (CodexThreadSourceKind.CLI,))

    def test_each_listing_takes_only_its_own_window_or_query(self) -> None:
        # The since window and the query each belong to one listing; the
        # recent listing takes neither.
        recent = CodexThreadListing(operation=Op.LIST_RECENT_CODEX_THREADS, cwd="/work", limit=20)
        self.assertEqual((recent.query, recent.since), ("", None))
        since = CodexThreadListing(operation=Op.LIST_CODEX_THREADS_SINCE, cwd="", limit=1000, since=0)
        self.assertEqual(since.since, 0)
        with self.assertRaises(ConfigurationError):
            CodexThreadListing(operation=Op.LIST_CODEX_THREADS_SINCE, cwd="", limit=5)
        with self.assertRaises(ConfigurationError):
            CodexThreadListing(operation=Op.SEARCH_CODEX_THREADS, cwd="", limit=5, since=3, query="x")


@requires_sdk
class CodexHostInputBoundaryTests(HostTestCase):
    """Every public CodexHost method that takes input refuses a bad argument before any request."""

    async def test_every_public_method_refuses_a_bad_argument_before_any_request(self) -> None:
        from vidbyte.harnesses.native.codex import CodexHost

        host = await self.open_host()
        rows: tuple[tuple[str, Callable[[], Any], str], ...] = (
            ("list_codex_models", lambda: host.list_codex_models(include_hidden="yes"), "list_codex_models include_hidden"),
            ("spawn_codex_thread", lambda: host.spawn_codex_thread({}), "spawn_codex_thread request"),
            ("continue_codex_thread", lambda: host.continue_codex_thread("", "Keep going."), "continue_codex_thread thread_id"),
            ("fork_codex_thread", lambda: host.fork_codex_thread("thr-1", exclude_turns="no"), "fork_codex_thread exclude_turns"),
            ("list_codex_threads", lambda: host.list_codex_threads(source_kinds=("cli",)), "list_codex_threads source_kinds"),
            ("read_codex_thread", lambda: host.read_codex_thread(""), "read_codex_thread thread_id"),
            ("wait_codex_turn", lambda: host.wait_codex_turn(HANDLE, timeout_seconds=-1), "wait_codex_turn timeout_seconds"),
            ("get_codex_turn_result", lambda: host.get_codex_turn_result("turn-1"), "get_codex_turn_result handle"),
            ("steer_codex_turn", lambda: host.steer_codex_turn(HANDLE, 5), "steer_codex_turn input"),
            ("interrupt_codex_turn", lambda: host.interrupt_codex_turn(None), "interrupt_codex_turn handle"),
            ("track_codex_thread_usage", lambda: host.track_codex_thread_usage(""), "track_codex_thread_usage thread_id"),
            # docs/spec/codex-host-hardening/spec.md INV-22 and INV-48: the new local method builds CodexThreadRef first.
            ("forget_codex_turns", lambda: host.forget_codex_turns(""), "forget_codex_turns thread_id"),
            ("launch_codex_subagents", lambda: host.launch_codex_subagents("One prompt."), "not one string"),
            ("start_codex_review", lambda: host.start_codex_review("thr-1", "uncommitted"), "start_codex_review target"),
            ("list_recent_codex_threads", lambda: host.list_recent_codex_threads("", limit=0), "list_recent_codex_threads limit"),
            ("list_codex_threads_since", lambda: host.list_codex_threads_since("", since=-1), "list_codex_threads_since since"),
            ("search_codex_threads", lambda: host.search_codex_threads("", ""), "search_codex_threads query"),
            ("get_codex_thread_lineage", lambda: host.get_codex_thread_lineage(""), "get_codex_thread_lineage thread_id"),
            ("list_codex_turns", lambda: host.list_codex_turns("thr-1", limit=0), "list_codex_turns limit"),
            ("compact_codex_thread", lambda: host.compact_codex_thread(""), "compact_codex_thread thread_id"),
            ("delete_codex_thread", lambda: host.delete_codex_thread(" "), "delete_codex_thread thread_id"),
            ("get_codex_goal", lambda: host.get_codex_goal(""), "get_codex_goal thread_id"),
            ("run_codex_goal", lambda: host.run_codex_goal("Ship it.", request=CodexSpawnRequest(prompt="p")), "run_codex_goal takes its input as arguments"),
            ("list_codex_skills", lambda: host.list_codex_skills(cwd=None), "list_codex_skills cwd"),
            ("run_codex_skill", lambda: host.run_codex_skill("s", ""), "run_codex_skill prompt"),
            ("run_codex_openai_docs", lambda: host.run_codex_openai_docs(""), "run_codex_openai_docs question"),
        )
        # Every public method that takes an argument has a row, so a
        # new one cannot skip its input record unnoticed.
        public = {name for name, method in inspect.getmembers(CodexHost, inspect.iscoroutinefunction) if not name.startswith("_") and len(inspect.signature(method).parameters) > 1}
        self.assertEqual({row[0] for row in rows}, public)
        for name, call, expected in rows:
            with self.subTest(method=name):
                before = len(self.server.requests)
                with self.assertRaises(ConfigurationError) as caught:
                    await asyncio.wait_for(call(), WAIT_SECONDS)
                self.assertIn(expected, str(caught.exception))
                self.assertEqual(list(self.server.requests)[before:], [])


if __name__ == "__main__":
    unittest.main()
