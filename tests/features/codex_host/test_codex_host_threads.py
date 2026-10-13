"""FILE: tests/features/codex_host/test_codex_host_threads.py

PURPOSE: Proves the thread operations over the in-memory app-server: continue (its wire order, the busy and unknown-thread refusals, and the race between two continues), the per-operation field rules, launch (prompt order, one preflight, partial failure), fork (its turn rules and Codex's refusal), list and read, readiness, rate limits and models, the user-reviewer refusal after start and resume, dynamic tools (a fork's included), and the agents config.
ROLE IN CODEBASE: Thread layer of tests/features/codex_host/ (spec AC-14, AC-15, AC-18, AC-21, AC-22, AC-37, INV-24, INV-27 to INV-30, INV-37, D-20, D-22, D-28, D-29, D-32, EC-6, EC-11, EC-15 to EC-22, EC-47, EC-49, EC-51, EC-52, EC-75, EC-76). Every class needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: The fake app-server answers as codex app-server 0.162 does and stores threads and turns, so fork rules, reviewer reports and listing run against data the test seeds. The fake reports the reviewer the request sent, else its default (user), unless force_reviewer or force_policy is set, which is how the D-32 rows are staged.
COMMON MODIFICATION PATTERNS: Add a field-rule row to the tables in test_fields_an_operation_cannot_apply_are_rejected_before_any_request when spec section 9.2 adds one; add a reviewer case as a subTest with the fake's reviewer state reset afterwards.
KNOWN EDGE CASES: The partial-launch test seeds four threads first so that no thread or turn id the error might quote contains a standalone 2, which keeps the "2 were started" check honest. thread/read always carries includeTurns because openai-codex's thread_read sends it.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host/spec.md sections 6.1 (INV-24, INV-27 to INV-30, INV-37), 8.1 (D-20, D-22, D-28, D-29, D-32) and 9.2.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_threads.py
"""

from __future__ import annotations

import asyncio
import re
import unittest
from typing import Any
from unittest import mock

from tests.features.codex_host.codex_host_support import (
    EXPERIMENTAL_API_TEXT,
    MINIMUM_VERSION,
    NEXT_STEPS,
    WAIT_SECONDS,
    HostTestCase,
    assert_no_canary,
    input_texts,
    make_echo_tool,
    requires_sdk,
)
from vidbyte.lib.errors import CodexAgentError, ConfigurationError

GRANULAR_POLICY = {"granular": {"mcp_elicitations": True, "rules": True, "sandbox_approval": True}}
APPROVAL_KEYS = ("approvalPolicy", "approvalsReviewer")


def _thread_methods(server: Any, thread_id: str) -> list[str]:
    return [request.method for request in server.requests if request.params.get("threadId") == thread_id]


