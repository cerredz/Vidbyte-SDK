# S1 spec author report — prebuilt-agent-tools

Spec: `docs/spec/prebuilt-agent-tools/spec.md`, revision 1, committed as `d7cc529a` on `feat/prebuilt-agent-tools` (base `8387d666`).

## What I read

- **Pipeline inputs (the only `docs/` files read):** `request.md`, `context/code-map.md`, `context/research.md`, `reports/S0-scout.md`, `reports/S0-research.md`.
- **Repository rules:**
  - `AGENTS.md`, all of it: the five coding principles, Placement Rules, and the Repository Map rules.
  - `REPO_MAP.md` entries for `vidbyte/tools/`, `tools/builtins/`, `tools/toolsets/` (stale: it says "one such bundle"), `lib/constants/`, `lib/enums/`, and `lib/errors/`.
  - `vidbyte/tools/README.md`, all of it.
- **Field guide** (`field-guide/vidbyte-sdk/`): `model-facing-tool-contracts.md`, `prebuilt-agents.md`, `strict-config-dataclasses.md`, `blocking-lint-invariants.md`, `local-ci-verification.md`, `class-bound-helpers.md`, `comment-format.md`, `agents-md-map.md`, `review-scope.md`, `declarative-config-resolution.md`, `vidbyte-gates.md`.
- **Code read to ground the design:**
  - `vidbyte/tools/function_tool.py`: schema build, JSON-mode validation, error conversion, `_stringify_output`, `_docstring_summary`, and null-means-default.
  - `vidbyte/tools/catalog.py`: duplicate rejection, `subset` order, and `Sequence` indexing.
  - `vidbyte/tools/base.py`.
  - `vidbyte/lib/dataclasses/tools.py`: `ToolCall`, `ToolResult`, `ToolStatus`, `ToolSpec`, `ToolParameter`.
  - `vidbyte/lib/errors/base.py`.
  - `vidbyte/tools/toolsets/coding.py` and `__init__.py`.
  - `vidbyte/lib/enums/__init__.py` and `reasoning_strategies.py`.
  - `vidbyte/lib/util/math.py` and `text.py`.
  - `vidbyte/lib/tools/formatter.py`.
  - `vidbyte/__init__.py` (`__all__` at `:690`).
- **Lint sources read to predict findings:**
  - Rules: A001, A002 (`a002_intent_comments.py:25-75`), A003, A007 (`a007_operational_constants.py:23-38,60-137`), C006 (`c006_finite_numeric_guards.py:27-28`), C008 (`c008_shared_validator_owner.py:25-40`), C015, S009, S016, S017, S020 (`s020_readme_file_index_parity.py`), and S025 (`SentenceCounter` at `:185`).
  - Config: `lint/ruff.toml` and `.semgrep/typed-mapping-boundary-policy.yml`.
- **Probes I ran (scratch files outside the repo, nothing committed):**
  - 300 `FunctionTool`s build in about 0.22 s, and `import vidbyte` takes about 0.7 s.
  - Pydantic accepts an aware `time` (so the tool must reject it), rejects `2023-02-29`, and with `allow_inf_nan=False` rejects non-finite floats. A tuple-of-enum default renders as an array.
  - A parameter named `schema_json` makes pydantic warn that it shadows a `BaseModel` attribute.
  - `statistics.quantiles` exclusive and inclusive values for 1–8.
  - 1463! has 3,998 digits and 1464! has 4,001, and C(10000, 5000) has 3,009 digits.
  - `Agent(...)` builds without an API key.
- **Baseline on the clean worktree:**
  - `python lint/run.py` ended `SDK-LINT: PASS`. Eight rules already show IMPROVED before any change.
  - `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` gave `4015 passed, 13 skipped`, `CI passed.`.
  - I did not run the package stage or semgrep.

## Approaches weighed

