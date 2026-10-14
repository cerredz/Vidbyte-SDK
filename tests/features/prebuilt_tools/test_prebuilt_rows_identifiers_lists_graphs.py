"""FILE: tests/features/prebuilt_tools/test_prebuilt_rows_identifiers_lists_graphs.py

PURPOSE: Exact-output and error cases for every Appendix A row in the identifiers, lists, and graphs categories (A.23 to A.25), run through FunctionTool.execute the way a model calls them.
ROLE IN CODEBASE: Row-level acceptance tests (AC-11) for the prebuilt tool library; they reach tools through the session catalogue built in conftest.py and compare with values computed by hand or from published check-digit and UUID vectors.
ARCHITECTURE NOTE: Each case is a pytest.param built by the harness helpers ok, bad, and invalid. Graph inputs use many distinct node names inserted out of order, so a set-ordered or insertion-ordered tie-break gives a different answer than the documented code-point rule.
FUNCTION INVENTORY: test_identifiers_lists_graphs_rows_return_documented_output checks SUCCESS_CASES; test_identifiers_lists_graphs_rows_reject_bad_input checks FAILURE_CASES.
COMMON MODIFICATION PATTERNS: Add a row case as one ok, bad, or invalid entry beside the other cases of the same tool, and verify its expected value by a route that does not reuse the implementation.
WHAT NOT TO DO IN THIS FILE: 1. Do not compute expectations by calling vidbyte code; a copy of the implementation cannot catch its mistakes. 2. Do not import vidbyte.tools.toolsets or vidbyte.tools.builtins.prebuilt at module level; a missing feature must fail at setup, not at collection.
KNOWN EDGE CASES: Check digits come from published vectors (Luhn 79927398713, ISBN 978-0-306-40615-7, IBAN GB82 WEST 1234 5698 7654 32, GTIN 4006381333931) and the RFC 4122 name-based UUIDs of python.org. The two-step float chain in critical_path_schedule leaves a slack of about 3e-17, which the 1e-9 rule must still call critical.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md Appendix A.23, A.24, A.25 and §9.2
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_rows_identifiers_lists_graphs.py
"""

from __future__ import annotations

import pytest

from tests.features.prebuilt_tools.prebuilt_tool_harness import FailureCase, SuccessCase, ToolRunner, bad, invalid, ok

LONG_DOMAIN = ".".join(["b" * 63, "c" * 63, "d" * 63, "e" * 61])
DNS_NAMESPACE_UUID = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"


def frequency(item: str, count: int) -> dict[str, object]:
    """One entry of a frequencies list."""
    return {"item": item, "count": count}


def task_row(task: str, earliest_start: float, latest_start: float, duration: float, critical: bool) -> dict[str, object]:
    """One critical_path_schedule entry built from its start times and duration."""
    return {
        "task": task,
        "earliest_start": earliest_start,
        "earliest_finish": earliest_start + duration,
        "latest_start": latest_start,
        "latest_finish": latest_start + duration,
        "slack": latest_start - earliest_start,
        "critical": critical,
    }


