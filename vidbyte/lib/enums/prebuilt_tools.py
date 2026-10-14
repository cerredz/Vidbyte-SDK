"""FILE: vidbyte/lib/enums/prebuilt_tools.py

PURPOSE: Defines PrebuiltToolCategory, the 31 categories of the prebuilt tool library, and the 57 other closed vocabularies that the prebuilt tools take as parameters or report in their outputs.
ROLE IN CODEBASE: Imported by vidbyte/tools/toolsets/prebuilt.py (PrebuiltTools picks categories with PrebuiltToolCategory), by every category module in vidbyte/tools/builtins/prebuilt/, and by vidbyte/lib/constants/prebuilt_tools.py (PREBUILT_COMMENT_SYNTAX and PREBUILT_SIZE_UNIT_LABELS are keyed by enum). Re-exported from vidbyte/lib/enums/__init__.py.
ARCHITECTURE NOTE: Every enum is a str Enum whose values are the exact strings the model sends and reads, so a pydantic schema built from a tool signature lists them as its enum choices. The declaration order of each enum is part of the contract: PrebuiltToolCategory fixes catalogue order, and the problem enums fix their check order.
FUNCTION INVENTORY: PrebuiltToolCategory.values() returns the category values in declaration order. Every other class is a plain member list.
COMMON MODIFICATION PATTERNS: A new category adds its member here at its catalogue position, a category module in vidbyte/tools/builtins/prebuilt/, and one entry in the PrebuiltTools dispatch table. A new vocabulary adds a class here and its name to vidbyte/lib/enums/__init__.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not reorder members; tests and catalogue order depend on declaration order. 2. Do not add behavior beyond values(). 3. Do not import anything above vidbyte.lib.
KNOWN EDGE CASES: CompassPoint member names equal their uppercase values; every other member name is its value in upper case. BitwiseOperation values include the Python keywords and, or, and not, which are fine as member values because the member names are AND, OR, and NOT.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (section 9.2 enum table); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/ (test_prebuilt_toolset_contract.py checks every value and member name)
"""

from __future__ import annotations

from enum import Enum


