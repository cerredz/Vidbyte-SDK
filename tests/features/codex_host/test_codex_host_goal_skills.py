"""FILE: tests/features/codex_host/test_codex_host_goal_skills.py

PURPOSE: Proves the goal and skill functions over the in-memory app-server: get_codex_goal's record, run_codex_goal's request order, its stored-goal read-back and the single goal cancel on a failed or cancelled check; list_codex_skills's params and records; run_codex_skill and run_codex_openai_docs resolving the skill before any thread starts, sending the skill as first-class input, confirming it with the bounded read-back, and the single interrupt on a failed or cancelled check; and the argument refusals of all three run functions.
ROLE IN CODEBASE: Goal and skill layer of tests/features/codex_host/ (docs/spec/codex-host-thread-helpers/spec.md AC-24 to AC-32, AC-39, AC-40, AC-42, AC-43, INV-20 to INV-27, INV-34, INV-35, EC-25 to EC-34, EC-37, EC-45, EC-46, EC-48). Every class needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: The fake stores a goal as goal/set sent it, and goal_get_answer can make thread/goal/get answer something else, which stages a goal that did not take. skills maps a working folder to its skills/list entries. record_turn_input makes turn/start store its input as the turn's userMessage, drop_skill_input leaves the skill entry out, and input_hidden_reads hides that item from the first reads. The read-back bounds are patched in skill_functions, where spec section 13 says the module imports them by name: the interval to 0 with a long deadline for exact read counts, or a deadline below the interval for the deadline stop. Exact cancel and interrupt counts use the one-worker barrier.
COMMON MODIFICATION PATTERNS: Add a goal mismatch as a goal_get_answer row; add a skill case by seeding server.skills for the folder the request names (DEFAULT_CWD for an empty cwd) and asserting the turn/start input and the thread/turns/list count.
KNOWN EDGE CASES: openai-codex's goal cancel pauses the goal and interrupts its turn and swallows its own failures, so a goal cancel is counted from the fake client's cancel_goal_operation log, not from turn/interrupt requests. A skill run with no thread yet (not found, disabled) names no thread, so its message has no thread suffix.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-thread-helpers/spec.md sections 6.1 (INV-20 to INV-27, INV-34, INV-35), 9.2 and 13.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_goal_skills.py
"""

from __future__ import annotations

import asyncio
import os
import re
import unittest
from typing import Any

from tests.features.codex_host.codex_host_support import (
    APP_SERVER_PLACE,
    BUDGET_DIFFERS_MESSAGE,
    EPHEMERAL_SKILL_MESSAGE,
    GOAL_UNCHECKED_MESSAGE,
    INPUT_NOT_RECORDED_MESSAGE,
    NEXT_STEPS,
    NO_GOAL_MESSAGE,
    OBJECTIVE_DIFFERS_MESSAGE,
    OWN_INPUT_MESSAGE,
    SKILL_DISABLED_MESSAGE,
    SKILL_DROPPED_MESSAGE,
    SKILL_NAME_MESSAGE,
    SKILL_NOT_FOUND_MESSAGE,
    SKILL_UNCHECKED_MESSAGE,
    WAIT_SECONDS,
    HostTestCase,
    requires_sdk,
    thread_suffix,
)
from vidbyte.lib.errors import ConfigurationError

PREFLIGHT_METHODS = frozenset({"account/read", "account/rateLimits/read", "windowsSandbox/readiness", "model/list"})
WORK_A = os.path.abspath(os.path.join(os.sep, "work", "a"))
SKILL_PATH = os.path.abspath(os.path.join(os.sep, "skills", "s", "SKILL.md"))
DOCS_PATH = os.path.abspath(os.path.join(os.sep, "codex-home", "skills", ".system", "openai-docs", "SKILL.md"))
GOAL_STATUSES = ("active", "paused", "blocked", "usageLimited", "budgetLimited", "complete")
# Spec section 9.3: CODEX_HOST_INPUT_CHECK_ATTEMPTS and CODEX_HOST_SKILL_NAMES_IN_ERROR.
INPUT_CHECK_ATTEMPTS = 10
SKILL_NAMES_IN_ERROR = 50
# A deadline no read-back test can reach, so read counts depend on the attempt bound only.
FAR_DEADLINE_SECONDS = 600.0


def _thread_methods(requests: list[Any], thread_id: str) -> list[str]:
    return [request.method for request in requests if request.params.get("threadId") == thread_id]


