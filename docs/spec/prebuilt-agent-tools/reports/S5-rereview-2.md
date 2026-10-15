LENS: conformance
VERDICT: SOUND — R-15, R-16, R-17 and the A.29 zero case all hold against their own evidence and against independent oracles, with no regression to R-1..R-14 or to the A.20, A.27 and A.29 rows. One Minor remains: extract_numbers has an undocumented far-exponent rule, and its new comment, its commit message and its tool description all describe that rule wrongly.

Reviewed: branch `feat/prebuilt-agent-tools` at HEAD `59d6a1a7` (clean). Code changed since `c8eefe53` is `202ef85f`, `9f7b70ac` and `70298784`; `985460fd..59d6a1a7` touches docs only. Interpreters: Python 3.11.0 (dev/CI) and `py -3.13` (3.13.1) for the cross-version checks. I was the only reviewer this round. Probes are in the session scratchpad `…/scratchpad/s5r2/`, called `s5r2/` below.

WHAT THE IMPLEMENTATION GETS RIGHT

- **The TOML scan matches tomllib on where comments and strings begin, in linear time.** In a 60,000-text differential against an instrumented `tomllib` (`tomllib._parser.parse_key` wrapped to record every key length it actually parses; 1 in 3 texts randomly mutated):
  - 0 under-refusals. This covers 12,172 valid texts and 1,122 invalid texts in which `tomllib` parsed a key of more than 100 segments before failing.
  - 0 over-refusals among 44,200 valid texts.
  - The piece-split hash and the verdict hash are identical on 3.11.0 and 3.13.1.
  - Every EC-51, R-6 and R-17 shape at the cap takes at most 0.125 s through the tool.
- **parse_data_size's far-exponent branch changes no ordinary result.** 3,828 ordinary inputs (every suffix, case variants, signs, `-0`, decimals, small `e`/`E` exponents, separators, unknown units) give results identical to the `c8eefe53` module and to an oracle written from the A.27 row text. 19 far-exponent inputs give the same result under the default, no-trap and hostile host contexts.
- **The extract_numbers change is surgical.** Across 40,000 random texts, the only differences from `c8eefe53` are added entries with value `"0"` whose exponent is past 4,002 (3,315 texts, 0 unexpected). R-2 still splits `1,2,3` into 1@0, 2@2, 3@4. Ordinary scientific notation still expands exactly (`2.5E-3` → `0.0025`, `1,234,567.5e2` → `123456750`).
- **The boundaries are intact.**
  - The repair changed no test: tests were last touched in S2's `225ab221`, and `git diff --stat 225ab221 59d6a1a7 -- tests` is empty.
  - `lint/baseline.json` is untouched, and nothing outside docs and tests changed beyond the 39 A + 4 M that §8.4 plans.
  - The three changed files are 501, 336 and 301 lines long.
  - The r7 regression cases can fail: with the `c8eefe53` behaviour restored in-process (`-p mut_plugin`), 12 of them fail.

FINDINGS (ranked, most severe first)

