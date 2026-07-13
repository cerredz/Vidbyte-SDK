"""Context Protocol Header

Description:
    Defines stable enum values for ledger-driven multi-agent orchestration.
Purpose:
    Keeps task state, orchestrator actions, and stop reasons independent from
    concrete agent implementations and serialization formats.
Architecture:
    - TaskStatus: Stored TaskLedger lifecycle states.
    - OrchestratorAction: One controller decision per orchestration round.
    - MultiAgentStopReason: Terminal outcome classification for a team run.
Relations:
    Imported by vidbyte.lib.dataclasses.multi_agent and vidbyte.agents.multi.
"""

from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    """Stored lifecycle states for one task ledger record."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SUPERSEDED = "superseded"


class OrchestratorAction(str, Enum):
    """Actions the orchestrator may request for the next controller round."""

    DELEGATE = "delegate"
    REPLAN = "replan"
    FINISH = "finish"


class MultiAgentStopReason(str, Enum):
    """Machine-readable terminal reasons for a multi-agent run."""

    COMPLETED = "completed"
    PARTIAL = "partial"
    MAX_ROUNDS = "max_rounds"
    MAX_REPLANS = "max_replans"
    TIMEOUT = "timeout"
    UNRECOVERABLE = "unrecoverable"


__all__ = ["MultiAgentStopReason", "OrchestratorAction", "TaskStatus"]
