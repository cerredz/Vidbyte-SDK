"""Context Protocol Header

Description:
    Re-exports all provider backends for SDK tool abstractions.
Purpose:
    Provides a single import surface for all backend implementations (sandbox,
    git, web_search, web_fetch) that tools depend on for platform-specific operations.
Architecture:
    - Re-exports from git, sandbox, web_search, and web_fetch subpackages.
Relations:
    Used by vidbyte.tools.builtins and other tool categories.
"""

from __future__ import annotations

from vidbyte.lib.providers.git import BaseGitBackend, SubprocessGitBackend
from vidbyte.lib.providers.sandbox import BaseSandboxBackend, LocalSandboxBackend, SandboxResult
from vidbyte.lib.providers.web_fetch import BaseWebFetchBackend, FetchResult, HttpxFetchBackend
from vidbyte.lib.providers.web_search import (
    AutoWebSearchBackend,
    BaseWebSearchBackend,
    BraveWebSearchBackend,
    DuckDuckGoBackend,
    SearchResult,
    TavilyWebSearchBackend,
)

__all__ = [
    "AutoWebSearchBackend",
    "BaseGitBackend",
    "BaseSandboxBackend",
    "BaseWebFetchBackend",
    "BaseWebSearchBackend",
    "BraveWebSearchBackend",
    "DuckDuckGoBackend",
    "FetchResult",
    "HttpxFetchBackend",
    "LocalSandboxBackend",
    "SandboxResult",
    "SearchResult",
    "SubprocessGitBackend",
    "TavilyWebSearchBackend",
]
