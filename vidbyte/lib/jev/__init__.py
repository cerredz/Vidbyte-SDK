"""FILE: vidbyte/lib/jev/__init__.py

PURPOSE: Exposes the JevAgent capability substrate: the preflight flags (JevPresets) and the registry over every fixed preflight question (JevPreflightRegistry).
ROLE IN CODEBASE: vidbyte/agents/jev imports these to validate settings and to build the one preflight Jev request; the gate that acts on Jev's answers is JevPreflightGate in vidbyte/agents/jev/gate/.
ARCHITECTURE NOTE: This package sits in vidbyte.lib and imports only lib modules; it holds question text and flag policy but never calls Jev.
COMMON MODIFICATION PATTERNS: Add a flag in presets.py and its questions under preflight/; export only the classes JevAgent needs.
KNOWN EDGE CASES: Importing this package performs no Jev call and needs no TypeSafe credential.
RELATED DOCS: docs/design/jev-preflight-clarity.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_preflight.py and scripts/test-jev-preflight.py.
"""

from vidbyte.lib.jev.preflight import JevPreflightRegistry
from vidbyte.lib.jev.presets import JevPresets

__all__ = ["JevPreflightRegistry", "JevPresets"]
