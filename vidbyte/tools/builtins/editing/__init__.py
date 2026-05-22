"""Context Protocol Header

Description:
    Exports built-in editing tools.
Purpose:
    Provides a stable import surface for exact patch/edit primitives.
Architecture:
    - PatchTool: Applies exact root-scoped search/replace edits.
Relations:
    Related to vidbyte.tools.builtins and vidbyte.tools.security.
"""

from __future__ import annotations

from vidbyte.tools.builtins.editing.patch import PatchTool

__all__ = [
    "PatchTool",
]
