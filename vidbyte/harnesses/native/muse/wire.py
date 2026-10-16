"""FILE: vidbyte/harnesses/native/muse/wire.py

PURPOSE: Defines the Muse codecs: MuseWire speaks the batch `muse serve` exchange (MSP frames on stdin, the answer to request id 2 on stdout) that checks or forks a thread before exec runs; MuseExecOutput reads the JSON records of one `muse exec --json` run into a NativeThreadResult, or into the NativeThreadError that names what went wrong; MuseSessionWire builds the session/list and session/read parameters of the thread helpers and the evidence read, and reads their answers into NativeThreadSummary records and tool calls.
ROLE IN CODEBASE: Called by MuseThreadRun.execute in vidbyte/harnesses/native/muse/threads.py: MuseWire builds the serve stdin and reads its answer, MuseExecOutput reads the exec outcome. MuseHelperRun (muse/helpers.py) builds its serve batches with MuseWire.batch_frames and the MuseSessionWire params, and reads them with MuseSessionWire. All raise through the call's NativeErrorFactory (hostkit/errors.py).
ARCHITECTURE NOTE: Separate classes because writing the run's MSP batch, reading exec records and reading the helpers' session answers are three jobs (spec D-17). A Session is read strictly as msp.schema.json shapes it: forkedFrom is null or an object carrying sessionId, and a member the record refuses is protocol_mismatch naming the MSP member (spec INV-6). The history of a session/read with items comes in mode inline (history.items), snapshot (history.snapshot.state.items), anchoredSnapshot (items only after a compaction boundary) or none (with noneReason). Pure: no process, no file and no await. Every member name, request id and marker comes from vidbyte/lib/constants/native_threads.py (spec INV-15). The checks run in the INV-6 order: timeout, output cap, then the vendor's own answer.
FUNCTION INVENTORY: MuseWire.new_command_id mints a UUIDv7; batch_frames joins the initialize request, the initialized notification and the session request; session_read_params and session_fork_params build the request parameters; read_answer is the narrated reader of the serve answer; _answer finds the line answering request id 2. MuseExecOutput.read is the narrated reader of exec records, read through CliRunner.json_objects; _session finds the first session stream id; _terminal finds the terminal record's payload. MuseSessionWire.list_params and read_items_params build the request parameters; result reads the answer to request id 2 for one method; sessions and session read Session records into summaries; tool_calls reads the toolCall items of a history, or None after compaction; _summary builds one summary, naming a refused member as MSP spells it.
COMMON MODIFICATION PATTERNS: A new MSP request is one MuseMethod member and one params builder here; a new exec failure text is one more marker in MUSE_KEY_REJECTED_MARKERS or one more check in MuseExecOutput.read.
WHAT NOT TO DO IN THIS FILE: 1. Do not copy vidbyte.__version__ at import time; batch_frames reads it on every call. 2. Do not send a commandId that is not from new_command_id. 3. Do not copy vendor text into an error unscrubbed; pass it as vendor_text and the factory scrubs and caps it.
KNOWN EDGE CASES: -32020 is thread_not_found, -32601 (an older Muse without the method) is protocol_mismatch naming the method, and any other JSON-RPC error is run_failed with Muse's message. History mode none means there are no items to check, so the evidence read fails closed naming noneReason (spec EC-56). `muse exec --session-id <unknown>` silently starts a new thread, so a continue checks the id with session/read first, and an exec whose session stream is not the id it was given is thread_not_found carrying the stream's id. A fork whose serve answer is its source id is protocol_mismatch before exec starts. The session stream id is looked for before the runner checks, so a timed-out or cut run still reports it (spec INV-5). Lines that are not JSON objects are skipped.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_threads.py, tests/features/harness_threads/test_harness_threads_errors.py, tests/features/harness_threads/test_harness_threads_muse_helpers.py, tests/features/harness_threads/test_harness_threads_muse_commands.py
"""

from __future__ import annotations

import json
import secrets
import time
import uuid
from collections.abc import Mapping
from datetime import datetime

