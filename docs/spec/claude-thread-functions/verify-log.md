# Verification log: Run, continue and fork Claude Code threads with the caller's API key

Gate set (from context/code-map.md §1; run from the worktree root, in CI order):
1. **Source stage** (local, and remote as CI `ci.yml` jobs Source / Python 3.11 and 3.12): `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source < /dev/null`. It runs the tracked-bytecode check, `python lint/run.py` (must end `SDK-LINT: PASS`; never `--update-baseline`), `compileall`, the three `scripts/check_*.py` scripts, and `python -m pytest`.
2. **Import order** (local only; the input to S051): `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`. Main has 223 findings tree-wide. None may sit on a touched path.
3. **Package stage** (local, and remote as the CI package job): `python scripts/run_ci.py --stage package` with PYTHONPATH **unset** (build, twine, clean-venv install, smoke).
4. **Semgrep** (local, and remote as CI job Static policy): `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`. Run it from its own venv with `PYTHONUTF8=1`. It scans git-tracked files only, so commit first.
5. **Remote checks** (remote only). Auto-triggers are disabled. Dispatch with `gh workflow run ci.yml --ref feat/claude-host` and `gh workflow run static-policy.yml --ref feat/claude-host`. Read with `gh api repos/cerredz/Vidbyte-SDK/commits/<sha>/check-runs --jq '.check_runs[] | "\(.name)\t\(.status)\t\(.conclusion)"'`; `gh pr checks` stays empty.
6. **Contracts the orchestrator checks:** `git log --no-merges --oneline 4806c697..HEAD --not origin/main -- tests` is empty, and `git diff <merge-base>...HEAD -- lint/` is empty.

## Iteration 1 — 2026-10-16 — agent report: reports/S5-repair-1.md

**Defects in:**
- Majors R-1, R-2, R-3, R-4 (`review.md`, status open).
- Trivial Minors R-5 (the comment move only), R-7 (status only, fixed in spec r4), R-8, R-9, R-15.
- One red gate, the Claude pack: `5 failed, 195 passed` at cabf0f80 + the S2 tests (2c1e233c). The failures were the AC-23 map test, `[lone-surrogate]`, the output-cap stderr test, and the printed-then-hung timeout test `[run]` and `[fork]`.
- Step 0: catch up with origin/main (845a4d9b, 60 commits) by merge.

