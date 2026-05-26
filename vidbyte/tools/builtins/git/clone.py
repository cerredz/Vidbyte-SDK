"""Context Protocol Header

Description:
    Implements git clone and remote list tools via subprocess execution.
Purpose:
    Clones repositories and lists remote references.
Architecture:
    - Function-based tools using @tool decorator.
    - Uses SubprocessGitBackend to run git clone and remote commands.
Relations:
    Related to vidbyte.lib.providers.git.subprocess_backend and vidbyte.tools.builtins.git.
"""

from __future__ import annotations

from vidbyte.lib.providers.git.subprocess_backend import SubprocessGitBackend
from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission


@tool(permission=ToolPermission.EXECUTE)
async def git_clone(url: str, target_dir: str, branch: str | None = None) -> str:
    """Clone a repository into a new directory."""
    args = ["clone", url, target_dir]
    if branch:
        args.extend(["--branch", branch])

    backend = SubprocessGitBackend()
    exit_code, stdout, stderr = await backend.run(".", args)
    if exit_code != 0:
        return f"Error ({exit_code}): {stderr.strip()}"
    return stdout.strip() or f"Cloned into '{target_dir}'"


@tool(permission=ToolPermission.READ)
async def git_remote_list(repo_path: str = ".") -> str:
    """List remote repositories."""
    backend = SubprocessGitBackend()
    exit_code, stdout, stderr = await backend.run(repo_path, ["remote", "-v"])
    if exit_code != 0:
        return f"Error ({exit_code}): {stderr.strip()}"
    if not stdout.strip():
        return "(no remotes configured)"
    return stdout.strip()
