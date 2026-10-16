"""FILE: vidbyte/lib/util/text.py

PURPOSE:
    Counts every start position where a substring occurs, including matches
    that overlap, so "exactly once" edit checks cannot mistake two overlapping
    matches for one. Also estimates how many tokens a text holds, and cuts a
    text to a token budget, with one fixed characters-per-token rule, and
    truncates a text to a character limit with a marker inside the limit.

ROLE IN CODEBASE:
    SubstringCounter is called by the unique-match edit tools: PatchTool
    (vidbyte/tools/builtins/editing/patch.py), ReplaceTextTool
    (vidbyte/tools/filesystem/replace_text.py), ContextEditTool
    (vidbyte/tools/builtins/context_primitives/edit.py), and the
    InfiniteMemory workspace's edit_file (vidbyte/agents/infinite/workspace.py).
    TokenEstimate is called by the InfiniteMemory agent
    (vidbyte/agents/infinite/) for every workspace cap, the map, and the
    result cards, and by its toolset (vidbyte/tools/toolsets/infinite.py)
    for grep's file-size cap. TokenEstimate.truncate_chars is the SDK's one
    character cut with a marker: OutputText.truncate
    (vidbyte/lib/outputs/text.py) delegates to it, so the output connectors,
    InfiniteEvents, and InfiniteMemoryAgent.run_handoff use it through that
    method, and InfiniteHandoff (vidbyte/context/handoff/infinite.py) calls
    it directly, because importing vidbyte.lib.outputs there breaks import
    vidbyte. Calls only str methods and math.ceil.

ARCHITECTURE NOTE:
    Static-method-only classes with no SDK dependencies. Python's str.count
    counts only non-overlapping matches: "}\\n}\\n}\\n".count("}\\n}\\n") is 1
    although the search text starts at two positions. TokenEstimate is a
    character estimate, not a tokenizer: one token per
    TOKEN_ESTIMATE_CHARS_PER_TOKEN characters, rounded up.

FUNCTION INVENTORY:
    SubstringCounter.count_overlapping(text, search) -> int: number of start
    positions of a non-empty search in text. TokenEstimate.count(text) -> int:
    0 for "", otherwise the characters divided by four, rounded up.
    TokenEstimate.cut(text, max_tokens) -> str: the text when it fits,
    otherwise its prefix of max_tokens times four characters.
    TokenEstimate.cap(text, max_tokens, marker) -> str: the text when it
    fits, otherwise its cut followed by the marker, so a reader sees that
    text was left out. TokenEstimate.truncate_chars(text, max_chars,
    marker) -> str: the text when it has at most max_chars characters,
    otherwise its first max_chars minus the marker's length characters
    followed by the marker.

COMMON MODIFICATION PATTERNS:
    Add another general text helper as a @staticmethod here.

WHAT NOT TO DO IN THIS FILE:
    1. Do not import any SDK feature package.
    2. Do not replace the loop with str.count; it misses overlapping matches.
    3. Do not change TOKEN_ESTIMATE_CHARS_PER_TOKEN without checking every
       cap that is counted with it.

KNOWN EDGE CASES:
    An empty search raises ValueError; every caller rejects it earlier.
    TokenEstimate counts characters, not bytes, so five euro signs are 2
    tokens. cap adds the marker after the cut, so a capped text can be
    the marker's length over max_tokens. truncate_chars instead keeps the
    marker inside max_chars, and expects max_chars to be at least the
    marker's length, as every caller's limit is.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/unique-edit-overlapping-matches.md;
    docs/spec/infinite-memory-agent/spec.md (TokenEstimate, FR-15)

TESTS:
    tests/test_patch_tool.py, tests/test_filesystem_tools.py, and
    tests/test_context_primitives_builtins.py cover SubstringCounter through
    its callers. tests/features/infinite_memory_agent/test_infinite_memory_contract.py
    covers TokenEstimate, count, cut, and cap.
    tests/test_output_text_truncate_marker.py covers truncate_chars through
    OutputText.truncate, and
    tests/features/infinite_memory_agent/test_infinite_memory_handoff.py
    through the handoff's list lines.
"""

from __future__ import annotations

import math

# One estimated token per this many characters, rounded up.
TOKEN_ESTIMATE_CHARS_PER_TOKEN = 4


class SubstringCounter:
    """Static-method home for overlap-aware substring counting."""

    @staticmethod
    def count_overlapping(text: str, search: str) -> int:
        """Return how many positions in text the non-empty search starts at, overlaps included."""
        # @intent unique-edit-counts-overlapping-matches
        if not search:
            raise ValueError("search cannot be empty.")
        count = 0
        index = text.find(search)
        while index != -1:
            count += 1
            index = text.find(search, index + 1)
        return count


class TokenEstimate:
    """Static-method home for the SDK's text budgets: the characters-per-token estimate and the cuts to a token or character limit."""

    @staticmethod
    def count(text: str) -> int:
        """Return 0 for "", otherwise the characters divided by four, rounded up."""
        return math.ceil(len(text) / TOKEN_ESTIMATE_CHARS_PER_TOKEN)

    @staticmethod
    def cut(text: str, max_tokens: int) -> str:
        """Return text when it fits max_tokens, otherwise its prefix of max_tokens times four characters."""
        if TokenEstimate.count(text) <= max_tokens:
            return text
        return text[: max_tokens * TOKEN_ESTIMATE_CHARS_PER_TOKEN]

    @staticmethod
    def cap(text: str, max_tokens: int, marker: str) -> str:
        """Return text when it fits max_tokens, otherwise its cut followed by marker, so the reader knows text was left out."""
        if TokenEstimate.count(text) <= max_tokens:
            return text
        return f"{TokenEstimate.cut(text, max_tokens)}{marker}"

    @staticmethod
    def truncate_chars(text: str, max_chars: int, marker: str) -> str:
        """Return text when it has at most max_chars characters, otherwise its first max_chars - len(marker) characters followed by marker, so the marker stays inside the limit."""
        if len(text) <= max_chars:
            return text
        return text[: max_chars - len(marker)] + marker


__all__ = ["TOKEN_ESTIMATE_CHARS_PER_TOKEN", "SubstringCounter", "TokenEstimate"]
