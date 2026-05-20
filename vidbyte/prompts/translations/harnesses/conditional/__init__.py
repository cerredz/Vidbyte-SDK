# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines package exports for conditional harnesses prompt translations.
# Purpose: Groups and exposes standard prompt translations for conditional loops and stopping evaluations.
# Architecture & Functions:
#   - Bundles ConditionalLoopAgentPrompt, ConditionalStoppingEvaluatorPrompt.
# Codebase Relation:
#   - Exposes translations under the conditional harness namespace.
# ==============================================================================

from __future__ import annotations

from vidbyte.prompts.translations.harnesses.conditional.loop_agent import ConditionalLoopAgentPrompt
from vidbyte.prompts.translations.harnesses.conditional.stopping_evaluator import (
    ConditionalStoppingEvaluatorPrompt,
)

__all__ = [
    "ConditionalLoopAgentPrompt",
    "ConditionalStoppingEvaluatorPrompt",
]