def _name_tokens(text: str) -> list[str]:
    """The skill-name-shaped words of a message tail, whatever separator the list uses (spec section 9.2 says comma-separated)."""
    return re.findall(r"[A-Za-z0-9_.-]+(?<!\.)", text)


def _not_found_prefix(skill: str, place: str) -> str:
    """SKILL_NOT_FOUND_MESSAGE up to its {names} list, which the tests read separator-agnostically."""
    return SKILL_NOT_FOUND_MESSAGE.split("{names}")[0].format(skill=skill, place=place)


def _skill_input(prompt: str, name: str, path: str) -> list[dict[str, str]]:
    """Spec INV-25: the exact two input items of a skill turn."""
    return [{"text": prompt, "type": "text"}, {"name": name, "path": path, "type": "skill"}]


class _GoalSkillCase(HostTestCase):
    """Opens a host, remembers where its requests begin, and counts goal cancels and interrupts."""

    async def opened(self) -> Any:
        host = await self.open_host()
        self.mark = len(self.server.requests)
        return host

    def sent(self) -> list[Any]:
        return list(self.server.requests)[self.mark :]

    def sent_methods(self) -> list[str]:
        return [request.method for request in self.sent()]

    def remark(self) -> None:
        self.mark = len(self.server.requests)

    def started_thread(self) -> str:
        """The thread the last thread/start created: the fake numbers threads in creation order."""
        return list(self.server.threads)[-1]

    def goal_cancels(self, thread_id: str) -> int:
        return sum(1 for entry in self.server.kinds("cancel_goal_operation") if entry[1] == thread_id)

    def interrupts(self, thread_id: str) -> int:
        return self.count("turn/interrupt", lambda params: params["threadId"] == thread_id)

    async def barrier(self, host: Any, thread_id: str) -> None:
        # With one host worker, this read returns only after any stop queued before it was sent.
        await asyncio.wait_for(host.read_codex_thread(thread_id), WAIT_SECONDS)

    async def call(self, awaitable: Any) -> Any:
        return await asyncio.wait_for(awaitable, WAIT_SECONDS)

    async def refused(self, awaitable: Any) -> ConfigurationError:
        with self.assertRaises(ConfigurationError) as caught:
            await asyncio.wait_for(awaitable, WAIT_SECONDS)
        return caught.exception

    def list_skill(self, cwd: str, *entries: Any) -> None:
        self.server.skills[cwd] = list(entries)

    def fast_read_back(self) -> None:
        self.patch_skill_functions("CODEX_HOST_INPUT_CHECK_INTERVAL_SECONDS", 0.0)
        self.patch_skill_functions("CODEX_HOST_INPUT_CHECK_DEADLINE_SECONDS", FAR_DEADLINE_SECONDS)


