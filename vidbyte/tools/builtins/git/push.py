"""Context Protocol Header

Description:
    Implements a git push tool via subprocess execution.
Purpose:
    Updates remote refs along with associated objects.
Architecture:
    - Function-based tool using @tool decorator.
    - Uses SubprocessGitBackend to run `git push`.
Relations:
    Related to vidbyte.lib.providers.git.subprocess_backend and vidbyte.tools.builtins.git.
"""

from __future__ import annotations

from vidbyte.lib.providers.git.subprocess_backend import SubprocessGitBackend
from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission


@tool(permission=ToolPermission.EXECUTE)
async def git_push(repo_path: str, remote: str = "origin", branch: str | None = None) -> str:
    """Update remote refs along with associated objects."""
    args = ["push", remote]
    if branch:
        args.append(branch)

    backend = SubprocessGitBackend()
    exit_code, stdout, stderr = await backend.run(repo_path, args)
    if exit_code != 0:
        return f"Error ({exit_code}): {stderr.strip()}"
    return stdout.strip() or "Push successful"
