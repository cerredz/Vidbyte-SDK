"""FILE: vidbyte/agents/jev/alignment/result.py

PURPOSE: Re-exports the public JevAlignmentGap, JevAlignmentResult, JevAlignmentStatus, and JevPromptEdit records from the shared dataclass and enum layers.
ROLE IN CODEBASE: JevAgentAlignment returns these records; callers can import them from the alignment package without reaching into the shared record module.
ARCHITECTURE NOTE: Record definitions live in vidbyte/lib/dataclasses/jev_alignment.py and enum definitions in vidbyte/lib/enums/jev.py; this module is only a stable feature-facing export.
COMMON MODIFICATION PATTERNS: When a record becomes part of the alignment API, re-export it from this module and update the alignment package's __init__.py.
KNOWN EDGE CASES: JevAlignmentStatus is defined in the enum layer despite being re-exported here; do not create a duplicate enum for compatibility.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/jev-agent-alignment.md.
TESTS: tests/test_jev_alignment.py.
"""

from vidbyte.lib.dataclasses.jev_alignment import (
    JevAlignmentGap,
    JevAlignmentResult,
    JevAlignmentStatus,
    JevPromptEdit,
)

__all__ = ["JevAlignmentGap", "JevAlignmentResult", "JevAlignmentStatus", "JevPromptEdit"]
