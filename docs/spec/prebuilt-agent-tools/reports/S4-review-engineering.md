LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — The design and most guards hold up. But hostile input within the caps can drive seven tools into tens of seconds, minutes, or hours of CPU, and one into unbounded memory. Separately, the host's decimal context leaks into eight call sites. NFR-7, T-2, §12.3 row 36, and §9.2 item 16 forbid both problems, and the pack has no test that detects either.

Reviewed: `git diff origin/main...0fd73086` (worktree HEAD 9d8eb2f7). Measurements are from Python 3.11.0 on the dev machine through `FunctionTool.execute`, unless a line says otherwise. Read-only review: no repository file other than this report was written.

## WHAT THE IMPLEMENTATION GETS RIGHT

- **JSON input is hardened.** `_support.parse_json_text` refuses NaN and Infinity, integers longer than 4,300 digits, and nesting deeper than 100 levels. It also turns `RecursionError` and `ValueError` into `ToolExecutionError`.
- **Deep Python input fails cleanly.** `code_analysis` refused six 200,000-character shapes (`a.`×99k, `+0`×99k, unary `-`×190k, `not `×49k, `()`×99k, `[0]`×66k) with a `ToolExecutionError` in under 0.05 s each.
- **The INV-20 output guards predict size or measure it while building, as specified.** Examples: `format_json._formatted_length`, the running size in `apply_json_patch`, `regex._match_values` and `_replace_measured`, `xml_to_json._element_value`, and the CSV and records writers.
- **Every count that could explode is arithmetic.** This covers subnets, ranges, combinations, business days, and recurrences, and enumerations are lazy and capped by `cap_items`.
- **Exact domains run in explicit contexts.** `exact_arithmetic` and `number_formatting` use an explicit `Context(prec, Emin, Emax, traps)`. Finance money steps are exact in `Fraction`, with a single half-up rounding.
- **The XML guards hold.** `<!doctype` fails as a syntax error, and a long `xmlns` URI is refused after a tab, a newline, or another attribute.
- **Most text tools are fast at the cap.** 97 tools that take text at the 1,000,000-character cap stayed under 1.2 s on 38 repetitive input shapes (sweep below).

## FINDINGS (ranked)

R-E1 [Blocker] [failure modes / scale] vidbyte/tools/builtins/prebuilt/structured_formats.py:130 — `xml_find_elements` can exhaust host memory from under 400 characters of input, and it returns duplicate matches.

  Evidence:
  - `root.findall(path)` materializes the whole ElementPath result. The descendant step (`//`) in the standard library yields `elem.iter(tag)` for every context element, with no de-duplication, so every extra `//a` step multiplies the result.
  - Measured:

    | Document | Path | count | Peak memory | Time |
    |---|---|---|---|---|
    | `<a>`×2000 + `</a>`×2000 | `.//a//a` | 1,997,001 | — | 0.10 s |
    | `<a>`×6000 + `</a>`×6000 | `.//a//a` | 17,991,001 | 161 MB | 0.80 s |
    | `<a>`×60 + `</a>`×60 (420 characters) | `.//a//a//a//a//a//a//a` (22 characters) | 45,057,474 | 366 MB | 6.38 s |

  - Each further `//a` multiplies the result by about 9 at depth 60. The path cap is 1,000 characters, and this tool has no depth check.
  - Correctness: on `<r><a x='1'><a x='2'><a x='3'/></a></a></r>`, the path `.//a//a` returns `count: 3` and lists `{"x":"3"}` twice. Only two elements match, and the row promises matches "in document order".

  Failure: One prompt-injected call takes the host process into MemoryError or an OS OOM kill. It can happen inside the worker thread, where `tool_timeout_seconds` cannot stop it (EC-28). Neither EC-10 nor EC-46 covers this case.

  Smallest fix:
  - Iterate `root.iterfind(path)` lazily.
  - De-duplicate by identity with a `seen` set, and order the distinct matches by their index in `root.iter()`.
  - Raise `ToolExecutionError` on `path` once the matches yielded pass a work budget (for example 1,000,000).
  - Add a resource-bounds case: the 60-deep document with seven `//a` steps must fail quickly. Add a row case: `.//a//a` on the 3-chain must give a count of 2.

  Spec IDs: T-2, INV-17, INV-20, NFR-7, A.20 `xml_find_elements`.

