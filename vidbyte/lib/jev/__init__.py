"""FILE: vidbyte/lib/jev/__init__.py

PURPOSE: Groups the shared JevAgent policy vocabulary: enable-able presets and the canonical fixed preflight questions.
ROLE IN CODEBASE: `vidbyte/agents/jev/` imports presets and the preflight registry from here; nothing here imports the agents layer.
ARCHITECTURE NOTE: Kept in `vidbyte.lib` so settings, runtime, and tests share one definition; wire records stay in `vidbyte/lib/dataclasses/jev.py` and enums in `vidbyte/lib/enums/jev.py`.
COMMON MODIFICATION PATTERNS: Add preset validation to presets.py and fixed questions under preflight/.
KNOWN EDGE CASES: Importing this package performs no Jev call.
RELATED DOCS: docs/design/jev-preflight-sensitive-data.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_sensitive_preflight.py and tests/test_jev_tool_selector.py.
"""

from vidbyte.lib.jev.preflight import SECURITY_QUESTIONS, JevPreflightRegistry
from vidbyte.lib.jev.presets import JevPresets

__all__ = ["SECURITY_QUESTIONS", "JevPreflightRegistry", "JevPresets"]
