"""Context Protocol Header

Description:
    Implements a git log tool via subprocess execution.
Purpose:
    Shows commit logs in a compact one-line format.
Architecture:
    - Function-based tool using @tool decorator.
    - Uses SubprocessGitBackend to run `git log`.
Relations:
    Related to vidbyte.lib.providers.git.subprocess_backend and vidbyte.tools.builtins.git.
"""

from __future__ import annotations

from vidbyte.lib.providers.git.subprocess_backend import SubprocessGitBackend
from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission


@tool(permission=ToolPermission.READ)
async def git_log(repo_path: str = ".", max_count: int = 20, file_path: str | None = None) -> str:
    """Show commit logs."""
    args = ["log", f"--max-count={max_count}", "--oneline"]
    if file_path:
        args.append(file_path)

    backend = SubprocessGitBackend()
    exit_code, stdout, stderr = await backend.run(repo_path, args)
    if exit_code != 0:
        return f"Error ({exit_code}): {stderr.strip()}"
    if not stdout.strip():
        return "(no commits)"
    return stdout.strip()
