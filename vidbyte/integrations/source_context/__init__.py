"""FILE: vidbyte/integrations/source_context/__init__.py

PURPOSE: Exposes the public SourceContext class from its implementation module.
ROLE IN CODEBASE: Stable package import for source-to-context loading.
ARCHITECTURE NOTE: The package facade owns no validation, provider calls, or budget logic.
COMMON MODIFICATION PATTERNS: Re-export only public source-context symbols and keep implementation in context.py.
KNOWN EDGE CASES: Importing this facade must not perform network or CLI work.
RELATED DOCS: docs/design/source-context-tools.md and vidbyte/integrations/source_context/README.md
TESTS: tests/test_source_context_tools.py
"""

from vidbyte.integrations.source_context.context import SourceContext

__all__ = ["SourceContext"]
