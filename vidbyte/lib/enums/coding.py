"""FILE: vidbyte/lib/enums/coding.py

PURPOSE: Defines CodingContextSection, the closed set of sections a CodingAgent places in the model's context right after the system prompt, in the order the model sees them.
ROLE IN CODEBASE: Typed field of CodingContextSectionText (vidbyte/lib/dataclasses/coding.py); read by CodingContextWindow (vidbyte/agents/coding_context/window.py) to order sections and name their primitives; set by each section loader in vidbyte/agents/coding_context/. Re-exported from vidbyte/lib/enums/__init__.py.
ARCHITECTURE NOTE: Declaration order is render order, and each value is the section's stable primitive id in the agent's ContextManager, so the window needs no separate order list or id builder.
FUNCTION INVENTORY: No functions; CodingContextSection is a str Enum with AGENTS_MD, ENVIRONMENT, REPO_MAP, SETUP_RESULTS, and PROGRESS_NOTES.
COMMON MODIFICATION PATTERNS: A new section kind adds one member at the position where the model should see it. A loader for an existing member uses that member and changes nothing here.
WHAT NOT TO DO IN THIS FILE: 1. Do not reorder members to fix one feature; the order is the whole context window's contract. 2. Do not add behavior or methods. 3. Do not change a value; it is the primitive id callers and tests look up.
KNOWN EDGE CASES: A member with no loader, or whose loader returns None, never appears in the context.
RELATED DOCS: docs/design/coding-agent-agents-md.md; docs/design/coding-agent-progress-notes.md; vidbyte/agents/coding_context/README.md
TESTS: tests/features/coding_agent/test_coding_agent_agents_md.py and tests/features/coding_agent/test_coding_agent_progress_notes.py
"""

from __future__ import annotations

from enum import Enum


class CodingContextSection(str, Enum):
    """One section of a CodingAgent's context window; members render in declaration order.

    AGENTS_MD is filled by AgentsMdLoader. ENVIRONMENT, REPO_MAP, and
    SETUP_RESULTS are reserved for the environment-context,
    repository-map, and setup-command sections, each filled by its own
    loader in vidbyte/agents/coding_context/. PROGRESS_NOTES is filled
    by ProgressNotesLoader and comes last, closest to the user's task.
    Each value is the stable primitive id the section is placed under.
    """

    AGENTS_MD = "coding:agents_md"
    ENVIRONMENT = "coding:environment"
    REPO_MAP = "coding:repo_map"
    SETUP_RESULTS = "coding:setup_results"
    PROGRESS_NOTES = "coding:progress_notes"


__all__ = ["CodingContextSection"]
