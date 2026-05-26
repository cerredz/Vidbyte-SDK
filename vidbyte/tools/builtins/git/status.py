"""Context Protocol Header

Description:
    Implements a git status tool via subprocess execution.
Purpose:
    Shows the working tree status in short format.
Architecture:
    - Function-based tool using @tool decorator.
    - Uses SubprocessGitBackend to run `git status --short`.
Relations:
    Related to vidbyte.lib.providers.git.subprocess_backend and vidbyte.tools.builtins.git.
"""

from __future__ import annotations

from vidbyte.lib.providers.git.subprocess_backend import SubprocessGitBackend
from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission


@tool(permission=ToolPermission.READ)
async def git_status(repo_path: str = ".") -> str:
    """Show the working tree status."""
    backend = SubprocessGitBackend()
    exit_code, stdout, stderr = await backend.run(repo_path, ["status", "--short"])
    if exit_code != 0:
        return f"Error ({exit_code}): {stderr.strip()}"
    if not stdout.strip():
        return "Working tree clean"
    return stdout.strip()
