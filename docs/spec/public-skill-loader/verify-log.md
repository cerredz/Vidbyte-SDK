# Verification log: Public skill loader: resolve every #904 skill source without JevAgent (SDK 0.3.1)

Gate set (from context/code-map.md §1 and the S5 briefing §4; run from the worktree root):
(1) local: `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/public_skill_loader tests/features/jev_skills_preload tests/test_jev_skill_preload.py`;
(2) local, also inside the source stage: `python lint/run.py`, last line `SDK-LINT: PASS`;
(3) local: `python scripts/generate-sdk-public-api.py --check` and `python lint/run.py --rule C016`;
(4) local: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`;
(5) local, without PYTHONPATH: `python scripts/run_ci.py --stage package`;
(6) local: semgrep `typed-mapping-boundary-policy.yml` over `vidbyte` via the scratchpad wrapper `run_semgrep_without_mcp.py`, because local semgrep 1.170.1 crashes on `mcp` 2.3.0;
(7) remote only: `gh workflow run ci.yml` (jobs Source / Python 3.11, Source / Python 3.12, Package) and `gh workflow run static-policy.yml` (Static policy), both dispatch-only, so `gh pr checks` is empty.

## Iteration 1 — 2026-10-15 — agent report: reports/S5-repair-1.md (not written: the harness blocks subagent report files; the report is the agent's final message)

**Defects in:** R-1 (Major, release test pinned the literal `0.3.1`); R-2, R-3, R-4 (Minor, trivial text); R-5 (Minor, granted test edit); R-6, R-7 (follow-ups, not built). No red gate at the start (`c1eaa21b`). Mid-iteration, the orchestrator added a step: merge `origin/main` (`0754e01f`).

**Hypotheses and attempts (in order):**
- R-1. Root cause: the test compared all eight places with `RELEASE_VERSION = "0.3.1"`. Fix, as granted: compare each place with `pyproject_version(monkeypatch)` and add a `(0, 3, 1)` floor. The first draft's floor comment was 113 columns, so it was rewrapped to 72 to add nothing to R-6.
  - Proof on `git archive HEAD` scratch copies, never in the worktree:

    | Copy | Result |
    |---|---|
    | as is | 8 passed |
    | all eight places at 0.3.2 | 8 passed |
    | `llms.txt` alone at 0.3.2 | 1 failed, 7 passed |
    | all eight places at 0.3.0 | 8 failed, on `(0, 3, 0) >= (0, 3, 1)` |
- R-5. Root cause: `split(heading, 1)[-1]` returns the whole map when the heading is missing. Fix: `partition`, returning `""` when the heading is not found.
  - With the heading renamed, the pre-fix commit `e4041b3e` gave 9 passed, so the rule passed without checking anything. After the fix, a renamed heading or a level-4 heading gives 1 failed. Unchanged HEAD gives 9 passed.
  - All 15 S4 mutants are still killed.
- R-2. Text only, in `loader.py:9` and skills README `:25`, using r4's exact `Iterable` rule. `loader.py:45` is unchanged.
- R-3. The first wrap of the new `@intent` sentence filled lines unevenly (43/72/71/16 columns), which `comment-format.md` forbids. The whole block was rewrapped evenly (68/70/63/68/70/41). A001 and A002 pass.
- R-4. Premise correction: README `:23` and `:48` were not lines this PR edited. Only `loader.py:9` was. They were reworded anyway under FR-10, since that file is in §12.3 row 12. The `load()`, `documents()`, and `_pending_groups()` bodies are byte-identical to `c9d31a7f`, checked with an AST slice.
- §4 snippet, first attempt: `python -I` with a Git Bash `$(pwd)` path imported the main checkout's editable install and raised `ImportError: ConfigurationError`. The working form is `PYTHONPATH=$(pwd -W) python snippet.py` from an empty folder, without `-I`.
- 429 interruption: the session hit an API limit right after the first push of `922823f6`. The runs I had dispatched there both succeeded: CI 38817378839 and Static policy 38817385024.
- Merge of `origin/main` `0754e01f`, approved by the orchestrator:
  - Only `contracts/sdk-public-api.json` conflicted.
  - README.md, llms.txt, REPO_MAP.md, `vidbyte/agents/README.md`, and `vidbyte/__init__.py` auto-merged. For each, `git diff origin/main` has the same changed lines as this PR's `c9d31a7f..58bb0404` diff (hash-compared).
  - The contract took the branch's side only to finish the merge, then was regenerated: 643 exports, version 0.3.1. Compared with main's contract, it adds ConfigurationError, SkillLoader, and SkillResolution, and removes nothing. `--check` reports it current, and C016 passes.
- Post-merge source stage: 4 failed. Each was diagnosed (the "On main" column comes from a temporary detached worktree, since removed):

  | # | Test | On main | Cause | Verdict |
  |---|---|---|---|---|
  | (a) | `test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` | `assert 148 == 120`, fails identically | It compares with `git merge-base origin/main HEAD`, which now already contains #1036: `FailureCode` has 120 members at `f216fdcf^` and 148 at `f216fdcf` | **Inherited** |
  | (b) | `tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport` | 4 of 8 runs fail | Timing flake. Neither the test nor the transport changed in main's 15 commits. On this branch, 2 of 5 isolated runs failed | **Inherited** |
  | (c) | `::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` | passes (HEAD equals the base) | `git diff --name-only <merge-base> -- vidbyte/tools …` lists `vidbyte/tools/mcp/client.py`, the INV-16 version literal | Collision |
  | (d) | `::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` | passes (HEAD equals the base) | It asserts root `__all__` equals the merge-base's, and FR-1 adds 3 names | Collision |

  For (c) and (d), approaches considered and rejected:
  - revert the literal or the exports: breaks INV-16, AC-11, and FR-1;
  - make `client.py` read `vidbyte.__version__`: still a diff under `vidbyte/tools`;
  - hide `origin/main` so the tests skip: games the gate.

  The only fix is to edit main's test, which is outside the grant. So it is BLOCKED for an orchestrator decision.
- Remote CI checks out shallow, with no `origin/main`, so these git checks skip there: `5851 passed, 56 skipped`, against 16 skipped locally.

**Changes:**

| Commit | Change |
|---|---|
| `e4041b3e` | R-1 test |
| `852ea989` | R-5 test |
| `a5638085` | R-2 docs. The type is `docs(skills)`, not the prescribed `fix(...)`; not amended, because §12.6 forbids amending |
| `320bcb8a` | R-3 |
| `922823f6` | R-4 |
| `58bb0404` | orchestrator, pipeline.md |
| `fc0175da` | merge of `origin/main` |
| `778b094a` | contract regenerated |
| (this commit) | verify-log and review.md statuses |

**Granted test edits (exact before/after):**
- R-1, `tests/features/public_skill_loader/test_public_skill_loader_release.py`.
  - Before, `:34-35` and `:113`:
    ```python
    # D-13: 0.3.0 is released, so the first release that can carry the public loader is 0.3.1 (Q-8 may override it).
    RELEASE_VERSION = "0.3.1"
        assert read(monkeypatch) == RELEASE_VERSION, place
    ```
  - After:
    ```python
    # EC-29, D-13: 0.3.1 is the first release that carries the public
    # loader, so a later bump may raise the version but never go below it.
    FIRST_LOADER_RELEASE = (0, 3, 1)
        assert read(monkeypatch) == pyproject_version(monkeypatch), place
        assert tuple(int(part) for part in pyproject_version(monkeypatch).split(".")[:3]) >= FIRST_LOADER_RELEASE, place
    ```
  - The header changed in two places:
    - PURPOSE: "reads the release version" became "equals pyproject.toml's version, …, and that version is never below 0.3.1, the first release that carries the loader".
    - COMMON MODIFICATION PATTERNS: "The next bump changes RELEASE_VERSION;" became "A routine version bump changes nothing here, because every place is compared with pyproject.toml's version and FIRST_LOADER_RELEASE is only a floor;".
  - The eight PLACES rows and the CLI-fallback patching are unchanged.
  - A pre-release version such as `0.4.0rc1` would make `int()` raise, so the test errors loudly. That is outside the grant and was left as is.
- R-5, `tests/features/public_skill_loader/test_public_skill_loader_docs.py` `:44-46`.
  - Before:
    ```python
    # The File Index entry for vidbyte/agents/skills/, up to the next heading.
    return text.split("##### `vidbyte/agents/skills/`", 1)[-1].split("\n#", 1)[0]
    ```
  - After:
    ```python
    # The File Index entry for vidbyte/agents/skills/, up to the next
    # heading; empty when the heading is gone, so the guard fails.
    _, found, entry = text.partition("##### `vidbyte/agents/skills/`")
    return entry.split("\n#", 1)[0] if found else ""
    ```

**Gate matrix out** (final pushed code head `778b094a`, post-merge; the docs-only head `612f75e1` was also dispatched: CI 38828979286, with Source / Python 3.11, Source / Python 3.12, and Package all success at `5851 passed, 56 skipped`, and Static policy 38828981180 success):

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests + Jev area | (1) | PASS | `493 passed, 1 skipped in 4.90s` |
| lint | (2) | PASS | `S064 RATCHETED: 4 known finding(s)…` / `SDK-LINT: PASS`. Nothing REGRESSED or ERRORED. 8 rules IMPROVED (A001 642→640 after merge; A002, C011, C012, S001, S010, S025, S061 as at S0). `lint/` is identical to main's |
| contract | (3) | PASS | `contracts/sdk-public-api.json is current at fc0175dac652f9da580a302b8d4195da0a72286a (vidbyte-sdk 0.3.1, 643 exports).` / C016 `SDK-LINT: PASS` |
| source stage | (4) | **FAIL (4)** | `=========== 4 failed, 5887 passed, 16 skipped in 116.22s` / `CI failed: …pytest…`. Two are inherited (a, b) and two are collisions (c, d). Pre-merge at `922823f6`: `5243 passed, 14 skipped` / `CI passed.` |
| package stage | (5) | PASS | `Installed vidbyte-sdk 0.3.1 passed smoke checks.` / `CI passed.` |
| semgrep | (6) | PASS | `Ran 1 rule on 962 files: 0 findings.` |
| remote CI | run 38828398623 | PASS | Source / Python 3.11 = success, Source / Python 3.12 = success, Package = success. `5851 passed, 56 skipped` / `CI passed.` / `Installed vidbyte-sdk 0.3.1 passed smoke checks.` |
| remote Static policy | run 38828401693 | PASS | Static policy = success |
| §4 snippet | `PYTHONPATH=$(pwd -W) python snippet.py` from an empty folder | PASS | `house-review loaded 22 bytes` / `pdf not_found False` / `rejected: ['house-review']` |
| invariants | `git diff origin/main -- vidbyte/agents/jev/ lint/` | PASS | empty. The nine version places read 0.3.1. There is one `ConfigurationError` class (`vidbyte/lib/errors/base.py:287` after the merge). The production diff against main is the 15 §12.3 files |

**Still open:**
- Local source-stage failures (c) and (d) need an orchestrator decision on main's test `tests/features/harness_threads/test_harness_threads_surface.py`.
- (a) and (b) are inherited from main.
- No confirmed finding is open. R-6 and R-7 are follow-ups.
