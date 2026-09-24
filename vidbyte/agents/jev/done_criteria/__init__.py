"""FILE: vidbyte/agents/jev/done_criteria/__init__.py

PURPOSE: Exposes Jev's built-in deterministic done-criteria contracts and presets.
ROLE IN CODEBASE: Jev settings and public SDK namespaces import the criterion types from this package boundary.
ARCHITECTURE NOTE: This package owns policy evaluation, while JevRuntime owns clock access and continuation messages.
FUNCTION INVENTORY: Re-exports JevDoneCriteria, JevDoneCriterion, MinimumTime, and JevPreset.
COMMON MODIFICATION PATTERNS: Keep imports and __all__ synchronized when adding a criterion subclass or preset.
WHAT NOT TO DO: Do not perform runtime execution or provider requests in this export module.
KNOWN EDGE CASES: Importing the package is credential-free and performs no runtime construction.
RELATED DOCS: docs/design/jev-done-criteria.md.
TESTS: tests/test_jev_done_criteria.py.
"""

from vidbyte.agents.jev.done_criteria.base import (
    JevDoneCriteria,
    JevDoneCriteriaResult,
    JevDoneCriterion,
    JevDoneCriterionResult,
)
from vidbyte.agents.jev.done_criteria.criteria import MinimumTime
from vidbyte.agents.jev.done_criteria.presets import JevPreset

__all__ = ["JevDoneCriteria", "JevDoneCriteriaResult", "JevDoneCriterion", "JevDoneCriterionResult", "JevPreset", "MinimumTime"]
