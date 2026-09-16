"""FILE: vidbyte/integrations/__init__.py

PURPOSE: Exposes the public source-integration surface for external provider resources.
ROLE IN CODEBASE: Re-exports SourceContext and SourceTool so developers import both from one stable namespace.
ARCHITECTURE NOTE: Only the two public classes are exported; configs, clients, and budgets stay on their owning modules.
COMMON MODIFICATION PATTERNS: Add a new public class to the import tuple and __all__ together, in alphabetical order.
KNOWN EDGE CASES: Concrete modules carry the A006-relevant imports; this facade is excluded from the dependency graph.
RELATED DOCS: docs/design/source-context-tools.md and vidbyte/integrations/README.md.
TESTS: tests/test_source_context_tools.py and scripts/test-source-context-tools.py.
"""

from __future__ import annotations

from vidbyte.integrations.source_context import SourceContext
from vidbyte.integrations.source_tool import SourceTool

__all__ = [
    "SourceContext",
    "SourceTool",
]
