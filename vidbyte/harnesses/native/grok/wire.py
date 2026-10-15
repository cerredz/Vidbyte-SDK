"""FILE: vidbyte/harnesses/native/grok/wire.py

PURPOSE: Defines GrokWire, the reader of one `grok --single --output-format=json` run: it turns the run's CliOutcome into a NativeThreadResult, or into the NativeThreadError that names what went wrong.
ROLE IN CODEBASE: Called by GrokThreadRun.execute in vidbyte/harnesses/native/grok/threads.py after CliRunner returns; it raises through the call's NativeErrorFactory (hostkit/errors.py).
ARCHITECTURE NOTE: Pure: no process, no file and no await. Grok writes one JSON object at exit: on success {"text", "sessionId", ...}, on failure {"type": "error", "message"} with a non-zero exit. Every member name and marker comes from vidbyte/lib/constants/native_threads.py (spec INV-15). The checks run in the INV-6 order: timeout, output cap, the vendor's error object (key rejected or run failed), a bare non-zero exit, then the shape of the success answer and the thread id.
FUNCTION INVENTORY: read is the narrated main function; _answer parses stdout as one JSON object, or None.
COMMON MODIFICATION PATTERNS: A new sign-in failure text from grok is one more marker in GROK_NOT_SIGNED_IN_MARKERS; a new answer member the SDK must read gets its name constant and one check in read.
WHAT NOT TO DO IN THIS FILE: 1. Do not copy vendor text into an error unscrubbed; pass it as vendor_text and the factory scrubs and caps it. 2. Do not accept a cut stdout; a truncated answer is output_too_large, never parsed. 3. Do not start processes or await anything here.
KNOWN EDGE CASES: A continue is matched case-insensitively and returns the id the caller gave. A fork whose answer is its source thread is protocol_mismatch, because grok then continued the source instead of copying it. A thread id that the result record would refuse is protocol_mismatch, not an argument error. A timed-out run carries no new thread id, because grok prints it only at exit.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_errors.py, tests/features/harness_threads/test_harness_threads_threads.py
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


class GrokWire:
    """Reads the one JSON answer of a headless grok run."""

    @staticmethod
    def read(outcome: CliOutcome, request: NativeThreadRequest, errors: NativeErrorFactory, *, timeout_seconds: float) -> NativeThreadResult:
        # The run passed its time bound, or printed more than the cap:
        # the answer cannot be trusted, so the process outcome decides.
        if outcome.timed_out:
            raise errors.failure(NativeThreadProblem.TIMED_OUT, request=request, outcome=outcome, vendor_text=outcome.stderr, seconds=timeout_seconds)
        if outcome.stdout_truncated:
            raise errors.failure(NativeThreadProblem.OUTPUT_TOO_LARGE, request=request, outcome=outcome, vendor_text=outcome.stderr, cap_bytes=native_threads.GROK_CLI_MAX_OUTPUT_BYTES)

        # Grok's own error object: a sign-in failure means the key was
        # refused, anything else is a failed run.
        answer = GrokWire._answer(outcome.stdout)
        if answer is not None and answer.get(native_threads.GROK_TYPE_FIELD) == native_threads.GROK_ERROR_TYPE:
            message = str(answer.get(native_threads.GROK_MESSAGE_FIELD, ""))
            refused = any(marker in message.casefold() for marker in native_threads.GROK_NOT_SIGNED_IN_MARKERS)
            problem = NativeThreadProblem.KEY_REJECTED if refused else NativeThreadProblem.RUN_FAILED
            raise errors.failure(problem, request=request, outcome=outcome, vendor_text=message)

        # A non-zero exit without an error object: report what grok
        # wrote to stderr.
        if outcome.exit_code != native_threads.NATIVE_SUCCESS_EXIT_CODE:
            raise errors.failure(NativeThreadProblem.RUN_FAILED, request=request, outcome=outcome, vendor_text=outcome.stderr)

        # Exit 0: the answer must be one object with a usable thread id
        # and a text.
        if answer is None:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, outcome=outcome)
        session = answer.get(native_threads.GROK_SESSION_FIELD)
        if not isinstance(session, str) or not RecordFieldValidator.accepts_text(session, max_chars=native_threads.NATIVE_THREAD_ID_MAX_CHARS, pattern=native_threads.NATIVE_THREAD_ID_PATTERN):
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, outcome=outcome, missing_member=native_threads.GROK_SESSION_FIELD)
        text = answer.get(native_threads.GROK_TEXT_FIELD)
        if not isinstance(text, str):
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, thread_id=session, outcome=outcome, missing_member=native_threads.GROK_TEXT_FIELD)

        # A continue must answer on the thread it was given; a fork must
        # answer on a new one.
        wrong = NativeErrorFactory.wrong_thread(request, session)
        if wrong is not None:
            detail = native_threads.NATIVE_WRONG_THREAD_DETAILS[wrong].format(answered=session, requested=request.thread_id)
            raise errors.failure(wrong, request=request, thread_id=session, outcome=outcome, searched=detail)

        # Return the caller's own id on a continue, the new one
        # otherwise, with the text cut at the result cap.
        thread_id = request.thread_id if request.verb is NativeThreadVerb.CONTINUE and request.thread_id is not None else session
        cap = native_threads.NATIVE_RESULT_TEXT_MAX_CHARS
        return NativeThreadResult(harness=NativeHarness.GROK, thread_id=thread_id, text=text[:cap], text_truncated=len(text) > cap)

    @staticmethod
    def _answer(stdout: str) -> Mapping[str, object] | None:
        # The whole stdout as one JSON object, or None when it is not one.
        try:
            value = json.loads(stdout)
        except ValueError:
            return None
        return value if isinstance(value, dict) else None


__all__ = ["GrokWire"]