@requires_sdk
class CodexHostContinueTests(HostTestCase):
    """AC-14, INV-24 and INV-27: continue, its refusals, and the fields each operation rejects."""

    async def test_continue_reads_resumes_without_turns_then_starts_a_turn(self) -> None:
        # AC-14, INV-28, INV-30: resume sends no approval fields and no config the caller did not set.
        host = await self.open_host()
        seeded = self.server.seed_thread(completed_turns=1)
        handle = await asyncio.wait_for(host.continue_codex_thread(seeded.thread_id, "Carry on."), WAIT_SECONDS)

        self.assertEqual(_thread_methods(self.server, seeded.thread_id), ["thread/read", "thread/resume", "turn/start"])
        resume = self.server.matching("thread/resume")[0].params
        self.assertIs(resume["excludeTurns"], True)
        for key in (*APPROVAL_KEYS, "config"):
            self.assertNotIn(key, resume)
        self.assertEqual(input_texts(self.server.matching("turn/start")[0].params), [("text", "Carry on.")])
        self.assertEqual((handle.thread_id, handle.turn_id), (seeded.thread_id, seeded.turns[-1].turn_id))
        self.assert_problem(await host.get_codex_turn_result(handle), "inProgress", None)

    async def test_continue_and_review_refuse_a_busy_or_unknown_thread(self) -> None:
        # AC-14, EC-15, EC-18, INV-24: busy sends nothing at all; an unknown thread never reaches resume or a turn.
        from vidbyte.lib.dataclasses.codex_host import CodexReviewTarget
        from vidbyte.lib.enums.codex import CodexReviewTargetKind

        host = await self.open_host()
        running = await self.spawn(host)
        sent = len(self.server.requests)
        await self.assert_codex_error(host.continue_codex_thread(running.thread_id, "Again."), "codex.session_busy")
        target = CodexReviewTarget(kind=CodexReviewTargetKind.UNCOMMITTED_CHANGES)
        await self.assert_codex_error(host.start_codex_review(running.thread_id, target), "codex.session_busy")
        self.assertEqual(len(self.server.requests), sent)

        await self.assert_codex_error(host.continue_codex_thread("thr-unknown", "Hello."), "codex.session_not_found")
        self.assertEqual(_thread_methods(self.server, "thr-unknown"), ["thread/read"])

    async def test_two_concurrent_continues_on_one_idle_thread_start_one_turn(self) -> None:
        # EC-16, INV-24: the first call reserves the thread before it awaits anything, so the second is refused.
        host = await self.open_host()
        idle = self.server.seed_thread(completed_turns=1)
        outcomes = await asyncio.wait_for(
            asyncio.gather(
                host.continue_codex_thread(idle.thread_id, "First."),
                host.continue_codex_thread(idle.thread_id, "Second."),
                return_exceptions=True,
            ),
            WAIT_SECONDS,
        )
        errors = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
        self.assertEqual(len(errors), 1, outcomes)
        self.assertIsInstance(errors[0], CodexAgentError)
        self.assertEqual(errors[0].failure_code, "codex.session_busy")
        self.assertEqual(self.count("turn/start", lambda params: params["threadId"] == idle.thread_id), 1)

    async def test_fields_an_operation_cannot_apply_are_rejected_before_any_request(self) -> None:
        # INV-27, AC-14, AC-18, EC-51, section 9.2 field rules: no field is silently dropped, and nothing is sent.
        from vidbyte.lib.dataclasses.codex import CodexThreadSettings, CodexTurnSettings
        from vidbyte.lib.dataclasses.codex_host import CodexGoal, CodexSpawnRequest
        from vidbyte.lib.enums.codex import CodexPersonality, CodexReasoningEffort, CodexThreadSource, CodexThreadStartSource

        host = await self.open_host()
        seeded = self.server.seed_thread(completed_turns=1)
        goal = CodexGoal(objective="Ship it.")
        continue_rejects = {
            "prompt": CodexSpawnRequest(prompt="Hello."),
            "goal": CodexSpawnRequest(goal=goal),
            "thread.ephemeral": CodexSpawnRequest(thread=CodexThreadSettings(ephemeral=True)),
            "thread.thread_source": CodexSpawnRequest(thread=CodexThreadSettings(thread_source=CodexThreadSource.USER)),
            "thread.service_name": CodexSpawnRequest(thread=CodexThreadSettings(service_name="vidbyte")),
            "thread.session_start_source": CodexSpawnRequest(thread=CodexThreadSettings(session_start_source=CodexThreadStartSource.STARTUP)),
            "tools": CodexSpawnRequest(tools=(make_echo_tool(),)),
            "name": CodexSpawnRequest(name="Renamed"),
        }
        fork_rejects = {
            "prompt": CodexSpawnRequest(prompt="Hello."),
            "goal": CodexSpawnRequest(goal=goal),
            "thread.personality": CodexSpawnRequest(thread=CodexThreadSettings(personality=CodexPersonality.FRIENDLY)),
            "thread.service_name": CodexSpawnRequest(thread=CodexThreadSettings(service_name="vidbyte")),
            "thread.session_start_source": CodexSpawnRequest(thread=CodexThreadSettings(session_start_source=CodexThreadStartSource.STARTUP)),
            "turn": CodexSpawnRequest(turn=CodexTurnSettings(effort=CodexReasoningEffort.LOW)),
            "tools": CodexSpawnRequest(tools=(make_echo_tool(),)),
            "disabled_plugin_ids": CodexSpawnRequest(disabled_plugin_ids=("github",)),
            "output_schema": CodexSpawnRequest(output_schema={"type": "object"}),
            "max_output_tokens": CodexSpawnRequest(max_output_tokens=100),
            "timeout_seconds": CodexSpawnRequest(timeout_seconds=5.0),
        }
        calls: list[tuple[str, Any]] = []
        calls += [(f"continue {field}", lambda request=request: host.continue_codex_thread(seeded.thread_id, "Carry on.", overrides=request)) for field, request in continue_rejects.items()]
        calls += [(f"fork {field}", lambda request=request: host.fork_codex_thread(seeded.thread_id, overrides=request)) for field, request in fork_rejects.items()]
        calls += [
            ("launch prompt", lambda: host.launch_codex_subagents(["One."], request=CodexSpawnRequest(prompt="Hello."))),
            ("launch goal", lambda: host.launch_codex_subagents(["One."], request=CodexSpawnRequest(goal=goal))),
            ("spawn with neither prompt nor goal", lambda: host.spawn_codex_thread(CodexSpawnRequest())),
            ("launch with no prompts", lambda: host.launch_codex_subagents([])),
            ("launch with a prompt that is not text", lambda: host.launch_codex_subagents([123])),
            ("launch limit 0", lambda: host.launch_codex_subagents(["One."], limit=0)),
            ("launch limit True", lambda: host.launch_codex_subagents(["One."], limit=True)),
            ("launch over its limit", lambda: host.launch_codex_subagents(["One.", "Two.", "Three."], limit=2)),
        ]
        for label, call in calls:
            with self.subTest(case=label):
                sent = len(self.server.requests)
                with self.assertRaises(ConfigurationError):
                    await asyncio.wait_for(call(), WAIT_SECONDS)
                self.assertEqual(len(self.server.requests), sent, self.server.methods()[sent:])


