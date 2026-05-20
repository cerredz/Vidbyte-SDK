# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the prompt default registration hooks for the Vidbyte SDK.
# Purpose: Automatically instantiates and registers all built-in default strategy and harness
#          prompt translations upon PromptRegistry initialization.
# Architecture & Functions:
#   - register_defaults(registry): Central function registering standard default prompt classes.
# Codebase Relation:
#   - Automatically called by PromptRegistry or when the client initializes.
# Similar Files:
#   - None (houses built-in registration routines specifically)
# ==============================================================================

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.prompts.translations.harnesses.conditional.loop_agent import ConditionalLoopAgentPrompt
from vidbyte.prompts.translations.harnesses.conditional.stopping_evaluator import (
    ConditionalStoppingEvaluatorPrompt,
)
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

if TYPE_CHECKING:
    from vidbyte.prompts.registry import PromptRegistry


def register_defaults(registry: PromptRegistry) -> None:
    """Instantiates and registers all default SDK strategy and harness prompt translations."""
    # ReAct
    registry.register(ReActSystemPrompt())
    registry.register(ReActIterationPrompt())

    # Tree of Thoughts
    registry.register(TreeOfThoughtsBranchPrompt())
    registry.register(TreeOfThoughtsScoringPrompt())

    # Reflexion
    registry.register(ReflexionActorPrompt())
    registry.register(ReflexionEvaluatorPrompt())
    registry.register(ReflexionReflectorPrompt())

    # Self-Consistency
    registry.register(SelfConsistencyPrompt())

    # Step-Back
    registry.register(StepBackAbstractionPrompt())
    registry.register(StepBackReasoningPrompt())

    # Conditional Harness
    registry.register(ConditionalLoopAgentPrompt())
    registry.register(ConditionalStoppingEvaluatorPrompt())
