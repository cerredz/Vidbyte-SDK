"""Native dynamic tool execution boundary.

PURPOSE: Authorize native server requests through the existing Vidbyte executor.
ROLE IN CODEBASE: Synchronous Codex reader callback bridged onto the application loop.
ARCHITECTURE NOTE: Never issue native requests from the reader callback.
COMMON MODIFICATION PATTERNS: Add rejection cases before scheduling side effects.
KNOWN EDGE CASES: Cancellation cannot undo effects a tool already performed.
RELATED DOCS: docs/design/codex-native-tools.md
TESTS: tests/codex_native_tools/test_native_tools.py
"""

from __future__ import annotations

import asyncio
import copy
import json
import threading
from concurrent.futures import Future
from typing import Any

from vidbyte.lib.dataclasses.codex import CodexDynamicToolCall, CodexToolBridgeSettings
from vidbyte.lib.enums.failure import FailureCode
from vidbyte.lib.errors import CodexAgentError
from vidbyte.tools.catalog import Tools
from vidbyte.tools.executor import ToolExecutor
from vidbyte.tools.types import ToolCall, ToolResult, ToolStatus


class CodexToolDispatcher:
    """Serial native callback with per-run identity checks and idempotency."""

    def __init__(self, settings: CodexToolBridgeSettings) -> None:
        # Snapshot membership while retaining bound tool instances and their state.
        self.settings = settings
        self.tools = Tools(settings.tools.all())
        self.executor = ToolExecutor(self.tools, permission_policy=settings.permission_policy)
        self.loop = asyncio.get_running_loop()
        self.thread_id = ""
        self.cache: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
        self.pending: set[Future[ToolResult]] = set()
        self.lock = threading.Lock()
        self.closed = False

    def handle(self, method: str, params: dict[str, Any] | None) -> dict[str, Any]:
        # @intent authorize-before-native-tool-response
        # A native request blocks until validation and the existing executor finish.
        if method != "item/tool/call":
            return self.reject_request(method)
        try:
            call = CodexDynamicToolCall.model_validate(params)
            self.validate(call)
            fingerprint = json.dumps(call.model_dump(mode="json"), sort_keys=True, allow_nan=False)
            key = (call.turn_id, call.call_id)
            if key in self.cache:
                previous, response = self.cache[key]
                return copy.deepcopy(response) if previous == fingerprint else self.response("Conflicting duplicate tool call.")
            try:
                response = self.execute(call)
            except CodexAgentError:
                response = self.response("Vidbyte tool execution stopped.")
            self.cache[key] = (fingerprint, copy.deepcopy(response))
            return response
        except (ValueError, TypeError, CodexAgentError) as exc:
            return self.response(f"Codex tool request rejected ({type(exc).__name__}).")

    def validate(self, call: CodexDynamicToolCall) -> None:
        # Reject invalid routing before any application coroutine can be scheduled.
        if self.closed or not self.thread_id or call.thread_id != self.thread_id:
            raise ValueError("Inactive or mismatched tool thread.")
        if call.namespace is not None or call.tool not in self.tools.names():
            raise ValueError("Unregistered tool namespace or name.")
        if any(not value.strip() for value in (call.call_id, call.turn_id, call.tool)):
            raise ValueError("Empty native tool identity.")

    def execute(self, call: CodexDynamicToolCall) -> dict[str, Any]:
        # @intent bounded-callback-wait
        # Keep async tools on their owner's loop; cancel outstanding work on timeout.
        with self.lock:
            if self.closed:
                return self.response("Codex tool bridge is closed.")
            future = asyncio.run_coroutine_threadsafe(self.executor.execute_call(ToolCall(tool_name=call.tool, arguments=call.arguments, call_id=call.call_id, metadata={"codex_thread_id": call.thread_id, "codex_turn_id": call.turn_id})), self.loop)
            self.pending.add(future)
        try:
            result = future.result(timeout=self.settings.timeout_seconds)
            if result.metadata.get("error") == "execution_error":
                return self.response("Vidbyte tool execution failed.")
            return self.response(result.output, success=result.status is ToolStatus.SUCCESS)
        except Exception as exc:
            future.cancel()
            raise CodexAgentError("Vidbyte tool execution stopped.", failure_code=FailureCode.CODEX_TURN_FAILED.value, operation="native_tool_execute", error_type=type(exc).__name__) from exc
        finally:
            with self.lock:
                self.pending.discard(future)

    def close(self) -> None:
        # @intent cancel-before-reader-join
        # Unblock the native reader before client shutdown waits for that thread.
        with self.lock:
            self.closed = True
            for future in self.pending:
                future.cancel()

    @staticmethod
    def response(text: str, *, success: bool = False) -> dict[str, Any]:
        # Produce the exact experimental native text-result envelope.
        return {"contentItems": [{"type": "inputText", "text": text}], "success": success}

    @staticmethod
    def reject_request(method: str) -> dict[str, Any]:
        # @intent no-implicit-native-approval
        # This tool bridge cannot authorize unrelated native side effects.
        if method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}:
            return {"decision": "decline"}
        raise ValueError(f"Unsupported native server request: {method}")


__all__ = ["CodexToolDispatcher"]
