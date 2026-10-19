# S5 repair report, iteration 4 of 8 (R-17, R-18, `[gate:mergeable]`)

## Outcome

Two `CodexAgentError` rebuilds now keep every field. Both had kept only code, operation and next step, and dropped the `error_type` and `thread_id` that main's #1116 added. S2's three red tests are green, and no test changed. The spec now says the re-raise keeps every field. Main had moved one commit (`f7f32b19`, #1160), so I merged it with no conflict. The complete gate set is green on the merged tree, apart from the one inherited test. The PR is MERGEABLE.

| Commit | What |
|---|---|
| `5e30a226` | `fix(codex): keep every field when a run re-raises a CodexAgentError [R-17]` |
| `804bbc91` | `fix(codex): keep every field when a launch rebuilds a CodexAgentError [R-18]` |
| `04aa8cbe` | `docs(spec): say the re-raise keeps every CodexAgentError field [R-17]` |
| `fca03aea` | `merge: bring origin/main f7f32b19 into feat/codex-host [gate:mergeable]` |
| next | `docs(spec): verify-log iteration 4 for codex-host-thread-helpers` (this report, the verify-log entry, review.md rows R-17 and R-18) |

## R-17: the goal-check and skill read-back re-raise

- **Red at `fa78ac8f`.** `CodexRunReRaiseTests` has 2 tests, and both fail. The diff shows only `thread_id` (`''` vs `'thr-1'`) and `safe_runtime_details` (`error_type` `''` vs `'InternalRpcError'`).
- **Root cause.** `CodexSkillFunctions._unchecked` (`vidbyte/harnesses/native/codex/skill_functions.py:244-248`) builds a new error from the old one, field by field. It was written before the #1116 union, so it passed only the three fields that existed then.
- **Fix.** Pass `error_type=exc.safe_runtime_details.get("error_type", "")` and `thread_id=exc.thread_id`. `exc.error_type` would raise `AttributeError`, because `CodexAgentError` stores the type only in `safe_runtime_details` (`vidbyte/lib/errors/base.py:160`). The comment above it now names every kept field (widths 67, 64 and 53, all within 72). The file stays LF.
- **Green.** `test_codex_host_goal_skills.py`: `26 passed in 2.24s`.
- **Spec.** INV-22 and INV-35 now say "keeps every field it carried (code, operation, next step, error type and thread id), and only its message changes". §17 deviation 9 records R-17, R-18 and the cause.

## R-18: the partial-failure rebuild in `launch_codex_subagents`

- **Red at `fa78ac8f`.** `CodexHostLaunchRebuildFieldTests` fails. The diff shows `thread_id` `''` vs `'thr-3'` and the same `error_type` gap.
- **Root cause.** This is the same pattern in the original host code (`vidbyte/harnesses/native/codex/host.py:476`). §12.3 row 10 cites it as the precedent for R-17's rebuild, so the defect was copied.
- **Fix.** The same two arguments, plus one comment line: "Keep every field of the error; only its message grows." (69 columns). The file stays CRLF in the working copy. `host.py` goes from 892 to 893 lines, under the 900 cap.
- **Green.** `test_codex_host_review_gaps.py` plus `CodexRunReRaiseTests`: `18 passed in 2.11s`.

## Were there other sites?

`git grep -nE "CodexAgentError\([^)]*(exc|error|err)\.(message|failure_code)" -- vidbyte` finds exactly these two rebuilds. No class subclasses `CodexAgentError`. So no third site drops a field.

## The merge

- Main moved from `8da41971` to `f7f32b19`, which is #1160, "a rewritten history keeps the task in front of the run's own work". It touches only `vidbyte/agents/runtime.py` and `tests/test_prompt_sits_at_run_boundary.py`, and this PR touches neither.
- `git merge-tree --write-tree --name-only HEAD origin/main` was clean. The merge `fca03aea` has parents `04aa8cbe` and `f7f32b19`.
- The PR's net diff is byte-identical before and after the merge (`git diff -U0 8da41971 04aa8cbe` against `git diff -U0 f7f32b19 fca03aea`, without index lines and hunk headers).
- No test needed a re-pin, so the grant was not used.

## Gate matrix (local gates at `fca03aea`, clean tree)

| Gate | Result | Final lines |
|---|---|---|
| new tests (3) | PASS | `PASSED …::test_a_goal_check_error_keeps_every_field_it_carried` · `PASSED …::test_a_skill_read_back_error_keeps_every_field_it_carried` · `PASSED …::test_a_launch_that_fails_midway_keeps_every_field_of_the_mapped_error` · `3 passed in 1.21s` |
| 1 area tests | PASS (inherited only) | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 686 passed, 2 skipped in 53.30s` |
| 2 lint | PASS | `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` · `SDK-LINT: PASS` (A001 642/642, A007 255/255, C008 45/45, S008 19/19, S024 25/25 RATCHETED) |
| 3 public API | PASS | `contracts/sdk-public-api.json is current at d08e89ef75ff4a6ee07465ee5097363e7d0d26c4 (vidbyte-sdk 0.3.0, 640 exports).` |
| 4 source stage | PASS (inherited only) | `reasoning trace contracts: ok (182 tools, 55 shapes)` · `FAILED …::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `=========== 1 failed, 6236 passed, 26 skipped in 100.74s (0:01:40) ============` · `CI failed: Command failed with exit code 1: …python.exe -m pytest` |
| 5 package stage | PASS | `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| 6 static policy | PASS | `1/1: ✓ All tests passed` · `Ran 1 rule on 986 files: 0 findings.` |
| extra: mypy | PASS | `Success: no issues found in 2 source files` |
| inherited proof at `f7f32b19` | FAIL, as on main | `E       AssertionError: assert 148 == 120` · `1 failed in 0.89s` |
| mergeable | PASS | `"mergeStateStatus":"BLOCKED","mergeable":"MERGEABLE"` on `fca03aea` (BLOCKED is branch protection) |
| 7 remote checks | PASS 4/4 on `fca03aea` | runs 38942133235 (CI) and 38942136623 (Static policy): `Package completed success` · `Static policy completed success` · `Source / Python 3.11 completed success` · `Source / Python 3.12 completed success` |

**The counts add up.** The area suite has 683 tests plus S2's 3, so 686 passed. The source stage has 6229 plus 3 plus #1160's 4 (`def test_` goes from 9 to 13), so 6236 passed.

## Test changes

None. `git diff --name-only fa78ac8f 04aa8cbe -- tests/ lint/` is empty. The only `tests/` file that changed since `fa78ac8f` is main's own, and it came in with the merge.

## Findings

- Fixed: R-17 (`5e30a226`, spec `04aa8cbe`) and R-18 (`804bbc91`).
- Disputed: none.
- Observed, not a gate: a plain `ruff check` on `host.py` reports `PYI034` at `:139` (`__aenter__ -> CodexHost` rather than `Self`). The line predates this iteration, and `run_ci.py` does not run ruff. I made no change.

## For the S6 PR author (follow-ups for the PR body)

- **A canonical "same error, new message" helper.** AGENTS.md principle 5 applies: two sites do the same copy-every-field job, and each new `CodexAgentError` field will break both again. The natural home is `CodexAgentError` itself (for example a `with_message` method) in `vidbyte/lib/errors/base.py`. That file is outside §12.3, so this belongs in a separate PR.
- **`CodexErrorMapper.error` sets neither `thread_id` nor `error_type`** (`vidbyte/harnesses/native/codex/errors.py:65`; out of scope by orchestrator decision). Until it does, no host path fills either field, so the two fixes stop a loss that would happen once it does. S2's `FieldCarryingMapper` stands in for that future mapper.
- R-10 to R-15 as before.

## Open items

None.
