# S2 report: test author, prebuilt agent tools

Spec: `docs/spec/prebuilt-agent-tools/spec.md` r3 · Branch `feat/prebuilt-agent-tools` · Base `8387d666` · Start HEAD `01a41fa5`

Commits made by this stage:
- `bf26faa3` test(prebuilt-tools): add failing tests for prebuilt-agent-tools [AC-1..AC-21]. This commit holds the pack and `test-plan.md`.
- `384915f7` docs(spec): record test proof for prebuilt-agent-tools. This commit changes only the §6.2 Proof column, rows AC-1 to AC-21.
- A third commit adds this report.

`docs/spec/prebuilt-agent-tools/pipeline.md` has an uncommitted change that belongs to the orchestrator. It was neither staged nor touched.

## 1. What was produced

The pack lives in `tests/features/prebuilt_tools/`. It has no `__init__.py`. Every `test_*.py` has a full A001 header, and the header's `TESTS` field names that file's own pytest command.

| File | Role |
|---|---|
| `FEATURE.md` | Contract, the 16-item failure inventory, the suite map, and the omitted strategies (the §13 headings) |
| `README.md` | Folder Description / Intent, Non-Goals, File Index, and Logs |
| `conftest.py` | Session fixtures: `prebuilt_api` (imports `PrebuiltTools` and `PrebuiltToolCategory` lazily), `prebuilt_library` (the whole library, built once), and `tool_runner` |
| `prebuilt_tool_harness.py` | Case builders `ok`, `bad`, and `invalid`; `OutputMatcher` with `ANY` and `Close`; `ToolRunner`; `SchemaArgumentFactory`; `ConstructionCounter` |
| `prebuilt_catalogue_data.py` | Hand-copied Appendix A category table (265 names), the §9.2 enum table (68 enums), and the output keys of every tool |
| `prebuilt_parameter_data.py` | Hand-copied parameter table: names, JSON types, caps, and defaults for all 265 tools |
| `test_prebuilt_acceptance.py` | AC-1 (the §4 snippet, verbatim, in a fresh interpreter) and AC-5 (the import probe) |
| `test_prebuilt_toolset_contract.py` | AC-2, AC-3, AC-4, AC-12, AC-18, AC-19, INV-1 to INV-6, INV-8, INV-16, INV-22, and the enum tables |
| `test_prebuilt_model_facing_contract.py` | AC-7, AC-8, and AC-9 |
| `test_prebuilt_error_contract.py` | AC-6, INV-10, INV-11, INV-14, INV-15, and T-3 |
| `test_prebuilt_determinism.py` | AC-10 and INV-12 |
| `test_prebuilt_side_effects.py` | AC-13, INV-13, T-5, and T-6 |
| `test_prebuilt_resource_bounds.py` | AC-14, AC-15, AC-20, AC-21, and INV-17 to INV-20 |
| `test_prebuilt_rows_*.py` (12 files) | AC-11: exact-output and error cases for every Appendix A row |

The pack has 4,284 collected tests, built from 101 test functions. The row files hold 1,339 success cases and 511 failure cases. All 265 tools have at least one exact-output case at the model seam; a script checked this, and no tool is missing. Of 3,493 expected output values, 37 are `ANY`, used only where the spec leaves a value open or version-dependent.

No existing fixture or test was changed. The only shared fixtures are new ones in the pack's own `conftest.py`.

## 2. Failure inventory and selection

The inventory is the 16 numbered entries in `FEATURE.md` § Known Failure Modes. Every spec ID maps to a test in the `test-plan.md` coverage map: AC-1 to AC-21, INV-1 to INV-26, the key ECs, T-3, T-5, and T-6. The inventory entries I added beyond the spec's IDs are these:
- Float routes that break §9.2 items 16 and 17 on exact ties: 8.845 half-up, 2.0035 s, and 0.000875°.
- Positions read from a lowercased copy (ß, İ, ﬁ).
- `IndexError` from a regex template group and `TypeError` from ElementPath leaking past the error contract.
- A deep value that reaches `_stringify_output` and makes `execute` itself raise.
- Over-cap text built first and refused afterwards.
- Hash-seed order leaking from sets and dicts.

Selection followed the orchestrator's scale note. There are few test functions, parametrized over tables, plus library-wide sweeps parametrized over every tool, all at the real `FunctionTool.execute(ToolCall(...))` seam with nothing mocked. Only the AC-13 instrumentation monkeypatches anything (`socket`, `subprocess`, `os.system`, `os.environ`, the clock readers, and `open`). It records a call only when a frame from `vidbyte/tools/builtins/prebuilt/` is on the stack.