IDENTIFIER_SUCCESS_CASES = [
    ok("verify_luhn_checksum", {"number": "79927398713"}, {"valid": True, "digit_count": 11, "expected_check_digit": 3}, "published-valid"),
    ok("verify_luhn_checksum", {"number": "7992-7398 710"}, {"valid": False, "digit_count": 11, "expected_check_digit": 3}, "separators-wrong-digit"),
    ok("verify_luhn_checksum", {"number": "4539 1488 0343 6467"}, {"valid": True, "digit_count": 16, "expected_check_digit": 7}, "card-16"),
    ok("verify_luhn_checksum", {"number": "12"}, {"valid": False, "digit_count": 2, "expected_check_digit": 8}, "two-digit-minimum"),
    ok("verify_isbn", {"isbn": "978-0-306-40615-7"}, {"valid": True, "isbn10": "0306406152", "isbn13": "9780306406157", "input_length": 13}, "isbn13-978"),
    ok("verify_isbn", {"isbn": "0 306 40615 2"}, {"valid": True, "isbn10": "0306406152", "isbn13": "9780306406157", "input_length": 10}, "isbn10-spaces"),
    ok("verify_isbn", {"isbn": "0-8044-2957-X"}, {"valid": True, "isbn10": "080442957X", "isbn13": "9780804429573", "input_length": 10}, "isbn10-x"),
    ok("verify_isbn", {"isbn": "979-10-90636-07-1"}, {"valid": True, "isbn10": None, "isbn13": "9791090636071", "input_length": 13}, "isbn13-979"),
    ok("verify_isbn", {"isbn": "978-0-306-40615-8"}, {"valid": False, "isbn10": None, "isbn13": None, "input_length": 13}, "wrong-check"),
    ok("verify_isbn", {"isbn": "12345"}, {"valid": False, "isbn10": None, "isbn13": None, "input_length": 5}, "wrong-length"),
    ok(
        "verify_iban",
        {"iban": "gb82 west 1234 5698 7654 32"},
        {"valid": True, "country_code": "GB", "check_digits": "82", "formatted": "GB82 WEST 1234 5698 7654 32"},
        "published-gb-lowercase",
    ),
    ok(
        "verify_iban",
        {"iban": "DE89370400440532013000"},
        {"valid": True, "country_code": "DE", "check_digits": "89", "formatted": "DE89 3704 0044 0532 0130 00"},
        "published-de-ungrouped",
    ),
    ok(
        "verify_iban",
        {"iban": "GB83 WEST 1234 5698 7654 32"},
        {"valid": False, "country_code": "GB", "check_digits": "83", "formatted": "GB83 WEST 1234 5698 7654 32"},
        "pattern-ok-mod97-fails",
    ),
    ok("verify_iban", {"iban": "GB82"}, {"valid": False, "country_code": None, "check_digits": None, "formatted": None}, "pattern-mismatch"),
    ok("verify_gtin_barcode", {"code": "4006381333931"}, {"valid": True, "digit_count": 13, "expected_check_digit": 1}, "ean13-published"),
    ok("verify_gtin_barcode", {"code": "4006-3813 33932"}, {"valid": False, "digit_count": 13, "expected_check_digit": 1}, "ean13-wrong-separators"),
    ok("verify_gtin_barcode", {"code": "036000291452"}, {"valid": True, "digit_count": 12, "expected_check_digit": 2}, "upc-a"),
    ok("verify_gtin_barcode", {"code": "96385074"}, {"valid": True, "digit_count": 8, "expected_check_digit": 4}, "ean8"),
    ok("verify_gtin_barcode", {"code": "10012345678902"}, {"valid": True, "digit_count": 14, "expected_check_digit": 2}, "gtin14"),
    ok("verify_gtin_barcode", {"code": "12345"}, {"valid": False, "digit_count": 5, "expected_check_digit": None}, "other-length"),
    ok(
        "verify_email_syntax",
        {"email": "john.doe+tag@example.com"},
        {"valid": True, "reason": None, "local_part": "john.doe+tag", "domain": "example.com"},
        "valid-atext",
    ),
    ok("verify_email_syntax", {"email": "a@example.xn--p1ai"}, {"valid": True, "reason": None, "local_part": "a", "domain": "example.xn--p1ai"}, "punycode-tld"),
    ok("verify_email_syntax", {"email": "jöhn@example.com"}, {"valid": False, "reason": "not_ascii", "local_part": "jöhn", "domain": "example.com"}, "not-ascii"),
    ok("verify_email_syntax", {"email": "jöhn@@x"}, {"valid": False, "reason": "not_ascii", "local_part": None, "domain": None}, "not-ascii-before-at-count"),
    ok("verify_email_syntax", {"email": "john.example.com"}, {"valid": False, "reason": "missing_at_sign", "local_part": None, "domain": None}, "missing-at"),
    ok("verify_email_syntax", {"email": "a@b@c.com"}, {"valid": False, "reason": "multiple_at_signs", "local_part": None, "domain": None}, "two-at"),
    ok(
        "verify_email_syntax",
        {"email": "a@" + LONG_DOMAIN},
        {"valid": False, "reason": "address_too_long", "local_part": "a", "domain": LONG_DOMAIN},
        "address-255",
    ),
    ok("verify_email_syntax", {"email": "@example.com"}, {"valid": False, "reason": "local_part_empty", "local_part": "", "domain": "example.com"}, "local-empty"),
    ok(
        "verify_email_syntax",
        {"email": "a" * 65 + "@example.com"},
        {"valid": False, "reason": "local_part_too_long", "local_part": "a" * 65, "domain": "example.com"},
        "local-65",
    ),
    ok(
        "verify_email_syntax",
        {"email": "john..doe@example.com"},
        {"valid": False, "reason": "local_part_invalid", "local_part": "john..doe", "domain": "example.com"},
        "double-dot",
    ),
    ok(
        "verify_email_syntax",
        {"email": "john@-example.com"},
        {"valid": False, "reason": "domain_label_invalid", "local_part": "john", "domain": "-example.com"},
        "label-hyphen",
    ),
    ok("verify_email_syntax", {"email": "john@localhost"}, {"valid": False, "reason": "domain_needs_two_labels", "local_part": "john", "domain": "localhost"}, "one-label"),
    ok(
        "verify_email_syntax",
        {"email": "john@example.c0m"},
        {"valid": False, "reason": "top_level_domain_invalid", "local_part": "john", "domain": "example.c0m"},
        "tld-digit",
    ),
    ok(
        "verify_url_syntax",
        {"url": "HTTPS://User:pw@Host.Example.COM:8080/a?q=1#f"},
        {"valid": True, "reason": None, "scheme": "https", "host": "host.example.com"},
        "userinfo-port-case",
    ),
    ok("verify_url_syntax", {"url": "http://[2001:DB8::1]:443/"}, {"valid": True, "reason": None, "scheme": "http", "host": "2001:db8::1"}, "ipv6-host"),
    ok("verify_url_syntax", {"url": "http://192.168.0.1:8080"}, {"valid": True, "reason": None, "scheme": "http", "host": "192.168.0.1"}, "ipv4-host"),
    ok(
        "verify_url_syntax",
        {"url": "ftp://files.example.org/x", "allowed_schemes": ["FTP"]},
        {"valid": True, "reason": None, "scheme": "ftp", "host": "files.example.org"},
        "allowed-scheme-case",
    ),
    ok(
        "verify_url_syntax",
        {"url": "ftp://example.com/a b"},
        {"valid": False, "reason": "whitespace_or_control", "scheme": "ftp", "host": "example.com"},
        "whitespace-before-scheme-check",
    ),
    ok("verify_url_syntax", {"url": "example.com/path"}, {"valid": False, "reason": "missing_scheme", "scheme": None, "host": None}, "no-scheme"),
    ok("verify_url_syntax", {"url": "ftp://example.com/"}, {"valid": False, "reason": "scheme_not_allowed", "scheme": "ftp", "host": "example.com"}, "ftp-default-list"),
    ok(
        "verify_url_syntax",
        {"url": "mailto:a@b.example", "allowed_schemes": ["mailto"]},
        {"valid": False, "reason": "missing_host", "scheme": "mailto", "host": None},
        "no-authority",
    ),
    ok("verify_url_syntax", {"url": "http:///path"}, {"valid": False, "reason": "missing_host", "scheme": "http", "host": None}, "empty-host"),
    ok(
        "verify_url_syntax",
        {"url": "http://exa_mple.com:99999/"},
        {"valid": False, "reason": "invalid_port", "scheme": "http", "host": "exa_mple.com"},
        "port-before-host-check",
    ),
    ok("verify_url_syntax", {"url": "http://-bad-.com/"}, {"valid": False, "reason": "invalid_host", "scheme": "http", "host": "-bad-.com"}, "label-hyphen"),
    ok(
        "verify_uuid",
        {"value": "886313E1-3B8A-5372-9B90-0C9AEE199E5D"},
        {"valid": True, "canonical": "886313e1-3b8a-5372-9b90-0c9aee199e5d", "version": 5, "is_rfc_4122": True},
        "upper-v5",
    ),
    ok(
        "verify_uuid",
        {"value": "{6FA459EA-EE8A-3CA4-894E-DB77E160355E}"},
        {"valid": True, "canonical": "6fa459ea-ee8a-3ca4-894e-db77e160355e", "version": 3, "is_rfc_4122": True},
        "braces-v3",
    ),
    ok(
        "verify_uuid",
        {"value": "urn:uuid:886313e1-3b8a-5372-9b90-0c9aee199e5d"},
        {"valid": True, "canonical": "886313e1-3b8a-5372-9b90-0c9aee199e5d", "version": 5, "is_rfc_4122": True},
        "urn",
    ),
    ok(
        "verify_uuid",
        {"value": "886313e13b8a53729b900c9aee199e5d"},
        {"valid": True, "canonical": "886313e1-3b8a-5372-9b90-0c9aee199e5d", "version": 5, "is_rfc_4122": True},
        "32-hex",
    ),
    ok(
        "verify_uuid",
        {"value": "00000000-0000-0000-0000-000000000000"},
        {"valid": True, "canonical": "00000000-0000-0000-0000-000000000000", "version": None, "is_rfc_4122": False},
        "nil-ncs-variant",
    ),
    ok(
        "verify_uuid",
        {"value": "886313e1-3b8a-5372-cb90-0c9aee199e5d"},
        {"valid": True, "canonical": "886313e1-3b8a-5372-cb90-0c9aee199e5d", "version": None, "is_rfc_4122": False},
        "microsoft-variant",
    ),
    ok("verify_uuid", {"value": "not-a-uuid"}, {"valid": False, "canonical": None, "version": None, "is_rfc_4122": False}, "not-uuid"),
    ok("generate_name_based_uuid", {"name": "python.org", "namespace": "dns"}, {"uuid": "886313e1-3b8a-5372-9b90-0c9aee199e5d"}, "dns-v5-default"),
    ok(
        "generate_name_based_uuid",
        {"name": "python.org", "namespace": "dns", "version": "v3"},
        {"uuid": "6fa459ea-ee8a-3ca4-894e-db77e160355e"},
        "dns-v3",
    ),
    ok(
        "generate_name_based_uuid",
        {"name": "python.org", "namespace": DNS_NAMESPACE_UUID, "version": "v5"},
        {"uuid": "886313e1-3b8a-5372-9b90-0c9aee199e5d"},
        "namespace-as-uuid",
    ),
    ok(
        "generate_name_based_uuid",
        {"name": "https://www.python.org/", "namespace": "url"},
        {"uuid": "5406f80d-92e9-51cd-a176-77445955e733"},
        "url-namespace",
    ),
    ok(
        "compare_semantic_versions",
        {"first": "1.0.0-alpha", "second": "1.0.0-alpha.1"},
        {"comparison": -1, "first_is_prerelease": True, "second_is_prerelease": True},
        "fewer-fields-first",
    ),
    ok(
        "compare_semantic_versions",
        {"first": "1.0.0-beta.11", "second": "1.0.0-beta.2"},
        {"comparison": 1, "first_is_prerelease": True, "second_is_prerelease": True},
        "numeric-identifiers",
    ),
    ok(
        "compare_semantic_versions",
        {"first": "1.0.0-alpha.beta", "second": "1.0.0-alpha.1"},
        {"comparison": 1, "first_is_prerelease": True, "second_is_prerelease": True},
        "alphanumeric-beats-numeric",
    ),
    ok(
        "compare_semantic_versions",
        {"first": "1.0.0-rc.1", "second": "1.0.0"},
        {"comparison": -1, "first_is_prerelease": True, "second_is_prerelease": False},
        "prerelease-before-release",
    ),
    ok(
        "compare_semantic_versions",
        {"first": "v2.0.0+build.1", "second": "2.0.0+other.9"},
        {"comparison": 0, "first_is_prerelease": False, "second_is_prerelease": False},
        "build-ignored-leading-v",
    ),
    ok(
        "compare_semantic_versions",
        {"first": "1.10.0", "second": "1.9.0"},
        {"comparison": 1, "first_is_prerelease": False, "second_is_prerelease": False},
        "numeric-minor",
    ),
]