@requires_sdk
class CodexHostLaunchAndForkTests(HostTestCase):
    """AC-18 and AC-15: launch order and partial failure; fork rules."""

    async def test_launch_starts_one_thread_per_prompt_in_order_after_one_preflight(self) -> None:
        # AC-18, INV-37, D-22: the request's name goes on every thread.
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        host = await self.open_host()
        account_reads = self.count("account/read")
        prompts = ["Part one.", "Part two.", "Part three."]
        handles = await asyncio.wait_for(host.launch_codex_subagents(prompts, request=CodexSpawnRequest(name="Worker")), WAIT_SECONDS)

        turn_starts = [request.params for request in self.server.matching("turn/start")]
        self.assertEqual([input_texts(params) for params in turn_starts], [[("text", prompt)] for prompt in prompts])
        self.assertEqual([handle.thread_id for handle in handles], [params["threadId"] for params in turn_starts])
        self.assertEqual(len({handle.thread_id for handle in handles}), 3)
        for handle in handles:
            self.assertEqual([turn.turn_id for turn in self.server.threads[handle.thread_id].turns], [handle.turn_id])
        self.assertEqual([request.params["name"] for request in self.server.matching("thread/name/set")], ["Worker"] * 3)
        self.assertEqual(self.count("account/read") - account_reads, 1)

    async def test_a_launch_that_fails_midway_interrupts_each_turn_it_started_once(self) -> None:
        # AC-18, EC-52, INV-37: the error says 2 turns were started, and only those two get one interrupt each.
        from tests.features.codex_host.codex_host_fakes import FakeRpcError

        for _ in range(4):
            self.server.seed_thread(completed_turns=1)
        self.patch_connection("CODEX_HOST_WORKER_THREADS", 1)
        host = await self.open_host()
        self.server.fail("turn/start", FakeRpcError(-32603, "turn/start failed"), predicate=lambda params: input_texts(params) == [("text", "Part three.")])
        error = await self.assert_codex_error(host.launch_codex_subagents(["Part one.", "Part two.", "Part three."]), "codex.api_error")
        self.assertRegex(error.message, re.compile(r"\b2\b"))

        started = [request.params["threadId"] for request in self.server.matching("turn/start")][:2]
        turn_ids = [self.server.threads[thread_id].turns[-1].turn_id for thread_id in started]
        await self.wait_for_request("turn/interrupt", count=2)
        # Barrier: with one host worker, this read returns only after any interrupt queued before it was sent.
        await asyncio.wait_for(host.read_codex_thread(started[0]), WAIT_SECONDS)
        interrupted = [request.params["turnId"] for request in self.server.matching("turn/interrupt")]
        self.assertEqual(sorted(interrupted), sorted(turn_ids))

    async def test_fork_reads_the_turns_first_and_forks_through_a_completed_turn(self) -> None:
        # AC-15, D-29, EC-22: exclude_turns only shapes the response; an empty from_turn_id means the last completed turn.
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        host = await self.open_host()
        source = self.server.seed_thread(completed_turns=2)
        first, second = (turn.turn_id for turn in source.turns)
        info = await asyncio.wait_for(host.fork_codex_thread(source.thread_id, from_turn_id=first, exclude_turns=True), WAIT_SECONDS)
        self.assertEqual(_thread_methods(self.server, source.thread_id), ["thread/read", "thread/fork"])
        self.assertIs(self.server.matching("thread/read")[0].params["includeTurns"], True)
        fork = self.server.matching("thread/fork")[0].params
        self.assertEqual((fork["lastTurnId"], fork["excludeTurns"]), (first, True))
        self.assertNotEqual(info.thread_id, source.thread_id)
        self.assertIn(info.thread_id, self.server.threads)
        self.assertEqual(info.forked_from_id, source.thread_id)
        self.assertEqual(info.turns, ())

        await asyncio.wait_for(host.fork_codex_thread(source.thread_id, overrides=CodexSpawnRequest(name="Fork of the notes")), WAIT_SECONDS)
        fork = self.server.matching("thread/fork")[1].params
        self.assertEqual(fork["lastTurnId"], second)
        self.assertNotIn("excludeTurns", fork)
        renamed = self.server.matching("thread/name/set")[0].params
        self.assertNotEqual(renamed["threadId"], source.thread_id)
        self.assertEqual(renamed["name"], "Fork of the notes")

        # EC-21: while the last turn runs, an empty from_turn_id forks through the last completed one.
        busy = self.server.seed_thread(completed_turns=1, running_turn=True)
        completed, running = (turn.turn_id for turn in busy.turns)
        await asyncio.wait_for(host.fork_codex_thread(busy.thread_id), WAIT_SECONDS)
        self.assertEqual(self.server.matching("thread/fork")[2].params["lastTurnId"], completed)

        # EC-19, EC-20: no completed turn, an unknown turn, or one in progress stops before thread/fork.
        empty = self.server.seed_thread(completed_turns=0)
        for thread_id, from_turn_id in ((empty.thread_id, ""), (source.thread_id, "turn-unknown"), (busy.thread_id, running)):
            with self.subTest(thread_id=thread_id, from_turn_id=from_turn_id):
                forks = self.count("thread/fork")
                await self.assert_codex_error(host.fork_codex_thread(thread_id, from_turn_id=from_turn_id), "codex.fork_failed")
                self.assertEqual(self.count("thread/fork"), forks)

    async def test_fork_maps_codex_refusals_and_unknown_threads(self) -> None:
        # D-13: an invalid-request or invalid-params answer to thread/fork means fork_failed; a failed read means not found.
        from tests.features.codex_host.codex_host_fakes import FakeRpcError

        host = await self.open_host()
        source = self.server.seed_thread(completed_turns=1)
        for code in (-32600, -32602):
            with self.subTest(json_rpc_code=code):
                self.server.fail("thread/fork", FakeRpcError(code, "cannot fork this thread"), times=1)
                await self.assert_codex_error(host.fork_codex_thread(source.thread_id), "codex.fork_failed")
        await self.assert_codex_error(host.fork_codex_thread("thr-unknown"), "codex.session_not_found")
        self.assertEqual(self.count("thread/fork", lambda params: params["threadId"] == "thr-unknown"), 0)


