"""FILE: vidbyte/agents/jev/__init__.py

PURPOSE: Exposes JevAgent, its agent and runtime settings, the JevSpecialist record, its runtime, the preflight flags and done checks, and the records a caller reads on JevAgent.response.
ROLE IN CODEBASE: This is the public package boundary imported by vidbyte.agents and application code.
ARCHITECTURE NOTE: The agent types plus the preflight flag and done-check enums and result records are public; they are re-exported from vidbyte.lib, while preflight and done questions, JevPreflightGate, JevRunState, JevHandoff, decision records, and provider transport stay in their lower-level packages.
COMMON MODIFICATION PATTERNS: Export a named capability settings type only when it becomes part of the supported JevAgent API.
KNOWN EDGE CASES: Importing this package must not resolve credentials or construct a TypeSafe decision runner.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-claims-context.md, docs/design/jev-target-outcome-done-check.md, skills/jev-agent/SKILL.md, and skills/jev-continuation/SKILL.md.
TESTS: tests/test_jev_agent.py and scripts/test-jev-agent-scaffold.py.
"""

from vidbyte.agents.jev.agent import JevAgent
from vidbyte.agents.jev.runtime import JevRuntime
from vidbyte.agents.jev.settings import (
    JevAgentSettings,
    JevContinualSettings,
    JevRuntimeSettings,
)
from vidbyte.lib.dataclasses.jev import (
    JevAgentResponse,
    JevClaimAssertion,
    JevClaimContext,
    JevClaimEvidence,
    JevClaimIdentity,
    JevClaimScope,
    JevClaimsEvidence,
    JevClarification,
    JevClarifyingQuestion,
    JevDeliverable,
    JevDeliverableEvidence,
    JevDoneResult,
    JevHandoffRecord,
    JevOutputExtent,
    JevOutputExtentEvidence,
    JevOutputExtentEvidenceItem,
    JevOutputExtentItem,
    JevPresetResult,
    JevProblemResolutionItem,
    JevProblemsResolvedEvidence,
    JevRunStateRecord,
    JevSpecialist,
    JevTargetOutcome,
    JevTargetOutcomeEvidence,
    JevTargetOutcomeEvidenceItem,
    JevTargetOutcomeItem,
)
from vidbyte.lib.enums.jev import (
    JevClaimKind,
    JevDoneCheck,
    JevOutputExtentComparator,
    JevOutputExtentUnit,
    JevPreflightPreset,
    JevProblemCheckItemType,
)

__all__ = [
    "JevAgent",
    "JevAgentResponse",
    "JevAgentSettings",
    "JevClaimAssertion",
    "JevClaimContext",
    "JevClaimEvidence",
    "JevClaimIdentity",
    "JevClaimKind",
    "JevClaimScope",
    "JevClaimsEvidence",
    "JevClarification",
    "JevClarifyingQuestion",
    "JevContinualSettings",
    "JevDeliverable",
    "JevDeliverableEvidence",
    "JevDoneCheck",
    "JevDoneResult",
    "JevHandoffRecord",
    "JevOutputExtent",
    "JevOutputExtentComparator",
    "JevOutputExtentEvidence",
    "JevOutputExtentEvidenceItem",
    "JevOutputExtentItem",
    "JevOutputExtentUnit",
    "JevPreflightPreset",
    "JevPresetResult",
    "JevProblemCheckItemType",
    "JevProblemResolutionItem",
    "JevProblemsResolvedEvidence",
    "JevRunStateRecord",
    "JevRuntime",
    "JevRuntimeSettings",
    "JevSpecialist",
    "JevTargetOutcome",
    "JevTargetOutcomeEvidence",
    "JevTargetOutcomeEvidenceItem",
    "JevTargetOutcomeItem",
]
