"""Context Protocol Header

Description:
    Compatibility redirection module for AgentRuntime.
Purpose:
    Maintains backward compatibility for imports from vidbyte.agents.runtime
    after the runtimes were refactored into the vidbyte.agents.runtimes subpackage.
Architecture:
    Redirection module forwarding imports to vidbyte.agents.runtimes.linear.
Relations:
    Located in vidbyte/agents/runtime.py. Forwards to vidbyte/agents/runtimes/linear.py.
"""

from __future__ import annotations

from vidbyte.agents.runtimes.linear import AgentRuntime

__all__ = [
    "AgentRuntime",
]
