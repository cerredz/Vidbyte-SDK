"""FILE: vidbyte/harnesses/native/grok/__init__.py

PURPOSE: The Grok Build subpackage of the harness thread functions; it will export run_grok_thread, continue_grok_thread and fork_grok_thread once its threads module lands.
ROLE IN CODEBASE: Imported by vidbyte/harnesses/native/__init__.py. Nothing here is re-exported from vidbyte or vidbyte.harnesses.
ARCHITECTURE NOTE: A package initializer that only re-exports; it exports nothing yet while the rejected host design is removed.
FUNCTION INVENTORY: No functions. Exports nothing yet.
COMMON MODIFICATION PATTERNS: Bind each public function to its class attribute and list it in the literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not add import-time side effects such as finding the grok executable.
KNOWN EDGE CASES: None; the module defines no names.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: tests/features/harness_threads/
"""

from __future__ import annotations

__all__: list[str] = []
