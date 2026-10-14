"""FILE: tests/features/prebuilt_tools/test_prebuilt_rows_text.py

PURPOSE: Exact-output checks for every Appendix A row of the text_counting (A.12) and text_transform (A.13) categories, called the way a model calls them.
ROLE IN CODEBASE: Row tests of the prebuilt tool pack; runs each tool through FunctionTool.execute with the tool_runner fixture from tests/features/prebuilt_tools/conftest.py and compares parsed JSON with hand-computed expectations.
ARCHITECTURE NOTE: Cases are plain data built with ok, bad, and invalid from prebuilt_tool_harness; two parametrized functions run them, so each case reports under its own id `<tool>-<label>`.
FUNCTION INVENTORY: test_text_rows_return_documented_output checks SUCCESS_CASES; test_text_rows_reject_bad_input checks FAILURE_CASES; test_strip_html_tags_turns_block_tags_into_line_breaks checks the exact text the spec r4 block-tag rule gives; test_fill_text_template_reports_at_most_twenty_missing_names checks the reported-name cap.
COMMON MODIFICATION PATTERNS: Add a case to SUCCESS_CASES or FAILURE_CASES when a row gains an edge; compute the expectation by hand from the row and §9.2, never by running the tool.
WHAT NOT TO DO IN THIS FILE: 1. Do not copy an output of the implementation into an expectation; a copy cannot catch its mistakes. 2. Do not add the 1,000,000-character INV-20 amplification inputs here; test_prebuilt_resource_bounds.py owns them.
KNOWN EDGE CASES: Positions are code-point indices into the original text, so astral characters count once and case-insensitive matches of ß and İ never shift positions (EC-16). Line breaks are \r\n, \n, and \r, a trailing break does not start a line, and rebuilt text joins lines with \n and keeps one trailing \n (EC-15). Spec r6 caps find_substring_positions.substring and a case-insensitive find at 500 characters (S4 R-10, EC-50), and strip_html_tags drops markup left open at the end (S4 R-8, EC-47).
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md (Appendix A.12, Appendix A.13, §9.2 items 6 to 10)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_rows_text.py
"""

from __future__ import annotations

import pytest

from tests.features.prebuilt_tools.prebuilt_tool_harness import (
    Close,
    FailureCase,
    SuccessCase,
    ToolRunner,
    bad,
    invalid,
    ok,
)

ZERO_COUNTS = {
    "characters": 0,
    "non_whitespace": 0,
    "letters": 0,
    "digits": 0,
    "whitespace": 0,
    "punctuation": 0,
    "uppercase": 0,
    "lowercase": 0,
}
SENTENCE_TEXT = "Dr. Smith met J. Tolkien. Did he? Yes… \"Really!\" Then e.g. this. no end"
TEMPLATE_VALUES = "{\"name\": \"Ada\", \"age\": 36, \"user\": {\"role\": \"admin\"}, \"flag\": true, \"none\": null, \"list\": [1, \"a\"], \"obj\": {\"k\": 1}}"
BLANK_LINE_TEXT = "A" * 60 + "\n\n" + "B" * 60 + "\n" + "C" * 30
LINE_BREAK_TEXT = "a" * 55 + "\n" + "b " * 30 + "c" * 40
SENTENCE_BREAK_TEXT = "S" * 60 + ". " + "t" * 20 + " " + "u" * 80
BOUNDARY_TEXT = "a" * 49 + "\n" + "b" * 100


def chunk(index: int, start: int, end: int, text: str) -> dict[str, object]:
    """One expected split_text_into_chunks item; `text` is the source the chunk is sliced from."""
    return {"index": index, "start": start, "end": end, "text": text[start:end]}


