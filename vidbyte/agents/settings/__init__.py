"""Context Protocol Header

Description:
    Public exports for the vidbyte.agents.settings sub-package.
Purpose:
    Exposes validated agent-loop, tool, and adversarial workflow settings.
Architecture:
    - AdversarialSettings: Portable immutable adversarial workflow controls.
    - AgentLoopSettings: Main loop settings object.
    - ToolErrorPolicy: Nested policy for tool-error retry/render behavior.
    - ToolSettings: Nested universal tool-use constraints.
Relations:
    Re-exported from vidbyte.agents.__init__; portable adversarial data lives in
    vidbyte.lib.dataclasses.adversarial.
"""

from vidbyte.lib.dataclasses.adversarial import AdversarialSettings
from vidbyte.agents.settings.loop import AgentLoopSettings
from vidbyte.agents.settings.tool import ToolSettings
from vidbyte.agents.settings.tool_error import ToolErrorPolicy, UnrecoverableAction

__all__ = ["AdversarialSettings", "AgentLoopSettings", "ToolErrorPolicy", "ToolSettings", "UnrecoverableAction"]