LIST_SUCCESS_CASES = [
    ok(
        "count_item_frequencies",
        {"items": ["kiwi", "fig", "apple", "date", "fig", "kiwi", "cherry", "banana", "fig"]},
        {
            "total": 9,
            "distinct": 6,
            "frequencies": [
                frequency("fig", 3),
                frequency("kiwi", 2),
                frequency("apple", 1),
                frequency("date", 1),
                frequency("cherry", 1),
                frequency("banana", 1),
            ],
        },
        "ties-by-first-appearance",
    ),
    ok(
        "count_item_frequencies",
        {"items": ["Apple", "apple", "APPLE", "Banana", "banana", "cherry"], "case_sensitive": False},
        {"total": 6, "distinct": 3, "frequencies": [frequency("Apple", 3), frequency("Banana", 2), frequency("cherry", 1)]},
        "casefold-first-spelling",
    ),
    ok(
        "count_item_frequencies",
        {"items": ["Straße", "STRASSE", "strasse"], "case_sensitive": False},
        {"total": 3, "distinct": 1, "frequencies": [frequency("Straße", 3)]},
        "casefold-not-lower",
    ),
    ok(
        "count_item_frequencies",
        {"items": ["b", "a", "b", "c", "a", "b", "d"], "top": 2},
        {"total": 7, "distinct": 4, "frequencies": [frequency("b", 3), frequency("a", 2)]},
        "top-limits-list-not-counts",
    ),
    ok("count_item_frequencies", {"items": []}, {"total": 0, "distinct": 0, "frequencies": []}, "empty"),
    ok(
        "find_duplicate_items",
        {"items": ["x", "y", "x", "z", "y", "x", "w"]},
        {
            "duplicates": [{"item": "x", "count": 3, "indices": [0, 2, 5]}, {"item": "y", "count": 2, "indices": [1, 4]}],
            "duplicate_count": 2,
        },
        "first-appearance-order",
    ),
    ok(
        "find_duplicate_items",
        {"items": ["Foo", "bar", "FOO", "Bar", "baz"], "case_sensitive": False},
        {
            "duplicates": [{"item": "Foo", "count": 2, "indices": [0, 2]}, {"item": "bar", "count": 2, "indices": [1, 3]}],
            "duplicate_count": 2,
        },
        "case-insensitive",
    ),
    ok("find_duplicate_items", {"items": ["Foo", "FOO"]}, {"duplicates": [], "duplicate_count": 0}, "case-sensitive-default"),
    ok(
        "compare_two_lists",
        {"first": ["pear", "apple", "fig", "apple", "kiwi"], "second": ["kiwi", "grape", "pear", "lime", "grape"]},
        {
            "only_in_first": ["apple", "fig"],
            "only_in_second": ["grape", "lime"],
            "in_both": ["pear", "kiwi"],
            "only_in_first_count": 2,
            "only_in_second_count": 2,
            "in_both_count": 2,
        },
        "set-semantics-first-order",
    ),
    ok(
        "compare_two_lists",
        {"first": ["Apple", "banana"], "second": ["APPLE", "Cherry"], "case_sensitive": False},
        {
            "only_in_first": ["banana"],
            "only_in_second": ["Cherry"],
            "in_both": ["Apple"],
            "only_in_first_count": 1,
            "only_in_second_count": 1,
            "in_both_count": 1,
        },
        "case-insensitive",
    ),
    ok(
        "intersect_lists",
        {"lists": [["d", "a", "c", "b", "d"], ["b", "c", "d", "e"], ["c", "x", "d", "b"]]},
        {"common": ["d", "c", "b"], "count": 3},
        "first-list-order",
    ),
    ok(
        "intersect_lists",
        {"lists": [["Alpha", "beta"], ["ALPHA", "Gamma"], ["alpha"]], "case_sensitive": False},
        {"common": ["Alpha"], "count": 1},
        "case-insensitive",
    ),
    ok("intersect_lists", {"lists": [["Alpha"], ["alpha"]]}, {"common": [], "count": 0}, "case-sensitive-default"),
    ok("find_missing_integers", {"values": [7, 1, 2, 4]}, {"missing": [3, 5, 6], "count": 3, "truncated": False}, "default-bounds"),
    ok(
        "find_missing_integers",
        {"values": [5, 3, 3, 1], "start": 0, "end": 9},
        {"missing": [0, 2, 4, 6, 7, 8, 9], "count": 7, "truncated": False},
        "explicit-bounds",
    ),
    ok(
        "find_missing_integers",
        {"values": [-2, 2], "start": None, "end": None},
        {"missing": [-1, 0, 1], "count": 3, "truncated": False},
        "null-bounds-negative",
    ),
    ok(
        "find_missing_integers",
        {"values": [0, 2000]},
        {"missing": list(range(1, 1001)), "count": 1999, "truncated": True},
        "item-cap",
    ),
    ok(
        "compress_integer_ranges",
        {"values": [10, 5, 1, 2, 3, 3, 7, 8]},
        {
            "ranges": [{"start": 1, "end": 3}, {"start": 5, "end": 5}, {"start": 7, "end": 8}, {"start": 10, "end": 10}],
            "text": "1-3,5,7-8,10",
            "count": 4,
        },
        "sorted-distinct",
    ),
    ok(
        "compress_integer_ranges",
        {"values": [1, -1, -3, -2]},
        {"ranges": [{"start": -3, "end": -1}, {"start": 1, "end": 1}], "text": "-3--1,1", "count": 2},
        "negatives",
    ),
    ok("compress_integer_ranges", {"values": [42]}, {"ranges": [{"start": 42, "end": 42}], "text": "42", "count": 1}, "single"),
    ok("expand_integer_ranges", {"text": " 1-3 , 7 "}, {"values": [1, 2, 3, 7], "count": "4", "truncated": False}, "whitespace"),
    ok("expand_integer_ranges", {"text": "5,5,2-3"}, {"values": [5, 5, 2, 3], "count": "4", "truncated": False}, "token-order-duplicates"),
    ok("expand_integer_ranges", {"text": "-3--1,0"}, {"values": [-3, -2, -1, 0], "count": "4", "truncated": False}, "negatives"),
    ok(
        "expand_integer_ranges",
        {"text": "1-20000,5"},
        {"values": list(range(1, 10001)), "count": "20001", "truncated": True},
        "item-cap-full-count",
    ),
]