SUCCESS_CASES = [
    # A.12 count_characters: code points, str predicates, and Unicode P* categories.
    ok(
        "count_characters",
        {"text": "Hi, Ünïcode 42!\n"},
        {"characters": 16, "non_whitespace": 13, "letters": 9, "digits": 2, "whitespace": 3, "punctuation": 2, "uppercase": 2, "lowercase": 7},
        "mixed-kinds",
    ),
    ok(
        "count_characters",
        {"text": "a_b$²٣"},
        {"characters": 6, "non_whitespace": 6, "letters": 2, "digits": 1, "whitespace": 0, "punctuation": 1, "uppercase": 0, "lowercase": 2},
        "isdecimal-not-isdigit-and-underscore-is-punctuation",
    ),
    ok(
        "count_characters",
        {"text": "é\U0001f600"},
        {"characters": 3, "non_whitespace": 3, "letters": 1, "digits": 0, "whitespace": 0, "punctuation": 0, "uppercase": 0, "lowercase": 1},
        "code-points-not-utf16-units",
    ),
    ok("count_characters", {"text": ""}, ZERO_COUNTS, "empty"),
    # A.12 count_character_occurrences: the §4 anchor and EC-16 positions.
    ok("count_character_occurrences", {"text": "strawberry", "character": "r"}, {"count": 3, "positions": [2, 7, 8], "truncated": False}, "section-4-anchor"),
    ok(
        "count_character_occurrences",
        {"text": "Straße STRASSE", "character": "s", "case_sensitive": False},
        {"count": 4, "positions": [0, 7, 11, 12], "truncated": False},
        "case-insensitive-sharp-s-keeps-positions",
    ),
    ok(
        "count_character_occurrences",
        {"text": "İi", "character": "i", "case_sensitive": False},
        {"count": 2, "positions": [0, 1], "truncated": False},
        "case-insensitive-dotted-capital-i-keeps-positions",
    ),
    ok("count_character_occurrences", {"text": "\U0001f600rﬁ", "character": "r"}, {"count": 1, "positions": [1], "truncated": False}, "astral-counts-once"),
    ok(
        "count_character_occurrences",
        {"text": "a" * 1500, "character": "a"},
        {"count": 1500, "positions": list(range(1000)), "truncated": True},
        "item-cap-keeps-first-1000-and-full-count",
    ),
    # A.12 find_substring_positions: overlap stepping and literal case-insensitive search.
    ok("find_substring_positions", {"text": "aaaa", "substring": "aa"}, {"count": 3, "positions": [0, 1, 2], "truncated": False}, "overlap-default"),
    ok(
        "find_substring_positions",
        {"text": "aaaa", "substring": "aa", "allow_overlap": False},
        {"count": 2, "positions": [0, 2], "truncated": False},
        "no-overlap",
    ),
    ok(
        "find_substring_positions",
        {"text": "Straße STRASSE strasse", "substring": "SS", "case_sensitive": False},
        {"count": 2, "positions": [11, 19], "truncated": False},
        "case-insensitive-never-matches-sharp-s",
    ),
    ok("find_substring_positions", {"text": "a.b.c", "substring": "."}, {"count": 2, "positions": [1, 3], "truncated": False}, "literal-not-pattern"),
    ok(
        "find_substring_positions",
        {"text": "\U0001f600ab\U0001f600ab", "substring": "ab"},
        {"count": 2, "positions": [1, 4], "truncated": False},
        "astral-positions",
    ),
    # A.12 count_words: §9.2 word rule, casefold distinctness.
    ok(
        "count_words",
        {"text": "Don't stop—state-of-the-art isn't DON'T; snake_case 42."},
        {"words": 8, "unique_words": 7, "average_word_length": 5.75},
        "apostrophes-hyphens-underscore-em-dash",
    ),
    ok(
        "count_words",
        {"text": "Grüße straße STRASSE"},
        {"words": 3, "unique_words": 2, "average_word_length": 6.0},
        "casefold-merges-sharp-s",
    ),
    ok("count_words", {"text": " \n\t "}, {"words": 0, "unique_words": 0, "average_word_length": 0.0}, "no-words"),
    # A.12 count_sentences: abbreviations, initials, closing quotes, trailing fragment.
    ok("count_sentences", {"text": SENTENCE_TEXT}, {"sentences": 6, "average_words_per_sentence": 2.5}, "abbreviations-initials-quotes"),
    ok("count_sentences", {"text": "No terminator here"}, {"sentences": 1, "average_words_per_sentence": 3.0}, "trailing-text-is-a-sentence"),
    ok("count_sentences", {"text": "   "}, {"sentences": 0, "average_words_per_sentence": 0.0}, "blank"),
    # A.12 count_lines: EC-15 line breaks and the empty-text shape.
    ok(
        "count_lines",
        {"text": "alpha\r\n\r\n  \rbeta gamma\nz\n"},
        {"lines": 5, "blank_lines": 2, "non_blank_lines": 3, "longest_line_number": 4, "longest_line_length": 10, "ends_with_newline": True},
        "crlf-cr-lf-and-trailing-break",
    ),
    ok(
        "count_lines",
        {"text": ""},
        {"lines": 0, "blank_lines": 0, "non_blank_lines": 0, "longest_line_number": None, "longest_line_length": 0, "ends_with_newline": False},
        "empty",
    ),
    ok(
        "count_lines",
        {"text": "ab\ncd"},
        {"lines": 2, "blank_lines": 0, "non_blank_lines": 2, "longest_line_number": 1, "longest_line_length": 2, "ends_with_newline": False},
        "first-longest-wins",
    ),
    ok(
        "count_lines",
        {"text": "\U0001f600\U0001f600\U0001f600\nabcd"},
        {"lines": 2, "blank_lines": 0, "non_blank_lines": 2, "longest_line_number": 2, "longest_line_length": 4, "ends_with_newline": False},
        "length-in-code-points",
    ),
    ok(
        "count_lines",
        {"text": "\n\n"},
        {"lines": 2, "blank_lines": 2, "non_blank_lines": 0, "longest_line_number": 1, "longest_line_length": 0, "ends_with_newline": True},
        "only-breaks",
    ),
    # A.12 word_frequencies: casefold grouping, first spelling, count then code-point order.
    ok(
        "word_frequencies",
        {"text": "The cat and the hat. THE end, cat!"},
        {
            "total_words": 8,
            "unique_words": 5,
            "frequencies": [
                {"word": "The", "count": 3},
                {"word": "cat", "count": 2},
                {"word": "and", "count": 1},
                {"word": "end", "count": 1},
                {"word": "hat", "count": 1},
            ],
        },
        "case-insensitive-default",
    ),
    ok(
        "word_frequencies",
        {"text": "The cat and the hat. THE end, cat!", "case_sensitive": True, "top": 3},
        {
            "total_words": 8,
            "unique_words": 7,
            "frequencies": [{"word": "cat", "count": 2}, {"word": "THE", "count": 1}, {"word": "The", "count": 1}],
        },
        "case-sensitive-top-3",
    ),
    # A.12 character_frequencies.
    ok(
        "character_frequencies",
        {"text": "Hello World"},
        {
            "total": 10,
            "frequencies": [
                {"character": "l", "count": 3},
                {"character": "o", "count": 2},
                {"character": "H", "count": 1},
                {"character": "W", "count": 1},
                {"character": "d", "count": 1},
                {"character": "e", "count": 1},
                {"character": "r", "count": 1},
            ],
        },
        "defaults-skip-whitespace",
    ),
    ok(
        "character_frequencies",
        {"text": "AaBb a", "case_sensitive": False, "include_whitespace": True},
        {"total": 6, "frequencies": [{"character": "A", "count": 3}, {"character": "B", "count": 2}, {"character": " ", "count": 1}]},
        "case-insensitive-first-spelling-with-whitespace",
    ),
    ok(
        "character_frequencies",
        {"text": "Hello World", "top": 2},
        {"total": 10, "frequencies": [{"character": "l", "count": 3}, {"character": "o", "count": 2}]},
        "top-2",
    ),
    # A.12 ngram_frequencies.
    ok(
        "ngram_frequencies",
        {"text": "the cat the cat the dog"},
        {
            "total_ngrams": 5,
            "frequencies": [{"ngram": "cat the", "count": 2}, {"ngram": "the cat", "count": 2}, {"ngram": "the dog", "count": 1}],
        },
        "word-bigrams-default",
    ),
    ok(
        "ngram_frequencies",
        {"text": "The cat the CAT"},
        {"total_ngrams": 3, "frequencies": [{"ngram": "The cat", "count": 2}, {"ngram": "cat the", "count": 1}]},
        "case-insensitive-first-spelling",
    ),
    ok(
        "ngram_frequencies",
        {"text": "abab", "unit": "characters"},
        {"total_ngrams": 3, "frequencies": [{"ngram": "ab", "count": 2}, {"ngram": "ba", "count": 1}]},
        "character-bigrams",
    ),
    ok(
        "ngram_frequencies",
        {"text": "a a", "unit": "characters"},
        {"total_ngrams": 2, "frequencies": [{"ngram": " a", "count": 1}, {"ngram": "a ", "count": 1}]},
        "character-ngrams-include-whitespace",
    ),
    ok("ngram_frequencies", {"text": "one two", "n": 3}, {"total_ngrams": 0, "frequencies": []}, "fewer-words-than-n"),
    # A.12 character_at_position.
    ok(
        "character_at_position",
        {"text": "a\U0001f600\nbé", "position": 1},
        {"character": "\U0001f600", "code_point": "U+1F600", "name": "GRINNING FACE", "position": 1, "line": 1, "column": 2},
        "astral",
    ),
    ok(
        "character_at_position",
        {"text": "a\U0001f600\nbé", "position": -1},
        {"character": "é", "code_point": "U+00E9", "name": "LATIN SMALL LETTER E WITH ACUTE", "position": 4, "line": 2, "column": 2},
        "negative-counts-from-end",
    ),
    ok(
        "character_at_position",
        {"text": "a\U0001f600\nbé", "position": 2},
        {"character": "\n", "code_point": "U+000A", "name": None, "position": 2, "line": 1, "column": 3},
        "control-character-has-no-name",
    ),
    ok(
        "character_at_position",
        {"text": "x\ry", "position": 2},
        {"character": "y", "code_point": "U+0079", "name": "LATIN SMALL LETTER Y", "position": 2, "line": 2, "column": 1},
        "carriage-return-starts-a-line",
    ),
    # A.12 readability_scores: Flesch formulas over the §9.2 rules, rounded to 2 places.
    ok(
        "readability_scores",
        {"text": "The cat sat on the mat. It was happy."},
        {"words": 9, "sentences": 2, "syllables": 10, "flesch_reading_ease": Close(108.2675, 0.01), "flesch_kincaid_grade": Close(-0.723889, 0.01)},
        "two-sentences",
    ),
    ok(
        "readability_scores",
        {"text": "hello world"},
        {"words": 2, "sentences": 1, "syllables": 3, "flesch_reading_ease": Close(77.905, 0.01), "flesch_kincaid_grade": Close(2.89, 0.01)},
        "no-terminator-counts-as-one-sentence",
    ),
    ok(
        "readability_scores",
        {"text": "The little table."},
        {"words": 3, "sentences": 1, "syllables": 5, "flesch_reading_ease": Close(62.79, 0.01), "flesch_kincaid_grade": Close(5.246667, 0.01)},
        "consonant-le-keeps-syllable",
    ),
    # A.12 count_syllables: §9.2 item 10.
    ok(
        "count_syllables",
        {"text": "Make the little cake; rhythm 42 queue, ale"},
        {
            "syllables": 8,
            "words": 8,
            "per_word": [
                {"word": "Make", "syllables": 1},
                {"word": "the", "syllables": 1},
                {"word": "little", "syllables": 2},
                {"word": "cake", "syllables": 1},
                {"word": "rhythm", "syllables": 1},
                {"word": "42", "syllables": 0},
                {"word": "queue", "syllables": 1},
                {"word": "ale", "syllables": 1},
            ],
            "truncated": False,
        },
        "heuristic-edges",
    ),
    ok("count_syllables", {"text": ""}, {"syllables": 0, "words": 0, "per_word": [], "truncated": False}, "empty"),
    # A.13 reverse_text.
    ok("reverse_text", {"text": "abc\U0001f600"}, {"text": "\U0001f600cba"}, "characters-by-code-point"),
    ok("reverse_text", {"text": "Hello, big world!", "unit": "words"}, {"text": "world big Hello"}, "words-drop-punctuation"),
    ok("reverse_text", {"text": "a\r\nb\rc\n", "unit": "lines"}, {"text": "c\nb\na\n"}, "lines-normalize-breaks"),
    ok("reverse_text", {"text": ""}, {"text": ""}, "empty"),
    # A.13 convert_identifier_case: acronym ends, digits stay with the part before them.
    ok(
        "convert_identifier_case",
        {"text": "HTTPServer_v2 error-code", "target": "snake"},
        {"text": "http_server_v2_error_code", "words": ["http", "server", "v2", "error", "code"]},
        "snake",
    ),
    ok(
        "convert_identifier_case",
        {"text": "HTTPServer_v2 error-code", "target": "camel"},
        {"text": "httpServerV2ErrorCode", "words": ["http", "server", "v2", "error", "code"]},
        "camel",
    ),
    ok(
        "convert_identifier_case",
        {"text": "HTTPServer_v2 error-code", "target": "screaming_snake"},
        {"text": "HTTP_SERVER_V2_ERROR_CODE", "words": ["http", "server", "v2", "error", "code"]},
        "screaming-snake",
    ),
    ok(
        "convert_identifier_case",
        {"text": "parseXMLDocument", "target": "kebab"},
        {"text": "parse-xml-document", "words": ["parse", "xml", "document"]},
        "kebab-acronym-in-middle",
    ),
    ok(
        "convert_identifier_case",
        {"text": "already_snake", "target": "pascal"},
        {"text": "AlreadySnake", "words": ["already", "snake"]},
        "pascal",
    ),
    ok("convert_identifier_case", {"text": "user id", "target": "dot"}, {"text": "user.id", "words": ["user", "id"]}, "dot"),
    # Spec r4: an uppercase letter after a digit starts a new word, and capitalizing uppercases only the first character.
    ok("convert_identifier_case", {"text": "version2Beta", "target": "pascal"}, {"text": "Version2Beta", "words": ["version2", "beta"]}, "digit-then-uppercase"),
    ok(
        "convert_identifier_case",
        {"text": "max_retry_count", "target": "title"},
        {"text": "Max Retry Count", "words": ["max", "retry", "count"]},
        "title",
    ),
    # A.13 shorten_text.
    ok("shorten_text", {"text": "short", "max_length": 10}, {"text": "short", "shortened": False, "original_length": 5}, "within-limit"),
    ok(
        "shorten_text",
        {"text": "The quick brown fox jumps", "max_length": 12},
        {"text": "The quick…", "shortened": True, "original_length": 25},
        "characters-break-on-word",
    ),
    ok(
        "shorten_text",
        {"text": "The quick brown fox jumps", "max_length": 12, "break_on_word": False},
        {"text": "The quick b…", "shortened": True, "original_length": 25},
        "characters-hard-cut",
    ),
    ok(
        "shorten_text",
        {"text": "The quick brown fox jumps", "max_length": 5, "ellipsis": "", "break_on_word": False},
        {"text": "The q", "shortened": True, "original_length": 25},
        "empty-ellipsis",
    ),
    ok(
        "shorten_text",
        {"text": "one two three four", "max_length": 2, "unit": "words"},
        {"text": "one two …", "shortened": True, "original_length": 4},
        "words-ellipsis-after-space",
    ),
    ok(
        "shorten_text",
        {"text": "l1\nl2\nl3", "max_length": 2, "unit": "lines"},
        {"text": "l1\nl2\n…", "shortened": True, "original_length": 3},
        "lines-ellipsis-after-break",
    ),
    # A.13 replace_all_occurrences.
    ok("replace_all_occurrences", {"text": "a.b.c", "find": ".", "replacement": "-"}, {"text": "a-b-c", "replacements": 2}, "literal"),
    ok(
        "replace_all_occurrences",
        {"text": "Cat cat CAT", "find": "cat", "replacement": "dog", "case_sensitive": False},
        {"text": "dog dog dog", "replacements": 3},
        "case-insensitive",
    ),
    ok(
        "replace_all_occurrences",
        {"text": "aaaa", "find": "a", "replacement": "b", "max_replacements": 2},
        {"text": "bbaa", "replacements": 2},
        "max-replacements-left-to-right",
    ),
    ok("replace_all_occurrences", {"text": "aaa", "find": "aa", "replacement": "x"}, {"text": "xa", "replacements": 1}, "non-overlapping"),
    # S4 R-10 (spec r6 A.13, EC-50): a case-sensitive search is linear, so it keeps the full ShortText cap for find.
    ok(
        "replace_all_occurrences",
        {"text": "a" * 20000 + "a" * 9999 + "b", "find": "a" * 9999 + "b", "replacement": "x"},
        {"text": "a" * 20000 + "x", "replacements": 1},
        "case-sensitive-find-keeps-short-text-cap",
    ),
    ok(
        "replace_all_occurrences",
        {"text": "Straße STRASSE", "find": "SS", "replacement": "_", "case_sensitive": False},
        {"text": "Straße STRA_E", "replacements": 1},
        "case-insensitive-leaves-sharp-s",
    ),
    # A.13 deduplicate_lines.
    ok("deduplicate_lines", {"text": "a\nb\na\nB\n"}, {"text": "a\nb\nB\n", "kept": 3, "removed": 1}, "case-sensitive-default"),
    ok("deduplicate_lines", {"text": "a\nb\na\nB\n", "case_sensitive": False}, {"text": "a\nb\n", "kept": 2, "removed": 2}, "casefold"),
    ok(
        "deduplicate_lines",
        {"text": " x\r\nx \r\n\r\n\n", "ignore_surrounding_whitespace": True},
        {"text": " x\n\n", "kept": 2, "removed": 2},
        "strip-compare-keeps-original-line",
    ),
    ok("deduplicate_lines", {"text": ""}, {"text": "", "kept": 0, "removed": 0}, "empty"),
    # A.13 sort_text_lines.
    ok("sort_text_lines", {"text": "b\nA\na\nB"}, {"text": "A\nB\na\nb", "lines": 4}, "code-point-default"),
    ok("sort_text_lines", {"text": "b\nB\na\nA", "mode": "case_insensitive"}, {"text": "A\na\nB\nb", "lines": 4}, "casefold-ties-by-code-point"),
    ok(
        "sort_text_lines",
        {"text": "file10\nfile2\nfile1\nFile3\nfile02", "mode": "natural"},
        {"text": "file1\nfile2\nfile02\nFile3\nfile10", "lines": 5},
        "natural-stable-on-equal-values",
    ),
    ok("sort_text_lines", {"text": "!x\n1x", "mode": "natural"}, {"text": "1x\n!x", "lines": 2}, "natural-digit-run-first"),
    ok(
        "sort_text_lines",
        {"text": "v100000000000000000000000\nv99999999999999999999999", "mode": "natural"},
        {"text": "v99999999999999999999999\nv100000000000000000000000", "lines": 2},
        "natural-long-digit-runs",
    ),
    ok(
        "sort_text_lines",
        {"text": "10\nabc\n2.5\n-1\n 5\nx\n1e2", "mode": "numeric"},
        {"text": "-1\n2.5\n 5\n10\n1e2\nabc\nx", "lines": 7},
        "numeric-then-others-in-order",
    ),
    ok("sort_text_lines", {"text": "ccc\na\nbb\nb", "mode": "length"}, {"text": "a\nb\nbb\nccc", "lines": 4}, "length-then-code-point"),
    ok("sort_text_lines", {"text": "b\na\nc", "descending": True}, {"text": "c\nb\na", "lines": 3}, "descending"),
    # Spec r4: descending is a stable sort on reversed keys (1.0 stays before 1), and non-numeric lines stay last in input order.
    ok("sort_text_lines", {"text": "1.0\n2\nx\n1\n3\nw", "mode": "numeric", "descending": True}, {"text": "3\n2\n1.0\n1\nx\nw", "lines": 6}, "numeric-descending-stable"),
    ok("sort_text_lines", {"text": "b\r\na\r\nb\r\na\r\n", "unique": True}, {"text": "a\nb\n", "lines": 2}, "unique-crlf-trailing-break"),
    # A.13 strip_html_tags.
    ok(
        "strip_html_tags",
        {"html_text": "<b>Hello</b>   &amp; <i>world</i><script>var x = 1;</script><!-- note --><style>p {}</style>"},
        {"text": "Hello & world"},
        "script-style-comment-entities-spaces",
    ),
    ok("strip_html_tags", {"html_text": "<div><p>unclosed <b>bold"}, {"text": "unclosed bold"}, "malformed-never-raises"),
    ok("strip_html_tags", {"html_text": "&lt;tag&gt; &#169; &copy;"}, {"text": "<tag> © ©"}, "entities"),
    # S4 R-8 (spec r6 A.13, EC-47): a tail left open after feed() that starts with "<" is dropped before close().
    ok("strip_html_tags", {"html_text": "x <b"}, {"text": "x"}, "open-tag-at-end-dropped"),
    ok("strip_html_tags", {"html_text": "a <!--x"}, {"text": "a"}, "open-comment-at-end-dropped"),
    # A.13 split_text_into_chunks: break-point kinds in order, the open lower bound, overlap.
    ok(
        "split_text_into_chunks",
        {"text": BLANK_LINE_TEXT, "chunk_size": 100},
        {"chunks": [chunk(0, 0, 62, BLANK_LINE_TEXT), chunk(1, 62, 153, BLANK_LINE_TEXT)], "count": 2, "truncated": False},
        "after-blank-line",
    ),
    ok(
        "split_text_into_chunks",
        {"text": LINE_BREAK_TEXT, "chunk_size": 100},
        {"chunks": [chunk(0, 0, 56, LINE_BREAK_TEXT), chunk(1, 56, 156, LINE_BREAK_TEXT)], "count": 2, "truncated": False},
        "line-break-beats-later-spaces",
    ),
    ok(
        "split_text_into_chunks",
        {"text": SENTENCE_BREAK_TEXT, "chunk_size": 100},
        {
            "chunks": [chunk(0, 0, 62, SENTENCE_BREAK_TEXT), chunk(1, 62, 162, SENTENCE_BREAK_TEXT), chunk(2, 162, 163, SENTENCE_BREAK_TEXT)],
            "count": 3,
            "truncated": False,
        },
        "sentence-end-beats-later-space-then-hard-cut",
    ),
    ok(
        "split_text_into_chunks",
        {"text": BOUNDARY_TEXT, "chunk_size": 100},
        {"chunks": [chunk(0, 0, 100, BOUNDARY_TEXT), chunk(1, 100, 150, BOUNDARY_TEXT)], "count": 2, "truncated": False},
        "break-at-half-is-outside-window",
    ),
    ok(
        "split_text_into_chunks",
        {"text": "w" * 150, "chunk_size": 100, "overlap": 25},
        {"chunks": [chunk(0, 0, 100, "w" * 150), chunk(1, 75, 150, "w" * 150)], "count": 2, "truncated": False},
        "overlap-quarter",
    ),
    ok("split_text_into_chunks", {"text": "", "chunk_size": 100}, {"chunks": [], "count": 0, "truncated": False}, "empty"),
    # A.13 extract_line_range.
    ok(
        "extract_line_range",
        {"text": "one\r\ntwo\rthree\nfour", "start_line": 2, "end_line": 3},
        {"text": "two\nthree", "start_line": 2, "end_line": 3, "total_lines": 4},
        "middle-range-mixed-breaks",
    ),
    ok(
        "extract_line_range",
        {"text": "one\r\ntwo\rthree\nfour", "start_line": 3},
        {"text": "three\nfour", "start_line": 3, "end_line": 4, "total_lines": 4},
        "null-end-means-last",
    ),
    ok(
        "extract_line_range",
        {"text": "one\r\ntwo\rthree\nfour", "start_line": 1, "end_line": 99},
        {"text": "one\ntwo\nthree\nfour", "start_line": 1, "end_line": 4, "total_lines": 4},
        "end-clipped",
    ),
    ok(
        "extract_line_range",
        {"text": "one\r\ntwo\rthree\nfour", "start_line": 2, "end_line": 3, "number_lines": True},
        {"text": "2: two\n3: three", "start_line": 2, "end_line": 3, "total_lines": 4},
        "numbered",
    ),
    # Spec r4: a trailing line break is kept only when the range ends at the last line and the input ended with one.
    ok("extract_line_range", {"text": "a\nb\nc\n", "start_line": 1, "end_line": 2}, {"text": "a\nb", "start_line": 1, "end_line": 2, "total_lines": 3}, "middle-range-no-break"),
    ok("extract_line_range", {"text": "a\nb\nc\n", "start_line": 3}, {"text": "c\n", "start_line": 3, "end_line": 3, "total_lines": 3}, "last-line-keeps-break"),
    # A.13 fill_text_template.
    ok(
        "fill_text_template",
        {"template": "Hi {{ name }}, you are {{age}} ({{user.role}}) {{flag}}{{none}}{{list}}{{obj}} {name}", "values_json": TEMPLATE_VALUES},
        {"text": "Hi Ada, you are 36 (admin) true[1,\"a\"]{\"k\":1} {name}", "filled": 7, "missing": []},
        "value-kinds-and-dotted-names",
    ),
    ok(
        "fill_text_template",
        {"template": "{{z}} {{b}} {{a}} {{z}}", "values_json": "{\"b\": \"x\"}", "missing": "keep"},
        {"text": "{{z}} x {{a}} {{z}}", "filled": 1, "missing": ["z", "a"]},
        "keep-missing-in-first-appearance-order",
    ),
    ok(
        "fill_text_template",
        {"template": "{{z}} {{b}} {{a}}", "values_json": "{\"b\": \"x\"}", "missing": "empty"},
        {"text": " x ", "filled": 1, "missing": ["z", "a"]},
        "empty-missing",
    ),
]

