# S1 spec author report: jev-cli-root-exports (PR R1)

- **Stage:** S1 spec author, revision r1
- **Worktree:** `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-jev-cli-root-exports`, on branch `feat/jev-cli-root-exports`
- **Produced:** `docs/spec/jev-cli-root-exports/spec.md`, committed as `b53eeeb9` (`docs(spec): add jev-cli-root-exports spec r1`). This report is left uncommitted for the orchestrator, as S0's was.
- **Source edits:** none. **Tests written:** none. **Installs:** none.

## What I read

**In full:**
- house-style.md, spec-template.md and vidbyte-gates.md
- request.md, code-map.md, S0-scout.md and AGENTS.md
- the field-guide index, `local-ci-verification.md` and `review-scope.md`
- `docs/design/release-0-4-0.md` (named by the orchestrator)
- `vidbyte/lib/dataclasses/security.py`, `vidbyte/lib/enums/text_model.py`, `vidbyte/tools/security/__init__.py` and `vidbyte/tools/__init__.py`
- `scripts/generate-sdk-public-api.py`, `lint/rules/s015_public_export_integrity.py` and `contracts/README.md`
- `tests/features/root_native_thread_exports/{README.md,FEATURE.md,test_*_contract.py}` and `tests/features/public_skill_loader/test_public_skill_loader_docs.py`
- `.github/pull_request_template.md`

**The relevant parts:**
- `vidbyte/__init__.py`: the header, every import block, all of `__all__`, and the lazy and `__getattr__` tail
- `vidbyte/agents/settings/loop.py:1-70`, `vidbyte/agents/jev/settings.py:1-190` and `:330-417`, `vidbyte/agents/__init__.py:250-330`, `vidbyte/lib/enums/jev.py:1-20` and `:265-300`, `vidbyte/agents/base.py:85-115`
- `lint/rules/a006_*.py:55-80`, `lint/rules/s009_*.py:1-40`, `lint/ruff.toml`, `lint/baseline.json` (the relevant rules)
- `public_skill_loader` FEATURE.md and its contract test, `tests/features/harness_threads/test_harness_threads_surface.py:180-265` and `:88-107`, `infinite_memory` contract `:150-168`
- `scripts/run_ci.py:60-225`, `CONTRIBUTING.md:28-90`, `pyproject.toml` (version, tools), and the workflow triggers

## What I ran (all read-only against the repo; scratch files only in the session scratchpad)

- **The four names on `base_commit` and how `import vidbyte` loads them.**
  - All four are absent from the root. They are identical across every existing path.
  - All four defining modules load on `import vidbyte`; `vidbyte.harnesses.native` does not.
  - Which sub-packages export them: `vidbyte.agents`, `vidbyte.lib.enums`, `vidbyte.tools.security`, `vidbyte.lib.dataclasses` and `vidbyte.lib.config` do. `vidbyte.agents.jev`, `vidbyte.lib` and `vidbyte.tools` do not.
- **Lint on HEAD.**
  - `lint/run.py --rule C016`: CLEAN. `--rule S015`: 13 findings at baseline. The 4 on the root are ContinualTraceAgentDescriptor, FunctionTool, HandoffAgentDescriptor and ToolMixin.
  - `generate-sdk-public-api.py --check`: current, 664 exports.
  - ruff I001: 0 findings on the root.
  - Full `lint/run.py`: `SDK-LINT: PASS`. Seven rules already report IMPROVED on main: A002, S001, S009, S010, S025, S061 and S063.
- **Full pytest at HEAD** (`PYTHONPATH=<worktree> py -3.11 -m pytest`): `4 failed, 6715 passed, 17 skipped`. The 4 failures are the `assert 167 == 120` test and the 3 in `root_native_thread_exports`, which confirms the scout.
- **The import positions.** A ruff I001 probe on a scratch copy of the three import blocks, with a negative control, confirmed them.
- **The §4 snippet.** I extracted it from the spec and ran it with an in-memory shim that binds the four names on the module, which simulates the post-change root. The output matched the spec byte for byte. Without the shim it fails with `ImportError` (the red state AC-1 starts from). JevAgent constructs with `OPENAI_API_KEY` and `VIDBYTE_API_KEY` unset.
- **Counts.** `git show v0.3.0:contracts/sdk-public-api.json` has 639 exports. The new contract will have 668, and I computed the sort positions.
- **Import-time fingerprint.** `import vidbyte` loads 948 `vidbyte*` modules; the sorted names hash to SHA-256 `ff657e90…`.

## Approaches weighed

