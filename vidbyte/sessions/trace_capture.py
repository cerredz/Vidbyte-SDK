"""Context Protocol Header

Description:
    Extracts trace data from a completed agent reply for checkpoint persistence.
Purpose:
    Reads the agent's existing trace settings (continual-trace artifact and tracer
    events) and projects them onto a checkpoint, honoring the TraceCapture policy.
Architecture:
    - CapturedTrace: small carrier for artifact, summary, and raw events.
    - TraceRecorder: fail-open policy-driven extractor.
Relations:
    Used by vidbyte.sessions.session.Session; consumes vidbyte.agents.base.BaseAgent
    state (_trace_option, last_trace, _tracer) and AgentMessage.metadata.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from vidbyte.agents.types import AgentMessage
from vidbyte.sessions.contracts import TraceCapture

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent

_MAX_EVENTS = 200


@dataclass(frozen=True, slots=True)
class CapturedTrace:
    """Trace data lifted from a run, ready to attach to a checkpoint."""

    artifact: Mapping[str, Any] | None = None
    summary: Mapping[str, Any] | None = None
    events: tuple[Mapping[str, Any], ...] | None = None


class TraceRecorder:
    """Policy-driven, fail-open extractor of trace data from a reply and agent."""

    def __init__(self, policy: TraceCapture = TraceCapture.AUTO) -> None:
        # Bind the configured capture policy.
        self._policy = policy

    def capture(self, agent: "BaseAgent", reply: AgentMessage) -> CapturedTrace:
        # Return captured trace data per policy, never raising on extraction failure.
        try:
            if not self._should_capture(agent, reply):
                return CapturedTrace()
            artifact = self._artifact(agent, reply)
            summary = self._summary(reply)
            events = self._events(agent) if self._policy is TraceCapture.FULL else None
            return CapturedTrace(artifact=artifact, summary=summary, events=events)
        except Exception:
            return CapturedTrace()

    def _should_capture(self, agent: "BaseAgent", reply: AgentMessage) -> bool:
        # Decide whether capture runs for this policy and agent.
        if self._policy is TraceCapture.OFF:
            return False
        if self._policy in (TraceCapture.ARTIFACT, TraceCapture.FULL):
            return True
        return self._tracing_enabled(agent) or reply.metadata.get("trace") is not None

    @staticmethod
    def _tracing_enabled(agent: "BaseAgent") -> bool:
        # Report whether the agent has continual tracing configured.
        option = getattr(agent, "_trace_option", None)
        return bool(option is not None and getattr(option, "enabled", False)) or getattr(agent, "last_trace", None) is not None

    @staticmethod
    def _artifact(agent: "BaseAgent", reply: AgentMessage) -> Mapping[str, Any] | None:
        # Prefer the per-turn reply artifact, falling back to the agent's last_trace.
        artifact = reply.metadata.get("trace")
        if isinstance(artifact, Mapping):
            return dict(artifact)
        last = getattr(agent, "last_trace", None)
        return dict(last) if isinstance(last, Mapping) else None

    @staticmethod
    def _summary(reply: AgentMessage) -> Mapping[str, Any] | None:
        # Return the per-turn trace summary metadata when present.
        summary = reply.metadata.get("trace_metadata")
        return dict(summary) if isinstance(summary, Mapping) else None

    @staticmethod
    def _events(agent: "BaseAgent") -> tuple[Mapping[str, Any], ...] | None:
        # Return a bounded copy of the tracer's recorded events when available.
        tracer = getattr(agent, "_tracer", None)
        events = getattr(tracer, "events", None)
        if not isinstance(events, list):
            return None
        captured = [dict(event) for event in events[-_MAX_EVENTS:] if isinstance(event, Mapping)]
        return tuple(captured) if captured else None


__all__ = ["CapturedTrace", "TraceRecorder"]
