"""FILE: tests/features/claude_host/test_claude_host_admission.py

PURPOSE: Proves what the host admits before any process starts: continue resumes a known, idle session in its own cwd; launch registers all N handles or none and connects at most `limit` at once; the live cap, busy session ids and rejected rate-limit windows refuse spawns; empty and mistyped arguments are refused; the CLI path comes from the request or the host and is never empty or a batch script; and session ids follow the natural-key rules.
ROLE IN CODEBASE: Admission layer of tests/features/claude_host/ (spec AC-7, AC-11, AC-16, AC-30, INV-4, INV-5, INV-6, INV-10, D-8, D-22, D-27, EC-7, EC-11, EC-12, EC-32 to EC-34, EC-49, EC-50, EC-52, section 9.1 "Natural keys"). Exercises ClaudeHost admission in vidbyte/harnesses/native/claude/host.py.
ARCHITECTURE NOTE: Every refusal is checked twice: by the failure code and next step of the raised ClaudeOperationError, and by the fake SDK recording no new client, because a refused call must start nothing. Rate-limit windows reach the host only through a turn's stream, so those tests run one scripted turn first.
COMMON MODIFICATION PATTERNS: A new host precondition gets a refusal test that also counts fake clients, plus an ordering case against its neighbours in spawn's precondition order (input.empty, not_installed, session_busy for the cap then the id, usage_limited).
WHAT NOT TO DO IN THIS FILE: 1. Do not assert the status of a turn whose stream carried a rejected window with a success result; that combination is not fixed by the spec. 2. Do not compare paths as raw strings; use pathlib. 3. Do not import feature symbols at module level.
KNOWN EDGE CASES: A continue reads the session's info before its busy check, so a busy-session test registers the session in the fake history first. A host whose CLI lookup found nothing is built by patching ClaudeProbe.locate_cli during entry only, so a request's own path is still screened for real.
RELATED DOCS: tests/features/claude_host/FEATURE.md; docs/spec/claude-host/spec.md sections 6.1, 6.3, 9.1 and 9.2 (spawn, continue and launch rows).
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/features/claude_host/test_claude_host_admission.py
"""

from __future__ import annotations

import asyncio
import sys
import unittest
import uuid
from pathlib import Path
from typing import Any
from unittest import mock

from tests.features.claude_host.claude_host_fixtures import (
    CLAUDE_NEXT_STEPS,
    DEFAULT_PROMPT,
    EMPTY_INPUT_NEXT_STEP,
    FAR_FUTURE_RESET,
    FAR_PAST_RESET,
    FAKE_CLI_PATH,
    HANG_GUARD_SECONDS,
    INPUT_EMPTY,
    INVALID_ARGUMENT,
    INVALID_ARGUMENT_NEXT_STEP,
    LIVE_CAP_NEXT_STEP,
    OTHER_CLI_PATH,
    OTHER_DIR,
    UNSUPPORTED_COMBINATION,
    UNSUPPORTED_COMBINATION_NEXT_STEP,
    WORK_DIR,
    ClaudeHostCase,
    eventually,
    init_message,
    prompt_text,
    rate_limit_event,
    result_message,
    settle,
)

LAUNCH_PROMPTS = ("Review src/ for bugs.", "Review tests/ for gaps.", "Review docs/ for stale pages.")


def template(**fields: Any) -> Any:
    """Build a launch template request in WORK_DIR."""
    from vidbyte.lib.dataclasses.claude import ClaudeSpawnRequest

    fields.setdefault("cwd", WORK_DIR)
    return ClaudeSpawnRequest(**fields)


class AdmissionCase(ClaudeHostCase):
    """Adds helpers for a held live turn and for counting what a refusal started."""

    async def live_turn(self, host: Any, prompt: str = DEFAULT_PROMPT, **fields: Any) -> Any:
        """Spawn a held turn and return its handle once its client exists."""
        self.fake.hold(prompt)
        handle = await self.spawn(host, prompt, **fields)
        await self.client_for(handle)
        return handle

    async def launch(self, host: Any, prompts: tuple[str, ...], request: Any, limit: int) -> tuple[Any, ...]:
        return await asyncio.wait_for(host.launch_claude_subagents(prompts, request, limit), HANG_GUARD_SECONDS)

    def connect_attempts(self) -> int:
        """Count the fake clients that have called connect(); a client may be constructed before its launch slot frees."""
        return sum("connect" in client.calls for client in self.fake.clients)


