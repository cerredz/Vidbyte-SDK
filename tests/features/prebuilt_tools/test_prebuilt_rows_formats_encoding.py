"""FILE: tests/features/prebuilt_tools/test_prebuilt_rows_formats_encoding.py

PURPOSE: Exact-output and error cases for every Appendix A row of the structured_formats, encoding, and hashing categories (A.20 to A.22, 26 tools), run through FunctionTool.execute as a model would call them.
ROLE IN CODEBASE: Row-level proof of AC-11 for these three categories; uses the ToolRunner fixture from tests/features/prebuilt_tools/conftest.py and the case builders in prebuilt_tool_harness.py.
ARCHITECTURE NOTE: Expected values come from published vectors (RFC 3986, RFC 4231, RFC 2202, RFC 4648, FIPS and BLAKE2 test vectors, git's empty blob, the jwt.io sample token), from hand derivation, or from an independent pure-Python CRC-32 and Adler-32; nothing is copied from the implementation.
FUNCTION INVENTORY: test_formats_encoding_rows_return_documented_output checks SUCCESS_CASES; test_formats_encoding_rows_reject_bad_input checks FAILURE_CASES; test_compute_hmac_errors_never_repeat_the_key checks T-3; test_parse_dotenv_text_error_omits_line_content checks T-3 for .env text; test_encoding_round_trips_restore_the_text checks base64 and hex round trips.
COMMON MODIFICATION PATTERNS: Add a row case as one ok(...) or bad(...) entry in the matching table, with every output key listed and the source of the expected value obvious from a published vector or a short hand derivation.
WHAT NOT TO DO IN THIS FILE: 1. Do not compute expected values by calling hashlib, base64, or the tool under test at test time; use literal vectors. 2. Do not add nesting-depth or output-cap cases here; test_prebuilt_resource_bounds.py owns them.
KNOWN EDGE CASES: An unpaired surrogate cannot reach a tool through FunctionTool.execute (pydantic JSON mode rejects it), so EC-14 is exercised with characters a codec cannot encode, such as the euro sign in latin_1 or ascii. Expat reports the column of the mismatched end-tag name, and the row makes it 1-based. The codec utf_16 adds a byte-order mark in native order, so byte-exact cases use utf_16_le and utf_16_be. Spec r4 gives a rejected DOCTYPE or long namespace URI a fixed non-empty error with null line and column, and maps every findall exception for a path, KeyError for "@" included, to error(path). Spec r6 (S4 R-7) lists each matching element once, in document order; the hostile path inputs live in test_prebuilt_hostile_inputs.py.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md (Appendix A.20, A.21, A.22; §9.2; §10 T-3 and T-6)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_rows_formats_encoding.py
"""

from __future__ import annotations

import pytest

from tests.features.prebuilt_tools.prebuilt_tool_harness import NON_EMPTY_TEXT, FailureCase, SuccessCase, ToolRunner, bad, invalid, ok

ABC_SHA256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
JEFE_MESSAGE = "what do ya want for nothing?"
JEFE_HMAC_SHA256 = "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"
JWT_SAMPLE = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    + "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ."
    + "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
)
JWT_SAMPLE_OUTPUT = {
    "header": {"alg": "HS256", "typ": "JWT"},
    "payload": {"sub": "1234567890", "name": "John Doe", "iat": 1516239022},
    "signature_verified": False,
    "has_signature": True,
    "claims": {"issued_at": "2018-01-18T01:30:22+00:00", "expires_at": None, "not_before": None},
}
ENTITY_BOMB = "<!DOCTYPE r [<!ENTITY e \"x\">]><r>&e;</r>"
LONG_NAMESPACE_XML = "<r xmlns:p=\"urn:" + "u" * 200 + "\"><p:i/></r>"
DOTENV_SAMPLE = "export A=1\n# comment\n\nB=\" x\\ty\\n\"\nC='lit $X\\n'\nD=plain value # note\nmy.key-1=v\nF=\"q\\\"x\\\\y\"\nG=a#b\nA=2\n"

# Published "abc" vectors (FIPS 180-4, FIPS 202, RFC 1321, RFC 3174, RFC 7693, and the BLAKE2s reference).
ABC_DIGESTS = (
    ("md5", "900150983cd24fb0d6963f7d28e17f72"),
    ("sha1", "a9993e364706816aba3e25717850c26c9cd0d89d"),
    ("sha224", "23097d223405d8228642a477bda255b32aadbce4bda0b3f7e36c9da7"),
    ("sha256", ABC_SHA256),
    ("sha384", "cb00753f45a35e8bb5a03d699ac65007272c32ab0eded1631a8b605a43ff5bed8086072ba1e7cc2358baeca134c825a7"),
    (
        "sha512",
        "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f",
    ),
    ("sha3_256", "3a985da74fe225b2045c172d6bd390bd855f086e3e9d525b46bfe24511431532"),
    (
        "sha3_512",
        "b751850b1a57168a5693cd924b6b096e08f621827444f70d884f5d0240d2712e10e116e9192af3c91a7ec57647e3934057340b4cf408d5a56592f8274eec53f0",
    ),
    (
        "blake2b",
        "ba80a53f981c4d0d6a2797b69f12f6e94c212f14685ac4b74b12bb6fdbffa2d17d87c5392aab792dc252d5de4533cc9518d38aa8dbf1925ab92386edd4009923",
    ),
    ("blake2s", "508c5e8c327c14e2e1a72ba34eeb452f37458b209ed63a294d999b4c86675982"),
)

