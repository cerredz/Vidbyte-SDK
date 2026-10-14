"""FILE: tests/features/prebuilt_tools/test_prebuilt_rows_geometry_bits_markdown.py

PURPOSE: Exact-output and error-behavior cases for every Appendix A row of the geometry, bits_bytes, and markdown_html categories (20 tools), called through FunctionTool.execute the way a model calls them.
ROLE IN CODEBASE: Row-level proof of AC-11 for spec Appendix A.26, A.27, and A.28; uses the tool_runner fixture from conftest.py and the case builders in prebuilt_tool_harness.py.
ARCHITECTURE NOTE: Every expected value was computed without the implementation: geometry by unit-vector algebra (a different route from the haversine and bearing formulas) cross-checked against the classic formulas, rounding by Decimal(repr(x)) under spec §9.2 item 17, bit patterns and sizes by hand.
FUNCTION INVENTORY: SUCCESS_CASES and FAILURE_CASES are the parametrized tables; test_geometry_bits_markdown_rows_return_documented_output and test_geometry_bits_markdown_rows_reject_bad_input check them; test_fenced_code_block_code_and_lines checks the exact code and fence lines of extract_fenced_code_blocks on a document that ends with a line break; test_malformed_html_table_never_raises checks the HTML parser rule and the column names of a table with no header row.
COMMON MODIFICATION PATTERNS: Add a row case as one ok(...), bad(...), or invalid(...) entry with a hand-computed expectation and a label that says what it proves.
WHAT NOT TO DO IN THIS FILE: 1. Do not compute expectations by calling the tool functions or copying their algorithm; use a different route. 2. Do not add over-output-cap cases here; the resource-bounds module owns INV-20.
KNOWN EDGE CASES: decimal_degrees_to_dms must round 0.000875 degrees to 3.2 arc-seconds, while float rounding of 0.000875 * 3600 gives 3.1. Spec r4 fixes the setext heading line (its text line, not the underline), the autolink text (the URL between the angle brackets), and the fenced block lines (the fence lines; an unclosed block ends at the last line), so none of them is left open.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md Appendix A.26, A.27, A.28 and §9.2
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_rows_geometry_bits_markdown.py
"""

from __future__ import annotations

import math

import pytest

from tests.features.prebuilt_tools.prebuilt_tool_harness import FailureCase, SuccessCase, ToolRunner, bad, invalid, ok

EARTH_RADIUS_KILOMETERS = 6371.0088
QUARTER_CIRCLE_KILOMETERS = math.pi / 2 * EARTH_RADIUS_KILOMETERS
TEN_DEGREES_KILOMETERS = math.pi / 18 * EARTH_RADIUS_KILOMETERS
METERS_PER_MILE = 1609.344
LONDON_NEW_YORK = {"latitude1": 51.5007, "longitude1": -0.1246, "latitude2": 40.6892, "longitude2": -74.0445}
SQUARE_X = [0.0, 1.0, 1.0, 0.0]
SQUARE_Y = [0.0, 0.0, 1.0, 1.0]
NOTCHED_X = [0.0, 3.0, 3.0, 2.0, 2.0, 1.0, 1.0, 0.0]
NOTCHED_Y = [0.0, 0.0, 3.0, 3.0, 1.0, 1.0, 3.0, 3.0]
NO_FLAGS = {"setuid": False, "setgid": False, "sticky": False}

HEADINGS_MARKDOWN = "\n".join(
    [
        "# Hello World!",
        "Some text.",
        "## Setup & Install ##",
        "",
        "```",
        "# not a heading",
        "```",
        "### Hello World!",
        "",
        "Plain Title",
        "===========",
        "",
        "####### seven hashes",
        "",
        "###### Six",
        "",
    ]
)
TASKS_MARKDOWN = "\n".join(
    [
        "- [ ] write tests",
        "- [x] read spec",
        "  * [X] nested upper",
        "1. [ ] numbered",
        "2) [x] paren",
        "- [] not a task",
        "-[ ] no space",
        "```",
        "- [ ] fenced",
        "```",
        "",
    ]
)
TABLE_MARKDOWN = "\n".join(
    [
        "| Name | Qty | Note |",
        "|:-----|:---:|-----:|",
        "| apple | 3 | a \\| b |",
        "| pear |",
        "| fig | 1 | x | extra |",
        "",
    ]
)
TWO_TABLES_MARKDOWN = "\n".join(
    ["| a | a | b |", "|---|---|---|", "| 1 | 2 | 3 |", "", "Between the tables.", "", "| x |", "| --- |", "| y |", ""]
)
LINKS_MARKDOWN = "\n".join(
    [
        "See [Docs](https://example.com/docs \"Guide\") and ![Logo](img/logo.png).",
        "Auto <https://auto.example.org/x> link.",
        "Ref [Home][HOME] and [missing][nope].",
        "```",
        "[x](http://fenced.example)",
        "```",
        "[home]: https://home.example \"Home Page\"",
        "",
    ]
)
CODE_MARKDOWN = "\n".join(
    ["Intro", "```Python", "print(\"hi\")", "```", "~~~~ js extra words", "let a = 1;", "~~~~", "```", "plain", "unclosed"]
)
HTML_TABLE = "\n".join(
    [
        "<table>",
        " <tr><th>Name</th><th>Age</th></tr>",
        " <tr><td> Ann   Lee </td><td>30</td></tr>",
        " <tr><td colspan=\"2\">wide</td></tr>",
        "</table>",
    ]
)
HTML_NESTED_TABLES = "".join(
    [
        "<table><tr><th>A</th></tr><tr><td>x <table><tr><td>in</td></tr></table></td></tr></table>",
        "<p>between</p>",
        "<table><tr><td>z</td></tr></table>",
    ]
)
HTML_LINKS = "\n".join(
    [
        "<p><a href=\"/docs/intro\" rel=\"next\">  Intro",
        "   Page </a> and <a href=\"https://x.org/a?b=1&amp;c=2\">X</a></p>",
    ]
)


