"""FILE: vidbyte/tools/integrations/__init__.py

PURPOSE: Namespaces provider-specific tools built by source integrations.
ROLE IN CODEBASE: Package boundary below the general SDK tool contract.
ARCHITECTURE NOTE: Concrete provider tools remain in their provider subpackages and are not auto-discovered here.
COMMON MODIFICATION PATTERNS: Add a provider subpackage and README when a concrete integration is introduced.
KNOWN EDGE CASES: Importing this namespace must not construct clients or perform I/O.
RELATED DOCS: docs/design/source-context-tools.md and vidbyte/tools/integrations/README.md
TESTS: tests/test_source_context_tools.py
"""
