"""FILE: vidbyte/harnesses/native/muse/threads.py

PURPOSE: Defines the three public Muse Code thread functions (MuseThreads: run_muse_thread, continue_muse_thread, fork_muse_thread) and the flow of one call (MuseThreadRun): find muse (directly or through WSL), prepare a private config folder with the caller's skills, check or fork the thread over one batch `muse serve` exchange, run `muse exec --json` headless once with the caller's key, and read its records.
ROLE IN CODEBASE: The functions are bound as module names in vidbyte/harnesses/native/muse/__init__.py and re-exported from vidbyte.harnesses.native. MuseThreadRun uses MuseLauncher (muse/launcher.py), NativeSkillFolders and NativeErrorFactory from hostkit, CliArgv and CliRunner from vidbyte.lib.process, and MuseWire and MuseExecOutput (muse/wire.py).
ARCHITECTURE NOTE: Every call gets a fresh temp folder as XDG_CONFIG_HOME, holding only the caller's skills, and MUSE_AUTH_PATH points at a file in it that is never created, so no saved Muse login or setting is read and the key reaches muse only as META_API_KEY in the exec child's environment. `muse serve` needs no credential and gets none, not even a META_API_KEY of the caller's own (env_remove). In WSL mode every child carries the call's peer mark, and a timeout or a cancellation reaps the marked processes inside the distro before the call ends. The module holds no literals of its own (spec INV-15): flags are MuseFlag members and every other value comes from vidbyte/lib/constants/native_threads.py.
FUNCTION INVENTORY: MuseThreads.run_muse_thread, continue_muse_thread and fork_muse_thread are the public functions; MuseThreads._call is the one guarded try they share. MuseThreadRun.execute is the narrated main function of one call; _prepare_config creates the private config folder and its skills; _overlay builds the environment shared by serve and exec; _serve_invocation and _exec_invocation build the two children; _run runs one child, reaps it on a timeout or cancellation and reports launch failures.
COMMON MODIFICATION PATTERNS: A new Muse option is a MuseThreadConfig field (vidbyte/lib/dataclasses/native_threads.py), a MuseFlag member and one CliOption in _exec_invocation. A new failure condition goes in MuseExecOutput.read or MuseWire.read_answer.
WHAT NOT TO DO IN THIS FILE: 1. Do not put the key on argv or in a file, and do not give it to `muse serve`. 2. Do not start exec for a continue or fork whose serve answer failed; `muse exec --session-id <unknown>` would silently create a thread. 3. Do not give the temp folder a fixed location; tempfile.mkdtemp picks it (S054).
KNOWN EDGE CASES: The temp folder is removed in a finally block, after the reap, so a cancelled call still cleans up before CancelledError propagates (spec INV-9). On Windows the temp folder and the workspace reach muse in their /mnt form; a workspace with no /mnt form is refused naming workspace before anything is written. A fork that fails after session/fork answered carries the fork's new id (spec INV-5).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/
"""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
from collections.abc import Sequence
from pathlib import Path

from vidbyte.harnesses.native.hostkit import NativeErrorFactory, NativeSkillFolders
from vidbyte.harnesses.native.muse.launcher import MuseLauncher
from vidbyte.harnesses.native.muse.wire import MuseExecOutput, MuseWire
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    MuseThreadConfig,
    NativeThreadRequest,
    NativeThreadResult,
)
from vidbyte.lib.dataclasses.process import CliInvocation, CliOption, CliOutcome
from vidbyte.lib.dataclasses.validation import RecordFieldConverter
from vidbyte.lib.enums.native_threads import (
    MuseFlag,
    MuseMethod,
    NativeEnvironmentVariable,
    NativeHarness,
    NativeThreadOperation,
    NativeThreadProblem,
    NativeThreadVerb,
)
from vidbyte.lib.enums.process import CliOptionStyle
from vidbyte.lib.errors import ConfigurationError, NativeThreadError
from vidbyte.lib.process import CliArgv, CliRunner


