# S5 · Repair iteration 1 of 8 — infinite-memory-prompts

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-prompts` · branch `feat/infinite-memory-prompts` · entry HEAD `358bfadf` · code HEAD after repair `689599d3` (pushed) · PR https://github.com/cerredz/Vidbyte-SDK/pull/1176 (draft, base `feat/infinite-memory-agent`).

## 1. Outcome

Every packet item is fixed, one commit each: R-1 (Blocker), R-2 to R-6 (Majors), and the Minors R-7 to R-12, R-13 (root `:13` part only), R-19 and R-26. Each fix uses the verifier's text from review.md word for word. Every measured result matches the verifier's what-if numbers to the token. Every gate is green except the 3 inherited `harness_threads` surface failures in the source stage, which the orchestrator reproduced at base 7efceb55. No test, Python file, lint baseline or config changed. `git diff --stat f4cad411 HEAD -- tests` is empty, and `git diff --stat origin/feat/infinite-memory-agent HEAD -- 'vidbyte/*.py'` is empty.

The fixes moved the root prompt's estimate to 2,854, which rounds to 2,900 under AC-11. So `vidbyte/agents/infinite/README.md:68` "about 2,800 tokens" became false, and it now reads "about 2,900 tokens", in the same commit as R-26. The other two figures stay true.

## 2. Gate matrix (run in this worktree, this iteration)

| # | Gate | Command | Result | Final lines |
|---|---|---|---|---|
| 1 | new module | `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_prompts.py -q -p no:cacheprovider` | PASS | `...........................................................              [100%]` / `131 passed in 0.91s` |
| 2 | feature pack | `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` | PASS | `............................                                             [100%]` / `244 passed in 4.66s` |
| 3 | custom lint | `python lint/run.py` | PASS | `S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline` / `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` / `SDK-LINT: PASS` |
| 4 | semgrep | `git add -A` (the tree was clean), then `<scratchpad>/semgrep-venv/Scripts/python.exe <scratchpad>/run_semgrep.py` | PASS | `Ran 1 rule on 980 files: 0 findings.` |
| 5 | public API | `python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 9eca4a33ddb5ea1a21c07f840e556487a8770e19 (vidbyte-sdk 0.3.0, 644 exports).` |
| 6 | full gate, source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS except the 3 inherited failures | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` / `FAILED …::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` / `FAILED …::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` / `============ 3 failed, 6174 passed, 16 skipped in 98.09s (0:01:38) ============` / `CI failed: Command failed with exit code 1: …python.exe -m pytest` |
| 7 | full gate, package | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| 8 | measure | `python <scratchpad>/measure_seven.py <worktree>` | PASS | table in §3 |
| — | remote | `gh pr checks 1176` | none | `No checks reported on the 'feat/infinite-memory-prompts' branch`. GitHub Actions are disabled repo-wide, so the local gates are the gates of record. |

**The source stage.** The log is at `<scratchpad>/s5-1/source-stage.log`. Its earlier steps passed: `SDK-LINT: PASS` is at log line 182, then compileall and the three check scripts ran, and pytest is the only step that failed. The three failures are exactly the inherited set the briefing names, so they are not this repair's: this repair changes no Python, no root export, nothing under `vidbyte/tools`, and nothing under `vidbyte/lib/configs`. The known Windows stdio flake did not fire. `S063 IMPROVED` comes from an AST rule over Python (`asyncio.gather` handling). It was inherited, and I left the baseline alone.

## 3. Measurements (tiktoken cl100k_base and TokenEstimate, through `Prompts().get`)

| Asset | chars | est | tik | entry tik (358bfadf) | baseline tik | floor |
|---|---|---|---|---|---|---|
| root_system_prompt | 11,415 | 2,854 | 2,465 | 2,424 | 1,829 | ok (ceiling 2,600) |
| generator_system_prompt | 6,988 | 1,747 | 1,490 | 1,478 | 1,277 | ok |
| verifier_system_prompt | 5,733 | 1,434 | 1,216 | 1,209 | 1,059 | ok |
| task_prompt | 5,393 | 1,349 | 1,142 | 1,136 | 241 | ok |
| verifier_task_prompt | 5,489 | 1,373 | 1,160 | 1,135 | 251 | ok |
| resume_prompt | 5,292 | 1,323 | 1,137 | 1,123 | 232 | ok |
| launch_tool_description | 5,352 | 1,338 | 1,123 | 1,139 | 416 | ok |