class ContinueTests(AdmissionCase):
    """AC-7, D-27 and EC-32: continue resumes a known, idle session as a new turn in the session's own cwd."""

    async def test_continue_on_a_live_session_is_busy_and_starts_nothing(self) -> None:
        host = await self.open_host()
        live = await self.live_turn(host)
        self.fake.history.add_session(live.session_id, cwd=WORK_DIR)
        clients_before = len(self.fake.clients)
        error = await self.raises(host.continue_claude_session(live.session_id, "next"), "claude.session_busy")
        self.assertEqual(error.next_step, CLAUDE_NEXT_STEPS["claude.session_busy"])
        await settle()
        self.assertEqual(len(self.fake.clients), clients_before)

    async def test_continue_on_an_unknown_session_is_not_found(self) -> None:
        host = await self.open_host()
        unknown = str(uuid.uuid4())
        error = await self.raises(host.continue_claude_session(unknown, "next"), "claude.session_not_found")
        self.assertEqual(error.next_step, CLAUDE_NEXT_STEPS["claude.session_not_found"])
        self.assertEqual([call.arguments["session_id"] for call in self.fake.history.calls_to("get_session_info")], [unknown])
        self.assertEqual(self.fake.clients, [])

    async def test_continue_from_another_cwd_is_an_unsupported_combination(self) -> None:
        host = await self.open_host()
        session = self.fake.history.add_session(cwd=WORK_DIR)
        error = await self.raises(host.continue_claude_session(session, "next", request=template(cwd=OTHER_DIR)), UNSUPPORTED_COMBINATION)
        self.assertEqual(error.next_step, UNSUPPORTED_COMBINATION_NEXT_STEP)
        self.assertIn("cwd", error.reason)
        self.assertEqual(self.fake.clients, [])

    async def test_a_valid_continue_resumes_the_session_in_its_recorded_cwd(self) -> None:
        host = await self.open_host()
        session = self.fake.history.add_session(cwd=WORK_DIR)
        handle = await asyncio.wait_for(host.continue_claude_session(session, "Now fix the parser."), HANG_GUARD_SECONDS)
        # A plain resume keeps the session's own id.
        self.assertEqual(handle.session_id, session)
        result = await self.finished(host, handle)
        self.assertEqual(result.status.value, "completed")
        client = await self.client_for(handle)
        self.assertEqual(client.queries, ["Now fix the parser."])
        self.assertEqual(client.options.resume, session)
        self.assertIsNone(client.options.session_id)
        self.assertFalse(client.options.fork_session)
        self.assertFalse(client.options.continue_conversation)
        self.assertEqual(Path(client.options.cwd), Path(WORK_DIR))

    async def test_continue_clears_the_session_fields_of_the_given_request(self) -> None:
        host = await self.open_host()
        session = self.fake.history.add_session(cwd=WORK_DIR)
        request = template(
            prompt="This prompt is replaced.",
            model="sonnet",
            session_id=str(uuid.uuid4()),
            resume=str(uuid.uuid4()),
            fork_session=True,
            resume_session_at=str(uuid.uuid4()),
            resume_drops_turn=str(uuid.uuid4()),
        )
        handle = await asyncio.wait_for(host.continue_claude_session(session, "Carry on.", request=request), HANG_GUARD_SECONDS)
        self.assertEqual(handle.session_id, session)
        await self.finished(host, handle)
        client = await self.client_for(handle)
        self.assertEqual(client.queries, ["Carry on."])
        self.assertEqual(client.options.resume, session)
        self.assertEqual(client.options.model, "sonnet")
        self.assertIsNone(client.options.session_id)
        self.assertFalse(client.options.fork_session)
        self.assertFalse(client.options.continue_conversation)
        self.assertIsNone(client.options.resume_session_at)
        self.assertIsNone(client.options.resume_drops_turn)

    async def test_an_empty_continue_prompt_reads_no_history(self) -> None:
        host = await self.open_host()
        session = self.fake.history.add_session(cwd=WORK_DIR)
        error = await self.raises(host.continue_claude_session(session, ""), INPUT_EMPTY)
        self.assertEqual(error.next_step, EMPTY_INPUT_NEXT_STEP)
        self.assertEqual(self.fake.history.calls, [])
        self.assertEqual(self.fake.clients, [])


