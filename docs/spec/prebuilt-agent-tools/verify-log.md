# Verification log: A library of 250+ prebuilt agent tools in vidbyte-sdk

Gate set (from context/code-map.md §1.3, run in CI order from the worktree root):
1. Pack (local): `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/prebuilt_tools`. Expect 4,352 collected, 0 failed.
2. Lint (local): `PYTHONPATH=$(pwd) python lint/run.py` → `SDK-LINT: PASS`. Typecheck alone: `--rule S009`.
3. Import sort (local): `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`. The 223 whole-tree findings are inherited; none is in a file the PR changes. The PR's own files are checked with `--select I001,F401`.
4. Semgrep (local; remote in `static-policy.yml`): `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` → 0 findings.
5. Public API (local): `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` → "is current".
6. Source stage (local; remote in `ci.yml`): `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` → `CI passed.`
7. Package stage (local; remote in `ci.yml`): `env -u PYTHONPATH python scripts/run_ci.py --stage package` → `CI passed.`
8. Remote checks (remote only): `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1072`. CI is disabled repo-wide (`workflow_dispatch` only), and no workflow is dispatched.

## Iteration 1 — 2026-10-14 18:01 — agent report: reports/S5-repair-1.md
**Defects in:**
- Confirmed findings R-1 to R-14, plus Minors M-1 to M-4. M-5 is a follow-up.
- R-14 belongs to the test author, whose regression cases (`c9710ed2`: `test_prebuilt_hostile_inputs.py`, `test_prebuilt_resource_bounds.py`) were red at the start (`adef13e9`).
- Gate failing at the start: the pack, through those regression cases.

**Hypotheses and attempts** (in order, including the ones that failed):
- **R-1:** made the ATX closing run possessive and required the whitespace before it to be preceded by a non-blank: `(?:^|(?<![ \t])[ \t]++)#++[ \t]*+$`. Linear on the hostile input, and output is unchanged.
- **R-2:**
  - Tried first: the reviewer's lookbehind on the whole amount. Rejected, because it drops list items such as `1,2,3`.
  - Used instead: the verifier's guard on the grouped alternative only, `(?<![0-9]{3},)`.
- **R-3:** the scoped-IPv6 explode path now rebuilds the address as `type(parsed)(int(parsed)).exploded` and appends `%scope_id`. The old code crashed with a non-ToolExecutionError.
- **R-4:** reworded the three descriptions so they hold no literal values.
- **R-5 and M-1:**
  - The verifier proposed a `_noted_float` recording hook.
  - The briefing preferred reusing `_support._read_json_float` through `partial`, so that was chosen.
  - extract_json_from_text skips a candidate on the ToolExecutionError the hook raises.
  - verify_json_syntax maps that error to its overflow message.
  - The cost is a cross-class access to a private `_support` member. No lint rule flags it, and spec §17 deviation 2 names these hooks.
- **R-6:** a pre-scan before `tomllib.loads` refuses a dotted key with more than 100 segments. It uses a dot-count prefilter, then an exact possessive segment run. Every probe finished in ≤ 0.25 s.
- **R-7:**
  - Tried first: overriding iteration with `ElementTree.Element.__iter__(self)`. It failed with AttributeError, because the C Element has no `__iter__` and uses the sequence protocol.
  - Used instead: iterate `self[:]`. The counted `Element` subclass has `__slots__ = ("visits",)` and raises `argument_error("path")` past `PREBUILT_MAX_XML_PATH_VISITS` (2,000,000).
  - xml_find_elements now deduplicates in document order.
  - Verification: a 400-tree × 21-path fuzz against stdlib found 0 mismatches.
- **R-8:** the shared `parse_html` helper drops an unfinished `<…` tail at end of input before `close()`. The README gained the EC-47 limitation.
- **R-9:**
  - Change: a work total over the JSON that a patch reads and writes, capped by `PREBUILT_MAX_PATCH_WORK_CHARS`.
  - Problem hit: a variable named `read` tripped A007 ("operational call receives a literal"), so it was renamed `given_length`/`current_length`.
