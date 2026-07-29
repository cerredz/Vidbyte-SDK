"""Context Protocol Header

Description:
    Exa answer, webset, and monitor endpoint tools.
Purpose:
    Exposes Exa's agentic API surfaces as explicit tools while leaving normalized
    Search and Contents behavior in the common operation modules.
Architecture:
    Endpoint adapters delegate to ExaClient through ProviderApiTool and retain
    request/task identifiers in application metadata.
Relations:
    Consumed through vidbyte.tools.builtins.operations exports.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.operations import OperationCharge
from vidbyte.tools.builtins.operations.api import ProviderApiTool
from vidbyte.tools.types import ToolCall, ToolParameter


class ExaAnswerTool(ProviderApiTool):
    """Generate an answer grounded by Exa search."""

    operation = "answer"
    provider = "exa"
    tool_name = "exa_answer"
    description = "Answers a question using Exa web search with citations and optional structured output."
    path = "answer"
    parameters = (ToolParameter("query", "string", "Question to answer with current web evidence."), ToolParameter("type", "string", "Exa search type such as auto, deep, or deep-reasoning.", required=False, default="auto"), ToolParameter("output_schema", "object", "Optional JSON schema for a structured answer.", required=False))
    charge_operation = "answer"
    charge_meter = "request"


class ExaWebsetTool(ProviderApiTool):
    """Create, inspect, update, or delete an Exa Webset."""

    operation = "webset"
    provider = "exa"
    tool_name = "exa_webset"
    description = "Manages Exa Websets for structured search, verification, enrichment, imports, and webhook-driven updates."
    path = "websets"
    parameters = (ToolParameter("action", "string", "API action such as create, list, get, update, or delete."), ToolParameter("webset_id", "string", "Existing Webset ID when the action targets one.", required=False), ToolParameter("query", "string", "Natural-language Webset search objective.", required=False), ToolParameter("criteria", "array", "Structured verification or enrichment criteria.", required=False), ToolParameter("metadata", "object", "Provider-supported Webset metadata.", required=False))
    charge_operation = None

    async def _request(self, call: ToolCall):
        # Routes Webset CRUD, search, enrichment, import, and monitor actions to documented paths.
        action = str(call.arguments.get("action", "list"))
        webset_id = str(call.arguments.get("webset_id", ""))
        if action in {"get", "update", "delete", "searches", "enrichments", "imports"} and not webset_id:
            raise ValueError("webset_id is required for the selected action")
        suffix = f"/{webset_id}" if webset_id else ""
        path = {"create": "websets", "list": "websets", "get": f"websets{suffix}", "update": f"websets{suffix}", "delete": f"websets{suffix}", "searches": f"websets{suffix}/searches", "enrichments": f"websets{suffix}/enrichments", "imports": f"websets{suffix}/imports"}.get(action, "websets")
        method = {"create": "POST", "list": "GET", "get": "GET", "update": "PATCH", "delete": "DELETE", "searches": "POST", "enrichments": "POST", "imports": "POST"}.get(action, "GET")
        body = {key: value for key, value in call.arguments.items() if key not in {"action", "webset_id"} and value is not None}
        return await self._client.api("webset", method=method, path=path, body=body or None, charges=())


class ExaMonitorTool(ProviderApiTool):
    """Create or inspect Exa web monitors."""

    operation = "monitor"
    provider = "exa"
    tool_name = "exa_monitor"
    description = "Creates or inspects an Exa monitor that tracks fresh events across the web."
    path = "monitors"
    parameters = (ToolParameter("action", "string", "create, list, get, update, or delete.", required=False, default="list"), ToolParameter("monitor_id", "string", "Existing monitor ID for targeted actions.", required=False), ToolParameter("query", "string", "Natural-language monitoring query.", required=False), ToolParameter("webhook_url", "string", "Webhook destination for monitor updates.", required=False))
    charge_operation = "monitor"
    charge_mode = "default"
    charge_meter = "request"

    async def _request(self, call: ToolCall):
        # Routes Exa monitor CRUD actions while keeping the recurring API unpriced until execution metadata is known.
        action = str(call.arguments.get("action", "list"))
        monitor_id = str(call.arguments.get("monitor_id", ""))
        if action in {"get", "update", "delete"} and not monitor_id:
            raise ValueError("monitor_id is required for the selected action")
        suffix = f"/{monitor_id}" if monitor_id else ""
        path = "monitors" if action in {"create", "list"} else f"monitors{suffix}"
        method = {"create": "POST", "list": "GET", "get": "GET", "update": "PATCH", "delete": "DELETE"}.get(action, "GET")
        body = {key: value for key, value in call.arguments.items() if key not in {"action", "monitor_id"} and value is not None}
        charges = (OperationCharge("monitor", self.provider, mode="default", meter="request", units=1),) if action == "create" else ()
        return await self._client.api("monitor", method=method, path=path, body=body or None, charges=charges)


__all__ = ["ExaAnswerTool", "ExaMonitorTool", "ExaWebsetTool"]
