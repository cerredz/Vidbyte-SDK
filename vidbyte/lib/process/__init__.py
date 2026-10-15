"""FILE: vidbyte/lib/process/__init__.py

PURPOSE: Exposes the canonical process helpers: CliRunner (run a command-line program to completion within a timeout and an output cap) and ProcessStopper (stop and reap a child's whole process tree).
ROLE IN CODEBASE: Imported by the harness thread functions under vidbyte/harnesses/native/. The records they take and return live in vidbyte/lib/dataclasses/process.py.
ARCHITECTURE NOTE: Bottom-layer package (AGENTS.md principles 3 and 5): it imports only vidbyte.lib modules and the standard library, so any layer may use it. No child it starts inherits the caller's stdin.
FUNCTION INVENTORY: No functions. Re-exports CliRunner and ProcessStopper.
COMMON MODIFICATION PATTERNS: Add a new helper in its own module here and export it from this literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte.harnesses, vidbyte.tools or any higher layer (lint A006). 2. Do not add import-time side effects.
KNOWN EDGE CASES: Process-group stops are POSIX-only; on Windows the helpers use taskkill /T, which cannot reach a grandchild of a leader that already exited.
RELATED DOCS: vidbyte/lib/README.md
TESTS: tests/features/harness_threads/test_harness_threads_runner.py
"""

from __future__ import annotations

from vidbyte.lib.process.runner import CliRunner, ProcessStopper

__all__ = ["CliRunner", "ProcessStopper"]
