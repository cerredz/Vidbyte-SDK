"""Context Protocol Header

Description:
    Defines the durable-session exception hierarchy.
Purpose:
    Gives stores, the serializer, and the Session facade a single typed error
    family so callers can branch on session failure modes without catching raw
    JSONDecodeError or KeyError. Lives in vidbyte/sessions/ with the rest of the
    session logic; the shared VidbyteSdkError root stays in vidbyte.lib.errors.
Architecture:
    - SessionError: base for every durable-session failure.
    - SessionNotFoundError / CheckpointNotFoundError: lookup misses.
    - SessionSerializationError: malformed or unserializable payloads.
    - SessionStoreError: backend read/write or corruption failures.
    - SessionVersionError: unknown persisted schema_version.
Relations:
    Subclasses vidbyte.lib.errors.base.VidbyteSdkError to preserve one hierarchy.
    Re-exported from vidbyte.sessions.
"""

from __future__ import annotations

from vidbyte.lib.errors.base import VidbyteSdkError


class SessionError(VidbyteSdkError):
    """Base class for durable-session failures."""


class SessionNotFoundError(SessionError):
    """Raised when a session id is not present in the store."""


class CheckpointNotFoundError(SessionError):
    """Raised when a checkpoint id is not present in the store."""


class SessionSerializationError(SessionError):
    """Raised when a session payload cannot be serialized or parsed."""


class SessionStoreError(SessionError):
    """Raised when a session store read/write fails or returns corrupt data."""


class SessionVersionError(SessionError):
    """Raised when a persisted session payload has an unsupported schema version."""


__all__ = [
    "SessionError",
    "SessionNotFoundError",
    "CheckpointNotFoundError",
    "SessionSerializationError",
    "SessionStoreError",
    "SessionVersionError",
]
