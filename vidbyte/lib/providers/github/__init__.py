"""Context Protocol Header

Description:
    Re-exports GitHub backend implementations.
Purpose:
    Provides a stable import surface for GitHub provider backends without
    exposing internal implementation details.
Architecture:
    - BaseGitHubBackend: Abstract contract.
    - GitHubRestBackend: REST API-based implementation using HttpTransport.
Relations:
    Related to vidbyte.tools.builtins.github.
"""

from __future__ import annotations

from vidbyte.lib.providers.github.base import BaseGitHubBackend
from vidbyte.lib.providers.github.rest_backend import GitHubRestBackend

__all__ = [
    "BaseGitHubBackend",
    "GitHubRestBackend",
]
