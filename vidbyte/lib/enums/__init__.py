"""FILE: vidbyte/lib/enums/__init__.py

PURPOSE:
    Re-exports the SDK's enum contracts from one stable namespace for agents,
    providers, contexts, tools, and runtimes.

ROLE IN CODEBASE:
    Imports concrete enum definitions from sibling modules and is consumed by
    package-level configuration and runtime modules. It owns the public enum
    export list, not the behavior represented by those enums.

ARCHITECTURE NOTE:
    Keeping enum definitions in focused modules and exports here prevents
    runtime modules from duplicating string constants while preserving a single
    public import path.

FUNCTION INVENTORY:
    No functions. ``__all__`` lists the public enum classes.

WHAT NOT TO DO IN THIS FILE:
    1. Do not implement enum behavior here; edit the owning sibling module.
    2. Do not import runtime instances or add import-time side effects.

TEST FILES:
    Configuration and runtime tests cover the exported enum namespace.
"""

from __future__ import annotations

from vidbyte.lib.enums.agent_runtime import AgentRuntimeStateKey, AgentRuntimeType
from vidbyte.lib.enums.config import AgentType, DocumentType
from vidbyte.lib.enums.context import BudgetPreset, PermissionPreset
from vidbyte.lib.enums.cot_events import (
    AssumptionAction,
    BasisType,
    CotEventEnum,
    HypothesisStatus,
    ImpactLevel,
    ProgressState,
    ReturnableOption,
    Reversibility,
)
from vidbyte.lib.enums.model_modality import ModelModality, ModelNameModality
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.enums.multi_agent import (
    MultiAgentStopReason,
    OrchestratorAction,
    TaskStatus,
)
from vidbyte.lib.enums.platform import Platform
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.enums.reasoning_strategies import (
    AbsenceEvidenceSignificance,
    BurdenOfProofVerdict,
    CircularityVerdict,
    CompositionDivisionValidity,
    ConsistencyStatus,
    DefeasibleRuleApplies,
    EquivocationFallacy,
    IdentityVerdict,
    ModalStatus,
    NecessarySufficientVerdict,
    PartitionVerdict,
    PredictMatch,
    QuantifierKind,
    QuantifierVerdict,
    ReasoningStrategyEnum,
    RegressStyle,
    StrawmanCriticism,
    TestimonyTrust,
    TransitivityConsistency,
)
from vidbyte.lib.enums.skills import ContextMinimalFanoutSkill, Skill
from vidbyte.lib.enums.skills import Skills as SkillEnums
from vidbyte.lib.enums.sources import PinPolicy
from vidbyte.lib.enums.structured_output import StructuredOutputSupport

__all__ = [
    "AbsenceEvidenceSignificance",
    "AgentRuntimeStateKey",
    "AgentRuntimeType",
    "AgentType",
    "AssumptionAction",
    "BasisType",
    "BudgetPreset",
    "BurdenOfProofVerdict",
    "CircularityVerdict",
    "CompositionDivisionValidity",
    "ConsistencyStatus",
    "ContextMinimalFanoutSkill",
    "CotEventEnum",
    "DefeasibleRuleApplies",
    "DocumentType",
    "EquivocationFallacy",
    "HypothesisStatus",
    "IdentityVerdict",
    "ImpactLevel",
    "ModalStatus",
    "ModelModality",
    "ModelNameModality",
    "ModelProvider",
    "MultiAgentStopReason",
    "NecessarySufficientVerdict",
    "OrchestratorAction",
    "PartitionVerdict",
    "PermissionPreset",
    "PinPolicy",
    "Platform",
    "PredictMatch",
    "ProgressState",
    "Prompt",
    "QuantifierKind",
    "QuantifierVerdict",
    "ReasoningStrategyEnum",
    "RegressStyle",
    "ReturnableOption",
    "Reversibility",
    "Skill",
    "SkillEnums",
    "StrawmanCriticism",
    "StructuredOutputSupport",
    "TaskStatus",
    "TestimonyTrust",
    "TransitivityConsistency",
]
