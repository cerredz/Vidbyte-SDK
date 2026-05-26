"""Context Protocol Header

Description:
    Re-exports all built-in git tools.
Purpose:
    Provides a single import surface for git status, diff, log, branch, commit,
    push, and clone tools.
Architecture:
    - Function-based tools using the @tool decorator.
    - Each tool is a standalone async function wrapped as a FunctionTool.
Relations:
    Related to vidbyte.lib.providers.git and vidbyte.tools.builtins.
"""

from __future__ import annotations

from vidbyte.tools.builtins.git.branch import git_branch_create, git_branch_list, git_checkout
from vidbyte.tools.builtins.git.clone import git_clone, git_remote_list
from vidbyte.tools.builtins.git.commit import git_add, git_commit
from vidbyte.tools.builtins.git.diff import git_diff
from vidbyte.tools.builtins.git.log import git_log
from vidbyte.tools.builtins.git.push import git_push
from vidbyte.tools.builtins.git.status import git_status

__all__ = [
    "git_add",
    "git_branch_create",
    "git_branch_list",
    "git_checkout",
    "git_clone",
    "git_commit",
    "git_diff",
    "git_log",
    "git_push",
    "git_remote_list",
    "git_status",
]
