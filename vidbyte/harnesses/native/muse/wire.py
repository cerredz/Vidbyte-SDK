"""FILE: vidbyte/harnesses/native/muse/wire.py

PURPOSE: Defines the two Muse codecs of one call: MuseWire speaks the batch `muse serve` exchange (MSP frames on stdin, the answer to request id 2 on stdout) that checks or forks a thread before exec runs, and MuseExecOutput reads the JSON records of one `muse exec --json` run into a NativeThreadResult, or into the NativeThreadError that names what went wrong.
ROLE IN CODEBASE: Called by MuseThreadRun.execute in vidbyte/harnesses/native/muse/threads.py: MuseWire builds the serve stdin and reads its answer, MuseExecOutput reads the exec outcome. Both raise through the call's NativeErrorFactory (hostkit/errors.py).
ARCHITECTURE NOTE: Two classes because writing an MSP batch and reading exec records are two jobs (spec D-17). Pure: no process, no file and no await. Every member name, request id and marker comes from vidbyte/lib/constants/native_threads.py (spec INV-15). The checks run in the INV-6 order: timeout, output cap, then the vendor's own answer.
FUNCTION INVENTORY: MuseWire.new_command_id mints a UUIDv7; batch_frames joins the initialize request, the initialized notification and the session request; session_read_params and session_fork_params build the request parameters; read_answer is the narrated reader of the serve answer; _answer finds the line answering request id 2. MuseExecOutput.read is the narrated reader of exec records; _records parses the JSON lines; _session finds the first session stream id; _terminal finds the terminal record's payload.
COMMON MODIFICATION PATTERNS: A new MSP request is one MuseMethod member and one params builder here; a new exec failure text is one more marker in MUSE_KEY_REJECTED_MARKERS or one more check in MuseExecOutput.read.
WHAT NOT TO DO IN THIS FILE: 1. Do not copy vidbyte.__version__ at import time; batch_frames reads it on every call. 2. Do not send a commandId that is not from new_command_id. 3. Do not copy vendor text into an error unscrubbed; pass it as vendor_text and the factory scrubs and caps it.
KNOWN EDGE CASES: `muse exec --session-id <unknown>` silently starts a new thread, so a continue checks the id with session/read first, and an exec whose session stream is not the id it was given is thread_not_found carrying the stream's id. A fork whose serve answer is its source id is protocol_mismatch before exec starts. The session stream id is looked for before the runner checks, so a timed-out or cut run still reports it (spec INV-5). Lines that are not JSON objects are skipped.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_threads.py, tests/features/harness_threads/test_harness_threads_errors.py
"""

from __future__ import annotations

import json
import re
import secrets
import time
import uuid
from collections.abc import Mapping

import vidbyte
from vidbyte.harnesses.native.hostkit import NativeErrorFactory
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    NativeThreadRequest,
    NativeThreadResult,
)
from vidbyte.lib.dataclasses.process import CliOutcome
from vidbyte.lib.enums.native_threads import (
    MuseMethod,
    NativeHarness,
    NativeThreadProblem,
    NativeThreadVerb,
)


