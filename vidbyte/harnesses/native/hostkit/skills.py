"""FILE: vidbyte/harnesses/native/hostkit/skills.py

PURPOSE: Defines NativeSkillFolders, which makes one SDK-owned skills folder hold exactly the caller's skill folders, copying them only when the folder does not already hold identical copies.
ROLE IN CODEBASE: Called through asyncio.to_thread by GrokThreadRun (grok/threads.py) for the skills folder of the private Grok home, and by MuseThreadRun (muse/threads.py) for the skills folder of the per-call Muse config home. opencode reads the caller's folders in place and does not use it.
ARCHITECTURE NOTE: Synchronous file work, so callers move it off the event loop (lint S052). Comparing before copying matters for Grok, whose private home is shared by every call in one workspace: an unchanged skill set is never removed and copied again, so a concurrent call with the same skills never sees the folder half-built.
FUNCTION INVENTORY: replace is the narrated main function; remove deletes an SDK-owned folder of skill copies even when they kept read-only bits; _matches says whether the destination already holds exactly the requested folders with identical files.
COMMON MODIFICATION PATTERNS: A harness that needs its skills copied passes its own destination; the copy rules stay here.
WHAT NOT TO DO IN THIS FILE: 1. Do not write into a caller's skill folder; it is only read. 2. Do not follow symbolic links when copying; a link is copied as a link. 3. Do not leave a skill in the destination that the caller did not pass.
KNOWN EDGE CASES: An empty request matches a missing or empty destination and creates nothing. A copy keeps the read-only bits of the caller's files, so remove clears them on the copy (never on the caller's folder) before deleting it. Two calls in one workspace with different skill sets can still collide while one rebuilds the folder (spec EC-27); the README states the limit.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_skills.py
"""

from __future__ import annotations

import filecmp
import os
import shutil
import stat
from pathlib import Path


class NativeSkillFolders:
    """Keeps one skills folder holding exactly the caller's skill folders."""

    @staticmethod
    def replace(skills: tuple[Path, ...], destination: Path) -> None:
        # @intent skills-folder-holds-exactly-the-callers-skills
        # The harness reads every folder in the destination as a skill,
        # so it must hold the caller's skills and nothing else; a
        # destination that already holds identical copies is left
        # untouched so concurrent calls with the same skills never see
        # it half-built.
        if NativeSkillFolders._matches(skills, destination):
            return

        # Start from an empty folder, then copy each skill folder under
        # its own name, keeping links as links.
        if destination.exists():
            NativeSkillFolders.remove(destination)
        destination.mkdir(parents=True)
        for skill in skills:
            shutil.copytree(skill, destination / skill.name, symlinks=True)

    @staticmethod
    def remove(folder: Path) -> None:
        # @intent skill-copies-stay-removable
        # copytree keeps the read-only bits of the caller's files and
        # folders, and a read-only file (Windows) or folder (POSIX)
        # blocks its own removal, so every copied entry gets its
        # owner's write bit (and a folder its search bit) back first.
        # Links are left alone, so no link target is ever changed.
        for root, folders, files in os.walk(folder):
            for entry in (Path(root, name) for name in (*folders, *files)):
                if not entry.is_symlink():
                    extra = stat.S_IWRITE | (stat.S_IEXEC if entry.is_dir() else 0)
                    os.chmod(entry, stat.S_IMODE(entry.lstat().st_mode) | extra)
        shutil.rmtree(folder)

    @staticmethod
    def _matches(skills: tuple[Path, ...], destination: Path) -> bool:
        # Whether destination holds exactly the requested folder names,
        # each with the same files by relative path and by bytes.
        if not destination.is_dir():
            return not skills and not destination.exists()
        if sorted(child.name for child in destination.iterdir()) != sorted(skill.name for skill in skills):
            return False
        for skill in skills:
            copy = destination / skill.name
            wanted = sorted(os.path.relpath(os.path.join(root, name), skill) for root, _folders, names in os.walk(skill) for name in names)
            present = sorted(os.path.relpath(os.path.join(root, name), copy) for root, _folders, names in os.walk(copy) for name in names)
            _same, different, unreadable = filecmp.cmpfiles(skill, copy, wanted, shallow=False)
            if wanted != present or different or unreadable:
                return False
        return True


__all__ = ["NativeSkillFolders"]
