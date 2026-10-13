"""FILE: vidbyte/harnesses/native/claude/tool_server.py

PURPOSE: Hands a request's own Vidbyte tools to Claude Code through one in-process SDK MCP server named vidbyte.
ROLE IN CODEBASE: Used by ClaudeLiveSession (session.py) when a ClaudeSpawnRequest carries tools: build makes the server that ClaudeOptionsTranslator places under mcp_servers["vidbyte"], and auto_allowed gives the tool names it adds to allowed_tools.
ARCHITECTURE NOTE: Every tool runs through one shared ToolExecutor with PermissionPolicy.allow_all(), because Claude Code's own permission layer has already approved a call before it reaches the server; the executor still looks the tool up, validates the call and turns a raised error into an error result. Each SDK tool takes its input schema from ToolsFormatter.to_anthropic_tool, so Claude sees the schema an Anthropic model would.
COMMON MODIFICATION PATTERNS: A change to how a result reaches Claude edits ClaudeToolHandler.__call__ only. A change to which tools Claude Code may call without asking edits auto_allowed only.
WHAT NOT TO DO IN THIS FILE: Raise from ClaudeToolHandler.__call__ or put an exception's text in its answer; a raised error would reach Claude as the SDK's own error text, which carries the exception's message.
KNOWN EDGE CASES: Only SAFE and READ tools are added to allowed_tools, as mcp__vidbyte__<name>; a WRITE or EXECUTE tool stays under Claude Code's own permission rules, so a headless turn is refused it unless the caller allowed it. A tool's own error result reaches Claude as is_error text with the executor's message unchanged.
RELATED DOCS: https://platform.claude.com/docs/en/agent-sdk/custom-tools; vidbyte/harnesses/README.md.
TESTS: tests/features/claude_host/
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.constants.claude import CLAUDE_MCP_TOOL_PREFIX, CLAUDE_TOOL_SERVER_NAME
from vidbyte.lib.dataclasses.claude_host import ClaudeSdkTypes
from vidbyte.lib.dataclasses.security import PermissionPolicy
from vidbyte.lib.dataclasses.tools import ToolCall, ToolPermission, ToolStatus
from vidbyte.lib.tools.formatter import ToolsFormatter
from vidbyte.tools.base import BaseTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.executor import ToolExecutor


class ClaudeToolServer:
    """Builds the in-process vidbyte MCP server that carries a request's tools to Claude Code."""

    @staticmethod
    def build(tools: tuple[BaseTool, ...], sdk: ClaudeSdkTypes) -> object:
        """Return the SDK server config for these tools, each one run by a handler over one shared ToolExecutor."""
        # @intent request-tools-ride-the-vidbyte-mcp-server
        # Claude Code asks its own permission layer before it calls a tool, so the
        # executor allows every permission and only looks up, validates and runs the
        # call; a stricter policy here would refuse calls Claude Code already approved.
        executor = ToolExecutor(Tools(tools), permission_policy=PermissionPolicy.allow_all())
        specs = [tool.spec() for tool in tools]
        sdk_tools = [sdk.tool(spec.name, spec.description, ToolsFormatter.to_anthropic_tool(spec)["input_schema"])(ClaudeToolHandler(executor, spec.name)) for spec in specs]
        return sdk.create_sdk_mcp_server(CLAUDE_TOOL_SERVER_NAME, tools=sdk_tools)

    @staticmethod
    def auto_allowed(tools: tuple[BaseTool, ...]) -> tuple[str, ...]:
        """Return the mcp__vidbyte__<name> names of the SAFE and READ tools, which Claude Code may call without asking."""
        # @intent only-read-tools-skip-the-permission-prompt
        # Vidbyte's default policy allows SAFE and READ tools, so only those are
        # allowed up front; WRITE and EXECUTE tools stay behind Claude Code's own
        # permission rules, or a headless turn could change things nobody approved.
        prefix = f"{CLAUDE_MCP_TOOL_PREFIX}{CLAUDE_TOOL_SERVER_NAME}__"
        specs = [tool.spec() for tool in tools]
        return tuple(prefix + spec.name for spec in specs if spec.permission in (ToolPermission.SAFE, ToolPermission.READ))


class ClaudeToolHandler:
    """Runs one Vidbyte tool for Claude Code and answers with MCP text content; it never raises."""

    def __init__(self, executor: ToolExecutor, tool_name: str) -> None:
        # Holds the shared executor and the name of the one tool this handler runs.
        self._executor = executor
        self._tool_name = tool_name

    async def __call__(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Run the tool on Claude's arguments and answer with its output as text, marked as an error unless it succeeded."""
        # One try spans building the call and running it, because a raised error would reach
        # Claude as the SDK's own error text with the exception's message; a fixed text says
        # the tool failed instead.
        try:
            result = await self._executor.execute_call(ToolCall(tool_name=self._tool_name, arguments=dict(arguments)))
            return {"content": [{"type": "text", "text": result.output}], "is_error": result.status is not ToolStatus.SUCCESS}
        except Exception:
            return {"content": [{"type": "text", "text": f"The tool {self._tool_name} failed before it returned a result."}], "is_error": True}


__all__ = ["ClaudeToolHandler", "ClaudeToolServer"]
