"""FILE: vidbyte/harnesses/native/muse/browser.py

PURPOSE: Defines the three public Muse Code browser functions (MuseBrowserThreads: run_muse_with_browser, continue_muse_with_browser, fork_muse_with_browser), which run one Muse call with the caller's browser tools mounted and return a BrowserThreadResult, and MuseBrowserHarness, the Muse side of the shared browser flow.
ROLE IN CODEBASE: The functions are bound as module names in vidbyte/harnesses/native/muse/__init__.py and re-exported from vidbyte.harnesses.native. Each call hands NativeBrowserRun.execute (hostkit/browser.py) a MuseBrowserHarness, whose steps use MuseMounts (muse/mounts.py), MuseLauncher (muse/launcher.py), MuseThreadRun (muse/threads.py) and MuseExecOutput (muse/wire.py).
ARCHITECTURE NOTE: The functions take the plain Muse parameters with tools and tool_keys after model (spec INV-2) and share one guarded try, like the plain functions, so every failure is one NativeThreadError naming the browser function. The harness reuses the plain flow through MuseThreadRun.execute with a mount (D-3), which writes the settings into the per-call config folder and switches Muse's own web tools off. Muse treats every configured server as required and fails the run with its own reason when one cannot start, so that failure is the evidence check: a muse.run_failed whose vendor text carries the required-server marker becomes browser.tools_unavailable, and missing is always empty (D-11). Imports run browser -> threads, wire, mounts, launcher (D-27). The module holds no literals of its own (spec INV-15).
FUNCTION INVENTORY: MuseBrowserThreads.run_muse_with_browser, continue_muse_with_browser and fork_muse_with_browser are the public functions; MuseBrowserThreads._call is the one guarded try they share. MuseBrowserHarness.check refuses before any I/O what Muse cannot mount, run runs muse with the mount and names a required-server failure, tool_calls reads the calls on the mounted tools, and missing names nothing, because Muse itself fails a run whose server did not start.
COMMON MODIFICATION PATTERNS: A new mount rule goes in MuseMounts; a new reader rule in MuseExecOutput.tool_calls; the steps of a call change in NativeBrowserRun.execute, never here.
WHAT NOT TO DO IN THIS FILE: 1. Do not turn any other muse.run_failed into browser.tools_unavailable; only the required-server failure means the tools were unavailable. 2. Do not pass a key to a Muse server; MuseMounts.check refuses keyed tools before anything starts. 3. Do not import another harness's modules.
KNOWN EDGE CASES: In WSL mode, a Windows setup with wsl_distro and no muse_command, only the keyless remote tools mount, because the distro has no Node (spec AC-19). A continue or fork mounts only the tools of that call (EC-30).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_browser_mounts.py, tests/features/harness_threads/test_harness_threads_browser_lifecycle.py, tests/features/harness_threads/test_harness_threads_browser_contract.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path

from vidbyte.harnesses.native.hostkit import NativeBrowserRun, NativeErrorFactory
from vidbyte.harnesses.native.muse.launcher import MuseLauncher
from vidbyte.harnesses.native.muse.mounts import MuseMounts
from vidbyte.harnesses.native.muse.threads import MuseThreadRun
from vidbyte.harnesses.native.muse.wire import MuseExecOutput
from vidbyte.lib.constants import browser_tools, native_threads
from vidbyte.lib.dataclasses.browser_tools import (
    BrowserMount,
    BrowserThreadResult,
    BrowserToolCalls,
    BrowserToolRequest,
    BrowserToolSelection,
)
from vidbyte.lib.dataclasses.native_threads import (
    MuseThreadConfig,
    NativeThreadRequest,
    NativeThreadRun,
)
from vidbyte.lib.dataclasses.validation import RecordFieldConverter
from vidbyte.lib.enums.browser_tools import BrowserTool
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.enums.native_threads import (
    NativeHarness,
    NativeThreadOperation,
    NativeThreadProblem,
    NativeThreadVerb,
)
from vidbyte.lib.errors import ConfigurationError, NativeThreadError


class MuseBrowserThreads:
    """The public Muse Code browser functions: start, continue or fork one thread headless with the caller's browser tools mounted."""

    @staticmethod
    async def run_muse_with_browser(prompt: str, *, api_key: str, workspace: str | Path, model: str | None = None, tools: Sequence[str], tool_keys: Mapping[str, str] | None = None, skills: Sequence[str | Path] = (), config: MuseThreadConfig | None = None) -> BrowserThreadResult:
        """Start a new Muse Code thread in workspace with tools mounted, run prompt once with api_key, and return its id, answer, tool calls and artifacts."""
        return await MuseBrowserThreads._call(NativeThreadOperation.RUN_MUSE_WITH_BROWSER, NativeThreadVerb.RUN, None, prompt, api_key=api_key, workspace=workspace, model=model, tools=tools, tool_keys=tool_keys, skills=skills, config=config)

    @staticmethod
    async def continue_muse_with_browser(thread_id: str, prompt: str, *, api_key: str, workspace: str | Path, model: str | None = None, tools: Sequence[str], tool_keys: Mapping[str, str] | None = None, skills: Sequence[str | Path] = (), config: MuseThreadConfig | None = None) -> BrowserThreadResult:
        """Check that the Muse Code thread thread_id exists, then run prompt once more on it with tools mounted."""
        return await MuseBrowserThreads._call(NativeThreadOperation.CONTINUE_MUSE_WITH_BROWSER, NativeThreadVerb.CONTINUE, thread_id, prompt, api_key=api_key, workspace=workspace, model=model, tools=tools, tool_keys=tool_keys, skills=skills, config=config)

    @staticmethod
    async def fork_muse_with_browser(thread_id: str, prompt: str, *, api_key: str, workspace: str | Path, model: str | None = None, tools: Sequence[str], tool_keys: Mapping[str, str] | None = None, skills: Sequence[str | Path] = (), config: MuseThreadConfig | None = None) -> BrowserThreadResult:
        """Fork the Muse Code thread thread_id into a new thread, run prompt on the copy with tools mounted, and return the new id."""
        return await MuseBrowserThreads._call(NativeThreadOperation.FORK_MUSE_WITH_BROWSER, NativeThreadVerb.FORK, thread_id, prompt, api_key=api_key, workspace=workspace, model=model, tools=tools, tool_keys=tool_keys, skills=skills, config=config)

    @staticmethod
    async def _call(operation: NativeThreadOperation, verb: NativeThreadVerb, thread_id: str | None, prompt: str, *, api_key: str, workspace: str | Path, model: str | None, tools: Sequence[str], tool_keys: Mapping[str, str] | None, skills: Sequence[str | Path], config: MuseThreadConfig | None) -> BrowserThreadResult:
        # One guarded try per call: cancellation and the feature's own
        # errors pass through, a refused argument names the argument,
        # and anything else is a defect named only by its class. The
        # thread request comes first, so a refused tools argument still
        # names the workspace; no tool_keys is no keys.
        errors = NativeErrorFactory(NativeHarness.MUSE, operation)
        request: NativeThreadRequest | None = None
        try:
            request = NativeThreadRequest(harness=NativeHarness.MUSE, verb=verb, prompt=prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, thread_id=thread_id)
            browser = BrowserToolRequest(tools=tools, tool_keys={} if tool_keys is None else tool_keys)
            settings = MuseThreadConfig() if config is None else RecordFieldConverter.require_instance(config, native_threads.NATIVE_CONFIG_ARGUMENT, MuseThreadConfig)
            return await NativeBrowserRun.execute(request, browser, MuseBrowserHarness(settings), errors)
        except asyncio.CancelledError:
            raise
        except NativeThreadError:
            raise
        except ConfigurationError as exc:
            raise errors.from_configuration_error(exc, request) from exc
        except Exception as exc:
            raise errors.from_unexpected(exc, request) from exc