**Hypotheses and attempts (in order):**
1. **Merge (be18994a).** The one conflict was in the `vidbyte/lib/dataclasses/validation.py` header. This PR had changed only its `ROLE IN CODEBASE` line, and #1084 had rewritten that line and the `PURPOSE`, inventory, edge-case and TESTS lines. I took main's file (`git checkout --theirs`) and inserted `ClaudeWire` into main's reader list. After the merge, the Claude pack gave the same 5 failures and nothing else (`5 failed, 195 passed, 437 deselected`).
2. **R-1 (bb624cc9).** Root cause: the `OUTPUT_TOO_LARGE` call in `ClaudeWire.read` had no `vendor_text`. Adding `vendor_text=outcome.stderr` alone made the cap test pass. R-1 and R-3 split cleanly into two commits: R-1 is the argument, R-3 is the reorder.
3. **R-3 (b65590a4).** Root cause: `read` checked the timeout and the cap before it read the answer. I moved the four reading lines above both bound checks and passed `thread_id=newest` to both, as spec row 20 says. This is the verifier's `wire_fixed.py`, which I diffed and checked against spec r4. The factory's fallback (`hostkit/errors.py:104`, the caller's id when `thread_id` is None) gives fork-with-nothing-printed its source id, as INV-6 requires.
   - C901 for `read` stays at 8: `ruff --select C901` at max 7 reports `8 > 7`.
   - mypy reports nothing in the Claude files.
   - Header item 3 used to say "never parsed". It now says a cut stdout yields only its thread id, because the reorder does parse it to look for an id. The `wire.py:9` and `threads.py:9` sentences now say that only a run whose whole answer the SDK never read carries no new id.
4. **R-2 (9398d9ee).** I added `CLAUDE_PROMPT_PATTERN = r"[^\x00\ud800-\udfff]+"` beside `NATIVE_PROMPT_PATTERN`. In `__post_init__`, `prompt_pattern = CLAUDE_PROMPT_PATTERN if self.harness is NativeHarness.CLAUDE else NATIVE_PROMPT_PATTERN` is a local conditional expression, the same shape as `_checked_thread_id`'s pattern switch. It adds no `if` and does not use `NATIVE_STDIN_PROMPT_HARNESSES`. A direct probe of the record:
   - Claude refuses `"list \ud800 files"` with `ConfigurationError {'field': 'prompt'}`.
   - Emoji and accented text are accepted for all four harnesses.
   - opencode still accepts the surrogate prompt (EC-38 limitation, INV-20).
   - Grok and Muse raise `UnicodeEncodeError` from the pre-existing Windows unit check. That code path is unchanged from the merge base.
5. **R-4 (0fd70984).** I rewrote the native entry in plain words from the merge-base sentences. The private folder is "a private Claude Code config folder kept for each workspace". `--setting-sources user` became "reads its settings only from that private folder", and `CLAUDE.md` became "instruction file". The section's only backticks are now the heading plus `hostkit` and `vidbyte/lib/process/`, exactly as at b28c3027. This is one line of REPO_MAP; the merged sections are untouched. The README still holds every AC-23 token.
6. **R-8 (687141f7).** I dropped `text` from `_missing_member` and its call. A comment now says the `is not None` on the continue id only narrows the type for mypy. I appended item 5 to spec §17's deviations, the one spec edit allowed. C901 stays at 8 and the ruff ARG check is clean.
7. **R-9 (5d449187).** README: the native bullet now ends with one sentence that names both specs by slug: the harness-thread-functions spec for the Grok, opencode and Muse IDs, and the claude-thread-functions spec for the Claude IDs. I chose this over rewriting 14 tags inside the owner's and this PR's sentences. I used slugs rather than `docs/` paths so that the folder README does not point agents into the opaque `docs/` folder.
   - `folders.py` line 5: "(spec INV-15)", matching the hostkit siblings. That is #1036's literal policy; this spec's INV-16 covers only the `claude` modules.
   - `folders.py` line 9: "(claude-thread-functions spec EC-31 / EC-21)".
8. **R-15 (8d28e7f5)** and **R-5, the comment move only (821af103):** comment text only. No `@intent` blocks were added.
9. **Operator error, recovered.** While the first source-gate run was in the background, a stray `git checkout -q origin/main --` in an I001 command detached the worktree at origin/main. I stopped that gate run (TaskStop) and confirmed that no gate processes were left. `feat/claude-host` was intact at 821af103, so I checked the branch out again and reran the gate from scratch. The log records HEAD 821af103 at its start and at its end. **For the next agent: never put a bare `git checkout <ref> --` in a command.**

**Changes:** be18994a (merge), bb624cc9 [R-1], b65590a4 [R-3], 9398d9ee [R-2], 0fd70984 [R-4], 687141f7 [R-8], 5d449187 [R-9], 8d28e7f5 [R-15], 821af103 [R-5 comment move]. A docs commit with this log and the `review.md` statuses follows.

**Gate matrix out (all run at 821af103 in this iteration):**
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (Claude pack) | `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads/ -k claude < /dev/null` | PASS | `200 passed, 437 deselected in 23.72s` |
| full local gate, source stage | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source < /dev/null` | PASS | `SDK-LINT: PASS` · `reasoning trace contracts: ok (182 tools, 55 shapes)` · `6445 passed, 16 skipped in 122.23s (0:02:02)` · `CI passed.` |
| lint ratchets (inside the source stage) | `lint/run.py` | PASS; baseline unchanged | S008 19/19, A007 255/255, A006 34/34, S015 13/13, S017 79/79, S019 5/5, S051 259/259, C006 104/104, C008 45/45 RATCHETED; S009 346/350 and A002 566/703 IMPROVED (main's gains; not lowered, never `--update-baseline`) |
| import order on touched paths | `python -m ruff check $(git diff --name-only origin/main...HEAD -- 'vidbyte/*.py') --config lint/ruff.toml --select I001 --no-cache` | PASS | `All checks passed!` on the 19 touched files (tree-wide: `Found 223 errors.`, the same as main) |
| package stage | `env -u PYTHONPATH python scripts/run_ci.py --stage package < /dev/null` | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| Semgrep | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (semgrep 1.170.1, own venv) | PASS | `Ran 1 rule on 987 files: 0 findings.` |
| test-contract check | `git log --no-merges --oneline 4806c697..HEAD --not origin/main -- tests` · `git show --cc --format= be18994a -- tests` | PASS | both empty |
| lint/ unchanged | `git diff origin/main...HEAD --stat -- lint/ contracts/ pyproject.toml` | PASS | empty |
| remote checks | ci.yml run 38991106870, static-policy.yml run 38991108133, on 821af103 | PASS (4/4) | `Package completed success` · `Static policy completed success` · `Source / Python 3.11 completed success` · `Source / Python 3.12 completed success` (check-runs API) |

**Still open:** none of the confirmed findings. Follow-ups left for the user, with their status unchanged: R-5's `@intent` blocks, R-6, R-10, R-11, R-12, R-13, R-14 `[scope-adding]`, and opencode's lone-surrogate gap (EC-38).

## Iteration 2 — 2026-10-16 — agent report: reports/S5-repair-2.md

**Defects in:**
- The three Minors from the post-repair re-review (`reports/S5-rereview-conformance.md`, verdict SOUND). They are recorded in `review.md` as R-16 (R-C1), R-17 (R-C2) and R-18 (R-C3). All three are comment, docstring or whitespace only.
- No red gate. origin/main is still 845a4d9b, so no catch-up merge was needed.

**Hypotheses and attempts (in order):**
1. **R-C1 (809e60bc).** First I worked out the real rule from the code and from probes. I did not copy the suggested wording.
   - The code: `newest` in `ClaudeWire.read`, the factory fallback in `hostkit/errors.py` (`thread_id if not None else request.thread_id`), `from_launch_failure` and `from_configuration_error`.
   - The probes: `ClaudeWire.read` over 9 outcomes for each of the three verbs, plus a missing launcher and a failed launch. They used a nonexistent `claude_command`, so no real `claude` ran.
   - The rule: a run or fork error carries the printed id only when stdout is one JSON object whose `session_id` is a lowercase UUID. Otherwise a run carries `None` and a fork its source id. A bare exit 1 (`run_failed`), an exit-0 stdout that is not JSON or holds an upper-case id (`protocol_mismatch`), and `not_installed`/`launch_failed` all fall in the "otherwise" case. A continue's `claude.*` error always carries the caller's id.
   - One exception kept the `threads.py` wording at "a continue's claude.* error". A refused request record gives `configuration.invalid_argument` with `None` for every verb, because `request` is then `None` (#1036's shared behaviour).
   - Both headers now state the rule and give their cases as examples, not as a complete list. They say "an answer cut at the cap", because a cut JSON object can never parse.
   - Spec row 20's sentence now matches the headers, and spec §17 gains deviation item 6. `revision:` and `status:` are unchanged.
2. **R-C2 (547da5bf).** Both shared headers now read "(claude-thread-functions spec EC-38)". I confirmed that `spec.md:260` EC-38 is the lone-surrogate row.
3. **R-C3 (ee3b4e88).** I restored both spaces. Each line is now byte-identical to its version before 687141f7 and 821af103 (`git show <sha>^`, then `diff`). Independent check: `ruff check --isolated --preview --select E2` flags exactly these two lines at 547da5bf (`missing-whitespace-around-operator`). It passes on the fixed files and on all 19 touched `vidbyte/*.py` files. `ruff format --diff` proposes only line wrapping, which the repo does not use, so nothing else was reformatted.
4. The Claude pack ran after each fix: 200 passed each time. No timing flake appeared, so no test needed a rerun alone.

**Changes:** 809e60bc [R-C1], 547da5bf [R-C2], ee3b4e88 [R-C3]. A docs commit with this log, `review.md` rows R-16 to R-18, `reports/S5-repair-2.md` and `reports/S5-rereview-conformance.md` follows.

**Gate matrix out (all run at ee3b4e88 in this iteration):**
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (Claude pack) | `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads/ -k claude < /dev/null` | PASS | `200 passed, 437 deselected in 23.83s` (after R-C3; 24.46s after R-C1, 24.22s after R-C2) |
| full local gate, source stage | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source < /dev/null` | PASS | `SDK-LINT: PASS` · `reasoning trace contracts: ok (182 tools, 55 shapes)` · `6445 passed, 16 skipped in 147.15s (0:02:27)` · `CI passed.` (HEAD ee3b4e88 at start and end) |
| lint ratchets (inside the source stage) | `lint/run.py` | PASS; baseline unchanged | S008 19/19, A007 255/255, A006 34/34, A001 642/642, S015 13/13, S017 79/79, S019 5/5, S051 259/259, C006 104/104, C008 45/45 RATCHETED; S009 346/350 and A002 566/703 IMPROVED (unchanged from iteration 1; never `--update-baseline`) |
| import order on touched paths | `python -m ruff check $(git diff --name-only origin/main...HEAD -- 'vidbyte/*.py') --config lint/ruff.toml --select I001 --no-cache` | PASS | `All checks passed!` on the 19 touched files (tree-wide 223, as on main) |
| operator spacing on touched paths (extra, for R-C3) | `python -m ruff check <19 touched files> --isolated --preview --select E2 --no-cache` | PASS | `All checks passed!` (at 547da5bf the same check gives `Found 2 errors.`, the two R-C3 lines) |
| package stage | `env -u PYTHONPATH python scripts/run_ci.py --stage package < /dev/null` | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| Semgrep | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (semgrep 1.170.1, own venv, after committing) | PASS | `Ran 1 rule on 987 files: 0 findings.` |
| test-contract check | `git log --no-merges --oneline 4806c697..HEAD --not origin/main -- tests` | PASS | empty |
| lint/ unchanged | `git diff --stat origin/main...HEAD -- lint/ contracts/ pyproject.toml` | PASS | empty |
| remote checks | ci.yml run 38993797470, static-policy.yml run 38993799112, on ee3b4e88 | PASS (4/4) | `Package completed success` · `Static policy completed success` · `Source / Python 3.11 completed success` · `Source / Python 3.12 completed success` (check-runs API) |

**Still open:** none. All gates are green and no confirmed finding is open. The user's follow-ups are unchanged: R-5's `@intent` blocks, R-6, R-10 to R-14, opencode's lone-surrogate gap (EC-38), and the unfiled RecursionError-on-deep-JSON note.
