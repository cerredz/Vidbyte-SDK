"""Context Protocol Header

Description:
    Re-exports LSP backend implementations.
Purpose:
    Provides a stable import surface for LSP provider backends without
    exposing internal implementation details.
Architecture:
    - BaseLspBackend: Abstract contract with Location and HoverInfo dataclasses.
    - AutoLspBackend: Language-aware fallback using AST-based static analysis.
Relations:
    Related to vidbyte.tools.builtins.lsp.
"""

from __future__ import annotations

from vidbyte.lib.providers.lsp.auto_backend import AutoLspBackend
from vidbyte.lib.providers.lsp.base import BaseLspBackend, HoverInfo, Location

__all__ = [
    "AutoLspBackend",
    "BaseLspBackend",
    "HoverInfo",
    "Location",
]
