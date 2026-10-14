"""FILE: vidbyte/tools/builtins/prebuilt/structured_formats.py

PURPOSE: Defines StructuredFormatsToolFunctions, the nine prebuilt tools that read structured text formats: XML to JSON, XML well-formedness, XML element search, INI, TOML, URL parts, relative URL resolution, query strings, and .env files.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the STRUCTURED_FORMATS category is chosen. Builds on PrebuiltToolSupport in _support.py for the argument error, nesting level, item cap, and line splitting.
ARCHITECTURE NOTE: Every parser is a standard-library one (xml.etree.ElementTree, configparser, tomllib, urllib.parse), and each tool wraps it with the guards INV-19 and INV-20 need: XML text is refused before parsing when it declares a document type, an entity, or a namespace URI longer than PREBUILT_MAX_NAME_CHARS, converted values are measured with work stacks instead of recursion, and xml_to_json counts its keys and texts while building. Parser exceptions are converted from their attributes, never from their text.
FUNCTION INVENTORY: xml_to_json, verify_xml_wellformed, xml_find_elements, ini_to_json, toml_to_json, parse_url, resolve_relative_url, parse_query_string, and parse_dotenv_text are the tools; _CaseKeepingConfigParser keeps INI key case; _unsafe_xml_problem names a refused declaration; _parse_xml parses XML or fails naming xml_text; _element_level measures element nesting; _element_value converts elements to JSON under the output cap; _ini_error_line reads a configparser error's line; _has_long_dotted_key finds a TOML key with too many dotted segments; _plain_toml_values turns TOML dates into text and checks numbers; _dotenv_value reads one .env value; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new format tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.20, and its entry in tool_functions, and catches its parser's exceptions where they occur. A new XML tool runs _unsafe_xml_problem before _parse_xml.
WHAT NOT TO DO IN THIS FILE: 1. Do not let any XML parser see text before _unsafe_xml_problem has accepted it. 2. Do not format a parser exception with str or repr; read code, position, lineno, or errors, and give tomllib errors the fixed message. 3. Do not walk a converted value with recursion; the nesting cap must hold before anything reaches the output serializer. 4. Do not repeat a .env line in an error, because it may hold a credential.
KNOWN EDGE CASES: Expat reports 0-based columns, so a reported column is one more than the parser's. The ElementPath engine of Python 3.11 raises TypeError, SyntaxError, or KeyError for a bad path, and all three are errors on path. tomllib accepts infinite and NaN floats and integers of any size, which are refused here because the output must be finite JSON. tomllib takes time quadratic in the segments of one dotted key, so a run of more than 100 dotted key segments is refused before parsing; the scan does not track strings or comments, so such a run inside a multi-line string or a comment is refused too.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.20, section 9.2 items 3, 12, and 13, INV-19, INV-20); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_formats_encoding.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import configparser
import json
import math
import re
import tomllib
from datetime import date, time
from types import MappingProxyType
from typing import Annotated, Any
from urllib.parse import parse_qsl, urljoin, urlsplit
from xml.etree import ElementTree
from xml.parsers import expat

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_MAX_INTEGER_DIGITS,
    PREBUILT_MAX_JSON_NESTING,
    PREBUILT_MAX_LIST_ITEMS,
    PREBUILT_MAX_MEDIUM_TEXT_CHARS,
    PREBUILT_MAX_NAME_CHARS,
    PREBUILT_MAX_PATTERN_CHARS,
    PREBUILT_MAX_SHORT_TEXT_CHARS,
    PREBUILT_MAX_TEXT_CHARS,
)
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_XML_DECLARATIONS = ("<!DOCTYPE", "<!ENTITY")
_LONG_NAMESPACE_DECLARATION = re.compile(rf"""(?<=\s)xmlns(?::[^\s=>/]*)?\s*=\s*(?:"[^"]{{{PREBUILT_MAX_NAME_CHARS + 1}}}|'[^']{{{PREBUILT_MAX_NAME_CHARS + 1}}})""")
_DECLARATION_REFUSAL = "the text holds a document type or entity declaration, which is refused before parsing"
_NAMESPACE_REFUSAL = f"the text declares a namespace URI longer than {PREBUILT_MAX_NAME_CHARS} characters, which is refused before parsing"
_XML_EXPECTED = f"a well-formed XML document without DOCTYPE or ENTITY declarations and with namespace URIs of at most {PREBUILT_MAX_NAME_CHARS} characters"
_INI_HIDDEN_DEFAULT_SECTION = "\n"
_INI_DEFAULT_HEADER = "DEFAULT"
_INI_EXPECTED = "INI text with a section header first, no repeated section, no repeated key in a section, and no continuation of a key without a value"
_TOML_PROBLEM = "the text is not valid TOML 1.0"
_TOML_NESTING_PROBLEM = f"the TOML is nested deeper than {PREBUILT_MAX_JSON_NESTING} levels"
_TOML_NESTING_EXPECTED = "TOML nested at most that deep"
_TOML_KEY_SEGMENT = r"""[A-Za-z0-9_-]++|"(?:[^"\\\n]|\\.)*+"|'[^'\n]*+'"""
_TOML_DOTTED_RUN = re.compile(rf"(?:{_TOML_KEY_SEGMENT})(?:[ \t]*+\.[ \t]*+(?:{_TOML_KEY_SEGMENT}))*+")
_TOML_SEGMENT = re.compile(_TOML_KEY_SEGMENT)
_INTEGER_RESULT_BOUND = 10**PREBUILT_MAX_INTEGER_DIGITS
_DOTENV_ASSIGNMENT = re.compile(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_.-]*)\s*=(.*)")
_DOTENV_SINGLE_QUOTED = re.compile(r"'([^']*)'\s*(?:#.*)?")
_DOTENV_DOUBLE_QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"\s*(?:#.*)?')
_DOTENV_PIECES = re.compile(r"\\.|[^\\]+")
_DOTENV_ESCAPES = MappingProxyType({"\\n": "\n", "\\t": "\t", '\\"': '"', "\\\\": "\\"})
_DOTENV_COMMENT = re.compile(r"\s#")

