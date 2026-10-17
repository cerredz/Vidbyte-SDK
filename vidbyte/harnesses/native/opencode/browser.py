"""FILE: vidbyte/harnesses/native/opencode/browser.py

PURPOSE: Defines the three public opencode browser functions (OpencodeBrowserThreads: run_opencode_with_browser, continue_opencode_with_browser, fork_opencode_with_browser), which run one opencode call with the caller's browser tools mounted and return a BrowserThreadResult, and OpencodeBrowserHarness, the opencode side of the shared browser flow.
ROLE IN CODEBASE: The functions are bound as module names in vidbyte/harnesses/native/opencode/__init__.py and re-exported from vidbyte.harnesses.native. Each call hands NativeBrowserRun.execute (hostkit/browser.py) an OpencodeBrowserHarness, whose steps use OpencodeMounts (opencode/mounts.py), OpencodeThreadRun (opencode/threads.py) and OpencodeWire (opencode/wire.py).
ARCHITECTURE NOTE: The functions take the plain opencode parameters with tools and tool_keys after model (spec INV-2) and share one guarded try, like the plain functions, so every failure is one NativeThreadError naming the browser function. The harness reuses the plain flow through OpencodeThreadRun.execute with a mount (spec D-3): the tools are mounted as prefixed, enabled servers with fail-closed permissions inside OPENCODE_CONFIG_CONTENT, and the built-in web tools are denied. opencode prints no per-server status, so the evidence that the tools worked is at least one call on a mounted tool (D-11). Imports run browser -> threads, wire, mounts (D-27). The module holds no literals of its own (spec INV-15).
FUNCTION INVENTORY: OpencodeBrowserThreads.run_opencode_with_browser, continue_opencode_with_browser and fork_opencode_with_browser are the public functions; OpencodeBrowserThreads._call is the one guarded try they share. OpencodeBrowserHarness.check refuses before any I/O what opencode cannot mount, run runs opencode with the mount, tool_calls reads the calls on the mounted tools, and missing names the mounted tools when none was used.
COMMON MODIFICATION PATTERNS: A new mount rule goes in OpencodeMounts; a new reader rule in OpencodeWire.tool_calls; the steps of a call change in NativeBrowserRun.execute, never here.
WHAT NOT TO DO IN THIS FILE: 1. Do not register keys or build refusal text before the records exist; NativeBrowserRun.execute registers every key first. 2. Do not catch a NativeThreadError to rewrite it; the shared flow and the factory own the codes. 3. Do not import another harness's modules.
KNOWN EDGE CASES: A server that fails to start and a server the agent never used look the same, because opencode prints no per-server status, so both are reported as "no mounted tool was used" with the answer as vendor text (spec EC-17, Q-9). A continue or fork mounts only the tools of that call (EC-30).
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/test_harness_threads_browser_mounts.py, tests/features/harness_threads/test_harness_threads_browser_lifecycle.py, tests/features/harness_threads/test_harness_threads_browser_contract.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path

from vidbyte.harnesses.native.hostkit import NativeBrowserRun, NativeErrorFactory
from vidbyte.harnesses.native.opencode.mounts import OpencodeMounts
from vidbyte.harnesses.native.opencode.threads import OpencodeThreadRun
from vidbyte.harnesses.native.opencode.wire import OpencodeWire
from vidbyte.lib.constants import native_threads
from vidbyte.lib.dataclasses.browser_tools import (
    BrowserMount,
    BrowserThreadResult,
    BrowserToolCalls,
    BrowserToolRequest,
    BrowserToolSelection,
)
from vidbyte.lib.dataclasses.native_threads import (
    NativeThreadRequest,
    NativeThreadRun,
    OpencodeThreadConfig,
)
from vidbyte.lib.dataclasses.validation import RecordFieldConverter
from vidbyte.lib.enums.browser_tools import BrowserTool
from vidbyte.lib.enums.native_threads import (
    NativeHarness,
    NativeThreadOperation,
    NativeThreadVerb,
)
from vidbyte.lib.errors import ConfigurationError, NativeThreadError


class OpencodeBrowserThreads:
    """The public opencode browser functions: start, continue or fork one session headless with the caller's browser tools mounted."""

    @staticmethod
    async def run_opencode_with_browser(prompt: str, *, api_key: str, workspace: str | Path, model: str, tools: Sequence[str], tool_keys: Mapping[str, str] | None = None, skills: Sequence[str | Path] = (), config: OpencodeThreadConfig | None = None) -> BrowserThreadResult:
        """Start a new opencode session in workspace with tools mounted, run prompt once on model with api_key, and return its id, answer, tool calls and artifacts."""
        return await OpencodeBrowserThreads._call(NativeThreadOperation.RUN_OPENCODE_WITH_BROWSER, NativeThreadVerb.RUN, None, prompt, api_key=api_key, workspace=workspace, model=model, tools=tools, tool_keys=tool_keys, skills=skills, config=config)

    @staticmethod
    async def continue_opencode_with_browser(thread_id: str, prompt: str, *, api_key: str, workspace: str | Path, model: str, tools: Sequence[str], tool_keys: Mapping[str, str] | None = None, skills: Sequence[str | Path] = (), config: OpencodeThreadConfig | None = None) -> BrowserThreadResult:
        """Run prompt once more on the opencode session thread_id with tools mounted."""
        return await OpencodeBrowserThreads._call(NativeThreadOperation.CONTINUE_OPENCODE_WITH_BROWSER, NativeThreadVerb.CONTINUE, thread_id, prompt, api_key=api_key, workspace=workspace, model=model, tools=tools, tool_keys=tool_keys, skills=skills, config=config)

    @staticmethod
    async def fork_opencode_with_browser(thread_id: str, prompt: str, *, api_key: str, workspace: str | Path, model: str, tools: Sequence[str], tool_keys: Mapping[str, str] | None = None, skills: Sequence[str | Path] = (), config: OpencodeThreadConfig | None = None) -> BrowserThreadResult:
        """Copy the opencode session thread_id into a new session, run prompt on the copy with tools mounted, and return the new id."""
        return await OpencodeBrowserThreads._call(NativeThreadOperation.FORK_OPENCODE_WITH_BROWSER, NativeThreadVerb.FORK, thread_id, prompt, api_key=api_key, workspace=workspace, model=model, tools=tools, tool_keys=tool_keys, skills=skills, config=config)

    @staticmethod
    async def _call(operation: NativeThreadOperation, verb: NativeThreadVerb, thread_id: str | None, prompt: str, *, api_key: str, workspace: str | Path, model: str, tools: Sequence[str], tool_keys: Mapping[str, str] | None, skills: Sequence[str | Path], config: OpencodeThreadConfig | None) -> BrowserThreadResult:
        # One guarded try per call: cancellation and the feature's own
        # errors pass through, a refused argument names the argument,
        # and anything else is a defect named only by its class. The
        # thread request comes first, so a refused tools argument still
        # names the workspace; no tool_keys is no keys.
        errors = NativeErrorFactory(NativeHarness.OPENCODE, operation)
        request: NativeThreadRequest | None = None
        try:
            request = NativeThreadRequest(harness=NativeHarness.OPENCODE, verb=verb, prompt=prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, thread_id=thread_id)
            browser = BrowserToolRequest(tools=tools, tool_keys={} if tool_keys is None else tool_keys)
            settings = OpencodeThreadConfig() if config is None else RecordFieldConverter.require_instance(config, native_threads.NATIVE_CONFIG_ARGUMENT, OpencodeThreadConfig)
            return await NativeBrowserRun.execute(request, browser, OpencodeBrowserHarness(settings), errors)
        except asyncio.CancelledError:
            raise
        except NativeThreadError:
            raise
        except ConfigurationError as exc:
            raise errors.from_configuration_error(exc, request) from exc
        except Exception as exc:
            raise errors.from_unexpected(exc, request) from exc


