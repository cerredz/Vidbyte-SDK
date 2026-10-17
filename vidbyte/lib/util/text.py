"""FILE: vidbyte/lib/util/text.py

PURPOSE:
    Counts every start position where a substring occurs, including matches
    that overlap, so "exactly once" edit checks cannot mistake two overlapping
    matches for one. Also estimates how many tokens a text holds, and cuts a
    text to a token budget, with one fixed characters-per-token rule. And
    writes any text as one bounded, space-free log token, so a value a
    peer chose cannot split or forge a key=value log record.

ROLE IN CODEBASE:
    SubstringCounter is called by the unique-match edit tools: PatchTool
    (vidbyte/tools/builtins/editing/patch.py), ReplaceTextTool
    (vidbyte/tools/filesystem/replace_text.py), ContextEditTool
    (vidbyte/tools/builtins/context_primitives/edit.py), and the
    InfiniteMemory workspace's edit_file (vidbyte/agents/infinite/workspace.py).
    TokenEstimate is called by the InfiniteMemory agent
    (vidbyte/agents/infinite/) for every workspace cap, the map, and the
    result cards, and by its toolset (vidbyte/tools/toolsets/infinite.py)
    for grep's file-size cap. LogToken is called by the Codex host
    (vidbyte/harnesses/native/codex/) for every id it logs, with its own
    limit, CODEX_HOST_LOG_TOKEN_MAX_CHARS. Calls only str methods and
    math.ceil.

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
    text was left out. LogToken.of(value, limit) -> str: value with every
    character outside ASCII letters, digits and _.:/- replaced by _, and,
    when it is longer than limit, its first limit characters followed by
    "...".

COMMON MODIFICATION PATTERNS:
    Add another general text helper as a @staticmethod here.

WHAT NOT TO DO IN THIS FILE:
    1. Do not import any SDK feature package.
    2. Do not replace the loop with str.count; it misses overlapping matches.
    3. Do not change TOKEN_ESTIMATE_CHARS_PER_TOKEN without checking every
       cap that is counted with it.
    4. Do not give LogToken a limit of its own; each caller passes the
       limit its logs need.

KNOWN EDGE CASES:
    An empty search raises ValueError; every caller rejects it earlier.
    TokenEstimate counts characters, not bytes, so five euro signs are 2
    tokens. cap adds the marker after the cut, so a capped text can be
    the marker's length over max_tokens. LogToken maps code points, so an
    emoji or a non-ASCII digit is one _, and a token is at most limit + 3
    characters; "" stays "", and a token maps to itself.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/unique-edit-overlapping-matches.md;
    docs/spec/infinite-memory-agent/spec.md (TokenEstimate, FR-15);
    docs/spec/codex-host-hardening/spec.md (LogToken, INV-10)

TESTS:
    tests/test_patch_tool.py, tests/test_filesystem_tools.py, and
    tests/test_context_primitives_builtins.py cover SubstringCounter through
    its callers. tests/features/infinite_memory_agent/test_infinite_memory_contract.py
    covers TokenEstimate, count, cut, and cap.
    tests/features/codex_host/test_codex_host_hardening_contract.py
    (CodexLogTokenTests) covers LogToken, and
    tests/features/codex_host/test_codex_host_observability.py
    (CodexLogTokenRecordTests) covers it in the Codex host's records.
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
    """Static-method home for the SDK's characters-per-token estimate."""

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


class LogToken:
    """Static-method home for writing any text as one bounded log token."""

    @staticmethod
    def of(value: str, limit: int) -> str:
        """Return value as one space-free token: each character outside ASCII letters, digits and _.:/- becomes _, and a value longer than limit keeps its first limit characters followed by "..."."""
        # @intent a-logged-value-is-one-bounded-token
        # A value a peer chose can carry a space, "=" or a newline that
        # splits or forges a key=value record, or be long enough to
        # flood it. Each character maps to one character, so mapping
        # only the first limit characters gives the same token as
        # mapping the whole value first, and a huge value costs no more.
        kept = "".join(character if character.isascii() and (character.isalnum() or character in "_.:/-") else "_" for character in value[:limit])
        return kept if len(value) <= limit else f"{kept}..."


__all__ = ["TOKEN_ESTIMATE_CHARS_PER_TOKEN", "LogToken", "SubstringCounter", "TokenEstimate"]