class MuseWire:
    """Writes the batch muse serve frames and reads the answer to the session request."""

    @staticmethod
    def new_command_id() -> str:
        # An RFC 9562 UUIDv7: 48-bit unix_ts_ms, version 7, 12 bits
        # rand_a, variant 0b10, 62 bits rand_b, all 74 random bits from
        # one call.
        random_bits = secrets.randbits(native_threads.MUSE_UUID_RANDOM_BITS)
        unix_ts_ms = int(time.time() * native_threads.MUSE_MILLISECONDS_PER_SECOND)
        value = (
            ((unix_ts_ms & native_threads.MUSE_UUID_TIMESTAMP_MASK) << native_threads.MUSE_UUID_TIMESTAMP_SHIFT)
            | (native_threads.MUSE_UUID_VERSION << native_threads.MUSE_UUID_VERSION_SHIFT)
            | ((random_bits >> native_threads.MUSE_UUID_RAND_B_BITS) << native_threads.MUSE_UUID_RAND_A_SHIFT)
            | (native_threads.MUSE_UUID_VARIANT << native_threads.MUSE_UUID_VARIANT_SHIFT)
            | (random_bits & native_threads.MUSE_UUID_RAND_B_MASK)
        )
        return str(uuid.UUID(int=value))

    @staticmethod
    def batch_frames(method: MuseMethod, params: Mapping[str, object]) -> str:
        # The whole serve conversation, one JSON frame per line:
        # initialize (id 1) with the SDK's name and version, the
        # initialized notification, then the session request (id 2).
        client = {native_threads.MUSE_CLIENT_NAME_FIELD: native_threads.MUSE_CLIENT_NAME, native_threads.MUSE_CLIENT_VERSION_FIELD: vidbyte.__version__}
        frames = [
            {
                native_threads.JSONRPC_VERSION_FIELD: native_threads.JSONRPC_VERSION,
                native_threads.JSONRPC_ID_FIELD: native_threads.MUSE_INITIALIZE_REQUEST_ID,
                native_threads.JSONRPC_METHOD_FIELD: MuseMethod.INITIALIZE.value,
                native_threads.JSONRPC_PARAMS_FIELD: {native_threads.MUSE_CLIENT_INFO_FIELD: client},
            },
            {native_threads.JSONRPC_VERSION_FIELD: native_threads.JSONRPC_VERSION, native_threads.JSONRPC_METHOD_FIELD: MuseMethod.INITIALIZED.value},
            {
                native_threads.JSONRPC_VERSION_FIELD: native_threads.JSONRPC_VERSION,
                native_threads.JSONRPC_ID_FIELD: native_threads.MUSE_SESSION_REQUEST_ID,
                native_threads.JSONRPC_METHOD_FIELD: method.value,
                native_threads.JSONRPC_PARAMS_FIELD: dict(params),
            },
        ]
        return "".join(json.dumps(frame) + native_threads.NATIVE_LINE_SEPARATOR for frame in frames)

    @staticmethod
    def session_read_params(thread_id: str) -> dict[str, object]:
        # session/read of the thread's header only.
        return {native_threads.MUSE_SESSION_ID_FIELD: thread_id, native_threads.MUSE_EXCLUDE_ITEMS_FIELD: True}

    @staticmethod
    def session_fork_params(thread_id: str) -> dict[str, object]:
        # session/fork of the thread, with a fresh command id.
        return {native_threads.MUSE_COMMAND_ID_FIELD: MuseWire.new_command_id(), native_threads.MUSE_SESSION_ID_FIELD: thread_id, native_threads.MUSE_EXCLUDE_ITEMS_FIELD: True}

    @staticmethod
    def read_answer(outcome: CliOutcome, request: NativeThreadRequest, errors: NativeErrorFactory, *, timeout_seconds: float) -> str:
        # The serve exchange passed the control timeout, or printed more
        # than the cap: the answer cannot be trusted.
        if outcome.timed_out:
            raise errors.failure(NativeThreadProblem.TIMED_OUT, request=request, outcome=outcome, seconds=timeout_seconds)
        if outcome.stdout_truncated:
            raise errors.failure(NativeThreadProblem.OUTPUT_TOO_LARGE, request=request, outcome=outcome, cap_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES)

        # Muse must have answered the session request.
        answer = MuseWire._answer(outcome.stdout)
        if answer is None:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, outcome=outcome, vendor_text=outcome.stderr)

        # An error answer: -32020 means Muse has no such thread, any
        # other code is a failed request.
        error = answer.get(native_threads.JSONRPC_ERROR_FIELD)
        if isinstance(error, dict):
            message = error.get(native_threads.JSONRPC_MESSAGE_FIELD)
            problem = NativeThreadProblem.THREAD_NOT_FOUND if error.get(native_threads.JSONRPC_CODE_FIELD) == native_threads.MUSE_SESSION_NOT_FOUND_CODE else NativeThreadProblem.RUN_FAILED
            raise errors.failure(problem, request=request, outcome=outcome, vendor_text=message if isinstance(message, str) else "")

        # A continue runs exec on the thread session/read found.
        source = request.thread_id or ""
        if request.verb is not NativeThreadVerb.FORK:
            return source

        # A fork runs exec on the new thread session/fork answered,
        # which must be a usable id other than the source.
        result = answer.get(native_threads.JSONRPC_RESULT_FIELD)
        session = result.get(native_threads.MUSE_SESSION_FIELD) if isinstance(result, dict) else None
        forked = session.get(native_threads.MUSE_SESSION_ID_FIELD) if isinstance(session, dict) else None
        if not isinstance(forked, str) or len(forked) > native_threads.NATIVE_THREAD_ID_MAX_CHARS or re.fullmatch(native_threads.NATIVE_THREAD_ID_PATTERN, forked) is None:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, outcome=outcome, missing_member=native_threads.MUSE_FORK_SESSION_MEMBER)
        if forked == source:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, thread_id=forked, outcome=outcome, searched=native_threads.NATIVE_FORK_RETURNED_SOURCE_DETAIL)
        return forked

    @staticmethod
    def _answer(stdout: str) -> Mapping[str, object] | None:
        # The JSON object on its own line that answers request id 2.
        for line in stdout.splitlines():
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict) and value.get(native_threads.JSONRPC_ID_FIELD) == native_threads.MUSE_SESSION_REQUEST_ID:
                return value
        return None


