"""FILE: vidbyte/harnesses/native/grok/wire.py

PURPOSE: Defines GrokWire, the reader of one `grok --single` run: it turns the run's CliOutcome into a NativeThreadResult, or into the NativeThreadError that names what went wrong, from the one JSON answer of a plain call or the streamed events of a browser call, and reads a browser call's tool calls and connected servers from that stream.
ROLE IN CODEBASE: Called by GrokThreadRun.execute in vidbyte/harnesses/native/grok/threads.py after CliRunner returns (read on a plain call, read_stream on a browser call); GrokBrowserHarness (grok/browser.py) calls tool_calls and connected on a browser call's outcome. It raises through the call's NativeErrorFactory (hostkit/errors.py).
ARCHITECTURE NOTE: Pure: no process, no file and no await. With --output-format=json Grok writes one JSON object at exit: on success {"text", "sessionId", ...}, on failure {"type": "error", "message"} with a non-zero exit. With --output-format=streaming-json (browser calls only, spec D-8) it writes one event per line: available_commands with the connected tools, text chunks between usage events, tool_call and tool_call_update events, and a closing end event with stopReason and sessionId; read_stream applies read's checks in the same order (spec section 9.1). Every member name and marker comes from vidbyte/lib/constants/native_threads.py (spec INV-15). The checks run in the INV-6 order: timeout, output cap, the vendor's error object (key rejected or run failed), a bare non-zero exit, then the shape of the success answer and the thread id.
FUNCTION INVENTORY: read is the narrated main function of a plain call; read_stream is the narrated main function of a browser call; tool_calls reads the mounted-tool calls of a browser call; connected names the mounted servers the stream lists in available_commands; _answer parses stdout as one JSON object, or None; _stream_text joins the last non-empty run of text chunks.
COMMON MODIFICATION PATTERNS: A new sign-in failure text from grok is one more marker in GROK_NOT_SIGNED_IN_MARKERS; a new answer member the SDK must read gets its name constant and one check in read.
WHAT NOT TO DO IN THIS FILE: 1. Do not copy vendor text into an error unscrubbed; pass it as vendor_text and the factory scrubs and caps it. 2. Do not accept a cut stdout; a truncated answer is output_too_large, never parsed. 3. Do not start processes or await anything here.
KNOWN EDGE CASES: A browser run whose stop reason is cancelled is a failed run, because a headless run cancels the turn when the agent calls a tool no rule allows (spec EC-41). The readers never raise on vendor text: a name whose server is not mounted, or whose tool part fails NATIVE_NAME_PATTERN, is skipped (EC-44). A continue is matched case-insensitively and returns the id the caller gave. A fork whose answer is its source thread is protocol_mismatch, because grok then continued the source instead of copying it. A thread id that the result record would refuse is protocol_mismatch, not an argument error. A timed-out run carries no new thread id, because grok prints it only at exit.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_errors.py, tests/features/harness_threads/test_harness_threads_threads.py
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from vidbyte.harnesses.native.hostkit import NativeErrorFactory
from vidbyte.lib.constants import browser_tools, native_threads
from vidbyte.lib.dataclasses.browser_tools import (
    BrowserMount,
    BrowserToolCall,
    BrowserToolCalls,
)
from vidbyte.lib.dataclasses.native_threads import (
    NativeThreadRequest,
    NativeThreadResult,
)
from vidbyte.lib.dataclasses.process import CliOutcome
from vidbyte.lib.dataclasses.validation import RecordFieldValidator
from vidbyte.lib.enums.browser_tools import BrowserTool, BrowserToolCallStatus
from vidbyte.lib.enums.native_threads import (
    NativeHarness,
    NativeThreadProblem,
    NativeThreadVerb,
)
from vidbyte.lib.process import CliRunner


class GrokWire:
    """Reads the one JSON answer of a plain headless grok run, or the streamed events of a browser run."""

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
    def read_stream(outcome: CliOutcome, request: NativeThreadRequest, errors: NativeErrorFactory, *, timeout_seconds: float) -> NativeThreadResult:
        # Read the streamed events and the closing end event first, so
        # every failure below carries the thread Grok already named.
        events = CliRunner.json_objects(outcome.stdout)
        end = next((event for event in reversed(events) if event.get(native_threads.GROK_TYPE_FIELD) == native_threads.GROK_END_EVENT), None)
        session = None if end is None else end.get(native_threads.GROK_SESSION_FIELD)
        known = session if isinstance(session, str) and RecordFieldValidator.accepts_text(session, max_chars=native_threads.NATIVE_THREAD_ID_MAX_CHARS, pattern=native_threads.NATIVE_THREAD_ID_PATTERN) else None

        # The run passed its time bound, or printed more than the
        # browser path's cap: the stream cannot be trusted, so the
        # process outcome decides.
        if outcome.timed_out:
            raise errors.failure(NativeThreadProblem.TIMED_OUT, request=request, thread_id=known, outcome=outcome, vendor_text=outcome.stderr, seconds=timeout_seconds)
        if outcome.stdout_truncated:
            raise errors.failure(NativeThreadProblem.OUTPUT_TOO_LARGE, request=request, thread_id=known, outcome=outcome, vendor_text=outcome.stderr, cap_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES)

        # Grok's own error event: a sign-in failure means the key was
        # refused, anything else is a failed run.
        error = next((event for event in events if event.get(native_threads.GROK_TYPE_FIELD) == native_threads.GROK_ERROR_TYPE), None)
        if error is not None:
            message = str(error.get(native_threads.GROK_MESSAGE_FIELD, ""))
            refused = any(marker in message.casefold() for marker in native_threads.GROK_NOT_SIGNED_IN_MARKERS)
            problem = NativeThreadProblem.KEY_REJECTED if refused else NativeThreadProblem.RUN_FAILED
            raise errors.failure(problem, request=request, thread_id=known, outcome=outcome, vendor_text=message)

        # A non-zero exit without an error event: report what grok
        # wrote to stderr.
        if outcome.exit_code != native_threads.NATIVE_SUCCESS_EXIT_CODE:
            raise errors.failure(NativeThreadProblem.RUN_FAILED, request=request, thread_id=known, outcome=outcome, vendor_text=outcome.stderr)

        # Exit 0: the stream must close with an end event.
        if end is None:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, outcome=outcome, missing_member=native_threads.GROK_END_EVENT)

        # @intent grok-cancelled-turn-is-a-failed-run
        # A headless run cancels the turn when the agent calls a tool no
        # rule allows, so a cancelled stop is a failed run, never a
        # quiet answer.
        stop = end.get(native_threads.GROK_STOP_REASON_FIELD)
        if stop == native_threads.GROK_CANCELLED_STOP_REASON:
            raise errors.failure(NativeThreadProblem.RUN_FAILED, request=request, thread_id=known, outcome=outcome, searched=native_threads.GROK_STOP_REASON_DETAIL.format(reason=stop))

        # The end event must name a usable thread; a continue must
        # answer on the thread it was given and a fork on a new one.
        if known is None:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, outcome=outcome, missing_member=native_threads.GROK_SESSION_FIELD)
        wrong = NativeErrorFactory.wrong_thread(request, known)
        if wrong is not None:
            detail = native_threads.NATIVE_WRONG_THREAD_DETAILS[wrong].format(answered=known, requested=request.thread_id)
            raise errors.failure(wrong, request=request, thread_id=known, outcome=outcome, searched=detail)

        # Return the caller's own id on a continue, the new one
        # otherwise, with the answer cut at the result cap.
        thread_id = request.thread_id if request.verb is NativeThreadVerb.CONTINUE and request.thread_id is not None else known
        answer = GrokWire._stream_text(events)
        cap = native_threads.NATIVE_RESULT_TEXT_MAX_CHARS
        return NativeThreadResult(harness=NativeHarness.GROK, thread_id=thread_id, text=answer[:cap], text_truncated=len(answer) > cap)

    @staticmethod
    def tool_calls(outcome: CliOutcome, mount: BrowserMount) -> BrowserToolCalls:
        # @intent grok-reader-skips-vendor-names-it-cannot-trust
        # Each use_tool call on a mounted server, in the order Grok
        # printed them, with the last status Grok reported for it: the
        # model-written name splits at the first double underscore, a
        # name that fails the record's rule is skipped rather than
        # raised, and anything but completed (a denied call included)
        # is failed.
        events = CliRunner.json_objects(outcome.stdout)
        mounted = {server.selection.definition.tool.value: server.selection.definition.tool for server in mount.servers}
        statuses = {event.get(native_threads.GROK_TOOL_CALL_ID_FIELD): event.get(native_threads.GROK_STATUS_FIELD) for event in events if event.get(native_threads.GROK_TYPE_FIELD) == native_threads.GROK_TOOL_CALL_UPDATE_EVENT and isinstance(event.get(native_threads.GROK_STATUS_FIELD), str)}
        calls: list[BrowserToolCall] = []
        for event in events:
            raw = event.get(native_threads.GROK_RAW_INPUT_FIELD)
            name = raw.get(native_threads.GROK_RAW_TOOL_NAME_FIELD) if isinstance(raw, dict) else None
            if event.get(native_threads.GROK_TYPE_FIELD) != native_threads.GROK_TOOL_CALL_EVENT or event.get(native_threads.GROK_TOOL_NAME_FIELD) != native_threads.GROK_USE_TOOL_NAME or not isinstance(name, str):
                continue
            server, separator, tool = name.partition(browser_tools.GROK_TOOL_NAME_SEPARATOR)
            if not separator or server not in mounted or not RecordFieldValidator.accepts_text(tool, max_chars=native_threads.NATIVE_NAME_MAX_CHARS, pattern=native_threads.NATIVE_NAME_PATTERN):
                continue
            completed = statuses.get(event.get(native_threads.GROK_TOOL_CALL_ID_FIELD)) == native_threads.GROK_COMPLETED_STATUS
            calls.append(BrowserToolCall(tool=mounted[server], name=tool, status=BrowserToolCallStatus.COMPLETED if completed else BrowserToolCallStatus.FAILED))
        cap = browser_tools.BROWSER_TOOL_CALLS_MAX_ITEMS
        return BrowserToolCalls(calls=tuple(calls[:cap]), truncated=len(calls) > cap)

    @staticmethod
    def connected(outcome: CliOutcome, mount: BrowserMount) -> tuple[BrowserTool, ...]:
        # @intent grok-servers-show-only-in-the-tool-list
        # A mounted server counts as connected only when one of its
        # tools is in an available_commands list, the one per-server
        # evidence a headless run prints. A call never adds a server:
        # the model can name a tool whose server never connected, and
        # Grok then answers "Tool not found" (spec D-11).
        names: list[object] = []
        for event in CliRunner.json_objects(outcome.stdout):
            listed = event.get(native_threads.GROK_TOOLS_FIELD)
            if event.get(native_threads.GROK_TYPE_FIELD) == native_threads.GROK_AVAILABLE_COMMANDS_EVENT and isinstance(listed, list):
                names.extend(listed)
        parts = [name.partition(browser_tools.GROK_TOOL_NAME_SEPARATOR) for name in names if isinstance(name, str)]
        seen = {server for server, separator, _tool in parts if separator}
        return tuple(server.selection.definition.tool for server in mount.servers if server.selection.definition.tool.value in seen)

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
    def _stream_text(events: list[Mapping[str, object]]) -> str:
        # The answer is the last non-empty run of text chunks between
        # usage events; earlier runs are narration before tool calls.
        runs: list[list[str]] = [[]]
        for event in events:
            kind, data = event.get(native_threads.GROK_TYPE_FIELD), event.get(native_threads.GROK_DATA_FIELD)
            if kind == native_threads.GROK_USAGE_EVENT:
                runs.append([])
            elif kind == native_threads.GROK_TEXT_EVENT and isinstance(data, str):
                runs[-1].append(data)
        texts = ["".join(run) for run in runs]
        return next((joined for joined in reversed(texts) if joined), "")


__all__ = ["GrokWire"]
