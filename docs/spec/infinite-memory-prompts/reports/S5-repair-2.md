# S5 · Repair iteration 2 of 8 — infinite-memory-prompts

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-prompts` · branch `feat/infinite-memory-prompts` · entry HEAD `19397f5a` · code HEAD after repair `3825237d` (pushed) · PR https://github.com/cerredz/Vidbyte-SDK/pull/1176 (draft, base `feat/infinite-memory-agent`).

## 1. Outcome

Both packet items are fixed, one commit each. R-27 (Major) uses the scoped verifier's recommended text word for word (`fe04ab8c`). R-28 (Minor, added by the orchestrator) adds one clause to resume step 1 (`3825237d`). Every measured result for R-27 matches the verifier's what-if numbers to the token. Every gate is green except the 3 inherited `harness_threads` surface failures in the source stage, which the orchestrator reproduced at base 7efceb55. No test, Python file, lint baseline, config, or file outside the `infinite_memory` family changed. `vidbyte/agents/infinite/README.md` did not change, because all three `:68` figures stay true (§3).

## 2. Gate matrix (run in this worktree, this iteration, at `3825237d`, tree clean)

| # | Gate | Command | Result | Final lines |
|---|---|---|---|---|
| 1 | new module | `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_prompts.py -q -p no:cacheprovider` | PASS | `........................................................................ [ 54%]` / `...........................................................              [100%]` / `131 passed in 0.90s` |
| 2 | feature pack | `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` | PASS | `........................................................................ [ 88%]` / `............................                                             [100%]` / `244 passed in 4.55s` |
| 3 | custom lint | `python lint/run.py` | PASS | `S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline` / `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` / `SDK-LINT: PASS` |
| 4 | semgrep | `<scratchpad>/semgrep-venv/Scripts/python.exe <scratchpad>/run_semgrep.py` (tree clean, nothing to `git add`) | PASS | `Ran 1 rule on 980 files: 0 findings.` / `A new version of Semgrep is available. …` / `If Semgrep missed a finding, please send us feedback to let us know!` |
| 5 | public API | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 9eca4a33ddb5ea1a21c07f840e556487a8770e19 (vidbyte-sdk 0.3.0, 644 exports).` |
| 6 | full gate, source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS except the 3 inherited failures | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` / `FAILED …::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` / `FAILED …::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` / `============ 3 failed, 6174 passed, 16 skipped in 96.04s (0:01:36) ============` / `CI failed: Command failed with exit code 1: …python.exe -m pytest (cwd=…)` |
| 7 | full gate, package | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| 8 | measure | `python <scratchpad>/measure_seven.py <worktree>` | PASS | table in §3 |
| — | remote | `gh pr checks 1176` | none | `no checks reported on the 'feat/infinite-memory-prompts' branch`. GitHub Actions are disabled repo-wide, so the local gates are the gates of record. |

**The source stage.** The log is `<scratchpad>/s5-2/source.log`. `SDK-LINT: PASS` is at log line 182, and pytest is the only step that failed. The three failures are exactly the inherited set the briefing names. This repair changed only three Markdown leaves, so they cannot come from it. The known Windows stdio flake did not fire. `S063 IMPROVED` comes from an AST rule over Python and is inherited; I left the baseline alone.

`<scratchpad>` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7d03425b-8396-4738-89eb-c11a8a3fac1a/scratchpad`.

## 3. Measurements (tiktoken cl100k_base and TokenEstimate, through `Prompts().get`)

`measure_seven.py` output at `3825237d`:

| Asset | chars | est | tik | entry tik (19397f5a) | baseline tik | floor (≥ 1,000 est, ≥ 1,100 tik) |
|---|---|---|---|---|---|---|
| root_system_prompt | 11,431 | 2,858 | 2,470 | 2,465 | 1,829 | ok (ceiling 2,600) |
| generator_system_prompt | 6,988 | 1,747 | 1,490 | 1,490 | 1,277 | ok |
| verifier_system_prompt | 5,733 | 1,434 | 1,216 | 1,216 | 1,059 | ok |
| task_prompt | 5,393 | 1,349 | 1,142 | 1,142 | 241 | ok |
| verifier_task_prompt | 5,489 | 1,373 | 1,160 | 1,160 | 251 | ok |
| resume_prompt | 5,354 | 1,339 | 1,151 | 1,137 | 232 | ok |
| launch_tool_description | 5,352 | 1,338 | 1,123 | 1,123 | 416 | ok |

The 23-description per-leaf sums are est 4,577 (bound 4,900) and tik 3,905 (bound 4,183). note_path_description measures 181 tik and 204 est, with 7 S025 sentences (at least 4 required).