class LaunchTests(AdmissionCase):
    """AC-11, INV-6, EC-12 and EC-33: N handles or none, at most `limit` connected, a slot freed only after its close."""

    async def test_launch_runs_every_prompt_with_at_most_limit_connected(self) -> None:
        self.fake.hold(*LAUNCH_PROMPTS)
        self.fake.disconnect_gate = asyncio.Event()
        host = await self.open_host()
        handles = await self.launch(host, LAUNCH_PROMPTS, template(), 2)
        self.assertEqual(len(handles), 3)
        self.assertEqual(len({handle.session_id for handle in handles}), 3)
        self.assertEqual(len({handle.handle_id for handle in handles}), 3)
        for handle in handles:
            self.assertEqual(uuid.UUID(handle.session_id).version, 4)
        await eventually(lambda: len(self.fake.turn_clients()) == 2, "two launched turns are running")
        await settle()
        self.assertEqual(self.connect_attempts(), 2)
        first = self.fake.turn_clients()[0]
        first.finish("Reviewed.")
        await eventually(lambda: first.disconnect_calls == 1, "the first turn's close started")
        await settle()
        # The first client counts as connected until its close completes, so the third prompt has not connected yet.
        self.assertEqual(self.connect_attempts(), 2)
        self.fake.disconnect_gate.set()
        await eventually(lambda: len(self.fake.turn_clients()) == 3, "the third prompt connected")
        for client in self.fake.turn_clients()[1:]:
            client.finish("Reviewed.")
        results = [await self.finished(host, handle) for handle in handles]
        self.assertEqual([result.status.value for result in results], ["completed"] * 3)
        self.assertLessEqual(self.fake.max_connected, 2)
        self.assertEqual(sorted(self.fake.all_queries()), sorted(LAUNCH_PROMPTS))
        for handle in handles:
            client = await self.client_for(handle)
            self.assertEqual(client.options.session_id, handle.session_id)
            self.assertEqual(Path(client.options.cwd), Path(WORK_DIR))
            self.assertEqual(client.disconnect_calls, 1)

    async def test_a_refused_launch_registers_no_handle(self) -> None:
        host = await self.open_host(max_live_sessions=2)
        await self.live_turn(host)
        error = await self.raises(host.launch_claude_subagents(LAUNCH_PROMPTS[:2], template(), 2), "claude.session_busy")
        self.assertEqual(error.next_step, LIVE_CAP_NEXT_STEP)
        await settle()
        self.assertEqual(len(self.fake.clients), 1)
        # Nothing was registered, so the one free slot still admits a launch of one.
        (single,) = await self.launch(host, LAUNCH_PROMPTS[2:], template(), 1)
        self.assertEqual((await self.finished(host, single)).status.value, "completed")

    async def test_a_template_that_names_one_session_is_refused_for_several_prompts(self) -> None:
        from vidbyte.lib.errors import ClaudeOperationError

        host = await self.open_host()
        session = str(uuid.uuid4())
        cases = (
            ("session_id", template(session_id=session), (UNSUPPORTED_COMBINATION,)),
            ("resume without fork", template(resume=session), ("claude.session_busy",)),
            # EC-33 names a code for session_id and for resume only, so either refusal is accepted here.
            ("continue_conversation without fork", template(continue_conversation=True), ("claude.session_busy", UNSUPPORTED_COMBINATION)),
        )
        for label, request, codes in cases:
            with self.subTest(template=label):
                with self.assertRaises(ClaudeOperationError) as caught:
                    await asyncio.wait_for(host.launch_claude_subagents(LAUNCH_PROMPTS[:2], request, 2), HANG_GUARD_SECONDS)
                self.assertIn(caught.exception.failure_code, codes)
        await settle()
        self.assertEqual(self.fake.clients, [])

    async def test_a_plain_resume_launch_of_one_prompt_resumes_that_session(self) -> None:
        host = await self.open_host()
        session = str(uuid.uuid4())
        (handle,) = await self.launch(host, ("Carry on with the review.",), template(resume=session), 1)
        self.assertEqual(handle.session_id, session)
        self.assertEqual((await self.finished(host, handle)).status.value, "completed")
        client = await self.client_for(handle)
        self.assertEqual(client.options.resume, session)
        self.assertIsNone(client.options.session_id)

    async def test_a_fork_template_launches_one_fresh_session_per_prompt(self) -> None:
        host = await self.open_host()
        session = str(uuid.uuid4())
        handles = await self.launch(host, LAUNCH_PROMPTS[:2], template(resume=session, fork_session=True), 2)
        ids = {handle.session_id for handle in handles}
        self.assertEqual(len(ids), 2)
        self.assertNotIn(session, ids)
        for handle in handles:
            self.assertEqual((await self.finished(host, handle)).status.value, "completed")
            client = await self.client_for(handle)
            self.assertEqual((client.options.resume, client.options.fork_session, client.options.session_id), (session, True, handle.session_id))