- **Chosen (D-1, D-2): one typed `@staticmethod` per tool on 31 `<Category>ToolFunctions` classes, wrapped by the existing `FunctionTool`, and attached through `PrebuiltTools(categories)`, a `Tools` subclass.**
  - It reuses the SDK's only function-to-tool mechanism, so it adds no new tool machinery.
  - Category-sized attachment (6–12 tools) answers the research finding that accuracy drops once a model sees more than about 10–30 tools ([14][16][17][21] in `research.md`).
  - The rejected alternatives are in §8.3: one flat 277-tool `Tools`, about 60 multi-operation tools, and raw functions with no toolset.
  - Runner-up: a `BaseTool` subclass per tool. It would make S025 scan every description and would allow YAML discovery, but it means about 277 classes with hand-written `spec()` methods. It flips only if the user answers yes to Q-4.
- **Return type (D-7):** plain `dict[str, object]` with exact documented keys, not 277 frozen dataclasses.
  - `FunctionTool` already validates inputs through a generated pydantic model, and its output path serializes dicts.
  - One dataclass per tool would add about 277 records to `vidbyte/lib/dataclasses/` and nearly double the budget.
  - This is the decision I am least sure of against AGENTS.md principle 4. It is optional Q-6, default no.
- **Errors (D-8):** I first planned a `PrebuiltToolArgumentError`. The `REPO_MAP.md` entry for `vidbyte/lib/errors/` says a new failure mode should usually reuse an existing type, and A003 would also demand a full diagnostic packet. So every domain error is a `ToolExecutionError` built by one helper with one message form (INV-15).
- **Exactness (D-13, D-16):**
  - Integers, decimals, and fractions travel as canonical text, so JSON never loses precision past 2^53.
  - Integer results are capped at 4,000 digits (INV-18), so Python's 4,300-digit `int`-to-`str` limit never fires inside `_stringify_output`.
  - Unit tables are exact `Fraction` strings.
- **Count floor (D-9):** a test in the S2 pack asserts the count is at least 250 and that the name set equals Appendix A. I chose this over a CI script that would pin the exact count.

## Where I disagreed with the scout or the request

1. **The request assumed a modest set of built-ins with a registry to add tools to.** In fact `vidbyte/tools/builtins/` already holds about 218 reasoning-trace classes, `Tools` is local to each agent, and there is no global tool registry. The design therefore adds a toolset rather than registering anything (D-2, INV-6).
2. **The scout's lint table left out several rules the new files will trip:**
   - S050 (md5/sha1 `usedforsecurity=False`), S004 (no naive datetimes or `strptime`), S003 (`zip(strict=)`), S054 (secret-like names), S009 (mypy), C006/C008 (validator-shaped names), and the pydantic shadow-name warning.
   - A007's context window: for a literal in a parameter annotation, A007 scans every name in the whole signature. That forced two renames: the constant `PREBUILT_MAX_RECURRENCE_STEP` and the parameter `repeat_every`, instead of `interval`.
   - Other renames from these rules: `jwt_text` instead of `token`, `json_schema` instead of `schema_json`, `html_text` instead of `html`, `bit_format` instead of `format`, `float_result` instead of `finite_float` (C008 noun family), and `find_violations` instead of `validate` (C006).
   - All of these are §12.4 obligations.
3. **The scout raised a concern about provider-formatter `items` handling.** It does not apply on the `FunctionTool` path: pydantic emits `items` for lists, and the Gemini reducer expands `$defs`.
4. **Overlap with the existing calculator, which I verified (4,096-bit cap).** I dropped big-integer multiply, divide, and power so the two do not compete (NG-7).
5. **Research rows dropped as unsafe, non-deterministic, or overlapping:**
   - IANA time zones (`tzdata` is not a dependency) and current date or time (clock-dependent).
   - YAML (alias expansion; NG-10), a SQLite query tool, password or secret generation, gzip, punycode, cron, Easter dates, and calendar printing.
   - `is_palindrome`, `build_markdown_table` (overlaps `csv_to_markdown_table`), stop-word removal, color tools, and matrix tools.
6. **The request's "straight into spec"** means no questions block the spec. All six open questions are optional, with default "no" (NFR-11).

## Assumptions I am least sure of

