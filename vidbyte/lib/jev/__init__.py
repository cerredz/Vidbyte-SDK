"""FILE: vidbyte/lib/jev/__init__.py

PURPOSE: Exposes the JevAgent capability substrate: shared decision handling, preflight flags and questions, and done-check questions and thresholds.
ROLE IN CODEBASE: vidbyte/agents/jev imports these to validate settings, ask Jev, and score its answers; the agents layer retains each feature's actions and fail-open policy.
ARCHITECTURE NOTE: This package sits in vidbyte.lib and imports only lib modules. DecisionModelHelper composes the transport runner with canonical question scoring; question registries hold fixed questions and feature thresholds.
COMMON MODIFICATION PATTERNS: Add shared provider-independent answer handling to DecisionModelHelper, add a flag in presets.py and its questions under preflight/, or add a done check and its questions under done/; export the classes JevAgent needs.
KNOWN EDGE CASES: Importing this package performs no Jev call and needs no TypeSafe credential.
RELATED DOCS: docs/design/jev-preflight-clarity.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_preflight.py and scripts/test-jev-preflight.py.
"""

from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.jev.done import JevDoneRegistry
from vidbyte.lib.jev.preflight import JevPreflightRegistry
from vidbyte.lib.jev.presets import JevPresets

__all__ = ["DecisionModelHelper", "JevDoneRegistry", "JevPreflightRegistry", "JevPresets"]
