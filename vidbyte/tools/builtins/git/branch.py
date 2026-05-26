"""Context Protocol Header

Description:
    Implements git branch and checkout tools via subprocess execution.
Purpose:
    Lists, creates, and switches branches.
Architecture:
    - Function-based tools using @tool decorator.
    - Uses SubprocessGitBackend to run git branch and checkout commands.
Relations:
    Related to vidbyte.lib.providers.git.subprocess_backend and vidbyte.tools.builtins.git.
"""

from __future__ import annotations

from vidbyte.lib.providers.git.subprocess_backend import SubprocessGitBackend
from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission


@tool(permission=ToolPermission.READ)
async def git_branch_list(repo_path: str = ".") -> str:
    """List all branches."""
    backend = SubprocessGitBackend()
    exit_code, stdout, stderr = await backend.run(repo_path, ["branch", "-a"])
    if exit_code != 0:
        return f"Error ({exit_code}): {stderr.strip()}"
    if not stdout.strip():
        return "(no branches)"
    return stdout.strip()


@tool(permission=ToolPermission.WRITE)
async def git_branch_create(repo_path: str, branch_name: str) -> str:
    """Create a new branch."""
    backend = SubprocessGitBackend()
    exit_code, stdout, stderr = await backend.run(repo_path, ["branch", branch_name])
    if exit_code != 0:
        return f"Error ({exit_code}): {stderr.strip()}"
    return f"Created branch '{branch_name}'"


@tool(permission=ToolPermission.WRITE)
async def git_checkout(repo_path: str, branch: str) -> str:
    """Switch branches."""
    backend = SubprocessGitBackend()
    exit_code, stdout, stderr = await backend.run(repo_path, ["checkout", branch])
    if exit_code != 0:
        return f"Error ({exit_code}): {stderr.strip()}"
    return stdout.strip() or f"Switched to branch '{branch}'"
