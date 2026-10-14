# S5 repair, iteration 3 of 8: codex-host

Worktree `vidbyte-sdk-codex-host`, branch `feat/codex-host`, PR https://github.com/cerredz/Vidbyte-SDK/pull/1055. In: HEAD `0c6a5a8e`, code equal to `7b05e68b`. Out: the code commit `888db88f`, pushed as `780c26f4`, then this report and the log entry.

## Defects handed in

- **R-30 (Major, comment-only).** `interrupt_codex_turn` (host.py:400) calls `turn.send_stop` since `ad363725`. A002 splits identifiers on `_` and `.`, and `send` is one of its policy tokens, so it flags the function, which had no `# @intent` line. A002's slack (580 against a baseline of 703) kept the gate green.
- **R-31 (Minor, trivial, comment-only).** `send_stop` clears `stop_pending` in `finally:` around the await. The await can end before the request does, so the comments at turns.py:181-184 ("when the request ends") and host.py:402-404 ("still in flight") were wrong.
- **R-32** is a follow-up (tests-only) and was not handed in. It stays open.
- Failing gates in: none.

## What I did, per finding

### R-30: fixed @888db88f

- **Reproduced** at `0c6a5a8e` with `lint/run.py --rule A002 --all --format json`, filtered to the 27 files the branch changes under `vidbyte/`: `found 580 baseline 703 verdict IMPROVED`, with five rows. One is `vidbyte/harnesses/native/codex/host.py 400 interrupt_codex_turn external boundaries`. The other four are main's `lib/errors/base.py` `__init__`s.
- **Fix:** the verifier's block from the R-30 row, unchanged. The comment block now starts with `# @intent the-caller-can-always-retry-a-failed-stop`, on the line after the def, inside A002's window.
- **After:** `found 579 baseline 703 verdict IMPROVED`, four rows, all main's base.py. There are 0 rows under `vidbyte/harnesses/native/` or `vidbyte/tools/builtins/codex/`.
- **Main's rows.** A002's own `IntentAnalyzer`, run on `git show 8387d666:vidbyte/lib/errors/base.py`, gives the same four `__init__`s at 160, 250, 265 and 274. The branch adds one line at 151, which shifts them by one.
- `send_stop` was not renamed, and the call was not reshaped (R-8's precedent).

### R-31: fixed @888db88f (same commit)

- The host.py half is in R-30's block. The new text says "still being awaited", and that a stop whose "await failed, timed out or was cancelled" blocks nothing.
- The turns.py half is the verifier's wording, wrapped to 72 columns. It says the mark clears "when this await ends: answered, failed, timed out or cancelled". It says that a timed-out or cancelled await can leave the request on a worker (EC-70), so a retry may send a second interrupt. The existing `@intent a-stop-turns-others-away-only-while-in-flight` line stays first.
- The window itself is recorded as an accepted residual beside R-1's in verify-log iteration 3. That entry replaces iteration 2's narrower "R-27 residual". The PR body's residuals list belongs to S6. This stage must not edit the PR body.

### Mechanical checks (the orchestrator's spot-check)

- `git diff 7b05e68b HEAD -- vidbyte`: host.py `+4 -2`, turns.py `+5 -3`. 0 changed lines that are not `#` comments. The widest added line is 70 columns from column 1. host.py has 771 lines, and turns.py has 419.
- `git diff --stat 7b05e68b HEAD -- tests lint` is empty. `lint/baseline.json` is untouched.
- `vidbyte/harnesses/native/__init__.py` blob SHA-256: `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`.
- Untouched, as briefed: `stop()`'s `stop_sent` check, `over_cap()`, the order in which `stop()` sets `stop_pending` before it spawns `send_stop`, and `turn.stop_sent = True` on the user path.
- No file header changed. A001 stays at 643 of 643.

## Correction recorded for iteration 2

Iteration 2's claim that A002 "lists nothing under the branch's paths" (verify-log.md:229, S5-repair-2.md:34) was false from `ad363725` on. The cause: when a rule's verdict is IMPROVED, the text form of `lint/run.py --rule A002 --all` prints only the summary row. At `888db88f` it prints 7 lines in all, and leaves out main's four base.py rows as well. Only `--format json` lists rows by path. The correction is a new paragraph in iteration 3's entry. The iteration 2 entry is unchanged.

## Gate matrix (local runs on 780c26f4, whose code equals 888db88f)

| Gate | Result | Final lines |
|---|---|---|
| New tests | n/a (comment-only, no test added) | — |
| Feature pack | pass | `116 passed in 7.74s` |
| Feature pack, CI view (`openai_codex` hidden) | pass | `36 passed, 80 skipped in 1.78s` |
| A002 JSON, branch files | pass | `found 579 baseline 703 verdict IMPROVED` / `rows in branch files: 4` (main's) |
| run_ci source | pass | `SDK-LINT: PASS` … `4122 passed, 22 skipped in 40.47s` / `CI passed.` |
| run_ci package (no PYTHONPATH) | pass | `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| Lint | pass | `A002 IMPROVED 703 -> 579.` … `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` |
| Semgrep 1.170.1 | pass | `Ran 1 rule on 911 files: 0 findings.` |
| Public API | pass | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` |
| Remote CI, run 38530861705 on `780c26f4` | success | Source 3.11: `4045 passed, 99 skipped in 45.26s` / `CI passed.`; Source 3.12: `4045 passed, 99 skipped, 19 warnings in 50.02s` / `CI passed.`; Package: `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| Remote static policy, run 38530864005 on `780c26f4` | success | `Ran 1 rule on 911 files: 0 findings.` |

## Test changes proposed

None.

## Findings I believe are wrong

None. R-30's tier (Major, on R-9's precedent) and R-31's text were applied as the verifier set them.

## Still open

- R-32 (tests-only follow-up). A test is missing for a user interrupt that arrives while the same user's earlier stop is still in flight. The verifier's mutant `user_no_pending` survives the pack. Its row has the 12-line test shape.
- R-19 to R-25 are follow-ups. R-24's mutant M5 still survives.
- Accepted residuals: R-1, and R-31's window.

## What I would try next, if anything reopens

- **To close R-31's window instead of documenting it:** keep the worker future returned by `run_in_executor` inside `CodexConnection.call`, and clear `stop_pending` from its done-callback instead of from `send_stop`'s `finally:`. That is a behaviour change, so it would need its own test and a review. The verifier judged it out of proportion for a Minor.
- **For R-32:** the test shape in its row (`hold("turn/interrupt")`, a second user call, assert one interrupt). It goes in `CodexHostInterruptAfterFailedStopTests` and needs a grant.
