"""FILE: lint/rules/__init__.py

PURPOSE: Marks the package containing independently baselined SDK policies.
ROLE IN CODEBASE: Provides stable import paths for the explicit rule registry.
ARCHITECTURE NOTE: Rule modules are imported only through lint/core/registry.py.
FUNCTION INVENTORY: No functions; package marker only.
COMMON MODIFICATION PATTERNS: Keep this marker side-effect-free.
WHAT NOT TO DO: Do not auto-discover rules or import the vidbyte runtime here.
KNOWN EDGE CASES: Registry order is explicit so new files cannot silently become gates.
RELATED DOCS: lint/rules/README.md
TESTS: Exercised by RuleRegistry loading.
"""
