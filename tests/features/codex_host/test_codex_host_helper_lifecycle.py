"""FILE: tests/features/codex_host/test_codex_host_helper_lifecycle.py

PURPOSE: Proves the twelve thread-helper methods against the host lifecycle and the cross-cutting rules: the thread-helpers section 4 snippet's printed lines, the call guards of every new method (not open, closed, another event loop), no spend preflight from the nine helpers and no thread load from the READ ones, -32601 from each of the five new app-server methods as codex.protocol_mismatch with the function's own operation, and no skill path, skill description or goal objective in any new error text.
ROLE IN CODEBASE: Lifecycle and contract layer of the thread-helpers additions to tests/features/codex_host/ (docs/spec/codex-host-thread-helpers/spec.md AC-1, AC-34, AC-37, INV-3 to INV-5, INV-10, INV-29, INV-33, EC-35). Every class needs the optional openai-codex extra, so CI skips them.
ARCHITECTURE NOTE: The snippet runs verbatim against the fake app-server with paged listings, a listed openai-docs skill, recorded turn input and turns that finish as soon as they start, so every printed line comes from the real host code path. The guard tests reach each method through one table keyed by HELPER_METHODS, so a method missing from the table fails the key check rather than going untested.
COMMON MODIFICATION PATTERNS: When a new host method is added, add its call to _helper_calls and its name to HELPER_METHODS in codex_host_support.py; when Codex gains a method a helper sends, add its row to the -32601 table.
KNOWN EDGE CASES: The goal run in the snippet is still active when the block exits, so the host's close interrupts it (codex-host INV-7); the test waits on close with CLOSE_SECONDS. A privacy canary must be a valid absolute path segment when it stands in a skill path.
RELATED DOCS: tests/features/codex_host/FEATURE.md; docs/spec/codex-host-thread-helpers/spec.md sections 4, 6.1 (INV-3 to INV-5, INV-10, INV-29, INV-33) and 9.2.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host/test_codex_host_helper_lifecycle.py
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import unittest
from collections.abc import Awaitable, Callable
from typing import Any

from tests.features.codex_host.codex_host_support import (
    CLOSE_SECONDS,
    ENV_SECRET,
    HELPER_METHODS,
    LINE_SECRET,
    STDERR_SECRET,
    WAIT_SECONDS,
    HostTestCase,
    assert_no_canary,
    error_texts,
    requires_sdk,
)
from vidbyte.lib.errors import ConfigurationError

PREFLIGHT_METHODS = frozenset({"account/read", "account/rateLimits/read", "windowsSandbox/readiness", "model/list"})
DOCS_PATH = os.path.abspath(os.path.join(os.sep, "codex-home", "skills", ".system", "openai-docs", "SKILL.md"))
DOCS_ANSWER = "Use the response.output_text.delta event."


def _helper_calls(host: Any, thread_id: str) -> dict[str, Callable[[], Awaitable[Any]]]:
    """One call of each new host method, in section 8.5 order."""
    return {
        "list_recent_codex_threads": lambda: host.list_recent_codex_threads(""),
        "list_codex_threads_since": lambda: host.list_codex_threads_since("", 0),
        "search_codex_threads": lambda: host.search_codex_threads("", "fix"),
        "get_codex_thread_lineage": lambda: host.get_codex_thread_lineage(thread_id),
        "list_codex_turns": lambda: host.list_codex_turns(thread_id),
        "compact_codex_thread": lambda: host.compact_codex_thread(thread_id),
        "delete_codex_thread": lambda: host.delete_codex_thread(thread_id),
        "get_codex_goal": lambda: host.get_codex_goal(thread_id),
        "run_codex_goal": lambda: host.run_codex_goal("Ship the fix."),
        "list_codex_skills": lambda: host.list_codex_skills(),
        "run_codex_skill": lambda: host.run_codex_skill("openai-docs", "Find the event that streams text."),
        "run_codex_openai_docs": lambda: host.run_codex_openai_docs("Which event streams text deltas?"),
    }


@requires_sdk
class CodexHelperSnippetTests(HostTestCase):
    """AC-1: the developer-usage snippet of the thread-helpers spec section 4 prints its documented lines."""

    async def test_the_section_4_snippet_prints_its_seven_lines(self) -> None:
        from vidbyte.harnesses.native.codex import CodexHost
        from vidbyte.tools.toolsets import CodexHostTools

        base = self.fakes.BASE_TIME
        self.server.paged_thread_list = True
        self.server.new_thread(updated_at=base + 10)
        newest = self.server.new_thread(updated_at=base + 40, name="Release notes")
        second = self.server.new_thread(updated_at=base + 30)
        third = self.server.new_thread(updated_at=base + 20)
        self.server.skills[self.fakes.DEFAULT_CWD] = [self.fakes.skill_entry("openai-docs", DOCS_PATH, scope="system")]
        self.server.record_turn_input = True
        # Codex finishes a started turn at once, with a final answer and usage.
        self.server.autocomplete = {"final": DOCS_ANSWER, "usage": self.fakes.token_usage((120, 30), (120, 30))}
        docs_threads: list[str] = []

        async def main() -> None:
            # Spec section 4, verbatim apart from asyncio.run, which the test loop replaces, and the docs thread id kept for the check.
            async with CodexHost() as host:
                for summary in await host.list_recent_codex_threads("", limit=3):  # "" = every folder
                    print(summary.harness, summary.thread_id, summary.title, summary.updated_at)
                goal_run = await host.run_codex_goal("Make the failing tests pass.", token_budget=200_000)
                goal = await host.get_codex_goal(goal_run.thread_id)  # None when a thread has no goal
                print(goal.status.value, goal.token_budget)
                docs = await host.run_codex_openai_docs("Which Responses API event streams text deltas?")
                docs_threads.append(docs.thread_id)
                outcome = await host.wait_codex_turn(docs, timeout_seconds=600.0)
                print(outcome.status.value, outcome.result.final_response)
                page = await host.list_codex_turns(docs.thread_id)  # oldest turn first, every item
                print(len(page.turns), page.turns[0].status.value, len(page.turns[0].items))
                await host.delete_codex_thread(docs.thread_id)  # a plain function, never a tool
                tools = CodexHostTools(host, max_live_turns=2)
                print(len(tools), "delete_codex_thread" in tools.names())

        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            await asyncio.wait_for(main(), CLOSE_SECONDS)
        self.assertEqual(
            printed.getvalue().splitlines(),
            [
                f"codex {newest.thread_id} Release notes {base + 40}",
                f"codex {second.thread_id} None {base + 30}",
                f"codex {third.thread_id} None {base + 20}",
                "active 200000",
                f"completed {DOCS_ANSWER}",
                "1 completed 2",
                "26 False",
            ],
        )
        self.assertNotIn(docs_threads[0], self.server.threads)


@requires_sdk
class CodexHelperGuardTests(HostTestCase):
    """AC-34 and INV-4: every new method runs the host guard before anything else."""

    async def test_every_new_method_refuses_before_open_after_close_and_from_another_loop(self) -> None:
        from vidbyte.harnesses.native.codex import CodexHost

        idle = CodexHost()
        calls = _helper_calls(idle, "thr-1")
        self.assertEqual(tuple(calls), HELPER_METHODS)
        for name, start in calls.items():
            with self.subTest(not_open=name):
                with self.assertRaises(ConfigurationError):
                    await asyncio.wait_for(start(), WAIT_SECONDS)
        self.assertEqual(self.server.clients_created, 0)

        host = await self.open_host()
        seeded = self.server.seed_thread(completed_turns=1)
        sent = len(self.server.requests)
        for name, start in _helper_calls(host, seeded.thread_id).items():
            with self.subTest(other_loop=name):
                self.assertIsInstance(await self.run_in_other_loop(start), ConfigurationError)
        self.assertEqual(len(self.server.requests), sent)

        await self.close_host(host)
        sent = len(self.server.requests)
        for name, start in _helper_calls(host, seeded.thread_id).items():
            with self.subTest(closed=name):
                error = await self.assert_codex_error(start(), "codex.process_exited")
                self.assertEqual(error.operation, name)
        self.assertEqual(len(self.server.requests), sent)
        self.assertEqual(self.server.kinds("write_after_close"), [])


@requires_sdk
class CodexHelperNoPreflightTests(HostTestCase):
    """INV-10 and INV-33: the nine helpers send no check request, and the READ ones never load a thread."""

    async def test_helpers_send_no_check_and_reads_leave_a_not_loaded_thread_unloaded(self) -> None:
        from vidbyte.lib.enums.codex import CodexThreadStatus

        self.server.paged_thread_list = True
        stored = self.server.seed_thread(completed_turns=2)
        stored.status = "notLoaded"
        stored.goal = self.fakes.goal_record(stored.thread_id, "Ship the fix.", "paused")
        to_compact = self.server.seed_thread(completed_turns=1)
        to_delete = self.server.seed_thread(completed_turns=1)
        self.server.skills[self.fakes.DEFAULT_CWD] = [self.fakes.skill_entry("openai-docs", DOCS_PATH, scope="system")]
        host = await self.open_host()
        mark = len(self.server.requests)

        reads = (
            lambda: host.list_recent_codex_threads("", limit=5),
            lambda: host.list_codex_threads_since("", 0, limit=5),
            lambda: host.search_codex_threads("", "preview", limit=5),
            lambda: host.get_codex_thread_lineage(stored.thread_id),
            lambda: host.list_codex_turns(stored.thread_id),
            lambda: host.get_codex_goal(stored.thread_id),
            lambda: host.list_codex_skills(),
        )
        for read in reads:
            await asyncio.wait_for(read(), WAIT_SECONDS)
        read_methods = [request.method for request in list(self.server.requests)[mark:]]
        self.assertFalse({"thread/resume", "turn/start"} & set(read_methods), read_methods)
        self.assertEqual(stored.status, "notLoaded")
        info = await asyncio.wait_for(host.read_codex_thread(stored.thread_id), WAIT_SECONDS)
        self.assertEqual(info.status, CodexThreadStatus.NOT_LOADED)

        await asyncio.wait_for(host.compact_codex_thread(to_compact.thread_id), WAIT_SECONDS)
        await asyncio.wait_for(host.delete_codex_thread(to_delete.thread_id), WAIT_SECONDS)
        methods = [request.method for request in list(self.server.requests)[mark:]]
        self.assertFalse(PREFLIGHT_METHODS & set(methods), methods)


@requires_sdk
class CodexHelperProtocolTests(HostTestCase):
    """AC-37, EC-35 and INV-3: a runtime without one of the five new methods is a protocol mismatch, named by its function."""

    async def test_a_missing_method_is_protocol_mismatch_with_the_functions_own_operation(self) -> None:
        idle = self.server.seed_thread(completed_turns=1)
        host = await self.open_host()
        rows = (
            ("thread/compact/start", "compact_codex_thread", lambda: host.compact_codex_thread(idle.thread_id)),
            ("thread/delete", "delete_codex_thread", lambda: host.delete_codex_thread(idle.thread_id)),
            ("thread/goal/get", "get_codex_goal", lambda: host.get_codex_goal(idle.thread_id)),
            ("skills/list", "list_codex_skills", lambda: host.list_codex_skills()),
            ("thread/turns/list", "list_codex_turns", lambda: host.list_codex_turns(idle.thread_id)),
        )
        for method, operation, start in rows:
            with self.subTest(method=method):
                self.server.fail(method, self.fakes.FakeRpcError(-32601, f"method not found: {method}"), times=1)
                error = await self.assert_codex_error(start(), "codex.protocol_mismatch")
                self.assertEqual(error.operation, operation)

        # A skill run's listing failure keeps the listing's operation, and no thread starts.
        for name, start in (("run_codex_skill", lambda: host.run_codex_skill("openai-docs", "Find it.")), ("run_codex_openai_docs", lambda: host.run_codex_openai_docs("Which event?"))):
            with self.subTest(run=name):
                self.server.fail("skills/list", self.fakes.FakeRpcError(-32601, "method not found: skills/list"), times=1)
                error = await self.assert_codex_error(start(), "codex.protocol_mismatch")
                self.assertEqual(error.operation, "list_codex_skills")
        self.assertEqual(self.count("thread/start"), 0)


@requires_sdk
class CodexHelperPrivacyTests(HostTestCase):
    """INV-29: a new error message carries thread ids, skill names, the caller's cwd and counts, never what the host read."""

    async def test_skill_paths_descriptions_and_goal_objectives_stay_out_of_error_texts(self) -> None:
        secret_path = os.path.abspath(os.path.join(os.sep, STDERR_SECRET, "SKILL.md"))
        self.server.skills[self.fakes.DEFAULT_CWD] = [
            self.fakes.skill_entry("s", secret_path, description=f"Uses {ENV_SECRET}."),
            self.fakes.skill_entry("off", secret_path, enabled=False, description=f"Uses {ENV_SECRET}."),
        ]
        self.server.record_turn_input = True
        self.server.drop_skill_input = True
        host = await self.open_host()
        canaries = (ENV_SECRET, STDERR_SECRET, LINE_SECRET)
        errors = [
            await self.assert_codex_error(host.run_codex_skill("zz", "x"), "codex.skill_not_found"),
            await self.assert_codex_error(host.run_codex_skill("off", "x"), "codex.skill_disabled"),
            await self.assert_codex_error(host.run_codex_skill("s", "x"), "codex.command_not_run"),
        ]
        self.server.goal_get_answer = lambda thread: {**thread.goal, "objective": f"Stored {LINE_SECRET}"}
        errors.append(await self.assert_codex_error(host.run_codex_goal(f"Sent {LINE_SECRET}"), "codex.command_not_run"))
        for error in errors:
            with self.subTest(code=error.failure_code):
                assert_no_canary(self, error_texts(error), canaries)


if __name__ == "__main__":
    unittest.main()
