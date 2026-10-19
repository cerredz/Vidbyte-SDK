# S6 · PR author — infinite-memory-prompts

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-prompts` · branch `feat/infinite-memory-prompts` · entry HEAD `77171eeb` (clean) · exit HEAD `88a14bca` (pushed) · PR https://github.com/cerredz/Vidbyte-SDK/pull/1176 (draft, base `feat/infinite-memory-agent`).

## 1. Outcome

- `docs/spec/infinite-memory-prompts/pr-body.md` holds the title (line 1) and the body, with the template's nine headings in order.
- The spec is finalized:
  - frontmatter: `status: pr-open`, `updated: 2026-10-17`, `pr:` set;
  - §5: the diagrams and paragraph corrected to the code in three places;
  - §17: a new S6 row.
- Two docs-only commits, both pushed:
  - `4974e259` `docs(spec): finalize infinite-memory-prompts for PR`
  - `88a14bca` `docs(spec): state the gate commit of the infinite-memory-prompts PR body`

  The second commit was needed because the first body called `77171eeb` "the PR head", which the commit adding the body made false. The body now names `77171eeb` as the gate commit.
- The PR title and body were set from the committed file. The remote body equals the local file byte for byte after newline normalization (37,311 characters).
- No source, test or `pipeline.md` file changed. The PR is still a draft.

This report is the only file I wrote that is not committed. The briefing said to commit only the spec and `pr-body.md`, so the orchestrator commits this report with its next pipeline record.

## 2. What the shipped text does (my reading of the diff)

The PR touches 13 of the 40 leaves and one README line; the other 27 leaves are byte-identical to the base.

- **Three system prompts.** They keep every heading and every #1113 rule, and they gain the rules that apply at each stage the role passes through.
  - The root:
    - is told the run is unattended, so it decides and records open questions instead of ending its turn with a question;
    - writes the task's deliverables into a plan note before planning (flow step 2);
    - treats the workspace and the map as the record;
    - reads a file only to write a card, make a small fix, or check what its final answer depends on;
    - asks pairs for only what it will use;
    - treats a card as not memory: status and progress go to the plan note, never into an entry;
    - saves an entry only when a later agent would be wrong or slower without it, and treats the quota as a ceiling;
    - replays a trimmed card by its name;
    - checks every deliverable against a passed or fixed card before it answers.
  - The generator gets matching rules for working, delegating, memory, trimming and its final answer. Its final answer names notes and does not paste them, and it is not memory.
  - The verifier:
    - is told its context is limited;
    - treats the workspace as the record and does not redo the task;
    - drops staged entries that are not worth keeping;
    - re-checks instead of recalling.
- **Three briefings** (`task_prompt`, `verifier_task_prompt`, `resume_prompt`). Each gains a preamble and per-field reading guidance built from code truths:
  - a missing start file;
  - an ambiguous criterion, which counts as a claim;
  - a partial status and a cut summary;
  - a reworded duplicate entry, which gets through unless the verifier drops it;
  - a same-name relaunch, which keeps its finished children and counts again toward the agent limit;
  - a cut map that can hide the plan note;
  - running out of turns, which ends the run for good.

  Each briefing also gains an ordered checklist. All three stay at 1,142–1,160 tik.
- **`launch_tool_description`** gains:
  - why delegation saves context, since only the result card comes back;
  - when to delegate: by deliverable, with batches sized to what the root can read;
  - which agent receives what (only the generator gets the context);
  - card fields that must agree, because the verifier never sees the generator_prompt;
  - what failure and replay look like;
  - two bans: never ask for a transcript, never paste large excerpts.

  It keeps its four headings.
- **Compact leaves.** Four descriptions gained one nudge each: `launch_generator_prompt`, `remember_tool`, `note_path`, `write_note_text`. `note_path` also dropped the false "every file" claim (R-27). Two replies gained one nudge each: `remember_saved`, `remember_staged`. The shape leaves are byte-identical.
- **README `:68`.** The size figures are recomputed from measured `TokenEstimate.count` values with row 42's arithmetic.

## 3. The §4 snippet, as run

From the worktree root, `PYTHONPATH=$(pwd) python <scratchpad>/s6/snippet4.py` (the spec §4 text verbatim) at `77171eeb`:

```
root_system_prompt: estimate 2858, tiktoken 2470
generator_system_prompt: estimate 1747, tiktoken 1490
verifier_system_prompt: estimate 1434, tiktoken 1216
task_prompt: estimate 1349, tiktoken 1142
verifier_task_prompt: estimate 1373, tiktoken 1160
resume_prompt: estimate 1339, tiktoken 1151
launch_tool_description: estimate 1338, tiktoken 1123
```

The same snippet on `git archive origin/feat/infinite-memory-agent vidbyte` (7efceb55), exported to `<scratchpad>/s6/base`, printed the spec §8.5 baselines exactly: 2129/1829, 1503/1277, 1246/1059, 286/241, 294/251, 273/232, 495/416. `measure_seven.py` agrees with the HEAD figures, and its 23-description sums are est 4,577 and tik 3,905.

**Per-call load, measured** (`<scratchpad>/s6/percall.py`). It sums the actual schema leaves per role under the SPARSE preset, run on the base export and on HEAD.

| Role | Base | HEAD |
|---|---|---|
| Root | 1,829 + 0 + 3,438 = 5,267 | 2,470 + 0 + 4,247 = 6,717 |
| Resumed root | 1,829 + 232 + 3,438 = 5,499 | 2,470 + 1,151 + 4,247 = 7,868 |
| Generator | 1,277 + 241 + 3,438 = 4,956 | 1,490 + 1,142 + 4,247 = 6,879 |
| Verifier | 1,059 + 251 + 2,036 = 3,346 | 1,216 + 1,160 + 2,109 = 4,485 |

- Schema parts at HEAD: launch tool 1,123, eight `launch_*` 1,340, ten memory descriptions 1,784, `drop_entry` pair 325. The FULL preset's `edit_file` schema goes 607 → 637.
- The 24-description sums go est 4,950 → 5,915 and tik 4,219 → 5,028.
- All four roles stay under the spec §7 targets of 7,224 / 8,524 / 7,824 / 5,140. The conformance reviewer noted the resumed-root row was missing from S3's table; it is now in the body.

## 4. Gates (my run at `77171eeb`, logs in `<scratchpad>/s6/gates/`)

| Gate | Final line(s) |
|---|---|
| module | `131 passed in 0.88s` |
| pack | `244 passed in 4.56s` |
| lint | `S063 IMPROVED 4 -> 3 …` / `S064 RATCHETED: 4 known finding(s) …` / `SDK-LINT: PASS` |
| semgrep | `Ran 1 rule on 980 files: 0 findings.` (scratch venv, same arguments) |
| public API | `contracts/sdk-public-api.json is current at 9eca4a33ddb5ea1a21c07f840e556487a8770e19 (vidbyte-sdk 0.3.0, 644 exports).` |
| source | `SDK-LINT: PASS` (log line 182) / three inherited `FAILED tests/features/harness_threads/test_harness_threads_surface.py::…` / `3 failed, 6174 passed, 16 skipped in 93.09s (0:01:33)` / `CI failed: …python.exe -m pytest` |
| package | `No broken requirements found.` / `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |

