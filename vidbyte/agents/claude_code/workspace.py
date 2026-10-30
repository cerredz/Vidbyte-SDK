"""FILE: vidbyte/agents/claude_code/workspace.py

PURPOSE: Defines ClaudeCodeWorkspace, which owns the folders and files one ClaudeCodeHarnessAgent creates on disk: the working folder Claude Code runs in (the caller's, or one empty temporary folder made on the first run and kept for the agent's life) and, for each run, a private temporary file holding the instructions that --system-prompt-file reads.
ROLE IN CODEBASE: One instance per agent, built by ClaudeCodeHarnessAgent (agent.py), which calls ensure() and the instructions methods through asyncio.to_thread so the event loop never blocks on disk work, and close() when the caller is done with the agent.
ARCHITECTURE NOTE: Claude Code keys its transcripts by the working folder (~/.claude/projects/<folder key>/), so a resume finds the session only from the same folder; that is why the temporary folder is made once and reused rather than made per run. The instructions file lives in its own temporary folder, never in the workspace, so a caller's repository is left exactly as it was and the instructions never reach the command line, where 50 KB of text would pass the Windows limit.
COMMON MODIFICATION PATTERNS: Another per-run file Claude Code reads from disk (a settings or MCP config file) would get a write and remove pair here, in its own private folder, removed in the agent's finally block.
WHAT NOT TO DO IN THIS FILE: 1. Do not write into the caller's workspace. 2. Do not delete a folder the caller passed. 3. Do not log or quote the instructions.
KNOWN EDGE CASES: close() removes only the folder this class made, and after it the agent cannot resume, because the next run would start in a new folder. A removal that fails (a file held open on Windows) is ignored, because the folder is empty or private and leaving it costs nothing. mkdtemp makes the folders readable by the current user only on POSIX.
RELATED DOCS: docs/design/claude-code-harness-agent.md section 6.5; vidbyte/agents/claude_code/README.md
TESTS: tests/features/claude_code_agent/test_claude_code_agent.py
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from vidbyte.lib.constants.claude_code import (
    CLAUDE_CODE_INSTRUCTIONS_FILE_NAME,
    CLAUDE_CODE_INSTRUCTIONS_PREFIX,
    CLAUDE_CODE_TEXT_ENCODING,
    CLAUDE_CODE_WORKSPACE_PREFIX,
)


class ClaudeCodeWorkspace:
    """The working folder of one agent and the private instructions file of each run."""

    def __init__(self, folder: Path | None) -> None:
        self._given = folder
        self._made: Path | None = None

    @property
    def folder(self) -> Path | None:
        """The folder Claude Code runs in, or None before the first run when the agent makes its own."""
        return self._given if self._given is not None else self._made

    @property
    def owned(self) -> bool:
        """Whether the folder is the temporary one this agent made, not one the caller passed."""
        return self._given is None

    def ensure(self) -> Path:
        # @intent one-folder-per-agent-so-resume-finds-the-session
        # The caller's folder is used as is; otherwise one empty temporary
        # folder is made on the first run and kept, because Claude Code finds a
        # session only from the folder it ran in.
        if self._given is not None:
            return self._given
        if self._made is None:
            self._made = Path(tempfile.mkdtemp(prefix=CLAUDE_CODE_WORKSPACE_PREFIX))
        return self._made

    def close(self) -> None:
        """Remove the temporary folder this agent made; a caller's folder is never touched."""
        if self._made is not None:
            shutil.rmtree(self._made, ignore_errors=True)
            self._made = None

    @staticmethod
    def write_instructions(instructions: str) -> Path:
        # @intent instructions-travel-in-a-private-file
        # 52 KB instructions overflow the Windows command line, and argv is
        # visible to other local users, so the text goes in a file inside a
        # private temporary folder that the run removes afterwards.
        folder = Path(tempfile.mkdtemp(prefix=CLAUDE_CODE_INSTRUCTIONS_PREFIX))
        path = folder / CLAUDE_CODE_INSTRUCTIONS_FILE_NAME
        # newline="" writes the text verbatim, so Windows adds no carriage returns.
        path.write_text(instructions, encoding=CLAUDE_CODE_TEXT_ENCODING, newline="")
        return path

    @staticmethod
    def remove_instructions(path: Path) -> None:
        """Remove one run's private instructions folder and the file in it."""
        shutil.rmtree(path.parent, ignore_errors=True)


__all__ = ["ClaudeCodeWorkspace"]
