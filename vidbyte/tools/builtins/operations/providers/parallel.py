"""Context Protocol Header

Description:
    Parallel Chat, Task, FindAll, and Monitor endpoint tools.
Purpose:
    Exposes synchronous grounded chat and asynchronous web-agent workflows with
    processor-specific pricebook entries and resumable IDs.
Architecture:
    Tools delegate to ParallelClient methods so processor and run pricing remains
    explicit and centralized in the provider client.
Relations:
    Consumed through vidbyte.tools.builtins.operations exports.
"""

from __future__ import annotations

from vidbyte.tools.builtins.operations.api import ProviderApiTool
from vidbyte.tools.types import ToolCall, ToolParameter


class ParallelChatTool(ProviderApiTool):
    """Run a grounded Parallel Chat completion."""

    operation = "chat"
    provider = "parallel"
    tool_name = "parallel_chat"
    description = "Runs a fast web-grounded Parallel Chat completion at a selected model tier."
    charge_operation = None
    parameters = (ToolParameter("input", "string", "Question or conversation input."), ToolParameter("model", "string", "speed, lite, base, or core.", required=False, default="speed"), ToolParameter("system", "string", "Optional system instruction.", required=False))

    async def _request(self, call: ToolCall):
        # Runs Parallel Chat through the client so the selected model tier is priced.
        return await self._client.chat(str(call.arguments["input"]), model=str(call.arguments.get("model", "speed")), system=call.arguments.get("system"))


class ParallelResponseTool(ProviderApiTool):
    """Run the Parallel Responses API."""

    operation = "response"
    provider = "parallel"
    tool_name = "parallel_response"
    description = "Runs a web-grounded Parallel Responses API request at a selected model tier."
    charge_operation = None
    parameters = (ToolParameter("input", "string", "Response request input."), ToolParameter("model", "string", "speed, lite, base, or core.", required=False, default="speed"))

    async def _request(self, call: ToolCall):
        # Runs Parallel Responses through the client so its tier is priced separately.
        return await self._client.response(str(call.arguments["input"]), model=str(call.arguments.get("model", "speed")))


class ParallelTaskTool(ProviderApiTool):
    """Start an asynchronous Parallel Task run."""

    operation = "task"
    provider = "parallel"
    tool_name = "parallel_task"
    description = "Starts a Parallel asynchronous research or enrichment Task and returns a resumable task ID."
    charge_operation = None
    parameters = (ToolParameter("action", "string", "start, status, or cancel.", required=False, default="start"), ToolParameter("input", "string", "Research or enrichment objective for start.", required=False), ToolParameter("task_id", "string", "Task ID for status or cancel.", required=False), ToolParameter("processor", "string", "Processor such as lite, base, core, pro, or ultra.", required=False, default="base"), ToolParameter("output_schema", "object", "Optional structured output schema.", required=False))

    async def _request(self, call: ToolCall):
        # Starts or manages a Parallel Task while charging only the start run.
        action = str(call.arguments.get("action", "start"))
        if action == "start":
            input_text = str(call.arguments.get("input", ""))
            if not input_text.strip():
                raise ValueError("input is required to start a task")
            return await self._client.task(input_text, processor=str(call.arguments.get("processor", "base")), output_schema=call.arguments.get("output_schema"))
        task_id = str(call.arguments.get("task_id", ""))
        if not task_id:
            raise ValueError("task_id is required for task lifecycle actions")
        method = "DELETE" if action == "cancel" else "GET"
        return await self._client.api("task_status", method=method, path=f"v1/tasks/{task_id}", charges=())


class ParallelFindAllTool(ProviderApiTool):
    """Start a Parallel FindAll list-building run."""

    operation = "find_all"
    provider = "parallel"
    tool_name = "parallel_find_all"
    description = "Builds a verified list from natural-language criteria with an explicit FindAll generator."
    charge_operation = None
    parameters = (ToolParameter("action", "string", "start, status, or cancel.", required=False, default="start"), ToolParameter("objective", "string", "Natural-language list criteria for start.", required=False), ToolParameter("find_all_id", "string", "FindAll ID for status or cancel.", required=False), ToolParameter("generator", "string", "preview, base, core, or pro.", required=False, default="preview"), ToolParameter("output_schema", "object", "Optional enrichment schema.", required=False))

    async def _request(self, call: ToolCall):
        # Starts or manages Parallel FindAll while charging only the start run and matches.
        action = str(call.arguments.get("action", "start"))
        if action == "start":
            objective = str(call.arguments.get("objective", ""))
            if not objective.strip():
                raise ValueError("objective is required to start FindAll")
            return await self._client.find_all(objective, generator=str(call.arguments.get("generator", "preview")), output_schema=call.arguments.get("output_schema"))
        find_all_id = str(call.arguments.get("find_all_id", ""))
        if not find_all_id:
            raise ValueError("find_all_id is required for FindAll lifecycle actions")
        method = "DELETE" if action == "cancel" else "GET"
        return await self._client.api("find_all_status", method=method, path=f"v1/findall/{find_all_id}", charges=())


class ParallelMonitorTool(ProviderApiTool):
    """Create a scheduled Parallel Monitor."""

    operation = "monitor"
    provider = "parallel"
    tool_name = "parallel_monitor"
    description = "Creates a scheduled Parallel web monitor for change notifications."
    charge_operation = None
    parameters = (ToolParameter("action", "string", "create, list, get, update, or delete.", required=False, default="create"), ToolParameter("objective", "string", "Natural-language monitoring objective for create.", required=False), ToolParameter("monitor_id", "string", "Monitor ID for targeted actions.", required=False), ToolParameter("processor", "string", "lite or base.", required=False, default="lite"), ToolParameter("schedule", "string", "Provider-supported schedule expression.", required=False))

    async def _request(self, call: ToolCall):
        # Creates or manages a Parallel Monitor while charging only a new execution.
        action = str(call.arguments.get("action", "create"))
        if action == "create":
            objective = str(call.arguments.get("objective", ""))
            if not objective.strip():
                raise ValueError("objective is required to create a monitor")
            return await self._client.monitor(objective, processor=str(call.arguments.get("processor", "lite")), schedule=call.arguments.get("schedule"))
        monitor_id = str(call.arguments.get("monitor_id", ""))
        if action in {"get", "update", "delete"} and not monitor_id:
            raise ValueError("monitor_id is required for the selected monitor action")
        path = "v1/monitors" if action == "list" else f"v1/monitors/{monitor_id}"
        method = {"list": "GET", "get": "GET", "update": "PATCH", "delete": "DELETE"}.get(action, "GET")
        body = {key: value for key, value in call.arguments.items() if key not in {"action", "monitor_id"} and value is not None}
        return await self._client.api("monitor_lifecycle", method=method, path=path, body=body or None, charges=())


__all__ = ["ParallelChatTool", "ParallelFindAllTool", "ParallelMonitorTool", "ParallelResponseTool", "ParallelTaskTool"]