R-C1 [Minor] [conformance/spec drift + comment accuracy] vidbyte/tools/builtins/prebuilt/text_extraction.py:224 — extract_numbers skips a non-zero number whose exponent is past 4,002 even when its exact value fits DecText. So one number written two ways gets two results, while the new comment, the commit message and the model-facing description all say that only values too long to write out are skipped.
  Evidence:
    - The code (`:220-227`, rewritten in `70298784`):
      `# … zero stays zero under any exponent, and any other value would be too long to write out.`
      `far = abs(exponent) > PREBUILT_MAX_DECIMAL_TEXT_CHARS` … `if far and not number.is_zero(): return None`
    - The `70298784` commit message justifies the fix with "the module's own rule that only a value whose plain text passes the DecText cap is skipped", then says "any other value is still skipped because its plain text would pass the cap".
    - The tool description (`:120`) says: "A run of more than 4,000 digits or a value too long to write out in plain digits is skipped".
    - `python -u s5r2/p6_numbers.py` (the same before and after `70298784`, so this behaviour dates from S3 `0fd73086:…text_extraction.py:215`):
      `'1e-4000'    new=([('1e-4000', '0.0000000000000000000000...', 4002, 0, False)], 1)  SAME`
      `'1000e-4003' new=([], 0)  SAME`
      `'1e4001'     new=([('1e4001', '100000000000000000000000...', 4002, 0, False)], 1)  SAME`
      `'0.01e4003'  new=([], 0)  SAME`
    - The spec: §9.2 item 18 (spec.md:504) says a tool that bounds the exponent has a row that "gives the result for a farther exponent without building one (`parse_data_size`, A.27; `extract_numbers`, A.29)". The A.29 row (spec.md:1613) has no such clause. It says only "A number in scientific notation is expanded exactly. A run of more than 4,000 digits is skipped." and "Every occurrence is listed."
  Failure: the text `1000e-4003` (exactly 10^-4000, whose plain text is 4,002 characters) gives `{"numbers": [], "count": 0}`. The text `1e-4000`, the same number, gives one entry. A model that trusts the description expects both to be listed.
  Why Minor and not Major:
    - The non-zero behaviour is unchanged since S3, and two review rounds passed it.
    - The orchestrator's briefing treats "non-zero far → skipped" as the intended rule.
    - The input is contrived: an exponent past 4,002, offset by mantissa digits that bring the value back in range.
    - What is actually wrong is that the rule is undocumented and its stated reason is false.
  Smallest fix:
    - (a) The spec author adds to A.29 the clause that §9.2 item 18 already promises: "A number whose exponent is more than 4,002 in absolute value is listed as 0 when its digits are all zero, and is otherwise skipped, even when its value would fit."
    - (b) Correct the comment at `:220-223` and the KNOWN EDGE CASES sentence in the header at `:9`, and optionally extend the description's last sentence to "…or written with an exponent beyond 4,002…".
    - No behaviour changes. If the spec author would rather have "expanded exactly" govern, the fix becomes a code change (skip on `mantissa.adjusted() + exponent`, not on the raw exponent). That is a follow-up, not a repair item.
  Spec IDs: A.29 `extract_numbers` row, §9.2 item 18, the §9.2 caps row for `PREBUILT_MAX_DECIMAL_TEXT_CHARS`, G-4.

No other finding. I specifically tried and failed to produce:
- an over-refusal of valid TOML with ≤ 100 key segments;
- a key over 100 segments that reaches `tomllib` unscanned;
- a 3.11/3.13 divergence;
- a super-linear TOML input (every adversarial cap shape ≤ 0.2 s; ordinary cap-size TOML ≤ 0.85 s);
- a changed ordinary `parse_data_size` result;
- a leaked error type under any host decimal context.

FIX VERIFICATION

| finding id | fixing SHA | holds / does not hold | evidence (command or code line) | regression it introduced |
|---|---|---|---|---|
| R-15 | 202ef85f | holds | `structured_formats.py:68` makes both closing quotes optional (`"(?:[^"\\\n]\|\\.)*+"?\|'[^'\n]*+'?`). `p1_toml_tool.py big`: comment of `\"`×499,995 → success `{"value":{"a":1}}` in 0.011 s; open basic string of `\"`×499,990 → invalid-TOML message in 0.125 s; `'`×999,990 in 0.020 s; `"""`×333,333 in 0.023 s; `'''`×333,333 in 0.020 s. `p1 small`: the R-15 merge text `k(.k)×59."k(.k)×60 = 1` → "the text is not valid TOML 1.0". `p9_end_position.py`: one run of 61 segments on both 3.11.0 and 3.13.1 | none. Transient regex memory of up to 97.9 MB at the cap on crafted multi-line string content; ruled acceptable below |
| R-17 | 202ef85f | holds | `_TOML_SCAN_PIECE` (`:70-75`) skips comments and both multi-line strings whole. `p1 big`: the three R-17 shapes (literal + later quote, literal alone, basic + later quote) each → nesting message in 0.046 s. `p1 small`: 21 valid shapes parse exactly, including quotes in comments, `#` in strings, `'''` inside `"""` and the reverse, escaped quotes, backslash literals, quoted dotted keys, arrays of tables, 4 or 5 closing quotes, CRLF, and spaced dots. Runs in comments and strings are accepted; 100 segments are accepted and 101 refused in key, header, array-of-tables header, inline, quoted and literal forms. `p2_toml_diff.py`: 0 under, 0 over, identical hashes `d6fbf3434484d818`/`8af43d8cf62fb689` on 3.11.0 and 3.13.1 | none |
| R-16 | 9f7b70ac | holds | `bits_bytes.py:111-123`: `far` is computed before any `Decimal` is built; the mantissa's sign decides "negative"; `tiny = far or …`. `p5_data_size.py`: `ordinary grid: 3828 inputs, new!=old 0, new!=oracle 0, leaks 0`. All 19 far inputs give `same-under-3-contexts=True` and equal the row oracle: `1e999…` and `-1e999…` → error; `-1e-999…` → error; `1e-999…`, `0e±999…`, `-0e999…` and `1E-999…` → 0.0; `1e4003` → error and `1e-4003` → 0.0 at the boundary | none |
| A.29 zero case | 70298784 | holds for its stated scope (zero) | `p6_numbers.py`: `0e5000`, `-0e5000`, `0.000E-99999999999999999999`, `0,000e5000%` and `0e4003` → `"0"`, the same under no-trap and hostile contexts. `1e5000`, `1e-999…`, `-1e999…` and `2.5e5000` are still skipped. `p7_numbers_diffclass.py`: `3315 differ, all … added zero far-exponent entries: True`. `p8_numbers_time.py`: 142,857 × `0e5000 ` takes 0.147 s; a 750k-digit grouped mantissa with a far exponent takes 0.026 s; the R-2 chain takes 0.263 s | no regression. The same consistency class stays open for non-zero mantissas whose value fits (R-C1, Minor) |
| M-6 | 70df9458 (spec r7) | holds | The spec.md:661 row lists all four users of `PREBUILT_MAX_REPORTED_NAMES` | n/a |

