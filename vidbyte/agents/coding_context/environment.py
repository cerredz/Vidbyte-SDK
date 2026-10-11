"""FILE: vidbyte/agents/coding_context/environment.py

PURPOSE: Defines EnvironmentLoader, which gathers a short block of facts about the machine into the ENVIRONMENT section of a CodingAgent's context window: the OS, the CPU, today's date and time zone, the root folder, its project marker files, its git branch, which bash the bash tool runs, and the common tools that bash finds on its PATH.
ROLE IN CODEBASE: Called once by CodingAgent.__init__ (vidbyte/agents/coding.py) with the validated CodingAgentSettings; returns a CodingContextSectionText (vidbyte/lib/dataclasses/coding.py) that CodingContextWindow (vidbyte/agents/coding_context/window.py) places after the AGENTS.md section. Finds bash with BashTool._find_bash (vidbyte/tools/builtins/bash.py) and reads its script, limits, and marker list from vidbyte/lib/constants/coding.py.
ARCHITECTURE NOTE: Plain deterministic code with no model involvement. Everything but the tool list comes from Python and file checks; the tool list comes from one `bash -c` probe run with the bash tool's own executable, so it shows what the model's bash will find. The probe writes to a temporary file, not a pipe, so on Windows a killed launcher whose child still holds the output cannot hang the read. Its result is cached for the process by bash path and PATH; git is read from .git so the probe does not depend on the root folder.
FUNCTION INVENTORY: EnvironmentLoader.load is the narrated main function; _host_lines gives the OS, CPU, date, and root lines; _marker_line lists the project marker files; _git_line reads the branch from .git; _shell_line says which bash runs commands; _run_probe runs the probe into a temporary file and says why it failed; _read_output reads that file up to the cap; _probe_lines turns the output into lines and adds the failure line.
COMMON MODIFICATION PATTERNS: A new tool to report is one more name in CODING_ENVIRONMENT_PROBE_SCRIPT; a new marker file is one more name in CODING_ENVIRONMENT_PROJECT_MARKERS. A new Python-side fact is one more line in _host_lines.
WHAT NOT TO DO IN THIS FILE: 1. Do not show environment-variable values, the user name, or the host name; they can hold secrets and do not help the model. 2. Do not raise for a missing bash or a failed probe; the section says what failed instead. 3. Do not read the probe's output through a pipe. 4. Do not run git or any other command outside the one probe.
KNOWN EDGE CASES: With no bash the probe is skipped and the shell line says how to install it. On a timeout, subprocess.run kills bash, the lines printed so far are kept, and on Windows only Git's launcher is killed, so a hanging tool may keep running. A failed probe is cached too, so a hanging tool costs the time limit once per process. A relative PATH entry is resolved against the root folder of the first agent that ran the probe. The date is the date at construction.
RELATED DOCS: docs/design/coding-agent-environment-context.md; vidbyte/agents/coding_context/README.md; vidbyte/agents/README.md (Coding Agent)
TESTS: tests/features/coding_agent/test_coding_agent_environment.py
"""

from __future__ import annotations

import contextlib
import os
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

from vidbyte.lib.constants.coding import (
    CODING_ENVIRONMENT_PROBE_MAX_BYTES,
    CODING_ENVIRONMENT_PROBE_SCRIPT,
    CODING_ENVIRONMENT_PROBE_TIMEOUT_SECONDS,
    CODING_ENVIRONMENT_PROJECT_MARKERS,
)
from vidbyte.lib.dataclasses.coding import CodingAgentSettings, CodingContextSectionText
from vidbyte.lib.enums.coding import CodingContextSection
from vidbyte.tools.builtins.bash import BashTool

# Probe output and failure reason by (bash path, PATH value), so one
# probe serves every agent in the process.
_PROBE_RESULTS: dict[tuple[str, str], tuple[str, str | None]] = {}