R-E2 [Blocker] [scale] vidbyte/tools/builtins/prebuilt/text_extraction.py:56 (`_AMOUNT`), used at :67 (`_NUMBER`) and :78 (`_MONEY`) — The amount pattern is quadratic, which contradicts the linear-time promise in §12.3 row 36 and A.29.

  Evidence:
  - The atomic group `(?>[0-9]{1,3}(?:,[0-9]{3})++)` has an unbounded comma chain. The lookbehind `(?<![\w.])` accepts a start after every comma, so each group restarts a scan to the end of the chain.
  - Input `"1" + ",000"*n + "0"`, `extract_numbers`: 0.089 s at 10,002 characters, 0.273 s at 20,002, 0.931 s at 40,002, 3.431 s at 80,002.
  - `extract_money_amounts` on a plain comma chain: 0.109 s, 0.426 s, 1.696 s, 6.720 s at the same sizes.
  - Extrapolated to the 1,000,000-character cap: about 535 s and about 1,050 s.
  - Each tool also scans the text twice (:119/:120 and :155/:156).
  - The module header (lines 5 and 8) makes the same false claim.

  Failure: A crafted document pins a CPU core for 9 to 18 minutes per call. The worker thread cannot be killed (EC-28).

  Smallest fix:
  - Let a chain start only where a number starts: add `(?<![0-9],)` in front of `{_AMOUNT}` in both patterns. Each chain is then scanned once.
  - Pin the output for malformed chains such as `"1,000,0000"`, because the fix can change it.
  - Optionally fold the count pass into the list pass.

  Spec IDs: §12.3 row 36, A.29 intro, NFR-7, T-2.

R-E3 [Blocker] [failure modes] vidbyte/tools/builtins/prebuilt/text_transform.py:280, markdown_html.py:183, markdown_html.py:226 — The three tools built on `HTMLParser` are worse than quadratic on malformed tags.

  Evidence:
  - `strip_html_tags` with `"<a "` repeated: 12.325 s at 25,010 characters, 57.142 s at 50,009.
  - `strip_html_tags` with `"<a b='"` repeated: 2.987 s at 25k, 16.969 s at 50k.
  - The raw standard-library parser on Python 3.13.1, `"<a "`: 1.603 s at 10k, 7.292 s at 20k, 35.748 s at 40k. So this is not specific to 3.11.0.
  - `html_table_to_records` and `extract_html_links` feed the same parser, and `html_text` is `Text` (1,000,000 characters). At the cap the time is hours.
  - This is the CPython class gh-135462 / CVE-2025-6069, fixed only in later patch releases, while `requires-python` accepts any 3.11+. I did not test a patched interpreter.

  Failure:
  - Hours of CPU in a worker thread that cannot be killed.
  - These calls run on asyncio's shared default executor (`asyncio.to_thread`, function_tool.py:72). Two or three such calls can therefore starve every other `to_thread` user in the host, not only tools.

  Smallest fix (a spec decision is needed):
  - (a) Run a linear pre-pass that turns each `<` with no `>` before the next `<` into `&lt;` before feeding the parser, and re-measure the quoted-attribute shape.
  - (b) Require patch levels with the fix and test the shape.
  - (c) Accept it as a new EC with a README note. But unlike EC-46, this case does not finish in seconds.

  Spec IDs: NFR-7, T-2, EC-28, A.11, A.25.

R-E4 [Blocker] [scale] vidbyte/tools/builtins/prebuilt/structured_formats.py:168 — `toml_to_json` is quadratic on long dotted keys, and the nesting cap is checked only after the parse.

  Evidence:
  - `"a" + ".a"*n + "=1"`: 0.117 s at n=5k, 1.979 s at 20k, 9.374 s at 40k (80k characters).
  - Header form `"[a" + ".a"*n + "]"`: 3.023 s at n=80k, 16.978 s at n=160k.
  - Sweep input `"a."` repeated to 1,000,000 characters: killed by `timeout 150`.
  - The cost is inside `tomllib`'s key building, before line 179's `nesting_level` check can refuse the result.

  Failure: A 1 MB TOML document holds the worker for well over two minutes; extrapolation gives about 25 minutes.

  Smallest fix:
  - Before `tomllib.loads`, refuse with the existing nesting message any line whose key part has more than `PREBUILT_MAX_JSON_NESTING` dots. The key part is the text before the first `=`, or a `[...]` header. This over-refuses only quoted keys holding many dots.
  - Add the 1,000,000-character dotted case to `NESTING_CASES`.

  Spec IDs: NFR-7, T-2, INV-19, A.20 `toml_to_json`.

R-E5 [Blocker] [scale] vidbyte/tools/builtins/prebuilt/markdown_html.py:44 (`_ATX_CLOSING`), used at :274 — Heading extraction is quadratic on a long run of spaces.

  Evidence:
  - `(?:^|[ \t]++)#++[ \t]*+$` runs through `.sub(count=1)`, which is a search. Every position inside a run of spaces starts a new possessive scan to the run's end.
  - `extract_markdown_headings` with `"# a" + " "*k + "#x"`: 0.244 s at k=25k, 0.958 s at 50k, 3.822 s at 100k, so about 380 s at the cap.

  Failure: A single 1 MB Markdown line holds the worker for about 6 minutes.

  Smallest fix: Use `(?:^|(?<![ \t])[ \t]++)#++[ \t]*+$` so each run is tried once from its start. Add the case to the markdown row tests.

  Spec IDs: NFR-7, T-2, A.25 `extract_markdown_headings`.

