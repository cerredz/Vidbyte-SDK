"""FILE: vidbyte/harnesses/native/opencode/wire.py

PURPOSE: Defines OpencodeWire, the codec of one `opencode run --format=json` call: it builds the inline config that binds the caller's key to the provider its model names, and turns the run's CliOutcome into a NativeThreadResult, or into the NativeThreadError that names what went wrong. Also defines OpencodeHelperWire, the reader of the thread helpers' children: `session list` rows, `opencode db` session rows, an `export` document and a `session delete` answer.
ROLE IN CODEBASE: OpencodeWire is called by OpencodeThreadRun.execute in vidbyte/harnesses/native/opencode/threads.py (also for the command functions of opencode/commands.py): config_content before the run, read after CliRunner returns. OpencodeHelperWire is called by OpencodeHelperRun (opencode/helpers.py) after each helper child. Both raise through the call's NativeErrorFactory (hostkit/errors.py).
ARCHITECTURE NOTE: Pure: no process, no file and no await. opencode prints one JSON event per line, each with "type" and "sessionID"; "text" events carry part.text and part.messageID, "error" events carry error.name and error.data.message/statusCode; an unknown session is "Session not found" on stderr with exit 1. Every member name and marker comes from vidbyte/lib/constants/native_threads.py (spec INV-15). The checks run in the INV-6 order: timeout, output cap, a refused key, an unknown command (only when the run named one, spec D-8), an unknown session, a failed run, then the shape of the answer and the thread id. `session list` and `opencode db` print one JSON array of row objects; times are epoch milliseconds, read by one converter that refuses a bool (lint C002).
FUNCTION INVENTORY: OpencodeWire.config_content builds the OPENCODE_CONFIG_CONTENT value; read is the narrated main function, reading the JSON lines through CliRunner.json_objects; _session finds the first usable sessionID; _error classifies the first error event and builds its vendor text; _text joins the text parts of the last message. OpencodeHelperWire.sessions reads `session list` rows with their directories; rows reads the `opencode db` rows of one id; document returns an export whole; deleted accepts a delete; _checked holds the timeout, cap, not-found and exit checks every helper child shares; _array parses one JSON array of objects; _epoch converts epoch milliseconds to UTC; _summary builds one record, naming a refused member as opencode spells it.
COMMON MODIFICATION PATTERNS: A new key-refusal signal from opencode is one more name in OPENCODE_KEY_REJECTED_ERROR_NAMES or status in OPENCODE_KEY_REJECTED_STATUSES; a new config member is one more key in config_content; a new session row member is one name constant and one read in sessions or rows.
WHAT NOT TO DO IN THIS FILE: 1. Do not return the config value anywhere but the child's environment; it holds the key, and the caller registers it as a secret. 2. Do not copy vendor text into an error unscrubbed; pass it as vendor_text and the factory scrubs and caps it. 3. Do not start processes or await anything here.
KNOWN EDGE CASES: The thread id is looked for before the runner checks, so a timed-out or cut stream still reports the session opencode printed (spec INV-5). Lines that are not JSON objects, such as plugin log lines, are skipped. The answer text is only the last message's text parts, so earlier narration ("Let me look at the files first.") is left out; a run whose last message has no text returns "". A continue is matched case-insensitively and returns the id the caller gave; a fork whose answer is its source is protocol_mismatch. An empty `session list` prints nothing or [], both no threads. A list exactly NATIVE_OPENCODE_SCAN_MAX rows long may be cut and is protocol_mismatch (spec EC-75). A blank title reads as no title.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_errors.py, tests/features/harness_threads/test_harness_threads_threads.py, tests/features/harness_threads/test_harness_threads_acceptance.py, tests/features/harness_threads/test_harness_threads_opencode_helpers.py, tests/features/harness_threads/test_harness_threads_opencode_commands.py
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone

from vidbyte.harnesses.native.hostkit import NativeErrorFactory
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    NativeHelperRequest,
    NativeThreadRequest,
    NativeThreadResult,
    NativeThreadSummary,
)
from vidbyte.lib.dataclasses.process import CliOutcome
from vidbyte.lib.dataclasses.validation import RecordFieldValidator
from vidbyte.lib.enums.native_threads import (
    NativeHarness,
    NativeThreadProblem,
    NativeThreadVerb,
    OpencodeEventType,
)
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.process import CliRunner


class OpencodeWire:
    """Builds the inline opencode config and reads the JSON events of one headless opencode run."""

    @staticmethod
    def config_content(request: NativeThreadRequest) -> str:
        # @intent opencode-config-binds-the-key-to-the-models-provider
        # The key is bound to the provider before the slash in model,
        # because inline config beats a stored auth.json login; the
        # skills member appears only when the caller passed skills.
        provider, _slash, _model = (request.model or "").partition(native_threads.OPENCODE_MODEL_PROVIDER_SEPARATOR)
        options = {native_threads.OPENCODE_CONFIG_KEY_FIELD: request.api_key}
        config: dict[str, object] = {native_threads.OPENCODE_CONFIG_PROVIDER_FIELD: {provider: {native_threads.OPENCODE_CONFIG_OPTIONS_FIELD: options}}}
        if request.skills:
            config[native_threads.OPENCODE_CONFIG_SKILLS_FIELD] = {native_threads.OPENCODE_CONFIG_PATHS_FIELD: [str(skill) for skill in request.skills]}
        return json.dumps(config)

    @staticmethod
    def read(outcome: CliOutcome, request: NativeThreadRequest, errors: NativeErrorFactory, *, timeout_seconds: float) -> NativeThreadResult:
        # Read the events and the session they name first, so every
        # failure below carries the thread opencode already created.
        events = CliRunner.json_objects(outcome.stdout)
        session = OpencodeWire._session(events)

        # The run passed its time bound, or printed more than the cap:
        # the stream cannot be trusted, so the process outcome decides.
        if outcome.timed_out:
            raise errors.failure(NativeThreadProblem.TIMED_OUT, request=request, thread_id=session, outcome=outcome, vendor_text=outcome.stderr, seconds=timeout_seconds)
        if outcome.stdout_truncated:
            raise errors.failure(NativeThreadProblem.OUTPUT_TOO_LARGE, request=request, thread_id=session, outcome=outcome, vendor_text=outcome.stderr, cap_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES)

        # An auth error event means the provider refused the key.
        refused, vendor = OpencodeWire._error(events)
        if refused:
            raise errors.failure(NativeThreadProblem.KEY_REJECTED, request=request, thread_id=session, outcome=outcome, vendor_text=vendor)

        # @intent opencode-unknown-command-is-command-not-run
        # A run that named a command opencode does not know prints
        # its Command-not-found text in an error event or on stderr;
        # that is command_not_run, not a failed run (spec D-8).
        if request.command is not None:
            missing = native_threads.OPENCODE_COMMAND_NOT_FOUND_TEXT.format(command=request.command)
            if vendor is not None and missing in vendor:
                raise errors.failure(NativeThreadProblem.COMMAND_NOT_RUN, request=request, thread_id=session, outcome=outcome, vendor_text=vendor)
            if missing in outcome.stderr:
                raise errors.failure(NativeThreadProblem.COMMAND_NOT_RUN, request=request, thread_id=session, outcome=outcome, vendor_text=outcome.stderr)

        # opencode reports an unknown session on stderr.
        if native_threads.OPENCODE_SESSION_NOT_FOUND_MARKER in outcome.stderr:
            raise errors.failure(NativeThreadProblem.THREAD_NOT_FOUND, request=request, thread_id=session, outcome=outcome, vendor_text=outcome.stderr)

        # Any other error event, or a non-zero exit, is a failed run.
        if vendor is not None:
            raise errors.failure(NativeThreadProblem.RUN_FAILED, request=request, thread_id=session, outcome=outcome, vendor_text=vendor)
        if outcome.exit_code != native_threads.NATIVE_SUCCESS_EXIT_CODE:
            raise errors.failure(NativeThreadProblem.RUN_FAILED, request=request, thread_id=session, outcome=outcome, vendor_text=outcome.stderr)

        # Exit 0: the events must name the session.
        if session is None:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, outcome=outcome, missing_member=native_threads.OPENCODE_SESSION_FIELD)

        # A continue must answer on the thread it was given; a fork must
        # answer on a new one.
        wrong = NativeErrorFactory.wrong_thread(request, session)
        if wrong is not None:
            detail = native_threads.NATIVE_WRONG_THREAD_DETAILS[wrong].format(answered=session, requested=request.thread_id)
            raise errors.failure(wrong, request=request, thread_id=session, outcome=outcome, searched=detail)

        # Return the caller's own id on a continue, the new one
        # otherwise, with the last message's text cut at the result cap.
        thread_id = request.thread_id if request.verb is NativeThreadVerb.CONTINUE and request.thread_id is not None else session
        text = OpencodeWire._text(events)
        cap = native_threads.NATIVE_RESULT_TEXT_MAX_CHARS
        return NativeThreadResult(harness=NativeHarness.OPENCODE, thread_id=thread_id, text=text[:cap], text_truncated=len(text) > cap)

    @staticmethod
    def _session(events: list[Mapping[str, object]]) -> str | None:
        # The first sessionID, when it is a thread id the result record
        # accepts.
        for event in events:
            session = event.get(native_threads.OPENCODE_SESSION_FIELD)
            if isinstance(session, str):
                usable = RecordFieldValidator.accepts_text(session, max_chars=native_threads.NATIVE_THREAD_ID_MAX_CHARS, pattern=native_threads.NATIVE_THREAD_ID_PATTERN)
                return session if usable else None
        return None

    @staticmethod
    def _error(events: list[Mapping[str, object]]) -> tuple[bool, str | None]:
        # Whether the first error event refused the key, and its name,
        # HTTP status and message as vendor text; (False, None) when
        # opencode printed no error event.
        for event in events:
            if event.get(native_threads.OPENCODE_TYPE_FIELD) != OpencodeEventType.ERROR.value:
                continue
            error = event.get(native_threads.OPENCODE_ERROR_FIELD)
            body = error if isinstance(error, dict) else {}
            data = body.get(native_threads.OPENCODE_ERROR_DATA_FIELD)
            details = data if isinstance(data, dict) else {}
            name, status, message = body.get(native_threads.OPENCODE_ERROR_NAME_FIELD), details.get(native_threads.OPENCODE_STATUS_FIELD), details.get(native_threads.OPENCODE_ERROR_MESSAGE_FIELD)
            name = name if isinstance(name, str) else ""
            status = status if isinstance(status, int) and not isinstance(status, bool) else None
            template = native_threads.OPENCODE_ERROR_EVENT_TEXT if status is None else native_threads.OPENCODE_ERROR_EVENT_STATUS_TEXT
            refused = name in native_threads.OPENCODE_KEY_REJECTED_ERROR_NAMES or status in native_threads.OPENCODE_KEY_REJECTED_STATUSES
            return refused, template.format(name=name, status=status, message=message if isinstance(message, str) else "")
        return False, None

    @staticmethod
    def _text(events: list[Mapping[str, object]]) -> str:
        # The text parts of the message the last text event belongs to,
        # in order, one per line.
        parts = [event.get(native_threads.OPENCODE_PART_FIELD) for event in events if event.get(native_threads.OPENCODE_TYPE_FIELD) == OpencodeEventType.TEXT.value]
        texts = [part for part in parts if isinstance(part, dict) and isinstance(part.get(native_threads.OPENCODE_TEXT_FIELD), str)]
        if not texts:
            return ""
        *_earlier, last = texts
        message = last.get(native_threads.OPENCODE_MESSAGE_ID_FIELD)
        return native_threads.NATIVE_LINE_SEPARATOR.join(part[native_threads.OPENCODE_TEXT_FIELD] for part in texts if part.get(native_threads.OPENCODE_MESSAGE_ID_FIELD) == message)


class OpencodeHelperWire:
    """Reads what the opencode thread helpers' children print: session list and db rows, an export, a delete."""

    @staticmethod
    def sessions(outcome: CliOutcome, request: NativeHelperRequest, errors: NativeErrorFactory) -> tuple[tuple[NativeThreadSummary, str], ...]:
        # The child must have finished within its bounds; then its
        # output is one JSON array of rows, nothing meaning none.
        OpencodeHelperWire._checked(outcome, request, errors)
        rows = OpencodeHelperWire._array(outcome.stdout, outcome, request, errors)

        # @intent opencode-list-at-the-scan-cap-may-be-cut
        # The SDK asks for NATIVE_OPENCODE_SCAN_MAX rows; exactly that
        # many may be a cut list, so the call raises (spec EC-75).
        if len(rows) >= native_threads.NATIVE_OPENCODE_SCAN_MAX:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, outcome=outcome, searched=native_threads.OPENCODE_SCAN_CAP_DETAIL.format(cap=native_threads.NATIVE_OPENCODE_SCAN_MAX))

        # Each row is a root session with its folder; list rows carry no
        # parent and no model (spec D-24).
        found = []
        for row in rows:
            directory = row.get(native_threads.OPENCODE_DIRECTORY_FIELD)
            if not isinstance(directory, str):
                raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, outcome=outcome, searched=native_threads.OPENCODE_MEMBER_DETAIL.format(member=native_threads.OPENCODE_DIRECTORY_FIELD))
            created = OpencodeHelperWire._epoch(row.get(native_threads.OPENCODE_CREATED_FIELD), native_threads.OPENCODE_CREATED_FIELD, request, errors)
            updated = OpencodeHelperWire._epoch(row.get(native_threads.OPENCODE_UPDATED_FIELD), native_threads.OPENCODE_UPDATED_FIELD, request, errors)
            summary = OpencodeHelperWire._summary(row, native_threads.OPENCODE_LIST_MEMBERS, request, errors, created=created, updated=updated, parent=None)
            found.append((summary, directory))
        return tuple(found)

    @staticmethod
    def rows(outcome: CliOutcome, request: NativeHelperRequest, errors: NativeErrorFactory) -> tuple[NativeThreadSummary, ...]:
        # The rows of OPENCODE_SESSION_QUERY for one exact id: none
        # means opencode has no such session, more than one cannot be
        # (spec D-26).
        OpencodeHelperWire._checked(outcome, request, errors)
        rows = OpencodeHelperWire._array(outcome.stdout, outcome, request, errors)
        if len(rows) > 1:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, outcome=outcome, searched=native_threads.OPENCODE_ROWS_DETAIL.format(count=len(rows)))
        found = []
        for row in rows:
            created = OpencodeHelperWire._epoch(row.get(native_threads.OPENCODE_TIME_CREATED_COLUMN), native_threads.OPENCODE_TIME_CREATED_COLUMN, request, errors)
            updated = OpencodeHelperWire._epoch(row.get(native_threads.OPENCODE_TIME_UPDATED_COLUMN), native_threads.OPENCODE_TIME_UPDATED_COLUMN, request, errors)
            parent = row.get(native_threads.OPENCODE_PARENT_COLUMN)
            found.append(OpencodeHelperWire._summary(row, native_threads.OPENCODE_ROW_MEMBERS, request, errors, created=created, updated=updated, parent=parent))
        return tuple(found)

    @staticmethod
    def document(outcome: CliOutcome, request: NativeHelperRequest, errors: NativeErrorFactory) -> NativeThreadResult:
        # An `opencode export` document, returned whole (spec INV-21).
        OpencodeHelperWire._checked(outcome, request, errors)
        return NativeThreadResult(harness=NativeHarness.OPENCODE, thread_id=request.thread_id or "", text=outcome.stdout, text_truncated=False)

    @staticmethod
    def deleted(outcome: CliOutcome, request: NativeHelperRequest, errors: NativeErrorFactory) -> None:
        # An `opencode session delete` that exited 0 without the
        # not-found text.
        OpencodeHelperWire._checked(outcome, request, errors)

    @staticmethod
    def _checked(outcome: CliOutcome, request: NativeHelperRequest, errors: NativeErrorFactory) -> None:
        # What every helper child shares: its fixed time bound, the
        # output cap, opencode's not-found text, then any other
        # non-zero exit.
        if outcome.timed_out:
            raise errors.failure(NativeThreadProblem.TIMED_OUT, request=request, outcome=outcome, vendor_text=outcome.stderr, seconds=native_threads.NATIVE_CONTROL_TIMEOUT_SECONDS)
        if outcome.stdout_truncated:
            raise errors.failure(NativeThreadProblem.OUTPUT_TOO_LARGE, request=request, outcome=outcome, vendor_text=outcome.stderr, cap_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES)
        failed = outcome.exit_code != native_threads.NATIVE_SUCCESS_EXIT_CODE
        if failed and native_threads.OPENCODE_SESSION_NOT_FOUND_MARKER in outcome.stderr:
            raise errors.failure(NativeThreadProblem.THREAD_NOT_FOUND, request=request, outcome=outcome, vendor_text=outcome.stderr)
        if failed:
            raise errors.failure(NativeThreadProblem.RUN_FAILED, request=request, outcome=outcome, vendor_text=outcome.stderr)

    @staticmethod
    def _array(stdout: str, outcome: CliOutcome, request: NativeHelperRequest, errors: NativeErrorFactory) -> list[Mapping[str, object]]:
        # One JSON array of objects; blank output is no rows (spec
        # EC-29), anything else is protocol_mismatch (spec EC-30).
        if not stdout.strip():
            return []
        try:
            value = json.loads(stdout)
        except ValueError as exc:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, outcome=outcome, searched=native_threads.OPENCODE_SHAPE_DETAIL) from exc
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, outcome=outcome, searched=native_threads.OPENCODE_SHAPE_DETAIL)
        return value

    @staticmethod
    def _epoch(value: object, member: str, request: NativeHelperRequest, errors: NativeErrorFactory) -> datetime:
        # opencode's epoch milliseconds as a UTC time; a bool, text or
        # out-of-range value is protocol_mismatch naming the member.
        try:
            milliseconds = RecordFieldValidator.require_int(value, member, minimum=native_threads.NATIVE_EPOCH_MS_MIN, maximum=native_threads.NATIVE_EPOCH_MS_MAX)
        except ConfigurationError as exc:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, searched=native_threads.OPENCODE_MEMBER_DETAIL.format(member=member)) from exc
        return datetime.fromtimestamp(milliseconds / native_threads.OPENCODE_MILLISECONDS_PER_SECOND, timezone.utc)

    @staticmethod
    def _summary(row: Mapping[str, object], members: Mapping[str, str], request: NativeHelperRequest, errors: NativeErrorFactory, *, created: datetime, updated: datetime, parent: object) -> NativeThreadSummary:
        # One record from a row; a blank title reads as no title, and a
        # member the record refuses is named as opencode spells it.
        title = row.get(native_threads.OPENCODE_TITLE_FIELD)
        try:
            return NativeThreadSummary(
                harness=NativeHarness.OPENCODE,
                thread_id=row.get(native_threads.OPENCODE_ID_FIELD),
                title=None if isinstance(title, str) and not title.strip() else title,
                created_at=created,
                updated_at=updated,
                parent_thread_id=parent,
                model=None,
            )
        except ConfigurationError as exc:
            field = str(exc.details.get(native_threads.NATIVE_FIELD_DETAIL_KEY, ""))
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, searched=native_threads.OPENCODE_MEMBER_DETAIL.format(member=members.get(field, field))) from exc


__all__ = ["OpencodeHelperWire", "OpencodeWire"]