class MuseBrowserHarness:
    """The Muse Code side of a browser call: what it refuses, how it runs, and what its records show of the mounted tools."""

    def __init__(self, config: MuseThreadConfig) -> None:
        self._config = config

    def check(self, selections: tuple[BrowserToolSelection, ...], request: NativeThreadRequest, errors: NativeErrorFactory) -> None:
        # Keyed and narrowed tools, and stdio tools when WSL launches
        # muse, are refused before anything starts.
        MuseMounts.check(selections, request, errors, wsl_mode=MuseLauncher(self._config, errors).wsl_mode)

    async def run(self, request: NativeThreadRequest, mount: BrowserMount, errors: NativeErrorFactory) -> NativeThreadRun:
        # @intent muse-required-server-failure-is-tools-unavailable
        # The plain Muse flow, with the settings in its private config
        # folder; Muse fails the whole run when a mounted server cannot
        # start, and that failure, with Muse's own reason, is reported
        # as the tools being unavailable.
        try:
            return await MuseThreadRun.execute(request, self._config, errors, mount=mount)
        except NativeThreadError as exc:
            vendor = exc.vendor_message or ""
            if exc.failure_code is not FailureCode.MUSE_RUN_FAILED or native_threads.MUSE_REQUIRED_SERVER_MARKER not in vendor:
                raise
            raise errors.failure(NativeThreadProblem.TOOLS_UNAVAILABLE, request=request, thread_id=exc.thread_id, vendor_text=vendor, searched=browser_tools.BROWSER_REQUIRED_SERVER_DETAIL) from exc

    def tool_calls(self, run: NativeThreadRun, mount: BrowserMount) -> BrowserToolCalls:
        # The calls on mounted tools, from Muse's own records.
        return MuseExecOutput.tool_calls(run.outcome, mount)

    def missing(self, run: NativeThreadRun, mount: BrowserMount, calls: BrowserToolCalls) -> tuple[BrowserTool, ...]:
        # Muse fails the run itself when a mounted server did not start,
        # so a run that returned has every server.
        return ()


__all__ = ["MuseBrowserHarness", "MuseBrowserThreads"]
