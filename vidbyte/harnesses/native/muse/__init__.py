"""FILE: vidbyte/harnesses/native/muse/__init__.py

PURPOSE: Exports the Muse host's public API: MuseHost, the async context manager over the user's own Muse Code (`muse serve`, MSP 1.0.1), natively or inside a WSL distro.
ROLE IN CODEBASE: Imported by vidbyte/tools/builtins/muse/ and vidbyte/tools/toolsets/muse.py, and by callers who drive Muse directly. Not re-exported from vidbyte.harnesses or the root package (D-15).
ARCHITECTURE NOTE: A package initializer that only re-exports; the host lives in host.py, the codec in wire.py, the launcher in launcher.py and the turn driver in turn.py.
FUNCTION INVENTORY: No functions. Re-exports MuseHost.
COMMON MODIFICATION PATTERNS: A new public Muse name is added to the import and the literal __all__.
WHAT NOT TO DO IN THIS FILE: 1. Do not add import-time side effects. 2. Do not export MuseWire, MuseLauncher or MuseTurnDriver; they are internal to the host.
KNOWN EDGE CASES: None; the module only re-exports.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §8.5 (MuseHost)
TESTS: tests/features/muse_host/test_muse_host_acceptance.py
"""

from __future__ import annotations

from vidbyte.harnesses.native.muse.host import MuseHost

__all__ = ["MuseHost"]
