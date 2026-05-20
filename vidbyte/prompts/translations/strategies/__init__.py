# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines package exports for strategies prompt translations.
# Purpose: Groups and exposes all standard prompt translations for strategy loops.
# Architecture & Functions:
#   - Bundles ReAct, TreeOfThoughts, Reflexion, SelfConsistency, StepBack prompts.
# Codebase Relation:
#   - Direct import directory for strategy translations.
# ==============================================================================

from __future__ import annotations

from vidbyte.prompts.translations.strategies.react import ReActIterationPrompt, ReActSystemPrompt
from vidbyte.prompts.translations.strategies.reflexion import (
    ReflexionActorPrompt,
    ReflexionEvaluatorPrompt,
    ReflexionReflectorPrompt,
)
from vidbyte.prompts.translations.strategies.self_consistency import SelfConsistencyPrompt
from vidbyte.prompts.translations.strategies.step_back import (
    StepBackAbstractionPrompt,
    StepBackReasoningPrompt,
)
from vidbyte.prompts.translations.strategies.tree_of_thoughts import (
    TreeOfThoughtsBranchPrompt,
    TreeOfThoughtsScoringPrompt,
)

__all__ = [
    "ReActSystemPrompt",
    "ReActIterationPrompt",
    "TreeOfThoughtsBranchPrompt",
    "TreeOfThoughtsScoringPrompt",
    "ReflexionActorPrompt",
    "ReflexionEvaluatorPrompt",
    "ReflexionReflectorPrompt",
    "SelfConsistencyPrompt",
    "StepBackAbstractionPrompt",
    "StepBackReasoningPrompt",
]