# RFC 4231 test case 2 and RFC 2202 test case 2: key "Jefe", message "what do ya want for nothing?".
JEFE_HMACS = (
    ("md5", "750c783e6ab0b503eaa86e310a5db738"),
    ("sha1", "effcdf6ae5eb2fa2d27416d5f184df9c259a7c79"),
    ("sha224", "a30e01098bc6dbbf45690f3a7e9e6d0f8bbea2a39e6148008fd05e44"),
    ("sha384", "af45d2e376484031617f78d2b58a6b1b9c7ef464f5a01b47e42ec3736322445e8e2240ca5e69e2c78b3239ecfab21649"),
    (
        "sha512",
        "164b7a7bfcf819e2e395fbe73b56e0a387bd64222e831fd610270cd7ea2505549758bf75c05a994a6d034f65f8f0e6fdcaeab1a34d4a6b4b636e070a38bce737",
    ),
)

STRUCTURED_FORMAT_CASES = [
    ok(
        "xml_to_json",
        {"xml_text": "<root><a x=\"1\">t</a><a/><b>hi</b></root>"},
        {"root_tag": "root", "value": {"a": [{"@x": "1", "#text": "t"}, None], "b": "hi"}},
        "attributes-repeats-empty",
    ),
    ok(
        "xml_to_json",
        {"xml_text": "<r>\n  <item id=\"7\">\n    <name>x</name>\n  </item>\n</r>\n"},
        {"root_tag": "r", "value": {"item": {"@id": "7", "name": "x"}}},
        "blank-text-dropped",
    ),
    ok("xml_to_json", {"xml_text": "<greeting>hello</greeting>"}, {"root_tag": "greeting", "value": "hello"}, "text-only-root"),
    ok("xml_to_json", {"xml_text": "<empty/>"}, {"root_tag": "empty", "value": None}, "empty-root"),
    ok(
        "xml_to_json",
        {"xml_text": "<r xmlns=\"urn:x\"><i>1</i></r>"},
        {"root_tag": "{urn:x}r", "value": {"{urn:x}i": "1"}},
        "namespace-uri-form",
    ),
    ok(
        "xml_to_json",
        {"xml_text": "<r xmlns=\"" + "u" * 200 + "\"/>"},
        {"root_tag": "{" + "u" * 200 + "}r", "value": None},
        "namespace-uri-at-cap",
    ),
    ok(
        "verify_xml_wellformed",
        {"xml_text": "<root><a/></root>"},
        {"wellformed": True, "error": None, "line": None, "column": None, "root_tag": "root"},
        "wellformed",
    ),
    ok(
        "verify_xml_wellformed",
        {"xml_text": "<a>\n<b></a>"},
        {"wellformed": False, "error": "mismatched tag", "line": 2, "column": 6, "root_tag": None},
        "mismatched-tag",
    ),
    ok(
        "verify_xml_wellformed",
        {"xml_text": ""},
        {"wellformed": False, "error": "no element found", "line": 1, "column": 1, "root_tag": None},
        "empty-text",
    ),
    ok(
        "verify_xml_wellformed",
        {"xml_text": ENTITY_BOMB},
        {"wellformed": False, "error": NON_EMPTY_TEXT, "line": None, "column": None, "root_tag": None},
        "entity-bomb",
    ),
    ok(
        "verify_xml_wellformed",
        {"xml_text": LONG_NAMESPACE_XML},
        {"wellformed": False, "error": NON_EMPTY_TEXT, "line": None, "column": None, "root_tag": None},
        "long-namespace-uri",
    ),
    ok(
        "verify_xml_wellformed",
        {"xml_text": "<!DOCTYPE a>\n<a/>"},
        {"wellformed": False, "error": NON_EMPTY_TEXT, "line": None, "column": None, "root_tag": None},
        "plain-doctype",
    ),
    ok(
        "xml_find_elements",
        {"xml_text": "<lib><book id=\"1\"> A </book><book id=\"2\"/><mag>x</mag></lib>", "path": "book"},
        {
            "elements": [{"tag": "book", "attributes": {"id": "1"}, "text": "A"}, {"tag": "book", "attributes": {"id": "2"}, "text": None}],
            "count": 2,
            "truncated": False,
        },
        "children-text-stripped",
    ),
    ok(
        "xml_find_elements",
        {"xml_text": "<a><b>1</b><c><b k=\"v\">2</b></c></a>", "path": ".//b"},
        {
            "elements": [{"tag": "b", "attributes": {}, "text": "1"}, {"tag": "b", "attributes": {"k": "v"}, "text": "2"}],
            "count": 2,
            "truncated": False,
        },
        "descendants-document-order",
    ),
    ok(
        "xml_find_elements",
        {"xml_text": "<lib><book id=\"1\"/><book id=\"2\">B</book></lib>", "path": "book[@id='2']"},
        {"elements": [{"tag": "book", "attributes": {"id": "2"}, "text": "B"}], "count": 1, "truncated": False},
        "attribute-predicate",
    ),
    ok("xml_find_elements", {"xml_text": "<a><b/></a>", "path": "zzz"}, {"elements": [], "count": 0, "truncated": False}, "no-match"),
    # S4 R-7 (spec r6 A.20): matches are distinct elements in document order, although the stdlib's descendant step repeats them.
    ok(
        "xml_find_elements",
        {"xml_text": "<r><a x='1'><a x='2'><a x='3'/></a></a></r>", "path": ".//a//a"},
        {"elements": [{"tag": "a", "attributes": {"x": "2"}, "text": None}, {"tag": "a", "attributes": {"x": "3"}, "text": None}], "count": 2, "truncated": False},
        "repeated-descendant-listed-once",
    ),
    ok(
        "xml_find_elements",
        {"xml_text": "<a>" * 60 + "</a>" * 60, "path": ".//a//a"},
        {"elements": [{"tag": "a", "attributes": {}, "text": None}] * 58, "count": 58, "truncated": False},
        "chain-of-60-has-58-distinct-matches",
    ),
    ok(
        "ini_to_json",
        {"ini_text": "[DEFAULT]\nbase = 1\n\n[server]\nHost = example.com\nport = 8080\nflag\n"},
        {"sections": {"server": {"Host": "example.com", "port": "8080", "flag": None}}, "defaults": {"base": "1"}},
        "default-section-kept-apart",
    ),
    ok(
        "ini_to_json",
        {"ini_text": "[paths]\nhome = /h\nlog = %(home)s/log\n"},
        {"sections": {"paths": {"home": "/h", "log": "%(home)s/log"}}, "defaults": {}},
        "no-interpolation",
    ),
    ok("ini_to_json", {"ini_text": ""}, {"sections": {}, "defaults": {}}, "empty"),
    ok(
        "toml_to_json",
        {
            "toml_text": "title = \"x\"\nz = 1979-05-27T07:32:00Z\nd = 1979-05-27\nt = 07:32:00\nldt = 1979-05-27T00:32:00.999999\n"
            + "[owner]\ndob = 1979-05-27T07:32:00-08:00\n[db]\nports = [8000, 8001]\nenabled = true\nratio = 0.5\n"
        },
        {
            "value": {
                "title": "x",
                "z": "1979-05-27T07:32:00+00:00",
                "d": "1979-05-27",
                "t": "07:32:00",
                "ldt": "1979-05-27T00:32:00.999999",
                "owner": {"dob": "1979-05-27T07:32:00-08:00"},
                "db": {"ports": [8000, 8001], "enabled": True, "ratio": 0.5},
            }
        },
        "dates-become-iso-text",
    ),
    ok(
        "toml_to_json",
        {"toml_text": "[[fruit]]\nname = \"apple\"\n[[fruit]]\nname = \"pear\"\n"},
        {"value": {"fruit": [{"name": "apple"}, {"name": "pear"}]}},
        "array-of-tables",
    ),
    ok("toml_to_json", {"toml_text": ""}, {"value": {}}, "empty"),
    ok(
        "parse_url",
        {"url": "https://User:secret@Example.COM:8080/a/b?x=1&y=&x=3#frag"},
        {
            "scheme": "https",
            "username": "User",
            "has_password": True,
            "host": "example.com",
            "port": 8080,
            "path": "/a/b",
            "query": "x=1&y=&x=3",
            "fragment": "frag",
            "query_parameters": [{"name": "x", "value": "1"}, {"name": "y", "value": ""}, {"name": "x", "value": "3"}],
            "is_absolute": True,
        },
        "full-url-password-hidden",
    ),
    ok(
        "parse_url",
        {"url": "/path/only?q=a+b"},
        {
            "scheme": "",
            "username": None,
            "has_password": False,
            "host": None,
            "port": None,
            "path": "/path/only",
            "query": "q=a+b",
            "fragment": "",
            "query_parameters": [{"name": "q", "value": "a b"}],
            "is_absolute": False,
        },
        "relative",
    ),
    ok(
        "parse_url",
        {"url": "mailto:a@b.c"},
        {
            "scheme": "mailto",
            "username": None,
            "has_password": False,
            "host": None,
            "port": None,
            "path": "a@b.c",
            "query": "",
            "fragment": "",
            "query_parameters": [],
            "is_absolute": False,
        },
        "scheme-without-network-location",
    ),
    ok(
        "parse_url",
        {"url": "http://[::1]:80/"},
        {
            "scheme": "http",
            "username": None,
            "has_password": False,
            "host": "::1",
            "port": 80,
            "path": "/",
            "query": "",
            "fragment": "",
            "query_parameters": [],
            "is_absolute": True,
        },
        "ipv6-host",
    ),
    ok("resolve_relative_url", {"base_url": "http://a/b/c/d;p?q", "reference": "g"}, {"url": "http://a/b/c/g"}, "rfc3986-sibling"),
    ok("resolve_relative_url", {"base_url": "http://a/b/c/d;p?q", "reference": "../g"}, {"url": "http://a/b/g"}, "rfc3986-parent"),
    ok("resolve_relative_url", {"base_url": "http://a/b/c/d;p?q", "reference": "//g"}, {"url": "http://g"}, "rfc3986-network-path"),
    ok("resolve_relative_url", {"base_url": "http://a/b/c/d;p?q", "reference": "?y"}, {"url": "http://a/b/c/d;p?y"}, "rfc3986-query"),
    ok("resolve_relative_url", {"base_url": "http://a/b/c/d;p?q", "reference": "../../../g"}, {"url": "http://a/g"}, "rfc3986-above-root"),
    ok(
        "parse_query_string",
        {"query": "?a=1&b=two+words&a=%E2%82%AC&empty="},
        {
            "parameters": [
                {"name": "a", "value": "1"},
                {"name": "b", "value": "two words"},
                {"name": "a", "value": "€"},
                {"name": "empty", "value": ""},
            ],
            "by_name": {"a": ["1", "€"], "b": ["two words"], "empty": [""]},
        },
        "decoding-and-grouping",
    ),
    ok(
        "parse_query_string",
        {"query": "flag&x=%zz"},
        {"parameters": [{"name": "flag", "value": ""}, {"name": "x", "value": "%zz"}], "by_name": {"flag": [""], "x": ["%zz"]}},
        "blank-and-bad-escape",
    ),
    ok("parse_query_string", {"query": ""}, {"parameters": [], "by_name": {}}, "empty"),
    ok(
        "parse_dotenv_text",
        {"dotenv_text": DOTENV_SAMPLE},
        {
            "variables": {"A": "2", "B": " x\ty\n", "C": "lit $X\\n", "D": "plain value", "my.key-1": "v", "F": "q\"x\\y", "G": "a#b"},
            "count": 7,
            "duplicate_keys": ["A"],
        },
        "quoting-comments-duplicates",
    ),
    ok(
        "parse_dotenv_text",
        {"dotenv_text": "X=1\r\nY= 2 \r\nE=\r\n"},
        {"variables": {"X": "1", "Y": "2", "E": ""}, "count": 3, "duplicate_keys": []},
        "crlf-and-trim",
    ),
    ok("parse_dotenv_text", {"dotenv_text": ""}, {"variables": {}, "count": 0, "duplicate_keys": []}, "empty"),
]

