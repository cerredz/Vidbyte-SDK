LENS: conformance
VERDICT: SOUND — Every repair (R-1, R-2, R-3) holds when proved again from raw git objects and from execution, independently of the repair agent's scripts. The squash is exactly main plus this PR's 9 root lines, 4 contract names with a true stamp, and 3 release-note lines. The only residue is one Minor spec sentence that still tells S6 to name stale inherited reds in the PR body.

Scope of this re-review: post-repair round 1 at head `0a2f20be`, with `origin/main` = `$MB` = `0324d5d6` (fetched 2026-10-19, ancestor exit 0). It covers `git diff b1e17f66 0a2f20be`, which is mostly #1147 arriving through the merge, and `git diff origin/main...0a2f20be`, the squash. Every check below was run by me, with my own scripts under `scratchpad/r1-rereview/`. They read `git show <rev>:<path>` blobs and import no repo code, except where a command named in the spec (`--check`, `lint/run.py`, pytest) is the thing being proven.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **No hand edit anywhere in the merge.** `git merge-tree --write-tree 6c852a3f 0324d5d6` replays the merge mechanically to tree `81ddbdad`, with one conflict, in the contract. `git diff --stat 81ddbdad 731f094c` shows only `contracts/sdk-public-api.json | 8 --------`, which is exactly the 8 conflict-marker lines removed. Every other file in `731f094c`, including `vidbyte/__init__.py`, is git's own auto-merge. The merge's contract blob `e200af8a` is main's blob `e200af8a`.
- **The contract is pure generator output, proven without the generator.** My own renderer, written from the canonical format in `lint/core/public_api_contract.py:101-112`, takes `sorted(set(literal __all__))` from `git show 731f094c:vidbyte/__init__.py`, the `pyproject.toml` version, and the full SHA `731f094c…`. Its output is byte-identical to the `7c8f8377` blob (`4ba31d11`), which is also the head's blob. The same renderer reproduces main's blob byte for byte (a control). CR = 0.
- **The root resolution is lossless.** Head `__all__` = 733 names, 733 unique, one literal list (1 `Assign`, no `AugAssign` or `.extend`/`.append`). `head − main` is exactly the four, and `main − head` is empty. Head with the four removed equals main's 729 **in the same order**, so none of #1147's 51 names is lost, duplicated or moved. The `+` lines of `git diff -U0 origin/main 0a2f20be -- vidbyte/__init__.py` are byte-identical to the `+` lines of `git diff -U0 181f1992 b1e17f66`, so the 9-line change survived the merge unchanged.
- **The merged tree changes nothing at import time.** On a `git archive 0324d5d6` and on the head, both trees load 950 `vidbyte*` modules, sorted SHA `bcad6b199764ec12`, load-order SHA `6fa27c08e3b32a68`, in the same order, with native unloaded and 0 process audit events. All 12 INV-2 pairs are `is`-identical. The §4 snippet prints the 4 spec lines exactly (after Windows CRLF is normalized). Do not touch `vidbyte/__init__.py` again.

