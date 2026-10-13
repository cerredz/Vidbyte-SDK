"""FILE: vidbyte/lib/process/managed.py

PURPOSE: Defines ManagedProcess, the canonical way to start a long-running child (a local server), wait for the stdout line that says it is ready, keep draining its output so it never blocks, and stop its whole tree exactly once.
ROLE IN CODEBASE: Used by OpencodeServer (vidbyte/harnesses/native/opencode/server.py) to own `opencode serve`. Stops through ProcessStopper in vidbyte/lib/process/runner.py.
ARCHITECTURE NOTE: Canonical lib helper (AGENTS.md principle 5). The child always gets DEVNULL as stdin and starts in its own session on POSIX. start never raises except cancellation (after stopping the child); a launch failure, an early exit or a timeout is a field of the ProcessStartOutcome. stdout is read in chunks and split into lines here, so one very long line cannot break the reader.
FUNCTION INVENTORY: ManagedProcess.start is the narrated main function; _launch starts the child or reports a launch failure; _watch_stdout finds the ready line and then keeps draining; _drain_stderr keeps a bounded stderr tail; _settle waits for the ready line, the exit or the deadline; exit_code reports the reaped exit code; stop stops the tree once and returns the exit code.
COMMON MODIFICATION PATTERNS: A new readiness rule changes _watch_stdout only; a new stop rule belongs in ProcessStopper so CliRunner and the transport get it too.
WHAT NOT TO DO IN THIS FILE: 1. Do not give the child the caller's stdin or invocation.stdin_text; a server reads nothing. 2. Do not stop reading stdout or stderr after the ready line; a full pipe would block the server. 3. Do not wait unbounded after a kill.
KNOWN EDGE CASES: A child that closes stdout but keeps running is waited for until the deadline. stop on a process that never started returns None; a second stop returns the first result without signalling again.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Process helpers, Standard input), FR-18, D-4
TESTS: tests/features/grok_host/test_grok_host_process_helpers.py, tests/features/opencode_host/test_opencode_host_owned_server.py
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import shutil
import sys

from vidbyte.lib.constants import native_hosts as native_host_constants
from vidbyte.lib.dataclasses.process import CliInvocation, ProcessStartOutcome
from vidbyte.lib.enums.process import ProcessLaunchFailure
from vidbyte.lib.process.runner import ProcessStopper

_READ_CHUNK_BYTES = 65536
_LINE_BREAK = b"\n"


class ManagedProcess:
    """One long-running child: started once, watched until ready, drained while it runs, stopped once."""

    def __init__(self, invocation: CliInvocation) -> None:
        self._invocation = invocation
        self._process: asyncio.subprocess.Process | None = None
        self._ready: asyncio.Future[str | None] | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_tail = bytearray()
        self._stopped = False

    @property
    def exit_code(self) -> int | None:
        # The reaped exit code, or None while running or when the process never started.
        return None if self._process is None else self._process.returncode

    async def start(self, ready_pattern: re.Pattern[str]) -> ProcessStartOutcome:
        # @intent managed-start-is-bounded-and-never-raises
        # A server that never prints its ready line, or dies at boot, must
        # end the start within the invocation's timeout with the reason in
        # the outcome; a cancelled start stops the child before propagating.
        # Start the child with the null device as stdin, in its own session.
        failure = await self._launch()
        if self._process is None:
            return ProcessStartOutcome(ready_line=None, launch_failure=failure, exit_code=None, timed_out=False, stderr_tail="")
        # Watch stdout for the ready line while stderr drains into a bounded tail.
        self._ready = asyncio.get_running_loop().create_future()
        self._stdout_task = asyncio.create_task(self._watch_stdout(ready_pattern), name="managed-process-stdout")
        self._stderr_task = asyncio.create_task(self._drain_stderr(), name="managed-process-stderr")
        try:
            # Wait for the ready line, an exit, or the deadline, whichever comes first.
            ready_line, timed_out = await self._settle()
        except asyncio.CancelledError:
            await self.stop()
            raise
        return ProcessStartOutcome(
            ready_line=ready_line,
            launch_failure=None,
            exit_code=None if ready_line is not None else self.exit_code,
            timed_out=timed_out,
            stderr_tail=self._stderr_tail.decode("utf-8", errors="replace"),
        )

    async def stop(self) -> int | None:
        # Stops the whole tree once, gives the drain tasks one kill-wait, and returns the exit code.
        if self._process is None or self._stopped:
            return self.exit_code
        self._stopped = True
        await ProcessStopper.stop_tree(self._process, grace_seconds=native_host_constants.NATIVE_KILL_WAIT_SECONDS)
        tasks = [task for task in (self._stdout_task, self._stderr_task) if task is not None]
        if tasks:
            _done, pending = await asyncio.wait(tasks, timeout=native_host_constants.NATIVE_KILL_WAIT_SECONDS)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.wait(pending)
        return self.exit_code

    async def _launch(self) -> ProcessLaunchFailure | None:
        # @intent managed-child-never-inherits-stdin
        # A server child gets the null device as stdin, so it can never read
        # a stdio MCP client's stream; invocation.stdin_text is ignored.
        program, *arguments = self._invocation.argv
        if sys.platform == "win32":
            program = shutil.which(program) or program
        try:
            self._process = await asyncio.create_subprocess_exec(
                program,
                *arguments,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._invocation.cwd,
                env=dict(self._invocation.env),
                start_new_session=sys.platform != "win32",
            )
        except FileNotFoundError:
            return ProcessLaunchFailure.NOT_FOUND
        except PermissionError:
            return ProcessLaunchFailure.PERMISSION_DENIED
        except (OSError, ValueError):
            return ProcessLaunchFailure.OS_ERROR
        return None

    async def _watch_stdout(self, ready_pattern: re.Pattern[str]) -> None:
        # Splits stdout into lines until one matches, then keeps reading to EOF so the pipe never fills.
        process, ready = self._process, self._ready
        if process is None or process.stdout is None or ready is None:
            return
        pending = bytearray()
        with contextlib.suppress(OSError, ValueError):
            while chunk := await process.stdout.read(_READ_CHUNK_BYTES):
                if ready.done():
                    continue
                pending.extend(chunk)
                *lines, rest = pending.split(_LINE_BREAK)
                pending = bytearray(rest[-self._invocation.max_output_bytes:])
                matched = next((line for line in (item.decode("utf-8", errors="replace").rstrip("\r") for item in lines) if ready_pattern.search(line)), None)
                if matched is not None:
                    ready.set_result(matched)
        if not ready.done():
            ready.set_result(None)

    async def _drain_stderr(self) -> None:
        # Keeps only the newest max_output_bytes of stderr for error reports.
        process = self._process
        if process is None or process.stderr is None:
            return
        with contextlib.suppress(OSError, ValueError):
            while chunk := await process.stderr.read(_READ_CHUNK_BYTES):
                self._stderr_tail.extend(chunk)
                del self._stderr_tail[: max(0, len(self._stderr_tail) - self._invocation.max_output_bytes)]

    async def _settle(self) -> tuple[str | None, bool]:
        # Returns (ready line, timed out); an early exit returns (None, False) once stderr has been read.
        process, ready = self._process, self._ready
        if process is None or ready is None:
            return None, False
        try:
            async with asyncio.timeout(self._invocation.timeout_seconds):
                ready_line = await asyncio.shield(ready)
                if ready_line is not None:
                    return ready_line, False
                await process.wait()
        except TimeoutError:
            return None, True
        if self._stderr_task is not None:
            await asyncio.wait({self._stderr_task}, timeout=native_host_constants.NATIVE_KILL_WAIT_SECONDS)
        return None, False


__all__ = ["ManagedProcess"]
