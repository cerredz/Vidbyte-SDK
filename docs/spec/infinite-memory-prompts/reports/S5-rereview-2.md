LENS: conformance (post-repair re-review, round 2)
VERDICT: SOUND — Both repairs resolve their findings on every path I could build. The three edited sentences are true of the code, and no pin, floor, heading, newline rule, matrix cell, #1113 rule or boundary regressed.

Scope. I read `git diff origin/feat/infinite-memory-agent...c77bc7c6`; HEAD is now `9ae5db13`, and every commit after `c77bc7c6` changes only `pipeline.md`. I also read the latest repairs, `git diff 689599d3..3825237d -- vidbyte/`: three lines in three leaves. I read each touched leaf in full: `root_system_prompt.md`, `note_path_description.md` and `resume_prompt.md`. Paths are relative to `vidbyte/prompts/prompts/infinite_memory/` unless they start with `vidbyte/` or `docs/`. The short names are "root", "resume", "note_path", "task" (`task_prompt.md`), "vtask" (`verifier_task_prompt.md`), "gen" (`generator_system_prompt.md`) and "launch" (`launch_tool_description.md`). Token counts are tiktoken `cl100k_base` through `Prompts().get`, unless a count is marked "est".

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets)
- **R-27's two rewords make the family describe the map one way, and the code agrees.** Root `:58` now ends "one line per file with its size and description, as many as fit." note_path `:7` now says "the workspace map lists files by their paths". Both match task `:41`, which R-2 fixed. They also match the code: `vidbyte/agents/infinite/workspace.py:219-230` keeps the first lines that fit, in sorted path order (`vidbyte/lib/tools/filesystem/usage.py:33`), and ends with "… and {count} more files" (`vidbyte/lib/constants/infinite.py:135`). The words "every file" now appear only in sentences that are not about the map: root `:32`, task `:41`, vtask `:51` and `launch_verifier_prompt_description.md:7`.
- **The resumed root has the tools to follow R-28.** `vidbyte/agents/infinite/agent.py:77` gives the root `InfiniteMemoryAgentTools` (bash, grep, read_lines) under both presets. `grep` is a reserved tool name (`vidbyte/lib/constants/infinite.py:104-109`), and a developer tool that uses it is refused (`vidbyte/agents/infinite/runtime.py:72`). Grep skips only `.runs` and `superseded.jsonl` (`vidbyte/tools/toolsets/infinite.py:47`), so it also searches `files.jsonl`. That file holds each new file's description in creation order, and root step 2 has the plan note written first, so the plan note's description is on line 1.
- **Every mechanical rule still holds after the repairs.** The seven assets measure 2,470 / 1,490 / 1,216 / 1,142 / 1,160 / 1,151 / 1,123 tik, and each is at least 1,000 est. Resume sits in its 1,100–1,300 target band. The 23-description sum is 3,905 tik (bound 4,183) and 4,577 est (bound 4,900). note_path has 7 S025 sentences. The following all hold:
  - no pin is missing;
  - no sentence of five or more words appears twice;
  - no digit appears;
  - resume's braces equal 2 × 3 placeholders;
  - resume ends without a newline, and root and note_path end with exactly one;
  - the headings are in base order (audit §3–6 found nothing).

  README `:68` stays true: 2,858 est rounds to "about 2,900", 5,915 rounds to "about 5,900", and 106,773 rounds to "near 107,000".
- **The repairs stayed inside their boundaries.** Since `689599d3`, the only change outside `docs/` is those three lines. Since base, the PR touches only family assets, `vidbyte/agents/infinite/README.md` and S2's three test-pack files. `git diff --stat f4cad411..HEAD -- tests/` is empty. No `.py` file, lint file, script, constant, config or contract changed.

FINDINGS (ranked, most severe first, max 15)
None. I found no Blocker, Major or Minor inside the lens, and none outside it that the latest repairs introduced.