The 23-description per-leaf sums are est 4,577 (bound 4,900) and tik 3,906 (bound 4,183). remember_staged_prompt measures 42 tik and 47 est, under the 80-token reply bound. The README figures follow row 42's arithmetic. The root is 2,854 est, so "about 2,900". The 24 descriptions sum to 5,915 est, so "about 5,900". The total is 90,000 + 2,854 + 5,915 + 8,000 = 106,769, so "near 107,000".

**Independent check.** The verifier measured every fix on an exported copy (`reports/S4-findings-verifier.md` §7 and review.md). I re-measured on the live tree after each commit, and every number matched: generator 1,490, verifier 1,216, task 1,142, resume 1,137, launch 1,123, verifier_task 1,149 then +11 for R-12, root 2,452 then +20, −12 and +5, and the sum 3,906. The pack test pins the whole verifier system prompt into the verifier's system string (delegation `:416`), and it passed after R-3.

## 4. Per finding: reproduction, change, evidence

| ID | Reproduction (before) | Change (verifier's text) | Commit | Evidence after |
|---|---|---|---|---|
| R-1 Blocker | launch `:13` said both agents "see their task card, the context it names". In the code, `launch.py:309` `_verifier_message` formats only instructions, goal, criteria, status, summary, staged, files and quota; entries and paths go only into `_task_message` (`:302`) | First sentence of `:13` → "Both agents start fresh: each sees its own part of the task card, the workspace map, and the shared workspace, but not this conversation, and only the generator receives the context the card names." | `a2ae814c` | 1,139 → 1,149; the family's only remaining context-receipt claims all say generator-only (launch_context `:11`, launch_generator_prompt `:11`, launch `:13`) |
| R-2 | task `:41` said the map "lists every other file". In the code, `workspace.py:219-229` stops at `INFINITE_MAP_MAX_TOKENS` and ends with "… and {count} more files" | "lists the workspace's files with their sizes and descriptions, as many as fit," | `032dc49f` | 1,136 → 1,142; `grep -c "lists every other file"` → 0 |
| R-3 | `grep -o -i "[^.]*limited[^.]*\."` found nothing in either verifier asset | ver `:11` gains ", since your own context is limited"; vtask `:51` "Your context is limited, so read only the parts each check needs" | `572667bf` | the same grep finds both sentences; 1,216 and 1,141; pack 244 |
| R-4 | vtask `:35` "judge against that reading if the goal supports it" and task `:17` "so the verifier judges against it" contradicted vtask `:25` and `:61` | task `:17` → "so the verifier can test it."; vtask `:35` → "…that choice is a claim too, so name in your review the reading you judged by." | `d67bfadc` | `grep -c "judges against it\|judge against that reading"` → 0 in both; 1,142 and 1,149 |
| R-5 | root `:20` "only … never to do the work" contradicted `:48` and `:52` (#1113) and `:20`'s own "a small fix" | (a) `:20` → "…only to decide what a card should say, make a small fix, or check what your final answer depends on; never do a pair's work yourself." (b) `:48` → "so when you need the detail, read only that part of a named file." (c) `:3` adds "your small fixes," | `e04d62ea` | `grep -c "never to do the work\|so read the named files for detail"` → 0; 2,452; the pins "more text into your context than its result card" and "a card is not memory" are untouched |
| R-6 | `whatif.py R5_resume_drop_only` → 1,098 (under the floor) | The two restatements were deleted, and step 6 gained the code-true turn-limit sentence. Code: `agents/runtime.py:2002-2005` and `:371-378`, `infinite/runtime.py:101`, `journal.py:89-90`, `runtime.py:1649-1650`, and `infinite/settings.py:126` (the 500-turn default) | `0253ed07` | `grep -c "replays nothing\|relaunch only what the deliverables"` → 0; 1,137; pack 244. The sentence names no number. |
| R-7 | gen `:52` presupposed that entries exist | "…needs, if any, before you reply." | `08c412e0` | 1,482 |
| R-8 | gen `:37` invited a whole-note read-back | appended ", reading back only the parts you need" | `7b5c9616` | 1,490 |
| R-9 | note_path `:7` described write_note inside edit_file's path description too (`memory.py:182`, `:215`) | "Keep one stable path for your task's subject and give it again to add to that note, so related findings stay together instead of scattering across new files." | `65c8884c` | 189 → 182; sum 3,906; still ≥ 4 sentences |
| R-10 | launch `:13`'s last sentence duplicated launch_context and launch_tools in the same schema (outline 7.3) | deleted, after R-1 | `6647ca4e` | 1,149 → 1,123; pack 244 |
| R-11 | root `:54` lacked outline 1.6's ban, and its bar was "wrong without" against `:60`'s "wrong or slower" | the verifier's replacement text, which keeps the decision-entry rule | `60cf9597` | 2,472 |
| R-12 | vtask `:17` reported a goal miss but never fixed it | "say so in your review, and fix it when the fix stays inside the task; the criteria still decide the verdict." | `19203993` | 1,160 |
| R-13 (root `:13`) | "Record in the plan note which deliverables each card settles." restated `:54` and `:73`. It was new text; the base step 5 is only the first sentence | deleted | `347c8930` | 2,460 |
| R-19 | remember_staged_prompt had no nudge (INV-2) | appended "Stage only what a later agent would be wrong or slower without." | `5699f96e` | a fragment with no trailing newline (checked with `od -c`), `{key}` once, 42 tik; the render with `key='s1'` is correct; pack 244 |
| R-26 | root `:16` asked for a whole re-read of an append-only plan note | "re-read the part of your plan note you need" | `689599d3` | 2,465; README `:68` → "about 2,900 tokens" |

In review.md, each of these rows now reads `fixed @<sha>`. The R-13 row says its root `:13` part is fixed and its vtask `:25` and resume `:1` parts remain follow-ups.

## 5. #1113 sentences reworded (for INV-19 and the PR body)

Before every edit, I checked whether the old text exists at `origin/feat/infinite-memory-agent`, the #1113 base. Only two #1113 sentences are reworded. No #1113 sentence is dropped, and each rule is kept.

1. **`launch_tool_description.md`, How it behaves (R-1).**
   - Before: "Both agents start fresh: they see their task card, the context it names, the workspace map, and the shared workspace, but not this conversation."
   - After: "Both agents start fresh: each sees its own part of the task card, the workspace map, and the shared workspace, but not this conversation, and only the generator receives the context the card names."
   - Why: the old sentence is false for the verifier (`launch.py:309`). The rule it carries, that a fresh pair sees the card and the workspace but not the conversation, is kept.
2. **`root_system_prompt.md`, Reading result cards (R-5 b).**
   - Before: "- **Summary** is the generator's final answer and **Review** the verifier's; long text ends with a cut marker, so read the named files for detail."
   - After: "- **Summary** is the generator's final answer and **Review** the verifier's; long text ends with a cut marker, so when you need the detail, read only that part of a named file."
   - Why: the old wording conflicted with the new reading rule at `:20`, and it left the matrix cell P1 × parent reading a card without a rule. The kept rule is to read the named files for detail; the new wording adds "only that part".

Every other edited sentence is new text from this PR (S3), shown by `grep -F` against the base: launch `:13`'s last sentence, task `:17` and `:41`, vtask `:17`, `:35` and `:51`, ver `:11`, gen `:37` and `:52`, root `:3`, `:13`, `:16`, `:20` and `:54`, resume `:25`, and note_path `:7`. remember_staged_prompt keeps its base text and gains one sentence. Resume step 6 gains one sentence, and none of its text is changed.

## 6. Hypotheses tried and decisions

- For R-11, I considered using outline 1.6's literal words, "never save a card's status or progress". I kept the verifier's measured wording, "Keep its status and progress in the plan note, never in an entry", which states the same ban and which the orchestrator approved. The phrase is not a pin for root.
- R-26 crossed the README rounding boundary: est 2,849 → 2,854. Staying under 2,850 would allow at most 2 added characters. So the README figure was corrected, as the briefing allows, and I did not weaken R-26.
- I did not apply the rejected reviewer fixes the briefing lists (R-V1 vtask cut, R-E3, R-E1 alternative, R-C4, R-E2 alternative).
- The Edit tool leaves LF endings in a CRLF working tree, and git warns "LF will be replaced by CRLF". The index is LF, so this is harmless. Every count goes through `Prompts().get`.

## 7. New observation (not fixed; outside the packet)

Two base sentences make the claim that R-2 removed from task_prompt:
- `note_path_description.md:7`: "because the workspace map lists every file by its path and other agents decide from it what to read"
- `root_system_prompt.md:58`: "shows the totals against their caps, the count of live memory entries, and one line per file with its size and description"

Both are false once the map passes `INFINITE_MAP_MAX_TOKENS` (`workspace.py:219-229`). Both exist at `origin/feat/infinite-memory-agent`, so a reword needs an INV-19 note. The orchestrator should decide whether to add them as R-27. A possible fix is "as many as fit", as in R-2. note_path has a few tokens of room under the sum bound (3,906 / 4,183).

## 8. Still open

No packet item is open. The follow-ups keep the status review.md gives them: R-13 (vtask `:25` and resume `:1` parts), R-14, R-15, R-16, R-17, R-18 (the turn rule is now in resume only, per R-6), R-20, R-21, R-22, R-23, R-24 and R-25.
