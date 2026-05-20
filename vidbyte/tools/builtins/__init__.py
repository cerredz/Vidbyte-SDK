# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the built-ins module exports for Vidbyte SDK Tools.
# Purpose: Bundles all standardized built-in tools for clean imports.
# Architecture & Functions:
#   - Exports CalculatorTool, WebSearchTool, CodeExecutionTool, DocumentRetrievalTool.
# Codebase Relation:
#   - Exposes tools under vidbyte.tools.builtins namespace.
# Similar Files:
#   - vidbyte/prompts/builtins/__init__.py (prompts counterpart)
# ==============================================================================

from __future__ import annotations

from vidbyte.tools.builtins.calculator import CalculatorTool
from vidbyte.tools.builtins.code_execution import CodeExecutionTool
from vidbyte.tools.builtins.document_retrieval import DocumentRetrievalTool
from vidbyte.tools.builtins.web_search import WebSearchTool

__all__ = [
    "CalculatorTool",
    "WebSearchTool",
    "CodeExecutionTool",
    "DocumentRetrievalTool",
]
