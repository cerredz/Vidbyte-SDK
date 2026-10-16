"""FILE: vidbyte/harnesses/native/grok/helpers.py

PURPOSE: Defines the eight public Grok thread helpers (GrokThreadHelpers: list_grok_threads, list_recent_grok_threads, list_grok_threads_since, get_grok_thread, read_grok_thread, get_grok_thread_lineage, search_grok_threads, delete_grok_thread) and the flows behind them (GrokHelperRun): list, search, get and lineage read the summary.json files of a Grok store; read runs a keyless `grok export`; delete runs a keyless `grok sessions delete` and then checks that the session folder is gone.
ROLE IN CODEBASE: The helpers are bound as module names in vidbyte/harnesses/native/grok/__init__.py and re-exported from vidbyte.harnesses.native. GrokHelperRun uses GrokHome and GrokStore (grok/store.py) for the store, GrokHelperWire (grok/wire.py) for the children's output, NativeThreadListing, NativeLauncher and NativeErrorFactory from hostkit, and CliArgv and CliRunner from vidbyte.lib.process. GrokCommandRun (grok/commands.py) calls GrokHelperRun.export for the code-review evidence.
ARCHITECTURE NOTE: No helper takes a key or a model (spec INV-2). The SDK scope reads the private home the runs of the same workspace use, the USER scope the user's own ~/.grok (spec INV-13, D-21); a read path only names a home and never creates one (spec D-11). Store reads run in asyncio.to_thread (spec INV-18). The export and delete children run with GROK_HOME set to the scope's home, self-update off, every key variable removed from the inherited environment, the workspace as their working folder, and the fixed control timeout and output cap, whatever config.timeout_seconds says (spec INV-16, D-14); the timeout is read at call time. No flow calls another flow (spec R-1): each one calls the store, the wire, the listing rules and export directly. The module holds no literals of its own (spec INV-15).
FUNCTION INVENTORY: GrokThreadHelpers holds the eight public helpers and _call, the one guarded try they share. GrokHelperRun.list, search, get, lineage, read and delete are the narrated flows; export runs the keyless `grok export` child, shared with GrokCommandRun; _found turns a store miss into thread_not_found naming the scope and the home searched.
COMMON MODIFICATION PATTERNS: A new helper is one NativeThreadOperation member, its rows in the operation tables of vidbyte/lib/constants/native_threads.py, one public method here that calls _call with its flow, and one flow in GrokHelperRun.
WHAT NOT TO DO IN THIS FILE: 1. Do not create a Grok home on a read path. 2. Do not give a helper child a key, and do not let one inherit the caller's key variables. 3. Do not let one flow call another flow. 4. Do not start a child for an id the store lookup did not find (spec D-16, INV-11). 5. Do not remove a session folder from the SDK; only grok deletes its threads, and the SDK only checks that the folder is gone.
KNOWN EDGE CASES: A thread removed between the store lookup and `grok export` is thread_not_found from grok's own text (spec EC-21). A delete that exits 0 but leaves the folder is run_failed naming the folder (spec EC-23). A lineage stops at a parent the store no longer has, and raises on a cycle or past NATIVE_LINEAGE_MAX_DEPTH (spec EC-25 to EC-27). A search query is matched in the SDK and never reaches argv (spec INV-9). Two copies of one id under two groups of the USER scope list once, as the newer (spec EC-17).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_grok_helpers.py, tests/features/harness_threads/test_harness_threads_listing_properties.py, tests/features/harness_threads/test_harness_threads_helper_arguments.py, tests/features/harness_threads/test_harness_threads_helper_bounds.py, tests/features/harness_threads/test_harness_threads_helper_credentials.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from vidbyte.harnesses.native.grok.store import GrokHome, GrokStore
from vidbyte.harnesses.native.grok.wire import GrokHelperWire
from vidbyte.harnesses.native.hostkit import NativeErrorFactory, NativeLauncher, NativeThreadListing
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.native_threads import (
    GrokThreadConfig,
    GrokThreadFile,
    NativeHelperRequest,
    NativeThreadRequest,
    NativeThreadResult,
    NativeThreadSummary,
)
from vidbyte.lib.dataclasses.process import CliInvocation
from vidbyte.lib.dataclasses.validation import RecordFieldConverter
from vidbyte.lib.enums.native_threads import (
    GrokThreadScope,
    NativeHarness,
    NativeThreadOperation,
    NativeThreadProblem,
)
from vidbyte.lib.enums.process import CliOptionStyle
from vidbyte.lib.errors import ConfigurationError, NativeThreadError
from vidbyte.lib.process import CliArgv, CliRunner


class GrokThreadHelpers:
    """The public Grok thread helpers: list, search, get, read, follow and delete the threads of one Grok store, with no key."""

    @staticmethod
    async def list_grok_threads(workspace: str | Path, *, since: timedelta | None = None, limit: int = native_threads.NATIVE_LIST_DEFAULT_LIMIT, scope: GrokThreadScope = GrokThreadScope.SDK) -> tuple[NativeThreadSummary, ...]:
        """List the Grok threads of workspace in scope, newest first, at most limit, updated within since when given."""
        return await GrokThreadHelpers._call(NativeThreadOperation.LIST_GROK_THREADS, GrokHelperRun.list, workspace=workspace, since=since, limit=limit, scope=scope)

    @staticmethod
    async def list_recent_grok_threads(workspace: str | Path, *, limit: int = native_threads.NATIVE_RECENT_DEFAULT_LIMIT, scope: GrokThreadScope = GrokThreadScope.SDK) -> tuple[NativeThreadSummary, ...]:
        """List the limit most recently updated Grok threads of workspace in scope."""
        return await GrokThreadHelpers._call(NativeThreadOperation.LIST_RECENT_GROK_THREADS, GrokHelperRun.list, workspace=workspace, limit=limit, scope=scope)

    @staticmethod
    async def list_grok_threads_since(workspace: str | Path, since: timedelta, *, limit: int = native_threads.NATIVE_LIST_DEFAULT_LIMIT, scope: GrokThreadScope = GrokThreadScope.SDK) -> tuple[NativeThreadSummary, ...]:
        """List the Grok threads of workspace in scope updated within since, newest first, at most limit."""
        return await GrokThreadHelpers._call(NativeThreadOperation.LIST_GROK_THREADS_SINCE, GrokHelperRun.list, workspace=workspace, since=since, limit=limit, scope=scope)

    @staticmethod
    async def get_grok_thread(thread_id: str, workspace: str | Path, *, scope: GrokThreadScope = GrokThreadScope.SDK) -> NativeThreadSummary:
        """Return the summary of the Grok thread thread_id in scope."""
        return await GrokThreadHelpers._call(NativeThreadOperation.GET_GROK_THREAD, GrokHelperRun.get, workspace=workspace, thread_id=thread_id, scope=scope)

    @staticmethod
    async def read_grok_thread(thread_id: str, workspace: str | Path, *, scope: GrokThreadScope = GrokThreadScope.SDK, config: GrokThreadConfig | None = None) -> NativeThreadResult:
        """Return the whole transcript of the Grok thread thread_id, as `grok export` prints it."""
        return await GrokThreadHelpers._call(NativeThreadOperation.READ_GROK_THREAD, GrokHelperRun.read, workspace=workspace, thread_id=thread_id, scope=scope, config=config)

    @staticmethod
    async def get_grok_thread_lineage(thread_id: str, workspace: str | Path, *, scope: GrokThreadScope = GrokThreadScope.SDK) -> tuple[NativeThreadSummary, ...]:
        """Return the chain of threads thread_id was forked from, root first and ending with thread_id."""
        return await GrokThreadHelpers._call(NativeThreadOperation.GET_GROK_THREAD_LINEAGE, GrokHelperRun.lineage, workspace=workspace, thread_id=thread_id, scope=scope)

    @staticmethod
    async def search_grok_threads(workspace: str | Path, query: str, *, limit: int = native_threads.NATIVE_LIST_DEFAULT_LIMIT, scope: GrokThreadScope = GrokThreadScope.SDK) -> tuple[NativeThreadSummary, ...]:
        """List the Grok threads in scope whose title or summaries hold query, case-insensitively, newest first."""
        return await GrokThreadHelpers._call(NativeThreadOperation.SEARCH_GROK_THREADS, GrokHelperRun.search, workspace=workspace, query=query, limit=limit, scope=scope)

    @staticmethod
    async def delete_grok_thread(thread_id: str, workspace: str | Path, *, scope: GrokThreadScope = GrokThreadScope.SDK, config: GrokThreadConfig | None = None) -> None:
        """Delete the Grok thread thread_id through `grok sessions delete`, and return once its folder is gone."""
        await GrokThreadHelpers._call(NativeThreadOperation.DELETE_GROK_THREAD, GrokHelperRun.delete, workspace=workspace, thread_id=thread_id, scope=scope, config=config)

    @staticmethod
    async def _call(
        operation: NativeThreadOperation,
        flow: Callable[[NativeHelperRequest, GrokThreadConfig, NativeErrorFactory], Awaitable[Any]],
        *,
        workspace: str | Path,
        thread_id: str | None = None,
        since: timedelta | None = None,
        limit: int | None = None,
        query: str | None = None,
        scope: GrokThreadScope,
        config: GrokThreadConfig | None = None,
    ) -> Any:
        # One guarded try per call: cancellation and the feature's own
        # errors pass through, a refused argument names the argument,
        # and anything else is a defect named only by its class. The
        # result is whatever the helper's flow returns.
        errors = NativeErrorFactory(NativeHarness.GROK, operation)
        request: NativeHelperRequest | None = None
        try:
            request = NativeHelperRequest(harness=NativeHarness.GROK, operation=operation, workspace=workspace, thread_id=thread_id, since=since, limit=limit, query=query, scope=scope)
            settings = GrokThreadConfig() if config is None else RecordFieldConverter.require_instance(config, native_threads.NATIVE_CONFIG_ARGUMENT, GrokThreadConfig)
            return await flow(request, settings, errors)
        except asyncio.CancelledError:
            raise
        except NativeThreadError:
            raise
        except ConfigurationError as exc:
            raise errors.from_configuration_error(exc, request) from exc
        except Exception as exc:
            raise errors.from_unexpected(exc, request) from exc


class GrokHelperRun:
    """The flows of the Grok thread helpers: the store reads, the export and delete children, and the checks around them."""

    @staticmethod
    async def list(request: NativeHelperRequest, config: GrokThreadConfig, errors: NativeErrorFactory) -> tuple[NativeThreadSummary, ...]:
        # Take the clock once, so the window has one edge for the whole
        # call (spec INV-7).
        cutoff = NativeThreadListing.cutoff(request.since, datetime.now(timezone.utc))

        # Name the store of the scope; a read path never creates it.
        home = GrokStore.home(request, errors)

        # Read every thread in scope strictly, off the event loop.
        files = await asyncio.to_thread(GrokStore.threads, home, request, errors)

        # Keep one entry per id, inside the window, newest first, at
        # most limit. The request checked the limit; `or` only tells
        # the type checker it is set.
        return NativeThreadListing.newest((found.summary for found in files), cutoff=cutoff, limit=request.limit or 0)

    @staticmethod
    async def search(request: NativeHelperRequest, config: GrokThreadConfig, errors: NativeErrorFactory) -> tuple[NativeThreadSummary, ...]:
        # Name the store of the scope and read every thread in it, as a
        # list does.
        home = GrokStore.home(request, errors)
        files = await asyncio.to_thread(GrokStore.threads, home, request, errors)

        # Keep the threads whose title, session summary or last-turn
        # summary holds the query literally, in any letter case; the
        # query never reaches a child (spec INV-9).
        query = request.query or ""
        matching = (found.summary for found in files if NativeThreadListing.matches(found.search_text, query))

        # Newest first, one entry per id, at most limit.
        return NativeThreadListing.newest(matching, cutoff=None, limit=request.limit or 0)

    @staticmethod
    async def get(request: NativeHelperRequest, config: GrokThreadConfig, errors: NativeErrorFactory) -> NativeThreadSummary:
        # Name the store of the scope and read only this id's
        # summary.json in it (spec D-27).
        home = GrokStore.home(request, errors)
        found = await asyncio.to_thread(GrokStore.thread, home, request, errors, thread_id=request.thread_id or "")

        # An id no group has is thread_not_found naming the scope.
        return GrokHelperRun._found(found, home, request, errors).summary

    @staticmethod
    async def lineage(request: NativeHelperRequest, config: GrokThreadConfig, errors: NativeErrorFactory) -> tuple[NativeThreadSummary, ...]:
        # Name the store of the scope and read the requested thread; an
        # unknown id is thread_not_found.
        home = GrokStore.home(request, errors)
        found = await asyncio.to_thread(GrokStore.thread, home, request, errors, thread_id=request.thread_id or "")
        chain = [GrokHelperRun._found(found, home, request, errors).summary]

        # Follow parent_session_id one file at a time. Each step is
        # checked first, so a cycle or a chain past the depth cap
        # raises instead of walking forever (spec INV-10).
        parent = chain[-1].parent_thread_id
        while parent is not None:
            NativeThreadListing.check_step(tuple(chain), parent, errors, request)
            step = await asyncio.to_thread(GrokStore.thread, home, request, errors, thread_id=parent)

            # A parent the store no longer has ends the chain; the head
            # then names the missing id (spec EC-25).
            if step is None:
                break
            chain.append(step.summary)
            parent = step.summary.parent_thread_id

        # Root first, ending with the requested thread.
        return tuple(reversed(chain))

    @staticmethod
    async def read(request: NativeHelperRequest, config: GrokThreadConfig, errors: NativeErrorFactory) -> NativeThreadResult:
        # Name the store of the scope and look the id up first, so an
        # unknown id starts no child (spec D-16).
        home = GrokStore.home(request, errors)
        found = await asyncio.to_thread(GrokStore.thread, home, request, errors, thread_id=request.thread_id or "")
        thread_id = GrokHelperRun._found(found, home, request, errors).summary.thread_id

        # Export the whole transcript through a keyless grok child.
        return await GrokHelperRun.export(home, request, config, errors, thread_id=thread_id)

    @staticmethod
    async def delete(request: NativeHelperRequest, config: GrokThreadConfig, errors: NativeErrorFactory) -> None:
        # Name the store of the scope and look the id up first, so no
        # delete starts for an id the store does not have (spec INV-11).
        home = GrokStore.home(request, errors)
        found = GrokHelperRun._found(await asyncio.to_thread(GrokStore.thread, home, request, errors, thread_id=request.thread_id or ""), home, request, errors)
        thread_id = found.summary.thread_id

        # Find grok: the caller's command, then PATH, then the copy the
        # Grok installer puts under the user's home folder.
        launcher = NativeLauncher.resolve(config.grok_command, program=native_threads.GROK_PROGRAM, fallback=GrokHome.fallback(), errors=errors, request=request)

        # Run `grok sessions delete <id>` once against the scope's home,
        # with no key, no standard input and the fixed control bounds.
        invocation = CliInvocation(
            argv=CliArgv.build(launcher, command=(native_threads.GROK_SESSIONS_COMMAND, native_threads.GROK_DELETE_COMMAND), style=CliOptionStyle.JOINED, operands=(thread_id,)),
            env_overlay=GrokHome.environment(home, None),
            timeout_seconds=native_threads.NATIVE_CONTROL_TIMEOUT_SECONDS,
            max_output_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES,
            cwd=Path(request.workspace),
            env_remove=native_threads.NATIVE_HELPER_REMOVED_VARIABLES,
        )
        outcome = await CliRunner().run(invocation)

        # A program the OS would not start is reported with its path.
        if outcome.launch_failure is not None:
            program, *_arguments = launcher
            raise errors.from_launch_failure(outcome.launch_failure, program, request=request, thread_id=thread_id)

        # Read grok's answer: a timeout, the cap, not found or a failed
        # exit each raise.
        GrokHelperWire.deleted(outcome, request, errors)

        # @intent grok-delete-is-checked-on-disk
        # grok can exit 0 and keep the thread (it asked to confirm, or
        # answered for another home), so the session folder must be
        # gone before the delete counts (spec INV-11, EC-23).
        folder = found.path.parent
        if await asyncio.to_thread(folder.exists):
            raise errors.failure(NativeThreadProblem.RUN_FAILED, request=request, thread_id=thread_id, searched=native_threads.GROK_DELETE_LEFT_DETAIL.format(folder=folder))

    @staticmethod
    async def export(home: Path, request: NativeHelperRequest | NativeThreadRequest, config: GrokThreadConfig, errors: NativeErrorFactory, *, thread_id: str) -> NativeThreadResult:
        # The keyless `grok export <id>` child, which read_grok_thread
        # and the code-review evidence share (spec D-28). It builds its
        # own invocation and calls no other flow (spec R-22).
        launcher = NativeLauncher.resolve(config.grok_command, program=native_threads.GROK_PROGRAM, fallback=GrokHome.fallback(), errors=errors, request=request)
        invocation = CliInvocation(
            argv=CliArgv.build(launcher, command=(native_threads.GROK_EXPORT_COMMAND,), style=CliOptionStyle.JOINED, operands=(thread_id,)),
            env_overlay=GrokHome.environment(home, None),
            timeout_seconds=native_threads.NATIVE_CONTROL_TIMEOUT_SECONDS,
            max_output_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES,
            cwd=Path(request.workspace),
            env_remove=native_threads.NATIVE_HELPER_REMOVED_VARIABLES,
        )
        outcome = await CliRunner().run(invocation)
        if outcome.launch_failure is not None:
            program, *_arguments = launcher
            raise errors.from_launch_failure(outcome.launch_failure, program, request=request, thread_id=thread_id)

        # The transcript is returned whole, or the call raises (spec
        # INV-21).
        return GrokHelperWire.document(outcome, request, errors, thread_id=thread_id)

    @staticmethod
    def _found(found: GrokThreadFile | None, home: Path, request: NativeHelperRequest, errors: NativeErrorFactory) -> GrokThreadFile:
        # A store miss is thread_not_found naming the scope and the home
        # searched, so an id kept only in the other scope is easy to
        # tell apart (spec EC-20).
        if found is None:
            detail = native_threads.GROK_SCOPE_SEARCHED_DETAIL.format(scope=request.scope, home=home)
            raise errors.failure(NativeThreadProblem.THREAD_NOT_FOUND, request=request, searched=detail)
        return found


__all__ = ["GrokHelperRun", "GrokThreadHelpers"]
