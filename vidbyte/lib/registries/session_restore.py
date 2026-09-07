"""FILE: vidbyte/lib/registries/session_restore.py

PURPOSE: Maps a persisted provider-state kind to the callable that rebuilds its agent.
ROLE IN CODEBASE: Session's restore path consults this so a provider-backed agent is
    not silently rebuilt as a BaseAgent; each agent package registers its own kind.
ARCHITECTURE NOTE: The registry lives in vidbyte.lib because the A006 directed
    dependency graph forbids vidbyte.sessions from importing vidbyte.agents, and a
    lower-to-lower import is the only legal seam for that dispatch.
FUNCTION INVENTORY: register(kind, factory) records one restore callable;
    resolve(kind) returns it or None; kinds() lists what is registered.
COMMON MODIFICATION PATTERNS: An agent package registers itself at module import,
    following vidbyte/agents/runtimes/actor/actor.py and vidbyte/tools/mcp/presets.py.
WHAT NOT TO DO IN THIS FILE: Do not import any agent package here (that would
    reintroduce the layer violation this registry exists to avoid), and do not raise
    on an unknown kind — the caller's existing default path is the correct fallback.
KNOWN EDGE CASES: A kind resolves only once its module has been imported; through the
    public surface that always holds, since vidbyte/agents/__init__.py imports eagerly.
RELATED DOCS: docs/design/codex-durable-sessions.md
TESTS: tests/test_codex_durable_sessions.py; python scripts/run_ci.py.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar


class SessionRestoreRegistry:
    """Maps a persisted provider-state kind to the callable that rebuilds its agent."""

    _factories: ClassVar[dict[str, Callable[..., Any]]] = {}

    @classmethod
    def register(cls, kind: str, factory: Callable[..., Any]) -> None:
        """Register the callable that rebuilds an agent for one provider-state kind."""
        # Last registration wins: module import must stay idempotent under reloading
        # test runners, so re-registering the same kind is not an error.
        cls._factories[kind] = factory

    @classmethod
    def resolve(cls, kind: str) -> Callable[..., Any] | None:
        """Return the factory for a kind, or None when nothing is registered for it."""
        return cls._factories.get(kind)

    @classmethod
    def kinds(cls) -> tuple[str, ...]:
        """Return every registered kind, sorted for stable reporting."""
        return tuple(sorted(cls._factories))


__all__ = ["SessionRestoreRegistry"]
