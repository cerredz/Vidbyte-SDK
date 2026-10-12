"""FILE: vidbyte/agents/coding_context/environment.py

PURPOSE: Defines EnvironmentLoader, which gathers raw facts about the machine and the project into an EnvironmentContextItem for the ENVIRONMENT section of a CodingAgent's context window: the OS family and version, the CPU, the date and time zone, the root folder, its project files with the languages and package managers they imply, its declared dependencies and installed dependency folders, its git branch, which bash the bash tool runs, and what that bash finds on its PATH.
ROLE IN CODEBASE: Called once by CodingAgent.__init__ (vidbyte/agents/coding.py) with the validated CodingAgentSettings; returns a CodingContextSectionItem (vidbyte/lib/dataclasses/coding.py) whose EnvironmentContextItem (vidbyte/context/primitives/documents.py) CodingContextWindow (vidbyte/agents/coding_context/window.py) places after the AGENTS.md section. Uses EnvironmentProbe (environment_probe.py) for the one bash probe, ProjectDependencies (project_dependencies.py) for manifest names, BashTool.find_bash and BashTool.not_found_message (vidbyte/tools/builtins/bash.py) for the shell, and the marker tables in vidbyte/lib/constants/coding.py.
ARCHITECTURE NOTE: Plain deterministic code with no model involvement. This file only gathers; every word the model reads is written by EnvironmentContextItem. Everything but the probe comes from Python and file checks, and git is read from .git, so the cached probe does not depend on the root folder.
FUNCTION INVENTORY: EnvironmentLoader.load is the narrated main function; _os_family names the OS family; _shell_kind says whether bash is Git Bash; _linux_distribution reads the Linux distribution name; _project_files lists the marker files in the root; _labels maps those files to languages or package managers; _git_head reads the branch or commit from .git.
COMMON MODIFICATION PATTERNS: A new language, lockfile, build file, or dependency folder is one more entry in its table in vidbyte/lib/constants/coding.py. A new Python-side fact is one more field on EnvironmentContextItem, filled in load. A new tool is one more name in CODING_ENVIRONMENT_PROBE_SCRIPT.
WHAT NOT TO DO IN THIS FILE: 1. Do not gather environment-variable values, the user name, or the host name; they can hold secrets and do not help the model. 2. Do not raise for a missing bash, a failed probe, or an unreadable file; the section says what is missing instead. 3. Do not run git or any command outside EnvironmentProbe. 4. Do not write text for the model here; it belongs in EnvironmentContextItem.
KNOWN EDGE CASES: With no bash the probe is skipped and the item carries BashTool's install hint. The date is the date at construction. A worktree's .git file is followed to its git folder; a .git that cannot be read gives GitHeadState.UNREADABLE.
RELATED DOCS: docs/design/coding-agent-environment-context.md; vidbyte/agents/coding_context/README.md; vidbyte/agents/README.md (Coding Agent)
TESTS: tests/features/coding_agent/test_coding_agent_environment.py
"""

from __future__ import annotations

import contextlib
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from vidbyte.agents.coding_context.environment_probe import EnvironmentProbe
from vidbyte.agents.coding_context.project_dependencies import ProjectDependencies
from vidbyte.context.primitives import EnvironmentContextItem
from vidbyte.lib.constants.coding import (
    CODING_ENVIRONMENT_BUILD_FILES,
    CODING_ENVIRONMENT_DEPENDENCY_FOLDERS,
    CODING_ENVIRONMENT_LANGUAGE_MARKERS,
    CODING_ENVIRONMENT_PACKAGE_MANAGER_MARKERS,
)
from vidbyte.lib.dataclasses.coding import CodingAgentSettings, CodingContextSectionItem
from vidbyte.lib.enums.coding import CodingContextSection
from vidbyte.lib.enums.context import GitHeadState, OperatingSystemFamily, ShellKind
from vidbyte.tools.builtins.bash import BashTool