- **D-7 / A-7:** dict outputs against AGENTS.md principle 4. A reviewer may ask for typed output records, which is Q-6.
- **A-6:** model-facing descriptions carry no examples because the field guide forbids them, although research [16] found that examples help with format-heavy parameters such as dates, dice notation, and semver ranges.
- **EC-24:** seeded tools reproduce only within one Python minor version. Tests must not pin seeded sequences across 3.11 and 3.12.
- **NFR-7 / A-9:** the per-call target of ≤ 2 s at maximum input. It is least certain for `closest_string_matches` (1,000 candidates), `find_unicode_character` (a full scan of about 1.1 million code points), `diff_words` at 20,000 tokens, and `levenshtein_distance` at 1,000 × 1,000.
- **Heuristic tools** (syllables, sentence splitting, script detection, mojibake repair, `count_lines_of_code`): the spec defines exact algorithms so tests can bind to them. Their usefulness on real text is the part that has not been measured.
- **FR-8 wording:** domain-fixed bounds (months, bases 2–36, percent and coordinate ranges) are allowed as literal `Field` constraints, while every length cap and resource bound is a named constant. A strict reviewer may prefer constants for everything.

## Addendum — r2 (S1 review applied)

The reviewer's verdict was SOUND WITH FIXES (3 Blocker, 6 Major, 3 Minor). I accepted all twelve findings. R-2 and R-4 were widened after I probed the same failure classes, and R-9 and R-10 took their optional drops. §16 records each disposition.

**Changes by finding:**
- **R-1, exactness:**
  - §9.2 item 5 now has a float precision rule: `rel=1e-9, abs=1e-12`, or 10^-k for floats a row rounds to k places. Everything else is exact.
  - New item 15 is the numeric text rule. New item 16 covers money and shares: `Decimal(repr(x))`, `localcontext(prec=50, rounding=ROUND_HALF_EVEN)`, one `ROUND_HALF_UP` quantize per money output, and `Fraction` for largest-remainder shares.
  - I settled 11 rows. Reasons became three ordered enums.
  - Amortization now defines early payoff, and `total_paid` is the sum of the schedule.
- **R-2, growth:**
  - INV-20 now lists 14 tools that amplify their input, all capped at `PREBUILT_MAX_TEXT_CHARS`. I found the extra cases by reading each row for repetition:
    - `[DEFAULT]` copied into every INI section (fixed by changing the output shape)
    - header names repeated in every CSV record
    - `colspan`
    - qualified names in `list_python_*`
    - XML namespace URIs (also capped at 200 characters before parsing)
    - indentation in `format_json`
    - groups in `regex_match`
  - INV-17 adds a character budget for every enumerating output, and `cap_items` now consumes a lazy iterable.
- **R-3:** every raise inside `except` uses `from exc`, following the S002 repair text. Security guards carry `# @intent` blocks.
- **R-4, measured locally on Python 3.11.0:**

  | Case | Time | Change |
  |---|---|---|
  | `closest_string_matches`, 1,000 × 200 characters | 2.43 s | candidate cap 200 → 100 (0.59 s) |
  | unified diff, 10,000 lines | 4.63 s | cap 10,000 → 4,000 lines |
  | unified diff, 5,000 lines | 0.88 s | — |
  | levenshtein, 1,000 × 1,000 | 0.14 s | — |
  | sieve to 10^7 | 0.20 s | — |
  | tomllib, 1M characters | ≤ 0.53 s | — |
  | HTMLParser, 1M characters | ≤ 0.86 s | — |

  I also applied the reviewer's caps:
  - sequence matching and diff tokens: 2,000
  - modular operands: 2,001 characters
  - CSV sniffing: 10,000 characters
  - `split_text_into_chunks`: `chunk_size ≥ 100` and `overlap ≤ chunk_size // 4`, so counting every chunk stays linear