R-E6 [Major] [scale] vidbyte/tools/builtins/prebuilt/json_data.py:204 with :407-428 — `apply_json_patch` bounds the document's size but not the total work across its 1,000 operations.

  Evidence:
  - Document `{"a":[0]*200000}` (600,007 characters):
    - 500 × (copy `/a` to `/b`, remove `/b`) = 1,000 operations, about 40 KB of patch: 25.991 s.
    - 1,000 moves back and forth: 13.095 s.
  - Every operation re-serializes (`json.dumps`), deep-copies, or walks (`nesting_level`) a value of up to 1 MB.
  - T-2 names this tool's root-copy chain explicitly. The guard stops memory growth (EC-41) but not CPU.

  Failure: 13 to 26 s per call at the cap, against NFR-7's 2 s. This is not one of the accepted cases.

  Smallest fix:
  - Keep a cumulative work counter in `_measured_insertion`: the characters measured, plus the values walked or copied.
  - Raise on `patch_json` once it passes a small multiple of `PREBUILT_MAX_TEXT_CHARS`, for example 10×.
  - Add a resource-bounds case.

  Spec IDs: NFR-7, T-2, EC-41, INV-20.

R-E7 [Major] [scale] vidbyte/tools/builtins/prebuilt/text_counting.py:92-96 and text_transform.py:206-221 — Literal search costs O(text × substring) when matching is overlapping or case-insensitive, and the text is scanned twice.

  Evidence:
  - Text `"a"*1,000,000`, needle `"a"*9999+"b"`:
    - `find_substring_positions` (overlap and case-insensitive): 26.648 s.
    - `replace_all_occurrences` (case-insensitive): 13.424 s.
  - At 200k characters: overlap 1.992 s, case-insensitive 5.086 s, replace (case-insensitive) 2.549 s.
  - A case-sensitive, non-overlapping search takes 0.002 s.
  - The lookahead `(?=literal)` and `IGNORECASE` disable `re`'s fast literal search, and both tools run `finditer` twice.

  Failure: About 27 s per call at the caps. This is not one of the accepted cases (EC-10 covers only the regex tools).

  Smallest fix:
  - Single pass in both tools.
  - Use a `str.find` loop for the case-sensitive overlap path.
  - Make a spec decision for the case-insensitive path: cap `substring`/`find` (for example at `PREBUILT_MAX_PHRASE_CHARS`) or record an EC-46-style accepted limitation.

  Spec IDs: NFR-7, T-2, A.1 and A.11 rows.

R-E8 [Major] [error handling] vidbyte/tools/builtins/prebuilt/finance.py:297 (also geometry.py:179, timestamps_durations.py:253/296/305/313, encoding.py:273, text_extraction.py:250) — The host's decimal context leaks into tool results.

  Evidence:
  - `localcontext(prec=..., rounding=...)` copies the caller's traps, Emin, Emax, and clamp. `asyncio.to_thread` copies context variables, so the host's `decimal.getcontext()` reaches the worker thread.
  - With the host trapping `Inexact` and `Rounded`: `compound_interest_future_value(1000, 5, 10)` returns `ToolExecutionError` "Invalid value for 'years': the future value leaves the decimal range". The correct answer is 1647.01. Cause: the `except DecimalException` at finance.py:309 relabels the trap.
  - With the host at `Emax=5`: `decode_jwt_payload` returns `error_type: Overflow` with the output `[<class 'decimal.Overflow'>]`. That is not a `ToolExecutionError`, and it is the raw text of the exception.
  - `exact_arithmetic.py:286` and `number_formatting.py:283` already build an explicit `Context`.

  Failure: Wrong refusals, and a broken error contract, for any host that tightens its decimal context, as money software commonly does.

  Smallest fix:
  - Add one `_support` helper that returns `localcontext(Context(prec, rounding, Emin=MIN_EMIN, Emax=MAX_EMAX, traps=[InvalidOperation, DivisionByZero, Overflow]))`, and use it at the eight sites.
  - Add a test that sets host traps and `Emax` and checks that one tool per site returns its default-context output.

  Spec IDs: §9.2 item 16 ("set explicitly so a host's own decimal context cannot change a result"), INV-13, EC-27, §9.2 error contract.

