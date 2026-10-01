"""FILE: vidbyte/providers/skills/base.py

PURPOSE: Defines the narrow adapter boundary and safe per-source resolution failure.
ROLE IN CODEBASE: SkillSourceResolver dispatches explicit caller descriptors to a closed set of providers.
ARCHITECTURE NOTE: Adapters return resolved SkillDocument values and never execute companion files.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from vidbyte.lib.dataclasses.skills import SkillDocument, SkillSource
from vidbyte.lib.errors import VidbyteSdkError


class SkillSourceError(VidbyteSdkError):
    """A safe source lookup failure that Jev can record for one candidate."""


class SkillSourceAdapter(ABC):
    """Resolves one explicit source into a validated skill document."""

    @abstractmethod
    async def resolve(self, source: SkillSource) -> SkillDocument:
        # Resolves one source without exposing provider-specific retrieval to Jev.
        raise NotImplementedError


__all__ = ["SkillSourceAdapter", "SkillSourceError"]
