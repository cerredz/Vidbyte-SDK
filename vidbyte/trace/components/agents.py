"""Context Protocol Header

Description:
    Defines semantic span factories for single-agent, aggregate-agent, ledger-driven multi-agent, and adversarial-agent execution.
Purpose:
    Standardizes stable span names and component/detail policies without coupling agents to a tracing provider.
Architecture:
    `AgentTrace`, `AggregateTrace`, `MultiAgentTrace`, and `AdversarialTrace` return declarative `SpanSpec` instances for their lifecycle phases.
Relations:
    Routed by `TraceController` and emitted by agent implementations under `vidbyte.agents`.
    `AdversarialTrace` is defined in `vidbyte.trace.adversarial` and re-exported here for the components facade.
"""

from __future__ import annotations

from typing import Any

from vidbyte.trace.adversarial import AdversarialTrace
from vidbyte.trace.schema import ParentPolicy, SpanKind, SpanSpec, TraceDetail


class AgentTrace:
    """Factory for single-agent semantic spans."""

    @staticmethod
    def run(**attributes: Any) -> SpanSpec:
        # Describes the root agent run.
        return SpanSpec("agent.run", SpanKind.CHAIN, "agents", TraceDetail.MINIMAL, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def stop(**attributes: Any) -> SpanSpec:
        # Describes a final agent stop event.
        return SpanSpec("agent.stop", SpanKind.CHAIN, "agents", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)


class AggregateTrace:
    """Factory for aggregate-agent semantic spans."""

    @staticmethod
    def run(**attributes: Any) -> SpanSpec:
        # Describes the overall aggregate fan-out and synthesis run.
        return SpanSpec("aggregate.run", SpanKind.CHAIN, "aggregate", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def proposer(**attributes: Any) -> SpanSpec:
        # Describes one aggregate proposer phase.
        return SpanSpec("aggregate.proposer", SpanKind.CHAIN, "aggregate", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def synthesis(**attributes: Any) -> SpanSpec:
        # Describes the aggregate synthesis phase.
        return SpanSpec("aggregate.synthesis", SpanKind.CHAIN, "aggregate", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def failure(**attributes: Any) -> SpanSpec:
        # Describes an aggregate failure while preserving normal error propagation.
        return SpanSpec("aggregate.failure", SpanKind.CHAIN, "aggregate", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)


class MultiAgentTrace:
    """Factory for ledger-driven multi-agent semantic spans."""

    @staticmethod
    def run(**attributes: Any) -> SpanSpec:
        # Describes the bounded team controller lifecycle.
        return SpanSpec("multi_agent.run", SpanKind.CHAIN, "multi_agent", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def orchestrator(**attributes: Any) -> SpanSpec:
        # Describes one manager plan, progress, or recovery phase.
        return SpanSpec("multi_agent.orchestrator", SpanKind.CHAIN, "multi_agent", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def worker(**attributes: Any) -> SpanSpec:
        # Describes one serial worker dispatch without raw task payloads.
        return SpanSpec("multi_agent.worker", SpanKind.CHAIN, "multi_agent", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def ledger_update(**attributes: Any) -> SpanSpec:
        # Describes one committed ledger revision using safe transition fields.
        return SpanSpec("multi_agent.ledger_update", SpanKind.CHAIN, "multi_agent", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def replan(**attributes: Any) -> SpanSpec:
        # Describes one bounded plan replacement and worker reset cycle.
        return SpanSpec("multi_agent.replan", SpanKind.CHAIN, "multi_agent", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)

    @staticmethod
    def finalize(**attributes: Any) -> SpanSpec:
        # Describes the schema-free manager finalization phase.
        return SpanSpec("multi_agent.finalize", SpanKind.CHAIN, "multi_agent", TraceDetail.STANDARD, ParentPolicy.CURRENT, attributes)


__all__ = ["AdversarialTrace", "AgentTrace", "AggregateTrace", "MultiAgentTrace"]
