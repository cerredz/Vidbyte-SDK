"""Context Protocol Header

Description:
    Exposes all swappable agent loop execution runtimes.
Purpose:
    Allows BaseAgent to dynamically import and dispatch different runtime loop
    paradigms (linear execution, search trees, and actor mailboxes).
Architecture:
    - LinearAgentRuntime: Sequential perception-action model-tool loop.
    - SearchTreeRuntimeComponent: Branching Monte Carlo Tree Search.
    - ActorRuntimeComponent: Asynchronous peer-to-peer actor message loop.
Relations:
    Imported by vidbyte.agents.base and the test harness suite.
Similar Files:
    - vidbyte/agents/base.py: Client class dispatching these runtimes.
"""

from __future__ import annotations

from vidbyte.agents.runtimes.linear import AgentRuntime as LinearAgentRuntime
from vidbyte.agents.runtimes.search import SearchTreeRuntimeComponent
from vidbyte.agents.runtimes.actor import ActorRuntimeComponent

__all__ = [
    "LinearAgentRuntime",
    "SearchTreeRuntimeComponent",
    "ActorRuntimeComponent",
]