`git status --short` was clean after the gates. The only untracked file was `pr-body.md`, which I was writing at the time. These results match the orchestrator's gate of record at `5f41a5f4`. I did not reproduce the three harness_threads failures at the base myself. The body cites the orchestrator's detached-worktree run (`3 failed, 6 passed`), and S3 reproduced the same three at `b140af69`.

## 5. Independent checks of the body's own claims

- **Quotes** (`<scratchpad>/s6/check_quotes.py`), 82 checks, `no problems`:
  - all 57 quotes in the stage-by-stage rule table, each matched in its named leaf at HEAD after D-9 normalization;
  - the four INV-19 rewords: each Before is in the base leaf and gone at HEAD, and each After is at HEAD;
  - eleven prose quotes.
- **Mermaid** (`<scratchpad>/s6/mmd/validate.mjs`, mermaid 10.9.1 with jsdom): the body's flowchart and both spec §5 diagrams parse after my edits. A deliberately broken block fails with a parse error, so the validator does reject bad input.
- **Test names**: every test the AC table cites exists on the branch (`--collect-only`). The parametrized counts are pins 49, headings 30, floors 14, formatted leaves 12, shape leaves 6, duplicates 7. The pack collects 244.
- **Docs-only claim**: `git diff --name-only 3825237d HEAD -- . ':!docs'` is empty.
- **Secrets**: the body contains no `@` and no key, token or password text.

