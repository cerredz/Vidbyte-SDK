VERDICT: SOUND WITH FIXES — r2 holds up: attachment, nesting, growth, lint, and count fixes are mechanical and verifiable, but R-1's "exact output" goal is only partly met. Float values rounded into exact text outside finance, the order of money steps, the IRR grid on long series, and four open rows still let a correct implementer and a correct test author reach different answers.

Scope: round 2, scoped review of spec.md r2 (1,556 lines, commit ca46ac17, worktree HEAD fcf4416b). Sections read: §8 (D-2, D-7, D-9, D-12, D-16, D-18, §8.4, §8.5), §9.2 (items 5, 12, 15, 16, the enum and caps tables), §10 (T-1, T-2), §12 (rows 6–7, budget, §12.4 C, §12.6), Appendix A, and the parts of §4, §5, §6.1–6.3, and §13 that depend on them. Probes ran in `python -I -B` from the session scratchpad on CPython 3.11.0 (Windows). No repository file was written except this report.

WHAT THE SPEC GETS RIGHT
- The counts are consistent. Appendix A has 265 rows and 265 unique names (all match `^[a-z][a-z0-9_]*$`, longest 31 chars), and every table header count matches its rows. W-4…W-34 sum to 265. The ≥ 250 floor is the same in G-1, NFR-1, AC-2, AC-12, and FR-11. There are 68 enums (58 + 10) and 101 classes (31 + 1 + 1 + 68). The 39 planned files match the §12.3 CREATE rows, and the 4 MODIFY rows match the §6 rollback. The only stale "277" left is in the r1 history row.
- No new tool mechanism. The spec's claims about FunctionTool and Tools are accurate, which I checked against the code: `Tools.subset` returns a plain `Tools` in catalogue order (catalog.py), so the §4 `.subset([...])` snippet works. `_stringify_output` (:206) sits outside the try (:85) with `sort_keys`. Only TypeError/ValueError are caught around it, so a RecursionError would escape, and INV-19 is therefore the right guard. The execute error metadata (`error_type`, `error: execution_error`, :76-81) matches §13.
- The lint analysis is precise and correct. A007 splits whole words on `[_\.]+` over a 7-node context that stops at FunctionDef, and parameter (`ast.arg`) names are not collected. A002 matches `\b` against `_`-split body identifiers, so `permissions` does not trigger `permission`. S002/B904 has baseline 0, so the `from exc` rule is correct. None of the 68 enum names collides with an existing name in `vidbyte/lib/enums`. Ruff has no E501, so single-line description constants are fine.
- The r1 resource guards are well specified. INV-17 is a character budget with a lazy `cap_items`. INV-19 measures nesting without recursion before conversion. INV-20 gives a named list of tools with a measurement rule per tool (§9.2 item 12). EC-41 and EC-43 are concrete. D-18's 800-line split trigger is mechanical.

FINDINGS (ranked, most severe first)

R-13 [Major] [L10] §9.2 items 5 and 16, Appendix A.11 and A.26 — The rounding rule for exact output covers finance only. Rows that round a float into exact text have no conversion rule, and the two natural implementations disagree.
  Evidence: Item 5 (spec.md:460) says every text and integer output "is exact". Item 16's `Decimal(repr(x))` rule (:484) applies only to "finance rows". These rows round a float into exact text with no stated path:
    - `format_duration` (:1260): "Fractional seconds keep up to 3 places, rounded half-even"
    - `parse_duration_text.iso8601` (:1261): "in the `format_duration` form"
    - `decimal_degrees_to_dms` (:1482): "Seconds round half-even, and a carry moves into minutes and degrees"
    - `unix_timestamp_to_datetime` (:1255): "rounded half-even to microseconds"
  Probes, comparing `round(x, k)` with `Decimal(repr(x)).quantize(…, ROUND_HALF_EVEN)`:
    - 0.0125 → 0.013 vs 0.012; 0.0375 → 0.037 vs 0.038; 2.0035 → 2.003 vs 2.004.
    - `decimal_degrees_to_dms(0.000875, seconds_decimal_places=1)`, computed with the float `(x − d)·60` steps, gives 3.1″. The Decimal path gives 3.2″ (exact value 3.15″). 14,564 of 399,999 sampled inputs differ, even after the carry is applied.
    - `timedelta(seconds=1700000000.0000045)` gives …005 µs, while the Decimal path gives …004 µs; 421 of 3,999 half-µs inputs differ.
    - `timedelta(milliseconds=1700000000123.0015)` gives .123001, while `timedelta(seconds=x/1000)` gives .123002; 494 of 3,999 differ.
    - `format_duration` does not say whether to round before or after splitting into parts. 59.9996 s gives "60s" if split first and "1m" if rounded first.
  Failure: The S2 test author follows item 16's Decimal path because §13 says "compute expectations with §9.2 item 16". The implementer reaches for `round()` or `timedelta(seconds=float)`. Exact-comparison tests then fail on tie and near-tie inputs, which tests are likely to use (0.0125 s, 0.000875°). The loop ends BLOCKED with no rule to settle it.
  Smallest fix: Widen item 16 bullet 1 into a rule for every row (new item 17, or move it into item 5). "A `Float` that a row rounds to a fixed number of places for a text, integer, or exact output is converted with `Decimal(repr(x))`, scaled exactly in `Decimal` (×60, ×3600, ×1000, /1000), and rounded once with `quantize` in the row's mode. Whole-value rows round the total before splitting it into parts." `unix_timestamp_to_datetime` builds `timedelta(microseconds=int(rounded_microseconds))`. Name the four rows in the rule.

