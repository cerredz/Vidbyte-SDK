# S4 findings verifier: working notes

Stage: S4 findings verifier. Worktree HEAD is `8e283e51`, which adds only docs on top of `0fd73086`, so the reviewed code is `origin/main..0fd73086`. I made no commits and edited no source. The only files written are `review.md` and this report. Every probe ran from scratch scripts or heredocs outside the worktree.

## Inputs and method

**Inputs read:**
- `spec.md`, `request.md`, `test-plan.md`
- `context/code-map.md`
- `reports/S3-implementer.md`
- `reports/S4-review-conformance.md` (R-C1..R-C4), `reports/S4-review-conventions.md` (R-V1..R-V7), `reports/S4-review-engineering.md` (R-E1..R-E9)

**Method:**
1. **Read the code.** For every Blocker and Major, I read the cited lines at HEAD.
2. **Reproduce.** I reran the finding through `FunctionTool.execute` with the harness in review.md, under `timeout 120`, with `-u`, `PYTHONPATH=$(pwd)`, and `PYTHONDONTWRITEBYTECODE=1`.
3. **Time it.** Every time is wall time on Python 3.11.0. I used doubling inputs to separate a quadratic cost from a linear one.
4. **Prototype the fix.** Where a fix was proposed, I prototyped it in memory by monkeypatching from a scratchpad module, then reran the probe and the pack.
5. **Recheck the conventions.** I checked each convention finding against AGENTS.md, the field guide named in the spec, and §12.4. A reviewer's fix was treated as a proposal and tested before it went into the review.

**Scratch location:** `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/c033bb4d-236f-4839-b20c-c5c2bef451e8/scratchpad/s4v/`, which holds `vh.py`, `rawhtml*.py`, and `fixprobe.py`. On Windows, putting the scratchpad on `PYTHONPATH` did not work, so the probes call `sys.path.insert`. Printing `′` needed `PYTHONIOENCODING=utf-8`.

**Second interpreter:** a patched CPython 3.9.25, used for the R-8 comparison only, at `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8d0cc61b-7759-4726-ae02-a99db84e33e6/scratchpad/uv-py/cpython-3.9.25-windows-x86_64-none/python.exe`.

## Merge map

| Original | Lens | Original severity | Merged ID | Final severity | Note |
|---|---|---|---|---|---|
| R-E5 | engineering | Blocker | R-1 | Blocker | |
| R-E2 | engineering | Blocker | R-2 | Blocker | Reviewer fix refuted; replaced |
| R-C2 | conformance | Blocker | R-3 | Blocker | |
| R-V4 | conventions | Major | R-4 | Blocker | Raised (see adjudication) |
| R-C1 | conformance | Blocker | R-5 | Blocker | |
| R-E4 | engineering | Blocker | R-6 | Blocker | Reviewer fix incomplete; extended |
| R-E1 | engineering | Blocker | R-7 | Blocker | |
| R-E3 + [verifier] | engineering | Blocker | R-8 | Blocker | INV-12 cross-patch defect added |
| R-E6 | engineering | Major | R-9 | Major | |
| R-E7 | engineering | Major | R-10 | Major | Reviewer fix does not help; decision needed |
| R-V3 | conventions | Major | R-11 | Major | Kept Major |
| R-E8 | engineering | Major | R-12 | Major | |
| R-V1 (main copies) + R-C3 + R-V2 FR-8 part | conventions + conformance | Blocker / Major / Major | R-13 | Major | R-V1 downgraded |
| R-E9 | engineering | Major | R-14 | Major | |
| R-C4 | conformance | Minor | M-1 | Minor follow-up | |
| R-V5 | conventions | Minor | M-2 | Minor trivial | |
| R-V6 | conventions | Minor | M-3 | Minor trivial | |
| R-V7 | conventions | Minor | M-4 | Minor trivial | |
| R-V1 (lower-value copies) | conventions | Blocker | M-5 | Minor follow-up | |
| R-V2 INV-15 part | conventions | Major | — | Refuted | |

**Totals:** 8 Blockers, 6 Majors, 5 Minors, 1 refuted (the INV-15 part of R-V2), and 1 downgraded (R-V1). **Verdict:** MERGEABLE AFTER FIXES.

