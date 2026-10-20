LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — at its own merge base `181f1992` the PR meets every FR, INV, AC and §12.3 row, but `main` has since moved to `0324d5d6` (#1147, +51 root exports): GitHub now reports #1190 as `CONFLICTING`, and the release note's "682 … 43 added" would be false on the merged `main`, so the EC-7 merge, regenerate and recount path has to run a third time.

Reviewed: `git diff origin/main...b1e17f66`. The merge base is `181f1992`; the local `origin/main` and `git ls-remote origin main` both read `0324d5d6`. The worktree HEAD `9cec8da1` differs from `b1e17f66` only in `pipeline.md`.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- The root change is exactly the 9 lines of §12.3 row 1, in exactly the spec's positions:
  - (a) `AgentLoopSettings` sits between `AgentInput` and `AgentMessage`.
  - (b) `from vidbyte.lib.dataclasses.security import PermissionPolicy` sits between the `prosecutor_defender_judge` block and `skills`.
  - (c) the two enums are in the `vidbyte.lib.enums` block.
  - (d) the `__all__` entries sit beside the D-4 siblings.
  - (e) the header bullet is byte-identical to the spec text (`grep -cxF` returns 1) and to commit A's text (md5 `7890b849…` at both).
  - Proof: `git diff --numstat $MB b1e17f66 -- vidbyte/__init__.py` returns `9 0`. Nothing else under `vidbyte/` changed (INV-6).
- Every permanent invariant holds in a fresh interpreter with all five `*API_KEY*` variables removed. INV-1 (eager binding in `vars`, each name counted once), INV-2/INV-13 (12 of 12 identity pairs, plus `__all__` membership at every re-export path), INV-5/AC-7 (no process-start audit event, native unloaded), INV-7, INV-9, INV-10, INV-11 and INV-12 all hold. The §4 snippet prints the four expected lines byte for byte (AC-1).
- The contract's provenance is true, checked from git objects alone. `source.commit` is `76c61ffb`. `sorted(set(__all__))` at `76c61ffb` equals the committed `exports`, `76c61ffb` is an ancestor of the head, and `--check` exits 0 (`… current at 76c61ffb… (vidbyte-sdk 0.4.0, 682 exports).`). The two merge commits hold main's contracts byte-for-byte (`git diff --quiet` passes for both), and a generator commit follows each one. Nothing was hand-resolved.
- G-1/A-2 holds beyond the four names. I walked every dataclass field type of `JevAgentSettings` and `JevRuntimeSettings`, three levels deep. The only vidbyte types that are not root names are `ModelProvider` and `ProviderKeys` (both fields accept `str`), and `DecisionModelConfig`/`DecisionModelMode` (`.decision`, which is never exposed). The CLI's flag map is fully buildable from root names, so do not add more exports here.

FINDINGS (ranked, most severe first, max 15)
R-C1 [Blocker] [Budget and boundaries / EC-7] contracts/sdk-public-api.json:3, docs/design/release-0-4-0.md:19 — main's #1147 (`0324d5d6`) added 51 root exports after the last EC-7 merge, so #1190 is CONFLICTING and its release-note count is false for the `main` it would merge into
  Evidence:
  - The remote has moved:
    - `git ls-remote origin main` → `0324d5d6bcfdf5dd168efbe7272f45f9a035419a refs/heads/main`.
    - `git log --oneline 181f1992..origin/main` → `0324d5d6 feat(harnesses): thread helpers and verified built-in skill functions for Grok, opencode and Muse (#1147)`.
    - `git merge-base --is-ancestor origin/main HEAD` → exit 1. The briefing's "origin/main (181f1992) is an ancestor of the head" was true when written, and it is stale now.
  - GitHub refuses the merge: `gh pr view 1190 --json mergeable,mergeStateStatus` → `"mergeStateStatus":"DIRTY","mergeable":"CONFLICTING"`.
  - The read-only trial merge `git merge-tree 181f1992 b1e17f66 origin/main` (output saved at `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/r1-s4-mergetree.txt`):
    - It has 1 conflict, on the contract's `source` line: `"commit": "76c61ffb…"` on our side, `"commit": "5e08bef0…"` on theirs.
    - `vidbyte/__init__.py` merges without a conflict marker.
    - `docs/design/release-0-4-0.md` is not touched by #1147, so it merges silently with stale counts.
  - Counts, read from the committed contracts with `probe_git.py`:
    - `CURRENT origin/main: 729 added since 181f1992: 51 removed: 0`.
    - `post-merge union would be: 733 added since v0.3.0: 94`.
    - The note at `b1e17f66` says: "The contract now lists 682 exports, against 639 at `v0.3.0`: 43 added … 4 from #1190 …".
  Failure:
  - The orchestrator's `gh pr merge 1190 --squash --admin` on `0324d5d6` is refused because the PR conflicts.
  - Suppose the conflict is resolved by hand, by picking either `source` line. Git's textual merge of the export list yields the correct 733-name union, so C016 can pass (it compares data and bytes). The stamped commit, however, would name a tree that lists neither 733 names. That is EC-5's false provenance, which INV-15 forbids.
  - In either case the release record would state 682/43 on a `main` that ships 733/94. That violates FR-7, G-2 ("still describes exactly what 0.4.0 ships") and INV-17, so 0.4.0's only release record misstates the release.
  Smallest fix: run the spec's own EC-7 path a third time, the same way as `4c2fae0f`/`1c4452fc` and `76c61ffb`/`e332e43c`:
  1. Merge `origin/main` (`0324d5d6`) into the branch; do not rebase. In the merge commit, take main's contract verbatim (`git checkout --theirs contracts/sdk-public-api.json`).
  2. In a new commit, run `py -3.11 scripts/generate-sdk-public-api.py`. Expect `wrote … (vidbyte-sdk 0.4.0, 733 exports)`, stamped with the merge commit.
  3. In a new docs commit, change row 2(c) to: "The contract now lists 733 exports, against 639 at `v0.3.0`: 94 added and none removed, 3 from #1099, 4 from #1084, 17 from #1179, 11 from #1189, 3 from #1159, 51 from #1147, 4 from #1190, and `SystemPromptPreset` from #1095." The sum is 3+4+17+11+3+51+4+1 = 94, and 639 + 94 = 733.
  4. Rerun `--check`, AC-5/6/9/13/14/15 against the new `MB` (= `0324d5d6`), the pack, lint, and the full suite. Extend the §17 deviation bullets.
  5. Right before merging, re-check `git ls-remote origin main`.
  Spec IDs: EC-7, A-4, FR-5, FR-7, G-2, INV-4, INV-15, INV-17, AC-13, AC-15

No other finding. I prosecuted every ID listed below and found the defense's evidence concrete in each case.

ID walk (prosecution vs defense; each "holds" rests on a command in COMMANDS RUN):
- FR-1…FR-4: hold. Each name is bound from the spec's module (diff hunks above), and `__module__` equals the defining module for all four.
- FR-5: the clause "668" is superseded under INV-15's "unless a merged main adds root exports (EC-7)". Generator-only and after-commit-A both hold (commit scopes: c0f40bfd, 1c4452fc and e332e43c each touch only the contract).
- FR-6: holds. The header diff is the single added bullet.
- FR-7 and INV-17: hold at `b1e17f66`. The (a) and (b) texts match the spec with `#1190` (grep -cF = 1 each). The recomputed (c) sentence matches. The file has 0 `#<n>` and 2 `#1190`. The one `…` is kept. The only remaining "not the root" is CodexHost's (line 14), which is correct. They fail on current `main` (R-C1).
- FR-8 and INV-6: hold. `git diff --name-only $MB b1e17f66 -- vidbyte ':!vidbyte/__init__.py'` is empty, and the lazy-block line count is 0.
- FR-9, INV-8 and AC-9: hold. The version-file diff is 0 lines, and the root/contract diffs have 0 version lines.
- NFR-1, INV-16 and AC-14: hold. Both trees load 950 `vidbyte*` modules with SHA-256 prefix `bcad6b199764ec12`, native is unloaded, and the four are in `vars` only at the head.
- NFR-2: holds, revised as recorded in §17. The full suite gives `2 failed, 6958 passed, 17 skipped`, and both failures are the named inherited reds.
- NFR-3, §8.4 and AC-6: hold. The implementer changed 3 files and created 0. No file is outside §12.3, the S2 pack or the spec folder.
- NFR-4: holds. The full suite passes apart from the inherited reds.
- INV-3: holds. The four are added, none is removed, the old order is kept (678 → 682), and there are 0 duplicates.
- INV-14 and AC-12: hold. `SDK-LINT: PASS`, with C016 0 CLEAN, S015 13, A001 642, S051 259 and S062 889. No REGRESSED or ERRORED row. The ruff I001 command prints 0 root lines.
- AC-1, 2, 3, 4, 7, 8, 10 and 11: hold (the pack has 21 passed, and the independent probes agree).
- AC-5: holds, re-derived statically. At `f0527b55`, `4c2fae0f` and `76c61ffb`, `__all__` minus the committed contract is exactly the four, and nothing is removed.
- EC-1, 2 and 3: guarded. S015 is at 13, and the counts are 1. EC-4 and EC-6 are process items, met by the commit order. EC-5 is negated by the provenance check. EC-13 is negated by AC-14. EC-14 is an accepted limitation. EC-15 is INV-11. EC-22 is N/A.
- §14 Never list: no edit under `vidbyte/tools/**` or `vidbyte/lib/configs/**`. `lint/` and `lint/baseline.json` are unchanged. No defining module and no version literal changed. The pack equals `09b4ef23` (empty diff). No suppression is added (`noqa`, `type: ignore`, `pragma` and `nosemgrep` all return 0 on added lines). No pack test reads git, pins a count or hash, or pins `0.4.0`. No placeholder is committed.
- §5 diagram: it matches the code path. The generator reads `__all__` statically through `AllResolver` and `PyprojectReader`, never imports vidbyte (`scripts/generate-sdk-public-api.py:5,8`), and refuses uncommitted inputs (`:126`). The only divergence is the stale "668" edge label, which the §17 deviation already covers.
- request.md §A/§D:
  - Every weighted word is either served here or named in NG-12. Writes are served: `allow_all()` → `['execute','read','safe','write']` through root names. "Updates the version" is covered by D-7 (settled).
  - Nothing was built that the user did not ask for. Naming #1189/#1159 in row 2(c) is the A-4 recount the spec mandates, and it is reported in §17.

VERIFIED CLAIMS:
- Implementer: "682 exports at 0.4.0, `--check` current at `76c61ffb`" — HELD (`--check` exit 0, same line).
- Implementer: "pack 21 passed" — HELD (`21 passed in 3.47s`).
- Implementer: "`SDK-LINT: PASS`" and counts C016 0 / S015 13 / A001 642 / S051 259 / S062 889 — HELD.
- Implementer: "full pytest `2 failed, 6958 passed, 17 skipped`, both named inherited reds" — HELD exactly (249.99s). The tree is clean afterwards.
- Implementer: "`vidbyte/__init__.py` differs from main by exactly the 9 added lines" — HELD (`9 0` against `181f1992`).
- Implementer: "the header bullet is byte-identical to commit A's after conflict resolution" — HELD (same md5).
- Implementer: "BaseAgent takes the three types" (the header bullet claim) — HELD. `BaseAgent.__init__` has `permission_policy: PermissionPolicy | None`, `agent_loop_settings: AgentLoopSettings | None` and `model_mode: TextModelMode`.
- Implementer: "Commit C contains only the release note; B and the regenerations contain only the contract; A only the root" — HELD (`git show --name-only` per commit).
- Implementer: "AC-14: 950 vs 950, same hash, native unloaded" — HELD (`bcad6b199764ec12` on both).
- Implementer: "row 2(c) counts: 639 → 682, 43 added, 0 removed, #1189 = 11, #1159 = 3" — HELD at the merge base `181f1992`. The per-step contract diffs were 25 (v0.3.0 → b7350ed6), then 11, then 3, then the four.
- Test plan: "no test reads git / pins counts" — HELD (grep over the pack finds only WHAT-NOT-TO-DO text).
- Spec A-2 / G-1: "every flag-map field type is root or accepts a string" — HELD (field-type walk above).
- Briefing: "origin/main (181f1992) is an ancestor of the head" — NO LONGER HOLDS. `origin/main` is `0324d5d6`, the ancestor check exits 1, and the PR is CONFLICTING (R-C1).
- Spec "Proven once" cells AC-5, 6, 9, 12, 13, 14 and 15 — REPRODUCED all seven against `MB=$(git merge-base origin/main HEAD)` = `181f1992`.

COMMANDS RUN:
- `git ls-remote origin main` → `0324d5d6… refs/heads/main`. Also `git log --oneline 181f1992..origin/main` → `0324d5d6 … (#1147)`.
- `gh pr view 1190 --json number,state,isDraft,headRefOid,mergeable,mergeStateStatus,baseRefName` → `"headRefOid":"b1e17f66…","isDraft":true,"mergeStateStatus":"DIRTY","mergeable":"CONFLICTING"`.
- `git merge-tree 181f1992 b1e17f66 origin/main` → 1 conflict block, on `contracts/sdk-public-api.json` `source.commit`. No marker in `vidbyte/__init__.py`.
- Spec §4 snippet (`sed -n 84,103p spec.md`), run with `env -u <5 *API_KEY* vars> PYTHONPATH=<worktree> py -3.11 ac1_snippet.py` → exit 0, stderr 0 bytes, then `AC-1 STDOUT IDENTICAL` (diff against `sed -n 109,112p`).
- `probe_inv.py` (fresh interpreter, keys removed) → `AC-7 process events after import: []`, `native loaded: False`, `INV-2/INV-13 identity pairs ok: 12`, `INV-10 bullets: 1 True`, `INV-9 star unbound: [] four same: True`.
- `probe_git.py <worktree> 181f1992` → `INV-3 added: [four] removed: []`, `INV-15 source.commit: 76c61ffb derived==committed: True`, `note: v0.3.0 639 head 682 added 43 removed 0`, `CURRENT origin/main: 729 …`, `post-merge union would be: 733 added since v0.3.0: 94`.
- `probe_a2.py` → only `DecisionModelConfig`, `DecisionModelMode`, `ModelProvider` and `ProviderKeys` are NONROOT. Every other field type is ROOT.
- `git diff --numstat $MB b1e17f66 -- vidbyte/__init__.py` → `9 0`. The same command on `docs/design/release-0-4-0.md` → `3 3`.
- `git diff --name-only $MB b1e17f66 -- vidbyte/tools vidbyte/lib/configs vidbyte/agents/settings vidbyte/lib/dataclasses vidbyte/lib/enums vidbyte/lib/config vidbyte/agents/__init__.py vidbyte/agents/jev` → empty. `git diff $MB b1e17f66 -- <7 version files> | wc -l` → `0`.
- `git diff --name-only 09b4ef23 b1e17f66 -- tests/features/jev_cli_root_exports` → empty. `git diff --name-only origin/main...b1e17f66 -- lint` → empty.
- `PYTHONPATH=$(pwd) py -3.11 scripts/generate-sdk-public-api.py --check` → `… is current at 76c61ffbd61632af5c96e472e00208a87109abaf (vidbyte-sdk 0.4.0, 682 exports).` (exit 0). `git merge-base --is-ancestor 76c61ffb b1e17f66` → exit 0. `git show 76c61ffb:vidbyte/__init__.py` lists the four at `:846`, `:1076`, `:1077` and `:1409`.
- `git archive $MB|b1e17f66 vidbyte pyproject.toml` into the scratchpad, then `modset.py` → `950 bcad6b199764ec12 native False four False` / `950 bcad6b199764ec12 native False four True`.
- `PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 lint/run.py` → `SDK-LINT: PASS`, exit 0.
- `py -3.11 -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` → 0 `vidbyte\__init__.py` lines (the tree-wide 223 is pre-existing).
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/jev_cli_root_exports` → `21 passed in 3.47s`.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider` → `FAILED …test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, `FAILED …test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded`, `2 failed, 6958 passed, 17 skipped in 249.99s`. `git status --short` is empty afterwards.
