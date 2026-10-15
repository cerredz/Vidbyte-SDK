"""FILE: vidbyte/lib/enums/skills.py

PURPOSE: Defines the closed vocabularies for skills: the grouped catalog keys for the SDK's packaged skill assets, and the three enums of skill sources (which kind of entry a skill is, why a skill is unavailable, and which network step a source failed at).
ROLE IN CODEBASE: `vidbyte/skills/catalog.py` and `vidbyte/cli/skills.py` read the catalog keys; `vidbyte/lib/dataclasses/skills.py` fixes `SkillSourceType` on each skill entry, `vidbyte/agents/skills/` reports `SkillUnavailableReason` and names `SkillFetchStep` in details, and `vidbyte/lib/dataclasses/jev.py` carries the reason on `JevSkillResult`.
ARCHITECTURE NOTE: The vocabulary lives in `vidbyte.lib` because the record layer, the skill loader, and the JEV preload all read it, and lower layers may not import higher ones. The catalog keys group skills by paradigm instead of flattening every packaged skill into one enum. `SkillFetchStep` is internal: it is exported from `vidbyte.lib.enums` only, never from the `vidbyte` root.
FUNCTION INVENTORY: ContextMinimalFanoutSkill; Skill (alias); Skills (paradigm map); iter_skill_values; skill_from_value; SkillSourceType; SkillUnavailableReason; SkillFetchStep.
COMMON MODIFICATION PATTERNS: A new packaged-skill paradigm adds its enum and one `Skills` entry. A new skill source adds its `SkillSourceType` member together with its entry class, its resolver module, and the loader's resolver map. A new unavailable reason is a public contract change: decide whether it is transient (`SKILL_TRANSIENT_REASONS`) and document it.
WHAT NOT TO DO IN THIS FILE: Do not rename an existing value: saved settings carry `SkillSourceType.value`, and results print `SkillUnavailableReason.value`. Do not export `SkillFetchStep` beyond `vidbyte.lib.enums`.
KNOWN EDGE CASES: Catalog keys are manifest strings and must stay unique across paradigms, or `skill_from_value` returns the first match. `DECISION_FAILED` and the batching `TOO_LARGE` are set only by the Jev preload; the loader produces the other six reasons (and `TOO_LARGE` for oversized files).
RELATED DOCS: vidbyte/skills/README.md, vidbyte/agents/skills/README.md, docs/spec/jev-skill-sources/spec.md.
TESTS: tests/test_skills_interface.py; tests/features/jev_skills_preload/test_skill_sources_contract.py.
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


class SkillSourceType(str, Enum):
    """Where a configured skill entry's SKILL.md comes from; each entry class fixes one member."""

    INLINE = "inline"
    LOCAL = "local"
    SKILLS_SH = "skills_sh"
    GITHUB = "github"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class SkillUnavailableReason(str, Enum):
    """Why a configured skill was not offered to the agent; results print the value."""

    NOT_INSTALLED = "not_installed"
    NOT_FOUND = "not_found"
    AUTH_FAILED = "auth_failed"
    RATE_LIMITED = "rate_limited"
    FETCH_FAILED = "fetch_failed"
    INVALID_SKILL = "invalid_skill"
    TOO_LARGE = "too_large"
    DECISION_FAILED = "decision_failed"


class SkillFetchStep(str, Enum):
    """Which network step a skill source was on when it failed; named in details, never a root export."""

    GITHUB_COMMIT = "github_commit"
    GITHUB_TREE = "github_tree"
    GITHUB_FILE = "github_file"
    VENDOR_CONTENT = "vendor_content"
    VENDOR_METADATA = "vendor_metadata"


__all__ = [
    "ContextMinimalFanoutSkill",
    "Skill",
    "SkillFetchStep",
    "SkillSourceType",
    "SkillUnavailableReason",
    "Skills",
    "iter_skill_values",
    "skill_from_value",
]