- **R-5:** the nesting cap now applies to converted XML, TOML, and Python-literal output, and depth is measured with a work stack.
- **R-6:** D-7 is kept and is now argued on principle 4's purpose. I verified that `_build_args_model` turns each signature parameter into a schema field, so a single dataclass parameter would wrap the schema. The category classes are now internal (FR-5). The flip condition and the residual owner risk are stated in D-7 and Q-6.
- **R-7:** `categories: Iterable[PrebuiltToolCategory] | PrebuiltToolCategory`. Plain strings are rejected. New enums `IpVersion` and `WeekdayOccurrence`.
- **R-8:** helpers may call the leaves `argument_error` and `nesting_level`.
- **R-9:** D-18 allows up to 12 conditional `_<category>_<part>.py` split modules outside the BLOCKED rule. Row 7 is reused as CREATE-IF-NEEDED.
- **R-10:**
  - The calculator description is corrected.
  - I dropped 12 weak or near-duplicate tools: is_leap_year, days_in_month, collapse_whitespace, html_escape, both Roman numeral tools, sort_list, deduplicate_list, similarity_ratio, jaro_winkler_similarity, verify_json_against_schema (with `_json_schema.py`), and semver_satisfies_range.
  - I kept `generate_seeded_uuid4`, because seeded_random needs 6 tools.
- **R-11:** AC-2 now checks that every Appendix A name is present, AC-9 expects one declaration per tool, and INV-6 covers constructions only.
- **R-12:** §11 lists only the two split gate stages.

**Counts in r2:**
- 265 tools in 31 categories, 6 to 12 each
- 68 enums (58 + 10)
- 101 classes
- 39 planned files plus 0 to 12 conditional split modules
- FR 11, NFR 11, AC 21, INV 26, EC 44, D 18, T 6, W 38
- 0 blocking questions

**Sections that changed shape and need the scoped second review:**
- §8: D-2, D-7, D-9, D-12, D-16, the new D-18, §8.4, and §8.5
- §9.2: items 5, 12, 15, and 16, the enum table, and the caps table
- §10: T-1 and T-2
- §12: row 6 helpers, row 7 conditional, the budget, the §12.4 group C items, and §12.6 order
- Appendix A rows for finance, CSV, XML, INI, URL, email, IP, and chunking

**Least sure in r2:**
- The INV-20 cap equals the 1M text cap, so a CSV or XML near 1M characters can now fail with an error. I chose this for composability: such an output could not be passed to another tool anyway.
- The 10^47 money ceiling for `compound_interest_future_value` is a consequence of the 50-digit precision, not a business limit.

## Addendum — r3 (S1 round-2 review applied; status approved)

This was the final revision, with no third review round. I accepted all ten round-2 findings (R-13 to R-22) and disputed none, so no new Q-n was needed. The one judgment call that goes to the owner is Q-6, which now states D-7 honestly. Spec commit: `3ee4bbfd`.

**How each finding was closed:**
- **R-13:** New §9.2 item 17 sets the rule for rounding a float into exact output. Convert with `Decimal(repr(x))`, scale exactly in `Decimal`, `quantize` once in the row's mode, and round the whole value before splitting it into parts. The rule covers these rows:
  - `format_duration` rounds to milliseconds, so 59.9996 s is `1m`.
  - `parse_duration_text` sums its parts exactly in `Decimal`. Its `iso8601` is `format_duration` of the resulting float.
  - `decimal_degrees_to_dms` rounds the total arc-seconds, writes a fixed number of digits, and uses the sign rule for the hemisphere.
  - `unix_timestamp_to_datetime` uses `timedelta(microseconds=...)`.
  - I checked the three worked examples (0.012 s, 3.2″, 60.000 s) in Python.
- **R-14:** §9.2 item 16 now pins the evaluation order of money math.
  - Rational money steps are computed exactly in `Fraction`: period interest, the level payment, the net of tax, and shares.
  - A `Fraction` becomes money by a written half-up formula. I checked the reviewer's 1740.00 at 6.1% case: it gives 8.85.
  - Only `compound_interest_future_value` uses the 50-digit context, with the operation order written out.
  - 10^47 is now described as an overflow guard, not a cents claim.