FAILURE_CASES = [
    invalid("count_character_occurrences", {"text": "abc", "character": "ab"}, "character", "two-characters"),
    invalid("count_character_occurrences", {"text": "abc", "character": ""}, "character", "empty-character"),
    invalid("find_substring_positions", {"text": "abc", "substring": ""}, "substring", "empty-substring"),
    # S4 R-10 (spec r6 A.12, EC-50): substring is capped at PREBUILT_MAX_SEARCH_STRING_CHARS (500).
    invalid("find_substring_positions", {"text": "abc", "substring": "a" * 501}, "substring", "substring-over-search-cap"),
    invalid("word_frequencies", {"text": "a b", "top": 0}, "top", "top-zero"),
    invalid("word_frequencies", {"text": "a b", "top": 1001}, "top", "top-over-cap"),
    invalid("character_frequencies", {"text": "a b", "top": 0}, "top", "top-zero"),
    invalid("ngram_frequencies", {"text": "a b", "n": 0}, "n", "n-zero"),
    invalid("ngram_frequencies", {"text": "a b", "n": 11}, "n", "n-over-cap"),
    invalid("character_at_position", {"text": "", "position": 0}, "text", "empty-text"),
    bad("character_at_position", {"text": "abcde", "position": 5}, "position", "past-end"),
    bad("character_at_position", {"text": "abcde", "position": -6}, "position", "before-start"),
    bad("readability_scores", {"text": "!!! ... ?"}, "text", "no-words"),
    bad("readability_scores", {"text": ""}, "text", "empty"),
    invalid("reverse_text", {"text": "abc", "unit": "sentences"}, "unit", "unknown-unit"),
    bad("convert_identifier_case", {"text": "!!! ---", "target": "snake"}, "text", "no-letters-or-digits"),
    bad("convert_identifier_case", {"text": "___", "target": "camel"}, "text", "only-underscores"),
    invalid("convert_identifier_case", {"text": "abc", "target": "upper"}, "target", "unknown-target"),
    bad("shorten_text", {"text": "abcdefgh", "max_length": 3, "ellipsis": "..."}, "ellipsis", "ellipsis-as-long-as-limit"),
    invalid("shorten_text", {"text": "abc", "max_length": 0}, "max_length", "zero-limit"),
    invalid("shorten_text", {"text": "abc", "max_length": 5, "ellipsis": "." * 201}, "ellipsis", "ellipsis-over-cap"),
    invalid("replace_all_occurrences", {"text": "abc", "find": "", "replacement": "x"}, "find", "empty-find"),
    invalid("replace_all_occurrences", {"text": "abc", "find": "a", "replacement": "x", "max_replacements": 0}, "max_replacements", "zero-max"),
    bad("replace_all_occurrences", {"text": "a" * 1000, "find": "a", "replacement": "x" * 10000}, "replacement", "predicted-result-over-cap"),
    # S4 R-10 (spec r6 A.13, EC-50): a case-insensitive find longer than PREBUILT_MAX_SEARCH_STRING_CHARS is refused.
    bad("replace_all_occurrences", {"text": "abc", "find": "a" * 501, "replacement": "x", "case_sensitive": False}, "find", "case-insensitive-find-over-search-cap"),
    invalid("sort_text_lines", {"text": "b\na", "mode": "alphabetical"}, "mode", "unknown-mode"),
    invalid("split_text_into_chunks", {"text": "abc", "chunk_size": 99}, "chunk_size", "below-minimum-chunk"),
    invalid("split_text_into_chunks", {"text": "abc", "chunk_size": 100, "overlap": -1}, "overlap", "negative-overlap"),
    bad("split_text_into_chunks", {"text": "w" * 150, "chunk_size": 100, "overlap": 26}, "overlap", "overlap-above-quarter"),
    bad("extract_line_range", {"text": "one\ntwo\nthree\nfour", "start_line": 5}, "start_line", "start-past-end"),
    bad("extract_line_range", {"text": "", "start_line": 1}, "start_line", "empty-text"),
    bad("extract_line_range", {"text": "one\ntwo\nthree\nfour", "start_line": 3, "end_line": 2}, "end_line", "end-before-start"),
    invalid("extract_line_range", {"text": "one", "start_line": 0}, "start_line", "zero-start"),
    bad("fill_text_template", {"template": "{{b}} {{first_missing}}", "values_json": "{\"b\": 1}"}, "values_json", "missing-name-errors", "first_missing"),
    bad("fill_text_template", {"template": "{{a}}", "values_json": "[1]"}, "values_json", "values-not-object"),
    bad("fill_text_template", {"template": "{{a}}", "values_json": "not json"}, "values_json", "values-not-json"),
    invalid("fill_text_template", {"template": "{{a}}", "values_json": "{}", "missing": "skip"}, "missing", "unknown-policy"),
]


