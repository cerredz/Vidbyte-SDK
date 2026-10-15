"""FILE: tests/features/harness_threads/test_harness_threads_threads.py

PURPOSE: Thread ids across the verbs: continue sends each vendor's resume form and keeps the id (AC-6, FR-5), fork sends the fork form and returns a new id (AC-7, FR-6, D-9), Muse checks a thread over batch `muse serve` before it runs `exec` (AC-8, INV-11, D-17, EC-19), unknown ids fail as each vendor reports them (EC-20, EC-21), a fork that returns its source fails (EC-22; for Muse on the serve answer, before any exec, EC-45), a Muse exec answering on another stream is thread_not_found (EC-45), Grok compares the answered id case-insensitively (INV-11), and two spellings of one workspace reach the same Grok thread (EC-40, D-26).
ROLE IN CODEBASE: Start here when continue or fork reaches the wrong thread, or when Muse starts a billed run on an id it never checked.
ARCHITECTURE NOTE: The stand-in keeps threads as files (Grok under GROK_HOME keyed by --cwd, as Grok does; opencode and Muse in the scenario state folder), so continue and fork are checked against real vendor-side state rather than canned answers. `muse exec --session-id <unknown>` silently starts a new thread in the stand-in, as Muse 1.0.1 does, and logs that it did.
FUNCTION INVENTORY: serve_frames returns what the batch `muse serve` stand-in received; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new verb is a spec change first (D-2), then one more parametrized case here.
WHAT NOT TO DO IN THIS FILE: Do not fabricate thread ids that a stand-in never created for the success paths; read them from the stand-in's answer records.
KNOWN EDGE CASES: The Muse fork's new id comes from the serve exchange (the stand-in's `forked` record), not from exec.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-functions/spec.md §6.1 INV-5, INV-11, §6.2 AC-6 to AC-8, §6.3 EC-19 to EC-22, EC-40, EC-45, §9.2
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_threads.py
"""

from __future__ import annotations

import re
import sys

import pytest

HARNESSES = ("grok", "opencode", "muse")
UNKNOWN_ID = "0192f0c4-dead-7bee-8f00-000000000000"
UUID7 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def serve_frames(sandbox) -> list[dict]:
    return [record["frame"] for record in sandbox.records("frame", "muse-serve")]


def check_serve_handshake(frames: list[dict], method: str) -> dict:
    # §9.2 Muse serve: initialize{clientInfo{name,version}} id 1, the initialized notification, then the request id 2.
    assert [frame.get("method") for frame in frames] == ["initialize", "initialized", method]
    client = frames[0]["params"]["clientInfo"]
    assert frames[0]["id"] == 1 and isinstance(client["name"], str) and client["name"] and isinstance(client["version"], str) and client["version"]
    assert "id" not in frames[1]
    assert frames[2]["id"] == 2
    return frames[2]["params"]


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_continue_sends_the_resume_form_and_keeps_the_thread_id(sandbox, call, pack, harness) -> None:
    # AC-6 / FR-5: Grok --resume=<id>, opencode --session=<id>, Muse session/read then exec --session-id <id>.
    first = await call(harness)
    second = await call(harness, "continue", "Second prompt.", thread_id=first.thread_id)
    assert second.thread_id == first.thread_id
    assert second.text == f"{harness} answer to: Second prompt."
    if harness == "grok":
        start = sandbox.starts("grok")[-1]
        assert start["options"]["--resume"] == first.thread_id and start["switches"] == []
    elif harness == "opencode":
        start = sandbox.starts("opencode")[-1]
        assert start["options"]["--session"] == first.thread_id and start["switches"] == []
    else:
        assert [record["role_file"] for record in sandbox.starts()] == ["muse-exec", "muse-serve", "muse-exec"]
        assert check_serve_handshake(serve_frames(sandbox), "session/read") == {"sessionId": first.thread_id, "excludeItems": True}
        assert sandbox.starts("muse-exec")[-1]["options"]["--session-id"] == first.thread_id
        assert sandbox.records("silently_created") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_fork_runs_the_prompt_on_a_new_thread(sandbox, call, harness) -> None:
    # AC-7 / FR-6 / D-9: Grok --resume=<id> --fork-session, opencode --session=<id> --fork, Muse session/fork then exec on the new id.
    first = await call(harness)
    branch = await call(harness, "fork", "Branch prompt.", thread_id=first.thread_id)
    assert branch.thread_id != first.thread_id
    assert branch.text == f"{harness} answer to: Branch prompt."
    if harness == "grok":
        start = sandbox.starts("grok")[-1]
        assert start["options"]["--resume"] == first.thread_id and start["switches"] == ["--fork-session"]
        assert sandbox.answers("grok")[-1]["session"] == branch.thread_id
    elif harness == "opencode":
        start = sandbox.starts("opencode")[-1]
        assert start["options"]["--session"] == first.thread_id and start["switches"] == ["--fork"]
        assert sandbox.answers("opencode")[-1]["session"] == branch.thread_id
    else:
        assert [record["role_file"] for record in sandbox.starts()] == ["muse-exec", "muse-serve", "muse-exec"]
        params = check_serve_handshake(serve_frames(sandbox), "session/fork")
        assert params["sessionId"] == first.thread_id and params["excludeItems"] is True
        assert UUID7.fullmatch(params["commandId"]), "session/fork commandId must be a UUIDv7"
        assert [record["session"] for record in sandbox.records("forked")] == [branch.thread_id]
        assert sandbox.starts("muse-exec")[-1]["options"]["--session-id"] == branch.thread_id


