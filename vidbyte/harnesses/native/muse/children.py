"""FILE: vidbyte/harnesses/native/muse/children.py

PURPOSE: Defines MuseChildren, the shared plumbing of every muse child: the private config folder a call opens and closes, the environment overlay that points muse at it, the batch `muse serve` invocation, and the one way a muse child runs (reaped inside WSL on a timeout or a cancellation, with WSL launch failures explained).
ROLE IN CODEBASE: Used by MuseThreadRun (muse/threads.py) for #1036's run, continue and fork, by MuseHelperRun (muse/helpers.py) for the Muse thread helpers and the evidence read, and through them by MuseCommandRun (muse/commands.py). It uses MuseLauncher (muse/launcher.py) and NativeSkillFolders from hostkit.
ARCHITECTURE NOTE: Moved unchanged out of MuseThreadRun (spec D-10, INV-26), so the helpers launch muse exactly as the runs do. Every call gets a fresh temp folder as XDG_CONFIG_HOME, and MUSE_AUTH_PATH points at a file in it that is never created, so no saved Muse login or setting is read (spec INV-23). The folder is made in a worker thread whose preparation is shielded, so a cancel that lands while it is being made still removes it (spec INV-14). The module holds no literals of its own (spec INV-15).
FUNCTION INVENTORY: open_config creates the private config folder with the given skills and survives a cancel; close_config removes it; overlay builds the environment every muse child of the call shares; serve builds a batch `muse serve` invocation; run runs one child, reaps it on a timeout or cancellation and reports launch failures. _prepare_config makes the folder in a worker thread; _discard removes the folder of a preparation whose caller was cancelled.
COMMON MODIFICATION PATTERNS: A new variable every muse child needs goes in overlay; a new kind of muse child builds its own CliInvocation with launcher.environment and runs through run.
WHAT NOT TO DO IN THIS FILE: 1. Do not give `muse serve` a key; it needs none, and META_API_KEY is removed from what it inherits. 2. Do not give the temp folder a fixed location; tempfile.mkdtemp picks it (S054). 3. Do not skip the reap on a timeout or a cancel; stopping wsl.exe does not stop what it started in the distro.
KNOWN EDGE CASES: A removal that fails leaves the folder behind (#1036 EC-34). A second cancel while a cancelled preparation is being undone stops only the waiting, never the removal, which then ends in the background. On Windows the folder reaches muse in its /mnt form.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_threads.py, tests/features/harness_threads/test_harness_threads_wsl.py, tests/features/harness_threads/test_harness_threads_muse_helpers.py, tests/features/harness_threads/test_harness_threads_helper_bounds.py
"""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
from pathlib import Path

from vidbyte.harnesses.native.hostkit import NativeErrorFactory, NativeSkillFolders
from vidbyte.harnesses.native.muse.launcher import MuseLauncher
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    NativeHelperRequest,
    NativeThreadRequest,
)
from vidbyte.lib.dataclasses.process import CliInvocation, CliOutcome
from vidbyte.lib.enums.native_threads import (
    NativeEnvironmentVariable,
    NativeThreadProblem,
)
from vidbyte.lib.enums.process import CliOptionStyle
from vidbyte.lib.process import CliArgv, CliRunner


