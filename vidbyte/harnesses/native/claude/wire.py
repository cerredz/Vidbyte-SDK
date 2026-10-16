"""FILE: vidbyte/harnesses/native/claude/wire.py

PURPOSE: Defines ClaudeWire, the reader of one `claude --print --output-format json` run: it turns the run's CliOutcome into a NativeThreadResult, or into the NativeThreadError that names what went wrong.
ROLE IN CODEBASE: Called by ClaudeThreadRun.execute in vidbyte/harnesses/native/claude/threads.py after CliRunner returns; it raises through the call's NativeErrorFactory (hostkit/errors.py) and checks the answered thread id with RecordFieldValidator.accepts_text.
ARCHITECTURE NOTE: Pure: no process, no file and no await. Claude Code 2.1.301 writes one JSON object at exit, {"is_error", "session_id", "result", "api_error_status", "terminal_reason", "subtype", "errors", ...}, on success and on an in-run failure alike, and a failure before the run (an unknown --resume id) as text on stderr with exit 1. Every member name and marker comes from vidbyte/lib/constants/native_threads.py (spec INV-16). The checks run in the INV-7 order: timeout, output cap, the answer's own is_error (key rejected or run failed), a bare non-zero exit (thread not found or run failed), then the shape of the success answer and the thread id.
FUNCTION INVENTORY: read is the narrated main function; _answer parses stdout as one JSON object, or None; _session returns the answer's session_id when it is a lowercase UUID; _text returns its result when it is text; _missing_member names the member that makes a success answer unusable; _error_text builds the vendor text of an is_error answer.
COMMON MODIFICATION PATTERNS: A new answer member the SDK must read gets its name constant and one check in read; a new failure shape is a spec change first (INV-7).
WHAT NOT TO DO IN THIS FILE: 1. Do not decide success by subtype; Claude Code reports "success" on a rejected key. 2. Do not copy vendor text into an error unscrubbed; pass it as vendor_text and the factory scrubs and caps it. 3. Do not accept a cut stdout; a truncated answer is output_too_large, never parsed. 4. Do not start processes or await anything here.
KNOWN EDGE CASES: True counts as an int status, so "api_error_status": true is run_failed with the status shown, never key_rejected. A failed run or fork still reports the session_id of its answer, because Claude Code writes a resumable transcript even then; a failed continue reports the caller's id. A continue answered on another lowercase UUID is thread_not_found; one answered in upper case is a bad session_id, protocol_mismatch. A fork answered with its source id is protocol_mismatch. Stderr on a successful answer is ignored, because Claude Code prints notices there.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_claude_errors.py, tests/features/harness_threads/test_harness_threads_claude_threads.py, tests/features/harness_threads/test_harness_threads_claude_process_bounds.py
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from vidbyte.harnesses.native.hostkit import NativeErrorFactory
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    NativeThreadRequest,
    NativeThreadResult,
)
from vidbyte.lib.dataclasses.process import CliOutcome
from vidbyte.lib.dataclasses.validation import RecordFieldValidator
from vidbyte.lib.enums.native_threads import (
    NativeHarness,
    NativeThreadProblem,
    NativeThreadVerb,
)


class ClaudeWire:
    """Reads the one JSON answer of a headless claude run."""

    @staticmethod
    def read(outcome: CliOutcome, request: NativeThreadRequest, errors: NativeErrorFactory, *, timeout_seconds: float) -> NativeThreadResult:
        # The run passed its time bound, or printed more than the cap:
        # the answer cannot be trusted, so the process outcome decides.
        if outcome.timed_out:
            raise errors.failure(NativeThreadProblem.TIMED_OUT, request=request, outcome=outcome, vendor_text=outcome.stderr, seconds=timeout_seconds)
        if outcome.stdout_truncated:
            raise errors.failure(NativeThreadProblem.OUTPUT_TOO_LARGE, request=request, outcome=outcome, cap_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES)

        # Read the answer once. A failed run or fork still names the
        # thread Claude Code created, so that id is reported; a continue
        # always reports the id the caller gave.
        answer = ClaudeWire._answer(outcome.stdout)
        session = ClaudeWire._session(answer)
        text = ClaudeWire._text(answer)
        newest = request.thread_id if request.verb is NativeThreadVerb.CONTINUE else session

        # Claude Code's own error answer: a 401 or 403 from the API
        # means the key was refused, anything else is a failed run.
        if answer is not None and answer.get(native_threads.CLAUDE_IS_ERROR_FIELD) is True:
            status = answer.get(native_threads.CLAUDE_API_ERROR_STATUS_FIELD)
            rejected = isinstance(status, int) and status in native_threads.CLAUDE_KEY_REJECTED_STATUSES
            problem = NativeThreadProblem.KEY_REJECTED if rejected else NativeThreadProblem.RUN_FAILED
            raise errors.failure(problem, request=request, thread_id=newest, outcome=outcome, vendor_text=ClaudeWire._error_text(answer))

        # A non-zero exit without an error answer: Claude Code's own
        # not-found text means the thread is unknown here; anything
        # else is a failed run, reported with what it wrote to stderr.
        if outcome.exit_code != native_threads.NATIVE_SUCCESS_EXIT_CODE:
            not_found = native_threads.CLAUDE_SESSION_NOT_FOUND_MARKER in outcome.stderr
            problem = NativeThreadProblem.THREAD_NOT_FOUND if not_found else NativeThreadProblem.RUN_FAILED
            raise errors.failure(problem, request=request, thread_id=newest, outcome=outcome, vendor_text=outcome.stderr)

        # Exit 0: the answer must be one object that says it did not
        # fail, with a lowercase UUID session_id and a text result.
        if answer is None:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, thread_id=newest, outcome=outcome)
        if answer.get(native_threads.CLAUDE_IS_ERROR_FIELD) is not False or session is None or text is None:
            missing = ClaudeWire._missing_member(answer, session, text)
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, thread_id=newest, outcome=outcome, missing_member=missing)

        # A continue must answer on the thread it was given; a fork must
        # answer on a new one.
        wrong = NativeErrorFactory.wrong_thread(request, session)
        if wrong is not None:
            detail = native_threads.NATIVE_WRONG_THREAD_DETAILS[wrong].format(answered=session, requested=request.thread_id)
            raise errors.failure(wrong, request=request, thread_id=newest, outcome=outcome, searched=detail)

        # Return the caller's own id on a continue, the new one
        # otherwise, with the text cut at the result cap.
        thread_id = request.thread_id if request.verb is NativeThreadVerb.CONTINUE and request.thread_id is not None else session
        cap = native_threads.NATIVE_RESULT_TEXT_MAX_CHARS
        return NativeThreadResult(harness=NativeHarness.CLAUDE, thread_id=thread_id, text=text[:cap], text_truncated=len(text) > cap)

    @staticmethod
    def _answer(stdout: str) -> Mapping[str, object] | None:
        # The whole stdout as one JSON object, or None when it is not
        # one.
        try:
            value = json.loads(stdout)
        except ValueError:
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _session(answer: Mapping[str, object] | None) -> str | None:
        # The session_id member when it is a lowercase UUID, the only
        # id --resume can never mistake for a title or a path.
        session = None if answer is None else answer.get(native_threads.CLAUDE_SESSION_FIELD)
        if isinstance(session, str) and RecordFieldValidator.accepts_text(session, max_chars=native_threads.NATIVE_THREAD_ID_MAX_CHARS, pattern=native_threads.CLAUDE_THREAD_ID_PATTERN):
            return session
        return None

    @staticmethod
    def _text(answer: Mapping[str, object] | None) -> str | None:
        # The result member when it is text.
        text = None if answer is None else answer.get(native_threads.CLAUDE_RESULT_FIELD)
        return text if isinstance(text, str) else None

    @staticmethod
    def _missing_member(answer: Mapping[str, object], session: str | None, text: str | None) -> str:
        # The first unusable member of a success answer, in the order
        # is_error, session_id, result; read calls this only when one
        # of them is unusable, so the result is the one left when the
        # other two are usable.
        if answer.get(native_threads.CLAUDE_IS_ERROR_FIELD) is not False:
            return native_threads.CLAUDE_IS_ERROR_FIELD
        if session is None:
            return native_threads.CLAUDE_SESSION_FIELD
        return native_threads.CLAUDE_RESULT_FIELD

    @staticmethod
    def _error_text(answer: Mapping[str, object]) -> str | None:
        # Claude Code's words for a failed run: its terminal reason
        # (else its subtype), its API status when that is a number, and
        # its result text (else its errors list); None when it gave
        # neither a reason nor a message.
        terminal = answer.get(native_threads.CLAUDE_TERMINAL_REASON_FIELD)
        subtype = answer.get(native_threads.CLAUDE_SUBTYPE_FIELD)
        result = answer.get(native_threads.CLAUDE_RESULT_FIELD)
        listed = answer.get(native_threads.CLAUDE_ERRORS_FIELD)
        status = answer.get(native_threads.CLAUDE_API_ERROR_STATUS_FIELD)
        reason = terminal if isinstance(terminal, str) else subtype if isinstance(subtype, str) else None
        message = result if isinstance(result, str) else NativeErrorFactory.listing(listed) if isinstance(listed, list) else None
        if reason is None and message is None:
            return None
        if isinstance(status, int):
            return native_threads.CLAUDE_ERROR_STATUS_TEXT.format(reason=reason or "", status=status, message=message or "")
        return native_threads.CLAUDE_ERROR_TEXT.format(reason=reason or "", message=message or "")


__all__ = ["ClaudeWire"]
