# Verification log: JevAgent skill sources — declarative skill entries resolved under the hood

Gate set (from context/code-map.md §1, in CI order):
- **new tests** (local): `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) python -m pytest tests/features/jev_skills_preload tests/test_jev_skill_preload.py -q -p no:cacheprovider`
- **lint** (local; also step 2 of the source stage): `PYTHONPATH=$(pwd) python lint/run.py`. Never `--update-baseline` upward; A001 stays exactly 642 (AC-21).
- **source stage** (local and remote): `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`
- **package stage** (local and remote): `python scripts/run_ci.py --stage package`, with `PYTHONPATH` unset
- **contract** (local; lint C016 too): `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check`
- **semgrep** (local in a scratch venv; remote as Static policy): `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` and `semgrep scan --error --metrics=off --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`
- **remote checks** (remote only, dispatched by hand): `gh workflow run ci.yml` and `gh workflow run static-policy.yml` on the branch; jobs Source / Python 3.11, Source / Python 3.12, Package, Static policy. Read with `gh api repos/cerredz/Vidbyte-SDK/commits/<sha>/check-runs`.

## Iteration 1 — 2026-10-12 — agent report: reports/S5-repair-1.md

**Defects in:**
- Confirmed findings R-1 (Blocker), R-2 (Blocker), R-3 (Blocker), R-4 (Major), R-5 (Major), R-6 (Major, test gap already closed by S2b `f90b0680`).
- Trivial Minors R-8, R-9, R-12, R-13; R-14 (spec text, already done by spec r5 `18903d3d`).
- Failing gates: remote Source / Python 3.12 on `8eb304cc` (`test_unusable_lookup_or_listing_is_fetch_failed_and_retried_next_load[tree nests 2000 levels]`, R-1), Package skipped. Local new tests at `4a947559`: 44 failed, 382 passed, 1 skipped (R-1 5, R-2 38, R-4 1).

**Hypotheses and attempts:**
- **R-1.** Root cause: `_tree_paths` filtered items that were not dicts with a text `path`, so a listing of lists (what a 2,000-level body parses to on 3.12+) became "no paths", then `NOT_FOUND`, remembered. Fix: the existing `FETCH_FAILED` "unexpected answer" condition gains `or not all(isinstance(item, dict) and isinstance(item.get("path"), str) for item in tree)`; the return then filters on `type == "blob"` only. Worked first try. Proven on 3.13.1 too (closest local stand-in for 3.12, scratch venv): pack 425 passed, 2 skipped (the extra skip is `tiktoken` missing from that venv).
- **R-2.** Guard `not (value.isascii() and value.isprintable())` on the stripped value: in GitHub `resolve` right after the Vidbyte-prefix guard (same `(refused,) * len(entries)` shape), and in vendor `_key` after the Vidbyte check, before any request is built. The vendor key comes from `resolve_api_key`, which returns the entry value when set, so an unsafe entry never falls back to a usable env value. Worked first try (all 38 R-2 cases plus the 3 boundary cases green).
- **R-4.** Appended "This agent remembers the miss, so create a new agent after fixing it." to the local `NOT_FOUND` detail; the absolute path stays. Worked first try.
- **R-5.** Added `SkillText.require_version(value, field_name)` (integer hint, then `require`) and `SkillText.require_folder(value, field_name) -> Path`; the two vendor entries and the two folder entries call them. C002 stays 9, C008 passes, the 41 entry tests stay green. **Failed first attempt (tooling, not design):** the edit script sent through a Bash heredoc lost one level of backslashes, so its anchor `'\\'` did not match; the script's own assertion stopped it before any write. Writing the script with the Write tool fixed it.
- **R-6.** No source change. The four S2b tests pass (`4 passed`).
- **R-8.** The review's literal shape (`match members: case [member]: <the checks>`) would nest the encryption and size `if`s at depth 4 (try, with, match, if), over S024's maximum of 3 (baseline 25 would regress). Used guarded cases instead (`case [member] if <encrypted or bad method>`, `case [member] if <over cap>`, `case [member]`, `case _`), each body a single return, so depth stays 3. `SKILL_ARCHIVE_MARKDOWN_COUNT` and its `__all__` entry are deleted; the contract does not cover `vidbyte.lib.constants`.
- **R-9.** `HttpResponseParser().bearer_headers(token)`; no test asserts the whole header dict.
- **R-12.** jev `__init__` PURPOSE lists the seven entries and two enums; vendor.py's modification pattern and README step 3 say to add a new vendor's entry class to the constrained `VendorSkillT`.
- **R-13.** `SKILL_MARKDOWN_DELIMITER = "---"` in `lib/constants/skills.py`; markdown.py uses it, vendor.py uses `.encode()` of it.
- **R-3 (last, so comments added by R-1, R-2, R-5 were wrapped too).** Scripted re-wrap of every full-line `#` block that holds a PR-added line over 72 columns (`git diff -U0 <merge-base>...HEAD`). Three problems found and fixed in the dry run, before any write:
  1. Greedy `textwrap` at 72 left one-word orphan lines ("short.", "run.", "path=."), against the guide's "fill the lines evenly". Switched to a balanced fill: the narrowest width that keeps the greedy line count.
  2. The block detector merged `loader.py`'s `@intent` text (51-54) with the next step's narration (55-56), and `alignment/skills.py`'s pre-existing `@intent` line 78 with the PR's narration (79-81). Added explicit paragraph splits so each stays its own block, and line 78 (not PR-authored) is untouched.
  3. `jev/settings.py:89-90` is mixed: line 89 predates the PR, and line 90 was rewritten by it. It is wrapped as one block, because wrapping only line 90 would leave a 103-column line above a wrapped tail.
  The checks: only comment lines changed, and the 1,161 words before equal the 1,161 after. The PR-line checker reports 0 lines over 72. A002 is unchanged. `lib/dataclasses/skills.py:52-53` were not touched.