class LiveCapTests(AdmissionCase):
    """AC-30, INV-5 and D-22: max_live_sessions caps live handles, and the refusal reuses claude.session_busy."""

    async def test_the_cap_refuses_a_second_spawn_and_a_launch_of_one(self) -> None:
        host = await self.open_host(max_live_sessions=1)
        live = await self.live_turn(host)
        for label, call in (
            ("spawn", lambda: self.spawn(host, "Start another task.")),
            ("launch", lambda: host.launch_claude_subagents(("Start another task.",), template(), 1)),
        ):
            with self.subTest(call=label):
                error = await self.raises(call(), "claude.session_busy")
                self.assertEqual(error.next_step, LIVE_CAP_NEXT_STEP)
        await settle()
        self.assertEqual(len(self.fake.clients), 1)
        live_client = await self.client_for(live)
        live_client.finish("Done.")
        await self.finished(host, live)
        follow = await self.spawn(host, "Start another task.")
        self.assertEqual((await self.finished(host, follow)).status.value, "completed")

    async def test_spawn_preconditions_run_in_order(self) -> None:
        host = await self.open_host(max_live_sessions=1)
        live = await self.live_turn(host)
        # input.empty comes before the cap.
        error = await self.raises(self.spawn(host, ""), INPUT_EMPTY)
        self.assertEqual(error.next_step, EMPTY_INPUT_NEXT_STEP)
        # The cap comes before the session-id check.
        error = await self.raises(self.spawn(host, "Reuse that session.", session_id=live.session_id), "claude.session_busy")
        self.assertEqual(error.next_step, LIVE_CAP_NEXT_STEP)
        self.assertEqual(len(self.fake.clients), 1)

    def test_max_live_sessions_must_be_none_or_a_count(self) -> None:
        from vidbyte.harnesses.native.claude import ClaudeHost
        from vidbyte.lib.errors import ClaudeOperationError

        for value in (0, -1, True, 1.5, "2"):
            with self.subTest(max_live_sessions=value):
                with self.assertRaises(ClaudeOperationError) as caught:
                    ClaudeHost(cli_path=FAKE_CLI_PATH, max_live_sessions=value)
                self.assertEqual(caught.exception.failure_code, INVALID_ARGUMENT)
                self.assertIn("max_live_sessions", caught.exception.reason)
        with self.assertRaises(ClaudeOperationError) as caught:
            ClaudeHost(cli_path=5)
        self.assertEqual(caught.exception.failure_code, INVALID_ARGUMENT)
        self.assertIn("cli_path", caught.exception.reason)


class BusySessionTests(AdmissionCase):
    """INV-4 and EC-11: at most one live handle per session id."""

    async def test_a_spawn_that_targets_a_live_session_id_is_busy(self) -> None:
        host = await self.open_host()
        chosen = str(uuid.uuid4())
        live = await self.live_turn(host, "Work in the chosen session.", session_id=chosen)
        self.assertEqual(live.session_id, chosen)
        for label, fields in (("chosen session_id", {"session_id": chosen}), ("plain resume", {"resume": chosen})):
            with self.subTest(target=label):
                error = await self.raises(self.spawn(host, "Second writer.", **fields), "claude.session_busy")
                self.assertEqual(error.next_step, CLAUDE_NEXT_STEPS["claude.session_busy"])
        self.assertEqual(len(self.fake.clients), 1)
        # A fork of the live session is a new session, so it is admitted.
        fork = await self.spawn(host, "Fork it.", resume=chosen, fork_session=True)
        self.assertNotEqual(fork.session_id, chosen)
        self.assertEqual((await self.finished(host, fork)).status.value, "completed")