ENCODING_CASES = [
    ok("base64_encode", {"text": "foobar"}, {"base64": "Zm9vYmFy"}, "rfc4648-foobar"),
    ok("base64_encode", {"text": "fooba"}, {"base64": "Zm9vYmE="}, "rfc4648-fooba"),
    ok("base64_encode", {"text": "f"}, {"base64": "Zg=="}, "rfc4648-f"),
    ok("base64_encode", {"text": "f", "padding": False}, {"base64": "Zg"}, "no-padding"),
    ok("base64_encode", {"text": "ÿþý", "text_encoding": "latin_1"}, {"base64": "//79"}, "standard-alphabet"),
    ok("base64_encode", {"text": "ÿþý", "text_encoding": "latin_1", "url_safe": True}, {"base64": "__79"}, "url-safe-alphabet"),
    ok("base64_encode", {"text": "A", "text_encoding": "utf_16_le"}, {"base64": "QQA="}, "utf-16-le"),
    ok("base64_encode", {"text": "€", "text_encoding": "cp1252"}, {"base64": "gA=="}, "cp1252-euro"),
    ok("base64_encode", {"text": ""}, {"base64": ""}, "empty"),
    ok("base64_decode", {"data": "Zm9vYmFy"}, {"text": "foobar", "is_text": True, "size_bytes": 6, "hex_preview": "666f6f626172"}, "text"),
    ok("base64_decode", {"data": "Zg"}, {"text": "f", "is_text": True, "size_bytes": 1, "hex_preview": "66"}, "missing-padding"),
    ok("base64_decode", {"data": "Zm9v\nYmFy "}, {"text": "foobar", "is_text": True, "size_bytes": 6, "hex_preview": "666f6f626172"}, "whitespace"),
    ok("base64_decode", {"data": "__79"}, {"text": None, "is_text": False, "size_bytes": 3, "hex_preview": "fffefd"}, "url-safe-binary"),
    ok(
        "base64_decode",
        {"data": "__79", "text_encoding": "latin_1"},
        {"text": "ÿþý", "is_text": True, "size_bytes": 3, "hex_preview": "fffefd"},
        "latin-1-text",
    ),
    ok(
        "base64_decode",
        {"data": "YWFh" * 23 + "YQ=="},
        {"text": "a" * 70, "is_text": True, "size_bytes": 70, "hex_preview": "61" * 64},
        "preview-capped-at-64-bytes",
    ),
    ok("base64_decode", {"data": ""}, {"text": "", "is_text": True, "size_bytes": 0, "hex_preview": ""}, "empty"),
    ok("hex_encode", {"text": "hello"}, {"hex": "68656c6c6f"}, "default"),
    ok("hex_encode", {"text": "hello", "separator": "space"}, {"hex": "68 65 6c 6c 6f"}, "space"),
    ok("hex_encode", {"text": "hello", "separator": "colon", "uppercase": True}, {"hex": "68:65:6C:6C:6F"}, "colon-upper"),
    ok("hex_encode", {"text": "A", "text_encoding": "utf_16_be"}, {"hex": "0041"}, "utf-16-be"),
    ok("hex_encode", {"text": ""}, {"hex": ""}, "empty"),
    ok("hex_decode", {"hex_text": "68656c6c6f"}, {"text": "hello", "is_text": True, "size_bytes": 5}, "plain"),
    ok("hex_decode", {"hex_text": "0x68:65 6C"}, {"text": "hel", "is_text": True, "size_bytes": 3}, "prefix-colons-spaces-uppercase"),
    ok("hex_decode", {"hex_text": "ff"}, {"text": None, "is_text": False, "size_bytes": 1}, "invalid-utf-8"),
    ok("hex_decode", {"hex_text": "ff", "text_encoding": "latin_1"}, {"text": "ÿ", "is_text": True, "size_bytes": 1}, "latin-1"),
    ok("hex_decode", {"hex_text": ""}, {"text": "", "is_text": True, "size_bytes": 0}, "empty"),
    ok("url_encode", {"text": "a b/c?d=é"}, {"encoded": "a%20b%2Fc%3Fd%3D%C3%A9"}, "component"),
    ok("url_encode", {"text": "a b/c?d=é", "mode": "path"}, {"encoded": "a%20b/c%3Fd%3D%C3%A9"}, "path"),
    ok("url_encode", {"text": "a b/c?d=é", "mode": "form"}, {"encoded": "a+b%2Fc%3Fd%3D%C3%A9"}, "form"),
    ok("url_decode", {"text": "a%20b%2Fc+d"}, {"decoded": "a b/c+d", "had_invalid_sequences": False}, "component-keeps-plus"),
    ok("url_decode", {"text": "a%20b%2Fc+d", "mode": "form"}, {"decoded": "a b/c d", "had_invalid_sequences": False}, "form-plus-is-space"),
    ok("url_decode", {"text": "caf%C3%A9"}, {"decoded": "café", "had_invalid_sequences": False}, "utf-8"),
    ok("url_decode", {"text": "100%"}, {"decoded": "100%", "had_invalid_sequences": True}, "dangling-percent"),
    ok("url_decode", {"text": "%E2%82"}, {"decoded": "�", "had_invalid_sequences": True}, "truncated-utf-8"),
    ok(
        "html_unescape",
        {"text": "&lt;b&gt;Tom &amp; Jerry&lt;/b&gt; &#39;x&#39; &#x263A; &copy; &amp;amp;"},
        {"unescaped": "<b>Tom & Jerry</b> 'x' ☺ © &amp;"},
        "named-numeric-single-pass",
    ),
    ok("decode_jwt_payload", {"jwt_text": JWT_SAMPLE}, JWT_SAMPLE_OUTPUT, "jwt-io-sample"),
    ok("decode_jwt_payload", {"jwt_text": "  Bearer " + JWT_SAMPLE + "\n"}, JWT_SAMPLE_OUTPUT, "bearer-prefix"),
    ok(
        "decode_jwt_payload",
        {"jwt_text": "eyJhbGciOiJub25lIn0.eyJleHAiOjAsIm5iZiI6ODY0MDAsImlhdCI6Inllc3RlcmRheSJ9."},
        {
            "header": {"alg": "none"},
            "payload": {"exp": 0, "nbf": 86400, "iat": "yesterday"},
            "signature_verified": False,
            "has_signature": False,
            "claims": {"issued_at": None, "expires_at": "1970-01-01T00:00:00+00:00", "not_before": "1970-01-02T00:00:00+00:00"},
        },
        "unsigned-claims",
    ),
    ok("escape_json_string", {"text": "He said \"hi\"\n\tC:\\path"}, {"escaped": "He said \\\"hi\\\"\\n\\tC:\\\\path"}, "quotes-controls"),
    ok("escape_json_string", {"text": "é😀\u0001"}, {"escaped": "é😀\\u0001"}, "keeps-non-ascii"),
    ok("escape_json_string", {"text": "é😀\u0001", "ensure_ascii": True}, {"escaped": "\\u00e9\\ud83d\\ude00\\u0001"}, "ensure-ascii"),
    ok("escape_json_string", {"text": ""}, {"escaped": ""}, "empty"),
    ok("unescape_json_string", {"escaped": "\\\"hi\\\"\\n\\u00e9"}, {"text": "\"hi\"\né"}, "without-quotes"),
    ok("unescape_json_string", {"escaped": "\"a\\tb\""}, {"text": "a\tb"}, "with-quotes"),
    ok("unescape_json_string", {"escaped": "\\ud83d\\ude00"}, {"text": "😀"}, "surrogate-pair"),
    ok("unescape_json_string", {"escaped": ""}, {"text": ""}, "empty"),
]

