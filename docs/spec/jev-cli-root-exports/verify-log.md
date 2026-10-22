# Verification log: Root-export the loop, permission, text-mode, and compute names the CLI's JevAgent needs

Gate set (from `context/code-map.md` §1.2 and the S5 briefing §5). Run every gate from the worktree root, in this order:

1. **Pack (local):** `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/jev_cli_root_exports`
2. **Contract (local, needs a real git checkout):** `PYTHONPATH=$(pwd) py -3.11 scripts/generate-sdk-public-api.py --check`
3. **Source stage (local):** `PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source`. It runs the tracked-bytecode check, `lint/run.py` (C016 included), compileall, the three check scripts and the full pytest.
4. **Package stage (local):** `env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 py -3.11 scripts/run_ci.py --stage package`. Never set `PYTHONPATH` for this stage.
5. **Semgrep (local):** `PATH="$(cygpath -u <scratchpad>/s3-semgrep-venv)/Scripts:$PATH" semgrep scan --error --metrics=off --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`. Use the `cygpath` form: in Git Bash, `PATH="C:/…"` splits at the drive colon.
6. **Remote (dispatch-only; the runs do not attach to the PR):** `gh workflow run ci.yml --ref feat/jev-cli-root-exports` and `gh workflow run static-policy.yml --ref feat/jev-cli-root-exports`. Then `gh run watch <id> --exit-status`, and confirm each run's `headSha` is the pushed head. `gh pr checks` reports nothing, by design.
7. **Main moved? (local):** `git fetch origin && git merge-base --is-ancestor origin/main HEAD`

Local-only red: the merge-base clause of `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded`. CI has no `origin/main` ref, so it skips that clause. Remote-only flake: the GitHub-runner timeout of `test_real_bash_reports_its_version_and_git`. If it appears, rerun once with `gh run rerun <id> --failed`.

## Iteration 1 — 2026-10-19 22:00–22:20 (-0400) — agent report: reports/S5-repair-1.md

**Defects in:**
- **R-1** (Blocker): PR #1190 was CONFLICTING/DIRTY against `origin/main` `0324d5d6` (#1147, +51 root exports). The one conflict was the contract's `source.commit` line.
- **R-2** (Major): after R-1, the release note's "682 … 43 added" would be false.
- **R-3** (Minor, trivial): the spec named `…_28_harness_codes` (`171 == 120`) as an inherited red.
- **Failing gates:** none beyond R-1. The head's own gates passed against its `76c61ffb` stamp, and only GitHub's merge check saw the conflict.
- **R-4** (title) and **R-5** (draft): routed to S6 and the orchestrator, not to S5.

**Hypotheses and attempts** (each worked on the first try; nothing failed, so nothing needed a second hypothesis):
1. **R-1, the EC-7 merge cycle.**
   - `git merge --no-ff --no-commit origin/main` gave exactly 1 CONFLICT, in the contract. `vidbyte/__init__.py` and the release note auto-merged with 0 markers. Then `git diff --name-only --diff-filter=U` was empty, and `git ls-files -u` gave 0.
   - `git checkout --theirs contracts/sdk-public-api.json`, `git add`, then commit the merge `731f094c`. Its contract blob equals main's.
   - `--check` then printed `stale: exports added: AgentLoopSettings, JevDynamicComputeOption, PermissionPolicy, TextModelMode`, with no removal.
   - The generator printed `wrote … at 731f094c… (733 exports)`. The diff was the 4 names plus the `source` line, with 0 CR. It was committed alone as `7c8f8377`.
   - **Excluded by the spec, not tried:** a rebase (EC-7); regenerating inside the merge commit (the generator refuses uncommitted inputs and would stamp the pre-merge HEAD); hand-picking a `source` line (false provenance, EC-5).
