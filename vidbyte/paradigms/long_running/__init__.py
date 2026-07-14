"""Context Protocol Header

Path: vidbyte/paradigms/long_running/__init__.py
Purpose: Expose the complete durable long-running family from one stable namespace.
Architecture: Re-exports public contracts, stores, services, errors, and the paradigm;
implementation remains separated across focused family modules.
Exports: LongRunningParadigm and advanced orchestration/persistence contracts.
Invariants: Importing the namespace creates no stores, agents, or run state.
Do not: Start execution or hide live dependency construction in package imports.
Related: vidbyte/paradigms/README.md and long_running/README.md.
Tests: Existing public import verification; no new tests by approved workflow.
"""

from vidbyte.paradigms.long_running.client import LongRunningClient
from vidbyte.paradigms.long_running.context import LongRunningContextBroker, RoleAgentBundle, StateVerifiedContextSource
from vidbyte.paradigms.long_running.controller import LongRunningController
from vidbyte.paradigms.long_running.errors import LongRunningConfigurationError, LongRunningError, LongRunningFinalizationError, LongRunningLedgerError, LongRunningPlanError, LongRunningRecoveryRequiredError, LongRunningResumeError, LongRunningVerificationError
from vidbyte.paradigms.long_running.execution import AttemptIsolationStatus, AttemptIsolator, AttemptLease, TaskExecutionService
from vidbyte.paradigms.long_running.ledger import BehaviorFingerprint, FileRunLedgerStore, InMemoryRunLedgerStore, LongRunningCodec, LongRunningEvent, LongRunningEventKind, RunLedger, RunLedgerSnapshot, RunLedgerStore
from vidbyte.paradigms.long_running.paradigm import LongRunningParadigm
from vidbyte.paradigms.long_running.planning import LongRunningPlanner, ReadyTaskScheduler, TaskGraphReconciler, TaskGraphValidator
from vidbyte.paradigms.long_running.types import AgentRoleSettings, ArtifactRef, BehaviorFingerprintProvider, CriterionResult, DriftDecision, DriftReview, EvidenceRecord, GoalContract, InterruptedAttemptPolicy, LongRunningResult, LongRunningResumeOptions, LongRunningRunOptions, LongRunningRunStatus, LongRunningSettings, LongRunningState, LongRunningStopReason, LongRunningTask, LongRunningTaskState, LongRunningTaskStatus, LongRunningUsage, ProcedureValidationContext, TaskAttempt, TaskGraph, TaskResult, TaskValidationContext, ValidatorResult, VerificationResult
from vidbyte.paradigms.long_running.verification import FinalizationService, LedgerProcedurePromotionAuthority, ProcedureLearningService, ProcedureValidator, TaskValidator, VerificationService

__all__ = [
    "AgentRoleSettings", "ArtifactRef", "AttemptIsolationStatus", "AttemptIsolator",
    "AttemptLease", "BehaviorFingerprint", "BehaviorFingerprintProvider",
    "CriterionResult", "DriftDecision", "DriftReview", "EvidenceRecord",
    "FileRunLedgerStore", "FinalizationService", "GoalContract",
    "InMemoryRunLedgerStore", "InterruptedAttemptPolicy",
    "LedgerProcedurePromotionAuthority", "LongRunningClient", "LongRunningCodec",
    "LongRunningConfigurationError", "LongRunningContextBroker",
    "LongRunningController", "LongRunningError", "LongRunningEvent",
    "LongRunningEventKind", "LongRunningFinalizationError", "LongRunningLedgerError",
    "LongRunningParadigm", "LongRunningPlanError", "LongRunningPlanner",
    "LongRunningRecoveryRequiredError", "LongRunningResult", "LongRunningResumeError",
    "LongRunningResumeOptions", "LongRunningRunOptions", "LongRunningRunStatus",
    "LongRunningSettings", "LongRunningState", "LongRunningStopReason",
    "LongRunningTask", "LongRunningTaskState", "LongRunningTaskStatus",
    "LongRunningUsage", "LongRunningVerificationError", "ProcedureLearningService",
    "ProcedureValidationContext", "ProcedureValidator", "ReadyTaskScheduler",
    "RoleAgentBundle", "RunLedger", "RunLedgerSnapshot", "RunLedgerStore",
    "StateVerifiedContextSource", "TaskAttempt", "TaskExecutionService", "TaskGraph",
    "TaskGraphReconciler", "TaskGraphValidator", "TaskResult",
    "TaskValidationContext", "TaskValidator", "ValidatorResult", "VerificationResult",
    "VerificationService",
]
