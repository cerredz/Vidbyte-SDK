"""Context Protocol Header

Description:
    Public surface for the durable-sessions harness primitive.
Purpose:
    Lets developers attach an agent to a Session in one line and reconstruct
    sessions via continue/resume/fork over a checkpoint DAG.
Architecture:
    - Session: durable wrapper + verbs.
    - SessionClient: namespace client (also reachable via sdk.harnesses.sessions).
    - Stores: InMemory + File (local); DB providers live in vidbyte.lib.providers.
    - Contracts/enums re-exported from vidbyte.lib.dataclasses.sessions.
Relations:
    Built on vidbyte.agents.base export_state()/restore() and the SessionStore port.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.sessions import (
    SESSION_SCHEMA_VERSION,
    Checkpoint,
    CheckpointPolicy,
    RunState,
    SessionMeta,
    SessionStatus,
    TraceCapture,
)
from vidbyte.sessions.client import SessionClient
from vidbyte.sessions.serialization import SessionSerializer
from vidbyte.sessions.session import Session
from vidbyte.sessions.store import BaseSessionStore, SessionStore
from vidbyte.sessions.stores import FileSessionStore, InMemorySessionStore
from vidbyte.sessions.tool import SessionScope, SessionTool
from vidbyte.sessions.trace_capture import CapturedTrace, TraceRecorder

__all__ = [
    "SESSION_SCHEMA_VERSION",
    "BaseSessionStore",
    "CapturedTrace",
    "Checkpoint",
    "CheckpointPolicy",
    "FileSessionStore",
    "InMemorySessionStore",
    "RunState",
    "Session",
    "SessionClient",
    "SessionMeta",
    "SessionScope",
    "SessionSerializer",
    "SessionStatus",
    "SessionStore",
    "SessionTool",
    "TraceCapture",
    "TraceRecorder",
]
