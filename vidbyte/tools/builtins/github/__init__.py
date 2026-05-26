"""Context Protocol Header

Description:
    Re-exports all built-in GitHub tools.
Purpose:
    Provides a single import surface for GitHub issue and pull request tools.
Architecture:
    - Function-based tools using the @tool decorator.
    - Issues tools: list, get, create.
    - PR tools: list, get, create, diff, comment.
Relations:
    Related to vidbyte.lib.providers.github and vidbyte.tools.builtins.
"""

from __future__ import annotations

from vidbyte.tools.builtins.github.issues import github_create_issue, github_get_issue, github_list_issues
from vidbyte.tools.builtins.github.prs import github_add_pr_comment, github_create_pr, github_get_pr, github_get_pr_diff, github_list_prs

__all__ = [
    "github_add_pr_comment",
    "github_create_issue",
    "github_create_pr",
    "github_get_issue",
    "github_get_pr",
    "github_get_pr_diff",
    "github_list_issues",
    "github_list_prs",
]