R-14 [Major] [L10/L5] §9.2 item 16, A.7 (`amortization_schedule`, `loan_payment_amount`) — Money cents depend on an evaluation order the spec does not pin, because intermediate steps round at 50 digits.
  Evidence: Item 16 (:485) runs money formulas in a 50-digit context "which rounds the intermediate steps". The `amortization_schedule` row (:1195) says interest = "balance × i" with "i = rate / 1200" (:1194). Probe: balance 1740.00 at 6.1% has exact monthly interest 8.845, a cent tie. The spec's literal order is i = 6.1/1200 rounded to 50 digits, then 1740 × i = 8.8449999…, which gives 8.84. The other natural order, 1740 × 6.1 / 1200 = 8.845 exactly, gives 8.85. The wrong cent then carries into every later balance, `final_payment`, `total_paid`, and `total_interest` (the last three via :1194). A search found this case among about 285K balance × rate samples, so it is rare but reachable with round inputs. Separately, the "10^47 … cannot keep its cents within 50 digits" claim (:486, :1193) treats 10^47 as the point where cents stop being exact. That ignores how `**` multiplies the base's rounding error: with an exponent up to 365 × 1000, the relative error is about 4e-45, which is several units near 10^46. That part only matters if the claim is read as a promise of exact cents. Compound growth was probed and is order-safe in practice (P = 10^15, 10%, daily, 300 years: both orders give the same cents). Tax split and shares are also safe (one rounding of the same exact quotient).
  Failure: The implementer and the test author each pick a reasonable order and disagree by one cent on a tie, and the error runs down the whole schedule. That is an exact-comparison failure in the finance table, which is the exact problem R-1 named.
  Smallest fix: In item 16, add: "Rational money steps (period interest, the level payment for integer n, net of tax, shares) are computed exactly in `Fraction` from `Decimal(repr(x))` inputs and rounded once. Only a non-integer power and `exp` use the 50-digit context, evaluated as written: `base = 1 + r/m`, `exponent = m·t`, `FV = P × base ** exponent`." Keep 10^47 as an overflow guard, but drop "cannot keep its cents" or soften it to "guard".

R-15 [Major] [L5/L10] A.7 `internal_rate_of_return` — The grid scan fails on valid inputs from 154 cash flows up (the cap is 600), and the bisection stopping rule breaks item 5 for small IRRs.
  Evidence: The row (:1197) scans r_k from `PREBUILT_IRR_GRID_START` = −0.99 (:637). At r = −0.99, the discount factor is 0.01^t. Probe with [-10000] + [100]×n:
    - t = 154 is where it first goes wrong. At 154–161 flows NPV is ±inf or nan.
    - At 180 flows, the `cf / (1+r)**t` form raises ZeroDivisionError and the `cf * (1+r)**-t` form raises OverflowError.
  §12.4 C (:917) requires every OverflowError and ZeroDivisionError to be converted to a tool error. A literal implementation therefore rejects every monthly series longer than about 12.8 years, even though `PREBUILT_MAX_CASH_FLOWS` allows 600. The row also says "down to `PREBUILT_IRR_TOLERANCE`" (1e-12 on the rate), which is 1e-10 on `irr_percent`. Item 5 (:460) requires rel 1e-9 or abs 1e-12. Example: [-100, 100.01] has IRR 0.01%, so the allowed tolerance is 1e-11, below 1e-10. The row also does not say which point it returns: lo, hi, or the midpoint. (Checked: −0.99 + 99·0.01 == 0.0 exactly, so the "exactly zero" grid point is reachable.)
  Failure: Long series that a user would really send fail with an error, or the implementer quietly diverges from the spec. Precision tests on small IRRs fail by an order of magnitude, and the returned point is a coin flip.
  Smallest fix: (a) "A grid point where NPV overflows, divides by zero, or is not finite is skipped. A sign change is sought only between consecutive finite points." (b) "Return the bisection midpoint." (c) Give the row its own precision, "`irr_percent` is within 1e-10 absolute", as an explicit exception to item 5, the same way item 5 already handles rounded floats.