What I pruned and why is in the `test-plan.md` table "Tests deliberately NOT written". In short:
- Wall-clock bounds (AC-15, AC-20, NFR-7, EC-37) are replaced by structural checks: peak traced memory and counts that could not finish by enumeration.
- INV-23 to INV-26 already pass, and existing gates own them.
- An INV-3 collision runtime test would pass today. A static check found 0 collisions among 743 existing SDK name literals.
- The EC-14 surrogate path cannot be reached through `execute`.
- Cross-version pins (EC-24, EC-25, EC-26, EC-38) are left out.
- EC-10 backtracking would hang.
- EC-27, EC-28, and EC-40 are runtime behavior, not tool behavior.
- A row-coverage meta-test would pass today; coverage was checked by script instead.
- Unseeded fuzzing would not reproduce.

## 3. How the expected values were made independent

- Each row file used a different route from the obvious stdlib call wherever one existed:
  - published vectors: RFC 4231, 2202, 4648, 3986, and 6902; Luhn, ISBN, IBAN, GTIN, and uuid3/uuid5; π(10^7); C(52,5); z(0.975);
  - hand computation with `Fraction` or high-precision `Decimal`;
  - brute-force loops for dates and graphs;
  - sympy for primes and divisors, num2words, and mpmath (all pre-installed; nothing was pip-installed);
  - closed forms such as 2^128, C(39,20) = 68,923,264,410, and σ(963761198400) = 5,531,765,944,320.
- Where the spec names the mechanism, the same route was accepted, and the plan's "Row files" table lists those cases: `re` positions, `difflib`, `unicodedata`, the Expat, JSON, and `csv` messages, `ast.unparse`, `ipaddress`, and the seeded `random.Random(seed)` replay.
- The machinery itself was checked against a scratch-only fake plugin with 5 tools, which was never committed:
  - 85 tests passed. The only failures were the expected INV-8 qualname failure (the fake functions are module-level) and the base64url padding case, where the fake padded.
  - A leak module under a `.../vidbyte/tools/builtins/prebuilt/` path proved the recorder catches `os.environ` and `time.time`.
  - A build-first fake reached a peak of 20,923,132 bytes and failed the 5 MB peak test.
  - `set(SOUP_WORDS)` iterates differently under hash seeds 0 and 4242, so the determinism battery can see order leaks.
  - A pydantic probe confirmed length is checked before pattern, and that an over-cap list item reports loc `(0,)`, so the AC-7 logic holds.

## 4. Red run

Bootstrap: none (PYTHONPATH=<worktree>); verified import path.

```
PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"
C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-prebuilt-agent-tools\vidbyte\__init__.py
```

Each new file was run with `PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/<file>.py`. Every file showed 0 passed, and these are the final lines:

```
test_prebuilt_acceptance.py                   2 failed in 2.09s
test_prebuilt_determinism.py                  2 errors in 0.24s
test_prebuilt_error_contract.py               268 errors in 1.15s
test_prebuilt_model_facing_contract.py        746 errors in 2.88s
test_prebuilt_resource_bounds.py              38 errors in 0.39s
test_prebuilt_rows_code_network.py            96 errors in 0.57s
test_prebuilt_rows_extraction.py              19 errors in 0.30s
test_prebuilt_rows_finance_units.py           216 errors in 0.99s
test_prebuilt_rows_formats_encoding.py        209 errors in 0.96s
test_prebuilt_rows_geometry_bits_markdown.py  151 errors in 0.75s
test_prebuilt_rows_identifiers_lists_graphs.py 160 errors in 0.77s
test_prebuilt_rows_json_csv.py                149 errors in 0.79s
test_prebuilt_rows_numbers.py                 302 errors in 1.44s
test_prebuilt_rows_statistics.py              182 errors in 0.97s
test_prebuilt_rows_text.py                    132 errors in 0.69s
test_prebuilt_rows_time.py                    235 errors in 1.08s
test_prebuilt_rows_unicode_regex.py           167 errors in 0.81s
test_prebuilt_side_effects.py                 1 failed, 266 errors in 1.15s
test_prebuilt_toolset_contract.py             99 failed, 844 errors in 3.84s
```

Whole pack, after the commit:

```
PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/prebuilt_tools -rfE
ERROR tests/features/prebuilt_tools/test_prebuilt_toolset_contract.py::test_every_text_and_list_parameter_is_capped[convert_ip_address_integer]
ERROR tests/features/prebuilt_tools/test_prebuilt_toolset_contract.py::test_every_text_and_list_parameter_is_capped[convert_ipv4_netmask]
102 failed, 4182 errors in 16.85s
```

