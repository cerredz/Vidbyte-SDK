"""FILE: vidbyte/harnesses/native/hostkit/__init__.py

PURPOSE: Exposes the plumbing all three native hosts share: NativeErrorFactory (builds and scrubs errors), NativeTurnTable (reserved, live and finished turns), NativePeer (one JSON-RPC stdio peer) and NativeChildEnvironment (the caller's environment plus a host overlay).
ROLE IN CODEBASE: Imported by vidbyte.harnesses.native.grok, .opencode and .muse only. It is internal: nothing here is re-exported from vidbyte.harnesses or the root package.
ARCHITECTURE NOTE: Lives under harnesses/native rather than vidbyte.lib because scrubbing uses HarnessRedactor from vidbyte.harnesses.serialization and lib may not import upward (D-22). The folder name belongs to this feature, so it cannot collide with other hosts' files under native/.
FUNCTION INVENTORY: No functions. Re-exports NativeErrorFactory, NativeTurnTable, NativePeer and NativeChildEnvironment.
COMMON MODIFICATION PATTERNS: Plumbing a second host needs goes here, in its own module, and is exported from this literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not import a host package here; hosts import hostkit, never the reverse. 2. Do not add import-time side effects.
KNOWN EDGE CASES: None; the module only re-exports.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (Shared host plumbing), D-22; vidbyte/harnesses/README.md
TESTS: tests/features/grok_host/test_grok_host_shared_contract.py
"""

from __future__ import annotations

from vidbyte.harnesses.native.hostkit.errors import NativeErrorFactory
from vidbyte.harnesses.native.hostkit.peers import NativeChildEnvironment, NativePeer
from vidbyte.harnesses.native.hostkit.turns import NativeTurnTable

__all__ = ["NativeChildEnvironment", "NativeErrorFactory", "NativePeer", "NativeTurnTable"]