R-16 [Major] [L10] Appendix A — Four rows still leave outputs open (R-1 residue).
  Evidence:
    - `ini_to_json` (:1393): with `default_section` renamed, `[DEFAULT]` becomes an ordinary section. Probe: `ConfigParser(default_section='\n')` lists `'DEFAULT'` in `sections()`, giving `{'DEFAULT': {'a': '1'}, 's': {...}}`. The row says `defaults` holds those keys but never says whether `sections` also contains `"DEFAULT"`. The natural loop over `sections()` duplicates it.
    - `format_number_with_separators` (:1140): several cases are open. With `decimal_places` set, does `"1.5"` at 2 places give `"1.50"`? This row is not on item 5's fixed-digit exception list (:456), so canonical DecText output would strip the zero. Also open: leading zeros (`"0001234"`), `"1234."`, `".5"`, `"-0"`, and which space or apostrophe character the `space_*` and apostrophe styles use (U+0020/U+00A0/U+202F; U+0027 vs U+2019).
    - `parse_data_size` (:1490): says "a number" with no grammar for sign, exponent, `.5`, or thousands commas. The neighbouring item 15 grammar is not cited.
    - `profile_csv_columns` (:1378): when equal-valued cells differ in text (`"1"` and `"1.0"`), it is open which text `min`/`max` returns.
  Failure: Each open choice is a coin flip between the implementer and the S2 test author, which is the R-1 failure mode at smaller scale.
  Smallest fix: One sentence per row. Suggested: "`sections` never contains `DEFAULT`; other sections in file order." "With `decimal_places`, the fraction has exactly that many digits (add the row to item 5's exception list); input follows DecText; separators are U+0020 and U+0027." "The number follows §9.2 item 15." "Among equal values, the first in row order."

R-17 [Minor] [L4] §8 D-7 — The rationale misquotes AGENTS.md principle 4. There is no carve-out "for data that is not passed between layers".
  Evidence: D-7 (:282) says "That matches the principle's own carve-out for data that is not passed between layers." AGENTS.md principle 4 says: "Small private helpers do not need dataclasses of their own; the rule is for the functions that hold a feature's real logic and for the data passed between layers." Tool functions hold the real logic, and D-7 itself concedes the principle "nominally covers" them. The only carve-out is for small private helpers. Also, the "internal" category classes are listed in a public package's `__all__` (row 39, FR-5), so "internal" is a prose label, not something the code enforces.
  Failure: A reviewer, or the `@claude` placement/review workflow, checks the quote against AGENTS.md, finds no such carve-out, and re-opens D-7 at PR time. That is the late rework R-6 was meant to prevent.
  Smallest fix: Rewrite the sentence as a deliberate, owner-visible exception to the letter of principle 4. Keep the three good reasons already in the cell: the pydantic args model is the validated input record, a dataclass parameter would nest the schema (`_build_args_model` :136-151), and `_stringify_output` is the only reader. Keep the Q-6 default of no. R-6 status: partially resolved.

R-18 [Minor] [L9] INV-20, INV-12, NFR-10 — These invariants promise more than the rows deliver.
  Evidence: INV-20's first sentence (:147) covers any tool whose output "can grow much faster than its input … by repeating input text, padding … or copying". The list after it leaves out tools that amplify by a bounded factor. Probes:
    - `apply_unicode_normalization` NFKC/NFKD: U+FDFA → 18 chars (18×)
    - `hex_encode` with utf_32 and a separator: one astral char → 23 chars (~23×)
    - `escape_json_string` with ensure_ascii: astral → 12 chars (12×)
    - also `extract_line_range` with numbering (~9×), `base64_encode` (~5.3×), `unified_diff_text` (~2×)
  INV-12 (:139) says output does not depend on "the operating system", and NFR-10 (:263) says Windows, Linux, and macOS give identical outputs. Transcendental floats (sin, atan2, erf, exp) come from the platform libm. Dev is Windows and CI is ubuntu-latest, so byte identity across OS is not guaranteed.
  Failure: A test author who binds to INV-20's general sentence writes "no output exceeds 1,000,000 chars" and these tools fail it. A cross-OS byte-identity test (AC-11/NFR-10) on float output can fail the first time it runs on another OS. §13's `approx` comparison hides this today.
  Smallest fix: Start INV-20 with "These tools…", and add an EC that accepts the bounded factors (≤ 23× of a capped input). Exempt float values from byte identity in INV-12 and NFR-10 ("floats agree within item 5").

