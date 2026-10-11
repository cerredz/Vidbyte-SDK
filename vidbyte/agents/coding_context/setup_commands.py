"""FILE: vidbyte/agents/coding_context/setup_commands.py

PURPOSE: Defines SetupCommandsLoader, which runs a CodingAgent's setup commands (such as uv sync or npm ci) once, in order, before the agent starts, and puts a short pass/fail note in the SETUP_RESULTS section of its context window, so the environment is ready before turn one and the model sees any failure in its first request.
ROLE IN CODEBASE: Called once by CodingAgent.__init__ (vidbyte/agents/coding.py) with the validated CodingAgentSettings; returns a CodingContextSectionText (vidbyte/lib/dataclasses/coding.py) that CodingContextWindow (vidbyte/agents/coding_context/window.py) places after the system prompt. Reuses BashTool's bash lookup, its not-found message, and its BASH_* time limits from vidbyte/tools/builtins/bash.py, and reads its output caps from vidbyte/lib/constants/coding.py.
ARCHITECTURE NOTE: Construction blocks while the commands run, up to BASH_TIMEOUT_SECONDS each. Each command runs as `bash -c <command>` through the synchronous subprocess module, because CodingAgent.__init__ is synchronous and may be called inside a running event loop. Output goes to an unnamed temporary file, not a pipe, so a background process that keeps the output open cannot hang construction, and a huge output costs disk, not memory. The first failure stops the run, and nothing here raises for a command's outcome, so the model sees the failure and can fix it.
FUNCTION INVENTORY: SetupCommandsLoader.load is the narrated main function; _run runs one command and kills it at the time limit; _output_tail reads the capped end of a failed command's output; _section builds the section record.
COMMON MODIFICATION PATTERNS: Change the tail caps in vidbyte/lib/constants/coding.py. The per-command time limit is the bash tool's BASH_TIMEOUT_SECONDS, read at call time, so both change together.
WHAT NOT TO DO IN THIS FILE: 1. No shell=True; the command reaches bash as one argv item (S055). 2. Do not raise for a failed, timed-out, or unstartable command; the failure belongs in the section. 3. Do not use asyncio.run; the constructor may already be inside a running loop. 4. Do not show a passing command's output. 5. Do not copy BashTool's Windows bash lookup; call BashTool.find_bash.
KNOWN EDGE CASES: On Windows a timeout kills only Git's bash launcher, so the command may keep running after construction returns; on POSIX a descendant that leaves the process group (setsid) survives the group kill. A background process the command started (`server &`) keeps running, and the loader does not wait for it. The byte cap can cut the first shown line or a character in it (shown as U+FFFD). A command that cannot start (a removed root folder, a NUL character) is a failure that names only the exception class. A BaseAgent keyword error, such as a missing name, is raised after the commands ran, because sections load before BaseAgent.__init__.
RELATED DOCS: docs/design/coding-agent-setup-commands.md; vidbyte/agents/coding_context/README.md; vidbyte/agents/README.md (Coding Agent)
TESTS: tests/features/coding_agent/test_coding_agent_setup_commands.py
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import BinaryIO

import vidbyte.tools.builtins.bash as bash_tool
from vidbyte.lib.constants.coding import (
    CODING_SETUP_OUTPUT_TAIL_BYTES,
    CODING_SETUP_OUTPUT_TAIL_LINES,
)
from vidbyte.lib.dataclasses.coding import CodingAgentSettings, CodingContextSectionText
from vidbyte.lib.enums.coding import CodingContextSection


class SetupCommandsLoader:
    """Runs the setup commands once, in order, stopping at the first failure, into the SETUP_RESULTS context section."""

    @classmethod
    def load(cls, settings: CodingAgentSettings) -> CodingContextSectionText | None:
        """Run settings.setup_commands in settings.root_dir and return their results section, or None when there are none."""
        # With no setup commands, nothing runs and no section is added.
        commands = settings.setup_commands
        if not commands:
            return None
        root = Path(settings.root_dir)

        # Use the same bash the agent's bash tool runs. Without one,
        # nothing can run, so the model is told why and how to fix it.
        executable = bash_tool.BashTool.find_bash()
        if executable is None:
            listed = "\n".join(f"{number}. `{command}`: not run" for number, command in enumerate(commands, start=1))
            return cls._section(f"These commands were meant to run in {root} before this conversation started, but none of them ran. {bash_tool.BashTool.not_found_message()}\n{listed}")

        # Run the commands in order. After a failure, later commands
        # usually depend on the one that failed, so they are not
        # started and are listed as not run.
        lines: list[str] = []
        failed = False
        for number, command in enumerate(commands, start=1):
            if failed:
                lines.append(f"{number}. `{command}`: not run, because an earlier command failed")
                continue

            # Each command writes into its own temporary file, which is
            # deleted once its line is written.
            with tempfile.TemporaryFile() as output:
                passed, outcome = cls._run(executable, command, root, output)
                tail = "" if passed else cls._output_tail(output)

            # A passing command gets one short line. A failed one also
            # shows the end of its output, where the error usually is.
            if passed:
                lines.append(f"{number}. `{command}`: passed ({outcome})")
            elif tail:
                lines.append(f"{number}. `{command}`: FAILED ({outcome}). Last lines of its output:\n{tail}")
            else:
                lines.append(f"{number}. `{command}`: FAILED ({outcome}), with no output.")
            failed = not passed
        return cls._section(f"These commands ran in {root} before this conversation started:\n" + "\n".join(lines))

    @staticmethod
    def _run(executable: str, command: str, root: Path, output: BinaryIO) -> tuple[bool, str]:
        """Run `bash -c command` in root, writing into output, and return whether it passed and a short outcome."""
        # @intent setup-command-subprocess-is-bounded
        # The command reaches bash as one argv item, so no second shell
        # re-parses it. stdin is the null device, so a command that
        # waits for input cannot hang construction. On POSIX bash leads
        # its own process group, so a timeout can kill everything the
        # command started.
        limit = bash_tool.BASH_TIMEOUT_SECONDS
        started = time.monotonic()
        try:
            process = subprocess.Popen([executable, "-c", command], cwd=root, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        except (OSError, ValueError) as exc:
            # Name only the exception class: its text can carry paths
            # or the command itself (S017).
            return False, f"could not start: {type(exc).__name__}"
        try:
            exit_code = process.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            # Kill the whole group on POSIX, or Git's launcher on
            # Windows, then wait only briefly for the exit.
            with contextlib.suppress(ProcessLookupError, PermissionError):
                if sys.platform != "win32":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=bash_tool.BASH_KILL_GRACE_SECONDS)
            return False, f"timed out after {limit:g} s"
        return exit_code == 0, f"exit {exit_code}, {time.monotonic() - started:.1f} s"

    @staticmethod
    def _output_tail(output: BinaryIO) -> str:
        """Return the last output lines, at most the line cap taken from at most the byte cap, each indented by three spaces."""
        size = output.seek(0, os.SEEK_END)
        output.seek(max(0, size - CODING_SETUP_OUTPUT_TAIL_BYTES))
        text = output.read().decode("utf-8", errors="replace")
        lines = text.rstrip().splitlines()[-CODING_SETUP_OUTPUT_TAIL_LINES:]
        return "\n".join(f"   {line}" for line in lines)

    @staticmethod
    def _section(content: str) -> CodingContextSectionText:
        """Return the SETUP_RESULTS section record holding content."""
        return CodingContextSectionText(section=CodingContextSection.SETUP_RESULTS, title="Setup command results", content=content)


__all__ = ["SetupCommandsLoader"]