- **R-15:** The IRR row now states the NPV formula, the skip rule, a single ordered scan, the bisection step, and that it returns the midpoint. `irr_percent` has its own 1e-9 absolute precision, which item 5 names. I kept the 600-flow cap. My probe: 600 flows solve in 0.015 s with 30 grid points skipped, and [-100, 100.01] gives 0.00999999998.
- **R-16:**
  - `ini_to_json`: `sections` never holds `DEFAULT`. I did not add "file order", because `_stringify_output` sorts keys.
  - `format_number_with_separators`: the row now fixes the input form, leading zeros, the sign of zero, exact places (added to item 5's list), and the separator characters, which `parse_formatted_number` shares.
  - `parse_data_size`: the item 15 number form, with an exact factor product.
  - `profile_csv_columns`: among equal values, the first in row order.
- **R-17 / R-6 (decided):** I kept dict outputs. D-7 is rewritten as a deliberate exception to the letter of AGENTS.md principle 4. It no longer claims a carve-out; the principle's only exemption is for small private helpers. NG-13, A-7, FR-5 ("internal" is documentation only), and §11 now match. Q-6 asks the owner, default no (keep dicts). Switching would cost about 265 single-use dataclasses, and an input dataclass would nest the model-facing schema.
- **R-18:** INV-20 now opens with "These tools", and new EC-45 accepts bounded expansion of up to about 23×. INV-12 and NFR-10 no longer promise cross-OS byte identity for floats that come from the platform C math library; those agree within item 5.
- **R-19:** I took option (b). §12.4 B covers parameters and the vocabularies a tool chooses from. Recognition tables and display-label tables stay reference tables (new `PREBUILT_SIZE_UNIT_LABELS`), so the count stays at 68 enums.
  - Five constants are now named: `PREBUILT_APPROXIMATION_DIGITS`, `PREBUILT_MAX_REPORTED_NAMES`, `PREBUILT_PROFILE_EXAMPLES`, `PREBUILT_MAX_KEY_CHARS`, and `PREBUILT_MAX_MOJIBAKE_ROUNDS`.
  - `fraction_to_decimal` cites `PREBUILT_MAX_DECIMAL_PLACES`.
  - FR-8 lists the SMS and email limits as fixed by their standards.
- **R-20:** §14 now says to run the pack after P3 and after each later change.
- **R-21:** Row 40 and §12.4 E say to backtick only the folder's direct children inside `## File Index`.
- **R-22:** Row 6 adds `paired_values` and `weight_total`. §12.4 C requires them in place of inline checks.

**Counts in r3:** 265 tools in 31 categories (6 to 12 each), 68 enums, 101 classes, and 39 planned files plus 0 to 12 conditional split modules. FR 11, NFR 11, AC 21, INV 26, EC 45, D 18, T 6, W 38. 0 blocking questions.

**Stage E self-check (r3):**
- Traceability script: all IDs defined. The only flags are G-1 to G-4, which are defined in the §1 table; the script misses them.
- Table pipes: 0 problems.
- 18 `## §` headings.
- Appendix: 265 rows in 31 tables, every category between 6 and 12.
- Enum table: 68 rows.
- No "carve-out" claim remains outside the §16 log.
- spec.md is LF.

**Least sure in r3:**
- The 1e-9 IRR tolerance is a stated contract. A badly conditioned series (very flat NPV near the root) could still miss it, because NPV is evaluated in floats.
- EC-45 accepts outputs up to about 23 million characters from a capped input. The runtime's result truncation is the only control on them.

## Addendum — r4 (S2-found spec defects resolved; status approved)

r4 fixes the defects the S2 test author found, and writes the readings the tests pinned into the rows they belong to. Spec commit: `5d93fe88`. The tests are part of the contract now, so before writing each row I checked it against the exact assertions. Five read-only helpers mapped every item in S2 report §5 to its `file:line` assertion and its current spec text. No pinned reading contradicts §9.2, an INV-, another row, or the request, so there are no "test disagrees with spec" items.

**Defects (§16 S2-1 to S2-10):**
- **S2-1:** EC-14 now describes characters the chosen encoding cannot represent. It also says a lone surrogate fails pydantic validation before any tool runs. `unicode_character_info.utf8_hex` is now `str` instead of `str?`; the key set is unchanged, and no test checks whether it can be null. The `count_bytes_in_encoding` surrogate clause is removed.
- **S2-2:** The missing caps are now stated:
  - `add_business_days.holidays` is capped at `PREBUILT_MAX_HOLIDAYS`, and `weekend_days` at 7. Both match the sibling `business_days_between`, where the tests pin 1,000 and 7. FR-8 keeps an enum-sized bound as a literal, so `weekend_days` gets the literal 7 rather than a new constant.
  - The two `critical_path_schedule` dependency lists are capped at `PREBUILT_MAX_GRAPH_EDGES`.
- **S2-3:** `UtcOffset` gets `max_length=PREBUILT_MAX_UTC_OFFSET_CHARS` (6). The tests accept it, and they keep checking the exact pattern string.
- **S2-4:** `verify_email_syntax` now checks `domain_too_long` immediately before `address_too_long`. The enum's declaration order is unchanged, because the tests pin it. The test with a 253-character domain still gets `address_too_long`.
- **S2-5:** The `DigestFormat` rule is now in the §9.2 enum table and applies to all three users: lowercase hex, padded `base64`, unpadded `base64url`.
- **S2-6:** In `xml_find_elements`, any `SyntaxError`, `TypeError`, or `KeyError` from `findall` becomes error(`path`), and a parse error becomes error(`xml_text`). I probed this on 3.11: `[` raises `TypeError`, `/b` raises `SyntaxError`, and `@` raises `KeyError`.
- **S2-7:** The A.30 rule rejects a null character before `ast.parse`, so the result no longer depends on the Python version. `verify_python_syntax` returns `valid: false` with null line and column.
- **S2-8:** EC-26 and `classify_ip_address` now say which parts of an IPv4-mapped result depend on the Python version.
- **S2-9:** Each of the three error rows now names its parameter: `fiscal_quarter` → `target_date`, the shift amount → `right`, and seven weekend days → `weekend_days`.
- **S2-10:** The `list_combinations` count is computed with `math.comb` arithmetic.

**Loose rows (S2-11).** Each reading the tests pinned is now in its row. Where a test leaves a value open with `ANY`, I picked one value that test accepts, and S2 may tighten the test later:
- **Picked values:**
  - a Setext heading's `line` is the text line, not the underline
  - an autolink's `text` is its URL
  - fenced blocks use the fence lines as their line numbers
  - `list_python_imports` gives `module: null` for a plain `import`
  - `find_python_name_usages` columns point at the name itself
  - `sms_segment_count` reports 160 units per segment for empty text
  - `verify_json_syntax` and `verify_xml_wellformed` give null positions for their fixed-message cases
  - `profile_csv_columns` counts distinct values by text
  - `format_duration` `long` also leaves out zero parts
- **New §9.2 rules:** the `code_point` form (item 6), the `time` form (item 11), and the negative-money form (item 16).
- **`strip_html_tags`:** the row now lists what `PREBUILT_HTML_BLOCK_TAGS` contains.
- **`remove_diacritics`:** marks are now dropped only after Latin letters. The old row said "non-Latin scripts are left as they are" but its NFD rule changed Greek and Devanagari text; the new rule keeps the old intent. The tests cover only Latin and CJK, so both readings pass them.
- **Two rows that differ on purpose:** `join_records` keeps the right join field and `csv_join_tables` drops it. Each row says so, and the tests pin both.

**Unchanged:** no tool, parameter, return key, default, or test-pinned cap changed. I checked this by diffing every Appendix A parameter and return cell between r3 and r4. The only differences are the four new list caps and the `utf8_hex` type. The §6.2 Proof column is byte-identical to what S2 wrote.

**Stage E self-check (r4):**
- Traceability script: all IDs defined. The only flags are G-1 to G-4, which are defined in the §1 table; the script misses them.
- Table pipes: 0 problems.
- 18 `## §` headings.
- Appendix: 265 rows in 31 tables, every category between 6 and 12.
- Enum table: 68 rows.
- spec.md is LF.

## Addendum — r5 (S3-found NFR-7 gap resolved; status tests-written)

r5 settles the gaps the S3 implementer measured. Spec commit: `ce32c0a6`. The tests do not time any call, since `test_prebuilt_resource_bounds.py` forbids timing assertions. They do pin these caps:
- `diff_words`: 2,000 tokens is accepted and 2,002 is rejected.
- `closest_string_matches`: 1,000 candidates of 100 characters each.
- `unified_diff_text`: 4,000 lines.
- `seeded_weighted_choice`: the key set `picks`.

So r5 changes none of these values.

**S3-1 (NFR-7).**
- **Measurements.** I re-measured on the dev machine (Python 3.11.0) with plain `difflib`, shaped like the rows. S3's numbers held:
  - `diff_words` at 2,000 tokens: 14.4 s and 21.4 s. Time grows about 8× per doubling: 0.23 s at 500 tokens, 1.8 s at 1,000.
  - `closest_string_matches` at 1,000 candidates: 3.1 s.
  - Casefolded ligatures: 8.5 s at 100 candidates, about 85 s at 1,000.
- **A third slow tool.** `unified_diff_text` also misses NFR-7. With 4,000 lines that cycle through 98 short lines, against a version where every second line is unique, it takes 4.2 s. Each repeated line stays within the junk heuristic's popularity limit, so `difflib` keeps it in the matching.
- **Not slow.** `longest_common_substring` stays within NFR-7. It makes one `find_longest_match` call, which is worst on a single repeated character: 0.25 s at its cap.
- **Decision.** New EC-46 makes this a documented limitation, like EC-10. The call always finishes because the caps bound the work. `tool_timeout_seconds` bounds how long the agent waits (A-4, EC-28). NFR-7 now names the two accepted cases and no longer claims S1's unified-diff pattern was the worst. A-9, T-2, §12.3 rows 23 and 40, and the three A.16 rows cite EC-46.
- **Rejected options:**
  - **Lower caps.** These are pinned by tests. `diff_words` would need roughly 800 tokens to meet 2 s on a CI runner 2× slower than the dev machine.
  - **Fold per code point.** This breaks the §9.2 item 7 case rule, and it still leaves 3–5 s.

**S3-2 (`seeded_weighted_choice`).** INV-17 applies only to rows with a `truncated` key, and INV-20 is a closed list, so neither covered this tool. Adding `truncated` would change the pinned key set. I recorded the bound instead, in EC-45 and the row:
- The output is at most `PREBUILT_MAX_RANDOM_PICKS` × `PREBUILT_MAX_SHORT_TEXT_CHARS` = 10,000,000 characters.
- That is a tenth of the tool's capped input, and less than `seeded_shuffle_list` may already return.

**S3-3 (`intersect_lists`).** I logged it as a test defect, as the orchestrator ruled. The spec row stands, and the S2 test author fixes `prebuilt_parameter_data.py:257`.

**What must change outside the spec:**
- **Code:**
  - No tool code changes.
  - The folder README (§12.3 row 40, `vidbyte/tools/builtins/prebuilt/README.md`) must add a short EC-46 paragraph next to the EC-10 one.
- **Tests:**
  - No test must change for r5.
  - The `intersect_lists` parameter data is already routed to S2 (S3-3).

**Unchanged:** no tool, parameter, return key, default, or cap changed. `diff_contract.py` found no parameter or return cell that differs between r4 and r5. The §6.2 table is byte-identical to r4.

**Stage E self-check (r5):**
- ID counts: FR 11, NFR 11, AC 21, INV 26, EC 46, W 38, T 6, D 18.
- Every ID is defined. G-1 to G-4 show up as false positives of the script, as before.
- Table problems: 0.
- 18 `## §` headings.
- Appendix: 265 rows in 31 tables, with 0 bad rows.
- spec.md is LF.
