"""FILE: vidbyte/agents/skills/openai.py

PURPOSE: Defines OpenAISkillResolver, which loads an OpenAISkill entry from OpenAI's Skills API by setting the vendor-specific parts of VendorSkillResolver: the provider, the source type, and the bearer request headers.
ROLE IN CODEBASE: Registered for SkillSourceType.OPENAI in SkillLoader (loader.py). Everything else (key choice, download, latest fallback, status map, archive or bare SKILL.md reading) lives in vendor.py.
ARCHITECTURE NOTE: The headers come from the SDK's shared HttpResponseParser.bearer_headers (AGENTS.md principle 5), so the key travels only as a bearer token to OpenAI's fixed default endpoint.
FUNCTION INVENTORY: OpenAISkillResolver._headers(key) -> dict[str, str].
COMMON MODIFICATION PATTERNS: A new required OpenAI header is added to the headers this method returns, after the shared bearer headers.
WHAT NOT TO DO IN THIS FILE: Do not build the bearer header by hand or add an x-api-key header; do not add a configurable base URL.
KNOWN EDGE CASES: OpenAI's version content may be a zip or a bare SKILL.md; vendor.py reads both (spec A-4, pending real-key QA). The shared headers include content-type: application/json, which a GET ignores.
RELATED DOCS: vidbyte/agents/skills/README.md; docs/spec/jev-skill-sources/spec.md (D-19, D-20)
TESTS: tests/features/jev_skills_preload/test_skill_sources_vendor.py
"""

from __future__ import annotations

from typing import ClassVar

from vidbyte.agents.skills.vendor import VendorSkillResolver
from vidbyte.lib.dataclasses.skills import OpenAISkill
from vidbyte.lib.enums.model_provider import ModelProvider
from vidbyte.lib.enums.skills import SkillSourceType
from vidbyte.lib.http.parser import HttpResponseParser


class OpenAISkillResolver(VendorSkillResolver[OpenAISkill]):
    """Loads OpenAI Skills API skills with a bearer key."""

    PROVIDER: ClassVar[ModelProvider] = ModelProvider.OPENAI
    SOURCE_TYPE: ClassVar[SkillSourceType] = SkillSourceType.OPENAI

    def _headers(self, key: str) -> dict[str, str]:
        # OpenAI reads the key as a bearer token.
        return HttpResponseParser().bearer_headers(key)


__all__ = ["OpenAISkillResolver"]