class EnvironmentLoader:
    """Gathers the machine's and the project's facts into the ENVIRONMENT context section."""

    @classmethod
    def load(cls, settings: CodingAgentSettings) -> CodingContextSectionItem | None:
        """Return the environment section for settings.root_dir, or None when the switch is off."""
        # A caller who turned the section off gets nothing, and no
        # process is started for it.
        if not settings.load_environment:
            return None
        root = Path(settings.root_dir)

        # Find the manifests, lockfiles, and build files in the root.
        # They tell the model the project's languages, its package
        # managers, and how it is built.
        files = cls._project_files(root)

        # Read the dependency names those manifests declare, so the
        # model knows the frameworks and test tools in play.
        dependencies = ProjectDependencies.read(root)

        # Read the git branch from .git, without running git.
        git_state, git_ref = cls._git_head(root)

        # Ask the bash the bash tool runs which tools and package
        # managers it finds on its own PATH. With no bash the probe is
        # skipped, and the install hint is kept to show instead.
        bash = BashTool.find_bash()
        probe = EnvironmentProbe.run(bash, root)

        # Hand every raw fact to the environment primitive, which owns
        # how they read to the model. On Windows the bash tool runs Git
        # Bash, and naming it stops the model writing PowerShell.
        item = EnvironmentContextItem(
            os_family=cls._os_family(),
            os_name=platform.platform(),
            os_distribution=cls._linux_distribution(),
            architecture=platform.machine() or None,
            cpu_count=os.cpu_count(),
            local_time=datetime.now(timezone.utc).astimezone(),
            cwd=str(root),
            project_files=files,
            languages=cls._labels(files, CODING_ENVIRONMENT_LANGUAGE_MARKERS),
            package_managers=cls._labels(files, CODING_ENVIRONMENT_PACKAGE_MANAGER_MARKERS),
            dependencies=dependencies,
            dependency_folders=tuple(name for name in CODING_ENVIRONMENT_DEPENDENCY_FOLDERS if (root / name).is_dir()),
            git_state=git_state,
            git_ref=git_ref,
            shell=bash,
            shell_kind=cls._shell_kind(bash),
            shell_error=BashTool.not_found_message() if bash is None else None,
            bash_version=probe.bash_version,
            uname=probe.uname,
            system_package_managers=probe.package_managers,
            tools=probe.tools,
            probe_error=probe.error,
        )
        return CodingContextSectionItem(section=CodingContextSection.ENVIRONMENT, item=item)

    @staticmethod
    def _os_family() -> OperatingSystemFamily:
        """Return the OS family this process runs on."""
        if sys.platform in ("win32", "cygwin", "msys"):
            return OperatingSystemFamily.WINDOWS
        if sys.platform == "darwin":
            return OperatingSystemFamily.MACOS
        return OperatingSystemFamily.LINUX if sys.platform.startswith("linux") else OperatingSystemFamily.OTHER

    @staticmethod
    def _shell_kind(bash: str | None) -> ShellKind | None:
        """Return Git Bash on Windows and plain bash elsewhere, or None when there is no bash."""
        if bash is None:
            return None
        return ShellKind.GIT_BASH if sys.platform == "win32" else ShellKind.BASH

    @staticmethod
    def _linux_distribution() -> str | None:
        """Return the Linux distribution's name, or None off Linux or when /etc/os-release cannot be read."""
        # The distribution tells the model which package manager the
        # system has (apt, dnf, apk).
        if not sys.platform.startswith("linux"):
            return None
        with contextlib.suppress(OSError):
            return platform.freedesktop_os_release().get("PRETTY_NAME") or None
        return None

    @staticmethod
    def _project_files(root: Path) -> tuple[str, ...]:
        """Return the language markers, lockfiles, and build files that are regular files directly in root."""
        names = (*(name for name, _ in CODING_ENVIRONMENT_LANGUAGE_MARKERS), *(name for name, _ in CODING_ENVIRONMENT_PACKAGE_MANAGER_MARKERS), *CODING_ENVIRONMENT_BUILD_FILES)
        return tuple(name for name in names if (root / name).is_file())

    @staticmethod
    def _labels(files: tuple[str, ...], markers: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
        """Return the labels markers gives the present files, each once, in table order."""
        return tuple(dict.fromkeys(label for name, label in markers if name in files))

    @staticmethod
    def _git_head(root: Path) -> tuple[GitHeadState, str | None]:
        """Return where root stands in git and its branch or commit, read from .git without running git."""
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
                return GitHeadState.UNREADABLE, None
            if head.startswith("ref: refs/heads/"):
                return GitHeadState.BRANCH, head.removeprefix("ref: refs/heads/")
            return (GitHeadState.DETACHED, head) if head else (GitHeadState.UNREADABLE, None)
        return GitHeadState.NOT_A_REPOSITORY, None


__all__ = ["EnvironmentLoader"]
