"""Context Protocol Header

Description:
    Compatibility shim re-exporting AgentRuntime as LinearAgentRuntime.
Purpose:
    Keeps the vidbyte.agents.runtimes.linear import path stable after the canonical
    AgentRuntime implementation was consolidated into vidbyte.agents.runtime.
Architecture:
    Thin re-export — no logic lives here.
Relations:
    Located in vidbyte/agents/runtimes/linear.py. Source of truth is vidbyte/agents/runtime.py.
Similar Files:
    - vidbyte/agents/runtime.py: Canonical AgentRuntime implementation.
"""

from __future__ import annotations

from vidbyte.agents.runtime import AgentRuntime

__all__ = ["AgentRuntime"]
