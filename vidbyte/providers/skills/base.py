"""FILE: vidbyte/providers/skills/base.py

PURPOSE: Defines the narrow adapter boundary and safe per-source resolution failure.
ROLE IN CODEBASE: SkillSourceResolver dispatches explicit caller descriptors to a closed set of providers.
ARCHITECTURE NOTE: Adapters return resolved SkillDocument values and never execute companion files.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping

import yaml

from vidbyte.lib.dataclasses.skills import SkillDocument, SkillSource
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError

_FRONTMATTER_MARKER = b"---"


class SkillSourceError(VidbyteSdkError):
    """A safe source lookup failure that Jev can record for one candidate."""


class SkillDocumentParser:
    """Parses one bounded SKILL.md byte sequence without rewriting its text."""

    def parse(self, content: bytes, *, source: SkillSource, provenance: str) -> SkillDocument:
        # Validates YAML metadata and a nonblank body while preserving complete decoded text and provenance.
        if not isinstance(content, bytes):
            raise SkillSourceError("SKILL.md content must be UTF-8 bytes.")
        try:
            lines = content.splitlines(keepends=True)
            if not lines or self._without_line_ending(lines[0]) != _FRONTMATTER_MARKER:
                raise SkillSourceError("SKILL.md must begin with YAML frontmatter.")
            closing_index = next(
                (
                    index
                    for index, line in enumerate(lines[1:], start=1)
                    if self._without_line_ending(line).strip() == _FRONTMATTER_MARKER
                ),
                None,
            )
            if closing_index is None:
                raise SkillSourceError("SKILL.md frontmatter is missing its closing delimiter.")
            frontmatter = b"".join(lines[1:closing_index]).decode("utf-8")
            body = b"".join(lines[closing_index + 1 :]).decode("utf-8")
            full_text = content.decode("utf-8")
            metadata = yaml.safe_load(frontmatter)
        except (UnicodeDecodeError, yaml.YAMLError) as exc:
            raise SkillSourceError("SKILL.md frontmatter or body could not be parsed.") from exc
        if not isinstance(metadata, Mapping):
            raise SkillSourceError("SKILL.md frontmatter must contain a mapping.")
        name = metadata.get("name")
        description = metadata.get("description")
        if not isinstance(name, str) or not name.strip() or not isinstance(description, str) or not description.strip():
            raise SkillSourceError("SKILL.md frontmatter requires nonblank name and description fields.")
        if not body.strip():
            raise SkillSourceError("SKILL.md must include a nonblank body.")
        if source.skill_name is not None and source.skill_name != name:
            raise SkillSourceError("SKILL.md name does not match the requested skill name.")
        try:
            return SkillDocument(name=name, description=description, text=full_text, source=provenance)
        except ConfigurationError as exc:
            raise SkillSourceError("SKILL.md does not contain a usable text body.") from exc

    def _without_line_ending(self, line: bytes) -> bytes:
        # Removes only the physical line ending so frontmatter delimiters remain exact.
        return line[:-2] if line.endswith(b"\r\n") else line[:-1] if line.endswith((b"\r", b"\n")) else line


class SkillSourceAdapter(ABC):
    """Resolves one explicit source into a validated skill document."""

    @abstractmethod
    async def resolve(self, source: SkillSource) -> SkillDocument:
        # Resolves one source without exposing provider-specific retrieval to Jev.
        raise NotImplementedError


__all__ = ["SkillDocumentParser", "SkillSourceAdapter", "SkillSourceError"]
