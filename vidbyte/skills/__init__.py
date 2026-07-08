"""Context Protocol Header

Description:
    Top-level initializer for the Vidbyte SDK skills package.
Purpose:
    Exposes the typed skill enums and Skills catalog for packaged skill assets.
Architecture & Functions:
    - Re-exports ContextMinimalFanoutSkill, Skill, SkillRecord, and Skills
      without dynamic text exports.
Codebase Relation:
    Sibling public import surface to vidbyte.prompts for multi-file skills.
"""

from __future__ import annotations

from vidbyte.lib.enums.skills import ContextMinimalFanoutSkill, Skill
from vidbyte.skills.catalog import SkillRecord, Skills

__all__ = [
    "Skill",
    "ContextMinimalFanoutSkill",
    "SkillRecord",
    "Skills",
]
