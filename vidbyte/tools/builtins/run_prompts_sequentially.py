"""Context Protocol Header

Description:
    Implements RunPromptsSequentiallyTool — a model-callable builtin for queuing
    follow-up prompts that run sequentially after the current run completes.
Purpose:
    Lets the model schedule its own continuation: each queued prompt becomes a
    full run of the same agent (shared history) once the active agentic loop and
    runtime have finished. The model-facing form of BaseAgent.arun_sequentially().
Architecture:
    - RunPromptsSequentiallyTool: BaseTool bound to a live agent that validates a
      prompts array and appends it to the agent's queue via enqueue_prompts().
Relations:
    Bound by vidbyte.agents.base.BaseAgent._bind_agent_tool_context. Drained by
    BaseAgent._drain_queued_prompts at the end of generate_reply().
Similar Files:
    - vidbyte/tools/builtins/handoff/create.py: Other agent-bound builtin.
    - vidbyte/tools/builtins/trajectory_checkpoint.py: Other single-file builtin.
"""

from __future__ import annotations

from typing import Any

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec

_DESCRIPTION = (
    "Queue follow-up prompts that will each run as a fresh, full run of this same agent, "
    "in order, AFTER the current run finishes. The prompts are not executed immediately — "
    "this tool call only schedules them. Every queued run shares this agent's conversation "
    "history, tools, and context, so later prompts see the results of earlier ones. "
    "Use this to continue with multi-phase work once your current task completes."
)


class RunPromptsSequentiallyTool(BaseTool):
    """Builtin tool that queues follow-up prompts to run sequentially after the current run."""

    def __init__(self) -> None:
        # Starts unbound; BaseAgent attaches the live agent via bind_agent().
        self._agent: Any = None

    def bind_agent(self, agent: Any) -> None:
        """Attach the live agent whose queue receives the prompts."""
        self._agent = agent

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration with a JSON-Schema prompts array."""
        return ToolSpec(
            name="run_prompts_sequentially",
            description=_DESCRIPTION,
            permission=ToolPermission.SAFE,
            input_schema=self._input_schema(),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Validate the prompts array and enqueue it on the bound agent."""
        if self._agent is None:
            return ToolResult.error("run_prompts_sequentially", "run_prompts_sequentially is not bound to an agent.")
        try:
            raw_prompts = call.arguments.get("prompts")
            queue_size = self._agent.enqueue_prompts(raw_prompts)
        except ValueError as exc:
            return ToolResult.error("run_prompts_sequentially", str(exc))
        prompts = [prompt.strip() for prompt in raw_prompts]
        return ToolResult.success(
            "run_prompts_sequentially",
            self._render_confirmation(prompts, queue_size),
            metadata={"queued": len(prompts), "queue_size": queue_size},
        )

    def _render_confirmation(self, prompts: list[str], queue_size: int) -> str:
        """Render the queued-prompts confirmation the model reads back."""
        lines = [f"Queued {len(prompts)} prompt(s) to run in order after the current run finishes:"]
        lines.extend(f"{index}. {prompt}" for index, prompt in enumerate(prompts, start=1))
        lines.append(f"Pending queue size: {queue_size}.")
        return "\n".join(lines)

    def _input_schema(self) -> dict[str, Any]:
        """Return the JSON Schema for the tool's inputs."""
        return {
            "type": "object",
            "required": ["prompts"],
            "additionalProperties": False,
            "properties": {
                "prompts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": (
                        "Prompts to run in order after the current run completes. "
                        "Each becomes a full agent run sharing this agent's history."
                    ),
                },
            },
        }


__all__ = ["RunPromptsSequentiallyTool"]
