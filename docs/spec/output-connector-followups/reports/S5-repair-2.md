# S5 repair, iteration 2 of 8

Inputs: reports/S5-rereview.md (verdict SOUND, reviewed at `7cab8990`), findings R-RR1, R-RR2, R-RR3, all Minor and docs-only. Start HEAD `7a12530d` (pushed, clean). No failing gate came in: every gate was green at `8d8ba811`, and no code changed after it.

## Fixes

| ID | Where | What changed | Check | Commit |
|---|---|---|---|---|
| R-RR1 | `vidbyte/lib/outputs/README.md` Footguns | Added "Links in this section retrieved 2026-10-14." after the last Footguns bullet. That is the R-9 style (47696121), and one line covers the four links at :242, :244, :248, and :280. In the same commit I rewrapped the 94-column line R-13 left in How To Add A Destination step 3, with no change to its words. | No test asserts the wrapped phrase or the date line (`grep -rn` over `tests/` for the phrases finds nothing). Pack `664 passed`. README is 32,180 characters (A009 limit 40,000; A009 0/0 CLEAN). | 44b71741 |
| R-RR2 | spec §17 "Implementation deviations" | Added two bullets. (a) The public static `OutputHttp.basic_authorization(username, password) -> str` (efb2c26b, R-8) is not listed in §8.5 or D-2. It exists so Jira and Confluence build the Basic header in one place (Style 5). Jira's bytes are unchanged (AC-34). It adds a name and changes none, and the contract is unaffected because `OutputHttp` is not a root export. (b) `vidbyte/agents/README.md` was edited outside §12.3 (bde205cd, R-11). The orchestrator approved this as a docs-only truthfulness fix (pipeline.md, S4 routing decisions). | The wording keeps the bullet list's lead-in true ("none changes a public name or a tested behavior"). | 42018c13 |
| R-RR3 | spec §17 "Implementation deviations" | Added one bullet. `vidbyte/lib/constants/outputs.py` is 326 lines (160 at `336d6c78`), over NFR-2's 300 but within AGENTS.md Style 3's 1,000. It is not split, because a second module would be an eighth new file, over the §8.4 budget. | `wc -l` → `326 vidbyte/lib/constants/outputs.py`. Base → `160`. | b1c32edd |

Correction to the re-review's evidence, recorded in the R-RR3 bullet: `delivery.py` (249 lines) is a modified module, not a new one. The largest new modules are `adf.py` and `github_api.py`, at 109 lines each. The bullet also names the two other touched modules over 300, both over it before this batch: `vidbyte/__init__.py` (1,336 → 1,348, root exports) and `vidbyte/lib/errors/base.py` (552 before and after). Neither is a new finding. Both predate the PR, and `__init__.py` grows only by the six root exports §8.4 budgets.

review.md: I added a "Final re-review (S5) Minors — 3" table with R-RR1…R-RR3 and their `fixed @<sha>` values. The existing tables are unchanged.

## Gate matrix

| Gate | Result | Final lines |
|---|---|---|
| new tests (pack) | PASS | `664 passed in 5.18s` (on `b1c32edd`; also `664 passed in 5.14s` right after the R-RR1 edit) |
| lint `PYTHONIOENCODING=utf-8 python lint/run.py` | PASS | `S063 RATCHETED: 4 known finding(s)…` · `S064 RATCHETED: 4 known finding(s)…` · `SDK-LINT: PASS`, exit 0. A009 `0 0 CLEAN`, A002 `577 703 IMPROVED`, S009 `350 350 RATCHETED` |
| full local gate, source | PASS | `tests/test_workflow_agent_forks.py ......  [100%]` (Windows prints a backslash) · `====================== 4679 passed, 13 skipped in 36.69s ======================` · `CI passed.`, exit 0 |
| full local gate, package | SKIPPED | docs-only; last run at 8d8ba811: green |
| Semgrep, contract, NFR-6 seven rules, I001 | SKIPPED | docs-only; last run at 8d8ba811: green. `git diff 7a12530d..b1c32edd --name-only -- vidbyte` → `vidbyte/lib/outputs/README.md` only; `-- tests lint pyproject.toml` → empty |
| remote checks on `b1c32edd` | PASS 4/4 | `Package completed success` · `Static policy completed success` · `Source / Python 3.12 completed success` · `Source / Python 3.11 completed success` |

CI covered `b1c32edd`, the last commit that touches the README or the spec. The verify-log/report commit that follows is docs-only and was not dispatched.

## Commands run (final lines)

- `git push origin HEAD:feat/agent-output-connectors` → `7a12530d..b1c32edd  HEAD -> feat/agent-output-connectors`; `git ls-remote` → `b1c32edda44487518b37300e5e5c491586dfdf7c refs/heads/feat/agent-output-connectors`, equal to HEAD.
- `gh workflow run ci.yml` → run 38550257344; `gh workflow run static-policy.yml` → run 38550260311; both `headSha` `b1c32edd…`.
- `gh run watch 38550257344 --exit-status | tail -n 5` → `✓ Build and verify distributions` · `✓ Upload verified distributions` · `✓ Post Set up Python` · `✓ Post Check out source` · `✓ Complete job`, exit 0.
- `gh run watch 38550260311 --exit-status` → `Run Static policy (38550260311) has already completed with 'success'`, exit 0.
- `gh api repos/cerredz/Vidbyte-SDK/commits/b1c32edda44487518b37300e5e5c491586dfdf7c/check-runs` → four rows, all `completed success`.
- `wc -l vidbyte/lib/constants/outputs.py` → `326`; `git show 336d6c78:vidbyte/lib/constants/outputs.py | wc -l` → `160`; `wc -l` over every touched and new `vidbyte/*.py` → new modules max 109 (`adf.py`, `github_api.py`).
- `wc -c vidbyte/lib/outputs/README.md` → `32180`.

## Open items

None. Every gate is green, and R-RR1…R-RR3 are closed. R-3, R-4, and R-7 remain deferred follow-ups (orchestrator decision), as before.
