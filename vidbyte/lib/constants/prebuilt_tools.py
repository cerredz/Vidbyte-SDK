"""FILE: vidbyte/lib/constants/prebuilt_tools.py

PURPOSE: Holds every length cap, resource bound, fixed precision, shorthand pattern, and reference table the prebuilt tool library uses, so each limit has one name and one value.
ROLE IN CODEBASE: Imported by vidbyte/tools/builtins/prebuilt/_support.py and the 31 category modules beside it, which use the caps in their pydantic Field constraints and the tables in their parsing and formatting. Imports enums from vidbyte/lib/enums/prebuilt_tools.py for four tables.
ARCHITECTURE NOTE: Every value is immutable: an int, a float, a str, a tuple, a frozenset, or a read-only MappingProxyType. The caps are sized for the slowest algorithm that reads them (spec NFR-7), so raising one can make a tool call run far longer than two seconds.
FUNCTION INVENTORY: No functions. Caps and budgets (PREBUILT_MAX_*), the field patterns of the IntText, DecText, and UtcOffset shorthands (PREBUILT_*_PATTERN), fixed numeric settings (PREBUILT_FINANCE_PRECISION, the PREBUILT_IRR_* search settings, PREBUILT_EARTH_RADIUS_KILOMETERS), and reference tables (sentence abbreviations, GSM-7 alphabets, currency codes and symbols, diacritic fallbacks, CSV delimiter characters, JSON value types, number words, size and duration words, month names, HTML block tags, invisible code points, comment syntax).
COMMON MODIFICATION PATTERNS: A new bound gets a PREBUILT_ name here before any tool uses it, and that name goes into __all__. A reference table changes together with the Appendix A row that names its contents.
WHAT NOT TO DO IN THIS FILE: 1. Do not use a name that holds an A007 token (timeout, token, char, byte, limit, depth, interval, and the rest) as a whole underscore-separated word, because tool signatures read these names. 2. Do not store mutable lists, sets, or dicts. 3. Do not import anything above vidbyte.lib.
KNOWN EDGE CASES: PREBUILT_MAX_INTEGER_DIGITS stays below Python's default 4,300-digit int-to-text limit, so an allowed integer always converts to text. PREBUILT_MAX_UTC_OFFSET_CHARS is the longest text the UtcOffset pattern accepts.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (section 9.2 caps and constants, reference tables); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/ (the schema contract test compares every cap)
"""

from __future__ import annotations

from types import MappingProxyType

from vidbyte.lib.enums.prebuilt_tools import (
    CodeLanguage,
    CsvDelimiter,
    JsonType,
    SizeStandard,
)

# Text and list caps.
PREBUILT_MAX_TEXT_CHARS = 1_000_000
PREBUILT_MAX_SHORT_TEXT_CHARS = 10_000
PREBUILT_MAX_NAME_CHARS = 200
PREBUILT_MAX_LIST_ITEMS = 10_000
PREBUILT_MAX_RESULT_ITEMS = 1_000
PREBUILT_MAX_PHRASE_CHARS = 200
PREBUILT_MAX_UTC_OFFSET_CHARS = 6
PREBUILT_MAX_EXPRESSION_CHARS = 1_000
PREBUILT_MAX_MEDIUM_TEXT_CHARS = 100_000
PREBUILT_MAX_ENCODED_TEXT_CHARS = 2_000_000

# Exact numbers.
PREBUILT_MAX_INTEGER_DIGITS = 4_000
PREBUILT_MAX_INTEGER_TEXT_CHARS = 4_001
PREBUILT_MAX_DECIMAL_TEXT_CHARS = 4_002
PREBUILT_MAX_FRACTION_TEXT_CHARS = 8_002
PREBUILT_MAX_DENOMINATOR = 1_000_000_000_000
PREBUILT_MAX_MODULAR_TEXT_CHARS = 2_001
PREBUILT_MAX_DECIMAL_PLACES = 1_000
PREBUILT_DEFAULT_DIVISION_PLACES = 28
PREBUILT_APPROXIMATION_DIGITS = 20
PREBUILT_MAX_SIGNIFICANT_FIGURES = 100

# Field patterns of the IntText, DecText, and UtcOffset shorthands
# (section 9.2).
PREBUILT_INTEGER_TEXT_PATTERN = r"^[+-]?[0-9]+$"
PREBUILT_DECIMAL_TEXT_PATTERN = r"^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)$"
PREBUILT_UTC_OFFSET_PATTERN = r"^(Z|[+-](0[0-9]|1[0-9]|2[0-3]):[0-5][0-9])$"

