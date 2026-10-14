"""FILE: vidbyte/tools/builtins/prebuilt/identifiers.py

PURPOSE: Defines IdentifiersToolFunctions, the nine prebuilt tools that check and build identifiers: Luhn numbers, ISBNs, IBANs, GTIN barcodes, email address syntax, URL syntax, UUIDs, name-based UUIDs, and Semantic Versioning precedence.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the IDENTIFIERS category is chosen. Builds on PrebuiltToolSupport in _support.py for the argument error.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Check-digit tools work on ASCII digits only, and the two syntax tools return a problem enum value in the fixed order their rows give instead of failing.
FUNCTION INVENTORY: verify_luhn_checksum, verify_isbn, verify_iban, verify_gtin_barcode, verify_email_syntax, verify_url_syntax, verify_uuid, generate_name_based_uuid, and compare_semantic_versions are the tools; _luhn_check_digit, _isbn10_check, _isbn13_check, and _gs1_check_digit compute check digits; _email_shape_problem and _email_part_problem hold the email checks; _split_authority, _host_shape_ok, and _url_problem hold the URL checks; _parse_uuid_text reads the accepted UUID forms; _semver_key builds a precedence key; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new identifier tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.23, and its entry in tool_functions. A new email or URL rule adds its enum member and one check at the place its row gives in the check order.
WHAT NOT TO DO IN THIS FILE: 1. Do not generate time-based or random UUIDs; every UUID here comes from a name or from the input. 2. Do not reorder the email or URL checks to follow the enum declaration order; the rows fix the check order. 3. Do not read digits with str.isdigit or a Unicode digit class, because both accept non-ASCII digits.
KNOWN EDGE CASES: The email check reports domain_too_long before address_too_long, so a 254-character domain names the domain. A URL host is reported even when it is invalid, and it is null only when there is no authority or the host is empty. A 979 ISBN-13 has no ISBN-10 form, and a valid ISBN-10 with check value 10 is written with an uppercase X.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.23, section 9.2 items 2, 4, and 13); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_identifiers_lists_graphs.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import ipaddress
import re
import unicodedata
import uuid
from types import MappingProxyType
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_MAX_EXPRESSION_CHARS,
    PREBUILT_MAX_LISTS,
    PREBUILT_MAX_NAME_CHARS,
    PREBUILT_MAX_PHRASE_CHARS,
    PREBUILT_MAX_SHORT_TEXT_CHARS,
)
from vidbyte.lib.enums.prebuilt_tools import (
    EmailSyntaxProblem,
    UrlSyntaxProblem,
    UuidNameVersion,
)
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_ASCII_DIGITS = re.compile(r"[0-9]*")
_ISBN10_TEXT = re.compile(r"[0-9]{9}[0-9X]")
_ISBN13_TEXT = re.compile(r"97[89][0-9]{10}")
_ISBN10_PREFIX = "978"
_ISBN10_CHECK_TEN = "X"
_ISBN10_MODULUS = 11
_ISBN10_LENGTH = 10
_ISBN13_LENGTH = 13
_IBAN_TEXT = re.compile(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}")
_IBAN_GROUP_SIZE = 4
_IBAN_MODULUS = 97
_IBAN_HEADER_SIZE = 4
_IBAN_LETTER_BASE = 55
_GTIN_LENGTHS = frozenset({8, 12, 13, 14})
_LUHN_MINIMUM_DIGITS = 2
_EMAIL_LOCAL_PART = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*")
_DOMAIN_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_LETTER_LABEL = re.compile(r"[A-Za-z]{2,}")
_PUNYCODE_PREFIX = "xn--"
_MAX_DOMAIN_LENGTH = 253
_MAX_ADDRESS_LENGTH = 254
_MAX_LOCAL_PART_LENGTH = 64
_URL_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*(?=:)")
_AUTHORITY_END = re.compile(r"[/?#]")
_PORT_TEXT = re.compile(r"[0-9]{1,5}")
_MAX_PORT = 65535
_UUID_HYPHENATED = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_UUID_COMPACT = re.compile(r"[0-9a-fA-F]{32}")
_UUID_URN_PREFIX = "urn:uuid:"
_STANDARD_NAMESPACES = MappingProxyType({"dns": uuid.NAMESPACE_DNS, "url": uuid.NAMESPACE_URL, "oid": uuid.NAMESPACE_OID, "x500": uuid.NAMESPACE_X500})
_SEMVER_IDENTIFIER = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
_SEMVER = re.compile(
    r"v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    + rf"(?:-({_SEMVER_IDENTIFIER}(?:\.{_SEMVER_IDENTIFIER})*))?"
    + r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)

_VERSION_PARAMETER_DESCRIPTION = "One version to compare, written as MAJOR.MINOR.PATCH with an optional pre-release part after a hyphen and optional build metadata after a plus sign. Numeric parts and numeric pre-release identifiers must not have leading zeros. One leading lowercase v is allowed. The text may hold at most 1,000 characters."

_SemverKey = tuple[tuple[tuple[int, str], ...], int, tuple[tuple[int, int, str], ...]]


class IdentifiersToolFunctions:
    """The identifiers category: check digits, address syntax, UUIDs, and version precedence."""

    @staticmethod
    def verify_luhn_checksum(
        number: Annotated[str, Field(description="The number to check, written as decimal digits. Spaces and hyphens between digit groups are ignored. The last digit is the check digit, and at least two digits are needed. The text may hold at most 200 characters.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
    ) -> PrebuiltToolOutput:
        """Check a number such as a payment card or IMEI number against the Luhn checksum and report the check digit its other digits call for. Use it to catch a mistyped card, account, or device number before relying on it. Spaces and hyphens are ignored, and digit_count counts the digits that remain. Any other character, or fewer than two digits, fails with an error naming number."""
        # Drop the separators, then insist on at least two ASCII digits.
        digits = number.replace(" ", "").replace("-", "")
        expected = "decimal digits, optionally grouped with spaces or hyphens, with at least two digits"
        if _ASCII_DIGITS.fullmatch(digits) is None:
            raise PrebuiltToolSupport.argument_error("number", "the text holds a character other than digits, spaces, and hyphens", expected)
        if len(digits) < _LUHN_MINIMUM_DIGITS:
            raise PrebuiltToolSupport.argument_error("number", f"the text holds {len(digits)} digits", expected)

        # Compute the check digit from every digit but the last.
        check_digit = IdentifiersToolFunctions._luhn_check_digit(digits[:-1])
        return {"valid": int(digits[-1]) == check_digit, "digit_count": len(digits), "expected_check_digit": check_digit}

    @staticmethod
    def verify_isbn(
        isbn: Annotated[str, Field(description="The ISBN to check, as ten or thirteen characters once separators are removed. Hyphens and spaces may separate the groups. Only the final character of an ISBN-10 may be the letter X, in either case. The text may hold at most 200 characters.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
    ) -> PrebuiltToolOutput:
        """Check whether a text is a valid ISBN-10 or ISBN-13 and give both forms of a valid number. Use it to confirm a book number or to convert between the ten-digit and thirteen-digit forms. Hyphens and spaces are ignored, a final X is allowed in an ISBN-10, and an ISBN-13 that starts with 979 has no ISBN-10 form. A wrong length, prefix, or check digit gives valid false with both forms null, and the tool never fails on content."""
        # Drop the separators; the remaining length decides the form.
        compact = isbn.replace("-", "").replace(" ", "")
        upper = compact.upper() if compact.isascii() else compact
        isbn10: str | None = None
        isbn13: str | None = None

        # A valid ISBN-10 always has a 978 ISBN-13, and a valid 978
        # ISBN-13 has an ISBN-10; a 979 ISBN-13 has none.
        if _ISBN10_TEXT.fullmatch(upper) and IdentifiersToolFunctions._isbn10_check(upper[:-1]) == upper[-1]:
            isbn10 = upper
            isbn13 = _ISBN10_PREFIX + upper[:-1] + IdentifiersToolFunctions._isbn13_check(_ISBN10_PREFIX + upper[:-1])
        elif _ISBN13_TEXT.fullmatch(upper) and IdentifiersToolFunctions._isbn13_check(upper[:-1]) == upper[-1]:
            isbn13 = upper
            isbn10 = upper[3:-1] + IdentifiersToolFunctions._isbn10_check(upper[3:-1]) if upper.startswith(_ISBN10_PREFIX) else None
        return {"valid": isbn13 is not None, "isbn10": isbn10, "isbn13": isbn13, "input_length": len(compact)}

    @staticmethod
    def verify_iban(
        iban: Annotated[str, Field(description="The IBAN to check, in printed groups or as one run of characters. Spaces are removed and letters are uppercased before checking. It must then be a two-letter country code, two check digits, and 11 to 30 letters or digits. The text may hold at most 200 characters.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
    ) -> PrebuiltToolOutput:
        """Check an International Bank Account Number for the right shape and valid mod-97 check digits. Use it to catch a mistyped IBAN before it is used in a payment or a record. Spaces are removed and letters uppercased, and the IBAN length of each country is not checked. Text without the IBAN shape gives valid false with null parts, and the tool never fails on content."""
        # Remove spaces and uppercase the letters, then match the shape.
        compact = iban.replace(" ", "")
        normalized = compact.upper() if compact.isascii() else compact
        if _IBAN_TEXT.fullmatch(normalized) is None:
            return {"valid": False, "country_code": None, "check_digits": None, "formatted": None}

        # Move the first four characters to the end, turn letters into
        # numbers from 10 to 35, and take the remainder modulo 97.
        rearranged = normalized[_IBAN_HEADER_SIZE:] + normalized[:_IBAN_HEADER_SIZE]
        numeric = "".join(str(ord(character) - _IBAN_LETTER_BASE) if character.isalpha() else character for character in rearranged)
        groups = [normalized[start : start + _IBAN_GROUP_SIZE] for start in range(0, len(normalized), _IBAN_GROUP_SIZE)]
        return {
            "valid": int(numeric) % _IBAN_MODULUS == 1,
            "country_code": normalized[:2],
            "check_digits": normalized[2:_IBAN_HEADER_SIZE],
            "formatted": " ".join(groups),
        }

    @staticmethod
    def verify_gtin_barcode(
        code: Annotated[str, Field(description="The barcode number to check, written as decimal digits. Spaces and hyphens between digit groups are ignored. The last digit is the check digit. The text may hold at most 200 characters.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
    ) -> PrebuiltToolOutput:
        """Check the check digit of a GTIN, EAN, or UPC barcode number and report the digit it should have. Use it to confirm a product code copied from a label, a catalogue, or a feed. Lengths 8, 12, 13, and 14 follow the GS1 mod-10 rule, while any other length gives valid false and a null expected digit. Spaces and hyphens are ignored, and any other character fails with an error naming code."""
        # Drop the separators and refuse anything but ASCII digits.
        digits = code.replace(" ", "").replace("-", "")
        if _ASCII_DIGITS.fullmatch(digits) is None:
            raise PrebuiltToolSupport.argument_error("code", "the text holds a character other than digits, spaces, and hyphens", "decimal digits, optionally grouped with spaces or hyphens")

        # Only the four GTIN lengths have a defined check digit.
        if len(digits) not in _GTIN_LENGTHS:
            return {"valid": False, "digit_count": len(digits), "expected_check_digit": None}
        check_digit = IdentifiersToolFunctions._gs1_check_digit(digits[:-1])
        return {"valid": int(digits[-1]) == check_digit, "digit_count": len(digits), "expected_check_digit": check_digit}

    @staticmethod
    def verify_email_syntax(
        email: Annotated[str, Field(description="The email address to check, as plain text with no display name or angle brackets. Surrounding spaces are not removed, so they make the address invalid. Only ASCII characters can pass. The text may hold at most 1,000 characters.", min_length=1, max_length=PREBUILT_MAX_EXPRESSION_CHARS)],
    ) -> PrebuiltToolOutput:
        """Check whether an email address is syntactically valid and, when it is not, report the first rule it breaks. Use it to screen addresses typed by people or found in documents, knowing that deliverability is never checked. The rules cover ASCII text, a single at sign, length caps, an RFC 5322 dot-atom local part without the quoted form, and a domain of valid labels with a proper top-level label. The local part and domain are reported whenever there is exactly one at sign, and the tool never fails on content."""
        # Split at the at sign only when there is exactly one.
        at_count = email.count("@")
        local_part, _, domain = email.partition("@") if at_count == 1 else (None, "", None)

        # Check the overall shape first, then the two parts, in the
        # order the row fixes.
        problem = IdentifiersToolFunctions._email_shape_problem(email, at_count, domain)
        if problem is None and local_part is not None and domain is not None:
            problem = IdentifiersToolFunctions._email_part_problem(local_part, domain)
        return {"valid": problem is None, "reason": None if problem is None else problem.value, "local_part": local_part, "domain": domain}

    @staticmethod
    def verify_url_syntax(
        url: Annotated[str, Field(description="The URL to check, as absolute text that starts with its scheme. Whitespace or control characters anywhere make it invalid. User information before an at sign is allowed and skipped. The text may hold at most 10,000 characters.", max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)],
        allowed_schemes: Annotated[tuple[Annotated[str, Field(min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)], ...], Field(description="The schemes the URL may use, compared without regard to case. A URL whose scheme is not in this list is reported as scheme_not_allowed. The default allows http and https only. The list must hold between 1 and 100 names.", min_length=1, max_length=PREBUILT_MAX_LISTS)] = ("http", "https"),
    ) -> PrebuiltToolOutput:
        """Check whether a URL is well formed and uses an allowed scheme, and report the first problem found. Use it to screen links before storing or showing them, knowing that nothing is ever fetched. The URL needs a scheme, a double-slash authority with a host, an optional port up to 65535, and a host that is a bracketed IPv6 address, an IPv4 address, or valid dot-separated labels. The lowercased scheme and host are reported whenever they can be read, and the tool never fails on content."""
        # Read the scheme, then the authority right after its colon.
        scheme_match = _URL_SCHEME.match(url)
        scheme = scheme_match.group().lower() if scheme_match else None
        authority: str | None = None
        if scheme_match is not None and url.startswith("//", scheme_match.end() + 1):
            authority = _AUTHORITY_END.split(url[scheme_match.end() + 3 :], maxsplit=1)[0]

        # Take the host and port out of the authority, then judge the
        # host.
        host, port_text, bracketed = IdentifiersToolFunctions._split_authority(authority) if authority is not None else (None, None, False)
        host_ok = IdentifiersToolFunctions._host_shape_ok(host, bracketed) if host else False

        # Apply the checks in row order and report the first failure.
        allowed = {name.casefold() for name in allowed_schemes}
        problem = IdentifiersToolFunctions._url_problem(url, scheme, allowed, host, port_text, host_ok)
        return {"valid": problem is None, "reason": None if problem is None else problem.value, "scheme": scheme, "host": host.lower() if host else None}

    @staticmethod
    def verify_uuid(
        value: Annotated[str, Field(description="The text to check as a UUID. Hex digits may be uppercase or lowercase. Braces or a urn:uuid: prefix around the value are allowed, but surrounding spaces are not. The text may hold at most 200 characters.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
    ) -> PrebuiltToolOutput:
        """Check whether a text is a UUID and report its canonical form, its version, and whether it uses the RFC 4122 variant. Use it to confirm an identifier copied from logs, links, or databases. The hyphenated form, braces, a urn:uuid: prefix, and 32 bare hex digits are accepted, and the canonical form is lowercase and hyphenated. The version is null unless the variant is RFC 4122, and text that is not a UUID gives valid false instead of an error."""
        parsed = IdentifiersToolFunctions._parse_uuid_text(value)
        if parsed is None:
            return {"valid": False, "canonical": None, "version": None, "is_rfc_4122": False}
        is_rfc_4122 = parsed.variant == uuid.RFC_4122
        return {"valid": True, "canonical": str(parsed), "version": parsed.version if is_rfc_4122 else None, "is_rfc_4122": is_rfc_4122}

    @staticmethod
    def generate_name_based_uuid(
        name: Annotated[str, Field(description="The name to turn into a UUID, encoded as UTF-8 before hashing. Any text is allowed, including an empty name. The same name and namespace always give the same UUID. The text may hold at most 10,000 characters.", max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)],
        namespace: Annotated[str, Field(description="The namespace of the name, either one of the standard names dns, url, oid, and x500 or any UUID. The four standard names are matched without regard to case. A UUID may be hyphenated, braced, prefixed with urn:uuid:, or written as 32 hex digits. Anything else fails with an error naming namespace.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
        version: Annotated[UuidNameVersion, Field(description="Which name-based UUID version to generate. The value v5 hashes with SHA-1 and is the usual choice. The value v3 hashes with MD5 for compatibility with older systems. The default is v5.")] = UuidNameVersion.V5,
    ) -> PrebuiltToolOutput:
        """Generate the deterministic name-based UUID, version 3 or version 5, for a namespace and a name. Use it when the same input must always give the same identifier, such as a stable key derived from a domain name or a link. Version 5 hashes with SHA-1 and version 3 with MD5 as RFC 4122 defines, so the result never depends on time or randomness. The namespace is one of the four standard names or any UUID, and anything else fails with an error naming namespace."""
        # Look the namespace up by name first, then read it as a UUID.
        namespace_uuid = _STANDARD_NAMESPACES.get(namespace.lower()) or IdentifiersToolFunctions._parse_uuid_text(namespace)
        if namespace_uuid is None:
            raise PrebuiltToolSupport.argument_error("namespace", "the text is neither a standard namespace name nor a UUID", "dns, url, oid, x500, or a UUID")

        # Hash the name in the chosen version; a lone surrogate cannot
        # be encoded as UTF-8, so it fails naming the name.
        try:
            generated = uuid.uuid3(namespace_uuid, name) if version is UuidNameVersion.V3 else uuid.uuid5(namespace_uuid, name)
        except UnicodeEncodeError as exc:
            raise PrebuiltToolSupport.argument_error("name", f"the character at position {exc.start} cannot be encoded as UTF-8", "text made of encodable Unicode characters") from exc
        return {"uuid": str(generated)}

    @staticmethod
    def compare_semantic_versions(
        first: Annotated[str, Field(description=_VERSION_PARAMETER_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_EXPRESSION_CHARS)],
        second: Annotated[str, Field(description=_VERSION_PARAMETER_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_EXPRESSION_CHARS)],
    ) -> PrebuiltToolOutput:
        """Compare two Semantic Versioning 2.0.0 versions and report which one has higher precedence, plus whether each is a pre-release. Use it to sort releases, check upgrade order, or decide whether a version meets a minimum. Precedence follows the SemVer 2.0.0 rules, build metadata is ignored, and one leading v is allowed on each version. The comparison is -1, 0, or 1, and an invalid version fails with an error naming its parameter."""
        first_key, first_is_prerelease = IdentifiersToolFunctions._semver_key(first, "first")
        second_key, second_is_prerelease = IdentifiersToolFunctions._semver_key(second, "second")
        comparison = (first_key > second_key) - (first_key < second_key)
        return {"comparison": comparison, "first_is_prerelease": first_is_prerelease, "second_is_prerelease": second_is_prerelease}

    @staticmethod
    def _luhn_check_digit(payload: str) -> int:
        """Return the Luhn check digit for the given digits, doubling every second digit from the right."""
        total = 0
        for position, digit_text in enumerate(reversed(payload)):
            digit = int(digit_text)
            if position % 2 == 0:
                digit = digit * 2 - 9 if digit > 4 else digit * 2
            total += digit
        return (10 - total % 10) % 10

    @staticmethod
    def _isbn10_check(payload: str) -> str:
        """Return the ISBN-10 check character for nine digits, writing a check value of 10 as X."""
        total = sum((_ISBN10_LENGTH - position) * int(digit) for position, digit in enumerate(payload))
        check = (_ISBN10_MODULUS - total % _ISBN10_MODULUS) % _ISBN10_MODULUS
        return _ISBN10_CHECK_TEN if check == _ISBN10_LENGTH else str(check)

    @staticmethod
    def _isbn13_check(payload: str) -> str:
        """Return the ISBN-13 check digit for twelve digits, weighting them 1 and 3 in turn."""
        total = sum(int(digit) * (3 if position % 2 else 1) for position, digit in enumerate(payload))
        return str((10 - total % 10) % 10)

    @staticmethod
    def _gs1_check_digit(payload: str) -> int:
        """Return the GS1 mod-10 check digit, weighting digits 3 and 1 in turn from the right."""
        total = sum(int(digit) * (3 if position % 2 == 0 else 1) for position, digit in enumerate(reversed(payload)))
        return (10 - total % 10) % 10

    @staticmethod
    def _email_shape_problem(email: str, at_count: int, domain: str | None) -> EmailSyntaxProblem | None:
        """Return the first whole-address problem: characters, at signs, then the domain and address lengths."""
        if not email.isascii():
            return EmailSyntaxProblem.NOT_ASCII
        if at_count == 0:
            return EmailSyntaxProblem.MISSING_AT_SIGN
        if at_count > 1 or domain is None:
            return EmailSyntaxProblem.MULTIPLE_AT_SIGNS
        if len(domain) > _MAX_DOMAIN_LENGTH:
            return EmailSyntaxProblem.DOMAIN_TOO_LONG
        if len(email) > _MAX_ADDRESS_LENGTH:
            return EmailSyntaxProblem.ADDRESS_TOO_LONG
        return None

    @staticmethod
    def _email_part_problem(local_part: str, domain: str) -> EmailSyntaxProblem | None:
        """Return the first problem in the local part or the domain labels, in the row's order."""
        labels = domain.split(".")
        last_label = labels[-1]
        if not local_part:
            return EmailSyntaxProblem.LOCAL_PART_EMPTY
        if len(local_part) > _MAX_LOCAL_PART_LENGTH:
            return EmailSyntaxProblem.LOCAL_PART_TOO_LONG
        if _EMAIL_LOCAL_PART.fullmatch(local_part) is None:
            return EmailSyntaxProblem.LOCAL_PART_INVALID
        if not all(_DOMAIN_LABEL.fullmatch(label) for label in labels):
            return EmailSyntaxProblem.DOMAIN_LABEL_INVALID
        if len(labels) < 2:
            return EmailSyntaxProblem.DOMAIN_NEEDS_TWO_LABELS
        if _LETTER_LABEL.fullmatch(last_label) is None and not last_label.lower().startswith(_PUNYCODE_PREFIX):
            return EmailSyntaxProblem.TOP_LEVEL_DOMAIN_INVALID
        return None

    @staticmethod
    def _split_authority(authority: str) -> tuple[str, str | None, bool]:
        """Return the host text, the port text or None, and whether the host is a well-formed bracketed address."""
        # The host follows the last at sign; a bracketed host may hold
        # colons, so its port starts only after the closing bracket.
        host_and_port = authority.rpartition("@")[2]
        if host_and_port.startswith("["):
            inside, closed, tail = host_and_port[1:].partition("]")
            if closed and not tail:
                return inside, None, True
            if closed and tail.startswith(":"):
                return inside, tail[1:], True
            return host_and_port, None, False
        host, colon, port_text = host_and_port.partition(":")
        return host, port_text if colon else None, False

    @staticmethod
    def _host_shape_ok(host: str, bracketed: bool) -> bool:
        """Say whether a host is a bracketed IPv6 address, an IPv4 address, or dot-separated hostname labels."""
        try:
            if bracketed:
                ipaddress.IPv6Address(host)
                return True
            ipaddress.IPv4Address(host)
        except ValueError:
            return not bracketed and all(_DOMAIN_LABEL.fullmatch(label) for label in host.split("."))
        return True

    @staticmethod
    def _url_problem(url: str, scheme: str | None, allowed: set[str], host: str | None, port_text: str | None, host_ok: bool) -> UrlSyntaxProblem | None:
        """Return the first URL problem in the row's order, or None when the URL passes every check."""
        if any(character.isspace() or unicodedata.category(character) == "Cc" for character in url):
            return UrlSyntaxProblem.WHITESPACE_OR_CONTROL
        if scheme is None:
            return UrlSyntaxProblem.MISSING_SCHEME
        if scheme.casefold() not in allowed:
            return UrlSyntaxProblem.SCHEME_NOT_ALLOWED
        if not host:
            return UrlSyntaxProblem.MISSING_HOST
        if port_text is not None and (_PORT_TEXT.fullmatch(port_text) is None or int(port_text) > _MAX_PORT):
            return UrlSyntaxProblem.INVALID_PORT
        return None if host_ok else UrlSyntaxProblem.INVALID_HOST

    @staticmethod
    def _parse_uuid_text(text: str) -> uuid.UUID | None:
        """Read a UUID in hyphenated or 32-digit form, optionally braced or behind a urn:uuid: prefix, or return None."""
        body = text
        if body[: len(_UUID_URN_PREFIX)].lower() == _UUID_URN_PREFIX:
            body = body[len(_UUID_URN_PREFIX) :]
        elif len(body) > 1 and body.startswith("{") and body.endswith("}"):
            body = body[1:-1]
        if _UUID_HYPHENATED.fullmatch(body) is None and _UUID_COMPACT.fullmatch(body) is None:
            return None
        return uuid.UUID(body)

    @staticmethod
    def _semver_key(text: str, parameter_name: str) -> tuple[_SemverKey, bool]:
        """Build a precedence key for one version and say whether it is a pre-release, failing on invalid text."""
        match = _SEMVER.fullmatch(text)
        if match is None:
            problem = "the text is not a Semantic Versioning 2.0.0 version"
            raise PrebuiltToolSupport.argument_error(parameter_name, problem, "MAJOR.MINOR.PATCH with optional pre-release and build parts, no leading zeros, and at most one leading v")
        # Numbers without leading zeros compare by length, then by
        # text, which avoids turning very long digit runs into ints.
        core = tuple((len(part), part) for part in match.group(1, 2, 3))
        prerelease = match.group(4)
        if prerelease is None:
            return (core, 1, ()), False
        identifiers = tuple((0, len(part), part) if _ASCII_DIGITS.fullmatch(part) else (1, 0, part) for part in prerelease.split("."))
        return (core, 0, identifiers), True

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.verify_luhn_checksum,
            cls.verify_isbn,
            cls.verify_iban,
            cls.verify_gtin_barcode,
            cls.verify_email_syntax,
            cls.verify_url_syntax,
            cls.verify_uuid,
            cls.generate_name_based_uuid,
            cls.compare_semantic_versions,
        )


__all__ = ["IdentifiersToolFunctions"]
