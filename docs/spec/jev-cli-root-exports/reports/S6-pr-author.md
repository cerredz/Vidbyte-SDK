# S6 PR author report: jev-cli-root-exports (PR #1190, run R1)

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-jev-cli-root-exports`, branch `feat/jev-cli-root-exports`. Started at `004b5d42`; `origin/main` = `$MB` = `0324d5d6` (ancestor, exit 0, re-checked after the push). Date 2026-10-19.

## 1. What the code does (written from the diff, before reading the spec)

The squash diff against `main` changes three non-test files outside `docs/spec/`.

- `vidbyte/__init__.py`, +9 lines and 0 removed:
  - `AgentLoopSettings` joins the existing `from vidbyte.agents import (…)` block (`:54`). `vidbyte.agents` re-exports it from `vidbyte.agents.settings`, which imports it from `vidbyte/agents/settings/loop.py:46`.
  - `from vidbyte.lib.dataclasses.security import PermissionPolicy` is a new statement (`:488`), from the defining module (`security.py:33`).
  - `JevDynamicComputeOption` and `TextModelMode` join the existing `from vidbyte.lib.enums import (…)` block (`:497`, `:503`). They are defined in `vidbyte/lib/enums/jev.py:278` and `vidbyte/lib/enums/text_model.py:17`.
  - Four `__all__` entries sit beside domain siblings (`:897` after `JevComputeSettings`, `:1127`–`:1128` after `AgentStopReason`, `:1511` after `ToolPermission`). There is one new header bullet, `- Agent setting exports:` (`:13`).
  - `__getattr__`, `__dir__`, `_LAZY_NATIVE_THREAD_EXPORTS` and `__version__` are untouched.
- `contracts/sdk-public-api.json`: +4 names, and `source.commit` moves to `731f094c` (the third merge of `main`). It now lists 733 exports at 0.4.0.
- `docs/design/release-0-4-0.md`: 3 sentences change. `TextModelMode.DIRECT` is now "exported from the root and from `vidbyte.lib.enums`", a new "Later changes" sentence covers #1190, and the count is recounted to 733 = 639 + 94.
- The feature pack `tests/features/jev_cli_root_exports/` holds 5 files and 21 tests.

The real path is as follows. `import vidbyte` runs those eager imports, so after import the four names are in `vars(vidbyte)` as the defining class objects. `vidbyte.PermissionPolicy is vidbyte.tools.security.PermissionPolicy` is `True` (run). `JevAgentSettings.__post_init__` (`vidbyte/agents/jev/settings.py:153`; the checks are at `:169`–`:182`) does `isinstance` against these same classes, so objects that a root-only caller builds are accepted, and a string `model_mode` still raises `ConfigurationError`. A near-miss name still falls through the unchanged `__getattr__` (`:1645`) to `AttributeError`, without importing `vidbyte.harnesses.native`. Separately, the generator (`scripts/generate-sdk-public-api.py`, then `lint/core/public_api_contract.py:PublicApiDeriver.derive`) reads `vidbyte/__init__.py` and `pyproject.toml` as text with `ast`/`tomllib`, never imports `vidbyte`, and writes the sorted `__all__`. C016 enforces freshness. vidbyte-cli vendors the JSON (C4), and its C028 then admits `from vidbyte import X`. The header bullet says "which BaseAgent and JevAgentSettings take", and I checked it: `inspect.signature(vidbyte.BaseAgent)` has `agent_loop_settings: AgentLoopSettings | None`, `permission_policy: PermissionPolicy | None` and `model_mode: TextModelMode`.

## 2. The §4 snippet, run as written

- Extracted verbatim from spec §4 by `scratchpad/r1-s6/extract_s4.py`, which takes the first `python` block and the "Exact stdout" block.
- Ran it in a fresh `PYTHONPATH=$(pwd) py -3.11` from the worktree, with all five `*API_KEY*` variables unset (ANTHROPIC, DEEPSEEK, GEMINI, GROK, VIDBYTE; `env | grep -c API_KEY` → 0 inside the run) and `PYTHONDONTWRITEBYTECODE=1`.
- `vidbyte.__file__` → `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-jev-cli-root-exports\vidbyte\__init__.py 0.4.0`.

```
['execute', 'read', 'safe', 'write']
40 direct
['fresh_agent', 'clone']
True
exit=0
stderr bytes: 0
DIFF: identical to spec §4 Exact stdout
```

The comparison was made after `tr -d '\r'`. As a control, the same file against `git archive origin/main vidbyte pyproject.toml` (`0324d5d6`) failed with `ImportError: cannot import name 'AgentLoopSettings' from 'vidbyte' (…\main-0324\vidbyte\__init__.py)`, exit 1. **Snippet ran: yes, no correction needed.**

## 3. Independent re-proofs run by S6 (not copied from earlier stages)

| What | Command (abridged) | Result |
|---|---|---|
| Pack | `PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/jev_cli_root_exports` | `21 passed in 3.67s` |
| Contract | `scripts/generate-sdk-public-api.py --check` | `… is current at 731f094c6b23932937d7dc969b6f6c25c0b4d705 (vidbyte-sdk 0.4.0, 733 exports).` exit 0 |
| The one red | `pytest tests/features/harness_threads/test_harness_threads_surface.py` | `1 failed, 8 passed`. The failure is at `test_harness_threads_surface.py:309` (`Extra items in the left set: 'AgentLoopSettings' 'PermissionPolicy' 'TextModelMode' 'JevDynamicComputeOption'`), inside `if base is not None:` at `:304` |
| Stale reds really gone | `pytest …/test_root_native_thread_exports_contract.py -k "<the 3>"` · `git grep '28_harness_codes\|167 == 120' origin/main -- tests` | `3 passed, 4 deselected` · 0 lines. `:218` is now `…_32_harness_codes` |
| AC-6 / AC-9 / AC-13 / AC-15 | the spec's commands at `004b5d42`, `$MB` = `0324d5d6` | Only the 3 files, the 5 pack files and the spec folder differ, and the guarded-path diff is empty. The version-file diff is 0 lines, with 0 `__version__` lines and 0 removed root lines. `--is-ancestor 731f094c HEAD` exits 0, and `git show 731f094c:vidbyte/__init__.py` lists the four at `:897`, `:1127`, `:1128`, `:1511`. The release note is `3 3`, with 0 `#<n>` and `#1190` ×2 |
| AC-14 | `scratchpad/r1-s6/module_probe.py`, fresh `py -3.11` on the `origin/main` archive and on the worktree | Both trees: `count 950`, sorted SHA-256 prefix `bcad6b199764ec12`, `native_loaded false`. `four_in_vars` is all false on main and all true on the head |
| Every cited test exists | `git grep -n "def <name>"` for the 10 pack tests plus the 2 external ones | All found (acceptance `:53`; contract `:72`, `:86`, `:101`, `:126`, `:140`, `:157`, `:171`; import-time `:54`, `:102`; `root_native_thread_exports…contract.py:131`; `public_skill_loader_docs.py:91`) |
| Mermaid | `scratchpad/r1-s6/scripts/check_mermaid.mjs`, using mermaid 10.9.1's own `parse` under jsdom | pr-body block OK, spec §5 block OK. A broken control block fails |
| Key-shaped literals | `grep -nE 'sk-\|sk_\|xai-\|AIza\|ghp_\|…'` on pr-body.md | none. The push was accepted, with no GH013 |
| Doc bug claim | `PermissionPolicy(allowed={WRITE}, denied={EXECUTE})` | `TypeError: PermissionPolicy.__init__() got an unexpected keyword argument 'denied'` |
| PyPI | `https://pypi.org/pypi/vidbyte-sdk/json` | latest `0.3.0`, releases `0.1.0 0.2.0 0.2.1 0.3.0`; tags `v0.3.0`, `v0.3.1` only |

