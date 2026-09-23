"""FILE: vidbyte/agents/jev/alignment/result.py

PURPOSE: Defines the immutable records JevAgentAlignment returns for one run: gaps, edits, owner actions, and the prompt that ran.
ROLE IN CODEBASE: JevRuntime attaches one JevAlignmentResult to the main agent's result metadata under "jev_alignment".
ARCHITECTURE NOTE: Records hold only run-local evidence; nothing here is written back to JevAgentSettings or later runs.
COMMON MODIFICATION PATTERNS: Add a status member only with a matching branch in JevAgentAlignment.align and a test.
KNOWN EDGE CASES: A non-ALIGNED status always carries the original prompt; usage is None when no Jev call reported usage.
RELATED DOCS: docs/design/jev-agent-alignment.md.
TESTS: tests/test_jev_alignment.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from vidbyte.agents.jev.alignment.questions import JevAlignmentRole, JevPromptSection
from vidbyte.agents.pricing import JevUsage


class JevAlignmentStatus(StrEnum):
    """Outcome of one alignment pass."""

    ALIGNED = "aligned"  # at least one verified edit is in the prompt that ran
    NO_GAPS = "no_gaps"  # nothing the editor may fix was missing
    OUT_OF_SCOPE = "out_of_scope"  # a fit gate failed, so the prompt was left alone
    EDITS_REJECTED = "edits_rejected"  # the editor made no edit, or verification reverted every edit
    UNAVAILABLE = "unavailable"  # Jev or the editor failed; the original prompt ran
    SKIPPED = "skipped"  # the caller supplied its own context system prompt


@dataclass(frozen=True, slots=True)
class JevAlignmentGap:
    """One "no" answer that points at a prompt section."""

    question: str
    section: JevPromptSection
    role: JevAlignmentRole
    probability: float
    fix: str


@dataclass(frozen=True, slots=True)
class JevPromptEdit:
    """One additive edit the editor proposed for a section, and whether verification kept it."""

    section: JevPromptSection
    content: str
    fixes: tuple[str, ...]
    kept: bool = False


@dataclass(frozen=True, slots=True)
class JevAlignmentResult:
    """Everything one alignment pass decided, attached to the main agent's result metadata."""

    status: JevAlignmentStatus
    system_prompt: str
    gaps: tuple[JevAlignmentGap, ...] = ()
    edits: tuple[JevPromptEdit, ...] = ()
    owner_actions: tuple[str, ...] = ()
    probabilities: Mapping[str, float] = field(default_factory=dict)
    usage: JevUsage | None = None
    detail: str | None = None


__all__ = ["JevAlignmentGap", "JevAlignmentResult", "JevAlignmentStatus", "JevPromptEdit"]
