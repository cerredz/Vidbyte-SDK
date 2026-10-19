# S5 repair report, iteration 1 of 8

| | |
|---|---|
| Stage | S5 repair |
| Branch | `feat/harness-thread-helpers-skills` |
| PR | https://github.com/cerredz/Vidbyte-SDK/pull/1147 (draft, MERGEABLE) |
| Start HEAD | `999ff056` |
| Code head | `6b55dde5` (merge of `origin/main` `8da41971`) |
| Test head | `cd2b329b` (unchanged) |
| Venv | `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/harness-thread-helpers-skills/Scripts/python` |

The iteration's full record, including every hypothesis and the one failed attempt, is in `../verify-log.md`, Iteration 1.

## Outcome

Every confirmed finding handed to this iteration is fixed, with one commit each: R-1, R-6, R-5, R-23, R-2, R-3, R-16, R-10, R-11, R-15, R-17 and the trivial part of R-21. R-4 is marked as fixed by the granted test fixture `228b2a9e`.

All 34 red tests are green. Every local gate and all four remote checks are green on the merged tree, and no test, baseline or config file changed.

## Gate matrix (merged tree `6b55dde5`, `DEEPSEEK_API_KEY` set)

| Gate | Command | Result | Final lines |
|---|---|---|---|
| lint | `$PY lint/run.py` | PASS, exit 0 | `S063 IMPROVED 4 -> 3. Lower it with: …` · `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` · `SDK-LINT: PASS` |
| new tests | `$PY -m pytest -p no:cacheprovider -q tests/features/harness_threads` | PASS, 0 failing (was 34) | `....................  [100%]` · `1025 passed, 3 skipped in 87.79s (0:01:27)` |
| full local gate | `$PY scripts/run_ci.py` | PASS, exit 0 | `6632 passed, 17 skipped in 136.84s (0:02:16)` · `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| semgrep fixtures | `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` | PASS | `1/1: ✓ All tests passed` · `No tests for fixes found.` |
| semgrep scan | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS, exit 0 | `Ran 1 rule on 975 files: 0 findings.` |
| remote checks | `gh api repos/cerredz/Vidbyte-SDK/commits/6b55dde5…/check-runs` | 4/4 green | `Package: completed success` · `Static policy: completed success` · `Source / Python 3.11: completed success` · `Source / Python 3.12: completed success` |

Lint rule rows: S009 350/350, C002 9/9, S052 0, S062 889/889 and A001 642/642, all RATCHETED or CLEAN. A002 is 605/703 IMPROVED.

`S063 IMPROVED 4 -> 3` was already so at the base. I did not lower any baseline. `git diff 239c408a -- lint/baseline.json` is empty.

The remote runs:
- CI [38936498307](https://github.com/cerredz/Vidbyte-SDK/actions/runs/38936498307), where Source 3.12 and Source 3.11 each gave `6580 passed, 69 skipped` and `CI passed.`;
- Static policy [38936500713](https://github.com/cerredz/Vidbyte-SDK/actions/runs/38936500713).

Neither shows a billing annotation.

## Per finding

| ID | Commit | What I did | Evidence |
|---|---|---|---|
| R-1 | `3a1dc4b1` | Rewrapped the 7 listed comment lines at 72 columns, and every comment I touched later. | `scratchpad/wide.sh origin/main` (awk `length > 72` on comment lines, compared with the base) prints 0 lines. |
| R-6 | `53bca187` | Added pure `@staticmethod NativeErrorFactory.child_problem(outcome, *, marker=None, texts=())`, used in `GrokHelperWire._checked`, `OpencodeHelperWire._checked` and `MuseSessionWire.exited`. Each site keeps its marker source and still raises through `errors.failure(...)`. Main's 4 older copies stay. | 8 errors tests green. `outcome.timed_out` counts: grok 2, muse 3, opencode 1. |
| R-5 | `cdbbd72b` | Added `remember_thread`, used in `failure` and the three `from_*` factories in the order explicit id → remembered id → `request.thread_id`. It is called right after `GrokStreamWire.read` and `MuseThreadRun.execute`. | `s4c-inv29/repro.py`: `malformed RAISED FailureCode.GROK_PROTOCOL_MISMATCH thread_id= f27485b7-…`. `repro_grok_plan_evidence_id.py`: `raised grok.protocol_mismatch error.thread_id='59877c81-…'`. `repro_muse_evidence_id.py` A: `raised muse.launch_failed error.thread_id='8b564f1b-…'`. |
| R-23 | `3fbe9568` | `require(..., member=)`: with a member set, the arguments must parse as a JSON object whose member value equals the fragment exactly. There is no slash folding in that mode, and Grok's substring rule is unchanged. Added `MUSE_READ_SKILL_ID_MEMBER = "id"`. | `repro_muse_skill_prefix.py`: `raised muse.command_not_run`. |
| R-2 | `f8c00aa7` | The D-33 r5 rule. `tool_calls` returns a tuple and never `None`. `snapshot` and `anchoredSnapshot` read `history.snapshot.state.items`, and `inline` reads `history.items`. Deleted `MuseHelperRun.transcript` and the evidence `require_text`. Added one `require(..., member=MUSE_READ_SKILL_ID_MEMBER)`, the new `@intent muse-anchored-snapshot-holds-every-item` and the r5 likely cause. | `repro_muse_goal_anchored.py`: `[goal, anchoredSnapshot, exec never calls create_goal] raised muse.command_not_run` and `[plan, anchoredSnapshot, exec reads ANOTHER skill (bundled:import)] raised muse.command_not_run`. 16 muse_commands tests green. |
| R-3 | `844583d0` | `search` keeps only files whose summary wins `NativeThreadListing.newest(..., cutoff=None, limit=None)`, then matches. | `search_dupe.py`: `search 'LOGIN': []`. 6 listing_properties tests green. |
| R-4 | `228b2a9e` (S2) | Status only: `fixed @228b2a9e (test fixture, granted)`. No source change. | The new-tests and full gates pass with `DEEPSEEK_API_KEY` set. |
| R-16 | `3b1ab656` | The opencode scan-cap next step is the §12.4 text, copied from spec.md by script. | The helper_surface pin is green. |
| R-10 | `b27a2ff7` | `else:` with inline narrowing: `tools = () if command is None else …`, `fragment = None if command is None else …`. The unreachable both-`None` case fails closed (`command_not_run`). | S009 350/350; grok_commands green. |
| R-11 | `8953669d` | (a) The enums header names `_generate_next_value_`. (b) The README hostkit sentence lists its five jobs. (c) `children.py` :48, :62 and :139 cite `#1036 INV-9` and `#1036 EC-34`. | Docs only; lint A009 holds (README 15,205 chars). |
| R-15 | `94cf9d9a` | `to_utc_datetime` turns the `OverflowError` from `astimezone(UTC)` into the field's `ConfigurationError`. | `9999-12-31T23:00:00-05:00` and `0001-01-01T00:30:00+05:00` give `ConfigurationError` `{'field': 'updated_at'}`. |
| R-17 | `27765710` | `_export_file`: `except OSError` raises `protocol_mismatch` naming the path and the error type (`MUSE_EXPORT_FILE_UNREADABLE_DETAIL`). | `r17_probe.py` (a folder where the file should be): `win32 muse.protocol_mismatch path named: True thread_id: thread-0001`. |
| R-21 (trivial) | `42de68f5` | Moved `# @intent grok-delete-is-checked-on-disk` with `folder = found.path.parent` into `delete`'s window (def :215, intent :222). | Lint passes; the A002 count does not regress. |

