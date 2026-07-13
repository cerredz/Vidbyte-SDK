"""Context Protocol Header

Description:
    Exposes Vidbyte's ledger-driven multi-agent orchestration surface.
Purpose:
    Provides stable imports for the team facade, orchestrator policy, ledger,
    transfer hooks, settings, records, enums, and callback contracts.
Architecture:
    - Re-exports implementation classes from this folder.
    - Re-exports central immutable contracts from vidbyte.lib.
Relations:
    Imported by vidbyte.agents, AgentClient.multi(), and the root vidbyte namespace.
"""

from __future__ import annotations

from vidbyte.agents.multi.agent import MultiAgent
from vidbyte.agents.multi.ledger import TaskLedger
from vidbyte.agents.multi.orchestrator import FinalizationRenderer, MagenticOneOrchestrator, MultiAgentOrchestrator, OrchestrationRenderer, default_finalization_renderer, default_orchestration_renderer
from vidbyte.agents.multi.transfer import AgentBinding, AgentTransfer, default_report_parser, default_request_builder
from vidbyte.agents.multi.types import BeforeDispatch, CompletionCheck, EventHandler, LedgerFactory, ManagerAgentCloser, ManagerAgentFactory, MultiAgentEventCallback, ReportParser, ReportValidator, RequestBuilder, WorkerCloser, WorkerForkFactory
from vidbyte.lib.dataclasses.multi_agent import AgentDispatch, AgentReport, FinalizationContext, LedgerEvent, MultiAgentResult, MultiAgentSettings, OrchestrationContext, OrchestratorDecision, OrchestratorPlan, TaskBlocker, TaskEvidence, TaskLedgerSnapshot, TaskRecord, TaskSpec
from vidbyte.lib.enums.multi_agent import MultiAgentStopReason, OrchestratorAction, TaskStatus

__all__ = [
    "AgentBinding",
    "AgentDispatch",
    "AgentReport",
    "AgentTransfer",
    "BeforeDispatch",
    "CompletionCheck",
    "EventHandler",
    "FinalizationContext",
    "FinalizationRenderer",
    "LedgerEvent",
    "LedgerFactory",
    "MagenticOneOrchestrator",
    "ManagerAgentCloser",
    "ManagerAgentFactory",
    "MultiAgent",
    "MultiAgentEventCallback",
    "MultiAgentOrchestrator",
    "MultiAgentResult",
    "MultiAgentSettings",
    "MultiAgentStopReason",
    "OrchestrationContext",
    "OrchestrationRenderer",
    "OrchestratorAction",
    "OrchestratorDecision",
    "OrchestratorPlan",
    "ReportParser",
    "ReportValidator",
    "RequestBuilder",
    "TaskBlocker",
    "TaskEvidence",
    "TaskLedger",
    "TaskLedgerSnapshot",
    "TaskRecord",
    "TaskSpec",
    "TaskStatus",
    "WorkerCloser",
    "WorkerForkFactory",
    "default_finalization_renderer",
    "default_orchestration_renderer",
    "default_report_parser",
    "default_request_builder",
]