## Verification of each finding

All `path:line` references are under `vidbyte/tools/builtins/prebuilt/` unless stated.

### R-1 (R-E5): confirmed Blocker
- **Code:** `markdown_html.py:44` `_ATX_CLOSING`, used through `.sub(count=1)` at `:274`.
- **Probe:** `extract_markdown_headings` with `"# a" + " "*k + "#x"`. Measured 0.247 s at k=25,000, 0.966 s at k=50,000, and 3.843 s at k=100,000. The time grows 4× per doubling, which is quadratic. That extrapolates to about 6 minutes at 1,000,000 characters.
- **Fix prototype:** `(?:^|(?<![ \t])[ \t]++)#++[ \t]*+$`.
  - The 1,000,000-character case takes 0.093 s.
  - The sample headings `# Title ##  `, `## B #`, `### C#`, and `# D \#` are unchanged.
  - The pack passes with it loaded (see Commands).
- **Tier:** Blocker. NFR-7 and T-2 set a hard 2 s bar at the cap, this tool has no EC exception, and the result is a broken call.

### R-2 (R-E2): confirmed Blocker; reviewer fix refuted
- **Code:** `text_extraction.py:56` `_AMOUNT`, shared by `_NUMBER` (`:67`) and `_MONEY` (`:78`). The module header (lines 5 and 8) and A.29 both claim linear time.
- **Timings:**

  | Call | 40,002 chars | 80,002 chars |
  |---|---|---|
  | `extract_numbers` on `"1"+",000"*n+"0"` | 0.908 s | 3.294 s |
  | `extract_money_amounts` on `"1"+",000"*n` | 1.643 s | 6.546 s |

- **Reviewer's fix tested:** `(?<![0-9],)` placed in front of the whole `{_AMOUNT}`.
  - `values 1,2,3` gives only `1`.
  - `10,20,30` gives only `10`.
  - `1,2345` gives only `1`.
  - It breaks comma-separated lists, which the row covers ("a sign counts … after `,`"). Refuted as the repair.
- **My fix:** guard only the grouped-chain alternative, `(?:(?<![0-9]{3},)(?>[0-9]{1,3}(?:,[0-9]{3})++)|{_DIGITS})`.
  - Timings at 1,000,000 characters: 0.077 s and 0.177 s.
  - **Fuzz:** 200,000 random strings of 1 to 16 characters, drawn from the digits (weighted 3×) plus `,,,.. $€xUSDk%e-+`. 92 `_NUMBER` results and 8 `_MONEY` results differ, and every one is a malformed grouping such as `-9467,8,109e9`, which now gives `8` and `109e9` instead of `8,109e9`.
  - Lists `1,2,3` and `10,20,30` are unchanged.
  - **Tests:** with this variant loaded, the extraction, error-contract, and resource-bounds files pass (325).
- **Variant:** `(?<![0-9],)` applied to the chain alternative only also runs in linear time and differs on 70 of 60,000 fuzz strings, for example `1,8,779`. I ran the full-pack prototype with this variant. Either variant is acceptable, and the test author should pin `1,2,3` and `1,000,0000`.

### R-3 (R-C2): confirmed Blocker
- **Code:** `network_addresses.py:77` calls `.exploded` on the parsed address.
- **Probe on 3.11.0:**
  - `fe80::1%eth0` gives `error AddressValueError Only hex digits permitted in '1%eth0' in 'fe80::1%eth0'`.
  - `::ffff:1.2.3.4%x` gives the same error class.
- **3.13.1:** raw `ipaddress.ip_address("fe80::1%eth0").exploded` also raises, so the failure is not version-specific.
- **Other network tools on scoped input:** `classify_ip_address`, `ip_in_networks`, `ip_range_to_cidrs`, `cidr_network_details`, `split_cidr_into_subnets`, and `extract_ip_addresses` all succeed. Only this tool leaks.
- **Fix:** `IPv6Address(int(parsed)).exploded` plus `%scope_id`, which gives `fe80:0000:0000:0000:0000:0000:0000:0001%eth0`.
- **Tier:** Blocker, because INV-14 is absolute.

