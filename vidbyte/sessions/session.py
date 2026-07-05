"""Context Protocol Header

Description:
    Implements the Session facade that makes any agent durable in one line.
Purpose:
    Binds an agent, a store, and a session id, owning the continue/resume/fork/
    rewind/edit verbs over an append-only checkpoint DAG.
Architecture:
    - Session: aggregate wrapping a BaseAgent; persists a checkpoint per policy
      after each run and exposes lineage operations as DAG queries.
Relations:
    Uses vidbyte.sessions.store.SessionStore, TraceRecorder, SessionSerializer, and
    vidbyte.agents.base.BaseAgent export_state()/restore().
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from vidbyte.agents.types import AgentInput, AgentMessage
from vidbyte.sessions.contracts import (
    Checkpoint,
    CheckpointPolicy,
    SessionMeta,
    SessionStatus,
    TraceCapture,
)
from vidbyte.lib.errors import AgentExecutionError
from vidbyte.sessions.errors import SessionError
from vidbyte.sessions.serialization import SessionSerializer
from vidbyte.sessions.store import SessionStore
from vidbyte.sessions.stores.memory import InMemorySessionStore
from vidbyte.sessions.trace_capture import TraceRecorder

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent


@dataclass(frozen=True, slots=True)
class ForkOutcome:
    """Result of one attempted Session fork inside a batch."""

    index: int
    session: Session | None
    error: str | None


class Session:
    """Durable wrapper that persists an agent's run state as a checkpoint DAG."""

    def __init__(self, agent: "BaseAgent", *, store: SessionStore | None = None, session_id: str | None = None, policy: CheckpointPolicy | str = CheckpointPolicy.PER_TURN, trace: TraceCapture | str = TraceCapture.AUTO, tags: Sequence[str] = (), parent_session_id: str | None = None, _existing: bool = False) -> None:
        # Bind the agent/store/id and either record initial meta or adopt an existing session.
        self._agent = agent
        self._store = store or InMemorySessionStore()
        self._session_id = session_id or f"se_{uuid4().hex}"
        self._policy = CheckpointPolicy(policy)
        self._recorder = TraceRecorder(TraceCapture(trace))
        self._serializer = SessionSerializer()
        self._tags = tuple(tags)
        self._parent_session_id = parent_session_id
        self._head_id: str | None = None
        if _existing:
            self._adopt_existing_head()
        else:
            self._write_initial_meta()
        self._bind_session_tools()

    @property
    def id(self) -> str:
        """Return this session's id."""
        return self._session_id

    @property
    def head(self) -> str | None:
        """Return the current head checkpoint id, or None when no checkpoint exists yet."""
        return self._head_id

    @property
    def agent(self) -> "BaseAgent":
        """Return the wrapped agent."""
        return self._agent

    async def arun(self, message: str | AgentInput, **options: Any) -> AgentMessage:
        """Run the agent, then persist a checkpoint per policy; persistence never ends the run."""
        reply = await self._agent.arun(message, **options)
        if self._policy is not CheckpointPolicy.MANUAL:
            self._persist_fail_open(reply, label="")
        return reply

    def run(self, message: str | AgentInput, **options: Any) -> AgentMessage:
        """Run the agent synchronously, persisting a checkpoint per policy."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun(message, **options))
        raise AgentExecutionError("Session.run() cannot be called from an active event loop; use await arun().")

    def checkpoint(self, *, label: str = "") -> str:
        """Write a checkpoint of the current state on demand and return its id."""
        stored = self._persist(self._agent.last_reply, label=label)
        return stored.id

    def fork(self, *, at: str | None = None, tools: Sequence[object] | None = None, runner: object | None = None, middleware: Sequence[object] | None = None) -> "Session":
        """Branch a new session from a checkpoint (defaults to head), recording lineage."""
        checkpoint_id = at or self._head_id
        if checkpoint_id is None:
            raise SessionError("Cannot fork a session with no checkpoints.", details={"session_id": self._session_id})
        return self.fork_from(self._store, checkpoint_id, tools=tools or (), runner=runner, middleware=middleware or (), policy=self._policy, trace=self._recorder_policy(), tags=self._tags)

    def batch_fork(self, count: int, *, at: str | None = None, tools: Sequence[object] | None = None, runner: object | None = None, middleware: Sequence[object] | None = None) -> list[ForkOutcome]:
        # Attempt count independent forks from the same checkpoint, isolating branch creation failures.
        outcomes: list[ForkOutcome] = []
        for index in range(count):
            outcomes.append(self._attempt_batch_fork(index, at=at, tools=tools, runner=runner, middleware=middleware))
        return outcomes

    def _attempt_batch_fork(self, index: int, *, at: str | None, tools: Sequence[object] | None, runner: object | None, middleware: Sequence[object] | None) -> ForkOutcome:
        # Run one fork attempt and convert any creation error into a structured outcome record.
        try:
            branch = self.fork(at=at, tools=tools, runner=runner, middleware=middleware)
        except Exception as exc:
            return ForkOutcome(index=index, session=None, error=f"{type(exc).__name__}: {exc}")
        return ForkOutcome(index=index, session=branch, error=None)

    def rewind(self, *, to: str) -> "Session":
        """Move the head to an ancestor checkpoint so the next run branches from it."""
        target = self._store.get(to)
        if target.session_id != self._session_id:
            raise SessionError("Cannot rewind to a checkpoint from another session.", details={"checkpoint_id": to})
        self._restore_agent_history(target)
        self._head_id = to
        self._store.put_meta(replace(self._store.get_meta(self._session_id), head_id=to, updated_at=_now()))
        return self

    def edit(self, transform: Callable[[list[AgentMessage]], Sequence[AgentMessage]], *, label: str = "edit") -> "Session":
        """Apply a transform to history and write the result as a new checkpoint."""
        self._agent.history = list(transform(list(self._agent.history)))
        self._persist(self._agent.last_reply, label=label)
        return self

    def complete(self) -> None:
        """Mark this session COMPLETED in its metadata."""
        self._store.put_meta(replace(self._store.get_meta(self._session_id), status=SessionStatus.COMPLETED, updated_at=_now()))

    def tag(self, *names: str) -> "Session":
        """Attach one or more human-friendly names to this session and return self."""
        meta = self._store.get_meta(self._session_id)
        tags = tuple(dict.fromkeys((*meta.tags, *names)))
        self._store.put_meta(replace(meta, tags=tags, updated_at=_now()))
        self._tags = tags
        return self

    def adopt(self, checkpoint_id: str, *, label: str = "resume") -> str:
        """Replace the bound agent's history with another session's checkpoint and persist a new checkpoint (resume-replace)."""
        source = self._store.get(checkpoint_id)
        self._restore_agent_history(source)
        return self._persist(None, label=label).id

    def append_context(self, checkpoint_id: str, *, label: str = "resume") -> str:
        """Append another session's checkpoint history (framed) to the bound agent and persist a new checkpoint (resume-append)."""
        source = self._store.get(checkpoint_id)
        framed = self._frame_resumed_history(source)
        self._agent.history = list(self._agent.history) + framed
        return self._persist(None, label=label).id

    def append_output(self, session_id: str, *, label: str = "resume") -> str:
        """Append another session's final assistant output to the bound agent (resume-output); errors if that session is not COMPLETED."""
        session_id = self._store.resolve(session_id)
        meta = self._store.get_meta(session_id)
        if meta.status is not SessionStatus.COMPLETED:
            raise SessionError("Cannot append output from a session that is not completed.", details={"session_id": session_id, "status": meta.status.value})
        head = self._store.head(session_id)
        if head is None:
            raise SessionError("Cannot append output from a session with no checkpoints.", details={"session_id": session_id})
        output = self._extract_last_output(head)
        self._agent.history = list(self._agent.history) + [output]
        return self._persist(None, label=label).id

    @classmethod
    def resume(cls, store: SessionStore, session_id: str, *, checkpoint_id: str | None = None, tools: Sequence[object] = (), runner: object | None = None, middleware: Sequence[object] = (), tracer: object | None = None, output_schema: object | None = None, policy: CheckpointPolicy | str = CheckpointPolicy.PER_TURN, trace: TraceCapture | str = TraceCapture.AUTO) -> "Session":
        """Reconstruct a live session from a checkpoint, re-supplying non-serializable parts."""
        session_id = store.resolve(session_id)
        source = store.get(checkpoint_id) if checkpoint_id else store.head(session_id)
        if source is None:
            raise SessionError("Cannot resume a session with no checkpoints.", details={"session_id": session_id})
        agent = cls._restore_agent(source, tools=tools, runner=runner, middleware=middleware, tracer=tracer, output_schema=output_schema)
        return cls(agent, store=store, session_id=session_id, policy=policy, trace=trace, _existing=True)

    @classmethod
    def continue_(cls, store: SessionStore, session_id: str, **kwargs: Any) -> "Session":
        """Resume the head checkpoint of a session (sugar over resume)."""
        return cls.resume(store, session_id, **kwargs)

    @classmethod
    def fork_from(cls, store: SessionStore, checkpoint_id: str, *, tools: Sequence[object] = (), runner: object | None = None, middleware: Sequence[object] = (), tracer: object | None = None, output_schema: object | None = None, policy: CheckpointPolicy | str = CheckpointPolicy.PER_TURN, trace: TraceCapture | str = TraceCapture.AUTO, tags: Sequence[str] = ()) -> "Session":
        """Create a new session branched from any checkpoint, copying its state as the root."""
        source = store.get(checkpoint_id)
        agent = cls._restore_agent(source, tools=tools, runner=runner, middleware=middleware, tracer=tracer, output_schema=output_schema)
        session = cls(agent, store=store, session_id=f"se_{uuid4().hex}", policy=policy, trace=trace, tags=tags, parent_session_id=source.session_id)
        session._persist(None, label="fork")
        return session

    def _persist_fail_open(self, reply: AgentMessage | None, *, label: str) -> None:
        # Write a checkpoint but never let a store failure end the run.
        try:
            self._persist(reply, label=label)
        except Exception as exc:
            if reply is not None and isinstance(reply.metadata, dict):
                reply.metadata["__session_error__"] = f"{type(exc).__name__}: {exc}"

    def _persist(self, reply: AgentMessage | None, *, label: str) -> Checkpoint:
        # Build a checkpoint from the agent's current state and write it to the store.
        captured = self._recorder.capture(self._agent, reply) if reply is not None else self._recorder.capture(self._agent, _empty_reply(self._agent.name))
        checkpoint = Checkpoint(
            id=f"ck_{uuid4().hex}",
            session_id=self._session_id,
            parent_id=self._head_id,
            seq=0,
            created_at=_now(),
            run_state=self._agent.export_state(),
            label=label,
            status=SessionStatus.ACTIVE,
            trace_artifact=captured.artifact,
            trace_summary=captured.summary,
            trace_events=captured.events,
        )
        stored = self._store.put(checkpoint)
        self._head_id = stored.id
        return stored

    def _write_initial_meta(self) -> None:
        # Record an empty ACTIVE session so it lists and round-trips before the first run.
        now = _now()
        self._store.put_meta(
            SessionMeta(
                session_id=self._session_id,
                head_id=None,
                parent_session_id=self._parent_session_id,
                agent_name=self._agent.name,
                status=SessionStatus.ACTIVE,
                created_at=now,
                updated_at=now,
                tags=self._tags,
            )
        )

    def _adopt_existing_head(self) -> None:
        # Point this session at the stored head when resuming an existing session.
        existing = self._store.head(self._session_id)
        self._head_id = existing.id if existing is not None else None

    def _restore_agent_history(self, checkpoint: Checkpoint) -> None:
        # Reset the wrapped agent's history to a checkpoint's recorded state.
        self._agent.history = [self._serializer.message_from_dict(item) for item in checkpoint.run_state.history]

    def _frame_resumed_history(self, checkpoint: Checkpoint) -> list[AgentMessage]:
        # Render another session's history as a single framed assistant message preserving its turns.
        messages = [self._serializer.message_from_dict(item) for item in checkpoint.run_state.history]
        if not messages:
            return []
        transcript = "\n\n".join(f"[{m.sender}]: {m.content}" for m in messages)
        framed = AgentMessage(
            sender=checkpoint.run_state.agent_name,
            recipient=self._agent.name,
            content=f"<resumed_thread session_id=\"{checkpoint.session_id}\" checkpoint_id=\"{checkpoint.id}\">\n{transcript}\n</resumed_thread>",
            metadata={"resumed_session_id": checkpoint.session_id, "resumed_checkpoint_id": checkpoint.id},
        )
        return [framed]

    def _extract_last_output(self, checkpoint: Checkpoint) -> AgentMessage:
        # Pull the last assistant message from a checkpoint and frame it as a self-contained output.
        history = [self._serializer.message_from_dict(item) for item in checkpoint.run_state.history]
        last_assistant = next((m for m in reversed(history) if m.sender == checkpoint.run_state.agent_name), None)
        content = last_assistant.content if last_assistant is not None else ""
        return AgentMessage(
            sender=checkpoint.run_state.agent_name,
            recipient=self._agent.name,
            content=f"<resumed_output session_id=\"{checkpoint.session_id}\">\n{content}\n</resumed_output>",
            metadata={"resumed_session_id": checkpoint.session_id, "resumed_checkpoint_id": checkpoint.id},
        )

    def _bind_session_tools(self) -> None:
        # Attach this session to any bound session-builtin tools the agent carries.
        try:
            self._agent._active_session = self  # noqa: SLF001
        except Exception:
            pass
        tools = getattr(self._agent, "_agent_tool_items", ()) or ()
        for tool in tools:
            binder = getattr(tool, "bind_session", None)
            if callable(binder):
                binder(self)

    def _recorder_policy(self) -> TraceCapture:
        # Return the trace policy currently configured on this session.
        return self._recorder._policy

    @staticmethod
    def _restore_agent(source: Checkpoint, *, tools: Sequence[object], runner: object | None, middleware: Sequence[object], tracer: object | None, output_schema: object | None) -> "BaseAgent":
        # Rebuild a BaseAgent from a checkpoint's RunState via the rehydration contract.
        from vidbyte.agents.base import BaseAgent
        return BaseAgent.restore(source.run_state, tools=tools, runner=runner, middleware=middleware, tracer=tracer, output_schema=output_schema)


def _now() -> str:
    # Return the current UTC timestamp as an ISO-8601 string.
    return datetime.now(timezone.utc).isoformat()


def _empty_reply(agent_name: str) -> AgentMessage:
    # Build a placeholder reply for trace capture on manual/fork checkpoints.
    return AgentMessage(sender=agent_name, recipient="orchestrator", content="", metadata={})


__all__ = ["ForkOutcome", "Session"]
