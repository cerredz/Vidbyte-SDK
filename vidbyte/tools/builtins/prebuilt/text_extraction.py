"""FILE: vidbyte/tools/builtins/prebuilt/text_extraction.py

PURPOSE: Defines TextExtractionToolFunctions, the eight prebuilt tools that pull structured values out of free text: web addresses, email addresses, numbers, dates, IP addresses, money amounts, key and value pairs, and sentences.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the TEXT_EXTRACTION category is chosen. Builds on PrebuiltToolSupport in _support.py for the date, line, and sentence rules, exact decimal text, and the item cap, and on the currency, magnitude suffix, and month name tables in vidbyte/lib/constants/prebuilt_tools.py.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Each tool scans the text with one precompiled pattern whose repeated parts are bounded or possessive, so a million-character text is scanned in linear time, and then checks or converts each candidate in a private helper. Tools that list every occurrence count in one pass and build items lazily in a second, while tools that list distinct values tally them in order of first appearance.
FUNCTION INVENTORY: extract_urls, extract_email_addresses, extract_numbers, extract_dates, extract_ip_addresses, extract_money_amounts, extract_key_value_pairs, and extract_sentences are the tools; _url_text trims a web address; _email_text checks an email candidate; _number_entry, _date_entry, and _money_entry convert one match into an output item; _ip_address checks an address candidate with ipaddress; _key_value_pairs splits lines into pairs; _tally_unique counts distinct values; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new extraction tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.29, and its entry in tool_functions. A new currency, magnitude suffix, or month name goes into its table in vidbyte/lib/constants/prebuilt_tools.py, and the patterns here pick it up when the module loads.
WHAT NOT TO DO IN THIS FILE: 1. Do not add a pattern with an unbounded repeat that a later part can force to backtrack; keep every repeat bounded or possessive so scanning stays linear. 2. Do not multiply or scale a Decimal outside a localcontext with enough precision; the default context rounds to 28 digits. 3. Do not split lines or sentences with a local rule; use PrebuiltToolSupport so every category agrees. 4. Do not build every item before capping; count first and build items lazily so the item cap and the character budget stop the work.
KNOWN EDGE CASES: A number, an amount, or a date that runs into a longer run of digits is skipped rather than cut, so a run of more than 4,000 digits never yields part of itself. A value whose exact plain text would pass the DecText length cap of 4,002 characters, such as a huge exponent, is skipped. Currency codes are matched in uppercase only, so ordinary words that spell a code in lowercase are not amounts. An IP candidate that ipaddress rejects is skipped whole, so an invalid address never yields a shorter valid tail.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.29, section 9.2 items 5, 6, 7, 9, and 12, section 12.3 row 36); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_extraction.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable, Iterator
from decimal import Decimal, localcontext
from types import MappingProxyType
from typing import Annotated, TypeVar

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_ABBREVIATED_NUMBER_SUFFIXES,
    PREBUILT_CURRENCY_CODES,
    PREBUILT_CURRENCY_SYMBOLS,
    PREBUILT_FINANCE_PRECISION,
    PREBUILT_MAX_DECIMAL_TEXT_CHARS,
    PREBUILT_MAX_INTEGER_DIGITS,
    PREBUILT_MAX_KEY_CHARS,
    PREBUILT_MAX_SHORT_TEXT_CHARS,
    PREBUILT_MAX_TEXT_CHARS,
    PREBUILT_MONTH_NAMES,
)
from vidbyte.lib.enums.prebuilt_tools import KeyValueSeparator
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_Shown = TypeVar("_Shown")

_EMAIL_LOCAL_LENGTH = 64
_EMAIL_DOMAIN_LENGTH = 253
_PRODUCT_PRECISION = PREBUILT_MAX_DECIMAL_TEXT_CHARS + PREBUILT_FINANCE_PRECISION
_URL_TRAILING_PUNCTUATION = frozenset(".,;:!?'")
_URL_BRACKETS = MappingProxyType({")": "(", "]": "["})
_SEPARATOR_MARKS = MappingProxyType({KeyValueSeparator.AUTO: ":=", KeyValueSeparator.COLON: ":", KeyValueSeparator.EQUALS: "="})

# A digit run is bounded by the 4,000-digit rule and possessive, so a
# longer run fails at once instead of matching a part of itself.
_DIGITS = f"[0-9]{{1,{PREBUILT_MAX_INTEGER_DIGITS}}}+"
# A grouped amount never starts right after three digits and a comma,
# so a comma chain that fails at its end is scanned once, not once
# per comma; the guard covers only the grouped form, so 1,2,3 still
# gives three numbers.
_AMOUNT = rf"(?:(?<![0-9]{{3}},)(?>[0-9]{{1,3}}(?:,[0-9]{{3}})++)|{_DIGITS})(?:\.{_DIGITS})?|\.{_DIGITS}"
_SIGN = r"(?P<sign>(?<![^\s(\[=:,])[+-])?"
_MONTHS = "|".join(sorted(PREBUILT_MONTH_NAMES, key=lambda name: (-len(name), name)))
_SYMBOLS = "|".join(re.escape(symbol) for symbol in PREBUILT_CURRENCY_SYMBOLS)
_CODES = "|".join(PREBUILT_CURRENCY_CODES)
_SUFFIXES = "|".join("".join(f"[{letter}{letter.upper()}]" for letter in suffix) for suffix in sorted(PREBUILT_ABBREVIATED_NUMBER_SUFFIXES, key=lambda name: (-len(name), name)))

_URL = re.compile(r"(?P<prefix>[hH][tT][tT][pP][sS]?://|[fF][tT][pP]://|[wW][wW][wW]\.)(?P<body>[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]*+)")
_EMAIL = re.compile(rf"(?<![A-Za-z0-9._%+-])(?P<local>[A-Za-z0-9._%+-]{{1,{_EMAIL_LOCAL_LENGTH}}}+)@(?P<domain>[A-Za-z0-9.-]{{1,{_EMAIL_DOMAIN_LENGTH}}}+)(?![A-Za-z0-9.-])")
_EMAIL_LOCAL = re.compile(r"[A-Za-z0-9_%+-]+(?:\.[A-Za-z0-9_%+-]+)*")
_EMAIL_DOMAIN = re.compile(r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}")
_NUMBER = re.compile(rf"{_SIGN}(?<![\w.])(?P<mantissa>{_AMOUNT})(?:[eE](?P<exponent>[+-]?{_DIGITS}))?(?![0-9]|\.[0-9]|[eE][+-]?[0-9])(?P<percent>%)?")
_DATE = re.compile(
    r"(?<![0-9])[0-9]{4}(?P<iso_separator>[-/.])[0-9]{1,2}(?P=iso_separator)[0-9]{1,2}(?:[Tt ][0-9]{1,2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]++)?)?(?:[Zz]|[+-][0-9]{2}:?[0-9]{2})?)?(?![0-9])"
    + r"|(?<![0-9])[0-9]{1,2}(?P<numeric_separator>[/.-])[0-9]{1,2}(?P=numeric_separator)[0-9]{4}(?![0-9])"
    + rf"|(?i:\b(?:{_MONTHS})\.?\s++[0-9]{{1,2}}(?:st|nd|rd|th)?,?\s++[0-9]{{4}})(?![0-9])"
    + rf"|(?i:(?<![0-9])[0-9]{{1,2}}(?:st|nd|rd|th)?\s++(?:of\s++)?(?:{_MONTHS})\.?,?\s++[0-9]{{4}})(?![0-9])"
)
_IP_ADDRESS = re.compile(
    r"(?<![0-9A-Za-z.:])(?:[0-9]{1,3}(?:\.[0-9]{1,3}){3}(?![0-9A-Za-z]|\.[0-9])"
    + r"|(?=:*+[0-9A-Fa-f])(?:[0-9A-Fa-f]{1,4})?(?::[0-9A-Fa-f]{0,4}){2,7}(?:(?<=:)[0-9]{1,3}(?:\.[0-9]{1,3}){3})?(?![0-9A-Za-z:]|\.[0-9]))"
)
_MONEY = re.compile(
    rf"{_SIGN}(?:(?P<before>{_SYMBOLS}|(?<![A-Za-z])(?:{_CODES}))[ \u00a0]?(?P<number_before>{_AMOUNT})(?![0-9]|\.[0-9])(?:[ ]*+(?P<suffix_before>{_SUFFIXES})(?![A-Za-z]))?"
    + rf"|(?<![\w.])(?P<number_after>{_AMOUNT})(?![0-9]|\.[0-9])(?:[ ]*+(?P<suffix_after>{_SUFFIXES})(?![A-Za-z]))?[ \u00a0]?(?P<after>{_SYMBOLS}|(?:{_CODES})(?![A-Za-z])))"
)
_KEY = re.compile(rf"[\w ./-]{{1,{PREBUILT_MAX_KEY_CHARS}}}")

_TEXT_DESCRIPTION = "The text to search, given as plain characters. Positions count Unicode code points, so an emoji or an accented letter counts once. Line breaks may be CRLF, LF, or a lone CR. The text may hold at most one million characters."


class TextExtractionToolFunctions:
    """The text_extraction category: pulling addresses, numbers, dates, amounts, pairs, and sentences out of free text."""

    @staticmethod
    def extract_urls(text: Annotated[str, Field(description=_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Find the web addresses in a text and list each distinct one with how often it occurs and where it first appears. Use it to collect links from messages, logs, or documents without missing any by eye. An address starts at http, https, or ftp followed by a colon and two slashes, or at www followed by a dot, and runs over the ASCII characters web addresses allow, with trailing sentence punctuation and unbalanced closing brackets removed. Addresses are compared exactly, at most 1,000 are listed while count covers every distinct address, and the tool has no failure case beyond the text length cap."""
        # Find each candidate, trim what ends a sentence, and drop one
        # left with nothing after its prefix.
        found = ((TextExtractionToolFunctions._url_text(match), match.start()) for match in _URL.finditer(text))

        # Count each distinct address once, in order of first sight.
        tallies = TextExtractionToolFunctions._tally_unique((url, url, position) for url, position in found if url)
        urls, truncated = PrebuiltToolSupport.cap_items({"url": url, "occurrences": occurrences, "first_position": first} for url, occurrences, first in tallies)
        return {"urls": urls, "count": len(tallies), "truncated": truncated}

    @staticmethod
    def extract_email_addresses(text: Annotated[str, Field(description=_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Find the email addresses in a text and list each distinct one with how often it occurs and where it first appears. Use it to collect contact addresses from messages or documents reliably. An address needs a dot-separated local part of at most 64 characters, an at sign, and a domain of at most 253 characters whose last label has at least two letters. Addresses that differ only in case count as one and keep their first spelling, and at most 1,000 are listed while count covers every distinct address. The tool has no failure case beyond the text length cap."""
        # Find each candidate and keep those whose two parts are valid.
        found = ((TextExtractionToolFunctions._email_text(match), match.start()) for match in _EMAIL.finditer(text))

        # Count addresses once each without regard to case, keeping the
        # first spelling seen.
        tallies = TextExtractionToolFunctions._tally_unique((address.casefold(), address, position) for address, position in found if address is not None)
        emails, truncated = PrebuiltToolSupport.cap_items({"email": address, "occurrences": occurrences, "first_position": first} for address, occurrences, first in tallies)
        return {"emails": emails, "count": len(tallies), "truncated": truncated}

    @staticmethod
    def extract_numbers(text: Annotated[str, Field(description=_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Find every number written in a text, with its exact value, its position, and whether a percent sign follows it. Use it to pull figures out of prose, tables, or reports exactly instead of retyping them. Decimals, comma groups of three, and scientific notation are read and expanded exactly, a sign counts only at the start or after whitespace, an opening bracket, an equals sign, a colon, or a comma, and a percent value is kept as written rather than divided by 100. A run of more than 4,000 digits or a value too long to write out in plain digits is skipped, and at most 1,000 numbers are listed while count covers every one."""
        # Count every readable number first, then list them lazily so
        # the item cap and the character budget stop the work early.
        count = sum(1 for match in _NUMBER.finditer(text) if TextExtractionToolFunctions._number_entry(match) is not None)
        entries = (entry for entry in map(TextExtractionToolFunctions._number_entry, _NUMBER.finditer(text)) if entry is not None)
        numbers, truncated = PrebuiltToolSupport.cap_items(entries)
        return {"numbers": numbers, "count": count, "truncated": truncated}

    @staticmethod
    def extract_dates(
        text: Annotated[str, Field(description=_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        day_first: Annotated[bool, Field(description="How to read a numeric date whose first two parts could both be a month. When true, the first part is the day, and when false, it is the month. A part above twelve is always read as the day, whatever this says. The default is false.")] = False,
    ) -> PrebuiltToolOutput:
        """Find the dates written in a text and convert each to the ISO calendar form, with its position and whether its reading was ambiguous. Use it to normalize the dates in messages, contracts, or notes before comparing or sorting them. ISO dates with dashes, slashes, or dots and an optional time, day and month numbers with a four-digit year, and English month names before or after the day are read, while an eight-digit compact date is not. Impossible dates are skipped, day_first decides numeric dates whose first two parts could both be the month, and at most 1,000 dates are listed while count covers every one."""
        # Count every real date first, then list them lazily so the
        # item cap and the character budget stop the work early.
        count = sum(1 for match in _DATE.finditer(text) if TextExtractionToolFunctions._date_entry(match, day_first) is not None)
        entries = (entry for entry in (TextExtractionToolFunctions._date_entry(match, day_first) for match in _DATE.finditer(text)) if entry is not None)
        dates, truncated = PrebuiltToolSupport.cap_items(entries)
        return {"dates": dates, "count": count, "truncated": truncated}

    @staticmethod
    def extract_ip_addresses(text: Annotated[str, Field(description=_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Find the IPv4 and IPv6 addresses in a text and list each distinct one with its version, how often it occurs, and where it first appears. Use it to collect hosts from logs, configuration files, or incident notes. Every candidate is checked with the standard ipaddress rules, so an octet above 255 or a malformed IPv6 address is skipped as a whole, and addresses are reported and compared in their compressed form. At most 1,000 addresses are listed while count covers every distinct address, and the tool has no failure case beyond the text length cap."""
        # Find each candidate and keep those ipaddress accepts.
        found = ((TextExtractionToolFunctions._ip_address(match), match.start()) for match in _IP_ADDRESS.finditer(text))

        # Count each compressed address once, in order of first sight.
        tallies = TextExtractionToolFunctions._tally_unique((address[0], address, position) for address, position in found if address is not None)
        addresses, truncated = PrebuiltToolSupport.cap_items(
            {"address": address, "version": version, "occurrences": occurrences, "first_position": first} for (address, version), occurrences, first in tallies
        )
        return {"addresses": addresses, "count": len(tallies), "truncated": truncated}

    @staticmethod
    def extract_money_amounts(text: Annotated[str, Field(description=_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Find the money amounts in a text with their currency, exact value, and position. Use it to pull totals, fees, or budgets out of prose without misreading separators or magnitude suffixes. A currency symbol or an uppercase three-letter ISO code may come before or after the number, and a magnitude suffix of thousand, million, billion, or trillion in short or long form multiplies the value exactly. Every occurrence is listed in text order with its currency as written, and at most 1,000 amounts are listed while count covers every one."""
        # Count every readable amount first, then list them lazily so
        # the item cap and the character budget stop the work early.
        count = sum(1 for match in _MONEY.finditer(text) if TextExtractionToolFunctions._money_entry(match) is not None)
        entries = (entry for entry in map(TextExtractionToolFunctions._money_entry, _MONEY.finditer(text)) if entry is not None)
        amounts, truncated = PrebuiltToolSupport.cap_items(entries)
        return {"amounts": amounts, "count": count, "truncated": truncated}

    @staticmethod
    def extract_key_value_pairs(
        text: Annotated[str, Field(description=_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        separator: Annotated[KeyValueSeparator, Field(description="Which character separates a key from its value on each line. The auto setting splits at whichever of a colon or an equals sign comes first on the line, colon splits only at a colon, and equals splits only at an equals sign. The default is auto. Any other value fails validation.")] = KeyValueSeparator.AUTO,
    ) -> PrebuiltToolOutput:
        """Find key and value pairs written one per line with a colon or an equals sign, with the 1-based line number of each. Use it to read settings, headers, or form-like text into named fields. Each line splits at its first separator, both parts are trimmed, and a key must hold 1 to 100 letters, digits, spaces, underscores, hyphens, dots, or slashes, so lines without such a key are skipped. At most 1,000 pairs are listed while count covers every pair, and the tool has no failure case beyond the text length cap."""
        # Count every pair first, then list them lazily so the item cap
        # and the character budget stop the work early.
        count = sum(1 for _ in TextExtractionToolFunctions._key_value_pairs(text, separator))
        entries = ({"key": key, "value": value, "line": line} for line, key, value in TextExtractionToolFunctions._key_value_pairs(text, separator))
        pairs, truncated = PrebuiltToolSupport.cap_items(entries)
        return {"pairs": pairs, "count": count, "truncated": truncated}

    @staticmethod
    def extract_sentences(
        text: Annotated[str, Field(description=_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        contains: Annotated[str | None, Field(description="A phrase each listed sentence must contain, matched without regard to case. Null, the default, keeps every sentence. Sentence indexes still count every sentence, so a filtered list can skip indexes. The phrase may hold at most ten thousand characters.", max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)] = None,
    ) -> PrebuiltToolOutput:
        """Split a text into sentences with each one's index and starting position, optionally keeping only those that contain a phrase. Use it to quote, count, or filter sentences exactly instead of splitting text by eye. A sentence ends at a period, question mark, exclamation mark, or ellipsis followed by whitespace or the end, except after a common abbreviation or a single capital initial, and closing quotes or brackets stay with it. The phrase filter ignores case, index counts every sentence even when some are filtered out, and at most 1,000 sentences are listed while count covers every kept sentence."""
        # Split the text once and keep the sentences holding the phrase.
        phrase = contains.casefold() if contains is not None else None
        kept = [(index, start, sentence) for index, (start, sentence) in enumerate(PrebuiltToolSupport.split_sentences(text)) if phrase is None or phrase in sentence.casefold()]

        # List the kept sentences up to the item cap.
        sentences, truncated = PrebuiltToolSupport.cap_items({"index": index, "text": sentence, "start": start} for index, start, sentence in kept)
        return {"sentences": sentences, "count": len(kept), "truncated": truncated}

    @staticmethod
    def _url_text(found: re.Match[str]) -> str:
        """Trim trailing sentence punctuation and unbalanced closing brackets from a web address, or return empty text when only the prefix is left."""
        body = found["body"]
        opened = {closer: body.count(opener) for closer, opener in _URL_BRACKETS.items()}
        closed = {closer: body.count(closer) for closer in _URL_BRACKETS}
        end = len(body)
        while end:
            last = body[end - 1]
            if last in closed and closed[last] > opened[last]:
                closed[last] -= 1
            elif last not in _URL_TRAILING_PUNCTUATION:
                break
            end -= 1
        return found["prefix"] + body[:end] if end else ""

    @staticmethod
    def _email_text(found: re.Match[str]) -> str | None:
        """Return an email candidate without trailing dots when its local part and domain are valid, or None."""
        domain = found["domain"].rstrip(".")
        if _EMAIL_LOCAL.fullmatch(found["local"]) is None or _EMAIL_DOMAIN.fullmatch(domain) is None:
            return None
        return f"{found['local']}@{domain}"

    @staticmethod
    def _number_entry(found: re.Match[str]) -> dict[str, object] | None:
        """Turn a number match into its output item with the exact value, or None when the value is too long to write out."""
        exponent = int(found["exponent"]) if found["exponent"] else 0
        if abs(exponent) > PREBUILT_MAX_DECIMAL_TEXT_CHARS:
            return None
        value = PrebuiltToolSupport.decimal_text(Decimal(f"{found['sign'] or ''}{found['mantissa'].replace(',', '')}E{exponent}"))
        if len(value) > PREBUILT_MAX_DECIMAL_TEXT_CHARS:
            return None
        return {"text": found.group(), "value": value, "position": found.start(), "is_percent": found["percent"] is not None}

    @staticmethod
    def _date_entry(found: re.Match[str], day_first: bool) -> dict[str, object] | None:
        """Turn a date match into its output item, or None when it names a day that does not exist."""
        parsed = PrebuiltToolSupport.parse_date_text(found.group(), day_first)
        if parsed is None:
            return None
        day, ambiguous = parsed
        return {"text": found.group(), "date": day.isoformat(), "position": found.start(), "ambiguous": ambiguous}

    @staticmethod
    def _ip_address(found: re.Match[str]) -> tuple[str, int] | None:
        """Return the compressed form and version of an address candidate, or None when ipaddress rejects it."""
        try:
            address = ipaddress.ip_address(found.group())
        except ValueError:
            return None
        return address.compressed, address.version

    @staticmethod
    def _money_entry(found: re.Match[str]) -> dict[str, object] | None:
        """Turn a money match into its output item with the exact value, or None when the value is too long to write out."""
        number = found["number_before"] or found["number_after"]
        suffix = found["suffix_before"] or found["suffix_after"]
        if len(number) - number.count(",") - number.count(".") > PREBUILT_MAX_DECIMAL_TEXT_CHARS:
            return None
        # The context is wide enough that multiplying by a magnitude
        # suffix never rounds.
        multiplier = PREBUILT_ABBREVIATED_NUMBER_SUFFIXES[suffix.lower()] if suffix else 1
        with localcontext(prec=_PRODUCT_PRECISION):
            value = PrebuiltToolSupport.decimal_text(Decimal(f"{found['sign'] or ''}{number.replace(',', '')}") * multiplier)
        if len(value) > PREBUILT_MAX_DECIMAL_TEXT_CHARS:
            return None
        return {"text": found.group(), "currency": found["before"] or found["after"], "value": value, "position": found.start()}

    @staticmethod
    def _key_value_pairs(text: str, separator: KeyValueSeparator) -> Iterator[tuple[int, str, str]]:
        """Yield (line number, key, value) for every line that splits at its first separator into a valid key and a value."""
        marks = _SEPARATOR_MARKS[separator]
        for number, line in enumerate(PrebuiltToolSupport.split_lines(text), start=1):
            at = min((index for index in (line.find(mark) for mark in marks) if index >= 0), default=-1)
            key = line[:at].strip()
            if at >= 0 and _KEY.fullmatch(key) is not None:
                yield number, key, line[at + 1 :].strip()

    @staticmethod
    def _tally_unique(found: Iterable[tuple[str, _Shown, int]]) -> list[tuple[_Shown, int, int]]:
        """Count (key, shown value, position) triples by key in order of first appearance, keeping the first shown value and position."""
        tallies: dict[str, tuple[_Shown, int, int]] = {}
        for key, shown, position in found:
            first, occurrences, first_position = tallies.get(key, (shown, 0, position))
            tallies[key] = (first, occurrences + 1, first_position)
        return list(tallies.values())

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.extract_urls,
            cls.extract_email_addresses,
            cls.extract_numbers,
            cls.extract_dates,
            cls.extract_ip_addresses,
            cls.extract_money_amounts,
            cls.extract_key_value_pairs,
            cls.extract_sentences,
        )


__all__ = ["TextExtractionToolFunctions"]
