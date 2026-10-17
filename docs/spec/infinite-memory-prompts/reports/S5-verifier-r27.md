# S4 findings verifier, scoped to R-C101 → R-27

Worktree `feat/infinite-memory-prompts` at `db4d8a30` (the code is the same as `689599d3`). Base `origin/feat/infinite-memory-agent` = `7efceb55`. I wrote only `review.md` (one row, the heading count, and one sentence appended to the Verdict) and this report. Helper scripts and the copied texts are in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7d03425b-8396-4738-89eb-c11a8a3fac1a/scratchpad/s5-verifier-r27/`.

## Decision

**CONFIRMED, Major.** Both sentences describe a complete map. The code cuts the map at its cap, and that cut state is where a long run ends up. R-2 made the same claim in task `:41` and was confirmed Major under FR-10 (P0) and the field-guide lesson. These two sentences have the same defect and the same mitigation, so they get the same rating. It is not a Blocker for the reason R-2 was not: in the cut state the map shows the cut itself, because the header counts every file and the last line says how many were left out.

## Evidence

### 1. What the sentences say (read at HEAD)
- `root_system_prompt.md:58`: "The workspace map in your context, redrawn after each of your tool calls, shows the totals against their caps, the count of live memory entries, and one line per file with its size and description." A literal reader takes "one line per file" to mean that every file has a line.
- `note_path_description.md:7`: "…because the workspace map lists every file by its path and other agents decide from it what to read." This is false outright once the map is cut.

### 2. What the code does
- `vidbyte/agents/infinite/workspace.py:219-220` returns the whole map only when `TokenEstimate.count(rendered) <= INFINITE_MAP_MAX_TOKENS` (8,000, `vidbyte/lib/constants/infinite.py:71`).
- `:225-230`: past the cap, the map keeps the first lines that fit and returns `INFINITE_MORE_FILES` ("… and {count} more files", `constants :135`).
- The line order comes from `FolderUsage.tokens_by_file`, which iterates `sorted(root.rglob("*"))` (`vidbyte/lib/tools/filesystem/usage.py:33`). The cut therefore drops the paths that sort **last**. Recency and importance play no part.

### 3. Executed against the real `InfiniteWorkspace` (default settings, `max_files` 2,000)
`map_cut_demo.py` writes notes through `workspace.write_note`, the same call the memory tools make, and renders `map_text()`:

| Workspace | Files on disk | Map file lines | Last line |
|---|---|---|---|
| 20 notes, 60-char descriptions | 25 | 25 | a file line |
| 300 notes, 60-char descriptions | 305 | 305 (7,213 est) | a file line |
| 300 notes, 120-char descriptions | 305 | 208 (7,975 est) | "… and 97 more files" |

- In the cut case, the first note written (`zz-first-finding.md`, which sorts last) is **not** on the map, and the newest note (`aa-latest.md`, which sorts first) is.
- The first cut comes at 426, 279 and 166 files on disk for 40-, 80- and 160-character descriptions. The re-reviewer's "a few hundred files" holds.
- `plan_note_cut.py` adds a root `plan.md` and then 240 generator notes under `notes/`, 244 files in all. The map shows 230 lines plus "… and 14 more files", and **`plan.md` is not on the map**, because `notes/…` sorts before `plan.md`.

### 4. Who reads each sentence
- Root `:58`: the root's system prompt, used raw (`vidbyte/agents/infinite/agent.py:72`). A resumed root gets it too, because the system prompt is the same.
- note_path `:7`: the `path` description of `write_note` (`memory.py:182`) and of `edit_file` (`memory.py:215`). `InfiniteMemoryToolRegistry` grants `write_note` to every role under both presets (`vidbyte/lib/registries/infinite.py:36-37`). The root gets its tools at `infinite/runtime.py:85` and every child (generator and verifier) at `launch.py:286`. Under FULL the description appears twice per schema.
- A generator therefore reads "lists every file" in its schema and "as many as fit" (task `:41`, after the R-2 fix) in its briefing, in the same call. Those are two contradicting statements about one fact.

### 5. Base text
- `git show origin/feat/infinite-memory-agent:…/root_system_prompt.md` (= `7efceb55`) holds the root sentence verbatim at its line 51, and `…/note_path_description.md` holds the note_path sentence verbatim.
- `git log -S"one line per file with its size and description"` → `7efceb55` (#1113). `git log -S"lists every file by its path" --all -- …/note_path_description.md` → `2c84049c` (#1084), `75599001`, `7efceb55`. The sentence came from #1084 and #1113 moved it into the Markdown leaf.
- `git log -S"as many as fit"` → only `032dc49f` (R-2), which changed only task `:41`.

### 6. Why this matters
A literal model trusts "the map lists every file" and decides that a file missing from the map does not exist (EC-9).
- **Root:** launch `:13` tells it to "check the map … for what earlier pairs found". A note past the cut looks absent, so the root relaunches finished work under a new name. That breaks P7 and spends the agent budget.
- **Resumed root:** resume step 1 says "Read the workspace map and your plan note … If you kept no plan note, write one now". If `plan.md` sorts past the cut (shown in §3), a root that believes the map is complete can conclude that it kept no plan, and then start a new one that loses the deliverable statuses.
- **What limits the damage:** the header ("Files: 244 of 2000") and the last line both show the cut, and root `:58`'s next sentence says grep covers every note. That is why this is Major and not a Blocker.

## Smallest fix (recommended) and measurements

| # | Asset | Old string (exact, occurs once) | New string |
|---|---|---|---|
| 1 | `root_system_prompt.md:58` | `and one line per file with its size and description.` | `and one line per file with its size and description, as many as fit.` |
| 2 | `note_path_description.md:7` | `lists every file by its path` | `lists files by their paths` |

**Why I recommend a different variant from the re-reviewer's.** Fix 1 uses the same words R-2 put in task `:41` ("as many as fit"), so the family states this fact with one phrase. It is also 2 tik smaller. The re-reviewer's variant is kept as the alternative below.

**Measurements.** All counts go through `Prompts().family` / `Prompts().get`, with tiktoken `cl100k_base` and `TokenEstimate.count`. The scripts are `measure_fix.py` and `apply_fix.py`. The test run uses a `git archive HEAD` copy with the patch applied; the worktree was not touched.

| Check | HEAD | Recommended | Re-reviewer's alternative (", for as many files as fit.") |
|---|---|---|---|
| root tik / est | 2,465 / 2,854 | 2,470 / 2,858 | 2,472 / 2,861 (matches the re-reviewer's figures) |
| README `:68` "about 2,900" (est, nearest hundred) | 2,900 ✓ | 2,900 ✓ | 2,900 ✓ |
| 24-description est sum → "about 5,900" | 5,915 ✓ | 5,915 ✓ | 5,915 ✓ |
| per-call total → "near 107,000" | 106,769 ✓ | 106,773 ✓ | 106,776 ✓ |
| note_path tik / est / S025 sentences | 182 / 204 / 7 | 181 / 204 / 7 | 181 / 204 / 7 |
| 23-description sum tik (≤ 4,183) / est (≤ 4,900) | 3,906 / 4,577 | 3,905 / 4,577 | 3,905 / 4,577 (matches) |
| digits / braces in either leaf | none | none | none |
| root pins (8) missing / note_path keep nudge | 0 / present | 0 / present | 0 / present |
| root repeated sentences of 5+ words | none | none | none |
| `test_infinite_memory_prompts.py` | 131 passed | 131 passed | — |
| feature pack `tests/features/infinite_memory_agent` | 244 passed | 244 passed | 244 passed |
| `python lint/run.py` (in a throwaway git repo of the copy) | PASS | `SDK-LINT: PASS` (S064 ratcheted, 4 known) | — |

**INV-19.** Both edits reword a #1113 sentence and keep its rule. Root `:58` still describes what the map shows. note_path `:7` still says to choose a descriptive name because other agents decide from the map. The PR body should name both rewords next to R-1 and R-5b.

## Observations outside R-27 (no row added)
- **resume `:29`, step 1.** "If you kept no plan note, write one now" sits after "Read the workspace map and your plan note". §3 shows the root's plan note can fall off a cut map. The R-27 fix tells the root the map may be partial, and root `:58`'s grep sentence is the fallback. A sharper step 1 ("search for it before you decide you kept none") would add scope, which is the orchestrator's call. It is not needed for R-27.
- **`map_header`.** "Each line below is one workspace file…" does not cover the closing "… and N more files" line. That line reveals the cut, and `map_header` is a shape leaf that cannot grow (INV-15 d), so this is not a defect worth a change.
- **write_note_file_description `:3` and `:7`.** "shown beside its path on the workspace map" and "decide from the map alone" describe where a description appears. Neither claims that every file appears, so neither is false.
- **README `:58`.** It makes the same claim. It was already false at base, so it remains the recorded follow-up (Q-2/INV-20), as the brief directs.

## Commands run
- `git log --oneline -3`, `git status --short` → HEAD `db4d8a30`, clean before and after.
- `git log --oneline -S"…"` for each phrase (§5); `git show origin/feat/infinite-memory-agent:<leaf>`.
- Read: `workspace.py:207-231`, `usage.py:27-37`, `memory.py:55-60,170-225`, `registries/infinite.py`, `constants/infinite.py:48-71,130-137`, `agent.py:72,120`, `runtime.py:85,115`, `launch.py:276,286`, and the spec FR-10, INV-19, EC-9, outlines 1 and 22–25, §12.3 (2) and row 23 ("check every sentence against the code truth").
- `python s5-verifier-r27/map_cut_demo.py <worktree>` and `python s5-verifier-r27/plan_note_cut.py <worktree>` (§3).
- `python s5-verifier-r27/measure_fix.py <worktree> s5-verifier-r27/texts`. It wrote the current and patched leaf texts into `texts/`.
- `python s5-rereview/whatif_c101.py <worktree>`. I read the script first: its 23-leaf selection matches the test's `compact_descriptions`. Output: root 2,465 → 2,472 tik, 2,854 → 2,861 est; note_path 182 → 181; sums 3,905 / 4,577; total 106,776. Reproduced exactly.
- `python measure_seven.py <worktree>` → the seven assets 2,465 / 1,490 / 1,216 / 1,142 / 1,160 / 1,137 / 1,123 tik; sum 3,906.
- `git archive HEAD | tar -x` → copy; `apply_fix.py <copy> verifier-min`; `pytest …/test_infinite_memory_prompts.py` → 131 passed; `pytest tests/features/infinite_memory_agent` → 244 passed; `lint/run.py` → `SDK-LINT: PASS`. Then I restored the two leaves in the copy from `HEAD`, ran `apply_fix.py <copy> reviewer`, and the pack gave 244 passed.
