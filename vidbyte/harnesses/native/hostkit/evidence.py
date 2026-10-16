"""FILE: vidbyte/harnesses/native/hostkit/evidence.py

PURPOSE: Defines NativeCommandEvidence, the one check a Grok command or a Muse skill function makes before it returns: the record of the run it just made must show the vendor really ran the command (a named tool call, an agent name, or a fragment of the run's transcript), or the call raises command_not_run with the new thread's id.
ROLE IN CODEBASE: Called by GrokCommandRun (grok/commands.py) with the run's streaming tool calls, its summary.json agent_name or its grok export transcript, and by MuseCommandRun (muse/commands.py) with the thread's session/read tool calls or, after compaction, its muse export transcript (spec INV-8, D-28, D-33).
ARCHITECTURE NOTE: The check fails closed: no matching record means the command did not run, because a vendor that does not expand a slash command or a skill answers it as plain text and still exits 0 (spec EC-41). Tool arguments are compared after every run of backslashes becomes "/", so a Windows path names the same file as a POSIX one. The module holds no literals of its own (spec INV-15).
FUNCTION INVENTORY: NativeCommandEvidence.require looks for a call to one of the given tools, optionally with a fragment in its arguments; require_value compares one recorded value with the expected one; require_text looks for a fragment in a transcript. _seen lists the distinct tool names a run called, for the detail.
COMMON MODIFICATION PATTERNS: A new kind of evidence is one more require_* method raising the same command_not_run failure with its own detail text from vidbyte/lib/constants/native_threads.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not return on missing evidence; every path without a match raises. 2. Do not match the fragment as a pattern; it is literal text. 3. Do not import a harness subpackage (spec INV-20).
KNOWN EDGE CASES: A run that called no tool at all says so in the detail. The detail lists at most NATIVE_LISTING_MAX_ITEMS tool names, in the order the run first called them.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_grok_commands.py, tests/features/harness_threads/test_harness_threads_muse_commands.py
"""

from __future__ import annotations

import re

from vidbyte.harnesses.native.hostkit.errors import NativeErrorFactory
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import NativeThreadRequest, NativeToolCall
from vidbyte.lib.enums.native_threads import NativeThreadProblem


class NativeCommandEvidence:
    """The check that the record of a command run shows the vendor really ran the command."""

    @staticmethod
    def require(calls: tuple[NativeToolCall, ...], *, tools: tuple[str, ...], fragment: str | None, errors: NativeErrorFactory, request: NativeThreadRequest, thread_id: str) -> None:
        # @intent evidence-fails-closed
        # The command ran only when the run called one of its tools,
        # with the fragment in the arguments when one is given; Windows
        # backslash paths are folded to "/" first. Anything else is
        # command_not_run on the new thread.
        for call in calls:
            folded = re.sub(native_threads.NATIVE_BACKSLASH_RUN_PATTERN, native_threads.NATIVE_FORWARD_SLASH, call.arguments)
            if call.name in tools and (fragment is None or fragment in folded):
                return
        named = errors.listing(tools)
        seen = NativeCommandEvidence._seen(calls, errors)
        if fragment is None:
            detail = native_threads.NATIVE_EVIDENCE_TOOLS_DETAIL.format(tools=named, seen=seen)
        else:
            detail = native_threads.NATIVE_EVIDENCE_FRAGMENT_DETAIL.format(tools=named, fragment=fragment, seen=seen)
        raise errors.failure(NativeThreadProblem.COMMAND_NOT_RUN, request=request, thread_id=thread_id, searched=detail)

    @staticmethod
    def require_value(actual: str | None, *, expected: str, member: str, errors: NativeErrorFactory, request: NativeThreadRequest, thread_id: str) -> None:
        # The run's own record must hold exactly the expected value,
        # such as the agent name Grok wrote for an agent run.
        if actual == expected:
            return
        if actual is None:
            detail = native_threads.NATIVE_EVIDENCE_NO_VALUE_DETAIL.format(member=member, expected=expected)
        else:
            detail = native_threads.NATIVE_EVIDENCE_VALUE_DETAIL.format(actual=actual, member=member, expected=expected)
        raise errors.failure(NativeThreadProblem.COMMAND_NOT_RUN, request=request, thread_id=thread_id, searched=detail)

    @staticmethod
    def require_text(document: str, *, fragment: str, errors: NativeErrorFactory, request: NativeThreadRequest, thread_id: str) -> None:
        # The run's own transcript must contain the fragment literally.
        if fragment in document:
            return
        detail = native_threads.NATIVE_EVIDENCE_TEXT_DETAIL.format(fragment=fragment)
        raise errors.failure(NativeThreadProblem.COMMAND_NOT_RUN, request=request, thread_id=thread_id, searched=detail)

    @staticmethod
    def _seen(calls: tuple[NativeToolCall, ...], errors: NativeErrorFactory) -> str:
        # The distinct tool names the run called, in first-call order,
        # or a plain statement that it called none.
        names = list(dict.fromkeys(call.name for call in calls))
        return errors.listing(names) if names else native_threads.NATIVE_NO_TOOLS_SEEN


__all__ = ["NativeCommandEvidence"]