## 6. Deviations recorded in the body

1. Root: #1113's "Remember only what will matter again, never progress chatter" is merged into the "The default is not to remember" paragraph, which keeps "never for progress chatter". "Keep a large plan in a note" now reads "keep the plan in that note". `:64` is reworded as outline 1.8 directs.
2. Outline 1.3's "do the smallest piece yourself" is stated once, in §When a call is refused.
3. Optional reply nudges for rows 33, 34 and 37 were not added. Row 36 got its nudge through R-19.
4. `launch_tool_description` keeps exactly four headings. R-15 suggests a fifth.
5. Rules added by review that the outlines did not list: R-6 (the turn limit, in resume), R-12 (the verifier fixes a goal miss inside the task), R-28 (search for a plan note the map does not show).
6. Spec §12.6 conflicts with D-1's checklist layering. Ruled under R-14: the layering stays.
7. Spec test-id counts are off: AC-4 says 46 pins (shipped 49: 22 kept + 27 new), and AC-13 says 31 heading ids (shipped 30, because `launch_tool_description` is counted once). The cause is R-21.
8. Spec §5 was corrected at S6. The code did not change.
9. The spec §6.2 proof cells for AC-11 and AC-12 keep their S3-time figures (2,812 est, "about 2,800"). §17 notes that they are history; the current figures are in the body.

The INV-19 list in the body has four #1113 rewords with before/after text: launch `:13` (R-1), root `:48` (R-5b), root `:58` (R-27) and note_path `:7` (R-27). No #1113 rule is dropped. The body also names S3's merge and the other spec-directed rewords.

## 7. Spec edits

- **Frontmatter.** `status: verified` → `pr-open`; `updated: 2026-10-16` → `2026-10-17`; `pr:` unchanged, with the "filled at S3 … finalized at S6" comment removed.
- **§5 flowchart.** Added `B → D[DelegationLimitsMiddleware]` and back, for the depth and batch-size refusal. Added `L → B` "generator failed: no verifier runs, verdict unchecked". The card edge now reads "summary, review, dropped and files capped, entry ids whole". The `launch_rejected_prompt` edge now names the tool's own batch checks.
- **§5 sequence diagram.** Added a Note for a failed generator. The card message now says which fields are capped.
- **§5 paragraph.** One added sentence states the three paths with code references: `launch.py:231`, `:238`, `:219`, `:243`, `:364-372`, `:156-180`; `delegation_limits.py:54,66`, which I read to confirm both refusals.
- **§17.** Row `r4 | 2026-10-17 | S6 PR | finalized for review: …`.

## 8. Final PR state

```
$ gh pr view https://github.com/cerredz/Vidbyte-SDK/pull/1176 --json title,isDraft,baseRefName,headRefName,url
{"baseRefName":"feat/infinite-memory-agent","headRefName":"feat/infinite-memory-prompts","headRefOid":"88a14bca1e86167d792b46deeddf8a28562b8ff0","isDraft":true,"title":"feat(prompts): InfiniteMemoryAgent prompts restate its principles at every stage; the seven behavior-shaping prompts exceed 1,100 tokens","url":"https://github.com/cerredz/Vidbyte-SDK/pull/1176"}

$ gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1176
no checks reported on the 'feat/infinite-memory-prompts' branch
(exit 1)
```