These are the reasons, tallied from the `-rfE` run. Every one is the right reason, which is that the feature does not exist yet:
- 4,182 errors, each `AttributeError: module 'vidbyte.tools.toolsets' has no attribute 'PrebuiltTools'`, raised at fixture setup.
- 68 `test_enum_vocabulary_matches_spec` failures: `<Enum> is not exported from vidbyte.lib.enums`.
- 31 `test_category_class_lists_its_functions_in_row_order` failures: `ModuleNotFoundError: No module named 'vidbyte.tools.builtins.prebuilt'`.
- 2 acceptance failures, where the child process's returncode is 1 because `PrebuiltToolCategory` cannot be imported.
- 1 static-scan failure, because the expected `vidbyte/tools/builtins/prebuilt/*.py` modules are missing.

The neighbouring area is unchanged from the pre-S2 baseline, so I found no pre-existing failure to compare against merge-base `8387d666`:

```
PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/test_tools_catalog.py tests/test_function_tool_parameter_types.py tests/test_tool_core.py tests/features/coding_agent
........................................................................ [ 82%]
..............................................................           [100%]
338 passed, 12 skipped in 14.63s
```

Collecting the whole suite with `python -m pytest --collect-only -q` gives 8,312 tests and no collection error.

I ran lint with the pack, `FEATURE.md`, `README.md`, and `test-plan.md` all staged. Every rule count matched the first run exactly. No new finding appeared, and no baseline number rose; S061 even shows an existing improvement that was not mine:

```
PYTHONPATH=$(pwd) python lint/run.py
S063 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S063 --all

S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```

## 5. Spec defects and loose rows

**Defects.** These made a test impossible or forced a choice:
1. The EC-14 lone-surrogate path cannot be reached through `FunctionTool.execute`, because pydantic JSON mode rejects `"\ud800"` during validation. For the same reason, `unicode_character_info` can never return `utf8_hex: null`. The EC-14 text and that return value cannot be observed at the model seam.
2. Some list parameters have no stated cap, although INV-16 requires one for every list: `add_business_days.holidays`, `add_business_days.weekend_days`, `critical_path_schedule.dependency_sources`, and `critical_path_schedule.dependency_targets`. The tests require only that some cap exists (`ANY_CAP`).
3. `UtcOffset` has no length cap and is bounded only by its pattern. The tests pin the exact pattern `^(Z|[+-](0[0-9]|1[0-9]|2[0-3]):[0-5][0-9])$`.
4. `verify_email_syntax` can never report `domain_too_long`, because `address_too_long` fires first under the row's own limits. Effectively, that enum value is dead.
5. Unpadded base64url is stated only on the `hash_text` row. The tests apply it to `compute_hmac` too, since both use `DigestFormat`.
6. `xml_find_elements` with the path `"["` makes the stdlib raise `TypeError`, not `SyntaxError`. The implementation must catch both, and the test requires error(`path`).
7. A source containing a null byte raises `ValueError` on 3.11 and `SyntaxError` on 3.13. The code-analysis tools must handle both.
8. `classify_ip_address` flags for IPv4-mapped addresses depend on the Python version. They are not pinned.
9. Several error rows name no parameter. Tests pinned a parameter for these:
   - `fiscal_quarter` past year 9999;
   - the `bitwise_operation` shift amount;
   - `business_days_between` with all 7 days as weekend days.
10. The infeasible-if-enumerated count tests would hang, not fail, against an implementation that enumerates (2^128 subnets, 10^15 integers, C(39,20) combinations). This is by design, but a reviewer should know a hang means a failure.

**Loose rows where a test pinned one reading.** S3 and S4 should check each against the spec rather than change the test casually.

*Numbers and statistics*
- `number_to_english_words` separates scale groups with single spaces.
- `fraction_arithmetic` "more than 4,000 digits" is read as applying to the result.
- The `fraction_to_decimal` boundary "closed within 1,000 digits" is unclear.
- The birthday formula has a precision limit.
- `compute_quartiles` with 2 values is not tested.

*Finance*
- NPV overflow assumes float arithmetic.
- A negative money value is written as "-100.00".
- The full-schedule values (final payment 1200.14, total 431677.04) use the same route as the spec's own Fraction algorithm.

*Time*
- The `time` key is `time.isoformat()`.
- It is unclear what `resolve_relative_date_phrase` returns for `weekday` on a period phrase.
- The long style of `format_duration` with zero parts is unclear.
- `parse_duration_text` accepts decimals.

