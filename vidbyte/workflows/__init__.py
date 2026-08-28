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
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/validated-state-machine-workflows.md

TESTS:
    Root and package import smoke commands are defined in the approved design.
"""

from __future__ import annotations

from vidbyte.workflows.contracts import (
    MachineStatus,
    RetryPolicy,
    Router,
    RouteTarget,
    RoutingContext,
    Stage,
    StageContext,
    StageExecution,
    StagePolicy,
    StageResult,
    StateMachineResult,
    StateMachineSettings,
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
    WorkflowFeedback,
    WorkflowObserver,
)
from vidbyte.workflows.errors import (
    StageExecutionError,
    TransitionLimitError,
    WorkflowDefinitionError,
    WorkflowError,
    WorkflowExecutionError,
    WorkflowRoutingError,
    WorkflowStateError,
    WorkflowValidationError,
)
from vidbyte.workflows.graph import StateGraph
from vidbyte.workflows.machine import StateMachine
from vidbyte.workflows.routing import CallableRouter
from vidbyte.workflows.stages import AgentStage, CallableStage
from vidbyte.workflows.validation import (
    AgentValidator,
    AllOfValidator,
    AnyOfValidator,
    CallableValidator,
    GraderValidator,
    SchemaValidator,
    WeightedValidator,
)

__all__ = [
    "AgentStage",
    "AgentValidator",
    "AllOfValidator",
    "AnyOfValidator",
    "CallableRouter",
    "CallableStage",
    "CallableValidator",
    "GraderValidator",
    "MachineStatus",
    "RetryPolicy",
    "RouteTarget",
    "Router",
    "RoutingContext",
    "SchemaValidator",
    "Stage",
    "StageContext",
    "StageExecution",
    "StageExecutionError",
    "StagePolicy",
    "StageResult",
    "StateGraph",
    "StateMachine",
    "StateMachineResult",
    "StateMachineSettings",
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
    "WorkflowDefinitionError",
    "WorkflowError",
    "WorkflowEvent",
    "WorkflowEventType",
    "WorkflowExecutionError",
    "WorkflowFeedback",
    "WorkflowObserver",
    "WorkflowRoutingError",
    "WorkflowStateError",
    "WorkflowValidationError",
]
