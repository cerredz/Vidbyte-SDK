"""FILE: vidbyte/lib/outputs/text.py

PURPOSE: Defines OutputText, the pure string helpers connectors use to fit a title and body into a destination's fields.
ROLE IN CODEBASE: Called by the connectors in this package and by OutputShaping in vidbyte/agents/output/connector.py for the first-line title rule.
ARCHITECTURE NOTE: Leaf string functions with no knowledge of agents, replies, stop reasons, or structured output.
COMMON MODIFICATION PATTERNS: Add a helper here only when two or more connectors need the same text transform.
KNOWN EDGE CASES: single_line never calls truncate, because the truncation marker contains line breaks.
RELATED DOCS: vidbyte/lib/outputs/README.md
TESTS: tests/features/agent_output_connectors/test_output_connectors_wire_contract.py
"""

from __future__ import annotations

from vidbyte.lib.constants.outputs import OUTPUT_TRUNCATION_MARKER
from vidbyte.lib.dataclasses.outputs import OutputContent


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
    def truncate(text: str, limit: int) -> str:
        """Cut text so the result, including the truncation marker, is at most limit characters."""
        if len(text) <= limit:
            return text
        return text[: limit - len(OUTPUT_TRUNCATION_MARKER)] + OUTPUT_TRUNCATION_MARKER

    @staticmethod
    def single_line(text: str, limit: int) -> str:
        """Collapse every run of whitespace, line breaks included, to one space, then cut to limit with no marker."""
        return " ".join(text.split())[:limit]


__all__ = ["OutputText"]
