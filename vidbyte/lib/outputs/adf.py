"""FILE: vidbyte/lib/outputs/adf.py

PURPOSE: Defines OutputAdf, which turns a reply's Markdown-style text into an Atlassian Document Format (ADF) document.
ROLE IN CODEBASE: Called by the Jira connector for issue descriptions and comments, and by the Confluence connector for page bodies.
ARCHITECTURE NOTE: Pure static functions with no state, like OutputText; it reads line by line and needs no Markdown library.
COMMON MODIFICATION PATTERNS: Add a block kind as one ADF_* pattern in vidbyte/lib/constants/outputs.py, one branch in _line, and a test row.
KNOWN EDGE CASES: Lists are flat and carry no inline marks; a thematic break stays a paragraph; an empty code block and blank lines add nothing, since ADF text must not be empty; an unclosed fence runs to the end of the text.
RELATED DOCS: vidbyte/lib/outputs/README.md; https://developer.atlassian.com/cloud/jira/platform/apis/document/nodes/
TESTS: tests/features/agent_output_connectors/test_output_connectors_rendering.py
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Mapping, Sequence

from vidbyte.lib.constants.outputs import (
    ADF_BREAK_PATTERN,
    ADF_BULLET_PATTERN,
    ADF_FENCE,
    ADF_HEADING_PATTERN,
    ADF_ORDERED_PATTERN,
    JIRA_ADF_VERSION,
)

# One block, or one list item, with the kind its run is grouped by.
_Entry = tuple[str, Mapping[str, object]]
_LIST_KINDS = ("bulletList", "orderedList")


class OutputAdf:
    """Builds ADF documents from Markdown-style text: headings, flat lists, code blocks, and paragraphs."""

    @staticmethod
    def document(markdown: str) -> Mapping[str, object]:
        """Return {"type": "doc", "version": 1, "content": [...]} with one block per line or run of list items."""
        entries: list[_Entry] = []
        code: list[str] | None = None
        language = ""
        for line in markdown.splitlines():
            fence = line.strip().startswith(ADF_FENCE)
            # Inside a code block, every line is code, kept as written,
            # until the closing fence.
            if code is not None and not fence:
                code.append(line)
            # The closing fence ends the code block.
            elif code is not None:
                entries.extend(OutputAdf._code_block(language, code))
                code = None
            # An opening fence starts a code block, and the rest of its
            # line names the language.
            elif fence:
                language, code = line.strip().removeprefix(ADF_FENCE).strip(), []
            # Any other line is a heading, a list item, or a paragraph.
            else:
                entries.extend(OutputAdf._line(line))
        # A fence that is never closed runs to the end of the text.
        if code is not None:
            entries.extend(OutputAdf._code_block(language, code))
        # Gather each run of list items of one kind into one list.
        return {"type": "doc", "version": JIRA_ADF_VERSION, "content": OutputAdf._content(entries)}

    @staticmethod
    def _line(line: str) -> tuple[_Entry, ...]:
        # The patterns read the line without trailing spaces; a
        # paragraph keeps the line as written, so plain text is sent
        # unchanged. A blank line adds nothing.
        text = line.rstrip()
        if not text:
            return ()
        heading = re.fullmatch(ADF_HEADING_PATTERN, text)
        if heading:
            return (("heading", {"type": "heading", "attrs": {"level": len(heading.group(1))}, "content": [{"type": "text", "text": heading.group(2)}]}),)
        # A thematic break such as "* * *" is a paragraph, never a
        # list item. A list item holds one paragraph.
        bullet = None if re.fullmatch(ADF_BREAK_PATTERN, text) else re.fullmatch(ADF_BULLET_PATTERN, text)
        item = bullet or re.fullmatch(ADF_ORDERED_PATTERN, text)
        if item:
            kind = "bulletList" if bullet else "orderedList"
            return ((kind, {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": item.group(1)}]}]}),)
        return (("paragraph", {"type": "paragraph", "content": [{"type": "text", "text": line}]}),)

    @staticmethod
    def _code_block(language: str, lines: Sequence[str]) -> tuple[_Entry, ...]:
        # One text node holds the whole block; a block with no text
        # adds nothing, since ADF text must not be empty.
        text = "\n".join(lines)
        if not text.strip():
            return ()
        attrs = {"attrs": {"language": language}} if language else {}
        return (("codeBlock", {"type": "codeBlock", **attrs, "content": [{"type": "text", "text": text}]}),)

    @staticmethod
    def _content(entries: Sequence[_Entry]) -> list[Mapping[str, object]]:
        # Consecutive items of one list kind become one list. Blank
        # lines add no entry, so a loose list stays one list, and any
        # other block between two items ends the first list.
        content: list[Mapping[str, object]] = []
        for kind, run in itertools.groupby(entries, key=lambda entry: entry[0]):
            nodes = [node for _, node in run]
            if kind in _LIST_KINDS:
                content.append({"type": kind, "content": nodes})
            else:
                content.extend(nodes)
        return content


__all__ = ["OutputAdf"]
