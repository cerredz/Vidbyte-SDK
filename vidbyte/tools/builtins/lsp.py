"""Context Protocol Header

Description:
    Built-in LSP tools for code analysis including definitions, references,
    hover info, diagnostics, symbols, call hierarchy, type definitions, and
    formatting.
Purpose:
    Provides code intelligence tools for agents using AST-based static analysis
    as a fallback when no full LSP server is available.
Architecture:
    - Uses AutoLspBackend for language-aware analysis.
    - Python files use AST-based analysis for definitions, references, symbols.
    - Advanced features (call hierarchy, type definition, formatting) return
      descriptive messages when no LSP server is available.
    - Each tool is an async function decorated with @tool.
Relations:
    Related to vidbyte.lib.providers.lsp and vidbyte.tools.decorators.
"""

from __future__ import annotations

import json
import os

from vidbyte.lib.providers.lsp.auto_backend import AutoLspBackend
from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission


@tool(permission=ToolPermission.READ)
async def lsp_definition(file_path: str, line: int, character: int) -> str:
    """Find the definition of a symbol at the given location.

    Args:
        file_path: Path to the source file
        line: Line number (1-indexed)
        character: Character offset (0-indexed)
    """
    backend = AutoLspBackend()
    language = backend._detect_language(file_path)
    if not await backend.is_available():
        return "Error: LSP backend not available."
    try:
        await backend.initialize(file_path, language)
        locations = await backend.definition(file_path, line, character)
        if not locations:
            return f"No definitions found at {file_path}:{line}:{character}"
        return json.dumps([{"uri": loc.uri, "line": loc.line, "character": loc.character} for loc in locations], indent=2)
    except Exception as exc:
        return f"LSP definition error: {exc}"


@tool(permission=ToolPermission.READ)
async def lsp_references(file_path: str, line: int, character: int, include_declaration: bool = False) -> str:
    """Find all references to a symbol at the given location.

    Args:
        file_path: Path to the source file
        line: Line number (1-indexed)
        character: Character offset (0-indexed)
        include_declaration: Whether to include the declaration itself (default: False)
    """
    backend = AutoLspBackend()
    language = backend._detect_language(file_path)
    if not await backend.is_available():
        return "Error: LSP backend not available."
    try:
        await backend.initialize(file_path, language)
        locations = await backend.references(file_path, line, character)
        if not locations:
            return f"No references found for symbol at {file_path}:{line}:{character}"
        return json.dumps([{"uri": loc.uri, "line": loc.line, "character": loc.character} for loc in locations], indent=2)
    except Exception as exc:
        return f"LSP references error: {exc}"


@tool(permission=ToolPermission.READ)
async def lsp_hover(file_path: str, line: int, character: int) -> str:
    """Get hover information for a symbol at the given location.

    Args:
        file_path: Path to the source file
        line: Line number (1-indexed)
        character: Character offset (0-indexed)
    """
    backend = AutoLspBackend()
    language = backend._detect_language(file_path)
    if not await backend.is_available():
        return "Error: LSP backend not available."
    try:
        await backend.initialize(file_path, language)
        hover = await backend.hover(file_path, line, character)
        if hover is None:
            return f"No hover information at {file_path}:{line}:{character}"
        return hover.contents
    except Exception as exc:
        return f"LSP hover error: {exc}"


@tool(permission=ToolPermission.READ)
async def lsp_diagnostics(file_path: str) -> str:
    """Get diagnostics for a file.

    Args:
        file_path: Path to the source file
    """
    backend = AutoLspBackend()
    language = backend._detect_language(file_path)
    if not await backend.is_available():
        return "Error: LSP backend not available."
    try:
        await backend.initialize(file_path, language)
        diagnostics = await backend.diagnostics(file_path)
        if not diagnostics:
            return f"No diagnostics for {file_path}"
        return "\n".join(diagnostics)
    except Exception as exc:
        return f"LSP diagnostics error: {exc}"


@tool(permission=ToolPermission.READ)
async def lsp_symbols(file_path: str | None = None) -> str:
    """Get document or workspace symbols.

    Args:
        file_path: Optional path to a specific file. If omitted, returns workspace symbols.
    """
    backend = AutoLspBackend()
    if file_path is not None:
        language = backend._detect_language(file_path)
    else:
        language = "unknown"
    if not await backend.is_available():
        return "Error: LSP backend not available."
    try:
        await backend.initialize(file_path or os.getcwd(), language)
        symbols = await backend.symbols(file_path)
        if not symbols:
            return "No symbols found"
        return json.dumps(symbols, indent=2)
    except Exception as exc:
        return f"LSP symbols error: {exc}"


@tool(permission=ToolPermission.READ)
async def lsp_call_hierarchy(file_path: str, line: int, character: int, direction: str = "incoming") -> str:
    """Get call hierarchy for a symbol.

    Args:
        file_path: Path to the source file
        line: Line number (1-indexed)
        character: Character offset (0-indexed)
        direction: 'incoming' (default) or 'outgoing'
    """
    return "Not yet implemented — requires full LSP server"


@tool(permission=ToolPermission.READ)
async def lsp_type_definition(file_path: str, line: int, character: int) -> str:
    """Find the type definition of a symbol.

    Args:
        file_path: Path to the source file
        line: Line number (1-indexed)
        character: Character offset (0-indexed)
    """
    return "Not yet implemented — requires full LSP server"


@tool(permission=ToolPermission.READ)
async def lsp_format(file_path: str) -> str:
    """Format a source file.

    Args:
        file_path: Path to the source file
    """
    return "Formatting not available without LSP server"
