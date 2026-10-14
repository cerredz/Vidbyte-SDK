"""FILE: vidbyte/tools/builtins/prebuilt/json_records.py

PURPOSE: Defines JsonRecordsToolFunctions, the nine prebuilt tools that work on a record set, a JSON array of objects: filtering, plucking one field, grouping, aggregating, grouping with aggregation, sorting, counting values, joining two record sets, and writing records as CSV.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the JSON_RECORDS category is chosen. Builds on PrebuiltToolSupport in _support.py for record parsing, the numeric text rule, finite float results, the item cap, and the argument error.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Field values are compared type-aware through one group key, a JSON type tag plus the value, or plus the compact JSON text for objects and arrays, so grouping, distinct counts, value counts, and joins all agree. Groups live in insertion-ordered dicts keyed by that group key, which keeps every output in order of first appearance.
FUNCTION INVENTORY: filter_records, pluck_field, group_records_by_field, aggregate_field, group_and_aggregate_records, sort_records, count_field_values, join_records, and records_to_csv are the tools. _field_matches applies one filter comparison; _group_key builds the type-aware key; _aggregate computes one aggregate; _sort_key orders mixed types; _joined_records merges matching records lazily; _csv_cell writes one CSV cell; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new record tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.18, and its entry in tool_functions. A new comparison or aggregate adds its enum member in vidbyte/lib/enums/prebuilt_tools.py and its entry in _COMPARISONS or _NUMERIC_AGGREGATES here.
WHAT NOT TO DO IN THIS FILE: 1. Do not compare field values with == or hash them directly, because true equals 1 in Python; use _group_key. 2. Do not iterate a set or a hash-ordered container when building an output. 3. Do not enumerate joined records to count them; the count is computed from the match lists so a large join never has to be built.
KNOWN EDGE CASES: A JSON integer too large for a float makes the numeric aggregates fail naming the field parameter. When a right record's key is renamed to right_ plus its name and the left record already has that renamed key, the right value replaces it. The csv module quotes a cell holding the delimiter, a quote, or a line feed, but writes a lone carriage return as it is. Order comparisons on text, booleans, objects, and arrays compare code points of the field's text against the value.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.18, section 9.2 items 3, 5, 12, 13, 14, and 15); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_json_csv.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import io
import json
import math
import statistics
from collections.abc import Callable, Iterator
from operator import contains, eq, ge, gt, le, lt, ne
from types import MappingProxyType
from typing import Annotated, Any

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_MAX_NAME_CHARS,
    PREBUILT_MAX_RECORDS,
    PREBUILT_MAX_SHORT_TEXT_CHARS,
    PREBUILT_MAX_TABLE_COLUMNS,
    PREBUILT_MAX_TEXT_CHARS,
    PREBUILT_MAX_TOP_ITEMS,
)
from vidbyte.lib.enums.prebuilt_tools import (
    AggregateFunction,
    CsvDelimiter,
    FilterOperator,
    JoinKind,
    JsonType,
)
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_COMPACT_SEPARATORS = (",", ":")
_JSON_TYPES = MappingProxyType({dict: JsonType.OBJECT, list: JsonType.ARRAY, str: JsonType.STRING, bool: JsonType.BOOLEAN, int: JsonType.NUMBER, float: JsonType.NUMBER, type(None): JsonType.NULL})
_SORT_RANKS = MappingProxyType({JsonType.NUMBER: 0, JsonType.STRING: 1, JsonType.BOOLEAN: 2, JsonType.OBJECT: 3, JsonType.ARRAY: 3})
_BOOLEAN_TEXTS = frozenset({"true", "false"})
_TEXT_OPERATORS = frozenset({FilterOperator.CONTAINS, FilterOperator.STARTS_WITH, FilterOperator.ENDS_WITH})
_COMPARISONS: MappingProxyType[FilterOperator, Callable[[Any, Any], object]] = MappingProxyType(
    {
        FilterOperator.EQUALS: eq,
        FilterOperator.NOT_EQUALS: ne,
        FilterOperator.GREATER_THAN: gt,
        FilterOperator.GREATER_OR_EQUAL: ge,
        FilterOperator.LESS_THAN: lt,
        FilterOperator.LESS_OR_EQUAL: le,
        FilterOperator.CONTAINS: contains,
        FilterOperator.STARTS_WITH: str.startswith,
        FilterOperator.ENDS_WITH: str.endswith,
    }
)
_NUMERIC_AGGREGATES: MappingProxyType[AggregateFunction, Callable[[list[float]], float]] = MappingProxyType(
    {
        AggregateFunction.SUM: math.fsum,
        AggregateFunction.MEAN: statistics.fmean,
        AggregateFunction.MIN: min,
        AggregateFunction.MAX: max,
        AggregateFunction.MEDIAN: statistics.median,
    }
)

_RECORDS_PARAMETER_DESCRIPTION = "The records, given as the text of a JSON array whose elements are all objects. Each object is one record, and its top-level keys are its fields. An element that is not an object fails with an error naming its index. The array may hold at most 10,000 records in at most one million characters."
_FIELD_PARAMETER_DESCRIPTION = "The name of the field to read, matched exactly against each record's top-level keys. Nested fields are not reached, so a dotted name is simply a key that contains a dot. A record that lacks the key counts as missing, which is distinct from a null value. The name must hold 1 to 200 characters."
_FUNCTION_PARAMETER_DESCRIPTION = "The aggregate to compute: count, sum, mean, min, max, median, or distinct_count. Count and distinct_count use present non-null values of any type and return integers. The other functions use JSON numbers only, never booleans, and skip every other value. A sum that is not finite fails with an error."


class JsonRecordsToolFunctions:
    """The json_records category: filtering, grouping, aggregating, sorting, joining, and exporting record sets."""

    @staticmethod
    def filter_records(
        records_json: Annotated[str, Field(description=_RECORDS_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        field: Annotated[str, Field(description=_FIELD_PARAMETER_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
        operator: Annotated[FilterOperator, Field(description="The comparison to apply between each record's field and the value. Order comparisons are numeric for number fields and by code point for text, and contains, starts_with, and ends_with are case-sensitive. The is_empty operator matches a missing field, null, an empty string, an empty array, or an empty object, and is_not_empty matches everything else. Those two operators ignore the value.")],
        value: Annotated[str, Field(description="The value to compare each field with, given as text. For a number field it must be numeric text, and for a boolean field it must be true or false, or the record does not match. For text, arrays, and objects it is compared as written. The default is the empty string.", max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)] = "",
    ) -> PrebuiltToolOutput:
        """Keep the records whose field satisfies a comparison with a value, in their original order, and report how many matched. Use it to select records by an exact value, a numeric range, a text prefix or suffix, a substring, or whether a field is empty. The value is read as the type of each record's field: numeric text for number fields, true or false for boolean fields, and text otherwise, while contains on an array field tests membership. A missing or null field matches only is_empty, and a records_json that is not a JSON array of objects fails with an error."""
        records = PrebuiltToolSupport.records_from_json(PrebuiltToolSupport.parse_json_text(records_json, "records_json"), "records_json")
        number = PrebuiltToolSupport.parse_numeric_text(value)
        kept = [record for record in records if JsonRecordsToolFunctions._field_matches(record.get(field), operator, value, number)]
        return {"records": kept, "matched": len(kept)}

    @staticmethod
    def pluck_field(
        records_json: Annotated[str, Field(description=_RECORDS_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        field: Annotated[str, Field(description=_FIELD_PARAMETER_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
    ) -> PrebuiltToolOutput:
        """Extract one field from every record into a list, in record order, with null in place of each missing field. Use it to get a single column of values out of a record set before counting, summing, or comparing them. A present null and a missing field both appear as null, but only missing fields are counted in missing. A records_json that is not a JSON array of objects fails with an error naming records_json."""
        records = PrebuiltToolSupport.records_from_json(PrebuiltToolSupport.parse_json_text(records_json, "records_json"), "records_json")
        return {"values": [record.get(field) for record in records], "missing": sum(1 for record in records if field not in record)}

    @staticmethod
    def group_records_by_field(
        records_json: Annotated[str, Field(description=_RECORDS_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        field: Annotated[str, Field(description=_FIELD_PARAMETER_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
    ) -> PrebuiltToolOutput:
        """Group records by the value of one field and return each group's key, size, and records, in order of first appearance. Use it to split a record set into categories before summarizing or comparing them. Keys compare type-aware, so a number and a string never share a group while an integer and a float of the same value do, and objects and arrays compare by their compact JSON text. Records that lack the field share the null group with records whose field is null, and invalid records fail naming records_json."""
        records = PrebuiltToolSupport.records_from_json(PrebuiltToolSupport.parse_json_text(records_json, "records_json"), "records_json")
        # Each group keeps the first key value seen and its records.
        groups: dict[tuple[JsonType, object], tuple[object, list[dict[str, object]]]] = {}
        for record in records:
            key = record.get(field)
            groups.setdefault(JsonRecordsToolFunctions._group_key(key), (key, []))[1].append(record)
        return {"groups": [{"key": key, "count": len(members), "records": members} for key, members in groups.values()]}

    @staticmethod
    def aggregate_field(
        records_json: Annotated[str, Field(description=_RECORDS_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        field: Annotated[str, Field(description=_FIELD_PARAMETER_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
        function: Annotated[AggregateFunction, Field(description=_FUNCTION_PARAMETER_DESCRIPTION)],
    ) -> PrebuiltToolOutput:
        """Compute the count, sum, mean, minimum, maximum, median, or distinct count of one field across records, with how many values were used and skipped. Use it for totals and averages over a record set instead of adding numbers by reading them. Count and distinct_count use every present non-null value and return integers, while the numeric functions use JSON numbers only and skip strings, booleans, and other values. With no usable values the result is null, and a sum that is not finite fails naming field."""
        records = PrebuiltToolSupport.records_from_json(PrebuiltToolSupport.parse_json_text(records_json, "records_json"), "records_json")
        # Missing fields and null values take no part in any aggregate.
        values = [record[field] for record in records if record.get(field) is not None]
        keys = [JsonRecordsToolFunctions._group_key(value) for value in values]
        result, used, skipped = JsonRecordsToolFunctions._aggregate(values, keys, function, "field")
        return {"result": result, "values_used": used, "values_skipped": skipped}

    @staticmethod
    def group_and_aggregate_records(
        records_json: Annotated[str, Field(description=_RECORDS_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        group_by_field: Annotated[str, Field(description="The name of the field whose value decides each record's group, matched exactly against top-level keys. Keys compare type-aware, and objects and arrays compare by their compact JSON text. Records that lack the field join the null group. The name must hold 1 to 200 characters.", min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
        value_field: Annotated[str, Field(description="The name of the field to aggregate within each group, matched exactly against top-level keys. Missing fields and null values are left out of every aggregate. The numeric functions use JSON numbers only and skip other values. The name must hold 1 to 200 characters.", min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
        function: Annotated[AggregateFunction, Field(description=_FUNCTION_PARAMETER_DESCRIPTION)],
    ) -> PrebuiltToolOutput:
        """Group records by one field and compute an aggregate of another field within each group, in order of first appearance. Use it for per-category totals, averages, or counts, the way a grouped database query would. Grouping follows group_records_by_field, so missing and null keys share the null group, and each aggregate follows aggregate_field. A group with no usable values gets a null result, and a sum that is not finite fails naming value_field."""
        records = PrebuiltToolSupport.records_from_json(PrebuiltToolSupport.parse_json_text(records_json, "records_json"), "records_json")
        # Collect each group's present non-null values, keeping the
        # first key value seen for the group.
        groups: dict[tuple[JsonType, object], tuple[object, list[object]]] = {}
        for record in records:
            key = record.get(group_by_field)
            values = groups.setdefault(JsonRecordsToolFunctions._group_key(key), (key, []))[1]
            if record.get(value_field) is not None:
                values.append(record[value_field])

        # Aggregate each group in order of first appearance.
        results: list[dict[str, object]] = []
        for key, values in groups.values():
            keys = [JsonRecordsToolFunctions._group_key(value) for value in values]
            result, used, _ = JsonRecordsToolFunctions._aggregate(values, keys, function, "value_field")
            results.append({"key": key, "result": result, "values_used": used})
        return {"groups": results}

    @staticmethod
    def sort_records(
        records_json: Annotated[str, Field(description=_RECORDS_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        field: Annotated[str, Field(description=_FIELD_PARAMETER_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
        descending: Annotated[bool, Field(description="Whether to sort from the highest value to the lowest. When true, the type order is reversed as well, so objects and arrays come first and numbers last. Records whose field is missing or null stay at the end either way. The default is false.")] = False,
    ) -> PrebuiltToolOutput:
        """Sort records by one field with a fixed order across mixed types, keeping records with equal values in their original order. Use it to rank or order a record set when the field may hold numbers, text, or other JSON values. Numbers come first, then strings by code point, then booleans with false before true, then objects and arrays by compact JSON text, and missing or null fields always come last. Descending order reverses everything except the missing and null records, and invalid records fail naming records_json."""
        records = PrebuiltToolSupport.records_from_json(PrebuiltToolSupport.parse_json_text(records_json, "records_json"), "records_json")
        # Sort the records that have a value with a stable sort, then
        # put the missing and null ones after them in input order.
        present = [record for record in records if record.get(field) is not None]
        ordered = sorted(present, key=lambda record: JsonRecordsToolFunctions._sort_key(record[field]), reverse=descending)
        return {"records": ordered + [record for record in records if record.get(field) is None]}

    @staticmethod
    def count_field_values(
        records_json: Annotated[str, Field(description=_RECORDS_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        field: Annotated[str, Field(description=_FIELD_PARAMETER_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
        top: Annotated[int, Field(description="How many of the most frequent values to list. Values are ranked by count, highest first, and ties keep the order in which the values first appear. The total and distinct counts in the result still cover every value. The value must be between 1 and 1,000.", ge=1, le=PREBUILT_MAX_TOP_ITEMS)] = 100,
    ) -> PrebuiltToolOutput:
        """Count how often each value of one field occurs across records, listing the most frequent values first. Use it to find the distribution of a category field or to spot duplicate values. Values compare type-aware, a missing field counts as null, ties keep the order of first appearance, and the totals cover every value even when the list is shortened. Only the top entries are listed, and invalid records fail naming records_json."""
        records = PrebuiltToolSupport.records_from_json(PrebuiltToolSupport.parse_json_text(records_json, "records_json"), "records_json")
        # Tally each type-aware value, keeping the first spelling seen.
        tallies: dict[tuple[JsonType, object], tuple[object, int]] = {}
        for record in records:
            key = JsonRecordsToolFunctions._group_key(record.get(field))
            first, count = tallies.get(key, (record.get(field), 0))
            tallies[key] = (first, count + 1)

        # A stable sort by count keeps ties in first-appearance order.
        ranked = sorted(tallies.values(), key=lambda entry: -entry[1])
        counts = [{"value": first, "count": count} for first, count in ranked[:top]]
        return {"total": len(records), "distinct": len(tallies), "counts": counts}

    @staticmethod
    def join_records(
        left_json: Annotated[str, Field(description="The left records, given as the text of a JSON array of objects. Output keeps their order, and every joined record starts with all of the left record's keys. A left join keeps each left record that has no match unchanged. The array may hold at most 10,000 records in at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)],
        right_json: Annotated[str, Field(description="The right records, given as the text of a JSON array of objects. Matches for one left record follow the right list's order. Every key of a matching right record is added, the right join field included, and a key the left record already has is renamed with a right_ prefix. The array may hold at most 10,000 records in at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)],
        left_field: Annotated[str, Field(description="The name of the join field in the left records, matched exactly against top-level keys. A left record whose field is missing or null never matches. Keys compare type-aware, so a number never matches a string. The name must hold 1 to 200 characters.", min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
        right_field: Annotated[str, Field(description="The name of the join field in the right records, matched exactly against top-level keys. A right record whose field is missing or null never matches. The field stays in the joined record under its own name unless the left record already has that key. The name must hold 1 to 200 characters.", min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
        kind: Annotated[JoinKind, Field(description="Whether to keep only matched records or every left record. An inner join returns one merged record for each matching pair. A left join also returns each unmatched left record unchanged. The default is inner.")] = JoinKind.INNER,
    ) -> PrebuiltToolOutput:
        """Join two record lists on matching field values, as an inner join or a left join, returning merged records in left order and then right order. Use it to combine related data, such as attaching the details in one list to the matching entries of another. Keys compare type-aware, missing and null keys never match, and a right key that the left record already has is stored as right_ followed by the key name. At most 10,000 joined records are returned while count covers every one, and records that are not JSON arrays of objects fail naming their parameter."""
        left = PrebuiltToolSupport.records_from_json(PrebuiltToolSupport.parse_json_text(left_json, "left_json"), "left_json")
        right = PrebuiltToolSupport.records_from_json(PrebuiltToolSupport.parse_json_text(right_json, "right_json"), "right_json")

        # Index the right records by type-aware key, in their order;
        # missing and null keys never match.
        index: dict[tuple[JsonType, object], list[dict[str, object]]] = {}
        for record in right:
            if record.get(right_field) is not None:
                index.setdefault(JsonRecordsToolFunctions._group_key(record[right_field]), []).append(record)

        # Find each left record's matches and count the joined records
        # from them, so a huge join is counted without being built.
        matches = [index.get(JsonRecordsToolFunctions._group_key(record[left_field]), []) if record.get(left_field) is not None else [] for record in left]
        count = sum(len(found) if found else int(kind is JoinKind.LEFT) for found in matches)

        # Merge records lazily until the record cap or the character
        # budget stops the list.
        records, truncated = PrebuiltToolSupport.cap_items(JsonRecordsToolFunctions._joined_records(left, matches, kind), PREBUILT_MAX_RECORDS)
        return {"records": records, "count": count, "truncated": truncated}

    @staticmethod
    def records_to_csv(
        records_json: Annotated[str, Field(description=_RECORDS_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        columns: Annotated[tuple[Annotated[str, Field(min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)], ...], Field(description="The columns to write, in order, each naming a top-level field. An empty list writes every field that appears in any record, in order of first appearance. A record that lacks a column gets an empty cell. At most 500 columns are allowed, and each name holds 1 to 200 characters.", max_length=PREBUILT_MAX_TABLE_COLUMNS)] = (),
        delimiter: Annotated[CsvDelimiter, Field(description="The character that separates cells in the output: comma, semicolon, tab, or pipe. Cells holding the delimiter, a quote, or a line feed are quoted. Lines end with a single line feed. The default is comma.")] = CsvDelimiter.COMMA,
    ) -> PrebuiltToolOutput:
        """Write a list of records as CSV text with a header row, using the chosen columns or every field in order of first appearance. Use it to turn JSON records into a spreadsheet-ready table or a file another program reads as CSV. Strings are written as they are, numbers as JSON, booleans as true or false, missing and null values as empty cells, and objects and arrays as compact JSON, with quoting only where needed. More than 500 columns, or CSV text longer than one million characters, fails naming records_json."""
        records = PrebuiltToolSupport.records_from_json(PrebuiltToolSupport.parse_json_text(records_json, "records_json"), "records_json")

        # Use the chosen columns, or every key in order of first
        # appearance, refusing more columns than the table cap.
        names: dict[str, None] = dict.fromkeys(columns)
        if not columns:
            for record in records:
                names.update(dict.fromkeys(record))
                if len(names) > PREBUILT_MAX_TABLE_COLUMNS:
                    problem = f"the records have more than {PREBUILT_MAX_TABLE_COLUMNS} distinct keys"
                    raise PrebuiltToolSupport.argument_error("records_json", problem, "records with fewer distinct keys, or an explicit columns list")

        # Write the header and then one row per record, counting the
        # characters written so far.
        buffer = io.StringIO()
        write_row = PrebuiltToolSupport.csv_row_writer(buffer, delimiter)
        written = write_row(list(names))
        for record in records:
            written += write_row([JsonRecordsToolFunctions._csv_cell(record.get(name)) for name in names])
            # @intent prebuilt-output-text-cap
            # Short records under many columns can turn into far more
            # text than the input, so writing stops as soon as the CSV
            # passes the output cap.
            if written > PREBUILT_MAX_TEXT_CHARS:
                problem = f"the CSV would be longer than {PREBUILT_MAX_TEXT_CHARS} characters"
                raise PrebuiltToolSupport.argument_error("records_json", problem, "fewer records or columns, so the CSV fits the cap")
        return {"csv": buffer.getvalue(), "rows": len(records), "columns": list(names)}

    @staticmethod
    def _field_matches(field_value: object, comparison: FilterOperator, value: str, number: int | float | None) -> bool:
        """Apply one filter comparison to a field value, reading the value text as the field's type."""
        # Emptiness ignores the value text; otherwise a missing or null
        # field never matches, and a boolean needs true or false.
        empty = field_value is None or (isinstance(field_value, (str, list, dict)) and len(field_value) == 0)
        if comparison in {FilterOperator.IS_EMPTY, FilterOperator.IS_NOT_EMPTY}:
            return empty is (comparison is FilterOperator.IS_EMPTY)
        if field_value is None or (isinstance(field_value, bool) and value not in _BOOLEAN_TEXTS):
            return False
        # Arrays test membership, and numbers compare as numbers except
        # under the text operators.
        if isinstance(field_value, list) and comparison is FilterOperator.CONTAINS:
            return value in field_value
        if _JSON_TYPES[type(field_value)] is JsonType.NUMBER:
            if number is None:
                return False
            if comparison not in _TEXT_OPERATORS:
                return bool(_COMPARISONS[comparison](field_value, number))
        # Everything else compares the field's text with the value.
        text = field_value if isinstance(field_value, str) else json.dumps(field_value, separators=_COMPACT_SEPARATORS, ensure_ascii=False)
        return bool(_COMPARISONS[comparison](text, value))

    @staticmethod
    def _group_key(value: object) -> tuple[JsonType, object]:
        """Build a hashable type-aware key: the JSON type with the value, or with the compact JSON text of an object or array."""
        kind = _JSON_TYPES[type(value)]
        if kind in {JsonType.OBJECT, JsonType.ARRAY}:
            return kind, json.dumps(value, separators=_COMPACT_SEPARATORS, ensure_ascii=False)
        return kind, value

    @staticmethod
    def _aggregate(values: list[object], keys: list[tuple[JsonType, object]], function: AggregateFunction, parameter: str) -> tuple[int | float | None, int, int]:
        """Aggregate present non-null values and return the result, how many values were used, and how many were skipped."""
        if function is AggregateFunction.COUNT:
            return len(values), len(values), 0
        if function is AggregateFunction.DISTINCT_COUNT:
            return len(set(keys)), len(values), 0
        # The numeric functions use JSON numbers only, never booleans.
        numbers = [value for value in values if _JSON_TYPES[type(value)] is JsonType.NUMBER and isinstance(value, (int, float))]
        if not numbers:
            return None, 0, len(values)
        expected = "numbers whose aggregate is a finite floating-point number"
        try:
            result = _NUMERIC_AGGREGATES[function]([float(number) for number in numbers])
        except OverflowError as exc:
            raise PrebuiltToolSupport.argument_error(parameter, "the values overflow the floating-point range", expected) from exc
        return PrebuiltToolSupport.float_result(result, parameter), len(numbers), len(values) - len(numbers)

    @staticmethod
    def _sort_key(value: object) -> tuple[int, object]:
        """Order mixed JSON values: numbers, strings, booleans, then objects and arrays by compact JSON text."""
        kind = _JSON_TYPES[type(value)]
        if kind in {JsonType.OBJECT, JsonType.ARRAY}:
            return _SORT_RANKS[kind], json.dumps(value, separators=_COMPACT_SEPARATORS, ensure_ascii=False)
        return _SORT_RANKS[kind], value

    @staticmethod
    def _joined_records(left: list[dict[str, object]], matches: list[list[dict[str, object]]], kind: JoinKind) -> Iterator[dict[str, object]]:
        """Yield joined records in left order, then right order, renaming right keys the left record already has."""
        for record, found in zip(left, matches, strict=True):
            if not found and kind is JoinKind.LEFT:
                yield record
            for match in found:
                joined = dict(record)
                joined.update(("right_" + key if key in record else key, value) for key, value in match.items())
                yield joined

    @staticmethod
    def _csv_cell(value: object) -> str:
        """Write one field as a CSV cell: strings raw, missing and null empty, and anything else as compact JSON."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return json.dumps(value, separators=_COMPACT_SEPARATORS, ensure_ascii=False)

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.filter_records,
            cls.pluck_field,
            cls.group_records_by_field,
            cls.aggregate_field,
            cls.group_and_aggregate_records,
            cls.sort_records,
            cls.count_field_values,
            cls.join_records,
            cls.records_to_csv,
        )


__all__ = ["JsonRecordsToolFunctions"]