@pytest.mark.asyncio
@pytest.mark.parametrize("verb", ["continue", "fork"])
async def test_muse_unknown_thread_is_refused_before_any_exec(api, sandbox, call, check_error, verb) -> None:
    # AC-8 / INV-11 / EC-19: session/read or session/fork answers -32020, so `muse exec` (which would silently create a thread) never starts.
    with pytest.raises(api.NativeThreadError) as caught:
        await call("muse", verb, "Again.", thread_id=UNKNOWN_ID)
    check_error(caught.value, harness="muse", verb=verb, code="muse.thread_not_found", workspace=sandbox.workspace, thread_id=UNKNOWN_ID)
    assert len(sandbox.starts("muse-serve")) == 1
    assert sandbox.starts("muse-exec") == [] and sandbox.records("silently_created") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("verb", ["continue", "fork"])
async def test_opencode_session_not_found_is_thread_not_found(api, sandbox, call, check_error, verb) -> None:
    # AC-8 / EC-20: opencode prints "Session not found" on stderr and exits 1.
    with pytest.raises(api.NativeThreadError) as caught:
        await call("opencode", verb, "Again.", thread_id=UNKNOWN_ID)
    check_error(caught.value, harness="opencode", verb=verb, code="opencode.thread_not_found", workspace=sandbox.workspace, thread_id=UNKNOWN_ID, vendor="Session not found", exit_code=1)


@pytest.mark.asyncio
async def test_grok_unknown_thread_fails_with_groks_own_text(api, sandbox, call, check_error) -> None:
    # EC-21 / A-2: Grok answers an unknown --resume with an error object and a non-zero exit, which is run_failed carrying Grok's text.
    with pytest.raises(api.NativeThreadError) as caught:
        await call("grok", "continue", "Again.", thread_id=UNKNOWN_ID)
    check_error(caught.value, harness="grok", verb="continue", code="grok.run_failed", workspace=sandbox.workspace, thread_id=UNKNOWN_ID, vendor=f"Session {UNKNOWN_ID} does not exist", exit_code=1)


@pytest.mark.asyncio
async def test_grok_thread_is_found_only_from_the_workspace_that_created_it(api, sandbox, call, check_error) -> None:
    # EC-21 / INV-13: another workspace has another private GROK_HOME, so its continue cannot see the thread.
    first = await call("grok")
    other = sandbox.root / "ws-other"
    other.mkdir()
    with pytest.raises(api.NativeThreadError) as caught:
        await call("grok", "continue", "Again.", thread_id=first.thread_id, workspace=other)
    check_error(caught.value, harness="grok", verb="continue", code="grok.run_failed", workspace=other, thread_id=first.thread_id)
    homes = [record["plain"]["GROK_HOME"] for record in sandbox.starts("grok")]
    assert homes[0] != homes[1]


