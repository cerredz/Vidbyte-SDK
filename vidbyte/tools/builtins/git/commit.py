"""Context Protocol Header

Description:
    Implements git add and commit tools via subprocess execution.
Purpose:
    Stages and records changes to the repository.
Architecture:
    - Function-based tools using @tool decorator.
    - Uses SubprocessGitBackend to run git add and commit commands.
Relations:
    Related to vidbyte.lib.providers.git.subprocess_backend and vidbyte.tools.builtins.git.
"""

from __future__ import annotations

from vidbyte.lib.providers.git.subprocess_backend import SubprocessGitBackend
from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission


@tool(permission=ToolPermission.WRITE)
async def git_add(repo_path: str, files: list[str]) -> str:
    """Add file contents to the index."""
    backend = SubprocessGitBackend()
    exit_code, stdout, stderr = await backend.run(repo_path, ["add"] + files)
    if exit_code != 0:
        return f"Error ({exit_code}): {stderr.strip()}"
    return stdout.strip() or "Files staged successfully"


@tool(permission=ToolPermission.WRITE)
async def git_commit(repo_path: str, message: str) -> str:
    """Record changes to the repository."""
    backend = SubprocessGitBackend()
    exit_code, stdout, stderr = await backend.run(repo_path, ["commit", "-m", message])
    if exit_code != 0:
        return f"Error ({exit_code}): {stderr.strip()}"
    return stdout.strip() or "Commit successful"
