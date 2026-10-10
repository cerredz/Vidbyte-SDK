"""FILE: vidbyte/lib/util/text.py

PURPOSE:
    Counts every start position where a substring occurs, including matches
    that overlap, so "exactly once" edit checks cannot mistake two overlapping
    matches for one.

ROLE IN CODEBASE:
    Called by the unique-match edit tools: PatchTool
    (vidbyte/tools/builtins/editing/patch.py), ReplaceTextTool
    (vidbyte/tools/filesystem/replace_text.py), and ContextEditTool
    (vidbyte/tools/builtins/context_primitives/edit.py). Calls only str.find.

ARCHITECTURE NOTE:
    A static-method-only class with no SDK dependencies. Python's str.count
    counts only non-overlapping matches: "}\\n}\\n}\\n".count("}\\n}\\n") is 1
    although the search text starts at two positions.

FUNCTION INVENTORY:
    SubstringCounter.count_overlapping(text, search) -> int: number of start
    positions of a non-empty search in text.

COMMON MODIFICATION PATTERNS:
    Add another general text helper as a @staticmethod here.

WHAT NOT TO DO IN THIS FILE:
    1. Do not import any SDK feature package.
    2. Do not replace the loop with str.count; it misses overlapping matches.

KNOWN EDGE CASES:
    An empty search raises ValueError; every caller rejects it earlier.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/unique-edit-overlapping-matches.md

TESTS:
    tests/test_patch_tool.py, tests/test_filesystem_tools.py, and
    tests/test_context_primitives_builtins.py cover it through its callers.
"""

from __future__ import annotations


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


__all__ = ["SubstringCounter"]