GRAPH_SUCCESS_CASES = [
    ok(
        "topological_sort",
        {"sources": ["b", "a", "a", "c", "e"], "targets": ["d", "c", "b", "d", "f"], "nodes": ["z", "m"]},
        {"order": ["a", "b", "c", "d", "e", "f", "m", "z"], "levels": [["a", "e", "m", "z"], ["b", "c", "f"], ["d"]]},
        "min-heap-order-differs-from-levels",
    ),
    ok("topological_sort", {"sources": [], "targets": [], "nodes": ["b", "a"]}, {"order": ["a", "b"], "levels": [["a", "b"]]}, "isolated-nodes"),
    ok("topological_sort", {"sources": [], "targets": []}, {"order": [], "levels": []}, "empty"),
    ok(
        "find_graph_cycle",
        {"sources": ["a", "c", "a", "b"], "targets": ["c", "a", "b", "a"]},
        {"has_cycle": True, "cycle": ["a", "b", "a"]},
        "sorted-neighbors",
    ),
    ok(
        "find_graph_cycle",
        {"sources": ["b", "a", "b", "c"], "targets": ["c", "b", "a", "a"]},
        {"has_cycle": True, "cycle": ["a", "b", "a"]},
        "start-from-smallest-node",
    ),
    ok(
        "find_graph_cycle",
        {"sources": ["q", "b", "p"], "targets": ["p", "c", "q"], "nodes": ["a"]},
        {"has_cycle": True, "cycle": ["p", "q", "p"]},
        "later-component",
    ),
    ok("find_graph_cycle", {"sources": ["k"], "targets": ["k"]}, {"has_cycle": True, "cycle": ["k", "k"]}, "self-loop"),
    ok(
        "find_graph_cycle",
        {"sources": ["a", "b", "a"], "targets": ["b", "c", "c"], "nodes": ["z"]},
        {"has_cycle": False, "cycle": []},
        "acyclic",
    ),
    ok(
        "shortest_path",
        {"sources": ["s", "s", "b", "a"], "targets": ["b", "a", "g", "g"], "start": "s", "goal": "g"},
        {"found": True, "path": ["s", "a", "g"], "hops": 2},
        "sorted-neighbors-tie",
    ),
    ok(
        "shortest_path",
        {"sources": ["x", "y"], "targets": ["y", "z"], "start": "z", "goal": "x", "directed": False},
        {"found": True, "path": ["z", "y", "x"], "hops": 2},
        "undirected",
    ),
    ok(
        "shortest_path",
        {"sources": ["x", "y"], "targets": ["y", "z"], "start": "z", "goal": "x"},
        {"found": False, "path": [], "hops": None},
        "directed-unreachable",
    ),
    ok("shortest_path", {"sources": ["s"], "targets": ["t"], "start": "s", "goal": "s"}, {"found": True, "path": ["s"], "hops": 0}, "start-is-goal"),
    ok(
        "shortest_weighted_path",
        {"sources": ["a", "c", "a", "b"], "targets": ["c", "d", "b", "d"], "weights": [1, 1, 1, 1], "start": "a", "goal": "d"},
        {"found": True, "path": ["a", "b", "d"], "total_weight": 2.0},
        "equal-weight-code-point-tie",
    ),
    ok(
        "shortest_weighted_path",
        {"sources": ["a", "a", "b"], "targets": ["z", "b", "z"], "weights": [2, 1, 1], "start": "a", "goal": "z"},
        {"found": True, "path": ["a", "b", "z"], "total_weight": 2.0},
        "tie-not-by-hops",
    ),
    ok(
        "shortest_weighted_path",
        {"sources": ["a", "a", "b", "a"], "targets": ["b", "b", "c", "c"], "weights": [5, 2, 1, 4], "start": "a", "goal": "c"},
        {"found": True, "path": ["a", "b", "c"], "total_weight": 3.0},
        "lightest-parallel-edge",
    ),
    ok(
        "shortest_weighted_path",
        {"sources": ["a", "b", "a"], "targets": ["b", "c", "c"], "weights": [0.1, 0.2, 0.5], "start": "a", "goal": "c"},
        {"found": True, "path": ["a", "b", "c"], "total_weight": 0.3},
        "float-weights",
    ),
    ok(
        "shortest_weighted_path",
        {"sources": ["p"], "targets": ["q"], "weights": [2.5], "start": "q", "goal": "p", "directed": False},
        {"found": True, "path": ["q", "p"], "total_weight": 2.5},
        "undirected",
    ),
    ok(
        "shortest_weighted_path",
        {"sources": ["p", "r"], "targets": ["q", "s"], "weights": [1, 1], "start": "p", "goal": "s"},
        {"found": False, "path": [], "total_weight": None},
        "unreachable",
    ),
    ok(
        "connected_components",
        {"sources": ["b", "d", "e", "x"], "targets": ["a", "c", "d", "w"], "nodes": ["q", "m"]},
        {"components": [["c", "d", "e"], ["a", "b"], ["w", "x"], ["m"], ["q"]], "count": 5},
        "size-then-first-node",
    ),
    ok("connected_components", {"sources": [], "targets": []}, {"components": [], "count": 0}, "empty"),
    ok(
        "critical_path_schedule",
        {
            "tasks": ["design", "build", "test", "docs", "ship"],
            "durations": [3, 5, 2, 1, 1],
            "dependency_sources": ["design", "build", "design", "test", "docs"],
            "dependency_targets": ["build", "test", "docs", "ship", "ship"],
        },
        {
            "project_duration": 11.0,
            "critical_path": ["design", "build", "test", "ship"],
            "schedule": [
                task_row("design", 0.0, 0.0, 3.0, True),
                task_row("build", 3.0, 3.0, 5.0, True),
                task_row("docs", 3.0, 9.0, 1.0, False),
                task_row("test", 8.0, 8.0, 2.0, True),
                task_row("ship", 10.0, 10.0, 1.0, True),
            ],
        },
        "slack-on-docs",
    ),
    ok(
        "critical_path_schedule",
        {
            "tasks": ["a", "c", "b", "d"],
            "durations": [2, 3, 3, 1],
            "dependency_sources": ["a", "a", "b", "c"],
            "dependency_targets": ["b", "c", "d", "d"],
        },
        {
            "project_duration": 6.0,
            "critical_path": ["a", "b", "d"],
            "schedule": [
                task_row("a", 0.0, 0.0, 2.0, True),
                task_row("b", 2.0, 2.0, 3.0, True),
                task_row("c", 2.0, 2.0, 3.0, True),
                task_row("d", 5.0, 5.0, 1.0, True),
            ],
        },
        "smallest-name-at-choice",
    ),
    ok(
        "critical_path_schedule",
        {"tasks": ["x", "y"], "durations": [0.1, 0.2], "dependency_sources": ["x"], "dependency_targets": ["y"]},
        {
            "project_duration": 0.3,
            "critical_path": ["x", "y"],
            "schedule": [task_row("x", 0.0, 0.0, 0.1, True), task_row("y", 0.1, 0.1, 0.2, True)],
        },
        "float-slack-tolerance",
    ),
    ok(
        "critical_path_schedule",
        {"tasks": ["solo"], "durations": [4]},
        {"project_duration": 4.0, "critical_path": ["solo"], "schedule": [task_row("solo", 0.0, 0.0, 4.0, True)]},
        "single-task",
    ),
]

