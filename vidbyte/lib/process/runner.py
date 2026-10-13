"""FILE: vidbyte/lib/process/runner.py

PURPOSE: Defines CliRunner, the canonical way to run one command-line program to completion with a time bound, capped output and no inherited standard input, and ProcessStopper, which stops a child's whole process tree (process group on POSIX, taskkill /T on Windows) and reaps it within a bound.
ROLE IN CODEBASE: CliRunner runs grok --version, grok models, the Grok one-shot and fork runs, and the Muse in-distro reap and WSL distro listing (vidbyte/harnesses/native/). ProcessStopper is also used by ManagedProcess (vidbyte/lib/process/managed.py) and by McpStdioTransport when stop_process_tree is set (vidbyte/tools/mcp/transport.py).
ARCHITECTURE NOTE: Canonical lib helper (AGENTS.md principle 5). Every failure is a field of the returned CliOutcome; only asyncio.CancelledError is raised, after the tree is stopped. Children start with start_new_session=True on POSIX so their process group id is their pid, which is what lets ProcessStopper reach grandchildren even after the leader exited. Timing constants are read through the native_hosts constants module at call time so tests can shrink them.
FUNCTION INVENTORY: CliRunner.run is the narrated main function; CliRunner.launch is the shared static launch that run and ManagedProcess.start use, returning the child or the launch failure; _feed_stdin writes stdin_text and closes the pipe; _drain reads one stream into a capped buffer while counting the rest; _finish_readers bounds and cancels the drain tasks; _outcome builds the CliOutcome. ProcessStopper.stop_tree is the narrated main function; _signal_group, _taskkill, _kill_leader, _bounded_wait and _close_pipes are its single-step helpers.
COMMON MODIFICATION PATTERNS: A new process option adds a CliInvocation field and its use in run or launch; keep the stop path in ProcessStopper so every caller gets it.
WHAT NOT TO DO IN THIS FILE: 1. Do not pass shell=True or build a command string; argv goes to create_subprocess_exec (lint S055). 2. Do not let a child inherit the caller's stdin; it is a pipe or DEVNULL. 3. Do not wait without a bound after a kill; a grandchild can hold the pipes open forever.
KNOWN EDGE CASES: On Windows, taskkill /T cannot reach a grandchild of a leader that already exited (Q-19). A program name is looked up through PATH and PATHEXT on Windows so .cmd shims start. Output is decoded as UTF-8 and trimmed to whole characters within max_output_bytes.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Process helpers, Standard input), D-4, D-21, D-23; vidbyte/lib/README.md
TESTS: tests/features/grok_host/test_grok_host_process_helpers.py
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
import sys

from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.process import CliInvocation, CliOutcome
from vidbyte.lib.enums.process import ProcessLaunchFailure

_TASKKILL_ARGUMENTS = ("taskkill", "/T", "/F", "/PID")


class ProcessStopper:
    """Stops a child's whole process tree and reaps it, never raising anything but cancellation."""

    @staticmethod
    async def stop_tree(process: asyncio.subprocess.Process, *, grace_seconds: float) -> int | None:
        # @intent stop-tree-always-reaches-the-group
        # The leader may already have exited while a grandchild in its group
        # still runs and holds the pipes, so the group is always signalled,
        # whatever returncode says. A cancellation part-way still sends the
        # KILL and closes the pipes in the finally block.
        finished = False
        try:
            if sys.platform == "win32":
                # Windows follows parent ids from the live leader to stop the tree.
                await ProcessStopper._taskkill(process.pid, grace_seconds)
            else:
                # Ask the whole group to stop, give it the grace period, then kill it.
                ProcessStopper._signal_group(process.pid, signal.SIGTERM)
                await ProcessStopper._bounded_wait(process, grace_seconds)
                ProcessStopper._signal_group(process.pid, signal.SIGKILL)
            # Kill the leader itself if it is somehow still running, then reap it within the bound.
            ProcessStopper._kill_leader(process)
            await ProcessStopper._bounded_wait(process, grace_seconds)
            finished = True
        finally:
            if not finished and sys.platform != "win32":
                ProcessStopper._signal_group(process.pid, signal.SIGKILL)
            if not finished:
                ProcessStopper._kill_leader(process)
            # Release our end of the pipes even if a grandchild still holds the other end.
            ProcessStopper._close_pipes(process)
        return process.returncode

    @staticmethod
    def _signal_group(pid: int, signal_number: int) -> None:
        # The group id is the leader's pid because every helper starts children in a new session; Windows has no process groups.
        if sys.platform == "win32":
            return
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pid, signal_number)

    @staticmethod
    async def _taskkill(pid: int, grace_seconds: float) -> None:
        # Runs taskkill /T /F with its own deadline; a taskkill that cannot start or hangs is skipped.
        try:
            killer = await asyncio.create_subprocess_exec(*_TASKKILL_ARGUMENTS, str(pid), stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        except OSError:
            return
        try:
            await asyncio.wait_for(killer.wait(), grace_seconds)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                killer.kill()
        finally:
            ProcessStopper._close_pipes(killer)

    @staticmethod
    def _kill_leader(process: asyncio.subprocess.Process) -> None:
        # Kills the leader directly while it has not been reaped.
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                process.kill()

    @staticmethod
    async def _bounded_wait(process: asyncio.subprocess.Process, seconds: float) -> None:
        # Waits for the exit at most seconds; Python 3.12+ also waits for the pipes here.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(process.wait(), seconds)

    @staticmethod
    def _close_pipes(process: asyncio.subprocess.Process) -> None:
        # Closes the subprocess transport; getattr degrades to a pipe leak on a Python without it.
        transport = getattr(process, "_transport", None)
        if transport is not None:
            with contextlib.suppress(PermissionError, ProcessLookupError, OSError, RuntimeError):
                transport.close()


class CliRunner:
    """Runs one command-line program to completion within its invocation's bounds."""

    async def run(self, invocation: CliInvocation) -> CliOutcome:
        # @intent cli-run-is-bounded-and-never-raises
        # A CLI run can hang, flood its output or leave a grandchild behind,
        # so every run is time-bounded, its output capped while still read to
        # the end, and its whole tree stopped on timeout or cancellation.
        # Failures are fields of the outcome; only cancellation propagates.
        # Start the program in its own session, with stdin as a pipe or the null device.
        stdin = asyncio.subprocess.PIPE if invocation.stdin_text is not None else asyncio.subprocess.DEVNULL
        process, launch_failure = await CliRunner.launch(invocation, stdin=stdin)
        if process is None:
            return CliOutcome(exit_code=None, stdout="", stderr="", stdout_truncated=False, stderr_truncated=False, timed_out=False, launch_failure=launch_failure)
        stdout, stderr = bytearray(), bytearray()
        readers = (
            asyncio.create_task(self._drain(process.stdout, stdout, invocation.max_output_bytes), name="cli-runner-stdout"),
            asyncio.create_task(self._drain(process.stderr, stderr, invocation.max_output_bytes), name="cli-runner-stderr"),
        )
        timed_out = False
        try:
            # Hand over the standard-input text, then read both streams to the end and wait for the exit, all within the time bound.
            async with asyncio.timeout(invocation.timeout_seconds):
                await self._feed_stdin(process, invocation.stdin_text)
                await asyncio.wait(readers)
                await process.wait()
        except TimeoutError:
            # The run passed its bound: stop and reap the whole tree, keeping the output read so far.
            timed_out = True
            await ProcessStopper.stop_tree(process, grace_seconds=native_host_constants.NATIVE_KILL_WAIT_SECONDS)
        except asyncio.CancelledError:
            # The caller gave up: stop and reap the tree before the cancellation goes on.
            await ProcessStopper.stop_tree(process, grace_seconds=native_host_constants.NATIVE_KILL_WAIT_SECONDS)
            await self._finish_readers(readers)
            raise
        # Collect whatever the readers still hold, then report the outcome.
        await self._finish_readers(readers)
        return self._outcome(process, stdout, stderr, invocation.max_output_bytes, timed_out)

    @staticmethod
    async def launch(invocation: CliInvocation, *, stdin: int) -> tuple[asyncio.subprocess.Process | None, ProcessLaunchFailure | None]:
        # @intent process-launch-is-shared-and-never-inherits-stdin
        # The one way a helper here starts a child. stdin is a pipe or
        # the null device, never the caller's stream, which a child
        # could read and so corrupt a stdio MCP session. Windows looks
        # the program up through PATH and PATHEXT so a .cmd shim
        # starts; POSIX puts the child in a new session so
        # ProcessStopper reaches its whole group. A failed launch is
        # returned, never raised.
        program, *arguments = invocation.argv
        if sys.platform == "win32":
            program = shutil.which(program) or program
        try:
            process = await asyncio.create_subprocess_exec(
                program,
                *arguments,
                stdin=stdin,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=invocation.cwd,
                env=dict(invocation.env),
                start_new_session=sys.platform != "win32",
            )
        except FileNotFoundError:
            return None, ProcessLaunchFailure.NOT_FOUND
        except PermissionError:
            return None, ProcessLaunchFailure.PERMISSION_DENIED
        except (OSError, ValueError):
            return None, ProcessLaunchFailure.OS_ERROR
        return process, None

    async def _feed_stdin(self, process: asyncio.subprocess.Process, stdin_text: str | None) -> None:
        # Writes the text and closes the pipe so the child reads to EOF; a child that exits early is not an error.
        if process.stdin is None:
            return
        with contextlib.suppress(BrokenPipeError, ConnectionResetError, OSError):
            if stdin_text is not None:
                process.stdin.write(stdin_text.encode("utf-8"))
                await process.stdin.drain()
            process.stdin.close()

    async def _drain(self, stream: asyncio.StreamReader | None, buffer: bytearray, limit_bytes: int) -> None:
        # Keeps the first limit_bytes plus a one-byte truncation probe and reads past them until EOF, so the child never blocks on a full pipe.
        if stream is None:
            return
        with contextlib.suppress(OSError, ValueError):
            while chunk := await stream.read(native_host_constants.NATIVE_PROCESS_READ_CHUNK_BYTES):
                buffer.extend(chunk[: limit_bytes + native_host_constants.NATIVE_PROCESS_TRUNCATION_PROBE_BYTES - len(buffer)])

    async def _finish_readers(self, readers: tuple[asyncio.Task[None], ...]) -> None:
        # Gives the readers one kill-wait to reach EOF, then cancels any that a surviving grandchild keeps open.
        _done, pending = await asyncio.wait(readers, timeout=native_host_constants.NATIVE_KILL_WAIT_SECONDS)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.wait(pending)

    def _outcome(self, process: asyncio.subprocess.Process, stdout: bytearray, stderr: bytearray, limit_bytes: int, timed_out: bool) -> CliOutcome:
        # Decodes each stream within the byte cap, trimming a partly kept character.
        out_text = bytes(stdout[:limit_bytes]).decode("utf-8", errors="replace").encode("utf-8")[:limit_bytes].decode("utf-8", errors="ignore")
        err_text = bytes(stderr[:limit_bytes]).decode("utf-8", errors="replace").encode("utf-8")[:limit_bytes].decode("utf-8", errors="ignore")
        return CliOutcome(
            exit_code=process.returncode,
            stdout=out_text,
            stderr=err_text,
            stdout_truncated=len(stdout) > limit_bytes,
            stderr_truncated=len(stderr) > limit_bytes,
            timed_out=timed_out,
            launch_failure=None,
        )


__all__ = ["CliRunner", "ProcessStopper"]