@requires_sdk
class CodexHostReadTests(HostTestCase):
    """AC-21 and AC-22: listing and reading threads, readiness, rate limits and models."""

    async def test_list_sends_every_set_argument_and_omits_the_empty_ones(self) -> None:
        # AC-21: archived is sent only when True; the page and each thread are translated field by field.
        from vidbyte.lib.enums.codex import CodexSortDirection, CodexThreadSortKey, CodexThreadSourceKind, CodexThreadStatus

        host = await self.open_host()
        named = self.server.seed_thread(completed_turns=1)
        named.name, named.forked_from = "Release notes", "thr-parent"
        active = self.server.seed_thread(completed_turns=0, running_turn=True)
        workspace = self.fakes.DEFAULT_CWD

        page = await asyncio.wait_for(
            host.list_codex_threads(
                cwd=workspace,
                search="notes",
                archived=True,
                source_kinds=(CodexThreadSourceKind.APP_SERVER, CodexThreadSourceKind.CLI),
                sort=CodexThreadSortKey.UPDATED_AT,
                sort_direction=CodexSortDirection.DESC,
                cursor="cursor-before",
            ),
            WAIT_SECONDS,
        )
        expected = {"cwd": workspace, "searchTerm": "notes", "archived": True, "sourceKinds": ["appServer", "cli"], "sortKey": "updated_at", "sortDirection": "desc", "cursor": "cursor-before"}
        self.assertEqual(self.server.matching("thread/list")[0].params, expected)
        self.assertEqual(page.next_cursor, "cursor-after-page")
        listed = {info.thread_id: info for info in page.threads}
        info = listed[named.thread_id]
        fields = (info.name, info.preview, info.cwd, info.status, info.model, info.model_provider, info.created_at, info.updated_at, info.forked_from_id, info.ephemeral, info.turns)
        base = self.fakes.BASE_TIME
        self.assertEqual(fields, ("Release notes", f"preview of {named.thread_id}", workspace, CodexThreadStatus.IDLE, "gpt-5.5", "openai", base, base + 60, "thr-parent", False, ()))
        self.assertEqual(listed[active.thread_id].status, CodexThreadStatus.ACTIVE)

        await asyncio.wait_for(host.list_codex_threads(), WAIT_SECONDS)
        self.assertEqual(self.server.matching("thread/list")[1].params, {})

    async def test_read_returns_turn_summaries_only_when_asked(self) -> None:
        # AC-21, EC-18: summaries carry status, final answer, error message and timestamps; unknown ids are not found.
        from vidbyte.lib.enums.codex import CodexTurnStatus

        host = await self.open_host()
        thread = self.server.seed_thread(completed_turns=1, running_turn=True)
        failed = self.fakes.FakeTurn(turn_id=self.server.next_turn_id(), status="failed", error={"message": "Codex failed the turn.", "codexErrorInfo": "other"})
        thread.turns.insert(1, failed)
        completed, _, running = thread.turns
        base = self.fakes.BASE_TIME

        info = await asyncio.wait_for(host.read_codex_thread(thread.thread_id, include_turns=True), WAIT_SECONDS)
        self.assertIs(self.server.matching("thread/read")[0].params["includeTurns"], True)
        rows = [(summary.turn_id, summary.status, summary.final_response, summary.error_message, summary.started_at, summary.completed_at) for summary in info.turns]
        self.assertEqual(
            rows,
            [
                (completed.turn_id, CodexTurnStatus.COMPLETED, f"Answer of {completed.turn_id}.", "", base, base + 5),
                (failed.turn_id, CodexTurnStatus.FAILED, "", "Codex failed the turn.", base, base + 5),
                (running.turn_id, CodexTurnStatus.RUNNING, "", "", base, None),
            ],
        )
        self.assertEqual((await asyncio.wait_for(host.read_codex_thread(thread.thread_id), WAIT_SECONDS)).turns, ())
        await self.assert_codex_error(host.read_codex_thread("thr-unknown"), "codex.session_not_found")

    async def test_readiness_reports_account_and_sandbox_without_the_email(self) -> None:
        # AC-22, EC-6, EC-11, INV-9, D-28: problems are reported in the result, never raised.
        from vidbyte.lib.enums.codex import CodexAccountKind, CodexSandboxReadiness

        self.patch_platform("win32")
        host = await self.open_host()
        readiness = await asyncio.wait_for(host.check_codex_ready(), WAIT_SECONDS)
        fields = (readiness.ready, readiness.version, readiness.minimum_version, readiness.signed_in, readiness.account, readiness.plan_type, readiness.sandbox, readiness.problems)
        self.assertEqual(fields, (True, "0.162.1", MINIMUM_VERSION, True, CodexAccountKind.CHATGPT, "plus", CodexSandboxReadiness.READY, ()))
        assert_no_canary(self, [repr(readiness)])

        cases = (
            ("signed out", lambda: setattr(self.server, "account", None), CodexSandboxReadiness.READY, ["codex.not_signed_in"]),
            ("sandbox not configured", lambda: setattr(self.server, "sandbox_status", "notConfigured"), CodexSandboxReadiness.NOT_CONFIGURED, ["codex.sandbox_not_ready"]),
            ("readiness unknown to the runtime", lambda: self.server.fail("windowsSandbox/readiness", self.fakes.FakeRpcError(-32601, "method not found"), times=1), CodexSandboxReadiness.NOT_CHECKED, []),
        )
        for label, arrange, sandbox, codes in cases:
            with self.subTest(case=label):
                arrange()
                readiness = await asyncio.wait_for(host.check_codex_ready(), WAIT_SECONDS)
                self.assertEqual(readiness.sandbox, sandbox)
                self.assertEqual([problem.code.value for problem in readiness.problems], codes)
                self.assertEqual([problem.next_step for problem in readiness.problems], [NEXT_STEPS[code] for code in codes])
                self.assertEqual(readiness.ready, not codes)
                if label == "signed out":
                    self.assertEqual((readiness.signed_in, readiness.account, readiness.plan_type), (False, CodexAccountKind.NONE, ""))
                self.server.account = {"type": "chatgpt", "email": "owner@example.invalid", "planType": "plus"}
                self.server.sandbox_status = "ready"

        readiness_reads = self.count("windowsSandbox/readiness")
        with mock.patch("sys.platform", "linux"):
            readiness = await asyncio.wait_for(host.check_codex_ready(), WAIT_SECONDS)
        self.assertEqual(readiness.sandbox, CodexSandboxReadiness.NOT_CHECKED)
        self.assertEqual(self.count("windowsSandbox/readiness"), readiness_reads)

    async def test_rate_limits_and_models_are_translated_across_pages(self) -> None:
        # AC-22, EC-8, D-20: a None allowance stays None; models come from both pages, hidden ones only on request.
        host = await self.open_host()
        limits = await asyncio.wait_for(host.get_codex_rate_limits(), WAIT_SECONDS)
        base = self.fakes.BASE_TIME
        self.assertEqual((limits.ordinary_usage_allowed, limits.plan_type), (True, "plus"))
        self.assertEqual((limits.primary.used_percent, limits.primary.resets_at, limits.primary.window_minutes), (42, base + 3600, 300))
        self.assertEqual((limits.secondary.used_percent, limits.secondary.resets_at, limits.secondary.window_minutes), (7, base + 86400, 10080))
        self.server.ordinary_usage_allowed = None
        self.assertIsNone((await asyncio.wait_for(host.get_codex_rate_limits(), WAIT_SECONDS)).ordinary_usage_allowed)

        models = await asyncio.wait_for(host.list_codex_models(), WAIT_SECONDS)
        self.assertEqual([model.model_id for model in models], ["gpt-5.5", "gpt-5.5-codex-latest"])
        first = models[0]
        fields = (first.model, first.display_name, first.description, first.hidden, first.is_default, first.default_effort, first.efforts)
        self.assertEqual(fields, ("gpt-5.5", "GPT-5.5", "Fake model gpt-5.5.", False, True, "medium", ("low", "medium", "max")))
        self.assertEqual(models[1].model, "gpt-5.5-codex")
        listed = await asyncio.wait_for(host.list_codex_models(include_hidden=True), WAIT_SECONDS)
        self.assertEqual([model.model_id for model in listed], ["gpt-5.5", "codex-auto-review", "gpt-5.5-codex-latest"])
        last_pages = [request.params for request in self.server.matching("model/list")][-2:]
        self.assertEqual([params.get("includeHidden") for params in last_pages], [True, True])
        self.assertEqual(last_pages[1].get("cursor"), "page-2")


