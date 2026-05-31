"""Context Protocol Header

Description:
    Defines a tool wrapper for scheduled adversarial critique.
Purpose:
    Lets context-window algorithms run a critic agent or callable and normalize
    the result as an ordinary SDK ToolResult.
Architecture:
    - AdversarialAgentTool: BaseTool implementation for adversarial critique.
Relations:
    Used by the adversarial reflection context-window algorithm.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Any

from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent

CritiqueCallable = Callable[[Mapping[str, Any]], Awaitable[str] | str]

_MAX_OUTPUT_CHARS_LIMIT = 1_000_000


class AdversarialAgentTool(BaseTool):
    """Wrap an adversarial agent or callable as a safe SDK tool."""

    def __init__(self, *, agent: BaseAgent | None = None, critique: CritiqueCallable | None = None, name: str = "adversarial_critique", description: str | None = None, max_output_chars: int = 2000) -> None:
        # Store one validated critique executor and bounded output settings.
        _validate_executor(agent, critique)
        _validate_name(name)
        _validate_max_output_chars(max_output_chars)
        self._agent = agent
        self._critique = critique
        self._name = name
        self._description = description or "Run an adversarial critique of the current agent trajectory."
        self._max_output_chars = max_output_chars

    def spec(self) -> ToolSpec:
        # Return the model-facing declaration for scheduled adversarial critique.
        return ToolSpec(
            name=self._name,
            description=self._description,
            parameters=(
                ToolParameter("task", "str", "Original task or user request."),
                ToolParameter("trajectory", "str", "Current bounded trajectory to critique."),
                ToolParameter("iteration_count", "int", "Current main-agent iteration count."),
                ToolParameter("critique_count", "int", "Number of critiques already produced."),
            ),
            permission=ToolPermission.SAFE,
            metadata={"internal": True, "adversarial_agent_tool": True},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Execute the configured critic and normalize its bounded text result.
        try:
            output = await self._run_executor(call.arguments)
            critique = self._capture_output(str(output))
            if not critique.strip():
                return ToolResult.error(self.name, "Adversarial critique returned empty output.", metadata={"error": "empty_critique"})
            return ToolResult.success(self.name, critique, metadata={"adversarial_agent_tool": True})
        except Exception as exc:
            return ToolResult.error(self.name, f"Adversarial critique failed: {exc}", metadata={"error": "execution_error", "error_type": type(exc).__name__})

    async def _run_executor(self, arguments: Mapping[str, Any]) -> str:
        # Dispatch to the wrapped agent or callable and return raw critique text.
        if self._agent is not None:
            child = self._agent.fork()
            reply = await child.generate_reply(self._serialize_arguments(arguments))
            return str(reply.content)
        assert self._critique is not None
        result = self._critique(dict(arguments))
        if inspect.isawaitable(result):
            result = await result
        return str(result)

    def _capture_output(self, output: str) -> str:
        # Strip and bound critique output before it reaches model-visible context.
        text = output.strip()
        suffix = "\n...[adversarial critique truncated]"
        if len(text) <= self._max_output_chars:
            return text
        if self._max_output_chars <= len(suffix):
            return suffix[-self._max_output_chars :]
        return text[: self._max_output_chars - len(suffix)].rstrip() + suffix

    @staticmethod
    def _serialize_arguments(arguments: Mapping[str, Any]) -> str:
        # Render tool arguments into a stable critique request for wrapped agents.
        return "\n\n".join(
            (
                "# Adversarial Critique Request",
                f"Task:\n{arguments.get('task', '')}",
                f"Iteration Count:\n{arguments.get('iteration_count', '')}",
                f"Prior Critique Count:\n{arguments.get('critique_count', '')}",
                f"Trajectory:\n{arguments.get('trajectory', '')}",
            )
        )


def _validate_executor(agent: object | None, critique: object | None) -> None:
    # Require exactly one executor so tool behavior is deterministic.
    if (agent is None and critique is None) or (agent is not None and critique is not None):
        raise ConfigurationError("AdversarialAgentTool requires exactly one of agent or critique.")


def _validate_name(name: str) -> None:
    # Reject empty tool names before ToolSpec construction.
    if not name.strip():
        raise ConfigurationError("AdversarialAgentTool name must be non-empty.")


def _validate_max_output_chars(max_output_chars: int) -> None:
    # Bound max_output_chars to avoid unbounded context injection.
    if max_output_chars <= 0:
        raise ConfigurationError("max_output_chars must be greater than zero.")
    if max_output_chars > _MAX_OUTPUT_CHARS_LIMIT:
        raise ConfigurationError(f"max_output_chars exceeds limit of {_MAX_OUTPUT_CHARS_LIMIT}.")


__all__ = [
    "AdversarialAgentTool",
    "CritiqueCallable",
]

