"""FILE: tests/features/codex_host/test_codex_host_function_rows.py

PURPOSE: Proves the per-function rows of the hardening slice on a real host over the in-memory app-server: forget_codex_turns releasing a thread's ended turns; readiness reporting used-up usage in its place; one model-list refresh for a model or tier the cache lacks; continue refusing a stored unfinished goal before it loads the thread; list_codex_threads sending a validated limit on the host and the one-shot; list_codex_skills sending forceReload only when asked; a skill run resolving its skill in the folder the turn runs in; and each new argument refused before any request.
ROLE IN CODEBASE: Function-row layer of the hardening tests in tests/features/codex_host/ (docs/spec/codex-host-hardening/spec.md AC-16, AC-19, AC-20, AC-21, AC-23, AC-27, AC-28, AC-41, INV-22, INV-24, INV-25, INV-27, INV-29, INV-32, INV-33, INV-40, INV-48, EC-20 to EC-22, EC-41, D-10, D-20, D-25, D-26, D-30). Every class needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: Each row drives the public host or one-shot function and reads what the fake app-server received; request counts are compared before and after a call, so a refusal that sent anything fails. Thread-scoped methods are filtered by threadId, so the preflight's own reads do not count against a row.
COMMON MODIFICATION PATTERNS: A new per-function row adds one test here naming its INV and AC; a new input field adds one AC-41 row with the "<method> <field>" its refusal names.
KNOWN EDGE CASES: The fake lists models on two pages, so one model-list walk is two model/list requests. A goal read on a notLoaded thread is the only goal read continue may send. Paths are built with os.path so they are absolute on Windows and POSIX alike.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-hardening/spec.md section 6.1 (INV-22, INV-24 to INV-33).
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_function_rows.py
"""

from __future__ import annotations

import asyncio
import os
import unittest
from collections.abc import Awaitable, Callable
from typing import Any

from tests.features.codex_host.codex_host_support import (
    CLOSE_SECONDS,
    CONTINUE_GOAL_UNFINISHED_MESSAGE,
    WAIT_SECONDS,
    HostTestCase,
    make_echo_tool,
    mapped_summary,
    requires_sdk,
)
from vidbyte.lib.errors import ConfigurationError

SKILLS_HOME = os.path.abspath(os.path.join(os.sep, "skills-home"))
TURN_FOLDER = os.path.abspath(os.path.join(os.sep, "turn-folder"))
THREAD_FOLDER = os.path.abspath(os.path.join(os.sep, "thread-folder"))
SKILL_PATH = os.path.abspath(os.path.join(os.sep, "skills", "s", "SKILL.md"))
FAR_DEADLINE_SECONDS = 600.0
# The fake's model list spans two pages, so one full walk is two model/list requests.
MODEL_WALK = 2


def _on(thread_id: str) -> Callable[[dict[str, Any]], bool]:
    return lambda params: params.get("threadId") == thread_id


class RowTestCase(HostTestCase):
    """HostTestCase plus the request-window reads the rows share."""

    def methods_on(self, thread_id: str, since: int = 0) -> list[str]:
        return [request.method for request in list(self.server.requests)[since:] if request.params.get("threadId") == thread_id]

    async def finished_turn(self, host: Any, handle: Any) -> Any:
        self.server.complete_turn(handle.thread_id, handle.turn_id, final="Done.")
        return await self.wait_done(host, handle)


