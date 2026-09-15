"""FILE: vidbyte/integrations/source_tool/__init__.py

PURPOSE: Exposes the public SourceTool class from its implementation module.
ROLE IN CODEBASE: Stable package import for repository-tool construction.
ARCHITECTURE NOTE: The package facade owns no provider request or model-argument validation.
COMMON MODIFICATION PATTERNS: Re-export only public source-tool symbols and keep composition in builder.py.
KNOWN EDGE CASES: Importing this facade must not perform network or CLI work.
RELATED DOCS: docs/design/source-context-tools.md and vidbyte/integrations/source_tool/README.md
TESTS: tests/test_source_context_tools.py
"""

from vidbyte.integrations.source_tool.builder import SourceTool

__all__ = ["SourceTool"]