*Text and Unicode*
- `PREBUILT_HTML_BLOCK_TAGS` contents are not listed.
- `fill_text_template` `filled` semantics are unclear.
- `extract_line_range` trailing newline on a middle range is unclear.
- `convert_identifier_case` digit followed by an uppercase letter is unspecified.
- Numeric sort with `descending` is unspecified.
- The `code_point` format is stated only in A.12.
- `find_unicode_character` word vs substring match is unclear.
- `remove_diacritics` "non-Latin left as is" conflicts with dropping Mn after NFD.
- `find_invisible_characters` handling of CRLF in `cleaned_text` is unclear.
- `sms_segment_count` on empty text is unspecified.
- The `verify_regex_pattern` error text is unspecified.

*JSON, CSV, and formats*
- The `csv_to_markdown_table` separator and padding are unspecified, so the markdown is `ANY` plus a structural test.
- `detect_csv_dialect` `rows` is unclear.
- `extract_json_from_text` `end` is exclusive.
- `verify_json_syntax` depth and NaN messages are unspecified.
- `values_skipped` is unclear.
- `profile_csv_columns` distinct-by-text vs distinct-by-value is unclear.
- `json_set_value` on an index below the length replaces.
- `join_records` keeps the right join field.
- `parse_dotenv_text` `count` is distinct variables.
- The `verify_xml_wellformed` DOCTYPE fields are unspecified.
- An `xml_find_elements` parse error is error(`xml_text`).

*Identifiers, graphs, and Markdown*
- `verify_url_syntax` host on failure is unclear.
- `verify_iban` fields after a mod-97 failure are unclear.
- The `verify_isbn` output form is unclear.
- The `find_graph_cycle` start node is unclear.
- The setext heading `line` is unclear.
- Autolink `text` is undefined.
- Fenced-block line numbers are unclear.
- The column count of a malformed table in `html_table_to_records` is unclear.

*Extraction and code*
- `count` for the unique-value extractors is distinct values.
- `extract_numbers` handling of `%` is unclear.
- `list_python_imports` for plain `import` is undefined.
- `get_python_function_signature` bare vs qualified name and `*` prefixes are unclear.
- `python_literal_to_json` "compact" is `(",", ":")`.
- The `find_python_name_usages` column is in code points.

## 6. Notes for the implementer

The binding names and the error-message regex are in `test-plan.md` § Notes for the implementer. These points are the most likely to trip S3:
- `vidbyte/tools/builtins/prebuilt/` must hold `__init__.py`, `_support.py`, and one `<category value>.py` per category. Each function's `__qualname__` must be `<Category>ToolFunctions.<tool>`.
- Messages must match `Invalid value for '<parameter>': <problem>. Expected <form>.` exactly. Never echo more than 100 characters of an argument, and never echo the HMAC key.
- For outputs of 20 MB or more, the peak traced memory must stay under 5 MB, so predict the size; do not build the output and then measure it.
- A schema pattern that `SchemaArgumentFactory` has no sample for raises "add one to the pools". The fix is a new sample in `PATTERN_SAMPLES`. That is a fixture change, and it is allowed; changing an assertion is not.
- Once green, the pack runs for about one to several minutes. The sweeps make about 28 calls per tool (13 in the error contract, 6 in the side-effect tests, and 3 in each of three determinism interpreters), and `find_unicode_character` costs about 1 s per call (EC-37).

## Addendum: r4 tightening

Trigger: the coordinator's follow-up after spec r4 (`5d93fe88`) and the S1 r4 addendum (`deed7463`) resolved this report's open items. Commit: `f49db5db` test(prebuilt-tools): tighten assertions to spec r4 readings [AC-7, AC-11, INV-16]. Every value below was read from its r4 Appendix A row, §9.2, or the S1 addendum, then checked by script where it is computed (quartiles, the 1/2^1001 digits, domain lengths, `ast.unparse` text, and usage columns).

**Contradictions: none.** No existing assertion disagreed with r4. Every change replaces an `ANY`, a range, a "non-empty" check, or a "cap only needs to exist" sentinel with r4's exact value, or adds a case for behavior r4 newly states.

### What changed

