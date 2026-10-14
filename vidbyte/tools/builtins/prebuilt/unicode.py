"""FILE: vidbyte/tools/builtins/prebuilt/unicode.py

PURPOSE: Defines UnicodeToolFunctions, the ten prebuilt tools that inspect and repair Unicode text: character details, character search by name, normalization, diacritic removal, invisible and non-ASCII character reports, script detection, encoded size, SMS segments, and mojibake repair.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the UNICODE category is chosen. Builds on PrebuiltToolSupport in _support.py for the item cap, the word rule, and the argument error, and on the GSM-7, diacritic, zero-width, and bidirectional-control tables in vidbyte/lib/constants/prebuilt_tools.py.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Every character fact comes from the unicodedata module of the running Python, never from a hard-coded table, so names and categories follow its Unicode version. Work over a million-character text is done once per distinct character, found with collections.Counter or dict.fromkeys, and the text itself is walked only by C-level methods or one tight loop.
FUNCTION INVENTORY: unicode_character_info, find_unicode_character, apply_unicode_normalization, remove_diacritics, find_invisible_characters, find_non_ascii_characters, detect_scripts_in_text, count_bytes_in_encoding, sms_segment_count, and repair_mojibake_text are the tools; _exact_character and _named_matches serve the name search; _strip_latin_marks rewrites one character for diacritic removal; _invisible_kind and _invisible_findings classify and locate invisible characters; _first_appearances lists non-ASCII characters; _letter_script names the script of a letter; _undo_mojibake runs one repair round; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new Unicode tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.14, and its entry in tool_functions. A change to the GSM-7 alphabet, the diacritic fallbacks, or the zero-width and bidirectional-control sets goes in vidbyte/lib/constants/prebuilt_tools.py, not here.
WHAT NOT TO DO IN THIS FILE: 1. Do not hard-code Unicode names, categories, or script ranges; read them from unicodedata so results follow the running Python (EC-38). 2. Do not register a codec error handler for the mojibake repair, because that changes global interpreter state; split the text at the undefined bytes instead. 3. Do not iterate a set or a hash-ordered container when building an output. 4. Do not call PrebuiltToolSupport.line_and_column once per finding on a long text, because each call rescans the text from the start. 5. Do not hand a text that may expand to unicodedata.normalize in one piece, or expand it with str.translate; both grow their output a few code points at a time, so a million characters that expand eighteenfold take minutes.
KNOWN EDGE CASES: Positions count code points, so an emoji counts once. apply_unicode_normalization decomposes each distinct character first and joins the pieces, which gives the same result as one normalize call because decomposition is per character and the final pass reorders and composes the whole text. A combining mark typed as its own character is dropped by remove_diacritics when the nearest earlier base is Latin, and it counts as a changed character. A carriage return followed by a line feed is one line break for finding line numbers, and neither is ever a finding. An alias such as a control character's name can be the exact match of find_unicode_character even when the character has no Unicode name, and the alias then serves as its name.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.14, section 9.2 items 6, 8, and 12); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_unicode_regex.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_BIDI_CONTROL_CODE_POINTS,
    PREBUILT_DIACRITIC_FALLBACKS,
    PREBUILT_GSM7_BASIC_CHARACTERS,
    PREBUILT_GSM7_EXTENSION_CHARACTERS,
    PREBUILT_MAX_CHARACTER_MATCHES,
    PREBUILT_MAX_MOJIBAKE_ROUNDS,
    PREBUILT_MAX_PHRASE_CHARS,
    PREBUILT_MAX_SHORT_TEXT_CHARS,
    PREBUILT_MAX_TEXT_CHARS,
    PREBUILT_ZERO_WIDTH_CODE_POINTS,
)
from vidbyte.lib.enums.prebuilt_tools import (
    InvisibleCharacterKind,
    SmsEncoding,
    TextEncoding,
    UnicodeForm,
)
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_NORMALIZATION_FORMS: Mapping[UnicodeForm, Literal["NFC", "NFD", "NFKC", "NFKD"]] = MappingProxyType(
    {UnicodeForm.NFC: "NFC", UnicodeForm.NFD: "NFD", UnicodeForm.NFKC: "NFKC", UnicodeForm.NFKD: "NFKD"}
)
_DECOMPOSITION_FORMS: Mapping[UnicodeForm, Literal["NFD", "NFKD"]] = MappingProxyType(
    {UnicodeForm.NFC: "NFD", UnicodeForm.NFD: "NFD", UnicodeForm.NFKC: "NFKD", UnicodeForm.NFKD: "NFKD"}
)
_NAME_WORD_SEPARATOR = re.compile(r"[ -]")
_LINE_BREAK = re.compile(r"\r\n|\n|\r")
_CP1252_PIECES = re.compile("([\x81\x8d\x8f\x90\x9d])|([^\x81\x8d\x8f\x90\x9d]+)")
_LATIN_NAME_PREFIX = "LATIN "
_CJK_NAME_PREFIX = "CJK "
_KEPT_CONTROLS = frozenset("\t\n\r")
_GSM7_CHARACTERS = frozenset(PREBUILT_GSM7_BASIC_CHARACTERS + PREBUILT_GSM7_EXTENSION_CHARACTERS)
_GSM7_EXTENSION = frozenset(PREBUILT_GSM7_EXTENSION_CHARACTERS)
_GSM7_SINGLE_UNITS = 160
_GSM7_MULTIPART_UNITS = 153
_UCS2_SINGLE_UNITS = 70
_UCS2_MULTIPART_UNITS = 67
_UTF16_UNIT_SIZE = 2
_PERCENT_SCALE = 100
_PERCENT_PLACES = 2

_TEXT_PARAMETER_DESCRIPTION = "The text to examine, given as plain characters. Positions count Unicode code points, so an emoji or an accented letter counts once. Line breaks may be CRLF, LF, or a lone CR. The text may hold at most one million characters."


class UnicodeToolFunctions:
    """The unicode category: describing, finding, normalizing, cleaning, and measuring Unicode characters."""

    @staticmethod
    def unicode_character_info(
        text: Annotated[str, Field(description="The short text whose characters are described, given as plain characters. Each Unicode code point gets its own entry, so a letter followed by a separate accent mark gives two entries. It must hold at least 1 and at most 200 characters. Whitespace and control characters are described like any other character.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
    ) -> PrebuiltToolOutput:
        """List every character of a short text with its code point, Unicode name, general category, UTF-8 bytes in lowercase hex, and whether it is a combining mark. Use it to identify an odd or invisible symbol, to tell look-alike characters apart, or to see how a character is stored. Each code point is one entry, the name is null when Unicode gives the character none, and combining marks are the characters of general category M. Names and categories follow the Unicode version of the running Python, and the text must hold 1 to 200 characters."""
        # An unpaired surrogate has no UTF-8 form; the schema already
        # refuses one that arrives as JSON, so this guards direct calls.
        try:
            text.encode("utf-8")
        except UnicodeEncodeError as exc:
            problem = f"the character at position {exc.start} is an unpaired surrogate"
            raise PrebuiltToolSupport.argument_error("text", problem, "text made only of valid Unicode characters") from exc

        # Describe each code point from the running Python's Unicode
        # data.
        return {
            "characters": [
                {
                    "character": character,
                    "code_point": f"U+{ord(character):04X}",
                    "name": unicodedata.name(character, None),
                    "category": unicodedata.category(character),
                    "utf8_hex": character.encode("utf-8").hex(),
                    "is_combining": unicodedata.category(character).startswith("M"),
                }
                for character in text
            ]
        }

    @staticmethod
    def find_unicode_character(
        name_query: Annotated[str, Field(description="Words from the Unicode name of the character to find, separated by spaces. Matching ignores case and word order, and each query word must equal a whole word of the name, where hyphens also separate name words. The whole query is also tried as one exact character name or alias. It must hold 2 to 200 characters with at least one word.", min_length=2, max_length=PREBUILT_MAX_PHRASE_CHARS)],
    ) -> PrebuiltToolOutput:
        """Find Unicode characters whose names contain every word of a query, plus the character whose exact name or alias is the query. Use it to get a symbol, emoji, or accented letter when its name is known but the character itself is not at hand. Words match whole name words without regard to case or order, matches are listed in code-point order, and at most 100 are listed with truncated set when more exist. The search scans every code point and can take about a second, and a query with no words fails with an error naming name_query."""
        # Split the query into distinct case-folded words; a query of
        # only whitespace has nothing to look for.
        words = tuple(dict.fromkeys(name_query.casefold().split()))
        if not words:
            raise PrebuiltToolSupport.argument_error("name_query", "it holds only whitespace", "one or more words of a Unicode character name")

        # Try the whole query as one exact name or alias.
        exact = UnicodeToolFunctions._exact_character(name_query)

        # Scan every code point in order for names holding every word,
        # stopping once the match cap is passed.
        matches, truncated = PrebuiltToolSupport.cap_items(UnicodeToolFunctions._named_matches(words, exact), PREBUILT_MAX_CHARACTER_MATCHES)
        return {"exact": exact, "matches": matches, "truncated": truncated}

    @staticmethod
    def apply_unicode_normalization(
        text: Annotated[str, Field(description="The text to normalize, given as plain characters. Every character is kept or rewritten by the chosen Unicode normalization form, and nothing else changes. Compatibility forms can make the text longer, because some symbols expand into several letters. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)],
        form: Annotated[UnicodeForm, Field(description="The Unicode normalization form to apply. The value nfc composes letters and accents into single characters where possible, and nfd splits them apart. The values nfkc and nfkd also replace compatibility characters, such as ligatures and full-width forms, with their plain equivalents. There is no default, so the form must always be given.")],
    ) -> PrebuiltToolOutput:
        """Rewrite a text in one of the four Unicode normalization forms and report whether it changed and its length before and after. Use it before comparing, searching, or storing text whose accented letters may be composed in different ways. The canonical forms nfc and nfd keep the meaning of every character, while nfkc and nfkd also fold compatibility characters into plain ones and can lengthen the text. Lengths count code points, and the tool has no failure case beyond the text length cap."""
        # Decompose each distinct character on its own and join the
        # pieces first. CPython grows a normalization's output a few
        # code points at a time, which is very slow when a text expands
        # many times over, while the joined pieces never need to grow.
        # Normalizing them gives the same result as the original text.
        pieces = {character: unicodedata.normalize(_DECOMPOSITION_FORMS[form], character) for character in dict.fromkeys(text)}
        decomposed = "".join(map(pieces.__getitem__, text))

        # Apply the chosen form, which now only reorders and composes.
        normalized = unicodedata.normalize(_NORMALIZATION_FORMS[form], decomposed)
        return {"text": normalized, "changed": normalized != text, "length_before": len(text), "length_after": len(normalized)}

    @staticmethod
    def remove_diacritics(
        text: Annotated[str, Field(description="The text whose accents and diacritical marks are removed, given as plain characters. Only marks that follow a Latin letter are dropped, so other scripts keep their marks. A fixed table replaces the Latin letters with a stroke and the Latin ligatures, which Unicode does not decompose. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)],
    ) -> PrebuiltToolOutput:
        """Remove accents and other diacritical marks from Latin letters in a text and report how many input characters changed. Use it to build plain spellings for search keys, file names, or loose comparisons. Marks are dropped only when they follow a Latin letter, so Greek, Cyrillic, and other scripts keep theirs, and Latin letters without a decomposition are replaced through a fixed table. The result is in composed form, a character counts once however many letters replace it, and the tool has no failure case beyond the text length cap."""
        # Most characters stay as they are, so each distinct character
        # starts as itself, remembering whether it is a Latin base.
        distinct = dict.fromkeys(text)
        plain = {character: (character, False, unicodedata.name(character, "").startswith(_LATIN_NAME_PREFIX)) for character in distinct}
        after_latin: dict[str, tuple[str, bool, bool]] = {}

        # Rewrite the characters that can change: those in the fallback
        # table, those with a decomposition, and marks, once after a
        # Latin base and once after any other.
        for character in distinct:
            if character in PREBUILT_DIACRITIC_FALLBACKS or not unicodedata.is_normalized("NFD", character) or unicodedata.category(character).startswith("M"):
                plain[character] = UnicodeToolFunctions._strip_latin_marks(character, False)
                after_latin[character] = UnicodeToolFunctions._strip_latin_marks(character, True)

        # Walk the text once, carrying whether the last base was Latin,
        # because a separate mark belongs to the base before it.
        latin_base = False
        pieces: list[str] = []
        changed = 0
        for character in text:
            piece, was_changed, latin_base = after_latin.get(character, plain[character]) if latin_base else plain[character]
            pieces.append(piece)
            changed += was_changed

        # Recompose what is left into composed form.
        return {"text": unicodedata.normalize("NFC", "".join(pieces)), "changed_characters": changed}

    @staticmethod
    def find_invisible_characters(
        text: Annotated[str, Field(description=_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
    ) -> PrebuiltToolOutput:
        """Find zero-width characters, bidirectional controls, other format characters, unusual spaces, and control characters in a text, and return a cleaned copy. Use it to track down hidden characters that break parsing, comparisons, or copy and paste, or that disguise the direction of text. Each finding gives its code-point position, 1-based line and column, code point, name, and kind, at most 1,000 findings are listed while the count covers all, and tab, line feed, and carriage return are never findings. The cleaned text drops every finding except unusual spaces, which become plain spaces, and the tool has no failure case beyond the text length cap."""
        # Tally the text and classify each distinct character once.
        tallies = Counter(text)
        kinds: dict[str, InvisibleCharacterKind] = {}
        for character in tallies:
            kind = UnicodeToolFunctions._invisible_kind(character)
            if kind is not None:
                kinds[character] = kind

        # Drop every finding from the cleaned text, except unusual
        # spaces, which become plain spaces.
        cleaning = {ord(character): " " if kind is InvisibleCharacterKind.UNUSUAL_SPACE else None for character, kind in kinds.items()}

        # List the findings in text order up to the item cap, while the
        # count covers every one.
        findings, truncated = PrebuiltToolSupport.cap_items(UnicodeToolFunctions._invisible_findings(text, kinds))
        return {"count": sum(tallies[character] for character in kinds), "findings": findings, "truncated": truncated, "cleaned_text": text.translate(cleaning)}

    @staticmethod
    def find_non_ascii_characters(
        text: Annotated[str, Field(description=_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
    ) -> PrebuiltToolOutput:
        """List the distinct characters outside ASCII in a text, in order of first appearance, with their code point, name, number of occurrences, and first position. Use it to find accented letters, curly quotes, emoji, or other symbols that break ASCII-only systems. Positions count code points from zero, and the name is null when Unicode gives none. The count covers every distinct character while at most 1,000 are listed, and the tool has no failure case beyond the text length cap."""
        # A tally keeps characters in order of first appearance.
        tallies = Counter(text)
        outside = [character for character in tallies if not character.isascii()]
        characters, truncated = PrebuiltToolSupport.cap_items(UnicodeToolFunctions._first_appearances(text, outside, tallies))
        return {"count": len(outside), "characters": characters, "truncated": truncated}

    @staticmethod
    def detect_scripts_in_text(
        text: Annotated[str, Field(description=_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
    ) -> PrebuiltToolOutput:
        """Report which writing systems the letters of a text come from, with letter counts and percentages, and list words that mix letters from two or more systems. Use it to tell which scripts a text uses or to spot look-alike spoofing, where a letter from another script hides inside a word. The script of a letter is the first word of its Unicode name in lowercase, or cjk for the unified ideographs, and only letters are counted, so digits and punctuation are ignored. Scripts are sorted by letter count and then by name, percentages are rounded to two places, at most 1,000 mixed words are listed, and the tool has no failure case beyond the text length cap."""
        # Name the script of each distinct letter once, then add up the
        # letters of each script.
        tallies = Counter(text)
        scripts = {character: UnicodeToolFunctions._letter_script(character) for character in tallies if unicodedata.category(character).startswith("L")}
        totals: Counter[str] = Counter()
        for character, script in scripts.items():
            totals[script] += tallies[character]
        letters = sum(totals.values())
        ranked = sorted(totals.items(), key=lambda entry: (-entry[1], entry[0]))

        # List distinct words whose letters come from two or more
        # scripts; an ASCII word is all Latin, so it is skipped quickly.
        words = dict.fromkeys(word for _, word in PrebuiltToolSupport.split_words(text))
        mixed, truncated = PrebuiltToolSupport.cap_items(
            word for word in words if not word.isascii() and len({scripts[part] for part in word if part in scripts}) > 1
        )
        return {
            "scripts": [{"script": script, "letters": count, "percent": round(count * _PERCENT_SCALE / letters, _PERCENT_PLACES)} for script, count in ranked],
            "mixed_script_words": mixed,
            "truncated": truncated,
        }

    @staticmethod
    def count_bytes_in_encoding(
        text: Annotated[str, Field(description="The text whose encoded size is measured, given as plain characters. The character count in the result is in Unicode code points. An empty text has a size of zero, except for the byte-order mark some codecs write. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)],
        text_encoding: Annotated[TextEncoding, Field(description="The character encoding to measure the text in. The values name common codecs, and utf_16 and utf_32 count the byte-order mark the codec writes at the start. The variants with an explicit byte order write no mark. The default is utf_8.")] = TextEncoding.UTF_8,
    ) -> PrebuiltToolOutput:
        """Measure how many bytes a text takes in a chosen character encoding, and whether the encoding can represent it at all. Use it for storage limits, protocol size limits, or to check that a text survives a legacy encoding. The utf_16 and utf_32 sizes include the byte-order mark the codec writes, and the character count is in code points. Text the encoding cannot represent gives encodable false, a null size, and the position of the first character that fails, rather than an error."""
        try:
            size = len(text.encode(text_encoding.value.replace("_", "-")))
        except UnicodeEncodeError as exc:
            return {"size_bytes": None, "characters": len(text), "encodable": False, "first_unencodable_position": exc.start}
        return {"size_bytes": size, "characters": len(text), "encodable": True, "first_unencodable_position": None}

    @staticmethod
    def sms_segment_count(
        text: Annotated[str, Field(description="The SMS message text, given as plain characters. Every character counts, including spaces and line breaks. One character outside the GSM-7 alphabet switches the whole message to UCS-2, which fits fewer characters per segment. The text may hold at most ten thousand characters.", max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)],
    ) -> PrebuiltToolOutput:
        """Compute how many SMS segments a message needs, whether it must use the GSM-7 or the UCS-2 encoding, and how many encoding units it uses. Use it to keep a text message within one segment or to estimate its sending cost. GSM-7 fits 160 units in one segment and 153 per segment of a longer message, with extension characters costing two units, while UCS-2 fits 70 and 67 UTF-16 code units. The characters that force UCS-2 are listed once each in order of first appearance, and empty text gives zero segments."""
        # Collect the distinct characters GSM-7 cannot carry.
        offenders = [character for character in dict.fromkeys(text) if character not in _GSM7_CHARACTERS]

        # Without offenders the message is GSM-7, where an extension
        # character costs two units; otherwise it is UCS-2, counted in
        # UTF-16 code units.
        if offenders:
            encoding, single, multipart = SmsEncoding.UCS_2, _UCS2_SINGLE_UNITS, _UCS2_MULTIPART_UNITS
            units = len(text.encode("utf-16-le")) // _UTF16_UNIT_SIZE
        else:
            encoding, single, multipart = SmsEncoding.GSM_7, _GSM7_SINGLE_UNITS, _GSM7_MULTIPART_UNITS
            units = len(text) + sum(1 for character in text if character in _GSM7_EXTENSION)

        # A message that fits one segment uses the single size; a longer
        # one is split into multipart segments.
        per_segment = single if units <= single else multipart
        return {"encoding": encoding.value, "segments": -(-units // per_segment), "units_used": units, "units_per_segment": per_segment, "non_gsm_characters": offenders}

    @staticmethod
    def repair_mojibake_text(
        text: Annotated[str, Field(description="The text that may be garbled, given as plain characters. Garbled text shows UTF-8 byte sequences read as Windows-1252 or Latin-1, so one accented letter appears as two or three odd symbols. Text that is not garbled is returned unchanged. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)],
    ) -> PrebuiltToolOutput:
        """Repair text garbled by reading UTF-8 bytes as Windows-1252 or Latin-1, and report whether it changed and how many repair rounds ran. Use it when accented letters or symbols appear as clusters of odd characters after passing through a wrong encoding. Each round turns the text back into the bytes the wrong decoding came from and reads them as strict UTF-8, and at most two rounds run, which undoes double garbling. Text that is not garbled, or that a round cannot decode, comes back unchanged with repaired false, and the tool has no failure case beyond the text length cap."""
        # Keep a round only when it decodes and changes the text, and
        # stop at the first round that does not.
        repaired = text
        rounds = 0
        for _ in range(PREBUILT_MAX_MOJIBAKE_ROUNDS):
            candidate = UnicodeToolFunctions._undo_mojibake(repaired)
            if candidate is None or candidate == repaired:
                break
            repaired, rounds = candidate, rounds + 1
        return {"text": repaired, "repaired": rounds > 0, "rounds": rounds}

    @staticmethod
    def _exact_character(query: str) -> dict[str, str] | None:
        """Look the whole query up as one character name or alias, ignoring a named sequence of several characters."""
        try:
            found = unicodedata.lookup(query)
        except KeyError:
            return None
        if len(found) != 1:
            return None
        return {"character": found, "code_point": f"U+{ord(found):04X}", "name": unicodedata.name(found, query.upper())}

    @staticmethod
    def _named_matches(words: Sequence[str], exact: dict[str, str] | None) -> Iterator[dict[str, str]]:
        """Yield, in code-point order, every character whose name holds each word as a whole word, and the exact match in its place."""
        exact_point = ord(exact["character"]) if exact is not None else None
        wanted = set(words)
        for code_point in range(sys.maxunicode + 1):
            if code_point == exact_point and exact is not None:
                yield exact
                continue
            character = chr(code_point)
            name = unicodedata.name(character, "")
            folded = name.casefold()
            # A cheap substring test rules out almost every name before
            # the name is split into words.
            if name and all(word in folded for word in words) and wanted <= set(_NAME_WORD_SEPARATOR.split(folded)):
                yield {"character": character, "code_point": f"U+{code_point:04X}", "name": name}

    @staticmethod
    def _strip_latin_marks(character: str, latin_before: bool) -> tuple[str, bool, bool]:
        """Rewrite one character without the Mn marks that follow a Latin base, saying whether it changed and whether a Latin base comes last."""
        if character in PREBUILT_DIACRITIC_FALLBACKS:
            return PREBUILT_DIACRITIC_FALLBACKS[character], True, unicodedata.name(character, "").startswith(_LATIN_NAME_PREFIX)
        latin_base = latin_before
        kept: list[str] = []
        for part in unicodedata.normalize("NFD", character):
            category = unicodedata.category(part)
            if not category.startswith("M"):
                latin_base = unicodedata.name(part, "").startswith(_LATIN_NAME_PREFIX)
            if not (latin_base and category == "Mn"):
                kept.append(part)
        piece = "".join(kept)
        return piece, unicodedata.normalize("NFC", piece) != character, latin_base

    @staticmethod
    def _invisible_kind(character: str) -> InvisibleCharacterKind | None:
        """Classify one character as an invisible kind, or return None for an ordinary character."""
        code_point = ord(character)
        category = unicodedata.category(character)
        if code_point in PREBUILT_ZERO_WIDTH_CODE_POINTS:
            return InvisibleCharacterKind.ZERO_WIDTH
        if code_point in PREBUILT_BIDI_CONTROL_CODE_POINTS:
            return InvisibleCharacterKind.BIDI_CONTROL
        if category == "Cf":
            return InvisibleCharacterKind.FORMAT
        if category == "Zs" and character != " ":
            return InvisibleCharacterKind.UNUSUAL_SPACE
        if category == "Cc" and character not in _KEPT_CONTROLS:
            return InvisibleCharacterKind.CONTROL
        return None

    @staticmethod
    def _invisible_findings(text: str, kinds: Mapping[str, InvisibleCharacterKind]) -> Iterator[dict[str, object]]:
        """Yield each invisible character in text order with its 1-based line and column, counting line breaks as it goes."""
        if not kinds:
            return
        pattern = re.compile("[" + "".join(re.escape(character) for character in kinds) + "]")
        breaks = _LINE_BREAK.finditer(text)
        upcoming = next(breaks, None)
        line, line_start = 1, 0
        for match in pattern.finditer(text):
            position = match.start()
            # Move past every line break that ends before this finding.
            while upcoming is not None and upcoming.end() <= position:
                line, line_start = line + 1, upcoming.end()
                upcoming = next(breaks, None)
            character = match.group()
            yield {
                "position": position,
                "line": line,
                "column": position - line_start + 1,
                "code_point": f"U+{ord(character):04X}",
                "name": unicodedata.name(character, None),
                "kind": kinds[character].value,
            }

    @staticmethod
    def _first_appearances(text: str, characters: Sequence[str], tallies: Mapping[str, int]) -> Iterator[dict[str, object]]:
        """Yield each character with its tally and first position, given in order of first appearance."""
        # Each first position comes after the one before, so every
        # search starts where the last one stopped and the text is read
        # about once in all.
        position = 0
        for character in characters:
            position = text.index(character, position)
            yield {
                "character": character,
                "code_point": f"U+{ord(character):04X}",
                "name": unicodedata.name(character, None),
                "occurrences": tallies[character],
                "first_position": position,
            }

    @staticmethod
    def _letter_script(character: str) -> str:
        """Name the script of one letter from its Unicode name: cjk, the first name word in lowercase, or unknown."""
        name = unicodedata.name(character, "")
        if not name:
            return "unknown"
        if name.startswith(_CJK_NAME_PREFIX):
            return "cjk"
        return name.partition(" ")[0].lower()

    @staticmethod
    def _undo_mojibake(text: str) -> str | None:
        """Run one repair round: encode as cp1252 with Latin-1 for its five undefined bytes, then decode as strict UTF-8, or return None."""
        raw = bytearray()
        try:
            # Each piece is either one character of an undefined byte,
            # which Latin-1 writes as that same byte, or a run of other
            # characters.
            for gap, run in _CP1252_PIECES.findall(text):
                raw.extend(gap.encode("latin-1") if gap else run.encode("cp1252"))
            return raw.decode("utf-8")
        except UnicodeError:
            return None

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.unicode_character_info,
            cls.find_unicode_character,
            cls.apply_unicode_normalization,
            cls.remove_diacritics,
            cls.find_invisible_characters,
            cls.find_non_ascii_characters,
            cls.detect_scripts_in_text,
            cls.count_bytes_in_encoding,
            cls.sms_segment_count,
            cls.repair_mojibake_text,
        )


__all__ = ["UnicodeToolFunctions"]
