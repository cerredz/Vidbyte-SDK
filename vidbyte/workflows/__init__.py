"""FILE: vidbyte/workflows/__init__.py
PURPOSE: Defines the stable public import surface for validated state-machine workflows.
ROLE IN CODEBASE: Re-exports contracts and adapters to SDK users and the root vidbyte package.

ARCHITECTURE NOTE:
    Private compiled-definition and per-run helper classes remain in graph.py and
    machine.py. Only extension protocols, value contracts, adapters, public
    errors, StateGraph, and StateMachine are compatibility promises here.

PUBLIC API INVENTORY:
    StateGraph / StateMachine: Declaration and compiled execution surfaces.
    CallableStage / AgentStage / CallableRouter: Work and branch adapters.
    CallableValidator / SchemaValidator / GraderValidator / AgentValidator:
        Primitive validation adapters.
    AllOfValidator / AnyOfValidator / WeightedValidator: Composite validators.
    contracts.py exports: Contexts, policies, protocols, records, events, results.
    errors.py exports: Typed declaration and execution failures.

COMMON MODIFICATION PATTERNS:
    When adding a supported public name, update __all__, root vidbyte/__init__.py,
    README.md, llms.txt, and the workflows folder README in the same change.

WHAT NOT TO DO IN THIS FILE:
    1. Do not implement workflow behavior in the export module.
    2. Do not export private _CompiledGraph or per-run helper types.
    3. Do not add a VidbyteSDK client facade for direct construction APIs.

KNOWN EDGE CASES:
    Import order keeps graph.py's lazy StateMachine import from creating a cycle.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-harness-state-machine-runtime.md

TESTS:
    Root and package import smoke commands are defined in the approved design.
"""

from __future__ import annotations

from vidbyte.workflows.approval import AlwaysConfirm, ApprovalContext, ApprovalGate, ConfirmationPolicy, ConfirmRisky, NeverConfirm, RiskLevel
from vidbyte.workflows.budget import BudgetLedger, BudgetSnapshot, ChildBudgetPolicy, CostModel, StaticCostModel, UnknownCostPolicy, UsageReport, WorkflowBudget
from vidbyte.workflows.capabilities import (
    ActionContext,
    ActionDecision,
    ActionGuard,
    ActionImpact,
    ActionImpactEstimator,
    ActionPolicy,
    ActionPolicyMiddleware,
    AgentModelRoute,
    CallableImpactEstimator,
    CommandArgumentGuard,
    EditBudgetGuard,
    ModelRetryPolicy,
    PathActionGuard,
    StageCapabilities,
    ToolCapabilityResolver,
    ToolVisibility,
    ToolVisibilityMode,
)
from vidbyte.workflows.contracts import (
    MachineStatus,
    PendingRequest,
    PendingRequestKind,
    RetryPolicy,
    ResumeCommand,
    RouteTarget,
    Router,
    RoutingContext,
    Stage,
    StageContext,
    StageExecution,
    StagePolicy,
    StageResult,
    StateMachineResult,
    StateMachineSettings,
    TerminalStatus,
    TransitionRecord,
    ValidationContext,
    ValidationPhase,
    ValidationRecord,
    ValidationResult,
    ValidationStatus,
    Validator,
    ValidatorErrorPolicy,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowCommand,
    WorkflowFeedback,
    WorkflowInterrupt,
    WorkflowLifecycleStatus,
    WorkflowObserver,
)
from vidbyte.workflows.detection import StuckDetection, StuckDetectionPolicy, StuckDetectorMiddleware, StuckPattern
from vidbyte.workflows.detours import CallableSignalMatcher, DetourFrame, DetourReturnMode, DetourRule, FileSignalMatcher, SignalMatcher, SignalTypeMatcher, WorkflowSignal
from vidbyte.workflows.errors import (
    StageExecutionError,
    TransitionLimitError,
    WorkflowDefinitionError,
    WorkflowError,
    WorkflowErrorRecord,
    WorkflowExecutionError,
    WorkflowApprovalError,
    WorkflowBudgetError,
    WorkflowCapabilityError,
    WorkflowCommandError,
    WorkflowDetourError,
    WorkflowInterruptError,
    WorkflowPersistenceError,
    WorkflowResumeError,
    WorkflowRoutingError,
    WorkflowStateError,
    WorkflowStuckError,
    WorkflowSubgraphError,
    WorkflowValidationError,
)
from vidbyte.workflows.events import WORKFLOW_SCHEMA_VERSION, WorkflowEventFactory, WorkflowEventPayload, workflow_json_value
from vidbyte.workflows.graph import StateGraph
from vidbyte.workflows.machine import StateMachine
from vidbyte.workflows.routing import CallableRouter
from vidbyte.workflows.stages import AgentStage, CallableStage
from vidbyte.workflows.persistence import WorkflowCheckpoint, WorkflowCheckpointPolicy, WorkflowDefinitionRecord, WorkflowStore, assert_checkpoint_compatible
from vidbyte.workflows.state import AppendReducer, CallableReducer, MergeMappingReducer, ReplaceReducer, SetUnionReducer, StateChannel, StateCodec, StateCommitMode, StateReducer, StateSchema
from vidbyte.workflows.stores import FileWorkflowStore, InMemoryWorkflowStore
from vidbyte.workflows.subgraphs import ChildFailurePolicy, Send, SubgraphBinding, SubgraphExecutor, SubgraphSummary
from vidbyte.workflows.validation import AgentValidator, AllOfValidator, AnyOfValidator, CallableValidator, GraderValidator, SchemaValidator, WeightedValidator


