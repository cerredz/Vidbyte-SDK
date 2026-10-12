"""FILE: vidbyte/agents/skills/anthropic.py

PURPOSE: Defines AnthropicSkillResolver, which loads an AnthropicSkill entry from Anthropic's Skills API by setting the vendor-specific parts of VendorSkillResolver: the provider, the source type, and the request headers.
ROLE IN CODEBASE: Registered for SkillSourceType.ANTHROPIC in SkillLoader (loader.py). Everything else (key choice, download, latest fallback, status map, archive reading) lives in vendor.py.
ARCHITECTURE NOTE: The key travels only in x-api-key to Anthropic's fixed default endpoint, with the API version and the skills beta header that yield the response shapes the resolver reads.
FUNCTION INVENTORY: AnthropicSkillResolver._headers(key) -> dict[str, str].
COMMON MODIFICATION PATTERNS: A new required Anthropic header or a retired beta changes _headers and the ANTHROPIC_SKILLS_* constants together.
WHAT NOT TO DO IN THIS FILE: Do not add an authorization header or a configurable base URL; the key must reach only Anthropic.
KNOWN EDGE CASES: The Skills API is generally available and still honors the beta header with the beta response shapes (spec A-1, pending real-key QA).
RELATED DOCS: vidbyte/agents/skills/README.md; docs/spec/jev-skill-sources/spec.md (D-19)
TESTS: tests/features/jev_skills_preload/test_skill_sources_vendor.py
"""

from __future__ import annotations

from typing import ClassVar

from vidbyte.agents.skills.vendor import VendorSkillResolver
from vidbyte.lib.constants.skills import (
    ANTHROPIC_SKILLS_API_VERSION,
    ANTHROPIC_SKILLS_BETA,
)
from vidbyte.lib.dataclasses.skills import AnthropicSkill
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.enums.skills import SkillSourceType


class AnthropicSkillResolver(VendorSkillResolver[AnthropicSkill]):
    """Loads Anthropic Skills API skills with x-api-key and the skills beta header."""

    PROVIDER: ClassVar[ModelProvider] = ModelProvider.ANTHROPIC
    SOURCE_TYPE: ClassVar[SkillSourceType] = SkillSourceType.ANTHROPIC

    def _headers(self, key: str) -> dict[str, str]:
        # Anthropic reads the key from x-api-key, never from authorization.
        return {"x-api-key": key, "anthropic-version": ANTHROPIC_SKILLS_API_VERSION, "anthropic-beta": ANTHROPIC_SKILLS_BETA}


__all__ = ["AnthropicSkillResolver"]
