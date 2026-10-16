# S5 repair, iteration 3 of 8: harness-thread-helpers-skills

Branch `feat/harness-thread-helpers-skills` · PR https://github.com/cerredz/Vidbyte-SDK/pull/1147 · start HEAD `a35ccf11` · code SHA `25f36c6d`

## What came in

The S6 PR author's report (`reports/S6-pr-author.md`, "Things that looked wrong") routed two trivial defects in the shipped tree back to repair. No gate was red.

| ID | Source | Where | Defect |
|---|---|---|---|
| R-26 | S6 R-open-1 | `vidbyte/harnesses/README.md:179` | "22 keyless functions" was followed by 23 names, because `init_muse_workspace` sat in the same list. |
| R-27 | S6 R-open-2 | `vidbyte/harnesses/native/grok/store.py:104-106` | There were three blank lines between `GrokHome` and `GrokStore` (PEP 8 E303). |

I added both to review.md's Minor table, then marked each `fixed @<sha>`.

## Gate matrix (code SHA `25f36c6d`)

| Gate | Command | Result | Final lines |
|---|---|---|---|
| lint | `$PY lint/run.py` (own exit code, after `git add`) | PASS (exit 0) | `S063 IMPROVED 4 -> 3. Lower it with: …` · `S064 RATCHETED: 4 known finding(s). Inspect with: …` · `SDK-LINT: PASS` |
| new tests | `$PY -m pytest -p no:cacheprovider -q tests/features/harness_threads` | PASS (exit 0) | `1025 passed, 3 skipped in 91.72s (0:01:31)` |
| full local gate | `$PY scripts/run_ci.py` (`PYTHONPATH` unset) | PASS (exit 0) | `================ 6632 passed, 17 skipped in 149.54s (0:02:29) =================` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| semgrep fixtures | `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` | PASS (exit 0) | `1/1: ✓ All tests passed` · `No tests for fixes found.` |
| semgrep scan | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS (exit 0) | `Ran 1 rule on 975 files: 0 findings.` |
| remote CI | run 38951244041 on `25f36c6d` | 3/3 green | Source 3.11 `6580 passed, 69 skipped in 149.08s` · `CI passed.`; Source 3.12 `6580 passed, 69 skipped, 19 warnings in 154.22s` · `CI passed.`; Package `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| remote static policy | run 38951246923 on `25f36c6d` | 1/1 green | `1/1: ✓ All tests passed` · `Ran 1 rule on 975 files: 0 findings.` |

`gh api repos/cerredz/Vidbyte-SDK/commits/25f36c6d…/check-runs` returned:
```
Package	completed	success
Static policy	completed	success
Source / Python 3.12	completed	success
Source / Python 3.11	completed	success
```
The records commit that carries this report is dispatched again. Its results are in the STATUS message, because recording them here would move the head again.

## Per finding

### R-26: README helper count (fixed @`ccfe71ca`)

I considered three options.
1. Change "22" to "23". This contradicts spec r5 (`spec.md:17`: "22 are keyless thread helpers") and the PR body.
2. Move `init_muse_workspace` into the "Command and skill functions: 24" bullet. That bullet would then hold 25 names, against the PR body's "24 paid command/skill functions".
3. Keep "22", take `init_muse_workspace` out of the list, and give it its own sentence. **I chose this one.**

The edit has two parts.
- The list now ends at `delete_opencode_thread`.
- The return sentence drops its "and `init_muse_workspace` a `NativeCommandOutput`" clause. A new sentence follows it: "`init_muse_workspace` is keyless too: it runs `muse init` in the workspace, with `dry_run=True` to only show what it would create, and returns a `NativeCommandOutput`." Each fact now appears once, and every count stays as it was.

I checked the edit independently with a scratch parser. It extracts the backticked names between "keeps:" and "They take", expands `<h>` over the three harnesses, and compares the result with `vidbyte.harnesses.native.__all__`.
- At HEAD it found 23 names.
- After the fix it prints `count claimed: 22 names listed: 22` and `listed==exports: True`.
- (The parser's first version counted the bare `<h>` placeholder as a name and printed 25. I fixed the parser, not the README.)

Other checks:
- The claims in the new sentence match the code: the signature `init_muse_workspace(workspace, *, dry_run=False, config=None) -> NativeCommandOutput` is at `muse/helpers.py:86`, and the child runs keyless (AC-18).
- No test pins this README text.
- The README is 15,230 characters, and A009 is `0 CLEAN`.

### R-27: three blank lines in `grok/store.py` (fixed @`25f36c6d`)

I considered three options.
1. Delete one blank line. **I chose this one.**
2. Run a formatter. Rejected: it would touch other lines, which the briefing forbids.
3. Dispute it. Rejected: there is no basis.

The fix:
- **Reproduced:** `ruff check --no-cache --isolated --preview --select E303 vidbyte/harnesses/native/grok/store.py` printed `too-many-blank-lines: [*] Too many blank lines (3) --> vidbyte\harnesses\native\grok\store.py:107:1`.
- **Fixed:** `sed -i '106{/^$/d}'`, which deletes line 106 only if it is blank.
- **Checked:** `git diff --numstat` gives `0 1`. E303 prints `All checks passed!`, and so do E301, E302, E303 and E305 over all of `grok/`.
- **Also checked:** the Grok helper and command tests give `88 passed`, and lint exits 0.

The repo's own lint does not select E303. So this was a style defect, never a red gate.

## The one failed attempt, and why it matters to the next agent

The first full-gate run failed in the package stage, and the cause was my shell, not the branch.
- **What I ran:** `export PYTHONPATH="$(pwd)"`, following code-map §1.2's note for worktrees, then `run_ci.py`.
- **Source stage:** passed, `6632 passed, 17 skipped in 152.61s`.
- **Package stage:** pip printed `vidbyte-sdk is already installed with the same version as the provided wheel`. Then the smoke check failed with `ModuleNotFoundError: No module named 'vidbyte'`.

Root cause:
- `RunCi._verify_clean_install` (`scripts/run_ci.py:180-195`) runs `pip install <wheel>` with cwd at the repo root and the inherited environment. So pip sees the git-ignored `vidbyte_sdk.egg-info` through `PYTHONPATH` and skips the wheel.
- The smoke command passes `clean_python_path=True`, which pops `PYTHONPATH` (`:225-226`), so nothing is importable.
- Without `PYTHONPATH` this does not happen, because `python -m pip` drops cwd from `sys.path`.

Independent check: in an empty scratch venv, `pip list` shows `vidbyte-sdk 0.3.0` with `PYTHONPATH=<worktree>`, and nothing without it.

`scripts/run_ci.py` is not changed on this branch (`git diff --quiet <merge-base> HEAD -- scripts/run_ci.py`). With `PYTHONPATH` unset, the re-run passed. This is a latent defect in `run_ci.py`: the install step should also clean `PYTHONPATH`. It is outside §12.3 and is not a finding of this PR, so I left it alone. It is a candidate field-guide lesson.

## Test changes proposed

None. `git diff cd2b329b..HEAD -- tests/features/harness_threads | wc -l` → `0`.

## Findings I believe are wrong

None.

## Invariants

- `git diff 239c408a HEAD -- lint/baseline.json | wc -l` → `0`. There are no suppressions.
- `git diff --name-only a35ccf11..25f36c6d` → `vidbyte/harnesses/README.md` and `vidbyte/harnesses/native/grok/store.py` only.
- `spec.md` and `pr-body.md` are untouched.
- `origin/main` is `6983afd2`, 5 commits past the merge base `8da41971` (#1160–#1164). No file overlaps (`comm -12` is empty), and I did not merge.
- I did not force-push. Each push was a fast-forward: `5c93e6c9..25f36c6d`, and then the records commit.

## What remains open

No confirmed finding and no gate.
- The follow-ups are unchanged by decision: R-8, R-9, R-12, R-13, R-14, R-18..R-20, R-22, and R-21's 44 markers.
- After this, the PR author refreshes the live PR body's verification table for the final SHA.