Notes. These are not findings, and none needs action.
- **I tried to break R-28 with grep's own result cap.** Grep returns at most 50 matches by default (`vidbyte/tools/builtins/code_search/grep.py:47`). It could therefore hide a match the way the cut map hides a line. I built three cut workspaces with the real `InfiniteWorkspace`, and each time I ran the root's own grep (`grep_cap_attack.py`):
  - (A) `plan.md` at the top level, plus 240 notes under `notes/` that also contain "deliverable";
  - (B) the plan note at `z-run/plan.md`, plus 240 top-level notes that contain "deliverable";
  - (C) the same as (B), with the pattern "plan".

  The map hid the plan note every time. Grep found it every time, with its first match (hit #0) at `files.jsonl:1`, the note's description line, even when the cap cut the results in (A) and (B). When the cap cuts, grep says so: "Results truncated; narrow the pattern."

  One edge case remains: 50 or more matching top-level files whose names sort before `files.jsonl` could push the description line past the cap. In that case grep's truncation message shows the cut, and the tool accepts `subdir` and `max_results`. This is not a defect.
- **`write_note_file_description.md:3` is technically untrue for a cut map, but harmless.** It says a description is "shown beside its path on the workspace map", which is not so for a file past the cut. The sentence tells a writer where its description appears, so it cannot lead a reader to think that a file is absent. The repairs did not change it, and `reports/S5-verifier-r27.md` reached the same reading.
- **The recorded follow-ups are unchanged.** `map_header`'s "Each line below…" and README `:58` keep their status, and the repairs did not make either worse.

FIX CONFIRMATIONS:
- **R-27: CONFIRMED.**
  - **The prosecution's failure.** A literal model trusts "the map lists every file". It takes a note past the cut as missing (EC-9) and relaunches finished work (P7). On resume, it also misses its own plan note.
  - **Every path that delivered the false claim is closed:**
    1. The root, fresh or resumed, reads root `:58` raw (`agent.py:72`). It now reads "as many as fit", and the next sentence says that grep covers every note.
    2. A generator reads note_path `:7` in its write_note schema (`memory.py:182`; under FULL also edit_file, `:215`) and task `:41` in its brief. Both now agree in the same call: "lists files by their paths" and "as many as fit".
    3. Launch `:13` says "check the map and search memory for what earlier pairs found". The root and the generators read it, and both now know that the map is partial. The sentence itself also pairs the map with a search.
    4. The verifier holds no launch tool. Its map sentence (ver `:31`, "drawn when you started and does not change") does not claim that the map is complete.
  - **The defense holds.** Both are #1113 rewords that keep their rule. Root `:58` still lists what the map shows, and note_path `:7` still says to choose a descriptive name because agents decide from the map. INV-19 holds. The PR body must name both rewords; `reports/S5-repair-2.md` §5 has the before and after text.
- **R-28: CONFIRMED.**
  - **The prosecution's failure.** A cut map hides the plan note. The old step 1 said "If you kept no plan note, write one now", so the root starts a second plan note and loses the deliverable statuses.
  - **The new text puts the search before the decision:** "If the map does not show your plan note, search the workspace for it; if you kept none, write one now…".
  - **Executed.** `plan_note_found_by_grep.py` printed "plan.md on the map: False" and "found by the root's grep: True". My three scenarios above all found the plan note.
  - **No regression.**
    - The new clause is code-true and has no digit.
    - The placeholders and the newline rule are unchanged.
    - Outline 6.4's order still holds: read the map and the plan note, then compare, launch, record, decide and finish.
    - It restates no rule in resume (NFR-4). "Search memory", "search the workspace for it" and "search before you save" each search for a different thing.
    - It supports P1 and P7 at the resume stage, because searching is cheaper than reading notes and the workspace is the record.
    - Resume measures 1,137 → 1,151 tik.
  - **No INV-19 note is needed.** The old sentence is this PR's own text (`e5487315`), and the base resume prompt never says "plan note".

VERIFIED CLAIMS:
1. S5-repair-2 §4 says R-27 uses the scoped verifier's recommended text word for word. HELD: `git diff --word-diff` shows exactly `description.` → `description, as many as fit.` and `every file`/`its path` → `files`/`their paths`.
2. "`agent.py:77` gives these to the root under both presets." HELD: the tools are built unconditionally, and `grep` is reserved, so a clashing developer tool is refused (`vidbyte/agents/infinite/runtime.py:72`).
3. "grep finds `plan.md` by its description in `files.jsonl:1` and by its own text at `plan.md:1`." HELD: the repair agent's script reproduced it, and my scenario (A) printed hits `#0:files.jsonl:1` and `#1:plan.md:1`.
4. The measurements: root 2,470 tik / 2,858 est; resume 1,151 / 1,339; note_path 181 / 204 with 7 sentences; 23-description sum 3,905 / 4,577. HELD: the spec §4 snippet as written, `measure_seven.py` and `measure_repair2.py` all agree.
5. README `:68` keeps all three figures true. HELD: 2,858 → 2,900, 5,915 → 5,900, and 106,773 → 107,000.
6. R-28's old sentence is new text from this PR, so it needs no INV-19 note. HELD: `git log -S"If you kept no plan note"` returns `e5487315` and `3825237d`, and the base resume prompt contains "plan note" 0 times.
7. The root `:58` and note_path `:7` sentences are base text. HELD: `git log -S` returns `7efceb55` (#1113) for the root sentence, and the base note_path leaf holds "lists every file by its path" once.
8. "No test, Python file, lint baseline, config, or file outside the `infinite_memory` family changed." HELD: see the boundary commands below.
9. The briefing's gate figures (module 131, pack 244, `SDK-LINT: PASS`) and its seven tiktoken figures. HELD.
10. review.md marks R-27 `fixed @fe04ab8c` and R-28 `fixed @3825237d`. The figures in verify-log.md iteration 2 equal my measurements. HELD.
11. S5-repair-2 §4 says "every file" now appears only in sentences that are not about the map. HELD: the four leaves `measure_repair2.py` lists are root `:32`, task `:41`, vtask `:51` and launch_verifier_prompt `:7`, and I read each one.

I did not re-run the source and package stages, semgrep or the public-API check. The repairs change only three Markdown leaves, and the orchestrator ran those checks at `5f41a5f4`, whose code is identical to `3825237d`.

COMMANDS RUN:
- `git status --short; git log --oneline -4; git diff --stat c77bc7c6..HEAD; git diff --stat 3825237d..HEAD -- vidbyte tests` → clean; `9ae5db13` adds only `pipeline.md` (2 insertions); nothing under `vidbyte/` or `tests/` changed after `3825237d`.
- `git diff --stat origin/feat/infinite-memory-agent...c77bc7c6` → 38 files; outside `docs/`: README, 14 family assets, 3 test-pack files.
- `git diff 689599d3..3825237d -- vidbyte/` and `--word-diff=plain -U0` → 3 files, 3 insertions, 3 deletions.
- `git diff f4cad411..HEAD --stat -- tests/` → empty. `git diff --name-only origin/feat/infinite-memory-agent...HEAD -- '*.py' lint scripts pyproject.toml .semgrep contracts` (tests excluded) → empty. `git diff --name-only 689599d3..HEAD -- . ':!docs'` → the three leaves.
- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_prompts.py -q -p no:cacheprovider` → `131 passed in 1.02s`.
- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` → `244 passed in 6.94s`.
- `PYTHONPATH=$(pwd) python <scratchpad>/s5-rereview/snippet4.py` (the spec §4 snippet verbatim) → `root_system_prompt: estimate 2858, tiktoken 2470` … `resume_prompt: estimate 1339, tiktoken 1151` / `launch_tool_description: estimate 1338, tiktoken 1123`.
- `python <scratchpad>/measure_seven.py <worktree>` → `23-description per-leaf sums (23 leaves): est 4577  tik 3905`.
- `python <scratchpad>/s5-2/measure_repair2.py <worktree>` → for the three leaves: no pins missing, no duplicates, no digits, headings in order, placeholders once. Last lines: `== README :68: root est 2858 -> 2900 …; 24-sum est 5915 -> 5900 …; per-call 106773 -> 107000` / `== 'every file' anywhere in family: ['root_system_prompt', 'task_prompt', 'verifier_task_prompt', 'launch_verifier_prompt_description']`.
- `python -I <scratchpad>/s5-rereview/audit.py <worktree>` → §3/4, §5 and §6 print nothing (no duplicate, near-duplicate, digit, brace, newline or heading defect); `done`.
- `python lint/run.py` → `S064 RATCHETED: 4 known finding(s) …` / `SDK-LINT: PASS`.
- `git log --oneline -S"If you kept no plan note" -- …/resume_prompt.md` → `3825237d`, `e5487315`; `git show origin/feat/infinite-memory-agent:…/resume_prompt.md | grep -c "plan note"` → `0`; `git log -S"one line per file with its size and description" origin/feat/infinite-memory-agent` → `7efceb55`; base note_path `grep -c "lists every file by its path"` → `1`.
- `python <scratchpad>/s5-2/plan_note_found_by_grep.py <worktree>` → `files on disk 244; map lines shown 230; last line: … and 14 more files` / `plan.md on the map: False` / `plan.md found by the root's grep: True`.
- `python <scratchpad>/s5-rereview-2/grep_cap_attack.py <worktree>` (new; it writes only to a temp dir) → `[A] … map lines 228 … 16 more files … plan note on map: False; grep 'deliverable' finds it: True; truncated notice: True; … ['#0:files.jsonl:1', '#1:plan.md:1', 'total blocks 51']` / `[B] … on map: False; … finds it: True; truncated notice: True; ['#0:files.jsonl:1', …]` / `[C] … grep 'plan' finds it: True; truncated notice: False`.
- Code read: `workspace.py:207-231`, `usage.py:27-37`, `agent.py:60-125`, `toolsets/infinite.py:1-55`, `registries/infinite.py:20-50`, `code_search/grep.py:1-140`, `code_search/base.py:73-103`, `constants/infinite.py:71,104-125,135`, `infinite/runtime.py:72-73`, `dataclasses/tools.py:283-290`.
- `git status --short` after every run → clean (bytecode writing was off). This report is the only file I wrote in the worktree.

`<scratchpad>` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7d03425b-8396-4738-89eb-c11a8a3fac1a/scratchpad`.
