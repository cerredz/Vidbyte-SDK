"""FILE: vidbyte/harnesses/native/muse/helpers.py

PURPOSE: Defines the six public Muse thread helpers and init_muse_workspace (MuseThreadHelpers: list_muse_threads, list_recent_muse_threads, list_muse_threads_since, get_muse_thread, read_muse_thread, get_muse_thread_lineage, init_muse_workspace) and the flows behind them (MuseHelperRun): one keyless `muse serve` batch per session/list or session/read, a `muse export` into an SDK temp folder for read, and `muse init` in the workspace; plus the two evidence reads of the Muse skill functions, tool_calls (session/read with items) and transcript (the run's own export).
ROLE IN CODEBASE: The helpers are bound as module names in vidbyte/harnesses/native/muse/__init__.py and re-exported from vidbyte.harnesses.native. MuseHelperRun uses MuseLauncher (muse/launcher.py) to find muse and translate paths, MuseChildren (muse/children.py) for the private config folder, the serve invocation and the reaping run, MuseWire and MuseSessionWire (muse/wire.py) to build the batches and read the answers, and NativeThreadListing from hostkit. MuseCommandRun (muse/commands.py) calls MuseHelperRun.tool_calls and transcript for its evidence.
ARCHITECTURE NOTE: No helper takes a key or a model (spec INV-2). Every flow opens one fresh private config folder (XDG_CONFIG_HOME, with a MUSE_AUTH_PATH that never exists) and removes it in finally, however the call ends, so no saved login is read (spec INV-23). Every child runs with every key variable removed, self-update off, and the fixed control timeout and output cap whatever config.timeout_seconds says (spec INV-16, D-14); in WSL mode every child carries the call's mark and a timed-out or cancelled one is reaped in the distro (spec INV-14). session/list always asks for NATIVE_LIST_MAX_LIMIT sessions, because Muse orders ties by ascending id and the SDK's cut must order them by INV-7 instead. read exports into an empty folder inside the private one, with that folder as the working folder, so muse export writes nowhere else and cannot take a file named like the id for the session (spec D-17, EC-40); the file is read in asyncio.to_thread with its size taken from the open handle. No flow calls another flow (spec R-1). The module holds no literals of its own (spec INV-15).
FUNCTION INVENTORY: MuseThreadHelpers holds the seven public functions and _call, the one guarded try they share. MuseHelperRun.list, get, lineage, read, init, tool_calls and transcript are the narrated flows; _serve runs one serve batch for one method and returns its result; _export runs the `muse export` child into the private folder; _export_file reads the exported file with its byte cap.
COMMON MODIFICATION PATTERNS: A new helper is one NativeThreadOperation member, its rows in the operation tables of vidbyte/lib/constants/native_threads.py, one public method here that calls _call with its flow, and one flow that opens and closes its private config folder around its children.
WHAT NOT TO DO IN THIS FILE: 1. Do not give a helper or evidence child a key, and do not let one inherit META_API_KEY or any other key variable. 2. Do not run muse export in the workspace or the caller's folder; it writes there and reads a same-named file as the session. 3. Do not read the export file before checking its size. 4. Do not leave the private config folder behind on any path, a cancel included. 5. Do not let one flow call another flow.
KNOWN EDGE CASES: -32020 is thread_not_found for the requested id and ends a lineage at a parent Muse cannot find (spec EC-65); -32601 is protocol_mismatch naming the method (spec EC-36). An export that exits 0 but writes no file is protocol_mismatch naming the file, and a file over NATIVE_PROCESS_MAX_OUTPUT_BYTES is output_too_large (spec EC-38, EC-39). init_muse_workspace where Muse is already set up is run_failed with Muse's text (spec EC-58); with dry_run it writes nothing (spec EC-59). On Windows, Muse runs only through config.wsl_distro or config.muse_command (spec EC-34).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_muse_helpers.py, tests/features/harness_threads/test_harness_threads_listing_properties.py, tests/features/harness_threads/test_harness_threads_helper_arguments.py, tests/features/harness_threads/test_harness_threads_helper_bounds.py, tests/features/harness_threads/test_harness_threads_helper_credentials.py, tests/features/harness_threads/test_harness_threads_muse_commands.py
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from vidbyte.harnesses.native.hostkit import NativeErrorFactory, NativeThreadListing
from vidbyte.harnesses.native.muse.children import MuseChildren
from vidbyte.harnesses.native.muse.launcher import MuseLauncher
from vidbyte.harnesses.native.muse.wire import MuseSessionWire, MuseWire
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    MuseThreadConfig,
    NativeCommandOutput,
    NativeHelperRequest,
    NativeThreadRequest,
    NativeThreadResult,
    NativeThreadSummary,
    NativeToolCall,
)
from vidbyte.lib.dataclasses.process import CliInvocation, CliOption
from vidbyte.lib.dataclasses.validation import RecordFieldConverter
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.enums.native_threads import (
    MuseFlag,
    MuseMethod,
    NativeHarness,
    NativeThreadOperation,
    NativeThreadProblem,
)
from vidbyte.lib.enums.process import CliOptionStyle
from vidbyte.lib.errors import ConfigurationError, NativeThreadError
from vidbyte.lib.process import CliArgv


class MuseThreadHelpers:
    """The public Muse Code thread helpers and init_muse_workspace: list, get, read and follow the threads of one workspace, and set Muse up in it, with no key."""

    @staticmethod
    async def list_muse_threads(workspace: str | Path, *, since: timedelta | None = None, limit: int = native_threads.NATIVE_LIST_DEFAULT_LIMIT, config: MuseThreadConfig | None = None) -> tuple[NativeThreadSummary, ...]:
        """List the Muse Code threads of workspace, newest first, at most limit, updated within since when given."""
        return await MuseThreadHelpers._call(NativeThreadOperation.LIST_MUSE_THREADS, MuseHelperRun.list, workspace=workspace, since=since, limit=limit, config=config)

    @staticmethod
    async def list_recent_muse_threads(workspace: str | Path, *, limit: int = native_threads.NATIVE_RECENT_DEFAULT_LIMIT, config: MuseThreadConfig | None = None) -> tuple[NativeThreadSummary, ...]:
        """List the limit most recently updated Muse Code threads of workspace."""
        return await MuseThreadHelpers._call(NativeThreadOperation.LIST_RECENT_MUSE_THREADS, MuseHelperRun.list, workspace=workspace, limit=limit, config=config)

    @staticmethod
    async def list_muse_threads_since(workspace: str | Path, since: timedelta, *, limit: int = native_threads.NATIVE_LIST_DEFAULT_LIMIT, config: MuseThreadConfig | None = None) -> tuple[NativeThreadSummary, ...]:
        """List the Muse Code threads of workspace updated within since, newest first, at most limit."""
        return await MuseThreadHelpers._call(NativeThreadOperation.LIST_MUSE_THREADS_SINCE, MuseHelperRun.list, workspace=workspace, since=since, limit=limit, config=config)

    @staticmethod
    async def get_muse_thread(thread_id: str, workspace: str | Path, *, config: MuseThreadConfig | None = None) -> NativeThreadSummary:
        """Return the summary of the Muse Code thread thread_id."""
        return await MuseThreadHelpers._call(NativeThreadOperation.GET_MUSE_THREAD, MuseHelperRun.get, workspace=workspace, thread_id=thread_id, config=config)

    @staticmethod
    async def read_muse_thread(thread_id: str, workspace: str | Path, *, config: MuseThreadConfig | None = None) -> NativeThreadResult:
        """Return the whole document `muse export` writes for the thread thread_id."""
        return await MuseThreadHelpers._call(NativeThreadOperation.READ_MUSE_THREAD, MuseHelperRun.read, workspace=workspace, thread_id=thread_id, config=config)

    @staticmethod
    async def get_muse_thread_lineage(thread_id: str, workspace: str | Path, *, config: MuseThreadConfig | None = None) -> tuple[NativeThreadSummary, ...]:
        """Return the chain of threads thread_id was forked from, root first and ending with thread_id."""
        return await MuseThreadHelpers._call(NativeThreadOperation.GET_MUSE_THREAD_LINEAGE, MuseHelperRun.lineage, workspace=workspace, thread_id=thread_id, config=config)

    @staticmethod
    async def init_muse_workspace(workspace: str | Path, *, dry_run: bool = False, config: MuseThreadConfig | None = None) -> NativeCommandOutput:
        """Run `muse init` in workspace, or only show what it would create when dry_run is True, and return what it printed."""
        return await MuseThreadHelpers._call(NativeThreadOperation.INIT_MUSE_WORKSPACE, MuseHelperRun.init, workspace=workspace, dry_run=dry_run, config=config)

    @staticmethod
    async def _call(
        operation: NativeThreadOperation,
        flow: Callable[[NativeHelperRequest, MuseThreadConfig, NativeErrorFactory], Awaitable[Any]],
        *,
        workspace: str | Path,
        thread_id: str | None = None,
        since: timedelta | None = None,
        limit: int | None = None,
        dry_run: bool = False,
        config: MuseThreadConfig | None = None,
    ) -> Any:
        # One guarded try per call: cancellation and the feature's own
        # errors pass through, a refused argument names the argument,
        # and anything else is a defect named only by its class. The
        # result is whatever the helper's flow returns.
        errors = NativeErrorFactory(NativeHarness.MUSE, operation)
        request: NativeHelperRequest | None = None
        try:
            request = NativeHelperRequest(harness=NativeHarness.MUSE, operation=operation, workspace=workspace, thread_id=thread_id, since=since, limit=limit, dry_run=dry_run)
            settings = MuseThreadConfig() if config is None else RecordFieldConverter.require_instance(config, native_threads.NATIVE_CONFIG_ARGUMENT, MuseThreadConfig)
            return await flow(request, settings, errors)
        except asyncio.CancelledError:
            raise
        except NativeThreadError:
            raise
        except ConfigurationError as exc:
            raise errors.from_configuration_error(exc, request) from exc
        except Exception as exc:
            raise errors.from_unexpected(exc, request) from exc


class MuseHelperRun:
    """The flows of the Muse thread helpers and evidence reads: one private config folder per call, keyless serve, export and init children."""

    @staticmethod
    async def list(request: NativeHelperRequest, config: MuseThreadConfig, errors: NativeErrorFactory) -> tuple[NativeThreadSummary, ...]:
        # Take the clock once, so the window has one edge for the whole
        # call (spec INV-7).
        cutoff = NativeThreadListing.cutoff(request.since, datetime.now(timezone.utc))

        # Find muse: the caller's command, WSL on Windows, else PATH;
        # and the workspace as muse sees it.
        launcher = MuseLauncher(config, errors)
        prefix = launcher.resolve(request)
        root = launcher.visible_path(Path(request.workspace))

        # @intent muse-list-asks-for-the-ceiling
        # Ask Muse for the workspace's sessions inside the window, as
        # many as any caller may keep, in a fresh private config folder
        # removed however the call ends. Muse orders equal times by
        # ascending id, so the SDK makes the cut itself.
        folder = await MuseChildren.open_config((), request, errors)
        try:
            params = MuseSessionWire.list_params(root, native_threads.NATIVE_LIST_MAX_LIMIT, cutoff)
            result = await MuseHelperRun._serve(MuseMethod.SESSION_LIST, params, prefix, launcher, MuseChildren.overlay(launcher, folder), launcher.new_mark(), request, errors)
        finally:
            await MuseChildren.close_config(folder)

        # Read every Session strictly, then keep one entry per id,
        # inside the window, newest first, at most limit.
        return NativeThreadListing.newest(MuseSessionWire.sessions(result, request, errors), cutoff=cutoff, limit=request.limit)

    @staticmethod
    async def get(request: NativeHelperRequest, config: MuseThreadConfig, errors: NativeErrorFactory) -> NativeThreadSummary:
        # Find muse, then read the thread's header with one serve batch
        # in a fresh private config folder; -32020 is thread_not_found.
        launcher = MuseLauncher(config, errors)
        prefix = launcher.resolve(request)
        folder = await MuseChildren.open_config((), request, errors)
        try:
            params = MuseWire.session_read_params(request.thread_id or "")
            result = await MuseHelperRun._serve(MuseMethod.SESSION_READ, params, prefix, launcher, MuseChildren.overlay(launcher, folder), launcher.new_mark(), request, errors)
        finally:
            await MuseChildren.close_config(folder)

        # The Session, read strictly.
        return MuseSessionWire.session(result, request, errors)

    @staticmethod
    async def lineage(request: NativeHelperRequest, config: MuseThreadConfig, errors: NativeErrorFactory) -> tuple[NativeThreadSummary, ...]:
        # Find muse and open one private config folder for the walk.
        launcher = MuseLauncher(config, errors)
        prefix = launcher.resolve(request)
        folder = await MuseChildren.open_config((), request, errors)
        try:
            mark, overlay = launcher.new_mark(), MuseChildren.overlay(launcher, folder)

            # Read the requested thread; an unknown id is thread_not_found.
            result = await MuseHelperRun._serve(MuseMethod.SESSION_READ, MuseWire.session_read_params(request.thread_id or ""), prefix, launcher, overlay, mark, request, errors)
            head = MuseSessionWire.session(result, request, errors)
            chain = [head]

            # Follow forkedFrom one serve batch at a time. Each step is
            # checked first, so a cycle or a chain past the depth cap
            # raises instead of walking forever (spec INV-10).
            parent = head.parent_thread_id
            while parent is not None:
                NativeThreadListing.check_step(tuple(chain), parent, errors, request)
                try:
                    result = await MuseHelperRun._serve(MuseMethod.SESSION_READ, MuseWire.session_read_params(parent), prefix, launcher, overlay, mark, request, errors)
                except NativeThreadError as exc:
                    # A parent Muse cannot find ends the chain; the head
                    # then names the missing id (spec EC-65).
                    if exc.failure_code is not FailureCode.MUSE_THREAD_NOT_FOUND:
                        raise
                    break
                head = MuseSessionWire.session(result, request, errors)
                chain.append(head)
                parent = head.parent_thread_id
        finally:
            await MuseChildren.close_config(folder)

        # Root first, ending with the requested thread.
        return tuple(reversed(chain))

    @staticmethod
    async def read(request: NativeHelperRequest, config: MuseThreadConfig, errors: NativeErrorFactory) -> NativeThreadResult:
        # Find muse and open a fresh private config folder for the call.
        thread_id = request.thread_id or ""
        launcher = MuseLauncher(config, errors)
        prefix = launcher.resolve(request)
        folder = await MuseChildren.open_config((), request, errors)
        try:
            mark, overlay = launcher.new_mark(), MuseChildren.overlay(launcher, folder)

            # Check the id with session/read first, so an unknown id is
            # thread_not_found and starts no export (spec EC-35).
            await MuseHelperRun._serve(MuseMethod.SESSION_READ, MuseWire.session_read_params(thread_id), prefix, launcher, overlay, mark, request, errors)

            # Export the thread into an empty folder inside the private
            # one, then read the file whole, with its byte cap, off the
            # event loop (spec D-17).
            path = await MuseHelperRun._export(prefix, launcher, overlay, mark, folder, request, errors, thread_id=thread_id)
            text = await asyncio.to_thread(MuseHelperRun._export_file, path, request, errors, thread_id)
        finally:
            await MuseChildren.close_config(folder)

        # The document is returned whole (spec INV-21).
        return NativeThreadResult(harness=NativeHarness.MUSE, thread_id=thread_id, text=text, text_truncated=False)

    @staticmethod
    async def init(request: NativeHelperRequest, config: MuseThreadConfig, errors: NativeErrorFactory) -> NativeCommandOutput:
        # Find muse and open a fresh private config folder, so init
        # reads no saved login or setting either.
        launcher = MuseLauncher(config, errors)
        prefix = launcher.resolve(request)
        folder = await MuseChildren.open_config((), request, errors)
        try:
            # @intent muse-init-writes-only-when-asked
            # Run `muse init` once in the workspace with no key; with
            # dry_run it only prints what it would create (spec EC-59).
            mark = launcher.new_mark()
            options = (CliOption(MuseFlag.DRY_RUN),) if request.dry_run else ()
            invocation = CliInvocation(
                argv=CliArgv.build(prefix, command=(native_threads.MUSE_INIT_COMMAND,), options=options, style=CliOptionStyle.SEPARATE),
                env_overlay=launcher.environment(MuseChildren.overlay(launcher, folder), mark),
                env_remove=native_threads.NATIVE_HELPER_REMOVED_VARIABLES,
                timeout_seconds=native_threads.NATIVE_CONTROL_TIMEOUT_SECONDS,
                max_output_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES,
                cwd=Path(request.workspace),
            )
            outcome = await MuseChildren.run(invocation, launcher, request, errors, mark=mark, thread_id=None)
        finally:
            await MuseChildren.close_config(folder)

        # A timeout, the cap or a failed exit raises with Muse's words
        # (spec EC-58); otherwise its standard output is the answer.
        MuseSessionWire.exited(outcome, request, errors)
        return NativeCommandOutput(harness=NativeHarness.MUSE, text=outcome.stdout)

    @staticmethod
    async def tool_calls(request: NativeThreadRequest, config: MuseThreadConfig, errors: NativeErrorFactory, *, thread_id: str) -> tuple[NativeToolCall, ...] | None:
        # The evidence read of a skill run: session/read with items, in
        # a fresh private config folder and with no key, every error
        # carrying the new thread's id (spec INV-8, EC-61).
        launcher = MuseLauncher(config, errors)
        prefix = launcher.resolve(request)
        folder = await MuseChildren.open_config((), request, errors)
        try:
            params = MuseSessionWire.read_items_params(thread_id)
            result = await MuseHelperRun._serve(MuseMethod.SESSION_READ, params, prefix, launcher, MuseChildren.overlay(launcher, folder), launcher.new_mark(), request, errors, thread_id=thread_id)
        finally:
            await MuseChildren.close_config(folder)

        # The toolCall items of the history, or None after compaction,
        # when the evidence must come from the transcript (spec D-33).
        return MuseSessionWire.tool_calls(result, request, errors, thread_id=thread_id)

    @staticmethod
    async def transcript(request: NativeThreadRequest, config: MuseThreadConfig, errors: NativeErrorFactory, *, thread_id: str) -> str:
        # The run's own export, for evidence after compaction (spec
        # D-33): the same keyless export child as read, in a fresh
        # private config folder removed however the call ends.
        launcher = MuseLauncher(config, errors)
        prefix = launcher.resolve(request)
        folder = await MuseChildren.open_config((), request, errors)
        try:
            mark, overlay = launcher.new_mark(), MuseChildren.overlay(launcher, folder)
            path = await MuseHelperRun._export(prefix, launcher, overlay, mark, folder, request, errors, thread_id=thread_id)
            return await asyncio.to_thread(MuseHelperRun._export_file, path, request, errors, thread_id)
        finally:
            await MuseChildren.close_config(folder)

    @staticmethod
    async def _serve(
        method: MuseMethod,
        params: Mapping[str, object],
        prefix: tuple[str, ...],
        launcher: MuseLauncher,
        overlay: dict[str, str],
        mark: str | None,
        request: NativeHelperRequest | NativeThreadRequest,
        errors: NativeErrorFactory,
        *,
        thread_id: str | None = None,
    ) -> Mapping[str, object]:
        # One serve batch for one method, with every key variable
        # removed (spec INV-2), reaped in WSL when it times out or is
        # cancelled; the answer's result, or the error it maps to.
        frames = MuseWire.batch_frames(method, params)
        invocation = MuseChildren.serve(prefix, frames, launcher, overlay, mark, Path(request.workspace), removed=native_threads.NATIVE_HELPER_REMOVED_VARIABLES)
        outcome = await MuseChildren.run(invocation, launcher, request, errors, mark=mark, thread_id=thread_id)
        return MuseSessionWire.result(outcome, request, errors, method=method, thread_id=thread_id)

    @staticmethod
    async def _export(
        prefix: tuple[str, ...],
        launcher: MuseLauncher,
        overlay: dict[str, str],
        mark: str | None,
        folder: Path,
        request: NativeHelperRequest | NativeThreadRequest,
        errors: NativeErrorFactory,
        *,
        thread_id: str,
    ) -> Path:
        # @intent muse-export-runs-in-an-empty-sdk-folder
        # muse export writes into its working folder and takes a path
        # there named like the id for the session, so it runs in an
        # empty folder inside the private one, with --out there too, in
        # the form muse sees (spec D-17, EC-40).
        target = folder.joinpath(*native_threads.MUSE_EXPORT_PARTS)
        await asyncio.to_thread(target.parent.mkdir)
        options = (CliOption(MuseFlag.SESSION, thread_id), CliOption(MuseFlag.OUT, launcher.visible_path(target)))
        invocation = CliInvocation(
            argv=CliArgv.build(prefix, command=(native_threads.MUSE_EXPORT_COMMAND,), options=options, style=CliOptionStyle.SEPARATE),
            env_overlay=launcher.environment(overlay, mark),
            env_remove=native_threads.NATIVE_HELPER_REMOVED_VARIABLES,
            timeout_seconds=native_threads.NATIVE_CONTROL_TIMEOUT_SECONDS,
            max_output_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES,
            cwd=target.parent,
        )
        outcome = await MuseChildren.run(invocation, launcher, request, errors, mark=mark, thread_id=thread_id)

        # A timeout, the cap or a failed exit raises with Muse's words;
        # the caller then reads the file.
        MuseSessionWire.exited(outcome, request, errors, thread_id=thread_id)
        return target

    @staticmethod
    def _export_file(path: Path, request: NativeHelperRequest | NativeThreadRequest, errors: NativeErrorFactory, thread_id: str) -> str:
        # The exported file whole, as UTF-8 text. Its size comes from
        # the open handle, so a file over the cap is never loaded (spec
        # EC-39); no file at all is protocol_mismatch naming it (spec
        # EC-38).
        try:
            with path.open(native_threads.NATIVE_BINARY_READ_MODE) as handle:
                if os.fstat(handle.fileno()).st_size > native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES:
                    raise errors.failure(NativeThreadProblem.OUTPUT_TOO_LARGE, request=request, thread_id=thread_id, cap_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES)
                data = handle.read(native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES)
        except FileNotFoundError as exc:
            raise errors.failure(NativeThreadProblem.PROTOCOL_MISMATCH, request=request, thread_id=thread_id, searched=native_threads.MUSE_EXPORT_FILE_MISSING_DETAIL.format(path=path)) from exc
        return data.decode(native_threads.NATIVE_TEXT_ENCODING, native_threads.NATIVE_DECODE_REPLACE)


__all__ = ["MuseHelperRun", "MuseThreadHelpers"]