I did not run `scripts/run_ci.py`. The source-stage, package-stage and semgrep lines in the PR body are quoted from verify-log iteration 1 (`99d5f0fd`) and from the orchestrator's re-run at `0a2f20be`. The remote lines come from `gh run view 39358180543 --log` and `39358182288 --log`, which I read myself: 3.11 `7334 passed, 233 skipped in 149.49s`, 3.12 `7334 passed, 233 skipped, 19 warnings in 218.06s`, Package `Installed vidbyte-sdk 0.4.0 passed smoke checks.`, Static `Ran 1 rule on 1030 files: 0 findings.`. Both runs: `workflow_dispatch`, success, headSha `0a2f20be`.

## 4. Deviations from the spec (all recorded in the PR body)

1. **`main` was merged three times** (#1189 `b21fd94e`, #1159 `181f1992`, #1147 `0324d5d6`), against A-4's assumption of none. As a result, `source.commit` is `731f094c`, not commit A `f0527b55`. The root still differs from `main` by exactly 9 lines.
2. **The counts are 733 exports and 94 added, not 668 and 29.** FR-5, G-2, INV-17, §8.5 and §9.2 still say 668/29. INV-15's EC-7 clause and §17 carry the real numbers. INV-16's module set is 950 on both sides, not 948.
3. **The inherited-red set shrank from 5 to 1.** Only the `:309` clause remains, and it is local only.
4. **§5 had drifted ("668 sorted names").** It is redrawn to the PR's chart in `219ff9a8`.

There are no name, path or flow-step deviations in the code itself. D-2, D-3 and D-4 (import paths and `__all__` positions) and the §12.3 row-1 text all match the code exactly.

## 5. Spec finalize (`219ff9a8`)

- Frontmatter: `status: pr-open`. `pr:` and `updated: 2026-10-19` were already correct.
- §5 chart and walk-through now match the PR chart, with an italic note at the top of §5.
- §11 `…_28_harness_codes` field-guide bullet is marked historical (re-review R-C1).
- §12.5 S6 instruction names only the `:309` red, and drops Q-1 from the follow-ups because #1189 did it (R-C1).
- A §17 row is added: `r3 | 2026-10-19 | S6 PR | finalized for review …`.
- I left the §11 S1 baseline (`:408`–`:411`, "4 failed" at `b7350ed6`) alone, because it was true at its SHA and is labeled as the S1 baseline.

## 6. Final PR state

After `gh pr edit` (this was before the report commit; the title, draft state and base do not change with a push):

```
$ gh pr view https://github.com/cerredz/Vidbyte-SDK/pull/1190 --json title,isDraft,baseRefName,url
{"baseRefName":"main","isDraft":true,"title":"feat(agents): export AgentLoopSettings, PermissionPolicy, TextModelMode and JevDynamicComputeOption from vidbyte","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1190"}
$ gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1190
no checks reported on the 'feat/jev-cli-root-exports' branch
```

- `mergeable: MERGEABLE`, `mergeStateStatus: BLOCKED`. BLOCKED is expected for a draft with branch protection.
- The remote body equals `tail -n +2 pr-body.md`, apart from one trailing blank line that `gh` adds.
- The title has no `[WIP]` and no `(#N)`.
- No check attaches, because both workflows are dispatch-only. The orchestrator re-dispatches CI and Static policy on the final head.

## 7. Candidate field-guide lessons (report only; not written to the field guide)

Shape: When · Do · Because · Check · Evidence.

1. **A contract conflict after merging `main` is resolved by taking main's file and regenerating, never by picking a `source` line.** *(Refines "Main can break a long-lived feature branch …".)*
   - **When:** `git merge origin/main` conflicts in `contracts/sdk-public-api.json`, usually only on `source.commit`.
   - **Do:** `git checkout --theirs contracts/sdk-public-api.json && git add` it, then commit the merge. Next, run `scripts/generate-sdk-public-api.py` and commit the contract alone.
   - **Because:** the generator refuses uncommitted inputs and stamps HEAD. A hand-picked `source` line names a commit whose root lacks the merged names, which is false provenance, yet C016 still passes, because it compares only the data.
   - **Check:** `--check` prints `current at <merge SHA>`, and `git show <source.commit>:vidbyte/__init__.py` lists every new name.
   - **Evidence:** PR #1190 R-1: `731f094c`, then `7c8f8377`.
2. **Recount `docs/design/release-*.md` after every merge of `main`.**
   - **When:** a branch's release-note sentence states contract counts, and `main` is merged.
   - **Do:** recount from the committed contracts along `git log --first-parent v<prev>..origin/main`, plus the branch's own names, and fix only that sentence in a new commit.
   - **Because:** no test, lint rule or generator input reads the note, so the merge is silent and every gate stays green while the sentence is false.
   - **Check:** the per-PR parts sum to `exports(HEAD) − exports(v<prev>)`.
   - **Evidence:** PR #1190 R-2, `26d05084`.
3. **The `:309` clause of `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` is the only local red for a new non-native root export.** *(Refreshes "Two `harness_threads` surface tests fail locally …".)*
   - **When:** the source stage shows exactly that test failing at `test_harness_threads_surface.py:309` with "Extra items in the left set".
   - **Do:** classify it as local-only. Prove it with `9 passed` on a pristine `origin/main` worktree and a one-line `__all__` control edit, name only it in the PR body, and leave the test alone.
   - **Because:** the clause allows only native names to join root `__all__` relative to the merge base. CI has no `origin/main`, so it skips the clause, and after the squash the clause passes on `main`.
   - **Check:** the file passes on pristine `main`. Stale names to stop citing: `…_28_harness_codes` is gone (now `…_32_…`, passing since #1147), and the 3 `root_native_thread_exports` reds are green since #1189.
   - **Evidence:** PR #1190 R-3 and re-review R-C1, `99d5f0fd` and `219ff9a8`.
4. **The PR title is the squash subject on public `main`.**
   - **When:** a pipeline opened the draft PR as `[WIP] …`.
   - **Do:** before the merge, set it to `type(scope): sentence`, with no `[WIP]` and no `(#N)`; GitHub appends `(#N)`. Use a scope that `main` already uses (`agents`, `harnesses`, `skills`, …).
   - **Because:** the subject is permanent public history, and `git log` filters by scope.
   - **Check:** `gh pr view N --json title`.
   - **Evidence:** PR #1190 R-4.
5. **A draft PR cannot be merged, even with `--admin`.**
   - **When:** the merge step uses `gh pr merge N --squash --admin --match-head-commit <sha>`.
   - **Do:** run `gh pr ready N` first.
   - **Because:** GitHub refuses to merge a draft whatever the bypass rights.
   - **Check:** `gh pr view N --json isDraft` gives `false`.
   - **Evidence:** PR #1190 R-5 (verifier).
6. **Spec facts that count names belong in Proof cells, never in FR or goal text.**
   - **When:** a spec for a root-export PR states the contract's export count in FR, G or INV text.
   - **Do:** state "the four names are added" in requirements, and keep counts only in one-time Proof cells measured against `$MB`.
   - **Because:** on this repo `main` added 65 root names in one day (#1189, #1159, #1147), so FR-5, G-2 and INV-17 were stale before merge.
   - **Check:** `grep -n '[0-9]\{3\} exports' spec.md` hits only §6.2 Proof cells and §17.
   - **Evidence:** PR #1190 deviations.

## 8. Things that looked wrong while reading (none is in this PR's code)

- `tests/features/harness_threads/test_harness_threads_surface.py:309`: this is `main`'s test. Its merge-base clause makes it red locally on every branch that adds a non-native root export. It is a design limit of that test, not a bug in this PR. A follow-up could narrow it (named in the PR body's Follow-ups).
- `skills/usage/create_agent_with_tools.md:164`: `PermissionPolicy(allowed=…, denied=…)` raises `TypeError` (verified). This is a documentation bug outside this PR (spec NG-7, and in the PR Follow-ups).
- `docs/design/release-0-4-0.md:19`: the stale "Do not tag until the Meta key fix, #1184, is on `main`" sentence. #1184 merged as `513aa614` (PR Follow-ups).
- Spec FR-5, G-2, INV-17, §8.5 and §9.2 still say 668 and 29 (recorded deviation, left as the r3 design text).
- I found no vacuous test. Each pack test failed before the implementation (test-plan "Red run") and asserts identity, not equality. The acceptance test strips `*API_KEY*` variables, and the eager probe reads `vars(vidbyte)`, which a lazy hook cannot satisfy.

## 9. Commits by S6

- `219ff9a8` docs(spec): finalize jev-cli-root-exports for PR. It adds `pr-body.md` and changes `spec.md` (frontmatter, §5, §11, §12.5, §17).
- One docs commit adds this report, and fills the R-C1 fixing SHA `219ff9a8` into `pr-body.md`'s Adversarial review line. The PR body already shows that line.
