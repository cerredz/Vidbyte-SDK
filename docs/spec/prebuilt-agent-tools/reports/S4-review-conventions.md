LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — The layout, placement, headers, lint, and toolset shape follow the repo. But the PR writes about ten shared rules two to six times across the category modules. That breaks AGENTS.md principle 5, and the PR's own README says the opposite. Fixing it is mechanical: move each rule into `PrebuiltToolSupport` or `lib/constants`.

Review target: `git diff origin/main...0fd73086` (merge base `8387d666`). Worktree HEAD `9d8eb2f7` adds only docs on top of it. Severity calibration: the rubric treats any contradiction of AGENTS.md or the field guide as a Blocker. I applied that literally to R-V1, which is pervasive and contradicted by the PR's own docs. R-V3 and R-V4 are single-instance or tiny-scope contradictions, so I rated them Major and say why in each. The verifier may raise them.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **Placement and layering are exact.**
  - All 68 enums are `(str, Enum)`: 58 in `vidbyte/lib/enums/prebuilt_tools.py` and 10 in `units.py`. All are exported and alphabetized in `vidbyte/lib/enums/__init__.py`.
  - Caps and tables live in `vidbyte/lib/constants/`, and the lib modules import only `vidbyte.lib.enums`.
  - The PR adds no dataclass, `NamedTuple`, or `TypedDict`.
  - `PrebuiltTools(Tools)` copies the `CodingAgentTools` shape: a narrated `__init__` calls `select_categories` and then `get_tools` as sibling steps, which matches field guide `prebuilt-agents.md`.
- **Call depth is honored almost everywhere.** An AST scan of all 34 classes found exactly one two-hop chain inside a class (R-V3).
  - There are no nested `def`s.
  - The three nested classes (`_HtmlTextCollector`, `_TableParser`/`_LinkParser`, `_CaseKeepingConfigParser`) each subclass a stdlib API in order to override a hook.
  - The `ConfigParser` subclass is acceptable: overriding `optionxform` is the documented hook, and a class-level override avoids assigning to a method on an instance.
- **Headers, narration, and comments are high quality.**
  - All 34 new `.py` headers name their own path.
  - 33 of 34 FUNCTION INVENTORY fields match the class members exactly.
  - Every tool over about 15 lines carries step comments.
  - The 72-column awk check prints nothing, and `# @intent` sits on its own first line at every security guard I sampled: XML declarations, namespace URIs, nesting caps, digit caps, output caps, and `cap_items`.
- **Gates and hygiene are clean.**
  - `SDK-LINT` exits 0. No rule is REGRESSED, and the IMPROVED set is identical to the §11 base set.
  - Ruff I001 reports 0 issues on PR paths, and semgrep reports `0 findings`.
  - All 4,310 pack tests pass, and all 265 tool descriptions and every parameter description have 4–5 sentences by `SentenceCounter`.
  - There is one feature commit per category with W-/FR-/AC- IDs, and the three lint-fix commits each touch one file.
  - No cache, `dist/`, or scratch files are committed. `docs/spec/<slug>/reports` already has precedent on main in `docs/spec/coding-agent/`.

FINDINGS (ranked, most severe first, max 15)

