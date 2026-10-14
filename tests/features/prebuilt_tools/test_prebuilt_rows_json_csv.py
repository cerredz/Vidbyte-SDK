"""FILE: tests/features/prebuilt_tools/test_prebuilt_rows_json_csv.py

PURPOSE: Exact-output and error cases for every Appendix A row of the json_data, json_records, and csv_tables categories (A.17-A.19), run through FunctionTool.execute as a model would call them.
ROLE IN CODEBASE: Row-level acceptance (AC-11) for 27 prebuilt tools; reaches each tool through the session ToolRunner in tests/features/prebuilt_tools/conftest.py and compares with tests/features/prebuilt_tools/prebuilt_tool_harness.OutputMatcher.
ARCHITECTURE NOTE: Expected values are hand-computed from the rows, RFC 6901 and RFC 6902 published examples, or the stdlib json and csv modules the rows themselves name; nothing is read from the implementation.
FUNCTION INVENTORY: test_json_csv_rows_return_documented_output checks SUCCESS_CASES; test_json_csv_rows_reject_bad_input checks FAILURE_CASES; test_csv_to_records_infers_integer_and_float_types pins JSON number types; test_csv_to_markdown_table_escapes_cells_and_aligns_columns checks the exact table text for every alignment and the left default.
COMMON MODIFICATION PATTERNS: Add a row case as one ok(...) or bad(...) entry; keep each expected object complete, because the matcher demands the row's exact key set.
WHAT NOT TO DO IN THIS FILE: 1. Do not import vidbyte.tools.toolsets or the prebuilt package at module level; the conftest fixtures import them so a missing feature fails at setup. 2. Do not add output-amplification or 100,000-bracket cases here; test_prebuilt_resource_bounds.py owns INV-19 and INV-20 limits.
KNOWN EDGE CASES: JSON depth counts [] as one level, so 100 nested arrays are allowed and 101 are not. CSV cells holding only whitespace are empty. Pydantic rejects a JSON array sent for a *_json text parameter (EC-30). Spec r4 fixes the Markdown table text exactly, the null positions of the fixed verify_json_syntax messages, the fallback quote character and row count of detect_csv_dialect, and distinct-by-text profiling; has_header stays ANY because the row does not say how a header is detected.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md (Appendix A.17, A.18, A.19; §9.2 items 3, 12, 14, 15)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_rows_json_csv.py
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from tests.features.prebuilt_tools.prebuilt_tool_harness import ANY, NON_EMPTY_TEXT, FailureCase, SuccessCase, ToolRunner, bad, invalid, ok


def nested_empty_lists(depth: int) -> list[Any]:
    """The value of '[' * depth + ']' * depth, built without recursion."""
    value: list[Any] = []
    for _ in range(depth - 1):
        value = [value]
    return value


def markdown_cells(line: str) -> list[str]:
    """Split one Markdown table line on pipes that are not escaped with a backslash."""
    inner = line.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    inner = inner[:-1] if inner.endswith("|") and not inner.endswith("\\|") else inner
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", inner)]


NESTED_JSON_DOC = '{"a": {"b/c": [10, 20], "m~n": true, "z": null}}'
SET_DOC = '{"b": 1, "a": [1, 2]}'
PATH_DOC = '{"a": {"b": 1, "c": []}, "d": [true, null], "x/y": {"m~n": "s"}}'
DIFF_ORIGINAL = '{"a": 1, "b": [1, 2, 3], "c": true}'
DIFF_MODIFIED = '{"a": 1.0, "b": [1, 5], "c": 1, "d": null}'
FILTER_ORDER_RECORDS = '[{"n": 5}, {"n": 12.5}, {"n": "x"}, {"m": 1}, {"n": null}]'
EMPTY_RECORDS = '[{"a": ""}, {"a": null}, {}, {"a": []}, {"a": {}}, {"a": 0}, {"a": " "}]'
GROUP_RECORDS = '[{"k": 1, "i": 0}, {"k": "1", "i": 1}, {"k": 1.0, "i": 2}, {"i": 3}, {"k": null, "i": 4}, {"k": true, "i": 5}, {"k": [1], "i": 6}, {"k": [1], "i": 7}]'
MIXED_VALUES = '[{"v": 1}, {"v": 2.5}, {"v": "x"}, {"v": true}]'
GROUP_AGG_RECORDS = '[{"g": "x", "v": 1}, {"g": "y", "v": 10}, {"g": "x", "v": 2}, {"v": 5}, {"g": "y", "v": "n/a"}]'
SORT_MIXED = '[{"f": "b"}, {"f": 2}, {"id": "m"}, {"f": true}, {"f": null}, {"f": "a"}, {"f": [1]}, {"f": 1.5}, {"f": false}, {"f": {"z": 1}}]'
COUNT_RECORDS = '[{"c": "x"}, {"c": "y"}, {"c": "x"}, {}, {"c": null}, {"c": "y"}, {"c": "z"}]'
JOIN_LEFT = '[{"id": 1, "name": "a"}, {"id": 2, "name": "b"}, {"id": null, "name": "c"}, {"name": "d"}]'
JOIN_RIGHT = '[{"user_id": 1, "name": "x", "v": 10}, {"user_id": "1", "v": 14}, {"user_id": 1, "v": 11}, {"user_id": null, "v": 13}]'
CSV_RECORDS = '[{"a": 1, "b": "x,y"}, {"b": "q\\"t", "c": true}, {"a": null, "c": [1, 2]}, {"a": 1.5, "b": "line\\nbreak"}]'
PROFILE_CSV = "id,price,flag,day,name,blank\n3,2.5,true,2024-01-02,Bob,\n10,-1,FALSE,2023-12-31,alice,\n3,7,true,2024-01-02,Bob, \n"
FILTER_CSV = "name,qty\nA,10\nB,9\nC,x\nD,\nE, \n"
AGGREGATE_CSV = "id,v\na,1\nb,2.5\nc,x\ne,4\n"
GROUP_CSV = "g,v\nx,1\ny,10\nx,2\n,5\ny,n/a\n"
JOIN_LEFT_CSV = "id,name\n1,a\n2,b\n01,c\n"
JOIN_RIGHT_CSV = "id,name,v\n1,x,10\n1,y,11\n4,z,12\n"
JOINED_CSV = "id,name,right_name,v\n1,a,x,10\n1,a,y,11\n"
WIDE_RECORD = "[{" + ", ".join(f'"k{index}": 0' for index in range(501)) + "}]"

JSON_DATA_CASES = [
    ok("verify_json_syntax", {"json_text": '{"a": [1, 2]}'}, {"valid": True, "error": None, "line": None, "column": None, "position": None, "top_level_type": "object"}, "valid-object"),
    ok("verify_json_syntax", {"json_text": '{"a": 1,}'}, {"valid": False, "error": "Expecting property name enclosed in double quotes", "line": 1, "column": 9, "position": 8, "top_level_type": None}, "trailing-comma"),
    ok("verify_json_syntax", {"json_text": '{\n  "a": 1\n  "b": 2\n}'}, {"valid": False, "error": "Expecting ',' delimiter", "line": 3, "column": 3, "position": 13, "top_level_type": None}, "multiline-error"),
    ok("verify_json_syntax", {"json_text": ""}, {"valid": False, "error": "Expecting value", "line": 1, "column": 1, "position": 0, "top_level_type": None}, "empty-text"),
    ok("verify_json_syntax", {"json_text": "[1, NaN]"}, {"valid": False, "error": NON_EMPTY_TEXT, "line": None, "column": None, "position": None, "top_level_type": None}, "nan-constant-invalid"),
    ok("verify_json_syntax", {"json_text": "[" * 100 + "]" * 100}, {"valid": True, "error": None, "line": None, "column": None, "position": None, "top_level_type": "array"}, "depth-100-valid"),
    ok("verify_json_syntax", {"json_text": "[" * 101 + "]" * 101}, {"valid": False, "error": NON_EMPTY_TEXT, "line": None, "column": None, "position": None, "top_level_type": None}, "depth-101-invalid"),
    # S4 M-1 (spec r6 A.17): valid means every JSON tool here accepts the text, so a float overflow and a 4,400-digit integer are invalid.
    ok("verify_json_syntax", {"json_text": '{"a":1e400}'}, {"valid": False, "error": NON_EMPTY_TEXT, "line": None, "column": None, "position": None, "top_level_type": None}, "float-overflow-invalid"),
    ok("verify_json_syntax", {"json_text": "1" * 4400}, {"valid": False, "error": NON_EMPTY_TEXT, "line": None, "column": None, "position": None, "top_level_type": None}, "integer-of-4400-digits-invalid"),
    ok("format_json", {"json_text": '{"b": 1, "a": [1, 2], "c": {}}'}, {"json": '{\n  "b": 1,\n  "a": [\n    1,\n    2\n  ],\n  "c": {}\n}'}, "default-indent-2"),
    ok("format_json", {"json_text": '{"b": {"d": 1, "c": 2}, "a": []}', "sort_keys": True}, {"json": '{\n  "a": [],\n  "b": {\n    "c": 2,\n    "d": 1\n  }\n}'}, "sort-keys"),
    ok("format_json", {"json_text": '{ "a" : 1 , "b" : [ 1.0 , "é" ] }', "indent": 0}, {"json": '{"a":1,"b":[1.0,"é"]}'}, "indent-0-compact"),
    ok("format_json", {"json_text": '{"k": "é😀"}', "indent": 0, "ensure_ascii": True}, {"json": '{"k":"\\u00e9\\ud83d\\ude00"}'}, "ensure-ascii"),
    ok("format_json", {"json_text": '{"a": 1, "b": 2, "a": 3}', "indent": 0}, {"json": '{"a":3,"b":2}'}, "duplicate-key-last-wins"),
    ok("json_get_value", {"json_text": NESTED_JSON_DOC, "pointer": "/a/b~1c/1"}, {"found": True, "value": 20, "type": "number"}, "escaped-slash-index"),
    ok("json_get_value", {"json_text": NESTED_JSON_DOC, "pointer": "/a/m~0n"}, {"found": True, "value": True, "type": "boolean"}, "escaped-tilde"),
    ok("json_get_value", {"json_text": NESTED_JSON_DOC, "pointer": "/a/z"}, {"found": True, "value": None, "type": "null"}, "present-null"),
    ok("json_get_value", {"json_text": NESTED_JSON_DOC, "pointer": "/a/missing"}, {"found": False, "value": None, "type": None}, "missing-key"),
    ok("json_get_value", {"json_text": NESTED_JSON_DOC, "pointer": "/a/b~1c/-"}, {"found": False, "value": None, "type": None}, "dash-never-resolves"),
    ok("json_get_value", {"json_text": NESTED_JSON_DOC, "pointer": "/a/b~1c/2"}, {"found": False, "value": None, "type": None}, "index-out-of-range"),
    ok("json_get_value", {"json_text": '{"a": [1]}', "pointer": ""}, {"found": True, "value": {"a": [1]}, "type": "object"}, "root"),
    ok("json_get_value", {"json_text": '{"a": 1, "a": 2}', "pointer": "/a"}, {"found": True, "value": 2, "type": "number"}, "duplicate-key-last-wins"),
    ok("json_set_value", {"json_text": SET_DOC, "pointer": "/a/-", "value_json": "3"}, {"json": '{"b":1,"a":[1,2,3]}', "replaced": False}, "append-dash"),
    ok("json_set_value", {"json_text": SET_DOC, "pointer": "/a/2", "value_json": '"x"'}, {"json": '{"b":1,"a":[1,2,"x"]}', "replaced": False}, "append-at-length"),
    ok("json_set_value", {"json_text": SET_DOC, "pointer": "/a/0", "value_json": '{"k": "é"}'}, {"json": '{"b":1,"a":[{"k":"é"},2]}', "replaced": True}, "replace-array-item"),
    ok("json_set_value", {"json_text": SET_DOC, "pointer": "/b", "value_json": "null"}, {"json": '{"b":null,"a":[1,2]}', "replaced": True}, "replace-member-keeps-order"),
    ok("json_set_value", {"json_text": SET_DOC, "pointer": "/c", "value_json": "true"}, {"json": '{"b":1,"a":[1,2],"c":true}', "replaced": False}, "insert-member"),
    ok("json_set_value", {"json_text": SET_DOC, "pointer": "", "value_json": "[true]"}, {"json": "[true]", "replaced": True}, "replace-root"),
    ok("json_set_value", {"json_text": SET_DOC, "pointer": "/x/y", "value_json": "1", "create_missing": True}, {"json": '{"b":1,"a":[1,2],"x":{"y":1}}', "replaced": False}, "create-missing"),
    ok("list_json_paths", {"json_text": PATH_DOC}, {"paths": [{"pointer": "/a/b", "type": "number"}, {"pointer": "/a/c", "type": "array"}, {"pointer": "/d/0", "type": "boolean"}, {"pointer": "/d/1", "type": "null"}, {"pointer": "/x~1y/m~0n", "type": "string"}], "count": 5, "truncated": False}, "leaves-only"),
    ok("list_json_paths", {"json_text": PATH_DOC, "leaves_only": False}, {"paths": [{"pointer": "", "type": "object"}, {"pointer": "/a", "type": "object"}, {"pointer": "/a/b", "type": "number"}, {"pointer": "/a/c", "type": "array"}, {"pointer": "/d", "type": "array"}, {"pointer": "/d/0", "type": "boolean"}, {"pointer": "/d/1", "type": "null"}, {"pointer": "/x~1y", "type": "object"}, {"pointer": "/x~1y/m~0n", "type": "string"}], "count": 9, "truncated": False}, "with-containers"),
    ok("list_json_paths", {"json_text": "{}"}, {"paths": [{"pointer": "", "type": "object"}], "count": 1, "truncated": False}, "empty-root-is-leaf"),
    ok("diff_json_documents", {"original_json": DIFF_ORIGINAL, "modified_json": DIFF_MODIFIED}, {"identical": False, "changes": [{"op": "replace", "pointer": "/b/1", "old_value": 2, "new_value": 5}, {"op": "remove", "pointer": "/b/2", "old_value": 3, "new_value": None}, {"op": "replace", "pointer": "/c", "old_value": True, "new_value": 1}, {"op": "add", "pointer": "/d", "old_value": None, "new_value": None}], "count": 4, "truncated": False}, "type-aware-mixed"),
    ok("diff_json_documents", {"original_json": "[1, 2, 3, 4]", "modified_json": "[1]"}, {"identical": False, "changes": [{"op": "remove", "pointer": "/3", "old_value": 4, "new_value": None}, {"op": "remove", "pointer": "/2", "old_value": 3, "new_value": None}, {"op": "remove", "pointer": "/1", "old_value": 2, "new_value": None}], "count": 3, "truncated": False}, "array-removals-highest-first"),
    ok("diff_json_documents", {"original_json": "[1]", "modified_json": '[1, "x", {"k": 1}]'}, {"identical": False, "changes": [{"op": "add", "pointer": "/1", "old_value": None, "new_value": "x"}, {"op": "add", "pointer": "/2", "old_value": None, "new_value": {"k": 1}}], "count": 2, "truncated": False}, "array-additions-ascending"),
    ok("diff_json_documents", {"original_json": '{"x": 1, "y": {"p": 1}, "z": 3}', "modified_json": '{"z": 4, "w": 0, "y": {"p": 1, "q": [1]}}'}, {"identical": False, "changes": [{"op": "remove", "pointer": "/x", "old_value": 1, "new_value": None}, {"op": "add", "pointer": "/y/q", "old_value": None, "new_value": [1]}, {"op": "replace", "pointer": "/z", "old_value": 3, "new_value": 4}, {"op": "add", "pointer": "/w", "old_value": None, "new_value": 0}], "count": 4, "truncated": False}, "object-key-order"),
    ok("diff_json_documents", {"original_json": '{"a": {"b": 1}}', "modified_json": '{"a": [1]}'}, {"identical": False, "changes": [{"op": "replace", "pointer": "/a", "old_value": {"b": 1}, "new_value": [1]}], "count": 1, "truncated": False}, "object-to-array-one-replace"),
    ok("diff_json_documents", {"original_json": '{"a": [1, 2]}', "modified_json": '{"a": [1.0, 2]}'}, {"identical": True, "changes": [], "count": 0, "truncated": False}, "one-equals-one-point-zero"),
    ok("apply_json_patch", {"json_text": '{"foo": "bar"}', "patch_json": '[{"op": "add", "path": "/baz", "value": "qux"}]'}, {"json": '{"foo":"bar","baz":"qux"}', "applied_operations": 1}, "rfc6902-a1-add-member"),
    ok("apply_json_patch", {"json_text": '{"foo": ["bar", "baz"]}', "patch_json": '[{"op": "add", "path": "/foo/1", "value": "qux"}]'}, {"json": '{"foo":["bar","qux","baz"]}', "applied_operations": 1}, "rfc6902-a2-add-element"),
    ok("apply_json_patch", {"json_text": '{"baz": "qux", "foo": "bar"}', "patch_json": '[{"op": "remove", "path": "/baz"}]'}, {"json": '{"foo":"bar"}', "applied_operations": 1}, "rfc6902-a3-remove"),
    ok("apply_json_patch", {"json_text": '{"baz": "qux", "foo": "bar"}', "patch_json": '[{"op": "replace", "path": "/baz", "value": "boo"}]'}, {"json": '{"baz":"boo","foo":"bar"}', "applied_operations": 1}, "rfc6902-a5-replace"),
    ok("apply_json_patch", {"json_text": '{"foo": {"bar": "baz", "waldo": "fred"}, "qux": {"corge": "grault"}}', "patch_json": '[{"op": "move", "from": "/foo/waldo", "path": "/qux/thud"}]'}, {"json": '{"foo":{"bar":"baz"},"qux":{"corge":"grault","thud":"fred"}}', "applied_operations": 1}, "rfc6902-a6-move"),
    ok("apply_json_patch", {"json_text": '{"baz": "qux", "foo": ["a", 2, "c"]}', "patch_json": '[{"op": "test", "path": "/baz", "value": "qux"}, {"op": "test", "path": "/foo/1", "value": 2}]'}, {"json": '{"baz":"qux","foo":["a",2,"c"]}', "applied_operations": 2}, "rfc6902-a8-test-success"),
    ok("apply_json_patch", {"json_text": '{"foo": ["bar"]}', "patch_json": '[{"op": "add", "path": "/foo/-", "value": ["abc", "def"]}]'}, {"json": '{"foo":["bar",["abc","def"]]}', "applied_operations": 1}, "rfc6902-a16-add-array-value"),
    ok("apply_json_patch", {"json_text": '{"a": {"b": 1}}', "patch_json": '[{"op": "copy", "from": "/a", "path": "/c"}]'}, {"json": '{"a":{"b":1},"c":{"b":1}}', "applied_operations": 1}, "copy"),
    ok("summarize_json_structure", {"json_text": '{"a": [{"x": 1}, {"x": "s", "y": true}], "b": null}'}, {"top_level_type": "object", "max_nesting": 3, "value_count": 8, "shape": {"a": [{"x": "number|string", "y?": "boolean"}], "b": "null"}}, "merged-objects"),
    ok("summarize_json_structure", {"json_text": "5"}, {"top_level_type": "number", "max_nesting": 0, "value_count": 1, "shape": "number"}, "scalar"),
    ok("summarize_json_structure", {"json_text": "[]"}, {"top_level_type": "array", "max_nesting": 1, "value_count": 1, "shape": []}, "empty-array"),
    ok("summarize_json_structure", {"json_text": '[[1], [], ["a"]]'}, {"top_level_type": "array", "max_nesting": 2, "value_count": 6, "shape": [["number|string"]]}, "merged-arrays"),
    ok("summarize_json_structure", {"json_text": '[{"a": 1}, 2, null]'}, {"top_level_type": "array", "max_nesting": 2, "value_count": 5, "shape": ["null|number|object"]}, "mixed-types-sorted"),
    ok("extract_json_from_text", {"text": 'Result: {"a": 1} and [1, 2] then 42 and {bad} ok'}, {"documents": [{"start": 8, "end": 16, "value": {"a": 1}}, {"start": 21, "end": 27, "value": [1, 2]}], "count": 2, "truncated": False}, "objects-and-arrays-no-scalars"),
    ok("extract_json_from_text", {"text": 'x [NaN] y {"k": [1, {"m": null}]} z'}, {"documents": [{"start": 10, "end": 33, "value": {"k": [1, {"m": None}]}}], "count": 1, "truncated": False}, "nan-candidate-skipped-no-overlap"),
    ok("extract_json_from_text", {"text": '[1, {"x": 2}] {"y": [3]}'}, {"documents": [{"start": 0, "end": 13, "value": [1, {"x": 2}]}, {"start": 14, "end": 24, "value": {"y": [3]}}], "count": 2, "truncated": False}, "continues-after-document"),
    ok("extract_json_from_text", {"text": "[" * 101 + "]" * 101 + ' {"a": 1}'}, {"documents": [{"start": 1, "end": 201, "value": nested_empty_lists(100)}, {"start": 203, "end": 211, "value": {"a": 1}}], "count": 2, "truncated": False}, "too-deep-candidate-skipped"),
    ok("extract_json_from_text", {"text": "no json here 1 2 3"}, {"documents": [], "count": 0, "truncated": False}, "nothing-found"),
    # S4 R-5 (spec r6 A.17, INV-19): a float overflow makes a candidate invalid, so it is skipped and the scan goes on.
    ok("extract_json_from_text", {"text": 'x {"a":1e400} y'}, {"documents": [], "count": 0, "truncated": False}, "float-overflow-candidate-skipped"),
    ok("extract_json_from_text", {"text": '{"a":-1e999,"b":[1E309]}'}, {"documents": [], "count": 0, "truncated": False}, "negative-and-capital-e-overflow-skipped"),
    ok("extract_json_from_text", {"text": 'x {"a":1e400} {"b":2} y'}, {"documents": [{"start": 14, "end": 21, "value": {"b": 2}}], "count": 1, "truncated": False}, "scan-continues-after-overflow"),
]

JSON_RECORDS_CASES = [
    ok("filter_records", {"records_json": FILTER_ORDER_RECORDS, "field": "n", "operator": "greater_or_equal", "value": "5"}, {"records": [{"n": 5}, {"n": 12.5}, {"n": "x"}], "matched": 3}, "number-and-text-order"),
    ok("filter_records", {"records_json": '[{"n": 5}, {"n": "5"}, {"n": 5.5}]', "field": "n", "operator": "equals", "value": "5.0"}, {"records": [{"n": 5}], "matched": 1}, "value-read-as-field-type"),
    ok("filter_records", {"records_json": '[{"n": 5}]', "field": "n", "operator": "equals", "value": "abc"}, {"records": [], "matched": 0}, "non-numeric-value-on-number"),
    ok("filter_records", {"records_json": '[{"s": "Apple pie"}, {"s": "apple"}, {"s": ["apple", "x"]}, {"s": ["Apple"]}]', "field": "s", "operator": "contains", "value": "apple"}, {"records": [{"s": "apple"}, {"s": ["apple", "x"]}], "matched": 2}, "contains-case-sensitive-and-membership"),
    ok("filter_records", {"records_json": EMPTY_RECORDS, "field": "a", "operator": "is_empty"}, {"records": [{"a": ""}, {"a": None}, {}, {"a": []}, {"a": {}}], "matched": 5}, "is-empty"),
    ok("filter_records", {"records_json": EMPTY_RECORDS, "field": "a", "operator": "is_not_empty"}, {"records": [{"a": 0}, {"a": " "}], "matched": 2}, "is-not-empty"),
    ok("filter_records", {"records_json": '[{"b": true}, {"b": false}, {"b": "true"}]', "field": "b", "operator": "equals", "value": "true"}, {"records": [{"b": True}, {"b": "true"}], "matched": 2}, "boolean-field"),
    ok("filter_records", {"records_json": '[{"n": 1}, {"n": 2}, {}]', "field": "n", "operator": "not_equals", "value": "1"}, {"records": [{"n": 2}], "matched": 1}, "missing-matches-only-is-empty"),
    ok("pluck_field", {"records_json": '[{"a": 1}, {"b": 2}, {"a": null}, {"a": [1]}]', "field": "a"}, {"values": [1, None, None, [1]], "missing": 1}, "missing-versus-null"),
    ok("group_records_by_field", {"records_json": GROUP_RECORDS, "field": "k"}, {"groups": [{"key": 1, "count": 2, "records": [{"k": 1, "i": 0}, {"k": 1.0, "i": 2}]}, {"key": "1", "count": 1, "records": [{"k": "1", "i": 1}]}, {"key": None, "count": 2, "records": [{"i": 3}, {"k": None, "i": 4}]}, {"key": True, "count": 1, "records": [{"k": True, "i": 5}]}, {"key": [1], "count": 2, "records": [{"k": [1], "i": 6}, {"k": [1], "i": 7}]}]}, "type-aware-keys"),
    ok("aggregate_field", {"records_json": MIXED_VALUES, "field": "v", "function": "sum"}, {"result": 3.5, "values_used": 2, "values_skipped": 2}, "sum-skips-text-and-booleans"),
    ok("aggregate_field", {"records_json": MIXED_VALUES, "field": "v", "function": "mean"}, {"result": 1.75, "values_used": 2, "values_skipped": 2}, "mean"),
    ok("aggregate_field", {"records_json": '[{"v": 4}, {"v": 1}, {"v": 3}, {"v": 2}]', "field": "v", "function": "median"}, {"result": 2.5, "values_used": 4, "values_skipped": 0}, "median-even"),
    ok("aggregate_field", {"records_json": '[{"v": true}, {"v": 3}, {"v": 2}]', "field": "v", "function": "min"}, {"result": 2.0, "values_used": 2, "values_skipped": 1}, "min-ignores-boolean"),
    ok("aggregate_field", {"records_json": '[{"v": true}, {"v": 3}, {"v": 2}]', "field": "v", "function": "max"}, {"result": 3.0, "values_used": 2, "values_skipped": 1}, "max"),
    ok("aggregate_field", {"records_json": '[{"v": "a"}, {"v": "a"}, {"v": "b"}, {"v": 2}]', "field": "v", "function": "count"}, {"result": 4, "values_used": 4, "values_skipped": 0}, "count-integer"),
    ok("aggregate_field", {"records_json": '[{"v": "a"}, {"v": "a"}, {"v": "b"}, {"v": 2}]', "field": "v", "function": "distinct_count"}, {"result": 3, "values_used": 4, "values_skipped": 0}, "distinct-count"),
    ok("aggregate_field", {"records_json": '[{"v": "a"}]', "field": "v", "function": "sum"}, {"result": None, "values_used": 0, "values_skipped": 1}, "no-usable-values"),
    ok("group_and_aggregate_records", {"records_json": GROUP_AGG_RECORDS, "group_by_field": "g", "value_field": "v", "function": "sum"}, {"groups": [{"key": "x", "result": 3.0, "values_used": 2}, {"key": "y", "result": 10.0, "values_used": 1}, {"key": None, "result": 5.0, "values_used": 1}]}, "sum"),
    ok("group_and_aggregate_records", {"records_json": GROUP_AGG_RECORDS, "group_by_field": "g", "value_field": "v", "function": "count"}, {"groups": [{"key": "x", "result": 2, "values_used": 2}, {"key": "y", "result": 2, "values_used": 2}, {"key": None, "result": 1, "values_used": 1}]}, "count"),
    ok("sort_records", {"records_json": SORT_MIXED, "field": "f"}, {"records": [{"f": 1.5}, {"f": 2}, {"f": "a"}, {"f": "b"}, {"f": False}, {"f": True}, {"f": [1]}, {"f": {"z": 1}}, {"id": "m"}, {"f": None}]}, "ec34-mixed-type-order"),
    ok("sort_records", {"records_json": '[{"f": 2, "i": 0}, {"f": 1}, {}, {"f": 3}, {"f": null}, {"f": 2, "i": 1}]', "field": "f", "descending": True}, {"records": [{"f": 3}, {"f": 2, "i": 0}, {"f": 2, "i": 1}, {"f": 1}, {}, {"f": None}]}, "descending-stable-missing-last"),
    ok("count_field_values", {"records_json": COUNT_RECORDS, "field": "c"}, {"total": 7, "distinct": 4, "counts": [{"value": "x", "count": 2}, {"value": "y", "count": 2}, {"value": None, "count": 2}, {"value": "z", "count": 1}]}, "ties-by-first-appearance"),
    ok("count_field_values", {"records_json": COUNT_RECORDS, "field": "c", "top": 2}, {"total": 7, "distinct": 4, "counts": [{"value": "x", "count": 2}, {"value": "y", "count": 2}]}, "top-limits-counts-only"),
    ok("join_records", {"left_json": JOIN_LEFT, "right_json": JOIN_RIGHT, "left_field": "id", "right_field": "user_id"}, {"records": [{"id": 1, "name": "a", "user_id": 1, "right_name": "x", "v": 10}, {"id": 1, "name": "a", "user_id": 1, "v": 11}], "count": 2, "truncated": False}, "inner-type-aware"),
    ok("join_records", {"left_json": JOIN_LEFT, "right_json": JOIN_RIGHT, "left_field": "id", "right_field": "user_id", "kind": "left"}, {"records": [{"id": 1, "name": "a", "user_id": 1, "right_name": "x", "v": 10}, {"id": 1, "name": "a", "user_id": 1, "v": 11}, {"id": 2, "name": "b"}, {"id": None, "name": "c"}, {"name": "d"}], "count": 5, "truncated": False}, "left-keeps-unmatched"),
    ok("records_to_csv", {"records_json": CSV_RECORDS}, {"csv": 'a,b,c\n1,"x,y",\n,"q""t",true\n,,"[1,2]"\n1.5,"line\nbreak",\n', "rows": 4, "columns": ["a", "b", "c"]}, "union-columns-quote-minimal"),
    ok("records_to_csv", {"records_json": CSV_RECORDS, "columns": ["c", "a"]}, {"csv": 'c,a\n,1\ntrue,\n"[1,2]",\n,1.5\n', "rows": 4, "columns": ["c", "a"]}, "chosen-columns"),
    ok("records_to_csv", {"records_json": '[{"a": 1, "b": "x,y"}]', "delimiter": "semicolon"}, {"csv": "a;b\n1;x,y\n", "rows": 1, "columns": ["a", "b"]}, "semicolon"),
    ok("records_to_csv", {"records_json": '[{"a": 1.0, "b": false}]', "delimiter": "pipe"}, {"csv": "a|b\n1.0|false\n", "rows": 1, "columns": ["a", "b"]}, "pipe-json-numbers"),
]

CSV_TABLES_CASES = [
    ok("csv_to_records", {"csv_text": "name,age\nAnn,30\nBob,\n", "delimiter": "comma"}, {"records": [{"name": "Ann", "age": "30"}, {"name": "Bob", "age": ""}], "columns": ["name", "age"], "rows": 2}, "strings-by-default"),
    ok("csv_to_records", {"csv_text": "a,b,c\n1\n", "delimiter": "comma"}, {"records": [{"a": "1", "b": "", "c": ""}], "columns": ["a", "b", "c"], "rows": 1}, "short-row-padded"),
    ok("csv_to_records", {"csv_text": "i,f,b,e,t,x\n 7 ,2.50,TRUE,  ,x1,1e3\n", "delimiter": "comma", "infer_types": True}, {"records": [{"i": 7, "f": 2.5, "b": True, "e": None, "t": "x1", "x": 1000.0}], "columns": ["i", "f", "b", "e", "t", "x"], "rows": 1}, "infer-types"),
    ok("csv_to_records", {"csv_text": "a,b\r\n\"x\ny\",2\r\n", "delimiter": "comma"}, {"records": [{"a": "x\ny", "b": "2"}], "columns": ["a", "b"], "rows": 1}, "crlf-and-quoted-newline"),
    ok("csv_to_records", {"csv_text": "a;b;c\n1;2;3\n4;5;6\n"}, {"records": [{"a": "1", "b": "2", "c": "3"}, {"a": "4", "b": "5", "c": "6"}], "columns": ["a", "b", "c"], "rows": 2}, "detects-semicolon"),
    ok("detect_csv_dialect", {"csv_text": "a;b;c\n1;2;3\n4;5;6\n"}, {"delimiter": "semicolon", "has_header": True, "quote_character": "\"", "columns": 3, "rows": 2}, "semicolon"),
    ok("detect_csv_dialect", {"csv_text": "a\tb\n1\t2\n"}, {"delimiter": "tab", "has_header": ANY, "quote_character": "\"", "columns": 2, "rows": 1}, "tab"),
    ok("detect_csv_dialect", {"csv_text": "abc\n"}, {"delimiter": "comma", "has_header": ANY, "quote_character": "\"", "columns": 1, "rows": 0}, "falls-back-to-comma"),
    ok("profile_csv_columns", {"csv_text": PROFILE_CSV, "delimiter": "comma"}, {"rows": 3, "columns": [
        {"name": "id", "inferred_type": "integer", "non_empty": 3, "empty": 0, "distinct": 2, "min": "3", "max": "10", "mean": 16 / 3, "examples": ["3", "10"]},
        {"name": "price", "inferred_type": "number", "non_empty": 3, "empty": 0, "distinct": 3, "min": "-1", "max": "7", "mean": 8.5 / 3, "examples": ["2.5", "-1", "7"]},
        {"name": "flag", "inferred_type": "boolean", "non_empty": 3, "empty": 0, "distinct": 2, "min": "FALSE", "max": "true", "mean": None, "examples": ["true", "FALSE"]},
        {"name": "day", "inferred_type": "date", "non_empty": 3, "empty": 0, "distinct": 2, "min": "2023-12-31", "max": "2024-01-02", "mean": None, "examples": ["2024-01-02", "2023-12-31"]},
        {"name": "name", "inferred_type": "text", "non_empty": 3, "empty": 0, "distinct": 2, "min": "Bob", "max": "alice", "mean": None, "examples": ["Bob", "alice"]},
        {"name": "blank", "inferred_type": "empty", "non_empty": 0, "empty": 3, "distinct": 0, "min": None, "max": None, "mean": None, "examples": []},
    ]}, "all-column-types"),
    ok("profile_csv_columns", {"csv_text": "q\n02\n2\n5\n", "delimiter": "comma"}, {"rows": 3, "columns": [{"name": "q", "inferred_type": "integer", "non_empty": 3, "empty": 0, "distinct": 3, "min": "02", "max": "5", "mean": 3.0, "examples": ["02", "2", "5"]}]}, "equal-values-first-in-row-order"),
    ok("csv_filter_rows", {"csv_text": FILTER_CSV, "column": "qty", "operator": "greater_than", "value": "9", "delimiter": "comma"}, {"csv": "name,qty\nA,10\nC,x\n", "matched": 2}, "numeric-then-text-comparison"),
    ok("csv_filter_rows", {"csv_text": FILTER_CSV, "column": "qty", "operator": "is_empty", "delimiter": "comma"}, {"csv": "name,qty\nD,\nE, \n", "matched": 2}, "whitespace-cell-is-empty"),
    ok("csv_filter_rows", {"csv_text": "v\n1.0\n1\n01\nx\n", "column": "v", "operator": "equals", "value": "1", "delimiter": "comma"}, {"csv": "v\n1.0\n1\n01\n", "matched": 3}, "numeric-equality"),
    ok("csv_filter_rows", {"csv_text": "name\nBanana\nAN\nman\n", "column": "name", "operator": "contains", "value": "an", "delimiter": "comma"}, {"csv": "name\nBanana\nman\n", "matched": 2}, "contains-case-sensitive"),
    ok("csv_sort_rows", {"csv_text": "f\nfile10\nfile2\nFile1\n", "column": "f", "delimiter": "comma"}, {"csv": "f\nFile1\nfile2\nfile10\n", "rows": 3}, "natural-default"),
    ok("csv_sort_rows", {"csv_text": "v,i\n10,a\nabc,b\n-2,c\n3.5,d\nzz,e\n", "column": "v", "mode": "numeric", "delimiter": "comma"}, {"csv": "v,i\n-2,c\n3.5,d\n10,a\nabc,b\nzz,e\n", "rows": 5}, "numeric-then-others-in-order"),
    ok("csv_sort_rows", {"csv_text": "k,i\nx,1\nb,2\nx,3\na,4\n", "column": "k", "mode": "text", "descending": True, "delimiter": "comma"}, {"csv": "k,i\nx,1\nx,3\nb,2\na,4\n", "rows": 4}, "descending-stable"),
    ok("csv_sort_rows", {"csv_text": "w\nccc\nb\naa\nab\n", "column": "w", "mode": "length", "delimiter": "comma"}, {"csv": "w\nb\naa\nab\nccc\n", "rows": 4}, "length-then-code-point"),
    ok("csv_sort_rows", {"csv_text": "w\nb\nB\na\n", "column": "w", "mode": "case_insensitive", "delimiter": "comma"}, {"csv": "w\na\nB\nb\n", "rows": 3}, "case-insensitive-ties-by-code-point"),
    ok("csv_aggregate_column", {"csv_text": AGGREGATE_CSV, "column": "v", "function": "sum", "delimiter": "comma"}, {"result": 7.5, "values_used": 3, "values_skipped": 1}, "sum"),
    ok("csv_aggregate_column", {"csv_text": AGGREGATE_CSV, "column": "v", "function": "mean", "delimiter": "comma"}, {"result": 2.5, "values_used": 3, "values_skipped": 1}, "mean"),
    ok("csv_aggregate_column", {"csv_text": AGGREGATE_CSV, "column": "v", "function": "median", "delimiter": "comma"}, {"result": 2.5, "values_used": 3, "values_skipped": 1}, "median"),
    ok("csv_aggregate_column", {"csv_text": AGGREGATE_CSV, "column": "v", "function": "max", "delimiter": "comma"}, {"result": 4.0, "values_used": 3, "values_skipped": 1}, "max"),
    ok("csv_aggregate_column", {"csv_text": "id,v\na,1\nb,1\nc,x\n", "column": "v", "function": "count", "delimiter": "comma"}, {"result": 3, "values_used": 3, "values_skipped": 0}, "count"),
    ok("csv_aggregate_column", {"csv_text": "id,v\na,1\nb,1\nc,x\n", "column": "v", "function": "distinct_count", "delimiter": "comma"}, {"result": 2, "values_used": 3, "values_skipped": 0}, "distinct-count"),
    ok("csv_group_by", {"csv_text": GROUP_CSV, "group_column": "g", "value_column": "v", "function": "sum", "delimiter": "comma"}, {"groups": [{"key": "x", "result": 3.0, "values_used": 2}, {"key": "y", "result": 10.0, "values_used": 1}, {"key": "", "result": 5.0, "values_used": 1}]}, "sum-empty-key-group"),
    ok("csv_group_by", {"csv_text": GROUP_CSV, "group_column": "g", "value_column": "v", "function": "count", "delimiter": "comma"}, {"groups": [{"key": "x", "result": 2, "values_used": 2}, {"key": "y", "result": 2, "values_used": 2}, {"key": "", "result": 1, "values_used": 1}]}, "count"),
    ok("csv_join_tables", {"left_csv": JOIN_LEFT_CSV, "right_csv": JOIN_RIGHT_CSV, "left_column": "id", "right_column": "id", "delimiter": "comma"}, {"csv": JOINED_CSV, "rows": 2, "truncated": False}, "inner-text-keys"),
    ok("csv_join_tables", {"left_csv": JOIN_LEFT_CSV, "right_csv": JOIN_RIGHT_CSV, "left_column": "id", "right_column": "id", "kind": "left", "delimiter": "comma"}, {"csv": JOINED_CSV + "2,b,,\n01,c,,\n", "rows": 4, "truncated": False}, "left-pads-empty"),
    ok(
        "csv_to_markdown_table",
        {"csv_text": "name,qty\nA|B,10\n\"x\ny\",2\n", "delimiter": "comma", "alignment": "auto"},
        {"markdown": "| name | qty |\n| :--- | ---: |\n| A\\|B | 10 |\n| x<br>y | 2 |", "rows": 2, "columns": 2},
        "auto-exact-text",
    ),
]

SUCCESS_CASES = JSON_DATA_CASES + JSON_RECORDS_CASES + CSV_TABLES_CASES

FAILURE_CASES = [
    bad("format_json", {"json_text": '{"a": 1,}'}, "json_text", "syntax-error-position", contains="parsing stopped at line 1, column 9: Expecting property name enclosed in double quotes"),
    bad("format_json", {"json_text": "[1, NaN]"}, "json_text", "nan-constant"),
    bad("json_get_value", {"json_text": "Infinity", "pointer": ""}, "json_text", "infinity-constant"),
    bad("json_get_value", {"json_text": NESTED_JSON_DOC, "pointer": "a"}, "pointer", "missing-leading-slash"),
    bad("json_get_value", {"json_text": NESTED_JSON_DOC, "pointer": "/a~2"}, "pointer", "bad-tilde-escape"),
    bad("json_set_value", {"json_text": SET_DOC, "pointer": "/x/y", "value_json": "1"}, "pointer", "missing-parent"),
    bad("json_set_value", {"json_text": SET_DOC, "pointer": "/a/5", "value_json": "1"}, "pointer", "index-past-length"),
    bad("json_set_value", {"json_text": SET_DOC, "pointer": "/b/c", "value_json": "1"}, "pointer", "through-scalar"),
    bad("json_set_value", {"json_text": SET_DOC, "pointer": "/b", "value_json": "{"}, "value_json", "invalid-value-json"),
    bad("apply_json_patch", {"json_text": '{"baz": "qux"}', "patch_json": '[{"op": "test", "path": "/baz", "value": "bar"}]'}, "patch_json", "rfc6902-a9-failed-test"),
    bad("apply_json_patch", {"json_text": '{"foo": "bar"}', "patch_json": '[{"op": "add", "path": "/baz/bat", "value": "qux"}]'}, "patch_json", "rfc6902-a12-missing-target"),
    bad("apply_json_patch", {"json_text": '{"foo": "bar"}', "patch_json": '[{"op": "add", "path": "/x", "value": 1}, {"op": "remove", "path": "/nope"}]'}, "patch_json", "atomic-second-op-fails"),
    bad("apply_json_patch", {"json_text": '{"foo": "bar"}', "patch_json": '{"op": "add", "path": "/x", "value": 1}'}, "patch_json", "patch-not-array"),
    bad("apply_json_patch", {"json_text": '{"foo": "bar"}', "patch_json": '[{"op": "frobnicate", "path": "/foo"}]'}, "patch_json", "unknown-op"),
    bad("summarize_json_structure", {"json_text": "[" * 101 + "]" * 101}, "json_text", "nesting-over-100"),
    bad("filter_records", {"records_json": '[{"a": 1}, 2]', "field": "a", "operator": "equals", "value": "1"}, "records_json", "element-not-object"),
    bad("pluck_field", {"records_json": '{"a": 1}', "field": "a"}, "records_json", "top-level-not-array"),
    bad("aggregate_field", {"records_json": '[{"v": 1e308}, {"v": 1e308}]', "field": "v", "function": "sum"}, "field", "non-finite-sum"),
    bad("records_to_csv", {"records_json": WIDE_RECORD}, "records_json", "over-500-columns"),
    bad("csv_to_records", {"csv_text": "a,b\n1,2,3\n", "delimiter": "comma"}, "csv_text", "row-longer-than-header"),
    bad("csv_to_records", {"csv_text": "a,a\n1,2\n", "delimiter": "comma"}, "csv_text", "duplicate-header"),
    bad("csv_to_records", {"csv_text": "a,\n1,2\n", "delimiter": "comma"}, "csv_text", "empty-header-name"),
    bad("csv_filter_rows", {"csv_text": FILTER_CSV, "column": "zz", "operator": "equals", "value": "1", "delimiter": "comma"}, "column", "unknown-column"),
    bad("csv_sort_rows", {"csv_text": "k\nb\na\n", "column": "zz", "delimiter": "comma"}, "column", "unknown-column"),
    bad("csv_join_tables", {"left_csv": JOIN_LEFT_CSV, "right_csv": JOIN_RIGHT_CSV, "left_column": "id", "right_column": "zz", "delimiter": "comma"}, "right_column", "unknown-right-column"),
    invalid("format_json", {"json_text": [1, 2]}, "json_text", "ec30-array-for-json-text"),
    invalid("format_json", {"json_text": "{}", "indent": 9}, "indent", "indent-over-8"),
    invalid("apply_json_patch", {"json_text": "{}", "patch_json": [{"op": "add", "path": "/x", "value": 1}]}, "patch_json", "ec30-array-for-patch"),
    invalid("filter_records", {"records_json": "[]", "field": "", "operator": "equals"}, "field", "empty-name"),
    invalid("filter_records", {"records_json": "[]", "field": "a", "operator": "like"}, "operator", "unknown-operator"),
    invalid("count_field_values", {"records_json": "[]", "field": "a", "top": 0}, "top", "top-below-1"),
    invalid("records_to_csv", {"records_json": "[]", "delimiter": "colon"}, "delimiter", "unknown-delimiter"),
    invalid("csv_sort_rows", {"csv_text": "k\na\n", "column": "k", "mode": "random"}, "mode", "unknown-mode"),
]


@pytest.mark.parametrize("case", SUCCESS_CASES)
def test_json_csv_rows_return_documented_output(tool_runner: ToolRunner, case: SuccessCase) -> None:
    tool_runner.check_success(case)


@pytest.mark.parametrize("case", FAILURE_CASES)
def test_json_csv_rows_reject_bad_input(tool_runner: ToolRunner, case: FailureCase) -> None:
    tool_runner.check_failure(case)


def test_csv_to_records_infers_integer_and_float_types(tool_runner: ToolRunner) -> None:
    # The output matcher lets an int stand in for an expected float, so the JSON number types are pinned here.
    text = "i,f,x,big,neg\n 7 ,2.50,1e3,9007199254740993,-0\n"
    output = tool_runner.output("csv_to_records", {"csv_text": text, "delimiter": "comma", "infer_types": True})
    record = output["records"][0]
    assert type(record["i"]) is int and record["i"] == 7
    assert type(record["f"]) is float and record["f"] == 2.5
    assert type(record["x"]) is float and record["x"] == 1000.0
    # 2^53 + 1 is not an integer under the numeric text rule, so it becomes the nearest float.
    assert type(record["big"]) is float and record["big"] == 9007199254740992.0
    assert type(record["neg"]) is int and record["neg"] == 0


def test_csv_to_markdown_table_escapes_cells_and_aligns_columns(tool_runner: ToolRunner) -> None:
    text = "name,qty\nA|B,10\n\"x\ny\",2\n"
    body = "| A\\|B | 10 |\n| x<br>y | 2 |"
    # Spec r4 fixes the whole text: one space around each cell, no other padding, and no trailing line break.
    separators = {"left": "| :--- | :--- |", "center": "| :---: | :---: |", "right": "| ---: | ---: |", "auto": "| :--- | ---: |"}
    for alignment, separator in separators.items():
        output = tool_runner.output("csv_to_markdown_table", {"csv_text": text, "delimiter": "comma", "alignment": alignment})
        assert output["markdown"] == f"| name | qty |\n{separator}\n{body}", (alignment, output["markdown"])
    default = tool_runner.output("csv_to_markdown_table", {"csv_text": text, "delimiter": "comma"})
    assert markdown_cells(default["markdown"].split("\n")[1]) == [":---", ":---"], default["markdown"]