FINDINGS (ranked, most severe first, max 15)
R-C1 [Minor] [user's words / deviations] `docs/spec/jev-cli-root-exports/spec.md:515` (also `:390`) — §12.5's S6 instruction still names inherited reds that no longer exist, so the R-3 repair is incomplete for the stage that consumes it
  Evidence: `spec.md:515`: "PR body (S6): name the inherited failures, each with proof on pristine `main`. These are the 3 in `root_native_thread_exports`, the `assert 167 == 120` test, and the local-only `test_import_vidbyte_starts_no_process…`." `spec.md:390`: "`test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` fails on main itself: inherited, so name it in the PR body." On the head, the three `root_native_thread_exports` tests give `3 passed, 4 deselected`. `git grep -n "28_harness_codes\|167 == 120" 0324d5d6 -- tests` gives 0 lines. On a pristine `0324d5d6`, `test_harness_threads_surface.py` gives `9 passed in 2.80s`. R-3 (review.md:22) said "give S6 the post-merge set, not `171 == 120`". `99d5f0fd` fixed NFR-2, §11's baseline note, §13 and §17, but not §12.5 or the §11 field-guide bullet.
  Failure: S6 follows §12.5 as written → the PR body, which goes to public main with the squash, claims four failures that pass or do not exist, with "proof on pristine main" that cannot be produced. The one real red, `:309`, is listed beside them, so a human reviewer cannot tell which claim is true. No code or gate changes.
  Smallest fix: in §12.5, replace the list with: "the local-only `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded`, red only at its merge-base clause (`test_harness_threads_surface.py:309`, inside `if base is not None:`), which passes on pristine `0324d5d6`; CI skips that clause." Mark the `:390` bullet "historical: passes since #1147 renamed it `…_32_…`". Or put the same text in the S6 briefing, which leaves the spec as history and needs no new commit.
  Spec IDs: NFR-2 (the named inherited set), §12.5, review R-3

VERIFIED CLAIMS:
Repairs:
- **R-1 provenance: HELD.**
  - `git diff 0324d5d6 731f094c -- contracts/sdk-public-api.json` is 0 lines, with the same blob `e200af8a`.
  - `7c8f8377` touches only the contract (`5 +, 1 −`): the `source` line from `5e08bef0…` to `731f094c…`, plus `AgentLoopSettings`, `JevDynamicComputeOption`, `PermissionPolicy` and `TextModelMode`, each in sorted position. It is generator output, proved byte for byte by an independent render.
  - `git show 731f094c:vidbyte/__init__.py` lists the four at `:897`, `:1127`, `:1128` and `:1511`, plus the header bullet at `:13`.
  - `git merge-base --is-ancestor 731f094c HEAD` exits 0, and the contract is unchanged from `7c8f8377` to the head.
- **R-1 root resolution: HELD.**
  - `git diff --numstat origin/main 0a2f20be -- vidbyte/__init__.py` gives `9	0`. 0 changed lines mention `__getattr__`, `__dir__` or `_LAZY`.
  - S015 `--all`: the same 13 findings on the head and on pristine main (119 lines, identical after stripping line numbers). The 4 root findings are the NG-3 names, and none of the four is mentioned. C016 is `0 0 CLEAN`. ruff I001 prints 0 root lines.
- **R-2 arithmetic: HELD.**
  - `v0.3.0` has 639 exports and is an ancestor of `origin/main`.
  - Diffing the contract along all 98 first-parent commits of `v0.3.0..origin/main` gives #1095 +1, #1084 +4, #1179 +17, #1099 +3, #1189 +11, #1159 +3 and #1147 +51, with 0 removed and 0 names added and then removed. Adding #1190's 4 (`head − origin/main`) gives 94. 639 + 94 = 733, which equals the head's 733 (unique, sorted).
  - Lag control: at all 99 commits, main's contract equals `sorted(set(literal root __all__))`, with 0 mismatches. So no export is credited to a later PR. `-S'"GrokThreadScope"'` on main's first parent gives `0324d5d6 … (#1147)`.
  - `git diff --word-diff b1e17f66 0a2f20be -- docs/design/release-0-4-0.md` shows only `[-682-]{+733+}`, `[-43-]{+94+}` and `{+51 from #1147,+}` (numstat `1 1`). Against `$MB` the numstat is `3 3`, with 0 `#<n>`, `#1190` ×2, and CR 0. The sentence's parts are 3+4+17+11+3+51+4+1 = 94.
- **R-3 truth: HELD for NFR-2, §11 (`:411`), §13 (`:573-575`) and §17; NOT HELD for §12.5 (R-C1).**
  - Pristine detached worktree `0324d5d6` (`git worktree add`, later removed, clean): `9 passed`, and the `…_32_harness_codes` test passes.
  - Head: `1 failed, 8 passed`, at `:309` only, with the four as the "Extra items". The `:302` process/native assertion passes.
  - The helper `optional_merge_base()` (`:131-136`) returns None without `origin/main`, so CI skips only the clause, as the spec now says. After the squash, on main, the merge base is main itself, so the clause passes and no red is passed on to main.

Proof cells reproduced at `$MB` = `0324d5d6` (5 of 7):
- **AC-5: HELD.** In my scratch worktree, checked out at `731f094c`: `--check` → `stale: exports added: AgentLoopSettings, JevDynamicComputeOption, PermissionPolicy, TextModelMode` (exit 1, no `exports removed` line). At `7c8f8377` → current (733).
- **AC-6: HELD.** Outside the spec folder, only the 8 files differ. The second command prints nothing. `tests` differs from main only by the pack, and the pack equals `09b4ef23` (0 lines).
- **AC-9: HELD.** The version-file diff is 0 lines, with 0 `__version__` and 0 `"version"` changed lines. All 9 INV-8 places read `0.4.0`.
- **AC-12: HELD.** Full `lint/run.py` on the head and on pristine main: `SDK-LINT: PASS` on both, and 91 table rows (48 CLEAN, 36 RATCHETED, 7 IMPROVED), identical across the two trees (`diff` empty). Head: C016 0, S015 13, A001 642, S051 259, S062 889, S020 1, and 0 REGRESSED or ERRORED rows.
- **AC-13: HELD.** `--check` at the head → `current at 731f094c6b23932937d7dc969b6f6c25c0b4d705 (vidbyte-sdk 0.4.0, 733 exports).` (exit 0).
- **AC-14: HELD.** Numbers as in "gets right" above.
- **AC-15: HELD.** Numbers as in R-2 above.

Regression sweep on the merged tree:
- **AC-1: HELD.** The §4 snippet, extracted by `awk` from spec.md, run with every `*API_KEY*` variable unset (the child confirms `[]`): exit 0, empty stderr, and stdout identical to the spec block after CRLF→LF.
- **INV-1, INV-2, INV-5 and INV-13: HELD.** Eager binding in `vars`, `__all__.count == 1` for each name, 12/12 `is` pairs, and `__all__` membership at every listed re-export path. `import vidbyte` loads native: False. Audit-hook process events: `[]`.
- **INV-7: HELD.** The default policy is `['read', 'safe']`. `allow_all == frozenset(ToolPermission)`. The loop defaults are `None/None/None/25/3`. The text modes and compute members keep their values in order. The compute default is fresh_agent, fork_agent, subagent. A string `model_mode` raises `ConfigurationError`, and the default is `auto`.
- **INV-9: HELD.** The star import binds all 733 names, and the four are the root objects.
- **INV-11: HELD.** Reading `vidbyte.PermissionPolicies` raises AttributeError, and `from vidbyte import TextModelModes` raises ImportError. Native stays unloaded.
- **INV-10 and INV-12: HELD.** `- Agent setting exports:` appears once, and `- Error exports:` keeps `ConfigurationError`.
- **One class per name: HELD.** Each name has one definition: `loop.py:46`, `security.py:33`, `jev.py:278`, `text_model.py:17`. `vidbyte.harnesses.native.__all__` contains none of the four.
- **Pack and surface tests: HELD.** The pack gives `21 passed in 3.57s`. All 16 test files that read the root `__all__` or the contract, plus the root_native, public_skill_loader, sdk_loop_settings, infinite_memory, harness_threads, jev_compute_clone and restore_permission_policy suites, give `2 failed, 1950 passed, 4 skipped`. The 2 failures are the one `:309` test, collected twice (by file and by directory).

Orchestrator's facts:
- **Remote state: HELD.** CI `39358180543` and Static policy `39358182288` are both `success`, headSha `0a2f20be`. The CI log shows 3.11 and 3.12 each at `7334 passed, 233 skipped`, `SDK-LINT: PASS`, and `Installed vidbyte-sdk 0.4.0 passed smoke checks.` `gh pr view 1190` shows MERGEABLE, BLOCKED, `isDraft: true`, headRefOid `0a2f20be`. `ls-remote` gives main `0324d5d6` and the branch `0a2f20be`.
- **"The squash touches exactly 8 files": HELD only outside the spec folder.** The squash also adds 18 files under `docs/spec/jev-cli-root-exports/**`. AC-6 and INV-6 permit them, and main's precedent matches: all 15 spec folders on main carry `request.md` and `reports/`. Across the squash's added lines, the key-shaped scan and the email scan both find 0 hits.

ID walk (conformance; tie goes to the prosecution):
- **Held at the head:** G-1, G-3, FR-1 to FR-4, FR-6, FR-8, FR-9, NFR-1, NFR-3 and NFR-4.
- **Held under EC-7's 733 escape:** INV-3, INV-4, INV-6, INV-8, INV-14 to INV-16, INV-15, and AC-1 to AC-15.
- **Stale text only, a known follow-up and not re-raised:** FR-5, G-2 and INV-17, which still say 668/29.
- **NFR-2:** held on the code; the stale text is R-C1.
- **EC-5 (false stamp):** excluded by the merge-tree replay.
- **EC-7:** followed (merge, never rebase).
- **T-3 (an extra name slipped in):** excluded, because `head − main` = the four.
- **§14 Never:**
  - no hand edit;
  - no `vidbyte/tools` or `vidbyte/lib/configs` change;
  - no version change;
  - no placeholder;
  - `lint/` is untouched (0 lines);
  - no test weakened (only the pack differs from main);
  - no bytecode in the squash file list.
- **§8.4 budget:** 0 new files for the implementer, and 3 implementer files.
- **Settled decisions (four names, 0.4.0, Q-2, Q-3, NG-13):** none reversed.

COMMANDS RUN: (cwd = the worktree unless named; S = `scratchpad/r1-rereview`)
- `git fetch origin`; `git merge-base --is-ancestor origin/main 0a2f20be` → exit 0; `git merge-base origin/main 0a2f20be` → `0324d5d6…`
- `git diff --numstat origin/main 0a2f20be -- . ':(exclude)docs/spec/jev-cli-root-exports'` → `5 1` contract, `3 3` note, `9 0` root, pack +89/+17/+74/+184/+125
- `git rev-parse 0324d5d6:contracts/… 731f094c:… 7c8f8377:… 0a2f20be:…` → `e200af8a e200af8a 4ba31d11 4ba31d11`
- `git merge-tree --write-tree 6c852a3f 0324d5d6` → exit 1, `CONFLICT (content): … contracts/sdk-public-api.json`, `Auto-merging vidbyte/__init__.py`; `git diff --stat 81ddbdad 731f094c` → `contracts/sdk-public-api.json | 8 --------`
- `py -3.11 -I S/prov.py <wt>` → `head - main: [the four]  main - head: []`, `head without the four == main (same order): True`, `independent render == 7c8f8377 contract bytes: True`, `independent render of main == main blob: True`
- `py -3.11 -I S/recount.py <wt>` → `added since v0.3.0: 94 removed since v0.3.0: 0`, `sum of per-PR parts incl. #1190: 94`, `639 + added == head: True`
- `py -3.11 -I S/lagcheck.py <wt>` → `commits checked: 99 mismatches: 0`
- `git diff --word-diff=plain b1e17f66 0a2f20be -- docs/design/release-0-4-0.md` → `[-682-] {+733+} [-43-] {+94+} {+51 from #1147,+}`
- `git worktree add --detach …/r1-rereview-pristine 0324d5d6`; there, `PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/harness_threads/test_harness_threads_surface.py` → `9 passed in 2.80s`; the same on the head → `test_harness_threads_surface.py:309: AssertionError`, `1 failed, 8 passed in 2.09s`
- In the pristine worktree, `generate-sdk-public-api.py --check` at `0324d5d6` → `current at 5e08bef0… (729 exports)` (exit 0); at `731f094c` → `stale: exports added: AgentLoopSettings, JevDynamicComputeOption, PermissionPolicy, TextModelMode` (exit 1); at `7c8f8377` → `current at 731f094c… (733 exports)` (exit 0). On the head → `current at 731f094c6b23932937d7dc969b6f6c25c0b4d705 (vidbyte-sdk 0.4.0, 733 exports).` (exit 0)
- `PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) py -3.11 lint/run.py` on the head and on the pristine worktree → `SDK-LINT: PASS` on both; 91 rows each; `diff` of the rule rows is empty
- `lint/run.py --rule S015 --all` on both trees → 13 `is invalid` on each, identical after stripping line numbers; `--rule C016 --all` → `C016 … 0 0 CLEAN`, `SDK-LINT: PASS`
- `py -3.11 -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` → 0 `vidbyte\__init__.py` lines; `223 fixable` (pre-existing)
- §4 snippet: `env -u <every *API_KEY*> PYTHONPATH=<wt> py -3.11 S/snippet.py` → exit 0, stderr 0 bytes; `cmp` after CRLF→LF → `STDOUT IDENTICAL`
- `PYTHONPATH=<wt> py -3.11 S/probe.py` → `pairs identical: 12 of 12`, `native_loaded: False`, `process_events: []`, near-miss `AttributeError`/`ImportError`, `native_after: False`
- `git archive $MB vidbyte pyproject.toml | tar -x -C S/mb-archive`; `py -3.11 S/modules.py <archive> <wt>` → both `950`, `bcad6b199764ec12`, `6fa27c08e3b32a68`, `same load order: True`
- AC-6 and AC-9 commands (spec text) → as in VERIFIED CLAIMS; `git diff --stat origin/main...0a2f20be -- lint` → 0 lines
- `PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/jev_cli_root_exports` → `21 passed in 3.57s`; surface set → `2 failed, 1950 passed, 4 skipped in 219.52s` (one test twice)
- `pytest tests/features/root_native_thread_exports -k "every_native_export_is_listed or each_root_name_is_the_native_object or lists_every_root_native_name"` → `3 passed, 4 deselected`; `git grep -n "28_harness_codes\|167 == 120" 0324d5d6 -- tests` → 0
- `gh pr view 1190 --json …` → `MERGEABLE`, `BLOCKED`, `isDraft: true`; `gh run view 39358180543` / `39358182288` → `success`, headSha `0a2f20be…`; `gh run view 39358180543 --log` → `7334 passed, 233 skipped` (3.11 and 3.12), `CI passed.`
- `git worktree remove …/r1-rereview-pristine` → exit 0; `git worktree list` has 0 matches; worktree `git status --short` has 0 lines
