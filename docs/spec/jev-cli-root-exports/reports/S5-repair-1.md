# S5 repair, iteration 1: jev-cli-root-exports (PR #1190, run R1)

STAGE: S5 repair 1/8 · Date: 2026-10-19 · Branch `feat/jev-cli-root-exports` · Start `6c852a3f` (the briefing named `95bdc8e3`; `6c852a3f` is the orchestrator's `pipeline.md`-only commit on top of it) · Code head `99d5f0fd` · `$MB` = `0324d5d6` (= `origin/main`, re-checked after CI)

## Outcome

STATUS: DONE. All 3 open confirmed S5 findings (R-1, R-2, R-3) are fixed, and every gate is green apart from the one by-design local-only red, proven inherited on a pristine `0324d5d6`. R-4 and R-5 are routed to S6 and the orchestrator.

- **PR #1190 is mergeable again.** `gh pr view 1190 --json mergeable,mergeStateStatus` → `"mergeable":"MERGEABLE"`, `"mergeStateStatus":"BLOCKED"`. BLOCKED is only branch protection plus the draft state (R-5), which is the expected state for this repo.
- **The merged tree is provably main plus the four names.**
  - `git diff --numstat origin/main HEAD -- vidbyte/__init__.py` → `9	0`.
  - The contract differs from main's by the four names plus `source.commit` (`5	1`).
  - The head's literal `__all__` minus main's contract is exactly the four. It has 733 unique names, each of the four listed once.
  - Outside `docs/spec/jev-cli-root-exports/`, the only files that differ from `$MB` are the contract, the release note, the root, and the 5 pack files. The pack equals `09b4ef23`.
- **Provenance is true.** `source.commit` = `731f094c` (the merge). It is an ancestor of HEAD, its root lists the four (`:897`, `:1127`, `:1128`, `:1511`), and `--check` is current at it. The merge commit holds main's contract byte for byte, and the next commit is generator output alone.
- **The release note's numbers were re-derived by me** from the committed contracts: 733 = 639 + 94, 0 removed, with the per-PR parts summing to 94.

## Gate matrix

The full matrix, with final lines, is in `verify-log.md`, Iteration 1. In summary:

| Gate | Result | Final lines (abridged) |
|---|---|---|
| pack | PASS | `21 passed in 3.53s` |
| contract `--check` | PASS | `… is current at 731f094c… (vidbyte-sdk 0.4.0, 733 exports).` |
| source stage: lint | PASS | `C016 0 0 CLEAN`, `S015 13 13`, `A001 642 642`, `S051 259 259`, `S062 889 889`, `SDK-LINT: PASS`; 91 rows equal pristine `0324d5d6` |
| source stage: pytest | PASS apart from 1 inherited local-only red | `1 failed, 7548 passed, 18 skipped in 275.98s (0:04:35)`; the red is `test_import_vidbyte_starts_no_process…` at `:309` |
| package stage | PASS | `Installed vidbyte-sdk 0.4.0 passed smoke checks.` · `CI passed.` |
| semgrep | PASS | `Ran 1 rule on 1030 files: 0 findings.` |
| remote CI `39357404121` (headSha `99d5f0fd`) | 3/3 green | 3.11 `7334 passed, 233 skipped in 209.72s`; 3.12 `7334 passed, 233 skipped, 19 warnings in 165.02s`; Package `CI passed.` |
| remote Static policy `39357406167` (headSha `99d5f0fd`) | green | `Ran 1 rule on 1030 files: 0 findings.` |
| main moved? | no | `origin/main` `0324d5d6`, ancestor exit 0 |

## Per finding

### R-1 [Blocker]: fixed @`7c8f8377` (merge `731f094c`)
- **Reproduced:** `git merge-tree --write-tree --name-only origin/main HEAD` → `CONFLICT (content): Merge conflict in contracts/sdk-public-api.json`, `Auto-merging vidbyte/__init__.py`, exit 1. `gh pr view 1190` → `"mergeStateStatus":"DIRTY","mergeable":"CONFLICTING"`.
- **Fix:** the EC-7 path, exactly as the verifier simulated it.
  1. `git merge --no-ff --no-commit origin/main`.
  2. `git checkout --theirs contracts/sdk-public-api.json && git add`. Then `--diff-filter=U` was empty and `ls-files -u` gave 0. The staged contract equals `origin/main`'s, the root is `9 0` against main, and the note is `3 3`, with 0 markers in either.
  3. Commit `731f094c` (parents `6c852a3f`, `0324d5d6`).
  4. `--check` → `contracts/sdk-public-api.json is stale: exports added: AgentLoopSettings, JevDynamicComputeOption, PermissionPolicy, TextModelMode` (exit 1).
  5. The generator → `wrote contracts/sdk-public-api.json at 731f094c6b23932937d7dc969b6f6c25c0b4d705 (vidbyte-sdk 0.4.0, 733 exports)`. The diff is one `source` line out, one in, and `+` the four names, with CR = 0.
  6. Commit `7c8f8377` (the contract only).
- **After:** `--check` is current at `731f094c` (733). `merge-tree` with `origin/main` exits 0. `merge-base --is-ancestor origin/main HEAD` exits 0. The pack gives `21 passed`. C016 is `0 0 CLEAN`, S015 `13 13`, S051 `259 259`, and ruff I001 prints 0 root lines (tree-wide `Found 223 errors.`, pre-existing).
- **"Gets right" re-checked:**
  - The root is untouched by hand (`9 0` against main), and `- Agent setting exports:` appears once.
  - The import graph equals `$MB`'s (AC-14: 950 modules, `bcad6b199764ec12`, order `6fa27c08e3b32a68`, native unloaded on both trees).
  - In a fresh interpreter with no `*API_KEY*` variable, all 4 identity checks against the defining modules are True, and `allow_all()` permits `['execute', 'read', 'safe', 'write']`.

### R-2 [Major]: fixed @`26d05084`
- **Reproduced:** after the merge, line 19 still said "682 exports … 43 added" and named no #1147. No gate reads the file.
- **Re-derived independently.** `py -3.11 -I <scratchpad>/r1-s5-1/recount_s5.py HEAD` reads only committed objects and hardcodes no part:
  ```
  v0.3.0=639 origin/main=729 head=733 head_list_len=733 sorted=True
  head source.commit=731f094c6b23932937d7dc969b6f6c25c0b4d705 version=0.4.0
  head-main added=['AgentLoopSettings', 'JevDynamicComputeOption', 'PermissionPolicy', 'TextModelMode'] removed=[]
  0754e01f #1095 +1 · 2c84049c #1084 +4 · 82b46c85 #1179 +17 · 64e2bd67 #1099 +3 · b21fd94e #1189 +11 · 181f1992 #1159 +3 · 0324d5d6 #1147 +51 (each -0)
  parts sum=94 removed_along_main=0 ; 639 + 94 = 733 vs head 733
  root __all__ len=733 unique=733 == contract: True; four once each: True; root - main == four: True
  ```
- **Edit:** only the count sentence. The word diff is `[-682-]{+733+}`, `[-43-]{+94+}`, `{+51 from #1147,+}`. The stale "#1184" sentence was left alone (known follow-up).
- **AC-15:** `git diff --numstat $MB HEAD -- docs/design/release-0-4-0.md` → `3	3`. There are 0 `#<n>`, 1 `…` (as at `$MB`), and (a) and (b) are present once each. Main's note equals `181f1992`'s.

### R-3 [Minor, trivial]: fixed @`99d5f0fd`
- On pristine `0324d5d6` (a detached worktree, removed afterwards): `test_harness_threads_surface.py` → `9 passed in 2.87s`, and `def test_failure_codes…` is at `:218`, named `…_32_harness_codes`.
- On the head: `1 failed, 8 passed`. Only `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` fails, at `:309`, with the four as the extra items. The `:302` process/native assertion and the `:308` order clause pass, and the test file equals main's.
- **Control:** pristine main with `"PermissionPolicy",` added after `"ToolPermission",` → `Extra items in the left set: 'PermissionPolicy'` at `:309`, `1 failed`. The edit was reverted, and the worktree was clean before removal.
- **Spec:**
  - NFR-2 names the set per `$MB`.
  - §11 says that CI skips only the merge-base clause.
  - §13 lists only the import test, plus a "no longer red" line.
  - S3's §17 bullet is annotated as superseded at `0324d5d6`.
  - A new §17 revision row and an S5 deviations block are added.
  - `reports/S3-implementer.md` is unchanged.
- The Proof cells AC-5, 6, 9, 12, 13, 14 and 15 were re-proved at `$MB` = `0324d5d6`. Each leads with the S5 measurement and keeps the earlier record. AC-15 stays `3 3`.

### R-4, R-5: not S5's
These are routed to S6 (the title) and the orchestrator (`gh pr ready 1190`). The title and the draft state are unchanged. review.md says so.

## Test changes proposed
None. `git diff 09b4ef23 HEAD -- tests/features/jev_cli_root_exports` is empty, and `git diff --name-only origin/main HEAD -- tests` lists only the 5 pack files.

## Findings I believe are wrong
None. Every confirmed finding reproduced exactly as described.

## Observations (stated limitations, no code)
- **#1147 adds 4 `FailureCode` members** (`GROK_COMMAND_NOT_RUN`, `OPENCODE_COMMAND_NOT_RUN`, `MUSE_COMMAND_NOT_RUN`, `GROK_STORE_UNREADABLE`).
  - The note's "#1036 … `FailureCode` gains 28 members" is still true of #1036.
  - #1147 is covered by the generic "Later changes on `main`" bullet, so no sentence is false.
  - The release PR may want a #1147 line beside the stale "#1184" sentence.
- **Semgrep in Git Bash:** the briefing's `PATH="C:/…/Scripts:$PATH"` splits at the drive colon and falls back to a global semgrep that breaks on mcp 2.x. Use `PATH="$(cygpath -u <venv>)/Scripts:$PATH"`.
- **A002 reads 608.** It was 566 at S1, and main's own PRs moved it. It is IMPROVED against its 703 baseline and identical to pristine `0324d5d6`. It is not this PR's ratchet.

## What remains open, and what to try next
- Nothing is open for S5.
- **Race risk before the merge:** #1177, #1182 and #1174 touch the contract and the root. Run `git fetch origin && git merge-base --is-ancestor origin/main HEAD`. If it exits 1, repeat the same cycle: `git merge origin/main`, `git checkout --theirs contracts/sdk-public-api.json`, commit, run the generator, commit, rerun `recount_s5.py` for the R-2 sentence, then the gates and a re-dispatch.
