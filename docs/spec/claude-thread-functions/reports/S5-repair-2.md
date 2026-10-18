# S5 repair, iteration 2: claude-thread-functions

Branch `feat/claude-host`. The code head is ee3b4e88, which is pushed and was checked remotely. A docs commit with this report, `verify-log.md`, the `review.md` rows R-16 to R-18 and the re-review report follows it. PR https://github.com/cerredz/Vidbyte-SDK/pull/1044.

Defects in: R-C1, R-C2 and R-C3 from `reports/S5-rereview-conformance.md`, all Minor, all comment, docstring or whitespace. No gate was red. Every change below is text or whitespace only, and no file under `tests/` changed.

## Gate matrix (every gate run in this worktree, in this iteration, at ee3b4e88)

| Gate | Result | Final lines |
|---|---|---|
| Claude pack, `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads/ -k claude < /dev/null`, after each fix | PASS (3 of 3 runs) | `200 passed, 437 deselected in 24.46s` (R-C1) · `in 24.22s` (R-C2) · `in 23.83s` (R-C3) |
| Source stage, `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source < /dev/null` | PASS | `SDK-LINT: PASS` · `reasoning trace contracts: ok (182 tools, 55 shapes)` · `6445 passed, 16 skipped in 147.15s (0:02:27)` · `CI passed.` (the log records HEAD ee3b4e88 at its start and at its end) |
| Lint ratchets (inside the source stage) | PASS, baseline unchanged | Zero-headroom rules at baseline: S008 19/19, A007 255/255, A006 34/34, A001 642/642, S015 13/13, S017 79/79, S019 5/5, S051 259/259, C006 104/104, C008 45/45. S009 346/350 and A002 566/703 are the same IMPROVED counts as iteration 1 (not lowered; never `--update-baseline`) |
| I001 on the 19 touched `vidbyte/*.py` files | PASS | `All checks passed!` (tree-wide still 223, as on main) |
| Package stage, `env -u PYTHONPATH python scripts/run_ci.py --stage package < /dev/null` | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| Semgrep 1.170.1 (own venv, `PYTHONUTF8=1`), after committing | PASS | `Ran 1 rule on 987 files: 0 findings.` |
| Test contract | PASS | `git log --no-merges --oneline 4806c697..HEAD --not origin/main -- tests` is empty |
| `lint/`, `contracts/`, `pyproject.toml` vs origin/main | PASS | `git diff --stat origin/main...HEAD -- lint/ contracts/ pyproject.toml` is empty |
| Remote checks on ee3b4e88 (ci.yml run 38993797470, static-policy.yml run 38993799112) | PASS (4/4) | `Package completed success` · `Static policy completed success` · `Source / Python 3.11 completed success` · `Source / Python 3.12 completed success` (check-runs API) |

origin/main is still 845a4d9b (`git ls-remote`), so no catch-up merge was needed.

## Per finding

**R-C1 (review.md R-16), fixed in 809e60bc.** Before writing anything, I worked out the actual rule. I read `ClaudeWire.read` (`newest` is the caller's id on continue, else `session`), the factory fallback (`hostkit/errors.py`: `thread_id if thread_id is not None else request.thread_id`), `from_launch_failure` and `from_configuration_error`. Then I probed every path through `ClaudeWire.read` for all three verbs (scratch `probe_ids.py`). It covered 9 outcomes: a timeout with nothing printed, a timeout after a valid answer, an answer cut at the cap, a bare non-zero exit, an exit-0 stdout that is not JSON, an upper-case session, a 401 `is_error` answer, an `is_error` answer with no session, and an exit-0 answer with no result. I also checked a missing launcher and a failed launch through the public functions and the factory, using a nonexistent `claude_command`, so no real `claude` started. The results:
- **run:** the printed id only when stdout is one JSON object whose `session_id` is a lowercase UUID. In every other case, `None`, including `claude.run_failed` from a bare exit 1, `claude.protocol_mismatch` from non-JSON or an upper-case id, and `claude.not_installed` or `claude.launch_failed`.
- **fork:** the printed id under the same condition, otherwise its source id.
- **continue:** the caller's id on every `claude.*` error.
- **One more exception:** `configuration.invalid_argument` carries `None` for every verb when the request record itself was refused, because `request` is then `None`. That is #1036's shared behaviour. So the `threads.py` sentence says "a continue's claude.* error", not "every error".

I replaced the "only …" sentence in both headers with that rule, keeping each header's style:
- `wire.py:9` cites "(spec INV-6, EC-14, EC-15, D-9)".
- `threads.py:9` cites "(INV-6, D-9, EC-14, EC-15)", as its siblings do. It also says "even one it printed before it hung", which keeps the EC-14 case.

Both name examples ("for example …") instead of claiming a complete list. I wrote "an answer cut at the cap" rather than "stdout cut at the cap", because a cut JSON object can never parse, while in principle a cut stdout of an object followed by whitespace could.

I made the two spec edits I was allowed. The row 20 sentence now states the same rule and is tagged `*(r4, S4 R-3; S5 R-C1)*`. I also appended item 6 to §17's deviations list, the same place iteration 1 put item 5. `revision:` and `status:` are unchanged. Spec EC-14, D-9 and the §16 log were not touched. Their wording ("a run that times out before printing anything therefore reports no id") is true, and none of them says "only".

**R-C2 (review.md R-17), fixed in 547da5bf.** Both shared headers now say "(claude-thread-functions spec EC-38)". I confirmed that this spec's EC-38 (`spec.md:260`) is the lone-surrogate row, and that the same headers' bare citations ("(spec INV-15)" at constants :5 and :7, "(spec §9.1, EC-3)" at dataclasses :108) are #1036's.

**R-C3 (review.md R-18), fixed in ee3b4e88.** I restored the space at both sites. Each line is now byte-identical to its version before the commit that broke it: `git show 687141f7^` line 89 and `git show 821af103^` line 147, compared with `diff`. Independent check: ruff's preview pycodestyle rules (`--isolated --preview --select E2`) flag exactly these two lines at the parent commit ("missing-whitespace-around-operator" at `wire.py:91:19` and `native_threads.py:147:21`). They pass on the fixed files and on all 19 touched `vidbyte/*.py` files. `ruff format --diff` for both lines proposes only line wrapping, which the repo does not use, so I left it alone and reformatted nothing else.

## Not touched (per the briefing)
R-5's `@intent` blocks, R-6, R-10 to R-14, and the RecursionError-on-deep-JSON note. No code moved. S008 (`ClaudeWire.read` C901 = 8) and S009 (346/350) are unchanged. No `#` comment was added or edited, so the 72-column rule is not affected.

## Notes for the next agent
- In the Claude module headers, a bare "spec" means claude-thread-functions. In the shared `vidbyte/lib/{constants,dataclasses}/native_threads.py` and `hostkit` headers, a bare "spec" means #1036's harness-thread-functions spec, so qualify this spec's IDs there.
- `ruff check --isolated --preview --select E2 <files>` catches operator-spacing slips that `lint/run.py` and `ruff format` do not. Run it on touched files after any hand edit of a code line.
- The re-review report `reports/S5-rereview-conformance.md` was untracked; it is committed in this iteration's docs commit, because review.md R-16 to R-18 cite it.
- The final docs commit on top of ee3b4e88 has no check-runs of its own. Per field guide `local-ci-verification.md`, re-dispatch both workflows on the exact head before the merge.
