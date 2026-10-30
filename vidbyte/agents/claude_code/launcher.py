"""FILE: vidbyte/agents/claude_code/launcher.py

PURPOSE: Defines ClaudeCodeLauncher, which finds the `claude` executable one run starts: the settings' claude_bin when it names a file, a bare claude_bin or `claude` looked up in the PATH folders, and never a Windows batch launcher. It raises ClaudeCodeAgentError(NOT_INSTALLED) naming what it searched when nothing runnable is found.
ROLE IN CODEBASE: Called by ClaudeCodeHarnessAgent.arun (agent.py) before any folder or file is written, with the run's ClaudeCodeFailures (failures.py). The lookup is CliRunner.find_program from vidbyte/lib/process/runner.py, the same lookup CliRunner launches with, so the file checked here is the file that runs.
ARCHITECTURE NOTE: Synchronous and read-only. It applies the native harness launcher rules (vidbyte/harnesses/native/hostkit/launcher.py: PATH folders only, never the current folder; batch files refused on Windows) without that class, because NativeLauncher raises the native-thread error type and this agent's contract fixes ClaudeCodeAgentError.
COMMON MODIFICATION PATTERNS: A new install location to search would be added here after PATH, as NativeLauncher's fallback; none is searched today because the contract says None means `claude` on PATH.
WHAT NOT TO DO IN THIS FILE: 1. Do not return a .cmd or .bat file on Windows; cmd.exe re-reads its arguments as a command line, so text inside the JSON schema could run as commands. 2. Do not use shutil.which on Windows: on Python 3.11 it searches the current folder first. 3. Do not write anything.
KNOWN EDGE CASES: An npm install of Claude Code on Windows puts claude.cmd on PATH; it is refused with a message pointing at the native installer or claude_bin. Windows drops trailing dots and spaces from a file name, so "claude.CMD. " is still a batch file. An explicit path that exists but cannot run is reported by the launch itself, as NOT_INSTALLED too.
RELATED DOCS: docs/design/claude-code-harness-agent.md section 6.6; vidbyte/agents/claude_code/README.md
TESTS: tests/features/claude_code_agent/test_claude_code_failures.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from vidbyte.agents.claude_code.failures import ClaudeCodeFailures
from vidbyte.lib.constants.claude_code import (
    CLAUDE_CODE_PROGRAM,
    CLAUDE_CODE_WINDOWS_PLATFORM,
)
from vidbyte.lib.constants.native_threads import (
    NATIVE_BATCH_SUFFIXES,
    NATIVE_WINDOWS_DROPPED_TAIL,
)
from vidbyte.lib.enums.claude_code import ClaudeCodeFailureKind
from vidbyte.lib.process import CliRunner


class ClaudeCodeLauncher:
    """Finds the claude executable for one run, or raises NOT_INSTALLED."""

    @staticmethod
    def resolve(claude_bin: Path | None, failures: ClaudeCodeFailures) -> tuple[str, ...]:
        # @intent claude-is-found-on-path-and-never-runs-as-a-batch-file
        # The settings' path wins; a bare name and the default are looked up
        # only in the PATH folders, as CliRunner launches them. A Windows
        # batch file is refused wherever it came from, because cmd.exe would
        # re-read the command line and could run text from it.
        name = CLAUDE_CODE_PROGRAM if claude_bin is None else str(claude_bin)
        explicit = claude_bin is not None and bool(os.path.dirname(name))
        found = name if explicit and Path(name).is_file() else None
        if not explicit:
            found = CliRunner.find_program(name)

        # Nothing runnable: say exactly what was searched.
        if found is None:
            searched = f"the file {name}" if explicit else f"the PATH folders for {name}"
            raise failures.failure(ClaudeCodeFailureKind.NOT_INSTALLED, f"Claude Code could not be found: this SDK searched {searched} and found no file to run.")

        # A batch launcher on Windows is refused, never started.
        if ClaudeCodeLauncher._is_batch(found):
            raise failures.failure(ClaudeCodeFailureKind.NOT_INSTALLED, f"Claude Code was found only as the Windows batch launcher {found}, which this SDK will not start because cmd.exe re-reads its arguments; install the native Claude Code build (claude.exe) or pass claude_bin pointing at it.")
        return (found,)

    @staticmethod
    def _is_batch(program: str) -> bool:
        # A Windows batch file, named as Windows reads the name: trailing dots
        # and spaces dropped, the suffix in any letter case.
        name = program.rstrip(NATIVE_WINDOWS_DROPPED_TAIL).casefold()
        return sys.platform == CLAUDE_CODE_WINDOWS_PLATFORM and name.endswith(NATIVE_BATCH_SUFFIXES)


__all__ = ["ClaudeCodeLauncher"]