## Notes for the re-review

1. **R-2 and `require_text`.** The one `require_text` token left in `muse/commands.py` is `RecordFieldValidator.require_text` at :99. It is the D-25 argument-length check in `_call`, not evidence.
   - The evidence `NativeCommandEvidence.require_text` call is gone, and so is `MuseHelperRun.transcript`.
   - If §12.4 means the bare token, the fix would be to rename that validator call site, which is not a behavior change. I read it as the evidence call.
2. **R-10 shape.** A bare `else:` is not type-safe here: `command` is `GrokCommand | None`, and it raised two S009 mypy findings, 350 → 352.
   - The inline narrowing keeps the default branch and makes the case where neither field is set fail closed.
   - The narrating comment says so.
3. **Repro case B of `repro_muse_evidence_id.py`** prints `RETURNED`. Under r5 no `muse export` runs for evidence, so the seam it patched does not exist. The r5 replacement is covered by `test_an_evidence_folder_failure_after_the_run_carries_the_new_thread`, which is green.
4. **`repro_muse_d33_rule.py`** fails with `AttributeError: … no attribute 'transcript'`. That is expected, because the export path is deleted.
5. **R-5 boundaries.** Launch failures and #1036 runs keep their behavior (INV-26). The evidence config folder is still made with `tempfile.mkdtemp`, as the test author's patch point needs.
6. **Merge.** `origin/main` was at `8da41971`, one commit (#1158) past the briefing's `cb554ed3`. The merge `6b55dde5` had no conflicts. After a fetch, `HEAD..origin/main` is empty.

## Test changes proposed

None. `git diff cd2b329b..HEAD -- tests/features/harness_threads` is empty.

## Findings I believe are wrong

None disputed.

## What remains open

No confirmed finding is open, and no gate is red. These stay `follow-up` by the briefing's decision:
- R-8: spec text.
- R-9.
- R-12: split the constants. The file is at 842 of 900 lines.
- R-13: process.
- R-14: `[raw code-review; …] RETURNED SUCCESS` still reproduces, as designed.
- R-18: route S2.
- R-19: scope-adding.
- R-20.
- R-22.
- R-21's 44 "external boundaries" markers.

Hypotheses for the next agent, if a re-review reopens anything:
- For R-14, scope `GROK_CODE_REVIEW_FRAGMENT` to tool-call arguments rather than the whole export, the way R-23 did for Muse.
- For R-12, move the message texts into a sibling constants module. That needs a new-file budget the §8.4 ceiling does not allow in this PR.
