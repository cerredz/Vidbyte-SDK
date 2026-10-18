"""FILE: vidbyte/lib/process/reaper.py

PURPOSE: Defines ProcessReaper, which kills every process whose command line carries a given marker and says how many it killed. The browser functions use it after each call to end the browser a tool server left behind: the marker is the call's own folder, which is on the browser's command line as its profile option.
ROLE IN CODEBASE: NativeBrowserTools.complete and .discard (vidbyte/harnesses/native/hostkit/browser.py) call ProcessReaper.reap with the per-call folder once the harness run is over, however it ended.
ARCHITECTURE NOTE: Canonical lib helper (AGENTS.md principle 5) beside CliRunner and ProcessStopper. A browser started by a tool server is not in the harness's process tree once the server's spawner exits, so a tree stop cannot reach it; only its command line ties it to the call (spec D-12). Every child starts through CliRunner with an argv tuple, never a shell. On Windows it runs the System32 PowerShell by its full path under SystemRoot (the C: drive's Windows folder when unset) with the fixed NATIVE_REAP_POWERSHELL_SCRIPT, which reads the marker from VIDBYTE_REAP_MARKER, so the marker is never on the reaper's own command line; PowerShell runs without USERPROFILE, because at start it creates an AppData Roaming folder under it, and without it Windows uses the profile of the user's logon token, so the reaper writes nothing. On POSIX it lists processes with ps from the first NATIVE_PS_PATHS entry that is a file, checked off the event loop and read through the native_threads constants module at call time, never from PATH, then sends SIGKILL to each match but itself. Every failure, timeout included, is a count of 0; only cancellation propagates.
FUNCTION INVENTORY: ProcessReaper.reap is the narrated main function; _powershell gives the System32 PowerShell path or None; _fixed_ps gives the first ps file or None; _windows_count reads the count PowerShell printed; _kill_marked kills the POSIX matches and counts them.
COMMON MODIFICATION PATTERNS: A new platform adds its own branch in reap with its program at a fixed path and its own counter helper; keep the never-raise rule.
WHAT NOT TO DO IN THIS FILE: 1. Do not put the marker on a child's command line; the reaper would match itself. Do not give PowerShell the caller's USERPROFILE; a redirected one would get an AppData folder. 2. Do not find ps or PowerShell through PATH or CliRunner.find_program; a test sandbox or a cloned repository can put a stand-in there. 3. Do not raise on a failed or timed-out reap; the caller is cleaning up after a call that may already be failing. 4. Do not import from vidbyte.harnesses or any layer above vidbyte.lib (lint A006).
KNOWN EDGE CASES: With no ps at any fixed path nothing is reaped and the count is 0 (spec EC-22). A process that ends between the listing and the kill is skipped, not counted. On POSIX a killed process the reaper does not own stays a zombie until its parent waits for it. On Windows only the processes PowerShell actually stopped are counted, so a second reap of the same marker counts 0.
RELATED DOCS: vidbyte/lib/README.md
TESTS: tests/features/harness_threads/test_harness_threads_browser_lifecycle.py
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import signal
import sys

from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.process import CliInvocation, CliOutcome
from vidbyte.lib.enums.native_threads import NativeEnvironmentVariable
from vidbyte.lib.process.runner import CliRunner


class ProcessReaper:
    """Kills every process whose command line carries a marker, counting the kills and never raising anything but cancellation."""

    @staticmethod
    async def reap(marker: str, *, timeout_seconds: float) -> int:
        """Kill every other process whose command line holds marker and return how many were killed; 0 on any failure."""
        # @intent reaper-never-raises-and-never-shows-its-marker
        # The reaper runs while a call is being cleaned up, often after
        # it failed, so a reap that cannot run or times out counts 0
        # instead of raising; and the marker never sits on its own
        # command line, where it would match itself.
        try:
            if sys.platform == "win32":
                # Windows: the System32 PowerShell stops the matches and
                # prints how many it stopped; it reads the marker from
                # its environment, and runs without USERPROFILE so that
                # starting it writes nothing into a redirected profile.
                program = ProcessReaper._powershell()
                if program is None:
                    return native_threads.NATIVE_REAP_NONE_COUNT
                invocation = CliInvocation(
                    argv=(program, *native_threads.NATIVE_POWERSHELL_ARGUMENTS, native_threads.NATIVE_REAP_POWERSHELL_SCRIPT),
                    env_overlay={NativeEnvironmentVariable.VIDBYTE_REAP_MARKER.value: marker},
                    env_remove=(native_threads.NATIVE_USER_PROFILE_VARIABLE,),
                    timeout_seconds=timeout_seconds,
                    max_output_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES,
                )
                return ProcessReaper._windows_count(await CliRunner().run(invocation))

            # POSIX: list every process with ps from a fixed path,
            # looked up off the event loop; no ps means nothing to reap.
            ps = await asyncio.to_thread(ProcessReaper._fixed_ps)
            if ps is None:
                return native_threads.NATIVE_REAP_NONE_COUNT
            invocation = CliInvocation(
                argv=(ps, *native_threads.NATIVE_PS_ARGUMENTS),
                env_overlay={},
                timeout_seconds=timeout_seconds,
                max_output_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES,
            )
            listing = await CliRunner().run(invocation)

            # Kill each listed process whose command line holds the
            # marker, except this one.
            return ProcessReaper._kill_marked(listing, marker)
        except Exception:
            # A defect in a cleanup step must not hide the call's own
            # outcome; nothing was reaped that can be counted.
            return native_threads.NATIVE_REAP_NONE_COUNT

    @staticmethod
    def _powershell() -> str | None:
        # The full path under SystemRoot, never a bare name; a root that
        # is not absolute starts nothing.
        root = os.environ.get(native_threads.NATIVE_SYSTEM_ROOT_VARIABLE) or native_threads.NATIVE_WINDOWS_DEFAULT_SYSTEM_ROOT
        return os.path.join(root, *native_threads.NATIVE_POWERSHELL_PATH_PARTS) if os.path.isabs(root) else None

    @staticmethod
    def _fixed_ps() -> str | None:
        # The first fixed ps path that is a file, read at call time.
        return next((path for path in native_threads.NATIVE_PS_PATHS if os.path.isfile(path)), None)

    @staticmethod
    def _windows_count(outcome: CliOutcome) -> int:
        # The script's last word is the number of processes it stopped.
        if outcome.exit_code != native_threads.NATIVE_SUCCESS_EXIT_CODE or outcome.timed_out:
            return native_threads.NATIVE_REAP_NONE_COUNT
        match = re.fullmatch(native_threads.NATIVE_REAP_COUNT_PATTERN, outcome.stdout)
        return int(match.group(1)) if match is not None else native_threads.NATIVE_REAP_NONE_COUNT

    @staticmethod
    def _kill_marked(listing: CliOutcome, marker: str) -> int:
        # Each ps line is "<pid> <command line>"; a process that is gone
        # or not ours to kill is skipped. The platform check keeps the
        # "win32" literal, as runner.py does, because type checkers
        # narrow on it, and signal.SIGKILL exists only off Windows.
        if sys.platform == "win32" or listing.exit_code != native_threads.NATIVE_SUCCESS_EXIT_CODE or listing.timed_out:
            return native_threads.NATIVE_REAP_NONE_COUNT
        killed = 0
        for line in listing.stdout.splitlines():
            pid_text, _, command_line = line.strip().partition(" ")
            if not pid_text.isdigit() or marker not in command_line or int(pid_text) == os.getpid():
                continue
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(int(pid_text), signal.SIGKILL)
                killed += 1
        return killed


__all__ = ["ProcessReaper"]
