"""
FILE: vidbyte/tools/agent_tool.py

PURPOSE:
    Wraps an agent so another agent can call it as a tool.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/tools layer, which owns top-level tool contracts, catalogs, adapters, decorators, and execution helpers.
    It should be read with `vidbyte/tools/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.tools.base: imported by this file.
    - vidbyte.tools.types: imported by this file.

FUNCTION INVENTORY:
    - AgentTool (class): public or navigational symbol owned here.
    - AgentTool (export): public or navigational symbol owned here.

COMMON MODIFICATION PATTERNS:
    - When adding or removing a public symbol, update this header, the local `__all__` if present, and the nearest folder README file index.
    - When changing runtime behavior, update related docs or examples that describe the same contract before opening a PR.
    - When adding a new failure path, keep the error message safe for logs and include enough context for a future agent to route the fix.

WHAT NOT TO DO IN THIS FILE:
    1. Do not move responsibilities across SDK layers without updating the corresponding folder README and public exports.
    2. Do not add provider credentials, API keys, or unredacted prompt payloads to errors, metadata, traces, or comments.
    3. Do not edit generated cache files or make unrelated refactors while touching this file.

KNOWN EDGE CASES:
    - This SDK is in alpha and several files preserve compatibility exports; check `README.md` and `vidbyte/__init__.py` before renaming public symbols.
    - Agentic headers are living documentation. Re-run a header/code cross-check after changing imports, exports, errors, or concurrency behavior.

COMMON ERRORS RAISED BY THIS FILE:
    - None observed in this file; preserve this when adding new failure paths.

RELATED DOCS:
    - https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/system_prompt.md: source prompt for the agentic-engineering principles applied to this file.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/file_headers.md: file-header anatomy used for this header.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/function_design.md: function design guidance for future edits.
    - docs/design/agentic-engineering-principles-agents-middleware-tools.md: design record for this documentation pass.

TESTS:
    - python -m compileall vidbyte; tests/test_custom_function_tools.py and tool-related scripts when changing tool behavior.

CONCURRENCY MODEL:
    - Review async/task state carefully; this file participates in agent, middleware, tool, or actor execution.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent
    from vidbyte.agents.types import AgentMessage


class AgentTool(BaseTool):
    """Wraps a BaseAgent as a zero-parameter tool for use by a parent agent.

    When invoked, the parent's live context (history + active prompt) is
    serialized and forwarded to a fresh fork of the wrapped agent.
    """

    def __init__(self, agent: BaseAgent) -> None:
        self._agent = agent
        self._name = agent.agent_metadata.name
        self._description = self._build_agent_description()
        self._context_getter: Callable[[], tuple[str, list[Any]]] | None = None

    def bind_context_getter(
        self,
        getter: Callable[[], tuple[str, list[Any]]],
    ) -> None:
        """Bind a callable that returns (active_prompt, history) at call time."""
        self._context_getter = getter

    def clone_for_fork(self) -> AgentTool:
        # Returns an unbound wrapper around the same delegate agent for a forked parent.
        return AgentTool(self._agent)

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self._name,
            description=self._description,
            parameters=(),
            permission=ToolPermission.SAFE,
            metadata={"agent_name": self._agent.agent_metadata.name, "internal_agent_tool": True},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            if self._context_getter is not None:
                active_prompt, history = self._context_getter()
            else:
                active_prompt, history = "", []
            serialized = self._serialize_context(active_prompt, list(history))
            child = self._agent.fork()
            reply = await child.generate_reply(serialized)
            return ToolResult.success(
                self._name,
                reply.content,
                metadata={"agent_name": self._agent.agent_metadata.name},
            )
        except Exception as exc:
            return ToolResult.error(
                self._name,
                str(exc),
                metadata={"agent_name": self._agent.agent_metadata.name},
            )

    def _build_agent_description(self) -> str:
        meta = self._agent.agent_metadata
        return (
            f"Agent: {meta.name}\n"
            f"Description: {meta.description}\n"
            f"Use Cases: {meta.use_cases}\n"
            f"Use this tool to delegate tasks to the {meta.name} agent. "
            f"Calling this tool automatically passes the current conversation context."
        )

    @staticmethod
    def _serialize_context(active_prompt: str, history: list[AgentMessage]) -> str:
        """Serialize parent-agent context into a string for sub-agent consumption."""
        lines = ["<conversation_context>"]
        for msg in history:
            lines.append(f"[{msg.sender}]: {msg.content}")
        lines.append("</conversation_context>")
        if active_prompt:
            lines.extend(("", "<current_request>", active_prompt, "</current_request>"))
        return "\n".join(lines)


__all__ = ["AgentTool"]
