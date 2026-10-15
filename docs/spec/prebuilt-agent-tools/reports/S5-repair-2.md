# S5 repair, iteration 2 of 8 — prebuilt-agent-tools

- PR: https://github.com/cerredz/Vidbyte-SDK/pull/1072
- Branch: `feat/prebuilt-agent-tools`
- Start HEAD: `2dba19ac`. Code commits: `202ef85f`, `9f7b70ac`, `70298784`. The docs commit follows them.
- Test baseline: `0c055c40`. `git diff --stat 0c055c40 HEAD -- tests/` is empty, and `spec.md` and `test-plan.md` are untouched.

## Outcome
- R-15, R-16 and R-17 are fixed. M-6 was spec drift, which the spec author fixed in r7 (`70df9458`).
- The orchestrator's A.29 consistency case (`extract_numbers` of `0e5000`) is fixed in its own `[gate:pack]` commit.
- The pack went from `33 failed, 4364 passed` to `4397 passed`. Every local gate is green.
- No remote checks are configured: CI is `workflow_dispatch` only, and nothing was dispatched.
- review.md statuses:
  - R-15 and R-17: `fixed @202ef85f`, each noting it landed with the other.
  - R-16: `fixed @9f7b70ac`.
  - M-6: `fixed @70df9458 (spec author r7)`.
  - Every other row is unchanged.

## Findings → commits
| ID | Commit | Fix |
|---|---|---|
| R-15 + R-17 | 202ef85f | `structured_formats._has_long_dotted_key` now runs one `finditer` over `_TOML_SCAN_PIECE`, whose alternatives are a comment, a multi-line basic string, a multi-line literal string, and a dotted run. Only the run alternative is counted. `_TOML_KEY_SEGMENT`'s closing quotes are optional, so an unclosed one-line segment ends at its line end. The pattern is the verifier's prototype with one change, explained below: the multi-line content is unrolled inside its atomic group. |
| R-16 | 9f7b70ac | `parse_data_size`: `_NUMBER_PREFIX` names `mantissa` and `exponent`. `far = abs(int(exponent)) > PREBUILT_MAX_DECIMAL_TEXT_CHARS`, and a far exponent builds `Decimal(mantissa)` only. The existing float check refuses a huge size; the mantissa's sign refuses a negative one; `tiny = far or …` gives 0 bytes. This is the verifier's code, with its comments rewritten for accuracy. |
| A.29 case | 70298784 | `extract_numbers._number_entry`: a far exponent builds `Decimal(mantissa)` only. Zero gives `"0"`; any other value is skipped as before, because its plain text would pass the DecText cap. |

## The one deviation from the verifier's prototype, and why
The prototype matched multi-line string content as `(?>(?:[^"\\]|\\[\s\S]|"(?!""))*)`. That is a greedy group repeat inside an atomic group, and Python's `re` keeps one backtracking entry for each repetition of a group. I measured it with tracemalloc (`scratchpad/s5-2/toml_memory_ml.py`, `scan_memory.py`):

| Input (999,991 characters) | prototype | committed | `tomllib.loads` itself |
|---|---|---|---|
| `s = """` + `a.`×499,990 + `a"""` (ordinary content) | 0.102 s, **122.7 MB** | 0.002 s, **0.0 MB** | 1.0 MB |
| the same in `'''` | 0.097 s, 122.7 MB | 0.000 s, 0.0 MB | 1.0 MB |
| `"""` + `\"`×499,990 + `"""` (escapes) | 0.053 s, 62.8 MB | 0.054 s, 62.8 MB | 0.5 MB |
| `"""` + `"a`×499,990 + `"""` (lone quotes) | 0.105 s, 122.3 MB | 0.055 s, 62.6 MB | 1.0 MB |
| `'''` + `'a`×499,990 + `'''` (lone quotes) | 0.102 s, 122.3 MB | 0.033 s, 40.0 MB | 1.0 MB |

The committed form keeps the atomic group that spec r7 row 27 requires, and reads plain characters as single-character possessive runs inside it:
- basic: `"{3}(?>[^"\\]*+(?:(?:\\[\s\S]|"(?!""))[^"\\]*+)*)(?:"{3,5}+)?`
- literal: `'{3}(?>[^']*+(?:'(?!'')[^']*+)*)(?:'{3,5}+)?`

