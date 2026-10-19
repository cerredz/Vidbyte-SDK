# S5 repair, iteration 2 of 8: public-skill-loader

Branch `feat/public-skill-loader`: start `835c0da5`, code head `93a2b1a8`, and the docs head is the commit that adds this file. PR https://github.com/cerredz/Vidbyte-SDK/pull/1099. Verify-log entry: `verify-log.md` "## Iteration 2". It has every hypothesis, the probes, and the exact before/after for the test edit.

## Outcome

The release is 0.4.0 in all nine INV-16 places. The contract is regenerated (643 exports), the release test's floor is (0, 4, 0), and `docs/design/release-0-4-0.md` exists in the 0.3.0 precedent's shape. Every gate is green except three local source-stage failures, which are the inherited (a), (c), and (d). Remote CI and Static policy are green on `93a2b1a8`.

A maintainer can tag `v0.4.0` on the merge commit without touching a literal. vidbyte-cli can pin `vidbyte-sdk[codex]>=0.4.0,<0.5`, and its C029 will match the contract's `"version": "0.4.0"`.

## Gate matrix

| Gate | Result | Final lines |
|---|---|---|
| `python lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` / `SDK-LINT: PASS`. Nothing REGRESSED or ERRORED |
| pack: `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/public_skill_loader` | PASS | `67 passed in 0.46s` |
| pack + Jev area (`… tests/features/jev_skills_preload tests/test_jev_skill_preload.py`) | PASS | `493 passed, 1 skipped in 11.01s` |
| `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | FAIL, 3 inherited | `====== 3 failed, 5888 passed, 16 skipped, 1 warning in 136.28s (0:02:16) ======` / `CI failed: Command failed with exit code 1: …python.exe -m pytest …`. The 3 are (a) `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, (c) `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them`, and (d) `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` |
| `env -u PYTHONPATH python scripts/run_ci.py --stage package` | PASS | `Installed vidbyte-sdk 0.4.0 passed smoke checks.` / `CI passed.` |
| semgrep scan (wrapper, `scan --error … vidbyte`) | PASS | `Ran 1 rule on 962 files: 0 findings.` |
| semgrep fixtures (guarded wrapper, `--test …`) | PASS | `1/1: ✓ All tests passed` |
| `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 013cf884fb9a532101bbbe128d9fde908b2fd131 (vidbyte-sdk 0.4.0, 643 exports).` |
| remote CI 38839158032 (`93a2b1a8`) | PASS | Source / Python 3.11, Source / Python 3.12, and Package all success. `5851 passed, 56 skipped` / `Installed vidbyte-sdk 0.4.0 passed smoke checks.` / `CI passed.` |
| remote Static policy 38839160549 (`93a2b1a8`) | PASS | Static policy = success |

The first source-stage run gave 4 failures (`4 failed, 5887 passed, 16 skipped in 260.74s`). The fourth was `test_coding_agent_environment.py::test_real_bash_reports_its_version_and_git`, a 15-second real-bash probe that timed out while host CPU was at 100%.
- It failed the same way on a copy of the merge-base `0754e01f`.
- It passed in isolation once the load eased (`1 passed in 9.10s`), and it passed in the re-run.
- It is inherited and environmental; the evidence is in the verify log.

## Per item

**V: version 0.4.0 (D-15; rows 3(a), 4-11).**
- Found by `git grep -n -e "0\.3\.1" -e "0, 3, 1" -e "0_3_1" -e "0-3-1" -- ':!docs'`: the nine places at row 7's line numbers, plus the release test's own text.
- `013cf884` changes the eight literals in one source commit (+8/-8), following `a7ed9cde`'s subject style.
- `46416739` holds the contract alone, generated from the clean tree. Its data diff is only `"version"` and `source.commit`.
- `--check` and C016 are clean. Nothing was amended.
- A follow-up grep for `0\.3\.0`, `<0\.4`, and `>=0\.3` outside `docs/` is empty.
- D-15's flip condition does not hold: `origin/main` (`aac190e9`) still reads 0.3.0, with no `v0.4.0` tag.

**T: the release test's floor (granted, AC-11).**
- `dc522090` changes 6 lines (listed in the verify log) and no assertion. `FIRST_LOADER_RELEASE` is now `(0, 4, 0)`.
- Scratch-copy probe:

  | Version | Result |
  |---|---|
  | all eight places at 0.3.0, 0.3.1, or 0.3.9 | 8 failed, `assert (0, 3, x) >= (0, 4, 0)` |
  | 0.4.0, 0.4.1, or 0.5.0 | 8 passed |
  | `llms.txt` alone at 0.3.1 | 1 failed, 7 passed |

**N: release notes (D-16, row 16, FR-13, AC-19).** `93a2b1a8` adds `docs/design/release-0-4-0.md`, 15 lines like the precedent. It covers:
- the loader as the headline;
- #1027's two breaks: `api_key=` removed from 11 signatures on 8 root exports, and AUTO gateway routing with the "Missing Vidbyte API key" failure;
- #1095, #1036, and the 15 fixes;
- later `main` fixes;
- the nine places, 643 against 639 exports, no dependency change, and the release steps.

Each claim was checked by a probe or by git:
- the signature diff of every root export, from `v0.3.0` and HEAD archives;
- a gateway run with `httpx` faked, which sent 0 requests;
- `FailureCode` 120 → 148;
- 9 thread functions;
- the `pyproject.toml` diff;
- the `publish.yml` jobs.

One deliberate deviation from row 16's wording: the list cites `git log --first-parent v0.3.0..0754e01f` plus #1099, not `v0.3.0..HEAD`. On this branch, `v0.3.0..HEAD` first-parent shows only #1086 to #1088, because the merge's second parent carries the rest.

**review.md:** R-C11 is `fixed @ed354f3a (spec r5)`, R-C12 is `fixed @ed354f3a`, and R-C13 is `fixed @ed354f3a, b1a970c4`. R-C10 is still refuted.

## Test changes beyond the grant

None as BLOCKED. One reading to confirm:
- The grant names lines `:3`, `:9`, and `:34-35`, and the category "the docstring/comment lines that name 0.3.1 or D-13".
- `:4` (ROLE IN CODEBASE) and `:10` (RELATED DOCS) also name D-13. Only that token changed on each, to D-15.
- If the line list was meant to be exhaustive, revert those 2 tokens.

## Disputed findings

None.

## Open

- Local source-stage failures (a), (c), and (d) are inherited (pipeline.md decision, 2026-10-16 00:40).
- The release doc names #1103 to #1107 from the local `origin/main` ref (not fetched). Refresh it if `main` moves before the merge.
- Local tooling: use `it2/run_semgrep_guarded.py` in the scratchpad for `semgrep --test`. The original wrapper hangs on Windows spawn.
