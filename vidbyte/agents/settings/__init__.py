"""Context Protocol Header

Description:
    Public exports for the vidbyte.agents.settings sub-package.
Purpose:
    Exposes AgentLoopSettings and nested settings objects for agentic loop
    parameters.
Architecture:
    - AgentLoopSettings: Main loop settings object.
    - AgentFallbackSettings: Ordered model fallback chain for an agent.
    - ToolErrorPolicy: Nested policy for tool-error retry/render behavior.
    - ToolSettings: Nested universal tool-use constraints.
Relations:
    Re-exported from vidbyte.agents.__init__.
"""

from vidbyte.agents.settings.fallback import AgentFallbackSettings
from vidbyte.agents.settings.loop import AgentLoopSettings
from vidbyte.agents.settings.tool import ToolSettings
from vidbyte.agents.settings.tool_error import ToolErrorPolicy, UnrecoverableAction

__all__ = ["AgentFallbackSettings", "AgentLoopSettings", "ToolErrorPolicy", "ToolSettings", "UnrecoverableAction"]
