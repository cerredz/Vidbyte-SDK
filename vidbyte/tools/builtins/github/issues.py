"""Context Protocol Header

Description:
    GitHub issues tools for listing, viewing, and creating issues.
Purpose:
    Provides tools for agents to interact with GitHub issues through the
    GitHub REST API.
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
async def github_list_issues(repo: str, state: str = "open", labels: str | None = None) -> str:
    """List GitHub issues for a repository.

    Args:
        repo: Repository in 'owner/repo' format
        state: 'open' (default), 'closed', or 'all'
        labels: Optional comma-separated label filter
    """
    backend = GitHubRestBackend()
    if not await backend.is_available():
        return "Error: GitHub token not configured. Set the GITHUB_TOKEN environment variable."
    try:
        return await backend.list_issues(repo, state, labels)
    except Exception as exc:
        return f"Error listing issues: {exc}"


@tool(permission=ToolPermission.READ)
async def github_get_issue(repo: str, issue_number: int) -> str:
    """Get details of a specific GitHub issue.

    Args:
        repo: Repository in 'owner/repo' format
        issue_number: The issue number
    """
    backend = GitHubRestBackend()
    if not await backend.is_available():
        return "Error: GitHub token not configured. Set the GITHUB_TOKEN environment variable."
    try:
        return await backend.get_issue(repo, issue_number)
    except Exception as exc:
        return f"Error getting issue: {exc}"


@tool(permission=ToolPermission.WRITE)
async def github_create_issue(repo: str, title: str, body: str = "") -> str:
    """Create a new GitHub issue.

    Args:
        repo: Repository in 'owner/repo' format
        title: Issue title
        body: Issue body/description (optional)
    """
    backend = GitHubRestBackend()
    if not await backend.is_available():
        return "Error: GitHub token not configured. Set the GITHUB_TOKEN environment variable."
    try:
        return await backend.create_issue(repo, title, body)
    except Exception as exc:
        return f"Error creating issue: {exc}"