### R-4 (R-V4): confirmed; raised from Major to Blocker
- **Scan:** all 910 built descriptions (265 tools plus every parameter), searched with one regex for `true`/`false`/`null` near "equals" or "matches" and a digit, "the number N" or "the string N", "N equals" or "N matches", "such as" or "like" before a quote, and any quoted literal. After removing the 1,000-match cap phrases, exactly three remain:
  - `json_data.py:181` (`diff_json_documents`)
  - `json_records.py:113` (`group_records_by_field`)
  - `json_records.py:200` (`join_records.left_field`)
  - The quoted texts are in review.md.
- **Why the pack misses them:** its `EXAMPLE_MARKERS` looks for "for example", "e.g.", and similar markers, so the pack cannot catch the "so the number 1 …" form.
- **Adjudication:** see below.

### R-5 (R-C1): confirmed Blocker
- **Code:** `json_data.py:249` builds `json.JSONDecoder(parse_constant=constants.append)` with no `parse_float`. The skip at `:268` tests only `constants`.
- **Probes:**
  - `'x {"a":1e400} y'` gives `success {"count": 1, "documents": [{"end": 13, "start": 2, "value": {"a": Infinity}}], "truncated": false}`.
  - `json.loads(output, parse_constant=reject)` raises `non-finite Infinity`.
  - `'{"a":-1e999,"b":[1E309]}'` gives `-Infinity` and `Infinity`.
  - The literal `Infinity` token is already skipped.
- **Fix check:** a `parse_float` that calls `partial(_noted_float, constants)` records `1e400` and `1E309` and does not record `1.5`.
- **Tier:** Blocker. INV-11 says floats are always finite, and the output is not JSON.

### R-6 (R-E4): confirmed Blocker; reviewer fix extended
- **Code:** `structured_formats.py:168` calls `tomllib.loads`. The nesting check at `:179` runs only after the parse returns.
- **Timings:**

  | Form | n | Time |
  |---|---|---|
  | bare `a.a…=1` | 5,000 / 10,000 / 20,000 / 30,000 | 0.120 / 0.483 / 1.984 / 4.612 s |
  | header `[a.a…]` | 80,000 / 160,000 | 2.98 / 16.95 s |
  | inline `x={a.a…=1}` | 80,000 / 160,000 | 2.84 / 17.92 s |

  Every case ends in the correct nesting `ToolExecutionError`.
- **Reviewer's fix:** check the key part of each line before the first `=`. That misses the inline-table form, where the dotted key sits after `=`.
- **My prototype:** one possessive `finditer` over dotted runs of bare or quoted segments, counting separators outside quotes, and refusing a run of more than `PREBUILT_MAX_JSON_NESTING` segments.
  - All three forms take about 0.05 s at 1,000,000 characters.
  - A 100-segment key and an 800,000-character dotted string value are accepted.
  - A 101-segment key is refused, as it already is after the parse.
- **Residual over-refusal:** a matching run inside a multi-line string or a comment. It is noted in review.md.

### R-7 (R-E1): confirmed Blocker
- **Code:** `structured_formats.py:130` calls `root.findall(path)` and materializes the full list.
- **Blow-up probe:** document `"<a>"*60+"</a>"*60` (420 characters), path `"."+"//a"*6` (19 characters).
  - Result: `count 45057474` in 2.573 s.
  - With tracemalloc, the peak is 366,533,767 bytes and the run takes 6.395 s.
  - Each extra step multiplies the count by about 9. I did not run the 7-step case, which would need about 3.3 GB.
- **Wrong-result probes:**
  - `.//a//a` on `<r><a x='1'><a x='2'><a x='3'/></a></a></r>` gives count 3 with `x=2, x=3, x=3`, a duplicate.
  - On the 60-deep chain it gives count 1711, but 58 distinct elements match.
- **Prototype:** lazy `iterfind`, a yield bound of 1,000,000, de-duplication by `id`, and ordering by the index in `root.iter()`.
  - It gives `[x=2, x=3]` and 58.
  - It refuses the 6-step and 7-step paths in 0.05 s.
  - `.//b` over 150,000 siblings takes 0.04 s.
