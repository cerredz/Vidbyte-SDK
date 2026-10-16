# Verification log: Public skill loader: resolve every #904 skill source without JevAgent (SDK 0.4.0)

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

## Iteration 2 — 2026-10-15 — agent report: reports/S5-repair-2.md

**Defects in:**
- No open confirmed finding in code: R-C11, R-C12, and R-C13 were fixed in spec text by `ed354f3a` (r5) and `b1a970c4` (FEATURE.md), and only their statuses were left to update. R-C10 stays refuted.
- The user's decisions D-15 and D-16 (spec r5) made three items:
  - V: move the release to 0.4.0 (rows 3(a), 4-11);
  - T: raise the release test's floor to 0.4.0, as an orchestrator-granted test edit (AC-11);
  - N: add the release notes, `docs/design/release-0-4-0.md` (row 16, FR-13, AC-19).
- No red gate at the start (`835c0da5`) apart from the four inherited local source-stage failures (a) to (d) from Iteration 1.

**Hypotheses and attempts (in order):**
- **V, the literals.** `git grep -n -e "0\.3\.1" -e "0, 3, 1" -e "0_3_1" -e "0-3-1" -- ':!docs'` found the nine places named in INV-16, at the line numbers row 7 gives, plus four lines of the release test's text. Each of the eight hand-edited literals was changed by `sed` at its own line number, and `git diff` showed exactly 8 changed lines.
  - Re-grepping before the commit left only the contract and the test.
  - Later, `git grep -e "0\.3\.0" -e "<0\.4" -e ">=0\.3" -- ':!docs'` found nothing, so no other place pins the old minor.
  - D-15's flip condition does not hold: `origin/main` (local ref `aac190e9`) still reads `version = "0.3.0"`, with no `v0.4.0` tag. Its #1103 to #1107 touch no version place and not the contract.
- **V, the contract.** `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py` ran on the clean tree and printed `wrote … at 013cf884… (vidbyte-sdk 0.4.0, 643 exports)`. The data diff is exactly `"version"` and `source.commit`, and the file was committed alone. Nothing was amended.
- **T.** The pack was green at the contract commit (67 passed, because 0.4.0 is above the old floor (0, 3, 1)), so the test edit came after the bump.
  - The grant names lines `:3`, `:9`, and `:34-36`, and the category "docstring/comment lines that name 0.3.1 or D-13". Two more header lines name D-13: `:4` (ROLE IN CODEBASE, "Covers spec AC-11, INV-16, FR-8, D-13 and EC-29") and `:10` (RELATED DOCS, "8.1 D-13").
  - Reading the category as the grant, only the token `D-13` was changed to `D-15` on those two lines. **Flag for the orchestrator:** if the line list was meant to be exhaustive, revert `:4` and `:10` (2 tokens).
  - No assertion changed.
- **T, the proof that the test still fails at 0.3.x.** Scratch copies made with `git archive HEAD`, plus the edited test, imported through `PYTHONPATH` from an empty folder, never in the worktree:

  | Copy | Result |
  |---|---|
  | all eight places at 0.4.0 | 8 passed |
  | all at 0.3.1 | 8 failed, `assert (0, 3, 1) >= (0, 4, 0)` |
  | all at 0.3.9 | 8 failed, `assert (0, 3, 9) >= (0, 4, 0)` |
  | all at 0.3.0 | 8 failed, `assert (0, 3, 0) >= (0, 4, 0)` |
  | all at 0.4.1 | 8 passed |
  | all at 0.5.0 | 8 passed |
  | `llms.txt` alone at 0.3.1 | 1 failed, 7 passed, `assert '0.3.1' == '0.4.0'` |