@requires_sdk
class CodexForgetTurnsTests(RowTestCase):
    """AC-16, INV-22, D-10 and EC-20 to EC-22: forget_codex_turns drops an idle thread's ended turns, locally."""

    async def test_forget_drops_ended_turns_refuses_a_busy_thread_and_sends_nothing(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        host = await self.open_host()
        first = await asyncio.wait_for(host.spawn_codex_thread(CodexSpawnRequest(prompt="Use the tool.", tools=(make_echo_tool(),))), WAIT_SECONDS)
        await self.finished_turn(host, first)
        second = await asyncio.wait_for(host.continue_codex_thread(first.thread_id, "Carry on."), WAIT_SECONDS)
        await self.finished_turn(host, second)
        busy = await self.spawn(host)
        sent = len(self.server.requests)

        self.assertEqual(await asyncio.wait_for(host.forget_codex_turns(first.thread_id), WAIT_SECONDS), 2)
        # EC-22: a second forget of the same thread finds nothing left.
        self.assertEqual(await asyncio.wait_for(host.forget_codex_turns(first.thread_id), WAIT_SECONDS), 0)
        for handle in (first, second):
            with self.subTest(handle=handle.turn_id):
                await self.assert_codex_error(host.get_codex_turn_result(handle), "codex.session_not_found")
        await self.assert_codex_error(host.track_codex_thread_usage(first.thread_id), "codex.session_not_found")
        # A running turn makes the thread busy, and nothing of it is dropped.
        error = await self.assert_codex_error(host.forget_codex_turns(busy.thread_id), "codex.session_busy")
        self.assertEqual(error.operation, "forget_codex_turns")
        self.assert_problem(await asyncio.wait_for(host.get_codex_turn_result(busy), WAIT_SECONDS), "inProgress", None)
        self.assertEqual(await asyncio.wait_for(host.forget_codex_turns("thr-never-seen"), WAIT_SECONDS), 0)
        with self.assertRaises(ConfigurationError) as caught:
            await asyncio.wait_for(host.forget_codex_turns(""), WAIT_SECONDS)
        self.assertIn("forget_codex_turns thread_id", str(caught.exception))
        self.assertEqual(caught.exception.details.get("field"), "thread_id")
        self.assertEqual(len(self.server.requests), sent)

        # The thread's dynamic tools stay registered, so a later tool call still reaches the developer's tool.
        call = {"threadId": first.thread_id, "turnId": second.turn_id, "callId": "call-1", "tool": "echo_text", "arguments": {"text": "hi"}}
        self.assertIs((await self.ask("item/tool/call", call))["success"], True)

    async def test_forget_works_on_a_closed_host(self) -> None:
        host = await self.open_host()
        handle = await self.spawn(host)
        await self.finished_turn(host, handle)
        await asyncio.wait_for(host.__aexit__(None, None, None), CLOSE_SECONDS)
        self.assertEqual(await asyncio.wait_for(host.forget_codex_turns(handle.thread_id), WAIT_SECONDS), 1)
        await self.assert_codex_error(host.get_codex_turn_result(handle), "codex.session_not_found")


@requires_sdk
class CodexReadinessUsageTests(RowTestCase):
    """AC-19 and INV-24: readiness reports used-up usage between sign-in and sandbox; unknown or unreadable adds none."""

    async def test_used_up_usage_is_a_problem_in_its_place(self) -> None:
        self.patch_platform("win32")
        host = await self.open_host()
        self.server.ordinary_usage_allowed = False
        readiness = await asyncio.wait_for(host.check_codex_ready(), WAIT_SECONDS)
        self.assertIs(readiness.ready, False)
        self.assertEqual([problem.code.value for problem in readiness.problems], ["codex.usage_limited"])
        self.server.account = None
        self.server.sandbox_status = "notConfigured"
        readiness = await asyncio.wait_for(host.check_codex_ready(), WAIT_SECONDS)
        self.assertEqual([problem.code.value for problem in readiness.problems], ["codex.not_signed_in", "codex.usage_limited", "codex.sandbox_not_ready"])
        self.assertIs(readiness.ready, False)

    async def test_unknown_usage_or_a_failed_usage_read_adds_no_problem(self) -> None:
        host = await self.open_host()
        self.server.ordinary_usage_allowed = None
        readiness = await asyncio.wait_for(host.check_codex_ready(), WAIT_SECONDS)
        self.assertIs(readiness.ready, True)
        self.assertEqual(list(readiness.problems), [])
        self.server.ordinary_usage_allowed = False
        reads = self.count("account/rateLimits/read")
        self.server.fail("account/rateLimits/read", self.fakes.FakeRpcError(-32603, "rate limits unavailable"), times=1)
        readiness = await asyncio.wait_for(host.check_codex_ready(), WAIT_SECONDS)
        self.assertEqual(self.count("account/rateLimits/read"), reads + 1)
        self.assertIs(readiness.ready, True)
        self.assertEqual(list(readiness.problems), [])


@requires_sdk
class CodexModelRefreshTests(RowTestCase):
    """AC-20, INV-25 and D-26: a model the cached list lacks costs exactly one fresh walk."""

    async def test_a_model_added_after_the_cache_passes_after_one_walk_and_a_missing_one_fails_after_one(self) -> None:
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings

        host = await self.open_host()
        await self.spawn(host, thread=CodexThreadSettings(model="gpt-5.5"))
        cached = self.count("model/list")
        await self.spawn(host, thread=CodexThreadSettings(model="gpt-5.5"))
        self.assertEqual(self.count("model/list"), cached)
        self.server.model_pages[1].append(self.fakes._model("gpt-6-preview", "gpt-6-preview"))
        await self.spawn(host, thread=CodexThreadSettings(model="gpt-6-preview"))
        self.assertEqual(self.count("model/list") - cached, MODEL_WALK)
        before = self.count("model/list")
        starts = self.count("thread/start")
        await self.assert_codex_error(self.spawn(host, thread=CodexThreadSettings(model="gpt-unknown-9")), "codex.model_unknown")
        self.assertEqual(self.count("model/list") - before, MODEL_WALK)
        self.assertEqual(self.count("thread/start"), starts)

    async def test_a_fresh_host_walks_the_list_once_for_a_missing_model(self) -> None:
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings

        host = await self.open_host()
        before = self.count("model/list")
        await self.assert_codex_error(self.spawn(host, thread=CodexThreadSettings(model="gpt-unknown-9")), "codex.model_unknown")
        self.assertEqual(self.count("model/list") - before, MODEL_WALK)


@requires_sdk
class CodexContinueGoalGuardTests(RowTestCase):
    """AC-21, INV-27 and D-20: continue refuses a notLoaded thread whose stored goal is unfinished."""

    async def test_an_unfinished_stored_goal_is_refused_after_two_reads_and_the_thread_stays_unloaded_and_free(self) -> None:
        host = await self.open_host()
        thread = self.server.seed_thread()
        thread.status = "notLoaded"
        thread.goal = self.fakes.goal_record(thread.thread_id, "Ship the fix.", "active")
        since = len(self.server.requests)
        error = await self.assert_codex_error(host.continue_codex_thread(thread.thread_id, "Carry on."), "codex.goal_unfinished")
        self.assertEqual(error.operation, "continue_codex_thread")
        self.assertTrue(mapped_summary(self, error).startswith(CONTINUE_GOAL_UNFINISHED_MESSAGE.format(status="active")), error.message)
        self.assertEqual(self.methods_on(thread.thread_id, since), ["thread/read", "thread/goal/get"])
        self.assertEqual(thread.status, "notLoaded")
        # The reservation was released: a second continue is refused for the goal again, not as busy.
        await self.assert_codex_error(host.continue_codex_thread(thread.thread_id, "Carry on."), "codex.goal_unfinished")

    async def test_a_complete_goal_or_no_goal_resumes_and_starts_a_turn(self) -> None:
        host = await self.open_host()
        for label, goal_status in (("complete goal", "complete"), ("no goal", None)):
            with self.subTest(case=label):
                thread = self.server.seed_thread()
                thread.status = "notLoaded"
                if goal_status is not None:
                    thread.goal = self.fakes.goal_record(thread.thread_id, "Ship the fix.", goal_status)
                handle = await asyncio.wait_for(host.continue_codex_thread(thread.thread_id, "Carry on."), WAIT_SECONDS)
                self.assertEqual(handle.thread_id, thread.thread_id)
                methods = self.methods_on(thread.thread_id)
                self.assertEqual([method for method in methods if method in ("thread/resume", "turn/start")], ["thread/resume", "turn/start"])
                self.assertLess(methods.index("thread/goal/get"), methods.index("thread/resume"))


@requires_sdk
class CodexListingArgumentTests(RowTestCase):
    """AC-23, AC-27, INV-29, INV-32 and INV-40: limit and force_reload, sent only when given, refused before any request."""

    async def test_the_host_sends_a_limit_and_refuses_a_bad_one_before_any_request(self) -> None:
        host = await self.open_host()
        await asyncio.wait_for(host.list_codex_threads(limit=5), WAIT_SECONDS)
        self.assertEqual(self.server.matching("thread/list")[-1].params.get("limit"), 5)
        await asyncio.wait_for(host.list_codex_threads(), WAIT_SECONDS)
        self.assertNotIn("limit", self.server.matching("thread/list")[-1].params)
        sent = len(self.server.requests)
        for limit in (0, 1001, True, "5"):
            with self.subTest(limit=limit):
                with self.assertRaises(ConfigurationError) as caught:
                    await asyncio.wait_for(host.list_codex_threads(limit=limit), WAIT_SECONDS)
                self.assertIn("list_codex_threads limit", str(caught.exception))
        self.assertEqual(len(self.server.requests), sent)

    async def test_the_one_shot_mirrors_the_limit(self) -> None:
        from vidbyte.harnesses.native.codex import oneshot

        await asyncio.wait_for(oneshot.list_codex_threads(limit=5), CLOSE_SECONDS)
        self.assertEqual([request.params.get("limit") for request in self.server.matching("thread/list")], [5])
        for limit in (0, 1001, True, "5"):
            with self.subTest(limit=limit):
                with self.assertRaises(ConfigurationError) as caught:
                    await asyncio.wait_for(oneshot.list_codex_threads(limit=limit), CLOSE_SECONDS)
                self.assertIn("list_codex_threads limit", str(caught.exception))
        self.assertEqual(self.count("thread/list"), 1)

    async def test_force_reload_is_sent_only_when_asked(self) -> None:
        host = await self.open_host()
        await asyncio.wait_for(host.list_codex_skills(SKILLS_HOME, force_reload=True), WAIT_SECONDS)
        await asyncio.wait_for(host.list_codex_skills(SKILLS_HOME), WAIT_SECONDS)
        self.assertEqual([request.params for request in self.server.matching("skills/list")], [{"cwds": [SKILLS_HOME], "forceReload": True}, {"cwds": [SKILLS_HOME]}])


@requires_sdk
class CodexSkillFolderTests(RowTestCase):
    """AC-28 and INV-33: a skill run resolves its skill where the turn runs."""

    async def test_the_skill_is_resolved_in_the_turn_folder_else_the_thread_folder(self) -> None:
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings, CodexTurnSettings
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        self.patch_skill_functions("CODEX_HOST_INPUT_CHECK_INTERVAL_SECONDS", 0.0)
        self.patch_skill_functions("CODEX_HOST_INPUT_CHECK_DEADLINE_SECONDS", FAR_DEADLINE_SECONDS)
        self.server.record_turn_input = True
        for folder in (TURN_FOLDER, THREAD_FOLDER):
            self.server.skills[folder] = [self.fakes.skill_entry("s", SKILL_PATH)]
        host = await self.open_host()
        rows = (
            ("turn folder set", CodexSpawnRequest(thread=CodexThreadSettings(cwd=THREAD_FOLDER), turn=CodexTurnSettings(cwd=TURN_FOLDER)), TURN_FOLDER),
            ("only the thread folder", CodexSpawnRequest(thread=CodexThreadSettings(cwd=THREAD_FOLDER)), THREAD_FOLDER),
        )
        for label, request, folder in rows:
            with self.subTest(case=label):
                listed = self.count("skills/list")
                await asyncio.wait_for(host.run_codex_skill("s", "Do it.", request=request), WAIT_SECONDS)
                self.assertEqual([request.params["cwds"] for request in self.server.matching("skills/list")[listed:]], [[folder]])


@requires_sdk
class CodexNewArgumentRefusalTests(RowTestCase):
    """AC-41 and INV-48: each new argument is refused by its record on an open host, naming it, before any request."""

    async def test_each_new_bad_argument_names_its_method_and_field_and_sends_nothing(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexReviewTarget
        from vidbyte.lib.enums.codex import CodexReviewTargetKind

        host = await self.open_host()
        target = CodexReviewTarget(kind=CodexReviewTargetKind.UNCOMMITTED_CHANGES)
        rows: tuple[tuple[str, str, Callable[[], Awaitable[Any]]], ...] = (
            ("forget_codex_turns thread_id", "thread_id", lambda: host.forget_codex_turns("")),
            ("fork_codex_thread before_turn_id", "before_turn_id", lambda: host.fork_codex_thread("thr-1", before_turn_id=5)),
            ("fork_codex_thread defer_goal_continuation", "defer_goal_continuation", lambda: host.fork_codex_thread("thr-1", defer_goal_continuation="yes")),
            ("list_codex_threads limit", "limit", lambda: host.list_codex_threads(limit=0)),
            ("start_codex_review request", "request", lambda: host.start_codex_review("thr-1", target, request={})),
            ("list_codex_skills force_reload", "force_reload", lambda: host.list_codex_skills(force_reload="yes")),
        )
        sent = len(self.server.requests)
        for label, field_name, call in rows:
            with self.subTest(row=label):
                with self.assertRaises(ConfigurationError) as caught:
                    await asyncio.wait_for(call(), WAIT_SECONDS)
                self.assertIn(label, str(caught.exception))
                self.assertTrue(str(caught.exception.details.get("field", "")).endswith(field_name), caught.exception.details)
        self.assertEqual(len(self.server.requests), sent)


if __name__ == "__main__":
    unittest.main()