SUCCESS_CASES = IDENTIFIER_SUCCESS_CASES + LIST_SUCCESS_CASES + GRAPH_SUCCESS_CASES

FAILURE_CASES = [
    bad("verify_luhn_checksum", {"number": "7992a398713"}, "number", "letter"),
    bad("verify_luhn_checksum", {"number": "5"}, "number", "one-digit"),
    bad("verify_luhn_checksum", {"number": "- -"}, "number", "no-digits"),
    invalid("verify_luhn_checksum", {"number": ""}, "number", "empty"),
    invalid("verify_isbn", {"isbn": "9" * 201}, "isbn", "over-phrase-cap"),
    invalid("verify_iban", {"iban": ""}, "iban", "empty"),
    bad("verify_gtin_barcode", {"code": "4006381333a31"}, "code", "letter"),
    invalid("verify_email_syntax", {"email": ""}, "email", "empty"),
    invalid("verify_url_syntax", {"url": "http://example.com", "allowed_schemes": []}, "allowed_schemes", "no-schemes"),
    invalid("verify_uuid", {"value": ""}, "value", "empty"),
    bad("generate_name_based_uuid", {"name": "python.org", "namespace": "bogus"}, "namespace", "unknown-namespace"),
    invalid("generate_name_based_uuid", {"name": "python.org", "namespace": "dns", "version": "v4"}, "version", "random-version"),
    bad("compare_semantic_versions", {"first": "1.2", "second": "1.2.0"}, "first", "two-fields"),
    bad("compare_semantic_versions", {"first": "1.2.0", "second": "01.2.3"}, "second", "leading-zero"),
    bad("compare_semantic_versions", {"first": "vv1.0.0", "second": "1.0.0"}, "first", "two-v"),
    invalid("count_item_frequencies", {"items": ["a"], "top": 0}, "top", "top-zero"),
    invalid("count_item_frequencies", {"items": ["a"], "top": 1001}, "top", "top-over-cap"),
    invalid("find_duplicate_items", {"items": "a,b"}, "items", "text-not-list"),
    invalid("compare_two_lists", {"first": ["a"], "second": [1]}, "second", "number-item"),
    bad("intersect_lists", {"lists": [["a"] * 5001, ["a"] * 5000]}, "lists", "total-items-over-cap"),
    invalid("intersect_lists", {"lists": [["a"]]}, "lists", "one-list"),
    bad("find_missing_integers", {"values": [1, 2], "start": 5, "end": 4}, "end", "end-before-start"),
    bad("find_missing_integers", {"values": [1], "start": 0, "end": 20_000_000}, "end", "span-over-cap"),
    invalid("find_missing_integers", {"values": []}, "values", "empty-values"),
    invalid("find_missing_integers", {"values": [10**15 + 1]}, "values", "magnitude"),
    invalid("compress_integer_ranges", {"values": []}, "values", "empty-values"),
    bad("expand_integer_ranges", {"text": "3-1"}, "text", "descending"),
    bad("expand_integer_ranges", {"text": "1-2-3"}, "text", "bad-token"),
    bad("expand_integer_ranges", {"text": "1,x"}, "text", "letter"),
    bad("expand_integer_ranges", {"text": "1000000000000001"}, "text", "magnitude"),
    bad("topological_sort", {"sources": ["a", "b", "c"], "targets": ["b", "c", "a"]}, "sources", "cycle"),
    bad("topological_sort", {"sources": ["a"], "targets": ["a"]}, "sources", "self-loop"),
    bad("topological_sort", {"sources": ["a", "b"], "targets": ["c"]}, "targets", "length-mismatch"),
    invalid("topological_sort", {"sources": [""], "targets": ["a"]}, "sources", "empty-name"),
    bad("find_graph_cycle", {"sources": ["a"], "targets": []}, "targets", "length-mismatch"),
    bad("shortest_path", {"sources": ["a"], "targets": ["b"], "start": "zz", "goal": "b"}, "start", "unknown-start"),
    bad("shortest_path", {"sources": ["a"], "targets": ["b"], "start": "a", "goal": "zz"}, "goal", "unknown-goal"),
    bad("shortest_path", {"sources": ["a", "b"], "targets": ["b"], "start": "a", "goal": "b"}, "targets", "length-mismatch"),
    bad("shortest_weighted_path", {"sources": ["a"], "targets": ["b"], "weights": [-1], "start": "a", "goal": "b"}, "weights", "negative"),
    bad("shortest_weighted_path", {"sources": ["a"], "targets": ["b"], "weights": [1, 2], "start": "a", "goal": "b"}, "weights", "weights-length"),
    bad("shortest_weighted_path", {"sources": ["a"], "targets": ["b"], "weights": [1], "start": "q", "goal": "b"}, "start", "unknown-start"),
    bad("shortest_weighted_path", {"sources": ["a"], "targets": ["b"], "weights": [1], "start": "a", "goal": "q"}, "goal", "unknown-goal"),
    bad("connected_components", {"sources": [], "targets": ["a"]}, "targets", "length-mismatch"),
    bad("critical_path_schedule", {"tasks": ["a", "b", "a"], "durations": [1, 1, 1]}, "tasks", "duplicate-task"),
    bad("critical_path_schedule", {"tasks": ["a", "b"], "durations": [1]}, "durations", "durations-length"),
    bad("critical_path_schedule", {"tasks": ["a", "b"], "durations": [1, -1]}, "durations", "negative-duration"),
    bad(
        "critical_path_schedule",
        {"tasks": ["a", "b"], "durations": [1, 1], "dependency_sources": ["a"], "dependency_targets": ["zz"]},
        "dependency_targets",
        "unknown-target-task",
    ),
    bad(
        "critical_path_schedule",
        {"tasks": ["a", "b"], "durations": [1, 1], "dependency_sources": ["zz"], "dependency_targets": ["a"]},
        "dependency_targets",
        "unknown-source-task",
    ),
    bad(
        "critical_path_schedule",
        {"tasks": ["a", "b"], "durations": [1, 1], "dependency_sources": ["a", "b"], "dependency_targets": ["b"]},
        "dependency_targets",
        "dependency-length",
    ),
    bad(
        "critical_path_schedule",
        {"tasks": ["a", "b"], "durations": [1, 1], "dependency_sources": ["a", "b"], "dependency_targets": ["b", "a"]},
        "dependency_sources",
        "cycle",
    ),
    invalid("critical_path_schedule", {"tasks": [], "durations": []}, "tasks", "no-tasks"),
]


@pytest.mark.parametrize("case", SUCCESS_CASES)
def test_identifiers_lists_graphs_rows_return_documented_output(tool_runner: ToolRunner, case: SuccessCase) -> None:
    tool_runner.check_success(case)


@pytest.mark.parametrize("case", FAILURE_CASES)
def test_identifiers_lists_graphs_rows_reject_bad_input(tool_runner: ToolRunner, case: FailureCase) -> None:
    tool_runner.check_failure(case)

