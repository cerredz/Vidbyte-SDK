# S5 repair, iteration 1 of 8 — prebuilt-agent-tools

- PR: https://github.com/cerredz/Vidbyte-SDK/pull/1072
- Branch: `feat/prebuilt-agent-tools`
- Start HEAD: `adef13e9`. Last code commit: `7945a491`, pushed. The docs commit follows it.
- Test baseline: `f421047e`. `git diff --stat f421047e HEAD -- tests/` is empty, and `spec.md` and `test-plan.md` are untouched.

## Outcome
- All 14 confirmed findings (R-1 to R-14) and Minors M-1 to M-4 are fixed. M-5 stays a follow-up, as the review says.
- Every local gate is green.
- No remote checks are configured: CI is `workflow_dispatch` only, and nothing was dispatched.
- review.md: each status cell now reads `fixed @<sha>`. R-14 reads `fixed @c9710ed2 (test author; green after …)`.

## Findings → commits
| ID | Commit(s) | Fix |
|---|---|---|
| R-1 | c1b332d6 | `markdown_html._ATX_CLOSING` is now `(?:^\|(?<![ \t])[ \t]++)#++[ \t]*+$`, which is linear on long runs of `#` and blanks. Output is unchanged. |
| R-2 | 1d1e8acc | `text_extraction._AMOUNT`: the grouped alternative is guarded by `(?<![0-9]{3},)` (the verifier's form). |
| R-3 | ca9c7fc4 | `verify_ip_address` explodes a scoped IPv6 address via `type(parsed)(int(parsed)).exploded` and then appends `%scope`. |
| R-4 | a57738f1 | Three descriptions reworded without literal values. |
| R-5 | 27d7a7b2 | The `extract_json_from_text` decoder uses `parse_float=partial(PrebuiltToolSupport._read_json_float, "text")` and skips a candidate on its ToolExecutionError. |
| M-1 | da8980fe | `verify_json_syntax` uses the same hook and maps its error to the overflow message. |
| R-6 | a9b54ff1 | `toml_to_json` refuses a dotted key with more than 100 segments before calling `tomllib.loads`. Uses a dot-count prefilter, then an exact possessive segment count. |
| R-7 | b13273c4 | XML path evaluation runs on a counted Element subclass. `PREBUILT_MAX_XML_PATH_VISITS` (2,000,000) applies, and the error names `path`. `xml_find_elements` deduplicates in document order. |
| R-8 | 166b355a | New `PrebuiltToolSupport.parse_html` drops an unfinished `<…` tail before `close()`. The README gained EC-47. |
| R-9 | 1098a5f2 | `patch_json` caps the total JSON it reads and writes with `PREBUILT_MAX_PATCH_WORK_CHARS` (10,000,000). |
| R-10 | b8048af9 | `PREBUILT_MAX_SEARCH_STRING_CHARS` (500). `find_substring_positions` counts every match in one pass. A case-insensitive `replace_all_occurrences` find longer than 500 is refused. |
| R-11 | 1babbb9a | `records_from_json(value, name)` replaces `parse_records_json`, removing the three-level chain. |
| R-12 | 43b692d5 | `PrebuiltToolSupport.decimal_context(prec)` opens a fresh, fully specified context, used at every former `localcontext` site. `copy_negate` and `copy_abs` replace the context-dependent `-x` and `abs(x)`. |
| R-13 | 6ea8bfb1, 26dac7c7, 42a325f3, 3aad2048, 428cbe04, 5e76f6b3, 7945a491 | See the R-13 breakdown below. |
| R-14 | c9710ed2 (test author) | Green after the fixes above: `61 passed` in the two regression files. |
| M-2 | fb22c691 | `monthly_interest_fraction` and `yearly_interest_fraction`. |
| M-3 | 89c9953f | REPO_MAP toolsets entry: "…equips a specific agent or paradigm harness…". |
| M-4 | 8feb59d0 | README: "more than 4,000 digits". The `_support` inventory lists `_reject_json_constant` and `_read_json_float`. |

**R-13 breakdown:**
- (a) Base64: one raising reader, `base64_bytes`.
- (b) Sort orders: `natural_sort_key` and `numeric_order`.
- (c) CSV: `PREBUILT_CSV_DELIMITER_CHARACTERS` and `csv_row_writer`.
- (d) JSON types: `PREBUILT_JSON_TYPES`.
- (e) Shorthand patterns: `PREBUILT_INTEGER_TEXT_PATTERN`, `PREBUILT_DECIMAL_TEXT_PATTERN`, and `PREBUILT_UTC_OFFSET_PATTERN`.
- (f) Name shortening: `shortened_names` with `PREBUILT_MAX_ECHO_CHARS` (100).
- README: the list of shared rules.

## Decisions and failed attempts (the detail is in verify-log.md)
- **R-2:** the reviewer's whole-amount lookbehind was rejected, because it drops list items like `1,2,3`.
- **R-5/M-1:** the briefing's choice, reusing `_read_json_float`, was taken over the verifier's `_noted_float` recording hook. As a result json_data reaches the private `PrebuiltToolSupport._read_json_float` across classes. No lint rule objects, and spec §17 deviation 2 names these hooks.
- **R-7:**
  - Tried first: `ElementTree.Element.__iter__(self)`. It failed with AttributeError, because the C Element uses the sequence protocol.
  - Used instead: `self[:]`.
  - Verification: a 400-tree × 21-path fuzz against stdlib gave 0 mismatches. Hostile paths are refused in 0.2–0.42 s.
- **R-9:** a local variable named `read` tripped A007 and was renamed.
- **R-12:**
  - `format(d, "f")` without a precision, `Fraction(d)`, `int()`, `float()`, comparisons, `copy_*`, and `as_tuple` are context-free (probed), so the remaining calls outside the context are left as they are. A comment at `decimal_text` records this.
  - A sweep ran all 1,921 pack row cases with the host context set to prec 3, Emax 5, every trap, capitals 0, and clamp 1. It gave **0 failures**: `1921 cases, 0 failures under the hostile context`.
- **R-13 (a):** the shared reader raises, and hashing keeps a None-returning adapter, so the HMAC key error never describes the key. A 200k-case fuzz against the old hashing reader gave 0 differences.
- **R-13 (c):** `csv` exports no public writer type (typeshed `_csv.Writer` is not re-exported), so the helper returns the bound `writerow` as `Callable[[Iterable[object]], int]`. No output cap was added to csv_tables, because that would change its output.
- **R-13 (f):** this is an intentional error-text change. Spec §9.2 names `PREBUILT_MAX_ECHO_CHARS` (100) as "the one shared name shortener".
  - The old private lengths were 40 (csv_tables, graphs) and 60 (code_analysis, text_transform).
  - csv_tables now marks a cut name with "…", like the other sites.
  - The count of names stays 20 at all four sites.
  - The pack pins none of this text.

## Gate matrix (final lines quoted)
1. **Pack:** `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/prebuilt_tools`
   ```
   ........................................................................ [ 99%]
   ................................                                         [100%]
   4352 passed in 36.65s
   ```
2. **Lint:** `PYTHONPATH=$(pwd) python lint/run.py` (0 REGRESSED)
   ```
   S063 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S063 --all
   S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all
   SDK-LINT: PASS
   ```
   Typecheck: `--rule S009`
   ```
   S009   staged-mypy-contracts                     350    350 RATCHETED
   S009 RATCHETED: 350 known finding(s). Inspect with: python lint/run.py --rule S009 --all
   SDK-LINT: PASS
   ```
3. **Import sort:** `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`
   ```
   vidbyte\workflows\validation.py:48:1: I001 [*] Import block is un-sorted or un-formatted
   Found 223 errors.
   [*] 223 fixable with the `--fix` option.
   ```
   All 223 findings are inherited. A script cross-checked them against `git diff --name-only 8387d666 HEAD` (the merge-base): 0 of the 217 flagged files are among the 87 files the PR changes. The PR's 40 changed `vidbyte` .py files, checked with `--select I001,F401`, give `All checks passed!`.
4. **Semgrep:** `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`
   ```
   Ran 1 rule on 931 files: 0 findings.
   ```
5. **Public API:** `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check`
   ```
   contracts/sdk-public-api.json is current at f7a02bae175913f4ab1cd25d89bfce5ae78e86d0 (vidbyte-sdk 0.2.1, 606 exports).
   ```
6. **Source stage:** `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`
   ```
   tests\test_workflow_agent_forks.py ......                                [100%]
   ================= 8367 passed, 13 skipped in 73.09s (0:01:13) =================
   CI passed.
   ```
7. **Package stage:** `env -u PYTHONPATH python scripts/run_ci.py --stage package`
   ```
   No broken requirements found.
   Installed vidbyte-sdk 0.2.1 passed smoke checks.
   CI passed.
   ```
8. **Remote checks:** `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1072`
   ```
   no checks reported on the 'feat/prebuilt-agent-tools' branch
   ```
   CI is disabled repo-wide, and no workflow was dispatched.

New tests (the R-14 regression files): `pytest … test_prebuilt_hostile_inputs.py test_prebuilt_resource_bounds.py` gave `61 passed in 18.51s`.

## Points for the re-review (not open findings)
- **Unlisted copy left alone:** `number_formatting._REPORTED_WORD_LENGTH = 40` shortens one echoed word. R-13 (f) does not list it, so it was left unchanged.
- **New nested class:** R-7 adds the nested `_CountedElement` in `structured_formats.py`. It is a private helper class like the existing nested parser classes, so it is not counted in the §8.4 class budget.
- **Stale spec row:** the §9.2 `PREBUILT_MAX_REPORTED_NAMES` row lists two tools as users, but the shared shortener now applies it at four sites. Each of the two new sites already used 20 privately. The spec is not mine to edit.
- **Policy self-test not run:** `semgrep --test` on the policy file was not run, because the policy is unchanged.

## Niche facts
- The Bash tool halves backslashes, even inside quoted heredocs. Write edit scripts with the Write tool into the scratchpad, then run them.
- Some prebuilt files are CRLF in the working copy. The scratchpad edit helper keeps line endings.
- Lint traps:
  - A007 fires on local names such as `read` when they receive a literal.
  - S051/I001 fires on a long single-line `from x import (a, b, …)`.
  - `ruff --select I001 --fix` on a single changed file is the quickest way to sort a new import.
