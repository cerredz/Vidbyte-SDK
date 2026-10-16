"""FILE: vidbyte/harnesses/native/grok/store.py

PURPOSE: Defines GrokHome, the one owner of where a Grok child's GROK_HOME is (the SDK's private home for a workspace, or the user's own ~/.grok), how a run prepares the private home with the caller's skills, where the installer's grok lives, and the environment a grok child gets.
ROLE IN CODEBASE: Used by GrokThreadRun (grok/threads.py) for #1036's run, continue and fork, and by the Grok thread helpers and command functions (grok/helpers.py, grok/commands.py), so a helper reads exactly the home the runs write (spec INV-13).
ARCHITECTURE NOTE: The private home lives under ~/.vidbyte/grok-homes/, keyed by a hash of the resolved workspace (spec D-24 of #1036), never inside the workspace a repository controls. Only prepare creates anything; the helpers' read paths only compute the path (spec D-11). The methods are static and synchronous, so callers move file work off the event loop (lint S052). The module holds no literals of its own (spec INV-15): every value comes from vidbyte/lib/constants/native_threads.py or an enum.
FUNCTION INVENTORY: GrokHome.private names the private home of a workspace; user names ~/.grok; of picks one by scope; prepare creates the private home and its skills folder for a run; fallback names the installer's grok; environment builds a grok child's environment overlay, with the key variables only when a key is given.
COMMON MODIFICATION PATTERNS: A new variable every grok child needs goes in environment; a new scope is one GrokThreadScope member and one branch in of.
WHAT NOT TO DO IN THIS FILE: 1. Do not create a home on a read path; only prepare creates the private home, for a run. 2. Do not put the key anywhere but the two key variables of environment. 3. Do not read GROK_HOME from the caller's environment for the user scope; ~/.grok is literally the user's store (spec D-21).
KNOWN EDGE CASES: Path.home() raises RuntimeError when the user home cannot be determined: prepare reports it as launch_failed (#1036's text), fallback returns None, and private and user let it through so a helper can report store_unreadable. Concurrent runs in one workspace share one private home (#1036 EC-27).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_threads.py, tests/features/harness_threads/test_harness_threads_grok_helpers.py, tests/features/harness_threads/test_harness_threads_grok_commands.py
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

from vidbyte.harnesses.native.hostkit import NativeErrorFactory, NativeSkillFolders
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import NativeThreadRequest
from vidbyte.lib.enums.native_threads import (
    GrokThreadScope,
    NativeEnvironmentVariable,
    NativeThreadProblem,
)


class GrokHome:
    """Where a grok child's GROK_HOME is, how a run prepares it, and the environment a grok child gets."""

    @staticmethod
    def private(workspace: Path) -> Path:
        # @intent grok-home-stays-outside-the-workspace
        # Grok trusts everything under GROK_HOME as user scope, so the
        # home lives under the user's home folder, never in the
        # workspace a repository controls; its key is a hash of the
        # resolved workspace so a continue, and every helper, finds the
        # same home. Path.home() may raise RuntimeError.
        key = hashlib.sha256(os.path.normcase(str(workspace)).encode()).hexdigest()[: native_threads.GROK_HOME_KEY_HEX_CHARS]
        return Path.home().joinpath(*native_threads.GROK_PRIVATE_HOMES_PARTS, key)

    @staticmethod
    def user() -> Path:
        # The user's own store, literally ~/.grok (spec D-21).
        return Path.home().joinpath(*native_threads.GROK_USER_HOME_PARTS)

    @staticmethod
    def of(scope: GrokThreadScope, workspace: Path) -> Path:
        # @intent grok-sdk-scope-is-the-run-home
        # SDK scope is exactly the private home the runs of this
        # workspace use (spec INV-13); USER scope is ~/.grok.
        return GrokHome.user() if scope is GrokThreadScope.USER else GrokHome.private(workspace)

    @staticmethod
    def prepare(request: NativeThreadRequest, errors: NativeErrorFactory) -> Path:
        # A run creates the private home of its workspace and puts the
        # caller's skills in it; an unknown user home or a failed write
        # is launch_failed, as in #1036.
        try:
            home = GrokHome.private(Path(request.workspace))
        except RuntimeError as exc:
            raise errors.failure(NativeThreadProblem.LAUNCH_FAILED, request=request, searched=native_threads.GROK_HOME_UNKNOWN_DETAIL.format(error_type=type(exc).__name__)) from exc
        try:
            home.mkdir(parents=True, exist_ok=True)
            NativeSkillFolders.replace(tuple(Path(skill) for skill in request.skills), home / native_threads.GROK_SKILLS_DIR)
        except OSError as exc:
            detail = native_threads.GROK_HOME_FAILURE_DETAIL.format(home=home, error_type=type(exc).__name__, reason=exc.strerror or type(exc).__name__)
            raise errors.failure(NativeThreadProblem.LAUNCH_FAILED, request=request, searched=detail) from exc
        return home

    @staticmethod
    def fallback() -> Path | None:
        # The installer's ~/.grok/bin/grok[.exe]; skipped when the user
        # home cannot be determined.
        suffix = native_threads.NATIVE_WINDOWS_EXECUTABLE_SUFFIX if sys.platform == native_threads.NATIVE_WINDOWS_PLATFORM else ""
        try:
            return Path.home().joinpath(*native_threads.GROK_HOME_FOLDERS, native_threads.GROK_PROGRAM + suffix)
        except RuntimeError:
            return None

    @staticmethod
    def environment(home: Path, api_key: str | None) -> dict[str, str]:
        # @intent grok-key-wins-through-a-private-home
        # The private home holds no login, so the key passed here is the
        # only credential grok can use; both names carry it because the
        # precedence of the legacy alias is unknown. A helper child
        # passes no key and gets neither name. Self-update is off.
        keys = {} if api_key is None else {NativeEnvironmentVariable.XAI_API_KEY.value: api_key, NativeEnvironmentVariable.GROK_CODE_XAI_API_KEY.value: api_key}
        return {
            **keys,
            NativeEnvironmentVariable.GROK_HOME.value: str(home),
            NativeEnvironmentVariable.GROK_DISABLE_AUTOUPDATER.value: native_threads.NATIVE_ENABLED_SWITCH,
        }


__all__ = ["GrokHome"]
