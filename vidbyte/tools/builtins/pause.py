"""Agentic pause built-in for cooperative, bounded waits inside an agent run.

FILE: vidbyte/tools/builtins/pause.py

PURPOSE:
    Defines the model-callable ``pause_agent`` tool. It validates a whole-number
    delay, enforces a developer-owned maximum, and delegates the actual wait to
    the live agent's public ``pause()`` method. This file must not grow durable
    run-control, checkpoint, or cross-agent lookup behavior.

ROLE IN CODEBASE:
    ``vidbyte.agents.base.BaseAgent`` binds this tool to the agent that owns it.
    ``vidbyte.agents.runtime.AgentRuntime`` executes it through the normal
    ``BaseTool`` contract, so existing permission, timeout, tracing, and result
    handling remain in force. ``vidbyte.tools.builtins`` exports the class and
    ``vidbyte.lib.registries.components.ComponentRegistry`` discovers that export
    for declarative configuration.

ARCHITECTURE NOTE:
    This is an agent-bound built-in, like the handoff and fork tools. A parent
    agent reaches another agent through the existing ``AgentTool`` abstraction;
    the pause request is not an arbitrary serialized agent reference. The wait
    is cooperative and cancellation-safe because the delegated agent method
    awaits ``asyncio.sleep`` without swallowing ``CancelledError``.

FUNCTION INVENTORY:
    ``PauseAgentTool`` -> ``BaseTool`` with ``spec()``, ``bind_agent()``,
    ``clone_for_fork()``, and ``execute()`` contracts described by the class
    body. Validation helpers are private implementation details. No
    feature-specific test file is added by the deterministic-agent-pause design;
    verify through the repository CI gate.

COMMON MODIFICATION PATTERNS:
    Add model-facing arguments in ``spec()`` and ``_input_schema()`` together.
    Preserve strict integer validation and the configured maximum. If the tool's
    ownership or binding model changes, update ``BaseAgent._bind_agent_tool_context``
    and ``docs/design/deterministic-agent-pause.md`` in the same change.

WHAT NOT TO DO IN THIS FILE:
    1. Do not call ``time.sleep``; event-loop scheduling belongs to the async
       ``BaseAgent.pause`` contract.
    2. Do not catch ``asyncio.CancelledError`` or turn a runtime timeout into a
       successful ``ToolResult``; ``AgentRuntime`` owns those boundaries.
    3. Do not persist pause state or update run status; sessions and future run
       control APIs own durable lifecycle state.
    4. Do not accept an agent name or id and look it up; agent ownership is
       established by ``BaseAgent`` binding and existing ``AgentTool`` calls.

KNOWN EDGE CASES:
    ``bool`` must be rejected even though it subclasses ``int`` in Python.
    Zero is a valid delay and intentionally yields through ``asyncio.sleep(0)``.
    A tool constructed without a binding returns a normal tool error, while
    cancellation of a bound task propagates out of ``execute()``.

RELATED DOCS:
    Deterministic agent pause design:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/deterministic-agent-pause.md
    Built-in export and registry contract:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/lib/registries/components.py

TEST FILES:
    No new feature test file by design. Run ``python scripts/run_ci.py`` after
    implementation; the existing tool, agent, source, and package gates apply.

CONCURRENCY MODEL:
    The tool stores only its bound agent and immutable maximum configuration.
    Each invocation waits in the caller's task; no lock, thread, global state,
    or shared timer is introduced.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent


_TOOL_NAME = "pause_agent"
_DEFAULT_MAX_SECONDS = 60
_MIN_SECONDS = 0


class PauseAgentTool(BaseTool):
    """Bound built-in that pauses its owning agent for a bounded duration."""

    def __init__(self, max_seconds: int = _DEFAULT_MAX_SECONDS) -> None:
        # Store the developer cap and start unbound until BaseAgent attaches this tool.
        self._max_seconds = self._validate_max_seconds(max_seconds)
        self._agent: BaseAgent | None = None

    def bind_agent(self, agent: BaseAgent) -> None:
        # Attach the concrete agent whose task the tool is allowed to pause.
        self._agent = agent

    def clone_for_fork(self) -> PauseAgentTool:
        # Return an unbound copy so a forked agent cannot steal the parent's binding.
        return PauseAgentTool(max_seconds=self._max_seconds)

    def spec(self) -> ToolSpec:
        # Return the model-facing declaration with the configured duration bound.
        return ToolSpec(
            name=_TOOL_NAME,
            description=(
                f"Pause the agent that owns this tool for a whole number of seconds. "
                f"Allowed range: {_MIN_SECONDS} to {self._max_seconds} seconds."
            ),
            parameters=(
                ToolParameter(
                    name="seconds",
                    type="integer",
                    description=f"Number of seconds to pause, from {_MIN_SECONDS} to {self._max_seconds}.",
                    required=True,
                ),
            ),
            permission=ToolPermission.SAFE,
            input_schema=self._input_schema(),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Validate the request, delegate the cooperative wait, and confirm completion.
        if self._agent is None:
            return ToolResult.error(_TOOL_NAME, "pause_agent is not bound to an agent.")
        try:
            seconds = self._normalize_seconds(call.arguments.get("seconds"))
            await self._agent.pause(seconds)
        except ValueError as exc:
            return ToolResult.error(_TOOL_NAME, str(exc))
        return ToolResult.success(
            _TOOL_NAME,
            f"Paused the agent for {seconds} second(s).",
            metadata={"seconds": seconds},
        )

    def _input_schema(self) -> dict[str, Any]:
        # Return a provider-facing schema that mirrors the runtime validation rules.
        return {
            "type": "object",
            "required": ["seconds"],
            "additionalProperties": False,
            "properties": {
                "seconds": {
                    "type": "integer",
                    "minimum": _MIN_SECONDS,
                    "maximum": self._max_seconds,
                    "description": f"Number of seconds to pause, from {_MIN_SECONDS} to {self._max_seconds}.",
                },
            },
        }

    @staticmethod
    def _validate_max_seconds(value: object) -> int:
        # Validate the positive developer-owned maximum before the tool is usable.
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("PauseAgentTool.max_seconds must be an integer.")
        if value <= _MIN_SECONDS:
            raise ValueError("PauseAgentTool.max_seconds must be greater than zero.")
        return value

    def _normalize_seconds(self, value: object) -> int:
        # Validate one model-provided duration against the tool's inclusive bounds.
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("pause_agent 'seconds' must be an integer.")
        if value < _MIN_SECONDS:
            raise ValueError("pause_agent 'seconds' must be non-negative.")
        if value > self._max_seconds:
            raise ValueError(f"pause_agent 'seconds' must not exceed {self._max_seconds}.")
        return value


__all__ = ["PauseAgentTool"]