class PrebuiltToolCategory(str, Enum):
    """The 31 categories of the prebuilt tool library, in catalogue order."""

    EXACT_ARITHMETIC = "exact_arithmetic"
    NUMBER_THEORY = "number_theory"
    NUMBER_FORMATTING = "number_formatting"
    DESCRIPTIVE_STATISTICS = "descriptive_statistics"
    PROBABILITY = "probability"
    SEEDED_RANDOM = "seeded_random"
    FINANCE = "finance"
    UNIT_CONVERSION = "unit_conversion"
    DATES = "dates"
    SCHEDULING = "scheduling"
    TIMESTAMPS_DURATIONS = "timestamps_durations"
    TEXT_COUNTING = "text_counting"
    TEXT_TRANSFORM = "text_transform"
    UNICODE = "unicode"
    REGEX = "regex"
    TEXT_COMPARISON = "text_comparison"
    JSON_DATA = "json_data"
    JSON_RECORDS = "json_records"
    CSV_TABLES = "csv_tables"
    STRUCTURED_FORMATS = "structured_formats"
    ENCODING = "encoding"
    HASHING = "hashing"
    IDENTIFIERS = "identifiers"
    LISTS = "lists"
    GRAPHS = "graphs"
    GEOMETRY = "geometry"
    BITS_BYTES = "bits_bytes"
    MARKDOWN_HTML = "markdown_html"
    TEXT_EXTRACTION = "text_extraction"
    CODE_ANALYSIS = "code_analysis"
    NETWORK_ADDRESSES = "network_addresses"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Return the member values in declaration order."""
        return tuple(member.value for member in cls)


class ArithmeticOperation(str, Enum):
    """The four exact arithmetic operations on two decimals or two fractions."""

    ADD = "add"
    SUBTRACT = "subtract"
    MULTIPLY = "multiply"
    DIVIDE = "divide"


class RoundingMode(str, Enum):
    """How an exact decimal is rounded to a fixed number of places or figures."""

    HALF_EVEN = "half_even"
    HALF_UP = "half_up"
    HALF_DOWN = "half_down"
    UP = "up"
    DOWN = "down"
    CEILING = "ceiling"
    FLOOR = "floor"


class SeparatorStyle(str, Enum):
    """The group and decimal separator pair used to write or read a formatted number."""

    COMMA_PERIOD = "comma_period"
    PERIOD_COMMA = "period_comma"
    SPACE_PERIOD = "space_period"
    SPACE_COMMA = "space_comma"
    APOSTROPHE_PERIOD = "apostrophe_period"
    UNDERSCORE_PERIOD = "underscore_period"


class NotationStyle(str, Enum):
    """Whether a number is written in scientific or engineering notation."""

    SCIENTIFIC = "scientific"
    ENGINEERING = "engineering"


class PercentileMethod(str, Enum):
    """How a percentile is read between two ranked values."""

    LINEAR = "linear"
    LOWER = "lower"
    HIGHER = "higher"
    NEAREST_RANK = "nearest_rank"


class QuartileMethod(str, Enum):
    """Whether quartiles use the exclusive or the inclusive method."""

    EXCLUSIVE = "exclusive"
    INCLUSIVE = "inclusive"


class RankMethod(str, Enum):
    """How tied values share ranks."""

    AVERAGE = "average"
    MIN = "min"
    MAX = "max"
    DENSE = "dense"
    ORDINAL = "ordinal"


class ProbabilityTail(str, Enum):
    """Which outcomes a discrete probability covers relative to k."""

    EXACTLY = "exactly"
    AT_MOST = "at_most"
    AT_LEAST = "at_least"
    LESS_THAN = "less_than"
    GREATER_THAN = "greater_than"


class CompoundingFrequency(str, Enum):
    """How often interest is added to the balance."""

    ANNUALLY = "annually"
    SEMIANNUALLY = "semiannually"
    QUARTERLY = "quarterly"
    MONTHLY = "monthly"
    WEEKLY = "weekly"
    DAILY = "daily"
    CONTINUOUSLY = "continuously"


class DateUnit(str, Enum):
    """The calendar unit an offset is added in."""

    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"
    YEARS = "years"


class Weekday(str, Enum):
    """The seven days of the week, Monday first."""

    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class WeekdayOccurrence(str, Enum):
    """Which occurrence of a weekday inside a month is meant."""

    FIRST = "first"
    SECOND = "second"
    THIRD = "third"
    FOURTH = "fourth"
    FIFTH = "fifth"
    LAST = "last"


class SearchDirection(str, Enum):
    """Whether a search moves forward or backward."""

    NEXT = "next"
    PREVIOUS = "previous"


class RecurrenceFrequency(str, Enum):
    """The step of a recurring date series."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class TimestampUnit(str, Enum):
    """The unit a Unix timestamp counts in."""

    SECONDS = "seconds"
    MILLISECONDS = "milliseconds"
    MICROSECONDS = "microseconds"
    NANOSECONDS = "nanoseconds"


class DurationStyle(str, Enum):
    """How a number of seconds is written as a duration."""

    COMPACT = "compact"
    LONG = "long"
    CLOCK = "clock"
    ISO8601 = "iso8601"


class TextUnit(str, Enum):
    """The unit a text is reversed or shortened by."""

    CHARACTERS = "characters"
    WORDS = "words"
    LINES = "lines"


class NgramUnit(str, Enum):
    """Whether n-grams are built from words or from characters."""

    WORDS = "words"
    CHARACTERS = "characters"


class IdentifierCase(str, Enum):
    """The naming convention an identifier is rewritten into."""

    SNAKE = "snake"
    SCREAMING_SNAKE = "screaming_snake"
    KEBAB = "kebab"
    CAMEL = "camel"
    PASCAL = "pascal"
    DOT = "dot"
    TITLE = "title"


