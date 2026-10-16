"""FILE: tests/features/harness_threads/test_harness_threads_claude_threads.py

PURPOSE: Claude Code thread ids across the verbs (spec claude-thread-functions INV-12): continue sends `--resume <id>` without `--fork-session` and returns exactly the given id (AC-3, FR-2), fork sends `--resume <id> --fork-session` and returns the new id (AC-4, FR-3), an id Claude Code does not know is claude.thread_not_found carrying the caller's id (AC-12, EC-5), a thread is found only from the workspace that created it and from any spelling of that workspace (EC-7, INV-13), a continue answered on another id is claude.thread_not_found and one answered in upper case is claude.protocol_mismatch (AC-14, AC-13, INV-12, R-1), and a fork answered with its source id is claude.protocol_mismatch (AC-14, EC-19).
ROLE IN CODEBASE: Start here when continue or fork reaches the wrong Claude Code thread, or when a missing thread surfaces as something other than thread_not_found.
ARCHITECTURE NOTE: The stand-in keeps each thread as a transcript file under CLAUDE_CONFIG_DIR/projects/<cwd key>/<id>.jsonl and resolves `--resume` by searching every project folder of that config folder, as Claude Code 2.1.301 does (vendor-facts p07, p08), so continue and fork are checked against real vendor-side state. An unknown id gets Claude Code's own pre-run failure: exit 1, empty stdout, `No conversation found with session ID: <id>` on stderr (p05).
FUNCTION INVENTORY: the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new thread rule is a spec change first (INV-12), then one stand-in mode and one test here.
WHAT NOT TO DO IN THIS FILE: Do not fabricate thread ids for the success paths; read them from the stand-in's answer records. UNKNOWN_ID is a well-formed lowercase UUID on purpose, so it passes the argument check and reaches the stand-in.
KNOWN EDGE CASES: Under INV-6 a failed continue always reports the caller's id, so the wrong-thread error carries the id the caller gave and names the answered id only in its message.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/claude-thread-functions/spec.md §6.1 INV-6, INV-7, INV-12, INV-13, §6.2 AC-3, AC-4, AC-12 to AC-14, §6.3 EC-5, EC-7, EC-19; docs/spec/claude-thread-functions/context/vendor-facts.md §4, §7
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_claude_threads.py
"""

from __future__ import annotations

import os
import sys

import pytest

UNKNOWN_ID = "11111111-2222-4333-8444-555555555555"
NOT_FOUND_MARKER = "No conversation found with session ID"
TESTED_VERSION = "2.1.301"


@pytest.mark.asyncio
async def test_continue_resumes_the_thread_and_returns_exactly_the_given_id(sandbox, call) -> None:
    # AC-3 / FR-2 / INV-12: --resume <id> and no --fork-session; the
    # result carries the given id and the new answer.
    first = await call("claude")
    second = await call("claude", "continue", "Second prompt.", thread_id=first.thread_id)
    assert second.thread_id == first.thread_id
    assert second.text == "claude answer to: Second prompt."
    start = sandbox.starts("claude")[-1]
    assert start["options"]["--resume"] == first.thread_id and "--fork-session" not in start["switches"]
    assert sandbox.answers("claude")[-1]["session"] == first.thread_id and sandbox.answers("claude")[-1]["resumed"] == first.thread_id


@pytest.mark.asyncio
async def test_fork_resumes_with_fork_session_and_returns_the_new_id(sandbox, call) -> None:
    # AC-4 / FR-3 / INV-12: --resume <id> --fork-session; the result is
    # the stand-in's new id, never the source's.
    first = await call("claude")
    branch = await call("claude", "fork", "Branch prompt.", thread_id=first.thread_id)
    assert branch.thread_id != first.thread_id
    assert branch.thread_id == sandbox.answers("claude")[-1]["session"]
    assert branch.text == "claude answer to: Branch prompt."
    start = sandbox.starts("claude")[-1]
    assert start["options"]["--resume"] == first.thread_id and "--fork-session" in start["switches"]


@pytest.mark.asyncio
@pytest.mark.parametrize("verb", ["continue", "fork"])
async def test_unknown_thread_is_thread_not_found_with_the_callers_id(api, sandbox, call, check_error, verb) -> None:
    # AC-12 / EC-5 / INV-7 step 8: exit 1, empty stdout and Claude
    # Code's marker on stderr; the caller's id, the marker and the exit
    # status reach the error.
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", verb, "Again.", thread_id=UNKNOWN_ID)
    check_error(caught.value, harness="claude", verb=verb, code="claude.thread_not_found", workspace=sandbox.workspace, thread_id=UNKNOWN_ID, vendor=f"{NOT_FOUND_MARKER}: {UNKNOWN_ID}", exit_code=1)
    assert caught.value.vendor_message == f"{NOT_FOUND_MARKER}: {UNKNOWN_ID}"
    assert len(sandbox.starts("claude")) == 1, "INV-11: one child per call"