R-V1 [Blocker] [AGENTS.md principle 5 / PR's own support-class rule] vidbyte/tools/builtins/prebuilt/encoding.py:218 — Shared rules are copied across category modules instead of written once in `PrebuiltToolSupport`
  Evidence (each rule is defined two or more times):
  - **Tolerant Base64 reader.** `encoding.py:218-236 _base64_bytes` and `hashing.py:193-205 _base64_bytes`, plus five identical module constants (`_BASE64_GROUP`, `_URL_SAFE_ALTCHARS`, `_STANDARD_BASE64`, `_URL_SAFE_BASE64`, `_URL_SAFE_MARKS`) at `encoding.py:43-47` and `hashing.py:47-51`. The hashing header (`hashing.py:9`) says the reader "follows the base64_decode rules", a coupling held only by copy-paste.
  - **`SortMode` semantics.** The natural key appears at `csv_tables.py:435-439` and `text_transform.py:397-399`, numeric ordering at `csv_tables.py:444-449` and `text_transform.py:402-412`, and the run regex at `csv_tables.py:62` and `text_transform.py:46`. The two natural keys already differ in tuple shape: `(_TEXT_RUN_RANK, run.casefold())` versus `(1, 0, run.casefold())`.
  - **`CsvDelimiter` to character table, three times:**
    - `_support.py:60`, a **mutable** `dict`;
    - `csv_tables.py:53`, a `MappingProxyType`;
    - `json_records.py:76`, a `MappingProxyType`.
  - **CSV writer setup, twice.** `csv.writer(buffer, delimiter=..., quoting=csv.QUOTE_MINIMAL, lineterminator="\n")` appears at `csv_tables.py:325` and `json_records.py:247`.
  - **`JsonType` classification table, twice.** `json_data.py:47` and `json_records.py:50`.
  - **The INV-18 bound, rebuilt in five modules beside `PrebuiltToolSupport.integer_text`.** `_INTEGER_RESULT_BOUND = 10**PREBUILT_MAX_INTEGER_DIGITS` appears at:
    - `code_analysis.py:56`
    - `exact_arithmetic.py:68`
    - `number_formatting.py:61`
    - `number_theory.py:40`
    - `structured_formats.py:55`
  - **§9.2 shorthand patterns, redeclared per module.**
    - IntText: `bits_bytes.py:48`, `exact_arithmetic.py:72`, `number_formatting.py:75`, `number_theory.py:39`.
    - DecText: `exact_arithmetic.py:70`, `finance.py:57`, `number_formatting.py:74`.
    - UtcOffset: `scheduling.py:51`, `timestamps_durations.py:41`.
  - **Line and column rule, re-implemented as a variant.** `unicode.py:57` redefines `_LINE_BREAK`, and `unicode.py:349-366` re-implements line and column counting beside `_support.py:332 line_and_column`.
  - **Smaller copies:**
    - weekday numbering at `dates.py:44` and `scheduling.py:54`;
    - the Unix epoch at `encoding.py:60` and `timestamps_durations.py:39`;
    - `_EXACT_PRECISION` at `exact_arithmetic.py:66` and `number_formatting.py:59`;
    - script/style tags at `markdown_html.py:59` and `text_transform.py:48`;
    - seconds per duration unit in both `PREBUILT_DURATION_UNIT_WORDS` (`constants/prebuilt_tools.py:221`) and `DURATION_UNIT_FACTORS` (`constants/units.py:106`).
  - **The PR's own documents claim the opposite:**
    - `README.md:67`: "Open it before writing any parsing or rule that a second category could need, because each rule exists exactly once."
    - `_support.py:7`: "Add a helper here only when two or more category modules need the same job."
    - `text_comparison.py:8`: "Do not split lines or words with a local rule; use PrebuiltToolSupport so every category agrees."
  - Spec §17 item 5 records the Base64 copy and says it "could move to `_support.py` in a later change".
  Failure: AGENTS.md principle 5 says to write logic once, and if a helper is close, to "add the option you need to it rather than copying it into a variant beside your feature".
  - `unicode.py` is literally that variant.
  - D-14 made `PrebuiltToolSupport` the feature's canonical owner of every rule two categories share. Spec §12.4 C applies the same idea to pairing and weights.
  - Already-visible drift: one delimiter table is mutable while its copies are frozen, and the natural keys have different shapes. A later fix to one copy, such as Base64 padding, `SortMode.NATURAL` ties, or the INV-18 message, silently misses the other.
  - A human reviewer would write: "Why are there two Base64 readers and three delimiter tables? Put them in `_support` as your own README says."
  Smallest fix:
  - Add these to `PrebuiltToolSupport` and have every caller use them. Each is one call from a tool into another class, so principle 1 holds:
    - one Base64 reader, with a flag or two thin entry points for "raise naming p" versus "return None";
    - `sort_key(text, mode)` and `numeric_order(items, key, descending)`;
    - `CSV_DELIMITER_CHARACTERS` as a `MappingProxyType`, plus one `write_csv(rows, header, delimiter)`;
    - `json_type(value)`;
    - a streaming option on `line_and_column`, or a `line_columns(text, positions)` variant in the same class.
  - Replace the five per-module INV-18 checks with `integer_text` or one shared bound check, keeping the C006/C008-safe name.
  - Define the IntText, DecText, FractionText, and UtcOffset patterns once, as `PREBUILT_*_PATTERN` in `lib/constants` or as `Annotated` aliases in `_support.py`.
  - Make `_support._DELIMITER_CHARACTERS` immutable.
  Spec IDs: D-14, FR-8, §12.4 C ("Neither check is written inline"), NFR-2/G-4 ("simple"). Deviation §17 #5 was recorded but never resolved.

R-V2 [Major] [FR-8 / field guide strict-config-dataclasses.md / principle 5] vidbyte/tools/builtins/prebuilt/csv_tables.py:58 — The INV-15 echo bound is hand-rolled five times with private, disagreeing literals, and messages carry 800–1,200 characters of argument text
  Evidence:
  - **The named constant exists but two modules ignore it.** `PREBUILT_MAX_REPORTED_NAMES = 20` (`constants/prebuilt_tools.py:102`) is used only by `code_analysis.py:235` and `text_transform.py:354`. These modules use private copies instead:
    - `csv_tables.py:58 _REPORTED_COLUMNS = 20`;
    - `graphs.py:37 _SHOWN_CYCLE_NAMES = 20`.
  - **Per-name length bounds are private literals that differ:**
    - `code_analysis.py:57 _REPORTED_NAME_CHARS = 60`;
    - `text_transform.py:52 _REPORTED_NAME_LENGTH = 60`;
    - `csv_tables.py:59 _REPORTED_NAME_LENGTH = 40`;
    - `graphs.py:38 _SHOWN_NAME_LENGTH = 40`;
    - `number_formatting.py:73 _REPORTED_WORD_LENGTH = 40`;
    - `regex.py:43 _MESSAGE_PREVIEW_LENGTH = 80`.
  - **The shortening code itself is copied** at `code_analysis.py:235`, `csv_tables.py:317`, `graphs.py:269`, and `text_transform.py:354`.
  - **Run result:**
    - `fill_text_template` with 25 missing 74-character placeholders gives `error ToolExecutionError message chars: 1417`, of which 1,200 characters are text of `template`.
    - `topological_sort` on a 25-node cycle gives `message chars: 1038`.
    - `csv_filter_rows` with an unknown column over a 30-column header gives `message chars: 988`.
  Failure: FR-8 requires every size limit to be a named constant in `vidbyte/lib/constants/prebuilt_tools.py`. The strict-config check reads: "each validation comparison should reference the feature's constants module."
  - INV-15 says a message "never repeats more than 100 characters of an argument value".
  - S3's §17 item 6 claims these shortenings make it so that "no message repeats more than 100 characters of input". Under the plain reading, the run above shows up to 1,200.
  - The pack (`test_prebuilt_error_contract.py:9`) checks only contiguous 101-character windows, which the ", "-joined lists never form. So the gate is green while the stated rule and the stated claim do not hold.
  Smallest fix:
  - Add one `PrebuiltToolSupport` helper that writes a shortened name list, plus `PREBUILT_MAX_REPORTED_NAME_CHARS` in lib constants. Route all five sites through them, and delete the private literals.
  - Have the spec owner say whether INV-15 means per message (total) or per contiguous span. If per message, size count × length to stay at or under 100.
  Spec IDs: FR-8, INV-15, §17 deviation 6.

R-V3 [Major] [AGENTS.md principle 1 / spec §12.3 row 6] vidbyte/tools/builtins/prebuilt/_support.py:125 — `parse_records_json` calls `parse_json_text`, which calls further helpers, and three documents say no such chain exists
  Evidence:
  - `_support.py:125` reads `value = PrebuiltToolSupport.parse_json_text(text, parameter_name)`.
  - `parse_json_text` then calls `nesting_level` (`:100`) and the hooks `_reject_json_constant` and `_read_json_float` (`:82-83`), and those hooks call `argument_error`.
  - The AST scan output is: `_support.py:123 PrebuiltToolSupport.parse_records_json -> parse_json_text -> ['_read_json_float', '_reject_json_constant']`. That is the only such chain among the 34 classes.
  - **Contradicting claims:**
    - README `:67` says: "Its helpers call nothing else in the class except the error builder and the nesting measure."
    - Spec §17 deviation 2 says: "no helper calls another helper directly."
    - Row 6 says: "no other helper calls another helper, and each caller composes them."
    - The `_support.py:5` header admits the chain ("parse_records_json also reuses parse_json_text"), so the header and the README disagree with each other.
  Failure: AGENTS.md principle 1 says a helper may call another, "but that second function should not call a third". Rated Major rather than Blocker because it is one hop in one helper with no behavior impact. The README and §17 statements are false, though, and the next agent will trust them.
  Smallest fix:
  - Change the helper to `records_from_json(value, parameter_name)`, taking the already-parsed value. The `json_records`, `csv`, and `records_to_csv` callers call `parse_json_text` first.
  - Alternatively, keep the code and correct README `:67` and row 6/§17 to name the exception. Either fix makes the code and the docs agree.
  Spec IDs: §12.3 row 6, §17 deviation 2, FR-10 (README accuracy).

R-V4 [Major] [field guide model-facing-tool-contracts.md] vidbyte/tools/builtins/prebuilt/json_data.py:181 — Three model-facing descriptions carry concrete example values
  Evidence, from the built specs:
  - `diff_json_documents` (`json_data.py:181`): "...equality is type-aware, so true never equals 1 while 1 equals 1.0."
  - `group_records_by_field` (`json_records.py:113`): "...so the number 1 and the string 1 form separate groups while 1 and 1.0 form one..."
  - `join_records.left_field` (`json_records.py:200`): "...so the number 1 does not match the string 1."
  - The pack's detector, `EXAMPLE_MARKERS = r"\bfor example\b|\bfor instance\b|\be\.g\.|\b\d{4}-\d{2}-\d{2}\b"` (`test_prebuilt_model_facing_contract.py:28`), cannot see "so X while Y" examples.
  Failure: The field guide says "omit concrete examples from model-facing prose", and the owner flagged exactly this on PR #337 and #342. INV-9 says the same. Rated Major because it is 3 sentences out of about 1,000 descriptions. The rubric would allow Blocker.
  Smallest fix: Restate each sentence generally, for example "equality is type-aware: a boolean never equals a number, and integers equal floats of the same value". That keeps 4–5 sentences.
  Spec IDs: INV-9, AC-8, G-4.

R-V5 [Minor] [house style "names that say what things mean"; §14 lint-rule ask-first] vidbyte/tools/builtins/prebuilt/finance.py:334 — The C005 rename calls a monthly *rate* `monthly_interest`, beside a local named `interest` that holds cents
  Evidence:
  - `finance.py:111` reads `monthly_interest = Fraction(repr(annual_rate_percent)) / _MONTHLY_RATE_DIVISOR`.
  - `:320` is `def _level_payment(principal_cents, monthly_interest, ...)`.
  - `:334` reads `interest = math.floor(balance * monthly_interest + _HALF)`.
  - The rename is lint-driven, not meaning-driven:
    - `rate` survives wherever it is not a multiplication operand: `_MONTHLY_RATE_DIVISOR` (`:61`), `_npv_at(cash_flows, rate)` (`:357`), and `_bisect_root`'s "two rates";
    - `yearly` (`:299`) is an adjective standing in for a noun.
  - C005 (`lint/rules/c005_cost_arithmetic_site_parity.py`) targets token-pricing arithmetic, so firing on a loan formula is a false positive.
  Failure: In money code, `interest = balance * monthly_interest` reads as interest times interest. A reviewer would ask for an honest name. §14 lists "a lint rule fires on a pattern the spec requires" as ask-first, and the deviation is at least recorded (§17 #1).
  Smallest fix: Rename to `monthly_interest_fraction` and `yearly_interest_fraction`. Neither contains `rate` or `price`, so C005 stays clean.
  Spec IDs: n/a (NFR-3 spirit); §17 deviation 1.

R-V6 [Minor] [AGENTS.md "Repository Map … regenerate a wrong entry from the tree"; field guide agents-md-map.md] REPO_MAP.md:337 — The regenerated toolsets entry drops the paradigm bundle that is still in the tree
  Evidence:
  - The old text said "It currently holds one such bundle, assembled for a specific paradigm".
  - The new text says "One kind of bundle equips a specific agent … Another kind builds a bundle from the categories of utility tools".
  - `vidbyte/tools/toolsets/` holds `coding.py`, `paradigm_minimal.py` (`class ParadigmMinimalToolset … for paradigm harness agents`), and `prebuilt.py`.
  Failure: The entry was regenerated, but it still disagrees with the tree: it describes two kinds of bundle where three exist. Spec row 44's wording ("bundles for agents plus category-selected utility bundles") inherited the gap, and AGENTS.md wins.
  Smallest fix: Make it "One kind … equips a specific agent or paradigm harness with the tools it starts with". Keep 4–5 sentences and no file names.
  Spec IDs: FR-10, §12.3 row 44.

R-V7 [Minor] [A001 header accuracy; folder_readme.md "verify nothing … contradicts the code you shipped"] vidbyte/tools/builtins/prebuilt/README.md:36 — The README gets the digit cap wrong by one, and the `_support` inventory omits two members
  Evidence:
  - README `:36` says "Integer results of 4,000 or more digits are refused."
  - A run of `least_common_multiple` gives:
    - `4000 digits -> success 4000`;
    - `4001 digits -> error Invalid value for 'values': the running result passes 4000 digits`.
  - The code is `_support.py:174` `abs(value) >= 10**4000`, and INV-18 says "more than 4,000 digits".
  - The FUNCTION INVENTORY at `_support.py:6` does not list `_reject_json_constant` or `_read_json_float` (`:106`, `:113`). All 33 other headers list every member.
  Failure: Docs promise behavior the code does not have. The README is the routing artifact the next agent reads first.
  Smallest fix: Change README `:36` to "more than 4,000 digits", and add the two hooks to the `_support.py:6` inventory.
  Spec IDs: INV-18, FR-10, §12.4 A.

VERIFIED CLAIMS:
- **Held:**
  - S3: largest module is `json_data.py` at 582 lines, and no D-18 split exists. All new modules are 92–582 lines.
  - S3: README is 22,371 characters, and S020 and A009 pass. Measured 22,371; the tools README is 8,388. Lint shows S020 RATCHETED at baseline 1 with no PR path and A009 CLEAN.
  - S3: no comment line is wider than 72 columns. The awk check over all 38 new `.py` files printed nothing.
  - S3: md5 and sha1 use `usedforsecurity=False`. Every `hashlib.new` in `hashing.py` passes it, including the HMAC partial at `:118`.
  - S3: the listed files are byte-identical to main. `git diff --stat origin/main 0fd73086 -- vidbyte/__init__.py vidbyte/tools/builtins/__init__.py contracts/sdk-public-api.json pyproject.toml lint scripts .semgrep .github function_tool.py catalog.py llms.txt artifacts` printed nothing.
  - S3: every new `.py` starts with `from __future__ import annotations`.
  - S3: `SDK-LINT: PASS`, nothing REGRESSED, and the IMPROVED set equals the base. The JSON shows exit 0 and verdicts CLEAN 47, RATCHETED 35, IMPROVED 8. The IMPROVED counts are A002 579, C011 1, C012 23, S001 56, S010 0, S017 78, S025 261, and S061 5, identical to §11.
  - Semgrep: `Ran 1 rule on 931 files: 0 findings.`
  - Pack: `4310 passed in 21.52s`.
  - Spec row 3: 68 enums are exported and alphabetized. Row 39: `__all__` has 31 names, sorted.
  - INV-9 depth: 0 sentence-count violations across 265 tool and all parameter descriptions.
  - Every description that states a numeric cap matches the schema `maxLength`/`maxItems`. No parameter shadows a builtin or a `BaseModel` attribute.
  - No if/elif ladder of three or more cases on one value.
  - S3: no function name has a C006 or C008 prefix; lint C006 and C008 do not flag PR paths.
- **Failed:**
  - S3 §17 #2, "no helper calls another helper directly" (R-V3).
  - S3 §17 #6, "no message repeats more than 100 characters of input" (R-V2; it holds only under the pack's contiguous-window reading).
  - README `:67`, "each rule exists exactly once" (R-V1).
  - README `:36`, the digit cap (R-V7).
  - INV-9 "no example" (R-V4).
- **Partially held:** S3 §6, "every new .py file has the A001 header". It holds for new files. The modified `vidbyte/tools/toolsets/__init__.py` is still in the A001 baseline because it is missing ROLE IN CODEBASE and five other fields. I raised no finding: row 42 and `review-scope.md` restrict that edit to one line.

COMMANDS RUN:
- `PYTHONPATH=$(pwd) python lint/run.py --format json`, with output captured to the session scratchpad, not the worktree. Result: `exit 0`. PR-path findings: only the pre-existing A001 entry on `vidbyte/tools/toolsets/__init__.py`.
- `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache --output-format concise | grep <PR paths>`: no lines; the tree total is `Found 223 errors.`, all pre-existing.
- `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (scratchpad venv): `Ran 1 rule on 931 files: 0 findings.`
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/prebuilt_tools -x`: `4310 passed in 21.52s`.
- An AST scan for same-class two-hop call chains printed one line: `_support.py:123 PrebuiltToolSupport.parse_records_json -> parse_json_text -> [...]`.
- AST scans for nested defs, ladders, header inventories, and narration:
  - nested defs: none; nested classes: 4, all stdlib-subclass hooks;
  - ladders: none;
  - inventories: only `_support.py` is missing `_reject_json_constant` and `_read_json_float`;
  - narration: 0 tools over 15 lines without step comments.
- Module-constant duplicate scan (`grep -nF` per pattern) produced the R-V1 and R-V2 line lists.
- A catalogue introspection over `SentenceCounter`, caps, and example scans gives:
  - `sentence-count violations 0`;
  - 3 example sentences (R-V4).
- Echo probes through `tool.execute` (R-V2): `fill_text_template … message chars: 1417`, `topological_sort … 1038`, `csv_filter_rows … 988`.
- Digit-cap probe (R-V7): `4000 digits -> success 4000`, `4001 digits -> error …`.
- `git log --reverse origin/main..0fd73086 --format='%h %s'`: 80 commits. `git show --stat` on c76b998f, aa0e1fd9, 4b163520, 33a60a99, and 7ea64f63 shows each touches one file.
- `git diff --name-only origin/main...0fd73086 | grep -iE "__pycache__|\.pyc|dist/|scratch|\.log$"` prints nothing.
