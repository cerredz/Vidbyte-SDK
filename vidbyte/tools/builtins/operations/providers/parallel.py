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


class ParallelTaskTool(ProviderApiTool):
    """Start an asynchronous Parallel Task run."""

    operation = "task"
    provider = "parallel"
    tool_name = "parallel_task"
    description = "Starts a Parallel asynchronous research or enrichment Task and returns a resumable task ID."
    charge_operation = None
    parameters = (ToolParameter("input", "string", "Research or enrichment objective."), ToolParameter("processor", "string", "Processor such as lite, base, core, pro, or ultra.", required=False, default="base"), ToolParameter("output_schema", "object", "Optional structured output schema.", required=False))

    async def _request(self, call: ToolCall):
        # Starts Parallel Task through the client and records one processor run.
        return await self._client.task(str(call.arguments["input"]), processor=str(call.arguments.get("processor", "base")), output_schema=call.arguments.get("output_schema"))


class ParallelFindAllTool(ProviderApiTool):
    """Start a Parallel FindAll list-building run."""

    operation = "find_all"
    provider = "parallel"
    tool_name = "parallel_find_all"
    description = "Builds a verified list from natural-language criteria with an explicit FindAll generator."
    charge_operation = None
    parameters = (ToolParameter("objective", "string", "Natural-language list criteria."), ToolParameter("generator", "string", "preview, base, core, or pro.", required=False, default="preview"), ToolParameter("output_schema", "object", "Optional enrichment schema.", required=False))

    async def _request(self, call: ToolCall):
        # Starts Parallel FindAll through the client and records the generator run.
        return await self._client.find_all(str(call.arguments["objective"]), generator=str(call.arguments.get("generator", "preview")), output_schema=call.arguments.get("output_schema"))


class ParallelMonitorTool(ProviderApiTool):
    """Create a scheduled Parallel Monitor."""

    operation = "monitor"
    provider = "parallel"
    tool_name = "parallel_monitor"
    description = "Creates a scheduled Parallel web monitor for change notifications."
    charge_operation = None
    parameters = (ToolParameter("objective", "string", "Natural-language monitoring objective."), ToolParameter("processor", "string", "lite or base.", required=False, default="lite"), ToolParameter("schedule", "string", "Provider-supported schedule expression.", required=False))

    async def _request(self, call: ToolCall):
        # Creates Parallel Monitor through the client and records its first execution charge.
        return await self._client.monitor(str(call.arguments["objective"]), processor=str(call.arguments.get("processor", "lite")), schedule=call.arguments.get("schedule"))


__all__ = ["ParallelChatTool", "ParallelFindAllTool", "ParallelMonitorTool", "ParallelTaskTool"]