2. **R-2, an independent recount from the committed contracts.**
   - `scratchpad/r1-s5-1/recount_s5.py` reads `git show <rev>:contracts/sdk-public-api.json` along `git log --first-parent v0.3.0..origin/main`, plus the head's literal `__all__`. It hardcodes no part.
   - Result: 639 + 94 = 733, with 0 removed along main. The parts are 1 (#1095), 4 (#1084), 17 (#1179), 3 (#1099), 11 (#1189), 3 (#1159), 51 (#1147) and 4 (#1190). The verifier's script gives the same totals.
   - Only the count sentence changed (`26d05084`). The word diff is `682→733`, `43→94`, `+51 from #1147,`.
3. **R-3, re-measure on a pristine `0324d5d6`** (`git worktree add --detach …/r1-s5-pristine origin/main`, removed afterwards).
   - `test_harness_threads_surface.py` gave `9 passed` there.
   - On the head, `1 failed, 8 passed`, failing only at `:309` with the four as the extra items.
   - **Control:** pristine `main` plus `"PermissionPolicy",` in `__all__` failed at the same `:309`. The edit was reverted.
   - Spec NFR-2, §11, §13 and §17 were updated, and the S3 report was left alone (`99d5f0fd`).
4. **The AC-12/INV-14 proof, made stricter.** A full `lint/run.py` on the pristine `0324d5d6` worktree gives all 91 rule rows identical to the head's (`diff` empty), so no rule gains a finding from this PR.
5. **Semgrep environment trap (not a code defect).** The briefing's `PATH="C:/…/Scripts:$PATH"` falls back to the global semgrep in Git Bash, which fails with `No module named 'mcp.server.fastmcp'` (mcp 2.x). With `cygpath -u`, it is `1.170.1` using the venv's mcp 1.23.3.

**Changes:**
- `731f094c` Merge origin/main (0324d5d6, #1147 …) into feat/jev-cli-root-exports [R-1, EC-7]
- `7c8f8377` fix(contract): regenerate the public API contract after merging main [R-1]
- `26d05084` docs(release): recount the 0.4.0 contract after merging #1147 [R-2]
- `99d5f0fd` docs(spec): name the post-merge inherited red and re-prove the one-time facts at 0324d5d6 [R-3]
- the docs commit that adds this entry, the review statuses and the report

**Gate matrix out** (local gates at `99d5f0fd`; `$MB` = `0324d5d6`):
| Gate | Command | Result | Final lines |
|---|---|---|---|
| 1. pack (new tests) | gate 1 | PASS | `21 passed in 3.53s` |
| 2. contract | gate 2 | PASS | `contracts/sdk-public-api.json is current at 731f094c6b23932937d7dc969b6f6c25c0b4d705 (vidbyte-sdk 0.4.0, 733 exports).` (exit 0) |
| 3a. source stage, lint | gate 3 (`lint/run.py` step) | PASS | `C016 … 0 0 CLEAN` · `S015 … 13 13 RATCHETED` · `A001 … 642 642 RATCHETED` · `S051 … 259 259 RATCHETED` · `S062 … 889 889 RATCHETED` · `SDK-LINT: PASS`; 0 REGRESSED or ERRORED rows; all 91 rows equal pristine `0324d5d6`'s |
| 3b. source stage, pytest | gate 3 (pytest step) | PASS apart from 1 inherited local-only red (exit 1) | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` · `1 failed, 7548 passed, 18 skipped in 275.98s (0:04:35)` · `CI failed: Command failed with exit code 1: …python.exe -m pytest` · `source stage exit=1`. The failure is at `:309` (`Extra items in the left set: 'JevDynamicComputeOption' 'AgentLoopSettings' 'TextModelMode' 'PermissionPolicy'`). It passes on pristine `0324d5d6`, and the control edit reproduces it there. It is red by design on any branch that adds a root export (field guide), and CI skips the clause |
| 4. package stage | gate 4 | PASS | `Successfully built vidbyte_sdk-0.4.0.tar.gz and vidbyte_sdk-0.4.0-py3-none-any.whl` · twine `PASSED` ×2 · `Installed vidbyte-sdk 0.4.0 passed smoke checks.` · `CI passed.` · `package stage exit=0` |
| 5. semgrep | gate 5 | PASS | `Findings: 0 (0 blocking)` · `Ran 1 rule on 1030 files: 0 findings.` · exit 0 |
| 6a. remote CI | `gh workflow run ci.yml …`, run `39357404121` | PASS 3/3, `headSha` `99d5f0fdc11bf443d1a1b67a2159f9be7e0641e9` | Source / Python 3.11: `SDK-LINT: PASS` · `7334 passed, 233 skipped in 209.72s` · `CI passed.`. Source / Python 3.12: `SDK-LINT: PASS` · `7334 passed, 233 skipped, 19 warnings in 165.02s` · `CI passed.`. Package: `Installed vidbyte-sdk 0.4.0 passed smoke checks.` · `CI passed.`. No real-bash flake, so no rerun |
| 6b. remote static policy | `gh workflow run static-policy.yml …`, run `39357406167` | PASS, `headSha` `99d5f0fd…` | `Findings: 0 (0 blocking)` · `Ran 1 rule on 1030 files: 0 findings.` |
| 6c. PR checks | `gh pr checks …/pull/1190` | none (expected) | `no checks reported on the 'feat/jev-cli-root-exports' branch`; `gh pr view 1190` → `"mergeable":"MERGEABLE"`, `"mergeStateStatus":"BLOCKED"` (branch protection plus draft, R-5) |
| 7. main moved? | gate 7 | PASS | `origin/main` = `0324d5d6`; `--is-ancestor` exit 0, re-checked after CI |

The commit that adds this entry touches only `docs/spec/jev-cli-root-exports/**`, which is no gate input. CI and Static policy are dispatched again on that exact head, and their run IDs and `headSha` are in the S5 STATUS block.

**Still open:**
- No confirmed finding is open for S5.
- R-4 (PR title) belongs to S6, and R-5 (`gh pr ready 1190`) belongs to the orchestrator.
- Re-check right before `gh pr merge`: `git fetch origin && git merge-base --is-ancestor origin/main HEAD`. If main moved, repeat R-1 and R-2 with `recount_s5.py`. Open PRs #1177, #1182 and #1174 touch the contract and the root.
