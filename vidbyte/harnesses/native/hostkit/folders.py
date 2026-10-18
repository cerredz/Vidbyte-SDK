"""FILE: vidbyte/harnesses/native/hostkit/folders.py

PURPOSE: Defines NativePrivateFolders, which locates and prepares the SDK-owned private folder of one workspace under the user's home: the private Grok home and the private Claude Code config folder, each holding a skills folder with exactly the caller's skills.
ROLE IN CODEBASE: Called through asyncio.to_thread by GrokThreadRun (grok/threads.py) for the private Grok home and by ClaudeThreadRun (claude/threads.py) for the private Claude Code config folder; the two differ only in the constants they pass. It uses NativeSkillFolders (hostkit/skills.py) for the skills folder and raises through the call's NativeErrorFactory (hostkit/errors.py).
ARCHITECTURE NOTE: Synchronous file work, so callers move it off the event loop (lint S052). A class-wide lock makes the calls of one process prepare one at a time, because calls fanned out over one workspace share its folder. Every harness-specific value is a parameter: the folder parts under the home, the key length, the skills folder name and the two detail templates, whose fields are {error_type} for the unknown home and {home}, {error_type} and {reason} for a folder that cannot be prepared. The module holds no literals of its own (spec INV-15).
FUNCTION INVENTORY: prepare is the one function: it derives the folder from a SHA-256 key of the resolved workspace and, holding the class lock, creates it open to its owner only and makes its skills folder hold exactly the request's skills; it maps a failure to launch_failed.
COMMON MODIFICATION PATTERNS: A harness that needs its own private folder per workspace passes its own parts, key length, skills folder name and detail templates; the folder rules stay here.
WHAT NOT TO DO IN THIS FILE: 1. Do not put the folder inside the workspace; a repository controls what the workspace holds. 2. Do not write a credential or a settings file into the folder; the SDK writes only the skills folder. 3. Do not import a harness subpackage; harness subpackages import hostkit, never the reverse. 4. Do not create or fill the folder outside the lock; a cold fan-out then rebuilds the skills folder under its own calls.
KNOWN EDGE CASES: The same workspace, spelled another way (a relative segment, another letter case on Windows), maps to the same folder, because the key hashes the resolved, normcased path. A workspace that contains the user's home holds the folder inside it (claude-thread-functions spec EC-31). Calls of one process prepare one at a time, so a cold fan-out with one skill set builds the skills folder once (PR #1044 review L11); calls with different skill sets, or from separate processes at the same moment, can still collide while it is rebuilt (claude-thread-functions spec EC-21); the launch_failed likely causes say so. The folder is created with NATIVE_PRIVATE_FOLDER_MODE and an existing one is set to it, because it holds transcripts (EC-28); on Windows that only clears the read-only bit. The folder is never removed by the SDK.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_claude_skills.py, tests/features/harness_threads/test_harness_threads_launcher.py, tests/features/harness_threads/test_harness_threads_claude_launcher.py
"""

from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path

from vidbyte.harnesses.native.hostkit.errors import NativeErrorFactory
from vidbyte.harnesses.native.hostkit.skills import NativeSkillFolders
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import NativeThreadRequest
from vidbyte.lib.enums.native_threads import NativeThreadProblem


class NativePrivateFolders:
    """Prepares the SDK-owned private folder of one workspace, holding exactly the caller's skills."""

    # Held while a folder is created and its skills folder filled, so the
    # calls of this process prepare one at a time.
    _lock = threading.Lock()

    @staticmethod
    def prepare(request: NativeThreadRequest, errors: NativeErrorFactory, *, parts: tuple[str, ...], key_hex_chars: int, skills_dir: str, unknown_detail: str, failure_detail: str) -> Path:
        # @intent native-private-folder-stays-outside-the-workspace
        # The vendor trusts everything in this folder as user scope, so
        # it lives under the user's home folder, never in the workspace
        # a repository controls; its key is a hash of the resolved
        # workspace so a continue finds the same folder.
        key = hashlib.sha256(os.path.normcase(str(request.workspace)).encode()).hexdigest()[:key_hex_chars]
        try:
            folder = Path.home().joinpath(*parts, key)
        except RuntimeError as exc:
            raise errors.failure(NativeThreadProblem.LAUNCH_FAILED, request=request, searched=unknown_detail.format(error_type=type(exc).__name__)) from exc
        # @intent native-private-folder-prepared-one-call-at-a-time
        # Calls fanned out over one workspace share this folder, so one
        # call at a time creates it and fills its skills folder, and the
        # next finds identical copies and leaves them. Only its owner may
        # open it, because it holds the vendor's transcripts.
        try:
            with NativePrivateFolders._lock:
                folder.mkdir(mode=native_threads.NATIVE_PRIVATE_FOLDER_MODE, parents=True, exist_ok=True)
                folder.chmod(native_threads.NATIVE_PRIVATE_FOLDER_MODE)
                NativeSkillFolders.replace(tuple(Path(skill) for skill in request.skills), folder / skills_dir)
        except OSError as exc:
            detail = failure_detail.format(home=folder, error_type=type(exc).__name__, reason=exc.strerror or type(exc).__name__)
            raise errors.failure(NativeThreadProblem.LAUNCH_FAILED, request=request, searched=detail) from exc
        return folder


__all__ = ["NativePrivateFolders"]
