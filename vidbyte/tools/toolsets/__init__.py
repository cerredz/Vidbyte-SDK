"""Context Protocol Header

Description:
    Exports reusable predefined tool catalogs for thin harnesses.
Purpose:
    Lets harnesses import a canonical toolset instead of assembling filesystem,
    search, and execution tools by hand.
Architecture:
    - ParadigmMinimalToolset: Minimal universal filesystem toolset.
    - CodingAgentTools: The seven tools a CodingAgent starts with over one root folder.
    - PrebuiltTools: Category-selected catalog of the deterministic prebuilt utility tools.
Relations:
    Consumed by vidbyte.paradigms harnesses; composes vidbyte.tools builtins.
"""

from __future__ import annotations

from vidbyte.tools.toolsets.coding import CodingAgentTools
from vidbyte.tools.toolsets.paradigm_minimal import ParadigmMinimalToolset
from vidbyte.tools.toolsets.prebuilt import PrebuiltTools

__all__ = [
    "CodingAgentTools",
    "ParadigmMinimalToolset",
    "PrebuiltTools",
]
