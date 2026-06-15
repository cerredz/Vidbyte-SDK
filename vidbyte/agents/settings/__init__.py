"""Context Protocol Header

Description:
    Public exports for the vidbyte.agents.settings sub-package.
Purpose:
    Exposes AgentLoopSettings as the developer-facing configuration object
    for all agentic loop parameters.
Architecture:
    - AgentLoopSettings: The only public export from this sub-package.
Relations:
    Re-exported from vidbyte.agents.__init__.
"""

from vidbyte.agents.settings.loop import AgentLoopSettings

__all__ = ["AgentLoopSettings"]