class SortMode(str, Enum):
    """How lines or cells are compared when sorting."""

    TEXT = "text"
    CASE_INSENSITIVE = "case_insensitive"
    NATURAL = "natural"
    NUMERIC = "numeric"
    LENGTH = "length"


class MissingPlaceholderPolicy(str, Enum):
    """What a template does with a placeholder that has no value."""

    ERROR = "error"
    KEEP = "keep"
    EMPTY = "empty"


class UnicodeForm(str, Enum):
    """The Unicode normalization forms."""

    NFC = "nfc"
    NFD = "nfd"
    NFKC = "nfkc"
    NFKD = "nfkd"


class InvisibleCharacterKind(str, Enum):
    """The kinds of invisible or unusual characters a text scan reports."""

    ZERO_WIDTH = "zero_width"
    BIDI_CONTROL = "bidi_control"
    FORMAT = "format"
    UNUSUAL_SPACE = "unusual_space"
    CONTROL = "control"


class TextEncoding(str, Enum):
    """The text codecs the encoding, hashing, and unicode tools accept."""

    UTF_8 = "utf_8"
    UTF_16 = "utf_16"
    UTF_16_LE = "utf_16_le"
    UTF_16_BE = "utf_16_be"
    UTF_32 = "utf_32"
    LATIN_1 = "latin_1"
    ASCII = "ascii"
    CP1252 = "cp1252"


class SmsEncoding(str, Enum):
    """The encoding an SMS message must use."""

    GSM_7 = "gsm_7"
    UCS_2 = "ucs_2"


class RegexFlag(str, Enum):
    """The regular expression flags the regex tools accept."""

    IGNORE_CASE = "ignore_case"
    MULTILINE = "multiline"
    DOT_ALL = "dot_all"
    VERBOSE = "verbose"
    ASCII = "ascii"


class RegexMatchMode(str, Enum):
    """How much of the text a pattern must match."""

    FULL = "full"
    PREFIX = "prefix"
    SEARCH = "search"


class DiffOperation(str, Enum):
    """The kind of each step in a word diff."""

    EQUAL = "equal"
    INSERT = "insert"
    DELETE = "delete"
    REPLACE = "replace"


class JsonType(str, Enum):
    """The six JSON value types."""

    OBJECT = "object"
    ARRAY = "array"
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    NULL = "null"


class JsonChangeKind(str, Enum):
    """The kind of each change between two JSON documents."""

    ADD = "add"
    REMOVE = "remove"
    REPLACE = "replace"


