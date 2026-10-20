LENS: conventions
VERDICT: MERGEABLE AFTER FIXES — The change meets every AGENTS.md rule and field-guide entry that binds it, and lint shows no worsened count. But `main` moved to `0324d5d6` (#1147, 51 new root exports) after S3, so GitHub now reports PR #1190 as CONFLICTING, and the release note's counts will be false once `main` is merged in.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- The source change is the smallest one that works, and it follows the repo's pattern. Against `main` (both merge parents and `$MB` `181f1992`), `vidbyte/__init__.py` differs by `9	0` lines. `PermissionPolicy` is imported from its domain module (`from vidbyte.lib.dataclasses.security import PermissionPolicy`, the same shape as #1099's `SkillResolution`), as AGENTS.md Placement Rules / Dataclasses requires. The other three names join existing blocks in ruff-isort order, and ruff I001 prints 0 lines for `vidbyte\__init__.py`.
- `__all__` is still one literal list of string constants: 682 names, 682 unique. Each of the four names appears exactly once, beside its domain sibling. With the four removed, the head list equals the base list in the same order. No `+=`, `.extend` or `.append` call exists.
- Every committed version of the contract is verbatim generator output. The three regeneration commits (`c0f40bfd`, `1c4452fc`, `e332e43c`) each touch only `contracts/sdk-public-api.json`, and their bytes equal the canonical render of their own source. Each merge commit (`4c2fae0f`, `76c61ffb`) holds main's contract blob byte for byte. CR = 0 in every version, and `source.commit` is always an ancestor whose `__all__` derives exactly the recorded exports.
- The commits are clean. There is one row per commit: A touches only `vidbyte/__init__.py`, B and the regenerations touch only the contract, and C touches only the release note. The subjects follow Conventional Commits with W-/FR-/AC- IDs, and every commit carries the `Co-Authored-By` trailer. The diff adds no secrets, no bytecode and no build output. `lint/` is untouched, and the test tree differs from main only by the S2 pack, which equals `09b4ef23`.

FINDINGS (ranked, most severe first, max 15)
R-V1 [Blocker] [field guide / repo rules] contracts/sdk-public-api.json:3 — The PR head `b1e17f66` is behind `main` `0324d5d6` (#1147), whose new root exports conflict with the contract and make the release note's counts false. The field guide says to re-merge whenever `main` moves.
  Evidence:
  - `git log --oneline 181f1992..origin/main` → `0324d5d6 feat(harnesses): thread helpers and verified built-in skill functions for Grok, opencode and Muse (#1147)`. Its date is 2026-10-19 18:07, after S3 finished.
  - `git diff --name-only 181f1992 origin/main -- vidbyte/__init__.py contracts …` → `contracts/sdk-public-api.json`, `vidbyte/__init__.py`.
  - `gh pr view 1190 --json mergeable,mergeStateStatus` → `"mergeable":"CONFLICTING"`, `"mergeStateStatus":"DIRTY"`.
  - `git merge-tree 181f1992 origin/main b1e17f66` → exactly 1 conflict, in the contract's `"source"` line (`5e08bef0…` vs `76c61ffb…`). `vidbyte/__init__.py` and `docs/design/release-0-4-0.md` merge cleanly.
  - Contract export counts: `181f1992` 678, `b1e17f66` 682, `origin/main` 729 (+51, 0 removed). After the merge, the derived surface is 733 names, 94 added since `v0.3.0` (639), 0 removed, and none of the four names is already on main.
  - `docs/design/release-0-4-0.md:19` at the head says "The contract now lists 682 exports … 43 added".
  - `gh run list --branch feat/jev-cli-root-exports` → `[]`.
  Failure: Squash-merging the head as it stands is impossible, because GitHub refuses a DIRTY PR even with `--admin`. If someone resolves the conflict on GitHub by picking either side, the result is a contract that is hand-merged or stale (C016 `exports-stale`), and a release note that says 682/43 while the contract lists 733. These rules apply:
  - field guide `local-ci-verification.md`, "Main can break a long-lived feature branch …; re-test after every merge" ("After each merge, run the feature's own tests and `scripts/generate-sdk-public-api.py --check`").
  - the same file, "Dispatched checks never unblock the merge" ("If main moves before it runs, merge main again and re-check"; "`gh run list --branch <head>` shows both runs on the exact `--match-head-commit` sha").
  - CONTRIBUTING.md "Making a Change" step 1 ("from the latest `main`").
  - spec EC-7 and A-4 ("merge `main`, rerun the generator in a new commit, and recompute the counts in row 2 (c)").
  - `contracts/README.md` ("Never edit a contract by hand").

  A maintainer would write: "This conflicts with main; merge #1147, regenerate the contract, and fix the counts in the release note."

  This is not an S3 mistake: main moved after S3 finished. It is still a merge blocker.
  Smallest fix: Follow the EC-7 path S3 already used twice:
  1. `git merge origin/main`. Do not rebase. Keep main's contract in the merge commit, and keep `vidbyte/__init__.py` as auto-merged.
  2. `py -3.11 scripts/generate-sdk-public-api.py`, committed alone. Expect `733 exports`, with `source.commit` set to the merge commit.
  3. In a new docs commit, change only the count sentence in `docs/design/release-0-4-0.md:19` to "733 exports, against 639 at `v0.3.0`: 94 added and none removed, 3 from #1099, 4 from #1084, 17 from #1179, 11 from #1189, 3 from #1159, 51 from #1147, 4 from #1190, and `SystemPromptPreset` from #1095". The sum is 3+4+17+11+3+51+4+1 = 94.
  4. Rerun the pack, `--check`, `lint/run.py` and both gate stages on the merge result.
  5. Dispatch CI and Static policy on the exact new head before `gh pr merge 1190 --squash --admin --match-head-commit <sha>`.
  Spec IDs: EC-7, A-4, FR-5, FR-7, INV-4, INV-15, INV-17, AC-4, AC-13, AC-15, NFR-2

R-V2 [Minor] [commit hygiene] PR #1190 title — The title the squash-merge will use as `main`'s commit subject is `[WIP] feat: Root-export …`. It has no scope, and it does not match the repo's subject convention.
  Evidence: `gh pr view 1190 --json title` → `[WIP] feat: Root-export the loop, permission, text-mode, and compute names the CLI's JevAgent needs`. `git log --format=%s -8 origin/main` shows that every squash subject has the form `type(scope): sentence (#N)`, for example `feat(harnesses): … (#1147)`, `fix(harnesses): … (#1189)` and `feat(skills): … (#1099)`.
  Failure: These sources set the convention: code-map §1.4 ("The style of recent subject lines … `feat(<scope>): <sentence> (#NNNN)`"), spec §12.4 ("subjects follow `feat(<scope>): …`"), and the precedent commits `64e2bd67` and `82b46c85`. A squash merge with the current title puts `[WIP] feat: Root-export …` on public `main` permanently. A maintainer would write: "drop [WIP] and add a scope."
  Smallest fix: When S6 writes the body, it also sets the title to `feat(exports): root-export AgentLoopSettings, PermissionPolicy, TextModelMode and JevDynamicComputeOption for vidbyte-cli`. GitHub appends ` (#1190)` on squash.
  Spec IDs: n/a (§12.4 commit-subject obligation)

VERIFIED CLAIMS:
- "`vidbyte/__init__.py` differs from main by exactly the 9 added lines" — HELD. `git diff --numstat` gives `9	0` against `b21fd94e` (from `4c2fae0f`) and against `181f1992` (from `76c61ffb`). No changed line touches `__version__`, `__getattr__`, `__dir__` or `_LAZY`.
- "`__all__` is one literal list; each of the four is listed once; nothing else is added, removed or reordered" — HELD (AST check). At `181f1992`, one `Assign`/`List` gives 678 unique names. At `b1e17f66`, it gives 682 unique, all string constants, with no mutation calls. The head with the four removed equals the base list in the same order. The neighbours are `JevComputeSettings→JevDynamicComputeOption`, `AgentStopReason→AgentLoopSettings→TextModelMode→ToolSettings` and `ToolPermission→PermissionPolicy`, matching D-4.
- "S015 = 13; its root findings are exactly NG-3's names" — HELD. `--rule S015 --all` lists 4 root findings (`ContinualTraceAgentDescriptor`, `FunctionTool`, `HandoffAgentDescriptor`, `ToolMixin`). The other 9 are pre-existing findings in `vidbyte/lib/runners/__init__.py` (7), `vidbyte/sources/llms_txt/__init__.py` (1) and `vidbyte/tools/__init__.py` (1). The briefing's "the 13 findings must be the NG-3 names only" is imprecise, because only 4 of the 13 are on the root. No finding names any of the four new exports.
- "ruff I001 prints 0 `vidbyte\__init__.py` lines" — HELD. The concise output has 0 lines for the root file. The tree-wide `Found 223 errors.` is the pre-existing S051 surface.
- "No rule regresses" — HELD, and checked independently. I ran `lint/run.py` on a scratch git copy of `$MB` `181f1992` and on the head. The per-rule FOUND counts are identical across all rules. The head ends `SDK-LINT: PASS` with 0 REGRESSED or ERRORED rows. The seven IMPROVED rules (A002, S001, S009, S010, S025, S061, S063) show the same numbers on the merge base, so this PR did not cause them.
- "Every contract version is generator output; the merges take main's contract" — HELD. Re-rendered with the codec's format, the bytes are equal at `c0f40bfd`, `1c4452fc`, `e332e43c`, `29cac984` and `b1e17f66`. The merge-commit blobs equal the main-parent blobs. CR = 0. Provenance is true each time: the `__all__` of `source.commit` derives the recorded exports, and that commit is an ancestor.
- "The #1159 conflict was resolved as main's line followed by this branch's unchanged bullet" — HELD. `git show --cc 76c61ffb` shows only that header hunk. The bullet text is byte-identical to `f0527b55`'s.
- "Commit C changes only the release note and no generator input" — HELD. `git show --name-only 29cac984` lists only `docs/design/release-0-4-0.md`. `--check` → `current at 76c61ffbd616… (vidbyte-sdk 0.4.0, 682 exports)`, exit 0. The word diff is exactly (a), (b), and (c) with the counts recomputed. There are 0 `#<n>` placeholders, the `…` is kept, and CR = 0. 3+4+17+11+3+4+1 = 43 and 639+43 = 682, both true at `b1e17f66`. Both become false after main is merged (R-V1).
- "The header bullet is one line, follows its neighbours, and `- Error exports:` keeps `ConfigurationError`" — HELD. It is line 13, in the form `    - Agent setting exports: …`, directly after `- Agent exports:`. The Error bullet is unchanged. The existing `test_public_skill_loader_docs.py` passes, and so do the 47 other tests I ran with it. The bullet's claim that `BaseAgent` takes the three types is true: `inspect.signature(BaseAgent.__init__)` has `permission_policy: PermissionPolicy | None`, `agent_loop_settings: AgentLoopSettings | None` and `model_mode: TextModelMode`.
- "§12.5: README, llms.txt, REPO_MAP and file_index have no root-export listing; no `contracts/README.md` Change Log entry" — HELD. Re-running the spec's `git grep` finds only unrelated "public API" prose. No file outside `docs/` and the pack says any of the four is "not the root". `git log -- contracts/README.md` → only `b17222cd` (#628), so no regeneration PR (#1099, #1179, #1189, #1159, #1147) has added a Change Log line.
- "D-9 / Q-2: the four headers make no complete-list claim" — HELD. `loop.py:14` says "Exported from vidbyte.agents.settings" but already omits `vidbyte.agents`. `security.py:12` names only `vidbyte.tools.security.permissions`. The `text_model.py` and `jev.py` ROLE lines describe behaviour consumers, not export paths. No folder README lists consumers of the four, unlike the `vidbyte/agents/README.md:398` text that #1099 edited.
- "The S2 pack meets the repo's test conventions" — HELD:
  - All 3 `.py` files carry the 7 A001 fields.
  - The README File Index lists all 5 children (S020).
  - The FEATURE.md headings match `public_skill_loader` and `root_native_thread_exports`.
  - No duplicate test basenames exist in `tests/`.
  - No `#` comment line is over 72 columns (`comment-format.md` quick check).
  - No test reads `docs/`.
  - The pack is unchanged since `09b4ef23` (0-line diff), and its 21 tests pass.
- "AC-6 (2) and AC-9 are empty" — HELD. Both diffs from `$MB` to `b1e17f66` print nothing.
- "origin/main is an ancestor of the head" (briefing §2) — HELD for `181f1992`, but stale. `origin/main` is now `0324d5d6`, which is not an ancestor (R-V1).
- The `docs/` opacity rule — HELD. The only file outside the spec folder that is touched is `docs/design/release-0-4-0.md`, which request.md §C asks for ("add them there"). This review read only that file and the spec folder. Committing the `docs/spec/<slug>/**` artifacts and their local paths follows main's precedent (182 files under `docs/spec` on main contain `C:/Users/422mi`).

COMMANDS RUN:
- `git diff --stat origin/main...b1e17f66` → `19 files changed, 2471 insertions(+), 4 deletions(-)` (implementer files: `vidbyte/__init__.py` +9, contract 6, release note 6).
- `git log --oneline 181f1992..origin/main` → `0324d5d6 … (#1147)`; `gh pr view 1190 --json mergeable,mergeStateStatus,headRefOid` → `CONFLICTING`, `DIRTY`, `b1e17f66…`.
- `git merge-tree 181f1992 origin/main b1e17f66 | grep -c '<<<<<<<'` → `1` (contract `source` line).
- contract counts per revision (scratch script) → `v0.3.0 639`, `181f1992 678`, `b1e17f66 682`, `origin/main 729`; merged union `733`, `94` added since `v0.3.0`, `0` removed.
- `PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) py -3.11 lint/run.py` → `exit=0`, `SDK-LINT: PASS`, `C016 0 0 CLEAN`, `S015 13 13 RATCHETED`, `A001 642 642 RATCHETED`, `S051 259 259 RATCHETED`, `S062 889 889 RATCHETED`, REGRESSED/ERRORED count 0.
- the same lint on a scratch git copy of `181f1992` → `SDK-LINT: PASS`; the per-rule counts diffed against the head → `IDENTICAL`.
- `PYTHONPATH=$(pwd) py -3.11 lint/run.py --rule S015 --all` → 13 findings (4 root NG-3, 9 non-root, pre-existing).
- `py -3.11 -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache --output-format concise` → `root-init I001 lines: 0`; `Found 223 errors.`
- AST `__all__` check (scratch `r1-s4/conv_allcheck.py`) → `head minus four == base (order kept): True`, `added: [the four] removed: []`.
- contract provenance check (scratch `r1-s4/conv_contract_prov.py`) → `canonical_bytes=True`, `provenance_ok=True` and `ancestor=True` at every regeneration commit and at the head; the merge commits hold main's blobs.
- `git show --cc 76c61ffb` → one header hunk (main's `- Agent exports:` line, then the unchanged bullet); `git diff --numstat <main parent> <merge> -- vidbyte/__init__.py` → `9	0` for both merges.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/jev_cli_root_exports` → `21 passed in 4.39s`.
- `… pytest … test_public_skill_loader_docs.py tests/features/root_native_thread_exports test_public_skill_loader_release.py test_output_connectors_followup_contract.py` → `48 passed in 2.51s`.
- `py -3.11 scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 76c61ffbd61632af5c96e472e00208a87109abaf (vidbyte-sdk 0.4.0, 682 exports).` (exit 0).
- `git diff --name-only $MB b1e17f66 -- vidbyte/tools vidbyte/lib/configs …` → empty; the AC-9 version-file diff → 0 lines; `git diff --name-only origin/main...b1e17f66 -- lint tests scripts .github` → only the 5 pack files.
- `git diff 09b4ef23 b1e17f66 -- tests/features/jev_cli_root_exports | wc -l` → `0`.
- `gh run list --branch feat/jev-cli-root-exports` → `[]`; `gh pr view 1190 --json title` → `[WIP] feat: Root-export …`.
- commit messages (`git log -1 --format=%B` for all 11 work commits) → Conventional Commits subjects with IDs, `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` on each.
- a scan of added lines for secrets and emails → none (only `noreply@anthropic.com` and a decorator match).
