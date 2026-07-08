"""Context Protocol Header

Description:
    Defines grouped enum keys for distributable Vidbyte SDK skill assets.
Purpose:
    Gives callers a typed, autocomplete-friendly key space for skills loaded by
    vidbyte.skills.catalog.Skills while keeping each paradigm's skills isolated
    in its own enum.
Architecture and Key Functions:
    - ContextMinimalFanoutSkill: str Enum for the context minimal fanout skills.
    - Skills: dictionary mapping paradigm keys to their skill enum classes.
    - iter_skill_values: iterates every registered skill enum member.
    - skill_from_value: resolves manifest strings into their grouped enum member.
Relation to the codebase as a whole:
    Mirrors vidbyte.lib.enums.prompts.Prompt for multi-file skill assets, but
    groups skills by paradigm instead of flattening every skill into one enum.
"""

from __future__ import annotations

from enum import Enum
from typing import Final, TypeAlias


class ContextMinimalFanoutSkill(str, Enum):
    """Skill keys for context-minimal fanout assets."""

    DECOMPOSE_THEN_IMPLEMENT = "context_minimal_fanout.decompose_then_implement"
    DECOMPOSE_DESIGN_THEN_IMPLEMENT = "context_minimal_fanout.decompose_design_then_implement"
    DECOMPOSE_DESIGN_FANOUT = "context_minimal_fanout.decompose_design_fanout"
    DECOMPOSE_FANOUT = "context_minimal_fanout.decompose_fanout"


Skill: TypeAlias = ContextMinimalFanoutSkill

Skills: Final[dict[str, type[Skill]]] = {
    "context_minimal_fanout": ContextMinimalFanoutSkill,
}


def iter_skill_values() -> tuple[Skill, ...]:
    """Return every registered skill enum member across paradigms."""
    return tuple(skill for skill_enum in Skills.values() for skill in skill_enum)


def skill_from_value(value: str) -> Skill:
    """Resolve a manifest skill key into the matching grouped enum member."""
    for skill_enum in Skills.values():
        try:
            return skill_enum(value)
        except ValueError:
            continue
    raise ValueError(value)


__all__ = [
    "ContextMinimalFanoutSkill",
    "Skill",
    "Skills",
    "iter_skill_values",
    "skill_from_value",
]
