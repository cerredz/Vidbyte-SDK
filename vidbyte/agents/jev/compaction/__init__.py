"""FILE: vidbyte/agents/jev/compaction/__init__.py

PURPOSE: Exposes JevAgent's dynamic-compaction capability: the JevDynamicCompaction agent, the trigger contract, and the run report types.
ROLE IN CODEBASE: vidbyte/agents/jev/agent.py builds JevDynamicCompaction; JevRuntime drives it; tests and callers read JevCompactionReport from result metadata.
ARCHITECTURE NOTE: Users enable this through JevAgentSettings(dynamic_compaction=JevDynamicCompactionSettings(...)); nothing here is a caller-supplied decision hook.
COMMON MODIFICATION PATTERNS: Export a new trigger class here only after it is registered in JEV_COMPACTION_TRIGGERS and has a settings flag.
KNOWN EDGE CASES: Importing this package builds no Jev runner and resolves no credentials.
RELATED DOCS: docs/design/jev-dynamic-compaction.md.
TESTS: tests/test_jev_dynamic_compaction.py.
"""

from vidbyte.agents.jev.compaction.agent import JevDynamicCompaction
from vidbyte.agents.jev.compaction.ledger import JevUnitLedger, JevWorkUnit
from vidbyte.agents.jev.compaction.report import (
    JevCompactionReport,
    JevCompactionRun,
    JevUnitBoundary,
    JevUnitCompaction,
)
from vidbyte.agents.jev.compaction.steps import JevRunStep, JevRunSteps
from vidbyte.agents.jev.compaction.triggers import (
    JEV_COMPACTION_TRIGGERS,
    JevCompactionTrigger,
    JevStepView,
    JevUnitOfWorkTrigger,
)

__all__ = [
    "JEV_COMPACTION_TRIGGERS",
    "JevCompactionReport",
    "JevCompactionRun",
    "JevCompactionTrigger",
    "JevDynamicCompaction",
    "JevRunStep",
    "JevRunSteps",
    "JevStepView",
    "JevUnitBoundary",
    "JevUnitCompaction",
    "JevUnitLedger",
    "JevUnitOfWorkTrigger",
    "JevWorkUnit",
]