RULING ON BRIEFING ITEM 4 (transient regex memory of the TOML scan)

- **Measured** (`p3_toml_memory.py`, tracemalloc, 3.11.0, at about 1,000,000 characters):
  - The scan's peak is 0.0 MB on an ordinary multi-line string.
  - 62.8 MB for `\"`×499,990.
  - 97.8 MB for `""a`×333,330.
  - 97.9 MB for `""\"`×249,997, closed or unclosed.
  - 40.0 MB for a literal `'a`×499,990.
  - 50.0 MB for a literal `''a`×333,330.
  - Every case takes at most 0.086 s.
  - For comparison, `tomllib` itself allocates 24.3 MB on an ordinary cap-size `x = [{}, {}, …]`.
- **The repair report understates the worst case.** Its "62.8 MB at the cap" is too low: content with two lone quotes in every three characters gives 97.9 MB. The figure of about 147 B per entry is consistent with its "≈125 B".
- **r7 has no memory rule for parser or scanner scratch space.**
  - INV-20 and AC-20 bound output length, and only output that has been built.
  - The 5 MB tracemalloc limit (test-plan.md:29, :377) covers four INV-20 tools whose refused output would be 20 MB or more.
  - T-2 names memory exhaustion as a threat and the schema caps as its mitigation. Those caps hold here: the cost is linear in the 1,000,000-character `Text` cap, transient, and freed when the call returns.
- **Ruling: not a finding; an acceptable bounded transient.** Two follow-ups:
  - The PR should state the worst case as about 98 MB, not 62.8 MB.
  - If the owner wants a scratch-memory bound, that is a new NFR, which makes it a scope-adding follow-up, not a repair item.

VERIFIED CLAIMS

- **AC-1 holds.** The §4 snippet, extracted from spec.md and run with `python -I` and no `*_API_KEY` set, prints exactly `('days_between_dates', 'count_character_occurrences')` and `success {"count": 3, "positions": [2, 7, 8], "truncated": false}`.
- **The gate claims at 985460fd hold at 59d6a1a7:**
  - pack: 4,397 passed;
  - lint: `SDK-LINT: PASS`;
  - source stage: `8412 passed, 13 skipped`, `CI passed.`;
  - semgrep: 931 files, 0 findings;
  - public API: current, 606 exports.
- **The review.md statuses hold:** R-15 and R-17 `fixed @202ef85f`, R-16 `fixed @9f7b70ac`, and M-6 `fixed @70df9458`. Each was re-proved above.
- **The cross-version claim holds.** The repair report says the piece split is identical on 3.11.0 and 3.13.1. On my own corpus the split hash (piece starts and segment counts) and the verdict hash are identical.
- **The "benign 3.11.0 end-position" claim holds.** `p9_end_position.py` shows `a. = 1` ends at 3 on 3.11.0 and at 1 on 3.13.1, with the same next piece and the same counts.
- **The "only an escape or lone quote holds a backtracking entry" claim holds,** since ordinary content costs 0.0 MB. "62.8 MB at the cap" does not hold as a worst case: it is 97.9 MB.
- **EC-51's "at most 0.13 s for each shape at the cap" holds** for the committed (unrolled) pattern too: at most 0.125 s.
- **`70298784`'s "any other value is still skipped because its plain text would pass the cap" does NOT hold.** See R-C1.
- **The A.27 row and the module header hold.** The header text "a tiny negative value such as -1e-99999999999999999999 is refused as negative although its float is -0.0" is confirmed.
- **The r7 regression tests can fail.** `-p mut_plugin` gives `12 failed, 28 passed`: the R-15/R-17 in-process TOML cases, all 9 R-16 rows, and the A.29 zero row.
- **The repair touched no test,** and S2's `225ab221` is the only commit since `c8eefe53` that touches tests.
- **The §8.4 budget is intact:** 39 A + 4 M outside docs and tests, and the repair added no file.
- **§14 "Never" holds for the iteration-2 diff:** no suppression, no baseline edit, no global-state call, no test edit.
- **The IDs walked for the changed code all hold:** INV-12, INV-13, INV-14, INV-15, INV-17, INV-19, NFR-7, NFR-8, NFR-9, NFR-10, AC-1, AC-6, AC-11, AC-16, AC-17, AC-21, EC-31, EC-51, D-19, §9.2 item 18 (code side), and §12.3 rows 27, 34 and 36.
  - Row 27: the multi-line content is an atomic group, and its only possessive parts are lookahead-free single-class runs.
  - The exception is the A.29 far-exponent clause that item 18 promises (R-C1).