class MuseExecOutput:
    """Reads the JSON records of one muse exec --json run."""

    @staticmethod
    def read(outcome: CliOutcome, request: NativeThreadRequest, errors: NativeErrorFactory, *, thread_id: str | None, timeout_seconds: float) -> NativeThreadResult:
        # Read the records and the session stream first, so every
        # failure below carries the newest thread id: the stream's,
        # else the one exec was given (the fork's new id on a fork).
        records = MuseExecOutput._records(outcome.stdout)
        session = MuseExecOutput._session(records)
        known = session if session is not None else thread_id

        # The run passed its time bound, or printed more than the cap:
        # the records cannot be trusted, so the process outcome decides.
        if outcome.timed_out:
            raise errors.failure(NativeThreadProblem.TIMED_OUT, request=request, thread_id=known, outcome=outcome, seconds=timeout_seconds)
        if outcome.stdout_truncated:
            raise errors.failure(NativeThreadProblem.OUTPUT_TOO_LARGE, request=request, thread_id=known, outcome=outcome, cap_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES)

        # Muse says on stderr when the provider refused the key.
        if any(marker in outcome.stderr.casefold() for marker in native_threads.MUSE_KEY_REJECTED_MARKERS):
            raise errors.failure(NativeThreadProblem.KEY_REJECTED, request=request, thread_id=known, outcome=outcome, vendor_text=outcome.stderr)

        # exec must answer on the thread it was given; Muse silently
        # starts a new one for an id it does not know.
        if thread_id is not None and session is not None and session != thread_id:
            detail = native_threads.NATIVE_OTHER_THREAD_DETAIL.format(answered=session, requested=thread_id)
            raise errors.failure(NativeThreadProblem.THREAD_NOT_FOUND, request=request, thread_id=session, outcome=outcome, searched=detail)

        # The terminal record decides the run: without one, a non-zero
        # exit is a failed run and exit 0 is unreadable output.
        terminal = MuseExecOutput._terminal(records)
        if terminal is None and outcome.exit_code != native_threads.NATIVE_SUCCESS_EXIT_CODE:
            raise errors.failure(NativeThreadProblem.RUN_FAILED, request=request, thread_id=known, outcome=outcome, vendor_text=outcome.stderr)
        if terminal is None:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, thread_id=known, outcome=outcome, missing_member=native_threads.MUSE_TERMINAL_RECORD_MEMBER)
        if terminal.get(native_threads.MUSE_TERMINAL_FIELD) != native_threads.MUSE_COMPLETED_TERMINAL:
            reason = terminal.get(native_threads.MUSE_REASON_FIELD)
            raise errors.failure(NativeThreadProblem.RUN_FAILED, request=request, thread_id=known, outcome=outcome, vendor_text=reason if isinstance(reason, str) else outcome.stderr)

        # A completed run must name its session and carry a text.
        if session is None:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, thread_id=known, outcome=outcome, missing_member=native_threads.MUSE_SESSION_STREAM_MEMBER)
        text = terminal.get(native_threads.MUSE_TEXT_FIELD)
        if not isinstance(text, str):
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, thread_id=session, outcome=outcome, missing_member=native_threads.MUSE_TEXT_FIELD)

        # Return the session the run answered on, with the text cut at
        # the result cap.
        cap = native_threads.NATIVE_RESULT_TEXT_MAX_CHARS
        return NativeThreadResult(harness=NativeHarness.MUSE, thread_id=session, text=text[:cap], text_truncated=len(text) > cap)

    @staticmethod
    def _records(stdout: str) -> list[Mapping[str, object]]:
        # Every stdout line that is one JSON object; banner lines and
        # cut lines are skipped.
        records: list[Mapping[str, object]] = []
        for line in stdout.splitlines():
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                records.append(value)
        return records

    @staticmethod
    def _session(records: list[Mapping[str, object]]) -> str | None:
        # The id of the first record on a session stream, when it is a
        # thread id the result record accepts.
        for record in records:
            stream = record.get(native_threads.MUSE_STREAM_FIELD)
            if isinstance(stream, dict) and stream.get(native_threads.MUSE_STREAM_KIND_FIELD) == native_threads.MUSE_SESSION_STREAM_KIND:
                session = stream.get(native_threads.MUSE_STREAM_ID_FIELD)
                usable = isinstance(session, str) and len(session) <= native_threads.NATIVE_THREAD_ID_MAX_CHARS and re.fullmatch(native_threads.NATIVE_THREAD_ID_PATTERN, session) is not None
                return session if usable else None
        return None

    @staticmethod
    def _terminal(records: list[Mapping[str, object]]) -> Mapping[str, object] | None:
        # The payload of the first run.terminal.* record.
        for record in records:
            payload_type, payload = record.get(native_threads.MUSE_PAYLOAD_TYPE_FIELD), record.get(native_threads.MUSE_PAYLOAD_FIELD)
            if isinstance(payload_type, str) and payload_type.startswith(native_threads.MUSE_TERMINAL_PREFIX):
                return payload if isinstance(payload, dict) else {}
        return None


__all__ = ["MuseExecOutput", "MuseWire"]