# Patterns, comparison, and source code.
PREBUILT_MAX_PATTERN_CHARS = 1_000
PREBUILT_MAX_REGEX_TEXT_CHARS = 100_000
PREBUILT_MAX_REGEX_SAMPLES = 100
PREBUILT_MAX_SEARCH_STRING_CHARS = 500
PREBUILT_MAX_PAIRWISE_CHARS = 1_000
PREBUILT_MAX_SEQUENCE_MATCH_CHARS = 2_000
PREBUILT_MAX_DIFF_LINES = 4_000
PREBUILT_MAX_DIFF_TOKENS = 2_000
PREBUILT_MAX_FUZZY_CANDIDATES = 1_000
PREBUILT_MAX_FUZZY_CANDIDATE_CHARS = 100
PREBUILT_MAX_SOURCE_CHARS = 200_000

# Records, tables, JSON, and graphs.
PREBUILT_MAX_RECORDS = 10_000
PREBUILT_MAX_TABLE_COLUMNS = 500
PREBUILT_MAX_SNIFF_CHARS = 10_000
PREBUILT_MAX_JSON_NESTING = 100
PREBUILT_MAX_PATCH_OPERATIONS = 1_000
PREBUILT_MAX_PATCH_WORK_CHARS = 10_000_000
PREBUILT_MAX_JSON_SCAN_STARTS = 1_000
PREBUILT_MAX_XML_PATH_VISITS = 2_000_000
PREBUILT_MAX_GRAPH_EDGES = 10_000
PREBUILT_MAX_SCHEDULE_TASKS = 1_000

# Number theory, combinatorics, and probability.
PREBUILT_MAX_FACTORIZE_VALUE = 1_000_000_000_000
PREBUILT_MAX_PRIMALITY_VALUE = 3_317_044_064_679_887_385_961_980
PREBUILT_MAX_SIEVE_VALUE = 10_000_000
PREBUILT_MAX_NTH_PRIME = 100_000
PREBUILT_MAX_COMBINATORIC_N = 10_000
PREBUILT_MAX_COMBINATION_ITEMS = 20
PREBUILT_MAX_POISSON_OCCURRENCES = 100_000
PREBUILT_MAX_POISSON_RATE = 1_000_000
PREBUILT_MAX_BIRTHDAY_ITEMS = 100_000
PREBUILT_MAX_BIRTHDAY_VALUES = 1_000_000_000_000_000_000

# Seeded randomness.
PREBUILT_MAX_SEED = 9_223_372_036_854_775_807
PREBUILT_MAX_RANDOM_PICKS = 1_000
PREBUILT_MAX_RANDOM_MAGNITUDE = 1_000_000_000_000_000
PREBUILT_MAX_DICE = 1_000
PREBUILT_MAX_DIE_SIDES = 1_000
PREBUILT_MAX_DICE_MODIFIER = 1_000_000

# Finance.
PREBUILT_MAX_MONEY_AMOUNT = 1_000_000_000_000_000
PREBUILT_FINANCE_PRECISION = 50
PREBUILT_MAX_RATE_PERCENT = 1_000
PREBUILT_MAX_LOAN_MONTHS = 600
PREBUILT_MAX_FINANCE_YEARS = 1_000
PREBUILT_MAX_CASH_FLOWS = 600
PREBUILT_IRR_GRID_START = -0.99
PREBUILT_IRR_GRID_STEP = 0.01
PREBUILT_IRR_GRID_POINTS = 1_100
PREBUILT_IRR_TOLERANCE = 1e-12
PREBUILT_IRR_BISECTION_STEPS = 200
PREBUILT_MAX_SHARE_PLACES = 10

# Text tools.
PREBUILT_MIN_CHUNK_CHARS = 100
PREBUILT_MAX_REPORTED_NAMES = 20
PREBUILT_MAX_MOJIBAKE_ROUNDS = 2
PREBUILT_PROFILE_EXAMPLES = 3
PREBUILT_MAX_KEY_CHARS = 100
PREBUILT_MAX_TOP_ITEMS = 1_000
PREBUILT_MAX_NGRAM_SIZE = 10
PREBUILT_MAX_CHARACTER_MATCHES = 100
PREBUILT_MAX_CONTEXT_LINES = 100
PREBUILT_MAX_INDENT = 8
PREBUILT_MAX_NUMBER_WORD_DIGITS = 36
PREBUILT_HEX_PREVIEW_SIZE = 64

