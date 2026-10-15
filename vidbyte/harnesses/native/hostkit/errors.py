"""FILE: vidbyte/harnesses/native/hostkit/errors.py

PURPOSE: Defines NativeErrorFactory, which builds every NativeThreadError a thread function raises: it looks the failure code up in a closed table, composes the message from the INV-5 sentences in order, scrubs every dynamic part (the values the call injected, then the shared HarnessRedactor) and caps the vendor text.
ROLE IN CODEBASE: One factory per call, built by the public functions in vidbyte/harnesses/native/grok/threads.py, opencode/threads.py and muse/threads.py with the harness and the function, and handed to their flow classes, wire readers and launchers.
ARCHITECTURE NOTE: Lives in hostkit, not vidbyte.lib, because scrubbing reuses HarnessRedactor from vidbyte.harnesses.serialization and lib may not import upward. Every fixed word comes from vidbyte/lib/constants/native_threads.py (spec INV-15): the sentence templates, the harness labels, the failure code of each harness and problem, and the likely cause and next step of each code. The code is looked up in NATIVE_THREAD_FAILURE_CODES, never built from text, so a code that is not a FailureCode member cannot occur.
FUNCTION INVENTORY: register_secret remembers an injected value; scrub redacts and caps text; listing joins names for a sentence; failure is the narrated main function that builds the error for a problem; from_configuration_error, from_unexpected and from_launch_failure build the invalid-argument, runtime and launch errors; _context_sentences formats the scrubbed workspace and thread id sentences; _observed_sentences formats what the SDK saw; _error assembles the message and the error. Only the entry methods scrub, so every helper is one call deep (AGENTS.md principle 1).
COMMON MODIFICATION PATTERNS: A new problem adds its NativeThreadProblem member, its summary and observation templates, its codes in NATIVE_THREAD_FAILURE_CODES and their texts; this file needs no change unless the problem brings a new kind of observation, which becomes one more keyword argument of failure.
WHAT NOT TO DO IN THIS FILE: 1. Do not put raw exception text into a message; only class names, the SDK's own validator text and scrubbed vendor text. 2. Do not scrub or cut the likely cause and the next step; they must appear exactly as the constants hold them. 3. Do not raise from a builder; a builder that fails would hide the original error.
KNOWN EDGE CASES: A registered value is replaced before the redactor runs and before the cap, so a cap cannot cut a secret in half and leave its prefix. Empty text stays empty instead of becoming the redactor's "raised without a message" fallback. A timed-out outcome reports no exit code, because the status then comes from the tree stop, not from the vendor.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_errors.py, tests/features/harness_threads/test_harness_threads_credentials.py
"""

from __future__ import annotations

from collections.abc import Iterable

from vidbyte.harnesses.serialization import HarnessRedactor
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import NativeThreadRequest
from vidbyte.lib.dataclasses.process import CliOutcome
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.enums.native_threads import (
    NativeHarness,
    NativeThreadOperation,
    NativeThreadProblem,
)
from vidbyte.lib.enums.process import ProcessLaunchFailure
from vidbyte.lib.errors import ConfigurationError, NativeThreadError