class EnvironmentLoader:
    """Gathers the machine's OS, date, root folder, git branch, shell, and tools into the ENVIRONMENT context section."""

    @classmethod
    def load(cls, settings: CodingAgentSettings) -> CodingContextSectionText | None:
        """Return the environment section for settings.root_dir, or None when the switch is off."""
        # A caller who turned the section off gets nothing, and no
        # process is started for it.
        if not settings.load_environment:
            return None
        root = Path(settings.root_dir)

        # Start with what Python knows without running anything: the
        # OS, the CPU, today's date, and the root folder. Models do not
        # know today's date on their own.
        lines = cls._host_lines(root)

        # Name the lockfiles and build files in the root, which tell
        # the model which package manager to use, and the git branch.
        lines.append(cls._marker_line(root))
        lines.append(cls._git_line(root))

        # Say which bash the bash tool runs. On Windows that is Git
        # Bash, and saying so stops the model writing PowerShell.
        bash = BashTool._find_bash()
        lines.append(cls._shell_line(bash))

        # Ask that same bash which tools it finds on its own PATH, and
        # their versions. The answer is kept for the rest of the
        # process, since tools do not change during a run. A failed
        # probe still keeps what it printed and says it failed; it
        # never raises.
        if bash is not None:
            key = (bash, os.environ.get("PATH", ""))
            if key not in _PROBE_RESULTS:
                # @intent probe-output-goes-to-a-file
                # After a timeout, subprocess.run waits for a pipe to
                # close with no limit. On Windows only Git's launcher is
                # killed and its child keeps a pipe open, so the probe
                # writes to a temporary file instead.
                with tempfile.TemporaryFile() as output:
                    failure = cls._run_probe(bash, root, output)
                    _PROBE_RESULTS[key] = (cls._read_output(output), failure)
            lines.extend(cls._probe_lines(*_PROBE_RESULTS[key]))
        content = "\n".join(["Facts about the machine this agent runs on, gathered when the agent was built.", *lines])
        return CodingContextSectionText(section=CodingContextSection.ENVIRONMENT, title="Environment", content=content)

    @staticmethod
    def _host_lines(root: Path) -> list[str]:
        """Return the OS, CPU, date, and root folder lines, using Python only."""
        system = platform.platform()
        # On Linux the distribution tells the model which package
        # manager the system has (apt, dnf, apk).
        if sys.platform.startswith("linux"):
            with contextlib.suppress(OSError):
                system += f" ({platform.freedesktop_os_release().get('PRETTY_NAME', 'unknown distribution')})"
        now = datetime.now(timezone.utc).astimezone()
        return [
            f"- Operating system: {system}",
            f"- CPU: {platform.machine() or 'unknown architecture'}, {os.cpu_count() or 'unknown number of'} logical cores",
            f"- Today's date: {now:%Y-%m-%d} (time zone {now.tzname()}, UTC{now:%z})",
            f"- Root folder: {root}",
        ]

    @staticmethod
    def _marker_line(root: Path) -> str:
        """Return the line naming the project marker files present in root."""
        present = [name for name in CODING_ENVIRONMENT_PROJECT_MARKERS if (root / name).is_file()]
        return f"- Project files in the root folder: {', '.join(present) if present else 'none of the usual lockfiles or build files'}"

    @staticmethod
    def _git_line(root: Path) -> str:
        """Return whether root is inside a git repository and its branch, read from .git without running git."""
        for folder in (root, *root.parents):
            dot_git = folder / ".git"
            if not dot_git.exists():
                continue
            # @intent git-is-read-from-files-not-the-probe
            # A worktree's .git is a file naming the real git folder.
            # Reading files keeps the cached probe independent of the
            # root folder.
            try:
                git_dir = dot_git if dot_git.is_dir() else folder / dot_git.read_text(encoding="utf-8").removeprefix("gitdir:").strip()
                head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
            except (OSError, ValueError):
                return "- Git: inside a git repository; its branch could not be read."
            if head.startswith("ref: refs/heads/"):
                return f"- Git: inside a git repository, on branch {head.removeprefix('ref: refs/heads/')}."
            return f"- Git: inside a git repository, detached at commit {head}."
        return "- Git: not inside a git repository."

    @staticmethod
    def _shell_line(bash: str | None) -> str:
        """Return the line saying which bash runs commands, or that there is none and how to fix it."""
        if bash is None:
            fix = "install Git for Windows" if sys.platform == "win32" else "install bash"
            return f"- Shell: bash was not found, so the bash tool will fail; {fix}."
        if sys.platform == "win32":
            return f"- Shell: the bash tool runs Git Bash (MSYS) from {bash}. Write POSIX shell commands, not PowerShell or cmd. Windows paths appear as /c/Users/... inside bash."
        return f"- Shell: the bash tool runs {bash}."

    @staticmethod
    def _run_probe(bash: str, root: Path, output: IO[bytes]) -> str | None:
        """Run the probe script in root with its output going to output, and return why it failed, or None."""
        try:
            completed = subprocess.run([bash, "-c", CODING_ENVIRONMENT_PROBE_SCRIPT], cwd=root, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.DEVNULL, timeout=CODING_ENVIRONMENT_PROBE_TIMEOUT_SECONDS, check=False)
        except subprocess.TimeoutExpired:
            return f"bash did not finish within {CODING_ENVIRONMENT_PROBE_TIMEOUT_SECONDS:g} seconds"
        except OSError as exc:
            return f"bash could not start ({type(exc).__name__})"
        return f"bash exited with code {completed.returncode}" if completed.returncode else None

    @staticmethod
    def _read_output(output: IO[bytes]) -> str:
        """Return what the probe wrote to output, up to the cap, decoded as UTF-8."""
        output.seek(0)
        return output.read(CODING_ENVIRONMENT_PROBE_MAX_BYTES).decode("utf-8", errors="replace")

    @staticmethod
    def _probe_lines(output: str, failure: str | None) -> list[str]:
        """Return the probe's non-blank output lines, followed by the failure line when the probe failed."""
        lines = [line.rstrip() for line in output.replace("\r", "").split("\n") if line.strip()]
        if failure is not None:
            lines.append(f"- Tool probe failed: {failure}. The tool list above may be incomplete.")
        return lines


__all__ = ["EnvironmentLoader"]