class OpencodeBrowserHarness:
    """The opencode side of a browser call: what it refuses, how it runs, and what its output shows of the mounted tools."""

    def __init__(self, config: OpencodeThreadConfig) -> None:
        self._config = config

    def check(self, selections: tuple[BrowserToolSelection, ...], request: NativeThreadRequest, errors: NativeErrorFactory) -> None:
        # opencode carries every selection the registry makes.
        OpencodeMounts.check(selections, request, errors)

    async def run(self, request: NativeThreadRequest, mount: BrowserMount, errors: NativeErrorFactory) -> NativeThreadRun:
        # The plain opencode flow, with the tools mounted in its inline
        # config.
        return await OpencodeThreadRun.execute(request, self._config, errors, mount=mount)

    def tool_calls(self, run: NativeThreadRun, mount: BrowserMount) -> BrowserToolCalls:
        # The calls on mounted tools, from opencode's own events.
        return OpencodeWire.tool_calls(run.outcome, mount)

    def missing(self, run: NativeThreadRun, mount: BrowserMount, calls: BrowserToolCalls) -> tuple[BrowserTool, ...]:
        # @intent opencode-evidence-is-one-mounted-tool-call
        # opencode prints no per-server status, so a run that called no
        # mounted tool names every mounted tool as unused.
        if calls.calls:
            return ()
        return tuple(server.selection.definition.tool for server in mount.servers)


__all__ = ["OpencodeBrowserHarness", "OpencodeBrowserThreads"]
