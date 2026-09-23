"""FILE: vidbyte/agents/jev/alignment/__init__.py

PURPOSE: Exposes JevAgent's self-alignment capability: the editor agent, its result records, and the fixed question set.
ROLE IN CODEBASE: vidbyte.agents.jev imports JevAgentAlignment for JevAgent and JevRuntime; applications read JevAlignmentResult from run metadata.
ARCHITECTURE NOTE: Questions, draft rules, and the edit tool are internal policy; callers turn the capability on with JevAgentSettings(self_align=True).
COMMON MODIFICATION PATTERNS: Export a record here only when applications need to read it from run metadata.
KNOWN EDGE CASES: Importing this package performs no Jev call and needs no credentials.
RELATED DOCS: docs/design/jev-agent-alignment.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_alignment.py.
"""

from vidbyte.agents.jev.alignment.agent import JevAgentAlignment
from vidbyte.agents.jev.alignment.questions import (
    ALIGNMENT_QUESTIONS,
    JevAlignmentRole,
    JevPromptSection,
)
from vidbyte.agents.jev.alignment.result import (
    JevAlignmentGap,
    JevAlignmentResult,
    JevAlignmentStatus,
    JevPromptEdit,
)

__all__ = [
    "ALIGNMENT_QUESTIONS",
    "JevAgentAlignment",
    "JevAlignmentGap",
    "JevAlignmentResult",
    "JevAlignmentRole",
    "JevAlignmentStatus",
    "JevPromptEdit",
    "JevPromptSection",
]
