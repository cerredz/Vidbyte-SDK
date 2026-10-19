"""FILE: vidbyte/lib/outputs/text.py

PURPOSE: Defines OutputText, the pure string helpers connectors use to fit a title and body into a destination's fields.
ROLE IN CODEBASE: Called by the connectors in this package, by OutputShaping in vidbyte/agents/output/connector.py for the first-line title rule, and, through truncate with INFINITE_TRUNCATION_MARKER, by InfiniteEvents (vidbyte/agents/infinite/events.py) and InfiniteMemoryAgent.run_handoff to cut event and handoff text to its cap. truncate delegates the cut to TokenEstimate.truncate_chars (vidbyte/lib/util/text.py), which InfiniteHandoff (vidbyte/context/handoff/infinite.py) calls directly for its list lines, because vidbyte.lib.dataclasses imports vidbyte.context while it loads and this package's connectors need vidbyte.lib.dataclasses back.
ARCHITECTURE NOTE: Leaf string functions with no knowledge of agents, replies, stop reasons, or structured output.
COMMON MODIFICATION PATTERNS: Add a helper here only when two or more connectors need the same text transform.
KNOWN EDGE CASES: single_line never calls truncate, because the default truncation marker contains line breaks. With a one-line marker, such as the InfiniteMemory one, a cut one-line text stays one line.
RELATED DOCS: vidbyte/lib/outputs/README.md
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py; tests/test_output_text_truncate_marker.py (the marker option)
"""

from __future__ import annotations

from vidbyte.lib.constants.outputs import OUTPUT_TRUNCATION_MARKER
from vidbyte.lib.dataclasses.outputs import OutputContent
from vidbyte.lib.util.text import TokenEstimate


class OutputText:
    """Pure helpers that turn a title and body into destination-ready text."""

    @staticmethod
    def first_line(text: str) -> str:
        """The first line with text in it, without leading markdown heading marks."""
        lines = (line.strip().lstrip("#").strip() for line in text.splitlines())
        return next((line for line in lines if line), "")

    @staticmethod
    def chat_text(content: OutputContent) -> str:
        """One chat message: the title, a blank line, then the body, unless the body already opens with the title."""
        if OutputText.first_line(content.body) == content.title:
            return content.body
        return f"{content.title}\n\n{content.body}"

    @staticmethod
    def truncate(text: str, limit: int, *, marker: str = OUTPUT_TRUNCATION_MARKER) -> str:
        """Cut text so the result, including marker (OUTPUT_TRUNCATION_MARKER unless the caller names its own), is at most limit characters."""
        return TokenEstimate.truncate_chars(text, limit, marker)

    @staticmethod
    def single_line(text: str, limit: int) -> str:
        """Collapse every run of whitespace, line breaks included, to one space, then cut to limit with no marker."""
        return " ".join(text.split())[:limit]


__all__ = ["OutputText"]
