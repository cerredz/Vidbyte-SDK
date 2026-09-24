"""FILE: vidbyte/agents/jev/alignment/draft.py

PURPOSE: Holds one run's additive edits to the main agent's system prompt and renders the edited prompt; and JevToolScoutPass, the run-local state a tool-alignment pass shares with the scout's tools.
ROLE IN CODEBASE: JevAgentAlignment creates one JevPromptDraft per alignment pass; the edit tool writes to it and verification chooses which sections to keep.
ARCHITECTURE NOTE: Edits only add text under a named section heading, creating the heading when missing. The original prompt text is never replaced or deleted, so owner-written instructions survive every edit.
COMMON MODIFICATION PATTERNS: Change validation here, not in the tool, so every caller of add() gets the same rules.
KNOWN EDGE CASES: A second edit to the same section replaces the first, which lets the editor refine its own addition. Headings match case-insensitively at any markdown level.
RELATED DOCS: docs/design/jev-agent-alignment.md.
TESTS: tests/test_jev_alignment.py.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from vidbyte.agents.jev.alignment.questions import EDITABLE_SECTIONS, JevPromptSection
from vidbyte.agents.jev.alignment.result import (
    JevAlignmentGap,
    JevPromptEdit,
    JevToolCandidate,
    JevToolNeed,
)
from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.dataclasses.tool_catalogs import ToolCatalogEntry
from vidbyte.tools.mcp.types import McpServerHandle

MAX_EDIT_CHARS = 1_500
MAX_ADDED_CHARS = 6_000
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


class JevPromptDraft:
    """Run-local, additive edits to one system prompt, keyed by section."""

    def __init__(self, base: str, gaps: tuple[JevAlignmentGap, ...]) -> None:
        # Retains the original prompt and the open editor gaps each edit must cite.
        self.base = base
        self.gaps: Mapping[str, JevAlignmentGap] = {gap.question: gap for gap in gaps}
        self._edits: dict[JevPromptSection, JevPromptEdit] = {}

    @property
    def edits(self) -> tuple[JevPromptEdit, ...]:
        """Return the current edits in section declaration order."""
        return tuple(self._edits[section] for section in JevPromptSection if section in self._edits)

    def add(self, section: str, content: str, fixes: Collection[str]) -> JevPromptEdit:
        """Validate and record one additive edit, raising ValueError with a repair hint when it is refused."""
        target = self._editable_section(section)
        text = content.strip() if isinstance(content, str) else ""
        if not text:
            raise ValueError("content must be non-blank text to add under the section heading.")
        if len(text) > MAX_EDIT_CHARS:
            raise ValueError(f"content is {len(text)} characters; keep one section's addition under {MAX_EDIT_CHARS}.")
        cited = self._cited_gaps(target, fixes)
        others = sum(len(edit.content) for key, edit in self._edits.items() if key is not target)
        if others + len(text) > MAX_ADDED_CHARS:
            raise ValueError(f"all additions together must stay under {MAX_ADDED_CHARS} characters; shorten this or an earlier edit.")
        edit = JevPromptEdit(section=target, content=text, fixes=cited)
        self._edits[target] = edit
        return edit

    def render(self, sections: Collection[JevPromptSection] | None = None) -> str:
        """Return the base prompt with the chosen sections' additions inserted; all edits when sections is None."""
        lines = self.base.rstrip().splitlines()
        for edit in self.edits:
            if sections is None or edit.section in sections:
                lines = _insert_under_heading(lines, edit.section.heading, edit.content)
        return "\n".join(lines)

    def _editable_section(self, section: str) -> JevPromptSection:
        # @intent owner-sections-stay-owner-written
        # Role, scope, boundaries, audience, knowledge, and permissions decide what the agent is for;
        # letting a request-driven edit touch them would let any message widen the agent's job.
        try:
            target = JevPromptSection(section)
        except ValueError as exc:
            raise ValueError(f"unknown section {section!r}; use one of {sorted(item.value for item in EDITABLE_SECTIONS)}.") from exc
        if target not in EDITABLE_SECTIONS:
            raise ValueError(f"section {target.value!r} is owner-only; it is reported to the developer and cannot be edited.")
        return target

    def _cited_gaps(self, target: JevPromptSection, fixes: Collection[str]) -> tuple[str, ...]:
        # Requires every cited question to be an open gap for this exact section.
        cited = tuple(dict.fromkeys(str(item) for item in fixes))
        if not cited:
            raise ValueError("fixes must name at least one gap question this edit closes.")
        wrong = [name for name in cited if name not in self.gaps or self.gaps[name].section is not target]
        if wrong:
            allowed = sorted(name for name, gap in self.gaps.items() if gap.section is target)
            raise ValueError(f"fixes {wrong} are not open gaps for section {target.value!r}; allowed: {allowed}.")
        return cited


