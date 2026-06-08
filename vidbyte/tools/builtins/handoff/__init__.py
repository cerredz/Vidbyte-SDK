"""Context Protocol Header

Description:
    Exports the handoff builtin tool package.
Purpose:
    Provides the public entry point for CreateHandoffTool.
Architecture:
    - create: CreateHandoffTool implementation.
Relations:
    Re-exported by vidbyte.tools.builtins and vidbyte root namespace.
Similar Files:
    - vidbyte/tools/builtins/context_primitives/__init__.py: Other builtin tool packages.
"""

from __future__ import annotations

from vidbyte.tools.builtins.handoff.create import CreateHandoffTool

__all__ = ["CreateHandoffTool"]