- The title has no `[WIP]`, the PR is still a draft, and the base is `feat/infinite-memory-agent`.
- No checks are reported because GitHub Actions are disabled repo-wide; the local gates are the gates of record.
- The remote body matches `pr-body.md` from line 2 onward.

## 9. Candidate field-guide lessons (not written to the field guide)

1. **A prompt sentence about what an agent receives, or what a capped view shows.**
   - Trigger: the sentence says who sees which part of a card, or what the map or the card lists.
   - Preferred action: trace it to the formatter, then write the bounded truth ("only the generator receives the context the card names"; "as many as fit").
   - Reason: R-1 was a Blocker that passed all 244 tests. R-2 and R-27 shipped the same false "every file" claim in three leaves of one call.
   - Quick check: `grep -rn "every file\|lists every\|context it names" vidbyte/prompts/prompts/infinite_memory` and compare with `launch.py:302-309` and `workspace.py:219-229`. This extends `prompt-families.md`'s "who sees which context" lesson to capped views.
   - PR #1176.
2. **Clearing a token floor.**
   - Trigger: a prompt is expanded to meet a size floor.
   - Preferred action: measure the asset with each restatement removed. If it falls under the floor, add a code-true rule instead of keeping the restatement.
   - Reason: `resume_prompt` met 1,100 tik only through two restatements (1,098 without them, R-6).
   - Quick check: the five-word duplicate-sentence test, plus a what-if measurement without the restating clauses.
   - PR #1176.
3. **Ambiguous criteria in a generator/verifier pair.**
   - Trigger: briefing text tells the generator to pick a reading of an unclear criterion.
   - Preferred action: make the chosen reading a claim the verifier tests, never the verifier's standard.
   - Reason: the verifier reads the generator's summary verbatim (`launch.py:309`), so a stated reading becomes the bar (R-4).
   - Quick check: `grep -n "judge against\|judges against" verifier_task_prompt.md task_prompt.md` is empty.
   - PR #1176.
4. **A new "only" or "never" rule in a prompt that carries kept text.**
   - Trigger: an exclusive rule is added to a system prompt that already holds #1113 permissions.
   - Preferred action: list every kept permission the rule would forbid, and fold them into it.
   - Reason: R-5. Root `:20` "read a file only to decide a card" contradicted the kept "read the named files for detail" and "make a small fix".
   - Quick check: grep the asset for each verb the new rule restricts.
   - PR #1176.
5. **The root's notes under SPARSE.**
   - Trigger: a prompt asks the root to re-read or keep a note.
   - Preferred action: say "the part you need".
   - Reason: SPARSE grants no `edit_file` (`vidbyte/lib/registries/infinite.py:36-37`), so the root's plan note is append-only and grows with every card (R-26).
   - Quick check: `grep -n "re-read" root_system_prompt.md resume_prompt.md`.
   - PR #1176.
6. **The turn limit for an InfiniteMemory root.**
   - Trigger: prompt text about turns, or about finishing.
   - Preferred action: state that running out of turns ends the run for good.
   - Reason: a `max_iterations` stop returns normally (`vidbyte/agents/runtime.py:2002-2005`), `infinite/runtime.py:101` journals `run_finished`, and `journal.py:89-90` refuses to resume.
   - Quick check: follow that call chain. The root system prompt still lacks the rule (R-18).
   - PR #1176.
7. **Phrase pins in a prompt test pack.**
   - Trigger: tests pin phrases by presence.
   - Preferred action: in review, read the whole sentence around each pin.
   - Reason: presence pins pass a negated rule, a rule in the wrong role, or a false code claim. R-1 passed; engineering mutants passed all 244 (R-23, R-24).
   - Quick check: a review lens reads each pinned sentence against the code.
   - PR #1176.
