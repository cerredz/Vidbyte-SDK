"""FILE: vidbyte/providers/skills/file.py

PURPOSE: Resolves one explicit local SKILL.md file or directory under a fixed byte limit.
ROLE IN CODEBASE: The FILE source adapter supplies the first concrete adapter to JevSkillsPreload.
ARCHITECTURE NOTE: Only YAML frontmatter and the SKILL.md body are read; sibling assets are never opened.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

import yaml

from vidbyte.lib.dataclasses.skills import SkillDocument, SkillSource
from vidbyte.lib.enums.skills import SkillSourceKind
from vidbyte.lib.errors import ConfigurationError
from vidbyte.providers.skills.base import SkillSourceAdapter, SkillSourceError

_MAX_SKILL_FILE_BYTES = 256_000
_FRONTMATTER_MARKER = b"---"


class FileSkillSourceAdapter(SkillSourceAdapter):
    """Loads a single bounded SKILL.md document from an explicit local path."""

    async def resolve(self, source: SkillSource) -> SkillDocument:
        # Reads the bounded local document off the event loop and propagates cancellation.
        return await asyncio.to_thread(self._read_document, source)

    def _read_document(self, source: SkillSource) -> SkillDocument:
        # Validates the explicit path, parses metadata, and preserves the complete decoded file as text.
        path = self._skill_path(source)
        try:
            with path.open("rb") as source_file:
                content = source_file.read(_MAX_SKILL_FILE_BYTES + 1)
        except OSError as exc:
            raise SkillSourceError("Skill source could not be resolved.") from exc
        if len(content) > _MAX_SKILL_FILE_BYTES:
            raise SkillSourceError("Skill source exceeds the configured file size limit.")
        return self._document_from_content(source, content, path)

    def _skill_path(self, source: SkillSource) -> Path:
        # Accept only a SKILL.md path or a directory that contains that named file.
        if not isinstance(source, SkillSource) or source.kind is not SkillSourceKind.FILE:
            raise SkillSourceError("FILE adapter requires a FILE SkillSource.")
        try:
            path = Path(source.location).expanduser().resolve(strict=True)
            if path.is_dir():
                path = (path / "SKILL.md").resolve(strict=True)
        except (OSError, RuntimeError, TypeError) as exc:
            raise SkillSourceError("Skill source could not be resolved.") from exc
        if not path.is_file() or path.name != "SKILL.md":
            raise SkillSourceError("FILE sources must identify a SKILL.md file or its directory.")
        return path

    def _document_from_content(self, source: SkillSource, content: bytes, path: Path) -> SkillDocument:
        # Parses required frontmatter fields separately while retaining the complete file unchanged.
        try:
            lines = content.splitlines(keepends=True)
            if not lines or self._without_line_ending(lines[0]) != _FRONTMATTER_MARKER:
                raise SkillSourceError("SKILL.md must begin with YAML frontmatter.")
            closing_index = next(
                (index for index, line in enumerate(lines[1:], start=1) if self._without_line_ending(line).strip() == _FRONTMATTER_MARKER),
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
            return SkillDocument(name=name, description=description, text=full_text, source=str(path))
        except ConfigurationError as exc:
            raise SkillSourceError("SKILL.md does not contain a usable text body.") from exc

    def _without_line_ending(self, line: bytes) -> bytes:
        # Removes only the physical line ending so frontmatter delimiters remain exact.
        return line[:-2] if line.endswith(b"\r\n") else line[:-1] if line.endswith((b"\r", b"\n")) else line


__all__ = ["FileSkillSourceAdapter"]