def _insert_under_heading(lines: list[str], heading: str, content: str) -> list[str]:
    # Appends content at the end of the matching section, or adds a new level-2 section at the end.
    block = content.splitlines()
    start = _heading_index(lines, heading)
    if start is None:
        return [*lines, "", f"## {heading}", *block]
    end = _section_end(lines, start)
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    tail = lines[end:]
    spacer = [""] if tail and tail[0].strip() else []
    return [*lines[:end], "", *block, *spacer, *tail]


def _heading_index(lines: list[str], heading: str) -> int | None:
    # Returns the first line whose markdown heading text equals the section heading, ignoring case.
    wanted = heading.casefold()
    for index, line in enumerate(lines):
        match = _HEADING.match(line)
        if match and match.group(2).casefold() == wanted:
            return index
    return None


def _section_end(lines: list[str], start: int) -> int:
    # Returns the index of the next heading at the same or a higher level, or the end of the prompt.
    match = _HEADING.match(lines[start])
    level = len(match.group(1)) if match else 2
    for index in range(start + 1, len(lines)):
        following = _HEADING.match(lines[index])
        if following and len(following.group(1)) <= level:
            return index
    return len(lines)


class JevToolScoutPhase(StrEnum):
    """Which part of a tool-alignment pass the scout is in; each phase allows only its own tools."""

    NEEDS = "needs"  # write_tool_needs only
    SEARCH = "search"  # search_tool_catalogs, describe_catalog_entry, propose_tool_candidates


@dataclass(frozen=True, slots=True)
class JevToolProposal:
    """One entry and tool shortlist the scout proposed for one need."""

    need_id: str
    entry_key: str
    tool_names: tuple[str, ...]


@dataclass(slots=True)
class JevToolScoutPass:
    """Run-local state one tool-alignment pass shares with the scout's tools; JevAgentAlignment owns every rule."""

    request: str
    phase: JevToolScoutPhase = JevToolScoutPhase.NEEDS
    needs: list[JevToolNeed] = field(default_factory=list)
    # Every entry a search or describe returned this pass, keyed by ToolCatalogEntry.key; proposals may cite only these.
    entries: dict[str, ToolCatalogEntry] = field(default_factory=dict)
    described: set[str] = field(default_factory=set)
    proposals: list[JevToolProposal] = field(default_factory=list)
    searches: int = 0
    provider_errors: dict[str, str] = field(default_factory=dict)
    # Evidence and resources the pass accumulates; JevAgentAlignment turns them into the result and closes the sessions.
    probabilities: dict[str, float] = field(default_factory=dict)
    usages: list[JevUsage] = field(default_factory=list)
    rejected: list[JevToolCandidate] = field(default_factory=list)
    owner_actions: list[str] = field(default_factory=list)
    handles: list[McpServerHandle] = field(default_factory=list)

    def uncovered_ids(self) -> frozenset[str]:
        """Return the ids of needs no existing tool performs; only these may receive proposals."""
        return frozenset(need.need_id for need in self.needs if not need.covered)


__all__ = ["MAX_ADDED_CHARS", "MAX_EDIT_CHARS", "JevPromptDraft", "JevToolProposal", "JevToolScoutPass", "JevToolScoutPhase"]
