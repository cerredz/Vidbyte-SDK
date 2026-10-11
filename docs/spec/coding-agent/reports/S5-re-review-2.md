LENS: conformance (sole reviewer for re-review round 2: conformance plus any regression caused by the merges)
VERDICT: SOUND — All four merges of `origin/main` (`563f1db8`, `6d2191f7`, `38dca66d`, `d104bd78`) kept the feature and its R-1 to R-7 fixes byte for byte. Main's changes around `CodingAgent` and `BashTool` break no spec ID that I could drive, on Windows 3.11 or on WSL 3.12.

Scope:
- I reviewed `git diff origin/main...38572357` file by file and opened both new source files in full.
- I checked each merge for content that was not a clean merge, and the full PR change before and after the merges.
- I re-walked the spec IDs against main's changes to the feature's neighbors: #698, #700, #701, #703 and #705. The two commits that landed after the last merge, #704 (`ef527277`) and #706 (`1faf233a`), were checked too.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **No merge brought in any extra change.**
  - For each merge M, `git diff M^2 M` (main's parent against the merge result) lists exactly the feature files: the contract, three `__init__.py` files, two READMEs, `coding.py` and `bash.py`.
  - The PR's net change is the same, line for line, before and after the merges. I extracted the `+`/`-` lines of `git diff 8f23fd67...581fc272` and of `git diff origin/main...HEAD` over `contracts vidbyte tests/features/coding_agent` (contract `commit` line excluded). Both lists are 1,868 lines and `diff` shows no difference.
  - Do not "re-resolve" any merge.
- **The contract resolution follows main's own practice.**
  - It keeps main's `source.commit` `787afabf` and adds one line, `"CodingAgent"`.
  - Main's #698 did the same (`git diff bfe395fe^1 bfe395fe -- contracts/sdk-public-api.json`: 5 exports added, source line unchanged).
  - `--check` passes with 599 exports, and `git merge-tree --write-tree HEAD origin/main` is still clean at `1faf233a`.
  - Do not regenerate the contract to stamp a branch commit: a squash merge would drop that commit.
- **`_FetchedPagesView` still sits on contracts that main left intact.**
  - `PricedOperationTool._PAYLOAD_KEY` is still `"operation_payload"` (`operations/base.py:40`).
  - The runtime still unwraps before pricing (`runtime.py:1208` `ActivityToolFormatter.unwrap` → `_unwrap_tool`, `tools/base.py:166-171`). It reads `isinstance(tool, PricedOperationTool)` only after that (`runtime.py:1209`), and no other code in `vidbyte/` does an `isinstance` check on a priced tool.
  - `_ToolWrapper` gained no abstract member.
  - Main's new JevAgent fresh-continuation clone (`AgentForker._clone_tool(tool, None, None)`) returns the view itself, because fetch tools have no clone hook.
- **Main's #700 and #701 change only how the wired tools read their arguments; `CodingAgent` still wires them and the policy unchanged.**
  - Through a real `CodingAgent` loop, with explicit JSON nulls for every optional argument of `write_text`, `read_lines`, `glob` and `grep`, all four calls returned `succeeded`. `grep` with `regex: "true"` returned `failed`, with `'regex' must be a boolean (true/false).`. That is #700's intended rule for every agent, not a feature regression.
  - `BashTool` reads only the required string `command`, so neither change reaches it.

FINDINGS (ranked, most severe first, max 15)
None.
- I found no new Blocker, Major or Minor.
- R-C1 from re-review round 1 (`bash.py:68`, sentence 5 of the description says "the process is killed", which is not true on Windows) is still in the code unchanged. It stays a follow-up by the orchestrator's decision, so I have not raised it again.

VERIFIED CLAIMS: <each claim checked and whether it held>
- **HELD (briefing): the R-1 to R-7 fix lines are byte-identical after the merges.** `git diff 581fc272..HEAD -- vidbyte/tools/builtins/bash.py vidbyte/agents/coding.py | wc -l` → `0`. The test pack also has no change since `581fc272` (empty `--stat`).
- **HELD, with one stale detail (S5-repair-2 §1): "only `contracts/sdk-public-api.json` conflicted; merges 2 to 4 changed no feature file".** The per-merge `git diff M^2 M` check above confirms it.
  - Stale detail: the report gives the inherited `vidbyte/__init__.py` findings as S001 at `:396,398,543,550` and S015 at `:679`. At HEAD they are at `:401,403,548,555` and `:684`.
  - Each HEAD line is byte-identical to `origin/main` one line higher (`:400,402,547,554,683`). So the findings are main's, and the only shift is the branch's one `CodingAgent,` import line. The report's line numbers are from an earlier merge. This affects the report only, not the PR.
- **HELD (S5-repair-2 §3): the feature files have zero lint findings.**
  - I filtered `python lint/run.py --all --format json` to `vidbyte/agents/coding.py`, `vidbyte/tools/builtins/bash.py`, `tests/features/coding_agent/`, both READMEs and `contracts/`. Result: 0 findings. (10 raw path matches were `vidbyte/agents/contracts/*`, a substring false positive.)
  - All 90 rules ran: 45 CLEAN, 37 RATCHETED, 8 IMPROVED, and none REGRESSED or ERRORED.
  - Touched-rule counts are all at or below their baselines: A001 643/643, A002 661/703, A006 34/34, A007 254/255, A009 0/0, C016 0/0, S001 57/59, S008 19/19, S009 349/350, S015 13/13, S016 50/50, S017 79/79, S019 5/5, S024 23/25, S025 261/263, S039 5/5, S045 2/2, S051 257/259, S052 0, S055 0, S062 889/889, S063 4/4, S064 4/4.
  - The IMPROVED headroom is main's, since the feature files add nothing.
- **HELD (INV-2, briefing): main added no `BaseAgent.__init__` keyword.**
  - There are 31 keyword-only parameters at `8f23fd67` (counted with `ast`) and 31 at HEAD (`inspect.signature`).
  - The only names shared with `CodingAgent`'s explicit parameters are `tools` and `permission_policy`, as INV-2 intends.
  - Main's `export_state` now adds `fallback_models`, and `restore` passes `fallback=`. Both are pass-through, so the INV-2 parity test still compares like with like.
- **HELD (INV-20, §12.4): this PR edits none of the files it must leave alone.** `git diff --stat origin/main HEAD` over `fetch.py`, `tools/filesystem`, `code_search`, `agents/base.py`, `dataclasses/security.py`, `dataclasses/filesystem.py`, `runtime.py`, `fork.py` and `tools/base.py` is empty against current `main` `1faf233a`.
- **HELD (AC-1): spec §4, run exactly as written** in a temporary folder that holds `my-project`, with the pack's `ScriptedToolRunner` bound for `run`.
  - It printed the absolute `...\my-project` path and `('bash', 'read_lines', 'write_text', 'replace_text', 'glob', 'grep', 'firecrawl_fetch')`.
  - `run` returned `Fixed. ('succeeded', 'succeeded')`.
- **HELD (INV-22, INV-23, AC-21, INV-24, INV-17) on the merged tree.**
  - INV-22: `JevAgent(settings=JevAgentSettings(..., agents=(JevSpecialist(title="coder", ..., agent=<CodingAgent>),)))` constructs. `_require_metered_specialists` (`jev/agent.py:107-118`) still checks only that `generate_reply` is `BaseAgent`'s.
  - INV-23: `fork()` returns a `BaseAgent` with the same tool names, the same view object at index 6, and the same policy.
  - AC-21: `BaseAgent.restore(state, tools=...)` gives the same names, `['execute', 'read', 'safe', 'write']`, and no `__resume_tool_mismatch__`.
  - INV-17: the key is in neither `repr(export_state())` nor `card()`.
  - INV-24: `MctsSearchRuntime()`, `ActorRuntime()` and `LinearRuntime()` are accepted by both `CodingAgent` and the equivalent `BaseAgent`.
- **HELD (INV-14): the retry gate is unchanged.** `_IDEMPOTENT_PERMISSIONS = frozenset(("safe", "read"))` is still at `tool_error_policy.py:28`, and the gate is still at `:142-147`.
- **HELD (INV-19, INV-21): the defaults are unchanged.**
  - `base.py:186` still has `permission_policy or PermissionPolicy()`. The spec cites `:185` against `base_commit` `8f23fd67`.
  - `filesystem.py:31` still has `allow_write: bool = False`.
  - `test_agent_denies_write_tool_by_default` still exists (`tests/test_agent_tool_loop.py:118`).
- **HELD (INV-26 and AC-28 through the production path, which main changed).** `BaseAgent.run` now runs `asyncio.run(self._run_releasing_mcp(...))` (`mixins.py:207-221`).
  - Probe on WSL 3.12.3: `CodingAgent.run` with `BASH_TIMEOUT_SECONDS=1.0` and `BASH_KILL_GRACE_SECONDS=0.5`, on a `setsid sleep` descendant that holds the pipe.
  - Result: states `('failed', 'succeeded')`, elapsed `1.53s` (within limit + grace), `unraisable: []`, no transport warnings.
  - The AC-28 pack test drives `BashTool` under a bare `asyncio.run`, so this probe covers the agent path the test does not.
- **HELD (R-1 probes): every `[CODE]` row ends with `transport is_closing=True`.** Ran on WSL with `probe_stop.py` and `probe_eperm_alive.py`; leftover processes: none.
- **HELD (briefing gates).**
  - Full suite: `2865 passed, 12 skipped`.
  - Pack: Windows `86 passed, 11 skipped` (the 11 are the POSIX-only and stand-in-Git cases) and WSL `97 passed`.
  - `SDK-LINT: PASS`.
  - Remote check-runs on `8ff4f472`: Package, Static policy, Source 3.11 and Source 3.12 all `success`.
- **HELD (§14 Never): no baseline, rule or test was weakened.**
  - `git diff origin/main...HEAD -- lint/baseline.json` is 0 lines.
  - Every test-tree change against main is under `tests/features/coding_agent/`, and those are additions only.
  - No file under `tests/` outside the pack differs.
- **HELD (§12.3 rows 2, 4, 5, 7, 8, after the #698 auto-merge).**
  - The import positions, the `__all__` positions (`"CodingAgent"` before `"JevAgent"` in the root and between `"CodexUsageResponse"` and `"ContinualTraceAgent"` in `vidbyte.agents`) and the header bullets are as specified.
  - `## Coding Agent` still follows `## Usage` and comes before main's `## Model Fallback`.
  - Neither touched folder README has a `## Notes for agents` section, which main's new AGENTS.md paragraph would make binding. A009 is CLEAN (agents README: 10,723 chars).
- **DID NOT HOLD (briefing §2): "`origin/main` is `ef527277`".**
  - It is now `1faf233a`: #706, "stop null optional arguments rendering as 'None' text", landed after #704.
  - #704 and #706 touch only `tools/builtins/sessions/*`, `context_primitives/upsert.py`, `cot_events.py`, `handoff/create.py`, `reflexion.py`, their tests, and `docs/design`. None of these files is wired or depended on by the feature.
  - `git merge-tree --write-tree HEAD origin/main` is clean, and `gh pr view 690` gives `MERGEABLE` / `BEHIND` / draft.
- **NOTED (not a finding): HEAD `38572357` has no check-runs.** It is a docs-only commit after `8ff4f472`. With main's `strict: true` protection, the PR head needs `ci.yml` dispatched again before it can merge.

COMMANDS RUN: <each with its final lines>
- `git rev-parse origin/main; git merge-base origin/main 38572357` → `1faf233a…` / `84f7aee3…`
- `git diff --stat origin/main...38572357` → `38 files changed, 5875 insertions(+), 3 deletions(-)` (8 §12.3 files, 8 pack files, the rest under `docs/spec/coding-agent/`)
- `git diff 581fc272..HEAD -- vidbyte/tools/builtins/bash.py vidbyte/agents/coding.py | wc -l` → `0`; `git diff 581fc272..HEAD --stat -- tests/features/coding_agent/` → (empty)
- `for m in 563f1db8 6d2191f7 38dca66d d104bd78: git diff --stat $m^2 $m -- . ':!docs/spec/coding-agent' ':!tests/features/coding_agent'` → `8 files changed, 418 insertions(+), 3 deletions(-)` each (`563f1db8`: 7 files, with no contract line before `72ef4638`)
- net `+`/`-` line comparison, `8f23fd67...581fc272` against `origin/main...HEAD` → `1868` / `1868` / `IDENTICAL net +/- lines`
- `git diff origin/main...HEAD -- lint/baseline.json | wc -l` → `0`
- `git diff --stat 84f7aee3 origin/main` → `17 files changed, 324 insertions(+), 23 deletions(-)` (sessions and other builtins only); `git merge-tree --write-tree HEAD origin/main` → `0677259a…` (no conflicts)
- `git diff 8f23fd67 84f7aee3 -- vidbyte/agents/{base,fork,runtime}.py vidbyte/tools/base.py vidbyte/lib/tools/formatter.py vidbyte/agents/jev/agent.py vidbyte/tools/builtins/operations/fetch.py …` → read hunk by hunk (summary above)
- `git diff bfe395fe^1 bfe395fe -- contracts/sdk-public-api.json` → 5 `+` export lines and no `source` change
- `python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 787afabf… (vidbyte-sdk 0.2.1, 599 exports).`
- `python lint/run.py` → `S063 RATCHETED: 4 known finding(s).` / `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS`
- `python lint/run.py --all --format json`, filtered by path → `exit: 0 rules: 90 verdicts: {'RATCHETED': 37, 'IMPROVED': 8, 'CLEAN': 45}`, 0 findings in feature files
- `sed -n <n>p vidbyte/__init__.py` against `git show origin/main:vidbyte/__init__.py | sed -n <n-1>p` for 401, 403, 548, 555, 684 → all five equal
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider -rs tests/features/coding_agent/` (Windows 3.11) → `86 passed, 11 skipped in 5.05s`
- `wsl.exe -d MuseUbuntu1 … /tmp/s2-coding-agent-venv/bin/python -m pytest -q -p no:cacheprovider tests/features/coding_agent/` → `97 passed in 17.47s`
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider -x` (full, Windows 3.11) → `2865 passed, 12 skipped in 20.77s`
- `wsl.exe … probe_stop.py`, then `probe_eperm_alive.py` → 7 `[CODE]` rows, all `transport is_closing=True`; `leftover processes: none` (twice)
- §4 snippet, null-argument, fork, restore, key and Jev probe (heredoc, temp folder) → the rows quoted under VERIFIED CLAIMS; `jev specialist accepted: JevAgent`
- INV-24 runtime probe (heredoc) → `MctsSearchRuntime [('coding','ok',…),('base','ok',…)]`, and the same for `ActorRuntime` and `LinearRuntime`
- AC-28 probe through `CodingAgent.run` on WSL 3.12.3 (heredoc) → `states ('failed', 'succeeded') elapsed 1.53s` / `unraisable: [] transport warnings: []`; afterwards `ps … | grep "sleep 8$"` → `no leftover sleep 8`
- `gh api repos/cerredz/Vidbyte-SDK/commits/<sha>/check-runs` → `38572357`: none; `8ff4f472`: `Package: success` / `Static policy: success` / `Source / Python 3.11: success` / `Source / Python 3.12: success`
- `gh pr view 690 --json mergeable,mergeStateStatus,isDraft,headRefOid` → `{"headRefOid":"38572357…","isDraft":true,"mergeStateStatus":"BEHIND","mergeable":"MERGEABLE"}`
- `git status --short | wc -l` after every run → `0`