- **AC-7 and INV-16.** `prebuilt_parameter_data.py` gives the four `UtcOffset` parameters `maxLength` 6 beside the pattern. It also makes `add_business_days.holidays` 1,000, `weekend_days` 7, and both `critical_path_schedule` dependency lists 10,000. The `ANY_CAP` and `PATTERN_BOUND` sentinels are gone. The schema test compares every cap exactly and requires `maxLength` on every plain string. The one-over-cap test sends a list with an item cap twice: once with one over-long item (loc `param.0`), and once with one item too many. A scratch fake plugin passed AC-7 with the exact `add_business_days` caps.
- **AC-11, tightened to exact values.**
  - Markdown: the Setext `line` (10), autolink `text`, all three fenced blocks, and named columns for a malformed table.
  - CSV and JSON: `units_per_segment` 160 for empty text, the `detect_csv_dialect` fallback `quote_character` and `rows`, null positions in `verify_json_syntax` and `verify_xml_wellformed`, and `profile_csv_columns` distinct by text.
  - Code: `list_python_imports` plain-import fields, `find_python_name_usages` columns, and `get_python_function_signature` text.
  - Messages and text: `verify_regex_pattern` `re.error.msg` and `pos`, `extract_numbers` `"45%"`, exact `csv_to_markdown_table` and `strip_html_tags` text, and `format_duration` long form.
  - Top-level `ANY` values fall from 37 to 12, and no nested `ANY` remains (r3 had 23). A new `NON_EMPTY_TEXT` marker covers the six errors r4 fixes as non-empty text without giving words.
- **New cases (28 tests, a net 26 after the removals).**
  - A.30 null character: error(`literal`) and five error(`source`) cases. The existing `verify_python_syntax` case is now exact.
  - `xml_find_elements` `"@"` → error(`path`) (`KeyError` on 3.11), and `verify_xml_wellformed` with a plain DOCTYPE.
  - `verify_email_syntax`: a 254-character domain gives `domain_too_long` before `address_too_long`.
  - `fiscal_quarter` at year 1 and year 9999 → error(`target_date`).
  - `bitwise_operation` missing or 4,097 shift → error(`right`); seven weekend days → error(`weekend_days`).
  - Value cases: padded `base64` digest, ISBN lowercase `x`, `fraction_to_decimal` past 1,000 digits, two-value quartiles, `version2Beta`, numeric descending sort, two `extract_line_range` break cases, non-Latin marks kept, and CR, LF, and TAB kept.
  - Two more AC-7 tools: `convert_utc_offset` and `unix_timestamp_to_datetime`.
- **Removed.**
  - The parametrized `test_verify_xml_wellformed_reports_rejected_markup_with_a_message` (2 tests): the row cases now state the same outputs exactly.
  - `csv_to_markdown_table-counts`: renamed to `-auto-exact-text` with exact text.
  - Two `add_business_days` over-cap `invalid` cases drafted in this pass: AC-7 now covers them.
  - A drafted lone-surrogate case: `FunctionTool` rejects `"\ud800"` under loc `arguments` before any tool runs (r4 EC-14), so it could never fail because of prebuilt code.

### Proof

Pack: 4,310 tests (was 4,284); row files 1,353 success and 523 failure cases; 265 of 265 tools have a success case. Every file still has 0 passed; the per-file lines are in `test-plan.md` § Red run.

```
PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/prebuilt_tools -rfE
ERROR tests/features/prebuilt_tools/test_prebuilt_toolset_contract.py::test_every_text_and_list_parameter_is_capped[convert_ip_address_integer]
ERROR tests/features/prebuilt_tools/test_prebuilt_toolset_contract.py::test_every_text_and_list_parameter_is_capped[convert_ipv4_netmask]
102 failed, 4208 errors in 17.61s
```

Tally: 4,208 errors are all `AttributeError: module 'vidbyte.tools.toolsets' has no attribute 'PrebuiltTools'`. The 102 failures are 68 enum exports, 31 `ModuleNotFoundError: vidbyte.tools.builtins.prebuilt`, 2 acceptance returncodes, and 1 static-scan missing-module assertion.

```
PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/test_tools_catalog.py tests/test_function_tool_parameter_types.py tests/test_tool_core.py tests/features/coding_agent
........................................................................ [ 61%]
........................................................................ [ 82%]
..............................................................           [100%]
338 passed, 12 skipped in 14.87s

PYTHONPATH=$(pwd) python -m pytest --collect-only -q -p no:cacheprovider
8338 tests collected in 1.63s

PYTHONPATH=$(pwd) python lint/run.py        (tests and test-plan.md staged)
S063 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S063 --all

S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```

Lint exited 0, and its output matches the pre-tightening run line for line, apart from timings.

### Residual readings

These readings are S2's own, because r4 is silent. They are not spec defects.
- `get_python_function_signature` without a return annotation is `def run(self)`, with no arrow. r4 gives the form only as `def name(...) -> ...`.
- `detect_csv_dialect` `has_header` stays `ANY` in two cases, because the row does not say how the header is detected.
- The count tests (2^128 subnets, 10^15 integers, C(39,20)) hang rather than fail against an enumerating implementation; the pack sets no timeout.
