"""FILE: vidbyte/tools/builtins/prebuilt/csv_tables.py

PURPOSE: Defines CsvTablesToolFunctions, the nine prebuilt tools that work on CSV text: converting it to records, detecting its dialect, profiling its columns, filtering, sorting, aggregating, grouping, and joining its rows, and rendering it as a Markdown table.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the CSV_TABLES category is chosen. Builds on PrebuiltToolSupport in _support.py for reading CSV tables, the numeric text rule, the item cap, and the argument error.
ARCHITECTURE NOTE: Every tool except detect_csv_dialect reads its table through PrebuiltToolSupport.parse_csv_table, which sniffs only the first PREBUILT_MAX_SNIFF_CHARS characters, pads short rows, and checks the header, so the tools agree on what a valid table is. Output CSV is written by one private helper with QUOTE_MINIMAL and line feeds, cells compare as numbers only when both sides are numeric, sums and means run in exact fractions, and the two INV-20 tools count their output while building it.
FUNCTION INVENTORY: csv_to_records, detect_csv_dialect, profile_csv_columns, csv_filter_rows, csv_sort_rows, csv_aggregate_column, csv_group_by, csv_join_tables, and csv_to_markdown_table are the tools; _column_index finds a column or lists the available ones; _write_csv writes output CSV; _typed_cell converts one cell for infer_types; _read_rows and _header_vote serve dialect detection; _column_type and _column_profile describe one column; _cell_matches applies a filter comparison; _sort_key keys rows for every sort mode but numeric; _aggregate summarizes cells; _alignment_markers and _table_line build Markdown lines; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new CSV tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.19, and its entry in tool_functions, and reads its table through parse_csv_table. A new comparison or summary extends the operator tables or _aggregate together with its enum member.
WHAT NOT TO DO IN THIS FILE: 1. Do not call csv.field_size_limit or change any other csv module setting; a cell over the default limit is reported as an error on the CSV parameter. 2. Do not sniff more than PREBUILT_MAX_SNIFF_CHARS characters, because csv.Sniffer slows down sharply on long input. 3. Do not echo a requested column name or long header text in an error; list at most a few shortened column names.
KNOWN EDGE CASES: A cell holding only whitespace counts as empty, yet keeps its text in output CSV. Natural order compares digit runs by their length without leading zeros and then digit by digit, so no integer conversion runs on long digit strings. Single-column output writes an empty cell as two quote characters, so the row is not read back as a blank line.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.19, section 9.2 items 12, 13, and 15); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_json_csv.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import csv
import io
import json
import re
import statistics
from collections.abc import Callable, Iterable, Mapping
from fractions import Fraction
from itertools import chain
from operator import contains, eq, ge, gt, le, lt, ne
from types import MappingProxyType
from typing import Annotated, Any

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_CSV_DELIMITER_CHARACTERS,
    PREBUILT_MAX_NAME_CHARS,
    PREBUILT_MAX_RECORDS,
    PREBUILT_MAX_REPORTED_NAMES,
    PREBUILT_MAX_SHORT_TEXT_CHARS,
    PREBUILT_MAX_SNIFF_CHARS,
    PREBUILT_MAX_TEXT_CHARS,
    PREBUILT_PROFILE_EXAMPLES,
)
from vidbyte.lib.enums.prebuilt_tools import (
    AggregateFunction,
    ColumnType,
    CsvDelimiter,
    FilterOperator,
    JoinKind,
    SortMode,
    TableAlignment,
)
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_SNIFF_DELIMITERS = ",;\t|"
_DEFAULT_QUOTE = '"'
_HEADER_VOTE_ROWS = 21
_NUMBER_KIND = "number"
_BOOLEAN_WORDS = MappingProxyType({"true": True, "false": False})
_ISO_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_CELL_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_NUMERIC_TYPES = frozenset({ColumnType.INTEGER, ColumnType.NUMBER})
_EMPTINESS_TESTS = MappingProxyType({FilterOperator.IS_EMPTY: True, FilterOperator.IS_NOT_EMPTY: False})
_TEXT_TESTS: Mapping[FilterOperator, Callable[[str, str], bool]] = MappingProxyType(
    {FilterOperator.CONTAINS: contains, FilterOperator.STARTS_WITH: str.startswith, FilterOperator.ENDS_WITH: str.endswith}
)
_ORDER_TESTS: Mapping[FilterOperator, Callable[[Any, Any], Any]] = MappingProxyType(
    {
        FilterOperator.EQUALS: eq,
        FilterOperator.NOT_EQUALS: ne,
        FilterOperator.GREATER_THAN: gt,
        FilterOperator.GREATER_OR_EQUAL: ge,
        FilterOperator.LESS_THAN: lt,
        FilterOperator.LESS_OR_EQUAL: le,
    }
)
_NUMERIC_SUMMARIES: Mapping[AggregateFunction, Callable[[list[Fraction]], Fraction | int]] = MappingProxyType(
    {
        AggregateFunction.SUM: sum,
        AggregateFunction.MEAN: statistics.mean,
        AggregateFunction.MIN: min,
        AggregateFunction.MAX: max,
        AggregateFunction.MEDIAN: statistics.median,
    }
)
_ALIGNMENT_MARKERS = MappingProxyType({TableAlignment.LEFT: ":---", TableAlignment.CENTER: ":---:", TableAlignment.RIGHT: "---:"})

_CSV_TEXT_DESCRIPTION = "The CSV text to read, whose first row is the header that names every column. Header names must be distinct and not blank, and a row may not hold more cells than the header, while a shorter row is padded with empty cells. Quoted cells may hold delimiters, quotes, and line breaks. The text may hold at most one million characters, 10,000 data rows, and 500 columns."
_DELIMITER_DESCRIPTION = "The character that separates cells: comma, semicolon, tab, or pipe. When it is null, the delimiter is detected from the first 10,000 characters of the text. Detection falls back to comma when no delimiter stands out. Output CSV keeps the delimiter that was used."
_COLUMN_DESCRIPTION = "The exact header name of the column to use. Names are matched case-sensitively, with their spaces as written. A name that is not in the header fails with an error that lists the available columns. It must hold between 1 and 200 characters."
_FUNCTION_DESCRIPTION = "The summary to compute over the column's cells. Count and distinct count use every non-empty cell and return integers, and distinct cells are compared as written. Sum, mean, minimum, maximum, and median use the numeric cells only and return numbers. A summary with no usable cell returns null."


class CsvTablesToolFunctions:
    """The csv_tables category: reading, profiling, filtering, sorting, aggregating, joining, and rendering CSV tables."""

    @staticmethod
    def csv_to_records(
        csv_text: Annotated[str, Field(description=_CSV_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        delimiter: Annotated[CsvDelimiter | None, Field(description=_DELIMITER_DESCRIPTION)] = None,
        infer_types: Annotated[bool, Field(description="Whether to turn cell text into JSON values. When true, an empty or whitespace-only cell becomes null, true or false in any case becomes a boolean, and numeric text becomes an integer or a float. Numeric text follows the shared rule, so an integer has no point or exponent and stays below 2 to the power 53. Every other cell, and every cell when this is false, stays its original text.")] = False,
    ) -> PrebuiltToolOutput:
        """Convert CSV text into a list of records, one object per data row keyed by the header names, plus the column names and the row count. Use it to turn a spreadsheet export into structured records that other tools can filter, group, or join. Every value stays the cell's text unless infer_types is true, in which case empty cells become null and booleans and numbers become JSON values. Records whose combined JSON would pass one million characters, a header with blank or repeated names, or a row wider than the header fail with an error naming csv_text."""
        # Read the table, which checks the header and pads short rows.
        header, rows, _ = PrebuiltToolSupport.parse_csv_table(csv_text, delimiter, "csv_text")

        # Build one record per row, converting cells only when asked.
        records: list[dict[str, object]] = []
        size = 0
        for row in rows:
            cells: Iterable[object] = (CsvTablesToolFunctions._typed_cell(cell) for cell in row) if infer_types else row
            record = dict(zip(header, cells, strict=True))
            # @intent prebuilt-csv-records-output-cap
            # Every record repeats the header names, so a wide table of
            # empty cells grows many times over as records; building
            # stops once their compact JSON passes the output cap.
            size += len(json.dumps(record, separators=(",", ":"), ensure_ascii=False))
            if size > PREBUILT_MAX_TEXT_CHARS:
                problem = f"the records would pass {PREBUILT_MAX_TEXT_CHARS} characters of JSON"
                raise PrebuiltToolSupport.argument_error("csv_text", problem, "a table whose records fit in that many characters")
            records.append(record)
        return {"records": records, "columns": header, "rows": len(rows)}

    @staticmethod
    def detect_csv_dialect(csv_text: Annotated[str, Field(description="The CSV text to inspect, given as plain characters. Only its first 10,000 characters are used to detect the delimiter and the quote character. Rows and columns are counted over the whole text with the detected delimiter, and blank lines are skipped. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Detect the delimiter, quote character, and header row of CSV text, and count its columns and data rows. Use it before the other CSV tools when the format of a file is unknown. Detection reads only the first 10,000 characters, chooses among comma, semicolon, tab, and pipe, and falls back to comma without an error. The header guess compares the first row with the type and length pattern of the rows below it, and only text the CSV parser cannot read fails."""
        # Sniff only the start of the text, because the sniffer slows
        # down sharply on long input, and use comma when it gives up.
        try:
            dialect = csv.Sniffer().sniff(csv_text[:PREBUILT_MAX_SNIFF_CHARS], delimiters=_SNIFF_DELIMITERS)
            sniffed, quote = dialect.delimiter, dialect.quotechar or _DEFAULT_QUOTE
        except csv.Error:
            sniffed, quote = ",", _DEFAULT_QUOTE
        chosen = next((member for member, character in PREBUILT_CSV_DELIMITER_CHARACTERS.items() if character == sniffed), CsvDelimiter.COMMA)

        # Read every row with that delimiter, then guess the header from
        # the first rows.
        rows = CsvTablesToolFunctions._read_rows(csv_text, chosen)
        return {
            "delimiter": chosen.value,
            "has_header": CsvTablesToolFunctions._header_vote(rows[:_HEADER_VOTE_ROWS]),
            "quote_character": quote,
            "columns": len(rows[0]) if rows else 0,
            "rows": max(len(rows) - 1, 0),
        }

    @staticmethod
    def profile_csv_columns(
        csv_text: Annotated[str, Field(description=_CSV_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        delimiter: Annotated[CsvDelimiter | None, Field(description=_DELIMITER_DESCRIPTION)] = None,
    ) -> PrebuiltToolOutput:
        """Profile every column of CSV text: its inferred type, how many cells are empty or filled, how many distinct values it holds, its minimum, maximum, and mean, and a few example values. Use it to understand an unfamiliar table before filtering, sorting, or aggregating it. The type is the narrowest of integer, number, boolean, date, and text that fits every non-empty cell, or empty when no cell has a value. Minimum and maximum follow numeric order for numeric columns and code-point order otherwise, the mean is set only for numeric columns, and a malformed table fails with an error naming csv_text."""
        # Read the table, which checks the header and pads short rows.
        header, rows, _ = PrebuiltToolSupport.parse_csv_table(csv_text, delimiter, "csv_text")

        # Profile each column from its non-empty cells and the numeric
        # value of each one.
        columns = []
        for index, name in enumerate(header):
            filled = [row[index] for row in rows if row[index].strip()]
            numbers = [PrebuiltToolSupport.parse_numeric_text(cell) for cell in filled]
            column_type = CsvTablesToolFunctions._column_type(filled, numbers)
            columns.append(CsvTablesToolFunctions._column_profile(name, filled, numbers, column_type, len(rows)))
        return {"rows": len(rows), "columns": columns}

    @staticmethod
    def csv_filter_rows(
        csv_text: Annotated[str, Field(description=_CSV_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        column: Annotated[str, Field(description=_COLUMN_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
        operator: Annotated[FilterOperator, Field(description="The comparison applied to each cell of the column. Equality and ordering compare numerically when both sides are numeric and by code point otherwise. Contains, starts with, and ends with always compare case-sensitive text. Is empty and is not empty ignore the value and test whether the cell holds anything besides whitespace.")],
        value: Annotated[str, Field(description="The value each cell is compared with, given as text. It is read as a number when it is numeric under the shared numeric text rule and the cell is numeric too. The emptiness tests ignore it. It defaults to empty text and may hold at most 10,000 characters.", max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)] = "",
        delimiter: Annotated[CsvDelimiter | None, Field(description=_DELIMITER_DESCRIPTION)] = None,
    ) -> PrebuiltToolOutput:
        """Keep the rows of CSV text whose cell in one column satisfies a comparison, and return them as CSV with the header, plus the number of matching rows. Use it to select rows of a table by value, by text, or by emptiness. Cells are compared as numbers when both the cell and the value are numeric and as case-sensitive text otherwise, and a cell holding only whitespace counts as empty. The header row is always kept, and an unknown column fails with an error that lists the available columns."""
        # Read the table and find the column to test.
        header, rows, chosen = PrebuiltToolSupport.parse_csv_table(csv_text, delimiter, "csv_text")
        index = CsvTablesToolFunctions._column_index(header, column, "column")

        # Keep the rows whose cell passes, reading the value as a number
        # once for every comparison.
        value_number = PrebuiltToolSupport.parse_numeric_text(value)
        kept = [row for row in rows if CsvTablesToolFunctions._cell_matches(row[index], operator, value, value_number)]
        return {"csv": CsvTablesToolFunctions._write_csv(header, kept, chosen), "matched": len(kept)}

    @staticmethod
    def csv_sort_rows(
        csv_text: Annotated[str, Field(description=_CSV_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        column: Annotated[str, Field(description=_COLUMN_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
        mode: Annotated[SortMode, Field(description="How cells are compared when sorting. Text compares code points, case insensitive compares case-folded text with code-point order breaking ties, and length compares lengths and then code points. Natural compares digit runs by numeric value and other runs without regard to case, and numeric sorts the numeric cells by value and puts the other rows after them. The default is natural.")] = SortMode.NATURAL,
        descending: Annotated[bool, Field(description="Whether to sort from the largest key to the smallest. Rows with equal keys keep their input order in both directions. In numeric mode only the numeric cells are reversed, and the other rows still follow in input order. The default is false.")] = False,
        delimiter: Annotated[CsvDelimiter | None, Field(description=_DELIMITER_DESCRIPTION)] = None,
    ) -> PrebuiltToolOutput:
        """Sort the data rows of CSV text by one column and return the sorted CSV with the header first, plus the number of data rows. Use it to order a table alphabetically, by number, by length, or in natural order where embedded numbers sort by value. The modes match the text line sorter, every sort is stable, and descending order reverses the comparison while rows with equal keys keep their input order. In numeric mode the numeric cells sort by value and the other rows follow in input order, and an unknown column fails with an error naming column."""
        # Read the table and find the column to sort by.
        header, rows, chosen = PrebuiltToolSupport.parse_csv_table(csv_text, delimiter, "csv_text")
        index = CsvTablesToolFunctions._column_index(header, column, "column")

        # Numeric mode sorts the numeric cells and appends the rest in
        # input order; every other mode sorts all rows by one key.
        if mode is SortMode.NUMERIC:
            ordered = PrebuiltToolSupport.numeric_order([(PrebuiltToolSupport.parse_numeric_text(row[index]), row) for row in rows], descending)
        else:
            ordered = sorted(rows, key=lambda row: CsvTablesToolFunctions._sort_key(row[index], mode), reverse=descending)
        return {"csv": CsvTablesToolFunctions._write_csv(header, ordered, chosen), "rows": len(rows)}

    @staticmethod
    def csv_aggregate_column(
        csv_text: Annotated[str, Field(description=_CSV_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        column: Annotated[str, Field(description=_COLUMN_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
        function: Annotated[AggregateFunction, Field(description=_FUNCTION_DESCRIPTION)],
        delimiter: Annotated[CsvDelimiter | None, Field(description=_DELIMITER_DESCRIPTION)] = None,
    ) -> PrebuiltToolOutput:
        """Compute one summary over a CSV column: the count of non-empty cells, the sum, mean, minimum, maximum, or median of its numeric cells, or the count of distinct non-empty cells. Use it to answer totals and averages over a table exactly instead of estimating them. Numeric functions use only the cells that are numeric under the shared rule and report how many non-empty cells they skipped, and empty cells are never counted. No usable cell gives a null result, and an unknown column or a sum outside the floating-point range fails with an error naming column."""
        # Read the table, find the column, and summarize its cells.
        header, rows, _ = PrebuiltToolSupport.parse_csv_table(csv_text, delimiter, "csv_text")
        index = CsvTablesToolFunctions._column_index(header, column, "column")
        result, used, skipped = CsvTablesToolFunctions._aggregate([row[index] for row in rows], function, "column")
        return {"result": result, "values_used": used, "values_skipped": skipped}

    @staticmethod
    def csv_group_by(
        csv_text: Annotated[str, Field(description=_CSV_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        group_column: Annotated[str, Field(description="The exact header name of the column whose cell text defines the groups. Rows whose cells hold the same text, with the same spacing and case, fall in the same group. A name that is not in the header fails with an error that lists the available columns. It must hold between 1 and 200 characters.", min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
        value_column: Annotated[str, Field(description="The exact header name of the column that the function summarizes within each group. Numeric functions use only its numeric cells, while count and distinct count use every non-empty cell. A name that is not in the header fails with an error that lists the available columns. It must hold between 1 and 200 characters.", min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
        function: Annotated[AggregateFunction, Field(description=_FUNCTION_DESCRIPTION)],
        delimiter: Annotated[CsvDelimiter | None, Field(description=_DELIMITER_DESCRIPTION)] = None,
    ) -> PrebuiltToolOutput:
        """Group the rows of CSV text by the text of one column and compute a summary of another column within each group. Use it for per-category totals, averages, counts, or extremes in a table. Groups appear in the order their key first appears, keys are the exact cell text, and empty cells form a group of their own. Each group reports its result and how many cells the function used, and an unknown column fails with an error naming that column parameter."""
        # Read the table and find both columns.
        header, rows, _ = PrebuiltToolSupport.parse_csv_table(csv_text, delimiter, "csv_text")
        group_index = CsvTablesToolFunctions._column_index(header, group_column, "group_column")
        value_index = CsvTablesToolFunctions._column_index(header, value_column, "value_column")

        # Collect each group's value cells in order of first appearance.
        groups: dict[str, list[str]] = {}
        for row in rows:
            groups.setdefault(row[group_index], []).append(row[value_index])

        # Summarize every group with the same rules as one column.
        summaries = []
        for key, cells in groups.items():
            result, used, _ = CsvTablesToolFunctions._aggregate(cells, function, "value_column")
            summaries.append({"key": key, "result": result, "values_used": used})
        return {"groups": summaries}

    @staticmethod
    def csv_join_tables(
        left_csv: Annotated[str, Field(description="The left CSV table, whose first row is the header. Every left row appears in input order, once for each matching right row. Header names must be distinct and not blank, and short rows are padded with empty cells. The text may hold at most one million characters, 10,000 data rows, and 500 columns.", max_length=PREBUILT_MAX_TEXT_CHARS)],
        right_csv: Annotated[str, Field(description="The right CSV table, whose first row is the header. For each left row, its matching rows are joined in input order. Header names must be distinct and not blank, and short rows are padded with empty cells. The text may hold at most one million characters, 10,000 data rows, and 500 columns.", max_length=PREBUILT_MAX_TEXT_CHARS)],
        left_column: Annotated[str, Field(description="The exact header name of the key column in the left table. Keys are compared as exact text, so differing spacing, case, or leading zeros do not match. A name that is not in the left header fails with an error that lists its columns. It must hold between 1 and 200 characters.", min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
        right_column: Annotated[str, Field(description="The exact header name of the key column in the right table. This column is left out of the joined output, because it repeats the left key. A name that is not in the right header fails with an error that lists its columns. It must hold between 1 and 200 characters.", min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
        kind: Annotated[JoinKind, Field(description="Whether to keep only matched rows or every left row. An inner join keeps only the left rows that have at least one matching right row. A left join also keeps each unmatched left row once, with empty cells for the right columns. The default is inner.")] = JoinKind.INNER,
        delimiter: Annotated[CsvDelimiter | None, Field(description="The character that separates cells in both tables: comma, semicolon, tab, or pipe. When it is null, each table's delimiter is detected separately from its first 10,000 characters, with comma when detection fails. The output uses the left table's delimiter. A table read with the wrong delimiter usually fails on its header or its rows.")] = None,
    ) -> PrebuiltToolOutput:
        """Join two CSV tables on equal cell text in one column of each, as an inner join or a left join, and return the joined table as CSV. Use it to combine two related tables that share a key column. The right join column is dropped, a right column whose name the left table already uses is renamed with a right_ prefix, and a left join pads unmatched rows with empty cells. At most 10,000 joined rows are returned while rows counts every joined row, and an unknown column fails with an error naming left_column or right_column."""
        # Read both tables, each with its own detected delimiter, and
        # find the key columns.
        left_header, left_rows, left_delimiter = PrebuiltToolSupport.parse_csv_table(left_csv, delimiter, "left_csv")
        right_header, right_rows, _ = PrebuiltToolSupport.parse_csv_table(right_csv, delimiter, "right_csv")
        left_index = CsvTablesToolFunctions._column_index(left_header, left_column, "left_column")
        right_index = CsvTablesToolFunctions._column_index(right_header, right_column, "right_column")

        # Index the right rows by key text, without the key column, and
        # rename right columns whose names the left table already uses.
        matches: dict[str, list[list[str]]] = {}
        for row in right_rows:
            matches.setdefault(row[right_index], []).append(row[:right_index] + row[right_index + 1 :])
        left_names = set(left_header)
        kept_names = right_header[:right_index] + right_header[right_index + 1 :]
        header = left_header + [f"right_{name}" if name in left_names else name for name in kept_names]

        # Count every joined row, then keep rows up to the row cap and
        # the character budget.
        padding: list[list[str]] = [[""] * len(kept_names)] if kind is JoinKind.LEFT else []
        total = sum(len(matches.get(row[left_index]) or padding) for row in left_rows)
        joined = (left + right for left in left_rows for right in matches.get(left[left_index]) or padding)
        kept, truncated = PrebuiltToolSupport.cap_items(joined, PREBUILT_MAX_RECORDS)
        return {"csv": CsvTablesToolFunctions._write_csv(header, kept, left_delimiter), "rows": total, "truncated": truncated}

    @staticmethod
    def csv_to_markdown_table(
        csv_text: Annotated[str, Field(description=_CSV_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        delimiter: Annotated[CsvDelimiter | None, Field(description=_DELIMITER_DESCRIPTION)] = None,
        alignment: Annotated[TableAlignment, Field(description="How the columns are aligned in the separator line. Left, center, and right apply to every column. Auto right-aligns each column whose non-empty cells are all numeric and left-aligns the rest. The default is left.")] = TableAlignment.LEFT,
    ) -> PrebuiltToolOutput:
        """Render CSV text as a Markdown table with a header line, an alignment line, and one line per data row. Use it to show a table to a reader in a chat message or a Markdown document. Pipe characters in cells are escaped with a backslash, line breaks inside cells become HTML line breaks, and cells are separated by a pipe with one space on each side. A table that would pass one million characters fails with an error naming csv_text, and so does a malformed table."""
        # Read the table and choose each column's separator cell.
        header, rows, _ = PrebuiltToolSupport.parse_csv_table(csv_text, delimiter, "csv_text")
        markers = CsvTablesToolFunctions._alignment_markers(header, rows, alignment)

        # Build the lines one at a time, refusing a table that would
        # pass the output cap.
        lines: list[str] = []
        size = -1
        separator = "| " + " | ".join(markers) + " |"
        for line in chain([CsvTablesToolFunctions._table_line(header), separator], (CsvTablesToolFunctions._table_line(row) for row in rows)):
            # @intent prebuilt-markdown-table-output-cap
            # Padding short rows and turning line breaks into tags can
            # make the table several times longer than its CSV, so the
            # running length is checked before each line is kept.
            size += len(line) + 1
            if size > PREBUILT_MAX_TEXT_CHARS:
                problem = f"the Markdown table would pass {PREBUILT_MAX_TEXT_CHARS} characters"
                raise PrebuiltToolSupport.argument_error("csv_text", problem, "a table whose Markdown fits in that many characters")
            lines.append(line)
        return {"markdown": "\n".join(lines), "rows": len(rows), "columns": len(header)}

    @staticmethod
    def _column_index(header: list[str], name: str, parameter_name: str) -> int:
        """Return the position of a header name, or fail naming the parameter and listing a few shortened column names."""
        if name in header:
            return header.index(name)
        listed = ", ".join(f'"{column}"' for column in PrebuiltToolSupport.shortened_names(header))
        more = f", and {len(header) - PREBUILT_MAX_REPORTED_NAMES} more" if len(header) > PREBUILT_MAX_REPORTED_NAMES else ""
        raise PrebuiltToolSupport.argument_error(parameter_name, "the table has no column with that name", f"one of the columns {listed}{more}")

    @staticmethod
    def _write_csv(header: list[str], rows: Iterable[list[str]], delimiter: CsvDelimiter) -> str:
        """Write a header and rows as CSV with minimal quoting and line-feed line endings."""
        buffer = io.StringIO()
        write_row = PrebuiltToolSupport.csv_row_writer(buffer, delimiter)
        for row in chain([header], rows):
            write_row(row)
        return buffer.getvalue()

    @staticmethod
    def _typed_cell(cell: str) -> object:
        """Turn one cell into null, a boolean, a number, or its own text, in that order."""
        stripped = cell.strip()
        if not stripped:
            return None
        if stripped.lower() in _BOOLEAN_WORDS:
            return _BOOLEAN_WORDS[stripped.lower()]
        number = PrebuiltToolSupport.parse_numeric_text(cell)
        return cell if number is None else number

    @staticmethod
    def _read_rows(text: str, delimiter: CsvDelimiter) -> list[list[str]]:
        """Read every non-blank row of CSV text with one delimiter, reporting a parse failure by line."""
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=PREBUILT_CSV_DELIMITER_CHARACTERS[delimiter])
        try:
            return [row for row in reader if row]
        except csv.Error as exc:
            problem = f"the CSV could not be read at line {reader.line_num}"
            raise PrebuiltToolSupport.argument_error("csv_text", problem, "CSV text whose cells each hold at most 131,072 characters") from exc

    @staticmethod
    def _header_vote(rows: list[list[str]]) -> bool:
        """Guess whether the first row is a header by comparing it with the type and length pattern of the rows below it."""
        if not rows:
            return False
        # Note each column's kinds below the first row: numeric, or the
        # length of the text.
        header = rows[0]
        kinds: list[set[str | int]] = [set() for _ in header]
        for row in rows[1:]:
            if len(row) != len(header):
                continue
            for index, cell in enumerate(row):
                kinds[index].add(_NUMBER_KIND if PrebuiltToolSupport.parse_numeric_text(cell) is not None else len(cell))
        # A column with one consistent kind votes for a header when the
        # first row's cell has another kind, and against it otherwise.
        votes = 0
        for name, column_kinds in zip(header, kinds, strict=True):
            name_kind = _NUMBER_KIND if PrebuiltToolSupport.parse_numeric_text(name) is not None else len(name)
            if len(column_kinds) == 1:
                votes += -1 if name_kind in column_kinds else 1
        return votes > 0

    @staticmethod
    def _column_type(filled: list[str], numbers: list[int | float | None]) -> ColumnType:
        """Pick the narrowest column type that fits every non-empty cell, or empty when there is none."""
        if not filled:
            return ColumnType.EMPTY
        if all(isinstance(number, int) for number in numbers):
            return ColumnType.INTEGER
        if all(number is not None for number in numbers):
            return ColumnType.NUMBER
        stripped = [cell.strip() for cell in filled]
        if all(cell.lower() in _BOOLEAN_WORDS for cell in stripped):
            return ColumnType.BOOLEAN
        if all(_ISO_DAY.fullmatch(cell) and PrebuiltToolSupport.parse_date_text(cell, False) for cell in stripped):
            return ColumnType.DATE
        return ColumnType.TEXT

    @staticmethod
    def _column_profile(name: str, filled: list[str], numbers: list[int | float | None], column_type: ColumnType, row_count: int) -> dict[str, object]:
        """Describe one column: counts, distinct values, extremes by value or code point, the mean, and examples."""
        distinct = list(dict.fromkeys(filled))
        low, high = min(filled, default=None), max(filled, default=None)
        mean: float | None = None
        if column_type in _NUMERIC_TYPES:
            # Extremes compare values, and min and max keep the first
            # cell of equal value; the mean is exact until rounded.
            pairs = [(number, cell) for number, cell in zip(numbers, filled, strict=True) if number is not None]
            low = min(pairs, key=lambda pair: pair[0])[1]
            high = max(pairs, key=lambda pair: pair[0])[1]
            mean = float(sum((Fraction(number) for number, _ in pairs), Fraction(0)) / len(pairs))
        return {
            "name": name,
            "inferred_type": column_type.value,
            "non_empty": len(filled),
            "empty": row_count - len(filled),
            "distinct": len(distinct),
            "min": low,
            "max": high,
            "mean": mean,
            "examples": distinct[:PREBUILT_PROFILE_EXAMPLES],
        }

    @staticmethod
    def _cell_matches(cell: str, operator: FilterOperator, value: str, value_number: int | float | None) -> bool:
        """Apply one filter comparison to a cell, numerically when both sides are numeric and as text otherwise."""
        if operator in _EMPTINESS_TESTS:
            return _EMPTINESS_TESTS[operator] == (not cell.strip())
        if operator in _TEXT_TESTS:
            return _TEXT_TESTS[operator](cell, value)
        cell_number = PrebuiltToolSupport.parse_numeric_text(cell)
        if cell_number is not None and value_number is not None:
            return bool(_ORDER_TESTS[operator](cell_number, value_number))
        return bool(_ORDER_TESTS[operator](cell, value))

    @staticmethod
    def _sort_key(cell: str, mode: SortMode) -> tuple[object, ...]:
        """Build the sort key of one cell for every mode except numeric."""
        match mode:
            case SortMode.CASE_INSENSITIVE:
                return (cell.casefold(), cell)
            case SortMode.LENGTH:
                return (len(cell), cell)
            case SortMode.NATURAL:
                return PrebuiltToolSupport.natural_sort_key(cell)
            case _:
                return (cell,)

    @staticmethod
    def _aggregate(cells: list[str], function: AggregateFunction, parameter_name: str) -> tuple[int | float | None, int, int]:
        """Summarize cells, returning the result, the cells used, and the non-empty cells skipped as not numeric."""
        filled = [cell for cell in cells if cell.strip()]
        if function is AggregateFunction.COUNT or function is AggregateFunction.DISTINCT_COUNT:
            result = len(filled) if function is AggregateFunction.COUNT else len(set(filled))
            return result, len(filled), 0
        # Numeric summaries run on exact fractions and are rounded to a
        # float once, so a mean or median of two cells is exact too.
        exact = [Fraction(number) for number in map(PrebuiltToolSupport.parse_numeric_text, filled) if number is not None]
        skipped = len(filled) - len(exact)
        if not exact:
            return None, 0, skipped
        try:
            summary = float(_NUMERIC_SUMMARIES[function](exact))
        except OverflowError as exc:
            raise PrebuiltToolSupport.argument_error(parameter_name, "the sum is outside the floating-point range", "numeric cells whose sum is a finite number") from exc
        return summary, len(exact), skipped

    @staticmethod
    def _alignment_markers(header: list[str], rows: list[list[str]], alignment: TableAlignment) -> list[str]:
        """Return the separator cell of every column, right-aligning all-numeric columns under auto."""
        if alignment is not TableAlignment.AUTO:
            return [_ALIGNMENT_MARKERS[alignment]] * len(header)
        markers = []
        for index in range(len(header)):
            numeric = all(PrebuiltToolSupport.parse_numeric_text(row[index]) is not None for row in rows if row[index].strip())
            markers.append(_ALIGNMENT_MARKERS[TableAlignment.RIGHT if numeric else TableAlignment.LEFT])
        return markers

    @staticmethod
    def _table_line(cells: list[str]) -> str:
        """Write one Markdown table line, escaping pipes and turning line breaks into HTML line breaks."""
        escaped = (_CELL_LINE_BREAK.sub("<br>", cell.replace("|", "\\|")) for cell in cells)
        return "| " + " | ".join(escaped) + " |"

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.csv_to_records,
            cls.detect_csv_dialect,
            cls.profile_csv_columns,
            cls.csv_filter_rows,
            cls.csv_sort_rows,
            cls.csv_aggregate_column,
            cls.csv_group_by,
            cls.csv_join_tables,
            cls.csv_to_markdown_table,
        )


__all__ = ["CsvTablesToolFunctions"]
