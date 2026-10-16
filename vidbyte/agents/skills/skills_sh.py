"""FILE: vidbyte/agents/skills/skills_sh.py

PURPOSE: Defines SkillsShSkillResolver, which reads a skill installed by `npx skills add <source> --skill <name>` from `<directory>/<name>/SKILL.md`, checks the project's skills-lock.json when the install uses the default layout, and parses the file into a SkillDocument labelled `skills_sh:<source>/<name>[@<hash>]`.
ROLE IN CODEBASE: Registered for SkillSourceType.SKILLS_SH in SkillLoader (loader.py). It reuses LocalSkillResolver.read_capped (local.py) for both files and SkillMarkdown (markdown.py) for parsing.
ARCHITECTURE NOTE: The SDK never runs npx or any process; a missing install is NOT_INSTALLED with the command the developer runs. The lock check mirrors npx skills' own reading of skills-lock.json: a lock it cannot vouch with is treated as absent, and only a lock that names another source for this skill refuses it.
FUNCTION INVENTORY: SkillsShSkillResolver.resolve(entries) -> tuple[SkillResolution, ...]; SkillsShSkillResolver._lock_path(directory) -> Path | None; SkillsShSkillResolver._lock_record(read, name) -> dict[object, object] | None.
COMMON MODIFICATION PATTERNS: A change in the npx skills lock layout changes _lock_record and the SKILLS_SH_* constants together.
WHAT NOT TO DO IN THIS FILE: 1. Do not run npx, a subprocess, or a shell. 2. Do not treat a missing lock entry as a mismatch (spec Q-7 default). 3. Do not write a helper that takes an untyped value and returns a fallback after a mapping check (semgrep typed-mapping rule); JSON shapes are checked on locals.
KNOWN EDGE CASES: The lock is consulted only when directory is `<root>/.agents/skills`, at `<root>/skills-lock.json`. A lock that is missing, unreadable, over the SKILL.md cap, not JSON (merge markers), nested too deeply, whose version is missing, not a JSON number (true is not one), or below 1, or whose skills is not an object, is absent. A lock without an entry for the skill, or an entry without a text source, loads without the source check. A computedHash that is not text leaves the label without `@`.
RELATED DOCS: vidbyte/agents/skills/README.md; docs/spec/jev-skill-sources/spec.md (D-16, D-17, D-21)
TESTS: tests/features/jev_skills_preload/test_skill_sources_skills_sh.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from vidbyte.agents.skills.local import LocalSkillResolver
from vidbyte.agents.skills.markdown import SkillMarkdown
from vidbyte.agents.skills.resolver import SkillResolver
from vidbyte.lib.constants.skills import (
    SKILL_LABEL_HASH_CHARS,
    SKILL_MARKDOWN_FILE_NAME,
    SKILL_MARKDOWN_MAX_BYTES,
    SKILLS_SH_AGENTS_FOLDER,
    SKILLS_SH_LOCK_FILE_NAME,
    SKILLS_SH_LOCK_MIN_VERSION,
    SKILLS_SH_SKILLS_FOLDER,
)
from vidbyte.lib.dataclasses.skills import SkillResolution, SkillsShSkill
from vidbyte.lib.enums.skills import SkillSourceType, SkillUnavailableReason


class SkillsShSkillResolver(SkillResolver[SkillsShSkill]):
    """Reads one npx-skills install off the event loop, checks its lock entry, and parses it."""

    async def resolve(self, entries: tuple[SkillsShSkill, ...]) -> tuple[SkillResolution, ...]:
        # @intent skills-sh-installed-read
        # The SDK only reads what npx skills installed; it
        # never installs. A missing install is remembered
        # with the command that fixes it, and a lock
        # naming another source refuses a same-named fork.
        (entry,) = entries
        folder = Path(entry.directory) / entry.name
        skill_file = folder / SKILL_MARKDOWN_FILE_NAME
        # Read the installed SKILL.md in a worker thread.
        try:
            read = await asyncio.to_thread(LocalSkillResolver.read_capped, skill_file)
        except OSError as error:
            return (SkillResolution(reason=SkillUnavailableReason.FETCH_FAILED, detail=f"Could not read {skill_file} ({type(error).__name__}); it is read again on the next run."),)
        if read is None:
            return (SkillResolution(reason=SkillUnavailableReason.NOT_INSTALLED, detail=f"{entry.name} is not installed at {folder}: run `npx skills add {entry.source} --skill {entry.name}` in the project folder."),)
        raw, total_bytes = read
        if total_bytes > SKILL_MARKDOWN_MAX_BYTES:
            return (SkillResolution(reason=SkillUnavailableReason.TOO_LARGE, detail=f"{skill_file} is {total_bytes} bytes, over the {SKILL_MARKDOWN_MAX_BYTES}-byte SKILL_MARKDOWN_MAX_BYTES cap."),)
        # In the default layout, read the project's
        # lock entry for this skill; any problem with
        # the lock means there is nothing to check.
        lock_path = self._lock_path(Path(entry.directory))
        try:
            lock_read = await asyncio.to_thread(LocalSkillResolver.read_capped, lock_path) if lock_path is not None else None
        except OSError:
            lock_read = None
        record = self._lock_record(lock_read, entry.name) or {}
        # A lock that names another source means this folder holds a
        # different skill with the same name.
        locked_source = record.get("source")
        if isinstance(locked_source, str) and locked_source != entry.source:
            return (SkillResolution(reason=SkillUnavailableReason.INVALID_SKILL, detail=f"{SKILLS_SH_LOCK_FILE_NAME} says {entry.name} was installed from {locked_source}, but the entry expects {entry.source}; reinstall with `npx skills add {entry.source} --skill {entry.name}` or fix source=."),)
        # Label the document with the installed revision when the lock
        # records one, then parse.
        computed_hash = record.get("computedHash")
        revision = f"@{computed_hash[:SKILL_LABEL_HASH_CHARS]}" if isinstance(computed_hash, str) else ""
        return (SkillMarkdown.parse(raw, name=entry.name, source=f"{SkillSourceType.SKILLS_SH.value}:{entry.source}/{entry.name}{revision}"),)

    @staticmethod
    def _lock_path(directory: Path) -> Path | None:
        # npx skills keeps its lock at the project root only for the
        # default `<root>/.agents/skills` layout.
        if directory.name != SKILLS_SH_SKILLS_FOLDER or directory.parent.name != SKILLS_SH_AGENTS_FOLDER:
            return None
        return directory.parent.parent / SKILLS_SH_LOCK_FILE_NAME

    @staticmethod
    def _lock_record(read: tuple[bytes, int] | None, name: str) -> dict[object, object] | None:
        # @intent skills-sh-lock-absent-on-doubt
        # Mirrors npx skills: a lock it would not trust
        # (unreadable, over the cap, not JSON, nested
        # too deeply, a missing or non-number version
        # below 1, no skills object) counts as absent.
        if read is None:
            return None
        raw, total_bytes = read
        if total_bytes > SKILL_MARKDOWN_MAX_BYTES:
            return None
        try:
            lock = json.loads(raw)
        except (ValueError, RecursionError):
            return None
        if not isinstance(lock, dict):
            return None
        version, skills = lock.get("version"), lock.get("skills")
        if not isinstance(version, (int, float)) or type(version) is bool or version < SKILLS_SH_LOCK_MIN_VERSION or not isinstance(skills, dict):
            return None
        record = skills.get(name)
        return record if isinstance(record, dict) else None


__all__ = ["SkillsShSkillResolver"]