import vidbyte
from vidbyte.harnesses.native.hostkit import NativeErrorFactory
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    NativeHelperRequest,
    NativeThreadRequest,
    NativeThreadResult,
    NativeThreadSummary,
    NativeToolCall,
)
from vidbyte.lib.dataclasses.process import CliOutcome
from vidbyte.lib.dataclasses.validation import RecordFieldValidator
from vidbyte.lib.enums.native_threads import (
    MuseMethod,
    NativeHarness,
    NativeThreadProblem,
    NativeThreadVerb,
)
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.process import CliRunner


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
            raise errors.failure(NativeThreadProblem.TIMED_OUT, request=request, outcome=outcome, vendor_text=outcome.stderr, seconds=timeout_seconds)
        if outcome.stdout_truncated:
            raise errors.failure(NativeThreadProblem.OUTPUT_TOO_LARGE, request=request, outcome=outcome, vendor_text=outcome.stderr, cap_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES)

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
        if not isinstance(forked, str) or not RecordFieldValidator.accepts_text(forked, max_chars=native_threads.NATIVE_THREAD_ID_MAX_CHARS, pattern=native_threads.NATIVE_THREAD_ID_PATTERN):
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, outcome=outcome, missing_member=native_threads.MUSE_FORK_SESSION_MEMBER)
        if forked == source:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, thread_id=forked, outcome=outcome, searched=native_threads.NATIVE_FORK_RETURNED_SOURCE_DETAIL)
        return forked

    @staticmethod
    def _answer(stdout: str) -> Mapping[str, object] | None:
        # The JSON object on its own line that answers request id 2.
        answers = (frame for frame in CliRunner.json_objects(stdout) if frame.get(native_threads.JSONRPC_ID_FIELD) == native_threads.MUSE_SESSION_REQUEST_ID)
        return next(answers, None)


class MuseExecOutput:
    """Reads the JSON records of one muse exec --json run."""

    @staticmethod
    def read(outcome: CliOutcome, request: NativeThreadRequest, errors: NativeErrorFactory, *, thread_id: str | None, timeout_seconds: float) -> NativeThreadResult:
        # Read the records and the session stream first, so every
        # failure below carries the newest thread id: the stream's,
        # else the one exec was given (the fork's new id on a fork).
        records = CliRunner.json_objects(outcome.stdout)
        session = MuseExecOutput._session(records)
        known = session if session is not None else thread_id

        # The run passed its time bound, or printed more than the cap:
        # the records cannot be trusted, so the process outcome decides.
        if outcome.timed_out:
            raise errors.failure(NativeThreadProblem.TIMED_OUT, request=request, thread_id=known, outcome=outcome, vendor_text=outcome.stderr, seconds=timeout_seconds)
        if outcome.stdout_truncated:
            raise errors.failure(NativeThreadProblem.OUTPUT_TOO_LARGE, request=request, thread_id=known, outcome=outcome, vendor_text=outcome.stderr, cap_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES)

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
    def _session(records: list[Mapping[str, object]]) -> str | None:
        # The id of the first record on a session stream, when it is a
        # thread id the result record accepts.
        for record in records:
            stream = record.get(native_threads.MUSE_STREAM_FIELD)
            if isinstance(stream, dict) and stream.get(native_threads.MUSE_STREAM_KIND_FIELD) == native_threads.MUSE_SESSION_STREAM_KIND:
                session = stream.get(native_threads.MUSE_STREAM_ID_FIELD)
                usable = isinstance(session, str) and RecordFieldValidator.accepts_text(session, max_chars=native_threads.NATIVE_THREAD_ID_MAX_CHARS, pattern=native_threads.NATIVE_THREAD_ID_PATTERN)
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