class RateLimitTests(AdmissionCase):
    """AC-16, D-8, EC-7 and EC-52: windows come from the host's own streams, and only a live rejection refuses spawns."""

    async def run_turn_with(self, host: Any, prompt: str, *events: Any) -> None:
        self.fake.reply(prompt, init_message(), *events, result_message(result="Done."))
        await self.finished(host, await self.spawn(host, prompt))

    async def test_the_latest_window_per_type_is_kept_in_declaration_order(self) -> None:
        from vidbyte.lib.dataclasses.claude_host import ClaudeRateLimitWindow
        from vidbyte.lib.enums.claude import ClaudeRateLimitStatus, ClaudeRateLimitType

        host = await self.open_host()
        self.assertEqual(await host.get_claude_rate_limits(), ())
        await self.run_turn_with(
            host,
            DEFAULT_PROMPT,
            rate_limit_event("seven_day", "allowed", resets_at=FAR_FUTURE_RESET, utilization=0.2),
            rate_limit_event("five_hour", "allowed_warning", resets_at=FAR_FUTURE_RESET, utilization=0.85, overage_status="allowed", overage_resets_at=FAR_FUTURE_RESET),
            rate_limit_event("seven_day", "allowed", resets_at=FAR_FUTURE_RESET, utilization=0.3),
            rate_limit_event(None, "rejected", resets_at=FAR_FUTURE_RESET),
            rate_limit_event("weekly_mystery", "rejected", resets_at=FAR_FUTURE_RESET),
            rate_limit_event("seven_day_overage_included", "allowed", utilization=0.1, overage_disabled_reason="org_level_disabled"),
        )
        expected = (
            ClaudeRateLimitWindow(rate_limit_type=ClaudeRateLimitType.FIVE_HOUR, status=ClaudeRateLimitStatus.ALLOWED_WARNING, resets_at=FAR_FUTURE_RESET, utilization=0.85, overage_status=ClaudeRateLimitStatus.ALLOWED, overage_resets_at=FAR_FUTURE_RESET, overage_disabled_reason=""),
            ClaudeRateLimitWindow(rate_limit_type=ClaudeRateLimitType.SEVEN_DAY, status=ClaudeRateLimitStatus.ALLOWED, resets_at=FAR_FUTURE_RESET, utilization=0.3, overage_status=None, overage_resets_at=None, overage_disabled_reason=""),
            ClaudeRateLimitWindow(rate_limit_type=ClaudeRateLimitType.SEVEN_DAY_OVERAGE_INCLUDED, status=ClaudeRateLimitStatus.ALLOWED, resets_at=None, utilization=0.1, overage_status=None, overage_resets_at=None, overage_disabled_reason="org_level_disabled"),
        )
        self.assertEqual(await host.get_claude_rate_limits(), expected)
        # allowed_warning, an untyped rejection and an unknown type never stop spawns.
        follow = await self.spawn(host, "Start the next task.")
        self.assertEqual((await self.finished(host, follow)).status.value, "completed")

    async def test_only_a_live_rejection_without_allowed_overage_refuses_spawns(self) -> None:
        cases = (
            ("rejected, future reset, overage rejected", rate_limit_event("five_hour", "rejected", resets_at=FAR_FUTURE_RESET, overage_status="rejected"), True),
            ("rejected, future reset, no overage status", rate_limit_event("seven_day", "rejected", resets_at=FAR_FUTURE_RESET), True),
            ("rejected, past reset", rate_limit_event("five_hour", "rejected", resets_at=FAR_PAST_RESET, overage_status="rejected"), False),
            ("rejected, overage allowed", rate_limit_event("five_hour", "rejected", resets_at=FAR_FUTURE_RESET, overage_status="allowed"), False),
            ("allowed_warning", rate_limit_event("five_hour", "allowed_warning", resets_at=FAR_FUTURE_RESET, utilization=0.95), False),
            ("rejected without a type", rate_limit_event(None, "rejected", resets_at=FAR_FUTURE_RESET), False),
        )
        for label, event, refused in cases:
            with self.subTest(window=label):
                host = await self.open_host()
                await self.run_turn_with(host, f"Use the quota ({label}).", event)
                clients_before = len(self.fake.clients)
                if refused:
                    error = await self.raises(self.spawn(host, f"Next task ({label})."), "claude.usage_limited")
                    self.assertEqual(error.next_step, CLAUDE_NEXT_STEPS["claude.usage_limited"])
                    self.assertEqual(len(self.fake.clients), clients_before)
                else:
                    follow = await self.spawn(host, f"Next task ({label}).")
                    self.assertEqual((await self.finished(host, follow)).status.value, "completed")


