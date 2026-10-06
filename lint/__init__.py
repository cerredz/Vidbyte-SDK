"""FILE: lint/__init__.py

PURPOSE: Marks the repository-local SDK lint package.
ROLE IN CODEBASE: Enables absolute imports from lint/run.py and rule modules.
ARCHITECTURE NOTE: This package is repository tooling and is not distributed.
FUNCTION INVENTORY: No functions; package marker only.
COMMON MODIFICATION PATTERNS: Keep this marker side-effect-free.
WHAT NOT TO DO: Do not import analyzers or the vidbyte runtime here.
KNOWN EDGE CASES: The package is executed from source in Windows and POSIX worktrees.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py imports.
"""