__all__ = [
    "ActionContext",
    "ActionDecision",
    "ActionGuard",
    "ActionImpact",
    "ActionImpactEstimator",
    "ActionPolicy",
    "ActionPolicyMiddleware",
    "AgentModelRoute",
    "AgentStage",
    "AgentValidator",
    "AllOfValidator",
    "AnyOfValidator",
    "AlwaysConfirm",
    "AppendReducer",
    "ApprovalContext",
    "ApprovalGate",
    "BudgetLedger",
    "BudgetSnapshot",
    "CallableImpactEstimator",
    "CallableRouter",
    "CallableReducer",
    "CallableSignalMatcher",
    "CallableStage",
    "CallableValidator",
    "GraderValidator",
    "ChildBudgetPolicy",
    "ChildFailurePolicy",
    "CommandArgumentGuard",
    "ConfirmationPolicy",
    "ConfirmRisky",
    "CostModel",
    "DetourFrame",
    "DetourReturnMode",
    "DetourRule",
    "EditBudgetGuard",
    "FileSignalMatcher",
    "FileWorkflowStore",
    "InMemoryWorkflowStore",
    "MachineStatus",
    "MergeMappingReducer",
    "ModelRetryPolicy",
    "NeverConfirm",
    "PathActionGuard",
    "PendingRequest",
    "PendingRequestKind",
    "ReplaceReducer",
    "RetryPolicy",
    "ResumeCommand",
    "RiskLevel",
    "RouteTarget",
    "Router",
    "RoutingContext",
    "SchemaValidator",
    "Send",
    "SetUnionReducer",
    "SignalMatcher",
    "SignalTypeMatcher",
    "Stage",
    "StageContext",
    "StageExecution",
    "StageExecutionError",
    "StagePolicy",
    "StageCapabilities",
    "StageResult",
    "StateGraph",
    "StateMachine",
    "StateMachineResult",
    "StateMachineSettings",
    "StateChannel",
    "StateCodec",
    "StateCommitMode",
    "StateReducer",
    "StateSchema",
    "StaticCostModel",
    "StuckDetection",
    "StuckDetectionPolicy",
    "StuckDetectorMiddleware",
    "StuckPattern",
    "SubgraphBinding",
    "SubgraphExecutor",
    "SubgraphSummary",
    "TerminalStatus",
    "ToolCapabilityResolver",
    "ToolVisibility",
    "ToolVisibilityMode",
    "TransitionLimitError",
    "TransitionRecord",
    "ValidationContext",
    "ValidationPhase",
    "ValidationRecord",
    "ValidationResult",
    "ValidationStatus",
    "Validator",
    "ValidatorErrorPolicy",
    "WeightedValidator",
    "UnknownCostPolicy",
    "UsageReport",
    "WorkflowApprovalError",
    "WorkflowBudget",
    "WorkflowBudgetError",
    "WorkflowCapabilityError",
    "WorkflowCheckpoint",
    "WorkflowCheckpointPolicy",
    "WorkflowCommand",
    "WorkflowCommandError",
    "WorkflowDefinitionRecord",
    "WorkflowDefinitionError",
    "WorkflowError",
    "WorkflowErrorRecord",
    "WorkflowEvent",
    "WorkflowEventFactory",
    "WorkflowEventPayload",
    "WorkflowEventType",
    "WorkflowExecutionError",
    "WorkflowDetourError",
    "WorkflowFeedback",
    "WorkflowInterrupt",
    "WorkflowInterruptError",
    "WorkflowLifecycleStatus",
    "WorkflowObserver",
    "WorkflowRoutingError",
    "WorkflowPersistenceError",
    "WorkflowResumeError",
    "WorkflowSignal",
    "WorkflowStateError",
    "WorkflowStore",
    "WorkflowStuckError",
    "WorkflowSubgraphError",
    "WorkflowValidationError",
    "WORKFLOW_SCHEMA_VERSION",
    "assert_checkpoint_compatible",
    "workflow_json_value",
]