@requires_sdk
class CodexHostReviewerTests(HostTestCase):
    """AC-37, INV-28 and D-32: a thread whose approvals go to a user reviewer never starts a turn."""

    async def test_a_user_reviewer_reported_after_thread_start_stops_spawn_goal_and_launch(self) -> None:
        # AC-37, EC-75: the fake's configured default reviewer is user, as an interactive Codex install's can be.
        from vidbyte.lib.dataclasses.codex_host import CodexGoal, CodexSpawnRequest
        from vidbyte.lib.enums.codex import CodexApprovalPolicy

        host = await self.open_host()
        refused = {
            "spawn with only approval_policy": lambda: host.spawn_codex_thread(CodexSpawnRequest(prompt="Fix it.", approval_policy=CodexApprovalPolicy.UNTRUSTED, name="Fixer")),
            "goal spawn": lambda: host.spawn_codex_thread(CodexSpawnRequest(goal=CodexGoal(objective="Ship it."), approval_policy=CodexApprovalPolicy.ON_REQUEST)),
            "launch": lambda: host.launch_codex_subagents(["One.", "Two."], request=CodexSpawnRequest(approval_policy=CodexApprovalPolicy.UNTRUSTED)),
        }
        for label, start in refused.items():
            with self.subTest(case=label):
                starts = self.count("thread/start")
                error = await self.assert_codex_error(start(), "configuration.unsupported_combination")
                self.assertEqual(self.count("thread/start"), starts + 1)
                created = self.server.matching("thread/start")[-1]
                self.assertNotIn("approvalsReviewer", created.params)
                thread_id = list(self.server.threads)[-1]
                self.assertIn(thread_id, error.message)
                self.assertEqual(_thread_methods(self.server, thread_id), [])
                for method in ("thread/name/set", "turn/start", "thread/goal/clear", "thread/goal/set"):
                    self.assertEqual(self.count(method), 0, method)

    async def test_the_reported_policy_decides_whether_a_user_reviewer_may_start(self) -> None:
        # AC-37, D-32: user with on-request or a granular policy is refused; user with never, or auto_review, starts.
        cases = (
            ("user", "on-request", "configuration.unsupported_combination"),
            ("user", GRANULAR_POLICY, "configuration.unsupported_combination"),
            ("user", "never", None),
            (None, None, None),
        )
        host = await self.open_host()
        for reviewer, policy, code in cases:
            with self.subTest(reviewer=reviewer, policy=policy):
                self.server.force_reviewer, self.server.force_policy = reviewer, policy
                turn_starts = self.count("turn/start")
                if code is None:
                    handle = await self.spawn(host)
                    self.assertEqual(self.count("turn/start"), turn_starts + 1)
                    self.assertEqual(self.server.matching("thread/start")[-1].params["approvalsReviewer"], "auto_review")
                    self.assertEqual(handle.thread_id, list(self.server.threads)[-1])
                else:
                    await self.assert_codex_error(self.spawn(host), code)
                    self.assertEqual(self.count("turn/start"), turn_starts)
        self.server.force_reviewer, self.server.force_policy = None, None

    async def test_continue_checks_the_reviewer_resume_reports_and_an_override_fixes_it(self) -> None:
        # AC-37, EC-76, A-16: resume keeps the thread's reviewer unless the caller sets one.
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest
        from vidbyte.lib.enums.codex import CodexApprovalsReviewer

        host = await self.open_host()
        human = self.server.seed_thread(completed_turns=1, reviewer="user", policy="on-request")
        error = await self.assert_codex_error(host.continue_codex_thread(human.thread_id, "Carry on."), "configuration.unsupported_combination")
        self.assertIn(human.thread_id, error.message)
        self.assertEqual(_thread_methods(self.server, human.thread_id), ["thread/read", "thread/resume"])

        overrides = CodexSpawnRequest(approvals_reviewer=CodexApprovalsReviewer.AUTO_REVIEW)
        handle = await asyncio.wait_for(host.continue_codex_thread(human.thread_id, "Carry on.", overrides=overrides), WAIT_SECONDS)
        resume = self.server.matching("thread/resume")[-1].params
        self.assertEqual(resume["approvalsReviewer"], "auto_review")
        self.assertNotIn("approvalPolicy", resume)
        self.assertEqual(handle.turn_id, human.turns[-1].turn_id)


