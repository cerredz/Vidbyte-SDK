"""FILE: vidbyte/lib/jev/preflight/__init__.py

PURPOSE: Exposes the canonical fixed JevAgent preflight questions and the registry that runs them.
ROLE IN CODEBASE: `vidbyte/agents/jev/preflight.py` imports JevPreflightRegistry from here; tests import the question tuples.
ARCHITECTURE NOTE: One module per preset holds one frozen dataclass per question; registry.py is the single owner of lookup, validation, combination, and execution.
COMMON MODIFICATION PATTERNS: Add a preset module with its question dataclasses, then register its tuple in JevPreflightRegistry.
KNOWN EDGE CASES: Importing this package performs no Jev call and needs no TypeSafe credential.
RELATED DOCS: docs/design/jev-preflight-sensitive-data.md and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_sensitive_preflight.py.
"""

from vidbyte.lib.jev.preflight.registry import JevPreflightRegistry
from vidbyte.lib.jev.preflight.security import SECURITY_QUESTIONS

__all__ = ["SECURITY_QUESTIONS", "JevPreflightRegistry"]
