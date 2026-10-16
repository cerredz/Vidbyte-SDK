"""FILE: vidbyte/harnesses/native/grok/store.py

PURPOSE: Defines GrokHome, the one owner of where a Grok child's GROK_HOME is (the SDK's private home for a workspace, or the user's own ~/.grok), how a run prepares the private home with the caller's skills, where the installer's grok lives, and the environment a grok child gets; and GrokStore, which reads the session folders of one Grok home: every thread of a scope for a list or search, or one id's summary.json.
ROLE IN CODEBASE: GrokHome is used by GrokThreadRun (grok/threads.py) for #1036's run, continue and fork, and by the Grok thread helpers and command functions (grok/helpers.py, grok/commands.py), so a helper reads exactly the home the runs write (spec INV-13). GrokStore is called in asyncio.to_thread by GrokHelperRun (grok/helpers.py) and by GrokCommandRun (grok/commands.py) for the plan and explore agent evidence; it parses each summary.json through GrokHelperWire.thread_file (grok/wire.py).
ARCHITECTURE NOTE: The private home lives under ~/.vidbyte/grok-homes/, keyed by a hash of the resolved workspace (spec D-24 of #1036), never inside the workspace a repository controls. Only prepare creates anything; the helpers' read paths only compute the path (spec D-11). A Grok store is <home>/sessions/<group>/<id>/summary.json, a group being one url-encoded working folder; only directories are groups and session candidates, so the files Grok keeps beside them are ignored (spec EC-66). A list or search reads every summary.json in scope strictly (spec INV-6); an operation on one id reads only that id's file (spec D-27). Every file is opened in binary and read only up to its cap, with the size taken from the open handle (spec INV-16). The methods are static and synchronous, so callers move file work off the event loop (lint S052). The module holds no literals of its own (spec INV-15): every value comes from vidbyte/lib/constants/native_threads.py or an enum.
FUNCTION INVENTORY: GrokHome.private names the private home of a workspace; user names ~/.grok; of picks one by scope; prepare creates the private home and its skills folder for a run; fallback names the installer's grok; environment builds a grok child's environment overlay, with the key variables only when a key is given. GrokStore.home names the home of a helper's scope, or raises store_unreadable; threads (narrated) reads every thread in scope; thread (narrated) reads one id; _directories lists the folders inside a folder; _in_scope decides whether a group belongs to the scope; _read reads one capped summary.json; _check_layout applies the layout bound of a store whose folders hold no summary.json.
COMMON MODIFICATION PATTERNS: A new variable every grok child needs goes in environment; a new scope is one GrokThreadScope member, one branch in of and one in _in_scope. A new summary.json member is read in GrokHelperWire.thread_file, not here.
WHAT NOT TO DO IN THIS FILE: 1. Never create a home on a read path; only prepare creates the private home, for a run. 2. Do not put the key anywhere but the two key variables of environment. 3. Do not read GROK_HOME from the caller's environment for the user scope; ~/.grok is literally the user's store (spec D-21). 4. Do not skip a summary.json that is there but unreadable; only a folder without one is skipped (spec INV-6, EC-11). 5. Do not read a whole file before checking its size, and do not use builtin open() or read_bytes() (lint S061).
KNOWN EDGE CASES: Path.home() raises RuntimeError when the user home cannot be determined: prepare reports it as launch_failed (#1036's text), fallback returns None, and private and user let it through so GrokStore.home can report store_unreadable. Concurrent runs in one workspace share one private home (#1036 EC-27). A session folder without summary.json is a run still starting, or a folder grok removed during the scan, and is skipped (spec EC-11, EC-12), unless every folder in scope lacks one and the newest is older than GROK_SUMMARY_GRACE_SECONDS: then Grok changed its layout and the read raises (spec EC-67). The same id under two groups (two spellings of one path) is the newer copy (spec EC-17). On Windows a group matches the workspace whatever its letter case or slash direction (os.path.normcase; spec EC-19). A request of a run (NativeThreadRequest) has no scope and reads every group of its private home.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_threads.py, tests/features/harness_threads/test_harness_threads_grok_helpers.py, tests/features/harness_threads/test_harness_threads_grok_commands.py, tests/features/harness_threads/test_harness_threads_helper_credentials.py
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
import urllib.parse
from pathlib import Path

from vidbyte.harnesses.native.grok.wire import GrokHelperWire
from vidbyte.harnesses.native.hostkit import NativeErrorFactory, NativeSkillFolders
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    GrokThreadFile,
    NativeHelperRequest,
    NativeThreadRequest,
)
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



class GrokStore:
    """Reads the session folders of one Grok home: every thread of a scope for a list or search, or one id's summary.json."""

    @staticmethod
    def home(request: NativeHelperRequest, errors: NativeErrorFactory) -> Path:
        # @intent grok-helper-home-is-the-scope-home
        # The store of the helper's scope: the SDK scope is the private
        # home the runs of this workspace use, USER the user's ~/.grok
        # (spec INV-13, D-21). A user home Python cannot determine is
        # store_unreadable naming the error class (spec EC-13).
        try:
            return GrokHome.of(request.scope or GrokThreadScope.SDK, Path(request.workspace))
        except RuntimeError as exc:
            detail = native_threads.GROK_STORE_HOME_UNKNOWN_DETAIL.format(error_type=type(exc).__name__)
            raise errors.failure(NativeThreadProblem.STORE_UNREADABLE, request=request, searched=detail) from exc

    @staticmethod
    def threads(home: Path, request: NativeHelperRequest, errors: NativeErrorFactory) -> tuple[GrokThreadFile, ...]:
        # @intent grok-read-path-never-creates-a-home
        # Find the groups of the scope. A home or sessions folder that
        # does not exist holds no threads, and nothing is created on
        # the way (spec D-11, EC-1, EC-18).
        groups = [group for group in GrokStore._directories(home / native_threads.GROK_SESSIONS_DIR, request, errors) if GrokStore._in_scope(group, request, errors)]

        # Read the summary.json of every session folder in them. A file
        # that is there must be readable (spec INV-6); a folder without
        # one is a run still starting, or one grok just removed, and is
        # set aside (spec EC-11, EC-12).
        found: list[GrokThreadFile] = []
        waiting: list[Path] = []
        for group in groups:
            for folder in GrokStore._directories(group, request, errors):
                read = GrokStore._read(folder / native_threads.GROK_SUMMARY_FILE, request, errors)
                if read is None:
                    waiting.append(folder)
                else:
                    found.append(read)

        # Session folders but no summary.json at all may be a layout
        # Grok changed, which must not read as an empty store (spec
        # EC-67, D-31).
        if not found and waiting:
            GrokStore._check_layout(home, tuple(waiting), request, errors)
        return tuple(found)

    @staticmethod
    def thread(home: Path, request: NativeHelperRequest | NativeThreadRequest, errors: NativeErrorFactory, *, thread_id: str) -> GrokThreadFile | None:
        # Find the groups of the scope, as a list does; a run's request
        # reads every group of its private home.
        groups = [group for group in GrokStore._directories(home / native_threads.GROK_SESSIONS_DIR, request, errors) if GrokStore._in_scope(group, request, errors)]

        # @intent grok-one-id-reads-only-its-own-file
        # Read only <group>/<id>/summary.json, so another thread's
        # broken or half-written file cannot fail this one (spec D-27,
        # EC-68). The id passed NATIVE_THREAD_ID_PATTERN, so it is one
        # folder name and never a path.
        hits = [found for group in groups if (found := GrokStore._read(group / thread_id / native_threads.GROK_SUMMARY_FILE, request, errors)) is not None]

        # No group has it: the caller reports thread_not_found. An id
        # kept under two groups is the newer copy, as a list keeps it.
        return max(hits, key=lambda hit: hit.summary.updated_at, default=None)

    @staticmethod
    def _directories(folder: Path, request: NativeHelperRequest | NativeThreadRequest, errors: NativeErrorFactory) -> tuple[Path, ...]:
        # The folders directly inside folder; the files beside them are
        # not groups or sessions (spec EC-66), and a folder that is not
        # there holds none.
        try:
            return tuple(sorted(entry for entry in folder.iterdir() if entry.is_dir()))
        except FileNotFoundError:
            return ()
        except OSError as exc:
            detail = native_threads.GROK_STORE_PATH_DETAIL.format(path=folder, error_type=type(exc).__name__)
            raise errors.failure(NativeThreadProblem.STORE_UNREADABLE, request=request, searched=detail) from exc

    @staticmethod
    def _in_scope(group: Path, request: NativeHelperRequest | NativeThreadRequest, errors: NativeErrorFactory) -> bool:
        # @intent grok-user-scope-is-the-workspace-groups
        # The SDK scope, and a run, read every group of the private
        # home. The USER scope keeps a group whose decoded name, or
        # whose .cwd file, is the workspace, compared through
        # os.path.normcase so Windows ignores letter case and slash
        # direction (spec D-21, EC-19).
        if not isinstance(request, NativeHelperRequest) or request.scope is not GrokThreadScope.USER:
            return True
        wanted = os.path.normcase(str(request.workspace))
        if os.path.normcase(urllib.parse.unquote(group.name)) == wanted:
            return True
        path = group / native_threads.GROK_CWD_FILE
        try:
            if not path.is_file():
                return False
            with path.open(native_threads.NATIVE_BINARY_READ_MODE) as handle:
                data = handle.read(native_threads.GROK_CWD_MAX_BYTES)
        except FileNotFoundError:
            return False
        except OSError as exc:
            detail = native_threads.GROK_STORE_PATH_DETAIL.format(path=path, error_type=type(exc).__name__)
            raise errors.failure(NativeThreadProblem.STORE_UNREADABLE, request=request, searched=detail) from exc
        return os.path.normcase(data.decode(native_threads.NATIVE_TEXT_ENCODING, native_threads.NATIVE_DECODE_REPLACE).strip()) == wanted

    @staticmethod
    def _read(path: Path, request: NativeHelperRequest | NativeThreadRequest, errors: NativeErrorFactory) -> GrokThreadFile | None:
        # One summary.json, or None when it is not there. Only a regular
        # file is opened, and its size comes from the open handle, so
        # an oversize file is named and never loaded (spec EC-10); any
        # other OSError is store_unreadable naming the file (spec EC-13).
        try:
            if not path.is_file():
                return None
            with path.open(native_threads.NATIVE_BINARY_READ_MODE) as handle:
                size = os.fstat(handle.fileno()).st_size
                if size > native_threads.GROK_SUMMARY_MAX_BYTES:
                    detail = native_threads.GROK_SUMMARY_OVERSIZE_DETAIL.format(path=path, size=size, cap=native_threads.GROK_SUMMARY_MAX_BYTES)
                    raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, searched=detail)
                data = handle.read(native_threads.GROK_SUMMARY_MAX_BYTES)
        except FileNotFoundError:
            return None
        except OSError as exc:
            detail = native_threads.GROK_STORE_PATH_DETAIL.format(path=path, error_type=type(exc).__name__)
            raise errors.failure(NativeThreadProblem.STORE_UNREADABLE, request=request, searched=detail) from exc
        return GrokHelperWire.thread_file(data, path, errors, request)

    @staticmethod
    def _check_layout(home: Path, folders: tuple[Path, ...], request: NativeHelperRequest, errors: NativeErrorFactory) -> None:
        # @intent grok-store-without-summaries-is-a-layout-mismatch
        # Every session folder lacks summary.json. When the newest of
        # them is older than GROK_SUMMARY_GRACE_SECONDS no run is still
        # starting, so Grok keeps its threads elsewhere now and an
        # empty answer would be silently wrong (spec EC-67, D-31).
        changed: list[float] = []
        for folder in folders:
            try:
                changed.append(folder.stat().st_mtime)
            except FileNotFoundError:
                continue
            except OSError as exc:
                detail = native_threads.GROK_STORE_PATH_DETAIL.format(path=folder, error_type=type(exc).__name__)
                raise errors.failure(NativeThreadProblem.STORE_UNREADABLE, request=request, searched=detail) from exc
        if changed and time.time() - max(changed) > native_threads.GROK_SUMMARY_GRACE_SECONDS:
            detail = native_threads.GROK_STORE_LAYOUT_DETAIL.format(home=home, seconds=native_threads.GROK_SUMMARY_GRACE_SECONDS)
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, searched=detail)


__all__ = ["GrokHome", "GrokStore"]
