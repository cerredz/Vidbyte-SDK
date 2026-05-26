"""Context Protocol Header

Description:
    Defines the abstract base class for Git backend implementations.
Purpose:
    Establishes a contract for executing git commands so that tools can swap
    backends without changing their logic.
Architecture:
    - BaseGitBackend: Abstract class with a single async run() contract.
Relations:
    Related to vidbyte.lib.providers.git.subprocess_backend and vidbyte.tools.builtins.git.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseGitBackend(ABC):
    """Abstract backend for executing git commands."""

    @abstractmethod
    async def run(self, repo_path: str, args: list[str], timeout_ms: int = 30000) -> tuple[int, str, str]:
        """Execute a git command and return (exit_code, stdout, stderr)."""
        ...
