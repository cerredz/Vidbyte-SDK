"""Context Protocol Header

Description:
    Exports the context window template validation infrastructure.
Purpose:
    Provides a single import path for all template types used by test harnesses
    and algorithm validation scripts.
Architecture:
    - ContextWindowTemplate and TemplateViolation from base module.
    - ReflexionContextWindowTemplate from reflexion module.
    - ProsecutorDefenderJudgeContextWindowTemplate from its protocol module.
Relations:
    Consumed by tests and scripts. Imports RecorderBase from
    vidbyte.context.templates.
"""

from __future__ import annotations

from vidbyte.lib.templates.base import ContextWindowTemplate, TemplateViolation
from vidbyte.lib.templates.error_correction import ErrorCorrectionContextWindowTemplate
from vidbyte.lib.templates.independent_critic import (
    IndependentCriticContextWindowTemplate,
)
from vidbyte.lib.templates.problem_space_search import (
    ProblemSpaceSearchContextWindowTemplate,
)
from vidbyte.lib.templates.prosecutor_defender_judge import (
    ProsecutorDefenderJudgeContextWindowTemplate,
)
from vidbyte.lib.templates.reflexion import ReflexionContextWindowTemplate
from vidbyte.lib.templates.trajectory_checkpoints import (
    TrajectoryCheckpointContextWindowTemplate,
)

__all__ = [
    "ContextWindowTemplate",
    "ErrorCorrectionContextWindowTemplate",
    "IndependentCriticContextWindowTemplate",
    "ProblemSpaceSearchContextWindowTemplate",
    "ProsecutorDefenderJudgeContextWindowTemplate",
    "ReflexionContextWindowTemplate",
    "TemplateViolation",
    "TrajectoryCheckpointContextWindowTemplate",
]