HASHING_CASES = [
    *[ok("hash_text", {"text": "abc", "algorithm": name}, {"digest": digest, "algorithm": name}, f"abc-{name}") for name, digest in ABC_DIGESTS],
    ok("hash_text", {"text": "abc"}, {"digest": ABC_SHA256, "algorithm": "sha256"}, "default-sha256"),
    ok(
        "hash_text",
        {"text": "abc", "digest_format": "base64"},
        {"digest": "ungWv48Bz+pBQUDeXa4iI7ADYaOWF3qctBD/YfIAFa0=", "algorithm": "sha256"},
        "base64",
    ),
    ok(
        "hash_text",
        {"text": "abc", "digest_format": "base64url"},
        {"digest": "ungWv48Bz-pBQUDeXa4iI7ADYaOWF3qctBD_YfIAFa0", "algorithm": "sha256"},
        "base64url-unpadded",
    ),
    ok("hash_text", {"text": ""}, {"digest": EMPTY_SHA256, "algorithm": "sha256"}, "empty"),
    ok(
        "hash_text",
        {"text": "é", "text_encoding": "latin_1"},
        {"digest": "de2e331d891ae267a7009cb45b4e8830f170e0c937288ea2731a1941c7a53b0d", "algorithm": "sha256"},
        "latin-1-bytes",
    ),
    ok("hash_base64_content", {"data_base64": "YWJj"}, {"digest": ABC_SHA256, "algorithm": "sha256", "size_bytes": 3}, "abc"),
    ok(
        "hash_base64_content",
        {"data_base64": "YWJj", "algorithm": "md5"},
        {"digest": "900150983cd24fb0d6963f7d28e17f72", "algorithm": "md5", "size_bytes": 3},
        "md5",
    ),
    ok(
        "hash_base64_content",
        {"data_base64": "YWJj", "digest_format": "base64url"},
        {"digest": "ungWv48Bz-pBQUDeXa4iI7ADYaOWF3qctBD_YfIAFa0", "algorithm": "sha256", "size_bytes": 3},
        "base64url-digest",
    ),
    ok(
        "hash_base64_content",
        {"data_base64": "__79"},
        {"digest": "8ca9f8c269c0a4b1d8bf0efc67d97df8ad5e0ea93630fd9099860d36c0fe75ea", "algorithm": "sha256", "size_bytes": 3},
        "url-safe-detected",
    ),
    ok("hash_base64_content", {"data_base64": ""}, {"digest": EMPTY_SHA256, "algorithm": "sha256", "size_bytes": 0}, "empty"),
    ok(
        "hash_base64_content",
        {"data_base64": "YWJj", "digest_format": "base64"},
        {"digest": "ungWv48Bz+pBQUDeXa4iI7ADYaOWF3qctBD/YfIAFa0=", "algorithm": "sha256", "size_bytes": 3},
        "base64-digest-keeps-padding",
    ),
    ok("compute_hmac", {"message": JEFE_MESSAGE, "key": "Jefe"}, {"digest": JEFE_HMAC_SHA256, "algorithm": "sha256"}, "rfc4231-sha256"),
    *[
        ok("compute_hmac", {"message": JEFE_MESSAGE, "key": "Jefe", "algorithm": name}, {"digest": digest, "algorithm": name}, f"rfc-{name}")
        for name, digest in JEFE_HMACS
    ],
    ok(
        "compute_hmac",
        {"message": JEFE_MESSAGE, "key": "4a656665", "key_format": "hex"},
        {"digest": JEFE_HMAC_SHA256, "algorithm": "sha256"},
        "hex-key",
    ),
    ok(
        "compute_hmac",
        {"message": JEFE_MESSAGE, "key": "SmVmZQ==", "key_format": "base64"},
        {"digest": JEFE_HMAC_SHA256, "algorithm": "sha256"},
        "base64-key",
    ),
    ok(
        "compute_hmac",
        {"message": JEFE_MESSAGE, "key": "Jefe", "digest_format": "base64"},
        {"digest": "W9zBRr9gdU5qBCQmCJV1x1oAPwidJzmDnexYuWTsOEM=", "algorithm": "sha256"},
        "base64-digest",
    ),
    ok(
        "compute_hmac",
        {"message": JEFE_MESSAGE, "key": "Jefe", "digest_format": "base64url"},
        {"digest": "W9zBRr9gdU5qBCQmCJV1x1oAPwidJzmDnexYuWTsOEM", "algorithm": "sha256"},
        "base64url-digest",
    ),
    ok("verify_hash", {"text": "abc", "expected_digest": ABC_SHA256.upper()}, {"matches": True, "computed_hex": ABC_SHA256}, "uppercase-hex"),
    ok(
        "verify_hash",
        {"text": "abc", "expected_digest": "ungWv48Bz+pBQUDeXa4iI7ADYaOWF3qctBD/YfIAFa0="},
        {"matches": True, "computed_hex": ABC_SHA256},
        "base64",
    ),
    ok(
        "verify_hash",
        {"text": "abc", "expected_digest": "ungWv48Bz-pBQUDeXa4iI7ADYaOWF3qctBD_YfIAFa0"},
        {"matches": True, "computed_hex": ABC_SHA256},
        "base64url",
    ),
    ok(
        "verify_hash",
        {"text": "abc", "expected_digest": "a52d159f262b2c6ddb724a61840befc36eb30c88877a4030b65cbe86298449c9"},
        {"matches": False, "computed_hex": ABC_SHA256},
        "other-text-digest",
    ),
    ok("verify_hash", {"text": "abc", "expected_digest": "abcd"}, {"matches": False, "computed_hex": ABC_SHA256}, "wrong-length"),
    ok("verify_hash", {"text": "abc", "expected_digest": "zz!!"}, {"matches": False, "computed_hex": ABC_SHA256}, "undecodable"),
    ok(
        "verify_hash",
        {"text": "abc", "expected_digest": "900150983cd24fb0d6963f7d28e17f72", "algorithm": "md5"},
        {"matches": True, "computed_hex": "900150983cd24fb0d6963f7d28e17f72"},
        "md5",
    ),
    ok("crc32_checksum", {"text": "123456789"}, {"crc32_hex": "cbf43926", "crc32_decimal": 3421780262, "adler32_hex": "091e01de"}, "check-value"),
    ok("crc32_checksum", {"text": "Wikipedia"}, {"crc32_hex": "adaac02e", "crc32_decimal": 2913648686, "adler32_hex": "11e60398"}, "wikipedia"),
    ok("crc32_checksum", {"text": ""}, {"crc32_hex": "00000000", "crc32_decimal": 0, "adler32_hex": "00000001"}, "empty-padded"),
    ok("crc32_checksum", {"text": "é"}, {"crc32_hex": "0e048d3e", "crc32_decimal": 235179326, "adler32_hex": "0231016d"}, "utf-8"),
    ok(
        "crc32_checksum",
        {"text": "é", "text_encoding": "latin_1"},
        {"crc32_hex": "0bd4b551", "crc32_decimal": 198489425, "adler32_hex": "00ea00ea"},
        "latin-1",
    ),
    ok("git_blob_hash", {"content": "hello world\n"}, {"object_id": "3b18e512dba79e4c8300dd08aeb37f8e728b8dad", "size_bytes": 12}, "hello-world"),
    ok("git_blob_hash", {"content": ""}, {"object_id": "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391", "size_bytes": 0}, "empty-blob"),
    ok(
        "git_blob_hash",
        {"content": "hello world\r\n"},
        {"object_id": "f35d3e67b4cdad5ef058bec4a2ef955a98c4848a", "size_bytes": 13},
        "crlf-not-normalized",
    ),
    ok("git_blob_hash", {"content": "é\n"}, {"object_id": "c6003325155f475bd7c87731607525dce73be9cf", "size_bytes": 3}, "utf-8-size"),
    ok("assign_stable_bucket", {"key": "user-42", "buckets": 10}, {"bucket": 6, "hash_prefix": "6a9686217715350a"}, "no-salt"),
    ok(
        "assign_stable_bucket",
        {"key": "user-42", "buckets": 10, "salt": "exp1"},
        {"bucket": 9, "hash_prefix": "7f2e46f46b94cfc3"},
        "salted",
    ),
    ok("assign_stable_bucket", {"key": "user-42", "buckets": 1}, {"bucket": 0, "hash_prefix": "6a9686217715350a"}, "one-bucket"),
    ok("assign_stable_bucket", {"key": "alice", "buckets": 1000000}, {"bucket": 311535, "hash_prefix": "3b8d32346718b5af"}, "max-buckets"),
]