Only an escape or a lone quote now holds a backtracking entry. The piece split is unchanged:
- **Against the prototype:** over 200,000 random texts (`toml_split_dump.py` with the override `variant_unrolled.py`), the split is identical on 3.11.0 (hash `9f93184566131e7e`) and identical on 3.13.1 (hash `f4b0d2c092740783`).

A remaining worst case stays: ≈125 bytes for each escape or lone quote inside one multi-line string, so 62.8 MB at the cap. It is transient, and it is linear and bounded by the 1,000,000-character cap. I record it below for the re-reviewer rather than closing it, because the zero-memory alternative contradicts row 27's wording.

## Hypotheses tried and rejected
1. **Make the dotted run's outer repeat atomic too**, `(?>(?:[ \t]*+\.[ \t]*+(?:SEG))*)`. Rejected.
   - **Why it was tried:** on my wider corpus, the prototype's piece-split hash differs between 3.11.0 and 3.13.1: 25,585 of 200,000 texts.
   - **What the difference is:** every one of those differences is the end position of a run, and none is a segment count or another piece (`toml_split_diff2.py`). On 3.11.0, a failed final possessive iteration keeps its `[ \t]*\.[ \t]*`, so `a.` matches `a.` on 3.11.0 and `a` on 3.13.1.
   - **Why that is harmless:** the extra characters are space, tab or dot, and none of them starts a piece. A segment fails only at its first character, because both closing quotes are optional. So the piece sequence, every segment count, and therefore the verdict are the same on both interpreters. The dot count is only a necessary prefilter.
   - **What the change did:** it made the split hashes identical (`f4b0d2c092740783` on both).
   - **Why it was rejected:** it cost **77.2 MB** peak on a 500,000-segment run, against 0.0 MB for the possessive repeat, and doubled the time (0.046 s → 0.10 s through the tool).
   - **Where it is recorded:** the module header's KNOWN EDGE CASES now records the benign 3.11.0 end-position difference.
2. **Make the quoted segment's content atomic as well.** Rejected. It gave no difference on either interpreter, so it changed nothing.
3. **Constant-only R-15 fix.** Not tried. The verifier showed it widens R-17, and the briefing lists it as exhausted.

## Verification beyond the pack
- **TOML differential fuzz** (`toml_fuzz_timing.py`, through the real `_has_long_dotted_key`):
  - 55,175 valid texts that hold a 101-segment inline-table key after random strings of all four kinds and an optional comment: **0 misses**.
  - 55,934 valid texts with keys of at most 5 segments, strings, and trailing comments: **0 over-refusals**.
- **TOML cap-size timings through `FunctionTool.execute` on 3.11.0** (every EC-51 shape, plus controls):

  | Shape | Time |
  |---|---|
  | comment of escaped quotes | 0.012 s |
  | open basic string of escaped quotes | 0.128 s |
  | `"""`×333,333 | 0.024 s |
  | `'''`×333,333 | 0.020 s |
  | R-6 bare, header and inline forms | 0.046–0.048 s |
  | the three R-17 shapes | ≤ 0.049 s |
  | run in a comment | 0.006 s |
  | run in a multi-line basic string | 0.051 s |
  | run in a multi-line literal string | 0.012 s |
  | quoted-segment key | 0.042 s |
- **R-16 differential sweep** (`data_size_sweep.py`): 11,739 calls compared with an exact oracle written from the A.27 row.
  - Inputs: 13 mantissas, 22 exponents (exponents of 18, 19, 20 and 150 digits included), `e` and `E`, and 7 units.
  - Contexts: the default, `Context(traps=[])`, and the R-12 hostile context.
  - Result: **0 mismatches, 0 leaked error types**.
- **A.29 probe** (`numbers_probe.py`): `0e5000`, `-0e5000`, `0.000E-99999999999999999999`, `0,000e…%`, and `0e4003` beside `0e4002` all give `"0"`. `1e5000`, `1e-99999999999999999999`, and `-1e99999999999999999999` are skipped. The results are the same under all three contexts.

