"""Context Protocol Header

Description:
    Encapsulates multi-agent trace and span formatting.
Purpose:
    Keeps tracing policy out of controller branches while exposing small control-only outputs.
Architecture:
    MultiAgentTracer wraps TracerBase run handles, child spans, and JSON summaries.
Relations:
    Used by lifecycle, ledger, dispatcher, orchestrator, and post-run collaborators.
"""

from __future__ import annotations

import json
from typing import Any

from vidbyte.lib.dataclasses.multi_agent import MultiAgentResult, MultiAgentRunState
from vidbyte.lib.tracing import TracerBase


class MultiAgentTracer:
    """Trace multi-agent control flow without serializing arbitrary task payloads."""

    def __init__(self, tracer: TracerBase, agent_name: str) -> None:
        self._tracer = tracer
        self._agent_name = agent_name

    def start_run(self, state: MultiAgentRunState) -> tuple[Any, Any]:
        # The outer trace and run span share one stable run identifier.
        trace = self._tracer.start_trace("agent.run", agent_name=self._agent_name, run_id=state.run_id, strategy="multi_agent")
        try:
            span = self._tracer.start_span("multi_agent.run", run_id=state.run_id)
            return trace, span
        except BaseException as error:
            self._tracer.end_trace(trace, error=error)
            raise

    def finish_run(self, handles: tuple[Any, Any], state: MultiAgentRunState, result: MultiAgentResult | None, error: BaseException | None) -> None:
        # Finish both handles after cleanup so terminal metadata includes cleanup failures.
        trace, span = handles
        output = self.run_output(state, result) if error is None and result is not None else None
        try:
            if span is not None:
                self._tracer.end_span(span, output=output, error=error)
        finally:
            if trace is not None:
                self._tracer.end_trace(trace, output=output, error=error)

    def start_span(self, name: str, **attributes: Any) -> Any:
        # Collaborators use one adapter instead of depending directly on TracerBase.
        return self._tracer.start_span(name, **attributes)

    def end_span(self, span: Any, *, output: str | None = None, error: BaseException | None = None) -> None:
        # Span closure remains consistent across successful and exceptional branches.
        self._tracer.end_span(span, output=output, error=error)

    @classmethod
    def output(cls, **fields: Any) -> str:
        # Trace outputs contain only small deterministic controller fields.
        return json.dumps(fields, sort_keys=True, separators=(",", ":"))

    @classmethod
    def run_output(cls, state: MultiAgentRunState, result: MultiAgentResult) -> str:
        # The run summary deliberately excludes prompts, payloads, reports, and final content.
        return cls.output(run_id=state.run_id, stop_reason=result.stop_reason.value, completed=result.completed, rounds=result.rounds, replans=result.replans, revision=result.ledger.revision, cleanup_errors=len(state.cleanup_error_types))


__all__ = ["MultiAgentTracer"]
