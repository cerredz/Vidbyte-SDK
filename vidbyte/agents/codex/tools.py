"""FILE: vidbyte/agents/codex/tools.py

PURPOSE: Attaches Vidbyte tools to a Codex harness agent as app-server dynamic tools.
ROLE IN CODEBASE: The Codex translator builds one bridge at construction; the transport attaches it to each run's connection.
ARCHITECTURE NOTE: Tool code runs in-process through ToolExecutor on the agent's event loop, never on the SDK reader thread.
COMMON MODIFICATION PATTERNS: Keep every private openai-codex attribute access inside CodexToolBridge._sync_client; add Codex wire fields to the request/response records in vidbyte/lib/dataclasses/codex.py.
WHAT NOT TO DO IN THIS FILE: Raise from CodexToolCallHandler.handle; an exception there stops the SDK reader loop.
KNOWN EDGE CASES: Codex accepts dynamicTools only on thread/start, so resumed and forked threads keep their original definitions.
RELATED DOCS: docs/design/codex-harness-tools.md
TESTS: python -m pytest tests/test_codex_tools.py
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import re
from collections.abc import Callable, Coroutine, Mapping
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
from vidbyte.lib.dataclasses.codex import (
    CodexHarnessAgentSettings,
    CodexToolAttachRequest,
    CodexToolCallRequest,
    CodexToolCallResponse,
)
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

    @staticmethod
    def translate(settings: CodexHarnessAgentSettings) -> CodexToolBridge | None:
        # @intent reject-unregistrable-tools-before-launch
        # Codex rejects the whole thread/start for one bad declaration, so the
        # experimental-API opt-in and every tool name are checked against the
        # app-server's rules before any app-server process exists.
        if not settings.tools:
            return None
        if not settings.codex.client.experimental_api:
            raise ConfigurationError(
                "Codex harness agent tools require codex.client.experimental_api=True."
            )
        catalog = Tools(settings.tools)
        for name in catalog.names():
            if len(name) > CODEX_DYNAMIC_TOOL_NAME_MAX_LENGTH or not _TOOL_NAME.fullmatch(name):
                raise ConfigurationError(
                    f"Codex tool name {name!r} must be 1-{CODEX_DYNAMIC_TOOL_NAME_MAX_LENGTH} "
                    "characters of letters, digits, '_' or '-'."
                )
            if name == CODEX_RESERVED_DYNAMIC_TOOL_NAME or name.startswith(CODEX_RESERVED_DYNAMIC_TOOL_PREFIX):
                raise ConfigurationError(f"Codex tool name {name!r} is reserved for MCP tools.")
        return CodexToolBridge(catalog, settings.tool_permission_policy)


class CodexToolBridge:
    """Attaches one Vidbyte tool catalog to Codex app-server connections as dynamic tools."""

    def __init__(self, tools: Tools, permission_policy: PermissionPolicy) -> None:
        # Build the wire declarations and the executor once so every run registers identical tools.
        self.tools = tools
        self.dynamic_tools = tuple(ToolsFormatter.to_codex_tool(spec) for spec in tools.specs())
        self._executor = ToolExecutor(tools, permission_policy=permission_policy)

    def attach(self, request: CodexToolAttachRequest) -> CodexToolCallHandler:
        # @intent install-tools-on-one-connection
        # AsyncCodex exposes neither dynamicTools nor a server-request handler, so
        # both are installed on its sync client before the thread is opened.
        client = self._sync_client(request)
        handler = CodexToolCallHandler(self._executor, request.loop, client._approval_handler)
        client._approval_handler = handler.handle
        client.request = self._with_dynamic_tools(client.request)
        return handler

    @staticmethod
    def _sync_client(request: CodexToolAttachRequest) -> Any:
        # Resolves the pinned SDK's private sync client, failing loudly if its shape has moved.
        client = getattr(getattr(request.client, "_client", None), "_sync", None)
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
        coroutine: Coroutine[Any, Any, ToolResult] | None = None
        future: concurrent.futures.Future[ToolResult] | None = None
        # @intent answer-every-tool-call
        # One try spans reading the call, scheduling it, and waiting for it,
        # because any raise here would stop the SDK reader thread for the run.
        try:
            call = CodexToolCallRequest.from_params(params)
            coroutine = self._executor.execute_call(
                ToolCall(tool_name=call.tool, arguments=dict(call.arguments), call_id=call.call_id)
            )
            future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
            self._pending.add(future)
            result = future.result(timeout=CODEX_TOOL_CALL_TIMEOUT_SECONDS)
            response = CodexToolCallResponse(success=result.status == ToolStatus.SUCCESS, text=result.output)
        except ConfigurationError as exc:
            response = CodexToolCallResponse(success=False, text=exc.message)
        except concurrent.futures.TimeoutError:
            response = CodexToolCallResponse(
                success=False, text=f"Tool call timed out after {CODEX_TOOL_CALL_TIMEOUT_SECONDS:g} seconds."
            )
        # Cancellation by close(), a stopped loop, or a bridge failure must still answer Codex.
        except Exception:
            response = CodexToolCallResponse(
                success=False,
                text="The agent event loop stopped before the tool could run."
                if self._loop.is_closed()
                else "Tool call was cancelled or failed before returning a result.",
            )
        finally:
            if future is not None:
                future.cancel()
                self._pending.discard(future)
            elif coroutine is not None:
                coroutine.close()
        return {"success": response.success, "contentItems": [{"type": "inputText", "text": response.text}]}

    def close(self) -> None:
        # Cancels tool coroutines still running when the connection closes.
        for future in tuple(self._pending):
            future.cancel()


__all__ = ["CodexToolBridge", "CodexToolCallHandler", "CodexToolTranslator"]