class ArgumentTests(AdmissionCase):
    """EC-49 and EC-50: empty text and mistyped model-written arguments are refused before anything starts."""

    async def test_empty_text_is_refused_before_anything_starts(self) -> None:
        host = await self.open_host()
        live = await self.live_turn(host)
        live_client = await self.client_for(live)
        cases = (
            ("spawn prompt", lambda: host.spawn_claude_session(template())),
            ("continue prompt", lambda: host.continue_claude_session(live.session_id, "")),
            ("steer message", lambda: host.steer_claude_session(live, "")),
            ("empty prompts", lambda: host.launch_claude_subagents((), template(), 1)),
            ("empty launch item", lambda: host.launch_claude_subagents(("Review src/.", ""), template(), 2)),
        )
        for label, call in cases:
            with self.subTest(argument=label):
                error = await self.raises(call(), INPUT_EMPTY)
                self.assertEqual(error.next_step, EMPTY_INPUT_NEXT_STEP)
        await settle()
        self.assertEqual(len(self.fake.clients), 1)
        self.assertEqual(live_client.interrupt_calls, 0)
        self.assertEqual(self.fake.history.calls, [])

    async def test_mistyped_arguments_are_invalid(self) -> None:
        host = await self.open_host()
        handle = await self.spawn(host)
        await self.finished(host, handle)
        session = str(uuid.uuid4())
        cases: list[tuple[str, str, Any]] = []
        for limit in (0, -1, True, 1.5, "2", None):
            cases.append((f"launch limit={limit!r}", "limit", lambda limit=limit: host.launch_claude_subagents(("Review src/.",), template(), limit)))
        for timeout in (0, -1.0, float("nan"), float("inf"), True, "5"):
            cases.append((f"wait timeout_seconds={timeout!r}", "timeout_seconds", lambda timeout=timeout: host.wait_claude_turn(handle, timeout_seconds=timeout)))
        cases.extend(
            [
                ("list limit as text", "limit", lambda: host.list_claude_sessions(limit="2")),
                ("list limit as a flag", "limit", lambda: host.list_claude_sessions(limit=True)),
                ("list offset as text", "offset", lambda: host.list_claude_sessions(offset="1")),
                ("list include_worktrees as text", "include_worktrees", lambda: host.list_claude_sessions(include_worktrees="yes")),
                ("list directory as a number", "directory", lambda: host.list_claude_sessions(directory=5)),
                ("messages limit as text", "limit", lambda: host.get_claude_session_messages(session, limit="2")),
                ("info id as a number", "session_id", lambda: host.get_claude_session_info(5)),
                ("fork id as a number", "session_id", lambda: host.fork_claude_session(5)),
                ("continue id as a number", "session_id", lambda: host.continue_claude_session(5, "next")),
            ]
        )
        for label, argument, call in cases:
            with self.subTest(argument=label):
                error = await self.raises(call(), INVALID_ARGUMENT)
                self.assertEqual(error.next_step, INVALID_ARGUMENT_NEXT_STEP)
                self.assertIn(argument, error.reason)
        await settle()
        self.assertEqual(len(self.fake.clients), 1)
        self.assertEqual(self.fake.history.calls, [])


class CliPathTests(AdmissionCase):
    """INV-10, D-5 and EC-57: every client gets an explicit, screened CLI path, and an empty one starts nothing."""

    async def test_a_request_cli_path_overrides_the_hosts_path(self) -> None:
        host = await self.open_host()
        handle = await self.spawn(host, cli_path=OTHER_CLI_PATH)
        await self.finished(host, handle)
        client = await self.client_for(handle)
        self.assertEqual(Path(client.options.cli_path), Path(OTHER_CLI_PATH))

    async def test_a_request_batch_script_is_never_passed_on_windows(self) -> None:
        shim = "C:/Users/developer/AppData/Roaming/npm/claude.cmd"
        host = await self.open_host()
        if sys.platform == "win32":
            # The request path screens to "", and the host's path is never a fallback for it.
            error = await self.raises(self.spawn(host, cli_path=shim), "claude.not_installed")
            self.assertEqual(error.next_step, CLAUDE_NEXT_STEPS["claude.not_installed"])
            self.assertEqual(self.fake.clients, [])
        else:
            handle = await self.spawn(host, cli_path=shim)
            await self.finished(host, handle)
            client = await self.client_for(handle)
            self.assertEqual(client.options.cli_path, shim)

    async def test_a_host_that_found_no_cli_refuses_spawns_unless_the_request_names_one(self) -> None:
        from vidbyte.harnesses.native.claude.probe import ClaudeProbe

        with mock.patch.object(ClaudeProbe, "locate_cli", return_value=""):
            host = await self.open_host(cli_path="")
        error = await self.raises(self.spawn(host), "claude.not_installed")
        self.assertEqual(error.next_step, CLAUDE_NEXT_STEPS["claude.not_installed"])
        self.assertEqual(self.fake.clients, [])
        live = await self.live_turn(host, "Use the given CLI.", cli_path=OTHER_CLI_PATH)
        client = await self.client_for(live)
        self.assertEqual(Path(client.options.cli_path), Path(OTHER_CLI_PATH))
        # not_installed is checked before the busy guard.
        await self.raises(self.spawn(host, "Reuse that session.", session_id=live.session_id), "claude.not_installed")
        self.assertEqual(len(self.fake.clients), 1)


