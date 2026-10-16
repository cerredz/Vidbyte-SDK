"""FILE: vidbyte/harnesses/native/grok/wire.py

PURPOSE: Defines the readers of what grok prints and stores: GrokWire reads one `grok --single --output-format=json` run of #1036; GrokStreamWire reads one `--output-format=streaming-json` command run and its tool calls; GrokHelperWire reads one summary.json, a `grok export` transcript and a `grok sessions delete` answer. Each turns vendor output into a record, or into the NativeThreadError that names what went wrong.
ROLE IN CODEBASE: GrokWire is called by GrokThreadRun.execute (grok/threads.py), GrokStreamWire by GrokCommandRun.execute (grok/commands.py), and GrokHelperWire by GrokStore (grok/store.py) for each summary.json and by GrokHelperRun (grok/helpers.py) for the export and delete children; all raise through the call's NativeErrorFactory (hostkit/errors.py).
ARCHITECTURE NOTE: Pure: no process, no file and no await; the store and the helper flows read the files and run the children. Grok writes one JSON object at exit for a --single json run, and one JSON event per line for a streaming run (text, tool_call, tool_call_update, then end {sessionId}, or error {message}). Every member name and marker comes from vidbyte/lib/constants/native_threads.py (spec INV-15). The checks run in the INV-6 order: timeout, output cap, the vendor's error object (key rejected or run failed), a bare non-zero exit, then the shape of the answer and the thread id. A summary.json member the record refuses is protocol_mismatch naming the member as Grok spells it and the file (spec INV-6).
FUNCTION INVENTORY: GrokWire.read is the narrated main function of a #1036 run; _answer parses stdout as one JSON object, or None. GrokStreamWire.read reads a command run in the spec §9.2 order, on the id the SDK minted (spec D-29); tool_calls lists the run's tool calls for the evidence check; _events parses the stream. GrokHelperWire.thread_file reads one summary.json into a GrokThreadFile; document reads a `grok export` transcript whole; deleted reads a `grok sessions delete` answer; _checked holds the timeout, cap, not-found and exit checks the two children share; _optional_text reads one optional text member of a summary.json.
COMMON MODIFICATION PATTERNS: A new sign-in failure text from grok is one more marker in GROK_NOT_SIGNED_IN_MARKERS; a new answer member the SDK must read gets its name constant and one check in read; a new summary.json member is one name constant, one GROK_SUMMARY_MEMBERS entry and one read in thread_file.
WHAT NOT TO DO IN THIS FILE: 1. Do not copy vendor text into an error unscrubbed; pass it as vendor_text and the factory scrubs and caps it. 2. Do not accept a cut stdout; a truncated answer is output_too_large, never parsed, and a transcript is returned whole or not at all (spec INV-21). 3. Do not start processes, read files or await anything here. 4. Do not take a command run's thread id from the stream; the SDK minted it, and an end event naming another id is protocol_mismatch.
KNOWN EDGE CASES: A continue is matched case-insensitively and returns the id the caller gave. A fork whose answer is its source thread is protocol_mismatch, because grok then continued the source instead of copying it. A thread id that the result record would refuse is protocol_mismatch, not an argument error. A timed-out #1036 run carries no new thread id, because grok prints it only at exit; a command run always carries its minted id, and says the thread may not exist when it failed before any tool call or end event (spec INV-29, EC-81). A blank generated_title reads as no title. A tool event without a usable name is skipped, because it cannot be evidence.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_errors.py, tests/features/harness_threads/test_harness_threads_threads.py, tests/features/harness_threads/test_harness_threads_grok_commands.py, tests/features/harness_threads/test_harness_threads_grok_helpers.py
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from vidbyte.harnesses.native.hostkit import NativeErrorFactory
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    GrokThreadFile,
    NativeHelperRequest,
    NativeThreadRequest,
    NativeThreadResult,
    NativeThreadSummary,
    NativeToolCall,
)
from vidbyte.lib.dataclasses.process import CliOutcome
from vidbyte.lib.dataclasses.validation import (
    RecordFieldConverter,
    RecordFieldValidator,
)
from vidbyte.lib.enums.native_threads import (
    GrokEventType,
    NativeHarness,
    NativeThreadProblem,
    NativeThreadVerb,
)
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.process import CliRunner


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
        # The whole stdout as one JSON object, or None when it is not
        # one.
        try:
            value = json.loads(stdout)
        except ValueError:
            return None
        return value if isinstance(value, dict) else None


class GrokStreamWire:
    """Reads one `grok --output-format=streaming-json` command run, on the thread id the SDK minted."""

    @staticmethod
    def read(outcome: CliOutcome, request: NativeThreadRequest, errors: NativeErrorFactory, *, timeout_seconds: float, thread_id: str) -> NativeThreadResult:
        # The run passed its time bound, or printed more than the cap:
        # the stream cannot be trusted, so the process outcome decides.
        # Either way the thread exists, so no doubt is added.
        if outcome.timed_out:
            raise errors.failure(NativeThreadProblem.TIMED_OUT, request=request, thread_id=thread_id, outcome=outcome, vendor_text=outcome.stderr, seconds=timeout_seconds)
        if outcome.stdout_truncated:
            raise errors.failure(NativeThreadProblem.OUTPUT_TOO_LARGE, request=request, thread_id=thread_id, outcome=outcome, vendor_text=outcome.stderr, cap_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES)

        # @intent grok-command-thread-may-not-exist-before-it-started
        # Grok made the thread once it reported a tool call or the end;
        # before that, a failure may have come before the session
        # existed, and the error says so (spec INV-29).
        events = GrokStreamWire._events(outcome.stdout)
        kinds = [event.get(native_threads.GROK_TYPE_FIELD) for event in events]
        started = GrokEventType.TOOL_CALL in kinds or GrokEventType.END in kinds
        doubt = None if started else native_threads.GROK_THREAD_MAY_NOT_EXIST_DETAIL

        # Grok's own first error event: a sign-in failure means the key
        # was refused, anything else is a failed run.
        failed = next((event for event in events if event.get(native_threads.GROK_TYPE_FIELD) == GrokEventType.ERROR), None)
        if failed is not None:
            message = str(failed.get(native_threads.GROK_MESSAGE_FIELD, ""))
            refused = any(marker in message.casefold() for marker in native_threads.GROK_NOT_SIGNED_IN_MARKERS)
            problem = NativeThreadProblem.KEY_REJECTED if refused else NativeThreadProblem.RUN_FAILED
            raise errors.failure(problem, request=request, thread_id=thread_id, outcome=outcome, vendor_text=message, searched=doubt)

        # A non-zero exit without an error event: report what grok
        # wrote to stderr.
        if outcome.exit_code != native_threads.NATIVE_SUCCESS_EXIT_CODE:
            raise errors.failure(NativeThreadProblem.RUN_FAILED, request=request, thread_id=thread_id, outcome=outcome, vendor_text=outcome.stderr, searched=doubt)

        # Exit 0: the run must end with an end event that names the id
        # the SDK minted; another id means grok ran another session.
        ends = [event for event in events if event.get(native_threads.GROK_TYPE_FIELD) == GrokEventType.END]
        if not ends:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, thread_id=thread_id, outcome=outcome, missing_member=native_threads.GROK_END_MEMBER, searched=doubt)
        answered = ends[-1].get(native_threads.GROK_SESSION_FIELD)
        if not isinstance(answered, str) or not RecordFieldValidator.accepts_text(answered, max_chars=native_threads.NATIVE_THREAD_ID_MAX_CHARS, pattern=native_threads.NATIVE_THREAD_ID_PATTERN):
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, thread_id=thread_id, outcome=outcome, missing_member=native_threads.GROK_SESSION_FIELD)
        if answered.casefold() != thread_id.casefold():
            detail = native_threads.GROK_SESSION_ID_MISMATCH_DETAIL.format(answered=answered, requested=thread_id)
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, thread_id=thread_id, outcome=outcome, missing_member=native_threads.GROK_SESSION_FIELD, searched=detail)

        # The answer is the text grok streamed after its last tool
        # event, cut at the result cap (spec A-11).
        tool_kinds = (GrokEventType.TOOL_CALL, GrokEventType.TOOL_CALL_UPDATE)
        tool_indexes = [index for index, kind in enumerate(kinds) if kind in tool_kinds]
        tail = events[tool_indexes[-1] + 1 :] if tool_indexes else events
        parts = [event.get(native_threads.GROK_DATA_FIELD) for event in tail if event.get(native_threads.GROK_TYPE_FIELD) == GrokEventType.TEXT]
        if not all(isinstance(part, str) for part in parts):
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, thread_id=thread_id, outcome=outcome, missing_member=native_threads.GROK_DATA_FIELD)
        text = "".join(str(part) for part in parts)
        cap = native_threads.NATIVE_RESULT_TEXT_MAX_CHARS
        return NativeThreadResult(harness=NativeHarness.GROK, thread_id=thread_id, text=text[:cap], text_truncated=len(text) > cap)

    @staticmethod
    def tool_calls(stdout: str) -> tuple[NativeToolCall, ...]:
        # Every tool_call event with a usable name, its rawInput as
        # JSON text (a string input stays as it is); an event without a
        # usable name cannot be evidence and is skipped.
        calls = []
        for event in GrokStreamWire._events(stdout):
            name = event.get(native_threads.GROK_TOOL_NAME_FIELD)
            if event.get(native_threads.GROK_TYPE_FIELD) != GrokEventType.TOOL_CALL or not RecordFieldValidator.accepts_text(name, max_chars=native_threads.NATIVE_TOOL_NAME_MAX_CHARS):
                continue
            raw = event.get(native_threads.GROK_RAW_INPUT_FIELD)
            calls.append(NativeToolCall(name=str(name), arguments=raw if isinstance(raw, str) else json.dumps(raw)))
        return tuple(calls)

    @staticmethod
    def _events(stdout: str) -> list[Mapping[str, object]]:
        # One JSON object per line; log and cut lines are skipped the
        # way every CLI reader skips them.
        return CliRunner.json_objects(stdout)


class GrokHelperWire:
    """Reads one summary.json, a `grok export` transcript and a `grok sessions delete` answer."""

    @staticmethod
    def thread_file(data: bytes, path: Path, errors: NativeErrorFactory, request: NativeHelperRequest | NativeThreadRequest) -> GrokThreadFile:
        # The file must be one JSON object in UTF-8; anything else is
        # protocol_mismatch naming the file (spec EC-9).
        try:
            document = json.loads(data.decode(native_threads.NATIVE_TEXT_ENCODING))
        except ValueError as exc:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, searched=native_threads.GROK_SUMMARY_SHAPE_DETAIL.format(path=path)) from exc
        if not isinstance(document, dict):
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, searched=native_threads.GROK_SUMMARY_SHAPE_DETAIL.format(path=path))

        # The texts are strings, null or absent; a blank title reads as
        # no title.
        title = GrokHelperWire._optional_text(document, native_threads.GROK_TITLE_FIELD, path, errors, request)
        summary_text = GrokHelperWire._optional_text(document, native_threads.GROK_SESSION_SUMMARY_FIELD, path, errors, request)
        last_turn = GrokHelperWire._optional_text(document, native_threads.GROK_LAST_TURN_SUMMARY_FIELD, path, errors, request)
        agent_name = GrokHelperWire._optional_text(document, native_threads.GROK_AGENT_NAME_FIELD, path, errors, request)

        # The record checks the rest; a member it refuses is named as
        # Grok spells it, with the file (spec INV-6). The thread id is
        # the session folder's name.
        try:
            summary = NativeThreadSummary(
                harness=NativeHarness.GROK,
                thread_id=path.parent.name,
                title=title if title is not None and title.strip() else None,
                created_at=RecordFieldConverter.to_utc_datetime(document.get(native_threads.GROK_CREATED_AT_FIELD), native_threads.GROK_CREATED_AT_FIELD),
                updated_at=RecordFieldConverter.to_utc_datetime(document.get(native_threads.GROK_UPDATED_AT_FIELD), native_threads.GROK_UPDATED_AT_FIELD),
                parent_thread_id=document.get(native_threads.GROK_PARENT_FIELD),
                model=document.get(native_threads.GROK_MODEL_FIELD),
            )
        except ConfigurationError as exc:
            field = str(exc.details.get(native_threads.NATIVE_FIELD_DETAIL_KEY, ""))
            member = native_threads.GROK_SUMMARY_MEMBERS.get(field, field)
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, searched=native_threads.GROK_SUMMARY_MEMBER_DETAIL.format(member=member, path=path)) from exc
        return GrokThreadFile(summary=summary, search_text=(title, summary_text, last_turn), agent_name=agent_name, path=path)

    @staticmethod
    def document(outcome: CliOutcome, request: NativeHelperRequest | NativeThreadRequest, errors: NativeErrorFactory, *, thread_id: str) -> NativeThreadResult:
        # A `grok export` transcript, returned whole (spec INV-21).
        GrokHelperWire._checked(outcome, request, errors, thread_id=thread_id)
        return NativeThreadResult(harness=NativeHarness.GROK, thread_id=thread_id, text=outcome.stdout, text_truncated=False)

    @staticmethod
    def deleted(outcome: CliOutcome, request: NativeHelperRequest, errors: NativeErrorFactory) -> None:
        # A `grok sessions delete` that exited 0 without the not-found
        # text; the caller then checks that the folder is gone.
        GrokHelperWire._checked(outcome, request, errors, thread_id=request.thread_id or "")

    @staticmethod
    def _checked(outcome: CliOutcome, request: NativeHelperRequest | NativeThreadRequest, errors: NativeErrorFactory, *, thread_id: str) -> None:
        # The checks the export and delete children share: their fixed
        # time bound, the output cap, grok's not-found text for the id,
        # then any other non-zero exit.
        if outcome.timed_out:
            raise errors.failure(NativeThreadProblem.TIMED_OUT, request=request, thread_id=thread_id, outcome=outcome, vendor_text=outcome.stderr, seconds=native_threads.NATIVE_CONTROL_TIMEOUT_SECONDS)
        if outcome.stdout_truncated:
            raise errors.failure(NativeThreadProblem.OUTPUT_TOO_LARGE, request=request, thread_id=thread_id, outcome=outcome, vendor_text=outcome.stderr, cap_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES)
        missing = native_threads.GROK_SESSION_NOT_FOUND_TEXT.format(thread_id=thread_id)
        if outcome.exit_code != native_threads.NATIVE_SUCCESS_EXIT_CODE and (missing in outcome.stderr or missing in outcome.stdout):
            raise errors.failure(NativeThreadProblem.THREAD_NOT_FOUND, request=request, thread_id=thread_id, outcome=outcome, vendor_text=outcome.stderr)
        if outcome.exit_code != native_threads.NATIVE_SUCCESS_EXIT_CODE:
            raise errors.failure(NativeThreadProblem.RUN_FAILED, request=request, thread_id=thread_id, outcome=outcome, vendor_text=outcome.stderr)

    @staticmethod
    def _optional_text(document: Mapping[str, object], member: str, path: Path, errors: NativeErrorFactory, request: NativeHelperRequest | NativeThreadRequest) -> str | None:
        # One member that is a string, null or absent; any other type
        # is protocol_mismatch naming the member and the file.
        value = document.get(member)
        if value is not None and not isinstance(value, str):
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, searched=native_threads.GROK_SUMMARY_MEMBER_DETAIL.format(member=member, path=path))
        return value


__all__ = ["GrokHelperWire", "GrokStreamWire", "GrokWire"]
