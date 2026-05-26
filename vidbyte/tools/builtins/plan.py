"""Context Protocol Header

Description:
    Built-in plan mode tools for entering and exiting read-only planning mode.
Purpose:
    Allows agents to activate a restricted planning context where only
    READ and SAFE tools are permitted, then exit when ready to implement.
Architecture:
    - enter_plan_mode: Activates the plan mode gate.
    - exit_plan_mode: Deactivates the plan mode gate.
Relations:
    Related to vidbyte.middleware.plan_mode.PlanModeMiddleware.
"""

from __future__ import annotations

from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission


@tool(permission=ToolPermission.SAFE)
async def enter_plan_mode(topic: str = "") -> str:
    """Enter read-only planning mode. Research and design only - no file writes or command execution.

    In plan mode, only READ and SAFE tools are available. Use exit_plan_mode when ready to implement.

    Args:
        topic: Optional description of what is being planned.
    """
    return f"Plan mode activated{' for: ' + topic if topic else ''}. Only READ and SAFE tools are available. Use exit_plan_mode when ready to implement."


@tool(permission=ToolPermission.SAFE)
async def exit_plan_mode(summary: str = "") -> str:
    """Exit plan mode and resume full tool access.

    Args:
        summary: Optional summary of the plan for the approval step.
    """
    return f"Plan mode deactivated{'. Plan summary submitted.' if summary else ''}. Full tool access restored."


__all__ = [
    "enter_plan_mode",
    "exit_plan_mode",
]
