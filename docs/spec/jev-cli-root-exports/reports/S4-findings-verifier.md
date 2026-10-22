# S4 findings verifier: jev-cli-root-exports (PR #1190, run R1)

STAGE: S4 findings verifier · Date: 2026-10-19 · Code under review: `b1e17f66` (worktree HEAD `9dda0bd0`; `git diff --name-only b1e17f66 HEAD` lists only `docs/spec/jev-cli-root-exports/{pipeline.md, reports/S4-review-*.md}`) · Output: `review.md`

Verdict: **MERGEABLE AFTER FIXES**. There is 1 confirmed Blocker (R-1), 1 confirmed Major (R-2), and 3 Minors (R-3, R-4, R-5 [verifier]). Nothing was refuted. One tier was moved: the release-note half of R-C1/R-V1, from Blocker to Major, with the reason below.

## 1. Merge map

| Original | Lens | Proposed | → Merged | Note |
|---|---|---|---|---|
| R-C1 | conformance | Blocker | R-1 (contract half) and R-2 (release-note half) | R-C1 cites both `contracts/sdk-public-api.json:3` and `docs/design/release-0-4-0.md:19` |
| R-V1 | conventions | Blocker | R-1 (and the release-note sentence of its Failure → R-2) | same root cause as R-C1: main moved to `0324d5d6` after S3 |
| R-E1 | engineering | Blocker | R-1 | same path, line, and failure |
| R-E2 | engineering | Major | R-2 | the release note's count sentence |
| R-E3 | engineering | Minor | R-3 | inherited-red classification after the merge |
| R-V2 | conventions | Minor | R-4 | PR title |
| — | verifier | Minor | R-5 [verifier] | PR is still a draft |

Why R-1 and R-2 are two findings and not one: they share a cause (main moved), but they differ in path (`contracts/…:3` against `docs/design/…:19`), in failure (a loud merge refusal plus false provenance, against a silent false sentence), and in the command that reproduces them. If R-2 were folded into R-1, a repair agent that sees every gate green after the merge could close R-1 and leave the note false, because no gate reads it. That is exactly R-E2's point.

## 2. Verification of each Blocker and Major

