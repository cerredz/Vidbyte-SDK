"""Context Protocol Header

Description:
    Defines stable enum keys for distributable Vidbyte SDK skill assets.
Purpose:
    Gives callers a typed, autocomplete-friendly key space for skills loaded by
    vidbyte.skills.catalog.Skills.
Architecture and Key Functions:
    - Skill: str Enum whose values map to packaged skill manifest identifiers.
Relation to the codebase as a whole:
    Mirrors vidbyte.lib.enums.prompts.Prompt for multi-file skill assets instead
    of plain prompt text.
"""

from __future__ import annotations

from enum import Enum


class Skill(str, Enum):
    """Skill keys for Vidbyte SDK skill assets."""

    CONTEXT_MINIMAL_FANOUT_DECOMPOSE_THEN_IMPLEMENT = "context_minimal_fanout.decompose_then_implement"
    CONTEXT_MINIMAL_FANOUT_DECOMPOSE_DESIGN_THEN_IMPLEMENT = "context_minimal_fanout.decompose_design_then_implement"
    CONTEXT_MINIMAL_FANOUT_DECOMPOSE_DESIGN_FANOUT = "context_minimal_fanout.decompose_design_fanout"
    CONTEXT_MINIMAL_FANOUT_DECOMPOSE_FANOUT = "context_minimal_fanout.decompose_fanout"


__all__ = [
    "Skill",
]
