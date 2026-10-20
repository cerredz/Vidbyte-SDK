"""FILE: vidbyte/harnesses/native/hostkit/launcher.py

PURPOSE: Defines NativeLauncher, the one way the thread functions find the program to start: an explicit <harness>_command, then the program on PATH, then a fallback install path, refusing a Windows batch launcher wherever it is found.
ROLE IN CODEBASE: Called by GrokThreadRun (grok/threads.py), GrokHelperRun and GrokCommandRun (grok/helpers.py, grok/commands.py), OpencodeThreadRun and OpencodeHelperRun (opencode/threads.py, opencode/helpers.py) and MuseLauncher (muse/launcher.py) before anything is written or started, with the call's NativeThreadRequest or NativeHelperRequest; it raises the NativeThreadError that NativeErrorFactory (hostkit/errors.py) builds.
ARCHITECTURE NOTE: Synchronous and read-only: it looks at PATH and at the fallback file and never writes. The platform and every name it compares come from vidbyte/lib/constants/native_threads.py (spec INV-15). Programs are found by CliRunner.find_program, the lookup CliRunner itself launches with: the absolute PATH folders (with PATHEXT on Windows) and never the current folder, so a program a cloned repository ships under a vendor's name never runs (spec T-6), and on Windows the batch check sees the file that would really run.
FUNCTION INVENTORY: resolve is the narrated main function; _is_batch says whether a program is a Windows batch file.
COMMON MODIFICATION PATTERNS: A new harness passes its program name and, when its installer has one, its fallback path; the order and the batch refusal stay here.
WHAT NOT TO DO IN THIS FILE: 1. Do not return a .cmd or .bat launcher on Windows; cmd.exe re-reads its arguments as a command line and would run parts of a prompt. 2. Do not check an explicit command on POSIX; a missing or non-executable file is reported when the launch fails. 3. Do not write anything.
KNOWN EDGE CASES: Windows drops trailing dots and spaces from a file name and ignores letter case, so "grok.CMD. " is still a batch file. A batch file found on PATH falls through to the fallback install before it is refused. An explicit command that Windows cannot find is kept as given, and its launch then fails as not installed.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_launcher.py, tests/features/harness_threads/test_harness_threads_helper_bounds.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from vidbyte.harnesses.native.hostkit.errors import NativeErrorFactory
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    NativeHelperRequest,
    NativeThreadRequest,
)
from vidbyte.lib.enums.native_threads import NativeThreadProblem
from vidbyte.lib.process import CliRunner


class NativeLauncher:
    """Finds the launcher of one vendor program, or raises not installed or launcher refused."""

    @staticmethod
    def resolve(command: tuple[str, ...] | None, *, program: str, fallback: Path | None, errors: NativeErrorFactory, request: NativeThreadRequest | NativeHelperRequest) -> tuple[str, ...]:
        # @intent native-launcher-resolution-order
        # An explicit command wins, otherwise the program on PATH, then
        # the fallback install. A batch file is never returned on
        # Windows, because cmd.exe re-reads the argv and would run parts
        # of a prompt as commands.
        if command is not None:
            # Windows looks the explicit program up as a launch would;
            # POSIX starts it as given.
            first, *rest = command
            if sys.platform == native_threads.NATIVE_WINDOWS_PLATFORM:
                first = CliRunner.find_program(first) or first
            if NativeLauncher._is_batch(first):
                raise errors.failure(NativeThreadProblem.LAUNCHER_REFUSED, request=request, searched=native_threads.NATIVE_REFUSED_LAUNCHER.format(program=first))
            return (first, *rest)

        # Look in the PATH folders, never the current folder; a batch
        # hit there is set aside so the fallback install gets its
        # chance first.
        found = CliRunner.find_program(program)
        refused = found if found is not None and NativeLauncher._is_batch(found) else None
        if refused is not None:
            found = None
        if found is None and fallback is not None and fallback.is_file():
            found = str(fallback)
        if found is not None:
            return (found,)

        # Nothing runnable: name the refused batch file, or everything
        # that was searched.
        if refused is not None:
            raise errors.failure(NativeThreadProblem.LAUNCHER_REFUSED, request=request, searched=native_threads.NATIVE_REFUSED_LAUNCHER.format(program=refused))
        if fallback is None:
            searched = native_threads.NATIVE_SEARCHED_PATH.format(program=program)
        else:
            searched = native_threads.NATIVE_SEARCHED_PATH_AND_FALLBACK.format(program=program, fallback=fallback)
        raise errors.failure(NativeThreadProblem.NOT_INSTALLED, request=request, searched=searched)

    @staticmethod
    def _is_batch(program: str) -> bool:
        # A Windows batch file, named as Windows reads the name:
        # trailing dots and spaces dropped, the suffix in any letter
        # case. On POSIX a file named grok.cmd is an ordinary program.
        name = program.rstrip(native_threads.NATIVE_WINDOWS_DROPPED_TAIL).casefold()
        return sys.platform == native_threads.NATIVE_WINDOWS_PLATFORM and name.endswith(native_threads.NATIVE_BATCH_SUFFIXES)


__all__ = ["NativeLauncher"]
