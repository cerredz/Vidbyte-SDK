"""Agent semantic trace span specs."""

from __future__ import annotations

from typing import Any

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

    @staticmethod
    def loop_settings_resolved(**attributes: Any) -> SpanSpec:
        # Describes the final AgentLoopSettings after flat-kwarg merge.
        return SpanSpec("agent.loop_settings.resolved", SpanKind.CHAIN, "agents", TraceDetail.STANDARD, ParentPolicy.AGENT, attributes)

    @staticmethod
    def loop_settings_enforced(**attributes: Any) -> SpanSpec:
        # Describes a loop budget being hit (max_iterations, max_tokens, max_tool_calls).
        return SpanSpec("agent.loop_settings.enforced", SpanKind.CHAIN, "agents", TraceDetail.STANDARD, ParentPolicy.AGENT, attributes)

    @staticmethod
    def output_contract_enforced(**attributes: Any) -> SpanSpec:
        # Describes output_schema validation running on the final response.
        return SpanSpec("agent.output_contract.enforced", SpanKind.CHAIN, "agents", TraceDetail.VERBOSE, ParentPolicy.AGENT, attributes)

    @staticmethod
    def output_contract_violation(**attributes: Any) -> SpanSpec:
        # Describes an output_schema validation failure with error detail.
        return SpanSpec("agent.output_contract.violation", SpanKind.CHAIN, "agents", TraceDetail.STANDARD, ParentPolicy.AGENT, attributes)

    @staticmethod
    def handoff_requested(**attributes: Any) -> SpanSpec:
        # Describes an auto-handoff being triggered after a completed run.
        return SpanSpec("agent.handoff.requested", SpanKind.CHAIN, "agents", TraceDetail.VERBOSE, ParentPolicy.AGENT, attributes)

    @staticmethod
    def handoff_generated(**attributes: Any) -> SpanSpec:
        # Describes a handoff document being successfully produced.
        return SpanSpec("agent.handoff.generated", SpanKind.CHAIN, "agents", TraceDetail.VERBOSE, ParentPolicy.AGENT, attributes)

    @staticmethod
    def handoff_failed(**attributes: Any) -> SpanSpec:
        # Describes a handoff generation failure with fail-open behavior.
        return SpanSpec("agent.handoff.failed", SpanKind.CHAIN, "agents", TraceDetail.STANDARD, ParentPolicy.AGENT, attributes)

    @staticmethod
    def modality_resolved(**attributes: Any) -> SpanSpec:
        # Describes the resolved ModelModality after AUTO detection.
        return SpanSpec("agent.modality.resolved", SpanKind.CHAIN, "agents", TraceDetail.VERBOSE, ParentPolicy.AGENT, attributes)

    @staticmethod
    def aggregate_plan_resolved(**attributes: Any) -> SpanSpec:
        # Describes a multi-model aggregation plan being built.
        return SpanSpec("agent.aggregate.plan_resolved", SpanKind.CHAIN, "agents", TraceDetail.VERBOSE, ParentPolicy.AGENT, attributes)

    @staticmethod
    def algorithm_resolved(**attributes: Any) -> SpanSpec:
        # Describes the resolved ContextWindowAlgorithm name and admission mode.
        return SpanSpec("agent.algorithm.resolved", SpanKind.CHAIN, "agents", TraceDetail.VERBOSE, ParentPolicy.AGENT, attributes)

    @staticmethod
    def mcp_attached(**attributes: Any) -> SpanSpec:
        # Describes an MCP server being attached to the agent.
        return SpanSpec("agent.mcp.attached", SpanKind.CHAIN, "agents", TraceDetail.VERBOSE, ParentPolicy.AGENT, attributes)

    @staticmethod
    def runner_created(**attributes: Any) -> SpanSpec:
        # Describes the agent runner being constructed with provider and model info.
        return SpanSpec("agent.runner.created", SpanKind.CHAIN, "agents", TraceDetail.DIAGNOSTIC, ParentPolicy.AGENT, attributes)


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


__all__ = ["AgentTrace", "AggregateTrace"]