_XML_TEXT_DESCRIPTION = "The XML document to read, given as text. A document type declaration, an entity declaration, or a namespace URI longer than 200 characters is refused before parsing. Comments and processing instructions are ignored. The text may hold at most one million characters."


class StructuredFormatsToolFunctions:
    """The structured_formats category: reading XML, INI, TOML, URLs, query strings, and .env files."""

    class _CaseKeepingConfigParser(configparser.ConfigParser):
        """A ConfigParser that keeps the case of keys, which the standard parser lowercases."""

        def optionxform(self, optionstr: str) -> str:
            """Return the key exactly as written."""
            return optionstr

    @staticmethod
    def xml_to_json(xml_text: Annotated[str, Field(description=_XML_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Convert an XML document into an equivalent JSON value and report the tag of its root element. Use it to read an XML feed, export, or configuration file with JSON tools. Attributes become keys starting with an at sign, non-blank text becomes a key named #text, repeated child tags become arrays, a text-only element becomes its string, and an empty element becomes null. Nesting deeper than 100 elements, a value longer than one million characters, a document type or entity declaration, a namespace URI longer than 200 characters, or malformed XML fails with an error naming xml_text."""
        # Refuse declarations and long namespace URIs before the parser
        # ever sees the text.
        problem = StructuredFormatsToolFunctions._unsafe_xml_problem(xml_text)
        if problem is not None:
            raise PrebuiltToolSupport.argument_error("xml_text", problem, _XML_EXPECTED)

        # Parse the document and refuse one nested too deep to return.
        root = StructuredFormatsToolFunctions._parse_xml(xml_text)
        # @intent prebuilt-xml-nesting-cap
        # A converted value as deep as the document would make the
        # output serializer recurse past its limit after the tool has
        # returned, where the failure can no longer become a result.
        if StructuredFormatsToolFunctions._element_level(root) > PREBUILT_MAX_JSON_NESTING:
            problem = f"the elements are nested deeper than {PREBUILT_MAX_JSON_NESTING} levels"
            raise PrebuiltToolSupport.argument_error("xml_text", problem, "XML nested at most that deep")

        # Convert the elements from the innermost outward.
        return {"root_tag": root.tag, "value": StructuredFormatsToolFunctions._element_value(root)}

    @staticmethod
    def verify_xml_wellformed(xml_text: Annotated[str, Field(description="The text to check as an XML document. A document type declaration, an entity declaration, or a namespace URI longer than 200 characters is reported as not well-formed without parsing. Every other text is parsed by the standard XML parser. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Check whether a text is a well-formed XML document and, if it is not, report the parser's error with its line and column. Use it to find where an XML file breaks before editing or converting it. A malformed document is a normal result with wellformed false, a 1-based line and column, and the parser's error text, and a well-formed one reports its root tag. A document type or entity declaration, or a namespace URI longer than 200 characters, is reported as not well-formed with a fixed error and no position."""
        # Report refused text with a fixed error and no position.
        problem = StructuredFormatsToolFunctions._unsafe_xml_problem(xml_text)
        if problem is not None:
            return {"wellformed": False, "error": problem, "line": None, "column": None, "root_tag": None}

        # Parse the text, turning the parser's 0-based column into a
        # 1-based one.
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError as exc:
            line, column = exc.position
            return {"wellformed": False, "error": expat.ErrorString(exc.code), "line": line, "column": column + 1, "root_tag": None}
        return {"wellformed": True, "error": None, "line": None, "column": None, "root_tag": root.tag}

    @staticmethod
    def xml_find_elements(
        xml_text: Annotated[str, Field(description=_XML_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        path: Annotated[str, Field(description="The ElementPath expression to evaluate, relative to the root element. It supports child and descendant steps, wildcards, parent steps, and predicates on attributes, child text, and position. An absolute path, an unbalanced bracket, or another unsupported form fails with an error. It must hold between 1 and 1,000 characters.", min_length=1, max_length=PREBUILT_MAX_PATTERN_CHARS)],
    ) -> PrebuiltToolOutput:
        """Find the XML elements that match an ElementPath expression and list the tag, attributes, and stripped text of each. Use it to pull specific records or values out of an XML document without converting all of it. Paths are relative to the root element, matches are listed in document order, and at most 1,000 elements are listed while count covers every match. An unsupported or absolute path fails with an error naming path, and malformed or refused XML fails with an error naming xml_text."""
        # Refuse unsafe text, then parse the document.
        problem = StructuredFormatsToolFunctions._unsafe_xml_problem(xml_text)
        if problem is not None:
            raise PrebuiltToolSupport.argument_error("xml_text", problem, _XML_EXPECTED)
        root = StructuredFormatsToolFunctions._parse_xml(xml_text)

        # Evaluate the path; the engine raises several exception types
        # for paths it cannot read, and every one is the path's fault.
        try:
            found = root.findall(path)
        except (SyntaxError, TypeError, KeyError, ValueError) as exc:
            raise PrebuiltToolSupport.argument_error("path", "the path is not an ElementPath expression this parser supports", "a relative ElementPath expression with balanced brackets") from exc

        # List the matches up to the item cap while count covers all.
        elements, truncated = PrebuiltToolSupport.cap_items({"tag": element.tag, "attributes": dict(element.attrib), "text": (element.text or "").strip() or None} for element in found)
        return {"elements": elements, "count": len(found), "truncated": truncated}

    @staticmethod
    def ini_to_json(ini_text: Annotated[str, Field(description="The INI text to parse, with section headers in square brackets and one key per line. Keys and values are separated by an equals sign or a colon, and lines starting with a hash or a semicolon are comments. Indented lines continue the previous value. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Parse INI or config-file text into its sections, each mapping keys to values, plus the keys written under a DEFAULT section. Use it to read a configuration file as structured data without guessing its layout. Key case is kept, no interpolation is applied, a key without a value is null, and DEFAULT keys are reported on their own instead of being copied into every section. A missing first section header, a repeated section, a repeated key, or another parse error fails with an error naming ini_text and the line."""
        # The parser's own default section gets a name no header can
        # produce, so DEFAULT is read as a plain section and its keys
        # are never copied into the others.
        parser = StructuredFormatsToolFunctions._CaseKeepingConfigParser(interpolation=None, strict=True, allow_no_value=True, default_section=_INI_HIDDEN_DEFAULT_SECTION)
        try:
            parser.read_string(ini_text)
        except configparser.Error as exc:
            line = StructuredFormatsToolFunctions._ini_error_line(exc)
            where = "" if line is None else f" at line {line}"
            raise PrebuiltToolSupport.argument_error("ini_text", f"the INI text could not be parsed{where}", _INI_EXPECTED) from exc
        except AttributeError as exc:
            # The standard parser fails this way when an indented line
            # continues a key that has no value.
            raise PrebuiltToolSupport.argument_error("ini_text", "an indented line continues a key that has no value", _INI_EXPECTED) from exc

        # Report DEFAULT on its own and every other section with only
        # its own keys.
        defaults = dict(parser.items(_INI_DEFAULT_HEADER, raw=True)) if parser.has_section(_INI_DEFAULT_HEADER) else {}
        sections = {name: dict(parser.items(name, raw=True)) for name in parser.sections() if name != _INI_DEFAULT_HEADER}
        return {"sections": sections, "defaults": defaults}

    @staticmethod
    def toml_to_json(toml_text: Annotated[str, Field(description="The TOML 1.0 text to parse. Tables, arrays of tables, inline tables, and every TOML value type are accepted. A key may not be defined twice. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Parse TOML text into the equivalent JSON object. Use it to read a TOML configuration or manifest file as structured data. Dates, times, and datetimes become ISO 8601 text, and tables and arrays keep their structure. Invalid TOML fails with a fixed message and no position, and nesting deeper than 100 levels, an infinite or NaN float, or an integer of more than 4,000 digits fails too, each with an error naming toml_text."""
        # @intent prebuilt-toml-dotted-key-cap
        # tomllib takes time quadratic in the segments of one dotted
        # key, and a key of more segments than the nesting cap always
        # nests too deep, so such a key is refused before parsing.
        if StructuredFormatsToolFunctions._has_long_dotted_key(toml_text):
            raise PrebuiltToolSupport.argument_error("toml_text", _TOML_NESTING_PROBLEM, _TOML_NESTING_EXPECTED)

        # Parse the text; the decoder's error has no position to report,
        # so every invalid document gets the same message.
        try:
            value = tomllib.loads(toml_text)
        except (tomllib.TOMLDecodeError, ValueError) as exc:
            raise PrebuiltToolSupport.argument_error("toml_text", _TOML_PROBLEM, "TOML 1.0 text") from exc
        except RecursionError as exc:
            raise PrebuiltToolSupport.argument_error("toml_text", _TOML_NESTING_PROBLEM, _TOML_NESTING_EXPECTED) from exc

        # @intent prebuilt-toml-nesting-cap
        # A value nested past the cap would make the output serializer
        # recurse too deep after the tool returns, where the failure can
        # no longer become a result.
        if PrebuiltToolSupport.nesting_level(value) > PREBUILT_MAX_JSON_NESTING:
            raise PrebuiltToolSupport.argument_error("toml_text", _TOML_NESTING_PROBLEM, _TOML_NESTING_EXPECTED)

        # Turn dates and times into text and check every number.
        StructuredFormatsToolFunctions._plain_toml_values(value)
        return {"value": value}

    @staticmethod
    def parse_url(url: Annotated[str, Field(description="The URL or relative reference to split. It may be absolute, relative, or use a scheme without a network location. Query parameters are decoded with plus signs read as spaces, and blank values are kept. It may hold at most 10,000 characters.", max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Split a URL into its scheme, user name, host, port, path, query, fragment, and decoded query parameters. Use it to inspect or check a link without guessing where its parts begin and end. The host is lowercased, a password is never echoed and only reported as present, and the URL is absolute when it has both a scheme and a network location. An invalid or out-of-range port, or an unbalanced IPv6 bracket, fails with an error naming url."""
        # Split the URL and read the port, which is where a malformed
        # network location shows up.
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError as exc:
            raise PrebuiltToolSupport.argument_error("url", "the URL has an invalid port or an unbalanced IPv6 bracket", "a URL whose port is a number from 0 to 65535 and whose brackets are balanced") from exc

        # Report the parts, never the password itself.
        return {
            "scheme": parts.scheme,
            "username": parts.username,
            "has_password": parts.password is not None,
            "host": parts.hostname,
            "port": port,
            "path": parts.path,
            "query": parts.query,
            "fragment": parts.fragment,
            "query_parameters": [{"name": name, "value": value} for name, value in parse_qsl(parts.query, keep_blank_values=True)],
            "is_absolute": bool(parts.scheme and parts.netloc),
        }

    @staticmethod
    def resolve_relative_url(
        base_url: Annotated[str, Field(description="The absolute URL the reference is resolved against, which must include a scheme. Its path and query decide how relative references resolve. A base without a scheme fails with an error. It may hold at most 10,000 characters.", max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)],
        reference: Annotated[str, Field(description="The link to resolve, which may be relative, network-path relative, or already absolute. A reference with a different scheme replaces the base entirely. An empty reference gives the base URL back unchanged. It may hold at most 10,000 characters.", max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)],
    ) -> PrebuiltToolOutput:
        """Resolve a relative link against a base URL the way a browser does, following the reference resolution rules of RFC 3986. Use it to turn a link found in a page into the absolute URL it points to. Dot segments are removed, and a reference that already has its own scheme is returned as it is. A base URL without a scheme fails with an error naming base_url, and an unbalanced IPv6 bracket fails naming the parameter that holds it."""
        # The base must split cleanly and carry a scheme.
        try:
            base_scheme = urlsplit(base_url).scheme
        except ValueError as exc:
            raise PrebuiltToolSupport.argument_error("base_url", "the base URL has an unbalanced IPv6 bracket", "an absolute URL with balanced brackets") from exc
        if not base_scheme:
            raise PrebuiltToolSupport.argument_error("base_url", "the base URL has no scheme", "an absolute URL that starts with a scheme")

        # Resolve the reference; with a valid base, any split failure
        # comes from the reference.
        try:
            return {"url": urljoin(base_url, reference)}
        except ValueError as exc:
            raise PrebuiltToolSupport.argument_error("reference", "the reference has an unbalanced IPv6 bracket", "a URL reference with balanced brackets") from exc

    @staticmethod
    def parse_query_string(query: Annotated[str, Field(description="The query string to parse, with or without a leading question mark. Fields are separated by ampersands, and a field without an equals sign has an empty value. Invalid percent escapes are kept as written. It may hold at most 100,000 characters and 10,000 fields.", max_length=PREBUILT_MAX_MEDIUM_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Parse a URL query string into its parameters, both in order and grouped by name. Use it to read the parameters of a link or a form body without decoding them by hand. A leading question mark is removed, plus signs become spaces, percent escapes are decoded, and blank values are kept. More than 10,000 fields fail with an error naming query."""
        # Decode the fields, refusing more than the field cap.
        text = query[1:] if query.startswith("?") else query
        try:
            pairs = parse_qsl(text, keep_blank_values=True, max_num_fields=PREBUILT_MAX_LIST_ITEMS)
        except ValueError as exc:
            raise PrebuiltToolSupport.argument_error("query", f"the query has more than {PREBUILT_MAX_LIST_ITEMS} fields", f"a query of at most {PREBUILT_MAX_LIST_ITEMS} fields") from exc

        # Keep the fields in order and also group their values by name.
        by_name: dict[str, list[str]] = {}
        for name, value in pairs:
            by_name.setdefault(name, []).append(value)
        return {"parameters": [{"name": name, "value": value} for name, value in pairs], "by_name": by_name}

    @staticmethod
    def parse_dotenv_text(dotenv_text: Annotated[str, Field(description="The .env text to parse, one KEY=value assignment per line. A key starts with a letter or an underscore and may continue with letters, digits, underscores, dots, and hyphens. Values cannot span lines, and no variable is ever expanded. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Parse the text of a .env file into its variables without expanding or exporting anything. Use it to read settings from an environment file safely, because no value is substituted or run. Blank lines and hash comments are skipped, an export prefix is allowed, unquoted values are trimmed and lose a trailing comment, single-quoted values are literal, and double-quoted values decode a few backslash escapes. The last value of a repeated key wins and the key is listed as a duplicate, and an invalid line fails with an error that names only its line number."""
        variables: dict[str, str] = {}
        repeated: set[str] = set()
        for number, line in enumerate(PrebuiltToolSupport.split_lines(dotenv_text), start=1):
            # Skip blank and comment lines, then read one assignment;
            # an invalid line is reported by number only, because it
            # may hold a credential.
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            assignment = _DOTENV_ASSIGNMENT.fullmatch(stripped)
            value = StructuredFormatsToolFunctions._dotenv_value(assignment.group(2)) if assignment else None
            if assignment is None or value is None:
                raise PrebuiltToolSupport.argument_error("dotenv_text", f"line {number} is not a valid KEY=value assignment", "lines that are blank, comments, or assignments whose key starts with a letter or an underscore")

            # The last value wins, and a repeated key is remembered.
            if assignment.group(1) in variables:
                repeated.add(assignment.group(1))
            variables[assignment.group(1)] = value
        return {"variables": variables, "count": len(variables), "duplicate_keys": [key for key in variables if key in repeated]}

    @staticmethod
    def _unsafe_xml_problem(text: str) -> str | None:
        """Name the reason XML text is refused before parsing, or return None when it may be parsed."""
        # @intent prebuilt-xml-declaration-refusal
        # A document type declaration can define entities that expand
        # without bound, so DOCTYPE and ENTITY text never reaches the
        # parser, wherever it appears in the text.
        if any(marker in text for marker in _XML_DECLARATIONS):
            return _DECLARATION_REFUSAL
        # @intent prebuilt-xml-namespace-uri-cap
        # The parser copies a namespace URI into every name that uses
        # it, so a long URI multiplies the parsed size; the pattern only
        # looks a fixed distance past each quote, so it stays linear.
        if _LONG_NAMESPACE_DECLARATION.search(text) is not None:
            return _NAMESPACE_REFUSAL
        return None

    @staticmethod
    def _parse_xml(text: str) -> ElementTree.Element:
        """Parse accepted XML text, failing with the parser's error text, line, and 1-based column."""
        try:
            return ElementTree.fromstring(text)
        except ElementTree.ParseError as exc:
            line, column = exc.position
            problem = f"the XML is not well-formed at line {line}, column {column + 1}: {expat.ErrorString(exc.code)}"
            raise PrebuiltToolSupport.argument_error("xml_text", problem, _XML_EXPECTED) from exc

    @staticmethod
    def _element_level(root: ElementTree.Element) -> int:
        """Measure element nesting with a work stack: 1 for a root without children."""
        deepest = 0
        pending = [(root, 1)]
        while pending:
            element, level = pending.pop()
            deepest = max(deepest, level)
            pending.extend((child, level + 1) for child in element)
        return deepest

    @staticmethod
    def _element_value(root: ElementTree.Element) -> object:
        """Convert an element tree to JSON from the innermost elements outward, under the output cap."""
        values: dict[ElementTree.Element, object] = {}
        size = 0
        for element in reversed(list(root.iter())):
            # Attributes and non-blank text, the text between children
            # included, become keys of the element's object.
            children = list(element)
            text = "".join([element.text or "", *(child.tail or "" for child in children)])
            entry: dict[str, object] = {f"@{name}": value for name, value in element.attrib.items()}
            if text.strip():
                entry["#text"] = text
            # @intent prebuilt-xml-output-cap
            # A long tag or namespace repeated on many elements can make
            # the value far longer than the document, so the keys and
            # texts are counted as they are built.
            size += sum(len(json.dumps(piece, ensure_ascii=False)) for piece in (element.tag, *entry, *entry.values()))
            if size > PREBUILT_MAX_TEXT_CHARS:
                problem = f"the JSON value would pass {PREBUILT_MAX_TEXT_CHARS} characters"
                raise PrebuiltToolSupport.argument_error("xml_text", problem, "XML whose converted value fits in that many characters")
            # Children join under their tag, and a repeated tag becomes
            # an array in document order.
            grouped: dict[str, list[object]] = {}
            for child in children:
                grouped.setdefault(child.tag, []).append(values.pop(child))
            entry.update((tag, items[0] if len(items) == 1 else items) for tag, items in grouped.items())
            values[element] = entry if element.attrib or grouped else entry.get("#text")
        return values[root]

    @staticmethod
    def _ini_error_line(error: configparser.Error) -> int | None:
        """Read the line a configparser error reports, from its lineno or its first recorded error."""
        line = getattr(error, "lineno", None)
        if isinstance(line, int):
            return line
        recorded = getattr(error, "errors", None)
        if recorded:
            return int(recorded[0][0])
        return None

    @staticmethod
    def _has_long_dotted_key(toml_text: str) -> bool:
        """Say whether a run of key segments joined by dots has more segments than the nesting cap, scanning the text once."""
        # Only a run with enough dots can be too long, so the exact
        # count, which skips dots inside quoted segments, is rare.
        for run in _TOML_DOTTED_RUN.finditer(toml_text):
            if run.group().count(".") >= PREBUILT_MAX_JSON_NESTING and len(_TOML_SEGMENT.findall(run.group())) > PREBUILT_MAX_JSON_NESTING:
                return True
        return False

    @staticmethod
    def _plain_toml_values(document: dict[str, Any]) -> None:
        """Replace TOML dates and times with ISO 8601 text in place, refusing non-finite floats and huge integers."""
        pending: list[Any] = [document]
        while pending:
            container = pending.pop()
            keys = list(container) if isinstance(container, dict) else range(len(container))
            for key in keys:
                item = container[key]
                if isinstance(item, (dict, list)):
                    pending.append(item)
                elif isinstance(item, (date, time)):
                    container[key] = item.isoformat()
                elif isinstance(item, float) and not math.isfinite(item):
                    raise PrebuiltToolSupport.argument_error("toml_text", "the TOML holds an infinite or NaN float", "TOML whose floats are all finite")
                # @intent prebuilt-toml-integer-digit-cap
                # tomllib reads hexadecimal integers of any size, and
                # Python cannot write one of more than 4,300 digits as
                # text, so the output serializer would fail.
                elif isinstance(item, int) and abs(item) >= _INTEGER_RESULT_BOUND:
                    problem = f"the TOML holds an integer of more than {PREBUILT_MAX_INTEGER_DIGITS} digits"
                    raise PrebuiltToolSupport.argument_error("toml_text", problem, f"TOML whose integers have at most {PREBUILT_MAX_INTEGER_DIGITS} digits")

    @staticmethod
    def _dotenv_value(raw: str) -> str | None:
        """Read the value part of one .env assignment, or return None when its quoting is invalid."""
        text = raw.strip()
        if text.startswith("'"):
            single = _DOTENV_SINGLE_QUOTED.fullmatch(text)
            return single.group(1) if single else None
        if text.startswith('"'):
            double = _DOTENV_DOUBLE_QUOTED.fullmatch(text)
            if double is None:
                return None
            return "".join(_DOTENV_ESCAPES.get(piece, piece) for piece in _DOTENV_PIECES.findall(double.group(1)))
        comment = _DOTENV_COMMENT.search(raw)
        return (raw if comment is None else raw[: comment.start()]).strip()

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.xml_to_json,
            cls.verify_xml_wellformed,
            cls.xml_find_elements,
            cls.ini_to_json,
            cls.toml_to_json,
            cls.parse_url,
            cls.resolve_relative_url,
            cls.parse_query_string,
            cls.parse_dotenv_text,
        )


__all__ = ["StructuredFormatsToolFunctions"]
