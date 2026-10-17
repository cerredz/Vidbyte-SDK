"""FILE: vidbyte/harnesses/native/grok/browser.py

PURPOSE: Defines the three public Grok Build browser functions (GrokBrowserThreads: run_grok_with_browser, continue_grok_with_browser, fork_grok_with_browser), which run one Grok call with the caller's browser tools mounted and return a BrowserThreadResult, and GrokBrowserHarness, the Grok side of the shared browser flow.
ROLE IN CODEBASE: The functions are bound as module names in vidbyte/harnesses/native/grok/__init__.py and re-exported from vidbyte.harnesses.native. Each call hands NativeBrowserRun.execute (hostkit/browser.py) a GrokBrowserHarness, whose steps use GrokMounts (grok/mounts.py), GrokThreadRun (grok/threads.py), GrokWire (grok/wire.py) and NativeBrowserTools.write_file from hostkit.
ARCHITECTURE NOTE: The functions take the plain Grok parameters with tools and tool_keys after model (spec INV-2) and share one guarded try, like the plain functions, so every failure is one NativeThreadError naming the browser function. The harness writes the per-call agent file through the reviewed writer (D-25), then reuses the plain flow through GrokThreadRun.execute with a mount (D-3), which streams and adds the rules, the compat switches and the tool keys. Grok lists each connected server's tools in its stream, so the evidence that the tools worked is each mounted server listed or called (D-11). Imports run browser -> threads, wire, mounts (D-27). The module holds no literals of its own (spec INV-15).
FUNCTION INVENTORY: GrokBrowserThreads.run_grok_with_browser, continue_grok_with_browser and fork_grok_with_browser are the public functions; GrokBrowserThreads._call is the one guarded try they share. GrokBrowserHarness.check refuses before any I/O what Grok cannot mount, run writes the agent file and runs grok with the mount, tool_calls reads the calls on the mounted tools, and missing names each mounted server the stream never shows.
COMMON MODIFICATION PATTERNS: A new mount rule goes in GrokMounts; a new reader rule in GrokWire; the steps of a call change in NativeBrowserRun.execute, never here.
WHAT NOT TO DO IN THIS FILE: 1. Do not write the agent file with a direct file call; it goes through NativeBrowserTools.write_file (lint S061, D-25). 2. Do not put a key into the agent file; keys travel in Grok's environment. 3. Do not import another harness's modules.
KNOWN EDGE CASES: A server that is still connecting after Grok's start-up grace is not listed and is named as missing, with the new thread id and the answer (spec EC-16, EC-45). An agent file that cannot be written is launch_failed, naming the per-call folder. A continue or fork mounts only the tools of that call (EC-30).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_browser_mounts.py, tests/features/harness_threads/test_harness_threads_browser_lifecycle.py, tests/features/harness_threads/test_harness_threads_browser_contract.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path

from vidbyte.harnesses.native.grok.mounts import GrokMounts
from vidbyte.harnesses.native.grok.threads import GrokThreadRun
from vidbyte.harnesses.native.grok.wire import GrokWire
from vidbyte.harnesses.native.hostkit import (
    NativeBrowserRun,
    NativeBrowserTools,
    NativeErrorFactory,
)
from vidbyte.lib.constants import browser_tools, native_threads
from vidbyte.lib.dataclasses.browser_tools import (
    BrowserMount,
    BrowserThreadResult,
    BrowserToolCalls,
    BrowserToolRequest,
    BrowserToolSelection,
)
from vidbyte.lib.dataclasses.native_threads import (
    GrokThreadConfig,
    NativeThreadRequest,
    NativeThreadRun,
)
from vidbyte.lib.dataclasses.validation import RecordFieldConverter
from vidbyte.lib.enums.browser_tools import BrowserTool
from vidbyte.lib.enums.native_threads import (
    NativeHarness,
    NativeThreadOperation,
    NativeThreadProblem,
    NativeThreadVerb,
)
from vidbyte.lib.errors import ConfigurationError, NativeThreadError


class GrokBrowserThreads:
    """The public Grok Build browser functions: start, continue or fork one thread headless with the caller's browser tools mounted."""

    @staticmethod
    async def run_grok_with_browser(prompt: str, *, api_key: str, workspace: str | Path, model: str | None = None, tools: Sequence[str], tool_keys: Mapping[str, str] | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> BrowserThreadResult:
        """Start a new Grok Build thread in workspace with tools mounted, run prompt once with api_key, and return its id, answer, tool calls and artifacts."""
        return await GrokBrowserThreads._call(NativeThreadOperation.RUN_GROK_WITH_BROWSER, NativeThreadVerb.RUN, None, prompt, api_key=api_key, workspace=workspace, model=model, tools=tools, tool_keys=tool_keys, skills=skills, config=config)

    @staticmethod
    async def continue_grok_with_browser(thread_id: str, prompt: str, *, api_key: str, workspace: str | Path, model: str | None = None, tools: Sequence[str], tool_keys: Mapping[str, str] | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> BrowserThreadResult:
        """Run prompt once more on the Grok Build thread thread_id with tools mounted; only the workspace that created it can reach it."""
        return await GrokBrowserThreads._call(NativeThreadOperation.CONTINUE_GROK_WITH_BROWSER, NativeThreadVerb.CONTINUE, thread_id, prompt, api_key=api_key, workspace=workspace, model=model, tools=tools, tool_keys=tool_keys, skills=skills, config=config)

    @staticmethod
    async def fork_grok_with_browser(thread_id: str, prompt: str, *, api_key: str, workspace: str | Path, model: str | None = None, tools: Sequence[str], tool_keys: Mapping[str, str] | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> BrowserThreadResult:
        """Copy the Grok Build thread thread_id into a new thread, run prompt on the copy with tools mounted, and return the new id."""
        return await GrokBrowserThreads._call(NativeThreadOperation.FORK_GROK_WITH_BROWSER, NativeThreadVerb.FORK, thread_id, prompt, api_key=api_key, workspace=workspace, model=model, tools=tools, tool_keys=tool_keys, skills=skills, config=config)

    @staticmethod
    async def _call(operation: NativeThreadOperation, verb: NativeThreadVerb, thread_id: str | None, prompt: str, *, api_key: str, workspace: str | Path, model: str | None, tools: Sequence[str], tool_keys: Mapping[str, str] | None, skills: Sequence[str | Path], config: GrokThreadConfig | None) -> BrowserThreadResult:
        # One guarded try per call: cancellation and the feature's own
        # errors pass through, a refused argument names the argument,
        # and anything else is a defect named only by its class. The
        # thread request comes first, so a refused tools argument still
        # names the workspace; no tool_keys is no keys.
        errors = NativeErrorFactory(NativeHarness.GROK, operation)
        request: NativeThreadRequest | None = None
        try:
            request = NativeThreadRequest(harness=NativeHarness.GROK, verb=verb, prompt=prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, thread_id=thread_id)
            browser = BrowserToolRequest(tools=tools, tool_keys={} if tool_keys is None else tool_keys)
            settings = GrokThreadConfig() if config is None else RecordFieldConverter.require_instance(config, native_threads.NATIVE_CONFIG_ARGUMENT, GrokThreadConfig)
            return await NativeBrowserRun.execute(request, browser, GrokBrowserHarness(settings), errors)
        except asyncio.CancelledError:
            raise
        except NativeThreadError:
            raise
        except ConfigurationError as exc:
            raise errors.from_configuration_error(exc, request) from exc
        except Exception as exc:
            raise errors.from_unexpected(exc, request) from exc


class GrokBrowserHarness:
    """The Grok Build side of a browser call: what it refuses, how it runs, and what its stream shows of the mounted tools."""

    def __init__(self, config: GrokThreadConfig) -> None:
        self._config = config

    def check(self, selections: tuple[BrowserToolSelection, ...], request: NativeThreadRequest, errors: NativeErrorFactory) -> None:
        # Keyed remote tools and rules past the command-line budget are
        # refused before anything starts.
        GrokMounts.check(selections, request, errors)

    async def run(self, request: NativeThreadRequest, mount: BrowserMount, errors: NativeErrorFactory) -> NativeThreadRun:
        # @intent grok-agent-file-is-written-by-the-reviewed-writer
        # Write the per-call agent file whole into the call's folder,
        # then run the plain Grok flow with the mount; a file that
        # cannot be written starts nothing.
        try:
            await NativeBrowserTools.write_file(GrokMounts.agent_path(mount), GrokMounts.agent_text(mount))
        except OSError as exc:
            detail = browser_tools.BROWSER_GROK_AGENT_FILE_DETAIL.format(folder=mount.folder, error_type=type(exc).__name__)
            raise errors.failure(NativeThreadProblem.LAUNCH_FAILED, request=request, searched=detail) from exc
        return await GrokThreadRun.execute(request, self._config, errors, mount=mount)

    def tool_calls(self, run: NativeThreadRun, mount: BrowserMount) -> BrowserToolCalls:
        # The calls on mounted tools, from Grok's own stream.
        return GrokWire.tool_calls(run.outcome, mount)

    def missing(self, run: NativeThreadRun, mount: BrowserMount, calls: BrowserToolCalls) -> tuple[BrowserTool, ...]:
        # @intent grok-evidence-is-each-server-listed-or-called
        # Each mounted server must show in Grok's tool list or in a
        # call; the rest are named as missing.
        seen = {*GrokWire.connected(run.outcome, mount), *(call.tool for call in calls.calls)}
        return tuple(server.selection.definition.tool for server in mount.servers if server.selection.definition.tool not in seen)


__all__ = ["GrokBrowserHarness", "GrokBrowserThreads"]