@requires_sdk
class CodexGetGoalTests(_GoalSkillCase):
    """AC-24, EC-25 and INV-20: the stored goal as a record, None, or not found."""

    async def test_the_goal_record_mirrors_the_stored_goal_for_every_status(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexThreadGoal
        from vidbyte.lib.enums.codex import CodexGoalStatus

        base = self.fakes.BASE_TIME
        host = await self.opened()
        for status in GOAL_STATUSES:
            with self.subTest(status=status):
                thread = self.server.seed_thread(completed_turns=1)
                thread.goal = self.fakes.goal_record(thread.thread_id, "Ship the fix.", status, token_budget=500, tokens_used=120, time_used_seconds=30)
                goal = await self.call(host.get_codex_goal(thread.thread_id))
                expected = CodexThreadGoal(thread_id=thread.thread_id, objective="Ship the fix.", status=CodexGoalStatus(status), token_budget=500, tokens_used=120, time_used_seconds=30, created_at=base, updated_at=base + 30)
                self.assertEqual(goal, expected)
                self.assertIsInstance(goal.status, CodexGoalStatus)

        unbudgeted = self.server.seed_thread(completed_turns=1)
        unbudgeted.goal = self.fakes.goal_record(unbudgeted.thread_id, "Ship the fix.")
        self.assertIsNone((await self.call(host.get_codex_goal(unbudgeted.thread_id))).token_budget)

        # EC-25: a thread that never had a goal, loaded or not, answers None and stays notLoaded.
        for status in (None, "notLoaded"):
            with self.subTest(goalless=status):
                bare = self.server.seed_thread(completed_turns=1)
                bare.status = status
                self.remark()
                self.assertIsNone(await self.call(host.get_codex_goal(bare.thread_id)))
                self.assertEqual(self.sent_methods(), ["thread/read", "thread/goal/get"])
                self.assertEqual(bare.status, status)

        error = await self.assert_codex_error(host.get_codex_goal("thr-never"), "codex.session_not_found")
        self.assertEqual(error.operation, "get_codex_goal")


@requires_sdk
class CodexRunGoalTests(_GoalSkillCase):
    """AC-25 to AC-28, EC-26 to EC-29, INV-21, INV-22 and INV-27: start the goal, read it back, stop it on a miss."""

    async def test_a_goal_run_starts_goal_mode_sets_the_budget_and_reads_the_goal_back(self) -> None:
        # AC-25, INV-21: no text prompt, and the read-back is get_codex_goal's two requests.
        host = await self.opened()
        handle = await self.call(host.run_codex_goal("ship it", token_budget=500))
        thread_id = handle.thread_id
        on_thread = [request for request in self.sent() if request.params.get("threadId") == thread_id]
        self.assertEqual([request.method for request in on_thread], ["thread/read", "thread/goal/clear", "thread/goal/set", "thread/goal/set", "thread/read", "thread/goal/get"])
        self.assertEqual((on_thread[2].params.get("objective"), on_thread[2].params.get("status")), ("ship it", "active"))
        self.assertEqual(on_thread[3].params, {"threadId": thread_id, "tokenBudget": 500})
        self.assertEqual(on_thread[5].params, {"threadId": thread_id})
        self.assertEqual(self.count("turn/start"), 0)
        self.assertEqual(handle.turn_id, self.server.threads[thread_id].turns[0].turn_id)
        self.assertEqual(self.goal_cancels(thread_id), 0)

        self.remark()
        unbudgeted = await self.call(host.run_codex_goal("ship it"))
        self.assertEqual(_thread_methods(self.sent(), unbudgeted.thread_id), ["thread/read", "thread/goal/clear", "thread/goal/set", "thread/read", "thread/goal/get"])

    async def test_a_goal_that_did_not_take_is_cancelled_once_and_reported(self) -> None:
        # AC-26, EC-29, INV-22: a missing or different stored goal is codex.command_not_run, after one goal cancel.
        self.patch_connection("CODEX_HOST_WORKER_THREADS", 1)
        host = await self.opened()
        rows = (
            ("objective", lambda thread: {**thread.goal, "objective": "Something else."}, OBJECTIVE_DIFFERS_MESSAGE),
            ("budget", lambda thread: {**thread.goal, "tokenBudget": 400}, BUDGET_DIFFERS_MESSAGE.format(stored=400, sent=500)),
            ("missing", lambda thread: None, NO_GOAL_MESSAGE),
        )
        for name, answer, message in rows:
            with self.subTest(mismatch=name):
                self.server.goal_get_answer = answer
                error = await self.assert_codex_error(host.run_codex_goal("ship it", token_budget=500), "codex.command_not_run")
                thread_id = self.started_thread()
                self.assertEqual(error.operation, "run_codex_goal")
                self.assertEqual(error.message, message + thread_suffix(thread_id))
                self.assertEqual(error.next_step, NEXT_STEPS["codex.command_not_run"])
                self.assertEqual(self.goal_cancels(thread_id), 1)
                await self.barrier(host, thread_id)
                self.assertEqual(self.goal_cancels(thread_id), 1)

        # EC-29: the cancel's own requests fail too, and the mismatch is still what the caller sees.
        self.server.goal_get_answer = lambda thread: None
        self.server.fail("thread/goal/set", self.fakes.FakeRpcError(-32603, "pause refused"), predicate=lambda params: params.get("status") == "paused")
        self.server.fail("turn/interrupt", self.fakes.FakeRpcError(-32603, "interrupt refused"))
        error = await self.assert_codex_error(host.run_codex_goal("ship it"), "codex.command_not_run")
        self.assertEqual(error.message, NO_GOAL_MESSAGE + thread_suffix(self.started_thread()))

    async def test_a_goal_check_that_fails_cancels_the_run_and_keeps_its_error(self) -> None:
        # AC-27, INV-22: the check's api_error keeps operation get_codex_goal and gains GOAL_UNCHECKED_MESSAGE.
        self.patch_connection("CODEX_HOST_WORKER_THREADS", 1)
        host = await self.opened()
        self.server.fail("thread/goal/get", self.fakes.FakeRpcError(-32603, "goal read failed"))
        error = await self.assert_codex_error(host.run_codex_goal("ship it", token_budget=500), "codex.api_error")
        thread_id = self.started_thread()
        self.assertEqual(error.operation, "get_codex_goal")
        self.assertTrue(error.message.endswith(GOAL_UNCHECKED_MESSAGE.format(thread_id=thread_id)), error.message)
        self.assertEqual(error.next_step, NEXT_STEPS["codex.api_error"])
        await self.barrier(host, thread_id)
        self.assertEqual(self.goal_cancels(thread_id), 1)

    async def test_a_goal_run_cancelled_during_its_check_is_cancelled_once(self) -> None:
        # EC-28, INV-22: CancelledError propagates, and the goal run does not keep spending unseen.
        self.patch_connection("CODEX_HOST_WORKER_THREADS", 1)
        host = await self.opened()
        hold = self.server.hold("thread/goal/get")
        task = asyncio.ensure_future(host.run_codex_goal("ship it"))
        thread_id = (await asyncio.to_thread(hold.wait_arrived)).params["threadId"]
        task.cancel()
        # Releasing now frees the one worker, so the cancel queued behind the held read can run.
        hold.release()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, WAIT_SECONDS)
        await self.wait_until(lambda: self.goal_cancels(thread_id) >= 1, "the goal run's cancel")
        await self.barrier(host, thread_id)
        self.assertEqual(self.goal_cancels(thread_id), 1)

    async def test_a_goal_that_completed_before_the_check_still_returns_the_handle(self) -> None:
        # EC-27: a complete goal is still stored with the sent objective and budget.
        host = await self.opened()
        self.server.goal_get_answer = lambda thread: {**thread.goal, "status": "complete"}
        handle = await self.call(host.run_codex_goal("ship it", token_budget=500))
        self.assertEqual(self.goal_cancels(handle.thread_id), 0)

    async def test_bad_goal_arguments_are_refused_before_any_request(self) -> None:
        # AC-28, EC-26, INV-6.
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings
        from vidbyte.lib.dataclasses.codex_host import CodexGoal, CodexSpawnRequest

        host = await self.opened()
        rows = (
            ("empty objective", lambda: host.run_codex_goal("")),
            ("zero budget", lambda: host.run_codex_goal("x", token_budget=0)),
            ("bool budget", lambda: host.run_codex_goal("x", token_budget=True)),
            ("ephemeral thread", lambda: host.run_codex_goal("x", request=CodexSpawnRequest(thread=CodexThreadSettings(ephemeral=True)))),
        )
        for name, start in rows:
            with self.subTest(case=name):
                await self.refused(start())
        for name, request in (("prompt", CodexSpawnRequest(prompt="p")), ("goal", CodexSpawnRequest(goal=CodexGoal(objective="other")))):
            with self.subTest(own_input=name):
                error = await self.refused(host.run_codex_goal("x", request=request))
                self.assertEqual(str(error), OWN_INPUT_MESSAGE.format(operation="run_codex_goal"))
        self.assertEqual(self.sent(), [])

    async def test_a_goal_run_keeps_the_callers_posture(self) -> None:
        # INV-27: the request's thread settings reach thread/start unchanged.
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        host = await self.opened()
        request = CodexSpawnRequest(thread=CodexThreadSettings(cwd=WORK_A, model="gpt-5.5-codex"))
        await self.call(host.run_codex_goal("ship it", request=request))
        started = self.server.matching("thread/start")[-1].params
        self.assertEqual((started.get("cwd"), started.get("model")), (WORK_A, "gpt-5.5-codex"))


