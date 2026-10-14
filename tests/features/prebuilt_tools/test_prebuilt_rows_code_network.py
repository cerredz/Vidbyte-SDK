"""FILE: tests/features/prebuilt_tools/test_prebuilt_rows_code_network.py

PURPOSE: Exact-output and error-behavior cases for every Appendix A row of the code_analysis and network_addresses categories (A.30, A.31), run through FunctionTool.execute the way a model calls them.
ROLE IN CODEBASE: One of the AC-11 row files in tests/features/prebuilt_tools/; it uses the tool_runner fixture from conftest.py and the ok, bad, and invalid case builders from prebuilt_tool_harness.py.
ARCHITECTURE NOTE: Every expected value is hand-derived from the row text, a published fact (IPv4 and IPv6 CIDR arithmetic, POSIX shell quoting), or a different route (integer arithmetic for subnets); none is read back from the implementation.
FUNCTION INVENTORY: test_code_network_rows_return_documented_output checks SUCCESS_CASES; test_code_network_rows_reject_bad_input checks FAILURE_CASES; test_verify_python_syntax_reports_error_text checks the open error text; dotted_ipv4 and invalid_address build expectations.
COMMON MODIFICATION PATTERNS: Add an ok(...) or bad(...) entry beside the tool's existing cases; keep Python samples valid on both 3.11 and 3.12.
WHAT NOT TO DO IN THIS FILE: 1. Do not pin values that change between Python 3.11 and 3.12 (ipaddress flags of mapped or reserved ranges, SyntaxError wording, PEP 695 syntax); use ANY instead. 2. Do not add 100-level nesting, output-cap, or infeasible-enumeration inputs here; test_prebuilt_resource_bounds.py owns them.
KNOWN EDGE CASES: ast reports col_offset in UTF-8 bytes, so the find_python_name_usages case puts a two-byte character before a name; ast.walk visits breadth first, so the list_python_functions case puts a class before a function to tell source order apart; IPv6 hosts() skips only the subnet-router address.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md Appendix A.30 and A.31
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_rows_code_network.py
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

from tests.features.prebuilt_tools.prebuilt_tool_harness import ANY, FailureCase, SuccessCase, ToolRunner, bad, invalid, ok

PYTHON_VERSION = f"{sys.version_info.major}.{sys.version_info.minor}"


def dotted_ipv4(value: int) -> str:
    """Dotted-quad text of a 32-bit integer, built by shifting, not by ipaddress."""
    return ".".join(str((value >> shift) & 255) for shift in (24, 16, 8, 0))


SLASH_20_SUBNETS = [f"{dotted_ipv4((10 << 24) + index * 4096)}/20" for index in range(1000)]

FUNCTION_SOURCE = "\n".join(
    [
        "class Box:",
        "    async def fetch(self, /, key):",
        "        return key",
        "",
        "",
        "@functools.lru_cache(maxsize=None)",
        "def top(a, b=1, *args, c, **kw):",
        "    \"\"\"Doc.\"\"\"",
        "    def inner(x):",
        "        return x",
        "    return inner",
        "",
    ]
)
CLASS_SOURCE = "\n".join(
    [
        "import abc",
        "",
        "",
        "@dataclass(frozen=True)",
        "class Shape(Base, metaclass=abc.ABCMeta):",
        "    \"\"\"A shape.\"\"\"",
        "",
        "    def area(self):",
        "        return 0",
        "",
        "    class Inner:",
        "        pass",
        "",
        "    async def load(self):",
        "        pass",
        "",
        "",
        "def make():",
        "    class Local:",
        "        pass",
        "    return Local",
        "",
    ]
)
IMPORT_SOURCE = "\n".join(
    [
        "import json",
        "from collections import OrderedDict as OD, deque",
        "from . import sibling",
        "from ..pkg.mod import thing",
        "import xml.etree.ElementTree as ET",
        "",
    ]
)
SIGNATURE_SOURCE = "\n".join(
    [
        "class Repo:",
        "    async def get(self, key: str, *, default: int | None = None, **extra) -> dict:",
        "        \"\"\"Fetch one item.\"\"\"",
        "        return {}",
        "",
        "",
        "def helper(a, /, b=2, *rest: int) -> None:",
        "    pass",
        "",
    ]
)
TWO_RUN_SOURCE = "class A:\n    def run(self):\n        pass\n\n\nclass B:\n    def run(self):\n        pass\n"
USAGE_SOURCE = "\n".join(
    [
        "import os",
        "total = 0",
        "def add(total, step=total):",
        "    note = \"\u00e9\"; total += 1",
        "    del total",
        "    return obj.total + f(total=1)",
        "",
    ]
)
PYTHON_LINES_SOURCE = "# header comment\n\ndef f():\n    \"\"\"Docstring.\"\"\"\n    x = 1  # trailing\n\n    # inner comment\n    return x\n"
JAVASCRIPT_LINES_SOURCE = "// line comment\n/* block\n   still block */\nlet a = 1; // trailing\n\n/* one-line block */\nlet b = 2;\n"

REPO_GET_PARAMETERS = [
    {"name": "self", "kind": "positional_or_keyword", "annotation": None, "default": None},
    {"name": "key", "kind": "positional_or_keyword", "annotation": "str", "default": None},
    {"name": "default", "kind": "keyword_only", "annotation": "int | None", "default": "None"},
    {"name": "extra", "kind": "var_keyword", "annotation": None, "default": None},
]


def invalid_address(reason: str) -> dict[str, Any]:
    """The verify_ip_address output for a text that fails with `reason`."""
    return {"valid": False, "version": None, "compressed": None, "exploded": None, "reason": reason}


SUCCESS_CASES = [
    # A.30 code_analysis
    ok(
        "verify_python_syntax",
        {"source": "x = 1\n"},
        {"valid": True, "error": None, "line": None, "column": None, "python_version": PYTHON_VERSION},
        "valid",
    ),
    ok("verify_python_syntax", {"source": ""}, {"valid": True, "error": None, "line": None, "column": None, "python_version": PYTHON_VERSION}, "empty"),
    ok(
        "verify_python_syntax",
        {"source": "x = (1,\n"},
        {"valid": False, "error": ANY, "line": 1, "column": 5, "python_version": PYTHON_VERSION},
        "unclosed-bracket",
    ),
    ok(
        "verify_python_syntax",
        {"source": "x = 1\u0000"},
        {"valid": False, "error": ANY, "line": ANY, "column": ANY, "python_version": PYTHON_VERSION},
        "null-character",
    ),
    ok(
        "list_python_functions",
        {"source": FUNCTION_SOURCE},
        {
            "functions": [
                {
                    "name": "fetch",
                    "qualified_name": "Box.fetch",
                    "line": 2,
                    "end_line": 3,
                    "is_async": True,
                    "parameters": ["self", "key"],
                    "decorators": [],
                    "has_docstring": False,
                },
                {
                    "name": "top",
                    "qualified_name": "top",
                    "line": 7,
                    "end_line": 11,
                    "is_async": False,
                    "parameters": ["a", "b", "*args", "c", "**kw"],
                    "decorators": ["functools.lru_cache(maxsize=None)"],
                    "has_docstring": True,
                },
                {
                    "name": "inner",
                    "qualified_name": "top.<locals>.inner",
                    "line": 9,
                    "end_line": 10,
                    "is_async": False,
                    "parameters": ["x"],
                    "decorators": [],
                    "has_docstring": False,
                },
            ],
            "count": 3,
        },
        "source-order-qualified-names",
    ),
    ok("list_python_functions", {"source": "x = 1\n"}, {"functions": [], "count": 0}, "no-functions"),
    ok(
        "list_python_classes",
        {"source": CLASS_SOURCE},
        {
            "classes": [
                {
                    "name": "Shape",
                    "qualified_name": "Shape",
                    "line": 5,
                    "end_line": 15,
                    "bases": ["Base", "metaclass=abc.ABCMeta"],
                    "methods": ["area", "load"],
                    "decorators": ["dataclass(frozen=True)"],
                    "has_docstring": True,
                },
                {
                    "name": "Inner",
                    "qualified_name": "Shape.Inner",
                    "line": 11,
                    "end_line": 12,
                    "bases": [],
                    "methods": [],
                    "decorators": [],
                    "has_docstring": False,
                },
                {
                    "name": "Local",
                    "qualified_name": "make.<locals>.Local",
                    "line": 19,
                    "end_line": 20,
                    "bases": [],
                    "methods": [],
                    "decorators": [],
                    "has_docstring": False,
                },
            ],
            "count": 3,
        },
        "bases-methods-nesting",
    ),
    ok(
        "list_python_imports",
        {"source": IMPORT_SOURCE},
        {
            "imports": [
                {"module": ANY, "names": ANY, "line": 1, "from_import": False, "level": 0},
                {"module": "collections", "names": ["OrderedDict as OD", "deque"], "line": 2, "from_import": True, "level": 0},
                {"module": None, "names": ["sibling"], "line": 3, "from_import": True, "level": 1},
                {"module": "pkg.mod", "names": ["thing"], "line": 4, "from_import": True, "level": 2},
                {"module": ANY, "names": ANY, "line": 5, "from_import": False, "level": 0},
            ],
            "modules": ["collections", "json", "xml"],
        },
        "relative-and-aliased",
    ),
    ok(
        "count_lines_of_code",
        {"source": PYTHON_LINES_SOURCE},
        {"total_lines": 8, "code_lines": 4, "comment_lines": 2, "blank_lines": 2},
        "python-default-docstring-is-code",
    ),
    ok(
        "count_lines_of_code",
        {"source": JAVASCRIPT_LINES_SOURCE, "language": "javascript"},
        {"total_lines": 7, "code_lines": 2, "comment_lines": 4, "blank_lines": 1},
        "javascript-block-comments",
    ),
    ok(
        "count_lines_of_code",
        {"source": "x = 1\r\n\r\n# c\r\n"},
        {"total_lines": 3, "code_lines": 1, "comment_lines": 1, "blank_lines": 1},
        "crlf-lines",
    ),
    ok("count_lines_of_code", {"source": ""}, {"total_lines": 0, "code_lines": 0, "comment_lines": 0, "blank_lines": 0}, "empty"),
    ok(
        "get_python_function_signature",
        {"source": SIGNATURE_SOURCE, "name": "helper"},
        {
            "signature": "def helper(a, /, b=2, *rest: int) -> None",
            "parameters": [
                {"name": "a", "kind": "positional_only", "annotation": None, "default": None},
                {"name": "b", "kind": "positional_or_keyword", "annotation": None, "default": "2"},
                {"name": "rest", "kind": "var_positional", "annotation": "int", "default": None},
            ],
            "returns": "None",
            "docstring": None,
            "line": 7,
        },
        "plain-function",
    ),
    ok(
        "get_python_function_signature",
        {"source": SIGNATURE_SOURCE, "name": "Repo.get"},
        {"signature": ANY, "parameters": REPO_GET_PARAMETERS, "returns": "dict", "docstring": "Fetch one item.", "line": 2},
        "qualified-async-method",
    ),
    ok(
        "get_python_function_signature",
        {"source": SIGNATURE_SOURCE, "name": "get"},
        {"signature": ANY, "parameters": REPO_GET_PARAMETERS, "returns": "dict", "docstring": "Fetch one item.", "line": 2},
        "unique-bare-name",
    ),
    ok(
        "get_python_function_signature",
        {"source": TWO_RUN_SOURCE, "name": "B.run"},
        {
            "signature": ANY,
            "parameters": [{"name": "self", "kind": "positional_or_keyword", "annotation": None, "default": None}],
            "returns": None,
            "docstring": None,
            "line": 7,
        },
        "qualified-beats-ambiguous-bare",
    ),
    ok(
        "find_python_name_usages",
        {"source": USAGE_SOURCE, "name": "total"},
        {
            "usages": [
                {"line": 2, "column": 1, "context": "store"},
                {"line": 3, "column": 9, "context": "parameter"},
                {"line": 3, "column": 21, "context": "load"},
                {"line": 4, "column": 17, "context": "store"},
                {"line": 5, "column": 9, "context": "delete"},
                {"line": 6, "column": ANY, "context": "attribute"},
                {"line": 6, "column": 26, "context": "keyword"},
            ],
            "count": 7,
            "truncated": False,
        },
        "contexts-and-character-columns",
    ),
    ok(
        "find_python_name_usages",
        {"source": USAGE_SOURCE, "name": "add"},
        {"usages": [{"line": 3, "column": ANY, "context": "definition"}], "count": 1, "truncated": False},
        "definition",
    ),
    ok(
        "find_python_name_usages",
        {"source": "import os\nos.sep\n", "name": "os"},
        {"usages": [{"line": 1, "column": ANY, "context": "import"}, {"line": 2, "column": 1, "context": "load"}], "count": 2, "truncated": False},
        "import-and-load",
    ),
    ok(
        "python_literal_to_json",
        {"literal": "{'b': (1, 2), 'a': None, 3: True, 'f': 1.5}"},
        {"json": "{\"b\":[1,2],\"a\":null,\"3\":true,\"f\":1.5}"},
        "tuple-none-and-int-key",
    ),
    ok("python_literal_to_json", {"literal": "{9, 10}"}, {"json": "[10,9]"}, "set-sorted-by-json-text"),
    ok("python_literal_to_json", {"literal": "[{'b', 'a'}]"}, {"json": "[[\"a\",\"b\"]]"}, "nested-string-set"),
    ok(
        "shell_split_command",
        {"command": "ls -la 'a b' \"c d\" e\\ f"},
        {"arguments": ["ls", "-la", "a b", "c d", "e f"], "count": 5},
        "quotes-and-escapes",
    ),
    ok("shell_split_command", {"command": "echo a # b"}, {"arguments": ["echo", "a", "#", "b"], "count": 4}, "no-comment-handling"),
    ok("shell_split_command", {"command": ""}, {"arguments": [], "count": 0}, "empty"),
    ok(
        "shell_quote_arguments",
        {"arguments": ["ls", "a b", "it's", "", "--flag=x"]},
        {"command": "ls 'a b' 'it'\"'\"'s' '' --flag=x"},
        "posix-quoting",
    ),
    # A.31 network_addresses
    ok(
        "verify_ip_address",
        {"address": "10.0.0.1"},
        {"valid": True, "version": 4, "compressed": "10.0.0.1", "exploded": "10.0.0.1", "reason": None},
        "ipv4",
    ),
    ok(
        "verify_ip_address",
        {"address": "2001:DB8::1"},
        {
            "valid": True,
            "version": 6,
            "compressed": "2001:db8::1",
            "exploded": "2001:0db8:0000:0000:0000:0000:0000:0001",
            "reason": None,
        },
        "ipv6-forms",
    ),
    ok("verify_ip_address", {"address": "192.168.001.1"}, invalid_address("ipv4_leading_zero"), "leading-zero"),
    ok("verify_ip_address", {"address": "999.1.1.01"}, invalid_address("ipv4_leading_zero"), "leading-zero-before-range"),
    ok("verify_ip_address", {"address": "1.2.3"}, invalid_address("ipv4_wrong_part_count"), "three-parts"),
    ok("verify_ip_address", {"address": "1..2"}, invalid_address("ipv4_wrong_part_count"), "part-count-before-empty"),
    ok("verify_ip_address", {"address": "1..2.3"}, invalid_address("ipv4_empty_part"), "empty-part"),
    ok("verify_ip_address", {"address": "256.1.1.1"}, invalid_address("ipv4_octet_out_of_range"), "octet-range"),
    ok("verify_ip_address", {"address": "1.2.3.a"}, invalid_address("invalid_characters"), "letters"),
    ok("verify_ip_address", {"address": "1:2"}, invalid_address("invalid_ipv6"), "colon-means-ipv6"),
    ok(
        "cidr_network_details",
        {"cidr": "192.168.1.77/24"},
        {
            "network": "192.168.1.0/24",
            "network_address": "192.168.1.0",
            "broadcast_address": "192.168.1.255",
            "netmask": "255.255.255.0",
            "hostmask": "0.0.0.255",
            "prefix_length": 24,
            "total_addresses": "256",
            "usable_hosts": "254",
            "first_usable": "192.168.1.1",
            "last_usable": "192.168.1.254",
            "version": 4,
        },
        "host-bits-cleared",
    ),
    ok(
        "cidr_network_details",
        {"cidr": "10.0.0.5/31"},
        {
            "network": "10.0.0.4/31",
            "network_address": "10.0.0.4",
            "broadcast_address": "10.0.0.5",
            "netmask": "255.255.255.254",
            "hostmask": "0.0.0.1",
            "prefix_length": 31,
            "total_addresses": "2",
            "usable_hosts": "2",
            "first_usable": "10.0.0.4",
            "last_usable": "10.0.0.5",
            "version": 4,
        },
        "slash-31",
    ),
    ok(
        "cidr_network_details",
        {"cidr": "10.1.2.3"},
        {
            "network": "10.1.2.3/32",
            "network_address": "10.1.2.3",
            "broadcast_address": "10.1.2.3",
            "netmask": "255.255.255.255",
            "hostmask": "0.0.0.0",
            "prefix_length": 32,
            "total_addresses": "1",
            "usable_hosts": "1",
            "first_usable": "10.1.2.3",
            "last_usable": "10.1.2.3",
            "version": 4,
        },
        "bare-address",
    ),
    ok(
        "cidr_network_details",
        {"cidr": "2001:db8::/64"},
        {
            "network": "2001:db8::/64",
            "network_address": "2001:db8::",
            "broadcast_address": None,
            "netmask": "ffff:ffff:ffff:ffff::",
            "hostmask": "::ffff:ffff:ffff:ffff",
            "prefix_length": 64,
            "total_addresses": "18446744073709551616",
            "usable_hosts": "18446744073709551615",
            "first_usable": "2001:db8::1",
            "last_usable": "2001:db8::ffff:ffff:ffff:ffff",
            "version": 6,
        },
        "ipv6-no-broadcast",
    ),
    ok(
        "ip_in_networks",
        {"address": "10.1.2.3", "networks": ["10.0.0.0/8", "192.168.0.0/16", "10.1.2.0/24", "::/0", "10.1.2.9/25"]},
        {"contained": True, "matching_networks": ["10.0.0.0/8", "10.1.2.0/24", "10.1.2.0/25"], "most_specific": "10.1.2.0/25"},
        "longest-prefix",
    ),
    ok(
        "ip_in_networks",
        {"address": "8.8.8.8", "networks": ["10.0.0.0/8", "::/0"]},
        {"contained": False, "matching_networks": [], "most_specific": None},
        "no-match",
    ),
    ok(
        "split_cidr_into_subnets",
        {"cidr": "192.168.0.0/24", "new_prefix_length": 26},
        {"subnets": ["192.168.0.0/26", "192.168.0.64/26", "192.168.0.128/26", "192.168.0.192/26"], "count": "4", "truncated": False},
        "four-quarters",
    ),
    ok(
        "split_cidr_into_subnets",
        {"cidr": "192.168.0.0/24", "new_prefix_length": 24},
        {"subnets": ["192.168.0.0/24"], "count": "1", "truncated": False},
        "same-prefix",
    ),
    ok(
        "split_cidr_into_subnets",
        {"cidr": "10.0.0.0/8", "new_prefix_length": 20},
        {"subnets": SLASH_20_SUBNETS, "count": "4096", "truncated": True},
        "item-cap-1000",
    ),
    ok(
        "ip_range_to_cidrs",
        {"first_address": "192.168.0.1", "last_address": "192.168.0.10"},
        {"cidrs": ["192.168.0.1/32", "192.168.0.2/31", "192.168.0.4/30", "192.168.0.8/31", "192.168.0.10/32"], "count": 5},
        "uneven-range",
    ),
    ok("ip_range_to_cidrs", {"first_address": "10.0.0.0", "last_address": "10.0.0.255"}, {"cidrs": ["10.0.0.0/24"], "count": 1}, "aligned"),
    ok(
        "classify_ip_address",
        {"address": "127.0.0.1"},
        {
            "address": "127.0.0.1",
            "version": 4,
            "is_private": True,
            "is_global": False,
            "is_loopback": True,
            "is_link_local": False,
            "is_multicast": False,
            "is_reserved": False,
            "is_unspecified": False,
            "ipv4_mapped": None,
        },
        "loopback",
    ),
    ok(
        "classify_ip_address",
        {"address": "224.0.0.1"},
        {
            "address": "224.0.0.1",
            "version": 4,
            "is_private": False,
            "is_global": True,
            "is_loopback": False,
            "is_link_local": False,
            "is_multicast": True,
            "is_reserved": False,
            "is_unspecified": False,
            "ipv4_mapped": None,
        },
        "multicast",
    ),
    ok(
        "classify_ip_address",
        {"address": "10.0.0.1"},
        {
            "address": "10.0.0.1",
            "version": 4,
            "is_private": True,
            "is_global": False,
            "is_loopback": False,
            "is_link_local": False,
            "is_multicast": False,
            "is_reserved": False,
            "is_unspecified": False,
            "ipv4_mapped": None,
        },
        "private-ten",
    ),
    ok(
        "classify_ip_address",
        {"address": "::ffff:192.0.2.1"},
        {
            "address": ANY,
            "version": 6,
            "is_private": ANY,
            "is_global": ANY,
            "is_loopback": False,
            "is_link_local": False,
            "is_multicast": False,
            "is_reserved": ANY,
            "is_unspecified": False,
            "ipv4_mapped": "192.0.2.1",
        },
        "ipv4-mapped",
    ),
    ok(
        "convert_ip_address_integer",
        {"value": "192.168.1.1"},
        {"address": "192.168.1.1", "integer": "3232235777", "version": 4, "hex": "c0a80101"},
        "address-to-integer",
    ),
    ok(
        "convert_ip_address_integer",
        {"value": "3232235777"},
        {"address": "192.168.1.1", "integer": "3232235777", "version": 4, "hex": "c0a80101"},
        "integer-to-address",
    ),
    ok(
        "convert_ip_address_integer",
        {"value": "1", "version": "ipv6"},
        {"address": "::1", "integer": "1", "version": 6, "hex": "00000000000000000000000000000001"},
        "integer-to-ipv6-padded-hex",
    ),
    ok(
        "convert_ip_address_integer",
        {"value": "::1", "version": "ipv4"},
        {"address": "::1", "integer": "1", "version": 6, "hex": "00000000000000000000000000000001"},
        "address-reports-own-version",
    ),
    ok("convert_ip_address_integer", {"value": "0"}, {"address": "0.0.0.0", "integer": "0", "version": 4, "hex": "00000000"}, "zero"),
    ok("convert_ipv4_netmask", {"value": "255.255.255.0"}, {"prefix_length": 24, "netmask": "255.255.255.0", "hostmask": "0.0.0.255"}, "dotted"),
    ok("convert_ipv4_netmask", {"value": "/20"}, {"prefix_length": 20, "netmask": "255.255.240.0", "hostmask": "0.0.15.255"}, "slash"),
    ok("convert_ipv4_netmask", {"value": "0"}, {"prefix_length": 0, "netmask": "0.0.0.0", "hostmask": "255.255.255.255"}, "zero"),
    ok("convert_ipv4_netmask", {"value": "32"}, {"prefix_length": 32, "netmask": "255.255.255.255", "hostmask": "0.0.0.0"}, "thirty-two"),
]

FAILURE_CASES = [
    # A.30 code_analysis
    bad("list_python_functions", {"source": "def ("}, "source", "syntax-error"),
    bad("list_python_classes", {"source": "class :"}, "source", "syntax-error"),
    bad("list_python_imports", {"source": "import"}, "source", "syntax-error"),
    invalid("count_lines_of_code", {"source": "x", "language": "cobol"}, "language", "unknown-language"),
    bad("get_python_function_signature", {"source": SIGNATURE_SOURCE, "name": "missing"}, "name", "no-match"),
    bad("get_python_function_signature", {"source": TWO_RUN_SOURCE, "name": "run"}, "name", "ambiguous-bare-name"),
    bad("get_python_function_signature", {"source": "def (", "name": "f"}, "source", "syntax-error"),
    invalid("get_python_function_signature", {"source": "def f():\n    pass\n", "name": ""}, "name", "empty-name"),
    bad("find_python_name_usages", {"source": "x = (", "name": "x"}, "source", "syntax-error"),
    bad("python_literal_to_json", {"literal": "1j"}, "literal", "complex"),
    bad("python_literal_to_json", {"literal": "b'x'"}, "literal", "bytes"),
    bad("python_literal_to_json", {"literal": "{(1, 2): 3}"}, "literal", "tuple-key"),
    bad("python_literal_to_json", {"literal": "__import__('os')"}, "literal", "not-a-literal"),
    bad("python_literal_to_json", {"literal": "1e999"}, "literal", "infinite-float"),
    bad("python_literal_to_json", {"literal": "[1, 2"}, "literal", "unparseable"),
    bad("shell_split_command", {"command": "echo 'oops"}, "command", "unbalanced-quote"),
    invalid("shell_quote_arguments", {"arguments": []}, "arguments", "empty-list"),
    # A.31 network_addresses
    invalid("verify_ip_address", {"address": ""}, "address", "empty"),
    bad("cidr_network_details", {"cidr": "192.168.1.77/24", "strict": True}, "cidr", "strict-host-bits"),
    bad("cidr_network_details", {"cidr": "300.1.1.1/24"}, "cidr", "invalid"),
    bad("ip_in_networks", {"address": "10.0.0", "networks": ["10.0.0.0/8"]}, "address", "invalid-address"),
    bad("ip_in_networks", {"address": "10.0.0.1", "networks": ["10.0.0.0/8", "bogus"]}, "networks", "invalid-network"),
    invalid("ip_in_networks", {"address": "10.0.0.1", "networks": []}, "networks", "empty-networks"),
    bad("split_cidr_into_subnets", {"cidr": "192.168.0.0/24", "new_prefix_length": 20}, "new_prefix_length", "shorter-prefix"),
    bad("split_cidr_into_subnets", {"cidr": "192.168.0.0/24", "new_prefix_length": 33}, "new_prefix_length", "beyond-ipv4"),
    invalid("split_cidr_into_subnets", {"cidr": "::/0", "new_prefix_length": 129}, "new_prefix_length", "beyond-bound"),
    bad("ip_range_to_cidrs", {"first_address": "10.0.0.9", "last_address": "10.0.0.1"}, "last_address", "reversed"),
    bad("ip_range_to_cidrs", {"first_address": "10.0.0.1", "last_address": "::1"}, "last_address", "mixed-versions"),
    bad("classify_ip_address", {"address": "1.2.3"}, "address", "invalid"),
    bad("convert_ip_address_integer", {"value": "4294967296"}, "value", "ipv4-out-of-range"),
    bad("convert_ip_address_integer", {"value": "hello"}, "value", "neither"),
    invalid("convert_ip_address_integer", {"value": "1", "version": "ipv5"}, "version", "unknown-version"),
    bad("convert_ipv4_netmask", {"value": "255.0.255.0"}, "value", "non-contiguous"),
    bad("convert_ipv4_netmask", {"value": "33"}, "value", "prefix-too-long"),
    bad("convert_ipv4_netmask", {"value": "abc"}, "value", "unreadable"),
]


@pytest.mark.parametrize("case", SUCCESS_CASES)
def test_code_network_rows_return_documented_output(tool_runner: ToolRunner, case: SuccessCase) -> None:
    tool_runner.check_success(case)


@pytest.mark.parametrize("case", FAILURE_CASES)
def test_code_network_rows_reject_bad_input(tool_runner: ToolRunner, case: FailureCase) -> None:
    tool_runner.check_failure(case)


def test_verify_python_syntax_reports_error_text(tool_runner: ToolRunner) -> None:
    output = tool_runner.output("verify_python_syntax", {"source": "x = (1,\n"})
    assert isinstance(output["error"], str) and output["error"].strip(), output
