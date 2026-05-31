"""Context Protocol Header

Description:
    Exposes context-window algorithm implementations.
Purpose:
    Keeps runtime context algorithms separate from preset registration and
    public context primitives.
Architecture:
    - Tool-result admission algorithms from tool_results.
    - Reflexion runtime context-window algorithm from reflexion.
    - Adversarial reflection runtime context-window algorithm from adversarial_reflection.
    - Multi-provider agentic grader context-window algorithm from multi_provider_agentic_grader.
Relations:
    Used by vidbyte.context.presets and AgentRuntime.
"""

from __future__ import annotations

from vidbyte.context.algorithms.adversarial_reflection import AdversarialReflectionAlgorithm
from vidbyte.context.algorithms.reflexion import ReflexionAlgorithm
from vidbyte.context.algorithms.multi_provider_agentic_grader import MultiProviderAgenticGraderAlgorithm
from vidbyte.context.algorithms.tool_results import (
    ContextWindowAlgorithm,
    ToolResultAdmission,
)

__all__ = [
    "AdversarialReflectionAlgorithm",
    "ContextWindowAlgorithm",
    "MultiProviderAgenticGraderAlgorithm",
    "ReflexionAlgorithm",
    "ToolResultAdmission",
]