@requires_sdk
class CodexListSkillsTests(_GoalSkillCase):
    """AC-29 and INV-23: one skills/list, every entry as a CodexSkillInfo in Codex's order."""

    async def test_skills_are_listed_for_a_folder_or_for_the_app_servers_own(self) -> None:
        from vidbyte.lib.dataclasses.codex_host import CodexSkillInfo
        from vidbyte.lib.enums.codex import CodexSkillScope

        entries = [
            self.fakes.skill_entry("alpha", os.path.join(WORK_A, ".codex", "skills", "alpha", "SKILL.md"), scope="repo"),
            self.fakes.skill_entry("beta", os.path.join(WORK_A, "beta", "SKILL.md"), scope="user", enabled=False, description="Beta does things."),
            self.fakes.skill_entry("gamma", os.path.join(WORK_A, "gamma", "SKILL.md"), scope="system"),
            self.fakes.skill_entry("delta", os.path.join(WORK_A, "delta", "SKILL.md"), scope="admin"),
        ]
        self.list_skill(WORK_A, *entries)
        self.list_skill(self.fakes.DEFAULT_CWD, self.fakes.skill_entry("openai-docs", DOCS_PATH, scope="system"))
        host = await self.opened()

        listed = await self.call(host.list_codex_skills(WORK_A))
        expected = tuple(CodexSkillInfo(name=entry["name"], description=entry["description"], path=entry["path"], scope=CodexSkillScope(entry["scope"]), enabled=entry["enabled"]) for entry in entries)
        self.assertEqual(listed, expected)
        self.assertEqual([type(skill.scope) for skill in listed], [CodexSkillScope] * 4)
        self.assertEqual([skill.enabled for skill in listed], [True, False, True, True])
        self.assertEqual(self.sent_methods(), ["skills/list"])
        self.assertEqual(self.sent()[0].params, {"cwds": [WORK_A]})

        self.remark()
        own = await self.call(host.list_codex_skills())
        self.assertEqual([(skill.name, skill.path, skill.scope) for skill in own], [("openai-docs", DOCS_PATH, CodexSkillScope.SYSTEM)])
        self.assertEqual([request.params for request in self.sent()], [{}])
        self.assertFalse(PREFLIGHT_METHODS & set(self.sent_methods()))