class NativeErrorFactory:
    """Builds the scrubbed, detailed NativeThreadError values of one call to one thread function."""

    def __init__(self, harness: NativeHarness, operation: NativeThreadOperation) -> None:
        self._harness = harness
        self._operation = operation
        self._label = native_threads.NATIVE_HARNESS_LABELS[harness]
        self._secrets: set[str] = set()
        self._redactor = HarnessRedactor()

    def register_secret(self, value: str) -> None:
        # @intent native-errors-scrub-injected-secrets
        # Every value the call injected (the caller's API key, the
        # inline opencode config that holds it) is replaced in all
        # vendor text, because a vendor may echo it back in an error.
        if isinstance(value, str) and value:
            self._secrets.add(value)

    def scrub(self, text: str) -> str:
        # @intent native-errors-redact-before-cap
        # Registered values go first, on the full text, so the cap
        # cannot cut one in half; then the shared redactor scrubs
        # credential assignments, and the last
        # NATIVE_VENDOR_MESSAGE_MAX_CHARS are kept, because a vendor
        # prints its final error last.
        limit = native_threads.NATIVE_VENDOR_MESSAGE_MAX_CHARS
        for secret in sorted(self._secrets, key=len, reverse=True):
            text = text.replace(secret, native_threads.NATIVE_REDACTED)
        return str(self._redactor.redact(text))[-limit:]

    @staticmethod
    def listing(items: Iterable[str]) -> str:
        # Joins names for a sentence, keeping the first
        # NATIVE_LISTING_MAX_ITEMS in their given order.
        kept = [str(item) for item in items][: native_threads.NATIVE_LISTING_MAX_ITEMS]
        return native_threads.NATIVE_LISTING_SEPARATOR.join(kept)

    def failure(
        self,
        problem: NativeThreadProblem,
        *,
        request: NativeThreadRequest | None,
        thread_id: str | None = None,
        outcome: CliOutcome | None = None,
        vendor_text: str | None = None,
        seconds: float | None = None,
        cap_bytes: int | None = None,
        missing_member: str | None = None,
        searched: str | None = None,
    ) -> NativeThreadError:
        # The code comes from the closed table of harness and problem,
        # so every code this builds is a FailureCode member.
        code = native_threads.NATIVE_THREAD_FAILURE_CODES[(self._harness, problem)]

        # The newest thread id the call learned wins over the caller's.
        newest_id = thread_id if thread_id is not None else (None if request is None else request.thread_id)

        # A timed-out run reports no exit code: the status then comes
        # from the tree stop, not from the vendor.
        exit_code = None if outcome is None or outcome.timed_out else outcome.exit_code

        # Every dynamic part is scrubbed here, and the vendor text is
        # also capped, before it goes anywhere; the helpers below only
        # format.
        workspace = None if request is None else self.scrub(str(request.workspace))
        shown_id = None if newest_id is None else self.scrub(newest_id)
        detail = None if searched is None else self.scrub(searched)
        vendor = None if vendor_text is None or not vendor_text.strip() else self.scrub(vendor_text.strip())

        # Say who failed, where, what the SDK saw and what the vendor
        # printed, in the INV-5 order; the factory adds the likely
        # cause and the next step written for the code.
        sentences = [
            native_threads.NATIVE_THREAD_SUMMARIES[problem].format(harness=self._label),
            *self._context_sentences(workspace, shown_id),
            *self._observed_sentences(problem, exit_code=exit_code, seconds=seconds, cap_bytes=cap_bytes, missing_member=missing_member, searched=detail),
        ]
        if vendor is not None:
            sentences.append(native_threads.NATIVE_VENDOR_TEXT_SENTENCE.format(vendor_text=vendor))
        return self._error(code, sentences, thread_id=newest_id, exit_code=exit_code, vendor_message=vendor)

    def from_configuration_error(self, exc: ConfigurationError, request: NativeThreadRequest | None) -> NativeThreadError:
        # A record or validator refusal names its argument in
        # details["field"]; its message is the SDK's own text, which
        # never quotes the key.
        argument = str(exc.details.get(native_threads.NATIVE_FIELD_DETAIL_KEY, native_threads.NATIVE_UNNAMED_ARGUMENT))
        thread_id = None if request is None else request.thread_id
        workspace = None if request is None else self.scrub(str(request.workspace))
        shown_id = None if thread_id is None else self.scrub(thread_id)
        sentences = [
            native_threads.NATIVE_INVALID_ARGUMENT_SUMMARY.format(harness=self._label),
            *self._context_sentences(workspace, shown_id),
            native_threads.NATIVE_INVALID_ARGUMENT_OBSERVATION.format(argument=self.scrub(argument), rule=self.scrub(exc.message)),
        ]
        return self._error(FailureCode.CONFIGURATION_INVALID_ARGUMENT, sentences, thread_id=thread_id)

    def from_unexpected(self, exc: Exception) -> NativeThreadError:
        # @intent native-errors-defects-name-only-the-class
        # A defect reports only the exception's class name; its text may
        # hold paths, payloads or secrets and is never copied into the
        # error.
        error_type = type(exc).__name__
        sentences = [
            native_threads.NATIVE_RUNTIME_ERROR_SUMMARY.format(harness=self._label),
            native_threads.NATIVE_RUNTIME_ERROR_OBSERVATION.format(error_type=error_type),
        ]
        return self._error(FailureCode.RUNTIME_ERROR, sentences, error_type=error_type)

    def from_launch_failure(self, failure: ProcessLaunchFailure, program: str, *, request: NativeThreadRequest, thread_id: str | None = None) -> NativeThreadError:
        # A missing executable means not installed; any other launch
        # failure means the operating system refused to start it.
        if failure is ProcessLaunchFailure.NOT_FOUND:
            problem, searched = NativeThreadProblem.NOT_INSTALLED, native_threads.NATIVE_SEARCHED_COMMAND.format(program=program)
        else:
            problem, searched = NativeThreadProblem.LAUNCH_FAILED, native_threads.NATIVE_LAUNCH_FAILURE_DETAIL.format(program=program, kind=failure.value)
        newest_id = thread_id if thread_id is not None else request.thread_id
        shown_id = None if newest_id is None else self.scrub(newest_id)
        sentences = [
            native_threads.NATIVE_THREAD_SUMMARIES[problem].format(harness=self._label),
            *self._context_sentences(self.scrub(str(request.workspace)), shown_id),
            *self._observed_sentences(problem, exit_code=None, seconds=None, cap_bytes=None, missing_member=None, searched=self.scrub(searched)),
        ]
        return self._error(native_threads.NATIVE_THREAD_FAILURE_CODES[(self._harness, problem)], sentences, thread_id=newest_id)

    @staticmethod
    def _context_sentences(workspace: str | None, thread_id: str | None) -> list[str]:
        # The scrubbed workspace and thread id, when the call knows them.
        sentences = []
        if workspace is not None:
            sentences.append(native_threads.NATIVE_WORKSPACE_SENTENCE.format(workspace=workspace))
        if thread_id is not None:
            sentences.append(native_threads.NATIVE_THREAD_ID_SENTENCE.format(thread_id=thread_id))
        return sentences

    def _observed_sentences(self, problem: NativeThreadProblem, *, exit_code: int | None, seconds: float | None, cap_bytes: int | None, missing_member: str | None, searched: str | None) -> list[str]:
        # What the SDK observed: the problem's own observation, then the
        # scrubbed launcher detail, the missing member and the exit
        # status that apply.
        version = native_threads.NATIVE_TESTED_VERSIONS[self._harness]
        sentences = [native_threads.NATIVE_THREAD_OBSERVATIONS[problem].format(harness=self._label, version=version, seconds=seconds, cap_bytes=cap_bytes)]
        if searched is not None:
            sentences.append(searched)
        if missing_member is not None:
            sentences.append(native_threads.NATIVE_MISSING_MEMBER_SENTENCE.format(member=missing_member))
        if exit_code is not None:
            sentences.append(native_threads.NATIVE_EXIT_STATUS_SENTENCE.format(exit_code=exit_code))
        return sentences

    def _error(self, code: FailureCode, sentences: list[str], *, thread_id: str | None = None, exit_code: int | None = None, vendor_message: str | None = None, error_type: str = "") -> NativeThreadError:
        # Puts the head first and the likely cause and next step last,
        # then builds the error with every INV-5 attribute.
        likely_cause = native_threads.NATIVE_THREAD_LIKELY_CAUSES[code]
        next_step = native_threads.NATIVE_THREAD_NEXT_STEPS[code]
        head = native_threads.NATIVE_MESSAGE_HEAD.format(operation=self._operation.value, code=code.value)
        tail = [native_threads.NATIVE_LIKELY_CAUSE_SENTENCE.format(likely_cause=likely_cause), native_threads.NATIVE_NEXT_STEP_SENTENCE.format(next_step=next_step)]
        message = native_threads.NATIVE_SENTENCE_SEPARATOR.join([head, *sentences, *tail])
        return NativeThreadError(
            message,
            failure_code=code,
            harness=self._harness,
            operation=self._operation,
            next_step=next_step,
            likely_cause=likely_cause,
            thread_id=thread_id,
            exit_code=exit_code,
            vendor_message=vendor_message,
            error_type=error_type,
        )


__all__ = ["NativeErrorFactory"]
