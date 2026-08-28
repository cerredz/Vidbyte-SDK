"""Context Protocol Header

Description:
    Defines AgentKeyKind, the closed set of envelope kinds AgentKeys stores.
Purpose:
    Replaces AgentKeys' five private string constants with a strongly-typed
    enum so every kind tag written into an envelope is a validated member,
    not an unchecked string literal.
Architecture:
    - AgentKeyKind: String-backed Enum naming each AgentKeys envelope kind
      (settings, response, toolset, tool_call, step, identity).
Relations:
    Consumed by vidbyte.agents.settings.keys.AgentKeys.
Similar Files:
    - vidbyte/lib/enums/agent_runtime.py
"""

from __future__ import annotations

from enum import Enum


class AgentKeyKind(str, Enum):
    """String-backed enum naming each kind of envelope AgentKeys stores."""

    SETTINGS = "settings"
    RESPONSE = "response"
    TOOLSET = "toolset"
    TOOL_CALL = "tool_call"
    STEP = "step"
    IDENTITY = "identity"


__all__ = ["AgentKeyKind"]