@requires_sdk
class CodexRunSkillTests(_GoalSkillCase):
    """AC-30 to AC-32, AC-42, EC-30 to EC-34, EC-37, EC-48, INV-24 to INV-27: resolve, send, confirm."""

    async def test_a_skill_run_sends_the_skill_as_input_and_confirms_it_once(self) -> None:
        # AC-30: skills/list comes before thread/start, and one read-back finds the recorded input.
        self.list_skill(self.fakes.DEFAULT_CWD, self.fakes.skill_entry("s", SKILL_PATH))
        self.server.record_turn_input = True
        host = await self.opened()
        handle = await self.call(host.run_codex_skill("s", "do it"))
        methods = self.sent_methods()
        self.assertLess(methods.index("skills/list"), methods.index("thread/start"))
        starts = self.server.matching("turn/start")
        self.assertEqual([request.params["input"] for request in starts], [_skill_input("do it", "s", SKILL_PATH)])
        self.assertEqual(starts[0].params["threadId"], handle.thread_id)
        self.assertEqual(handle.turn_id, self.server.threads[handle.thread_id].turns[0].turn_id)
        reads = self.server.matching("thread/turns/list")
        self.assertEqual([request.params for request in reads], [{"threadId": handle.thread_id, "itemsView": "full", "sortDirection": "asc", "limit": 1}])
        self.assertLess(methods.index("turn/start"), methods.index("thread/turns/list"))
        self.assertEqual(self.interrupts(handle.thread_id), 0)

    async def test_a_skill_run_keeps_the_callers_posture_and_lists_skills_for_its_folder(self) -> None:
        # INV-24, INV-27: the folder the request names is the folder whose skills are listed.
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        folder_skill = os.path.join(WORK_A, ".codex", "skills", "s", "SKILL.md")
        self.list_skill(WORK_A, self.fakes.skill_entry("s", folder_skill, scope="repo"))
        self.server.record_turn_input = True
        host = await self.opened()
        request = CodexSpawnRequest(thread=CodexThreadSettings(cwd=WORK_A, model="gpt-5.5-codex"))
        handle = await self.call(host.run_codex_skill("s", "do it", request=request))
        self.assertEqual(self.server.matching("skills/list")[0].params, {"cwds": [WORK_A]})
        started = self.server.matching("thread/start")[-1].params
        self.assertEqual((started.get("cwd"), started.get("model")), (WORK_A, "gpt-5.5-codex"))
        self.assertEqual(self.server.matching("turn/start")[-1].params["input"], _skill_input("do it", "s", folder_skill))
        self.assertEqual(self.server.matching("turn/start")[-1].params["threadId"], handle.thread_id)

    async def test_the_first_enabled_skill_of_a_shared_name_is_used(self) -> None:
        # EC-31, INV-24.
        first = os.path.abspath(os.path.join(os.sep, "repo", "s", "SKILL.md"))
        second = os.path.abspath(os.path.join(os.sep, "user", "s", "SKILL.md"))
        disabled = os.path.abspath(os.path.join(os.sep, "admin", "s", "SKILL.md"))
        self.list_skill(
            self.fakes.DEFAULT_CWD,
            self.fakes.skill_entry("s", disabled, scope="admin", enabled=False),
            self.fakes.skill_entry("s", first, scope="repo"),
            self.fakes.skill_entry("s", second, scope="user"),
        )
        self.server.record_turn_input = True
        host = await self.opened()
        await self.call(host.run_codex_skill("s", "do it"))
        self.assertEqual(self.server.matching("turn/start")[-1].params["input"], _skill_input("do it", "s", first))

    async def test_an_unknown_or_disabled_skill_is_refused_before_any_thread_starts(self) -> None:
        # AC-31, EC-30, EC-32, INV-24: exact matching; the message lists the enabled names only.
        self.list_skill(
            self.fakes.DEFAULT_CWD,
            self.fakes.skill_entry("openai-docs", DOCS_PATH, scope="system"),
            self.fakes.skill_entry("rv", SKILL_PATH, enabled=False),
            self.fakes.skill_entry("review-agent", SKILL_PATH, scope="system", enabled=False),
            self.fakes.skill_entry("s", SKILL_PATH),
        )
        host = await self.opened()
        for skill in ("zz", "OpenAI-Docs"):
            with self.subTest(skill=skill):
                self.remark()
                error = await self.assert_codex_error(host.run_codex_skill(skill, "x"), "codex.skill_not_found")
                self.assertEqual(error.operation, "run_codex_skill")
                prefix = _not_found_prefix(skill, APP_SERVER_PLACE)
                self.assertTrue(error.message.startswith(prefix), error.message)
                self.assertTrue(error.message.endswith("."), error.message)
                names = set(_name_tokens(error.message[len(prefix) :]))
                self.assertLessEqual({"openai-docs", "s"}, names, error.message)
                self.assertFalse({"rv", "review-agent"} & names, error.message)
                self.assertEqual(self.sent_methods(), ["skills/list"])
        for skill in ("rv", "review-agent"):
            with self.subTest(disabled=skill):
                self.remark()
                error = await self.assert_codex_error(host.run_codex_skill(skill, "x"), "codex.skill_disabled")
                self.assertEqual(error.operation, "run_codex_skill")
                self.assertEqual(error.message, SKILL_DISABLED_MESSAGE.format(skill=skill, place=APP_SERVER_PLACE))
                self.assertEqual(self.sent_methods(), ["skills/list"])
        self.assertEqual(self.count("thread/start"), 0)
        self.assertEqual(self.count("turn/start"), 0)

    async def test_the_not_found_message_names_the_folder_and_bounds_the_list(self) -> None:
        # AC-31, EC-34, D-20: at most fifty names, then "and N more"; "none" when nothing is enabled.
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        many = [self.fakes.skill_entry(f"skill-{index:02d}", os.path.join(WORK_A, f"skill-{index:02d}", "SKILL.md")) for index in range(SKILL_NAMES_IN_ERROR + 5)]
        self.list_skill(WORK_A, *many)
        self.list_skill(self.fakes.DEFAULT_CWD, self.fakes.skill_entry("rv", SKILL_PATH, enabled=False))
        host = await self.opened()

        request = CodexSpawnRequest(thread=CodexThreadSettings(cwd=WORK_A))
        error = await self.assert_codex_error(host.run_codex_skill("zz", "x", request=request), "codex.skill_not_found")
        prefix = _not_found_prefix("zz", f"the folder {WORK_A}")
        self.assertTrue(error.message.startswith(prefix), error.message)
        self.assertTrue(error.message.endswith(" and 5 more."), error.message)
        tokens = set(_name_tokens(error.message[len(prefix) :]))
        named = [entry["name"] for entry in many if entry["name"] in tokens]
        self.assertEqual(len(named), SKILL_NAMES_IN_ERROR, named)

        nothing = await self.assert_codex_error(host.run_codex_skill("zz", "x"), "codex.skill_not_found")
        self.assertEqual(nothing.message, SKILL_NOT_FOUND_MESSAGE.format(skill="zz", place=APP_SERVER_PLACE, names="none"))

    async def test_the_docs_run_is_the_skill_run_for_openai_docs(self) -> None:
        # AC-32, INV-26: the same input and read-back, and the errors carry run_codex_openai_docs.
        self.server.record_turn_input = True
        host = await self.opened()
        missing = await self.assert_codex_error(host.run_codex_openai_docs("q"), "codex.skill_not_found")
        self.assertEqual(missing.operation, "run_codex_openai_docs")
        self.assertIn("'openai-docs'", missing.message)

        self.list_skill(self.fakes.DEFAULT_CWD, self.fakes.skill_entry("openai-docs", DOCS_PATH, scope="system", enabled=False))
        disabled = await self.assert_codex_error(host.run_codex_openai_docs("q"), "codex.skill_disabled")
        self.assertEqual(disabled.operation, "run_codex_openai_docs")

        self.list_skill(self.fakes.DEFAULT_CWD, self.fakes.skill_entry("openai-docs", DOCS_PATH, scope="system"))
        self.remark()
        handle = await self.call(host.run_codex_openai_docs("q"))
        self.assertEqual(self.server.matching("turn/start")[-1].params["input"], _skill_input("q", "openai-docs", DOCS_PATH))
        self.assertEqual(self.sent_methods().count("thread/turns/list"), 1)
        self.assertEqual(self.interrupts(handle.thread_id), 0)

        self.server.drop_skill_input = True
        dropped = await self.assert_codex_error(host.run_codex_openai_docs("q"), "codex.command_not_run")
        self.assertEqual(dropped.operation, "run_codex_openai_docs")
        self.assertEqual(dropped.message, SKILL_DROPPED_MESSAGE.format(skill="openai-docs") + thread_suffix(self.started_thread()))

    async def test_bad_skill_arguments_are_refused_before_any_request(self) -> None:
        # AC-42, EC-37, EC-48, INV-6: an ephemeral thread could never be confirmed, so it is refused first.
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings
        from vidbyte.lib.dataclasses.codex_host import CodexGoal, CodexSpawnRequest

        self.list_skill(self.fakes.DEFAULT_CWD, self.fakes.skill_entry("s", SKILL_PATH), self.fakes.skill_entry("openai-docs", DOCS_PATH, scope="system"))
        host = await self.opened()
        ephemeral = CodexSpawnRequest(thread=CodexThreadSettings(ephemeral=True))
        exact = (
            ("run_codex_skill", lambda: host.run_codex_skill("s", "x", request=ephemeral), EPHEMERAL_SKILL_MESSAGE),
            ("run_codex_openai_docs", lambda: host.run_codex_openai_docs("q", request=ephemeral), EPHEMERAL_SKILL_MESSAGE),
            ("run_codex_skill", lambda: host.run_codex_skill("s", "x", request=CodexSpawnRequest(prompt="p")), OWN_INPUT_MESSAGE),
            ("run_codex_skill", lambda: host.run_codex_skill("s", "x", request=CodexSpawnRequest(goal=CodexGoal(objective="g"))), OWN_INPUT_MESSAGE),
            ("run_codex_openai_docs", lambda: host.run_codex_openai_docs("q", request=CodexSpawnRequest(prompt="p")), OWN_INPUT_MESSAGE),
            ("run_codex_skill", lambda: host.run_codex_skill("", "x"), SKILL_NAME_MESSAGE),
        )
        for operation, start, message in exact:
            with self.subTest(operation=operation, message=message):
                error = await self.refused(start())
                self.assertEqual(str(error), message.format(operation=operation))
        for name, start in (("empty prompt", lambda: host.run_codex_skill("s", "")), ("empty question", lambda: host.run_codex_openai_docs(""))):
            with self.subTest(case=name):
                await self.refused(start())
        self.assertEqual(self.sent(), [])