1. **Eager root imports from existing blocks and modules, a regenerated contract, one header bullet, and three release-note sentences.** Chosen. The deciding facts are that all four modules already load on `import vidbyte`, and that AGENTS.md says "Import it from its domain module" for the dataclass. Budget: 0 new files, 3 changed files, +9 lines in the root file.
2. **Lazy entries in a `_LAZY_*_EXPORTS` mapping.** Rejected (D-1, NG-9). It saves no import time, and it adds a mapping and a hook branch.
3. **A second export path, by adding the names to `vidbyte.agents.jev.__all__` as well.** Rejected. It is not requested, it is a new public path, and C028 admits only root names anyway.
- **Smaller designs rejected (§8.3):** root imports and `__all__` only, with no contract and no docs (fails FR-5 through C016, and FR-7); only three names (fails FR-4 and the CLI's Choice-parity design).

## Where I disagreed with, or extended, the scout or the request

- **The release note is the release record, and it must change.** The scout could not read it. It enumerates every root export that 0.4.0 adds (664 = 639 + 25), and it says that `TextModelMode.DIRECT` is "exported from `vidbyte.lib.enums` and not the root". Both statements become false after this PR, so §12.3 row 2 edits three sentences. The PR's sentence goes in the "Later changes on `main`" bullet, so that the list's stated range (`v0.3.0..82b46c85` plus #1099) stays true.
- **Seven lint rules already report IMPROVED on main.** The scout recorded only ratchet baselines. I made "do not lower them" explicit (§12.5), because this PR did not cause those improvements.
- **`PermissionPolicy` source path.** I chose `vidbyte.lib.dataclasses.security` (D-2) over the `vidbyte.tools.security` path that JevAgentSettings uses. Three things decided it: the AGENTS.md placement wording, the root's `SkillResolution` precedent, and `vidbyte/lib/dataclasses/__init__.py:201`, which imports it the same way.
- **Header.** I chose one new bullet, `- Agent setting exports:`, over editing two existing bullets. The precedent for a new bullet is #1179's.
- **Defining-module headers.** These stay untouched (D-9, Q-2). Nothing in them becomes false.
- **D-P2.** I agree that there is no version bump (A-5).

## Assumptions I am least sure of

- **A-1, the PR number.** The release-note sentences need `#<n>`, and the spec makes the implementer stop rather than commit a placeholder. If `pr:` is not filled when the implementer starts, the orchestrator must supply the number.
- **A-6, the package stage.** It was not run at S1, because it needs a network install into a fresh venv.
- **AC-7, the unchanged set of loaded modules.** This is easy for the implementer to check by comparison. It is harder for a test written blind, so I gave the test author the 948-module fingerprint as a fact.
- **D-4, the `__all__` placement.** I placed each name beside its domain sibling, a judgment call between two precedents. A reviewer may prefer one cluster; the flip is free.

## Addendum r2 (review round 1: SOUND WITH FIXES)

Spec r2 is commit `a9d04b51`. I applied every finding, and §16 logs each one.

- **R-1 (Blocker), accepted.** §6.1 now has two parts:
  - 6.1.a holds the permanent properties, which the test author tests.
  - 6.1.b holds the one-time diff facts, which the implementer proves once with command output and which no test may assert. These are INV-3, 6, 8 and 14, plus the new INV-15 (provenance), INV-16 (module set) and INV-17 (release note).
  - INV-4 is now a superset check plus a version equality.
  - §6.2 is split the same way, with the new AC-13, AC-14 and AC-15.
  - NG-13, §13 and §14 forbid tests that compare against base or merge base, or that pin counts, hashes or versions.
  - §13 no longer offers the 948/hash fingerprint, and it marks the harness_threads merge-base helpers "do not copy".
- **R-2 (Major), accepted.** The work is now three commits, with the draft PR opened between B and C:
  - Commit A is row 1.
  - Commit B is the regenerated contract.
  - Commit C is the release note, with the number from `gh pr view`.

  I verified that commit C touches no generator input (`lint/core/public_api_contract.py:431`). If no PR exists when P2 ends, row 2 is reported as pending, not BLOCKED.
- **R-3 (Major), accepted.** INV-2 is now a name-to-path table, verified on base. `vidbyte.lib.config` carries only `TextModelMode`.
- **R-4 (Minor, scope-adding).** I applied the text fixes but added no scope:
  - `JevDynamicComputeOption` now rests on request.md §C naming it.
  - NG-2 and A-2 name `ModelProvider` as the one closed vocabulary that stays non-root, with a root-only check. Re-verified: `JevAgentSettings(provider='x')` raises `ConfigurationError: Unsupported model provider: 'x'`, and `'ModelProvider' in vidbyte.__all__` is False.
  - New Q-3 records the question, with the default "No: not built".
- **R-5 (Minor), accepted.**
  - EC-8 to EC-12 and EC-16 to EC-21 are struck through as withdrawn.
  - AC-8 is marked as implied by INV-2 and INV-6, needing at most one smoke test.
  - AC-10 points to the existing misspelled-name test.
- **R-6 (Minor), accepted.** D-9 now cites #1099's ROLE and README edits as the runner-up's precedent. The difference: those texts listed consumers as if the list were complete, while these four headers already omit most of their re-exporters (`security.py:12` against `vidbyte/lib/dataclasses/__init__.py:201`).
- **Notes from the review's verified-claims section, both accepted.**
  - The citation for keeping `__all__` one literal list now points at S015's `_exports` (`s015_public_export_integrity.py:48-53`).
  - T-1 now says that `PermissionCeiling` defaults to `None` and that `allow_all()` was already public through `vidbyte.tools.security`.
- **Citations corrected in passing.**
  - The contract-reading test lines are now `test_infinite_memory_contract.py:166-169` and `test_root_native_thread_exports_contract.py:138-141`. Only the latter compares versions.
- **Unchanged.** The four names, the row 1 edits, the version (D-P2) and `status: draft` all stay as they were.
- **Self-check.** All 18 sections are present. Every referenced ID is defined, and none is defined twice. The only remaining `#<n>` is the row 2 template plus the rules that forbid committing it. "Two commits" survives only as D-8's runner-up.

## Addendum r3 (review round 2, final: SOUND WITH FIXES, approved)

Spec r3 is commit `4f988bdb`, with `status: approved` and `revision: 3`. I applied every finding, and §16 logs each one as round 2.

- **R-1 (Major), accepted.** Every one-time proof now measures against `MB=$(git merge-base origin/main HEAD)`, not a fixed SHA.
  - This covers AC-5, 6, 9, 14 and 15, NFR-3, and INV-3, 6, 8 and 16.
  - I named the variable `MB`, not `B`, because "commit B" already names the contract commit.
  - I re-verified the optional line myself before adding it to P4. `origin/main` is `0cce5781` (#1184 `513aa614`, #1188), with 51 files changed. The gated-path diff is empty. The four other version-literal files have no diff. Under `vidbyte/`, only `provider_keys.py` and Markdown change. A `git archive` of `0cce5781` loads the same 948 `vidbyte*` modules with SHA-256 prefix `ff657e9052f220c0`, the same as `b7350ed6`.
- **R-2 (Major), accepted.** INV-15 and AC-13 now follow the generator's own provenance rule:
  - `--check` reports `current at <source.commit>`.
  - `source.commit` is an ancestor of HEAD.
  - `git show <source.commit>:vidbyte/__init__.py` lists the four names.

  I verified that the generator keeps `source.commit` when the derived data is unchanged (`scripts/generate-sdk-public-api.py:65-67`). EC-6 is reworded to match.
- **R-3 (Major), accepted.**
  - INV-2 no longer claims the names are absent elsewhere. The `__all__` listings are context only, and no test may sweep attributes.
  - The lazy-block "unchanged" sentence moved from INV-11 to INV-6. AC-5 proves it: 9 lines added, 0 removed.
  - §13 now says "the positive pairings".
- **R-4 (Minor), accepted.** P3, §14 Always and A-1 now say that S3 makes commit C right after `gh pr create` in its Phase 6. Row 2 is pending only if that command fails.
- **Stale facts, accepted.**
  - NG-4, §9.4 and A-3 now record that #1184 merged as `513aa614` on 2026-10-19.
  - The §11 baseline now names `0e7a8eb0` as this branch's first commit.
  - The native contract citation now reads `:139-142`.
- **Coordinator item, accepted as a follow-up only.**
  - The release note's "Do not tag until the Meta key fix, #1184 …" sentence (line 19) is stale. I verified on `0cce5781` that META accepts `("LLM|", "LLM_")` at `provider_keys.py:59`.
  - The follow-up is recorded in §12.5 and in the S6 PR-body list.
  - Row 2's edits are unchanged. I did not merge `main`.
- **Unchanged.** The scope stays at four names, the version stays 0.4.0, `ModelProvider` stays non-root (Q-3), and no edit touches `vidbyte/tools/**` or the module headers.
- **Self-check (Stage E).**
  - All 18 sections are present.
  - Every referenced ID is defined, and none is defined twice.
  - None of these stale phrases remains: "at no other place", "identical to the head's", the empty-diff clause, "waits on SDK #1184", "and only it", `:138-141`, or a fixed-SHA diff in a one-time proof.
  - The file uses LF line endings.
