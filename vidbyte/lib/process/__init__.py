"""FILE: vidbyte/lib/process/__init__.py

PURPOSE: Exposes the canonical process helpers: CliRunner (run a command-line program to completion), ManagedProcess (own a long-running server child) and ProcessStopper (stop and reap a child's whole process tree).
ROLE IN CODEBASE: Imported by the native hosts under vidbyte/harnesses/native/ and by McpStdioTransport in vidbyte/tools/mcp/transport.py. The records they take and return live in vidbyte/lib/dataclasses/process.py.
ARCHITECTURE NOTE: Bottom-layer package (AGENTS.md principles 3 and 5): it imports only vidbyte.lib modules and the standard library, so any layer may use it. No child it starts inherits the caller's stdin.
FUNCTION INVENTORY: No functions. Re-exports CliRunner, ManagedProcess and ProcessStopper.
COMMON MODIFICATION PATTERNS: Add a new helper in its own module here and export it from this literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte.harnesses, vidbyte.tools or any higher layer (lint A006). 2. Do not add import-time side effects.
KNOWN EDGE CASES: Process-group stops are POSIX-only; on Windows the helpers use taskkill /T, which cannot reach a grandchild of a leader that already exited.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Process helpers); vidbyte/lib/README.md
TESTS: tests/features/grok_host/test_grok_host_process_helpers.py
"""

from __future__ import annotations

from vidbyte.lib.process.managed import ManagedProcess
from vidbyte.lib.process.runner import CliRunner, ProcessStopper

__all__ = ["CliRunner", "ManagedProcess", "ProcessStopper"]
