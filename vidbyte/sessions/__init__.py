"""Context Protocol Header

Description:
    Public surface for the durable-sessions primitive.
Purpose:
    Lets developers attach an agent to a Session in one line and reconstruct
    sessions via continue/resume/fork over a checkpoint DAG.
Architecture:
    - Session: durable wrapper + verbs.
    - SessionClient: namespace client (also reachable via sdk.harnesses.sessions).
    - Stores: InMemory + File (local); DB providers live in vidbyte.lib.providers.
    - Contracts/enums/errors/scope live inside vidbyte.sessions (self-contained).
    - Agent-facing session tools (SessionTool, CheckpointTool, ForkTool, RewindTool,
      ResumeReplaceTool, ResumeAppendTool, ResumeOutputTool) live in
      vidbyte.tools.builtins.sessions and reuse the classes re-exported here.
Relations:
    Built on vidbyte.agents.base export_state()/restore() and the SessionStore port.
"""

from __future__ import annotations

from vidbyte.sessions.client import SessionClient
from vidbyte.sessions.contracts import (
    SESSION_SCHEMA_VERSION,
    Checkpoint,
    CheckpointPolicy,
    RunState,
    SessionMeta,
    SessionStatus,
    TraceCapture,
)
from vidbyte.sessions.errors import (
    CheckpointNotFoundError,
    SessionError,
    SessionNotFoundError,
    SessionSerializationError,
    SessionStoreError,
    SessionVersionError,
)
from vidbyte.sessions.portable import SessionBundleExporter, SessionBundleImporter
from vidbyte.sessions.scope import SessionScope
from vidbyte.sessions.serialization import SessionSerializer
from vidbyte.sessions.session import ForkOutcome, Session
from vidbyte.sessions.store import BaseSessionStore, SessionStore
from vidbyte.sessions.stores import FileSessionStore, InMemorySessionStore
from vidbyte.sessions.trace_capture import CapturedTrace, TraceRecorder

__all__ = [
    "SESSION_SCHEMA_VERSION",
    "BaseSessionStore",
    "CapturedTrace",
    "Checkpoint",
    "CheckpointNotFoundError",
    "CheckpointPolicy",
    "FileSessionStore",
    "ForkOutcome",
    "InMemorySessionStore",
    "RunState",
    "Session",
    "SessionBundleExporter",
    "SessionBundleImporter",
    "SessionClient",
    "SessionError",
    "SessionMeta",
    "SessionNotFoundError",
    "SessionScope",
    "SessionSerializationError",
    "SessionSerializer",
    "SessionStatus",
    "SessionStore",
    "SessionStoreError",
    "SessionVersionError",
    "TraceCapture",
    "TraceRecorder",
]
