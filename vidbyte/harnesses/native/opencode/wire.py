"""FILE: vidbyte/harnesses/native/opencode/wire.py

PURPOSE: Defines OpencodeWire, the codec of one `opencode run --format=json` call: it builds the inline config that binds the caller's key to the provider its model names, and turns the run's CliOutcome into a NativeThreadResult, or into the NativeThreadError that names what went wrong.
ROLE IN CODEBASE: Called by OpencodeThreadRun.execute in vidbyte/harnesses/native/opencode/threads.py: config_content before the run, read after CliRunner returns. It raises through the call's NativeErrorFactory (hostkit/errors.py).
ARCHITECTURE NOTE: Pure: no process, no file and no await. opencode prints one JSON event per line, each with "type" and "sessionID"; "text" events carry part.text and part.messageID, "error" events carry error.name and error.data.message/statusCode; an unknown session is "Session not found" on stderr with exit 1. Every member name and marker comes from vidbyte/lib/constants/native_threads.py (spec INV-15). The checks run in the INV-6 order: timeout, output cap, a refused key, an unknown session, a failed run, then the shape of the answer and the thread id.
FUNCTION INVENTORY: config_content builds the OPENCODE_CONFIG_CONTENT value; read is the narrated main function, reading the JSON lines through CliRunner.json_objects; _session finds the first usable sessionID; _error classifies the first error event and builds its vendor text; _text joins the text parts of the last message.
COMMON MODIFICATION PATTERNS: A new key-refusal signal from opencode is one more name in OPENCODE_KEY_REJECTED_ERROR_NAMES or status in OPENCODE_KEY_REJECTED_STATUSES; a new config member is one more key in config_content.
WHAT NOT TO DO IN THIS FILE: 1. Do not return the config value anywhere but the child's environment; it holds the key, and the caller registers it as a secret. 2. Do not copy vendor text into an error unscrubbed; pass it as vendor_text and the factory scrubs and caps it. 3. Do not start processes or await anything here.
KNOWN EDGE CASES: The thread id is looked for before the runner checks, so a timed-out or cut stream still reports the session opencode printed (spec INV-5). Lines that are not JSON objects, such as plugin log lines, are skipped. The answer text is only the last message's text parts, so earlier narration ("Let me look at the files first.") is left out; a run whose last message has no text returns "". A continue is matched case-insensitively and returns the id the caller gave; a fork whose answer is its source is protocol_mismatch.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_errors.py, tests/features/harness_threads/test_harness_threads_threads.py, tests/features/harness_threads/test_harness_threads_acceptance.py
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
    OpencodeEventType,
)
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
            raise errors.failure(NativeThreadProblem.TIMED_OUT, request=request, thread_id=session, outcome=outcome, seconds=timeout_seconds)
        if outcome.stdout_truncated:
            raise errors.failure(NativeThreadProblem.OUTPUT_TOO_LARGE, request=request, thread_id=session, outcome=outcome, cap_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES)

        # An auth error event means the provider refused the key.
        refused, vendor = OpencodeWire._error(events)
        if refused:
            raise errors.failure(NativeThreadProblem.KEY_REJECTED, request=request, thread_id=session, outcome=outcome, vendor_text=vendor)

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


__all__ = ["OpencodeWire"]