SUCCESS_CASES = STRUCTURED_FORMAT_CASES + ENCODING_CASES + HASHING_CASES

FAILURE_CASES = [
    bad("xml_to_json", {"xml_text": ENTITY_BOMB}, "xml_text", "doctype-entity"),
    bad("xml_to_json", {"xml_text": LONG_NAMESPACE_XML}, "xml_text", "namespace-uri-over-cap"),
    bad("xml_to_json", {"xml_text": "<a><b></a>"}, "xml_text", "parse-error", contains="mismatched tag"),
    bad("xml_find_elements", {"xml_text": "<a><b/></a>", "path": "["}, "path", "unbalanced-bracket"),
    bad("xml_find_elements", {"xml_text": "<a><b/></a>", "path": "/b"}, "path", "absolute-path"),
    # Spec r4: every exception findall raises for the path is error(path); the stdlib raises KeyError for "@".
    bad("xml_find_elements", {"xml_text": "<a><b/></a>", "path": "@"}, "path", "bare-attribute-key-error"),
    bad("xml_find_elements", {"xml_text": ENTITY_BOMB, "path": "x"}, "xml_text", "doctype-entity"),
    bad("xml_find_elements", {"xml_text": "<a><b></a>", "path": "b"}, "xml_text", "parse-error"),
    invalid("xml_find_elements", {"xml_text": "<a/>", "path": ""}, "path", "empty-path"),
    bad("ini_to_json", {"ini_text": "[a]\nk=1\n[a]\nk=2\n"}, "ini_text", "duplicate-section"),
    bad("ini_to_json", {"ini_text": "k = v\n"}, "ini_text", "missing-section-header"),
    bad("ini_to_json", {"ini_text": "[a]\nk=1\nk=2\n"}, "ini_text", "duplicate-key"),
    bad("toml_to_json", {"toml_text": "a = \n"}, "toml_text", "missing-value", contains="the text is not valid TOML 1.0"),
    bad("toml_to_json", {"toml_text": "a = 1\na = 2\n"}, "toml_text", "duplicate-key", contains="the text is not valid TOML 1.0"),
    bad("parse_url", {"url": "http://example.com:99999/"}, "url", "port-out-of-range"),
    bad("parse_url", {"url": "http://example.com:abc/"}, "url", "port-not-a-number"),
    bad("parse_url", {"url": "http://[::1/"}, "url", "unbalanced-ipv6-bracket"),
    bad("resolve_relative_url", {"base_url": "/relative/only", "reference": "x"}, "base_url", "base-without-scheme"),
    bad("parse_query_string", {"query": "a=1&" * 10000 + "a=1"}, "query", "too-many-fields"),
    bad("parse_dotenv_text", {"dotenv_text": "GOOD=1\nthis line is invalid\n"}, "dotenv_text", "invalid-line"),
    bad("parse_dotenv_text", {"dotenv_text": "1A=x\n"}, "dotenv_text", "key-starts-with-digit"),
    bad("base64_encode", {"text": "a€", "text_encoding": "ascii"}, "text", "ascii-unencodable"),
    bad("base64_encode", {"text": "€", "text_encoding": "latin_1"}, "text", "latin-1-unencodable"),
    invalid("base64_encode", {"text": "a", "text_encoding": "utf8"}, "text_encoding", "unknown-encoding"),
    bad("base64_decode", {"data": "ab+_"}, "data", "mixed-alphabets"),
    bad("base64_decode", {"data": "!!!!"}, "data", "invalid-characters"),
    bad("base64_decode", {"data": "Zm9vY"}, "data", "impossible-length"),
    bad("base64_decode", {"data": "__79", "url_safe": False}, "data", "url-safe-text-in-standard-mode"),
    bad("hex_encode", {"text": "é", "text_encoding": "ascii"}, "text", "ascii-unencodable"),
    invalid("hex_encode", {"text": "a", "separator": "dash"}, "separator", "unknown-separator"),
    bad("hex_decode", {"hex_text": "abc"}, "hex_text", "odd-digit-count"),
    bad("hex_decode", {"hex_text": "zz"}, "hex_text", "non-hex"),
    bad("hex_decode", {"hex_text": "0x0x41"}, "hex_text", "second-prefix"),
    invalid("url_encode", {"text": "a", "mode": "query"}, "mode", "unknown-mode"),
    bad("decode_jwt_payload", {"jwt_text": "a.b.c.d.e"}, "jwt_text", "encrypted-five-parts"),
    bad("decode_jwt_payload", {"jwt_text": "onlyonepart"}, "jwt_text", "one-part"),
    bad("decode_jwt_payload", {"jwt_text": "eyJhbGciOiJub25lIn0.WzFd."}, "jwt_text", "payload-not-object"),
    bad("decode_jwt_payload", {"jwt_text": "eyJhbGciOiJub25lIn0.!!!.x"}, "jwt_text", "payload-not-base64url"),
    invalid("decode_jwt_payload", {"jwt_text": ""}, "jwt_text", "empty"),
    bad("unescape_json_string", {"escaped": "\\x41"}, "escaped", "invalid-escape"),
    bad("unescape_json_string", {"escaped": "a\nb"}, "escaped", "raw-control-character"),
    bad("hash_text", {"text": "€", "text_encoding": "latin_1"}, "text", "latin-1-unencodable"),
    invalid("hash_text", {"text": "abc", "algorithm": "md4"}, "algorithm", "unknown-algorithm"),
    bad("hash_base64_content", {"data_base64": "!!!!"}, "data_base64", "invalid-base64"),
    bad("compute_hmac", {"message": "m", "key": "zz-not-hex", "key_format": "hex"}, "key", "invalid-hex-key"),
    bad("compute_hmac", {"message": "m", "key": "not*base64", "key_format": "base64"}, "key", "invalid-base64-key"),
    invalid("compute_hmac", {"message": "m", "key": ""}, "key", "empty-key"),
    invalid("verify_hash", {"text": "abc", "expected_digest": ""}, "expected_digest", "empty-digest"),
    bad("crc32_checksum", {"text": "€", "text_encoding": "ascii"}, "text", "ascii-unencodable"),
    bad("git_blob_hash", {"content": "€", "text_encoding": "ascii"}, "content", "ascii-unencodable"),
    invalid("assign_stable_bucket", {"key": "k", "buckets": 0}, "buckets", "zero-buckets"),
    invalid("assign_stable_bucket", {"key": "k", "buckets": 1000001}, "buckets", "over-max-buckets"),
    invalid("assign_stable_bucket", {"key": "", "buckets": 2}, "key", "empty-key"),
]


