"""FILE: lint/core/__init__.py

PURPOSE: Marks the lint engine infrastructure package.
ROLE IN CODEBASE: Provides import paths for discovery, analyzers, baselines, and reports.
ARCHITECTURE NOTE: Policy belongs in lint/rules, not this package marker.
FUNCTION INVENTORY: No functions; package marker only.
COMMON MODIFICATION PATTERNS: Keep this marker side-effect-free.
WHAT NOT TO DO: Do not eagerly construct registries or start analyzer subprocesses.
KNOWN EDGE CASES: Focused rule imports must remain cheap.
RELATED DOCS: lint/core/README.md
TESTS: Exercised by every lint command.
"""
