"""FILE: tests/features/harness_threads/test_harness_threads_claude_errors.py

PURPOSE: How a Claude Code answer is classified (spec claude-thread-functions INV-7, D-10): a JSON object with is_error true and an integer api_error_status of 401 or 403 is claude.key_rejected carrying the reason, status and result text and the answer's session_id (AC-11, EC-4, EC-34); one of 408, 429 or a 5xx is claude.api_error, the one retryable code, carrying the status as api_status (PR #1044 review); any other status, no status or a non-integer status is claude.run_failed with that text (AC-11, EC-18, EC-36); `subtype` decides only a stop at the call's own limit, error_max_budget_usd or error_max_turns, which is claude.budget_exhausted whatever its status, with the text built from the `errors` list when there is no `result` (EC-17, PR #1044 review); a non-zero exit whose stderr holds the option parser's error line (unknown option, invalid choice, missing argument) is claude.protocol_mismatch naming the tested version (PR #1044 review); any other non-zero exit is claude.run_failed carrying stderr (AC-12); exit 0 with output that is not one JSON object, an is_error that is not false, a session_id that is not a lowercase UUID or a result that is not a string is claude.protocol_mismatch naming the member and the tested version 2.1.302 (AC-10, AC-13, EC-16); stderr on a successful answer is ignored (EC-35); a success returns a ClaudeThreadResult whose num_turns, terminal_reason and permission_denials (tool name and tool-use id only) come from the answer, an unusable or missing one reading as its default (PR #1044 review); and a failed fork reports the fork's new id while a failed continue reports the caller's (INV-6, D-14).
ROLE IN CODEBASE: Start here when a Claude Code failure gets the wrong code, loses Claude's own text, or reports the wrong thread.
ARCHITECTURE NOTE: The stand-in prints Claude Code 2.1.302's one JSON result object (vendor-facts §6): success, the 401 shape with subtype "success", the budget shape with `errors` and no `result`, a generic in-run error, and any member overridden or dropped by the scenario's `override` and `drop` fields. check_error (conftest.py) asserts the INV-6 attributes, that likely_cause and next_step are the table texts for the code, and the message order. Vendor text is compared with the spec's own templates, CLAUDE_ERROR_TEXT and CLAUDE_ERROR_STATUS_TEXT, read from the constants module.
FUNCTION INVENTORY: printed_session reads the session id the stand-in printed; vendor_text formats the expected vendor text from the spec templates; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new answer shape is a spec change first (INV-7), then one row in a case table here.
WHAT NOT TO DO IN THIS FILE: Do not compare the free text of likely causes or next steps; compare them to the constants maps.
KNOWN EDGE CASES: `True` is an int in Python but never taken as a status, so `api_error_status: true` is run_failed with api_status None, though still formatted with the status template (spec §13). The exit code of an in-run error is 1, as Claude Code's; RUN_EXIT (93) is used for bare non-zero exits so it cannot be confused with other digits in a message.
RELATED DOCS: tests/features/harness_threads/FEATURE.md; docs/spec/claude-thread-functions/spec.md §6.1 INV-6, INV-7, §6.2 AC-10 to AC-13, §6.3 EC-4, EC-16 to EC-18, EC-34 to EC-36, §8.1 D-10, D-14, §9.2, §13; docs/spec/claude-thread-functions/context/vendor-facts.md §6
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/test_harness_threads_claude_errors.py
"""

from __future__ import annotations

import pytest