class FilterOperator(str, Enum):
    """The comparison a record or row filter applies to one field."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    GREATER_OR_EQUAL = "greater_or_equal"
    LESS_THAN = "less_than"
    LESS_OR_EQUAL = "less_or_equal"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"


class AggregateFunction(str, Enum):
    """The summary computed over one field or column."""

    COUNT = "count"
    SUM = "sum"
    MEAN = "mean"
    MIN = "min"
    MAX = "max"
    MEDIAN = "median"
    DISTINCT_COUNT = "distinct_count"


class JoinKind(str, Enum):
    """Whether a join keeps only matches or every left row."""

    INNER = "inner"
    LEFT = "left"


class CsvDelimiter(str, Enum):
    """The field delimiters the CSV tools read and write."""

    COMMA = "comma"
    SEMICOLON = "semicolon"
    TAB = "tab"
    PIPE = "pipe"


class ColumnType(str, Enum):
    """The type a CSV column profile reports."""

    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    TEXT = "text"
    EMPTY = "empty"


class HexSeparator(str, Enum):
    """What separates the byte pairs of hexadecimal output."""

    NONE = "none"
    SPACE = "space"
    COLON = "colon"


class UrlEncodingMode(str, Enum):
    """Which percent-encoding rules a URL tool applies."""

    COMPONENT = "component"
    PATH = "path"
    FORM = "form"


class HashAlgorithm(str, Enum):
    """The digest algorithms the hashing tools accept."""

    MD5 = "md5"
    SHA1 = "sha1"
    SHA224 = "sha224"
    SHA256 = "sha256"
    SHA384 = "sha384"
    SHA512 = "sha512"
    SHA3_256 = "sha3_256"
    SHA3_512 = "sha3_512"
    BLAKE2B = "blake2b"
    BLAKE2S = "blake2s"


class DigestFormat(str, Enum):
    """How a digest is written: lowercase hex, padded base64, or unpadded base64url."""

    HEX = "hex"
    BASE64 = "base64"
    BASE64URL = "base64url"


class KeyFormat(str, Enum):
    """How an HMAC key is given."""

    TEXT = "text"
    HEX = "hex"
    BASE64 = "base64"


class UuidNameVersion(str, Enum):
    """The name-based UUID versions."""

    V3 = "v3"
    V5 = "v5"


class EmailSyntaxProblem(str, Enum):
    """The reasons an email address fails the syntax check."""

    NOT_ASCII = "not_ascii"
    MISSING_AT_SIGN = "missing_at_sign"
    MULTIPLE_AT_SIGNS = "multiple_at_signs"
    ADDRESS_TOO_LONG = "address_too_long"
    LOCAL_PART_EMPTY = "local_part_empty"
    LOCAL_PART_TOO_LONG = "local_part_too_long"
    LOCAL_PART_INVALID = "local_part_invalid"
    DOMAIN_TOO_LONG = "domain_too_long"
    DOMAIN_LABEL_INVALID = "domain_label_invalid"
    DOMAIN_NEEDS_TWO_LABELS = "domain_needs_two_labels"
    TOP_LEVEL_DOMAIN_INVALID = "top_level_domain_invalid"


class UrlSyntaxProblem(str, Enum):
    """The reasons a URL fails the syntax check, in check order."""

    WHITESPACE_OR_CONTROL = "whitespace_or_control"
    MISSING_SCHEME = "missing_scheme"
    SCHEME_NOT_ALLOWED = "scheme_not_allowed"
    MISSING_HOST = "missing_host"
    INVALID_PORT = "invalid_port"
    INVALID_HOST = "invalid_host"


class TableAlignment(str, Enum):
    """The alignment of a Markdown table column."""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    AUTO = "auto"


class MarkdownLinkKind(str, Enum):
    """The kinds of links found in Markdown."""

    INLINE = "inline"
    IMAGE = "image"
    AUTOLINK = "autolink"
    REFERENCE = "reference"


class CodeLanguage(str, Enum):
    """The source languages whose lines of code can be counted."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    C = "c"
    CPP = "cpp"
    CSHARP = "csharp"
    GO = "go"
    RUST = "rust"
    KOTLIN = "kotlin"
    SWIFT = "swift"
    PHP = "php"
    RUBY = "ruby"
    SHELL = "shell"
    SQL = "sql"
    HTML = "html"
    CSS = "css"


class PythonParameterKind(str, Enum):
    """The kinds of parameter a Python function signature can declare."""

    POSITIONAL_ONLY = "positional_only"
    POSITIONAL_OR_KEYWORD = "positional_or_keyword"
    VAR_POSITIONAL = "var_positional"
    KEYWORD_ONLY = "keyword_only"
    VAR_KEYWORD = "var_keyword"


class PythonNameUsageKind(str, Enum):
    """How a Python name is used at one place in the source."""

    DEFINITION = "definition"
    PARAMETER = "parameter"
    IMPORT = "import"
    LOAD = "load"
    STORE = "store"
    DELETE = "delete"
    ATTRIBUTE = "attribute"
    KEYWORD = "keyword"


