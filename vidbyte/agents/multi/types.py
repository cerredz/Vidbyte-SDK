"""Context Protocol Header

Description:
    Defines callback contracts shared by multi-agent controller modules.
Purpose:
    Gives developers typed control over dispatch approval, serialization,
    report acceptance, worker construction, cleanup, ledger creation, and finish gates.
Architecture:
    - Transfer aliases describe the worker boundary.
    - Lifecycle aliases describe controller-owned factories and callbacks.
Relations:
    Imported by agent.py, orchestrator.py, transfer.py, and public exports.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, TypeAlias

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.types import AgentInput, AgentMessage
from vidbyte.lib.dataclasses.agents import AgentForkSettings
from vidbyte.lib.dataclasses.multi_agent import AgentDispatch, AgentReport, LedgerEvent, MultiAgentSettings, OrchestrationContext, OrchestratorDecision, TaskBlocker, TaskLedgerSnapshot

if TYPE_CHECKING:
    from vidbyte.agents.multi.ledger import TaskLedger


BeforeDispatch: TypeAlias = Callable[[AgentDispatch, TaskLedgerSnapshot], TaskBlocker | None | Awaitable[TaskBlocker | None]]
RequestBuilder: TypeAlias = Callable[[AgentDispatch, TaskLedgerSnapshot], str | AgentInput | Awaitable[str | AgentInput]]
ReportParser: TypeAlias = Callable[[AgentMessage, AgentDispatch, TaskLedgerSnapshot], AgentReport | Awaitable[AgentReport]]
ReportValidator: TypeAlias = Callable[[AgentReport, AgentDispatch, TaskLedgerSnapshot], AgentReport | Awaitable[AgentReport]]
WorkerForkFactory: TypeAlias = Callable[[BaseAgent, AgentForkSettings], BaseAgent]
WorkerCloser: TypeAlias = Callable[[BaseAgent], None | Awaitable[None]]
LedgerFactory: TypeAlias = Callable[[str, AgentInput, tuple[str, ...], MultiAgentSettings], "TaskLedger"]
CompletionCheck: TypeAlias = Callable[[OrchestrationContext, OrchestratorDecision], bool | Awaitable[bool]]
EventHandler: TypeAlias = Callable[[LedgerEvent, TaskLedgerSnapshot], None | Awaitable[None]]
MultiAgentEventCallback: TypeAlias = EventHandler
ManagerAgentFactory: TypeAlias = Callable[[BaseAgent, str, AgentForkSettings], BaseAgent]
ManagerAgentCloser: TypeAlias = Callable[[BaseAgent, str], None | Awaitable[None]]


__all__ = [
    "BeforeDispatch",
    "CompletionCheck",
    "EventHandler",
    "LedgerFactory",
    "ManagerAgentCloser",
    "ManagerAgentFactory",
    "MultiAgentEventCallback",
    "ReportParser",
    "ReportValidator",
    "RequestBuilder",
    "WorkerCloser",
    "WorkerForkFactory",
]