RUN_EXIT = 93
TESTED_VERSION = "2.1.302"
KEY_TEXT = "Invalid API key · Fix external API key"
VENDOR = "Overloaded: the API is busy, retry later"
BUDGET = "Reached maximum budget ($0.00001)"
TURNS = "Reached maximum number of turns (2)"
OTHER_SESSION = "22222222-3333-4444-8555-666666666666"
REJECTED_STATUSES = [401, 403]
# 2.1.302's option parser errors, as printed for a refused argv.
REFUSED_OPTION_LINES = [
    "error: unknown option '--example'",
    "error: option '--permission-mode <mode>' argument 'default' is invalid. Allowed choices are acceptEdits, auto, bypassPermissions, manual, dontAsk, plan.",
    "error: missing required argument 'prompt'",
    "Notice: a newer Claude Code is available\nerror: unknown option '--example'",
]
# PR #1044 review 4301626281: the statuses a later retry can clear.
RETRYABLE_STATUSES = [("timeout", 408), ("rate-limited", 429), ("server", 500), ("overloaded", 529)]
OTHER_STATUSES = [
    ("billing", 400, True, 400), ("null", None, False, None), ("true", True, True, None),
    ("string-401", "401", False, None), ("list", [401], False, None), ("object", {"code": 401}, False, None),
]
# PR #1044 review 4301898270: the stops at the call's own limits, as
# 2.1.302 prints them: the subtype, the terminal reason and an errors
# list, with no result member.
LIMIT_STOPS = [
    ("budget", {}, "budget_exhausted", BUDGET),
    ("turns", {"subtype": "error_max_turns", "terminal_reason": "max_turns"}, "max_turns", TURNS),
]
# PR #1044 review 4301626286: denied tool calls as 2.1.302 lists them,
# with unusable entries the reader skips.
DENIALS = [
    {"tool_name": "Bash", "tool_use_id": "toolu_01", "tool_input": {"command": "cat .env", "description": "Read the env file"}},
    {"tool_name": 7, "tool_use_id": "toolu_02"}, "Bash", {"tool_name": "Edit"}, {"tool_name": "Write", "tool_use_id": "x" * 257},
]
UNUSABLE_REPORTS = [
    ({"num_turns": True, "terminal_reason": 5, "permission_denials": {"tool_name": "Bash"}}, []),
    ({"num_turns": -1, "terminal_reason": "x" * 257}, []),
    ({}, ["num_turns", "terminal_reason", "permission_denials"]),
]
BAD_MEMBERS = [
    ("is_error-missing", {}, ["is_error"], "is_error"), ("is_error-string", {"is_error": "false"}, [], "is_error"), ("is_error-null", {"is_error": None}, [], "is_error"),
    ("is_error-zero", {"is_error": 0}, [], "is_error"), ("session-missing", {}, ["session_id"], "session_id"), ("session-upper", {"session_id": "C3F73F50-B50C-4F3A-8369-F97267313173"}, [], "session_id"),
    ("session-not-uuid", {"session_id": "fix-login"}, [], "session_id"), ("session-number", {"session_id": 7}, [], "session_id"),
    ("result-missing", {}, ["result"], "result"), ("result-number", {"result": 42}, [], "result"), ("result-list", {"result": ["done"]}, [], "result"),
]


def printed_session(sandbox) -> str:
    sessions = sandbox.records("session", "claude")
    assert sessions, "the stand-in printed no session"
    return sessions[-1]["session"]


def vendor_text(api, reason: str, message: str, status=None, with_status: bool = False) -> str:
    # D-10 / §8.5: "{reason} (status {status}): {message}" when the
    # status is an int, else "{reason}: {message}".
    constants = api.constants
    return constants.CLAUDE_ERROR_STATUS_TEXT.format(reason=reason, status=status, message=message) if with_status else constants.CLAUDE_ERROR_TEXT.format(reason=reason, message=message)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", REJECTED_STATUSES)
async def test_401_or_403_answer_is_key_rejected_with_the_answers_session(api, sandbox, call, check_error, status) -> None:
    # AC-11 / EC-4 / EC-34 / D-10: exit 1, is_error true, an int status
    # in {401, 403}, subtype "success" (so subtype cannot decide); the
    # reason, status and result reach vendor_message and the session_id
    # becomes thread_id.
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", fake={"mode": "key_rejected", "status": status})
    expected = vendor_text(api, "api_error", KEY_TEXT, status, True)
    check_error(caught.value, harness="claude", verb="run", code="claude.key_rejected", workspace=sandbox.workspace, thread_id=printed_session(sandbox), vendor=expected, exit_code=1)
    assert caught.value.vendor_message == expected
    assert caught.value.retryable is False and caught.value.api_status == status