def permissions(octal: str, symbolic: str, **flags: bool) -> dict[str, object]:
    """Expected convert_unix_permissions output, with the three triples cut from the symbolic text."""
    return {"octal": octal, "symbolic": symbolic, "owner": symbolic[0:3], "group": symbolic[3:6], "others": symbolic[6:9], **NO_FLAGS, **flags}


def dms(text: str, degrees: int, minutes: int, seconds: float, hemisphere: str) -> dict[str, object]:
    """Expected decimal_degrees_to_dms output."""
    return {"dms": text, "degrees": degrees, "minutes": minutes, "seconds": seconds, "hemisphere": hemisphere}


SUCCESS_CASES = [
    # A.26 haversine_distance: quarter circle on the equator, pole to pole, a published city pair, units.
    ok("haversine_distance", {"latitude1": 0, "longitude1": 0, "latitude2": 0, "longitude2": 90}, {"distance": QUARTER_CIRCLE_KILOMETERS, "unit": "kilometer"}, "equator-quarter-circle"),
    ok("haversine_distance", {"latitude1": 90, "longitude1": 0, "latitude2": -90, "longitude2": 0, "unit": "mile"}, {"distance": 12436.815523614543, "unit": "mile"}, "pole-to-pole-in-miles"),
    ok("haversine_distance", LONDON_NEW_YORK, {"distance": 5574.848157146155, "unit": "kilometer"}, "london-new-york"),
    ok("haversine_distance", {"latitude1": 12.5, "longitude1": -45.25, "latitude2": 12.5, "longitude2": -45.25}, {"distance": 0.0, "unit": "kilometer"}, "identical-points"),
    ok("haversine_distance", {"latitude1": 0, "longitude1": 10, "latitude2": 0, "longitude2": 11, "unit": "meter"}, {"distance": 111195.0802335329, "unit": "meter"}, "one-degree-in-meters"),
    # A.26 initial_bearing: cardinal directions, the 16-point index, and the wrap from NNW back to N.
    ok("initial_bearing", {"latitude1": 0, "longitude1": 0, "latitude2": 0, "longitude2": 90}, {"bearing_degrees": 90.0, "compass_point": "E"}, "due-east"),
    ok("initial_bearing", {"latitude1": 0, "longitude1": 0, "latitude2": -10, "longitude2": 0}, {"bearing_degrees": 180.0, "compass_point": "S"}, "due-south"),
    ok("initial_bearing", {"latitude1": 0, "longitude1": 0, "latitude2": 0, "longitude2": -90}, {"bearing_degrees": 270.0, "compass_point": "W"}, "due-west"),
    ok("initial_bearing", {"latitude1": 0, "longitude1": 0, "latitude2": 1, "longitude2": 1}, {"bearing_degrees": 44.99563645534485, "compass_point": "NE"}, "north-east"),
    ok("initial_bearing", LONDON_NEW_YORK, {"bearing_degrees": 288.3368596615278, "compass_point": "WNW"}, "london-new-york"),
    ok("initial_bearing", {"latitude1": 0, "longitude1": 0, "latitude2": 10, "longitude2": -1.5}, {"bearing_degrees": 351.55572424423883, "compass_point": "N"}, "index-16-wraps-to-north"),
    ok("initial_bearing", {"latitude1": 5, "longitude1": 5, "latitude2": 5, "longitude2": 5}, {"bearing_degrees": 0.0, "compass_point": "N"}, "identical-points"),
    # A.26 destination_point: exact anchors, longitude normalization, units, and a general case.
    ok("destination_point", {"latitude": 0, "longitude": 0, "bearing_degrees": 90, "distance": QUARTER_CIRCLE_KILOMETERS}, {"latitude": 0.0, "longitude": 90.0}, "quarter-circle-east"),
    ok("destination_point", {"latitude": 0, "longitude": 0, "bearing_degrees": 0, "distance": TEN_DEGREES_KILOMETERS}, {"latitude": 10.0, "longitude": 0.0}, "ten-degrees-north"),
    ok("destination_point", {"latitude": 0, "longitude": 170, "bearing_degrees": 90, "distance": 2 * TEN_DEGREES_KILOMETERS}, {"latitude": 0.0, "longitude": -170.0}, "longitude-normalized"),
    ok("destination_point", {"latitude": 0, "longitude": 0, "bearing_degrees": 180, "distance": 690.9341957563635, "unit": "mile"}, {"latitude": -10.0, "longitude": 0.0}, "miles"),
    ok("destination_point", {"latitude": 51.5007, "longitude": -0.1246, "bearing_degrees": 45, "distance": 1000}, {"latitude": 57.33093563031873, "longitude": 11.691551524094734}, "general"),
    ok("destination_point", {"latitude": 12.5, "longitude": -45.25, "bearing_degrees": 33, "distance": 0}, {"latitude": 12.5, "longitude": -45.25}, "zero-distance"),
    # A.26 dms_to_decimal_degrees: separators, hemisphere at either end, prime symbols, and no hemisphere.
    ok("dms_to_decimal_degrees", {"dms": "40°26'46\"N"}, {"decimal_degrees": 40.44611111111111, "axis": "latitude"}, "degree-sign-north"),
    ok("dms_to_decimal_degrees", {"dms": "79°58'56\"W"}, {"decimal_degrees": -79.98222222222222, "axis": "longitude"}, "west-is-negative"),
    ok("dms_to_decimal_degrees", {"dms": "40°26′46″N"}, {"decimal_degrees": 40.44611111111111, "axis": "latitude"}, "prime-symbols"),
    ok("dms_to_decimal_degrees", {"dms": "S 33 52 0"}, {"decimal_degrees": -33.86666666666667, "axis": "latitude"}, "hemisphere-first-spaces"),
    ok("dms_to_decimal_degrees", {"dms": "10d30m0sE"}, {"decimal_degrees": 10.5, "axis": "longitude"}, "letter-separators"),
    ok("dms_to_decimal_degrees", {"dms": "-12 30"}, {"decimal_degrees": -12.5, "axis": None}, "signed-without-hemisphere"),
    # A.26 decimal_degrees_to_dms: §9.2 item 17 rounding, ties, carries, and the hemisphere of a value that rounds to zero.
    ok("decimal_degrees_to_dms", {"decimal_degrees": 0.000875, "axis": "latitude"}, dms("0°0′3.2″N", 0, 0, 3.2, "N"), "decimal-not-float-rounding"),
    ok("decimal_degrees_to_dms", {"decimal_degrees": 0.00125, "axis": "latitude", "seconds_decimal_places": 0}, dms("0°0′4″N", 0, 0, 4.0, "N"), "half-even-tie-no-point"),
    ok("decimal_degrees_to_dms", {"decimal_degrees": -33.8675, "axis": "latitude"}, dms("33°52′3.0″S", 33, 52, 3.0, "S"), "south"),
    ok("decimal_degrees_to_dms", {"decimal_degrees": 10.999999, "axis": "longitude", "seconds_decimal_places": 0}, dms("11°0′0″E", 11, 0, 0.0, "E"), "total-rounded-before-split"),
    ok("decimal_degrees_to_dms", {"decimal_degrees": -0.00001, "axis": "longitude"}, dms("0°0′0.0″E", 0, 0, 0.0, "E"), "negative-rounding-to-zero-is-east"),
    ok("decimal_degrees_to_dms", {"decimal_degrees": 151.2093, "axis": "longitude", "seconds_decimal_places": 2}, dms("151°12′33.48″E", 151, 12, 33.48, "E"), "two-places"),
    # A.26 polygon_area: shoelace by hand, both orientations, a repeated closing vertex, and a degenerate polygon.
    ok("polygon_area", {"x": SQUARE_X, "y": SQUARE_Y}, {"area": 1.0, "signed_area": 1.0, "orientation": "counterclockwise", "perimeter": 4.0}, "unit-square"),
    ok("polygon_area", {"x": [0, 0, 4], "y": [0, 3, 0]}, {"area": 6.0, "signed_area": -6.0, "orientation": "clockwise", "perimeter": 12.0}, "clockwise-3-4-5"),
    ok("polygon_area", {"x": [0, 2, 2, 0, 0], "y": [0, 0, 2, 2, 0]}, {"area": 4.0, "signed_area": 4.0, "orientation": "counterclockwise", "perimeter": 8.0}, "closing-vertex"),
    ok("polygon_area", {"x": [0, 1, 2], "y": [0, 1, 2]}, {"area": 0.0, "signed_area": 0.0, "orientation": "degenerate", "perimeter": 4 * math.sqrt(2)}, "degenerate"),
    # A.26 point_in_polygon: inside, outside, edge, vertex, a notch, and a ray through horizontal edges.
    ok("point_in_polygon", {"point_x": 0.5, "point_y": 0.5, "polygon_x": SQUARE_X, "polygon_y": SQUARE_Y}, {"inside": True, "on_boundary": False}, "inside"),
    ok("point_in_polygon", {"point_x": 2, "point_y": 0.5, "polygon_x": SQUARE_X, "polygon_y": SQUARE_Y}, {"inside": False, "on_boundary": False}, "outside"),
    ok("point_in_polygon", {"point_x": 1, "point_y": 0.5, "polygon_x": SQUARE_X, "polygon_y": SQUARE_Y}, {"inside": True, "on_boundary": True}, "on-edge"),
    ok("point_in_polygon", {"point_x": 0, "point_y": 0, "polygon_x": SQUARE_X, "polygon_y": SQUARE_Y}, {"inside": True, "on_boundary": True}, "on-vertex"),
    ok("point_in_polygon", {"point_x": 1.5, "point_y": 2, "polygon_x": NOTCHED_X, "polygon_y": NOTCHED_Y}, {"inside": False, "on_boundary": False}, "in-the-notch"),
    ok("point_in_polygon", {"point_x": 0.5, "point_y": 1, "polygon_x": NOTCHED_X, "polygon_y": NOTCHED_Y}, {"inside": True, "on_boundary": False}, "ray-along-edge"),
    ok("point_in_polygon", {"point_x": 1.5, "point_y": 1, "polygon_x": NOTCHED_X, "polygon_y": NOTCHED_Y}, {"inside": True, "on_boundary": True}, "on-notch-floor"),
    # A.27 parse_data_size: binary and decimal units, bits, no unit, exponents, and Mb as megabyte.
    ok("parse_data_size", {"text": "1.5 GiB"}, {"size_bytes": 1610612736.0, "size_bits": 12884901888.0}, "gibibytes"),
    ok("parse_data_size", {"text": "100 Mbit"}, {"size_bytes": 12500000.0, "size_bits": 100000000.0}, "megabits"),
    ok("parse_data_size", {"text": "  512  "}, {"size_bytes": 512.0, "size_bits": 4096.0}, "no-unit-is-bytes"),
    ok("parse_data_size", {"text": "2Mb"}, {"size_bytes": 2000000.0, "size_bits": 16000000.0}, "mb-is-megabyte"),
    ok("parse_data_size", {"text": "1e3 kb"}, {"size_bytes": 1000000.0, "size_bits": 8000000.0}, "exponent"),
    ok("parse_data_size", {"text": "0.3 KiB"}, {"size_bytes": 307.2, "size_bits": 2457.6}, "fraction-of-kibibyte"),
    ok("parse_data_size", {"text": "8 bits"}, {"size_bytes": 1.0, "size_bits": 8.0}, "bits"),
    ok("parse_data_size", {"text": "3 TB"}, {"size_bytes": 3e12, "size_bits": 2.4e13}, "terabytes"),
    # A.27 format_bytes_human: below the base, rounding up into the next unit, half-even ties, and the largest unit.
    ok("format_bytes_human", {"size_bytes": 512}, {"text": "512 B", "value": 512.0, "unit": "B"}, "below-base"),
    ok("format_bytes_human", {"size_bytes": 0}, {"text": "0 B", "value": 0.0, "unit": "B"}, "zero"),
    ok("format_bytes_human", {"size_bytes": 1536}, {"text": "1.5 KiB", "value": 1.5, "unit": "KiB"}, "kibibytes"),
    ok("format_bytes_human", {"size_bytes": 1048575}, {"text": "1.0 MiB", "value": 1.0, "unit": "MiB"}, "rounds-up-to-next-unit"),
    ok("format_bytes_human", {"size_bytes": 1500000, "standard": "si", "decimal_places": 2}, {"text": "1.50 MB", "value": 1.5, "unit": "MB"}, "si-keeps-trailing-zero"),
    ok("format_bytes_human", {"size_bytes": 1250, "standard": "si"}, {"text": "1.2 kB", "value": 1.2, "unit": "kB"}, "half-even-tie"),
    ok("format_bytes_human", {"size_bytes": 1024, "decimal_places": 0}, {"text": "1 KiB", "value": 1.0, "unit": "KiB"}, "zero-places"),
    ok("format_bytes_human", {"size_bytes": 10**21, "standard": "si"}, {"text": "1000.0 EB", "value": 1000.0, "unit": "EB"}, "no-unit-above-exabyte"),
    ok("format_bytes_human", {"size_bytes": 1024**6}, {"text": "1.0 EiB", "value": 1.0, "unit": "EiB"}, "exbibyte"),
    # A.27 bitwise_operation: each operation, fixed widths with padding, negative results, and big shifts.
    ok("bitwise_operation", {"left": "12", "operation": "and", "right": "10"}, {"result": "8", "binary": "1000", "hex": "8"}, "and"),
    ok("bitwise_operation", {"left": "12", "operation": "or", "right": "10"}, {"result": "14", "binary": "1110", "hex": "e"}, "or-lowercase-hex"),
    ok("bitwise_operation", {"left": "12", "operation": "xor", "right": "10"}, {"result": "6", "binary": "110", "hex": "6"}, "xor"),
    ok("bitwise_operation", {"left": "-12", "operation": "xor", "right": "10"}, {"result": "-2", "binary": "-10", "hex": "-2"}, "negative-without-width"),
    ok("bitwise_operation", {"left": "5", "operation": "not", "width": 8}, {"result": "250", "binary": "11111010", "hex": "fa"}, "not-at-width"),
    ok("bitwise_operation", {"left": "1", "operation": "shift_left", "right": "70"}, {"result": "1180591620717411303424", "binary": "1" + "0" * 70, "hex": "4" + "0" * 17}, "shift-past-64-bits"),
    ok("bitwise_operation", {"left": "-16", "operation": "shift_right", "right": "2"}, {"result": "-4", "binary": "-100", "hex": "-4"}, "arithmetic-shift-right"),
    ok("bitwise_operation", {"left": "200", "operation": "shift_left", "right": "1", "width": 8}, {"result": "144", "binary": "10010000", "hex": "90"}, "shift-wraps-at-width"),
    ok("bitwise_operation", {"left": "-1", "operation": "and", "right": "6", "width": 4}, {"result": "6", "binary": "0110", "hex": "6"}, "negative-reduced-mod-width"),
    ok("bitwise_operation", {"left": "1", "operation": "or", "right": "4", "width": 12}, {"result": "5", "binary": "000000000101", "hex": "005"}, "zero-padded"),
    # A.27 integer_to_twos_complement: negative and positive values, odd widths, and the extremes.
    ok("integer_to_twos_complement", {"value": "-1", "width": 8}, {"binary": "11111111", "hex": "ff", "unsigned_value": "255"}, "minus-one"),
    ok("integer_to_twos_complement", {"value": "5", "width": 4}, {"binary": "0101", "hex": "5", "unsigned_value": "5"}, "positive-padded"),
    ok("integer_to_twos_complement", {"value": "-128", "width": 8}, {"binary": "10000000", "hex": "80", "unsigned_value": "128"}, "minimum"),
    ok("integer_to_twos_complement", {"value": "127", "width": 8}, {"binary": "01111111", "hex": "7f", "unsigned_value": "127"}, "maximum"),
    ok("integer_to_twos_complement", {"value": "-1", "width": 6}, {"binary": "111111", "hex": "3f", "unsigned_value": "63"}, "hex-digits-round-up"),
    ok("integer_to_twos_complement", {"value": "-1", "width": 1}, {"binary": "1", "hex": "1", "unsigned_value": "1"}, "width-one"),
    # A.27 twos_complement_to_integer: binary and hex, ignored prefixes and separators, and zero extension.
    ok("twos_complement_to_integer", {"bits": "11111111"}, {"signed_value": "-1", "unsigned_value": "255", "width": 8}, "binary"),
    ok("twos_complement_to_integer", {"bits": "0b0111_1111"}, {"signed_value": "127", "unsigned_value": "127", "width": 8}, "prefix-and-underscore"),
    ok("twos_complement_to_integer", {"bits": "ff", "bit_format": "hex"}, {"signed_value": "-1", "unsigned_value": "255", "width": 8}, "hex"),
    ok("twos_complement_to_integer", {"bits": "0x80 00", "bit_format": "hex"}, {"signed_value": "-32768", "unsigned_value": "32768", "width": 16}, "hex-prefix-and-space"),
    ok("twos_complement_to_integer", {"bits": "1111", "width": 8}, {"signed_value": "15", "unsigned_value": "15", "width": 8}, "zero-extended"),
    # A.27 convert_unix_permissions: octal and symbolic input, special bits, and a file-type character.
    ok("convert_unix_permissions", {"permissions": "755"}, permissions("0755", "rwxr-xr-x"), "three-digit-octal"),
    ok("convert_unix_permissions", {"permissions": "4755"}, permissions("4755", "rwsr-xr-x", setuid=True), "setuid"),
    ok("convert_unix_permissions", {"permissions": "2750"}, permissions("2750", "rwxr-s---", setgid=True), "setgid"),
    ok("convert_unix_permissions", {"permissions": "-rw-r--r--"}, permissions("0644", "rw-r--r--"), "symbolic-with-file-type"),
    ok("convert_unix_permissions", {"permissions": "rwxrwxrwT"}, permissions("1776", "rwxrwxrwT", sticky=True), "sticky-without-execute"),
    ok("convert_unix_permissions", {"permissions": "rwSr-Sr--"}, permissions("6644", "rwSr-Sr--", setuid=True, setgid=True), "capital-s"),
    # A.28 extract_markdown_headings: ATX with closing hashes, setext, fences ignored, GitHub slugs, and repeats.
    ok(
        "extract_markdown_headings",
        {"markdown": HEADINGS_MARKDOWN},
        {
            "headings": [
                {"level": 1, "text": "Hello World!", "line": 1, "anchor": "hello-world"},
                {"level": 2, "text": "Setup & Install", "line": 3, "anchor": "setup--install"},
                {"level": 3, "text": "Hello World!", "line": 8, "anchor": "hello-world-1"},
                {"level": 1, "text": "Plain Title", "line": 10, "anchor": "plain-title"},
                {"level": 6, "text": "Six", "line": 15, "anchor": "six"},
            ],
            "count": 5,
        },
        "atx-setext-slugs",
    ),
    ok("extract_markdown_headings", {"markdown": ""}, {"headings": [], "count": 0}, "empty"),
    # A.28 extract_markdown_tasks: the row's regex, list markers, upper-case X, fences, and CRLF lines.
    ok(
        "extract_markdown_tasks",
        {"markdown": TASKS_MARKDOWN},
        {
            "tasks": [
                {"line": 1, "checked": False, "text": "write tests"},
                {"line": 2, "checked": True, "text": "read spec"},
                {"line": 3, "checked": True, "text": "nested upper"},
                {"line": 4, "checked": False, "text": "numbered"},
                {"line": 5, "checked": True, "text": "paren"},
            ],
            "done": 3,
            "open": 2,
        },
        "markers-and-fences",
    ),
    ok(
        "extract_markdown_tasks",
        {"markdown": "- [ ] a\r\n- [x] b\r\n"},
        {"tasks": [{"line": 1, "checked": False, "text": "a"}, {"line": 2, "checked": True, "text": "b"}], "done": 1, "open": 1},
        "crlf-lines",
    ),
    # A.28 parse_markdown_table: alignment, escaped pipes, short and long rows, repeated names, and table_index.
    ok(
        "parse_markdown_table",
        {"markdown": TABLE_MARKDOWN},
        {
            "columns": ["Name", "Qty", "Note"],
            "records": [{"Name": "apple", "Qty": "3", "Note": "a | b"}, {"Name": "pear", "Qty": "", "Note": ""}, {"Name": "fig", "Qty": "1", "Note": "x"}],
            "table_count": 1,
            "alignment": ["left", "center", "right"],
        },
        "alignment-and-padding",
    ),
    ok(
        "parse_markdown_table",
        {"markdown": TWO_TABLES_MARKDOWN},
        {"columns": ["a", "a_2", "b"], "records": [{"a": "1", "a_2": "2", "b": "3"}], "table_count": 2, "alignment": [None, None, None]},
        "repeated-column-names",
    ),
    ok(
        "parse_markdown_table",
        {"markdown": TWO_TABLES_MARKDOWN, "table_index": 1},
        {"columns": ["x"], "records": [{"x": "y"}], "table_count": 2, "alignment": [None]},
        "second-table",
    ),
    # A.28 extract_markdown_links: inline with title, image, autolink, case-insensitive reference, fences ignored.
    ok(
        "extract_markdown_links",
        {"markdown": LINKS_MARKDOWN},
        {
            "links": [
                {"text": "Docs", "url": "https://example.com/docs", "title": "Guide", "kind": "inline", "line": 1},
                {"text": "Logo", "url": "img/logo.png", "title": None, "kind": "image", "line": 1},
                {"text": "https://auto.example.org/x", "url": "https://auto.example.org/x", "title": None, "kind": "autolink", "line": 2},
                {"text": "Home", "url": "https://home.example", "title": "Home Page", "kind": "reference", "line": 3},
            ],
            "count": 4,
            "truncated": False,
        },
        "every-kind",
    ),
    ok("extract_markdown_links", {"markdown": "No links here."}, {"links": [], "count": 0, "truncated": False}, "none"),
    # A.28 extract_fenced_code_blocks: languages, tilde fences, info-string words, unclosed blocks, and the filter.
    ok(
        "extract_fenced_code_blocks",
        {"markdown": CODE_MARKDOWN},
        {
            "blocks": [
                {"language": "Python", "code": "print(\"hi\")", "start_line": 2, "end_line": 4},
                {"language": "js", "code": "let a = 1;", "start_line": 5, "end_line": 7},
                {"language": None, "code": "plain\nunclosed", "start_line": 8, "end_line": 10},
            ],
            "count": 3,
        },
        "all-blocks",
    ),
    ok(
        "extract_fenced_code_blocks",
        {"markdown": CODE_MARKDOWN, "language": "PYTHON"},
        {"blocks": [{"language": "Python", "code": "print(\"hi\")", "start_line": 2, "end_line": 4}], "count": 1},
        "language-filter-ignores-case",
    ),
    ok("extract_fenced_code_blocks", {"markdown": CODE_MARKDOWN, "language": "go"}, {"blocks": [], "count": 0}, "language-not-present"),
    # A.28 html_table_to_records: th header, collapsed whitespace, colspan copies, generated names, nested tables.
    ok(
        "html_table_to_records",
        {"html_text": HTML_TABLE},
        {"columns": ["Name", "Age"], "records": [{"Name": "Ann Lee", "Age": "30"}, {"Name": "wide", "Age": "wide"}], "table_count": 1},
        "header-and-colspan",
    ),
    ok(
        "html_table_to_records",
        {"html_text": "<table><tr><td>1</td><td>2</td></tr></table>"},
        {"columns": ["column_1", "column_2"], "records": [{"column_1": "1", "column_2": "2"}], "table_count": 1},
        "generated-column-names",
    ),
    ok(
        "html_table_to_records",
        {"html_text": HTML_NESTED_TABLES},
        {"columns": ["A"], "records": [{"A": "x in"}], "table_count": 2},
        "nested-table-joins-cell",
    ),
    ok(
        "html_table_to_records",
        {"html_text": HTML_NESTED_TABLES, "table_index": 1},
        {"columns": ["column_1"], "records": [{"column_1": "z"}], "table_count": 2},
        "second-top-level-table",
    ),
    # A.28 extract_html_links: urljoin against a base, collapsed text, rel, and unescaped attribute values.
    ok(
        "extract_html_links",
        {"html_text": HTML_LINKS, "base_url": "https://example.com/base/index.html"},
        {
            "links": [
                {"url": "https://example.com/docs/intro", "text": "Intro Page", "rel": "next"},
                {"url": "https://x.org/a?b=1&c=2", "text": "X", "rel": None},
            ],
            "count": 2,
            "truncated": False,
        },
        "resolved-against-base",
    ),
    ok(
        "extract_html_links",
        {"html_text": HTML_LINKS},
        {
            "links": [{"url": "/docs/intro", "text": "Intro Page", "rel": "next"}, {"url": "https://x.org/a?b=1&c=2", "text": "X", "rel": None}],
            "count": 2,
            "truncated": False,
        },
        "no-base",
    ),
]