class MuseChildren:
    """The private config folder, environment, serve invocation and reaping run every muse child of a call shares."""

    @staticmethod
    async def open_config(skills: tuple[Path, ...], request: NativeThreadRequest | NativeHelperRequest, errors: NativeErrorFactory) -> Path:
        # @intent muse-key-and-skills-through-a-private-config-home
        # A fresh private config folder holds only the caller's skills,
        # so muse reads no saved login or setting; it is removed when
        # the call ends, however it ends. Cancelling the await does not
        # stop the worker thread that fills it, so a cancel that lands
        # mid-way waits for that work and removes the folder before it
        # goes on (spec INV-9).
        preparing = asyncio.ensure_future(asyncio.to_thread(MuseChildren._prepare_config, skills, request, errors))
        try:
            return await asyncio.shield(preparing)
        except asyncio.CancelledError:
            # The wait and the removal run as one shielded task, so a
            # second cancel cannot stop the removal half-way; it only
            # stops this call from waiting for it.
            await asyncio.shield(asyncio.ensure_future(MuseChildren._discard(preparing)))
            raise

    @staticmethod
    async def close_config(folder: Path) -> None:
        # The private folder goes however the call ends; a removal that
        # fails leaves it behind (spec EC-34).
        with contextlib.suppress(OSError):
            await asyncio.to_thread(NativeSkillFolders.remove, folder)

    @staticmethod
    def overlay(launcher: MuseLauncher, folder: Path) -> dict[str, str]:
        # What every child of the call shares: no self-update, the
        # private config folder, and an auth file inside it that never
        # exists, so a MUSE_AUTH_PATH of the caller's cannot point at a
        # saved login.
        return {
            NativeEnvironmentVariable.MUSE_NO_AUTO_UPDATE.value: native_threads.NATIVE_ENABLED_SWITCH,
            NativeEnvironmentVariable.XDG_CONFIG_HOME.value: launcher.visible_path(folder),
            NativeEnvironmentVariable.MUSE_AUTH_PATH.value: launcher.visible_path(folder.joinpath(*native_threads.MUSE_AUTH_FILE_PARTS)),
        }

    @staticmethod
    def serve(prefix: tuple[str, ...], frames: str, launcher: MuseLauncher, overlay: dict[str, str], mark: str | None, cwd: Path, *, removed: tuple[str, ...] = (NativeEnvironmentVariable.META_API_KEY.value,)) -> CliInvocation:
        # `muse serve` with the whole batch on stdin, bounded by the
        # control timeout, and with no key at all: META_API_KEY by
        # default, every key variable for a helper (spec INV-2).
        return CliInvocation(
            argv=CliArgv.build(prefix, command=(native_threads.MUSE_SERVE_COMMAND,), style=CliOptionStyle.SEPARATE),
            env_overlay=launcher.environment(overlay, mark),
            env_remove=removed,
            timeout_seconds=native_threads.NATIVE_CONTROL_TIMEOUT_SECONDS,
            max_output_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES,
            cwd=cwd,
            stdin_text=frames,
        )

    @staticmethod
    async def run(invocation: CliInvocation, launcher: MuseLauncher, request: NativeThreadRequest | NativeHelperRequest, errors: NativeErrorFactory, *, mark: str | None, thread_id: str | None) -> CliOutcome:
        # @intent muse-wsl-run-is-reaped
        # A cancelled or timed-out child is reaped inside WSL before the
        # call goes on, because stopping wsl.exe does not stop what it
        # started in the distro.
        try:
            outcome = await CliRunner().run(invocation)
        except asyncio.CancelledError:
            await launcher.reap(mark)
            raise
        if outcome.timed_out:
            await launcher.reap(mark)

        # A program the OS would not start, or a WSL that could not find
        # the distro or muse inside it, is reported as such.
        if outcome.launch_failure is not None:
            program, *_arguments = invocation.argv
            raise errors.from_launch_failure(outcome.launch_failure, program, request=request, thread_id=thread_id)
        failure = await launcher.launch_failure(outcome, request, thread_id=thread_id)
        if failure is not None:
            raise failure
        return outcome

    @staticmethod
    def _prepare_config(skills: tuple[Path, ...], request: NativeThreadRequest | NativeHelperRequest, errors: NativeErrorFactory) -> Path:
        # A new temp folder, with the skills copied into muse/skills; a
        # folder that cannot be prepared is launch_failed and leaves
        # nothing behind.
        folder: Path | None = None
        try:
            folder = Path(tempfile.mkdtemp())
            NativeSkillFolders.replace(skills, folder.joinpath(*native_threads.MUSE_CONFIG_SKILLS_PARTS))
        except OSError as exc:
            if folder is not None:
                with contextlib.suppress(OSError):
                    NativeSkillFolders.remove(folder)
            detail = native_threads.MUSE_CONFIG_FAILURE_DETAIL.format(error_type=type(exc).__name__, reason=exc.strerror or type(exc).__name__)
            raise errors.failure(NativeThreadProblem.LAUNCH_FAILED, request=request, searched=detail) from exc
        return folder

    @staticmethod
    async def _discard(preparing: asyncio.Future[Path]) -> None:
        # Waits for a preparation whose caller was cancelled, then
        # removes the folder it made. A preparation that failed has
        # already removed its own folder, and a removal that fails
        # leaves it behind (spec EC-34).
        await asyncio.wait({preparing})
        if preparing.exception() is None:
            with contextlib.suppress(OSError):
                await asyncio.to_thread(NativeSkillFolders.remove, preparing.result())


__all__ = ["MuseChildren"]
