"""Context Protocol Header

Description:
    Namespace client for durable sessions, exposed as sdk.harnesses.sessions.
Purpose:
    Offers ergonomic one-line entry points for attaching, resuming, continuing,
    and forking sessions, plus local store constructors.
Architecture:
    - SessionClient: thin factory over Session and the local stores.
Relations:
    Wired into vidbyte.harnesses.client.HarnessClient.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from vidbyte.sessions.session import Session
from vidbyte.sessions.store import SessionStore
from vidbyte.sessions.stores.file import FileSessionStore
from vidbyte.sessions.stores.memory import InMemorySessionStore

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent


class SessionClient:
    """Namespace client for creating and reconstructing durable sessions."""

    def attach(self, agent: "BaseAgent", *, store: SessionStore | None = None, **kwargs: Any) -> Session:
        # Attach an agent to a (defaulted in-memory) durable session in one line.
        return Session(agent, store=store, **kwargs)

    def resume(self, store: SessionStore, session_id: str, **kwargs: Any) -> Session:
        # Reconstruct a live session from its head (or a given checkpoint).
        return Session.resume(store, session_id, **kwargs)

    def continue_(self, store: SessionStore, session_id: str, **kwargs: Any) -> Session:
        # Resume the head checkpoint of an existing session.
        return Session.continue_(store, session_id, **kwargs)

    def fork(self, store: SessionStore, checkpoint_id: str, **kwargs: Any) -> Session:
        # Branch a new session from any checkpoint.
        return Session.fork_from(store, checkpoint_id, **kwargs)

    def memory_store(self) -> InMemorySessionStore:
        # Build a process-local in-memory store.
        return InMemorySessionStore()

    def file_store(self, root: str) -> FileSessionStore:
        # Build a filesystem-backed store rooted at the given directory.
        return FileSessionStore(root)


__all__ = ["SessionClient"]
