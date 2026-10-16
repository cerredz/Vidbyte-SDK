"""FILE: tests/features/harness_threads/test_harness_threads_acceptance_helpers.py

PURPOSE: The developer-facing outcome of the helpers spec: its §4 snippet runs verbatim in a fresh interpreter whose current folder is the workspace, against grok and opencode stand-ins found first on PATH, and prints the goal's id and text, one merged newest-first line per thread, and the goal's lineage (AC-1); and threads made by #1036's run and fork functions are the ones the helpers list, read and link, per harness (INV-13, AC-6, EC-76).
ROLE IN CODEBASE: Start here when the documented snippet breaks, or when the helpers stop seeing the threads the run functions make.
ARCHITECTURE NOTE: AC-1 copies the snippet unchanged: its key is the literal placeholder "xai-your-key" and its workspace is Path.cwd(), so the subprocess runs with cwd set to the sandbox workspace, PATH set to the sandbox's stand-in folder, and USERPROFILE/HOME set to the sandbox home. The opencode store is seeded before the run; the Grok thread is the one the goal run makes. Expected lines are derived from the stores the stand-ins wrote, not from the SDK.
FUNCTION INVENTORY: summary_time reads a Grok summary.json time as an aware datetime; ms_time converts epoch milliseconds; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: When spec §4 changes, copy the new snippet into SNIPPET verbatim.
WHAT NOT TO DO IN THIS FILE: Do not edit SNIPPET beyond the spec text, and do not put a real key in the environment.
KNOWN EDGE CASES: On win32 the PATH stand-ins are `.exe` launchers built from pip's distlib launcher; the test skips without it. Threads made in the same second can tie on updated_at, so the run-and-fork test compares sets and links, not list order.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-helpers-skills/spec.md §4, §6.1 INV-10, INV-13, §6.2 AC-1, AC-6, §6.3 EC-76
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_acceptance_helpers.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

SNIPPET = '''import asyncio
from datetime import timedelta
from pathlib import Path

from vidbyte.harnesses.native import (
    NativeThreadError,
    get_grok_thread_lineage,
    list_grok_threads_since,
    list_recent_opencode_threads,
    run_grok_goal,
)


async def main() -> None:
    repo = Path.cwd()
    try:
        goal = await run_grok_goal("Make the auth test suite pass without changing public endpoints.", api_key="xai-your-key", workspace=repo)
    except NativeThreadError as error:
        print(error.failure_code.value, error.next_step)  # e.g. grok.command_not_run and what to do next
        return
    print(goal.thread_id, goal.text[:200])

    # Every list helper returns the same NativeThreadSummary, so a cross-harness view is one sort.
    day = [*await list_grok_threads_since(repo, timedelta(hours=24)), *await list_recent_opencode_threads(repo)]
    for thread in sorted(day, key=lambda summary: summary.updated_at, reverse=True):
        print(thread.harness.value, thread.updated_at.isoformat(), thread.thread_id, thread.title, thread.parent_thread_id)

    print([summary.thread_id for summary in await get_grok_thread_lineage(goal.thread_id, repo)])


asyncio.run(main())
'''
GOAL = "Make the auth test suite pass without changing public endpoints."


def summary_time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def ms_time(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def test_the_helpers_example_runs_as_written_against_stand_ins_on_path(sandbox, stores, pack) -> None:
    # AC-1: the goal's id and text; one merged newest-first line per
    # Grok and opencode thread; the lineage ending with the goal.
    sandbox.stand_in(sandbox.bin, "grok", "grok")
    sandbox.stand_in(sandbox.bin, "opencode", "opencode")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    recent_ms, older_ms = int((now - timedelta(hours=2)).timestamp() * 1000), int((now - timedelta(hours=30)).timestamp() * 1000)
    stores.opencode_session("ses_recentfix", title="Fix flaky login test", created_ms=older_ms, updated_ms=recent_ms)
    stores.opencode_session("ses_oldercache", title="Refactor the cache", created_ms=older_ms, updated_ms=older_ms)
    stores.opencode_session("ses_otherrepo", directory=sandbox.root / "other-repo", updated_ms=recent_ms)
    environment = {**os.environ, "PYTHONPATH": str(pack.REPO_ROOT), "PATH": str(sandbox.bin), "USERPROFILE": str(sandbox.home), "HOME": str(sandbox.home)}
    for name in ("XAI_API_KEY", "GROK_CODE_XAI_API_KEY", "PWD"):
        environment.pop(name, None)
    finished = subprocess.run([sys.executable, "-c", SNIPPET], cwd=sandbox.workspace, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=240, stdin=subprocess.DEVNULL, check=False)
    assert finished.returncode == 0, finished.stderr[-3000:]
    start = sandbox.only_start("grok")
    goal_id = start["options"]["--session-id"]
    assert start["credentials"]["XAI_API_KEY"] == pack.key_digest("xai-your-key")
    summary_path = sandbox.grok_home() / "sessions" / stores.grok_group() / goal_id / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    expected = [
        f"{goal_id} {('grok answer to: /goal ' + GOAL)[:200]}",
        f"grok {summary_time(summary['updated_at']).isoformat()} {goal_id} {summary['generated_title']} None",
        f"opencode {ms_time(recent_ms).isoformat()} ses_recentfix Fix flaky login test None",
        f"opencode {ms_time(older_ms).isoformat()} ses_oldercache Refactor the cache None",
        str([goal_id]),
    ]
    assert finished.stdout.splitlines() == expected, finished.stdout + finished.stderr[-2000:]


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", ["grok", "opencode", "muse"])
async def test_threads_made_by_the_run_functions_are_the_ones_the_helpers_see(api, sandbox, call, helper, harness) -> None:
    # INV-13 / AC-6 / EC-76: run, then fork; both list in the default
    # scope; read returns the run's transcript; Grok and Muse forks link
    # to their source, an opencode fork is a one-element chain.
    first = await call(harness, prompt="Start the audit.")
    fork = await call(harness, "fork", "Branch the audit.", thread_id=first.thread_id)
    ws = sandbox.workspace
    listed = await helper(f"list_{harness}_threads", ws)
    assert {summary.thread_id for summary in listed} == {first.thread_id, fork.thread_id}
    chain = await helper(f"get_{harness}_thread_lineage", fork.thread_id, ws)
    if harness == "opencode":
        assert [(summary.thread_id, summary.parent_thread_id) for summary in chain] == [(fork.thread_id, None)], "EC-76: opencode forks record no parent"
    else:
        assert [(summary.thread_id, summary.parent_thread_id) for summary in chain] == [(first.thread_id, None), (fork.thread_id, first.thread_id)]
    found = await helper(f"get_{harness}_thread", first.thread_id, ws)
    assert found.thread_id == first.thread_id and found.harness.value == harness
    document = await helper(f"read_{harness}_thread", first.thread_id, ws)
    assert document.thread_id == first.thread_id and document.text_truncated is False and "Start the audit." in document.text
