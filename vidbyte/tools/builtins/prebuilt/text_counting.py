"""FILE: vidbyte/tools/builtins/prebuilt/text_counting.py

PURPOSE: Defines TextCountingToolFunctions, the twelve prebuilt tools that count and locate things in a text: characters by kind, one character, a substring, words, sentences, lines, word, character, and n-gram frequencies, the character at a position, readability scores, and syllables.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the TEXT_COUNTING category is chosen. Builds on PrebuiltToolSupport in _support.py for the line, word, sentence, and syllable rules, the item cap, and the argument error.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Counting runs over collections.Counter so a million-character text is tallied in C, and the three frequency tools share one private ranking helper.
FUNCTION INVENTORY: count_characters, count_character_occurrences, find_substring_positions, count_words, count_sentences, count_lines, word_frequencies, character_frequencies, ngram_frequencies, character_at_position, readability_scores, and count_syllables are the tools; _rank_counts groups and ranks tallies for the frequency tools; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new counting tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.12, and its entry in tool_functions. Shared word, sentence, line, and syllable rules change only in PrebuiltToolSupport.
WHAT NOT TO DO IN THIS FILE: 1. Do not split words, sentences, or lines with a local rule; use PrebuiltToolSupport so every category agrees. 2. Do not lowercase text before a positional search; re.IGNORECASE keeps positions on the original text. 3. Do not iterate a set or a hash-ordered container when building an output.
KNOWN EDGE CASES: Positions and lengths count code points, so an emoji counts once. A case-insensitive search folds one code point at a time, so a sharp s never matches a double s. A carriage return followed by a line feed is one line break, so the line feed belongs to the line it ends.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.12, section 9.2 items 6 to 10); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_text.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Mapping
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_MAX_NGRAM_SIZE,
    PREBUILT_MAX_RESULT_ITEMS,
    PREBUILT_MAX_SEARCH_STRING_CHARS,
    PREBUILT_MAX_TEXT_CHARS,
    PREBUILT_MAX_TOP_ITEMS,
)
from vidbyte.lib.enums.prebuilt_tools import NgramUnit
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_SCORE_PLACES = 2

_TEXT_PARAMETER_DESCRIPTION = "The text to examine, given as plain characters. Positions and lengths count Unicode code points, so an emoji or an accented letter counts once. Line breaks may be CRLF, LF, or a lone CR. The text may hold at most one million characters."
_TOP_PARAMETER_DESCRIPTION = "How many of the most frequent entries to list. Entries are ranked by count, highest first, and ties are broken by code-point order. The totals in the result still cover every entry, not only the listed ones. The value must be between 1 and 1,000."


class TextCountingToolFunctions:
    """The text_counting category: counting and locating characters, words, sentences, and lines."""

    @staticmethod
    def count_characters(text: Annotated[str, Field(description=_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Count the characters in a text, in total and broken down into letters, digits, whitespace, punctuation, uppercase, lowercase, and non-whitespace. Use it whenever an exact character count matters, because a model cannot count characters reliably by reading. Every count is of Unicode code points, and each kind follows the Unicode character properties. Empty text gives all zeros, and the tool has no failure case beyond the text length cap."""
        # Tally each distinct character once, then add up the tallies of
        # the characters that belong to each kind.
        tallies = Counter(text)
        return {
            "characters": len(text),
            "non_whitespace": sum(count for character, count in tallies.items() if not character.isspace()),
            "letters": sum(count for character, count in tallies.items() if character.isalpha()),
            "digits": sum(count for character, count in tallies.items() if character.isdecimal()),
            "whitespace": sum(count for character, count in tallies.items() if character.isspace()),
            "punctuation": sum(count for character, count in tallies.items() if unicodedata.category(character).startswith("P")),
            "uppercase": sum(count for character, count in tallies.items() if character.isupper()),
            "lowercase": sum(count for character, count in tallies.items() if character.islower()),
        }

    @staticmethod
    def count_character_occurrences(
        text: Annotated[str, Field(description=_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        character: Annotated[str, Field(description="The single character to look for, given as exactly one Unicode code point. It is matched literally, never as a pattern. An emoji made of one code point counts as one character. Text of any other length fails validation.", min_length=1, max_length=1)],
        case_sensitive: Annotated[bool, Field(description="Whether uppercase and lowercase must match exactly. When false, the match folds case one code point at a time, so positions still point into the original text. The default is true. Folding never turns one character into two.")] = True,
    ) -> PrebuiltToolOutput:
        """Count how many times one character appears in a text and list the 0-based positions where it appears. Use it for questions such as how many times a letter occurs in a word, which models often get wrong. Positions count Unicode code points, and at most 1,000 positions are listed while the count covers every occurrence. The character must be exactly one code point, and anything else fails validation."""
        # Build a literal pattern so the character is never read as
        # regex syntax, folding case only when asked.
        pattern = re.compile(re.escape(character), 0 if case_sensitive else re.IGNORECASE)

        # Count every occurrence, then list positions up to the cap.
        count = sum(1 for _ in pattern.finditer(text))
        positions, truncated = PrebuiltToolSupport.cap_items(match.start() for match in pattern.finditer(text))
        return {"count": count, "positions": positions, "truncated": truncated}

    @staticmethod
    def find_substring_positions(
        text: Annotated[str, Field(description=_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        substring: Annotated[str, Field(description="The literal text to search for, which is never read as a pattern. It must hold at least one character and at most five hundred. Characters that are special in regular expressions only match themselves. Case folding applies only when case_sensitive is false.", min_length=1, max_length=PREBUILT_MAX_SEARCH_STRING_CHARS)],
        case_sensitive: Annotated[bool, Field(description="Whether uppercase and lowercase must match exactly. When false, the match folds case one code point at a time, so positions still point into the original text. The default is true. Folding never matches one character against two.")] = True,
        allow_overlap: Annotated[bool, Field(description="Whether matches may overlap one another. When true, the search steps forward one position after each match start. When false, the search continues after the end of each match. The default is true.")] = True,
    ) -> PrebuiltToolOutput:
        """Find every 0-based position where a literal substring occurs in a text, with overlapping matches allowed by default. Use it to count or locate a word, phrase, or symbol exactly instead of estimating. Positions count Unicode code points, and at most 1,000 positions are listed while the count covers every match. An empty substring fails validation, and no other input fails."""
        # A lookahead finds a match starting at every position, which
        # is how overlapping matches are counted; a plain pattern skips
        # past each match instead.
        literal = re.escape(substring)
        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = re.compile(f"(?={literal})" if allow_overlap else literal, flags)

        # @intent prebuilt-search-string-cap
        # An overlapping or case-insensitive search compares the
        # substring at every position, so the substring is capped and
        # one pass over the text both counts every match and keeps the
        # positions up to the item cap.
        positions: list[int] = []
        count = 0
        for match in pattern.finditer(text):
            if count < PREBUILT_MAX_RESULT_ITEMS:
                positions.append(match.start())
            count += 1
        return {"count": count, "positions": positions, "truncated": count > len(positions)}

    @staticmethod
    def count_words(text: Annotated[str, Field(description=_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Count the words in a text, how many distinct words it holds, and their average length in characters. Use it for word counts, length limits, and vocabulary questions. A word is a run of Unicode letters and digits, joined across an internal apostrophe or hyphen, and distinct words are compared without regard to case. Text with no words gives zeros, and the tool has no failure case beyond the text length cap."""
        words = [word for _, word in PrebuiltToolSupport.split_words(text)]
        average = sum(len(word) for word in words) / len(words) if words else 0.0
        return {"words": len(words), "unique_words": len({word.casefold() for word in words}), "average_word_length": average}

    @staticmethod
    def count_sentences(text: Annotated[str, Field(description=_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Count the sentences in a text and the average number of words per sentence. Use it for sentence counts, writing limits, and summaries of text structure. A sentence ends at a period, question mark, exclamation mark, or ellipsis followed by a space or the end, except after a common abbreviation or a single capital initial, and trailing text without a terminator still counts. Text with no sentences gives zero and an average of zero."""
        sentences = PrebuiltToolSupport.split_sentences(text)
        words = PrebuiltToolSupport.split_words(text)
        average = len(words) / len(sentences) if sentences else 0.0
        return {"sentences": len(sentences), "average_words_per_sentence": average}

    @staticmethod
    def count_lines(text: Annotated[str, Field(description=_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Count the lines in a text, how many are blank, and which line is the longest. Use it to check line limits or to inspect the shape of a file before editing it. A line ends at CRLF, LF, or CR, a trailing break does not start an extra empty line, and a blank line holds only whitespace. Empty text has no lines, so the longest line number is null."""
        # Split at every kind of line break, then measure each line.
        lines = PrebuiltToolSupport.split_lines(text)
        blank = sum(1 for line in lines if not line.strip())
        lengths = [len(line) for line in lines]
        longest = max(lengths, default=0)

        # The first line of the greatest length is the one reported.
        return {
            "lines": len(lines),
            "blank_lines": blank,
            "non_blank_lines": len(lines) - blank,
            "longest_line_number": lengths.index(longest) + 1 if lines else None,
            "longest_line_length": longest,
            "ends_with_newline": text.endswith(("\n", "\r")),
        }

    @staticmethod
    def word_frequencies(
        text: Annotated[str, Field(description=_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        case_sensitive: Annotated[bool, Field(description="Whether words that differ only in case are counted apart. When false, words are grouped by their case-folded form and the first spelling seen is reported. The default is false. No stop words are ever removed.")] = False,
        top: Annotated[int, Field(description=_TOP_PARAMETER_DESCRIPTION, ge=1, le=PREBUILT_MAX_TOP_ITEMS)] = 50,
    ) -> PrebuiltToolOutput:
        """List the most frequent words in a text with how many times each appears, plus the total and distinct word counts. Use it to find repeated terms, key topics, or overused words. Words follow the Unicode letter-and-digit rule, are ranked by count and then by code-point order, and are grouped without regard to case unless case_sensitive is true. The list holds at most top entries, and the tool has no failure case beyond its caps."""
        words = Counter(word for _, word in PrebuiltToolSupport.split_words(text))
        unique, frequencies = TextCountingToolFunctions._rank_counts(words, case_sensitive, top, "word")
        return {"total_words": sum(words.values()), "unique_words": unique, "frequencies": frequencies}

    @staticmethod
    def character_frequencies(
        text: Annotated[str, Field(description=_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        case_sensitive: Annotated[bool, Field(description="Whether characters that differ only in case are counted apart. When false, characters are grouped by their case-folded form and the first spelling seen is reported. The default is true. Grouping never changes the total.")] = True,
        include_whitespace: Annotated[bool, Field(description="Whether spaces, tabs, line breaks, and other whitespace are counted. When false, whitespace is skipped and left out of the total. The default is false. Every other character is always counted.")] = False,
        top: Annotated[int, Field(description=_TOP_PARAMETER_DESCRIPTION, ge=1, le=PREBUILT_MAX_TOP_ITEMS)] = 100,
    ) -> PrebuiltToolOutput:
        """List the most frequent characters in a text with how many times each appears, plus the number of characters considered. Use it for letter-frequency questions, simple cipher work, or spotting unusual symbols. Characters are Unicode code points ranked by count and then by code point, and whitespace is skipped unless include_whitespace is true. The list holds at most top entries, and the tool has no failure case beyond its caps."""
        # Tally every character, leaving whitespace out unless asked.
        tallies = Counter(text)
        considered = {character: count for character, count in tallies.items() if include_whitespace or not character.isspace()}

        # Group by case when asked and keep the most frequent entries.
        _, frequencies = TextCountingToolFunctions._rank_counts(considered, case_sensitive, top, "character")
        return {"total": sum(considered.values()), "frequencies": frequencies}

    @staticmethod
    def ngram_frequencies(
        text: Annotated[str, Field(description=_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        n: Annotated[int, Field(description="How many words or characters make up one sequence. Small values find common pairs, and larger values find longer repeated passages. The value must be between 1 and 10. A text with fewer units than this gives no sequences.", ge=1, le=PREBUILT_MAX_NGRAM_SIZE)] = 2,
        unit: Annotated[NgramUnit, Field(description="Whether sequences are built from words or from characters. Word sequences follow the Unicode letter-and-digit word rule and are joined by one space. Character sequences run over the raw text, whitespace included. The default is words.")] = NgramUnit.WORDS,
        case_sensitive: Annotated[bool, Field(description="Whether sequences that differ only in case are counted apart. When false, sequences are grouped by their case-folded form and the first spelling seen is reported. The default is false. Grouping never changes the total.")] = False,
        top: Annotated[int, Field(description=_TOP_PARAMETER_DESCRIPTION, ge=1, le=PREBUILT_MAX_TOP_ITEMS)] = 50,
    ) -> PrebuiltToolOutput:
        """List the most frequent sequences of n consecutive words or n consecutive characters in a text, with the total number of sequences. Use it to find repeated phrases, common word pairs, or recurring character patterns. Word sequences are joined by a single space, character sequences include whitespace, and entries are ranked by count and then by code-point order. The list holds at most top entries, and a text shorter than n units gives an empty list."""
        # Cut the text into units, then slide a window of n units along
        # it so every sequence is tallied once per position.
        units: str | list[str] = text if unit is NgramUnit.CHARACTERS else [word for _, word in PrebuiltToolSupport.split_words(text)]
        separator = "" if unit is NgramUnit.CHARACTERS else " "
        tallies = Counter(separator.join(units[start : start + n]) for start in range(len(units) - n + 1))

        # Group by case when asked and keep the most frequent entries.
        _, frequencies = TextCountingToolFunctions._rank_counts(tallies, case_sensitive, top, "ngram")
        return {"total_ngrams": sum(tallies.values()), "frequencies": frequencies}

    @staticmethod
    def character_at_position(
        text: Annotated[str, Field(description="The text to look into, given as plain characters. Positions count Unicode code points, so an emoji or an accented letter counts once. It must hold at least one character and at most one million. Line breaks may be CRLF, LF, or a lone CR.", min_length=1, max_length=PREBUILT_MAX_TEXT_CHARS)],
        position: Annotated[int, Field(description="The 0-based position of the character to report. A negative position counts back from the end of the text. The result reports the resolved non-negative position. A position outside the text fails with an error.")],
    ) -> PrebuiltToolOutput:
        """Report which character sits at a position in a text, with its code point, Unicode name, line, and column. Use it to identify an invisible or unusual character, or to see exactly what is at an index. Positions count code points, negative positions count from the end, and lines and columns are 1-based. A position outside the text fails with an error naming position, and the name is null when Unicode gives none."""
        # Resolve a negative position against the end of the text.
        resolved = position + len(text) if position < 0 else position
        if not 0 <= resolved < len(text):
            problem = f"the text has {len(text)} characters, so the position is outside it"
            raise PrebuiltToolSupport.argument_error("position", problem, f"a position from {-len(text)} to {len(text) - 1}")

        # Find the line and column, then describe the character itself.
        line, column = PrebuiltToolSupport.line_and_column(text, resolved)
        character = text[resolved]
        return {
            "character": character,
            "code_point": f"U+{ord(character):04X}",
            "name": unicodedata.name(character, None),
            "position": resolved,
            "line": line,
            "column": column,
        }

    @staticmethod
    def readability_scores(text: Annotated[str, Field(description="The English text to score, given as plain characters. Words, sentences, and syllables are counted with the same rules as the other text counting tools. Text with words but no sentence terminator counts as one sentence. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Compute the Flesch Reading Ease score and the Flesch-Kincaid grade level of an English text, with the word, sentence, and syllable counts behind them. Use it to judge whether a text suits its readers or to compare two drafts. Both scores use the standard Flesch formulas, are rounded to two decimal places, and rely on a heuristic syllable count, so treat them as estimates. Text with no words fails with an error naming text."""
        # Count the words first, because the formulas divide by them.
        words = [word for _, word in PrebuiltToolSupport.split_words(text)]
        if not words:
            raise PrebuiltToolSupport.argument_error("text", "it holds no words", "text with at least one word")

        # Count sentences and syllables, then apply the two formulas.
        sentences = max(len(PrebuiltToolSupport.split_sentences(text)), 1)
        syllables = sum(PrebuiltToolSupport.count_syllables(word) for word in words)
        words_per_sentence = len(words) / sentences
        syllables_per_word = syllables / len(words)
        return {
            "words": len(words),
            "sentences": sentences,
            "syllables": syllables,
            "flesch_reading_ease": round(206.835 - 1.015 * words_per_sentence - 84.6 * syllables_per_word, _SCORE_PLACES),
            "flesch_kincaid_grade": round(0.39 * words_per_sentence + 11.8 * syllables_per_word - 15.59, _SCORE_PLACES),
        }

    @staticmethod
    def count_syllables(text: Annotated[str, Field(description="The English text whose syllables are estimated, given as plain characters. Words follow the Unicode letter-and-digit word rule. A word without any letter from a to z has no syllables. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Estimate the English syllables in each word of a text and in total, with the word count. Use it for meter, rhyme, and readability work where a quick estimate is enough. The estimate counts vowel groups with a silent final e rule, so unusual words can be off by one. At most 1,000 words are listed in text order while the totals cover every word, and the tool has no failure case beyond the text length cap."""
        # Estimate every word once, then list the first ones up to the
        # item cap while the totals cover them all.
        counted = [(word, PrebuiltToolSupport.count_syllables(word)) for _, word in PrebuiltToolSupport.split_words(text)]
        per_word, truncated = PrebuiltToolSupport.cap_items({"word": word, "syllables": syllables} for word, syllables in counted)
        return {"syllables": sum(syllables for _, syllables in counted), "words": len(counted), "per_word": per_word, "truncated": truncated}

    @staticmethod
    def _rank_counts(tallies: Mapping[str, int], case_sensitive: bool, top: int, label: str) -> tuple[int, list[dict[str, object]]]:
        """Group tallies by case-folded form when asked, keep the first spelling, and return the group count and the top entries."""
        grouped: dict[str, tuple[str, int]] = {}
        for spelling, count in tallies.items():
            key = spelling if case_sensitive else spelling.casefold()
            first, total = grouped.get(key, (spelling, 0))
            grouped[key] = (first, total + count)
        ranked = sorted(grouped.values(), key=lambda entry: (-entry[1], entry[0]))
        return len(grouped), [{label: spelling, "count": count} for spelling, count in ranked[:top]]

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.count_characters,
            cls.count_character_occurrences,
            cls.find_substring_positions,
            cls.count_words,
            cls.count_sentences,
            cls.count_lines,
            cls.word_frequencies,
            cls.character_frequencies,
            cls.ngram_frequencies,
            cls.character_at_position,
            cls.readability_scores,
            cls.count_syllables,
        )


__all__ = ["TextCountingToolFunctions"]
