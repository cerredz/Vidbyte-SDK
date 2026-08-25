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
from vidbyte.lib.enums.fallback import FallbackPolicyMode
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
    "BudgetPreset",
    "DocumentType",
    "ContextMinimalFanoutSkill",
    "FallbackPolicyMode",
    "ModelModality",
    "ModelNameModality",
    "ModelProvider",
    "MultiAgentStopReason",
    "OrchestratorAction",
    "PermissionPreset",
    "PinPolicy",
    "Platform",
    "Prompt",
    "Skill",
    "SkillEnums",
    "StructuredOutputSupport",
    "TaskStatus",
]
