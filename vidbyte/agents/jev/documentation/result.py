"""FILE: vidbyte/agents/jev/documentation/result.py

PURPOSE: Defines the records one documentation lookup returns: its status, the verified links, and whether the request needs documentation.
ROLE IN CODEBASE: JevDocumentation.lookup() returns a JevDocumentationResult; JevRuntime appends its links to the run's system prompt and attaches it as metadata["jev_documentation"].
ARCHITECTURE NOTE: needs_documentation is Jev's decision alone; it stays True even when the search later fails, so a caller can tell "not needed" from "needed but not found".
COMMON MODIFICATION PATTERNS: Add a status member only for a new terminal branch in JevDocumentation.lookup(), and render links only through prompt_section().
KNOWN EDGE CASES: When Jev itself fails, needs_documentation is False and the status is UNAVAILABLE.
RELATED DOCS: docs/design/jev-documentation.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_documentation.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from vidbyte.agents.pricing import JevUsage

DOCUMENTATION_HEADING = "## Documentation"


class JevDocumentationStatus(StrEnum):
    """Outcome of one documentation lookup."""

    FOUND = "found"  # verified links were appended to this run's system prompt
    NOT_NEEDED = "not_needed"  # Jev judged that the request needs no outside documentation
    NO_LINKS = "no_links"  # the search agent returned no link that search had actually returned
    UNAVAILABLE = "unavailable"  # Jev, the search key, or the search agent failed; the run continued without links


@dataclass(frozen=True, slots=True)
class JevDocumentationLink:
    """One documentation page the search agent chose and search had returned."""

    url: str
    title: str


@dataclass(frozen=True, slots=True)
class JevDocumentationResult:
    """Everything one documentation lookup decided, attached to the main agent's result metadata."""

    status: JevDocumentationStatus
    needs_documentation: bool
    links: tuple[JevDocumentationLink, ...] = ()
    probabilities: Mapping[str, float] = field(default_factory=dict)
    usage: JevUsage | None = None
    detail: str | None = None

    def prompt_section(self) -> str | None:
        """Return the system prompt section that lists the links, or None when there are none."""
        if not self.links:
            return None
        lines = "\n".join(f"- {link.title}: {link.url}" for link in self.links)
        return (
            f"{DOCUMENTATION_HEADING}\n"
            "This request depends on outside libraries, APIs, or platforms whose details may have changed since your training. "
            "These official documentation pages were found for it. Prefer them over memory for exact names, parameters, and behavior.\n"
            f"{lines}"
        )


__all__ = ["DOCUMENTATION_HEADING", "JevDocumentationLink", "JevDocumentationResult", "JevDocumentationStatus"]