- **Spec impact:** the A.20 row names `findall` and lists its errors, so the orchestrator must update the row.

### R-8 (R-E3 + [verifier]): confirmed Blocker
- **Code:** `text_transform.py:280-281` and `markdown_html.py:182-184` / `:225-227`, which call `feed()` then `close()`.
- **Tool timings on 3.11.0** with `"<a "*k`:

  | Tool | 6,000 chars | 12,000 chars | 24,000 chars |
  |---|---|---|---|
  | `strip_html_tags` | 0.219 s | 1.847 s | 11.358 s |
  | `extract_html_links` | | | 11.411 s |
  | `html_table_to_records` | | | 11.287 s |

- **Raw stdlib comparison:** `HTMLParser().feed(s); close()` on the 24,000-character input.
  - 11.526 s on 3.11.0.
  - 0.005 s on patched 3.9.25.
  - This confirms CVE-2025-6069 (gh-135462), which is fixed in 3.11.13, 3.12.11, and 3.13.4. This machine has 3.11.0 and 3.13.1.
- **Where the cost is:** `feed()` alone takes 0.004 s; the whole cost is in `close()`.
- **Tail-only pre-pass is not enough:** `"<!--x>"*k`, where each piece is closed by `>`, still takes 2.163 s at 120,000 characters on 3.11.0.
- **[verifier] blind spot:** the patched and unpatched stdlib differ in end-of-input output. For `x <b`, the raw parser data is `'x <b'` on 3.11.0 and `'x '` on 3.9.25. The tool output therefore depends on the CPython patch level within one minor version, which breaks INV-12 (same input, same output). No reviewer raised this.
- **Fix prototype:** one helper that, after `feed()`, drops the unparsed tail when it starts with `<` and is not exactly `<` or `</`, then calls `close()`.
  - All three tools take ≤ 0.18 s at 1,000,000 characters on `<a `, `<a b='`, and `<!--x>`.
  - `x <b` gives `x` on 3.11.0, which matches the patched behavior.
  - The pack passes with it loaded.
- **Alternatives rejected:**
  - Lowering the cap is pinned by S2 and would need about 12,000 characters.
  - Requiring a patch release changes `pyproject.toml`, which is out of scope.
  - Accepting the cost as a new EC is a spec decision, and it would still leave INV-12 broken.

### R-9 (R-E6): confirmed Major
- **Code:** `json_data.py:203-228` loops over up to 1,000 operations. `_measured_insertion` (`:407-428`) bounds each value's size but not the cumulative work.
- **Probe:** doc `{"a":[0]*m}`, patch 500 × (copy `/a`→`/b`, remove `/b`), about 38,000 characters.
  - m=50,000: 6.381 s.
  - m=100,000: 13.128 s.
  - m=200,000: 25.878 s.
  - 1,000 alternating moves on the 400,007-character doc take 13.026 s.
  - The cost is linear in work, at about 64 ns per character.
- **Tier:** Major rather than Blocker. The cost is bounded (about 1,000 × 1 MB) and degrades linearly, with no superlinear blow-up. It still misses NFR-7 by more than 10×, and EC-41 covers only memory.

### R-10 (R-E7): confirmed Major; reviewer fix does not help
- **Code:** `text_counting.py:92-96` (an overlapping lookahead, plus a case-insensitive `re.escape` with `IGNORECASE`) and `text_transform.py:206-221`, each with two passes.
- **Probe:** text `"a"*n`, search string `"a"*9999+"b"`.

  | Call | n=200,000 | n=400,000 |
  |---|---|---|
  | `find_substring_positions`, default mode | 2.022 s | 4.122 s |
  | `find_substring_positions`, case-insensitive | 5.143 s | 10.542 s |
  | `replace_all_occurrences`, case-insensitive | 2.565 s | 5.248 s |

  A case-sensitive search without overlap takes 0.003 s.
