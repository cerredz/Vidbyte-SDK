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