@pytest.mark.parametrize("case", SUCCESS_CASES)
def test_text_rows_return_documented_output(tool_runner: ToolRunner, case: SuccessCase) -> None:
    tool_runner.check_success(case)


@pytest.mark.parametrize("case", FAILURE_CASES)
def test_text_rows_reject_bad_input(tool_runner: ToolRunner, case: FailureCase) -> None:
    tool_runner.check_failure(case)


def test_strip_html_tags_turns_block_tags_into_line_breaks(tool_runner: ToolRunner) -> None:
    # Spec r4 lists PREBUILT_HTML_BLOCK_TAGS: each start and end tag inserts a break, three or more breaks become two, and the result is trimmed.
    output = tool_runner.output("strip_html_tags", {"html_text": "<p>first</p><div>second</div>"})
    assert output == {"text": "first\n\nsecond"}
    # A void br is one start tag, so it inserts one break; inline tags insert nothing, and each line is stripped of spaces.
    output = tool_runner.output("strip_html_tags", {"html_text": "a <br> b<b>c</b>  <li> d </li>"})
    assert output == {"text": "a\nbc\nd"}


def test_fill_text_template_reports_at_most_twenty_missing_names(tool_runner: ToolRunner) -> None:
    names = [f"name_{index:02d}" for index in range(25)]
    template = " ".join("{{" + name + "}}" for name in names)
    failure = FailureCase("fill_text_template", {"template": template, "values_json": "{}"}, "values_json", "ToolExecutionError")
    result = tool_runner.check_failure(failure)
    assert "name_00" in result.output
    assert "name_19" in result.output
    assert "name_20" not in result.output and "name_24" not in result.output