class MuseThreads:
    """The public Muse Code thread functions: start, continue or fork one thread headless with the caller's key."""

    @staticmethod
    async def run_muse_thread(prompt: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: MuseThreadConfig | None = None) -> NativeThreadResult:
        """Start a new Muse Code thread in workspace, run prompt once with api_key, and return its id and answer."""
        return await MuseThreads._call(NativeThreadOperation.RUN_MUSE_THREAD, NativeThreadVerb.RUN, None, prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def continue_muse_thread(thread_id: str, prompt: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: MuseThreadConfig | None = None) -> NativeThreadResult:
        """Check that the Muse Code thread thread_id exists, then run prompt once more on it."""
        return await MuseThreads._call(NativeThreadOperation.CONTINUE_MUSE_THREAD, NativeThreadVerb.CONTINUE, thread_id, prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def fork_muse_thread(thread_id: str, prompt: str, *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: MuseThreadConfig | None = None) -> NativeThreadResult:
        """Fork the Muse Code thread thread_id into a new thread, run prompt on the copy, and return the new id."""
        return await MuseThreads._call(NativeThreadOperation.FORK_MUSE_THREAD, NativeThreadVerb.FORK, thread_id, prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, config=config)

    @staticmethod
    async def _call(operation: NativeThreadOperation, verb: NativeThreadVerb, thread_id: str | None, prompt: str, *, api_key: str, workspace: str | Path, model: str | None, skills: Sequence[str | Path], config: MuseThreadConfig | None) -> NativeThreadResult:
        # One guarded try per call: cancellation and the feature's own
        # errors pass through, a refused argument names the argument,
        # and anything else is a defect named only by its class.
        errors = NativeErrorFactory(NativeHarness.MUSE, operation)
        request: NativeThreadRequest | None = None
        try:
            request = NativeThreadRequest(harness=NativeHarness.MUSE, verb=verb, prompt=prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, thread_id=thread_id)
            settings = MuseThreadConfig() if config is None else RecordFieldConverter.require_instance(config, native_threads.NATIVE_CONFIG_ARGUMENT, MuseThreadConfig)
            return await MuseThreadRun.execute(request, settings, errors)
        except asyncio.CancelledError:
            raise
        except NativeThreadError:
            raise
        except ConfigurationError as exc:
            raise errors.from_configuration_error(exc, request) from exc
        except Exception as exc:
            raise errors.from_unexpected(exc, request) from exc


class MuseThreadRun:
    """One Muse Code call: launcher, private config folder, optional serve check or fork, exec run and records."""

    @staticmethod
    async def execute(request: NativeThreadRequest, config: MuseThreadConfig, errors: NativeErrorFactory) -> NativeThreadResult:
        # Find muse: the caller's command, WSL on Windows, else PATH.
        launcher = MuseLauncher(config, errors)
        prefix = launcher.resolve(request)

        # The workspace as muse sees it; a path WSL cannot mount is
        # refused here, before anything is written.
        workspace = launcher.visible_path(Path(request.workspace))

        # From here on the key is scrubbed from anything muse prints.
        errors.register_secret(request.api_key)

        # @intent muse-key-and-skills-through-a-private-config-home
        # A fresh private config folder holds only the caller's skills,
        # so muse reads no saved login or setting; it is removed when
        # the call ends, however it ends.
        folder = await asyncio.to_thread(MuseThreadRun._prepare_config, request, errors)
        try:
            # One mark for every child of this call, so a reap finds
            # exactly this call's processes inside WSL.
            mark = launcher.new_mark()
            overlay = MuseThreadRun._overlay(launcher, folder)

            # @intent muse-continue-checks-the-thread-first
            # A continue checks the thread with session/read, and a fork
            # copies it with session/fork, before exec runs; exec would
            # silently start a new thread for an id Muse does not know.
            thread_id = request.thread_id
            if request.verb is not NativeThreadVerb.RUN:
                serve = MuseThreadRun._serve_invocation(prefix, request, launcher, overlay, mark)
                answered = await MuseThreadRun._run(serve, launcher, request, errors, mark=mark, thread_id=None)
                thread_id = MuseWire.read_answer(answered, request, errors, timeout_seconds=native_threads.NATIVE_CONTROL_TIMEOUT_SECONDS)

            # Run muse exec once, headless, with the key in its
            # environment and no standard input, on the checked or new
            # thread.
            run = MuseThreadRun._exec_invocation(prefix, request, config, launcher, overlay, mark, workspace=workspace, thread_id=thread_id)
            outcome = await MuseThreadRun._run(run, launcher, request, errors, mark=mark, thread_id=thread_id)

            # Read the records: the session stream and the final text.
            return MuseExecOutput.read(outcome, request, errors, thread_id=thread_id, timeout_seconds=config.timeout_seconds)
        finally:
            # The private folder goes however the call ends; a removal
            # that fails leaves it behind (spec EC-34).
            with contextlib.suppress(OSError):
                await asyncio.to_thread(NativeSkillFolders.remove, folder)

    @staticmethod
    def _prepare_config(request: NativeThreadRequest, errors: NativeErrorFactory) -> Path:
        # A new temp folder, with the caller's skills copied into
        # muse/skills; a folder that cannot be prepared is launch_failed
        # and leaves nothing behind.
        folder: Path | None = None
        try:
            folder = Path(tempfile.mkdtemp())
            NativeSkillFolders.replace(tuple(Path(skill) for skill in request.skills), folder.joinpath(*native_threads.MUSE_CONFIG_SKILLS_PARTS))
        except OSError as exc:
            if folder is not None:
                with contextlib.suppress(OSError):
                    NativeSkillFolders.remove(folder)
            detail = native_threads.MUSE_CONFIG_FAILURE_DETAIL.format(error_type=type(exc).__name__, reason=exc.strerror or type(exc).__name__)
            raise errors.failure(NativeThreadProblem.LAUNCH_FAILED, request=request, searched=detail) from exc
        return folder

    @staticmethod
    def _overlay(launcher: MuseLauncher, folder: Path) -> dict[str, str]:
        # What serve and exec share: no self-update, the private config
        # folder, and an auth file inside it that never exists, so a
        # MUSE_AUTH_PATH of the caller's cannot point at a saved login.
        return {
            NativeEnvironmentVariable.MUSE_NO_AUTO_UPDATE.value: native_threads.NATIVE_ENABLED_SWITCH,
            NativeEnvironmentVariable.XDG_CONFIG_HOME.value: launcher.visible_path(folder),
            NativeEnvironmentVariable.MUSE_AUTH_PATH.value: launcher.visible_path(folder.joinpath(*native_threads.MUSE_AUTH_FILE_PARTS)),
        }

    @staticmethod
    def _serve_invocation(prefix: tuple[str, ...], request: NativeThreadRequest, launcher: MuseLauncher, overlay: dict[str, str], mark: str | None) -> CliInvocation:
        # `muse serve` with the whole batch on stdin, bounded by the
        # control timeout, and with no META_API_KEY at all.
        source = request.thread_id or ""
        if request.verb is NativeThreadVerb.FORK:
            frames = MuseWire.batch_frames(MuseMethod.SESSION_FORK, MuseWire.session_fork_params(source))
        else:
            frames = MuseWire.batch_frames(MuseMethod.SESSION_READ, MuseWire.session_read_params(source))
        return CliInvocation(
            argv=CliArgv.build(prefix, command=(native_threads.MUSE_SERVE_COMMAND,), style=CliOptionStyle.SEPARATE),
            env_overlay=launcher.environment(overlay, mark),
            env_remove=(NativeEnvironmentVariable.META_API_KEY.value,),
            timeout_seconds=native_threads.NATIVE_CONTROL_TIMEOUT_SECONDS,
            max_output_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES,
            cwd=Path(request.workspace),
            stdin_text=frames,
        )

    @staticmethod
    def _exec_invocation(prefix: tuple[str, ...], request: NativeThreadRequest, config: MuseThreadConfig, launcher: MuseLauncher, overlay: dict[str, str], mark: str | None, *, workspace: str, thread_id: str | None) -> CliInvocation:
        # `muse exec` with separate option elements and the prompt after
        # a literal --, so it can never become a flag; the key travels
        # only as META_API_KEY.
        options = [CliOption(MuseFlag.JSON), CliOption(MuseFlag.PROVIDER, native_threads.MUSE_PROVIDER), CliOption(MuseFlag.WORKSPACE, workspace)]
        if thread_id is not None:
            options.append(CliOption(MuseFlag.SESSION_ID, thread_id))
        if request.model is not None:
            options.append(CliOption(MuseFlag.MODEL, request.model))
        if config.reasoning_effort is not None:
            options.append(CliOption(MuseFlag.REASONING_EFFORT, config.reasoning_effort.value))
        options.append(CliOption(MuseFlag.USER_INPUT_AUTO_RESOLVE))
        argv = CliArgv.build(prefix, command=(native_threads.MUSE_EXEC_COMMAND,), options=tuple(options), style=CliOptionStyle.SEPARATE, operands=(MuseFlag.END_OF_OPTIONS, request.prompt))
        return CliInvocation(
            argv=argv,
            env_overlay=launcher.environment({**overlay, NativeEnvironmentVariable.META_API_KEY.value: request.api_key}, mark),
            timeout_seconds=config.timeout_seconds,
            max_output_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES,
            cwd=Path(request.workspace),
        )

    @staticmethod
    async def _run(invocation: CliInvocation, launcher: MuseLauncher, request: NativeThreadRequest, errors: NativeErrorFactory, *, mark: str | None, thread_id: str | None) -> CliOutcome:
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


__all__ = ["MuseThreadRun", "MuseThreads"]
