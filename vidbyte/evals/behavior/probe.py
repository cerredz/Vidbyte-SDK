"""Context Protocol Header

Description:
    Defines the RunProbe frozen snapshot of a completed agent run's observable state.
Purpose:
    Captures tool calls, stop reason, iterations, tokens, output, handoff, and trace
    artifact into a single immutable dataclass that behavior predicates read from.
Architecture:
    - RunProbe: frozen, slotted dataclass built from agent.last_reply.metadata and
      the agent's post-run fields (last_handoff, handoffs, last_trace).
    - from_agent: robust constructor reading a BaseAgent after a run.
    - from_reply: standalone constructor from an AgentMessage with optional agent.
Relations:
    Consumed by Behavior facade and all category behavior classes in
    vidbyte/evals/behavior/. Built per-case by EvalRunner for PredicateGrader.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent
    from vidbyte.context.handoff.base import Handoff
    from vidbyte.lib.dataclasses.agents import AgentMessage
    from vidbyte.lib.dataclasses.tools import ToolCallContext


@dataclass(frozen=True, slots=True)
class RunProbe:
    """Frozen snapshot of a completed agent run's observable state."""

    tool_calls: tuple[Any, ...] = field(default_factory=tuple)
    tool_call_states: tuple[str, ...] = field(default_factory=tuple)
    tool_call_count: int = 0
    stop_reason: str = "final_response"
    iteration_count: int = 0
    tokens_used: int | None = None
    output: str = ""
    handoff: Any = None
    handoffs: tuple[Any, ...] = field(default_factory=tuple)
    trace_artifact: Mapping[str, Any] | None = None

    @classmethod
    def from_agent(cls, agent: BaseAgent) -> RunProbe:
        # Builds a probe from agent.last_reply.metadata and the agent's post-run fields.
        reply = agent.last_reply
        if reply is None:
            return cls()
        return cls._from_reply_and_agent(reply, agent)

    @classmethod
    def from_reply(cls, reply: AgentMessage, agent: BaseAgent | None = None) -> RunProbe:
        # Builds a probe from a standalone AgentMessage with optional agent for handoff/trace.
        if agent is not None:
            return cls._from_reply_and_agent(reply, agent)
        return cls._from_reply_only(reply)

    @classmethod
    def _from_reply_and_agent(cls, reply: AgentMessage, agent: BaseAgent) -> RunProbe:
        # Extracts metadata from reply and handoff/trace fields from the agent.
        md = dict(reply.metadata) if reply.metadata else {}
        tool_calls = tuple(md.get("tool_calls", ()))
        tool_call_states = tuple(md.get("tool_call_states", ()))
        if not tool_call_states and tool_calls:
            tool_call_states = tuple(c.state.value for c in tool_calls)
        return cls(
            tool_calls=tool_calls,
            tool_call_states=tool_call_states,
            tool_call_count=int(md.get("tool_call_count", len(tool_calls))),
            stop_reason=str(md.get("stop_reason", "final_response")),
            iteration_count=int(md.get("iteration_count", 0)),
            tokens_used=md.get("tokens_used"),
            output=str(reply.content),
            handoff=agent.last_handoff,
            handoffs=tuple(agent.handoffs),
            trace_artifact=agent.last_trace,
        )

    @classmethod
    def _from_reply_only(cls, reply: AgentMessage) -> RunProbe:
        # Extracts metadata from reply without agent-level handoff/trace fields.
        md = dict(reply.metadata) if reply.metadata else {}
        tool_calls = tuple(md.get("tool_calls", ()))
        tool_call_states = tuple(md.get("tool_call_states", ()))
        if not tool_call_states and tool_calls:
            tool_call_states = tuple(c.state.value for c in tool_calls)
        return cls(
            tool_calls=tool_calls,
            tool_call_states=tool_call_states,
            tool_call_count=int(md.get("tool_call_count", len(tool_calls))),
            stop_reason=str(md.get("stop_reason", "final_response")),
            iteration_count=int(md.get("iteration_count", 0)),
            tokens_used=md.get("tokens_used"),
            output=str(reply.content),
        )


__all__ = ["RunProbe"]
