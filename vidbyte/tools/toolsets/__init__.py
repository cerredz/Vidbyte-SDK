"""Context Protocol Header

Description:
    Exports reusable predefined tool catalogs for thin harnesses.
Purpose:
    Lets harnesses import a canonical toolset instead of assembling filesystem,
    search, and execution tools by hand.
Architecture:
    - ParadigmMinimalToolset: Minimal universal filesystem toolset.
Relations:
    Consumed by vidbyte.paradigms harnesses; composes vidbyte.tools builtins.
"""

from __future__ import annotations

from vidbyte.tools.toolsets.paradigm_minimal import ParadigmMinimalToolset

__all__ = [
    "ParadigmMinimalToolset",
]
