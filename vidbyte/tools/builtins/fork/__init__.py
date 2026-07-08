"""Context Protocol Header

Description:
    Exports the fork_conversation builtin tool.
Purpose:
    Keeps the agent self-forking builtin importable from the builtins namespace.
Architecture:
    - ForkConversationTool: Agent-bound tool that runs a modified child fork inline.
Relations:
    Bound by vidbyte.agents.base.BaseAgent._bind_agent_tool_context.
"""

from __future__ import annotations

from vidbyte.tools.builtins.fork.fork import ForkConversationTool

__all__ = ["ForkConversationTool"]