@pytest.mark.asyncio
@pytest.mark.parametrize(("case", "status"), RETRYABLE_STATUSES, ids=[case for case, _ in RETRYABLE_STATUSES])
async def test_timeout_rate_limit_or_server_status_is_a_retryable_api_error(api, sandbox, call, check_error, case, status) -> None:
    # PR #1044 review 4301626281 / 4301898270: is_error true with 408,
    # 429 or a 5xx is claude.api_error, whose error says a plain retry
    # can succeed and carries the status, so a caller can back off on
    # it without reading the vendor text; the answer's session stays
    # the thread to continue.
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", fake={"mode": "api_error", "status": status, "vendor_text": VENDOR})
    expected = vendor_text(api, "api_error", VENDOR, status, True)
    check_error(caught.value, harness="claude", verb="run", code="claude.api_error", workspace=sandbox.workspace, thread_id=printed_session(sandbox), vendor=expected, exit_code=1)
    assert caught.value.retryable is True and caught.value.api_status == status
    assert caught.value.safe_runtime_details["retryable"] == "true" and caught.value.safe_runtime_details["api_status"] == str(status)


@pytest.mark.asyncio
@pytest.mark.parametrize(("case", "status", "with_status", "api_status"), OTHER_STATUSES, ids=[case for case, _, _, _ in OTHER_STATUSES])
async def test_any_other_error_status_is_run_failed_with_claudes_text(api, sandbox, call, check_error, case, status, with_status, api_status) -> None:
    # AC-11 / EC-18 / EC-36 / §13: is_error true with 400, true, null or
    # a status that is not an int; only an int status is shown in the
    # vendor text, and only a real int one becomes api_status; none of
    # them is retryable.
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", fake={"mode": "api_error", "status": status, "vendor_text": VENDOR})
    expected = vendor_text(api, "api_error", VENDOR, status, with_status)
    check_error(caught.value, harness="claude", verb="run", code="claude.run_failed", workspace=sandbox.workspace, thread_id=printed_session(sandbox), vendor=expected, exit_code=1)
    assert caught.value.vendor_message == expected
    assert caught.value.retryable is False and caught.value.api_status == api_status


@pytest.mark.asyncio
@pytest.mark.parametrize(("case", "override", "reason", "text"), LIMIT_STOPS, ids=[case for case, _, _, _ in LIMIT_STOPS])
async def test_stop_at_the_calls_own_limit_is_budget_exhausted_from_its_errors_list(api, sandbox, call, check_error, case, override, reason, text) -> None:
    # AC-11 / EC-17 / f7 and PR #1044 review 4301898270: subtype
    # error_max_budget_usd or error_max_turns, an errors list and no
    # result member is claude.budget_exhausted, not retryable, carrying
    # the answer's session to continue with a higher limit.
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", fake={"mode": "budget", "errors": [text, "Second note"], "override": override})
    error = caught.value
    check_error(error, harness="claude", verb="run", code="claude.budget_exhausted", workspace=sandbox.workspace, thread_id=printed_session(sandbox), vendor=reason, exit_code=1)
    assert error.vendor_message.startswith(f"{reason}: ") and text in error.vendor_message and "Second note" in error.vendor_message
    assert "(status" not in error.vendor_message and error.retryable is False and error.api_status is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("override", "code"), [({"subtype": "error_max_turns", "api_error_status": 429}, "claude.budget_exhausted"), ({"subtype": ["error_max_turns"], "api_error_status": 429}, "claude.api_error")], ids=["limit-with-429", "list-subtype"])
async def test_only_a_text_limit_subtype_decides_before_the_api_status(api, sandbox, call, override, code) -> None:
    # PR #1044 review 4301898270: the subtype is read before the status,
    # so a limit stop that also carries a 429 is budget_exhausted; a
    # subtype that is not text never decides, so the 429 does.
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", fake={"mode": "budget", "override": override})
    assert caught.value.failure_code.value == code and caught.value.api_status == 429


