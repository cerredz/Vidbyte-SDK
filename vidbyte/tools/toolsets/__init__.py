"""Context Protocol Header

Description:
    Exports reusable predefined tool catalogs for thin harnesses.
Purpose:
    Lets harnesses import a canonical toolset instead of assembling filesystem,
    search, and execution tools by hand.
Architecture:
    - ParadigmMinimalToolset: Minimal universal filesystem toolset.
    - CodingAgentTools: The seven tools a CodingAgent starts with over one root folder.
    - CodexHostTools: One tool per CodexHost function over one host.
    - InfiniteMemoryAgentTools: bash over the project folder plus grep and read_lines over the memory workspace.
    - AgentSwarmTools: bash, grep, read_lines, write_text and patch_file over one swarm's shared workplace folder, plus the selected web-search tool.
Relations:
    Consumed by vidbyte.paradigms harnesses; composes vidbyte.tools builtins.
"""

from __future__ import annotations

from vidbyte.tools.toolsets.agent_swarm import AgentSwarmTools
from vidbyte.tools.toolsets.codex import CodexHostTools
from vidbyte.tools.toolsets.coding import CodingAgentTools
from vidbyte.tools.toolsets.infinite import InfiniteMemoryAgentTools
from vidbyte.tools.toolsets.paradigm_minimal import ParadigmMinimalToolset

__all__ = [
    "AgentSwarmTools",
    "CodexHostTools",
    "CodingAgentTools",
    "InfiniteMemoryAgentTools",
    "ParadigmMinimalToolset",
]
