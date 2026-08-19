"""Context Protocol Header

Description:
    Defines the FallbackPolicyMode enum composing multiple per-hop fallback
    policies into one trigger condition.
Purpose:
    Lets a developer choose whether the fallback chain advances proactively when
    ANY configured checkpoint policy fires (the default) or only when ALL of them
    fire, without writing policy-specific runtime logic.
Architecture:
    - FallbackPolicyMode: String-backed Enum containing ANY and ALL.
Relations:
    Imported by vidbyte.lib.enums and consumed by AgentFallbackSettings.
Similar Files:
    - vidbyte/lib/enums/agent_runtime.py: Standard string-backed enums.
"""

from __future__ import annotations
from enum import Enum


class FallbackPolicyMode(str, Enum):
    """String-backed enum class composing per-hop fallback policy votes."""

    ANY = "any"
    ALL = "all"