"""Context Protocol Header

Description:
    Browserbase session and context lifecycle tools.
Purpose:
    Exposes browser infrastructure API actions without silently creating sessions
    inside search/fetch tools or returning connection capabilities to the model.
Architecture:
    Lifecycle adapters use ProviderApiTool with non-billable management calls.
Relations:
    Consumed through vidbyte.tools.builtins.operations exports.
"""

from __future__ import annotations

from dataclasses import replace

from vidbyte.lib.dataclasses.operations import OperationCharge
from vidbyte.tools.builtins.operations.api import ProviderApiTool
from vidbyte.tools.types import ToolCall, ToolParameter


class BrowserbaseSessionTool(ProviderApiTool):
    """Create, inspect, or stop an explicitly identified Browserbase session."""

    operation = "session"
    provider = "browserbase"
    tool_name = "browserbase_session"
    description = "Creates, inspects, or stops a Browserbase browser session. Session connection URLs are redacted."
    parameters = (ToolParameter("action", "string", "create, get, or stop.", required=False, default="create"), ToolParameter("session_id", "string", "Existing session ID for get or stop.", required=False), ToolParameter("region", "string", "Browserbase region for creation.", required=False), ToolParameter("keep_alive", "bool", "Keep the session alive after the tool call.", required=False, default=False))
    charge_operation = None

    async def _request(self, call: ToolCall):
        # Selects a session lifecycle endpoint without inventing hidden browser state.
        action = str(call.arguments.get("action", "create"))
        session_id = str(call.arguments.get("session_id", ""))
        if action in {"get", "stop"} and not session_id:
            raise ValueError("session_id is required for get or stop")
        path = "sessions" if action == "create" else f"sessions/{session_id}"
        method = "POST" if action == "create" else ("DELETE" if action == "stop" else "GET")
        body = {key: value for key, value in call.arguments.items() if key not in {"action", "session_id"} and value is not None}
        payload = await self._client.api("session", method=method, path=path, body=body or None, charges=())
        if action != "stop":
            return payload
        duration = payload.data.get("durationHours", payload.data.get("duration_hours"))
        if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
            seconds = payload.data.get("durationSeconds", payload.data.get("duration_seconds"))
            duration = float(seconds) / 3600 if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) else 0
        charges = (OperationCharge("session_hour", self.provider, meter="browser_hour", units=float(duration)),) if duration > 0 else ()
        return replace(payload, charges=charges)


class BrowserbaseContextTool(ProviderApiTool):
    """Create, list, or delete Browserbase persistent browser contexts."""

    operation = "context"
    provider = "browserbase"
    tool_name = "browserbase_context"
    description = "Creates, lists, or deletes Browserbase contexts that persist cookies and authenticated browser state."
    parameters = (ToolParameter("action", "string", "create, list, or delete.", required=False, default="list"), ToolParameter("context_id", "string", "Existing context ID for deletion.", required=False), ToolParameter("name", "string", "Context name for creation.", required=False))
    charge_operation = None

    async def _request(self, call: ToolCall):
        # Selects a context lifecycle endpoint while requiring explicit IDs for deletion.
        action = str(call.arguments.get("action", "list"))
        context_id = str(call.arguments.get("context_id", ""))
        if action == "delete" and not context_id:
            raise ValueError("context_id is required for delete")
        path = "contexts" if action in {"create", "list"} else f"contexts/{context_id}"
        method = "POST" if action == "create" else ("DELETE" if action == "delete" else "GET")
        body = {"name": call.arguments["name"]} if call.arguments.get("name") else None
        return await self._client.api("context", method=method, path=path, body=body, charges=())


__all__ = ["BrowserbaseContextTool", "BrowserbaseSessionTool"]