R-19 [Minor] [L8/L9] §12.4 B vs §9.2 — "A categorical vocabulary is never a bare tuple in `lib/constants`" contradicts two rows, and an implementer who follows it hits the enum budget.
  Evidence: §12.4 B (:908) says: "Every parameter or output value from a closed set is typed or produced through one of these enums." `format_bytes_human.unit` (:1491) is a closed set (B…EiB / B, kB…EB) with no enum. `extract_money_amounts.currency` (:1522) draws from `PREBUILT_CURRENCY_CODES`, listed as a reference tuple (:664). The field guide's "centralize categorical vocabularies" entry records the owner flagging tuples in constants twice (PR #342, #384). Separately, FR-8 says every resource bound is a named constant, but §9.2 and row 4 leave several unnamed: `fraction_to_decimal` 1,000 digits, the 20-digit approximation (:1110), "up to 20" missing names (:1296), 3 profile examples, key length 1–100, 2 mojibake rounds, GSM 160/153/70/67, email 64/253/254, ≤ 5 regex flags, ≤ 7 weekdays.
  Failure: An implementer who follows B literally adds 1–2 enums, so §8.4's 68 becomes 70 and the budget check reports BLOCKED. An implementer who follows the rows breaks a B checkbox the reviewer will tick against.
  Smallest fix: Do one of two things. Either type `unit` with an enum (extend `DataSizeUnit` with exabyte/exbibyte, or add `SizeUnitSymbol`), add `CurrencyCode`, and set the budget to 70. Or narrow B to "parameters and fixed output vocabularies; recognition word lists and suffix tables are reference tables (:664)" and mark `unit` as such. Either add the FR-8 constants or change FR-8 to "resource caps in the §9.2 caps table".

R-20 [Minor] [L11] §14 vs §12.6 and §13 — "Run … pytest … after each category module" cannot be done in the planned phase order.
  Evidence: §14 (:1010) requires the feature pack to run after each category module. §13 (:985) says tests are built "through `PrebuiltTools([...])`". `PrebuiltTools` (row 41) lands in P3, after all 31 modules (§12.6 :962-963). Row 41's `_CATEGORY_FUNCTIONS` maps every member, so it cannot exist until P2 ends.
  Failure: The implementer either skips a "never skip" rule or builds a partial dispatch table and changes it later. Either way the check run after each module does not happen as written.
  Smallest fix: Change §14 to "after P3, and after each later change". Alternatively, move rows 41–42 to the start of P2 and grow `_CATEGORY_FUNCTIONS` as each module lands, with AC-2 allowed to fail until P2 ends.

R-21 [Minor] [L8] §12.4 E and row 40 — The README File Index will trip S020 on backticked references to other files.
  Evidence: `lint/rules/s020_readme_file_index_parity.py` counts every backticked `name.ext` inside `## File Index` as an entry, for the suffixes .json .md .py .toml .txt .yaml .yml (README.md and llms.txt excepted). It reports any entry that is not a direct child as stale. S020 is blocking with baseline 1. Row 40 (:885) asks for 3–4 sentences per entry, which invites mentions such as `function_tool.py` or `vidbyte/lib/constants/prebuilt_tools.py`.
  Failure: A well-written File Index fails lint in P4, and the fix (removing helpful cross-references) is found only by trial.
  Smallest fix: Add to row 40 and §12.4 E: "Inside `## File Index`, backtick only the folder's own direct children; name other files without backticks or outside the section."