- **request.md §A is unaffected.** Iteration 2 adds no tool, file, API or scope.

COMMANDS RUN (from the worktree; `PYTHONPATH` = worktree; probe files in `s5r2/`)

- `python -u s5r2/p1_toml_tool.py small` → `BAD COUNT 0`
- `python -u s5r2/p1_toml_tool.py big` → every shape at most 0.194 s (the EC-51 shapes at most 0.125 s) / `BAD COUNT 0`
- `python -I -u s5r2/p2_toml_diff.py gen … 60000 20261014`, then `check` on `python` and on `py -3.13`:
  - `3.11.0 {'texts': 60000, 'valid': 44200, 'valid_long': 12172, 'invalid_long': 1122, 'under': 0, 'over': 0, 'refused_invalid_short': 945}` / `split hash d6fbf3434484d818 verdict hash 8af43d8cf62fb689`
  - `3.13.1` gives the identical line and hashes
- `python -u s5r2/p3_toml_memory.py` → `ml basic quote-quote-escape len=999,998 scan: False 97.9 MB 0.086s` (the full table is in the ruling)
- `python -u s5r2/p4_toml_ordinary_time.py` → `array of ones: success 0.846s`, `array of empty inline tables: success 0.824s`
- `python -u s5r2/p5_data_size.py` → `ordinary grid: 3828 inputs, new!=old 0, new!=oracle 0, leaks 0`, with 19 far lines all `same-under-3-contexts=True`
- `python -u s5r2/p6_numbers.py` → the lines quoted in R-C1 / `random texts differing between new and old: 1873` (classified by p7)
- `python -u s5r2/p7_numbers_diffclass.py` → `40000 texts: 3315 differ, all differences are added zero far-exponent entries: True (unexpected 0)`
- `python -u s5r2/p8_numbers_time.py` → at most 0.263 s
- `python -E -s s5r2/p9_end_position.py <structured_formats.py>` on 3.11.0 and 3.13.1 → `(0, 3, 1)` against `(0, 1, 1)`, with the same counts
- `python -m pytest -q -p no:cacheprovider -o faulthandler_timeout=120 -p mut_plugin <3 row files> -k "toml or data_size or extract_numbers"` → `12 failed, 28 passed, 368 deselected in 0.71s`
- `python -m pytest -q -p no:cacheprovider -o faulthandler_timeout=120 tests/features/prebuilt_tools` → `4397 passed in 45.98s`
- `python lint/run.py` → `S063 RATCHETED: 4 known finding(s)…` / `S064 RATCHETED: 4…` / `SDK-LINT: PASS`
- `python scripts/run_ci.py --stage source` → `8412 passed, 13 skipped in 84.67s (0:01:24)` / `CI passed.`
- `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (scratchpad venv) → `Findings: 0 (0 blocking)` / `Ran 1 rule on 931 files: 0 findings.`
- `python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).`
- §4 snippet, run with `python -I` and no API keys → the two documented lines exactly
- `git diff origin/main...59d6a1a7 -- lint/baseline.json | wc -l` → `0`
- `git log --format='%h %s' c8eefe53..59d6a1a7 -- tests` → only `225ab221 test(prebuilt-tools): add failing regression cases …`
- `git diff --name-status origin/main...59d6a1a7 -- . ':!docs' ':!tests'` → `39 A`, `4 M`
- `git diff --stat 985460fd 59d6a1a7` → `docs/spec/prebuilt-agent-tools/pipeline.md | 7 ++++++-`
- `git show 0fd73086:vidbyte/tools/builtins/prebuilt/text_extraction.py` → `:215 if abs(exponent) > PREBUILT_MAX_DECIMAL_TEXT_CHARS: return None` (R-C1 predates iteration 2)
