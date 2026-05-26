"""Context Protocol Header

Description:
    Implements a git diff tool via subprocess execution.
Purpose:
    Shows changes between commits, the working tree, and the index.
Architecture:
    - Function-based tool using @tool decorator.
    - Uses SubprocessGitBackend to run `git diff` with optional flags.
Relations:
    Related to vidbyte.lib.providers.git.subprocess_backend and vidbyte.tools.builtins.git.
"""

from __future__ import annotations

from vidbyte.lib.providers.git.subprocess_backend import SubprocessGitBackend
from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission

MAX_OUTPUT_CHARS = 30000


@tool(permission=ToolPermission.READ)
async def git_diff(repo_path: str = ".", staged: bool = False, file_path: str | None = None) -> str:
    """Show changes between commits, commit and working tree, etc."""
    args = ["diff"]
    if staged:
        args.append("--staged")
    if file_path:
        args.append(file_path)

    backend = SubprocessGitBackend()
    exit_code, stdout, stderr = await backend.run(repo_path, args)
    if exit_code != 0:
        return f"Error ({exit_code}): {stderr.strip()}"

    output = stdout.strip()
    if not output:
        return "(no changes)"

    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n...[truncated at 30000 chars]"
    return output