- **Lint IMPROVED rows** (A002 640/703, A007 254/255, C012, S001, S010, S025, S051) were already there before this iteration (S3 deviation 7; A007 is 254 both with and without R-8). No baseline was changed.

**Changes:** `879a4b16` R-1 · `556b84fc` R-2 · `757a0464` R-4 · `ca340b36` R-5 · `dde94f83` R-8 · `9567cd4a` R-9 · `4079d101` R-13 · `472c7b1a` R-12 · `75c5f459` R-3 · this docs commit (review.md statuses, this log, the report). Since the test baseline `578cd064`, `tests/` and `lint/` are unchanged.

**Gate matrix out** (local runs at `75c5f459`, Windows, Python 3.11.0):
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests | pack command above | PASS | `426 passed, 1 skipped in 4.42s` (skip: case-insensitive `skill.md` row) |
| new tests on 3.13.1 | same, scratch venv | PASS | `425 passed, 2 skipped in 68.80s` (second skip: `tiktoken is not installed`) |
| lint | `PYTHONPATH=$(pwd) python lint/run.py` | PASS | `S063 RATCHETED: 4 known finding(s).` / `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` (A001 642/642, C002 9/9, S024 25/25, S009 350/350, C016 0/0) |
| source stage | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `====================== 3800 passed, 14 skipped in 29.64s ======================` / `CI passed.` |
| package stage | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| contract | `generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 3a4cb929… (vidbyte-sdk 0.2.1, 615 exports).` |
| semgrep | rule test + scan (semgrep 1.170.1, scratch venv) | PASS | `1/1: ✓ All tests passed` / `Ran 1 rule on 900 files: 0 findings.` |
| remote checks | `gh api …/commits/75c5f459…/check-runs` | PASS | 4/4 on `75c5f459` (CI run 38247240051, Static policy run 38247243321): `Package success` / `Static policy success` / `Source / Python 3.12 success` / `Source / Python 3.11 success`. 3.12 log: `3796 passed, 18 skipped, 19 warnings in 47.39s` / `CI passed.`; 3.11: `3796 passed, 18 skipped in 36.34s` / `CI passed.`; Package: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.`; Static policy: `1/1: ✓ All tests passed` / `Ran 1 rule on 900 files: 0 findings.` |

**Still open:** None: every gate is green, and no confirmed finding is open (R-1 to R-6 fixed; trivial Minors R-8, R-9, R-12, R-13 fixed; R-14 done by spec r5). The follow-up Minors R-7, R-10, R-11, and R-15 to R-19 are for the user, not open defects. This docs commit (review.md, verify-log.md, the report) changes no code; it is pushed and both workflows are dispatched on it as well.