- **R-10:** `PREBUILT_MAX_SEARCH_STRING_CHARS` (500) caps the substring. find_substring_positions now counts all matches in one pass while keeping at most the result cap. A case-insensitive find longer than 500 is refused.
- **R-11:** `records_from_json(value, name)` replaces `parse_records_json`, so callers compose it with `parse_json_text`.
- **R-12:**
  - Change: `PrebuiltToolSupport.decimal_context(prec)` opens a fresh, fully specified context, and it replaced every `localcontext` site. Context-dependent operations outside it became context-free: `copy_negate`, `copy_abs`, and geometry's text formatted inside the context.
  - Problem hit: the first edit script failed on a docstring mismatch and was redone.
  - Problem hit: a long `from decimal import` line tripped S051/I001 and was wrapped.
  - Left unchanged: `format(d, "f")` without a precision, because it is context-free (probed).
  - Verification: 1,921 pack row cases pass under a hostile host context (prec 3, Emax 5, every trap, capitals 0, clamp 1).
- **R-13** (one commit per group):
  - (a) One raising Base64 reader. hashing keeps a thin adapter that turns its error into None, so the HMAC key error still never describes the key. A 200k fuzz against the old hashing reader found 0 differences.
  - (b) `natural_sort_key` and `numeric_order`.
  - (c) An immutable `PREBUILT_CSV_DELIMITER_CHARACTERS` and `csv_row_writer`. The helper returns the bound `writerow`, because the `_csv.Writer` type is not exported by `csv`. No output cap was added to csv_tables.
  - (d) `PREBUILT_JSON_TYPES`.
  - (e) `PREBUILT_INTEGER_TEXT_PATTERN`, `PREBUILT_DECIMAL_TEXT_PATTERN`, and `PREBUILT_UTC_OFFSET_PATTERN`. The pinned schema strings are unchanged.
  - (f) `shortened_names` with `PREBUILT_MAX_ECHO_CHARS` (100), the §9.2 shared shortener constant. This changes some error text:
    - names that used to be cut at 40 or 60 characters are now cut at 100;
    - csv_tables now adds "…" to a name it cuts, like the other three sites.
- **M-2:** renamed `monthly_interest_fraction` and `yearly_interest_fraction`.
- **M-3:** the REPO_MAP toolsets entry now counts the paradigm harness bundle.
- **M-4:** the README now says "more than 4,000 digits", and the `_support` inventory now lists both JSON decoder hooks.

**Changes:**
- **Confirmed findings:**
  - R-1 `c1b332d6`, R-2 `1d1e8acc`, R-3 `ca9c7fc4`, R-4 `a57738f1`, R-5 `27d7a7b2`
  - R-6 `a9b54ff1`, R-7 `b13273c4`, R-8 `166b355a`, R-9 `1098a5f2`, R-10 `b8048af9`
  - R-11 `1babbb9a`, R-12 `43b692d5`
  - R-13: `6ea8bfb1` (a), `26dac7c7` (b), `42a325f3` (c), `3aad2048` (d), `428cbe04` (e), `5e76f6b3` (f), and `7945a491` (README list of shared rules)
- **Minors:** M-1 `da8980fe`, M-2 `fb22c691`, M-3 `89c9953f`, M-4 `8feb59d0`
- `tests/`, `spec.md`, and `test-plan.md` are unchanged since `f421047e`.

**Gate matrix out:**
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests | `pytest -q -p no:cacheprovider tests/features/prebuilt_tools/test_prebuilt_hostile_inputs.py tests/features/prebuilt_tools/test_prebuilt_resource_bounds.py` | PASS | `61 passed in 18.51s` |
| pack | gate 1 | PASS | `4352 passed in 36.65s` |
| lint | gate 2 | PASS | `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` (0 REGRESSED) |
| typecheck | `lint/run.py --rule S009` | PASS | `S009 RATCHETED: 350 known finding(s).` / `SDK-LINT: PASS` |
| import sort | gate 3 | PASS (inherited only) | whole tree: `Found 223 errors.`, with 0 in the 87 files the PR changes since merge-base `8387d666`; the PR's 40 `vidbyte` .py files with `--select I001,F401`: `All checks passed!` |
| semgrep | gate 4 | PASS | `Ran 1 rule on 931 files: 0 findings.` |
| public API | gate 5 | PASS | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` |
| full local gate (source) | gate 6 | PASS | `8367 passed, 13 skipped in 73.09s (0:01:13)` / `CI passed.` |
| full local gate (package) | gate 7 | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| remote checks | `gh pr checks` | none configured | `no checks reported on the 'feat/prebuilt-agent-tools' branch` (CI disabled repo-wide; nothing dispatched) |

**Still open:**
- No confirmed finding and no gate is open.
- M-5 stays a follow-up.
- Reproducers for every fixed finding live in the c9710ed2 regression files, and the hostile-decimal sweep lives in reports/S5-repair-1.md.
