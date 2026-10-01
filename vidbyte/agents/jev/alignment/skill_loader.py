"""FILE: vidbyte/agents/jev/alignment/skill_loader.py

PURPOSE: Materializes the full text of one already-selected Jev skill candidate from inline text or an explicit local UTF-8 file. This core loader must not discover candidates, contact remote providers, unpack archives, or decide relevance.
ROLE IN CODEBASE: JevSkillsPreload calls this loader only after Jev selects a candidate; settings validation owns candidate shape, while future provider adapters must convert their result into the same source-neutral JevSkillCandidate contract.
ARCHITECTURE NOTE: Candidate metadata is sent to Jev before full instructions are loaded. Delaying file reads until after selection keeps unrelated skill bodies out of both the main agent context and the selection request.
FUNCTION INVENTORY: JevSkillContentLoader.load(candidate: JevSkillCandidate) -> str returns non-empty inline or local file text; unreadable or invalid files raise ConfigurationError. Covered by tests/test_jev_skill_preload.py.
COMMON MODIFICATION PATTERNS: Add new source formats in a separate provider adapter; keep this loader limited to inline content and local files, and have adapters produce a JevSkillCandidate for core selection.
WHAT NOT TO DO IN THIS FILE: (1) Do not make HTTP calls or parse Claude/GitHub/skills.sh URLs; those belong to separate adapter packages. (2) Do not add candidate-selection or Jev question logic; that belongs to skills.py.
KNOWN EDGE CASES: A selected local path may disappear or become unreadable after settings validation; a failure raises a file-specific ConfigurationError and the preloader records only the candidate name, never the path or partial text.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/jev-skill-preloading.md
TESTS: tests/test_jev_skill_preload.py
"""

from pathlib import Path

from vidbyte.agents.jev.settings import JevSkillCandidate
from vidbyte.lib.errors import ConfigurationError


class JevSkillContentLoader:
    """Read source-neutral skill content after Jev has selected its candidate."""

    def load(self, candidate: JevSkillCandidate) -> str:
        """Return candidate instructions, refusing empty or unreadable local files."""
        if candidate.content is not None:
            return candidate.content
        path = Path(candidate.path or "").expanduser()
        try:
            if not path.is_file():
                raise ConfigurationError(f"Selected Jev skill {candidate.name!r} must point to a regular file.")
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ConfigurationError(f"Could not read selected Jev skill {candidate.name!r} as UTF-8 text.") from exc
        if not content.strip():
            raise ConfigurationError(f"Selected Jev skill {candidate.name!r} contains no instructions.")
        return content


__all__ = ["JevSkillContentLoader"]