@pytest.mark.asyncio
async def test_reason_falls_back_to_subtype_when_terminal_reason_is_missing(api, sandbox, call, check_error) -> None:
    # D-10 / §12.3 row 20 _error_text: the reason is terminal_reason,
    # else subtype.
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", fake={"mode": "api_error", "status": 500, "vendor_text": VENDOR, "override": {"subtype": "error_during_execution"}, "drop": ["terminal_reason"]})
    expected = vendor_text(api, "error_during_execution", VENDOR, 500, True)
    check_error(caught.value, harness="claude", verb="run", code="claude.api_error", workspace=sandbox.workspace, vendor=expected, exit_code=1)
    assert caught.value.vendor_message == expected


@pytest.mark.asyncio
async def test_error_object_decides_before_the_exit_status(api, sandbox, call, check_error) -> None:
    # INV-7 steps 6-7 come before step 9: an is_error answer is judged
    # by its own members even when the process exits 0.
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", fake={"mode": "key_rejected", "exit_code": 0})
    check_error(caught.value, harness="claude", verb="run", code="claude.key_rejected", workspace=sandbox.workspace, thread_id=printed_session(sandbox))


@pytest.mark.asyncio
@pytest.mark.parametrize("verb", ["run", "continue"])
async def test_bare_non_zero_exit_is_run_failed_carrying_stderr(api, sandbox, call, check_error, verb) -> None:
    # AC-12 / INV-7 step 9: no JSON on stdout, a non-zero exit and
    # stderr without the not-found marker.
    thread = (await call("claude")).thread_id if verb == "continue" else None
    vendor = "Error: the workspace is not readable"
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", verb, "Again.", thread_id=thread, fake={"mode": "stderr_exit", "vendor_text": vendor, "exit_code": RUN_EXIT})
    check_error(caught.value, harness="claude", verb=verb, code="claude.run_failed", workspace=sandbox.workspace, thread_id=thread, observations=[("exit status", (str(RUN_EXIT),))], vendor=vendor, exit_code=RUN_EXIT)


@pytest.mark.asyncio
@pytest.mark.parametrize("vendor", REFUSED_OPTION_LINES, ids=["unknown-option", "invalid-choice", "missing-argument", "after-a-notice"])
async def test_option_parser_refusal_is_protocol_mismatch_naming_the_tested_version(api, sandbox, call, check_error, vendor) -> None:
    # PR #1044 review 4301626282: 2.1.302 refuses an unknown option or a
    # value outside its choices with exit 1, no stdout and its option
    # parser's error line, so the installed release differs from the
    # tested one; a notice printed before the line does not hide it.
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", fake={"mode": "stderr_exit", "vendor_text": vendor, "exit_code": 1})
    check_error(caught.value, harness="claude", verb="run", code="claude.protocol_mismatch", workspace=sandbox.workspace, thread_id=None, observations=[("tested version", (TESTED_VERSION,))], vendor=vendor, exit_code=1)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["garbage", "array"])
async def test_exit_zero_without_one_json_object_is_protocol_mismatch(api, sandbox, call, check_error, mode) -> None:
    # AC-10 / AC-13 / EC-16: text or a JSON array on stdout; the
    # message names the tested version, and the run reports the id it
    # minted, since it printed none (PR #1044 review).
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", fake={"mode": mode})
    check_error(caught.value, harness="claude", verb="run", code="claude.protocol_mismatch", workspace=sandbox.workspace, thread_id=sandbox.minted_id(), observations=[("tested version", (TESTED_VERSION,))])


