"""FILE: vidbyte/tools/builtins/operations/__init__.py

PURPOSE:
    Exports the priced search/fetch tool vocabulary and its executor contract.
ROLE IN CODEBASE:
    Re-exported by vidbyte.tools.builtins; applications import concrete tools and
    OperationExecutor from this package without auto-registering instances.
ARCHITECTURE NOTE:
    Concrete schemas remain provider-specific while PricedOperationTool owns the
    shared execution and usage boundary.
FUNCTION INVENTORY:
    OperationExecutor and PricedOperationTool plus all supported operation tools.
COMMON MODIFICATION PATTERNS:
    Export a new concrete operation tool here after defining and testing it.
WHAT NOT TO DO IN THIS FILE:
    1. Do not instantiate or auto-register tools.
KNOWN EDGE CASES:
    This module is a public import surface; removing names is a breaking change.
RELATED DOCS:
    vidbyte/tools/builtins/operations/README.md
TESTS:
    tests/features/priced_operation_executor/test_contract.py
"""

from __future__ import annotations

from vidbyte.tools.builtins.operations.base import (
    OperationExecutor,
    PricedOperationTool,
)
from vidbyte.tools.builtins.operations.fetch import (
    DirectHttpFetchTool,
    FirecrawlFetchTool,
    LinkupFetchTool,
    ParallelExtractTool,
    TavilyExtractTool,
)
from vidbyte.tools.builtins.operations.search import (
    BraveSearchTool,
    ExaSearchTool,
    LinkupSearchTool,
    OpenAlexSearchTool,
    ParallelSearchTool,
    SemanticScholarSearchTool,
    TavilySearchTool,
)

__all__ = [
    "BraveSearchTool",
    "DirectHttpFetchTool",
    "ExaSearchTool",
    "FirecrawlFetchTool",
    "LinkupFetchTool",
    "LinkupSearchTool",
    "OpenAlexSearchTool",
    "OperationExecutor",
    "ParallelExtractTool",
    "ParallelSearchTool",
    "PricedOperationTool",
    "SemanticScholarSearchTool",
    "TavilyExtractTool",
    "TavilySearchTool",
]