R-E9 [Major] [test quality] tests/features/prebuilt_tools/test_prebuilt_resource_bounds.py:1-12 (and test-plan "Wall-clock assertions" row) — No pack test drives any tool to its CPU cost at the cap with adversarial input, so every finding above passes the pack, and a count regression would hang CI instead of failing it.

  Evidence:
  - The pack gives `4310 passed in 20.48s` at this HEAD, with R-E1 through R-E7 all present.
  - For three likely bugs in each risky area, I checked whether the pack catches them:
    - Parsing and regex cost (quadratic regex, HTMLParser, ElementPath growth): 0 of 3 caught.
    - Decimal exactness (host traps, host Emax, a wrong `DecimalException` mapping): 0 of 3 caught.
    - Output amplification (missing character budget, mispredicted `format_json`, an uncapped root copy): 3 of 3 caught (`test_regex_matches_stop_at_the_character_budget`, EC-43, EC-41).
    - Enumerated counts (2^128, 10^15, C(39,20)): caught only as a hang. The file header admits this: "would hang on the count cases rather than fail".
  - The test plan's reason for skipping timing is that timings flake on shared CI. That argument does not apply to a ceiling 15 times NFR-7: every finding above is at least 6 s, and most take minutes at sizes within the cap.

  Failure: CPU-exhaustion regressions ship silently, and a counting regression shows up as a CI timeout with no test name.

  Smallest fix:
  - Add a harness helper that runs `tool_runner.result` in a daemon thread and fails after `join(30)` with the tool's name. This needs no new dependency.
  - Use it for the three count tests.
  - Add one adversarial cap-size case per R-E1 through R-E7 tool.

  Spec IDs: NFR-7, T-2, AC-14, AC-20, test-plan rule 3.

## VERIFIED CLAIMS

1. S3 §3 says the pack gives `4310 passed`. CONFIRMED: `4310 passed in 20.48s`.
2. S3 §2 says no module is longer than 800 lines and the largest is `json_data.py` at 582. CONFIRMED by `wc -l`: 582, then 577, 528, 503.
3. S3 §6 says md5 and sha1 use `usedforsecurity=False`. CONFIRMED: every `hashlib.new` in hashing.py (lines 76, 89, 118, 132, 158, 170) passes it.
4. S3 §6 lists no `eval`, `exec`, `compile`, or `open`. CONFIRMED: grep finds only `re.compile`, and `literal_eval` appears only in code_analysis.py.
5. §12.3 row 36 says every internal regex is linear in time. REFUTED (R-E2).
6. §12.3 row 26 says only `PREBUILT_MAX_SNIFF_CHARS` characters are sniffed. CONFIRMED (csv_tables `detect_csv_dialect` and `_support.parse_csv_table`), and `csv.field_size_limit` is never called.
7. §12.3 row 23 says direct `SequenceMatcher` uses pass `autojunk=False`. CONFIRMED (text_comparison.py:102, 137, 151).
8. INV-13 and the seeded_random header say each call builds its own `random.Random(seed)`. CONFIRMED (seeded_random.py:64-135); no global generator call.
9. §9.2 item 16 says the decimal context is set explicitly. REFUTED for 8 sites (R-E8); it holds for exact_arithmetic and number_formatting.
10. EC-39 says the JSON scan is bounded. CONFIRMED: the worst case found is 1.076 s at 100,000 characters (`[`×900 + `0,`…).
11. EC-41 says the root-copy chain is refused. CONFIRMED for memory (the test passes). The CPU side is not bounded (R-E6).
12. The test-plan coverage map lists the count tests with no timeout. CONFIRMED (resource_bounds header, lines 8 and 11).
13. INV-19 says deep XML and TOML array nesting fail cleanly. CONFIRMED: 140,000-deep XML → `ToolExecutionError` in 0.12 s; TOML arrays and inline tables 5,000 deep → 0.002 s. The dotted-key form is the exception (R-E4).

## COMMANDS RUN

- `git diff origin/main...0fd73086 --stat`, `git status --short`, `git log -1`; `wc -l vidbyte/tools/builtins/prebuilt/*.py`; greps over prebuilt/*.py for `localcontext`, `hashlib`, `SequenceMatcher`, `random.Random`, `re.compile`, and banned calls.
- `PYTHONPATH=$(pwd) timeout 600 python -m pytest -q -p no:cacheprovider tests/features/prebuilt_tools` → `4310 passed in 20.48s`.
- Probe harness (scratchpad, outside the worktree): `PYTHONPATH=$(pwd) timeout N python -u - <<'EOF' … call(name, args, mem=True) … EOF`, which uses `FunctionTool.execute` with optional tracemalloc peaks. Used for every measurement above, including host decimal-context probes (`getcontext().traps[Inexact]=True`, `Emax=5`).
- Adversarial sweep (scratchpad `sweep.py` plus `run_sweep.sh`): 100 tools that take text, 38 repetitive shapes at the schema cap (up to 1,000,000 characters), 4 parallel workers, `timeout 150` per tool. Only `toml_to_json` timed out; every other call took ≤ 1.20 s.
- Raw `html.parser` timing on `/c/Users/422mi/AppData/Local/Programs/Python/Python313/python` (3.13.1).