@pytest.mark.parametrize("case", SUCCESS_CASES)
def test_formats_encoding_rows_return_documented_output(tool_runner: ToolRunner, case: SuccessCase) -> None:
    tool_runner.check_success(case)


@pytest.mark.parametrize("case", FAILURE_CASES)
def test_formats_encoding_rows_reject_bad_input(tool_runner: ToolRunner, case: FailureCase) -> None:
    tool_runner.check_failure(case)


@pytest.mark.parametrize(
    ("key", "key_format"),
    [("zz-SECRET-KEY-zz", "hex"), ("SECRET*KEY*not*base64", "base64")],
    ids=["hex", "base64"],
)
def test_compute_hmac_errors_never_repeat_the_key(tool_runner: ToolRunner, key: str, key_format: str) -> None:
    # T-3 and INV-15: a rejected key must not leak into the error text the model and the traces see.
    arguments = {"message": "m", "key": key, "key_format": key_format}
    result = tool_runner.check_failure(FailureCase("compute_hmac", arguments, "key", "ToolExecutionError"))
    assert key not in result.output
    assert "SECRET" not in result.output


def test_parse_dotenv_text_error_omits_line_content(tool_runner: ToolRunner) -> None:
    # T-3: an invalid .env line may hold a secret, so the error names the line number only.
    arguments = {"dotenv_text": "GOOD=1\nthis line holds SECRETVALUE\n"}
    result = tool_runner.check_failure(FailureCase("parse_dotenv_text", arguments, "dotenv_text", "ToolExecutionError"))
    assert "SECRETVALUE" not in result.output
    assert "this line holds" not in result.output


@pytest.mark.parametrize("text_encoding", ["utf_8", "utf_16_le", "utf_16_be", "utf_32", "cp1252"])
@pytest.mark.parametrize("text", ["", "foobar", "Grüße, Zoë!", "\r\n\t~"])
def test_encoding_round_trips_restore_the_text(tool_runner: ToolRunner, text: str, text_encoding: str) -> None:
    # Encoding then decoding with the same codec must give the original text back, for Base64 and for hex.
    encoded = tool_runner.output("base64_encode", {"text": text, "text_encoding": text_encoding})["base64"]
    decoded = tool_runner.output("base64_decode", {"data": encoded, "text_encoding": text_encoding})
    assert decoded["text"] == text and decoded["is_text"] is True
    hexed = tool_runner.output("hex_encode", {"text": text, "text_encoding": text_encoding, "separator": "colon"})["hex"]
    unhexed = tool_runner.output("hex_decode", {"hex_text": hexed, "text_encoding": text_encoding})
    assert unhexed["text"] == text and unhexed["size_bytes"] == decoded["size_bytes"]
