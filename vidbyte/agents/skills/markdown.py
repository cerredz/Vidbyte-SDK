"""FILE: vidbyte/agents/skills/markdown.py

PURPOSE: Defines SkillMarkdown, the one parser every skill source uses to turn the raw bytes of a SKILL.md into a SkillDocument: strict UTF-8, YAML frontmatter between two `---` lines read with the safe loader, a non-blank name and description, and the exact body after the closing line.
ROLE IN CODEBASE: Called by the local, skills_sh, github, and vendor resolvers in this package after they have the file's bytes; returns a SkillResolution so a malformed file is data (INVALID_SKILL), never an exception.
ARCHITECTURE NOTE: A static helper class with one narrated main (parse) and leaf helpers. It does not reuse the packaged skill catalog's line parser (vidbyte/skills/catalog.py), which rejects folded YAML, requires the name to equal the folder, and returns no body.
FUNCTION INVENTORY: SkillMarkdown.parse(raw, *, name, source) -> SkillResolution; SkillMarkdown._decode(raw) -> str | None; SkillMarkdown._split(text) -> tuple[str, str] | str; SkillMarkdown._load(frontmatter) -> dict[object, object] | str; SkillMarkdown._invalid(detail) -> SkillResolution.
COMMON MODIFICATION PATTERNS: A new required frontmatter field adds one check in parse with its own SDK-written detail. Keep every detail free of file text.
WHAT NOT TO DO IN THIS FILE: 1. Do not use yaml.load or any loader but safe_load (S049). 2. Do not trim, re-join, or normalize the body; agents follow it exactly. 3. Do not copy a YAML error message into a detail: PyYAML quotes the offending line. 4. Do not decode with errors="replace"; replacement characters would silently change instructions.
KNOWN EDGE CASES: One byte-order mark is removed; a second one makes the first line fail the `---` check. The frontmatter `name` must be non-blank text but is not compared with the entry name, because npx skills sanitizes folder names; the document takes the entry's name. A folded description may keep its final line break. PyYAML raises ValueError for impossible dates and RecursionError for deep nesting, so the single safe_load call also catches those. Line splitting uses str.splitlines, so the body offset is exact for every line ending.
RELATED DOCS: vidbyte/agents/skills/README.md; docs/spec/jev-skill-sources/spec.md (sections 6.3 and 9.2)
TESTS: tests/features/jev_skills_preload/test_skill_sources_markdown.py
"""

from __future__ import annotations

import yaml

from vidbyte.lib.constants.skills import SKILL_MARKDOWN_DELIMITER
from vidbyte.lib.dataclasses.skills import SkillDocument, SkillResolution
from vidbyte.lib.enums.skills import SkillUnavailableReason


class SkillMarkdown:
    """Parses one SKILL.md into a document, or into INVALID_SKILL with an SDK-written detail."""

    @staticmethod
    def parse(raw: bytes, *, name: str, source: str) -> SkillResolution:
        # Read the file as strict UTF-8, so a damaged byte never becomes a
        # silently different instruction.
        text = SkillMarkdown._decode(raw)
        if text is None:
            return SkillMarkdown._invalid("SKILL.md is not valid UTF-8 text.")
        # Split the frontmatter from the body at the opening and closing
        # `---` lines.
        parts = SkillMarkdown._split(text)
        if isinstance(parts, str):
            return SkillMarkdown._invalid(parts)
        frontmatter, body = parts
        # Read the frontmatter with the safe YAML loader only.
        fields = SkillMarkdown._load(frontmatter)
        if isinstance(fields, str):
            return SkillMarkdown._invalid(fields)
        # The frontmatter must say what the skill is called and what it is
        # for; Jev decides relevance from the description.
        title, description = fields.get("name"), fields.get("description")
        if not isinstance(title, str) or not title.strip():
            return SkillMarkdown._invalid("SKILL.md frontmatter needs a non-blank text name field.")
        if not isinstance(description, str) or not description.strip():
            return SkillMarkdown._invalid("SKILL.md frontmatter needs a non-blank text description field.")
        # The body is the exact text after the closing line, and it must
        # hold some guidance.
        if not body.strip():
            return SkillMarkdown._invalid("SKILL.md has no body after its frontmatter.")
        return SkillResolution(document=SkillDocument(name=name, description=description, text=body, source=source))

    @staticmethod
    def _decode(raw: bytes) -> str | None:
        # Strict UTF-8 with one optional byte-order mark removed.
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return None

    @staticmethod
    def _split(text: str) -> tuple[str, str] | str:
        # Returns (frontmatter, body), or the detail that explains why the
        # delimiter lines are wrong. Trailing spaces on a delimiter line are
        # allowed; anything before `---` is not.
        lines = text.splitlines(keepends=True)
        if not lines or lines[0].rstrip() != SKILL_MARKDOWN_DELIMITER:
            return "SKILL.md must start with a '---' line that opens its frontmatter."
        for index in range(1, len(lines)):
            if lines[index].rstrip() == SKILL_MARKDOWN_DELIMITER:
                return "".join(lines[1:index]), "".join(lines[index + 1 :])
        return "SKILL.md opens its frontmatter with '---' but never closes it with a second '---' line."

    @staticmethod
    def _load(frontmatter: str) -> dict[object, object] | str:
        # @intent skill-markdown-safe-yaml
        # Hostile YAML must end as data: the safe loader builds no objects,
        # and the three caught classes cover bad syntax, impossible dates,
        # and deep nesting. The detail never quotes the YAML error.
        try:
            fields = yaml.safe_load(frontmatter)
        except (yaml.YAMLError, ValueError, RecursionError):
            return "SKILL.md frontmatter is not valid YAML."
        if not isinstance(fields, dict):
            return "SKILL.md frontmatter must be a YAML mapping with name and description fields."
        return fields

    @staticmethod
    def _invalid(detail: str) -> SkillResolution:
        # Every parse failure is the same permanent reason.
        return SkillResolution(reason=SkillUnavailableReason.INVALID_SKILL, detail=detail)


__all__ = ["SkillMarkdown"]
