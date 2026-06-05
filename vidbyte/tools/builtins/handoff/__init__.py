"""Context Protocol Header

Description:
    Exports the handoff-authoring builtin tool.
Purpose:
    Provides the package entry point for CreateHandoffTool.
Architecture:
    - create: CreateHandoffTool implementation.
Relations:
    Re-exported by vidbyte.tools.builtins and the vidbyte root namespace.
Similar Files:
    - vidbyte/tools/builtins/context_primitives/__init__.py: Sibling builtin package.
"""

from __future__ import annotations

from vidbyte.tools.builtins.handoff.create import CreateHandoffTool

__all__ = ["CreateHandoffTool"]