@pytest.mark.asyncio
async def test_grok_continue_compares_the_answered_id_case_insensitively(sandbox, call) -> None:
    # INV-11: Grok may answer the id in another case; the result carries the id the caller gave.
    first = await call("grok")
    second = await call("grok", "continue", "Again.", thread_id=first.thread_id, fake={"mode": "continue_upper_id"})
    assert sandbox.answers("grok")[-1]["session"] == first.thread_id.upper() != first.thread_id
    assert second.thread_id == first.thread_id


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", ["grok", "opencode"])
async def test_continue_answered_on_another_thread_is_thread_not_found(api, sandbox, call, harness) -> None:
    # INV-6 / INV-11 / §12.3 rows 37 and 40: a continue whose answer names a different thread is <harness>.thread_not_found.
    first = await call(harness)
    with pytest.raises(api.NativeThreadError) as caught:
        await call(harness, "continue", "Again.", thread_id=first.thread_id, fake={"mode": "continue_other_id"})
    assert caught.value.failure_code.value == f"{harness}.thread_not_found"


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", ["grok", "opencode"])
async def test_fork_that_returns_its_source_is_protocol_mismatch(api, sandbox, call, check_error, harness) -> None:
    # EC-22 / INV-11: the vendor continued the source thread instead of forking it.
    first = await call(harness)
    with pytest.raises(api.NativeThreadError) as caught:
        await call(harness, "fork", "Branch.", thread_id=first.thread_id, fake={"mode": "fork_returns_source"})
    check_error(caught.value, harness=harness, verb="fork", code=f"{harness}.protocol_mismatch", workspace=sandbox.workspace, thread_id=first.thread_id)


@pytest.mark.asyncio
async def test_grok_continue_reaches_the_thread_through_another_spelling_of_the_workspace(sandbox, call) -> None:
    # EC-40 / D-26: the workspace is stored resolved, so --cwd and the private home do not depend on the spelling.
    first = await call("grok")
    (sandbox.workspace / "sub").mkdir()
    spelled = str(sandbox.workspace / "sub" / "..")
    if sys.platform == "win32":
        spelled = spelled.swapcase()
    second = await call("grok", "continue", "Again.", thread_id=first.thread_id, workspace=spelled)
    assert second.thread_id == first.thread_id
    run_start, continue_start = sandbox.starts("grok")
    assert continue_start["plain"]["GROK_HOME"] == run_start["plain"]["GROK_HOME"]
    assert continue_start["options"]["--cwd"] == run_start["options"]["--cwd"] == str(sandbox.workspace)


@pytest.mark.asyncio
async def test_muse_fork_answered_with_its_source_is_protocol_mismatch_before_any_exec(api, sandbox, call, check_error) -> None:
    # EC-45 / INV-6 / INV-11: session/fork answering the source id is decided on the serve answer, so exec never starts.
    first = await call("muse")
    with pytest.raises(api.NativeThreadError) as caught:
        await call("muse", "fork", "Branch.", thread_id=first.thread_id, fake={"serve_mode": "fork_returns_source"})
    assert [record["session"] for record in sandbox.records("forked")] == [first.thread_id]
    check_error(caught.value, harness="muse", verb="fork", code="muse.protocol_mismatch", workspace=sandbox.workspace, thread_id=first.thread_id)
    assert len(sandbox.starts("muse-exec")) == 1, "only the first run's exec; the fork never reached exec"


@pytest.mark.asyncio
async def test_muse_continue_answered_on_another_stream_is_thread_not_found(api, sandbox, call, check_error) -> None:
    # EC-45 / INV-11 / INV-5: the exec's session stream is not the id sent with --session-id; the error carries the stream id Muse answered.
    first = await call("muse")
    with pytest.raises(api.NativeThreadError) as caught:
        await call("muse", "continue", "Again.", thread_id=first.thread_id, fake={"mode": "continue_other_id"})
    execs = sandbox.starts("muse-exec")
    assert len(execs) == 2 and execs[-1]["options"]["--session-id"] == first.thread_id
    answered = sandbox.records("session", "muse-exec")[-1]["session"]
    assert answered != first.thread_id
    check_error(caught.value, harness="muse", verb="continue", code="muse.thread_not_found", workspace=sandbox.workspace, thread_id=answered)
