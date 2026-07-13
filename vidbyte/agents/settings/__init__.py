"""Context Protocol Header

PURPOSE:
    Public export surface for the vidbyte.agents.settings sub-package, exposing
    AgentLoopSettings and its nested settings objects for agentic loop parameters.
ROLE IN CODEBASE:
    Imported by vidbyte.agents.base and re-exported from vidbyte.agents.__init__
    so callers configure loop budgets and tool policy without importing internals.
ARCHITECTURE:
    - AgentLoopSettings: main loop settings object.
    - ToolErrorPolicy / UnrecoverableAction: nested tool-error retry policy.
    - ToolSettings: nested universal tool-use constraints.
FUNCTION INVENTORY:
    - (package init) re-exports AgentLoopSettings, ToolSettings, ToolErrorPolicy,
      and UnrecoverableAction; no callable logic lives here.
"""

from vidbyte.agents.settings.loop import AgentLoopSettings
from vidbyte.agents.settings.tool import ToolSettings
from vidbyte.agents.settings.tool_error import ToolErrorPolicy, UnrecoverableAction

__all__ = ["AgentLoopSettings", "ToolErrorPolicy", "ToolSettings", "UnrecoverableAction"]
