"""Context Protocol Header

Description:
    Exports the context-minimal fanout paradigm and its public data contracts.
Purpose:
    Provides the concrete first Vidbyte paradigm: extract context, split into
    non-overlapping prompts, de-overlap adversarially, and implement in parallel.
Architecture:
    - ContextMinimalFanoutParadigm: The four-stage harness.
    - ContextMinimalFanoutClient: Namespace factory.
    - Typed contracts: settings, environment context, split plan, results.
Relations:
    Re-exported by vidbyte.paradigms and the top-level vidbyte package.
"""

from __future__ import annotations

from vidbyte.paradigms.context_minimal_fanout.client import ContextMinimalFanoutClient
from vidbyte.paradigms.context_minimal_fanout.paradigm import ContextMinimalFanoutParadigm
from vidbyte.paradigms.context_minimal_fanout.types import (
    AgentRoleSettings,
    ContextFile,
    ContextMinimalFanoutResult,
    ContextMinimalFanoutSettings,
    EnvironmentContext,
    ImplementationOutput,
    PromptSplitPlan,
    SplitPrompt,
)

__all__ = [
    "AgentRoleSettings",
    "ContextFile",
    "ContextMinimalFanoutClient",
    "ContextMinimalFanoutParadigm",
    "ContextMinimalFanoutResult",
    "ContextMinimalFanoutSettings",
    "EnvironmentContext",
    "ImplementationOutput",
    "PromptSplitPlan",
    "SplitPrompt",
]
