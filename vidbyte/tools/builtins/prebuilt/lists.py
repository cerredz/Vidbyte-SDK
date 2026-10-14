"""FILE: vidbyte/tools/builtins/prebuilt/lists.py

PURPOSE: Defines ListsToolFunctions, the seven prebuilt tools that work on lists of text items and integers: item frequencies, duplicate items, two-list comparison, intersection of several lists, missing integers in a range, and compressing and expanding integer range text.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the LISTS category is chosen. Builds on PrebuiltToolSupport in _support.py for the item cap, the integer text output, and the argument error.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Text items are grouped in insertion-ordered dicts keyed by the item or its case-folded form, so every output follows first appearance, and integer counts that could be huge are computed arithmetically while the listed values come from lazy generators.
FUNCTION INVENTORY: count_item_frequencies, find_duplicate_items, compare_two_lists, intersect_lists, find_missing_integers, compress_integer_ranges, and expand_integer_ranges are the tools; _positions_by_item groups item positions under their first spelling; _distinct_items keeps each distinct item once; _range_bounds reads and checks range text; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new list tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.24, and its entry in tool_functions. A tool that groups text items reuses _positions_by_item or _distinct_items so case folding and first-spelling rules stay the same.
WHAT NOT TO DO IN THIS FILE: 1. Do not iterate a set of strings to build an output; sets here only answer membership questions. 2. Do not expand an integer range to count it; the count is the arithmetic sum of the range sizes. 3. Do not call int on unchecked digit runs, because Python refuses more than 4,300 digits.
KNOWN EDGE CASES: Case-insensitive grouping uses casefold, so a sharp s groups with a double s and the first spelling seen is reported. Range text such as a run from minus three to minus one is written with both minus signs, and expanding it reads the second hyphen as the start of a negative number. Blank range text expands to an empty list.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.24, section 9.2 items 2, 7, 12, and 14); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_identifiers_lists_graphs.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_MAX_INTEGER_RANGE_SPAN,
    PREBUILT_MAX_LIST_ITEMS,
    PREBUILT_MAX_LISTS,
    PREBUILT_MAX_MEDIUM_TEXT_CHARS,
    PREBUILT_MAX_RANDOM_MAGNITUDE,
    PREBUILT_MAX_SHORT_TEXT_CHARS,
    PREBUILT_MAX_TOP_ITEMS,
)
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_RANGE_PIECE = re.compile(r"\s*(-?[0-9]+)\s*(?:-\s*(-?[0-9]+)\s*)?")
_MAX_MAGNITUDE_DIGITS = len(str(PREBUILT_MAX_RANDOM_MAGNITUDE))

_ITEMS_PARAMETER_DESCRIPTION = "The list of text items to examine, in their original order. Items are compared as whole strings, so surrounding spaces count. The list may hold at most 10,000 items. Each item may hold at most 10,000 characters."
_CASE_SENSITIVE_PARAMETER_DESCRIPTION = "Whether items that differ only in case count as different items. When false, items are compared by their case-folded form and the first spelling seen is reported. The default is true. Folding follows the full Unicode case folding rules."
_INTEGER_VALUES_PARAMETER_DESCRIPTION = "The integers to use, in any order and with repeats allowed. Each value must be between minus one quadrillion and one quadrillion. The list must hold at least one value. It may hold at most 10,000 values."


class ListsToolFunctions:
    """The lists category: frequencies, duplicates, set comparisons, and integer ranges."""

    @staticmethod
    def count_item_frequencies(
        items: Annotated[list[Annotated[str, Field(max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)]], Field(description=_ITEMS_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_LIST_ITEMS)],
        case_sensitive: Annotated[bool, Field(description=_CASE_SENSITIVE_PARAMETER_DESCRIPTION)] = True,
        top: Annotated[int, Field(description="How many of the most frequent items to list. Items are ranked by count, highest first, and ties keep their order of first appearance. The totals in the result still cover every item, not only the listed ones. The value must be between 1 and 1,000.", ge=1, le=PREBUILT_MAX_TOP_ITEMS)] = 100,
    ) -> PrebuiltToolOutput:
        """Count how often each distinct item occurs in a list and list the most frequent items with their counts. Use it to tally votes, tags, categories, or any repeated values exactly instead of estimating. Items are ranked by count, highest first, with ties kept in order of first appearance, and case_sensitive false groups items by their case-folded form under the first spelling seen. At most top items are listed while total and distinct cover the whole list, and the tool has no failure case beyond its caps."""
        # Group the positions of each item, then rank the groups; the
        # sort is stable, so equal counts keep first-appearance order.
        grouped = ListsToolFunctions._positions_by_item(items, case_sensitive)
        ranked = sorted(grouped.values(), key=lambda entry: -len(entry[1]))
        frequencies = [{"item": spelling, "count": len(positions)} for spelling, positions in ranked[:top]]
        return {"total": len(items), "distinct": len(grouped), "frequencies": frequencies}

    @staticmethod
    def find_duplicate_items(
        items: Annotated[list[Annotated[str, Field(max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)]], Field(description=_ITEMS_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_LIST_ITEMS)],
        case_sensitive: Annotated[bool, Field(description=_CASE_SENSITIVE_PARAMETER_DESCRIPTION)] = True,
    ) -> PrebuiltToolOutput:
        """List the items that occur more than once in a list, with how many times each occurs and the 0-based positions where it occurs. Use it to find repeated entries before deduplicating, merging, or loading a list. Duplicates are listed in order of first appearance, and duplicate_count is the number of distinct repeated items. With case_sensitive false, items are grouped by their case-folded form under the first spelling seen, and the tool has no failure case beyond its caps."""
        grouped = ListsToolFunctions._positions_by_item(items, case_sensitive)
        duplicates = [{"item": spelling, "count": len(positions), "indices": positions} for spelling, positions in grouped.values() if len(positions) > 1]
        return {"duplicates": duplicates, "duplicate_count": len(duplicates)}

    @staticmethod
    def compare_two_lists(
        first: Annotated[list[Annotated[str, Field(max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)]], Field(description="The first list of text items, whose order decides the order of the shared items. Items are compared as whole strings, so surrounding spaces count. The list may hold at most 10,000 items. Each item may hold at most 10,000 characters.", max_length=PREBUILT_MAX_LIST_ITEMS)],
        second: Annotated[list[Annotated[str, Field(max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)]], Field(description="The second list of text items to compare with the first. Items are compared as whole strings, so surrounding spaces count. The list may hold at most 10,000 items. Each item may hold at most 10,000 characters.", max_length=PREBUILT_MAX_LIST_ITEMS)],
        case_sensitive: Annotated[bool, Field(description=_CASE_SENSITIVE_PARAMETER_DESCRIPTION)] = True,
    ) -> PrebuiltToolOutput:
        """Split two lists into the distinct items found only in the first, only in the second, and in both, with a count for each group. Use it to reconcile two lists of names, identifiers, or keys and see what was added or removed. Each distinct item appears once, in its own list's order of first appearance, and the shared items follow the first list. With case_sensitive false, items match by their case-folded form and the first spelling seen in each list is reported, and the tool has no failure case beyond its caps."""
        # Keep each distinct item once per list, in first-appearance
        # order, keyed by the form used for matching.
        first_items = ListsToolFunctions._distinct_items(first, case_sensitive)
        second_items = ListsToolFunctions._distinct_items(second, case_sensitive)

        # Walk each list in its own order and sort its items into
        # groups.
        only_first = [spelling for key, spelling in first_items.items() if key not in second_items]
        only_second = [spelling for key, spelling in second_items.items() if key not in first_items]
        in_both = [spelling for key, spelling in first_items.items() if key in second_items]
        return {
            "only_in_first": only_first,
            "only_in_second": only_second,
            "in_both": in_both,
            "only_in_first_count": len(only_first),
            "only_in_second_count": len(only_second),
            "in_both_count": len(in_both),
        }

    @staticmethod
    def intersect_lists(
        lists: Annotated[list[Annotated[list[Annotated[str, Field(max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)]], Field(max_length=PREBUILT_MAX_LIST_ITEMS)]], Field(description="The lists to intersect, given as two or more lists of text items. The first list decides the order of the result. There may be at most 100 lists, and each item may hold at most 10,000 characters. All the lists together may hold at most 10,000 items.", min_length=2, max_length=PREBUILT_MAX_LISTS)],
        case_sensitive: Annotated[bool, Field(description=_CASE_SENSITIVE_PARAMETER_DESCRIPTION)] = True,
    ) -> PrebuiltToolOutput:
        """Find the distinct items that appear in every one of several lists, in the order of the first list. Use it to find the names, tags, or keys that a whole set of lists share. Repeats within a list do not matter, and with case_sensitive false the items match by their case-folded form under the first list's spelling. The lists together may hold at most 10,000 items, and more fails with an error naming lists."""
        # Refuse more items in total than one list may hold.
        total = sum(len(group) for group in lists)
        if total > PREBUILT_MAX_LIST_ITEMS:
            raise PrebuiltToolSupport.argument_error("lists", f"the lists hold {total} items together", f"at most {PREBUILT_MAX_LIST_ITEMS} items across all the lists")

        # Keep the distinct items of the first list that every other
        # list also has.
        candidates = ListsToolFunctions._distinct_items(lists[0], case_sensitive)
        others = [ListsToolFunctions._distinct_items(group, case_sensitive) for group in lists[1:]]
        common = [spelling for key, spelling in candidates.items() if all(key in other for other in others)]
        return {"common": common, "count": len(common)}

    @staticmethod
    def find_missing_integers(
        values: Annotated[list[Annotated[int, Field(ge=-PREBUILT_MAX_RANDOM_MAGNITUDE, le=PREBUILT_MAX_RANDOM_MAGNITUDE)]], Field(description="The integers that are present, in any order and with repeats allowed. Each value must be between minus one quadrillion and one quadrillion. The list must hold at least one value and at most 10,000. Values outside the searched range are ignored.", min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS)],
        start: Annotated[int | None, Field(description="The first integer of the range to search, included in the range. When null or omitted, it is the smallest value given. It must not be greater than end. The end may be at most ten million above it.")] = None,
        end: Annotated[int | None, Field(description="The last integer of the range to search, included in the range. When null or omitted, it is the largest value given. It must not be less than start, or the call fails naming end. It may be at most ten million above start.")] = None,
    ) -> PrebuiltToolOutput:
        """List the integers missing from a sequence within a range, in ascending order, with how many are missing. Use it to find gaps in invoice numbers, record numbers, or page numbers. The range runs from start to end inclusive, and a null bound defaults to the smallest or largest value given. At most 1,000 missing integers are listed while count covers them all, and an end before start or more than ten million above it fails with an error naming end."""
        # Fill in the default bounds, then check the range they make.
        low = min(values) if start is None else start
        high = max(values) if end is None else end
        if high < low:
            raise PrebuiltToolSupport.argument_error("end", "the range ends before it starts", "an end that is not less than the start")
        if high - low > PREBUILT_MAX_INTEGER_RANGE_SPAN:
            raise PrebuiltToolSupport.argument_error("end", "the range is too wide", f"an end at most {PREBUILT_MAX_INTEGER_RANGE_SPAN} above the start")

        # Count the gaps arithmetically, then list the first of them.
        present = {value for value in values if low <= value <= high}
        missing, truncated = PrebuiltToolSupport.cap_items(value for value in range(low, high + 1) if value not in present)
        return {"missing": missing, "count": high - low + 1 - len(present), "truncated": truncated}

    @staticmethod
    def compress_integer_ranges(
        values: Annotated[list[Annotated[int, Field(ge=-PREBUILT_MAX_RANDOM_MAGNITUDE, le=PREBUILT_MAX_RANDOM_MAGNITUDE)]], Field(description=_INTEGER_VALUES_PARAMETER_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS)],
    ) -> PrebuiltToolOutput:
        """Collapse a list of integers into the fewest runs of consecutive values and write them as compact range text. Use it to summarize page numbers, record numbers, or line numbers, or to build range text for another tool. Values are sorted and made distinct first, each run is written as its two ends joined by a hyphen or as one value, and runs are joined with commas, so a run with negative ends keeps both minus signs. The list must hold at least one value, and the tool has no other failure case."""
        # Sort the distinct values and start a new run at every gap.
        ranges: list[dict[str, int]] = []
        for value in sorted(set(values)):
            if ranges and value == ranges[-1]["end"] + 1:
                ranges[-1]["end"] = value
            else:
                ranges.append({"start": value, "end": value})

        # Write each run as a-b, or as a alone when it holds one value.
        text = ",".join(f"{run['start']}-{run['end']}" if run["start"] != run["end"] else str(run["start"]) for run in ranges)
        return {"ranges": ranges, "text": text, "count": len(ranges)}

    @staticmethod
    def expand_integer_ranges(
        text: Annotated[str, Field(description="The range text to expand, made of tokens separated by commas. Each token is one integer or two integers joined by a hyphen, and a minus sign may start either integer. Whitespace around tokens and numbers is ignored, and blank text gives an empty list. The text may hold at most 100,000 characters.", max_length=PREBUILT_MAX_MEDIUM_TEXT_CHARS)],
    ) -> PrebuiltToolOutput:
        """Expand range text made of single integers and inclusive integer ranges into the list of integers it covers. Use it to turn page selections, record ranges, or line ranges written by people into explicit numbers. Tokens are separated by commas with whitespace ignored, each token is one integer or a low-high pair with negatives allowed, and values keep token order with duplicates included. At most 10,000 values are listed while count gives the full total as integer text, and a bad token, a low end above its high end, or a magnitude over one quadrillion fails with an error naming text."""
        # Read every token first, so a bad one fails before any output.
        bounds = [] if not text.strip() else [ListsToolFunctions._range_bounds(piece, position) for position, piece in enumerate(text.split(","), start=1)]

        # Count every value arithmetically, then list values lazily up
        # to the item cap so a huge range is never expanded.
        total = sum(high - low + 1 for low, high in bounds)
        values, truncated = PrebuiltToolSupport.cap_items((value for low, high in bounds for value in range(low, high + 1)), PREBUILT_MAX_LIST_ITEMS)
        return {"values": values, "count": PrebuiltToolSupport.integer_text(total, "text"), "truncated": truncated}

    @staticmethod
    def _positions_by_item(items: Sequence[str], case_sensitive: bool) -> dict[str, tuple[str, list[int]]]:
        """Group item positions by the item, or its case-folded form, keeping the first spelling and first-appearance order."""
        grouped: dict[str, tuple[str, list[int]]] = {}
        for position, item in enumerate(items):
            key = item if case_sensitive else item.casefold()
            grouped.setdefault(key, (item, []))[1].append(position)
        return grouped

    @staticmethod
    def _distinct_items(items: Sequence[str], case_sensitive: bool) -> dict[str, str]:
        """Map each distinct matching form to the first spelling seen, in first-appearance order."""
        distinct: dict[str, str] = {}
        for item in items:
            distinct.setdefault(item if case_sensitive else item.casefold(), item)
        return distinct

    @staticmethod
    def _range_bounds(piece: str, position: int) -> tuple[int, int]:
        """Read one range token as its low and high ends, failing on a bad token, a reversed range, or a huge magnitude."""
        expected = f"comma-separated integers or low-high ranges with magnitudes of at most {PREBUILT_MAX_RANDOM_MAGNITUDE}"
        match = _RANGE_PIECE.fullmatch(piece)
        if match is None:
            raise PrebuiltToolSupport.argument_error("text", f"token {position} is not an integer or a range of two integers", expected)
        parts = [part for part in match.groups() if part is not None]
        digit_runs = [part.lstrip("-").lstrip("0") or "0" for part in parts]
        # @intent prebuilt-integer-digit-cap
        # Leading zeros are dropped and a digit run longer than the
        # largest allowed magnitude fails before int() sees it, because
        # Python refuses to read more than 4,300 digits.
        if any(len(run) > _MAX_MAGNITUDE_DIGITS for run in digit_runs) or any(int(run) > PREBUILT_MAX_RANDOM_MAGNITUDE for run in digit_runs):
            raise PrebuiltToolSupport.argument_error("text", f"token {position} has a number of magnitude over {PREBUILT_MAX_RANDOM_MAGNITUDE}", expected)
        numbers = [-int(run) if part.startswith("-") else int(run) for part, run in zip(parts, digit_runs, strict=True)]
        low, high = numbers[0], numbers[-1]
        if low > high:
            raise PrebuiltToolSupport.argument_error("text", f"token {position} runs from a higher number down to a lower one", expected)
        return low, high

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.count_item_frequencies,
            cls.find_duplicate_items,
            cls.compare_two_lists,
            cls.intersect_lists,
            cls.find_missing_integers,
            cls.compress_integer_ranges,
            cls.expand_integer_ranges,
        )


__all__ = ["ListsToolFunctions"]