- **N, the release notes. Every claim was checked against git or a probe, not memory:**
  - **PR list.** `git log --first-parent --oneline v0.3.0..0754e01f` lists 18 PRs: 3 features (#1036, #1027, #1095) and 15 fixes, grouped by commit scope: compaction 6, context 4, and one each in providers, agents, sessions, jev, and algorithms.
  - **Root signatures.** A probe compared `inspect.signature` of every root export, from `git archive` copies of `v0.3.0` and HEAD (639 and 643 names).
    - `api_key` is removed from exactly 11 signatures on 8 roots: `Agent`, `Agent.restore`, `AgentRoleSettings`, `AgentRunnerConfig` (first parameter `api_key` → `api_keys`), `AggregateAgent`, `BaseAgent`, `BaseAgent.restore`, `JevAgentSettings`, `JevRunBriefSettings`, `Session.fork_from`, and `Session.resume`.
    - All 11 take `api_keys`, and all but `AgentRunnerConfig` and `JevRunBriefSettings` take `vidbyte_api_key`.
    - `model_mode=TextModelMode.AUTO` is on `Agent`, `AgentRunnerConfig`, `AggregateAgent`, `BaseAgent`, and `JevAgentSettings`.
    - `api_key` remains on `AnthropicSkill`, `OpenAISkill`, `LinearIssueOutput`, `NotionPageOutput`, and `TypefullyDraftOutput`.
    - `algorithm=` is new on the two `restore` methods, `Session.resume`, and `Session.fork_from` (#1093).
    - `system_prompt_presets` is on `Agent`, `BaseAgent`, and `JevAgentSettings` (#1095).
    - Root names: 4 added (`ConfigurationError`, `SkillLoader`, `SkillResolution`, `SystemPromptPreset`), 0 removed.
  - **Gateway probe** at HEAD, with `httpx` send faked, a fake `OPENAI_API_KEY`, and no `VIDBYTE_API_KEY`:
    - `Agent(..., api_key=…)` raises `TypeError: BaseAgent.__init__() got an unexpected keyword argument 'api_key'`.
    - `Agent(...).run("hello")` raises `AgentExecutionError`, caused by `ConfigurationError: Missing Vidbyte API key. Pass vidbyte_api_key or set VIDBYTE_API_KEY, or use mode=TextModelMode.DIRECT …`, with 0 requests sent.
    - `TextModelMode` is in `vidbyte.lib.enums.__all__`, not in `vidbyte.__all__`.
  - **#1036.**
    - `FailureCode` goes from 120 members at `v0.3.0` to 148 at HEAD.
    - 9 `*_thread` functions are in `vidbyte.harnesses.native.__all__`.
    - Its squash diff deletes no file under `vidbyte/`, so the "removed" items in its body never shipped.
  - **No dependency change.** `git diff v0.3.0 HEAD -- pyproject.toml` changes only the version line.
  - **publish.yml** runs `validate-tag`, then `ci` (`ci.yml`), then `publish` through the `pypi` environment.
- **N, a deviation from row 16's wording.** Row 16 heads the list "from `git log --first-parent v0.3.0..HEAD`", but on this branch that range shows only #1086 to #1088: the merge's second parent carries the rest. So the doc cites `v0.3.0..0754e01f` plus #1099.
  - #1103 to #1107, on the local `origin/main` ref and not on this branch, appear as "fixes merged there after `0754e01f` ship too … at the time of writing", naming #1104 by its own subject.
  - The doc has 15 lines, as the precedent does, and no other `docs/` file was read.
- **Source stage, first run: a fourth failure.** `tests/features/coding_agent/test_coding_agent_environment.py::test_real_bash_reports_its_version_and_git` failed with `Tool probe failed: bash did not finish within 15 seconds` (`CODING_ENVIRONMENT_PROBE_TIMEOUT_SECONDS`).
  - Hypothesis: host load, not this PR.
  - Evidence:
    - (1) None of this iteration's commits, and nothing in the PR, touches the coding agent or `vidbyte/tools/builtins/`.
    - (2) It failed 3 of 3 in isolation (about 16 s each), and identically on a `git archive 0754e01f` copy, the merge-base.
    - (3) A bare `bash -c` took 0.95 s, but the probe script took 33 s under xtrace, spread over the tools' `--version` calls (1 to 4 s each).
    - (4) Host CPU was at 100%, with two long-lived `bash` processes of about 4,500 CPU-seconds each, not this session's, left alone.
    - (5) After the load eased it passed (`1 passed in 9.10s`), and the source-stage re-run passed it.
  - Verdict: environmental and inherited. It is not a test or timeout change for this PR.
- **Semgrep fixtures, first attempt.** `python -I run_semgrep_without_mcp.py --test …` hung for more than 600 s, with 8 idle spawn workers, and printed Python's `freeze_support()` spawn error. The cause: the scratch wrapper calls `main()` at module level with no `__main__` guard, so Windows spawn workers re-import it.
  - Fix, in scratch only: `it2/run_semgrep_guarded.py`. It keeps the `mcp` stub at module level and moves `main()` under `if __name__ == "__main__"`, so `--test` passes.
  - Use the guarded wrapper for `--test`. Either wrapper works for `scan`.
  - `.semgrep/` and the workflows have no diff against `origin/main`.

**Changes:**

| Commit | Change |
|---|---|
| `013cf884` | V: the eight literals to 0.4.0, as `release: bump vidbyte-sdk to 0.4.0 (D-15, rows 4-10)`. 8 files, +8/-8 |
| `46416739` | V: contract regenerated alone, as `chore(contracts): regenerate the public-API contract for 0.4.0 (W-5, row 11)`. Version and `source.commit` only |
| `dc522090` | T: the granted test edit, alone. 6 lines |
| `93a2b1a8` | N: `docs/design/release-0-4-0.md`, alone. 15 lines |
| (this commit) | the verify log, the review.md statuses (R-C11 `fixed @ed354f3a (spec r5)`, R-C12 `fixed @ed354f3a`, R-C13 `fixed @ed354f3a, b1a970c4`), and `reports/S5-repair-2.md`. The log title now says SDK 0.4.0, as the spec's does |

**Granted test edit (exact before/after),** in `tests/features/public_skill_loader/test_public_skill_loader_release.py`. Only the named token changed on each line, and no assertion changed. `:35` ("loader, so a later bump may raise the version but never go below it.") is unchanged.

| Line | Before | After |
|---|---|---|
| `:3` | `… and that version is never below 0.3.1, the first release that carries the loader.` | `… never below 0.4.0, …` |
| `:4` | `ROLE IN CODEBASE: Covers spec AC-11, INV-16, FR-8, D-13 and EC-29 for …` | `… FR-8, D-15 and EC-29 …` (outside the grant's line list; see above) |
| `:9` | `KNOWN EDGE CASES: YAML reads the placeholder 0.3.1 as text, since it has two dots. …` | `… the placeholder 0.4.0 as text …` |
| `:10` | `RELATED DOCS: … (sections 6.1 INV-16, 8.1 D-13, 9.2 row 7, …)` | `… 8.1 D-15, …` (outside the grant's line list; see above) |
| `:34` | `# EC-29, D-13: 0.3.1 is the first release that carries the public` | `# EC-29, D-15: 0.4.0 is the first release that carries the public` |
| `:36` | `FIRST_LOADER_RELEASE = (0, 3, 1)` | `FIRST_LOADER_RELEASE = (0, 4, 0)` |

**Gate matrix out** (code head `93a2b1a8`, pushed; the docs-only head of this commit is dispatched again, and its runs are in the S5-repair-2 STATUS):

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (the pack) | `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/public_skill_loader` | PASS | `67 passed in 0.46s` |
| pack + Jev area | (1) | PASS | `493 passed, 1 skipped in 11.01s` |
| lint | (2) | PASS | `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` / `SDK-LINT: PASS`. 0 REGRESSED or ERRORED. IMPROVED: A001, A002, C011, C012, S001, S010, S025, S061, S063. `git diff origin/main -- lint/` is empty |
| contract | (3) | PASS | `contracts/sdk-public-api.json is current at 013cf884fb9a532101bbbe128d9fde908b2fd131 (vidbyte-sdk 0.4.0, 643 exports).` / `C016 public-api-contract-current 0 0 CLEAN` / `SDK-LINT: PASS` |
| source stage | (4) | **FAIL (3, all inherited)** | Re-run: `====== 3 failed, 5888 passed, 16 skipped, 1 warning in 136.28s (0:02:16) ======` / `CI failed: …-m pytest…`. The 3 are (a), (c), and (d) from Iteration 1; (b) passed. First run: `4 failed, 5887 passed, 16 skipped in 260.74s`, which is (a), (c), (d), and the host-load bash-probe timeout above |
| package stage | (5), `env -u PYTHONPATH` | PASS | `Installed vidbyte-sdk 0.4.0 passed smoke checks.` / `CI passed.` (`vidbyte_sdk.egg-info` removed afterwards) |
| semgrep scan | (6), `scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS | `Ran 1 rule on 962 files: 0 findings.` |
| semgrep fixtures | `--test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` (guarded wrapper) | PASS | `1/1: ✓ All tests passed` |
| remote CI | (7), run 38839158032 on `93a2b1a8` | PASS | Source / Python 3.11, Source / Python 3.12, and Package all success. `5851 passed, 56 skipped` / `Installed vidbyte-sdk 0.4.0 passed smoke checks.` / `CI passed.` |
| remote Static policy | (7), run 38839160549 on `93a2b1a8` | PASS | Static policy = success |
| version places | `git grep -n -e "0\.3\.1" -e "0, 3, 1" -- ':!docs'` | PASS | empty. All nine INV-16 places read 0.4.0, the contract by `--check` |

**Still open:**
- No confirmed finding is open. R-6 and R-7 remain follow-ups, and R-C10 stays refuted.
- Local source-stage failures (a), (c), and (d) are inherited, per the orchestrator decision of 2026-10-16 00:40 in pipeline.md.
- For the orchestrator: the `:4` and `:10` reading of the test grant (2 tokens, `D-13` → `D-15`). Revert them if the grant's line list was exhaustive.
- For S6 and the release:
  - The doc's "#1103 to #1107 at the time of writing" reflects the local `origin/main` ref `aac190e9`, which was not fetched.
  - Refresh that line if `main` moves before the merge (row 16).
  - If `main` releases 0.4.0 first, D-15 flips.
