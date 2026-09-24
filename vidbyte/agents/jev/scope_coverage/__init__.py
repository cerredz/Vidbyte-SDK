"""FILE: vidbyte/agents/jev/scope_coverage/__init__.py

PURPOSE: Groups the scope-coverage done check (JevPresets.ScopeCoverage): state section, handoff section, questions, decision, and check.
ROLE IN CODEBASE: run_state.py imports the section records; runtime.py imports check.py directly.
ARCHITECTURE NOTE: This package init imports only modules that do not import run_state.py, which keeps the import graph acyclic.
COMMON MODIFICATION PATTERNS: Keep one role per module; add new public records to the owning module's __all__, not here.
KNOWN EDGE CASES: Importing check.py from here would create a cycle through run_state.py and done_checks.py.
RELATED DOCS: docs/design/jev-scope-coverage-done-criteria.md.
TESTS: tests/test_jev_agent.py.
"""

from vidbyte.agents.jev.scope_coverage.enums import (
    JevScopeBreadth,
    JevScopeCoverageOutcome,
    JevScopeUnitSource,
    JevScopeUniverse,
)
from vidbyte.agents.jev.scope_coverage.handoff import (
    JevScopeDimensionHandoff,
    JevScopeHandoff,
    JevScopeUnitRecord,
)
from vidbyte.agents.jev.scope_coverage.state import JevScopeDimension, JevScopeSection

__all__ = [
    "JevScopeBreadth",
    "JevScopeCoverageOutcome",
    "JevScopeDimension",
    "JevScopeDimensionHandoff",
    "JevScopeHandoff",
    "JevScopeSection",
    "JevScopeUnitRecord",
    "JevScopeUnitSource",
    "JevScopeUniverse",
]
