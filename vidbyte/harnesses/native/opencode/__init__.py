"""FILE: vidbyte/harnesses/native/opencode/__init__.py

PURPOSE: Exports OpencodeHost, the native host that drives opencode through its HTTP server.
ROLE IN CODEBASE: The import path callers and vidbyte/tools/builtins/opencode/ use for the opencode host. Not re-exported from vidbyte.harnesses or the root package (D-15).
ARCHITECTURE NOTE: A package initializer that only re-exports; the host lives in host.py and its collaborators in client.py, server.py, turn.py and wire.py, which stay internal.
FUNCTION INVENTORY: No functions. Re-exports OpencodeHost.
COMMON MODIFICATION PATTERNS: A new public name of the opencode host package is added to the import and the literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not add import-time side effects. 2. Do not export OpencodeClient, OpencodeServer, OpencodeTurnWatcher or OpencodeWire; they are internal collaborators.
KNOWN EDGE CASES: None; the module only re-exports.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (OpencodeHost), §12.3 row 34
TESTS: tests/features/opencode_host/
"""

from __future__ import annotations

from vidbyte.harnesses.native.opencode.host import OpencodeHost

__all__ = ["OpencodeHost"]