@pytest.mark.asyncio
@pytest.mark.parametrize(("case", "override", "drop", "member"), BAD_MEMBERS, ids=[case for case, _, _, _ in BAD_MEMBERS])
async def test_exit_zero_with_a_bad_member_is_protocol_mismatch_naming_it(api, sandbox, call, check_error, case, override, drop, member) -> None:
    # AC-13 / EC-16 / INV-7 step 10 / R-13: is_error not false, a
    # session_id that is not a lowercase UUID, or a result that is not a
    # str; the member and 2.1.302 are named; a valid session_id still
    # becomes thread_id, and a bad one leaves the id the run minted.
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", fake={"mode": "ok", "override": override, "drop": drop})
    session_ok = member != "session_id"
    thread_id = printed_session(sandbox) if session_ok else sandbox.minted_id()
    missing = api.constants.NATIVE_MISSING_MEMBER_SENTENCE.format(member=member)
    check_error(caught.value, harness="claude", verb="run", code="claude.protocol_mismatch", workspace=sandbox.workspace, thread_id=thread_id, observations=[("tested version", (TESTED_VERSION,)), ("bad member", (missing,))])


@pytest.mark.asyncio
async def test_stderr_on_a_successful_answer_is_ignored(sandbox, call, pack) -> None:
    # EC-35: Claude Code prints notices on stderr even when it succeeds.
    result = await call("claude", fake={"stderr_text": "[claude-code:unrecognized_model] the model name is not known to this release"})
    assert result.thread_id == sandbox.answers("claude")[0]["session"]
    assert result.text == f"claude answer to: {pack.PROMPT}"


@pytest.mark.asyncio
async def test_success_reports_its_turns_reason_and_denied_tools_by_name_and_id(api, sandbox, call) -> None:
    # PR #1044 review 4301626286 / 4301898273: a success can hold the tool
    # calls its mode denied (seen on 2.1.302 with exit 0 and subtype
    # success); the result keeps each usable one by tool name and
    # tool-use id, never its input, beside num_turns and terminal_reason.
    result = await call("claude", fake={"override": {"num_turns": 2, "permission_denials": DENIALS}})
    assert isinstance(result, api.ClaudeThreadResult) and isinstance(result, api.NativeThreadResult)
    assert (result.num_turns, result.terminal_reason) == (2, "completed")
    assert result.permission_denials == (api.ClaudePermissionDenial(tool_name="Bash", tool_use_id="toolu_01"),)
    assert "cat .env" not in repr(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(("override", "drop"), UNUSABLE_REPORTS, ids=["wrong-types", "out-of-range", "missing"])
async def test_unusable_or_missing_reports_read_as_defaults_not_protocol_mismatch(sandbox, call, override, drop) -> None:
    # PR #1044 review 4301898273: only is_error, session_id and result are
    # required; num_turns, terminal_reason and permission_denials are
    # reports, so an unusable or missing one reads as 0, None or ().
    result = await call("claude", fake={"override": override, "drop": drop})
    assert (result.num_turns, result.terminal_reason, result.permission_denials) == (0, None, ())


@pytest.mark.asyncio
async def test_failed_fork_reports_the_forks_new_id(api, sandbox, call) -> None:
    # INV-6 / D-14 / EC-34: a fork that fails after Claude Code created
    # the new thread reports that thread, which can be continued.
    first = await call("claude")
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", "fork", "Branch.", thread_id=first.thread_id, fake={"mode": "key_rejected"})
    forked = printed_session(sandbox)
    assert forked != first.thread_id
    assert caught.value.failure_code.value == "claude.key_rejected" and caught.value.thread_id == forked


@pytest.mark.asyncio
async def test_failed_continue_reports_the_callers_id(api, sandbox, call) -> None:
    # INV-6 / §12.3 row 20 step 3: a continue reports the id it sent,
    # even when Claude's failed answer names another valid session.
    first = await call("claude")
    with pytest.raises(api.NativeThreadError) as caught:
        await call("claude", "continue", "Again.", thread_id=first.thread_id, fake={"mode": "api_error", "status": 529, "vendor_text": VENDOR, "override": {"session_id": OTHER_SESSION}})
    assert caught.value.failure_code.value == "claude.api_error" and caught.value.thread_id == first.thread_id
