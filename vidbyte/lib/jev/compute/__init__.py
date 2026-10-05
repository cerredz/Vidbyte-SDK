"""FILE: vidbyte/lib/jev/compute/__init__.py

PURPOSE: Exports the mid-run compute question content: JevComputeRegistry over every fixed sign question and JevComputeSituations, each situation's recognition policy.
ROLE IN CODEBASE: JevComputeSettings validates situations through the registry, and the recognizer in vidbyte/agents/jev/compute/ reads questions and policy from here.
ARCHITECTURE NOTE: This package holds question content and lookup only; asking Jev and acting on its answers stays in the agent layer, as for preflight and done checks.
COMMON MODIFICATION PATTERNS: Load skills/asking-jev-questions/SKILL.md before writing or reviewing a question here (see README.md in this folder).
KNOWN EDGE CASES: Importing this package builds every question dataclass, so a malformed question fails at import.
RELATED DOCS: docs/design/jev-compute-situations.md.
TESTS: tests/test_jev_compute_situations.py.
"""

from __future__ import annotations

from vidbyte.lib.jev.compute.compute import JevComputeRegistry
from vidbyte.lib.jev.compute.situations import JevComputeSituations

__all__ = ["JevComputeRegistry", "JevComputeSituations"]
