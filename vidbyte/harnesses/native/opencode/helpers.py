"""FILE: vidbyte/harnesses/native/opencode/helpers.py

PURPOSE: Defines the eight public opencode thread helpers (OpencodeThreadHelpers: list_opencode_threads, list_recent_opencode_threads, list_opencode_threads_since, get_opencode_thread, read_opencode_thread, get_opencode_thread_lineage, search_opencode_threads, delete_opencode_thread) and the flows behind them (OpencodeHelperRun): each one starts opencode's own session commands keyless, `session list` for lists and search, one `opencode db` query per id for get and lineage, `export` for read and `session delete` for delete.
ROLE IN CODEBASE: The helpers are bound as module names in vidbyte/harnesses/native/opencode/__init__.py and re-exported from vidbyte.harnesses.native. OpencodeHelperRun uses NativeLauncher, NativeErrorFactory and NativeThreadListing from hostkit, OpencodeHelperWire (opencode/wire.py) to read each child's output, and CliArgv and CliRunner from vidbyte.lib.process.
ARCHITECTURE NOTE: No helper takes a key or a model (spec INV-2): every child runs without OPENCODE_CONFIG_CONTENT or any other key variable, with self-update off, in the workspace with PWD overlaid to it, so an inherited PWD cannot choose the project (spec D-22), and within the fixed control timeout and output cap whatever config.timeout_seconds says (spec INV-16, D-14). `session list` returns the root sessions of the whole project, so lists keep the rows whose directory is the workspace (spec D-19) and ask for NATIVE_OPENCODE_SCAN_MAX rows, the most the SDK reads. get and lineage read one exact id database-wide with the constant OPENCODE_SESSION_QUERY, whose only caller value is a pattern-checked id (spec D-26, INV-9). No flow calls another flow (spec R-1). The module holds no literals of its own (spec INV-15).
FUNCTION INVENTORY: OpencodeThreadHelpers holds the eight public helpers and _call, the one guarded try they share. OpencodeHelperRun.list, search, get, lineage, read and delete are the narrated flows; _child runs one keyless opencode child and reports a launch failure; _query builds the db query of one id.
COMMON MODIFICATION PATTERNS: A new helper is one NativeThreadOperation member, its rows in the operation tables of vidbyte/lib/constants/native_threads.py, one public method here that calls _call with its flow, and one flow that calls _child and an OpencodeHelperWire reader.
WHAT NOT TO DO IN THIS FILE: 1. Do not give a helper child OPENCODE_CONFIG_CONTENT or any key. 2. Do not put the search query, or any caller text other than a checked id, on argv or in the SQL (spec INV-9). 3. Do not drop --max-count from session list; without it opencode stops at 100 rows across the project (spec D-19). 4. Do not let one flow call another flow.
KNOWN EDGE CASES: `session list` lists roots only, so a subagent child never lists, but get, read and lineage still reach it by id (spec EC-77). A thread made by fork_opencode_thread records no parent, so its lineage is itself alone (spec EC-76). An empty list output, or [], is no threads (spec EC-29); exactly NATIVE_OPENCODE_SCAN_MAX rows may be a cut list and raises (spec EC-75). A parent that has no row ends the chain (spec EC-25).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_opencode_helpers.py, tests/features/harness_threads/test_harness_threads_listing_properties.py, tests/features/harness_threads/test_harness_threads_helper_arguments.py, tests/features/harness_threads/test_harness_threads_helper_bounds.py, tests/features/harness_threads/test_harness_threads_helper_credentials.py
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from vidbyte.harnesses.native.hostkit import NativeErrorFactory, NativeLauncher, NativeThreadListing
from vidbyte.harnesses.native.opencode.wire import OpencodeHelperWire
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    NativeHelperRequest,
    NativeThreadResult,
    NativeThreadSummary,
    OpencodeThreadConfig,
)
from vidbyte.lib.dataclasses.process import CliInvocation, CliOption, CliOutcome
from vidbyte.lib.dataclasses.validation import RecordFieldConverter
from vidbyte.lib.enums.native_threads import (
    NativeEnvironmentVariable,
    NativeHarness,
    NativeThreadOperation,
    NativeThreadProblem,
    OpencodeFlag,
)
from vidbyte.lib.enums.process import CliOptionStyle
from vidbyte.lib.errors import ConfigurationError, NativeThreadError
from vidbyte.lib.process import CliArgv, CliRunner


class OpencodeThreadHelpers:
    """The public opencode thread helpers: list, search, get, read, follow and delete the sessions of one workspace, with no key."""

    @staticmethod
    async def list_opencode_threads(workspace: str | Path, *, since: timedelta | None = None, limit: int = native_threads.NATIVE_LIST_DEFAULT_LIMIT, config: OpencodeThreadConfig | None = None) -> tuple[NativeThreadSummary, ...]:
        """List the opencode sessions of workspace, newest first, at most limit, updated within since when given."""
        return await OpencodeThreadHelpers._call(NativeThreadOperation.LIST_OPENCODE_THREADS, OpencodeHelperRun.list, workspace=workspace, since=since, limit=limit, config=config)

    @staticmethod
    async def list_recent_opencode_threads(workspace: str | Path, *, limit: int = native_threads.NATIVE_RECENT_DEFAULT_LIMIT, config: OpencodeThreadConfig | None = None) -> tuple[NativeThreadSummary, ...]:
        """List the limit most recently updated opencode sessions of workspace."""
        return await OpencodeThreadHelpers._call(NativeThreadOperation.LIST_RECENT_OPENCODE_THREADS, OpencodeHelperRun.list, workspace=workspace, limit=limit, config=config)

    @staticmethod
    async def list_opencode_threads_since(workspace: str | Path, since: timedelta, *, limit: int = native_threads.NATIVE_LIST_DEFAULT_LIMIT, config: OpencodeThreadConfig | None = None) -> tuple[NativeThreadSummary, ...]:
        """List the opencode sessions of workspace updated within since, newest first, at most limit."""
        return await OpencodeThreadHelpers._call(NativeThreadOperation.LIST_OPENCODE_THREADS_SINCE, OpencodeHelperRun.list, workspace=workspace, since=since, limit=limit, config=config)

    @staticmethod
    async def get_opencode_thread(thread_id: str, workspace: str | Path, *, config: OpencodeThreadConfig | None = None) -> NativeThreadSummary:
        """Return the summary of the opencode session thread_id, a subagent child included."""
        return await OpencodeThreadHelpers._call(NativeThreadOperation.GET_OPENCODE_THREAD, OpencodeHelperRun.get, workspace=workspace, thread_id=thread_id, config=config)

    @staticmethod
    async def read_opencode_thread(thread_id: str, workspace: str | Path, *, config: OpencodeThreadConfig | None = None) -> NativeThreadResult:
        """Return the whole document `opencode export` prints for the session thread_id."""
        return await OpencodeThreadHelpers._call(NativeThreadOperation.READ_OPENCODE_THREAD, OpencodeHelperRun.read, workspace=workspace, thread_id=thread_id, config=config)

    @staticmethod
    async def get_opencode_thread_lineage(thread_id: str, workspace: str | Path, *, config: OpencodeThreadConfig | None = None) -> tuple[NativeThreadSummary, ...]:
        """Return the chain of sessions above thread_id by parent_id, root first and ending with thread_id."""
        return await OpencodeThreadHelpers._call(NativeThreadOperation.GET_OPENCODE_THREAD_LINEAGE, OpencodeHelperRun.lineage, workspace=workspace, thread_id=thread_id, config=config)

    @staticmethod
    async def search_opencode_threads(workspace: str | Path, query: str, *, limit: int = native_threads.NATIVE_LIST_DEFAULT_LIMIT, config: OpencodeThreadConfig | None = None) -> tuple[NativeThreadSummary, ...]:
        """List the opencode sessions of workspace whose title holds query, case-insensitively, newest first."""
        return await OpencodeThreadHelpers._call(NativeThreadOperation.SEARCH_OPENCODE_THREADS, OpencodeHelperRun.search, workspace=workspace, query=query, limit=limit, config=config)

    @staticmethod
    async def delete_opencode_thread(thread_id: str, workspace: str | Path, *, config: OpencodeThreadConfig | None = None) -> None:
        """Delete the opencode session thread_id through `opencode session delete`."""
        await OpencodeThreadHelpers._call(NativeThreadOperation.DELETE_OPENCODE_THREAD, OpencodeHelperRun.delete, workspace=workspace, thread_id=thread_id, config=config)

    @staticmethod
    async def _call(
        operation: NativeThreadOperation,
        flow: Callable[[NativeHelperRequest, OpencodeThreadConfig, NativeErrorFactory], Awaitable[Any]],
        *,
        workspace: str | Path,
        thread_id: str | None = None,
        since: timedelta | None = None,
        limit: int | None = None,
        query: str | None = None,
        config: OpencodeThreadConfig | None = None,
    ) -> Any:
        # One guarded try per call: cancellation and the feature's own
        # errors pass through, a refused argument names the argument,
        # and anything else is a defect named only by its class. The
        # result is whatever the helper's flow returns.
        errors = NativeErrorFactory(NativeHarness.OPENCODE, operation)
        request: NativeHelperRequest | None = None
        try:
            request = NativeHelperRequest(harness=NativeHarness.OPENCODE, operation=operation, workspace=workspace, thread_id=thread_id, since=since, limit=limit, query=query)
            settings = OpencodeThreadConfig() if config is None else RecordFieldConverter.require_instance(config, native_threads.NATIVE_CONFIG_ARGUMENT, OpencodeThreadConfig)
            return await flow(request, settings, errors)
        except asyncio.CancelledError:
            raise
        except NativeThreadError:
            raise
        except ConfigurationError as exc:
            raise errors.from_configuration_error(exc, request) from exc
        except Exception as exc:
            raise errors.from_unexpected(exc, request) from exc


class OpencodeHelperRun:
    """The flows of the opencode thread helpers: one keyless opencode child per step, and the checks around it."""

    @staticmethod
    async def list(request: NativeHelperRequest, config: OpencodeThreadConfig, errors: NativeErrorFactory) -> tuple[NativeThreadSummary, ...]:
        # Take the clock once, so the window has one edge for the whole
        # call (spec INV-7).
        cutoff = NativeThreadListing.cutoff(request.since, datetime.now(timezone.utc))

        # Ask opencode for the root sessions of the workspace's project,
        # as many as the SDK reads at most (spec D-19).
        options = (CliOption(OpencodeFlag.FORMAT, native_threads.OPENCODE_JSON_FORMAT), CliOption(OpencodeFlag.MAX_COUNT, str(native_threads.NATIVE_OPENCODE_SCAN_MAX)))
        outcome = await OpencodeHelperRun._child(request, config, errors, command=(native_threads.OPENCODE_SESSION_COMMAND, native_threads.OPENCODE_LIST_COMMAND), options=options)

        # @intent opencode-list-keeps-the-workspace-rows
        # A project spans its subfolders and the global project spans
        # every folder, so only the rows whose directory is the
        # workspace are its threads (spec D-19, EC-28).
        wanted = os.path.normcase(str(request.workspace))
        mine = (summary for summary, directory in OpencodeHelperWire.sessions(outcome, request, errors) if os.path.normcase(directory) == wanted)

        # Keep one entry per id, inside the window, newest first, at
        # most limit. The request checked the limit; `or` only tells
        # the type checker it is set.
        return NativeThreadListing.newest(mine, cutoff=cutoff, limit=request.limit or 0)

    @staticmethod
    async def search(request: NativeHelperRequest, config: OpencodeThreadConfig, errors: NativeErrorFactory) -> tuple[NativeThreadSummary, ...]:
        # Read the workspace's sessions as a list does; the query never
        # reaches opencode (spec INV-9).
        options = (CliOption(OpencodeFlag.FORMAT, native_threads.OPENCODE_JSON_FORMAT), CliOption(OpencodeFlag.MAX_COUNT, str(native_threads.NATIVE_OPENCODE_SCAN_MAX)))
        outcome = await OpencodeHelperRun._child(request, config, errors, command=(native_threads.OPENCODE_SESSION_COMMAND, native_threads.OPENCODE_LIST_COMMAND), options=options)
        wanted = os.path.normcase(str(request.workspace))

        # Keep the workspace's sessions whose title holds the query
        # literally, in any letter case: the title is the only text a
        # list row carries.
        query = request.query or ""
        matching = (summary for summary, directory in OpencodeHelperWire.sessions(outcome, request, errors) if os.path.normcase(directory) == wanted and NativeThreadListing.matches((summary.title,), query))

        # Newest first, one entry per id, at most limit.
        return NativeThreadListing.newest(matching, cutoff=None, limit=request.limit or 0)

    @staticmethod
    async def get(request: NativeHelperRequest, config: OpencodeThreadConfig, errors: NativeErrorFactory) -> NativeThreadSummary:
        # Read the id's row from opencode's session table, database-wide,
        # with one db child (spec D-26).
        options = (CliOption(OpencodeFlag.FORMAT, native_threads.OPENCODE_JSON_FORMAT),)
        outcome = await OpencodeHelperRun._child(request, config, errors, command=(native_threads.OPENCODE_DB_COMMAND,), options=options, operands=(OpencodeHelperRun._query(request.thread_id or ""),))
        rows = OpencodeHelperWire.rows(outcome, request, errors)

        # No row means opencode has no such session.
        if not rows:
            raise errors.failure(NativeThreadProblem.THREAD_NOT_FOUND, request=request)
        return rows[0]

    @staticmethod
    async def lineage(request: NativeHelperRequest, config: OpencodeThreadConfig, errors: NativeErrorFactory) -> tuple[NativeThreadSummary, ...]:
        # Read the requested session's row; no row is thread_not_found.
        options = (CliOption(OpencodeFlag.FORMAT, native_threads.OPENCODE_JSON_FORMAT),)
        outcome = await OpencodeHelperRun._child(request, config, errors, command=(native_threads.OPENCODE_DB_COMMAND,), options=options, operands=(OpencodeHelperRun._query(request.thread_id or ""),))
        chain = [*OpencodeHelperWire.rows(outcome, request, errors)]
        if not chain:
            raise errors.failure(NativeThreadProblem.THREAD_NOT_FOUND, request=request)

        # Follow parent_id one db child at a time. Each step is checked
        # first, so a cycle or a chain past the depth cap raises instead
        # of walking forever (spec INV-10).
        parent = chain[-1].parent_thread_id
        while parent is not None:
            NativeThreadListing.check_step(tuple(chain), parent, errors, request)
            step = await OpencodeHelperRun._child(request, config, errors, command=(native_threads.OPENCODE_DB_COMMAND,), options=options, operands=(OpencodeHelperRun._query(parent),))
            rows = OpencodeHelperWire.rows(step, request, errors)

            # A parent with no row ends the chain; the head then names
            # the missing id (spec EC-25).
            if not rows:
                break
            chain.append(rows[0])
            parent = rows[0].parent_thread_id

        # Root first, ending with the requested session.
        return tuple(reversed(chain))

    @staticmethod
    async def read(request: NativeHelperRequest, config: OpencodeThreadConfig, errors: NativeErrorFactory) -> NativeThreadResult:
        # Export the session whole; an unknown id is opencode's own
        # Session not found (spec EC-32).
        outcome = await OpencodeHelperRun._child(request, config, errors, command=(native_threads.OPENCODE_EXPORT_COMMAND,), operands=(request.thread_id or "",))
        return OpencodeHelperWire.document(outcome, request, errors)

    @staticmethod
    async def delete(request: NativeHelperRequest, config: OpencodeThreadConfig, errors: NativeErrorFactory) -> None:
        # Delete the session through opencode; an exit 0 without the
        # not-found text is the vendor's success (spec INV-11).
        outcome = await OpencodeHelperRun._child(request, config, errors, command=(native_threads.OPENCODE_SESSION_COMMAND, native_threads.OPENCODE_DELETE_COMMAND), operands=(request.thread_id or "",))
        OpencodeHelperWire.deleted(outcome, request, errors)

    @staticmethod
    async def _child(request: NativeHelperRequest, config: OpencodeThreadConfig, errors: NativeErrorFactory, *, command: tuple[str, ...], options: tuple[CliOption, ...] = (), operands: tuple[str, ...] = ()) -> CliOutcome:
        # @intent opencode-helper-child-is-keyless-in-the-workspace
        # One opencode child: found as a run finds it, started with no
        # key variable, self-update off, the workspace as its working
        # folder and PWD (spec D-22), and the fixed control bounds.
        launcher = NativeLauncher.resolve(config.opencode_command, program=native_threads.OPENCODE_PROGRAM, fallback=None, errors=errors, request=request)
        workspace = Path(request.workspace)
        invocation = CliInvocation(
            argv=CliArgv.build(launcher, command=command, options=options, style=CliOptionStyle.JOINED, operands=operands),
            env_overlay={
                NativeEnvironmentVariable.OPENCODE_DISABLE_AUTOUPDATE.value: native_threads.NATIVE_ENABLED_SWITCH,
                NativeEnvironmentVariable.PWD.value: str(workspace),
            },
            timeout_seconds=native_threads.NATIVE_CONTROL_TIMEOUT_SECONDS,
            max_output_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES,
            cwd=workspace,
            env_remove=native_threads.NATIVE_HELPER_REMOVED_VARIABLES,
        )
        outcome = await CliRunner().run(invocation)

        # A program the OS would not start is reported with its path.
        if outcome.launch_failure is not None:
            program, *_arguments = launcher
            raise errors.from_launch_failure(outcome.launch_failure, program, request=request)
        return outcome

    @staticmethod
    def _query(thread_id: str) -> str:
        # The constant session query with one id that passed
        # NATIVE_THREAD_ID_PATTERN: no quote, space or semicolon can
        # reach the SQL (spec INV-9, T-9).
        return native_threads.OPENCODE_SESSION_QUERY.format(thread_id=thread_id)


__all__ = ["OpencodeHelperRun", "OpencodeThreadHelpers"]
