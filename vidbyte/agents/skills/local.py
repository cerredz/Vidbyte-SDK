"""FILE: vidbyte/agents/skills/local.py

PURPOSE: Defines LocalSkillResolver, which reads `<path>/SKILL.md` for a LocalSkill entry from this machine and parses it into a SkillDocument labelled `local:<folder name>`, and the capped file read that the skills.sh resolver reuses.
ROLE IN CODEBASE: Registered for SkillSourceType.LOCAL in SkillLoader (loader.py); SkillsShSkillResolver (skills_sh.py) calls LocalSkillResolver.read_capped for the installed SKILL.md and for skills-lock.json.
ARCHITECTURE NOTE: The read is synchronous and runs in a worker thread through asyncio.to_thread, so a slow disk never blocks the other sources (ASYNC230, S047). The read is capped with the os.fstat pattern from vidbyte/agents/coding_context/root_file.py, so the true size is known without reading past the cap.
FUNCTION INVENTORY: LocalSkillResolver.read_capped(path) -> tuple[bytes, int] | None (static, sync); LocalSkillResolver.resolve(entries) -> tuple[SkillResolution, ...].
COMMON MODIFICATION PATTERNS: Change the cap in vidbyte/lib/constants/skills.py. A new local failure maps to a reason in resolve with a detail that names the absolute path.
WHAT NOT TO DO IN THIS FILE: 1. Do not open the file inside an async function. 2. Do not put the machine path in the label; it reaches Jev and logs. 3. Do not catch anything wider than OSError around the read.
KNOWN EDGE CASES: A missing folder, a missing file, a SKILL.md that is a directory, a path that is a file, a dangling symlink, and a symlink loop all mean "no regular file" (NOT_FOUND, remembered). Any other OSError, such as PermissionError, is FETCH_FAILED and the file is read again on the next run. Symlinks are followed. The cap is inclusive.
RELATED DOCS: vidbyte/agents/skills/README.md; docs/spec/jev-skill-sources/spec.md (D-6, D-15, D-23)
TESTS: tests/features/jev_skills_preload/test_skill_sources_local.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from vidbyte.agents.skills.markdown import SkillMarkdown
from vidbyte.agents.skills.resolver import SkillResolver
from vidbyte.lib.constants.skills import (
    SKILL_MARKDOWN_FILE_NAME,
    SKILL_MARKDOWN_MAX_BYTES,
)
from vidbyte.lib.dataclasses.skills import LocalSkill, SkillResolution
from vidbyte.lib.enums.skills import SkillSourceType, SkillUnavailableReason


class LocalSkillResolver(SkillResolver[LocalSkill]):
    """Reads one local SKILL.md off the event loop and parses it."""

    @staticmethod
    def read_capped(path: Path) -> tuple[bytes, int] | None:
        # Returns at most the cap's bytes and the
        # file's true size, or None when no regular
        # file is at path; other OSErrors propagate.
        if not path.is_file():
            return None
        with path.open("rb") as handle:
            total_bytes = os.fstat(handle.fileno()).st_size
            return handle.read(SKILL_MARKDOWN_MAX_BYTES), total_bytes

    async def resolve(self, entries: tuple[LocalSkill, ...]) -> tuple[SkillResolution, ...]:
        # @intent local-skill-read
        # A missing file is the developer's to fix, so it is remembered;
        # a read error such as a permission problem is FETCH_FAILED, so
        # a fix takes effect on the next run without a restart.
        (entry,) = entries
        folder = Path(entry.path)
        skill_file = folder / SKILL_MARKDOWN_FILE_NAME
        # Read SKILL.md in a worker thread so a
        # slow disk never blocks the other sources.
        try:
            read = await asyncio.to_thread(LocalSkillResolver.read_capped, skill_file)
        except OSError as error:
            return (SkillResolution(reason=SkillUnavailableReason.FETCH_FAILED, detail=f"Could not read {skill_file} ({type(error).__name__}); it is read again on the next run."),)
        if read is None:
            return (SkillResolution(reason=SkillUnavailableReason.NOT_FOUND, detail=f"No {SKILL_MARKDOWN_FILE_NAME} file at {skill_file}; point path= at the folder that holds it. This agent remembers the miss, so create a new agent after fixing it."),)
        # Refuse a file over the cap instead of sending part of it.
        raw, total_bytes = read
        if total_bytes > SKILL_MARKDOWN_MAX_BYTES:
            return (SkillResolution(reason=SkillUnavailableReason.TOO_LARGE, detail=f"{skill_file} is {total_bytes} bytes, over the {SKILL_MARKDOWN_MAX_BYTES}-byte SKILL_MARKDOWN_MAX_BYTES cap."),)
        # Parse it under a label that names only the folder, never the
        # machine path.
        return (SkillMarkdown.parse(raw, name=entry.name, source=f"{SkillSourceType.LOCAL.value}:{folder.name}"),)


__all__ = ["LocalSkillResolver"]
