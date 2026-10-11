# S5 repair, iteration 2 of 8: bring `main` into `feat/coding-agent`

**Scope.** This iteration had one defect: gate `merge-main`. PR #690 reported `mergeable=CONFLICTING DIRTY`. No review finding was open: R-1 to R-7 are `fixed`, and R-8 and R-9 are `follow-up` by the orchestrator's decision. The job was to merge `origin/main` into the branch and make every gate green on the merged tree, including main's new lint rules. No feature source, test, lint baseline, rule or config changed.

## Gate matrix (code HEAD `d104bd78`, `origin/main` `84f7aee3` merged)

| Gate | Command | Result | Final lines |
|---|---|---|---|
| merge-main | `gh pr view 690 --json mergeable,mergeStateStatus,isDraft` | PASS | `{"headRefOid":"d104bd78…","mergeStateStatus":"BLOCKED","mergeable":"MERGEABLE"}`, main `84f7aee3` is an ancestor of HEAD. BLOCKED = the PR is a draft (`isDraft: true`); main's protection requires Source 3.11, Source 3.12 and Package on the head SHA, `strict: true`. |
| contract (C016's check) | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 787afabf4c733f6489eed1cfc729d75f1fb0751a (vidbyte-sdk 0.2.1, 599 exports).` |
| new tests, Windows 3.11 | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/` | PASS | `86 passed, 11 skipped in 5.06s` |
| new tests, WSL 3.12 | `MSYS_NO_PATHCONV=1 wsl.exe -d MuseUbuntu1 -- bash -lc '… /tmp/s2-coding-agent-venv/bin/python -m pytest -q tests/features/coding_agent/'` | PASS | `97 passed in 17.27s` |
| lint | `python lint/run.py` (step 2 of the source stage) | PASS | `S063 RATCHETED: 4 known finding(s).` / `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` |
| full local gate, source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `reasoning trace contracts: ok (182 tools, 55 shapes)` / `====== 2865 passed, 12 skipped in 20.65s ======` / `CI passed.` (#703 deleted `tests/test_review_agents.py`, so the count dropped) |
| full local gate, package | `python scripts/run_ci.py --stage package` (PYTHONPATH unset) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| remote CI | `gh workflow run ci.yml --ref feat/coding-agent` → `38081495740` on `d104bd78` | PASS | Source 3.11 `2865 passed, 12 skipped in 28.60s` / `CI passed.`; Source 3.12 `2865 passed, 12 skipped, 12 warnings in 23.99s` / `CI passed.`; Package `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| remote Semgrep | `gh workflow run static-policy.yml --ref feat/coding-agent` → `38081497380` on `d104bd78` | PASS | `Ran 1 rule on 869 files: 0 findings.` |
| remote check-runs | `gh api repos/cerredz/Vidbyte-SDK/commits/d104bd78…/check-runs` | PASS (4/4) | `Package: success` / `Static policy: success` / `Source / Python 3.12: success` / `Source / Python 3.11: success` |

Each earlier merge passed the same gates locally before main moved again.
- **Merge 1** (`563f1db8` + `72ef4638`, main at `6b7ba7c3`):
  - lint: `SDK-LINT: PASS`;
  - source: `2869 passed, 12 skipped in 32.36s` / `CI passed.`;
  - package: `CI passed.`;
  - pack: 86 passed / 11 skipped on Windows, and 97 passed on WSL.
- **Merge 2** (`6d2191f7`, main at `bfe395fe`):
  - source: `2889 passed, 12 skipped in 30.15s` / `CI passed.`;
  - package: `CI passed.`;
  - pack: 86 passed / 11 skipped on Windows, and 97 passed on WSL;
  - remote: CI `38080381482` (Source 3.11 `2889 passed, 12 skipped in 26.57s` / `CI passed.`; Source 3.12 `2889 passed, 12 skipped, 12 warnings in 30.12s` / `CI passed.`; Package `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.`) and Static policy `38080383145` (`Ran 1 rule on 869 files: 0 findings.`), with all 4 check-runs `success` on `6d2191f7`.
- **Merge 3** (`38dca66d`, main at `c6e758fe`):
  - source: `2894 passed, 12 skipped in 34.39s` / `CI passed.`;
  - package: `CI passed.`;
  - pack: 86 passed / 11 skipped on Windows, and 97 passed on WSL;
  - remote: CI `38080888378` (Source 3.11 `2894 passed, 12 skipped in 25.66s`; Source 3.12 `2894 passed, 12 skipped, 12 warnings in 30.29s`; Package `CI passed.`) and Static policy `38080889677`, 4/4 `success`.

## What I did, in order

### 1. The merge: done four times, because `main` moved four times during the iteration
- **Fetch.** `git fetch origin` gave `origin/main = d7b25110`, as the briefing said.
- **The first attempt was stale.** `git merge --no-ff --no-commit origin/main` conflicted only in `contracts/sdk-public-api.json`. Before committing, `git diff --cached --stat origin/main` showed files the branch never touched as differences: `vidbyte/tools/base.py -13`, the filesystem tools, `tests/test_mongodb_tools.py -81` and `docs/design/tool-args-strict-booleans.md -94`. `git rev-parse MERGE_HEAD` was `d7b25110`, but `origin/main` was now `6b7ba7c3`. #700 ("reject stringly booleans in model-facing tool arguments") had landed, and another session's fetch had updated the shared remote-tracking ref. I ran `git merge --abort` and merged `6b7ba7c3`.
- **Merge 1 (`563f1db8`, main at `6b7ba7c3`).** Same single conflict. After this merge, `git diff --cached --stat origin/main` showed only the feature files.
- **Main moved again.** After merge 1 was committed and gated, `git diff origin/main..HEAD` showed main-side Jev files as deletions, because `bfe395fe` (#698, Jev skills preload) had landed.
- **Merge 2 (`6d2191f7`, main at `bfe395fe`).** It auto-merged with no conflict; the contract decision is described below. All local gates passed, and all 4 remote check-runs were green on `6d2191f7`.
- **Main moved a third time.** The PR then showed `{"mergeStateStatus":"BEHIND","mergeable":"MERGEABLE"}`, because `c6e758fe` (#701, "treat null optional arguments as the documented default") had landed. It changes `glob.py`, `grep.py` and `read_lines.py`, three of the seven tools `CodingAgent` wires, and adds `BaseTool._optional_argument`.
- **Merge 3 (`38dca66d`, main at `c6e758fe`).** It auto-merged with no conflict. The contract is untouched (`--check`: current, 599 exports). I re-ran every gate on it, and remote CI `38080888378` and Static policy `38080889677` went 4/4 green on it.
- **Main moved a fourth time.** While I committed the docs (`8b50a6ee`), `ebeb56b5` (#703: it replaces the review-agents pipeline with `.github/workflows/claude.yml`, and its `lint/rules/a009_readme_size_limit.py` change is docstring and diagnostic text only) and `84f7aee3` (#705: null `limit` on provider read tools) landed. `git merge-tree --write-tree HEAD origin/main` was clean.
- **Merge 4 (`d104bd78`, main at `84f7aee3`).** It auto-merged with no conflict. I re-ran every gate on it. I stopped chasing here: any later main move is reported, not merged.
- **The final state.** `git ls-remote origin refs/heads/main` = `84f7aee3`, and `git merge-base --is-ancestor origin/main HEAD` holds. `git diff origin/main..HEAD --stat -- . ':!docs/spec/coding-agent' ':!tests/features/coding_agent'` shows exactly the 8 §12.3 files: the contract (+1 line), `vidbyte/__init__.py`, `vidbyte/agents/README.md`, `vidbyte/agents/__init__.py`, `vidbyte/agents/coding.py`, `vidbyte/tools/README.md`, `vidbyte/tools/builtins/__init__.py` and `vidbyte/tools/builtins/bash.py`.

**Conflicted files, across all four merges:** only `contracts/sdk-public-api.json`, line 3 (`source.commit`), in merge 1. Merge 2 auto-resolved every file, including the contract, `vidbyte/__init__.py` and `vidbyte/agents/__init__.py`. Merges 3 and 4 auto-resolved their 11 and 25 files, none of them a feature file.

### 2. The contract
The briefing names "this branch's two additions, `CodingAgent` and `BashTool`". The contract lists root `vidbyte.__all__` only. `BashTool` is exported from `vidbyte.tools.builtins` (`vidbyte/tools/builtins/__init__.py`), not from the root, so the branch's only contract line is `"CodingAgent"`. `git diff 8f23fd67 51c5745c -- contracts/sdk-public-api.json` shows exactly that, plus the `source` line.

The order the briefing gives cannot work as written. It says to take main's hunk, then regenerate, then commit. But the generator rewrites only when the derived data differs from the committed file, so if main's hunk is kept together with `"CodingAgent"`, the data already matches and it writes nothing. And while `vidbyte/__init__.py` is uncommitted, which it is mid-merge, the generator refuses to stamp.

- **Tried first, for provenance.** I resolved to main's whole generated file, committed merge 1, then ran the generator. It wrote `wrote contracts/sdk-public-api.json at 563f1db8… (vidbyte-sdk 0.2.1, 594 exports)`, committed as `72ef4638`. My reason was the generator header's WHAT NOT TO DO #2: "Do not record a commit whose inputs differ from what was read."
- **Settled on, in merge 2.** Main's `source` line (`787afabf`) plus `"CodingAgent"`, which is what the briefing asked for. The evidence that flipped the decision was main's own #698 (`git show bfe395fe -- contracts/sdk-public-api.json`): it added 5 exports and kept `787afabf`. So main's practice is "keep the source line; add exports", and C016 compares data only.
- **The practical gain.** The contract now differs from main by one line, `+ "CodingAgent"`. A future release bump that rewrites line 3 cannot conflict with this branch again; that line is exactly what caused this iteration's conflict.
- **Verified.** `--check` gave `current at 787afabf… (vidbyte-sdk 0.2.1, 599 exports)`, and write mode gave `already current at 787afabf…; nothing written.`
- **Interim history.** `72ef4638` stays in the history (no rewrite allowed). Its stamp is superseded by `6d2191f7`.

### 3. Main's new lint rules
- **Every rule ran.** `python lint/run.py --all --format json`: exit_code 0, 90 rules, no ERRORED or REGRESSED verdict. Main's new rules on the merged tree:
  - CLEAN: A009 0/0, C010 0/0, C014 0/0, C016 0/0;
  - RATCHETED: C006 104/104, C007 16/16, C008 45/45, C009 1/1, C011 2/2, C012 24/24, C013 9/9, C015 3/3, S063 4/4, S064 4/4.
- **Zero findings in the feature's files.** A per-path filter over the JSON found nothing, under any rule, in `vidbyte/agents/coding.py`, `vidbyte/tools/builtins/bash.py`, `vidbyte/agents/README.md`, `vidbyte/tools/README.md`, `contracts/` or `tests/features/coding_agent/`. A009 (README size limit) is 0/0, so the "## Coding Agent" README sections fit.
- **No source change was needed.** The briefing's likely spots (A009, C006/C007, C008, C011, S063) did not fire.
- **Inherited findings in feature-touched files.** Only the three `__init__.py` files have findings: A001 on each (main's "Context Protocol Header" form, no A001 header), plus S001 F401 at `vidbyte/__init__.py:396,398,543,550` and S015 at `:679`. Each of those lines is byte-identical to `git show origin/main:vidbyte/__init__.py` at the line one above (`:395,397,542,549,678`); the shift is the branch's one added `CodingAgent,` import line. They are main's findings, not this branch's.
- **IMPROVED verdicts are main's slack.** A002 661/703, S001 57/59, S009 347/350, S010 0/5, S024 23/25, S025 261/263 and S051 258/259 are all IMPROVED. Iteration 1 recorded the branch at main's counts, and the feature files add zero findings, so the slack is main's. I did not touch the baseline.

### 4. Interactions with what main changed under the feature
- **INV-2 (keyword pass-through).** `git diff 8f23fd67 origin/main -- vidbyte/agents/base.py` shows no change to `BaseAgent.__init__`. Main changed `restore` (it now passes `fallback=`), `export_state` (it adds `fallback_models`), `run` and `run_sequentially` (`_run_releasing_mcp`), and the trace scrub. The pack's signature and `**kwargs` tests pass.
- **`_FetchedPagesView`.**
  - `PricedOperationTool._PAYLOAD_KEY` is still `"operation_payload"` (`vidbyte/tools/builtins/operations/base.py:40`, written at `:74`).
  - Main's `fetch.py` change touches only `_url_list`: an empty `urls` list now falls back to `url`.
  - The `test_coding_agent_web_fetch.py` AC tests pass.
- **Pricing unwrap.** `runtime.py:1208` still does `ActivityToolFormatter.unwrap(tool)`, which goes through `_unwrap_tool` (`vidbyte/tools/base.py:158-163`, `while isinstance(unwrapped, _ToolWrapper)`). Main's `runtime.py` changes are a catalog re-resolve, the `allowed_tools` gate, truncation of middleware tails, compaction counting and the trace scrub. None of them touches pricing or the unwrap path.
- **#700 (strict booleans).** It added `BaseTool._resolve_bool_argument` and uses it in `write_text`, `grep` and others. `BashTool` reads only the string `command`. The pack's write and grep acceptance cases pass.
- **#701 (null optional arguments).** It added `BaseTool._optional_argument` and uses it in `glob`, `grep`, `read_lines` and others. This only widens what those wired tools accept: a null now means the default. The pack's acceptance cases pass on the merged tree on both platforms. Lint was re-filtered per path on `38dca66d` and again on `d104bd78`: zero findings in feature files, nothing regressed (90 rules).
- **#703 and #705.** Neither touches a file `CodingAgent` wires or depends on: #705 changes `providers/mongodb.py` and `providers/rows.py`, and #703 changes CI and review scripts. The A009 rule's logic is unchanged.

### 5. Scope checks
- `git diff d158d5f6..HEAD --stat -- tests/features/coding_agent/` lists `README.md` and `test_bash_tool_contract.py` only, the two files granted in iteration 1.
- `git diff origin/main...HEAD --name-only -- tests/` lists only `tests/features/coding_agent/`, 8 files.
- No suppression, skip, xfail, baseline, rule, CI or config change. The spec is unchanged: no lint rule forced a behavior change, so §17 needs no deviation line. `review.md` is unchanged, because no status changed.
- The worktree is clean after every commit.

## Findings
- **Fixed this iteration:** none were open.
- **Still open:** none. R-8 and R-9 stay `follow-up` by the orchestrator's decision.
- **Disputed:** none.
- **Test changes proposed:** none.

## Notes for the next stage
- **The re-review should look at merges 2 to 4, not only merge 1.**
  - `6d2191f7` brought #698, whose `vidbyte/agents/__init__.py` and `vidbyte/__init__.py` export blocks auto-merged next to `CodingAgent`.
  - `38dca66d` brought #701, which changes three of the seven wired tools.
  - `d104bd78` brought #703 and #705, which touch no feature-adjacent code.
- **Main is moving fast:** five commits landed during this iteration (#700, #698, #701, #703, #705), all after the `d7b25110` the briefing named. `BEHIND` is not `CONFLICTING`, but main's protection has `strict: true` and requires Source 3.11, Source 3.12 and Package on the head SHA. So every new head, including a docs-only one, needs `ci.yml` dispatched again, and every main move needs another merge before the PR can merge. If the PR turns `CONFLICTING` again, the most likely cause is a release bump or another root export landing next to `"CodingAgent"` in the contract. Resolve it the same way: keep main's `source` line and the `"CodingAgent"` line, then run `--check`.
- **The known flake** `tests/test_codex_tools.py::CodexSdkContractTests::test_cancelled_turn_releases_its_waiting_reader` did not occur in any of the four full runs (2869, 2889, 2894 and 2865 passed).
