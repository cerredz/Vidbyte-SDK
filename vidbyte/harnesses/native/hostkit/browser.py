"""FILE: vidbyte/harnesses/native/hostkit/browser.py

PURPOSE: Defines the shared flow of every browser function: NativeBrowserRun.execute, the one main function that registers the keys, resolves the tool strings, lets the harness refuse what it cannot mount, prepares Node, Chrome, the tool cache and the per-call folder, runs the harness, reads its tool calls, checks that the mounted tools were used, and reaps the browser and collects the artifacts, or discards everything on a failure; NativeBrowserHarness, the seam each harness implements; BrowserRuntimes (Node and Chrome checks), BrowserToolCache (one pinned install per tool) and NativeBrowserTools (prepare, write_file, require, complete and discard).
ROLE IN CODEBASE: The browser functions in vidbyte/harnesses/native/grok/browser.py, opencode/browser.py and muse/browser.py build the request records and call NativeBrowserRun.execute with their own NativeBrowserHarness; Grok's seam writes its agent file through NativeBrowserTools.write_file, and Muse's synchronous _prepare_config writes settings.json through NativeBrowserTools.backend. Exported from the hostkit package for those modules only.
ARCHITECTURE NOTE: Every layer of spec section 5 runs inside execute, so no harness can skip one. Validation (the two records, BrowserToolRegistry.select, the seam's check) happens before any process starts or file is written; after prepare, any failure or cancellation first runs discard, shielded from a further cancel, then propagates. The keys are registered with the error factory before the first step that can make error text. Every child starts through CliRunner with an argv tuple; every file and folder step runs through asyncio.to_thread (lint S052); files are written only through backend, the reviewed LocalFileSystemBackend (spec D-25). BROWSER_CHROME_PATHS, BROWSER_TOOL_INSTALL_TIMEOUT_SECONDS and BROWSER_REAP_TIMEOUT_SECONDS are read through the constants module at call time. It imports hostkit siblings from their concrete modules, never from the hostkit package that imports this one (spec D-27). The module holds no literals of its own (spec INV-15).
FUNCTION INVENTORY: NativeBrowserRun.execute is the narrated main function. NativeBrowserHarness lists check, run, tool_calls and missing. BrowserRuntimes.node finds and checks Node; BrowserRuntimes.chrome searches the Chrome locations. BrowserToolCache.ensure returns a tool's cached entry, installing it first when needed; _install runs the bundled npm into a staging folder and checks its outcome; _staging makes a staging folder; _publish renames it into place. NativeBrowserTools.prepare builds the mount; write_file writes one per-call file; require raises tools_unavailable for missing servers; complete reaps, removes the profiles and returns the result; discard reaps and removes the whole per-call folder; _make_folder creates the per-call folder; _command builds one stdio server's command; _remove tries a few times to remove a folder until the call's cleanup deadline; _artifacts lists the saved files.
COMMON MODIFICATION PATTERNS: A new preflight step goes into prepare, before the per-call folder is made, and raises through the error factory. A new harness implements NativeBrowserHarness in its own browser.py; this file does not change.
WHAT NOT TO DO IN THIS FILE: 1. Do not put a key on argv, in a file or in os.environ; keys reach a server only through the harness's own channel. 2. Do not run a Windows batch file as node. 3. Do not repair a published cache folder that lacks its entry; name it. 4. Do not import the hostkit package or a harness subpackage here. 5. Do not let a failure after prepare skip discard.
KNOWN EDGE CASES: A selection with no stdio tool needs neither Node nor the cache, and one with no tool that drives Chrome needs no Chrome (spec INV-1). Two calls installing one tool at once each use their own staging folder; the first rename publishes and the loser keeps the published copy. A cancelled install removes its staging folder before CancelledError propagates. On Windows a killed browser can hold its profile lock for a moment, so a removal is tried up to BROWSER_REMOVE_ATTEMPTS times until one deadline, BROWSER_REAP_TIMEOUT_SECONDS after the reap starts, which the reap and every removal of the call share (spec INV-12); the first try always runs, and a folder that still cannot be removed is left behind. The per-call folder survives only a successful call that saved artifacts, and then without its profiles.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_browser_runtime.py, tests/features/harness_threads/test_harness_threads_browser_lifecycle.py
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import ClassVar, Protocol

from vidbyte.harnesses.native.hostkit.errors import NativeErrorFactory
from vidbyte.harnesses.native.hostkit.skills import NativeSkillFolders
from vidbyte.lib.constants import browser_tools, native_threads
from vidbyte.lib.dataclasses.browser_tools import (
    BrowserMount,
    BrowserServer,
    BrowserThreadResult,
    BrowserToolCalls,
    BrowserToolDefinition,
    BrowserToolRequest,
    BrowserToolSelection,
)
from vidbyte.lib.dataclasses.native_threads import NativeThreadRequest, NativeThreadRun
from vidbyte.lib.dataclasses.process import CliInvocation
from vidbyte.lib.enums.browser_tools import BrowserTool, BrowserToolTransport
from vidbyte.lib.enums.native_threads import NativeThreadProblem
from vidbyte.lib.process.reaper import ProcessReaper
from vidbyte.lib.process.runner import CliRunner
from vidbyte.lib.registries.browser_tools import BrowserToolRegistry
from vidbyte.lib.tools.filesystem.backends.local import LocalFileSystemBackend


class NativeBrowserHarness(Protocol):
    """The per-harness seam NativeBrowserRun drives: refuse what the harness cannot mount, run it mounted, read its calls and name the servers it never used."""

    def check(self, selections: tuple[BrowserToolSelection, ...], request: NativeThreadRequest, errors: NativeErrorFactory) -> None:
        """Raise browser.mount_unsupported for a selection this harness cannot mount, before any I/O."""

    async def run(self, request: NativeThreadRequest, mount: BrowserMount, errors: NativeErrorFactory) -> NativeThreadRun:
        """Run the harness once with the mount and return its result and CLI outcome."""

    def tool_calls(self, run: NativeThreadRun, mount: BrowserMount) -> BrowserToolCalls:
        """Read the vendor's calls to the mounted tools from the run's output."""

    def missing(self, run: NativeThreadRun, mount: BrowserMount, calls: BrowserToolCalls) -> tuple[BrowserTool, ...]:
        """Name the mounted tools the output shows no evidence of; empty when the harness proves it otherwise."""


class NativeBrowserRun:
    """The one shared flow of a browser function call, from the checked request to the BrowserThreadResult."""

    @staticmethod
    async def execute(request: NativeThreadRequest, tools: BrowserToolRequest, harness: NativeBrowserHarness, errors: NativeErrorFactory) -> BrowserThreadResult:
        """Run one browser call through every layer and return its result, or raise one NativeThreadError."""
        # @intent browser-keys-registered-before-any-error-text
        # The harness key and every tool key are scrubbed from all
        # error text from here on, before any step that can fail with a
        # message (spec KD-6, INV-4).
        errors.register_secret(request.api_key)
        for key in tools.tool_keys.values():
            errors.register_secret(key)

        # Resolve each tool string into its pinned row, the tools it
        # allows and denies, and its key.
        selections = BrowserToolRegistry.select(tools)

        # The harness refuses what it cannot carry safely, still before
        # any process starts or any file is written.
        harness.check(selections, request, errors)

        # Check Node and Chrome, install what the cache lacks, and make
        # this call's own folder for profiles and artifacts.
        mount = await NativeBrowserTools.prepare(selections, request, errors)

        # @intent browser-call-cleans-up-however-it-ends
        # From here on a failure or a cancel first reaps the browser
        # and removes the per-call folder, shielded so a second cancel
        # cannot stop the cleanup half-way, then propagates.
        try:
            # Run the harness with the tools mounted; the vendor CLI is
            # the MCP client.
            run = await harness.run(request, mount, errors)

            # Read the vendor's own calls to the mounted tools.
            calls = harness.tool_calls(run, mount)

            # A mounted server the output shows no sign of fails the
            # call, with the thread id so the caller can continue it.
            NativeBrowserTools.require(harness.missing(run, mount, calls), run, mount, request, errors)

            # Reap the browser, keep the artifacts, drop the profiles.
            return await NativeBrowserTools.complete(mount, run, calls)
        except BaseException:
            cleanup = asyncio.ensure_future(NativeBrowserTools.discard(mount))
            await asyncio.shield(cleanup)
            raise


class BrowserRuntimes:
    """The programs the selected tools need: Node for a stdio tool and Chrome stable for a tool that drives Chrome."""

    @staticmethod
    async def node(request: NativeThreadRequest, errors: NativeErrorFactory) -> str:
        # @intent browser-node-is-a-real-program-at-the-floor
        # node is found the way CliRunner launches it, never in the
        # current folder; a Windows batch file is refused unrun, as the
        # harness launchers refuse theirs; and its version must reach
        # the release the pinned tools were verified on (spec D-6).
        minimum = browser_tools.BROWSER_VERSION_SEPARATOR.join(str(part) for part in browser_tools.BROWSER_NODE_MIN_VERSION)
        program = CliRunner.find_program(browser_tools.BROWSER_NODE_PROGRAM)
        if program is None:
            raise errors.failure(NativeThreadProblem.RUNTIME_MISSING, request=request, searched=browser_tools.BROWSER_NODE_MISSING_DETAIL.format(minimum=minimum))
        name = program.rstrip(native_threads.NATIVE_WINDOWS_DROPPED_TAIL).casefold()
        if sys.platform == native_threads.NATIVE_WINDOWS_PLATFORM and name.endswith(native_threads.NATIVE_BATCH_SUFFIXES):
            raise errors.failure(NativeThreadProblem.RUNTIME_MISSING, request=request, searched=browser_tools.BROWSER_NODE_BATCH_DETAIL.format(program=program))
        invocation = CliInvocation(argv=(program, browser_tools.BROWSER_NODE_VERSION_OPTION), env_overlay={}, timeout_seconds=native_threads.NATIVE_CONTROL_TIMEOUT_SECONDS, max_output_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES)
        outcome = await CliRunner().run(invocation)
        match = re.search(browser_tools.BROWSER_NODE_VERSION_PATTERN, outcome.stdout) if outcome.exit_code == 0 else None
        if match is None:
            raise errors.failure(NativeThreadProblem.RUNTIME_MISSING, request=request, searched=browser_tools.BROWSER_NODE_UNREADABLE_DETAIL.format(program=program))
        if tuple(int(part) for part in match.groups()) < browser_tools.BROWSER_NODE_MIN_VERSION:
            found = browser_tools.BROWSER_VERSION_SEPARATOR.join(match.groups())
            raise errors.failure(NativeThreadProblem.RUNTIME_MISSING, request=request, searched=browser_tools.BROWSER_NODE_TOO_OLD_DETAIL.format(program=program, found=found, minimum=minimum))
        return program

    @staticmethod
    async def chrome(request: NativeThreadRequest, errors: NativeErrorFactory) -> None:
        # Each location with its environment variables filled in, in
        # order; the first that is a file is Chrome. The tools find
        # Chrome themselves, so only its presence is checked.
        locations = [os.path.expandvars(location) for location in browser_tools.BROWSER_CHROME_PATHS]
        for location in locations:
            if await asyncio.to_thread(os.path.isfile, location):
                return
        raise errors.failure(NativeThreadProblem.RUNTIME_MISSING, request=request, searched=browser_tools.BROWSER_CHROME_MISSING_DETAIL.format(locations=errors.listing(locations)))


class BrowserToolCache:
    """The shared tool cache under ~/.vidbyte/tools: one pinned install per tool, published by rename."""

    @staticmethod
    async def ensure(definition: BrowserToolDefinition, node: str, request: NativeThreadRequest, errors: NativeErrorFactory) -> Path:
        # @intent browser-cache-installs-pinned-and-publishes-atomically
        # A tool is installed once, at its pinned version, into its own
        # staging folder, and published by one rename, so a reader sees
        # a whole install or none; a published folder without its entry
        # is named for the caller to delete, never repaired (spec D-5).
        try:
            root = Path.home().joinpath(*browser_tools.BROWSER_TOOL_CACHE_PARTS)
        except RuntimeError as exc:
            raise errors.failure(NativeThreadProblem.TOOL_INSTALL_FAILED, request=request, searched=browser_tools.BROWSER_HOME_UNKNOWN_DETAIL.format(error_type=type(exc).__name__)) from exc
        published = root / browser_tools.BROWSER_TOOL_FOLDER_TEMPLATE.format(tool=definition.tool.value, version=definition.version)
        entry = published.joinpath(*definition.entry)
        if await asyncio.to_thread(entry.is_file):
            return entry
        if await asyncio.to_thread(published.exists):
            raise errors.failure(NativeThreadProblem.TOOL_INSTALL_FAILED, request=request, searched=browser_tools.BROWSER_FOLDER_BROKEN_DETAIL.format(folder=published))

        # npm is the one bundled with this node: beside node.exe on
        # Windows, under ../lib beside bin/node on POSIX.
        package = browser_tools.BROWSER_PACKAGE_VERSION_TEMPLATE.format(package=definition.package, version=definition.version)
        node_folder = Path(node).parent
        npm_cli = node_folder.joinpath(*browser_tools.BROWSER_NPM_CLI_WINDOWS_PARTS) if sys.platform == native_threads.NATIVE_WINDOWS_PLATFORM else node_folder.parent.joinpath(*browser_tools.BROWSER_NPM_CLI_POSIX_PARTS)
        if not await asyncio.to_thread(npm_cli.is_file):
            raise errors.failure(NativeThreadProblem.TOOL_INSTALL_FAILED, request=request, searched=browser_tools.BROWSER_NPM_MISSING_DETAIL.format(path=npm_cli, package=package))

        # Install into a fresh staging folder; it is removed however the
        # install ends, a cancel included.
        staging_root = root / browser_tools.BROWSER_STAGING_FOLDER
        try:
            staging = await asyncio.to_thread(BrowserToolCache._staging, staging_root)
        except OSError as exc:
            raise errors.failure(NativeThreadProblem.TOOL_INSTALL_FAILED, request=request, searched=browser_tools.BROWSER_CACHE_FOLDER_DETAIL.format(folder=staging_root, error_type=type(exc).__name__)) from exc
        try:
            await BrowserToolCache._install(definition, (node, str(npm_cli), *browser_tools.BROWSER_NPM_INSTALL_ARGUMENTS, str(staging), package), package, staging, request, errors)

            # Publish by rename; a concurrent install that published
            # first wins, and its copy is used.
            try:
                await asyncio.to_thread(BrowserToolCache._publish, staging, published, entry)
            except OSError as exc:
                raise errors.failure(NativeThreadProblem.TOOL_INSTALL_FAILED, request=request, searched=browser_tools.BROWSER_CACHE_FOLDER_DETAIL.format(folder=published, error_type=type(exc).__name__)) from exc
            return entry
        finally:
            with contextlib.suppress(OSError):
                await asyncio.to_thread(NativeSkillFolders.remove, staging)

    @staticmethod
    async def _install(definition: BrowserToolDefinition, argv: tuple[str, ...], package: str, staging: Path, request: NativeThreadRequest, errors: NativeErrorFactory) -> None:
        # The bundled npm installs the pinned package into the staging
        # folder; a start failure, a timeout, a non-zero exit or a
        # missing entry each name the package and fail the install.
        invocation = CliInvocation(
            argv=argv,
            env_overlay={},
            timeout_seconds=browser_tools.BROWSER_TOOL_INSTALL_TIMEOUT_SECONDS,
            max_output_bytes=native_threads.NATIVE_PROCESS_MAX_OUTPUT_BYTES,
        )
        outcome = await CliRunner().run(invocation)
        if outcome.launch_failure is not None:
            raise errors.failure(NativeThreadProblem.TOOL_INSTALL_FAILED, request=request, searched=browser_tools.BROWSER_INSTALL_LAUNCH_DETAIL.format(package=package, kind=outcome.launch_failure.value))
        if outcome.timed_out:
            raise errors.failure(NativeThreadProblem.TOOL_INSTALL_FAILED, request=request, searched=browser_tools.BROWSER_INSTALL_TIMEOUT_DETAIL.format(package=package, seconds=invocation.timeout_seconds))
        if outcome.exit_code != native_threads.NATIVE_SUCCESS_EXIT_CODE:
            raise errors.failure(NativeThreadProblem.TOOL_INSTALL_FAILED, request=request, outcome=outcome, vendor_text=outcome.stderr, searched=browser_tools.BROWSER_INSTALL_FAILED_DETAIL.format(package=package))
        if not await asyncio.to_thread(staging.joinpath(*definition.entry).is_file):
            raise errors.failure(NativeThreadProblem.TOOL_INSTALL_FAILED, request=request, searched=browser_tools.BROWSER_INSTALL_NO_ENTRY_DETAIL.format(package=package))

    @staticmethod
    def _staging(staging_root: Path) -> Path:
        # A new, uniquely named staging folder under the cache.
        staging_root.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(dir=staging_root))

    @staticmethod
    def _publish(staging: Path, published: Path, entry: Path) -> None:
        # One rename publishes the whole install; losing the race to a
        # copy that already holds the entry is not a failure.
        try:
            os.rename(staging, published)
        except OSError:
            if not entry.is_file():
                raise


class NativeBrowserTools:
    """The per-call side of a browser call: the mount, its files, the required check, and the cleanup that reaps and removes."""

    # The reviewed writer for every per-call file (spec D-25).
    backend: ClassVar[LocalFileSystemBackend] = LocalFileSystemBackend()

    @staticmethod
    async def prepare(selections: tuple[BrowserToolSelection, ...], request: NativeThreadRequest, errors: NativeErrorFactory) -> BrowserMount:
        # Node only when a stdio tool is selected, Chrome only when a
        # selected tool drives it (spec INV-1).
        stdio = [selection for selection in selections if selection.definition.transport is BrowserToolTransport.STDIO]
        node = await BrowserRuntimes.node(request, errors) if stdio else ""
        if any(selection.definition.needs_chrome for selection in selections):
            await BrowserRuntimes.chrome(request, errors)

        # Every stdio tool's entry, installed first when the cache lacks
        # it.
        entries = {selection.definition.tool: await BrowserToolCache.ensure(selection.definition, node, request, errors) for selection in stdio}

        # @intent browser-call-folder-outside-the-workspace
        # The call's own folder lives in the temp folder, never in the
        # workspace; its path is on every browser's command line, which
        # is how the reaper finds them later (spec D-3, D-12).
        try:
            folder = await asyncio.to_thread(NativeBrowserTools._make_folder, selections)
        except OSError as exc:
            detail = browser_tools.BROWSER_CALL_FOLDER_DETAIL.format(folder=tempfile.gettempdir(), error_type=type(exc).__name__)
            raise errors.failure(NativeThreadProblem.LAUNCH_FAILED, request=request, searched=detail) from exc
        artifacts = folder / browser_tools.BROWSER_ARTIFACTS_FOLDER
        servers = tuple(BrowserServer(selection=selection, command=NativeBrowserTools._command(selection, node, entries.get(selection.definition.tool), folder, artifacts)) for selection in selections)
        return BrowserMount(servers=servers, folder=folder, artifacts=artifacts)

    @staticmethod
    async def write_file(path: Path, text: str) -> None:
        # One per-call file, written whole, off the event loop.
        await asyncio.to_thread(NativeBrowserTools.backend.write_text, path, text, encoding=browser_tools.BROWSER_FILE_ENCODING, create_parents=True, atomic=True)

    @staticmethod
    def require(missing: tuple[BrowserTool, ...], run: NativeThreadRun, mount: BrowserMount, request: NativeThreadRequest, errors: NativeErrorFactory) -> None:
        # @intent browser-required-servers-show-evidence
        # A mounted server the vendor's output never shows connected or
        # used fails the call, naming those servers, with the thread id
        # and the answer, so nothing that silently lacked its tools
        # passes as a success (spec FR-14).
        if missing:
            servers = errors.listing(tool.value for tool in missing)
            raise errors.failure(NativeThreadProblem.TOOLS_UNAVAILABLE, request=request, thread_id=run.result.thread_id, vendor_text=run.result.text, searched=browser_tools.BROWSER_TOOLS_UNAVAILABLE_DETAIL.format(servers=servers))

    @staticmethod
    async def complete(mount: BrowserMount, run: NativeThreadRun, calls: BrowserToolCalls) -> BrowserThreadResult:
        # End the browsers the servers left behind, then remove their
        # profiles; the reap and every removal share one deadline.
        deadline = asyncio.get_running_loop().time() + browser_tools.BROWSER_REAP_TIMEOUT_SECONDS
        await ProcessReaper.reap(str(mount.folder), timeout_seconds=browser_tools.BROWSER_REAP_TIMEOUT_SECONDS)
        await NativeBrowserTools._remove(mount.folder / browser_tools.BROWSER_PROFILES_FOLDER, deadline)

        # Keep the folder only when the tools saved files in it.
        files = await asyncio.to_thread(NativeBrowserTools._artifacts, mount.artifacts)
        if not files:
            await NativeBrowserTools._remove(mount.folder, deadline)
        kept = tuple(files[: browser_tools.BROWSER_ARTIFACTS_MAX_ITEMS])
        result = run.result
        return BrowserThreadResult(
            harness=result.harness,
            thread_id=result.thread_id,
            text=result.text,
            text_truncated=result.text_truncated,
            tool_calls=calls.calls,
            tool_calls_truncated=calls.truncated,
            artifacts=kept,
            artifacts_truncated=len(files) > len(kept),
        )

    @staticmethod
    async def discard(mount: BrowserMount) -> None:
        # A failed or cancelled call keeps nothing: reap the browsers,
        # then remove the whole per-call folder, artifacts included,
        # both within one deadline.
        deadline = asyncio.get_running_loop().time() + browser_tools.BROWSER_REAP_TIMEOUT_SECONDS
        await ProcessReaper.reap(str(mount.folder), timeout_seconds=browser_tools.BROWSER_REAP_TIMEOUT_SECONDS)
        await NativeBrowserTools._remove(mount.folder, deadline)

    @staticmethod
    def _make_folder(selections: tuple[BrowserToolSelection, ...]) -> Path:
        # The per-call folder with its artifacts folder and one profile
        # folder per tool that takes one; a half-made folder is removed.
        folder = Path(tempfile.mkdtemp(prefix=browser_tools.BROWSER_CALL_FOLDER_PREFIX))
        try:
            (folder / browser_tools.BROWSER_ARTIFACTS_FOLDER).mkdir()
            for selection in selections:
                if selection.definition.profile_option is not None:
                    folder.joinpath(browser_tools.BROWSER_PROFILES_FOLDER, selection.definition.tool.value).mkdir(parents=True)
        except OSError:
            NativeSkillFolders.remove(folder)
            raise
        return folder

    @staticmethod
    def _command(selection: BrowserToolSelection, node: str, entry: Path | None, folder: Path, artifacts: Path) -> tuple[str, ...]:
        # A remote server has no command. A stdio server is node with
        # the absolute entry, its fixed arguments, its own profile in
        # the per-call folder, the artifacts folder and the extra
        # capability groups, each option as one --flag=value element.
        definition = selection.definition
        if entry is None:
            return ()
        options = []
        if definition.profile_option is not None:
            options.append(browser_tools.BROWSER_OPTION_TEMPLATE.format(option=definition.profile_option, value=folder.joinpath(browser_tools.BROWSER_PROFILES_FOLDER, definition.tool.value)))
        if definition.output_option is not None:
            options.append(browser_tools.BROWSER_OPTION_TEMPLATE.format(option=definition.output_option, value=artifacts))
        if definition.caps_option is not None and selection.server_capabilities:
            options.append(browser_tools.BROWSER_OPTION_TEMPLATE.format(option=definition.caps_option, value=browser_tools.BROWSER_CAPABILITY_LIST_SEPARATOR.join(selection.server_capabilities)))
        return (node, str(entry), *definition.arguments, *options)

    @staticmethod
    async def _remove(folder: Path, deadline: float) -> None:
        # @intent browser-removal-retries-until-the-cleanup-deadline
        # A removal right after a kill can race the operating system
        # releasing the browser's files, so it is tried a few times,
        # a pause apart, until the deadline the reap also counts
        # against (spec INV-12). The first try always runs; a folder
        # that still stays is left behind, and no call reuses it.
        loop = asyncio.get_running_loop()
        for _attempt in range(browser_tools.BROWSER_REMOVE_ATTEMPTS):
            with contextlib.suppress(OSError):
                await asyncio.to_thread(NativeSkillFolders.remove, folder)
            if not await asyncio.to_thread(folder.exists) or loop.time() >= deadline:
                return
            await asyncio.sleep(browser_tools.BROWSER_REMOVE_PAUSE_SECONDS)

    @staticmethod
    def _artifacts(artifacts: Path) -> list[Path]:
        # Every file the tools saved, absolute and sorted; a missing
        # folder holds none.
        return sorted(Path(root, name) for root, _folders, names in os.walk(artifacts) for name in names)


__all__ = ["BrowserRuntimes", "BrowserToolCache", "NativeBrowserHarness", "NativeBrowserRun", "NativeBrowserTools"]
