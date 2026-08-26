"""Context Protocol Header

Description:
    Enumerations for the batch-2 deep CoT monitoring tools.
Purpose:
    Gives the prediction, goal_check, counterfactual, assumptions, failures,
    and why tools (vidbyte.tools.builtins.cot_events) a single typed source
    of truth for every categorical field they validate, instead of ad hoc
    string tuples declared inline in that module. Each enum's original value
    set is preserved; members without that marker were derived afterward to
    round out the category so the field distinguishes more than the minimum
    the tool shipped with.
Architecture:
    - YesNo: shared binary decision enum reused across strictly two-state
      fields (a third or fourth state would blur, not sharpen, the signal).
    - One enum per categorical field.
Relations:
    Consumed by vidbyte.tools.builtins.cot_events, which derives its
    CotEventParser.parse_enum allowed tuples from these members via
    `tuple(member.value for member in Enum)`. Batch-1 fields in that same
    module (HYPOTHESIS_STATUSES, BASIS_TYPES, REVERSIBILITY_LEVELS,
    ASSUMPTION_ACTIONS, IMPACT_LEVELS, PROGRESS_STATES, RETURNABLE_OPTIONS)
    are out of scope here and tracked by the separate PR #337 comment
    resolution.
Similar Files:
    - vidbyte/lib/enums/context.py
"""

from __future__ import annotations

from enum import Enum


class YesNo(str, Enum):
    """Shared binary decision enum for strictly two-state monitoring fields."""

    YES = "yes"
    NO = "no"


class GoalServiceLevel(str, Enum):
    """How much current activity still serves the originally stated goal."""

    DIRECTLY = "directly"
    INDIRECTLY = "indirectly"
    TANGENTIALLY = "tangentially"
    UNCLEAR = "unclear"
    NO = "no"


class ReconsiderLevel(str, Enum):
    """How much a rationale retrospective concluded should change."""

    NONE = "none"
    MINOR = "minor"
    SOME = "some"
    CORE = "core"
    TOTAL = "total"


class FailureLikelihood(str, Enum):
    """How likely one named premortem failure is to actually occur."""

    NEGLIGIBLE = "negligible"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    NEAR_CERTAIN = "near_certain"


class Severity(str, Enum):
    """Blast radius or consequence tier for a prediction turning out wrong."""

    COSMETIC = "cosmetic"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"
    FATAL = "fatal"


class PredictionCategory(str, Enum):
    """What kind of outcome a forward-looking prediction is actually about."""

    TOOL_RESULT = "tool_result"
    TEST_RESULT = "test_result"
    USER_RESPONSE = "user_response"
    SYSTEM_BEHAVIOR = "system_behavior"
    OTHER = "other"


class AssumptionRiskLevel(str, Enum):
    """Overall risk carried by the current full set of active assumptions."""

    NEGLIGIBLE = "negligible"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FailureScanRisk(str, Enum):
    """Overall risk verdict for the current premortem failure scan."""

    HEALTHY = "healthy"
    WATCHFUL = "watchful"
    ELEVATED = "elevated"
    SEVERE = "severe"
    CRITICAL = "critical"


__all__ = [
    "AssumptionRiskLevel",
    "FailureLikelihood",
    "FailureScanRisk",
    "GoalServiceLevel",
    "PredictionCategory",
    "ReconsiderLevel",
    "Severity",
    "YesNo",
]
