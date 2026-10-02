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
from vidbyte.agents.jev.alignment import (
    JevAlignmentResult,
    JevAlignmentStatus,
    JevToolAlignmentResult,
    JevToolAlignmentStatus,
)
from vidbyte.agents.jev.runtime import JevRuntime
from vidbyte.agents.jev.settings import (
    JevAgentSettings,
    JevAlignmentSettings,
    JevBulkSettings,
    JevContinualSettings,
    JevRuntimeSettings,
    JevToolAlignmentSettings,
)
from vidbyte.lib.dataclasses.jev import (
    JevAgentResponse,
    JevBulkItemResult,
    JevBulkWorkResult,
    JevAlignmentOutcome,
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
    JevPresetResult,
    JevProblemResolutionItem,
    JevProblemsResolvedEvidence,
    JevPromptAlignmentOutcome,
    JevRunStateRecord,
    JevSkillResult,
    JevSkillsOutcome,
    JevSpecialist,
    JevTargetOutcome,
    JevTargetOutcomeEvidence,
    JevTargetOutcomeEvidenceItem,
    JevTargetOutcomeItem,
    JevToolAlignmentOutcome,
)
from vidbyte.lib.dataclasses.skills import (
    ClaudeSkillReference,
    ClaudeSkillSession,
    SkillDocument,
    SkillSource,
)
from vidbyte.lib.enums.jev import (
    JevBulkItemError,
    JevBulkPlanningError,
    JevClaimKind,
    JevDoneCheck,
    JevPreflightPreset,
    JevProblemCheckItemType,
    JevSkillStatus,
)
from vidbyte.lib.enums.skills import ClaudeSkillType, SkillSourceKind

__all__ = [
    "JevAgent",
    "JevAgentResponse",
    "JevAgentSettings",
    "JevAlignmentOutcome",
    "JevAlignmentResult",
    "JevAlignmentSettings",
    "JevAlignmentStatus",
    "JevPromptAlignmentOutcome",
    "JevClarification",
    "JevClarifyingQuestion",
    "JevClaimEvidence",
    "JevClaimsEvidence",
    "JevBulkItemResult",
    "JevBulkItemError",
    "JevBulkPlanningError",
    "JevBulkSettings",
    "JevBulkWorkResult",
    "JevClaimAssertion",
    "JevClaimContext",
    "JevClaimIdentity",
    "JevClaimKind",
    "JevClaimScope",
    "JevContinualSettings",
    "JevDeliverable",
    "JevDeliverableEvidence",
    "JevDoneCheck",
    "JevDoneResult",
    "JevHandoffRecord",
    "JevPreflightPreset",
    "JevPresetResult",
    "JevProblemCheckItemType",
    "JevProblemResolutionItem",
    "JevProblemsResolvedEvidence",
    "JevRunStateRecord",
    "JevRuntime",
    "JevRuntimeSettings",
    "JevSpecialist",
    "JevSkillResult",
    "JevSkillsOutcome",
    "JevSkillStatus",
    "ClaudeSkillType",
    "SkillSourceKind",
    "ClaudeSkillReference",
    "ClaudeSkillSession",
    "SkillDocument",
    "SkillSource",
    "JevToolAlignmentResult",
    "JevToolAlignmentSettings",
    "JevToolAlignmentOutcome",
    "JevToolAlignmentStatus",
    "JevTargetOutcome",
    "JevTargetOutcomeEvidence",
    "JevTargetOutcomeEvidenceItem",
    "JevTargetOutcomeItem",
]