- **Reviewer's `str.find` loop:** with dense matches, `"a"*5000` in 1,000,000 `a`s takes 8.686 s, and 1.646 s at 200,000. It does not fix the problem.
- **Measured option:** lower the search-string cap to 1,000. At 1,000,000 characters that gives 1.031 s by default, 2.695 s case-insensitive with two passes (about 1.35 s with one), and 1.355 s for replace.
- **Decision needed:** the cap is pinned by S2 in `prebuilt_parameter_data.py`, so the fix belongs to the test author and the orchestrator. The alternative is an EC-46-style accepted limit.
- **Tier:** Major, because no single-line fix exists within the current caps.

### R-11 (R-V3): confirmed Major (kept)
- **Code:** `_support.py:125` calls `parse_json_text`, which calls `nesting_level` (`:100`) and `argument_error` (`:86-98`). That is three levels inside one class.
- **Callers:** `json_records.py` lines 94, 105, 114, 129, 144, 169, 183, 205, 206, and 232.
- **Tests:** `grep -rn parse_records_json tests` returns nothing.
- **Documents contradicted:** README `:67` and §17 deviation 2.
- **Adjudication:** see below.

### R-12 (R-E8): confirmed Major
- **Code:** the eight `localcontext(prec=…, rounding=…)` sites listed in review.md. `asyncio.to_thread` copies the caller's contextvars, and the decimal context is one of them.
- **Probe with host traps:** `decimal.getcontext().traps[Inexact] = traps[Rounded] = True` set before `asyncio.run`.
  - `compound_interest_future_value(1000, 5, 10)` gives `'years': the future value leaves the decimal range`.
  - `decimal_degrees_to_dms(0.000875, latitude, 1)` gives `error_type: Inexact` with the output `[<class 'decimal.Inexact'>, <class 'decimal.Rounded'>]`.
- **Probe with `decimal.setcontext(Context(Emax=5))`:** `decode_jwt_payload`, `parse_duration_text("1h 30m")`, and `unix_timestamp_to_datetime(1.5)` each give `error_type: Overflow`.
- **Contrast:** `exact_arithmetic` and `number_formatting` use an explicit `Context` and are unaffected.
- **Isolation:** each probe ran in its own Python process, so the altered host context never reached any other run.
- **Tier:** Major. It needs a host that changes its decimal context, but the spec names exactly that case in §9.2 item 16.

### R-13 (R-V1 + R-C3 + R-V2 FR-8): confirmed Major
- **Check:** I read every listed copy.
  - (a) Base64: the five constants and the steps are identical in `encoding.py` and `hashing.py`.
  - (b) Natural sort: the two keys differ in shape, but read side by side they split digit runs the same way and compare runs the same way, so they order the same. Numeric order and the run regex are identical.
  - (c) Delimiter tables: three copies, one of them a mutable dict at `_support.py:60`.
  - (d) The JsonType table and (e) the IntText, DecText, and UtcOffset patterns are textually identical across files.
  - (f) Name-list shortening: four copies. `_REPORTED_COLUMNS = 20` and `_SHOWN_CYCLE_NAMES = 20` duplicate `PREBUILT_MAX_REPORTED_NAMES`, against FR-8.
- **Adjudication:** see below.

### R-14 (R-E9): confirmed Major
- **Pack:** `4310 passed` at HEAD with R-1 through R-12 all present.
- **Grep:** the pack has no `1e400`, no `%eth`, and no zone case. The only `1e999` case is in `python_literal_to_json`.
- **Count tests:** the header of `test_prebuilt_resource_bounds.py` (`:9`) and test-plan `:195` say they hang rather than fail.
- **Fix:** test author. The liveness-guard proposal is a hang detector with a ceiling at least 30× the fixed runtime, so it is not a timing assertion. Rule 3 belongs to S2, so the orchestrator decides.

## Adjudications

- **R-V1 (Blocker) against R-C3 (Major) on duplication: merged into R-13 as a Major.**
  - R-V1 treated principle 5 as mandatory. Its mandatory clause concerns canonical helpers in `vidbyte/lib/` for jobs that recur across features, and it says logic "that only one feature will ever need can stay with that feature".
  - Inside the feature, D-14 and the PR's own README (`:67`, "each rule exists exactly once") govern. Breaking them is a real gap a human reviewer would flag, which makes it a Major.
  - Behavior is identical today, so nothing is wrong, unsafe, or broken, which a Blocker would require.
  - The lower-value copies went to M-5.
