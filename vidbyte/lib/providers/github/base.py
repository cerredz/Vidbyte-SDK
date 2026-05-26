"""Context Protocol Header

Description:
    Defines the abstract base class for GitHub API backends.
Purpose:
    Provides a typed contract that GitHub provider backends must implement
    for issues and pull requests operations.
Architecture:
    - BaseGitHubBackend: ABC with 9 async abstract methods.
    - Covers Issues: list, get, create.
    - Covers PRs: list, get, create, diff, comment.
Relations:
    Related to vidbyte.lib.providers.github and vidbyte.tools.builtins.github.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseGitHubBackend(ABC):
    @abstractmethod
    async def list_issues(self, repo: str, state: str, labels: str | None) -> str:
        ...

    @abstractmethod
    async def get_issue(self, repo: str, issue_number: int) -> str:
        ...

    @abstractmethod
    async def create_issue(self, repo: str, title: str, body: str) -> str:
        ...

    @abstractmethod
    async def list_prs(self, repo: str, state: str) -> str:
        ...

    @abstractmethod
    async def get_pr(self, repo: str, pr_number: int) -> str:
        ...

    @abstractmethod
    async def create_pr(self, repo: str, title: str, body: str, head: str, base: str, draft: bool) -> str:
        ...

    @abstractmethod
    async def get_pr_diff(self, repo: str, pr_number: int) -> str:
        ...

    @abstractmethod
    async def add_pr_comment(self, repo: str, pr_number: int, body: str, commit_id: str | None, file: str | None, line: int | None) -> str:
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...


__all__ = ["BaseGitHubBackend"]