8. **Gates on a branch stacked on #1084.**
   - Trigger: running `run_ci.py --stage source` on a branch stacked on `feat/infinite-memory-agent`.
   - Preferred action: expect exactly the three `harness_threads` surface failures, and confirm them at the base in a detached worktree.
   - Reason: those tests diff against `git merge-base origin/main HEAD` and reject what #1084 adds.
   - Quick check: the same file at the base ends `3 failed, 6 passed`.
   - A related environment fact: the global semgrep 1.170.1 cannot start with global `mcp` 2.3.0, so run it from a venv with `mcp<2`.

## 10. Anything that looked wrong (not fixed; no source change)

These are all already recorded follow-ups, except that this run confirmed or located them precisely:

- `vidbyte/lib/constants/infinite.py:5`: the header says "about 105,000 tokens"; README `:68` says "near 107,000" (106,773). Not edited, per D-D/NG-6.
- `vidbyte/agents/infinite/README.md:58`: "one line per file with its token count and description". False once the map is cut; already false at the base.
- `vidbyte/prompts/prompts/infinite_memory/map_header.md:1`: "Each line below is one workspace file…" does not cover the closing "… and N more files" line. It is a shape leaf and cannot grow.
- `vidbyte/prompts/prompts/infinite_memory/verifier_task_prompt.md:51`: "the card lists every file you write". The files list is cut at the card cap (`launch.py:364-371`); this is practically unreachable.
- `vidbyte/prompts/prompts/infinite_memory/task_prompt.md:33`: "Treat them as established" also covers live root entries that no verifier reviewed (R-17).
- `docs/spec/infinite-memory-prompts/spec.md`: the AC-4 row says "46 ids" (49 shipped), the AC-13 row says "31 ids" (30 shipped), and the AC-11 proof cell holds S3 figures. These are spec rows I may not edit (R-21).
- `tests/features/infinite_memory_agent/test_infinite_memory_prompts.py:374`: the docstring says "six labels"; the code checks the heading plus seven labels (R-21; needs a grant).
- Spec §5 before S6: three paths differed from the code. Corrected in this stage; see §7.

## Commands run

- `git status --short`, `git log origin/feat/infinite-memory-agent..HEAD --oneline`, `git diff --stat|--numstat origin/feat/infinite-memory-agent...HEAD`, and the full diff of `vidbyte/` and the test-pack docs.
- `git archive --format=tar origin/feat/infinite-memory-agent vidbyte | tar -x -C <scratchpad>/s6/base`.
- `PYTHONPATH=$(pwd) python <scratchpad>/s6/snippet4.py` at HEAD and on the base export. `percall.py HEAD|base-7efceb55`, `leaves.py`, and `measure_seven.py` (outputs quoted above).
- `pytest --collect-only` on the module and the pack.
- `bash <scratchpad>/run_gates.sh <worktree> <scratchpad>/s6/gates` (§4).
- `python -I <scratchpad>/s6/check_quotes.py`; `node <scratchpad>/s6/mmd/validate.mjs pr-body.md spec.md neg.md`.
- Code read:
  - `vidbyte/agents/infinite/agent.py:60-130`, `infinite/runtime.py:75-125`, `launch.py:80-380`;
  - `memory.py` (schema lines), `vidbyte/lib/registries/infinite.py:20-50`, `vidbyte/middleware/builtins/delegation_limits.py:45-70`;
  - `vidbyte/lib/constants/infinite.py:1-8`, `vidbyte/agents/infinite/README.md:55-70`, `map_header.md`;
  - the three system prompts in full.
- `git commit -F` ×2, `git push origin feat/infinite-memory-prompts` (`77171eeb..4974e259`, `4974e259..88a14bca`).
- `gh pr edit --title … --body-file …`, `gh pr view --json …`, `gh pr checks`; a body round-trip comparison returned `True`.

`<scratchpad>` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7d03425b-8396-4738-89eb-c11a8a3fac1a/scratchpad`.