@pytest.mark.asyncio
async def test_thread_is_found_only_from_the_workspace_that_created_it(api, sandbox, call, check_error) -> None:
    # EC-7 / INV-13 / D-3: another workspace has another private config
    # folder, so its continue cannot see the thread.
    first = await call("claude")
    other = sandbox.root / "ws-other"
    other.mkdir()
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", "continue", "Again.", thread_id=first.thread_id, workspace=other)
    check_error(caught.value, harness="claude", verb="continue", code="claude.thread_not_found", workspace=other, thread_id=first.thread_id)
    homes = [record["plain"]["CLAUDE_CONFIG_DIR"] for record in sandbox.starts("claude")]
    assert os.path.normcase(homes[1]) == os.path.normcase(str(sandbox.claude_config(other))) != os.path.normcase(homes[0])


@pytest.mark.asyncio
async def test_continue_reaches_the_thread_through_another_spelling_of_the_workspace(sandbox, call) -> None:
    # INV-13 / D-3: the folder key is the resolved, normcased workspace,
    # so `ws/sub/..` (and on win32 another letter case) finds the run's
    # config folder and runs in the same folder.
    first = await call("claude")
    (sandbox.workspace / "sub").mkdir()
    spelled = str(sandbox.workspace / "sub" / "..")
    if sys.platform == "win32":
        spelled = spelled.swapcase()
    second = await call("claude", "continue", "Again.", thread_id=first.thread_id, workspace=spelled)
    assert second.thread_id == first.thread_id
    run_start, continue_start = sandbox.starts("claude")
    assert continue_start["plain"]["CLAUDE_CONFIG_DIR"] == run_start["plain"]["CLAUDE_CONFIG_DIR"]
    assert os.path.normcase(continue_start["cwd"]) == os.path.normcase(run_start["cwd"]) == os.path.normcase(str(sandbox.workspace))


@pytest.mark.asyncio
async def test_continue_answered_on_another_valid_id_is_thread_not_found(api, sandbox, call, check_error) -> None:
    # AC-14 / INV-12 / EC-19 / R-1: a lowercase UUID other than the one
    # sent; the error carries the caller's id (INV-6) and names the
    # answered one.
    first = await call("claude")
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", "continue", "Again.", thread_id=first.thread_id, fake={"mode": "continue_other_id"})
    answered = sandbox.answers("claude")[-1]["session"]
    assert answered != first.thread_id
    check_error(caught.value, harness="claude", verb="continue", code="claude.thread_not_found", workspace=sandbox.workspace, thread_id=first.thread_id, observations=[("answered id", (answered,))])


@pytest.mark.asyncio
async def test_continue_answered_in_upper_case_is_protocol_mismatch(api, sandbox, call, check_error) -> None:
    # AC-13 / INV-12 / A-4 / R-1: Claude Code ids are lowercase UUIDs,
    # so the caller's id in upper case is a bad session_id member, not a
    # match and not another thread.
    first = await call("claude")
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", "continue", "Again.", thread_id=first.thread_id, fake={"mode": "continue_upper_id"})
    assert sandbox.answers("claude")[-1]["session"] == first.thread_id.upper() != first.thread_id
    check_error(caught.value, harness="claude", verb="continue", code="claude.protocol_mismatch", workspace=sandbox.workspace, thread_id=first.thread_id, observations=[("tested version", (TESTED_VERSION,)), ("bad member", ("session_id",))])


@pytest.mark.asyncio
async def test_fork_answered_with_its_source_is_protocol_mismatch(api, sandbox, call, check_error) -> None:
    # AC-14 / INV-12 / EC-19: Claude Code continued the source instead
    # of forking it.
    first = await call("claude")
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", "fork", "Branch.", thread_id=first.thread_id, fake={"mode": "fork_returns_source"})
    assert sandbox.answers("claude")[-1]["session"] == first.thread_id
    check_error(caught.value, harness="claude", verb="fork", code="claude.protocol_mismatch", workspace=sandbox.workspace, thread_id=first.thread_id, observations=[("tested version", (TESTED_VERSION,))])