# Dates, times, and durations.
PREBUILT_MAX_DATE_OFFSET = 1_000_000
PREBUILT_MAX_BUSINESS_DAYS = 100_000
PREBUILT_MAX_DATE_SPAN_DAYS = 36_600
PREBUILT_MAX_RECURRENCE_STEP = 1_000
PREBUILT_MAX_HOLIDAYS = 1_000
PREBUILT_MAX_DURATION_SECONDS = 1_000_000_000_000
PREBUILT_MAX_FREE_SLOT_MINUTES = 525_600

# Statistics, lists, bits, sizes, and geometry.
PREBUILT_MAX_MOVING_AVERAGE_WINDOW = 1_000
PREBUILT_MAX_OUTLIER_MULTIPLIER = 10
PREBUILT_MAX_BIT_WIDTH = 4_096
PREBUILT_MAX_DATA_SIZE_BYTES = 1_000_000_000_000_000_000_000_000
PREBUILT_MAX_SIZE_DECIMAL_PLACES = 6
PREBUILT_MAX_INTEGER_RANGE_SPAN = 10_000_000
PREBUILT_MAX_LISTS = 100
PREBUILT_MAX_BUCKETS = 1_000_000
PREBUILT_EARTH_RADIUS_KILOMETERS = 6371.0088

# Tokens that do not end a sentence when a period follows them (section
# 9.2 item 9); a single uppercase letter, an initial, does not either.
PREBUILT_SENTENCE_ABBREVIATIONS = frozenset(
    {"mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.", "st.", "vs.", "etc.", "e.g.", "i.e.", "inc.", "ltd.", "co.", "no."}
)

# The GSM 03.38 default alphabet, without the escape code, and its
# extension table, whose characters cost two units each.
PREBUILT_GSM7_BASIC_CHARACTERS = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    + "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
PREBUILT_GSM7_EXTENSION_CHARACTERS = "\f^{}\\[~]|€"

PREBUILT_CURRENCY_CODES = (
    "USD", "EUR", "GBP", "JPY", "CNY", "INR", "CAD", "AUD", "CHF", "SEK", "NOK", "DKK", "NZD", "MXN", "BRL", "ZAR",
    "KRW", "SGD", "HKD", "RUB", "TRY", "PLN", "ILS", "AED", "SAR", "THB", "IDR", "MYR", "PHP", "CZK", "HUF",
)
PREBUILT_CURRENCY_SYMBOLS = ("$", "€", "£", "¥", "₹", "₩", "₽", "₺", "₪")

# Letters with no Unicode decomposition and the ASCII text that replaces
# them when diacritics are removed.
PREBUILT_DIACRITIC_FALLBACKS: MappingProxyType[str, str] = MappingProxyType(
    {
        "ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L", "ß": "ss", "æ": "ae",
        "Æ": "AE", "œ": "oe", "Œ": "OE", "þ": "th", "Þ": "Th", "ð": "d", "Ð": "D", "ı": "i",
    }
)

# English number words: ONES is indexed by value (0 to 19), TENS by
# the tens digit (2 to 9), and SCALES by the power of one thousand
# (1 to 11).
PREBUILT_NUMBER_WORDS_ONES = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
)
PREBUILT_NUMBER_WORDS_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
PREBUILT_NUMBER_WORDS_SCALES = (
    "", "thousand", "million", "billion", "trillion", "quadrillion", "quintillion",
    "sextillion", "septillion", "octillion", "nonillion", "decillion",
)

