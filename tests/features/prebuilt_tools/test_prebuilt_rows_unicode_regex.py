"""FILE: tests/features/prebuilt_tools/test_prebuilt_rows_unicode_regex.py

PURPOSE: Exact-output and error cases for every Appendix A row of the unicode (A.14), regex (A.15), and text_comparison (A.16) categories, run through FunctionTool.execute as a model would call them.
ROLE IN CODEBASE: Row-level acceptance tests (AC-11) for 23 prebuilt tools; reaches each tool through the session ToolRunner over PrebuiltTools(PrebuiltToolCategory) built in tests/features/prebuilt_tools/conftest.py.
ARCHITECTURE NOTE: Cases are data (ok, bad, invalid from prebuilt_tool_harness) checked by two parametrized functions; a few extra functions cover properties that one expected object cannot state, such as the text of a compile error.
FUNCTION INVENTORY: char_info builds one unicode_character_info entry; found builds one find_unicode_character entry; test_unicode_regex_rows_return_documented_output checks SUCCESS_CASES; test_unicode_regex_rows_reject_bad_input checks FAILURE_CASES; test_verify_regex_pattern_reports_compile_error_text checks that the error is re.error.msg without the position suffix; test_find_unicode_character_without_exact_name_lists_word_matches checks a query with no exact name.
COMMON MODIFICATION PATTERNS: Add a row case as one ok(...) or bad(...) entry with a hand-computed expectation; keep every key of the row in the expected object.
WHAT NOT TO DO IN THIS FILE: 1. Do not pin characters added after Unicode 14.0 or names that changed between Python 3.11 and 3.12 (EC-38). 2. Do not add catastrophic regex patterns (EC-10) or million-character amplification inputs; test_prebuilt_resource_bounds.py owns INV-20.
KNOWN EDGE CASES: Positions are code-point indices, so an astral character counts once. An unknown group name in a replacement template raises IndexError, not re.error, inside the re module. utf_16 and utf_32 sizes include the byte-order mark even for empty text. An unpaired surrogate cannot reach a tool through pydantic JSON mode (spec r4 EC-14), and no prebuilt code can change that, so unencodable text uses real characters. Spec r4 fixes verify_regex_pattern's error to re.error.msg, 160 units per segment for empty SMS text, and Latin-only mark removal.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md Appendix A.14, A.15, A.16 and §9.2
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_rows_unicode_regex.py
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.features.prebuilt_tools.prebuilt_tool_harness import Close, FailureCase, SuccessCase, ToolRunner, bad, invalid, ok


def char_info(character: str, code_point: str, name: str | None, category: str, utf8_hex: str, is_combining: bool = False) -> dict[str, Any]:
    """One unicode_character_info entry, written out by hand from the Unicode Character Database."""
    return {
        "character": character,
        "code_point": code_point,
        "name": name,
        "category": category,
        "utf8_hex": utf8_hex,
        "is_combining": is_combining,
    }


def found(character: str, code_point: str, name: str) -> dict[str, str]:
    """One find_unicode_character match or exact entry."""
    return {"character": character, "code_point": code_point, "name": name}


GRINNING_MATCHES = [
    found("\U0001F600", "U+1F600", "GRINNING FACE"),
    found("\U0001F601", "U+1F601", "GRINNING FACE WITH SMILING EYES"),
    found("\U0001F638", "U+1F638", "GRINNING CAT FACE WITH SMILING EYES"),
    found("\U0001F929", "U+1F929", "GRINNING FACE WITH STAR EYES"),
    found("\U0001F92A", "U+1F92A", "GRINNING FACE WITH ONE LARGE AND ONE SMALL EYE"),
]
SMILING_CAT_MATCHES = [
    found("\U0001F638", "U+1F638", "GRINNING CAT FACE WITH SMILING EYES"),
    found("\U0001F63A", "U+1F63A", "SMILING CAT FACE WITH OPEN MOUTH"),
    found("\U0001F63B", "U+1F63B", "SMILING CAT FACE WITH HEART-SHAPED EYES"),
]
CJK_RUN = "".join(chr(0x4E00 + index) for index in range(1200))
CJK_FIRST_THOUSAND = [
    {
        "character": chr(0x4E00 + index),
        "code_point": f"U+{0x4E00 + index:04X}",
        "name": f"CJK UNIFIED IDEOGRAPH-{0x4E00 + index:04X}",
        "occurrences": 1,
        "first_position": index,
    }
    for index in range(1000)
]
ZERO_WIDTH_FIRST_THOUSAND = [
    {"position": index, "line": 1, "column": index + 1, "code_point": "U+200B", "name": "ZERO WIDTH SPACE", "kind": "zero_width"}
    for index in range(1000)
]
SINGLE_A_MATCHES = [{"match": "a", "start": index, "end": index + 1, "groups": [], "named_groups": {}} for index in range(1000)]
FOUR_THOUSAND_LINES = "x\n" * 4000

UNICODE_SUCCESS_CASES = [
    # A.14 unicode_character_info: code point U+XXXX, lowercase UTF-8 hex, null name when Unicode gives none.
    ok(
        "unicode_character_info",
        {"text": "Aé日"},
        {
            "characters": [
                char_info("A", "U+0041", "LATIN CAPITAL LETTER A", "Lu", "41"),
                char_info("é", "U+00E9", "LATIN SMALL LETTER E WITH ACUTE", "Ll", "c3a9"),
                char_info("日", "U+65E5", "CJK UNIFIED IDEOGRAPH-65E5", "Lo", "e697a5"),
            ]
        },
        "latin-and-cjk",
    ),
    ok(
        "unicode_character_info",
        {"text": "é\U0001F600\t"},
        {
            "characters": [
                char_info("e", "U+0065", "LATIN SMALL LETTER E", "Ll", "65"),
                char_info("́", "U+0301", "COMBINING ACUTE ACCENT", "Mn", "cc81", is_combining=True),
                char_info("\U0001F600", "U+1F600", "GRINNING FACE", "So", "f09f9880"),
                char_info("\t", "U+0009", None, "Cc", "09"),
            ]
        },
        "combining-astral-and-unnamed-control",
    ),
    # A.14 find_unicode_character: at most two calls, because each scans every code point (EC-37).
    ok(
        "find_unicode_character",
        {"name_query": "grinning face"},
        {"exact": found("\U0001F600", "U+1F600", "GRINNING FACE"), "matches": GRINNING_MATCHES, "truncated": False},
        "exact-lookup-and-word-matches",
    ),
    # A.14 apply_unicode_normalization: the four forms, including the 18-character NFKD expansion of U+FDFA (EC-45).
    ok("apply_unicode_normalization", {"text": "é", "form": "nfc"}, {"text": "é", "changed": True, "length_before": 2, "length_after": 1}, "nfc-composes"),
    ok("apply_unicode_normalization", {"text": "é", "form": "nfd"}, {"text": "é", "changed": True, "length_before": 1, "length_after": 2}, "nfd-decomposes"),
    ok("apply_unicode_normalization", {"text": "ﬁ", "form": "nfkc"}, {"text": "fi", "changed": True, "length_before": 1, "length_after": 2}, "nfkc-ligature"),
    ok("apply_unicode_normalization", {"text": "ﬁ", "form": "nfc"}, {"text": "ﬁ", "changed": False, "length_before": 1, "length_after": 1}, "nfc-keeps-ligature"),
    ok(
        "apply_unicode_normalization",
        {"text": "ﷺ", "form": "nfkd"},
        {
            "text": "صلى الله عليه وسلم",
            "changed": True,
            "length_before": 1,
            "length_after": 18,
        },
        "nfkd-expands-fdfa",
    ),
    # A.14 remove_diacritics: NFD minus Mn marks, plus the fallback table for letters with no decomposition.
    ok("remove_diacritics", {"text": "Crème Brûlée"}, {"text": "Creme Brulee", "changed_characters": 3}, "accents"),
    ok(
        "remove_diacritics",
        {"text": "Øresund straße łódź"},
        {"text": "Oresund strasse lodz", "changed_characters": 5},
        "fallback-table-and-sharp-s",
    ),
    ok("remove_diacritics", {"text": "日本語 abc"}, {"text": "日本語 abc", "changed_characters": 0}, "nothing-to-remove"),
    # Spec r4: only marks after a Latin letter are dropped, so Greek tonos and Cyrillic diaeresis stay.
    ok("remove_diacritics", {"text": "ά Ё é"}, {"text": "ά Ё e", "changed_characters": 1}, "non-latin-marks-stay"),
    ok("remove_diacritics", {"text": ""}, {"text": "", "changed_characters": 0}, "empty"),
    # A.14 find_invisible_characters: kinds, 1-based line and column, cleaned text with unusual spaces turned into U+0020.
    ok(
        "find_invisible_characters",
        {"text": "a​b c‮­\x07"},
        {
            "count": 5,
            "findings": [
                {"position": 1, "line": 1, "column": 2, "code_point": "U+200B", "name": "ZERO WIDTH SPACE", "kind": "zero_width"},
                {"position": 3, "line": 1, "column": 4, "code_point": "U+00A0", "name": "NO-BREAK SPACE", "kind": "unusual_space"},
                {"position": 5, "line": 1, "column": 6, "code_point": "U+202E", "name": "RIGHT-TO-LEFT OVERRIDE", "kind": "bidi_control"},
                {"position": 6, "line": 1, "column": 7, "code_point": "U+00AD", "name": "SOFT HYPHEN", "kind": "format"},
                {"position": 7, "line": 1, "column": 8, "code_point": "U+0007", "name": None, "kind": "control"},
            ],
            "truncated": False,
            "cleaned_text": "ab c",
        },
        "every-kind",
    ),
    ok(
        "find_invisible_characters",
        {"text": "x\n\ny⁠"},
        {
            "count": 1,
            "findings": [{"position": 4, "line": 3, "column": 2, "code_point": "U+2060", "name": "WORD JOINER", "kind": "zero_width"}],
            "truncated": False,
            "cleaned_text": "x\n\ny",
        },
        "line-and-column",
    ),
    ok(
        "find_invisible_characters",
        {"text": "﻿A‎B\t\n"},
        {
            "count": 2,
            "findings": [
                {"position": 0, "line": 1, "column": 1, "code_point": "U+FEFF", "name": "ZERO WIDTH NO-BREAK SPACE", "kind": "zero_width"},
                {"position": 2, "line": 1, "column": 3, "code_point": "U+200E", "name": "LEFT-TO-RIGHT MARK", "kind": "bidi_control"},
            ],
            "truncated": False,
            "cleaned_text": "AB\t\n",
        },
        "listed-cf-characters-keep-their-kind-and-tab-is-not-reported",
    ),
    ok("find_invisible_characters", {"text": "plain text"}, {"count": 0, "findings": [], "truncated": False, "cleaned_text": "plain text"}, "clean"),
    # Spec r4: carriage returns are not findings and line breaks are never rewritten; CRLF is one line break for line numbers.
    ok(
        "find_invisible_characters",
        {"text": "a\r\n\u200bb\rc"},
        {
            "count": 1,
            "findings": [{"position": 3, "line": 2, "column": 1, "code_point": "U+200B", "name": "ZERO WIDTH SPACE", "kind": "zero_width"}],
            "truncated": False,
            "cleaned_text": "a\r\nb\rc",
        },
        "crlf-and-cr-kept",
    ),
    ok(
        "find_invisible_characters",
        {"text": "​" * 1500},
        {"count": 1500, "findings": ZERO_WIDTH_FIRST_THOUSAND, "truncated": True, "cleaned_text": ""},
        "item-cap",
    ),
    # A.14 find_non_ascii_characters: distinct characters in first-appearance order with code-point positions.
    ok(
        "find_non_ascii_characters",
        {"text": "naïve café ñ ï"},
        {
            "count": 3,
            "characters": [
                {"character": "ï", "code_point": "U+00EF", "name": "LATIN SMALL LETTER I WITH DIAERESIS", "occurrences": 2, "first_position": 2},
                {"character": "é", "code_point": "U+00E9", "name": "LATIN SMALL LETTER E WITH ACUTE", "occurrences": 1, "first_position": 9},
                {"character": "ñ", "code_point": "U+00F1", "name": "LATIN SMALL LETTER N WITH TILDE", "occurrences": 1, "first_position": 11},
            ],
            "truncated": False,
        },
        "first-appearance-order",
    ),
    ok(
        "find_non_ascii_characters",
        {"text": "a\U0001F600bé\x80\U0001F600"},
        {
            "count": 3,
            "characters": [
                {"character": "\U0001F600", "code_point": "U+1F600", "name": "GRINNING FACE", "occurrences": 2, "first_position": 1},
                {"character": "é", "code_point": "U+00E9", "name": "LATIN SMALL LETTER E WITH ACUTE", "occurrences": 1, "first_position": 3},
                {"character": "\x80", "code_point": "U+0080", "name": None, "occurrences": 1, "first_position": 4},
            ],
            "truncated": False,
        },
        "astral-counts-as-one-position",
    ),
    ok("find_non_ascii_characters", {"text": "only ascii"}, {"count": 0, "characters": [], "truncated": False}, "none"),
    ok("find_non_ascii_characters", {"text": CJK_RUN}, {"count": 1200, "characters": CJK_FIRST_THOUSAND, "truncated": True}, "item-cap"),
    # A.14 detect_scripts_in_text: letters only, sorted by count then name, percent rounded to 2 places.
    ok(
        "detect_scripts_in_text",
        {"text": "Hello мир"},
        {
            "scripts": [{"script": "latin", "letters": 5, "percent": Close(62.5, 0.01)}, {"script": "cyrillic", "letters": 3, "percent": Close(37.5, 0.01)}],
            "mixed_script_words": [],
            "truncated": False,
        },
        "two-scripts",
    ),
    ok(
        "detect_scripts_in_text",
        {"text": "Pаypal login Pаypal"},
        {
            "scripts": [{"script": "latin", "letters": 15, "percent": Close(88.24, 0.01)}, {"script": "cyrillic", "letters": 2, "percent": Close(11.76, 0.01)}],
            "mixed_script_words": ["Pаypal"],
            "truncated": False,
        },
        "mixed-word-listed-once",
    ),
    ok(
        "detect_scripts_in_text",
        {"text": "日本語 text 123"},
        {
            "scripts": [{"script": "latin", "letters": 4, "percent": Close(57.14, 0.01)}, {"script": "cjk", "letters": 3, "percent": Close(42.86, 0.01)}],
            "mixed_script_words": [],
            "truncated": False,
        },
        "cjk-and-digits-ignored",
    ),
    ok(
        "detect_scripts_in_text",
        {"text": "ab мн"},
        {
            "scripts": [{"script": "cyrillic", "letters": 2, "percent": Close(50.0, 0.01)}, {"script": "latin", "letters": 2, "percent": Close(50.0, 0.01)}],
            "mixed_script_words": [],
            "truncated": False,
        },
        "tie-sorted-by-name",
    ),
    ok("detect_scripts_in_text", {"text": "123 !?"}, {"scripts": [], "mixed_script_words": [], "truncated": False}, "no-letters"),
    # A.14 count_bytes_in_encoding: the codec is the value with "_" replaced by "-"; utf_16 and utf_32 include the BOM.
    ok("count_bytes_in_encoding", {"text": "héllo"}, {"size_bytes": 6, "characters": 5, "encodable": True, "first_unencodable_position": None}, "utf-8-default"),
    ok(
        "count_bytes_in_encoding",
        {"text": "héllo", "text_encoding": "utf_16"},
        {"size_bytes": 12, "characters": 5, "encodable": True, "first_unencodable_position": None},
        "utf-16-with-bom",
    ),
    ok(
        "count_bytes_in_encoding",
        {"text": "a\U0001F600", "text_encoding": "utf_16_be"},
        {"size_bytes": 6, "characters": 2, "encodable": True, "first_unencodable_position": None},
        "utf-16-be-surrogate-pair",
    ),
    ok(
        "count_bytes_in_encoding",
        {"text": "a\U0001F600", "text_encoding": "utf_32"},
        {"size_bytes": 12, "characters": 2, "encodable": True, "first_unencodable_position": None},
        "utf-32-with-bom",
    ),
    ok("count_bytes_in_encoding", {"text": "", "text_encoding": "utf_16"}, {"size_bytes": 2, "characters": 0, "encodable": True, "first_unencodable_position": None}, "empty-utf-16-bom"),
    ok(
        "count_bytes_in_encoding",
        {"text": "€", "text_encoding": "cp1252"},
        {"size_bytes": 1, "characters": 1, "encodable": True, "first_unencodable_position": None},
        "euro-in-cp1252",
    ),
    ok(
        "count_bytes_in_encoding",
        {"text": "ab€", "text_encoding": "latin_1"},
        {"size_bytes": None, "characters": 3, "encodable": False, "first_unencodable_position": 2},
        "euro-not-in-latin-1",
    ),
    ok(
        "count_bytes_in_encoding",
        {"text": "héllo", "text_encoding": "ascii"},
        {"size_bytes": None, "characters": 5, "encodable": False, "first_unencodable_position": 1},
        "ascii-unencodable",
    ),
    # A.14 sms_segment_count: GSM-7 at 160/153 units with extension characters costing 2, otherwise UCS-2 at 70/67.
    ok("sms_segment_count", {"text": "Hello"}, {"encoding": "gsm_7", "segments": 1, "units_used": 5, "units_per_segment": 160, "non_gsm_characters": []}, "short"),
    ok(
        "sms_segment_count",
        {"text": "a{b}€"},
        {"encoding": "gsm_7", "segments": 1, "units_used": 8, "units_per_segment": 160, "non_gsm_characters": []},
        "extension-characters-cost-two",
    ),
    ok("sms_segment_count", {"text": "a" * 160}, {"encoding": "gsm_7", "segments": 1, "units_used": 160, "units_per_segment": 160, "non_gsm_characters": []}, "gsm-160"),
    ok("sms_segment_count", {"text": "a" * 161}, {"encoding": "gsm_7", "segments": 2, "units_used": 161, "units_per_segment": 153, "non_gsm_characters": []}, "gsm-161"),
    ok("sms_segment_count", {"text": "a" * 307}, {"encoding": "gsm_7", "segments": 3, "units_used": 307, "units_per_segment": 153, "non_gsm_characters": []}, "gsm-307"),
    ok(
        "sms_segment_count",
        {"text": "Hi \U0001F600"},
        {"encoding": "ucs_2", "segments": 1, "units_used": 5, "units_per_segment": 70, "non_gsm_characters": ["\U0001F600"]},
        "emoji-two-code-units",
    ),
    ok(
        "sms_segment_count",
        {"text": "ê" * 71},
        {"encoding": "ucs_2", "segments": 2, "units_used": 71, "units_per_segment": 67, "non_gsm_characters": ["ê"]},
        "ucs-2-71",
    ),
    ok(
        "sms_segment_count",
        {"text": "Ok ę ą ę"},
        {"encoding": "ucs_2", "segments": 1, "units_used": 8, "units_per_segment": 70, "non_gsm_characters": ["ę", "ą"]},
        "distinct-offenders-in-order",
    ),
    ok("sms_segment_count", {"text": ""}, {"encoding": "gsm_7", "segments": 0, "units_used": 0, "units_per_segment": 160, "non_gsm_characters": []}, "empty"),
    # A.14 repair_mojibake_text: cp1252 with Latin-1 fallback for 0x81/0x8D/0x8F/0x90/0x9D, strict UTF-8, at most 2 rounds.
    ok("repair_mojibake_text", {"text": "cafÃ©"}, {"text": "café", "repaired": True, "rounds": 1}, "one-round"),
    ok("repair_mojibake_text", {"text": "cafÃƒÂ©"}, {"text": "café", "repaired": True, "rounds": 2}, "two-rounds"),
    ok(
        "repair_mojibake_text",
        {"text": "cafÃƒÆ’Ã‚Â©"},
        {"text": "cafÃ©", "repaired": True, "rounds": 2},
        "stops-after-two-rounds",
    ),
    ok("repair_mojibake_text", {"text": "Ã\x81rbol"}, {"text": "Árbol", "repaired": True, "rounds": 1}, "latin-1-fallback-byte"),
    ok("repair_mojibake_text", {"text": "hello"}, {"text": "hello", "repaired": False, "rounds": 0}, "ascii-unchanged"),
    ok("repair_mojibake_text", {"text": "café 日本"}, {"text": "café 日本", "repaired": False, "rounds": 0}, "not-garbled"),
]

REGEX_SUCCESS_CASES = [
    # A.15 regex_find_all: finditer with null for groups that did not take part.
    ok(
        "regex_find_all",
        {"pattern": "(\\d+)-(?P<word>[a-z]+)?", "text": "10-ab 7- 3-c"},
        {
            "count": 3,
            "matches": [
                {"match": "10-ab", "start": 0, "end": 5, "groups": ["10", "ab"], "named_groups": {"word": "ab"}},
                {"match": "7-", "start": 6, "end": 8, "groups": ["7", None], "named_groups": {"word": None}},
                {"match": "3-c", "start": 9, "end": 12, "groups": ["3", "c"], "named_groups": {"word": "c"}},
            ],
            "truncated": False,
        },
        "groups-and-null-group",
    ),
    ok(
        "regex_find_all",
        {"pattern": "\\d+", "text": "é1 \U0001F60022"},
        {
            "count": 2,
            "matches": [
                {"match": "1", "start": 1, "end": 2, "groups": [], "named_groups": {}},
                {"match": "22", "start": 4, "end": 6, "groups": [], "named_groups": {}},
            ],
            "truncated": False,
        },
        "code-point-positions",
    ),
    ok(
        "regex_find_all",
        {"pattern": "abc", "text": "ABC abc", "flags": ["ignore_case"]},
        {
            "count": 2,
            "matches": [
                {"match": "ABC", "start": 0, "end": 3, "groups": [], "named_groups": {}},
                {"match": "abc", "start": 4, "end": 7, "groups": [], "named_groups": {}},
            ],
            "truncated": False,
        },
        "ignore-case-flag",
    ),
    ok(
        "regex_find_all",
        {"pattern": "\\w+", "text": "é1", "flags": ["ascii"]},
        {"count": 1, "matches": [{"match": "1", "start": 1, "end": 2, "groups": [], "named_groups": {}}], "truncated": False},
        "ascii-flag",
    ),
    ok(
        "regex_find_all",
        {"pattern": "^\\w", "text": "ab\ncd", "flags": ["multiline"]},
        {
            "count": 2,
            "matches": [
                {"match": "a", "start": 0, "end": 1, "groups": [], "named_groups": {}},
                {"match": "c", "start": 3, "end": 4, "groups": [], "named_groups": {}},
            ],
            "truncated": False,
        },
        "multiline-flag",
    ),
    ok(
        "regex_find_all",
        {"pattern": "x*", "text": "ab"},
        {
            "count": 3,
            "matches": [
                {"match": "", "start": 0, "end": 0, "groups": [], "named_groups": {}},
                {"match": "", "start": 1, "end": 1, "groups": [], "named_groups": {}},
                {"match": "", "start": 2, "end": 2, "groups": [], "named_groups": {}},
            ],
            "truncated": False,
        },
        "empty-matches",
    ),
    ok("regex_find_all", {"pattern": "z", "text": "abc"}, {"count": 0, "matches": [], "truncated": False}, "no-match"),
    ok("regex_find_all", {"pattern": "a", "text": "a" * 1500}, {"count": 1500, "matches": SINGLE_A_MATCHES, "truncated": True}, "item-cap-counts-all"),
    # A.15 regex_match: full, prefix, and search modes; nulls and empty groups when nothing matches.
    ok(
        "regex_match",
        {"pattern": "(\\d{4})-(\\d{2})", "text": "2024-05"},
        {"matched": True, "match": "2024-05", "start": 0, "end": 7, "groups": ["2024", "05"], "named_groups": {}},
        "full-default",
    ),
    ok(
        "regex_match",
        {"pattern": "(\\d{4})-(\\d{2})", "text": "x2024-05"},
        {"matched": False, "match": None, "start": None, "end": None, "groups": [], "named_groups": {}},
        "full-no-match",
    ),
    ok(
        "regex_match",
        {"pattern": "\\d+", "text": "123abc", "mode": "prefix"},
        {"matched": True, "match": "123", "start": 0, "end": 3, "groups": [], "named_groups": {}},
        "prefix",
    ),
    ok(
        "regex_match",
        {"pattern": "(?P<n>b+)", "text": "aabbbcc", "mode": "search"},
        {"matched": True, "match": "bbb", "start": 2, "end": 5, "groups": ["bbb"], "named_groups": {"n": "bbb"}},
        "search-named",
    ),
    ok(
        "regex_match",
        {"pattern": "(?P<a>x)?y", "text": "y"},
        {"matched": True, "match": "y", "start": 0, "end": 1, "groups": [None], "named_groups": {"a": None}},
        "unmatched-optional-group",
    ),
    ok(
        "regex_match",
        {"pattern": "a.b", "text": "a\nb", "flags": ["dot_all"]},
        {"matched": True, "match": "a\nb", "start": 0, "end": 3, "groups": [], "named_groups": {}},
        "dot-all",
    ),
    ok(
        "regex_match",
        {"pattern": "a.b", "text": "a\nb"},
        {"matched": False, "match": None, "start": None, "end": None, "groups": [], "named_groups": {}},
        "dot-without-dot-all",
    ),
    # A.15 regex_replace: numbered and named templates, max_replacements, no match.
    ok("regex_replace", {"pattern": "(\\w+)@(\\w+)\\.com", "replacement": "\\2 at \\1", "text": "joe@site.com, ann@web.com"}, {"text": "site at joe, web at ann", "replacements": 2}, "numbered-groups"),
    ok(
        "regex_replace",
        {"pattern": "(?P<y>\\d{4})-(?P<m>\\d{2})", "replacement": "\\g<m>/\\g<y>", "text": "2024-05 and 1999-12"},
        {"text": "05/2024 and 12/1999", "replacements": 2},
        "named-groups",
    ),
    ok("regex_replace", {"pattern": "a", "replacement": "b", "text": "aaa", "max_replacements": 1}, {"text": "baa", "replacements": 1}, "max-replacements"),
    ok("regex_replace", {"pattern": "q", "replacement": "z", "text": "abc"}, {"text": "abc", "replacements": 0}, "no-match"),
    ok("regex_replace", {"pattern": "X", "replacement": "-", "text": "aXbxc", "flags": ["ignore_case"]}, {"text": "a-b-c", "replacements": 2}, "flag"),
    # A.15 regex_split: re.split semantics, captured groups among the parts, null for unmatched groups.
    ok("regex_split", {"pattern": "[,;]\\s*", "text": "a, b;c"}, {"parts": ["a", "b", "c"], "count": 3, "truncated": False}, "simple"),
    ok(
        "regex_split",
        {"pattern": "(-)|(\\+)", "text": "1-2+3"},
        {"parts": ["1", "-", None, "2", None, "+", "3"], "count": 7, "truncated": False},
        "captured-and-null-groups",
    ),
    ok("regex_split", {"pattern": ",", "text": "a,b,c", "max_splits": 1}, {"parts": ["a", "b,c"], "count": 2, "truncated": False}, "max-splits"),
    ok("regex_split", {"pattern": ",", "text": ""}, {"parts": [""], "count": 1, "truncated": False}, "empty-text"),
    ok("regex_split", {"pattern": ",", "text": "," * 1500}, {"parts": [""] * 1000, "count": 1501, "truncated": True}, "item-cap-counts-all"),
    # A.15 verify_regex_pattern: an invalid pattern is a successful result with valid false.
    ok(
        "verify_regex_pattern",
        {"pattern": "(?P<year>\\d{4})-(\\d{2})(?P<day>\\d{2})?"},
        {"valid": True, "error": None, "error_position": None, "group_count": 3, "group_names": ["year", "day"]},
        "valid-with-names",
    ),
    ok(
        "verify_regex_pattern",
        {"pattern": "a b # comment", "flags": ["verbose"]},
        {"valid": True, "error": None, "error_position": None, "group_count": 0, "group_names": []},
        "verbose-flag",
    ),
    # Spec r4: error is re.error.msg and error_position is re.error.pos, never str(exc), which would append the position.
    ok(
        "verify_regex_pattern",
        {"pattern": "(abc"},
        {"valid": False, "error": "missing ), unterminated subpattern", "error_position": 0, "group_count": 0, "group_names": []},
        "unterminated-group",
    ),
    ok(
        "verify_regex_pattern",
        {"pattern": "abc)"},
        {"valid": False, "error": "unbalanced parenthesis", "error_position": 3, "group_count": 0, "group_names": []},
        "unbalanced",
    ),
    # A.15 regex_test_samples: failures in input order, should-match samples first.
    ok(
        "regex_test_samples",
        {"pattern": "\\d{3}-\\d{4}", "should_match": ["555-1234", "5551234"], "should_not_match": ["555-12345", "abc"]},
        {"all_passed": False, "passed": 3, "failed": 1, "failures": [{"sample": "5551234", "expected_match": True}]},
        "full-mode-default",
    ),
    ok(
        "regex_test_samples",
        {"pattern": "a+", "should_match": ["b", "aaa", "c"], "should_not_match": ["aa", "x"]},
        {
            "all_passed": False,
            "passed": 2,
            "failed": 3,
            "failures": [{"sample": "b", "expected_match": True}, {"sample": "c", "expected_match": True}, {"sample": "aa", "expected_match": False}],
        },
        "failure-order",
    ),
    ok(
        "regex_test_samples",
        {"pattern": "cat", "should_match": ["concatenate"], "should_not_match": ["dog"], "mode": "search"},
        {"all_passed": True, "passed": 2, "failed": 0, "failures": []},
        "search-mode",
    ),
    ok(
        "regex_test_samples",
        {"pattern": "ab", "should_match": ["abc"], "should_not_match": ["cab"], "mode": "prefix"},
        {"all_passed": True, "passed": 2, "failed": 0, "failures": []},
        "prefix-mode",
    ),
    ok(
        "regex_test_samples",
        {"pattern": "abc", "should_match": ["ABC"], "flags": ["ignore_case"]},
        {"all_passed": True, "passed": 1, "failed": 0, "failures": []},
        "flag-and-default-should-not-match",
    ),
    # A.15 wildcard_match_names: fnmatchcase, optional lowercasing, input order kept.
    ok("wildcard_match_names", {"pattern": "*.py", "names": ["a.py", "b.txt", "c.PY", "dir/d.py"]}, {"matches": ["a.py", "dir/d.py"], "count": 2, "truncated": False}, "case-sensitive"),
    ok(
        "wildcard_match_names",
        {"pattern": "*.py", "names": ["a.py", "b.txt", "c.PY", "dir/d.py"], "case_sensitive": False},
        {"matches": ["a.py", "c.PY", "dir/d.py"], "count": 3, "truncated": False},
        "case-insensitive-keeps-spelling",
    ),
    ok(
        "wildcard_match_names",
        {"pattern": "file?.[ch]", "names": ["file1.c", "file22.c", "fileA.h", "file1.o"]},
        {"matches": ["file1.c", "fileA.h"], "count": 2, "truncated": False},
        "question-mark-and-set",
    ),
    ok("wildcard_match_names", {"pattern": "[!a]*", "names": ["abc", "bcd", ""]}, {"matches": ["bcd"], "count": 1, "truncated": False}, "negated-set"),
    ok(
        "wildcard_match_names",
        {"pattern": "n*", "names": [f"n{index}" for index in range(1500)]},
        {"matches": [f"n{index}" for index in range(1000)], "count": 1500, "truncated": True},
        "item-cap-counts-all",
    ),
]

COMPARISON_SUCCESS_CASES = [
    # A.16 unified_diff_text: difflib.unified_diff with lineterm "" joined by "\n".
    ok(
        "unified_diff_text",
        {"original": "a\nb\nc\n", "modified": "a\nB\nc\n"},
        {"diff": "--- original\n+++ modified\n@@ -1,3 +1,3 @@\n a\n-b\n+B\n c", "added_lines": 1, "removed_lines": 1, "identical": False},
        "defaults",
    ),
    ok(
        "unified_diff_text",
        {"original": "1\n2\n3\n4\n5", "modified": "1\n2\nX\n4\n5", "context_lines": 0},
        {"diff": "--- original\n+++ modified\n@@ -3 +3 @@\n-3\n+X", "added_lines": 1, "removed_lines": 1, "identical": False},
        "no-context",
    ),
    ok(
        "unified_diff_text",
        {
            "original": "1\n2\n3\n4\n5\n6\n7\n8\n9",
            "modified": "1\n2\n3\n4\nfive\n6\n7\n8\n9",
            "context_lines": 1,
            "original_label": "v1.txt",
            "modified_label": "v2.txt",
        },
        {"diff": "--- v1.txt\n+++ v2.txt\n@@ -4,3 +4,3 @@\n 4\n-5\n+five\n 6", "added_lines": 1, "removed_lines": 1, "identical": False},
        "labels-and-one-line-context",
    ),
    ok("unified_diff_text", {"original": "", "modified": "a"}, {"diff": "--- original\n+++ modified\n@@ -0,0 +1 @@\n+a", "added_lines": 1, "removed_lines": 0, "identical": False}, "from-empty"),
    ok(
        "unified_diff_text",
        {"original": "keep\ndrop\n", "modified": "keep\n"},
        {"diff": "--- original\n+++ modified\n@@ -1,2 +1 @@\n keep\n-drop", "added_lines": 0, "removed_lines": 1, "identical": False},
        "removal",
    ),
    ok("unified_diff_text", {"original": FOUR_THOUSAND_LINES, "modified": FOUR_THOUSAND_LINES}, {"diff": "", "added_lines": 0, "removed_lines": 0, "identical": True}, "identical-at-line-cap"),
    # A.16 diff_words: word and whitespace tokens, SequenceMatcher(autojunk=False) opcodes, ratio as similarity.
    ok(
        "diff_words",
        {"original": "the quick brown fox", "modified": "the slow brown fox"},
        {
            "operations": [
                {"op": "equal", "original": "the ", "modified": "the "},
                {"op": "replace", "original": "quick", "modified": "slow"},
                {"op": "equal", "original": " brown fox", "modified": " brown fox"},
            ],
            "similarity": 12 / 14,
        },
        "replace",
    ),
    ok(
        "diff_words",
        {"original": "a b", "modified": "a b c"},
        {"operations": [{"op": "equal", "original": "a b", "modified": "a b"}, {"op": "insert", "original": "", "modified": " c"}], "similarity": 0.75},
        "insert",
    ),
    ok(
        "diff_words",
        {"original": "a b c", "modified": "a c"},
        {
            "operations": [
                {"op": "equal", "original": "a ", "modified": "a "},
                {"op": "delete", "original": "b ", "modified": ""},
                {"op": "equal", "original": "c", "modified": "c"},
            ],
            "similarity": 0.75,
        },
        "delete",
    ),
    ok("diff_words", {"original": "", "modified": ""}, {"operations": [], "similarity": 1.0}, "both-empty"),
    ok(
        "diff_words",
        {"original": "a " * 1000, "modified": "a " * 1000},
        {"operations": [{"op": "equal", "original": "a " * 1000, "modified": "a " * 1000}], "similarity": 1.0},
        "token-cap-boundary",
    ),
    # A.16 levenshtein_distance: unit-cost edits over code points; similarity 1 - distance / max length.
    ok("levenshtein_distance", {"first": "kitten", "second": "sitting"}, {"distance": 3, "similarity": 1 - 3 / 7}, "kitten-sitting"),
    ok("levenshtein_distance", {"first": "flaw", "second": "lawn"}, {"distance": 2, "similarity": 0.5}, "flaw-lawn"),
    ok("levenshtein_distance", {"first": "", "second": ""}, {"distance": 0, "similarity": 1.0}, "both-empty"),
    ok("levenshtein_distance", {"first": "abc", "second": ""}, {"distance": 3, "similarity": 0.0}, "one-empty"),
    ok("levenshtein_distance", {"first": "a\U0001F600", "second": "a"}, {"distance": 1, "similarity": 0.5}, "astral-is-one-character"),
    ok("levenshtein_distance", {"first": "ABC", "second": "abc"}, {"distance": 3, "similarity": 0.0}, "case-sensitive-default"),
    ok("levenshtein_distance", {"first": "ABC", "second": "abc", "case_sensitive": False}, {"distance": 0, "similarity": 1.0}, "case-insensitive"),
    ok("levenshtein_distance", {"first": "straße", "second": "STRASSE", "case_sensitive": False}, {"distance": 0, "similarity": 1.0}, "casefold-sharp-s"),
    # A.16 closest_string_matches: SequenceMatcher ratio, score descending then index, casefold by default.
    ok(
        "closest_string_matches",
        {"query": "apple", "candidates": ["apply", "ape", "maple", "banana", "Apple"]},
        {
            "matches": [
                {"candidate": "Apple", "index": 4, "score": 1.0},
                {"candidate": "apply", "index": 0, "score": 0.8},
                {"candidate": "maple", "index": 2, "score": 0.8},
                {"candidate": "ape", "index": 1, "score": 0.75},
                {"candidate": "banana", "index": 3, "score": 2 / 11},
            ]
        },
        "defaults",
    ),
    ok(
        "closest_string_matches",
        {"query": "apple", "candidates": ["apply", "ape", "maple", "banana", "Apple"], "top": 3, "case_sensitive": True},
        {
            "matches": [
                {"candidate": "apply", "index": 0, "score": 0.8},
                {"candidate": "maple", "index": 2, "score": 0.8},
                {"candidate": "Apple", "index": 4, "score": 0.8},
            ]
        },
        "case-sensitive-ties-by-index",
    ),
    ok(
        "closest_string_matches",
        {"query": "apple", "candidates": ["apply", "ape", "maple", "banana", "Apple"], "minimum_score": 0.79},
        {"matches": [{"candidate": "Apple", "index": 4, "score": 1.0}, {"candidate": "apply", "index": 0, "score": 0.8}, {"candidate": "maple", "index": 2, "score": 0.8}]},
        "minimum-score",
    ),
    ok("closest_string_matches", {"query": "apple", "candidates": []}, {"matches": []}, "no-candidates"),
    ok("closest_string_matches", {"query": "", "candidates": [""]}, {"matches": [{"candidate": "", "index": 0, "score": 1.0}]}, "empty-strings"),
    # A.16 longest_common_substring: find_longest_match over full ranges, earliest run in first.
    ok("longest_common_substring", {"first": "xabcdey", "second": "zzabcdq"}, {"substring": "abcd", "length": 4, "first_position": 1, "second_position": 2}, "simple"),
    ok("longest_common_substring", {"first": "abXcd", "second": "cdYab"}, {"substring": "ab", "length": 2, "first_position": 0, "second_position": 3}, "tie-earliest-in-first"),
    ok("longest_common_substring", {"first": "abc", "second": "xyz"}, {"substring": "", "length": 0, "first_position": None, "second_position": None}, "nothing-shared"),
    ok("longest_common_substring", {"first": "", "second": ""}, {"substring": "", "length": 0, "first_position": None, "second_position": None}, "both-empty"),
    ok("longest_common_substring", {"first": "\U0001F600abc", "second": "xabc"}, {"substring": "abc", "length": 3, "first_position": 1, "second_position": 1}, "code-point-positions"),
    # A.16 jaccard_similarity: sets of distinct n-grams built like ngram_frequencies.
    ok("jaccard_similarity", {"first": "The cat sat.", "second": "the CAT ran!"}, {"jaccard": 0.5, "intersection": 2, "union": 4}, "words-case-insensitive"),
    ok("jaccard_similarity", {"first": "the cat sat", "second": "The cat ran", "case_sensitive": True}, {"jaccard": 0.2, "intersection": 1, "union": 5}, "words-case-sensitive"),
    ok("jaccard_similarity", {"first": "a b c", "second": "a b d", "n": 2}, {"jaccard": 1 / 3, "intersection": 1, "union": 3}, "word-bigrams"),
    ok("jaccard_similarity", {"first": "night", "second": "nacht", "unit": "characters", "n": 2}, {"jaccard": 1 / 7, "intersection": 1, "union": 7}, "character-bigrams"),
    ok("jaccard_similarity", {"first": "ab", "second": "AB", "unit": "characters"}, {"jaccard": 1.0, "intersection": 2, "union": 2}, "characters-case-insensitive"),
    ok("jaccard_similarity", {"first": "", "second": ""}, {"jaccard": 1.0, "intersection": 0, "union": 0}, "both-empty"),
    ok("jaccard_similarity", {"first": "a b", "second": "a b", "n": 3}, {"jaccard": 1.0, "intersection": 0, "union": 0}, "no-ngrams-on-either-side"),
    ok("jaccard_similarity", {"first": "word", "second": ""}, {"jaccard": 0.0, "intersection": 0, "union": 1}, "one-side-empty"),
]

SUCCESS_CASES = UNICODE_SUCCESS_CASES + REGEX_SUCCESS_CASES + COMPARISON_SUCCESS_CASES

FAILURE_CASES = [
    # A.14 schema bounds.
    invalid("unicode_character_info", {"text": ""}, "text", "empty-text"),
    invalid("unicode_character_info", {"text": "a" * 201}, "text", "over-phrase-cap"),
    invalid("find_unicode_character", {"name_query": "a"}, "name_query", "query-too-short"),
    invalid("apply_unicode_normalization", {"text": "a", "form": "NFC"}, "form", "form-is-not-an-enum-value"),
    invalid("count_bytes_in_encoding", {"text": "a", "text_encoding": "utf-8"}, "text_encoding", "codec-name-instead-of-enum-value"),
    invalid("sms_segment_count", {"text": "a" * 10_001}, "text", "over-short-text-cap"),
    # A.15 regex: invalid patterns and templates are tool errors; flags, modes, and bounds are schema errors.
    bad("regex_find_all", {"pattern": "(", "text": "a"}, "pattern", "pattern-does-not-compile"),
    bad("regex_match", {"pattern": "[a-", "text": "a"}, "pattern", "pattern-does-not-compile"),
    bad("regex_replace", {"pattern": "abc)", "replacement": "x", "text": "abc"}, "pattern", "pattern-does-not-compile"),
    bad("regex_replace", {"pattern": "(a)", "replacement": "\\3", "text": "a"}, "replacement", "unknown-group-number"),
    bad("regex_replace", {"pattern": "(a)", "replacement": "\\g<zz>", "text": "a"}, "replacement", "unknown-group-name-raises-index-error-in-re"),
    bad("regex_replace", {"pattern": "(a)", "replacement": "\\g<zz>", "text": "zzz"}, "replacement", "bad-template-without-a-match"),
    bad("regex_split", {"pattern": "*a", "text": "a"}, "pattern", "pattern-does-not-compile"),
    bad("regex_test_samples", {"pattern": "(", "should_match": ["a"]}, "pattern", "pattern-does-not-compile"),
    bad("regex_test_samples", {"pattern": "a", "should_match": [], "should_not_match": []}, "should_match", "both-lists-empty"),
    invalid("regex_find_all", {"pattern": "", "text": "a"}, "pattern", "empty-pattern"),
    invalid("regex_find_all", {"pattern": "a", "text": "a", "flags": ["unicode"]}, "flags", "unknown-flag"),
    invalid("regex_find_all", {"pattern": "a", "text": "a", "flags": ["ignore_case"] * 6}, "flags", "more-than-five-flags"),
    invalid("regex_find_all", {"pattern": "a", "text": "a" * 100_001}, "text", "over-regex-text-cap"),
    invalid("regex_match", {"pattern": "a", "text": "a", "mode": "fullmatch"}, "mode", "unknown-mode"),
    invalid("regex_replace", {"pattern": "a", "replacement": "b", "text": "a", "max_replacements": 0}, "max_replacements", "zero-replacements"),
    invalid("regex_split", {"pattern": "a", "text": "a", "max_splits": 0}, "max_splits", "zero-splits"),
    invalid("regex_test_samples", {"pattern": "a", "should_match": ["a"] * 101}, "should_match", "over-sample-cap"),
    invalid("verify_regex_pattern", {"pattern": "a" * 1001}, "pattern", "over-pattern-cap"),
    invalid("wildcard_match_names", {"pattern": "", "names": ["a"]}, "pattern", "empty-pattern"),
    # A.16 text_comparison: line and token caps are tool errors naming the text; the rest are schema errors.
    bad("unified_diff_text", {"original": "x\n" * 4001, "modified": "x"}, "original", "original-over-line-cap"),
    bad("unified_diff_text", {"original": "x", "modified": "x\n" * 4001}, "modified", "modified-over-line-cap"),
    bad("diff_words", {"original": "a " * 1001, "modified": "a"}, "original", "original-over-token-cap"),
    bad("diff_words", {"original": "a", "modified": "a " * 1001}, "modified", "modified-over-token-cap"),
    invalid("unified_diff_text", {"original": "a", "modified": "b", "context_lines": 101}, "context_lines", "context-over-cap"),
    invalid("unified_diff_text", {"original": "a", "modified": "b", "original_label": ""}, "original_label", "empty-label"),
    invalid("diff_words", {"original": "a" * 100_001, "modified": "a"}, "original", "over-medium-text-cap"),
    invalid("levenshtein_distance", {"first": "a" * 1001, "second": "a"}, "first", "over-pairwise-cap"),
    invalid("closest_string_matches", {"query": "a", "candidates": ["a"], "top": 0}, "top", "top-zero"),
    invalid("closest_string_matches", {"query": "a", "candidates": ["a"], "minimum_score": 1.5}, "minimum_score", "score-above-one"),
    invalid("closest_string_matches", {"query": "a", "candidates": ["a" * 101]}, "candidates", "candidate-over-cap"),
    invalid("closest_string_matches", {"query": "a" * 101, "candidates": ["a"]}, "query", "query-over-cap"),
    invalid("longest_common_substring", {"first": "a" * 2001, "second": "a"}, "first", "over-sequence-cap"),
    invalid("jaccard_similarity", {"first": "a", "second": "a", "n": 11}, "n", "n-over-cap"),
    invalid("jaccard_similarity", {"first": "a", "second": "a", "unit": "sentences"}, "unit", "unknown-unit"),
]


@pytest.mark.parametrize("case", SUCCESS_CASES)
def test_unicode_regex_rows_return_documented_output(tool_runner: ToolRunner, case: SuccessCase) -> None:
    tool_runner.check_success(case)


@pytest.mark.parametrize("case", FAILURE_CASES)
def test_unicode_regex_rows_reject_bad_input(tool_runner: ToolRunner, case: FailureCase) -> None:
    tool_runner.check_failure(case)


def test_verify_regex_pattern_reports_compile_error_text(tool_runner: ToolRunner) -> None:
    # Spec r4 (S017): the error is re.error.msg alone, so str(exc) with its " at position N" suffix is wrong.
    output = tool_runner.output("verify_regex_pattern", {"pattern": "a{2,1}"})
    assert output["error"] == "min repeat greater than max repeat"
    assert output["error_position"] == 2


def test_find_unicode_character_without_exact_name_lists_word_matches(tool_runner: ToolRunner) -> None:
    # "smiling cat" is no character's full name, so exact is null while every name holding both words is listed.
    case = SuccessCase("find_unicode_character", {"name_query": "smiling cat"}, {"exact": None, "matches": SMILING_CAT_MATCHES, "truncated": False})
    tool_runner.check_success(case)