@requires_sdk
class CodexHostThreadConfigTests(HostTestCase):
    """INV-29, D-29 and INV-30: dynamic tools on thread/start and on a fork, and the agents config."""

    async def test_dynamic_tools_need_the_experimental_api_and_valid_names_before_any_request(self) -> None:
        # INV-29, EC-49, D-18: both checks run before anything is sent.
        from vidbyte.lib.dataclasses.codex import CodexClientSettings
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        host = await self.open_host(CodexClientSettings(experimental_api=False))
        sent = len(self.server.requests)
        with self.assertRaises(ConfigurationError) as caught:
            await asyncio.wait_for(host.spawn_codex_thread(CodexSpawnRequest(prompt="Echo.", tools=(make_echo_tool(),))), WAIT_SECONDS)
        self.assertIn(EXPERIMENTAL_API_TEXT, str(caught.exception))
        self.assertEqual(len(self.server.requests), sent)
        await self.close_host(host)

        host = await self.open_host()
        sent = len(self.server.requests)
        for name, fragment in (("bad name!", "must be 1-128 characters of letters, digits, '_' or '-'."), ("mcp__lookup", "is reserved for MCP tools.")):
            with self.subTest(name=name):
                with self.assertRaises(ConfigurationError) as caught:
                    await asyncio.wait_for(host.spawn_codex_thread(CodexSpawnRequest(prompt="Echo.", tools=(make_echo_tool(name),))), WAIT_SECONDS)
                self.assertIn(f"Codex tool name {name!r} {fragment}", str(caught.exception))
        self.assertEqual(len(self.server.requests), sent)

    async def test_dynamic_tools_are_registered_on_thread_start_and_answer_codex(self) -> None:
        # INV-29: the call runs through the real ToolExecutor on the host's loop and its output reaches Codex.
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        echo = make_echo_tool()
        host = await self.open_host()
        handle = await asyncio.wait_for(host.spawn_codex_thread(CodexSpawnRequest(prompt="Echo hi.", tools=(echo,))), WAIT_SECONDS)
        declared = self.server.matching("thread/start")[0].params["dynamicTools"]
        self.assertEqual([(tool["type"], tool["name"]) for tool in declared], [("function", "echo_text")])
        call = {"threadId": handle.thread_id, "turnId": handle.turn_id, "callId": "call-1", "tool": "echo_text", "arguments": {"text": "hi"}}
        answer = await self.ask("item/tool/call", call)
        self.assertEqual(answer, {"success": True, "contentItems": [{"type": "inputText", "text": "echo: hi"}]})
        self.assertEqual([recorded.arguments for recorded in echo.calls], [{"text": "hi"}])

    async def test_a_fork_answers_tool_calls_with_its_parent_threads_tools(self) -> None:
        # D-29: Codex gives the fork its parent's dynamic tools, so the host registers the parent's handler for the new thread.
        from vidbyte.lib.dataclasses.codex_host import CodexSpawnRequest

        echo = make_echo_tool()
        host = await self.open_host()
        parent = await asyncio.wait_for(host.spawn_codex_thread(CodexSpawnRequest(prompt="Echo hi.", tools=(echo,))), WAIT_SECONDS)
        self.server.complete_turn(parent.thread_id, parent.turn_id, final="Done.")
        await self.wait_done(host, parent)
        fork = await asyncio.wait_for(host.fork_codex_thread(parent.thread_id), WAIT_SECONDS)
        turn = await asyncio.wait_for(host.continue_codex_thread(fork.thread_id, "Echo again."), WAIT_SECONDS)

        call = {"threadId": fork.thread_id, "turnId": turn.turn_id, "callId": "call-fork", "tool": "echo_text", "arguments": {"text": "from the fork"}}
        answer = await self.ask("item/tool/call", call)
        self.assertEqual(answer, {"success": True, "contentItems": [{"type": "inputText", "text": "echo: from the fork"}]})
        self.assertEqual([recorded.arguments for recorded in echo.calls], [{"text": "from the fork"}])

    async def test_the_agents_config_is_written_only_when_subagents_are_set(self) -> None:
        # INV-30, D-17: an empty config is omitted, the caller's own config is kept as given.
        from vidbyte.agents.codex.config import CodexContentTranslator
        from vidbyte.lib.dataclasses.codex import CodexSubagentSettings, CodexThreadSettings

        host = await self.open_host()
        await self.spawn(host)
        self.assertNotIn("config", self.server.matching("thread/start")[-1].params)
        own = {"agents": {"max_threads": 3}, "model_verbosity": "low"}
        await self.spawn(host, thread=CodexThreadSettings(config=own))
        self.assertEqual(self.server.matching("thread/start")[-1].params["config"], own)
        subagents = CodexSubagentSettings(max_concurrent_threads=2, default_model="gpt-5.5")
        await self.spawn(host, subagents=subagents)
        self.assertEqual(self.server.matching("thread/start")[-1].params["config"], {"agents": CodexContentTranslator._subagent_config(subagents)})


if __name__ == "__main__":
    unittest.main()
