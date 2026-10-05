"""FILE: vidbyte/skills/sources/file.py

PURPOSE: Resolves one explicit local SKILL.md file or directory under a fixed byte limit.
ROLE IN CODEBASE: The FILE source adapter supplies the first concrete adapter to JevSkillsPreload.
ARCHITECTURE NOTE: Only YAML frontmatter and the SKILL.md body are read; sibling assets are never opened.
COMMON MODIFICATION PATTERNS: Keep the byte bound, async file-read boundary, and parsed local provenance aligned.
KNOWN EDGE CASES: Missing, unreadable, over-limit, and malformed files fail safely without probing companion files.
RELATED DOCS: docs/design/jev-skill-providers.md and docs/jev-skill-providers.md.
TESTS: tests/test_jev_skill_providers.py and scripts/test-jev-skill-providers.py.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from vidbyte.lib.dataclasses.skills import SkillDocument, SkillSource
from vidbyte.lib.enums.skills import SkillSourceKind
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderRequestError,
    SkillSourceError,
)
from vidbyte.lib.errors.skills import provider_failure_reason
from vidbyte.skills.sources.base import (
    SkillDocumentParser,
    SkillSourceAdapter,
)

_MAX_SKILL_FILE_BYTES = 256_000
_FILE_READ_OVERFLOW_SENTINEL_BYTES = 1


class FileSkillSourceAdapter(SkillSourceAdapter):
    """Loads a single bounded SKILL.md document from an explicit local path."""

    def __init__(self, *, document_parser: SkillDocumentParser | None = None) -> None:
        # Shares the validated full-document parser with remote text adapters.
        self.document_parser = document_parser or SkillDocumentParser()

    async def resolve(self, source: SkillSource) -> SkillDocument:
        # Keeps all expected lookup, decoding, validation, and filesystem failures at one safe boundary.
        try:
            return await asyncio.to_thread(self._read_document, source)
        except SkillSourceError as exc:
            raise SkillSourceError(exc.reason, source_kind="file", status_code=exc.status_code) from exc
        except ProviderRequestError as exc:
            raise SkillSourceError(provider_failure_reason(exc.status_code, message=exc.message), source_kind="file", status_code=exc.status_code) from exc
        except TimeoutError as exc:
            raise SkillSourceError("the local file operation timed out", source_kind="file") from exc
        except OSError as exc:
            raise SkillSourceError("the file could not be opened or read", source_kind="file") from exc
        except UnicodeError as exc:
            raise SkillSourceError("the skill document is not valid UTF-8", source_kind="file") from exc
        except yaml.YAMLError as exc:
            raise SkillSourceError("the skill document frontmatter is not valid YAML", source_kind="file") from exc
        except (ConfigurationError, ValueError, TypeError) as exc:
            raise SkillSourceError("the local source or parsed skill did not satisfy the SDK contract", source_kind="file") from exc

    def _read_document(self, source: SkillSource) -> SkillDocument:
        # Validates the explicit path, parses metadata, and preserves the complete decoded file as text.
        path = self._skill_path(source)
        with path.open("rb") as source_file:
            content = source_file.read(_MAX_SKILL_FILE_BYTES + _FILE_READ_OVERFLOW_SENTINEL_BYTES)
        if len(content) > _MAX_SKILL_FILE_BYTES:
            raise SkillSourceError("Skill source exceeds the configured file size limit.")
        return self.document_parser.parse(content, source=source, provenance=str(path))

    def _skill_path(self, source: SkillSource) -> Path:
        # Accept only a SKILL.md path or a directory that contains that named file.
        if not isinstance(source, SkillSource) or source.kind is not SkillSourceKind.FILE:
            raise SkillSourceError("FILE adapter requires a FILE SkillSource.")
        path = Path(source.location).expanduser().resolve(strict=True)
        if path.is_dir():
            path = (path / "SKILL.md").resolve(strict=True)
        if not path.is_file() or path.name != "SKILL.md":
            raise SkillSourceError("FILE sources must identify a SKILL.md file or its directory.")
        return path

__all__ = ["FileSkillSourceAdapter"]