# Cardinal words whose ordinal is irregular; every other ordinal adds
# "th", and a word ending in "y" ends in "ieth" instead.
PREBUILT_ORDINAL_WORDS: MappingProxyType[str, str] = MappingProxyType(
    {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth", "twelve": "twelfth"}
)

# Magnitude suffixes of abbreviated numbers, matched without regard to
# case, and the multiplier each one stands for.
PREBUILT_ABBREVIATED_NUMBER_SUFFIXES: MappingProxyType[str, int] = MappingProxyType(
    {
        "k": 1_000, "thousand": 1_000,
        "m": 1_000_000, "mm": 1_000_000, "mn": 1_000_000, "million": 1_000_000,
        "b": 1_000_000_000, "bn": 1_000_000_000, "billion": 1_000_000_000,
        "t": 1_000_000_000_000, "tn": 1_000_000_000_000, "trillion": 1_000_000_000_000,
    }
)

# Data size unit words, matched without regard to case, and the exact
# number of bytes in one unit as Fraction text.
PREBUILT_DATA_SIZE_SUFFIXES: MappingProxyType[str, str] = MappingProxyType(
    {
        "b": "1", "byte": "1", "bytes": "1",
        "k": "1000", "kb": "1000", "kilobyte": "1000", "kib": "1024",
        "m": "1000000", "mb": "1000000", "mib": "1048576",
        "g": "1000000000", "gb": "1000000000", "gib": "1073741824",
        "t": "1000000000000", "tb": "1000000000000", "tib": "1099511627776",
        "p": "1000000000000000", "pb": "1000000000000000", "pib": "1125899906842624",
        "bit": "1/8", "bits": "1/8",
        "kbit": "125", "kilobit": "125",
        "mbit": "125000", "megabit": "125000",
        "gbit": "125000000", "gigabit": "125000000",
    }
)

# The character each CsvDelimiter member stands for, in reading and
# in writing CSV.
PREBUILT_CSV_DELIMITER_CHARACTERS: MappingProxyType[CsvDelimiter, str] = MappingProxyType(
    {CsvDelimiter.COMMA: ",", CsvDelimiter.SEMICOLON: ";", CsvDelimiter.TAB: "\t", CsvDelimiter.PIPE: "|"}
)

# The JsonType of each Python type json.loads returns, looked up by
# exact type, so a boolean is never read as a number.
PREBUILT_JSON_TYPES: MappingProxyType[type, JsonType] = MappingProxyType(
    {
        dict: JsonType.OBJECT,
        list: JsonType.ARRAY,
        str: JsonType.STRING,
        bool: JsonType.BOOLEAN,
        int: JsonType.NUMBER,
        float: JsonType.NUMBER,
        type(None): JsonType.NULL,
    }
)

# Display labels of byte sizes, from bytes up, one power of the base
# (1000 for si, 1024 for iec) apart.
PREBUILT_SIZE_UNIT_LABELS: MappingProxyType[SizeStandard, tuple[str, ...]] = MappingProxyType(
    {
        SizeStandard.SI: ("B", "kB", "MB", "GB", "TB", "PB", "EB"),
        SizeStandard.IEC: ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB"),
    }
)

# Duration unit words, matched without regard to case, and the exact
# number of seconds in one unit as Decimal text.
PREBUILT_DURATION_UNIT_WORDS: MappingProxyType[str, str] = MappingProxyType(
    {
        "w": "604800", "wk": "604800", "wks": "604800", "week": "604800", "weeks": "604800",
        "d": "86400", "day": "86400", "days": "86400",
        "h": "3600", "hr": "3600", "hrs": "3600", "hour": "3600", "hours": "3600",
        "m": "60", "min": "60", "mins": "60", "minute": "60", "minutes": "60",
        "s": "1", "sec": "1", "secs": "1", "second": "1", "seconds": "1",
        "ms": "0.001", "millisecond": "0.001", "milliseconds": "0.001",
    }
)

# English month names, three-letter forms, and "sept", lowercase, with
# their month numbers.
PREBUILT_MONTH_NAMES: MappingProxyType[str, int] = MappingProxyType(
    {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
        "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    }
)

# HTML elements whose start and end tags become line breaks when tags
# are stripped.
PREBUILT_HTML_BLOCK_TAGS = frozenset(
    {
        "address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt", "figcaption", "figure",
        "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol",
        "p", "pre", "section", "table", "td", "th", "tr", "ul",
    }
)

PREBUILT_ZERO_WIDTH_CODE_POINTS = frozenset({0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF})
PREBUILT_BIDI_CONTROL_CODE_POINTS = frozenset(
    {0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069, 0x200E, 0x200F, 0x061C}
)

# Comment syntax per language: the line-comment prefixes, then the
# (opening, closing) pairs of block comments.
_C_STYLE_COMMENTS: tuple[tuple[str, ...], tuple[tuple[str, str], ...]] = (("//",), (("/*", "*/"),))
PREBUILT_COMMENT_SYNTAX: MappingProxyType[CodeLanguage, tuple[tuple[str, ...], tuple[tuple[str, str], ...]]] = MappingProxyType(
    {
        CodeLanguage.PYTHON: (("#",), ()),
        CodeLanguage.JAVASCRIPT: _C_STYLE_COMMENTS,
        CodeLanguage.TYPESCRIPT: _C_STYLE_COMMENTS,
        CodeLanguage.JAVA: _C_STYLE_COMMENTS,
        CodeLanguage.C: _C_STYLE_COMMENTS,
        CodeLanguage.CPP: _C_STYLE_COMMENTS,
        CodeLanguage.CSHARP: _C_STYLE_COMMENTS,
        CodeLanguage.GO: _C_STYLE_COMMENTS,
        CodeLanguage.RUST: _C_STYLE_COMMENTS,
        CodeLanguage.KOTLIN: _C_STYLE_COMMENTS,
        CodeLanguage.SWIFT: _C_STYLE_COMMENTS,
        CodeLanguage.PHP: (("//", "#"), (("/*", "*/"),)),
        CodeLanguage.RUBY: (("#",), (("=begin", "=end"),)),
        CodeLanguage.SHELL: (("#",), ()),
        CodeLanguage.SQL: (("--",), (("/*", "*/"),)),
        CodeLanguage.HTML: ((), (("<!--", "-->"),)),
        CodeLanguage.CSS: ((), (("/*", "*/"),)),
    }
)

__all__ = [
    "PREBUILT_ABBREVIATED_NUMBER_SUFFIXES",
    "PREBUILT_APPROXIMATION_DIGITS",
    "PREBUILT_BIDI_CONTROL_CODE_POINTS",
    "PREBUILT_COMMENT_SYNTAX",
    "PREBUILT_CSV_DELIMITER_CHARACTERS",
    "PREBUILT_CURRENCY_CODES",
    "PREBUILT_CURRENCY_SYMBOLS",
    "PREBUILT_DATA_SIZE_SUFFIXES",
    "PREBUILT_DECIMAL_TEXT_PATTERN",
    "PREBUILT_DEFAULT_DIVISION_PLACES",
    "PREBUILT_DIACRITIC_FALLBACKS",
    "PREBUILT_DURATION_UNIT_WORDS",
    "PREBUILT_EARTH_RADIUS_KILOMETERS",
    "PREBUILT_FINANCE_PRECISION",
    "PREBUILT_GSM7_BASIC_CHARACTERS",
    "PREBUILT_GSM7_EXTENSION_CHARACTERS",
    "PREBUILT_HEX_PREVIEW_SIZE",
    "PREBUILT_HTML_BLOCK_TAGS",
    "PREBUILT_INTEGER_TEXT_PATTERN",
    "PREBUILT_IRR_BISECTION_STEPS",
    "PREBUILT_IRR_GRID_POINTS",
    "PREBUILT_IRR_GRID_START",
    "PREBUILT_IRR_GRID_STEP",
    "PREBUILT_IRR_TOLERANCE",
    "PREBUILT_JSON_TYPES",
    "PREBUILT_MAX_BIRTHDAY_ITEMS",
    "PREBUILT_MAX_BIRTHDAY_VALUES",
    "PREBUILT_MAX_BIT_WIDTH",
    "PREBUILT_MAX_BUCKETS",
    "PREBUILT_MAX_BUSINESS_DAYS",
    "PREBUILT_MAX_CASH_FLOWS",
    "PREBUILT_MAX_CHARACTER_MATCHES",
    "PREBUILT_MAX_COMBINATION_ITEMS",
    "PREBUILT_MAX_COMBINATORIC_N",
    "PREBUILT_MAX_CONTEXT_LINES",
    "PREBUILT_MAX_DATA_SIZE_BYTES",
    "PREBUILT_MAX_DATE_OFFSET",
    "PREBUILT_MAX_DATE_SPAN_DAYS",
    "PREBUILT_MAX_DECIMAL_PLACES",
    "PREBUILT_MAX_DECIMAL_TEXT_CHARS",
    "PREBUILT_MAX_DENOMINATOR",
    "PREBUILT_MAX_DICE",
    "PREBUILT_MAX_DICE_MODIFIER",
    "PREBUILT_MAX_DIE_SIDES",
    "PREBUILT_MAX_DIFF_LINES",
    "PREBUILT_MAX_DIFF_TOKENS",
    "PREBUILT_MAX_DURATION_SECONDS",
    "PREBUILT_MAX_ENCODED_TEXT_CHARS",
    "PREBUILT_MAX_EXPRESSION_CHARS",
    "PREBUILT_MAX_FACTORIZE_VALUE",
    "PREBUILT_MAX_FINANCE_YEARS",
    "PREBUILT_MAX_FRACTION_TEXT_CHARS",
    "PREBUILT_MAX_FREE_SLOT_MINUTES",
    "PREBUILT_MAX_FUZZY_CANDIDATES",
    "PREBUILT_MAX_FUZZY_CANDIDATE_CHARS",
    "PREBUILT_MAX_GRAPH_EDGES",
    "PREBUILT_MAX_HOLIDAYS",
    "PREBUILT_MAX_INDENT",
    "PREBUILT_MAX_INTEGER_DIGITS",
    "PREBUILT_MAX_INTEGER_RANGE_SPAN",
    "PREBUILT_MAX_INTEGER_TEXT_CHARS",
    "PREBUILT_MAX_JSON_NESTING",
    "PREBUILT_MAX_JSON_SCAN_STARTS",
    "PREBUILT_MAX_KEY_CHARS",
    "PREBUILT_MAX_LISTS",
    "PREBUILT_MAX_LIST_ITEMS",
    "PREBUILT_MAX_LOAN_MONTHS",
    "PREBUILT_MAX_MEDIUM_TEXT_CHARS",
    "PREBUILT_MAX_MODULAR_TEXT_CHARS",
    "PREBUILT_MAX_MOJIBAKE_ROUNDS",
    "PREBUILT_MAX_MONEY_AMOUNT",
    "PREBUILT_MAX_MOVING_AVERAGE_WINDOW",
    "PREBUILT_MAX_NAME_CHARS",
    "PREBUILT_MAX_NGRAM_SIZE",
    "PREBUILT_MAX_NTH_PRIME",
    "PREBUILT_MAX_NUMBER_WORD_DIGITS",
    "PREBUILT_MAX_OUTLIER_MULTIPLIER",
    "PREBUILT_MAX_PAIRWISE_CHARS",
    "PREBUILT_MAX_PATCH_OPERATIONS",
    "PREBUILT_MAX_PATCH_WORK_CHARS",
    "PREBUILT_MAX_PATTERN_CHARS",
    "PREBUILT_MAX_PHRASE_CHARS",
    "PREBUILT_MAX_POISSON_OCCURRENCES",
    "PREBUILT_MAX_POISSON_RATE",
    "PREBUILT_MAX_PRIMALITY_VALUE",
    "PREBUILT_MAX_RANDOM_MAGNITUDE",
    "PREBUILT_MAX_RANDOM_PICKS",
    "PREBUILT_MAX_RATE_PERCENT",
    "PREBUILT_MAX_RECORDS",
    "PREBUILT_MAX_RECURRENCE_STEP",
    "PREBUILT_MAX_REGEX_SAMPLES",
    "PREBUILT_MAX_REGEX_TEXT_CHARS",
    "PREBUILT_MAX_REPORTED_NAMES",
    "PREBUILT_MAX_RESULT_ITEMS",
    "PREBUILT_MAX_SCHEDULE_TASKS",
    "PREBUILT_MAX_SEARCH_STRING_CHARS",
    "PREBUILT_MAX_SEED",
    "PREBUILT_MAX_SEQUENCE_MATCH_CHARS",
    "PREBUILT_MAX_SHARE_PLACES",
    "PREBUILT_MAX_SHORT_TEXT_CHARS",
    "PREBUILT_MAX_SIEVE_VALUE",
    "PREBUILT_MAX_SIGNIFICANT_FIGURES",
    "PREBUILT_MAX_SIZE_DECIMAL_PLACES",
    "PREBUILT_MAX_SNIFF_CHARS",
    "PREBUILT_MAX_SOURCE_CHARS",
    "PREBUILT_MAX_TABLE_COLUMNS",
    "PREBUILT_MAX_TEXT_CHARS",
    "PREBUILT_MAX_TOP_ITEMS",
    "PREBUILT_MAX_UTC_OFFSET_CHARS",
    "PREBUILT_MAX_XML_PATH_VISITS",
    "PREBUILT_MIN_CHUNK_CHARS",
    "PREBUILT_MONTH_NAMES",
    "PREBUILT_NUMBER_WORDS_ONES",
    "PREBUILT_NUMBER_WORDS_SCALES",
    "PREBUILT_NUMBER_WORDS_TENS",
    "PREBUILT_ORDINAL_WORDS",
    "PREBUILT_PROFILE_EXAMPLES",
    "PREBUILT_SENTENCE_ABBREVIATIONS",
    "PREBUILT_SIZE_UNIT_LABELS",
    "PREBUILT_UTC_OFFSET_PATTERN",
    "PREBUILT_ZERO_WIDTH_CODE_POINTS",
]
