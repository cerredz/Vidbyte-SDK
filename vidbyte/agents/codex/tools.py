"""FILE: vidbyte/agents/codex/tools.py

PURPOSE: Translates Vidbyte tools into Codex-consumable definitions and executes calls.
ROLE IN CODEBASE: Agent facade composes this collaborator; transport and result layers stay unchanged.
ARCHITECTURE NOTE: Definitions cross the lib boundary as data; live tool objects never enter lib.
COMMON MODIFICATION PATTERNS: Add a method per translation or execution concern, never inline logic in agent.py.
WHAT NOT TO DO IN THIS FILE: Open threads, run turns, or import provider SDK objects.
KNOWN EDGE CASES: Mixed BaseTool, ToolLike, and definition inputs must deduplicate by name, not identity.
RELATED DOCS: docs/design/codex-custom-tools.md.
TESTS: scripts/test-codex-custom-tools.py and tests/test_codex_custom_tools.py.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.lib.dataclasses.codex import CodexToolDefinition
from vidbyte.lib.dataclasses.tools import ToolCall, ToolResult
from vidbyte.lib.errors import ConfigurationError


class CodexToolTranslator:
    """Converts SDK tools into validated Codex tool definitions."""

    def from_sdk_tools(
        self, tools: Sequence[object]
    ) -> tuple[CodexToolDefinition, ...]:
        # Accept BaseTool, ToolLike, and definition inputs in one pass.
        seen: dict[str, CodexToolDefinition] = {}
        for tool in tools:
            definition = self._to_definition(tool)
            if definition.name in seen:
                raise ConfigurationError(
                    f"Duplicate Codex tool name {definition.name!r}."
                )
            seen[definition.name] = definition
        return tuple(seen[name] for name in sorted(seen))

    def to_prompt_block(self, definitions: Sequence[CodexToolDefinition]) -> str:
        # Render deterministic developer-context text for prompt-described tools.
        blocks = [
            self._render_definition(item)
            for item in sorted(definitions, key=lambda d: d.name)
        ]
        return "\n\n".join(block for block in blocks if block)

    def to_mcp_config(
        self, definitions: Sequence[CodexToolDefinition], command: str
    ) -> Mapping[str, Any]:
        # Build the thread-config mcp_servers block for sidecar execution.
        names = [item.name for item in sorted(definitions, key=lambda d: d.name)]
        if not command.strip():
            raise ConfigurationError("Codex MCP config command must be non-empty.")
        if not names:
            return {}
        return {"mcp_servers": {"vidbyte-tools": {"command": command, "tools": names}}}

    def build_call(self, tool_name: str, arguments: Mapping[str, Any]) -> ToolCall:
        # Construct one validated runtime call record for the executor.
        if not tool_name.strip():
            raise ConfigurationError("Codex tool call name must be non-empty.")
        if not isinstance(arguments, Mapping):
            raise ConfigurationError("Codex tool call arguments must be a mapping.")
        return ToolCall(tool_name=tool_name, arguments=dict(arguments))

    def _to_definition(self, tool: object) -> CodexToolDefinition:
        # Passthrough for pre-translated records; otherwise read spec() once.
        if isinstance(tool, CodexToolDefinition):
            return tool
        spec = self._tool_spec(tool)
        return CodexToolDefinition(
            name=str(spec.name),
            description=str(spec.description),
            input_schema=self._schema_from_spec(spec),
        )

    def _tool_spec(self, tool: object) -> Any:
        # Structural read so ToolLike implementations need no BaseTool import.
        spec_method = getattr(tool, "spec", None)
        if not callable(spec_method):
            raise ConfigurationError("Codex tools must expose spec().")
        spec = spec_method()
        if not getattr(spec, "name", "") or not str(spec.name).strip():
            raise ConfigurationError("Codex tool spec name must be non-empty.")
        if not getattr(spec, "description", "") or not str(spec.description).strip():
            raise ConfigurationError("Codex tool spec description must be non-empty.")
        return spec

    def _schema_from_spec(self, spec: Any) -> dict[str, Any]:
        # Prefer explicit input_schema; otherwise derive an object schema from parameters.
        raw = getattr(spec, "input_schema", None)
        if isinstance(raw, Mapping):
            return dict(raw)
        properties: dict[str, Any] = {}
        required: list[str] = []
        for parameter in getattr(spec, "parameters", ()) or ():
            properties[str(parameter.name)] = {"type": str(parameter.type)}
            if getattr(parameter, "required", True):
                required.append(str(parameter.name))
        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    def _render_definition(self, definition: CodexToolDefinition) -> str:
        # One stable block per tool so repeated runs render byte-identical text.
        schema = json.dumps(dict(definition.input_schema), sort_keys=True)
        lines = [f"Tool: {definition.name}", f"Description: {definition.description}"]
        lines.append(f"Arguments: {schema}")
        return "\n".join(lines)


class CodexToolExecutor:
    """Executes translated tool calls against caller-owned tool objects."""

    def __init__(self, tools: Sequence[object]) -> None:
        # Index executable tools by name; definitions alone stay describable elsewhere.
        self._tools: dict[str, Any] = {}
        for tool in tools:
            name = self._executable_name(tool)
            if name is not None:
                self._tools[name] = tool

    def tool_names(self) -> tuple[str, ...]:
        # Sorted names keep prompt blocks and MCP configs deterministic.
        return tuple(sorted(self._tools))

    def has_tool(self, tool_name: str) -> bool:
        # Membership check before any validation or execution work starts.
        return tool_name in self._tools

    async def execute_tool_call(
        self, tool_name: str, arguments: Mapping[str, Any]
    ) -> ToolResult:
        # Validate through the tool's own contract, then run and return its result.
        tool = self._tools.get(tool_name)
        if tool is None:
            raise ConfigurationError(f"Unknown Codex tool {tool_name!r}.")
        call = ToolCall(tool_name=tool_name, arguments=dict(arguments))
        validator = getattr(tool, "validate_call", None)
        if callable(validator):
            problem = validator(call)
            if problem:
                raise ConfigurationError(f"Codex tool {tool_name!r} rejected its call.")
        execute = getattr(tool, "execute", None)
        if not callable(execute):
            raise ConfigurationError(f"Codex tool {tool_name!r} cannot execute.")
        return await execute(call)

    def _executable_name(self, tool: object) -> str | None:
        # Only objects with both spec() and execute() can run in-process.
        if isinstance(tool, CodexToolDefinition):
            return None
        spec_method = getattr(tool, "spec", None)
        execute_method = getattr(tool, "execute", None)
        if not callable(spec_method) or not callable(execute_method):
            return None
        try:
            name = str(spec_method().name).strip()
        except (AttributeError, TypeError, ValueError):
            return None
        return name or None


__all__ = ["CodexToolExecutor", "CodexToolTranslator"]
