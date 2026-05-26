"""Context Protocol Header

Description:
    Re-exports Git backend implementations for built-in git tools.
Purpose:
    Provides a single import surface for all Git provider backends.
Architecture:
    - BaseGitBackend: Abstract contract for git command execution.
    - SubprocessGitBackend: Subprocess-based implementation.
Relations:
    Related to vidbyte.tools.builtins.git.
"""

from __future__ import annotations

from vidbyte.lib.providers.git.base import BaseGitBackend
from vidbyte.lib.providers.git.subprocess_backend import SubprocessGitBackend

__all__ = [
    "BaseGitBackend",
    "SubprocessGitBackend",
]
