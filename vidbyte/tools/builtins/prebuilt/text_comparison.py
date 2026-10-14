"""FILE: vidbyte/tools/builtins/prebuilt/text_comparison.py

PURPOSE: Defines TextComparisonToolFunctions, the six prebuilt tools that compare two texts: a unified line diff, a word diff, the Levenshtein edit distance, fuzzy ranking of candidates against a query, the longest common substring, and n-gram Jaccard similarity.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the TEXT_COMPARISON category is chosen. Builds on PrebuiltToolSupport in _support.py for the line and word rules and the argument error, and on the NFR-7 caps in vidbyte/lib/constants/prebuilt_tools.py.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. The diff, ranking, and substring tools use difflib, and every SequenceMatcher built here passes autojunk=False so frequent elements still match, while unified_diff keeps its own default. The edit distance uses a bit-parallel algorithm over Python integers, which handles the longest allowed strings in milliseconds where a cell-by-cell table would take seconds.
FUNCTION INVENTORY: unified_diff_text, diff_words, levenshtein_distance, closest_string_matches, longest_common_substring, and jaccard_similarity are the tools; _edit_distance computes the Levenshtein distance; _ngram_set builds the distinct n-grams of one text; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new comparison tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.16, and its entry in tool_functions. A cap that bounds a slow algorithm changes in vidbyte/lib/constants/prebuilt_tools.py together with the NFR-7 measurement in the spec, never here.
WHAT NOT TO DO IN THIS FILE: 1. Do not build a SequenceMatcher without autojunk=False; its default treats frequent elements of a long sequence as junk and changes the results. 2. Do not lowercase instead of case folding; case-insensitive comparison uses str.casefold under section 9.2 item 7. 3. Do not split lines or words with a local rule; use PrebuiltToolSupport so every category agrees.
KNOWN EDGE CASES: Case folding can lengthen a string, so the lengths in the Levenshtein similarity are those of the folded strings. The unified diff compares lines without their line breaks, so two texts that differ only in line-break style give an empty diff while identical is false. SequenceMatcher can be very slow on long periodic sequences, which the schema caps bound but do not remove (spec NFR-7).
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.16, section 9.2 items 6 to 8, NFR-7); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_unicode_regex.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import difflib
import re
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_MAX_CONTEXT_LINES,
    PREBUILT_MAX_DIFF_LINES,
    PREBUILT_MAX_DIFF_TOKENS,
    PREBUILT_MAX_FUZZY_CANDIDATE_CHARS,
    PREBUILT_MAX_FUZZY_CANDIDATES,
    PREBUILT_MAX_MEDIUM_TEXT_CHARS,
    PREBUILT_MAX_NAME_CHARS,
    PREBUILT_MAX_NGRAM_SIZE,
    PREBUILT_MAX_PAIRWISE_CHARS,
    PREBUILT_MAX_SEQUENCE_MATCH_CHARS,
    PREBUILT_MAX_TEXT_CHARS,
    PREBUILT_MAX_TOP_ITEMS,
)
from vidbyte.lib.enums.prebuilt_tools import DiffOperation, NgramUnit
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_WORD_DIFF_PIECES = re.compile(r"\s+|\S+")
_DIFF_HEADER_LINES = 2

_ORIGINAL_DIFF_TEXT_DESCRIPTION = "The earlier version of the text, given as plain characters. It is split into lines at CRLF, LF, or a lone CR, and a final line break does not add an empty line. It may hold at most 4,000 lines, or the call fails naming this parameter. The text may hold at most one million characters."
_MODIFIED_DIFF_TEXT_DESCRIPTION = "The later version of the text, given as plain characters. It is split into lines at CRLF, LF, or a lone CR, and a final line break does not add an empty line. It may hold at most 4,000 lines, or the call fails naming this parameter. The text may hold at most one million characters."
_ORIGINAL_WORDS_DESCRIPTION = "The earlier version of the text, given as plain characters. It is cut into runs of non-whitespace characters and runs of whitespace, and each run is one piece. It may hold at most 2,000 pieces, or the call fails naming this parameter. The text may hold at most one hundred thousand characters."
_MODIFIED_WORDS_DESCRIPTION = "The later version of the text, given as plain characters. It is cut into runs of non-whitespace characters and runs of whitespace, and each run is one piece. It may hold at most 2,000 pieces, or the call fails naming this parameter. The text may hold at most one hundred thousand characters."
_PAIRWISE_STRING_DESCRIPTION = "One of the two strings to compare, given as plain characters. Each Unicode code point is one character, so an emoji counts once. It may be empty. It may hold at most 1,000 characters."
_SUBSTRING_TEXT_DESCRIPTION = "One of the two texts to search for a shared run, given as plain characters. Matching is exact, so case and accents must agree. It may be empty. It may hold at most 2,000 characters."
_JACCARD_TEXT_DESCRIPTION = "One of the two texts to compare, given as plain characters. Word n-grams follow the Unicode letter-and-digit word rule, and character n-grams run over the raw text. It may be empty. The text may hold at most one million characters."


class TextComparisonToolFunctions:
    """The text_comparison category: diffs, edit distance, fuzzy matching, shared substrings, and n-gram overlap."""

    @staticmethod
    def unified_diff_text(
        original: Annotated[str, Field(description=_ORIGINAL_DIFF_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        modified: Annotated[str, Field(description=_MODIFIED_DIFF_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        context_lines: Annotated[int, Field(description="How many unchanged lines to show before and after each change. Changes whose context overlaps are merged into one hunk. Zero shows only the changed lines. The value must be between 0 and 100, and the default is 3.", ge=0, le=PREBUILT_MAX_CONTEXT_LINES)] = 3,
        original_label: Annotated[str, Field(description="The name shown for the earlier version in the first header line of the diff. It is copied into the header as given and has no other effect. It must hold 1 to 200 characters. The default is original.", min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)] = "original",
        modified_label: Annotated[str, Field(description="The name shown for the later version in the second header line of the diff. It is copied into the header as given and has no other effect. It must hold 1 to 200 characters. The default is modified.", min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)] = "modified",
    ) -> PrebuiltToolOutput:
        """Produce a unified diff between two versions of a text, with the number of added and removed lines. Use it to show or review exactly what changed between two drafts, files, or outputs. Lines split at CRLF, LF, or CR and are compared without their line breaks, and identical compares the exact texts, so a change only in line-break style gives an empty diff while identical is false. Either text with more than 4,000 lines fails with an error naming that text."""
        # Split both texts into lines and refuse one past the line cap,
        # which keeps the diff within its time budget.
        original_lines = PrebuiltToolSupport.split_lines(original)
        modified_lines = PrebuiltToolSupport.split_lines(modified)
        for parameter, lines in (("original", original_lines), ("modified", modified_lines)):
            if len(lines) > PREBUILT_MAX_DIFF_LINES:
                raise PrebuiltToolSupport.argument_error(parameter, f"the text has {len(lines)} lines", f"text with at most {PREBUILT_MAX_DIFF_LINES} lines")

        # Build the diff, then count added and removed lines below the
        # two file header lines.
        diff = list(difflib.unified_diff(original_lines, modified_lines, fromfile=original_label, tofile=modified_label, n=context_lines, lineterm=""))
        body = diff[_DIFF_HEADER_LINES:]
        return {
            "diff": "\n".join(diff),
            "added_lines": sum(1 for line in body if line.startswith("+")),
            "removed_lines": sum(1 for line in body if line.startswith("-")),
            "identical": original == modified,
        }

    @staticmethod
    def diff_words(
        original: Annotated[str, Field(description=_ORIGINAL_WORDS_DESCRIPTION, max_length=PREBUILT_MAX_MEDIUM_TEXT_CHARS)],
        modified: Annotated[str, Field(description=_MODIFIED_WORDS_DESCRIPTION, max_length=PREBUILT_MAX_MEDIUM_TEXT_CHARS)],
    ) -> PrebuiltToolOutput:
        """Compare two texts word by word and return the runs of equal, inserted, deleted, and replaced text with an overall similarity ratio. Use it to show small edits inside sentences or paragraphs, where a line diff would mark whole lines as changed. Words are runs of non-whitespace characters, whitespace runs are pieces of their own, each run carries the original and modified text it covers, and the similarity is twice the matched pieces over all pieces. Either text with more than 2,000 pieces fails with an error naming that text."""
        # Cut both texts into word and whitespace pieces and refuse one
        # past the piece cap, which keeps the matcher within its budget.
        original_pieces = _WORD_DIFF_PIECES.findall(original)
        modified_pieces = _WORD_DIFF_PIECES.findall(modified)
        for parameter, pieces in (("original", original_pieces), ("modified", modified_pieces)):
            if len(pieces) > PREBUILT_MAX_DIFF_TOKENS:
                raise PrebuiltToolSupport.argument_error(parameter, f"the text has {len(pieces)} word and whitespace pieces", f"text with at most {PREBUILT_MAX_DIFF_TOKENS} pieces")

        # Match the two piece sequences and report each step with the
        # text it covers on both sides.
        matcher = difflib.SequenceMatcher(None, original_pieces, modified_pieces, autojunk=False)
        operations = [
            {"op": DiffOperation(tag).value, "original": "".join(original_pieces[first_start:first_end]), "modified": "".join(modified_pieces[second_start:second_end])}
            for tag, first_start, first_end, second_start, second_end in matcher.get_opcodes()
        ]
        return {"operations": operations, "similarity": matcher.ratio()}

    @staticmethod
    def levenshtein_distance(
        first: Annotated[str, Field(description=_PAIRWISE_STRING_DESCRIPTION, max_length=PREBUILT_MAX_PAIRWISE_CHARS)],
        second: Annotated[str, Field(description=_PAIRWISE_STRING_DESCRIPTION, max_length=PREBUILT_MAX_PAIRWISE_CHARS)],
        case_sensitive: Annotated[bool, Field(description="Whether uppercase and lowercase letters count as different. When false, both strings are case folded before comparing, which can lengthen a string that holds a sharp s or a ligature. The default is true. The lengths in the similarity are those of the compared strings.")] = True,
    ) -> PrebuiltToolOutput:
        """Count the fewest single-character insertions, deletions, and substitutions that turn one string into another, with a similarity score. Use it to measure how close two words, names, or codes are, or to judge whether one is a typo of the other. Characters are Unicode code points, every edit costs one, and the similarity is one minus the distance divided by the longer length, which is one for two empty strings. Without case sensitivity both strings are case folded first, and each string may hold at most 1,000 characters."""
        # Fold case first when asked, so the edits compare folded text.
        left, right = (first, second) if case_sensitive else (first.casefold(), second.casefold())
        distance = TextComparisonToolFunctions._edit_distance(left, right)
        longest = max(len(left), len(right))
        return {"distance": distance, "similarity": 1.0 - distance / longest if longest else 1.0}

    @staticmethod
    def closest_string_matches(
        query: Annotated[str, Field(description="The string to look for, given as plain characters. It is compared with every candidate. It may be empty and may hold at most 100 characters. Longer input is refused because the comparison cost grows quickly with length.", max_length=PREBUILT_MAX_FUZZY_CANDIDATE_CHARS)],
        candidates: Annotated[list[Annotated[str, Field(max_length=PREBUILT_MAX_FUZZY_CANDIDATE_CHARS)]], Field(description="The strings to rank against the query, in any order. The index in the result is the position in this list, starting at zero. The list may hold at most 1,000 strings of at most 100 characters each. An empty list gives no matches.", max_length=PREBUILT_MAX_FUZZY_CANDIDATES)],
        top: Annotated[int, Field(description="How many of the best matches to return. Matches below minimum_score are dropped before the best ones are chosen. The value must be between 1 and 1,000. The default is 5.", ge=1, le=PREBUILT_MAX_TOP_ITEMS)] = 5,
        minimum_score: Annotated[float, Field(description="The lowest score a candidate may have and still be returned. Scores run from 0, sharing nothing, to 1, identical. The value must be between 0 and 1. The default is 0, which keeps every candidate.", ge=0, le=1, allow_inf_nan=False)] = 0.0,
        case_sensitive: Annotated[bool, Field(description="Whether uppercase and lowercase letters count as different. When false, the query and every candidate are case folded before scoring, but results show the candidates as given. The default is false. Folding can lengthen a string that holds a sharp s or a ligature.")] = False,
    ) -> PrebuiltToolOutput:
        """Rank candidate strings by how similar they are to a query and return the best ones with their scores and positions in the list. Use it for fuzzy lookup, such as matching a misspelled name against a list of known names. The score is the difflib SequenceMatcher ratio from 0 to 1, results are sorted by score and then by position, and candidates scoring below minimum_score are dropped. At most top results are returned, comparisons ignore case unless case_sensitive is true, and the tool has no failure case beyond its caps."""
        # Score every candidate against the query, folding case on both
        # sides unless case matters.
        folded_query = query if case_sensitive else query.casefold()
        scored: list[tuple[float, int]] = []
        for index, candidate in enumerate(candidates):
            compared = candidate if case_sensitive else candidate.casefold()
            score = difflib.SequenceMatcher(None, folded_query, compared, autojunk=False).ratio()
            if score >= minimum_score:
                scored.append((score, index))

        # Rank by score, highest first, then by position in the list.
        scored.sort(key=lambda entry: (-entry[0], entry[1]))
        return {"matches": [{"candidate": candidates[index], "index": index, "score": score} for score, index in scored[:top]]}

    @staticmethod
    def longest_common_substring(
        first: Annotated[str, Field(description=_SUBSTRING_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_SEQUENCE_MATCH_CHARS)],
        second: Annotated[str, Field(description=_SUBSTRING_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_SEQUENCE_MATCH_CHARS)],
    ) -> PrebuiltToolOutput:
        """Find the longest run of consecutive characters that two texts share, with its length and its position in each text. Use it to find the shared core of two names, identifiers, or passages. Positions count code points from zero, and when several runs share the longest length the one that starts earliest in the first text is returned. Texts with no character in common give an empty substring, a length of zero, and null positions, and each text may hold at most 2,000 characters."""
        found = difflib.SequenceMatcher(None, first, second, autojunk=False).find_longest_match(0, len(first), 0, len(second))
        if not found.size:
            return {"substring": "", "length": 0, "first_position": None, "second_position": None}
        return {"substring": first[found.a : found.a + found.size], "length": found.size, "first_position": found.a, "second_position": found.b}

    @staticmethod
    def jaccard_similarity(
        first: Annotated[str, Field(description=_JACCARD_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        second: Annotated[str, Field(description=_JACCARD_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        unit: Annotated[NgramUnit, Field(description="Whether n-grams are built from words or from characters. Word n-grams follow the Unicode letter-and-digit word rule and are joined by one space. Character n-grams run over the raw text, whitespace included. The default is words.")] = NgramUnit.WORDS,
        n: Annotated[int, Field(description="How many words or characters make up one n-gram. Larger values reward shared phrases rather than shared single words. The value must be between 1 and 10, and the default is 1. A text shorter than n units contributes no n-grams.", ge=1, le=PREBUILT_MAX_NGRAM_SIZE)] = 1,
        case_sensitive: Annotated[bool, Field(description="Whether n-grams that differ only in case count as different. When false, each n-gram is case folded before the sets are compared. The default is false. Folding never changes how the text is split into words.")] = False,
    ) -> PrebuiltToolOutput:
        """Score how much two texts overlap as the number of distinct n-grams they share divided by the number of distinct n-grams found in either. Use it to compare documents, detect near duplicates, or rank texts by shared vocabulary. The n-grams are sequences of n words joined by a space or of n characters including whitespace, built as the n-gram frequency tool builds them, and they are compared without regard to case unless case_sensitive is true. Two texts with no n-grams at all score one, and the tool has no failure case beyond its caps."""
        first_set = TextComparisonToolFunctions._ngram_set(first, unit, n, case_sensitive)
        second_set = TextComparisonToolFunctions._ngram_set(second, unit, n, case_sensitive)
        # The union is counted from the two sizes, so a third set of
        # every n-gram is never built.
        intersection = len(first_set & second_set)
        union = len(first_set) + len(second_set) - intersection
        return {"jaccard": intersection / union if union else 1.0, "intersection": intersection, "union": union}

    @staticmethod
    def _edit_distance(first: str, second: str) -> int:
        """Return the Levenshtein distance with the bit-parallel algorithm of Myers as reformulated by Hyyrö."""
        if not first:
            return len(second)
        # Bit i of a symbol's mask is set where that symbol sits in the
        # first string; the vertical deltas of one column of the edit
        # table are held as two bit vectors, positive and negative.
        masks: dict[str, int] = {}
        for index, symbol in enumerate(first):
            masks[symbol] = masks.get(symbol, 0) | (1 << index)
        full = (1 << len(first)) - 1
        top = 1 << (len(first) - 1)
        positive, negative, distance = full, 0, len(first)
        # Each symbol of the second string advances the table by one
        # column, and the bottom row's change updates the distance.
        for symbol in second:
            match = masks.get(symbol, 0)
            diagonal = ((((match & positive) + positive) ^ positive) | match | negative) & full
            horizontal_up = negative | ~(diagonal | positive) & full
            horizontal_down = diagonal & positive
            distance += bool(horizontal_up & top) - bool(horizontal_down & top)
            horizontal_up = ((horizontal_up << 1) | 1) & full
            horizontal_down = (horizontal_down << 1) & full
            positive = horizontal_down | ~(diagonal | horizontal_up) & full
            negative = horizontal_up & diagonal
        return distance

    @staticmethod
    def _ngram_set(text: str, unit: NgramUnit, n: int, case_sensitive: bool) -> set[str]:
        """Build the distinct word or character n-grams of one text, case folded unless case matters."""
        if unit is NgramUnit.CHARACTERS:
            grams = (text[start : start + n] for start in range(len(text) - n + 1))
        else:
            words = [word for _, word in PrebuiltToolSupport.split_words(text)]
            grams = (" ".join(words[start : start + n]) for start in range(len(words) - n + 1))
        return set(grams) if case_sensitive else {gram.casefold() for gram in grams}

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.unified_diff_text,
            cls.diff_words,
            cls.levenshtein_distance,
            cls.closest_string_matches,
            cls.longest_common_substring,
            cls.jaccard_similarity,
        )


__all__ = ["TextComparisonToolFunctions"]
