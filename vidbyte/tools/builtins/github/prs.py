"""Context Protocol Header

Description:
    GitHub pull request tools for listing, viewing, creating PRs, viewing
    diffs, and adding comments.
Purpose:
    Provides tools for agents to interact with GitHub pull requests through
    the GitHub REST API.
Architecture:
    - Uses GitHubRestBackend for API calls.
    - Each tool is an async function decorated with @tool.
Relations:
    Related to vidbyte.lib.providers.github and vidbyte.tools.builtins.github.
"""

from __future__ import annotations

from vidbyte.lib.providers.github.rest_backend import GitHubRestBackend
from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission


@tool(permission=ToolPermission.READ)
async def github_list_prs(repo: str, state: str = "open") -> str:
    """List pull requests for a repository.

    Args:
        repo: Repository in 'owner/repo' format
        state: 'open' (default), 'closed', or 'all'
    """
    backend = GitHubRestBackend()
    if not await backend.is_available():
        return "Error: GitHub token not configured. Set the GITHUB_TOKEN environment variable."
    try:
        return await backend.list_prs(repo, state)
    except Exception as exc:
        return f"Error listing PRs: {exc}"


@tool(permission=ToolPermission.READ)
async def github_get_pr(repo: str, pr_number: int) -> str:
    """Get details of a specific pull request.

    Args:
        repo: Repository in 'owner/repo' format
        pr_number: The pull request number
    """
    backend = GitHubRestBackend()
    if not await backend.is_available():
        return "Error: GitHub token not configured. Set the GITHUB_TOKEN environment variable."
    try:
        return await backend.get_pr(repo, pr_number)
    except Exception as exc:
        return f"Error getting PR: {exc}"


@tool(permission=ToolPermission.WRITE)
async def github_create_pr(repo: str, title: str, body: str, head: str, base: str = "main", draft: bool = False) -> str:
    """Create a new pull request.

    Args:
        repo: Repository in 'owner/repo' format
        title: Pull request title
        body: Pull request description
        head: Source branch name
        base: Target branch name (default: 'main')
        draft: Whether to create as draft PR (default: False)
    """
    backend = GitHubRestBackend()
    if not await backend.is_available():
        return "Error: GitHub token not configured. Set the GITHUB_TOKEN environment variable."
    try:
        return await backend.create_pr(repo, title, body, head, base, draft)
    except Exception as exc:
        return f"Error creating PR: {exc}"


@tool(permission=ToolPermission.READ)
async def github_get_pr_diff(repo: str, pr_number: int) -> str:
    """Get the diff of a pull request.

    Args:
        repo: Repository in 'owner/repo' format
        pr_number: The pull request number
    """
    backend = GitHubRestBackend()
    if not await backend.is_available():
        return "Error: GitHub token not configured. Set the GITHUB_TOKEN environment variable."
    try:
        return await backend.get_pr_diff(repo, pr_number)
    except Exception as exc:
        return f"Error getting PR diff: {exc}"


@tool(permission=ToolPermission.WRITE)
async def github_add_pr_comment(repo: str, pr_number: int, body: str, commit_id: str | None = None, file: str | None = None, line: int | None = None) -> str:
    """Add a comment to a pull request, optionally as a review comment on a specific line.

    Args:
        repo: Repository in 'owner/repo' format
        pr_number: The pull request number
        body: Comment body text
        commit_id: Optional commit SHA for review comment
        file: Optional file path for review comment
        line: Optional line number for review comment
    """
    backend = GitHubRestBackend()
    if not await backend.is_available():
        return "Error: GitHub token not configured. Set the GITHUB_TOKEN environment variable."
    try:
        return await backend.add_pr_comment(repo, pr_number, body, commit_id, file, line)
    except Exception as exc:
        return f"Error adding PR comment: {exc}"
