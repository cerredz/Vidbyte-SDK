# Prebuilt agent tools feature tests

## Folder Description / Intent

This pack holds the behavioral contract of the prebuilt tool library: `PrebuiltTools`, `PrebuiltToolCategory`, the §9.2 enums, and all 265 Appendix A tools. Every test reaches a tool the way a model does, through `FunctionTool.execute(ToolCall(...))`, so schema validation, the worker thread, and output serialization stay real. Expected values come from hand-copied spec tables and from independent computation, never from the implementation. Read `FEATURE.md` first for the contract and the failure inventory.

Run the pack with `PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools`. Run one file by adding its name after the folder path.

## Non-Goals

- Pinning values that differ between Python 3.11 and 3.12 (seeded draws, `ast` grammar, `ipaddress` flags, Unicode data).
- Timing assertions. The pack never measures speed; its only clock is the liveness watchdog of `test_prebuilt_hostile_inputs.py`, which turns a hung call into a failure.
- Testing `FunctionTool`, `Tools`, or the provider formatters themselves; their own suites own that.
- Root export lists and the public API contract; existing gates own those.

## File Index

- `README.md` explains the pack boundary and how to run it.
- `FEATURE.md` states the contract, the failure inventory the tests were chosen from, the suite map, and the omitted strategies.
- `conftest.py` imports `PrebuiltTools` and `PrebuiltToolCategory` lazily (`prebuilt_api`), builds the whole library once per session (`prebuilt_library`), and wraps it in a `ToolRunner` (`tool_runner`).
- `prebuilt_tool_harness.py` holds the case builders (`ok`, `bad`, `invalid`), the output matcher (`ANY`, `Close`, float tolerance), `ToolRunner`, `SchemaArgumentFactory`, and `ConstructionCounter`.
- `prebuilt_catalogue_data.py` is the hand-copied category table, the enum table, and the output keys of every tool.
- `prebuilt_parameter_data.py` is the hand-copied parameter table of every tool: names, JSON types, caps, and defaults.
- `test_prebuilt_acceptance.py` runs the §4 snippet and the import probe in fresh interpreters. Start here for a caller-visible regression.
- `test_prebuilt_toolset_contract.py` checks construction, category validation, catalogue order, enums, tool shape, and per-tool schemas.
- `test_prebuilt_model_facing_contract.py` checks description depth, provider schemas, and one-over-cap validation.
- `test_prebuilt_error_contract.py` sweeps every tool with schema-derived arguments for the result and error contract.
- `test_prebuilt_determinism.py` compares outputs across hash seeds and environments in child interpreters.
- `test_prebuilt_side_effects.py` instruments sockets, processes, environment, clock, and files, and scans the source for banned calls.
- `test_prebuilt_resource_bounds.py` checks truncation, integer limits, output caps, peak memory, and deep nesting.
- `test_prebuilt_rows_numbers.py` covers rows A.1 to A.3: exact arithmetic, number theory, and number formatting.
- `test_prebuilt_rows_statistics.py` covers rows A.4 to A.6: descriptive statistics, probability, and seeded random tools.
- `test_prebuilt_rows_finance_units.py` covers rows A.7 and A.8: finance money rules and unit conversion.
- `test_prebuilt_rows_time.py` covers rows A.9 to A.11: dates, scheduling, timestamps, and durations.
- `test_prebuilt_rows_text.py` covers rows A.12 and A.13: text counting and text transforms.
- `test_prebuilt_rows_unicode_regex.py` covers rows A.14 to A.16: Unicode, regular expressions, and text comparison.
- `test_prebuilt_rows_json_csv.py` covers rows A.17 to A.19: JSON data, JSON records, and CSV tables.
- `test_prebuilt_rows_formats_encoding.py` covers rows A.20 to A.22: structured formats, encodings, and hashing.
- `test_prebuilt_rows_identifiers_lists_graphs.py` covers rows A.23 to A.25: identifiers, lists, and graphs.
- `test_prebuilt_rows_geometry_bits_markdown.py` covers rows A.26 to A.28: geometry, bits and bytes, and Markdown and HTML.
- `test_prebuilt_rows_extraction.py` covers row group A.29: text extraction.
- `test_prebuilt_rows_code_network.py` covers rows A.30 and A.31: code analysis and network addresses.
- `test_prebuilt_hostile_inputs.py` runs cap-sized hostile inputs in a child interpreter under a 30 s liveness watchdog and checks their exact output, and checks that a hostile host decimal context changes no result (S4 R-1 to R-14).

## Logs

- 2026-10-14 - The pack was written red before implementation from spec revision 3. Every test fails or errors until `PrebuiltTools`, `PrebuiltToolCategory`, the enums, and `vidbyte/tools/builtins/prebuilt/` exist.
- 2026-10-14 - The pack was tightened to spec revision 4: values revision 3 left open are now exact, every list and `UtcOffset` cap is an exact number, and the new error mappings have cases.
- 2026-10-14 - S3 found that the parameter table typed `intersect_lists.lists` as a list of strings, while Appendix A.24 makes it `list[TextList]`. The table now describes it with `TextListsShape`, and the schema and over-cap tests check the inner lists too.
- 2026-10-14 - Regression cases for the S4 findings went in before the repair, from spec revision 6. Cap-sized hostile inputs run in `test_prebuilt_hostile_inputs.py` under a liveness watchdog, row-level cases sit in the matching row files, INV-9's illustrative literals are flagged, and `find_substring_positions.substring` is capped at 500.
