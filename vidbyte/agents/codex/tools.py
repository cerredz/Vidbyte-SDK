"""FILE: vidbyte/agents/codex/tools.py

PURPOSE: Attaches Vidbyte tools to a Codex harness agent as app-server dynamic tools.
ROLE IN CODEBASE: The Codex translator builds one bridge at construction; the transport attaches it to each run's connection.
ARCHITECTURE NOTE: Tool code runs in-process through ToolExecutor on the agent's event loop, never on the SDK reader thread.
COMMON MODIFICATION PATTERNS: Keep every private openai-codex attribute access inside CodexToolBridge._sync_client.
WHAT NOT TO DO IN THIS FILE: Raise from CodexToolCallHandler.handle; an exception there stops the SDK reader loop.
KNOWN EDGE CASES: Codex accepts dynamicTools only on thread/start, so resumed and forked threads keep their original definitions.
RELATED DOCS: docs/design/codex-harness-tools.md
TESTS: python -m pytest tests/test_codex_tools.py
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import re
from collections.abc import Callable, Mapping
from typing import Any

from vidbyte.lib.constants.codex import (
    CODEX_DYNAMIC_TOOL_NAME_MAX_LENGTH,
    CODEX_DYNAMIC_TOOL_NAME_PATTERN,
    CODEX_DYNAMIC_TOOLS_PARAM,
    CODEX_RESERVED_DYNAMIC_TOOL_NAME,
    CODEX_RESERVED_DYNAMIC_TOOL_PREFIX,
    CODEX_THREAD_START_METHOD,
    CODEX_TOOL_CALL_METHOD,
    CODEX_TOOL_CALL_TIMEOUT_SECONDS,
)
from vidbyte.lib.dataclasses.codex import CodexAgentSettings, CodexHarnessAgentSettings
from vidbyte.lib.dataclasses.security import PermissionPolicy
from vidbyte.lib.dataclasses.tools import ToolCall, ToolResult, ToolStatus
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError, ConfigurationError
from vidbyte.lib.tools import ToolsFormatter
from vidbyte.tools.catalog import Tools
from vidbyte.tools.executor import ToolExecutor

ServerRequestHandler = Callable[[str, "Mapping[str, Any] | None"], dict[str, Any]]
_TOOL_NAME = re.compile(CODEX_DYNAMIC_TOOL_NAME_PATTERN)


class CodexToolTranslator:
    """Resolves declared Vidbyte tools into one Codex dynamic-tool bridge at construction."""

    @classmethod
    def translate(cls, settings: CodexHarnessAgentSettings) -> CodexToolBridge | None:
        # @intent reject-unregistrable-tools-before-launch
        # Codex rejects the whole thread/start for one bad declaration, so every
        # tool is normalized and checked before any app-server process exists.
        if not settings.tools:
            return None
        cls._require_experimental_api(settings.codex)
        catalog = Tools(settings.tools)
        for name in catalog.names():
            cls._validate_name(name)
        return CodexToolBridge(catalog, settings.tool_permission_policy)

    @staticmethod
    def _require_experimental_api(settings: CodexAgentSettings) -> None:
        # dynamicTools is an experimental thread/start field the app-server refuses without the opt-in.
        if not settings.client.experimental_api:
            raise ConfigurationError(
                "Codex harness agent tools require codex.client.experimental_api=True."
            )

    @staticmethod
    def _validate_name(name: str) -> None:
        # Mirrors the app-server's dynamic function-name rules so a bad name fails at construction.
        if len(name) > CODEX_DYNAMIC_TOOL_NAME_MAX_LENGTH or not _TOOL_NAME.fullmatch(name):
            raise ConfigurationError(
                f"Codex tool name {name!r} must be 1-{CODEX_DYNAMIC_TOOL_NAME_MAX_LENGTH} "
                "characters of letters, digits, '_' or '-'."
            )
        if name == CODEX_RESERVED_DYNAMIC_TOOL_NAME or name.startswith(CODEX_RESERVED_DYNAMIC_TOOL_PREFIX):
            raise ConfigurationError(f"Codex tool name {name!r} is reserved for MCP tools.")


class CodexToolBridge:
    """Attaches one Vidbyte tool catalog to Codex app-server connections as dynamic tools."""

    def __init__(self, tools: Tools, permission_policy: PermissionPolicy) -> None:
        # Build the wire declarations and the executor once so every run registers identical tools.
        self.tools = tools
        self.dynamic_tools = tuple(ToolsFormatter.to_codex_tool(spec) for spec in tools.specs())
        self._executor = ToolExecutor(tools, permission_policy=permission_policy)

    def attach(self, codex: object, loop: asyncio.AbstractEventLoop) -> CodexToolCallHandler:
        # @intent install-tools-on-one-connection
        # AsyncCodex exposes neither dynamicTools nor a server-request handler, so
        # both are installed on its sync client before the thread is opened.
        client = self._sync_client(codex)
        handler = CodexToolCallHandler(self._executor, loop, client._approval_handler)
        client._approval_handler = handler.handle
        client.request = self._with_dynamic_tools(client.request)
        return handler

    @staticmethod
    def _sync_client(codex: object) -> Any:
        # Resolves the pinned SDK's private sync client, failing loudly if its shape has moved.
        client = getattr(getattr(codex, "_client", None), "_sync", None)
        if not callable(getattr(client, "_approval_handler", None)) or not callable(getattr(client, "request", None)):
            raise CodexAgentError(
                "Installed openai-codex does not expose the client hooks Codex tools require.",
                failure_code=FailureCode.CODEX_SDK_UNAVAILABLE.value,
                operation="attach_tools",
            )
        return client

    def _with_dynamic_tools(self, send_request: Callable[..., Any]) -> Callable[..., Any]:
        # Wraps the client's request method so only thread/start gains the dynamicTools field.
        dynamic_tools = [dict(tool) for tool in self.dynamic_tools]

        def request(method: str, params: Mapping[str, Any] | None, **kwargs: Any) -> Any:
            # @intent register-tools-at-thread-start
            # Codex accepts dynamicTools only on thread/start; resume and fork
            # restore the definitions the thread was started with.
            if method == CODEX_THREAD_START_METHOD:
                params = {**dict(params or {}), CODEX_DYNAMIC_TOOLS_PARAM: dynamic_tools}
            return send_request(method, params, **kwargs)

        return request


class CodexToolCallHandler:
    """Answers one Codex connection's server requests on the SDK reader thread."""

    def __init__(self, executor: ToolExecutor, loop: asyncio.AbstractEventLoop, fallback: ServerRequestHandler) -> None:
        # Holds the executor, the agent loop that runs tool coroutines, and the SDK's original handler.
        self._executor = executor
        self._loop = loop
        self._fallback = fallback
        self._pending: set[concurrent.futures.Future[ToolResult]] = set()

    def handle(self, method: str, params: Mapping[str, Any] | None) -> dict[str, Any]:
        # @intent tools-only-server-requests
        # Approvals and every other server request keep the SDK's own answer, so
        # attaching tools cannot change command or file-change approval behavior.
        if method != CODEX_TOOL_CALL_METHOD:
            return self._fallback(method, params)
        return self._response(self._execute(params or {}))

    def close(self) -> None:
        # Cancels tool coroutines still running when the connection closes.
        for future in tuple(self._pending):
            future.cancel()

    def _execute(self, params: Mapping[str, Any]) -> ToolResult:
        # Runs one call on the agent loop; every failure becomes a result because a raise would stop the reader thread.
        call = self._parse_call(params)
        if isinstance(call, ToolResult):
            return call
        coroutine = self._executor.execute_call(call)
        try:
            future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        except RuntimeError:
            coroutine.close()
            return ToolResult.error(call.tool_name, "The agent event loop stopped before the tool could run.", metadata={"error": "loop_closed"})
        self._pending.add(future)
        try:
            return future.result(timeout=CODEX_TOOL_CALL_TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError:
            future.cancel()
            return ToolResult.error(call.tool_name, f"Tool call timed out after {CODEX_TOOL_CALL_TIMEOUT_SECONDS:g} seconds.", metadata={"error": "timeout"})
        # Cancellation by close() or an unexpected bridge failure must still answer Codex.
        except Exception as exc:
            return ToolResult.error(call.tool_name, "Tool call was cancelled or failed before returning a result.", metadata={"error": "execution_error", "error_type": type(exc).__name__})
        finally:
            self._pending.discard(future)

    @staticmethod
    def _parse_call(params: Mapping[str, Any]) -> ToolCall | ToolResult:
        # Builds the Vidbyte call from a Codex request, or the error result for a malformed one.
        name = params.get("tool")
        arguments = params.get("arguments")
        if not isinstance(name, str) or not name.strip():
            return ToolResult.error("unknown", "Codex tool call did not name a tool.", metadata={"error": "invalid_call"})
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, Mapping):
            return ToolResult.error(name, "Tool arguments must be a JSON object.", metadata={"error": "validation_error"})
        call_id = params.get("callId")
        return ToolCall(tool_name=name, arguments=dict(arguments), call_id=call_id if isinstance(call_id, str) else None)

    @staticmethod
    def _response(result: ToolResult) -> dict[str, Any]:
        # Encodes a ToolResult as the app-server's dynamic tool call response.
        return {
            "success": result.status == ToolStatus.SUCCESS,
            "contentItems": [{"type": "inputText", "text": result.output}],
        }


__all__ = ["CodexToolBridge", "CodexToolCallHandler", "CodexToolTranslator"]
