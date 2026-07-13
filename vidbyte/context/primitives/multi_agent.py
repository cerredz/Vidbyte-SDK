"""Context Protocol Header

Description:
    Defines context primitives used by ledger-driven multi-agent orchestration.
Purpose:
    Keeps request, team, ledger, report, limit, and terminal rendering inside the
    shared context layer instead of embedding context policy in agent runtimes.
Architecture:
    - Domain primitives render explicitly tagged prompt sections.
    - MultiAgentContextSerializer bounds opaque values before JSON encoding.
Relations:
    Managed by vidbyte.context.MultiAgentContext and consumed by multi-agent orchestrators.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.dataclasses.agents import AgentCard
from vidbyte.lib.dataclasses.multi_agent import AgentReport, FinalizationContext, MultiAgentSettings, TaskBlocker, TaskEvidence, TaskLedgerSnapshot, TaskRecord


class MultiAgentContextSerializer:
    """Bounds and serializes values crossing the manager prompt boundary."""

    max_value_chars = 2_000

    @classmethod
    def tagged(cls, name: str, value: str, *, untrusted: bool = False) -> str:
        # Explicit trust boundaries keep worker/user data from blending with manager instructions.
        body = f"<untrusted_data>\n{value}\n</untrusted_data>" if untrusted else value
        return f"<{name}>\n{body}\n</{name}>"

    @classmethod
    def dumps(cls, value: Any) -> str:
        # Deterministic JSON makes trace comparisons and manager retries reproducible.
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)

    @classmethod
    def safe_value(cls, value: Any) -> Any:
        # Opaque or oversized values become type-only markers instead of leaking repr output.
        try:
            encoded = cls.dumps(value)
        except (TypeError, ValueError):
            return {"omitted_type": type(value).__name__}
        if len(encoded) <= cls.max_value_chars:
            return value
        return {"json_chars": len(encoded), "omitted_type": type(value).__name__, "reason": "value_exceeds_render_limit"}

    @classmethod
    def card(cls, card: AgentCard) -> dict[str, Any]:
        # Worker cards expose capability summaries without prompts, tools, or live objects.
        return {"name": card.name, "description": card.description, "capabilities": list(card.capabilities)}

    @classmethod
    def evidence(cls, evidence: TaskEvidence) -> dict[str, Any]:
        # Evidence remains explicitly unverified unless the developer marked it otherwise.
        return {"source": evidence.source, "kind": evidence.kind, "verified": evidence.verified, "value": cls.safe_value(evidence.value)}

    @classmethod
    def blocker(cls, blocker: TaskBlocker) -> dict[str, Any]:
        # Blocker rendering includes only coordination fields needed for recovery.
        return {"code": blocker.code, "message": cls.safe_value(blocker.message), "retryable": blocker.retryable}

    @classmethod
    def task(cls, task: TaskRecord) -> dict[str, Any]:
        # Task rendering intentionally omits arbitrary metadata and event history.
        return {
            "task_id": task.task_id,
            "goal": cls.safe_value(task.goal),
            "owner": task.owner,
            "status": task.status.value,
            "depends_on": list(task.depends_on),
            "required": task.required,
            "acceptance_criteria": [cls.safe_value(item) for item in task.acceptance_criteria],
            "payload": cls.safe_value(task.payload),
            "attempts": task.attempts,
            "max_attempts": task.max_attempts,
            "result": cls.safe_value(task.result),
            "evidence": [cls.evidence(item) for item in task.evidence],
            "blockers": [cls.blocker(item) for item in task.blockers],
            "next_action": cls.safe_value(task.next_action),
        }

    @classmethod
    def ledger(cls, ledger: TaskLedgerSnapshot) -> dict[str, Any]:
        # The manager receives current structural state, not the full audit-event tail.
        return {
            "run_id": ledger.run_id,
            "goal": cls.safe_value(ledger.goal),
            "plan_summary": cls.safe_value(ledger.plan_summary),
            "verified_facts": [cls.safe_value(item) for item in ledger.verified_facts],
            "facts_to_find": [cls.safe_value(item) for item in ledger.facts_to_find],
            "facts_to_derive": [cls.safe_value(item) for item in ledger.facts_to_derive],
            "educated_guesses": [cls.safe_value(item) for item in ledger.educated_guesses],
            "tasks": [cls.task(task) for task in ledger.tasks],
            "next_action": cls.safe_value(ledger.next_action),
            "revision": ledger.revision,
        }

    @classmethod
    def report(cls, report: AgentReport | None) -> dict[str, Any] | None:
        # The latest report is untrusted worker output even after structural validation.
        if report is None:
            return None
        return {
            "task_id": report.task_id,
            "status": report.status.value,
            "result": cls.safe_value(report.result),
            "evidence": [cls.evidence(item) for item in report.evidence],
            "blockers": [cls.blocker(item) for item in report.blockers],
            "next_action": cls.safe_value(report.next_action),
        }


@dataclass(frozen=True, slots=True)
class MultiAgentRequestContextItem:
    """Untrusted user request supplied to every orchestration phase."""

    prompt: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "multi_agent_request"
    title: str = "Multi-Agent Request"
    primitive_id: str | None = "multi_agent:request"
    primitive_frozen: bool = True

    def to_context_text(self) -> str:
        # User-authored request text always renders behind an untrusted-data boundary.
        return MultiAgentContextSerializer.tagged("request", self.prompt, untrusted=True)


@dataclass(frozen=True, slots=True)
class MultiAgentTeamContextItem:
    """Trusted team instructions and bounded worker capability cards."""

    instructions: str
    team: tuple[AgentCard, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "multi_agent_team"
    title: str = "Multi-Agent Team"
    primitive_id: str | None = "multi_agent:team"
    primitive_frozen: bool = True

    def to_context_text(self) -> str:
        # Team configuration is trusted SDK context and excludes child system prompts.
        cards = MultiAgentContextSerializer.dumps([MultiAgentContextSerializer.card(card) for card in self.team])
        return "\n".join((MultiAgentContextSerializer.tagged("team_instructions", self.instructions), MultiAgentContextSerializer.tagged("team", cards)))


@dataclass(frozen=True, slots=True)
class MultiAgentLedgerContextItem:
    """Untrusted ledger snapshot available to the manager."""

    ledger: TaskLedgerSnapshot
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "multi_agent_ledger"
    title: str = "Multi-Agent Ledger"
    primitive_id: str | None = "multi_agent:ledger"
    primitive_frozen: bool = True

    def to_context_text(self) -> str:
        # Ledger content includes model- and worker-authored values, so it stays untrusted.
        rendered = MultiAgentContextSerializer.dumps(MultiAgentContextSerializer.ledger(self.ledger))
        return MultiAgentContextSerializer.tagged("ledger", rendered, untrusted=True)


@dataclass(frozen=True, slots=True)
class MultiAgentReportContextItem:
    """Latest structurally valid but semantically untrusted worker report."""

    report: AgentReport | None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "multi_agent_report"
    title: str = "Multi-Agent Report"
    primitive_id: str | None = "multi_agent:report"
    primitive_frozen: bool = True

    def to_context_text(self) -> str:
        # Report payloads never become trusted instructions merely because parsing succeeded.
        rendered = MultiAgentContextSerializer.dumps(MultiAgentContextSerializer.report(self.report))
        return MultiAgentContextSerializer.tagged("last_report", rendered, untrusted=True)


@dataclass(frozen=True, slots=True)
class MultiAgentLimitsContextItem:
    """Finite controller budgets and current orchestration counters."""

    settings: MultiAgentSettings
    round: int
    replans: int
    stalls: int
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "multi_agent_limits"
    title: str = "Multi-Agent Limits"
    primitive_id: str | None = "multi_agent:limits"
    primitive_frozen: bool = True

    def to_context_text(self) -> str:
        # Explicit limits remind the manager that its policy loop has finite authority.
        value = {
            "current": {"round": self.round, "replans": self.replans, "stalls": self.stalls},
            "maximum": {"events": self.settings.max_events, "replans": self.settings.max_replans, "rounds": self.settings.max_rounds, "stalls_before_replan": self.settings.replan_after_stalls, "task_attempts": self.settings.max_task_attempts},
            "timeouts_seconds": {"orchestrator": self.settings.orchestrator_timeout_seconds, "run": self.settings.run_timeout_seconds, "worker": self.settings.worker_timeout_seconds},
        }
        return MultiAgentContextSerializer.tagged("limits", MultiAgentContextSerializer.dumps(value))


@dataclass(frozen=True, slots=True)
class MultiAgentTerminalContextItem:
    """Terminal controller outcome supplied only during final synthesis."""

    finalization: FinalizationContext
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "multi_agent_terminal"
    title: str = "Multi-Agent Terminal State"
    primitive_id: str | None = "multi_agent:terminal"
    primitive_frozen: bool = True

    def to_context_text(self) -> str:
        # Candidate answers and rationales remain untrusted manager-generated data.
        decision = self.finalization.finish_decision
        terminal = {"candidate_answer": MultiAgentContextSerializer.safe_value(self.finalization.candidate_answer), "completed": self.finalization.completed, "stop_reason": self.finalization.stop_reason.value}
        finish = None if decision is None else {"action": decision.action.value, "final_answer": MultiAgentContextSerializer.safe_value(decision.final_answer), "rationale": MultiAgentContextSerializer.safe_value(decision.rationale)}
        return "\n".join((
            MultiAgentContextSerializer.tagged("terminal_state", MultiAgentContextSerializer.dumps(terminal), untrusted=True),
            MultiAgentContextSerializer.tagged("finish_decision", MultiAgentContextSerializer.dumps(finish), untrusted=True),
        ))


__all__ = [
    "MultiAgentContextSerializer",
    "MultiAgentLedgerContextItem",
    "MultiAgentLimitsContextItem",
    "MultiAgentReportContextItem",
    "MultiAgentRequestContextItem",
    "MultiAgentTeamContextItem",
    "MultiAgentTerminalContextItem",
]
