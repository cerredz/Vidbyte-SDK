"""FILE: vidbyte/agents/jev/alignment/__init__.py

PURPOSE: Exposes JevAgent's alignment capabilities: the alignment agent (prompt editing and tool alignment), their result records, and the fixed question sets.
ROLE IN CODEBASE: vidbyte.agents.jev imports JevAgentAlignment for JevAgent and JevRuntime; applications read JevAlignmentResult from run metadata.
ARCHITECTURE NOTE: Questions, draft rules, the edit tool, and the scout tools are internal policy; callers turn the capabilities on with JevAgentSettings(self_align=True) and JevAgentSettings(tool_align=JevToolAlignmentSettings(...)).
COMMON MODIFICATION PATTERNS: Export a record here only when applications need to read it from run metadata.
KNOWN EDGE CASES: Importing this package performs no Jev call and needs no credentials.
RELATED DOCS: docs/design/jev-agent-alignment.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_alignment.py.
"""

from vidbyte.agents.jev.alignment.agent import JevAgentAlignment
from vidbyte.agents.jev.alignment.questions import (
    ALIGNMENT_QUESTIONS,
    TOOL_QUESTIONS,
    JevAlignmentRole,
    JevPromptSection,
)
from vidbyte.agents.jev.alignment.result import (
    JevAlignmentGap,
    JevAlignmentResult,
    JevAlignmentStatus,
    JevAttachedTool,
    JevPromptEdit,
    JevToolAlignmentResult,
    JevToolAlignmentStatus,
    JevToolAttachment,
    JevToolCandidate,
    JevToolEffect,
    JevToolNeed,
    JevToolRejection,
)

__all__ = [
    "ALIGNMENT_QUESTIONS",
    "TOOL_QUESTIONS",
    "JevAgentAlignment",
    "JevAlignmentGap",
    "JevAlignmentResult",
    "JevAlignmentRole",
    "JevAlignmentStatus",
    "JevAttachedTool",
    "JevPromptEdit",
    "JevPromptSection",
    "JevToolAlignmentResult",
    "JevToolAlignmentStatus",
    "JevToolAttachment",
    "JevToolCandidate",
    "JevToolEffect",
    "JevToolNeed",
    "JevToolRejection",
]
