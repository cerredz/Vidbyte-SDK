"""FILE: vidbyte/tools/builtins/bash.py

PURPOSE: Defines BashTool, a minimal unsandboxed tool that runs one model-supplied command per call as `bash -c <command>` in a fresh process started in a root folder, and returns the combined output and the exit code.
ROLE IN CODEBASE: Exported by vidbyte/tools/builtins/__init__.py, preloaded by vidbyte/agents/coding.py (CodingAgent), and executed by vidbyte/agents/runtime.py after the agent's PermissionPolicy allows EXECUTE.
ARCHITECTURE NOTE: The command reaches bash through asyncio.create_subprocess_exec as one argv item, never a shell string; bash runs in its own session (POSIX process group) with stdin closed and stderr merged into stdout. One time limit, BASH_TIMEOUT_SECONDS, covers reading the output to its end and waiting for the exit; only the first BASH_MAX_OUTPUT_BYTES are kept and the rest is read and counted. On timeout or cancellation the command is stopped (POSIX: the whole process group is killed), the wait for exit after the kill is bounded by BASH_KILL_GRACE_SECONDS, and the subprocess transport is closed, so every call returns. A command that finishes on its own is never killed. The four BASH_* constants are read as module globals at call time.
FUNCTION INVENTORY: BashTool.__init__ resolves the root and the executable once; _find_bash picks the executable per OS; spec declares the model-facing contract; validate_call requires a non-blank command string; execute is the narrated main function; _spawn starts bash; _collect reads the bounded output and waits for the exit; _stop kills, waits within the grace bound, and closes the pipe; _render builds the completed-command result.
COMMON MODIFICATION PATTERNS: Change a bound by editing its BASH_* constant here; add a new stop path by routing it through _stop so the kill, the bounded wait, and the pipe close stay together; keep execute's helpers flat (none calls another).
WHAT NOT TO DO IN THIS FILE: 1. No shell=True, asyncio.create_subprocess_shell, or os.system. 2. No SandboxTransport; the tool is unsandboxed by the user's decision. 3. No environment filtering; commands inherit the parent environment. 4. No persistent shell session between calls. 5. No unbounded process.wait(); every wait sits under BASH_TIMEOUT_SECONDS or BASH_KILL_GRACE_SECONDS.
KNOWN EDGE CASES: On Windows the bash on PATH can be the WSL launcher, so only Git for Windows' bin/bash.exe found next to git is used. On Windows the kill stops only Git's bash launcher, so a timed-out or cancelled command may keep running after the call returns. On POSIX a descendant that leaves the process group (setsid) survives the group kill. A background process that still holds the output pipe makes the call wait for the time limit, where it is killed. Python 3.12+ Process.wait() returns only after every pipe closes, which is why both waits are bounded. When a stop leaves such an orphan, the parent still closes its end of the pipe before the call returns.
RELATED DOCS: docs/spec/coding-agent/spec.md (INV-9 to INV-15, INV-25, INV-26; D-10 to D-15, D-17 to D-19); vidbyte/tools/README.md
TESTS: tests/features/coding_agent/test_bash_tool_contract.py and tests/features/coding_agent/test_bash_tool_process_bounds.py
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
import sys
from pathlib import Path

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)

BASH_TIMEOUT_SECONDS = 600.0
BASH_MAX_OUTPUT_BYTES = 50_000
BASH_READ_CHUNK_BYTES = 65_536
BASH_KILL_GRACE_SECONDS = 5.0


class BashTool(BaseTool):
    """Runs one bash command per call in a fresh process started in the root folder."""

    def __init__(self, root_dir: str | Path) -> None:
        # Resolves the root and the bash executable once; a missing bash is reported per call, never raised here.
        self.root_dir = Path(root_dir).resolve()
        self._executable = self._find_bash()

    @staticmethod
    def _find_bash() -> str | None:
        """Return the bash executable this platform should run, or None when there is none."""
        # @intent windows-bash-is-git-for-windows
        # On Windows the bash found on PATH is often the WSL launcher (System32 or WindowsApps), which fails when WSL is
        # not set up, or Git's usr/bin/bash.exe, which cannot find ls or grep when Python was started from PowerShell.
        # Only Git for Windows' bin/bash.exe, one or two folders above the resolved git, is trusted there; searching three
        # parents covers git in cmd/, bin/, and mingw64/bin/. Falling back to the PATH bash would bring the WSL failure back.
        if sys.platform != "win32":
            return shutil.which("bash")
        git = shutil.which("git")
        if git is None:
            return None
        candidates = (folder / "bin" / "bash.exe" for folder in Path(git).resolve().parents[:3])
        return next((str(candidate) for candidate in candidates if candidate.is_file()), None)

    def spec(self) -> ToolSpec:
        """Declare the bash tool, its single command parameter, and its EXECUTE permission."""
        return ToolSpec(
            name="bash",
            description=(
                f"Runs one command in a fresh bash process that starts in the agent's root folder and returns what the command printed. Changes of directory and shell variables do not carry over from one call to the next, and the command is not confined to the root folder. Standard output and standard error come back together in the order they were written, and only the first {BASH_MAX_OUTPUT_BYTES:,} bytes are kept, so filter a long output or write it to a file and read that file in parts. The exit code of the command is always the last line of the result. A command that has not finished after {BASH_TIMEOUT_SECONDS:g} seconds is stopped, and standard input is closed, so anything that waits for typed input sees end of file at once. A background process must redirect both its standard output and its standard error to a file, otherwise the call waits for the time limit and the process is killed."
            ),
            parameters=(
                ToolParameter(
                    name="command",
                    type="string",
                    description=(
                        "The bash command line to run, passed to bash exactly as written. It may use pipes, redirections, conditionals, loops, and any other bash syntax. It runs in a new process that starts in the root folder every time. It must be a non-empty string, and it must not wait for input from a keyboard."
                    ),
                    required=True,
                ),
            ),
            permission=ToolPermission.EXECUTE,
        )

    def validate_call(self, call: ToolCall) -> str | None:
        """Return a validation error unless the call carries a non-blank command string."""
        missing = super().validate_call(call)
        if missing is not None:
            return missing
        command = call.arguments["command"]
        if not isinstance(command, str) or not command.strip():
            return "The bash command must be a non-empty string."
        return None

    async def execute(self, call: ToolCall) -> ToolResult:
        """Run one command and return its output and exit code, or a classified error."""
        command = str(call.arguments["command"])

        # Without a usable bash there is nothing to run, so tell the model how the developer can fix it.
        executable = self._executable
        if executable is None:
            hint = "Install Git for Windows and put git on PATH; this tool runs the bin/bash.exe that Git for Windows installs." if sys.platform == "win32" else "Install bash and put it on PATH."
            return ToolResult.error(self.name, f"bash was not found. {hint}", metadata={"error": "bash_not_found"})

        # Start bash in the root folder; a command the operating system refuses to start comes back as an error result.
        process = await self._spawn(executable, command)
        if isinstance(process, ToolResult):
            return process

        # Read the output and wait for the exit under one time limit, so a command that never ends cannot hang the run.
        buffer = bytearray()
        try:
            omitted, exit_code = await asyncio.wait_for(self._collect(process, buffer), BASH_TIMEOUT_SECONDS)
        except TimeoutError:
            # At the limit, stop the command and show the model what it printed so far, and whether that was cut.
            await self._stop(process)
            truncated = len(buffer) >= BASH_MAX_OUTPUT_BYTES
            marker = f"\n[output truncated at {BASH_MAX_OUTPUT_BYTES:,} bytes]" if truncated else ""
            stopped = f"\n[command stopped: it did not finish within the {BASH_TIMEOUT_SECONDS:g}-second time limit]"
            text = buffer.decode("utf-8", errors="replace")
            return ToolResult.error(self.name, text + marker + stopped, metadata={"error": "timeout", "truncated": truncated})
        except asyncio.CancelledError:
            # A cancelled call still stops the command before the cancellation moves on.
            await self._stop(process)
            raise

        # The command finished on its own: report its output and exit code, and kill nothing.
        return self._render(buffer, omitted, exit_code)

    async def _spawn(self, executable: str, command: str) -> asyncio.subprocess.Process | ToolResult:
        """Start `bash -c command` in the root folder, or return a spawn_failed result."""
        # @intent argv-exec-in-its-own-session
        # The command reaches bash as a single argv item through exec, so no second shell re-parses quotes, `$`, or `;`
        # and lint S055 holds. start_new_session makes bash the leader of its own process group, which is what lets _stop
        # kill everything the command started. stdin is the null device so a command that reads input cannot hang the call.
        # OSError and ValueError (NUL byte, argument list too long) become a spawn_failed result naming only the exception
        # class, because the exception text can carry paths or the command itself (S017).
        try:
            return await asyncio.create_subprocess_exec(
                executable,
                "-c",
                command,
                cwd=self.root_dir,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            return ToolResult.error(self.name, f"bash could not start this command ({type(exc).__name__}). Shorten the command or remove NUL characters from it.", metadata={"error": "spawn_failed"})

    async def _collect(self, process: asyncio.subprocess.Process, buffer: bytearray) -> tuple[int, int]:
        """Read the output into buffer up to the cap, count the rest, and return (bytes not kept, exit code)."""
        # @intent one-limit-over-reading-and-waiting
        # Reading to the end of the output and waiting for the exit run as one step, so the caller's single wait_for bounds
        # both: a command that closes its output and keeps running would otherwise block process.wait() for as long as it
        # runs. Only the first BASH_MAX_OUTPUT_BYTES are kept; everything after is still read and counted so the command is
        # never blocked on a full pipe and memory stays bounded. The read loop holds no numeric literal (A007).
        omitted = 0
        output = process.stdout
        while output is not None and (chunk := await output.read(BASH_READ_CHUNK_BYTES)):
            kept = chunk[: BASH_MAX_OUTPUT_BYTES - len(buffer)]
            buffer.extend(kept)
            omitted += len(chunk) - len(kept)
        return omitted, await process.wait()

    async def _stop(self, process: asyncio.subprocess.Process) -> None:
        """Kill the command, wait at most BASH_KILL_GRACE_SECONDS for the exit, and close the subprocess transport."""
        # @intent stop-kills-waits-briefly-and-closes-the-pipe
        # Runs only on timeout or cancellation, never after a normal completion, and never raises, because an exception
        # here would replace a propagating CancelledError. On POSIX the group is killed even when bash itself has already
        # exited, since a background child can still hold the output; ProcessLookupError means the group is already empty.
        # On Windows only Git's launcher can be killed. The wait after the kill is bounded because a process the kill cannot
        # reach (a setsid descendant, the command behind Git's launcher) keeps the pipe open, and Python 3.12+ waits for the
        # pipe. Closing the transport last releases the parent's end of the pipe; without it a long-lived service leaks one
        # pipe per timed-out command and asyncio.run reports "Event loop is closed" at shutdown. getattr keeps mypy clean
        # and degrades to that documented leak on a Python without the private attribute instead of raising.
        with contextlib.suppress(ProcessLookupError):
            if sys.platform != "win32":
                os.killpg(process.pid, signal.SIGKILL)
            elif process.returncode is None:
                process.kill()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(process.wait(), BASH_KILL_GRACE_SECONDS)
        transport = getattr(process, "_transport", None)
        if transport is not None:
            transport.close()

    def _render(self, buffer: bytearray, omitted: int, exit_code: int) -> ToolResult:
        """Build the success result: the kept output, a note on what was cut, and the exit code as the last line."""
        text = buffer.decode("utf-8", errors="replace")
        note = f"\n[output truncated: {omitted:,} bytes not shown]" if omitted else ""
        return ToolResult.success(self.name, f"{text}{note}\nexit code: {exit_code}", metadata={"exit_code": exit_code, "truncated": bool(omitted)})


__all__ = ["BashTool"]