FAILURE_CASES = [
    # A.26 schema bounds and row errors.
    invalid("haversine_distance", {"latitude1": 91, "longitude1": 0, "latitude2": 0, "longitude2": 0}, "latitude1", "latitude-over-90"),
    invalid("haversine_distance", {"latitude1": 0, "longitude1": 0, "latitude2": 0, "longitude2": 180.5}, "longitude2", "longitude-over-180"),
    invalid("initial_bearing", {"latitude1": 0, "longitude1": -181, "latitude2": 0, "longitude2": 0}, "longitude1", "longitude-under-minus-180"),
    invalid("destination_point", {"latitude": 0, "longitude": 0, "bearing_degrees": 361, "distance": 1}, "bearing_degrees", "bearing-over-360"),
    invalid("destination_point", {"latitude": 0, "longitude": 0, "bearing_degrees": 0, "distance": -1}, "distance", "negative-distance"),
    bad("dms_to_decimal_degrees", {"dms": "40°60'0\"N"}, "dms", "sixty-minutes"),
    bad("dms_to_decimal_degrees", {"dms": "10°0'60\"E"}, "dms", "sixty-seconds"),
    bad("dms_to_decimal_degrees", {"dms": "-40°26'46\"S"}, "dms", "sign-with-south"),
    bad("dms_to_decimal_degrees", {"dms": "91°0'0\"N"}, "dms", "latitude-over-90"),
    bad("dms_to_decimal_degrees", {"dms": "181°0'0\"E"}, "dms", "longitude-over-180"),
    bad("dms_to_decimal_degrees", {"dms": "north"}, "dms", "unreadable"),
    invalid("dms_to_decimal_degrees", {"dms": ""}, "dms", "empty"),
    bad("decimal_degrees_to_dms", {"decimal_degrees": 90.5, "axis": "latitude"}, "decimal_degrees", "latitude-out-of-range"),
    bad("decimal_degrees_to_dms", {"decimal_degrees": -180.25, "axis": "longitude"}, "decimal_degrees", "longitude-out-of-range"),
    invalid("decimal_degrees_to_dms", {"decimal_degrees": 1, "axis": "latitude", "seconds_decimal_places": 7}, "seconds_decimal_places", "too-many-places"),
    invalid("decimal_degrees_to_dms", {"decimal_degrees": 1, "axis": "altitude"}, "axis", "unknown-axis"),
    bad("polygon_area", {"x": [0, 1, 1], "y": [0, 0, 1, 1]}, "y", "length-mismatch"),
    invalid("polygon_area", {"x": [0, 1], "y": [0, 1, 1]}, "x", "fewer-than-three-vertices"),
    bad("point_in_polygon", {"point_x": 0, "point_y": 0, "polygon_x": SQUARE_X, "polygon_y": [0, 0, 1]}, "polygon_y", "length-mismatch"),
    # A.27 row errors.
    bad("parse_data_size", {"text": "1,000 MB"}, "text", "thousands-separator"),
    bad("parse_data_size", {"text": "-5 MB"}, "text", "negative"),
    bad("parse_data_size", {"text": "5 zb"}, "text", "unknown-unit"),
    bad("parse_data_size", {"text": "MB"}, "text", "no-number"),
    invalid("format_bytes_human", {"size_bytes": -1}, "size_bytes", "negative-size"),
    invalid("format_bytes_human", {"size_bytes": 1, "decimal_places": 7}, "decimal_places", "too-many-places"),
    bad("bitwise_operation", {"left": "12", "operation": "and"}, "right", "and-needs-right"),
    bad("bitwise_operation", {"left": "12", "operation": "xor"}, "right", "xor-needs-right"),
    bad("bitwise_operation", {"left": "12", "operation": "not"}, "width", "not-needs-width"),
    bad("bitwise_operation", {"left": "1", "operation": "shift_left", "right": "-1"}, "right", "negative-shift"),
    # Spec r4 names `right` for a missing or out-of-range shift amount; PREBUILT_MAX_BIT_WIDTH is 4096.
    bad("bitwise_operation", {"left": "1", "operation": "shift_left"}, "right", "shift-without-amount"),
    bad("bitwise_operation", {"left": "1", "operation": "shift_right", "right": "4097"}, "right", "shift-past-bit-width"),
    bad("bitwise_operation", {"left": "9" * 4000, "operation": "shift_left", "right": "1"}, "right", "result-over-4000-digits"),
    invalid("bitwise_operation", {"left": "1", "operation": "or", "right": "1", "width": 4097}, "width", "width-over-cap"),
    bad("integer_to_twos_complement", {"value": "128", "width": 8}, "value", "above-range"),
    bad("integer_to_twos_complement", {"value": "-129", "width": 8}, "value", "below-range"),
    invalid("integer_to_twos_complement", {"value": "1", "width": 0}, "width", "zero-width"),
    bad("twos_complement_to_integer", {"bits": "11111111", "width": 4}, "width", "width-smaller-than-pattern"),
    bad("twos_complement_to_integer", {"bits": "1012"}, "bits", "invalid-binary-digit"),
    bad("twos_complement_to_integer", {"bits": "fg", "bit_format": "hex"}, "bits", "invalid-hex-digit"),
    bad("twos_complement_to_integer", {"bits": "1" * 4097}, "bits", "more-than-4096-bits"),
    bad("convert_unix_permissions", {"permissions": "999"}, "permissions", "not-octal"),
    bad("convert_unix_permissions", {"permissions": "rwxr-xr-"}, "permissions", "eight-characters"),
    bad("convert_unix_permissions", {"permissions": "rwxrwxrwz"}, "permissions", "unknown-letter"),
    # A.28 row errors.
    bad("parse_markdown_table", {"markdown": "Just a paragraph."}, "markdown", "no-table"),
    bad("parse_markdown_table", {"markdown": "```\n| a |\n|---|\n| 1 |\n```\n"}, "markdown", "table-inside-fence-ignored"),
    bad("parse_markdown_table", {"markdown": TABLE_MARKDOWN, "table_index": 1}, "table_index", "index-past-count"),
    bad("html_table_to_records", {"html_text": "<p>no table</p>"}, "html_text", "no-table"),
    bad("html_table_to_records", {"html_text": HTML_NESTED_TABLES, "table_index": 2}, "table_index", "index-past-count"),
]