- **R-V4 raised from Major to Blocker.** The rubric makes contradicting a field-guide lesson a Blocker. INV-9 states the rule outright ("No description contains a concrete example value"), the owner enforced the field guide `model-facing-tool-contracts.md` on PR #337 and PR #342, and no test can catch this form. The text is model-facing, so the defect ships to every agent that loads these tools.
- **R-V3 kept at Major.**
  - **Against Blocker:** principle 1 is worded "should not" and is "the shape to aim for". Row 6's own signature (text in, records out) forces the hop. Behavior is unaffected.
  - **For Major:** the README and §17 state the opposite of the code, and a human reviewer would catch it.
- **R-V2 split.**
  - **INV-15 part refuted.** The spec's own `fill_text_template` row demands up to 20 names in the message. A 25-placeholder probe produced a 1,417-character message whose longest contiguous echo is 60 characters. INV-15's 100-character limit is therefore per echoed span, and the code honors it.
  - **Reviewer's fix:** capping count × length at 100 would break the row.
  - **FR-8 part:** confirmed and merged into R-13(f).
- **Reviewer fixes refuted or extended:**
  - R-E2's lookbehind breaks comma lists, and the fix was replaced.
  - R-E4's per-line check misses inline tables, and the fix was extended.
  - R-E7's `str.find` loop is still slow on dense matches, so a cap decision is needed.
- **Decisions already made:** no finding asks to reverse D-7 or any listed decision.
  - R-10 does not ask for a per-tool timeout. It asks for a cap or an EC.
  - R-8 does not ask to require tzdata or a new Python. That option was rejected.
  - R-2 does not touch `seeded_weighted_choice` (EC-45).

## Blind-spot checks

- **Every `re.compile` in the 34 modules, checked for the R-1 and R-2 shape** (an unanchored repeat that a failed search can restart at every position):
  - `_SENTENCE_END` has a lookbehind guard.
  - `_WORD_BEFORE_END` searches a bounded window.
  - `_MARKDOWN_LINK` is possessive and anchored at a delimiter.
  - `_TEMPLATE_FIELD` is linear.
  - No new quadratic pattern was found.
- **`regex_split`:** lazy, with an arithmetic count. This was confirmed.
- **Cross-patch output stability of the HTMLParser tools:** found the INV-12 defect, folded into R-8 as `[verifier]`.
- **Convention fixes that would break conformance:**
  - R-V2's fix would break the `fill_text_template` row (refuted).
  - R-E2's fix would break comma lists (replaced).
  - The R-13 helper constraints (principle 1, no C006/C008 prefixes, no A007 tokens) are written into the fix so it does not create new lint or convention findings.

## Commands run and their final lines

**Pack at HEAD `8e283e51`, unpatched (rerun just before writing this report):**
```
$ PYTHONPATH="$(pwd)" PYTHONDONTWRITEBYTECODE=1 timeout 300 python -u -m pytest -q -p no:cacheprovider tests/features/prebuilt_tools
........................................................................ [ 96%]
........................................................................ [ 98%]
..............................................................           [100%]
4310 passed in 21.07s
```
An earlier run of the same command ended in `4310 passed in 21.11s`.

**Pack with the R-1, R-2 (chain-only `(?<![0-9],)` variant), and R-8 prototypes from the scratchpad's `fixprobe.py` applied in memory, so no worktree file changed:**
```
........................................................................ [ 96%]
........................................................................ [ 98%]
..............................................................           [100%]
4310 passed in 20.41s
```

**Extraction, error-contract, and resource-bounds files with the recommended R-2 variant `(?<![0-9]{3},)`:**
```
325 passed in 6.87s
```

**Worktree state after writing both files:**
```
$ git rev-parse --short HEAD
8e283e51
$ git status --short
?? docs/spec/prebuilt-agent-tools/review.md
```
This report is also untracked once written. No source file changed.

I ran no lint, CI, or package stage myself. The "What the implementation gets right" list in review.md carries the reviewers' gate results (SDK-LINT, ruff, semgrep) as they reported them. Only the pack runs above are my own.