class MuseSessionWire:
    """Builds the session/list and session/read parameters of the Muse helpers and reads their answers."""

    @staticmethod
    def list_params(workspace_root: str, limit: int, cutoff: datetime | None) -> dict[str, object]:
        # session/list of the workspace's sessions; updatedAfter only
        # when the call has a window.
        params: dict[str, object] = {native_threads.MUSE_WORKSPACE_ROOT_FIELD: workspace_root, native_threads.MUSE_LIMIT_FIELD: limit}
        if cutoff is not None:
            params[native_threads.MUSE_UPDATED_AFTER_FIELD] = cutoff.isoformat()
        return params

    @staticmethod
    def read_items_params(thread_id: str) -> dict[str, object]:
        # session/read of the thread with its items, for the evidence.
        return {native_threads.MUSE_SESSION_ID_FIELD: thread_id, native_threads.MUSE_EXCLUDE_ITEMS_FIELD: False}

    @staticmethod
    def result(outcome: CliOutcome, request: NativeHelperRequest | NativeThreadRequest, errors: NativeErrorFactory, *, method: MuseMethod, thread_id: str | None = None) -> Mapping[str, object]:
        # The serve exchange passed the control timeout, or printed more
        # than the cap: the answer cannot be trusted.
        if outcome.timed_out:
            raise errors.failure(NativeThreadProblem.TIMED_OUT, request=request, thread_id=thread_id, outcome=outcome, vendor_text=outcome.stderr, seconds=native_threads.NATIVE_CONTROL_TIMEOUT_SECONDS)
        if outcome.stdout_truncated:
            raise errors.failure(NativeThreadProblem.OUTPUT_TOO_LARGE, request=request, thread_id=thread_id, outcome=outcome, vendor_text=outcome.stderr, cap_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES)

        # Muse must have answered the session request.
        answers = [frame for frame in CliRunner.json_objects(outcome.stdout) if frame.get(native_threads.JSONRPC_ID_FIELD) == native_threads.MUSE_SESSION_REQUEST_ID]
        if not answers:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, thread_id=thread_id, outcome=outcome, vendor_text=outcome.stderr)
        answer = answers[0]

        # @intent muse-helper-json-rpc-errors-are-classified
        # -32020 is a thread Muse does not have; -32601 is a Muse too old
        # for the method, which the SDK cannot read around; any other
        # error is a failed request with Muse's own message.
        error = answer.get(native_threads.JSONRPC_ERROR_FIELD)
        if isinstance(error, dict):
            code, message = error.get(native_threads.JSONRPC_CODE_FIELD), error.get(native_threads.JSONRPC_MESSAGE_FIELD)
            vendor = message if isinstance(message, str) else ""
            if code == native_threads.MUSE_SESSION_NOT_FOUND_CODE:
                raise errors.failure(NativeThreadProblem.THREAD_NOT_FOUND, request=request, thread_id=thread_id, outcome=outcome, vendor_text=vendor)
            if code == native_threads.MUSE_METHOD_NOT_FOUND_CODE:
                raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, thread_id=thread_id, outcome=outcome, vendor_text=vendor, searched=native_threads.MUSE_METHOD_NOT_FOUND_DETAIL.format(method=method.value))
            raise errors.failure(NativeThreadProblem.RUN_FAILED, request=request, thread_id=thread_id, outcome=outcome, vendor_text=vendor)

        # A success answer carries one result object.
        result = answer.get(native_threads.JSONRPC_RESULT_FIELD)
        if not isinstance(result, dict):
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, thread_id=thread_id, outcome=outcome, missing_member=native_threads.JSONRPC_RESULT_FIELD)
        return result

    @staticmethod
    def sessions(result: Mapping[str, object], request: NativeHelperRequest, errors: NativeErrorFactory) -> tuple[NativeThreadSummary, ...]:
        # Every Session of a session/list result, read strictly: one bad
        # Session fails the whole list (spec INV-6).
        sessions = result.get(native_threads.MUSE_SESSIONS_FIELD)
        if not isinstance(sessions, list) or not all(isinstance(session, dict) for session in sessions):
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, searched=native_threads.MUSE_MEMBER_DETAIL.format(member=native_threads.MUSE_SESSIONS_FIELD))
        return tuple(MuseSessionWire._summary(session, request, errors) for session in sessions)

    @staticmethod
    def session(result: Mapping[str, object], request: NativeHelperRequest, errors: NativeErrorFactory) -> NativeThreadSummary:
        # The Session of a session/read result.
        session = result.get(native_threads.MUSE_SESSION_FIELD)
        if not isinstance(session, dict):
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, searched=native_threads.MUSE_MEMBER_DETAIL.format(member=native_threads.MUSE_SESSION_FIELD))
        return MuseSessionWire._summary(session, request, errors)

    @staticmethod
    def tool_calls(result: Mapping[str, object], request: NativeThreadRequest, errors: NativeErrorFactory, *, thread_id: str) -> tuple[NativeToolCall, ...] | None:
        # The history comes in one of four modes; only inline and
        # snapshot hold every item of the thread.
        history = result.get(native_threads.MUSE_HISTORY_FIELD)
        mode = history.get(native_threads.MUSE_HISTORY_MODE_FIELD) if isinstance(history, dict) else None
        if not isinstance(history, dict) or mode is None:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, thread_id=thread_id, searched=native_threads.MUSE_MEMBER_DETAIL.format(member=native_threads.MUSE_HISTORY_FIELD))

        # @intent muse-evidence-after-compaction-comes-from-the-export
        # An anchored snapshot starts at a compaction boundary, so the
        # early read_skill call may be gone from it: the caller reads
        # the run's export instead (spec D-33). Mode none has no items
        # at all, so the evidence read fails closed naming the reason.
        if mode == native_threads.MUSE_HISTORY_ANCHORED:
            return None
        if mode == native_threads.MUSE_HISTORY_NONE:
            reason = history.get(native_threads.MUSE_NONE_REASON_FIELD)
            raise errors.failure(NativeThreadProblem.COMMAND_NOT_RUN, request=request, thread_id=thread_id, searched=native_threads.MUSE_HISTORY_NONE_DETAIL.format(reason=reason))
        items: object = None
        if mode == native_threads.MUSE_HISTORY_INLINE:
            items = history.get(native_threads.MUSE_ITEMS_FIELD)
        if mode == native_threads.MUSE_HISTORY_SNAPSHOT:
            snapshot = history.get(native_threads.MUSE_SNAPSHOT_FIELD)
            state = snapshot.get(native_threads.MUSE_STATE_FIELD) if isinstance(snapshot, dict) else None
            items = state.get(native_threads.MUSE_ITEMS_FIELD) if isinstance(state, dict) else None
        if not isinstance(items, list):
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, thread_id=thread_id, searched=native_threads.MUSE_MEMBER_DETAIL.format(member=native_threads.MUSE_ITEMS_FIELD))

        # Every toolCall item with a usable tool name, its args as Muse
        # wrote them; an item without a usable name cannot be evidence.
        calls = []
        for item in items:
            if not isinstance(item, dict) or item.get(native_threads.MUSE_ITEM_KIND_FIELD) != native_threads.MUSE_TOOL_CALL_KIND:
                continue
            tool, args = item.get(native_threads.MUSE_TOOL_FIELD), item.get(native_threads.MUSE_ARGS_FIELD)
            if RecordFieldValidator.accepts_text(tool, max_chars=native_threads.NATIVE_TOOL_NAME_MAX_CHARS):
                calls.append(NativeToolCall(name=str(tool), arguments=args if isinstance(args, str) else json.dumps(args)))
        return tuple(calls)

    @staticmethod
    def _summary(session: Mapping[str, object], request: NativeHelperRequest, errors: NativeErrorFactory) -> NativeThreadSummary:
        # One MSP Session as a summary: forkedFrom is null or an object
        # naming the source; Muse keeps no title. A member the record
        # refuses is named as MSP spells it.
        forked = session.get(native_threads.MUSE_FORKED_FROM_FIELD)
        if forked is not None and not isinstance(forked, dict):
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, searched=native_threads.MUSE_MEMBER_DETAIL.format(member=native_threads.MUSE_FORKED_FROM_FIELD))
        try:
            return NativeThreadSummary(
                harness=NativeHarness.MUSE,
                thread_id=session.get(native_threads.MUSE_SESSION_ID_FIELD),
                title=None,
                created_at=session.get(native_threads.MUSE_CREATED_AT_FIELD),
                updated_at=session.get(native_threads.MUSE_UPDATED_AT_FIELD),
                parent_thread_id=None if forked is None else forked.get(native_threads.MUSE_SESSION_ID_FIELD),
                model=session.get(native_threads.MUSE_MODEL_ID_FIELD),
            )
        except ConfigurationError as exc:
            field = str(exc.details.get(native_threads.NATIVE_FIELD_DETAIL_KEY, ""))
            member = native_threads.MUSE_SESSION_MEMBERS.get(field, field)
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, searched=native_threads.MUSE_MEMBER_DETAIL.format(member=member)) from exc


__all__ = ["MuseExecOutput", "MuseSessionWire", "MuseWire"]
