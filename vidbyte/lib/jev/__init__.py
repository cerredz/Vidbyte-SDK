"""FILE: vidbyte/lib/jev/__init__.py

PURPOSE: Exposes the JevAgent capability substrate: the preflight flags (JevPresets) and the preflight question registry and logic (JevPreflight).
ROLE IN CODEBASE: vidbyte/agents/jev imports these to validate settings and run preflight without owning any question text or scoring itself.
ARCHITECTURE NOTE: This package sits in vidbyte.lib and imports only lib modules; it reaches decision usage parsing through ModelProvider.usage_class instead of importing the agents layer.
COMMON MODIFICATION PATTERNS: Add a flag in presets.py and its questions under preflight/; export only the classes JevAgent needs.
KNOWN EDGE CASES: Importing this package performs no Jev call and needs no TypeSafe credential.
RELATED DOCS: docs/design/jev-preflight-clarity.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_preflight.py and scripts/test-jev-preflight.py.
"""

from vidbyte.lib.jev.preflight import JevPreflight
from vidbyte.lib.jev.presets import JevPresets

__all__ = ["JevPreflight", "JevPresets"]