R-22 [Minor] [L4] row 6 and §12.4 C — The same validation is repeated inline in about 22 tools, and no shared helper is planned for it.
  Evidence: About 18 rows prescribe the same check that parallel lists have equal length: `weighted_mean`, `pearson_correlation`, `spearman_correlation`, `linear_regression`, `seeded_weighted_choice`, `percentage_breakdown`, `merge_time_intervals`, `find_common_free_slots`, `polygon_area`, `point_in_polygon`, six graph tools, `shortest_weighted_path`, `critical_path_schedule`. Four rows repeat the weight checks (negative weight, zero total). Row 6 lists `PrebuiltToolSupport` helpers but neither of these. AGENTS.md principle 5, and the field guide's strict-config entry ("any primitive value validated inline in more than one call site", PauseDuration, PR #352), call for one helper.
  Failure: The PR review flags the duplication, or the error messages drift: the same mistake gets different `expected` text in different tools, which AC-6's message-shape tests may catch late.
  Smallest fix: Add two static methods to row 6, such as `paired_values(first, second, first_name, second_name)` and `weight_total(weights, parameter_name)`. Name them without the C006/C008 prefixes (`validate|require|ensure|check|normalize|coerce`).

VERIFIED CLAIMS

Round-1 closure:
| ID | Status | Notes |
|---|---|---|
| R-1 | partially | Item 5, 15, and 16 rules and the 11 settled rows are good; residue in R-13, R-14, R-15, R-16 |
| R-2 | resolved | INV-20 running size for `apply_json_patch`; EC-41; AC-20 |
| R-3 | resolved | |
| R-4 | resolved | |
| R-5 | resolved | INV-19, nesting measured without recursion before conversion |
| R-6 | partially | D-7 now argued, but on a misquoted carve-out (R-17) |
| R-7 | resolved | |
| R-8 | resolved | |
| R-9 | resolved | |
| R-10 | resolved | |
| R-11 | resolved | |
| R-12 | resolved | |

Held (checked against code or by probe):
- `vidbyte/tools/function_tool.py` (249 lines):
  - :62 validate, :72 `to_thread`
  - :76-81 failure result with `error_type: exc.__class__.__name__` and `error: execution_error`
  - :85 stringify outside the try; :93 null means default
  - :136-151 `_build_args_model`; :138 `get_type_hints(include_extras=True)`
  - :180 JSON-mode validation; :192 docstring first paragraph
  - :206 `json.dumps(sort_keys=True, ensure_ascii=False)`; :241-242 dataclass serialization
- catalog.py: duplicate name raises `ToolRegistrationError` (:38); `subset` and `without` return plain `Tools` in catalogue order.
- toolsets `__all__` = CodingAgentTools, ParadigmMinimalToolset. `vidbyte/__init__.py:611` imports toolsets. The REPO_MAP toolsets entry is stale ("one such bundle"), so FR-10's update is warranted. The tools README has `## Deep Reasoning Traces` and `## Key Modules`.
- errors/base.py: `VidbyteSdkError(message, *, details)` :62, `ToolRegistryError` :69, `ToolExecutionError` :73. S016 BOUNDARY_PREFIXES includes `vidbyte/tools/builtins/`.
- Lint baselines: A001 643, A002 703, A007 255, S015 13, S020 1, S025 263, S002 (B904) 0. A001 requires 7 fields and scans 80 header lines.
- Ruff selectors include ANN, B904, B905, C901, DTZ, PLR0912, PLR0915, RUF012, TID251/252, TRY002, S324, I001, UP; no E501. lint/ruff.toml bans TypedDict, assert_never, and asyncio.Lock.
- `vidbyte/lib/enums/__init__.py` is 235 lines with no collision with the 68 new names. The new enum module estimate (~680 lines) is under 800.
- `lib/constants/__init__` re-exports only some modules, so not re-exporting `prebuilt_tools` is fine. Constants importing enums has precedent (codex, cot_events, jev).
- Tests: `SentenceCounter` at s025:185. Tests already import lint modules (test_readme_size_limit.py:18, test_jev_done.py:28). Pytest has testpaths and `asyncio_default_fixture_loop_scope` but no `asyncio_mode`. There is no tests/conftest.py. Feature packs exist (sdk_operation_costs).
- CI: ubuntu-latest, Python 3.11 and 3.12.
- IRR grid: −0.99 + 99·0.01 == 0.0 exactly.
- Compound interest with the 50-digit context gives the same cents for `(1 + r/m)` and `((m + r)/m)` on a large probe (P = 10^15, 10%, daily, 300 years).

Did not hold:
- D-7 "the principle's own carve-out" (R-17).
- §12.4 B "never a bare tuple" vs `format_bytes_human.unit` and currency codes (R-19).
- INV-12 and NFR-10 cross-OS byte identity for floats (R-18).
- §14 running tests after each module (R-20).
- "Cents kept below 10^47" as an exactness claim (R-14).
- The IRR grid being usable up to the 600-flow cap (R-15).
- "Text outputs exact" for float-derived text outside finance (R-13).