**README `:68`.** The root is 2,858 est, which rounds to 2,900, so "about 2,900" holds. The 24 descriptions sum to 5,915 est, which rounds to 5,900, so "about 5,900" holds. The total is 90,000 + 2,858 + 5,915 + 8,000 = 106,773, which rounds to 107,000, so "near 107,000" holds. No figure became false, so the README is unchanged.

**Further checks.** `<scratchpad>/s5-2/measure_repair2.py` runs the following checks on root, resume, and note_path through `Prompts().family`, cross-checked against `Prompts().get`:
- no digit and no stray brace;
- placeholders: resume has `{task}`, `{finished}` and `{interrupted}`, each once;
- no pin missing;
- no repeated sentence of five or more words;
- headings present and in order;
- trailing newline: resume, a fragment, ends with none (`od -c` ends in `m i s s i n g .`); root and note_path end with one.

## 4. Per finding: reproduction, change, evidence

### R-27 (Major) — `fe04ab8c`

- **Reproduction (before).** The scoped verifier ran the real `InfiniteWorkspace` (reports/S5-verifier-r27.md §3). At 305 files with 120-character descriptions, the map shows 208 lines and then "… and 97 more files". At 244 files, the root's `plan.md` is missing from the map. I reproduced the second case (§4, R-28). The code: `workspace.py:219-230` cuts at `INFINITE_MAP_MAX_TOKENS`, in sorted path order (`usage.py:33`).
- **Change (the verifier's recommended text, word for word).**
  - `root_system_prompt.md:58`: "and one line per file with its size and description." → "and one line per file with its size and description, as many as fit."
  - `note_path_description.md:7`: "lists every file by its path" → "lists files by their paths".
- **Evidence after.**
  - `grep -c "lists every file\|one line per file with its size and description\.$"` → 0 in both files.
  - In the family, "every file" now appears only in sentences that do not describe the map: launch_verifier_prompt `:7` and root `:32` ("name every file … it needs"), task `:41` ("every file you read fills your context"), and vtask `:51` (see §6).
  - root 2,465 → 2,470 tik (2,854 → 2,858 est). note_path 182 → 181 tik. The sum went 3,906 → 3,905. These match the verifier's figures exactly.
  - Gates: module 131, pack 244.

### R-28 (Minor, orchestrator-added) — `3825237d`

- **Reproduction (before).** Resume step 1 said "Read the workspace map and your plan note …" and then "If you kept no plan note, write one now from the task and the finished cards." `plan_note_found_by_grep.py` extends the verifier's `plan_note_cut.py`. It builds `plan.md` and then 240 generator notes:
  - `files on disk 244; map lines shown 230; last line: … and 14 more files`
  - `plan.md on the map: False`
- **Which tool the root holds.** `vidbyte/lib/registries/infinite.py:36-37` lists only memory tools (remember and write_note, plus edit_file under FULL). Search comes from `InfiniteMemoryAgentTools` (`vidbyte/tools/toolsets/infinite.py:41-50`: bash, grep and read_lines, with grep and read_lines rooted at the workspace). `agent.py:77` gives these to the root under both presets. So the clause says "search the workspace for it", as the briefing asked.
- **Change.** "If you kept no plan note, write one now from the task and the finished cards." → "If the map does not show your plan note, search the workspace for it; if you kept none, write one now from the task and the finished cards." This is one added clause, with no number. The step still ends in the original instruction, and the decision to write a new note now comes after the search.
- **Check that the new instruction works.** On the same cut workspace, I ran the root's own grep tool (built by `InfiniteMemoryAgentTools.get_tools`, called as `ToolCall(tool_name="grep", arguments={"pattern": "deliverable"})`). The search used a word that root step 2 puts in every plan note ("write every deliverable … into a plan note"). It found `plan.md` twice: by its description in `files.jsonl:1` and by its own text at `plan.md:1`. Output: `plan.md found by the root's grep: True`.
- **Evidence after.** resume 1,137 → 1,151 tik (1,323 → 1,339 est), above the 1,100 floor. Every check in §3 holds. Module 131, pack 244.
- **Origin.** The old sentence is new text from this PR (`git log -S"If you kept no plan note"` → `e5487315`). The base resume prompt contains no "plan note" at all (`git show origin/feat/infinite-memory-agent:…/resume_prompt.md | grep -c "plan note"` → 0). So INV-19 needs no PR-body note for R-28.

In review.md, R-27 reads `fixed @fe04ab8c`, and R-28 was added to the Minor table as `fixed @3825237d`, in the briefing's wording. The Minor heading count went from 20 to 21. The Verdict's last sentence ("it is open and is a two-phrase text edit") now records both fixes.

## 5. #1113 sentences reworded (for INV-19 and the PR body)

Both R-27 edits reword #1113 sentences and keep their rules. List them in the PR body next to R-1 and R-5 b from iteration 1.

1. **`root_system_prompt.md`, Memory (R-27).** The sentence is at base `:51` (`7efceb55`).
   - Before: "The workspace map in your context, redrawn after each of your tool calls, shows the totals against their caps, the count of live memory entries, and one line per file with its size and description."
   - After: "The workspace map in your context, redrawn after each of your tool calls, shows the totals against their caps, the count of live memory entries, and one line per file with its size and description, as many as fit."
   - Why: past `INFINITE_MAP_MAX_TOKENS` the map keeps only the first lines that fit, in path order (`workspace.py:219-230`, `usage.py:33`). The kept rule is that the map shows totals, the entry count, and per-file lines with size and description. "As many as fit" is the phrase R-2 put in task `:41`, so the family states this fact in one way.
2. **`note_path_description.md`, How to write it (R-27).** The sentence came from #1084 (`2c84049c`), and #1113 (`7efceb55`) moved it into this leaf.
   - Before: "Choose a folder and file name that say what the file holds, because the workspace map lists every file by its path and other agents decide from it what to read."
   - After: "Choose a folder and file name that say what the file holds, because the workspace map lists files by their paths and other agents decide from it what to read."
   - Why: the same code truth. This leaf is the `path` description of write_note for every role, and of edit_file under FULL (`memory.py:182`, `:215`). Before the fix, a generator read "every file" in its schema and "as many as fit" in its briefing in the same call. The kept rule is to choose a descriptive name, because agents decide from the map.

## 6. Hypotheses tried and decisions

- **R-27 variant.** I used the verifier's recommended text, not the re-reviewer's (", for as many files as fit"). It reuses task `:41`'s exact phrase, as the briefing asks, and it is 2 tik smaller.
- **R-28 wording.** I weighed three options:
  - Option (a), the shipped text: prepend "If the map does not show your plan note, search the workspace for it;" and shorten the old condition to "if you kept none". This is the smallest diff that puts the search before the decision.
  - Option (b): add an explicit reason ("since the map may leave files out"). Rejected: that is a second clause, and root `:58` now states the fact ("as many as fit") in the same context. The resumed root gets the same system prompt (`agent.py:72`).
  - Option (c): name grep in the text. Rejected: the briefing prescribes "search the workspace for it" when the root holds grep, and step 1 already says "search memory" without naming the tool.
- **README `:68`.** I recomputed all three figures after both commits. None crossed a rounding boundary.
- **The Edit tool's LF writes into the CRLF tree.** They are harmless, as in iteration 1: git's "LF will be replaced by CRLF" warning, an LF index, and every count goes through `Prompts().get`.

## 7. Observations (not fixed; outside the packet)

- **vtask `:51`, "the card lists every file you write".** This is new in this PR (`de8012e6`). The rendered card cuts its joined files list at `INFINITE_CARD_TEXT_MAX_TOKENS` (800 est, `launch.py:364-371`). So the sentence is false only when one pair writes roughly 80 or more distinct paths, which is out of reach under the per-agent new-file allowance unless a pair appends to many existing files. I judge this not a defect worth a change. It is recorded in case a later review raises it.
- **README `:58`.** It still makes the "one line per file" claim. That claim was already false at base, so it stays the recorded follow-up (Q-2/INV-20). I did not edit it, as the briefing directs.
- **`map_header`.** As the verifier noted, "Each line below is one workspace file…" does not cover the closing "… and N more files" line. It is a shape leaf that cannot grow (INV-15 d), so I made no change.

## 8. Still open

No packet item is open. The follow-ups keep the status review.md gives them: R-13 (vtask `:25` and resume `:1` parts), R-14 to R-18, and R-20 to R-25.

## Commands run (besides the gate set)

- `git status --short`, `git log --oneline -5` → clean at `19397f5a` at entry.
- I read: `verify-log.md`; `review.md`; `reports/S5-verifier-r27.md`; spec FR-10, INV-19, EC-9, AC-11 and §12.3.1 outlines 1, 6 and 22–25; `AGENTS.md`; field guide `prompt-families.md`; `registries/infinite.py`; `infinite/runtime.py:60-125`; `agent.py:5`, `:77`; `toolsets/infinite.py:40-50`; `grep.py:27-96`; `launch.py:286`, `:308-371`.
- `python <scratchpad>/s5-2/measure_repair2.py <worktree>`, after each fix.
- `python <scratchpad>/s5-2/plan_note_found_by_grep.py <worktree>` (R-28 reproduction and the grep check).
- `git log --oneline -S"If you kept no plan note"` and `-S"the card lists every file you write"`; `git show origin/feat/infinite-memory-agent:<leaf>`.
- `git push origin feat/infinite-memory-prompts` → `19397f5a..3825237d`; `git rev-parse --short HEAD origin/feat/infinite-memory-prompts` → both `3825237d`.