class NaturalKeyTests(AdmissionCase):
    """Section 9.1 "Natural keys" and EC-34: which session id each kind of spawn gets, and what the client is told."""

    async def test_session_ids_follow_the_natural_key_rules(self) -> None:
        host = await self.open_host()
        chosen = str(uuid.uuid4())
        resumed = str(uuid.uuid4())
        new = await self.spawn(host, "Start a new session.")
        picked = await self.spawn(host, "Use the chosen id.", session_id=chosen)
        resume = await self.spawn(host, "Resume that session.", resume=resumed)
        fork = await self.spawn(host, "Fork that session.", resume=resumed, fork_session=True)
        handles = (new, picked, resume, fork)
        for handle in handles:
            self.assertEqual(uuid.UUID(handle.handle_id).version, 4)
            self.assertEqual((await self.finished(host, handle)).status.value, "completed")
        self.assertEqual(len({handle.handle_id for handle in handles}), 4)
        self.assertEqual(uuid.UUID(new.session_id).version, 4)
        self.assertEqual(picked.session_id, chosen)
        self.assertEqual(resume.session_id, resumed)
        self.assertEqual(uuid.UUID(fork.session_id).version, 4)
        self.assertNotIn(fork.session_id, (resumed, new.session_id))
        expected = {
            new.session_id: (new.session_id, None, False),
            chosen: (chosen, None, False),
            resumed: (None, resumed, False),
            fork.session_id: (fork.session_id, resumed, True),
        }
        for session_id, (option_id, option_resume, option_fork) in expected.items():
            with self.subTest(session_id=session_id):
                client = self.fake.client_for_session(session_id)
                self.assertIsNotNone(client)
                self.assertEqual((client.options.session_id, client.options.resume, client.options.fork_session), (option_id, option_resume, option_fork))

    async def test_continue_conversation_without_fork_has_no_session_id_until_the_result(self) -> None:
        first_prompt, second_prompt = "Continue the last session.", "Continue it once more."
        self.fake.hold(first_prompt, second_prompt)
        host = await self.open_host()
        first = await self.spawn(host, first_prompt, continue_conversation=True)
        # No busy guard applies to an unknown id, so a second one is admitted too.
        second = await self.spawn(host, second_prompt, continue_conversation=True)
        self.assertEqual((first.session_id, second.session_id), ("", ""))
        await eventually(lambda: len(self.fake.turn_clients()) == 2, "both turns were sent")
        clients = {prompt_text(client.queries[0]): client for client in self.fake.turn_clients()}
        for client in clients.values():
            self.assertTrue(client.options.continue_conversation)
            self.assertIsNone(client.options.session_id)
        clients[first_prompt].finish("Continued.")
        result = await self.finished(host, first)
        self.assertEqual(result.session_id, clients[first_prompt].session)
        self.assertNotEqual(result.session_id, "")
        clients[second_prompt].finish("Continued again.")
        self.assertEqual((await self.finished(host, second)).status.value, "completed")

    async def test_continue_conversation_with_fork_gets_a_fresh_session_id(self) -> None:
        host = await self.open_host()
        handle = await self.spawn(host, "Fork the last session.", continue_conversation=True, fork_session=True)
        self.assertEqual(uuid.UUID(handle.session_id).version, 4)
        await self.finished(host, handle)
        client = await self.client_for(handle)
        self.assertEqual((client.options.session_id, client.options.continue_conversation, client.options.fork_session), (handle.session_id, True, True))


if __name__ == "__main__":
    unittest.main()