## Gate matrix (final lines quoted)
| # | Gate | Command | Result | Final lines |
|---|---|---|---|---|
| — | new tests (the 45 r7 cases) | `pytest … -k "toml or data_size or extract_numbers or far_exponent"` over the four files | PASS | the 33 red cases are now green; full pack below |
| 1 | pack | `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider -o faulthandler_timeout=120 tests/features/prebuilt_tools` | PASS | `4397 passed in 43.29s` |
| 2 | lint | `PYTHONPATH=$(pwd) python lint/run.py` | PASS | `S063 RATCHETED: 4 known finding(s).` / `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS`; 0 REGRESSED and 0 ERRORED |
| 2b | typecheck | `PYTHONPATH=$(pwd) python lint/run.py --rule S009` | PASS | `S009 RATCHETED: 350 known finding(s).` / `SDK-LINT: PASS` |
| 3 | import sort | `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` | PASS (inherited only) | whole tree: `Found 223 errors.` (base count). The 40 PR `vidbyte/*.py` files since merge-base `8387d666` with `--select I001,F401`: `All checks passed!` |
| 4 | semgrep | `PATH=…/semgrep-venv/Scripts:$PATH semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS | `• Findings: 0 (0 blocking)` / `Ran 1 rule on 931 files: 0 findings.` |
| 5 | public API | `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` |
| 6 | source stage | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS (on the rerun) | first run: `1 failed, 8411 passed, 13 skipped in 83.80s` / `CI failed: Command failed with exit code 1: …python.exe -m pytest`. The failure was `tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport`, a 5 s `wait_for` `TimeoutError` in a subprocess test. That file passes 3 of 3 times alone (`22 passed in 2.23s`), and no MCP file is in the PR. Rerun: `8412 passed, 13 skipped in 79.16s (0:01:19)` / `CI passed.` |
| 7 | package stage | `env -u PYTHONPATH python scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| 8 | remote | `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1072` | none configured | `no checks reported on the 'feat/prebuilt-agent-tools' branch` (CI is disabled repo-wide; nothing was dispatched; code pushed at `70298784`) |

## Test changes proposed
None. No test contradicts r7.

## Findings I believe are wrong
None.

## Points for the final re-review (not open findings)
1. **Worst-case regex memory in the TOML scan:** ≈125 bytes for each escape or lone quote inside one multi-line string, 62.8 MB at the 1,000,000-character cap. Ordinary content costs 0 MB. It is transient, and `tomllib` itself uses about 1 MB on the same text. Two zero-memory forms exist, and neither is clean:
   - A possessive repeat with the lookahead first, `(?:[^"\\]++|\\[\s\S]?|(?!""")"{1,2}+)*+`, which contradicts row 27's "atomic group, not a possessive repeat" and would need a spec change and its own cross-version proof.
   - Moving the multi-line lookup out of the single pattern, against row 27's "one compiled pattern".
2. **The 3.11.0 end-position difference** of a dotted run, which is benign as shown above. It is documented in the module header.

## Niche facts
- `tr '\\' '/'` in this Bash halves the backslash. To compare ruff's Windows paths, run ruff on the PR's file list directly instead.
- `core.autocrlf=true`: the index holds LF for every prebuilt file, and `file` reports CRLF in the working copy for `bits_bytes.py` and `structured_formats.py`. Python edit scripts must keep each file's working-copy endings. `git ls-files --eol` shows `i/lf` before and after.
- A greedy group repeat, even inside an atomic group, costs one backtracking entry for each repetition, about 120–155 bytes. Possessive group repeats and single-character runs cost none. Measure with tracemalloc before you adopt any `(?>(?:…)*)`.
- The 3.11.0 `re` keeps the consumed part of a failed final iteration of a possessive group repeat. In this scan that is harmless only because each segment can fail at its first character alone. If you change `_TOML_KEY_SEGMENT` so that a segment can fail after consuming characters, re-run `toml_split_dump.py` and `toml_split_diff2.py` on 3.11.0 and on `py -3.13`.
- The source stage can fail once under load on `test_mcp_stdio_transport.py::…test_cancelled_waiter_does_not_break_transport`, which hits a 5 s asyncio subprocess timeout on Windows. Run that file alone, then rerun the stage before you call it a regression. Iteration 1 never hit it.
