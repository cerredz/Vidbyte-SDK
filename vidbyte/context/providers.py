"""Context Protocol Header

Description:
    Dynamic context providers that inject run-time environment information into
    the agent system prompt without consuming tool calls.
Purpose:
    Gives agents awareness of the current date/time, OS, Python version, git
    branch, and top-level repository structure at the start of every session.
Architecture:
    - ContextProvider: ABC requiring a single provide() async method.
    - DateTimeProvider: Emits current date, time, and day of the week.
    - EnvironmentProvider: Emits OS, Python, shell, and working directory.
    - GitStatusProvider: Emits the current git branch if available.
    - RepoStructureProvider: Emits a compact tree of the repository root.
Relations:
    Related to vidbyte.context.manager for dynamic context injection.
"""

from __future__ import annotations

import asyncio
import os
import platform
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path


class ContextProvider(ABC):
    """Injects dynamic context into system prompt without consuming tool calls."""

    @abstractmethod
    async def provide(self) -> str:
        """Return a string to inject into the agent's system context."""
        ...


class DateTimeProvider(ContextProvider):
    """Provides the current local date, time, and day of the week."""

    async def provide(self) -> str:
        now = datetime.now()
        return (
            f"Current date: {now.strftime('%Y-%m-%d')}\n"
            f"Current time: {now.strftime('%H:%M:%S')}\n"
            f"Day of week: {now.strftime('%A')}"
        )


class EnvironmentProvider(ContextProvider):
    """Provides OS, Python version, shell, and working directory."""

    async def provide(self) -> str:
        shell = os.environ.get("SHELL", os.environ.get("COMSPEC", "unknown"))
        return (
            f"OS: {platform.system()} {platform.release()}\n"
            f"Python: {platform.python_version()}\n"
            f"Shell: {shell}\n"
            f"Working directory: {Path.cwd()}"
        )


class GitStatusProvider(ContextProvider):
    """Provides the current git branch name if the working directory is a repo."""

    async def provide(self) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "branch",
                "--show-current",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            branch = stdout.decode().strip()
            if branch:
                return f"Current git branch: {branch}"
        except Exception:
            pass
        return ""


class RepoStructureProvider(ContextProvider):
    """Provides a summary of the top-level repository structure."""

    async def provide(self) -> str:
        root = Path.cwd()
        if not (root / ".git").exists():
            return ""

        items: list[str] = []
        for p in sorted(root.iterdir()):
            if p.name.startswith(".") and p.name != ".git":
                continue
            if p.is_dir():
                items.append(f"  {p.name}/")
            elif p.suffix in {".py", ".md", ".toml", ".cfg", ".json", ".yaml", ".yml", ".txt"}:
                items.append(f"  {p.name}")
            else:
                items.append(f"  {p.name}")

        if len(items) > 50:
            items = items[:50] + ["  ..."]

        if not items:
            return ""

        return "Repository structure:\n" + "\n".join(items)


__all__ = [
    "ContextProvider",
    "DateTimeProvider",
    "EnvironmentProvider",
    "GitStatusProvider",
    "RepoStructureProvider",
]