@requires_sdk
class CodexSkillReadBackTests(_GoalSkillCase):
    """AC-39, AC-40, AC-43, EC-45, EC-46, EC-50, INV-34 and INV-35: the bounded read-back and its single interrupt."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.list_skill(self.fakes.DEFAULT_CWD, self.fakes.skill_entry("s", SKILL_PATH))

    async def test_input_recorded_late_is_found_on_a_later_read(self) -> None:
        # EC-45: two reads miss the userMessage, the third finds it.
        self.fast_read_back()
        self.server.record_turn_input = True
        self.server.input_hidden_reads = 2
        host = await self.opened()
        handle = await self.call(host.run_codex_skill("s", "do it"))
        self.assertEqual(self.count("thread/turns/list"), 3)
        self.assertEqual(self.interrupts(handle.thread_id), 0)

    async def test_input_never_recorded_or_recorded_without_the_skill_stops_the_run_once(self) -> None:
        # AC-39, EC-46, INV-35: exactly the attempt bound of reads when nothing is recorded; one read when the skill was dropped.
        self.fast_read_back()
        self.patch_connection("CODEX_HOST_WORKER_THREADS", 1)
        host = await self.opened()
        error = await self.assert_codex_error(host.run_codex_skill("s", "do it"), "codex.command_not_run")
        thread_id = self.started_thread()
        self.assertEqual(error.operation, "run_codex_skill")
        self.assertEqual(error.message, INPUT_NOT_RECORDED_MESSAGE.format(skill="s", seconds=FAR_DEADLINE_SECONDS) + thread_suffix(thread_id))
        self.assertEqual(self.count("thread/turns/list", lambda params: params["threadId"] == thread_id), INPUT_CHECK_ATTEMPTS)
        self.assertEqual(self.interrupts(thread_id), 1)
        await self.barrier(host, thread_id)
        self.assertEqual(self.interrupts(thread_id), 1)

        self.server.record_turn_input = True
        self.server.drop_skill_input = True
        error = await self.assert_codex_error(host.run_codex_skill("s", "do it"), "codex.command_not_run")
        dropped = self.started_thread()
        self.assertEqual(error.message, SKILL_DROPPED_MESSAGE.format(skill="s") + thread_suffix(dropped))
        self.assertEqual(self.count("thread/turns/list", lambda params: params["threadId"] == dropped), 1)
        self.assertEqual(self.interrupts(dropped), 1)
        await self.barrier(host, dropped)
        self.assertEqual(self.interrupts(dropped), 1)

    async def test_a_failed_interrupt_does_not_hide_the_miss(self) -> None:
        # EC-29 for skills, INV-35: the interrupt's failure is ignored.
        self.server.record_turn_input = True
        self.server.drop_skill_input = True
        self.server.fail("turn/interrupt", self.fakes.FakeRpcError(-32603, "interrupt refused"))
        host = await self.opened()
        error = await self.assert_codex_error(host.run_codex_skill("s", "do it"), "codex.command_not_run")
        self.assertEqual(error.message, SKILL_DROPPED_MESSAGE.format(skill="s") + thread_suffix(self.started_thread()))
        self.assertEqual(self.interrupts(self.started_thread()), 1)

    async def test_a_read_back_that_fails_interrupts_once_and_keeps_its_error(self) -> None:
        # AC-40, INV-35: the read's api_error keeps operation list_codex_turns and gains SKILL_UNCHECKED_MESSAGE.
        self.patch_connection("CODEX_HOST_WORKER_THREADS", 1)
        self.server.record_turn_input = True
        self.server.fail("thread/turns/list", self.fakes.FakeRpcError(-32603, "history read failed"))
        host = await self.opened()
        error = await self.assert_codex_error(host.run_codex_skill("s", "do it"), "codex.api_error")
        thread_id = self.started_thread()
        self.assertEqual(error.operation, "list_codex_turns")
        self.assertTrue(error.message.endswith(SKILL_UNCHECKED_MESSAGE.format(thread_id=thread_id)), error.message)
        self.assertEqual(error.next_step, NEXT_STEPS["codex.api_error"])
        await self.barrier(host, thread_id)
        self.assertEqual(self.interrupts(thread_id), 1)

    async def test_a_skill_run_cancelled_during_its_read_back_is_interrupted_once(self) -> None:
        # INV-35: CancelledError propagates after the single interrupt.
        self.patch_connection("CODEX_HOST_WORKER_THREADS", 1)
        self.server.record_turn_input = True
        host = await self.opened()
        hold = self.server.hold("thread/turns/list")
        task = asyncio.ensure_future(host.run_codex_skill("s", "do it"))
        thread_id = (await asyncio.to_thread(hold.wait_arrived)).params["threadId"]
        task.cancel()
        # Releasing now frees the one worker, so the interrupt queued behind the held read can run.
        hold.release()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, WAIT_SECONDS)
        await self.wait_for_request("turn/interrupt", lambda params: params["threadId"] == thread_id)
        await self.barrier(host, thread_id)
        self.assertEqual(self.interrupts(thread_id), 1)

    async def test_a_deadline_shorter_than_the_interval_allows_one_read(self) -> None:
        # AC-43, EC-50, INV-34: no wait would end before the deadline, so the first miss ends the read-back.
        self.patch_skill_functions("CODEX_HOST_INPUT_CHECK_DEADLINE_SECONDS", 0.25)
        host = await self.opened()
        error = await self.assert_codex_error(host.run_codex_skill("s", "do it"), "codex.command_not_run")
        thread_id = self.started_thread()
        self.assertEqual(error.operation, "run_codex_skill")
        self.assertEqual(error.message, INPUT_NOT_RECORDED_MESSAGE.format(skill="s", seconds=0.25) + thread_suffix(thread_id))
        on_thread = [method for method in _thread_methods(self.sent(), thread_id) if method in ("thread/turns/list", "turn/interrupt")]
        self.assertEqual(on_thread, ["thread/turns/list", "turn/interrupt"])


if __name__ == "__main__":
    unittest.main()
