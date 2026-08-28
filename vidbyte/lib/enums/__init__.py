"""Context Protocol Header

Description:
    Exposes library enums for Vidbyte SDK.
Purpose:
    Exposes all SDK-level enums in a single clean namespace for consumption
    by providers, clients, contexts, and runtimes.
Architecture:
    - Namespace package mapping various enum types.
Relations:
    Imported by agents, providers, contexts, and strategies.
Similar Files:
    - vidbyte/lib/enums/agent_runtime.py: Swappable runtime enums.
"""

from __future__ import annotations

from vidbyte.lib.enums.agent_runtime import AgentRuntimeType
from vidbyte.lib.enums.config import AgentType, DocumentType
from vidbyte.lib.enums.context import BudgetPreset, PermissionPreset
from vidbyte.lib.enums.cot import (
    AgreementLevel,
    BiasAssessment,
    BlockedResponse,
    CalibrationTrend,
    ContextAttachLevel,
    ContextCrowding,
    ContextImbalance,
    Criticality,
    CriteriaOutcome,
    DirectionChangeLevel,
    DisputeVerdict,
    ExpectedSource,
    FactVisibility,
    FailureOwner,
    FixedStatus,
    GapFrequency,
    GapSeverity,
    HandoffCompletenessGap,
    HandoffReason,
    MatchState,
    MonitoringHealth,
    PatternSeenBefore,
    ReadinessLevel,
    RecallMatchOutcome,
    RecheckCost,
    Recoverability,
    ReloadCost,
    ReviewSource,
    SearchExpectedYield,
    SearchFoundOutcome,
    SearchPivot,
    SearchUrgency,
    Severity,
    Staleness,
    SurpriseLevel,
    TestCoverage,
    TestRanStatus,
    TestResult,
    TrustLevel,
    VerificationMethod,
    VerificationVerdict,
    YesNo,
)
from vidbyte.lib.enums.model_modality import ModelModality, ModelNameModality
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.enums.multi_agent import MultiAgentStopReason, OrchestratorAction, TaskStatus
from vidbyte.lib.enums.platform import Platform
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.lib.enums.skills import ContextMinimalFanoutSkill, Skill, Skills as SkillEnums
from vidbyte.lib.enums.sources import PinPolicy
from vidbyte.lib.enums.structured_output import StructuredOutputSupport

__all__ = [
    "AgentRuntimeType",
    "AgentType",
    "AgreementLevel",
    "BiasAssessment",
    "BlockedResponse",
    "BudgetPreset",
    "CalibrationTrend",
    "ContextAttachLevel",
    "ContextCrowding",
    "ContextImbalance",
    "ContextMinimalFanoutSkill",
    "Criticality",
    "CriteriaOutcome",
    "DirectionChangeLevel",
    "DisputeVerdict",
    "DocumentType",
    "ExpectedSource",
    "FactVisibility",
    "FailureOwner",
    "FixedStatus",
    "GapFrequency",
    "GapSeverity",
    "HandoffCompletenessGap",
    "HandoffReason",
    "MatchState",
    "ModelModality",
    "ModelNameModality",
    "ModelProvider",
    "MonitoringHealth",
    "MultiAgentStopReason",
    "OrchestratorAction",
    "PatternSeenBefore",
    "PermissionPreset",
    "PinPolicy",
    "Platform",
    "Prompt",
    "ReadinessLevel",
    "RecallMatchOutcome",
    "RecheckCost",
    "Recoverability",
    "ReloadCost",
    "ReviewSource",
    "SearchExpectedYield",
    "SearchFoundOutcome",
    "SearchPivot",
    "SearchUrgency",
    "Severity",
    "Skill",
    "SkillEnums",
    "Staleness",
    "StructuredOutputSupport",
    "SurpriseLevel",
    "TaskStatus",
    "TestCoverage",
    "TestRanStatus",
    "TestResult",
    "TrustLevel",
    "VerificationMethod",
    "VerificationVerdict",
    "YesNo",
]
