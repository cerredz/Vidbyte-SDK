"""Context Protocol Header

Description:
    Exports the context-minimal fanout paradigm, its public data contracts, and
    package-local skill/prompt assets.
Purpose:
    Provides the concrete first Vidbyte paradigm: extract context, split into
    non-overlapping prompts, de-overlap adversarially, and implement in parallel.
    Also makes package-local skill files available through importlib.resources.
Architecture:
    - ContextMinimalFanoutParadigm: The four-stage harness.
    - ContextMinimalFanoutClient: Namespace factory.
    - Typed contracts: settings, environment context, split plan, results.
    - skills/: External harness skill assets loaded by vidbyte.skills.catalog.
    - prompts/: Stage system-prompt Markdown assets.
Relations:
    Re-exported by vidbyte.paradigms and the top-level vidbyte package.
    Skills are loaded by vidbyte.skills.catalog.Skills for registry access.
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
    EnvironmentSummary,
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
    "EnvironmentSummary",
    "ImplementationOutput",
    "PromptSplitPlan",
    "SplitPrompt",
]
