"""FILE: tests/features/harness_threads/test_harness_threads_errors.py

PURPOSE: Failure classification and detail: each INV-6 condition provoked through a stand-in yields its closed code with every INV-5 element in order (AC-10, NFR-7, FR-10): not installed, launch failed (EC-13), key rejected (EC-9), run failed (EC-23), protocol mismatch (EC-18), Muse serve failures, and an unexpected defect as runtime.error naming only its class (EC-32), the workspace, and on continue and fork the caller's thread id (INV-5 element 4, review R-7). Also the error class itself (D-10, §12.3 row 24) and the per-code likely-cause and next-step texts (comment 1).
ROLE IN CODEBASE: Start here when an error has the wrong code, loses a detail, or shows exception text it should not.
ARCHITECTURE NOTE: check_error (conftest.py) asserts the INV-5 attributes, that likely_cause and next_step are exactly the texts NATIVE_THREAD_LIKELY_CAUSES and NATIVE_THREAD_NEXT_STEPS hold for the code, and that the message names, in order, the function, the code, the harness label, the workspace, the thread id when known, the observation, the vendor text, the likely cause and the next step. Timeouts and output caps are in test_harness_threads_process_bounds.py, batch launchers in test_harness_threads_launcher.py, WSL in test_harness_threads_wsl.py.
FUNCTION INVENTORY: printed_session reads the thread id the stand-in printed; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new failure condition is a spec change first (INV-6), then one stand-in mode and one case here.
WHAT NOT TO DO IN THIS FILE: Do not compare the free text of likely causes or next steps; compare them to the constants maps.
KNOWN EDGE CASES: The failure exit code is 93 so it cannot be confused with other digits in the message. On win32 a non-program file fails as os_error (WinError 193); on POSIX a non-executable file fails as permission_denied.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/harness-thread-functions/spec.md §6.1 INV-5, INV-6, §6.2 AC-10, §6.3 EC-9, EC-13, EC-18, EC-23, EC-32, §12.3 rows 23, 24, 32; docs/spec/harness-thread-functions/review.md R-7
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_errors.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HARNESSES = ("grok", "opencode", "muse")
EXIT = 93
UNKNOWN_ID = "0192f0c4-beef-7bee-8f00-000000000000"
DEFECT_THREAD = "0192f0c4-feed-7bee-8f00-000000000001"
PROBLEMS = ["not_installed", "launcher_refused", "launch_failed", "key_rejected", "thread_not_found", "timed_out", "output_too_large", "protocol_mismatch", "run_failed"]
DIAGNOSTIC_FIELDS = ("error_kind", "expected", "actual", "safe_runtime_details", "likely_causes", "repair_approaches", "related_docs", "relevant_tests")


def printed_session(sandbox) -> str:
    sessions = sandbox.records("session")
    assert len(sessions) == 1
    return sessions[0]["session"]


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_missing_launcher_is_not_installed_naming_it(api, sandbox, call, check_error, pack, harness) -> None:
    # INV-6 not_installed / EC-11: an explicit command that does not exist.
    missing = sandbox.root / "no-such-folder" / f"{harness}-bin"
    with pytest.raises(api.NativeThreadError) as caught:
        await call(harness, command=(str(missing),))
    check_error(caught.value, harness=harness, verb="run", code=f"{harness}.not_installed", workspace=sandbox.workspace, thread_id=None, observations=[("launcher path", pack.path_spellings(missing))])
    assert sandbox.starts() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_launcher_the_os_refuses_is_launch_failed(api, sandbox, call, check_error, pack, harness) -> None:
    # INV-6 launch_failed / EC-13: the file exists but the OS will not start it; the message names the program and the failure kind.
    if sys.platform == "win32":
        target, kind = sandbox.root / f"{harness}-not-a-program.txt", "os_error"
        target.write_text("this file is not a program\n", encoding="utf-8")
    else:
        target, kind = sandbox.root / f"{harness}-not-executable", "permission_denied"
        target.write_text("#!/bin/sh\necho never\n", encoding="utf-8")
        target.chmod(0o644)
    with pytest.raises(api.NativeThreadError) as caught:
        await call(harness, command=(str(target),))
    check_error(caught.value, harness=harness, verb="run", code=f"{harness}.launch_failed", workspace=sandbox.workspace, thread_id=None, observations=[("program", pack.path_spellings(target)), ("launch failure kind", (kind,))])


@pytest.mark.asyncio
@pytest.mark.parametrize(("harness", "mode", "vendor"), [
    ("grok", "key_rejected", "Not signed in"),
    ("opencode", "key_rejected", "was not accepted"),
    ("opencode", "key_rejected_status", "the provider refused the credentials"),
    ("muse", "key_rejected", "authentication failed"),
])
async def test_vendor_refusing_the_key_is_key_rejected(api, sandbox, call, check_error, harness, mode, vendor) -> None:
    # INV-6 key_rejected / EC-9: Grok "Not signed in", opencode ProviderAuthError or status 401/403, Muse "authentication failed".
    with pytest.raises(api.NativeThreadError) as caught:
        await call(harness, fake={"mode": mode})
    thread_id = printed_session(sandbox) if harness == "opencode" else None
    check_error(caught.value, harness=harness, verb="run", code=f"{harness}.key_rejected", workspace=sandbox.workspace, thread_id=thread_id, vendor=vendor, exit_code=1)


@pytest.mark.asyncio
@pytest.mark.parametrize(("harness", "mode", "printed"), [
    ("grok", "fail", False), ("grok", "stderr_exit", False),
    ("opencode", "fail", True), ("opencode", "stderr_exit", False),
    ("muse", "terminal_failed", True), ("muse", "fail", False),
])
async def test_vendor_reported_failure_is_run_failed_with_exit_status_and_text(api, sandbox, call, check_error, harness, mode, printed) -> None:
    # INV-6 run_failed / EC-23: a Grok error object, an opencode error event, a Muse terminal state other than completed, or a bare non-zero exit.
    vendor = "the model refused because the workspace is read only"
    with pytest.raises(api.NativeThreadError) as caught:
        await call(harness, fake={"mode": mode, "vendor_text": vendor, "exit_code": EXIT})
    thread_id = printed_session(sandbox) if printed else None
    check_error(caught.value, harness=harness, verb="run", code=f"{harness}.run_failed", workspace=sandbox.workspace, thread_id=thread_id, observations=[("exit status", (str(EXIT),))], vendor=vendor, exit_code=EXIT)


@pytest.mark.asyncio
@pytest.mark.parametrize(("harness", "mode", "member", "printed"), [
    ("grok", "garbage", None, False), ("grok", "missing_session", "sessionId", False),
    ("opencode", "garbage", "sessionID", False),
    ("muse", "no_terminal", None, True), ("muse", "no_session", None, False),
])
async def test_unreadable_success_output_is_protocol_mismatch(api, sandbox, call, check_error, harness, mode, member, printed) -> None:
    # INV-6 protocol_mismatch / EC-18: exit 0 but no readable answer, no thread id, or no terminal record; the missing member is named.
    with pytest.raises(api.NativeThreadError) as caught:
        await call(harness, fake={"mode": mode})
    thread_id = printed_session(sandbox) if printed else None
    observations = [("missing member", (member,))] if member else []
    check_error(caught.value, harness=harness, verb="run", code=f"{harness}.protocol_mismatch", workspace=sandbox.workspace, thread_id=thread_id, observations=observations, exit_code=0)


@pytest.mark.asyncio
async def test_muse_serve_error_other_than_not_found_is_run_failed_and_no_exec_starts(api, sandbox, call, check_error) -> None:
    # §12.3 row 43: an error answer other than -32020 to session/read is run_failed; exec never starts.
    with pytest.raises(api.NativeThreadError) as caught:
        await call("muse", "continue", "Again.", thread_id=UNKNOWN_ID, fake={"serve_mode": "other_error"})
    check_error(caught.value, harness="muse", verb="continue", code="muse.run_failed", workspace=sandbox.workspace, thread_id=UNKNOWN_ID, vendor="the session store is locked")
    assert sandbox.starts("muse-exec") == []


@pytest.mark.asyncio
async def test_muse_serve_that_never_answers_the_request_is_protocol_mismatch(api, sandbox, call, check_error) -> None:
    # §12.3 row 43: no answer with id 2 before the serve child exits is protocol_mismatch; exec never starts.
    with pytest.raises(api.NativeThreadError) as caught:
        await call("muse", "fork", "Branch.", thread_id=UNKNOWN_ID, fake={"serve_mode": "no_answer"})
    check_error(caught.value, harness="muse", verb="fork", code="muse.protocol_mismatch", workspace=sandbox.workspace, thread_id=UNKNOWN_ID)
    assert sandbox.starts("muse-exec") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
async def test_unexpected_defect_is_runtime_error_naming_only_the_class(api, sandbox, call, check_error, monkeypatch, harness) -> None:
    # EC-32 / INV-5: an exception inside the SDK becomes runtime.error; its text never reaches the error.
    secret_detail = "internal-detail-that-must-not-leak"

    async def broken_run(self, invocation):
        raise KeyError(secret_detail)

    monkeypatch.setattr(api.CliRunner, "run", broken_run)
    with pytest.raises(api.NativeThreadError) as caught:
        await call(harness)
    error = caught.value
    check_error(error, harness=harness, verb="run", code="runtime.error", observations=[("exception class", ("KeyError",))])
    for text in (str(error), repr(error), error.vendor_message or "", repr(error.details)):
        assert secret_detail not in text


@pytest.mark.asyncio
@pytest.mark.parametrize("harness", HARNESSES)
@pytest.mark.parametrize("verb", ["run", "continue", "fork"])
async def test_unexpected_defect_names_the_workspace_and_the_callers_thread(api, sandbox, call, check_error, monkeypatch, harness, verb) -> None:
    # INV-5 element 4 / EC-32 / R-7: runtime.error still names the
    # workspace, and on continue and fork carries the caller's thread.
    secret_detail = "internal-detail-that-must-not-leak"

    async def broken_run(self, invocation):
        raise KeyError(secret_detail)

    monkeypatch.setattr(api.CliRunner, "run", broken_run)
    thread_id = None if verb == "run" else DEFECT_THREAD
    with pytest.raises(api.NativeThreadError) as caught:
        await call(harness, verb, thread_id=thread_id)
    error = caught.value
    assert error.thread_id == thread_id, f"INV-5 / R-7: runtime.error dropped the caller's thread id {thread_id!r}"
    check_error(error, harness=harness, verb=verb, code="runtime.error", workspace=sandbox.workspace, thread_id=thread_id, observations=[("exception class", ("KeyError",))])
    for text in (str(error), repr(error), error.vendor_message or "", repr(error.details)):
        assert secret_detail not in text


@pytest.mark.asyncio
async def test_error_class_carries_the_diagnostic_packet_for_this_feature(api, sandbox, call) -> None:
    # D-10 / §12.3 row 24: literal DIAGNOSTIC_FIELDS, the harnesses README, this pack, and likely cause and next step as the packet.
    with pytest.raises(api.NativeThreadError) as caught:
        await call("grok", api_key="")
    error = caught.value
    assert issubclass(api.NativeThreadError, api.AgentExecutionError)
    assert api.NativeThreadError.DIAGNOSTIC_FIELDS == DIAGNOSTIC_FIELDS
    assert error.related_docs == ("vidbyte/harnesses/README.md",)
    assert error.relevant_tests == ("tests/features/harness_threads",)
    assert all((Path(__file__).resolve().parents[3] / path).exists() for path in (*error.related_docs, *error.relevant_tests))
    assert error.likely_causes == (error.likely_cause,) and error.repair_approaches == (error.next_step,)
    assert set(error.details) == set(DIAGNOSTIC_FIELDS)
    runtime = repr(error.safe_runtime_details)
    assert "grok" in runtime and "run_grok_thread" in runtime
    assert (error.thread_id, error.exit_code, error.vendor_message) == (None, None, None)


def test_every_code_has_its_own_likely_cause_and_next_step(lib_api) -> None:
    # D-10 / comment 1: texts written per code, for the 28 harness codes plus invalid_argument and runtime.error.
    codes = lib_api.FailureCode
    harness_codes = [codes(f"{harness}.{problem}") for harness in HARNESSES for problem in PROBLEMS] + [codes("muse.wsl_unavailable")]
    expected = {*harness_codes, codes.CONFIGURATION_INVALID_ARGUMENT, codes.RUNTIME_ERROR}
    for table in (lib_api.constants.NATIVE_THREAD_LIKELY_CAUSES, lib_api.constants.NATIVE_THREAD_NEXT_STEPS):
        assert set(table) == expected
        assert all(isinstance(text, str) and text.strip() for text in table.values())
        for harness in HARNESSES:
            texts = [table[code] for code in harness_codes if code.value.startswith(harness + ".")]
            assert len(set(texts)) == len(texts), f"{harness}: two codes share one text"