class CompassPoint(str, Enum):
    """The 16 points of the compass rose."""

    N = "N"
    NNE = "NNE"
    NE = "NE"
    ENE = "ENE"
    E = "E"
    ESE = "ESE"
    SE = "SE"
    SSE = "SSE"
    S = "S"
    SSW = "SSW"
    SW = "SW"
    WSW = "WSW"
    W = "W"
    WNW = "WNW"
    NW = "NW"
    NNW = "NNW"


class CoordinateAxis(str, Enum):
    """Whether a coordinate is a latitude or a longitude."""

    LATITUDE = "latitude"
    LONGITUDE = "longitude"


class PolygonOrientation(str, Enum):
    """The winding direction of a polygon's vertices."""

    COUNTERCLOCKWISE = "counterclockwise"
    CLOCKWISE = "clockwise"
    DEGENERATE = "degenerate"


class SizeStandard(str, Enum):
    """Whether byte sizes use powers of 1000 or of 1024."""

    SI = "si"
    IEC = "iec"


class BitwiseOperation(str, Enum):
    """The bitwise operations on fixed-width integers."""

    AND = "and"
    OR = "or"
    XOR = "xor"
    NOT = "not"
    SHIFT_LEFT = "shift_left"
    SHIFT_RIGHT = "shift_right"


class BitStringFormat(str, Enum):
    """How a two's complement bit string is written."""

    BINARY = "binary"
    HEX = "hex"


class KeyValueSeparator(str, Enum):
    """Which separator splits a key from its value."""

    AUTO = "auto"
    COLON = "colon"
    EQUALS = "equals"


class IpVersion(str, Enum):
    """The two IP address versions."""

    IPV4 = "ipv4"
    IPV6 = "ipv6"


class IpAddressProblem(str, Enum):
    """The reasons an IP address fails the check, in check order."""

    INVALID_IPV6 = "invalid_ipv6"
    INVALID_CHARACTERS = "invalid_characters"
    IPV4_WRONG_PART_COUNT = "ipv4_wrong_part_count"
    IPV4_EMPTY_PART = "ipv4_empty_part"
    IPV4_LEADING_ZERO = "ipv4_leading_zero"
    IPV4_OCTET_OUT_OF_RANGE = "ipv4_octet_out_of_range"


__all__ = [
    "AggregateFunction",
    "ArithmeticOperation",
    "BitStringFormat",
    "BitwiseOperation",
    "CodeLanguage",
    "ColumnType",
    "CompassPoint",
    "CompoundingFrequency",
    "CoordinateAxis",
    "CsvDelimiter",
    "DateUnit",
    "DiffOperation",
    "DigestFormat",
    "DurationStyle",
    "EmailSyntaxProblem",
    "FilterOperator",
    "HashAlgorithm",
    "HexSeparator",
    "IdentifierCase",
    "InvisibleCharacterKind",
    "IpAddressProblem",
    "IpVersion",
    "JoinKind",
    "JsonChangeKind",
    "JsonType",
    "KeyFormat",
    "KeyValueSeparator",
    "MarkdownLinkKind",
    "MissingPlaceholderPolicy",
    "NgramUnit",
    "NotationStyle",
    "PercentileMethod",
    "PolygonOrientation",
    "PrebuiltToolCategory",
    "ProbabilityTail",
    "PythonNameUsageKind",
    "PythonParameterKind",
    "QuartileMethod",
    "RankMethod",
    "RecurrenceFrequency",
    "RegexFlag",
    "RegexMatchMode",
    "RoundingMode",
    "SearchDirection",
    "SeparatorStyle",
    "SizeStandard",
    "SmsEncoding",
    "SortMode",
    "TableAlignment",
    "TextEncoding",
    "TextUnit",
    "TimestampUnit",
    "UnicodeForm",
    "UrlEncodingMode",
    "UrlSyntaxProblem",
    "UuidNameVersion",
    "Weekday",
    "WeekdayOccurrence",
]