All commands were run by the verifier on 2026-10-19 after `git fetch origin`. Scratch work is in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/r1-s4/verifier/`:

- `clone/`: a `--shared` clone at `9dda0bd0`, with `origin/main` set to `0324d5d6`, where the EC-7 fix was simulated.
- `main/`: a pristine detached `0324d5d6`.
- `recount.py`, `handpick.py`, `modset.py`, and `data/`.

The worktree itself was only read: no merge, commit, or checkout ran there.

### R-1: CONFIRMED (Blocker)

**The PR cannot merge.**
```
$ git rev-parse origin/main ; git ls-remote origin main
0324d5d6bcfdf5dd168efbe7272f45f9a035419a
0324d5d6bcfdf5dd168efbe7272f45f9a035419a	refs/heads/main
$ git log --oneline 181f1992..origin/main
0324d5d6 feat(harnesses): thread helpers and verified built-in skill functions for Grok, opencode and Muse (#1147)
$ git merge-base --is-ancestor origin/main HEAD ; echo exit=$?
exit=1
$ gh pr view 1190 --json number,state,isDraft,headRefOid,mergeable,mergeStateStatus,baseRefName,title
{"baseRefName":"main","headRefOid":"b1e17f667a2b79fb18f74757f68911c117a8af55","isDraft":true,"mergeStateStatus":"DIRTY","mergeable":"CONFLICTING","number":1190,"state":"OPEN","title":"[WIP] feat: Root-export the loop, permission, text-mode, and compute names the CLI's JevAgent needs"}
$ git merge-tree --write-tree --name-only origin/main HEAD      # identical result for b1e17f66
c21ceb1dc2f906a14bef27a1e7b528ba4354e1d2
contracts/sdk-public-api.json

Auto-merging contracts/sdk-public-api.json
CONFLICT (content): Merge conflict in contracts/sdk-public-api.json
Auto-merging vidbyte/__init__.py
exit=1
```
The conflict is exactly one hunk, at line 3: `<<<<<<< origin/main` `"commit": "5e08bef0…"` `=======` `"commit": "76c61ffb…"` `>>>>>>> b1e17f66`. There are 0 markers in `vidbyte/__init__.py`, and `git diff --name-only 181f1992 origin/main -- docs/design vidbyte/__init__.py contracts pyproject.toml` → `contracts/sdk-public-api.json`, `vidbyte/__init__.py`.

**The head's own gates cannot see it.** In the worktree, `--check` → `contracts/sdk-public-api.json is current at 76c61ffbd61632af5c96e472e00208a87109abaf (vidbyte-sdk 0.4.0, 682 exports).` (exit 0). The pack gives `21 passed in 3.73s`.

**Hand-resolving gives false provenance (R-C1's EC-5 claim, reproduced).** `handpick.py` resolves the conflicted blob both ways:
```
main side: source.commit=5e08bef0 exports=733 unique=733 sorted=True
branch side: source.commit=76c61ffb exports=733 unique=733 sorted=True
5e08bef0 root __all__ unique names: 729
76c61ffb root __all__ unique names: 682
```
Either pick gives a contract whose data C016 would accept, stamped with a tree that lists neither set of 733 names. INV-15 forbids this, and EC-5 describes it.

**The rule it breaks.** The field guide `local-ci-verification.md`, "Dispatched checks never unblock the merge", says: "If main moves before it runs, merge main again and re-check." Its "Main can break a long-lived feature branch" entry says: "After each merge, run the feature's own tests and `scripts/generate-sdk-public-api.py --check`." The spec's EC-7 and A-4 ("If wrong: merge `main`, rerun the generator in a new commit, and recompute the counts in row 2 (c)") give the same instruction. This finding also does not reverse a settled decision: merging (not rebasing) and regenerating is the briefing's settled EC-7 path.

**Spec reading.** FR-5 and INV-4 (the contract is the generator's canonical output for the current source) fail on the merged tree until regeneration. INV-15 (true provenance) fails on any hand pick. The finding does not ask for anything the user declined.

**Existing guard?** None reaches it. `--check` and C016 compare a checkout only with its own contract. `--match-head-commit` pins the head, not the base. CI is dispatch-only. GitHub's conflict refusal is the only signal.

**The fix, simulated end to end** (in `clone/`, exactly the recipe in the review row):
```
$ git merge --no-ff --no-edit origin/main
CONFLICT (content): Merge conflict in contracts/sdk-public-api.json
$ git checkout --theirs contracts/sdk-public-api.json && git add … && git commit --no-edit
merge=0805a86800ffae78f267faa6ef57c87bf431b103 parents=9dda0bd0… 0324d5d6…
merge contract == main blob: yes
$ py -3.11 scripts/generate-sdk-public-api.py --check
contracts/sdk-public-api.json is stale: exports added: AgentLoopSettings, JevDynamicComputeOption, PermissionPolicy, TextModelMode
exit=1                                   # no "exports removed" line: the AC-5 analogue holds
$ py -3.11 scripts/generate-sdk-public-api.py
wrote contracts/sdk-public-api.json at 0805a86800ffae78f267faa6ef57c87bf431b103 (vidbyte-sdk 0.4.0, 733 exports)
$ git diff -U0 contracts/sdk-public-api.json | grep '^[-+] '
-  "source": {… "commit": "5e08bef0…" …},
+  "source": {… "commit": "0805a868…" …},
+    "AgentLoopSettings",
+    "JevDynamicComputeOption",
+    "PermissionPolicy",
+    "TextModelMode",
$ py -3.11 scripts/generate-sdk-public-api.py --check
contracts/sdk-public-api.json is current at 0805a86800ffae78f267faa6ef57c87bf431b103 (vidbyte-sdk 0.4.0, 733 exports).
exit=0                                   # CR bytes in the contract: 0
$ git diff --numstat origin/main HEAD -- vidbyte/__init__.py
9	0	vidbyte/__init__.py              # the same 9 added lines as at 181f1992
$ grep -c "^    - Agent setting exports:" vidbyte/__init__.py   → 1 ; "- Error exports:" at :26
$ ruff I001 over vidbyte, root lines → 0   (tree-wide total unchanged: 223 fixable, pre-existing)
$ modset.py, fresh interpreter, each tree on PYTHONPATH
main:  950 bcad6b199764ec12 order 6fa27c08e3b32a68 native False four_in_vars False
clone: 950 bcad6b199764ec12 order 6fa27c08e3b32a68 native False four_in_vars True
head-worktree: 950 bcad6b199764ec12 order 6fa27c08e3b32a68 native False four_in_vars True
```
Full lint and full suite on the merged clone:
```
$ PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 lint/run.py     # in clone/, at the regeneration commit
A001   agent-readable-file-headers               642    642 RATCHETED
C016   public-api-contract-current                 0      0 CLEAN
S015   public-export-integrity                    13     13 RATCHETED
S051   modernized-import-and-syntax-hygiene      259    259 RATCHETED
S062   no-implicit-string-concatenation          889    889 RATCHETED
SDK-LINT: PASS
lint exit=0                                       # grep -c "REGRESSED\|ERRORED" → 0
$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider     # in clone/
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded
1 failed, 7548 passed, 18 skipped in 302.74s (0:05:02)
E           AssertionError: assert {'AgentLoopSe...extModelMode'} <= {'BrowserThre...dConfig', ...}
E             Extra items in the left set: 'AgentLoopSettings' 'TextModelMode' 'JevDynamicComputeOption' 'PermissionPolicy'
tests\features\harness_threads\test_harness_threads_surface.py:309: AssertionError
```
`git status --short` in the clone after the suite: empty.

**The race is real.** `gh pr view <n> --json files` shows that three open PRs touch both `contracts/sdk-public-api.json` and `vidbyte/__init__.py`: #1177 (non-draft, updated 19:25Z today), #1182 (non-draft), and #1174 (draft). If any of them lands before #1190, R-1 recurs. Hence fix step 4: re-check `git merge-base --is-ancestor origin/main HEAD` right before `gh pr merge`.

**Smallest fix.** It is the reviewers' fix: the EC-7 cycle, in two commits (a merge, then a contract-only regeneration). No smaller fix exists:
- A rebase is excluded by EC-7 (settled).
- Regenerating inside the merge commit is impossible. The generator refuses uncommitted inputs, and it would stamp the pre-merge HEAD (D-8, `generate-sdk-public-api.py:118-130`).
- Picking a `source` line by hand falsifies provenance (shown above).
- GitHub's "Update branch" cannot resolve a conflict.

### R-2: CONFIRMED (Major; re-tiered from the Blocker that R-C1/R-V1 folded it into)

**The note merges silently with stale counts.** `git diff --stat b1e17f66 8236855301d36488bdf48eb8206807ca53ac730d -- docs/design/release-0-4-0.md` (the merge-tree result for `b1e17f66` with `origin/main`) is empty. The merged note is therefore byte-identical to the head's. Its line 19 reads "The contract now lists 682 exports, against 639 at `v0.3.0`: 43 added and none removed, 3 from #1099, 4 from #1084, 17 from #1179, 11 from #1189, 3 from #1159, 4 from #1190, and `SystemPromptPreset` from #1095."

**Nothing reads it.** `git grep -n "release-0-4-0" -- tests lint scripts .github vidbyte` finds nothing. The generator's inputs are `PYPROJECT_REL` plus `resolver.resolved_modules()` (`lint/core/public_api_contract.py:431`).

**The verifier's own recount** (`recount.py`, run with `py -3.11 -I` from the worktree root). It reads only `git show <rev>:contracts/sdk-public-api.json`, plus `ast` over the merge-tree's root:
```
counts: v0.3.0=639 MB(181f1992)=678 head(b1e17f66)=682 origin/main(0324d5d6)=729
head-v0.3.0 added=43 removed=0
head-MB added=['AgentLoopSettings', 'JevDynamicComputeOption', 'PermissionPolicy', 'TextModelMode'] removed=[]
main-MB (#1147) added=51 removed=0
four already on main? []
  0754e01f (#1095)  added=  1 removed=0 names=['SystemPromptPreset']
  2c84049c (#1084)  added=  4 removed=0 names=['InfiniteMemoryAgent', 'InfiniteMemoryAgentSettings', 'InfiniteMemoryPreset', 'InfiniteWorkspaceSettings']
  82b46c85 (#1179)  added= 17 removed=0
  64e2bd67 (#1099)  added=  3 removed=0 names=['ConfigurationError', 'SkillLoader', 'SkillResolution']
  b21fd94e (#1189)  added= 11 removed=0
  181f1992 (#1159)  added=  3 removed=0 names=['InfiniteEvent', 'InfiniteEventKind', 'InfiniteHandoff']
  0324d5d6 (#1147)  added= 51 removed=0
sum on main since v0.3.0 = 90; main-v0.3.0 = 90; removed since v0.3.0 = 0
merged __all__: len=733 unique=733 dupes=0
merged == main|four: True; merged - main = ['AgentLoopSettings', 'JevDynamicComputeOption', 'PermissionPolicy', 'TextModelMode']; main - merged = []
each of four listed once: True
merged added since v0.3.0 = 94; removed since v0.3.0 = 0
proposed sentence parts sum = 94; 639 + sum = 733
```
The per-PR attribution comes from main's first-parent history of the contract file, so each delta belongs to exactly one squash commit. The three reviewers' numbers (733, 94, 51) all reproduce. So do the S3 numbers at the old merge base (682, 43, 11, 3). The simulated regeneration independently prints `733 exports`.

**Spec reading.** FR-7 ("records the four exports and the new counts"), G-2 ("still describes exactly what 0.4.0 ships"), INV-17 and AC-15 require true counts. A-4 names the recount as the remedy when main adds root exports. Naming "51 from #1147" is forced by the arithmetic, and it follows S3's own precedent for #1189 and #1159 (spec §17). It does not add scope.

**Why Major and not Blocker.** The calibration's Blocker classes are a wrong or broken result, a breach of AGENTS.md or of a field-guide lesson, a weighted word, or a test that cannot fail. This false sentence changes no behavior: no code, test, lint rule, generator, or CLI consumer reads the note, and the CLI vendors the contract. No field-guide entry covers release-note counts. It is "a real gap that would surface in human review" (the Major definition). The Blocker label that R-C1/R-V1 gave it came from the merge refusal and the provenance risk, and R-1 keeps both. The tier does not make R-2 optional: it is confirmed, and it ships in the same repair.

**Smallest fix.** It is the reviewers' fix: one sentence, in one docs commit. It changes only the count sentence, and AC-15 stays `3	3` against `MB=0324d5d6`, because main's copy of the note equals `181f1992`'s.

## 3. Minors (passed through; spot-checked)

- **R-3 (R-E3).**
  - On pristine `0324d5d6` (`main/`): `PYTHONPATH=… py -3.11 -m pytest … test_harness_threads_surface.py -k "failure_codes or import_vidbyte_starts"` → `2 passed, 7 deselected in 3.05s`.
  - `git show origin/main:tests/…/test_harness_threads_surface.py | grep -n "def test_failure_codes"` → `218:def test_failure_codes_keep_main_and_append_exactly_the_32_harness_codes`.
  - At the head, the import test's merge-base clause is `if base is not None:` (`test_harness_threads_surface.py:259-261`), and `assert report["started"] == [] and report["native"] is False` runs before it, unconditionally.
  - On the simulated merge, the full suite has exactly one red, the import test. #1147 rewrote its merge-base clause, so it now fails at `:309` (`set(report["all"]) - set(before) <= set(native.__all__)`: main's version admits only native names as additions). That line is inside `if base is not None:` (`:304`). The process/native assertion (`:302`) and the order clause (`:308`) pass. It is still red locally by design and skipped in CI. The failure-code test (`_32_`) passes. So the post-merge NFR-2 record is "1 inherited red, local-only merge-base clause", and `171 == 120` must not appear in the S6 body.
  - Tagged trivial: the change is text in §17 and NFR-2 that R-1 step 3 rewrites anyway, plus the S6 body.
- **R-4 (R-V2).** `gh pr view 1190 --json title` → `[WIP] feat: Root-export …`. Trivial: S6 sets the title.
- **R-5 [verifier].** `gh pr view 1190 --json isDraft` → `true`. GitHub's merge API rejects a draft PR whatever the admin bypass, so `gh pr ready 1190` must precede the merge. The verifier did not test this, because testing it changes state; it is a known platform rule. Trivial.

## 4. Adjudications between reviewers

1. **One Blocker or two findings (R-C1/R-V1 against R-E1/R-E2).** Split into R-1 and R-2, for the reasons in §1. The release-note half was re-tiered to Major (§2, R-2).
2. **"Take ours" (R-E1) against "the textual union" (R-C1).** Both are right about different actions. Resolving only the conflicting hunk, by either side, keeps git's 733-name union with a false stamp (reproduced above). Taking the whole file with `--ours` would restore the branch's 682-name list, and C016 would then report it stale against the merged root's 733. The prescribed action, `--theirs` for the whole file followed by regeneration, avoids both.
3. **The briefing against the reviewers on ancestry.** The briefing's "origin/main (181f1992) is an ancestor of the head" was true when written. It is false now (exit 1). All three reviewers caught this. It is not a finding against S3, because main moved after S3 finished (`0324d5d6` at 2026-10-19 18:07:23 -0400).
4. **S3's inherited reds against R-E3.** S3's `171 == 120` claim is right at `181f1992`. R-E3 is right for the post-merge state. After R-1, record the measured post-merge set (R-3).

## 5. Blind-spot sweep (risks between the lenses)

- **`source.commit` after the two earlier merges: sound.**
  - `git merge-base --is-ancestor 76c61ffb b1e17f66` → exit 0.
  - `--check` reports the head current.
  - Each merge commit's contract blob equals its main parent's (`4c2fae0f` = `b21fd94e`, `76c61ffb` = `181f1992`).
  - The commits that touch only the contract are `c0f40bfd`, `1c4452fc` and `e332e43c`.
  - After the squash, the stamp names a branch commit that is not on `main`. That is the accepted EC-6 norm: main's own stamp `5e08bef0` is not an ancestor of `origin/main` either (`git merge-base --is-ancestor 5e08bef0 origin/main` → exit 1). Not a finding.
- **The release-note counts after the merges.** They are R-2.
- **The header conflict resolution: sound, at both merges.**
  - `git show --cc 76c61ffb -- vidbyte/__init__.py` shows one header hunk: main's `- Agent exports:` line, then the unchanged `- Agent setting exports:` bullet.
  - The #1147 auto-merge leaves the root `9	0` against main, with the bullet once.
- **#1147 auto-merging into the same import blocks (silent misordering).** Ruled out: ruff I001 prints 0 root lines on the merged tree.
- **Import cost at the new merge base.** Unchanged (`modset.py` above).
- **Merge mechanics.** The PR is a draft (R-5). There is also a re-merge race with #1177, #1182 and #1174 (R-1 step 4).
- **No Blocker-class risk was found that the lenses missed.**

## 6. Claims I did not take on trust, and their result

| Claim (source) | Result |
|---|---|
| main is `0324d5d6`, and #1190 is CONFLICTING/DIRTY on `source.commit` only (all three lenses) | HELD (`git fetch`, `gh pr view`, `git merge-tree --write-tree`) |
| 733 / 94 / 51, and the proposed sentence sums correctly (R-C1, R-V1, R-E2) | HELD (`recount.py`, and the generator's own `733 exports`) |
| "simulated merge was green" (R-E1) | HELD, and checked more widely. The verifier ran the full suite, not just the root packs: `1 failed, 7548 passed, 18 skipped`, and the 1 is the local-only import test. Full lint: `SDK-LINT: PASS`, 0 REGRESSED |
| `vidbyte/__init__.py` and the release note auto-merge cleanly (all three lenses) | HELD (0 markers; empty diff for the note) |
| Picking a `source` line by hand gives false provenance (R-C1) | HELD (`handpick.py`: 733 names stamped with 729- or 682-name trees) |
| The failure-code red disappears on today's main (R-E3) | HELD on pristine `0324d5d6` (2 passed) |