@pytest.mark.parametrize("case", SUCCESS_CASES)
def test_geometry_bits_markdown_rows_return_documented_output(tool_runner: ToolRunner, case: SuccessCase) -> None:
    tool_runner.check_success(case)


@pytest.mark.parametrize("case", FAILURE_CASES)
def test_geometry_bits_markdown_rows_reject_bad_input(tool_runner: ToolRunner, case: FailureCase) -> None:
    tool_runner.check_failure(case)


def test_fenced_code_block_code_and_lines(tool_runner: ToolRunner) -> None:
    blocks = tool_runner.output("extract_fenced_code_blocks", {"markdown": CODE_MARKDOWN + "\n"})["blocks"]
    # Spec r4: code is the lines between the fences joined with a line break and no trailing break, even when the document ends with one.
    assert [block["code"] for block in blocks] == ["print(\"hi\")", "let a = 1;", "plain\nunclosed"]
    # Lines are 1-based fence lines; an unclosed block ends at the document's last line, and a trailing break starts no new line.
    assert [(block["start_line"], block["end_line"]) for block in blocks] == [(2, 4), (5, 7), (8, 10)]


def test_malformed_html_table_never_raises(tool_runner: ToolRunner) -> None:
    output = tool_runner.output("html_table_to_records", {"html_text": "<table><tr><td>a<td>b</tr><tr><td>c"})
    assert output["table_count"] == 1
    # Spec r4: with no th header row, the longest row sets how many columns are named.
    assert output["columns"] == ["column_1", "column_2"]
    assert output["records"][0] == {"column_1": "a", "column_2": "b"}
