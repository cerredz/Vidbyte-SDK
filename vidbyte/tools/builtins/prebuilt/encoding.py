"""FILE: vidbyte/tools/builtins/prebuilt/encoding.py

PURPOSE: Defines EncodingToolFunctions, the ten prebuilt tools that encode and decode text: Base64 and hexadecimal in both directions, URL percent-encoding in both directions, HTML entity decoding, JSON Web Token inspection without verification, and JSON string escaping in both directions.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the ENCODING category is chosen. Builds on PrebuiltToolSupport in _support.py for strict text encoding, JSON parsing with the nesting cap, and the argument error.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Text becomes bytes only through PrebuiltToolSupport.encode_text, and decoded bytes become text only when they decode strictly, so no tool ever invents a replacement character the row does not ask for.
FUNCTION INVENTORY: base64_encode, base64_decode, hex_encode, hex_decode, url_encode, url_decode, html_unescape, decode_jwt_payload, escape_json_string, and unescape_json_string are the tools; _base64_bytes reads tolerant Base64, _decoded_text reads bytes strictly as text, _jwt_object decodes one JSON Web Token part, and _claim_time turns a numeric claim into a UTC datetime; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new encoding tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.21, and its entry in tool_functions. A new codec is a new TextEncoding member, and every tool here picks it up through encode_text and _decoded_text.
WHAT NOT TO DO IN THIS FILE: 1. Do not encode text with str.encode directly; PrebuiltToolSupport.encode_text names the first character a codec cannot represent. 2. Do not decode bytes with a replacing error handler except in url_decode, whose row asks for U+FFFD. 3. Do not report a JSON Web Token signature as verified; this library holds no keys. 4. Do not echo the input in an error message.
KNOWN EDGE CASES: The utf_16 and utf_32 codecs write a byte-order mark even for empty text, so their round trips hold bytes even when the text is empty. Python reads a JSON number with an overlong exponent as infinity and refuses integers longer than 4,300 digits, so a JSON Web Token part holding either fails as a bad part. A JSON Web Token time claim outside the datetime range, or one that is not a number, is null rather than an error.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.21, section 9.2 items 2, 3, 5, 11, and 13); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_formats_encoding.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import base64
import binascii
import html
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import MappingProxyType
from typing import Annotated
from urllib.parse import quote, quote_plus, unquote

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_FINANCE_PRECISION,
    PREBUILT_HEX_PREVIEW_SIZE,
    PREBUILT_MAX_ENCODED_TEXT_CHARS,
    PREBUILT_MAX_MEDIUM_TEXT_CHARS,
    PREBUILT_MAX_TEXT_CHARS,
)
from vidbyte.lib.enums.prebuilt_tools import HexSeparator, TextEncoding, UrlEncodingMode
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_BASE64_GROUP = 4
_URL_SAFE_ALTCHARS = b"-_"
_STANDARD_BASE64 = re.compile(r"[A-Za-z0-9+/]*")
_URL_SAFE_BASE64 = re.compile(r"[A-Za-z0-9_-]*")
_URL_SAFE_MARKS = re.compile(r"[-_]")
_STANDARD_MARKS = re.compile(r"[+/]")
_HEX_IGNORED = re.compile(r"[\s:]+")
_HEX_PREFIX = re.compile(r"\A0[xX]")
_HEX_DIGITS = re.compile(r"[0-9A-Fa-f]*")
_HEX_SEPARATORS = MappingProxyType({HexSeparator.NONE: "", HexSeparator.SPACE: " ", HexSeparator.COLON: ":"})
_DANGLING_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")
_BEARER_PREFIX = re.compile(r"\Abearer\s+", re.IGNORECASE)
_JWT_SEGMENT = re.compile(r"[A-Za-z0-9_-]*={0,2}")
_SIGNED_JWT_PARTS = 3
_ENCRYPTED_JWT_PARTS = 5
_JWT_TIME_CLAIMS = MappingProxyType({"issued_at": "iat", "expires_at": "exp", "not_before": "nbf"})
_JWT_EXPECTED = "a compact JSON Web Token of three dot-separated parts whose header and payload are Base64url-encoded JSON objects"
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MICROSECONDS_PER_SECOND = 1_000_000
_MAX_CLAIM_SECONDS = Decimal(10**12)

_ENCODE_TEXT_DESCRIPTION = "The text to encode, given as plain characters. It is first turned into bytes with text_encoding, and those bytes are what get encoded. Empty text gives an empty result unless the encoding writes a byte-order mark. The text may hold at most one million characters."
_ENCODE_ENCODING_DESCRIPTION = "The character encoding that turns the text into bytes before the bytes are encoded. Encoding is strict, so a character the codec cannot represent fails with an error naming its position. The utf_16 and utf_32 codecs start the bytes with a byte-order mark, while their _le and _be variants do not. The default is utf_8."
_DECODE_ENCODING_DESCRIPTION = "The character encoding used to read the decoded bytes back as text. The bytes count as text only when they decode strictly in this encoding, with no replacement characters. The utf_16 and utf_32 codecs read and drop a leading byte-order mark. The default is utf_8, and the choice never changes the decoded bytes themselves."
_URL_TEXT_DESCRIPTION = "The text to percent-encode, given as plain characters. Every character outside the unreserved set is written as percent escapes of its UTF-8 bytes. Empty text gives an empty result. The text may hold at most one hundred thousand characters."
_URL_ENCODED_DESCRIPTION = "The percent-encoded text to decode. An escape is a percent sign followed by two hexadecimal digits in either case. Characters that are not part of an escape are kept as they are. The text may hold at most one hundred thousand characters."


class EncodingToolFunctions:
    """The encoding category: Base64, hexadecimal, URL, HTML, JSON Web Token, and JSON string encodings."""

    @staticmethod
    def base64_encode(
        text: Annotated[str, Field(description=_ENCODE_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        text_encoding: Annotated[TextEncoding, Field(description=_ENCODE_ENCODING_DESCRIPTION)] = TextEncoding.UTF_8,
        url_safe: Annotated[bool, Field(description="Whether to use the URL-safe alphabet, which writes minus and underscore in place of plus and slash. URL-safe output can go into a URL or a file name without further escaping. The default is false, which gives the standard alphabet. Both alphabets encode the same bytes.")] = False,
        padding: Annotated[bool, Field(description="Whether to keep the trailing equals signs that pad the output to a multiple of four characters. When false they are removed, as JSON Web Tokens and many URL formats expect. The default is true. The base64_decode tool accepts the output either way.")] = True,
    ) -> PrebuiltToolOutput:
        """Encode a text as Base64 in the standard or the URL-safe alphabet and return the encoded text. Use it to put text into a data URL, an HTTP header, a JSON field, or any other place that needs plain ASCII. The text is first turned into bytes with text_encoding, and padding can be dropped for formats that omit the trailing equals signs. A character the encoding cannot represent fails with an error naming text and the position of that character."""
        raw = PrebuiltToolSupport.encode_text(text, text_encoding, "text")
        encoded = (base64.urlsafe_b64encode(raw) if url_safe else base64.b64encode(raw)).decode("ascii")
        return {"base64": encoded if padding else encoded.rstrip("=")}

    @staticmethod
    def base64_decode(
        data: Annotated[str, Field(description="The Base64 text to decode, in the standard or the URL-safe alphabet. Spaces and line breaks anywhere in it are ignored, and the trailing equals signs may be left out. Characters outside the chosen alphabet make the call fail. The text may hold at most two million characters.", max_length=PREBUILT_MAX_ENCODED_TEXT_CHARS)],
        url_safe: Annotated[bool | None, Field(description="Which Base64 alphabet the data uses: true for URL-safe, false for standard, or null to detect it. Detection picks the URL-safe alphabet when the data holds a minus sign or an underscore. Data that holds characters of the other alphabet fails with an error. The default is null.")] = None,
        text_encoding: Annotated[TextEncoding, Field(description=_DECODE_ENCODING_DESCRIPTION)] = TextEncoding.UTF_8,
    ) -> PrebuiltToolOutput:
        """Decode Base64 text into bytes and return them as text when they decode strictly in text_encoding, with the byte count and a lowercase hexadecimal preview of the first 64 bytes. Use it to read an encoded payload, an attachment, or an opaque field whose contents are unknown. Whitespace is ignored, missing padding is tolerated, and the alphabet is detected from the characters unless url_safe is set. Invalid Base64, or a mix of characters from both alphabets, fails with an error naming data."""
        raw = EncodingToolFunctions._base64_bytes(data, url_safe)
        decoded = EncodingToolFunctions._decoded_text(raw, text_encoding)
        return {"text": decoded, "is_text": decoded is not None, "size_bytes": len(raw), "hex_preview": raw[:PREBUILT_HEX_PREVIEW_SIZE].hex()}

    @staticmethod
    def hex_encode(
        text: Annotated[str, Field(description=_ENCODE_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        text_encoding: Annotated[TextEncoding, Field(description=_ENCODE_ENCODING_DESCRIPTION)] = TextEncoding.UTF_8,
        separator: Annotated[HexSeparator, Field(description="What to put between the two-digit groups of the bytes. The value none writes the digits with nothing between them, space puts one space between bytes, and colon puts one colon between bytes. No separator is written before the first byte or after the last. The default is none.")] = HexSeparator.NONE,
        uppercase: Annotated[bool, Field(description="Whether to write the hexadecimal digits a to f in uppercase. The default is false, which gives lowercase digits. The separator and the byte order do not change. Both forms decode to the same bytes.")] = False,
    ) -> PrebuiltToolOutput:
        """Encode a text as hexadecimal, two digits per byte, with an optional separator between bytes. Use it to inspect the exact bytes of a text, to compare encodings, or to prepare a hexadecimal literal. The text is first turned into bytes with text_encoding, and the digits are lowercase unless uppercase is true. A character the encoding cannot represent fails with an error naming text and the position of that character."""
        raw = PrebuiltToolSupport.encode_text(text, text_encoding, "text")
        separator_text = _HEX_SEPARATORS[separator]
        digits = raw.hex(separator_text) if separator_text else raw.hex()
        return {"hex": digits.upper() if uppercase else digits}

    @staticmethod
    def hex_decode(
        hex_text: Annotated[str, Field(description="The hexadecimal text to decode, two digits per byte. Spaces, line breaks, colons, and one leading 0x prefix are ignored. Any other character that is not a hexadecimal digit makes the call fail. The text may hold at most two million characters.", max_length=PREBUILT_MAX_ENCODED_TEXT_CHARS)],
        text_encoding: Annotated[TextEncoding, Field(description=_DECODE_ENCODING_DESCRIPTION)] = TextEncoding.UTF_8,
    ) -> PrebuiltToolOutput:
        """Decode hexadecimal text into bytes and return them as text when they decode strictly in text_encoding, with the byte count. Use it to read a hex dump, a hexadecimal literal, or a hex-encoded field. Whitespace, colons, and one leading 0x prefix are ignored, and digits may be uppercase or lowercase. A character that is not a hexadecimal digit, or an odd number of digits, fails with an error naming hex_text."""
        # Drop the separators and one prefix, leaving only the digits.
        digits = _HEX_PREFIX.sub("", _HEX_IGNORED.sub("", hex_text), count=1)
        expected = "pairs of hexadecimal digits, optionally separated by whitespace or colons"
        if _HEX_DIGITS.fullmatch(digits) is None:
            raise PrebuiltToolSupport.argument_error("hex_text", "the text holds a character that is not a hexadecimal digit", expected)
        if len(digits) % 2:
            raise PrebuiltToolSupport.argument_error("hex_text", f"the text holds an odd number of digits ({len(digits)})", expected)

        # Turn the digits into bytes and read them as text when they
        # decode strictly.
        raw = bytes.fromhex(digits)
        decoded = EncodingToolFunctions._decoded_text(raw, text_encoding)
        return {"text": decoded, "is_text": decoded is not None, "size_bytes": len(raw)}

    @staticmethod
    def url_encode(
        text: Annotated[str, Field(description=_URL_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_MEDIUM_TEXT_CHARS)],
        mode: Annotated[UrlEncodingMode, Field(description="Which percent-encoding rules to apply. The value component encodes every reserved character including slashes, path keeps slashes so a whole path stays readable, and form also writes spaces as plus signs. Every mode encodes the text as UTF-8 first. The default is component.")] = UrlEncodingMode.COMPONENT,
    ) -> PrebuiltToolOutput:
        """Percent-encode a text as UTF-8 so it can be placed in a URL component, a URL path, or a form body. Use it before putting free text into a query value, a path segment, or a form-encoded request body. Letters, digits, and the four characters minus, period, underscore, and tilde are never encoded, the path mode also keeps slashes, and the form mode writes spaces as plus signs. Text that passes the schema always encodes, so the tool has no failure case beyond the text length cap."""
        raw = PrebuiltToolSupport.encode_text(text, TextEncoding.UTF_8, "text")
        match mode:
            case UrlEncodingMode.PATH:
                encoded = quote(raw, safe="/")
            case UrlEncodingMode.FORM:
                encoded = quote_plus(raw, safe="")
            case _:
                encoded = quote(raw, safe="")
        return {"encoded": encoded}

    @staticmethod
    def url_decode(
        text: Annotated[str, Field(description=_URL_ENCODED_DESCRIPTION, max_length=PREBUILT_MAX_MEDIUM_TEXT_CHARS)],
        mode: Annotated[UrlEncodingMode, Field(description="Which percent-decoding rules to apply. The values component and path decode every escape the same way, while form also turns plus signs into spaces. Escapes are always read as UTF-8 bytes. The default is component.")] = UrlEncodingMode.COMPONENT,
    ) -> PrebuiltToolOutput:
        """Decode percent-encoded URL text back into plain text, reading the escaped bytes as UTF-8. Use it to read a query value, a path segment, or a form body that holds escapes. The form mode also turns plus signs into spaces, bytes that are not valid UTF-8 become the replacement character U+FFFD, and a percent sign not followed by two hexadecimal digits is kept as it is. The had_invalid_sequences flag reports either problem, and the tool has no failure case beyond the text length cap."""
        # Form bodies write spaces as plus signs; the other modes keep
        # a plus sign as it is.
        plain = text.replace("+", " ") if mode is UrlEncodingMode.FORM else text

        # Decode the escapes twice: replacing bad bytes gives the
        # output, and escaping them instead differs only when a byte
        # was bad.
        decoded = unquote(plain, errors="replace")
        invalid_bytes = decoded != unquote(plain, errors="surrogateescape")
        dangling = _DANGLING_PERCENT.search(plain) is not None
        return {"decoded": decoded, "had_invalid_sequences": invalid_bytes or dangling}

    @staticmethod
    def html_unescape(text: Annotated[str, Field(description="The text whose character references are decoded, given as plain characters. Named, decimal, and hexadecimal references are all recognized. Tags are left in place and are not removed. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Decode the HTML character references and named entities in a text and return the plain text. Use it to read text copied from HTML source, a feed, or an API that returns escaped markup. It follows the HTML5 rules of the Python standard library, decodes each reference once, and leaves text that is not a valid reference as it is. The tool has no failure case beyond the text length cap."""
        return {"unescaped": html.unescape(text)}

    @staticmethod
    def decode_jwt_payload(jwt_text: Annotated[str, Field(description="The JSON Web Token to decode, in its compact form of three Base64url parts joined by periods. Surrounding whitespace and a leading Bearer prefix are removed. The third part, the signature, may be empty for an unsigned token. The text must hold at least one character and at most one hundred thousand.", min_length=1, max_length=PREBUILT_MAX_MEDIUM_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Decode the header and claims of a JSON Web Token without verifying its signature, and report its issued-at, expiry, and not-before times as UTC datetimes. Use it to inspect the algorithm, subject, audience, or expiry of a token while debugging, never to decide whether to trust it. The signature_verified flag is always false, expiry is not checked, and surrounding whitespace and a Bearer prefix are removed first. A token without exactly three dot-separated parts, an encrypted five-part token, or a header or payload that is not a Base64url-encoded JSON object fails with an error naming jwt_text."""
        # Remove surrounding whitespace and the authorization scheme
        # word that often comes copied with the token.
        compact = _BEARER_PREFIX.sub("", jwt_text.strip(), count=1)

        # Split the token into header, payload, and signature; an
        # encrypted token has five parts and its claims are unreadable.
        parts = compact.split(".")
        if len(parts) == _ENCRYPTED_JWT_PARTS:
            raise PrebuiltToolSupport.argument_error("jwt_text", "the token has five parts, so it is encrypted and its claims cannot be read without a key", _JWT_EXPECTED)
        if len(parts) != _SIGNED_JWT_PARTS:
            raise PrebuiltToolSupport.argument_error("jwt_text", f"the token has {len(parts)} dot-separated parts", _JWT_EXPECTED)

        # Decode the header and payload, then read the numeric time
        # claims as UTC datetimes.
        header = EncodingToolFunctions._jwt_object(parts[0], "header")
        payload = EncodingToolFunctions._jwt_object(parts[1], "payload")
        claims = {label: EncodingToolFunctions._claim_time(payload.get(name)) for label, name in _JWT_TIME_CLAIMS.items()}
        return {"header": header, "payload": payload, "signature_verified": False, "has_signature": parts[2] != "", "claims": claims}

    @staticmethod
    def escape_json_string(
        text: Annotated[str, Field(description="The text to escape, given as plain characters. Quotes, backslashes, and control characters are replaced by their JSON escape sequences. Empty text gives an empty result. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)],
        ensure_ascii: Annotated[bool, Field(description="Whether to escape every character outside ASCII as a backslash-u sequence. Characters beyond the Basic Multilingual Plane become a surrogate pair of two sequences. The default is false, which keeps those characters as they are. Quotes, backslashes, and control characters are escaped either way.")] = False,
    ) -> PrebuiltToolOutput:
        """Escape a text so it can be placed between the double quotes of a JSON string literal, and return it without the surrounding quotes. Use it when writing JSON or JavaScript by hand and the text holds quotes, backslashes, line breaks, or other control characters. The escaping matches the Python standard library JSON encoder, and ensure_ascii also escapes every non-ASCII character as one or two backslash-u sequences. The tool has no failure case beyond the text length cap."""
        return {"escaped": json.dumps(text, ensure_ascii=ensure_ascii)[1:-1]}

    @staticmethod
    def unescape_json_string(escaped: Annotated[str, Field(description="The escaped JSON string content to decode, with or without its surrounding double quotes. It may use every JSON escape, including backslash-u sequences. Raw line breaks and other control characters are not allowed inside a JSON string. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Decode the escape sequences of a JSON string literal back into plain text. Use it to read a string copied out of JSON source or a log line, where line breaks, quotes, and Unicode characters appear as escapes. Surrounding double quotes are optional and are added when missing, and a surrogate pair of backslash-u sequences becomes one character. An invalid escape, an unescaped control character, or a stray quote fails with an error naming escaped and the position of the problem."""
        # Add the surrounding quotes when they are missing, remembering
        # the shift so error positions point into the original text.
        quoted = len(escaped) > 1 and escaped.startswith('"') and escaped.endswith('"')
        shift = 0 if quoted else 1
        literal = escaped if quoted else f'"{escaped}"'

        # Let the JSON decoder read the literal and report where it
        # stopped when the text is not a valid string.
        try:
            decoded = json.loads(literal)
        except json.JSONDecodeError as exc:
            position = max(exc.pos - shift, 0)
            raise PrebuiltToolSupport.argument_error("escaped", f"{exc.msg} at position {position}", "the content of one JSON string literal with valid escapes and no raw control characters") from exc
        return {"text": decoded}

    @staticmethod
    def _base64_bytes(data: str, url_safe: bool | None) -> bytes:
        """Decode Base64 with whitespace removed and padding optional, in the chosen or detected alphabet."""
        compact = "".join(data.split())
        core = compact.rstrip("=")
        expected = "Base64 text in one alphabet, with whitespace ignored and padding optional"
        detected = _URL_SAFE_MARKS.search(core) is not None
        if detected and _STANDARD_MARKS.search(core) is not None:
            raise PrebuiltToolSupport.argument_error("data", "the text mixes characters of the standard and the URL-safe Base64 alphabets", expected)
        chosen = detected if url_safe is None else url_safe
        alphabet_name = "URL-safe" if chosen else "standard"
        if (_URL_SAFE_BASE64 if chosen else _STANDARD_BASE64).fullmatch(core) is None:
            raise PrebuiltToolSupport.argument_error("data", f"the text holds a character outside the {alphabet_name} Base64 alphabet", expected)
        missing = -len(core) % _BASE64_GROUP
        if len(core) % _BASE64_GROUP == 1 or len(compact) - len(core) > missing:
            raise PrebuiltToolSupport.argument_error("data", f"the text has {len(core)} Base64 digits with a padding of {len(compact) - len(core)}, which no Base64 text can have", expected)
        try:
            return base64.b64decode(core + "=" * missing, altchars=_URL_SAFE_ALTCHARS if chosen else None, validate=True)
        except binascii.Error as exc:
            raise PrebuiltToolSupport.argument_error("data", f"the text is not valid {alphabet_name} Base64", expected) from exc

    @staticmethod
    def _decoded_text(raw: bytes, text_encoding: TextEncoding) -> str | None:
        """Read bytes as text in the chosen encoding, or return None when they do not decode strictly."""
        try:
            return raw.decode(text_encoding.value.replace("_", "-"))
        except UnicodeDecodeError:
            return None

    @staticmethod
    def _jwt_object(segment: str, part_name: str) -> dict[str, object]:
        """Decode one Base64url JSON Web Token part into the JSON object it must hold."""
        if _JWT_SEGMENT.fullmatch(segment) is None:
            raise PrebuiltToolSupport.argument_error("jwt_text", f"the {part_name} is not Base64url text", _JWT_EXPECTED)
        core = segment.rstrip("=")
        try:
            raw = base64.urlsafe_b64decode(core + "=" * (-len(core) % _BASE64_GROUP))
            value = PrebuiltToolSupport.parse_json_text(raw.decode("utf-8"), "jwt_text")
            # Python reads a number with an overlong exponent as
            # infinity, which would break the finite JSON output rule.
            json.dumps(value, allow_nan=False)
        except (binascii.Error, UnicodeError, ValueError) as exc:
            raise PrebuiltToolSupport.argument_error("jwt_text", f"the {part_name} is not Base64url-encoded UTF-8 JSON with finite numbers", _JWT_EXPECTED) from exc
        if not isinstance(value, dict):
            raise PrebuiltToolSupport.argument_error("jwt_text", f"the {part_name} is JSON but not an object", _JWT_EXPECTED)
        return value

    @staticmethod
    def _claim_time(value: object) -> str | None:
        """Turn a numeric seconds-since-epoch claim into a UTC ISO datetime, or None for anything else."""
        numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
        seconds = Decimal(repr(value)) if numeric else None
        if seconds is None or seconds.copy_abs() > _MAX_CLAIM_SECONDS:
            return None
        # Round once to whole microseconds from the number's own text,
        # so a fractional claim never picks up float error.
        with PrebuiltToolSupport.decimal_context(PREBUILT_FINANCE_PRECISION):
            microseconds = int((seconds * _MICROSECONDS_PER_SECOND).to_integral_value())
        try:
            return (_UNIX_EPOCH + timedelta(microseconds=microseconds)).isoformat()
        except OverflowError:
            return None

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.base64_encode,
            cls.base64_decode,
            cls.hex_encode,
            cls.hex_decode,
            cls.url_encode,
            cls.url_decode,
            cls.html_unescape,
            cls.decode_jwt_payload,
            cls.escape_json_string,
            cls.unescape_json_string,
        )


__all__ = ["EncodingToolFunctions"]
