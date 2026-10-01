"""FILE: vidbyte/agents/jev/alignment/__init__.py

PURPOSE: Exposes JevAgent's alignment capabilities: prompt editing, tool alignment, and source-neutral skill preloading, along with result records and fixed question sets.
ROLE IN CODEBASE: JevAgent and JevRuntime import the alignment classes; applications enable named capabilities through JevAlignmentSettings and read redacted outcomes from JevAgent.response.
ARCHITECTURE NOTE: Questions, draft rules, editor/scout tools, and skill materialization are internal policy; remote skill-source adapters are not part of this package boundary.
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
