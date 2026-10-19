LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — every pin, floor, bound, heading and #1113 rule holds and 80 of the 81 matrix cells are carried, but the root prompt's card-reading stage tells the root to read files while a new rule says it never should (P1, the user's main point), and the two verifier assets never state that the verifier's context is scarce (INV-1 "every").

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)

- No #1113 rule was dropped. A sentence-by-sentence diff of the 12 changed assets against base (`sentence_diff.py`) finds 29 base clauses that are no longer verbatim. Each one is extended or reworded with its rule kept. Examples: root `:8` "keep a large plan in a note" became `:11` "keep the plan in that note, where it survives trimming and a resume"; root `:55` "Remember only what will matter again, never progress chatter" became `:60` "...save one only when a later agent would be wrong or slower without it, and never for progress chatter"; root `:64` was reworded exactly as outline 1.8 directs. All 29 review-only keep nudges in §8.5 (2)–(4) are still present (`keep_nudges.py`: missing none).
- Every tested contract holds, inside the review thresholds. The 46 pins sit in the section the matrix names. The seven assets measure 2,424 / 1,478 / 1,209 / 1,136 / 1,135 / 1,123 / 1,139 tiktoken, so the four expanded assets sit at the low end of their band. The 23-description sum grew by 2.9 % against a 10 % bound. The only reply that grew is `remember_saved_prompt`, from 25 to 32 tiktoken, and the shape leaves are byte-identical.
- The PR stays inside its scope. It changes 12 assets, README line 68, and three S2 test-pack files, and nothing else. No Python under `vidbyte/` changed. The test tree changed only in S2's `b719c400`, which added files and reworded the one README line that row 45 sanctions. `lint/`, `.semgrep/`, `pyproject.toml` and `contracts/` are untouched, and `python lint/run.py` ends `SDK-LINT: PASS`.
- The new claims about how the code behaves match the code. A failed generator gets no verifier and its card comes back `unchecked` (`launch.py:231`). A same-name relaunch keeps its finished children (`journal.finished_children(writer.key)`, `launch.py:217`). A relaunch counts again toward `max_agents` (`journal.py:122-124`). A drop reason is fixed text (`memory.py:101`). Saved entries are live before the card returns (`_commit` runs before `_finish`). The resume lists only the root's own children (`agent.py:118-119`).

FINDINGS (ranked, most severe first, max 15)

R-C1 [Major] [matrix P1 × Parent reading a card] vidbyte/prompts/prompts/infinite_memory/root_system_prompt.md:20 vs :48, :52 — The new "only" rule against reading files contradicts three kept sentences, and the card-reading section has no rule that protects the context
  Evidence:
  - `:20` (new) says: "Read a file yourself only to decide what a card should say, never to do the work."
  - `:48` (kept) says: "long text ends with a cut marker, so read the named files for detail."
  - `:52` (kept) says: "Accept passed and fixed work, and read the files behind anything your final answer depends on."
  - `:83` says the answer is "built from the result cards and the files they name".
  - The matrix cell P1 × "Parent reading a card" names "root §Reading result cards". No sentence in `:42-54` says the root's context is scarce or that it should read in small ranges. "read files in small ranges" appears only at `:73`, in §Working within history trimming.
  Failure:
  - The root gets a batch of cards whose summaries end in " … [cut]". Following `:48`, it reads each named file. A note may be up to `max_file_tokens` (100,000), which is more than the 90,000 history cap, so a whole-file read is dropped whole after it has been paid for.
  - A model that follows `:20` instead accepts the cut summary without checking. Either way, the same asset gives two orders that cannot both be obeyed, at the stage where the main agent spends the most context. This is the user's main point: "train main agent context window as as a scarce resource at every stage".
  Smallest fix: reword without dropping anything (INV-19 allows a reword).
  - Change `:20` to: "Read a file yourself only to decide what a card should say or to confirm what your final answer depends on, and then only the part you need; never to do the work."
  - Change `:48`'s clause to: "so read only the part of a named file you need, with read_lines, or launch a pair to condense it."
  - After the edit, re-run the INV-15 (e) duplicate check and the §4 floor.
  Spec IDs: INV-1, G-1, matrix P1 × Parent reading a card, NFR-4, outline 1.3 vs INV-19 (#1113 `:43`/`:47`)

R-C2 [Major] [invariant INV-1] vidbyte/prompts/prompts/infinite_memory/verifier_system_prompt.md:11, verifier_task_prompt.md:51 — Neither verifier asset says that the verifier's own context is limited
  Evidence:
  - Ran `grep -o -i "[^.]*\(context\|scarce\|limited\|lean\)[^.]*\."` over the seven assets.
  - In `verifier_system_prompt` the only hit is ":25 ... does it stand alone for a reader with no context".
  - In `verifier_task_prompt` the only hit is ":1 This message stays in your context for the whole check".
  - The other five assets each state it: generator `:11` "Your context is limited too"; task `:41` "every file you read fills your context"; root `:3` "the run's scarcest resource"; resume `:1` "keep your context as lean as before"; launch `:3`/`:7`.
  - The verifier assets name only the behavior: ver `:11` "reading only what each check needs"; vtask `:51` "Read only the parts each check needs".
  Failure:
  - INV-1 says "Every asset a model reads as instruction (the seven) states, for its stage, that the model's own context is the scarce resource and names the concrete behavior that protects it". The rule holds for 5 of the 7.
  - The verifier is the role that reads the most files. It is told what to do but never why. With no reason given, a model is more likely to read a whole file "to be sure", be trimmed, and lose the evidence its review needs.
  - Rated Major, not Blocker, because both assets do name the behavior that protects the context.
  Smallest fix: prefix ver `:11` step 3 with "Your context is limited too:", which mirrors generator `:11` and costs about 7 tiktoken tokens. Optionally do the same in vtask `:51`. Neither edit duplicates a sentence.
  Spec IDs: INV-1, matrix P1 × Verifier checking, request §D "scarce resource at every stage"

R-C3 [Minor] [matrix P2 × Memory staging / deviation 3] vidbyte/prompts/prompts/infinite_memory/remember_staged_prompt.md:1 — The reply that children see after every `remember` call carries no sparse-memory nudge; the D-C example nudge went only to the reply that only the root sees
  Evidence:
  - The file is unchanged: "Staged as {key}. It is saved to memory only when this pair's verifier gives a verdict, and the verifier may drop it first."
  - INV-2 lists `remember_staged_prompt` among the assets that "state that the default is not to remember". The matrix cell P2 × Memory staging names it.
  - `remember_saved_prompt`, which gained "Keep anything longer in a note.", reaches only the root, whose saves are live (`remember_tool_description` "How it behaves").
  - Deviation 3's reason, "'one idea per entry' is already on remember_text", is true.
  Failure: generators and verifiers do almost all of the staging in a run that lasts days, and after each staged entry they get a reply with no reinforcement. The prompt at the moment of the call (`remember_tool_description`, "The default is not to remember") does cover the decision itself, which is why this is rated Minor.
  Smallest fix: append one sentence of 13 tiktoken tokens, which keeps the reply at 42 against a bound of 80: "Stage only what a later agent would be wrong or slower without." This is within FR-7's "≤ 1 nudge"; the placeholder and the trailing-newline rule do not change, and the `template_regex` pins track it.
  Spec IDs: INV-2, FR-7, outline 36, matrix P2 × Memory staging, request §D "sparse and infrequent"

R-C4 [Minor] [outline 1.6 / EC-10] vidbyte/prompts/prompts/infinite_memory/root_system_prompt.md:54 — The memory rule fires on every card, and outline 1.6's explicit ban is missing
  Evidence:
  - `:54` says: "...so when you read a card, put what a later pair needs from it into one entry or your plan note. Track status and progress in the plan note..."
  - Outline 1.6 and EC-10's guard column both require "never save a card's status or progress" in root §Reading result cards. In the shipped text that phrase exists only in `resume_prompt:32`.
  - Nothing in `:54` says that the card's "Entries saved" ids already hold what the pair learned.
  Failure: the root reads a card listing "#12, #13" and saves a reworded summary of #12. A reworded copy is not refused (`verifier_task_prompt:43` says so). The root agent lives for the whole run, so each such save spends one of its lifetime `remember` calls on a duplicate, and the gate here is the weaker "needs" rather than "wrong or slower without it".
  Smallest fix: change `:54` to "...put what a later pair needs from it into your plan note, and save an entry only when the card's saved entries do not already hold it. Never save a card's status or progress as an entry." This also removes the "Track status and progress in the plan note" restatement noted in R-C6.
  Spec IDs: outline 1.6, EC-10, INV-2

R-C5 [Minor] [outline 7.3 / FR-5] vidbyte/prompts/prompts/infinite_memory/launch_tool_description.md:13 — The tool description repeats the field-level nudges, and the repeat is paid on every root and generator call
  Evidence:
  - `:13` says: "Name in the card only the entries, paths, and tools the pair needs, since each one fills its context before it starts."
  - `launch_context_description` says: "Choose only what the task needs, since every pasted entry and listed file costs the generator attention".
  - `launch_tools_description` says: "only when the work needs it, because every tool the pair holds adds its description to the pair's context on every call".
  - Outline 7.3 requires "each field is described on its parameter (no duplication of the eight field descriptions)", and FR-5 says "without duplicating the tool description".
  Failure: the same rule is sent three times in one schema on every root and generator call, about 26 tiktoken each time. That is token cost with no behavior gain, in an asset that rides in every call (§7 table).
  Smallest fix: delete the sentence. The asset falls to about 1,113 tiktoken and 1,325 estimate, which still clears both floors; re-run the §4 snippet to confirm.
  Spec IDs: outline 7.3, FR-5, NFR-1

R-C6 [Minor] [NFR-4] root_system_prompt.md:13/:54/:73, :52/:73/:81; resume_prompt.md:21/:25/:31; verifier_task_prompt.md:1/:29; task_prompt.md:13/:17/:65 — Several rules are stated two or three times within one asset, in different words
  Evidence:
  - Progress goes in the plan note: root `:13` "Record in the plan note which deliverables each card settles", `:54` "Track status and progress in the plan note", and `:73` "Keep your plan and progress in a note of your own".
  - Check deliverables before finishing: root `:73` "re-read the deliverables in your plan note", `:81` "check each deliverable against the cards", and `:52` "A failed or unchecked card alone never settles a deliverable" (which `:81` repeats as "needs a passed or fixed card").
  - Relaunch only if needed: resume `:21` "Launch them again if their work is still needed", `:25` "relaunch only what the deliverables still need", and `:31` "Relaunch the interrupted work that still matters".
  - The answer is claims: vtask `:1` "The generator's report is a set of claims" and `:29` "Treat the answer as claims to check".
  - Report evidence per criterion: task `:13`, `:17` and `:65`.
  Failure:
  - INV-15 (e) cannot catch these, because they are reworded. NFR-4 says "no sentence repeats a rule already stated in the same asset". The briefing's standard for the coming goal-continuation check is one statement per rule per asset.
  - Most of these are required by the spec itself: outlines 1.6, 1.8 and 1.10 each ask for one, and D-1's checklist re-lists the per-section guidance. They are therefore spec-level redundancy, not implementer drift. Only root `:13`'s sentence and resume `:25`'s last clause were not asked for by an outline.
  Smallest fix: none is required for merge. Drop root `:13`'s second sentence and resume `:25`'s final clause; R-C4's fix removes the `:54` restatement.
  Spec IDs: NFR-4, A-7, D-F

R-C7 [Minor] [weighted word "fix anything that it finds"] vidbyte/prompts/prompts/infinite_memory/verifier_task_prompt.md:17 — When the verifier finds that the work misses the goal, the new sentence tells it to report the problem but not to fix it
  Evidence: `:17` (new) says: "When the work meets every criterion yet plainly misses the goal, say so in your review; the criteria still decide the verdict."
  Failure: a verifier that finds the miss writes it up and gives `VERDICT: passed`. Nothing in the asset tells it to repair the miss even when the repair is small and inside the task. The user's words are "the verifier subagent will run after the generator and fix anything that it finds", and ver `:19` says "Fix what falls short directly".
  Smallest fix: "...say so in your review, and fix it when the fix stays inside the task; the criteria still decide the verdict."
  Spec IDs: INV-6, request §A.4 / §D

VERIFIED CLAIMS:

Claims checked:
- Spec §4 / AC-1, run as written: held. The output has seven lines, every estimate is ≥ 1,000 (minimum 1,310) and every tiktoken count is ≥ 1,100 (minimum 1,123).
- Briefing and S3 figures (chars / estimate / tiktoken for the seven; 23-description sums 4,586 / 3,913; 24-description estimate sum 5,941): held exactly (`measure_seven.py`, `readme_figures.py`).
- AC-11 / INV-20 (README `:68`): held.
  - Root estimate 2,812 rounds to about 2,800.
  - The 24-description estimate sum 5,941 rounds to about 5,900.
  - 90,000 + 2,812 + 5,941 + 8,000 = 106,753, which rounds to near 107,000.
  - `vidbyte/prompts/README.md:229-250` is still true, so leaving it unchanged was correct.
  - `constants/infinite.py:5` still says "about 105,000"; that drift is a follow-up under NG-6.
- S3 "131 passed / 244 passed / SDK-LINT: PASS": held (I re-ran all three).
- §8.4 budget, §12.3 "no file outside", and §14 "Never": held.
  - There is one new file, the S2 test module; no file was created under `vidbyte/`.
  - No Python under `vidbyte/` changed, and `lint/baseline.json` and the test tree are clean after S2 (`git diff --stat f4cad411 c86005c2 -- tests/` is empty).
  - The only removed line in `tests/` is the pack README line 7, which row 45 sanctions.
- INV-19 and deviation 1 (#1113 kept): held, per `sentence_diff.py` as described above. Deviation 1 is necessary and minimal.
- Deviation 2 (outline 1.3's fallback stated once, in §When a call is refused): held. `:77` says "do the work yourself at a depth or agent limit".
- Deviation 4: held. `launch_tool_description` keeps exactly its four headings, which D-5 allows.
- Deviation 3 (rows 33, 34, 36, 37), checked row by row:
  - Rows 33, 34 and 37: allowed. FR-7 and the outlines say "≤ 1 nudge", and the reasons given hold. `launch_rejected` already ends "or do the work yourself", and `memory_rejected` already ends "or move on if the content is not worth keeping".
  - Row 36: allowed by FR-7 but named in INV-2 and in the matrix (R-C3).
  - Row 32 (`replayed_label`, also optional): the S3 tick list files it under deviation 3, but the spec's §17 deviation 3 does not list it. Its base text already says the work was done, so there is no behavior gap. This is a record-keeping nit only.
- §8.5 "exactly one nudge each" (review) vs outlines 12, 23 and 24, which each ask for two: the implementation follows the outlines. `note_path_description` and `write_note_text_description` each went from 6 to 7 S025 sentences; base was already above field-guide 4–5 for 20 of 23. This is a spec-internal inconsistency, not a defect.
- S3 per-call loads: held. Root 6,695, generator 6,885 and verifier 4,461 match. The resumed-root row (1,829+232+3,438 = 5,499 → 2,424+1,123+4,271 = 7,818) is missing from the S3 report, and §12.5 requires the PR body to carry all four §7 rows.
- P8: held. Beyond the contract scan, a scan for code|test|commit|branch|build|function|script|debug|merge|diff|module finds only general uses ("test them against", "build on").
- Spec §5 compared with the code path: three divergences, all in the spec's diagram, none in the prompts.
  - The failed-generator branch (no verifier, `unchecked`) is drawn in neither diagram. The prompts state it: `launch_tool_description:15`, root `:46`.
  - "result_card formatted, each field capped": `entries` is not capped. Summary and review are capped at creation and dropped/files at `render` (`launch.py:364-372`).
  - Depth and parallel refusals come from `DelegationLimitsMiddleware` (`delegation_limits.py:54,66`), not from `launch_rejected_prompt`. The diagram shows only the latter.

Principle × stage matrix (spec §6.1). Each cell gives a quoted shipped sentence and its asset:line; ✗ marks a cell that is not carried.

| | Root planning | Card writing | Gen working | Gen final reply | Verifier checking | Staging/commit | Parent reads card | Resume | Trimming |
|---|---|---|---|---|---|---|---|---|---|
| P1 | root:20 "more text into your context than its result card"; launch:3 "costs it one card" | gen_prompt_desc "ask for exactly what you will need"; context_desc "Choose only what the task needs"; tools_desc "adds its description" | gen:11 "Your context is limited too"; task:61 "small reads" | gen:45 "name a note rather than paste" | ver:11 "reading only what each check needs"; vtask:51 (behavior only, R-C2) | remember_text "one short line"; write_note_tool "does not fit in a one-line memory entry" | ✗ root §Reading result cards: none; :48/:52 say read files (R-C1) | resume:1 "keep your context as lean as before" | root:73, gen:37, ver:31 "Read files in small ranges" |
| P2 | root:60 "The default is not to remember." | launch:13 "which findings deserve an entry, if any" | gen:29 "The default is not to remember"; task:55 "most tasks need few entries or none" | gen:52 "Your final answer is not memory" | ver:25 "only while it stays small, so drop what is not worth keeping" | remember_tool:7 "The default is not to remember"; remember_saved "Keep anything longer in a note."; remember_staged none (R-C3) | root:54 "A card is not memory." | resume:32 "never save a card's status or progress" | root:73 / gen:37 / ver:31 "Trimming is not a reason to remember" |
| P3 | root:11 "where it survives trimming and a resume" | gen_prompt_desc "which detail belongs in a note" | write_note_text "Append findings as you make them"; task:62 "Keep a note as you go" | gen:52 "stage the few entries ... before you reply" | ver:31 "keep your findings ... short and current" | note_saved "written now, not staged" | root:54 "only until trimming drops it" | resume:32 "so another interruption loses nothing" | all three trimming sections |
| P4 | root:20 "Delegate work that reads sources..." | root:26 "Neither can see this conversation or the cards"; launch:13 "write every card to stand on its own" | task:1 "your whole brief"; gen:19 "a complete brief" | — | vtask:1 "cannot be checked" unless filed | — | root:52 "a sharper brief or narrower scope" | resume:31 "the new pairs cannot see the earlier part of the run" | — |
| P5 | root:12 "only one result card per pair comes back to you" | gen_prompt_desc "never for a transcript of its steps" | gen:3 "it sees only your final answer" | gen:45 "Your parent reads only this" | ver:39 "cut to a fixed length, so lead with what matters" | — | root:44 "never its conversation"; result_card; replayed_label | resume:17 "every card you replay lands in your context" | root:73 "comes back when you launch its name again" |
| P6 | root:11 "outcomes another agent can check" | launch:13 "a requirement stated only there is never checked" | gen:13 "Check each criterion before you reply." | gen:52 "Report only what you did and checked" | ver:10 "Treat the answer as claims"; vtask:25 "counts as not met" | ver:25; drop_entry_tool "against the evidence" | root:52 "never settles a deliverable" | resume:17 "The verdict, not the status" | ver:31 "check again rather than recall it" |
| P7 | root:16 "the record of this run, not this conversation"; root:5 unattended | launch_name "its recorded card comes back instead" | gen:9 "instead of redoing it"; gen:3 "No one answers" | gen:49 Deliverables (file list kept; P7 reason absent, same behavior) | ver:15 "The workspace is the record" | note_saved "every agent can already read it" | root:50 "already done"; replayed_label | resume:33 "No one will answer during the run"; :25 same-name relaunch | root:73 replay by name; gen:37 "Your note is your record" |
| P8 | contract scan plus the extra scan above: clean in all 40 leaves | " | " | " | " | " | " | " | " |
| P9 | root:10 "List the deliverables." | launch_goal "the result rather than the steps"; done_criteria "another agent can confirm" | task:63 "close every gap you can" | gen:50 "state plainly what is not done" | ver:15 "count a claimed deliverable you cannot find as missing" | — | root:52, :81 "check each deliverable against the cards" | resume:30 "Compare the deliverables with the finished cards" | root:73 "re-read the deliverables in your plan note" |

§12.3.1 outlines: every rule in outlines 1–40 is stated, with three exceptions:
- Outline 1.6's explicit ban is missing (R-C4).
- Outline 7.3's no-duplication rule is broken (R-C5).
- Outline 36's optional nudge was not added (R-C3).

Rules that sit in a different section of the same asset (2.2 "write findings into your note" sits in §Working within history trimming; 3.1 "never pass what you did not check" sits in §Your final reply; 7.3 "checked before anything starts" sits in §Rules and refusals) are in their #1113 location, so this is not a behavior gap.

Weighted words in request §D:
- "every stage": held except R-C1.
- "sparse and infrequent": held; root, generator, task, verifier, verifier task and resume each state it. Exceptions: R-C3, R-C4.
- "scarce resource at every stage": held for the main agent (root:3), with the R-C1 caveat.
- "ruthlessly delegate": held (root:20, launch:7).
- "unattended, resumable": held (root:5, resume:33). The generator gained it as well (gen:3).
- "not just coding": held.
- "the verifier ... fix anything that it finds": held (ver:19, vtask:63), except R-C7.

COMMANDS RUN:
- `git diff --stat origin/feat/infinite-memory-agent...c86005c2` → `27 files changed, 2459 insertions(+), 50 deletions(-)`
- `git log --oneline c86005c2..HEAD; git diff --stat c86005c2 HEAD -- vidbyte tests` → `b59c62dc`, `3b8c3066` (docs only); no diff.
- `PYTHONPATH=$(pwd) python scratchpad/s4-conformance/snippet4.py` (spec §4 verbatim) → `root_system_prompt: estimate 2812, tiktoken 2424` … `launch_tool_description: estimate 1355, tiktoken 1139`
- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_prompts.py -q -p no:cacheprovider` → `131 passed in 0.96s`
- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` → `244 passed in 4.53s`
- `python lint/run.py` → `S064 RATCHETED: 4 known finding(s)` / `SDK-LINT: PASS`; `git status --short` empty afterwards.
- `git diff --stat origin/feat/infinite-memory-agent...c86005c2 -- lint/ .semgrep/ pyproject.toml contracts/` → empty
- `git log --oneline origin/feat/infinite-memory-agent..c86005c2 -- tests/` → `b719c400` only
- `git diff --stat f4cad411 c86005c2 -- tests/` → empty
- `git diff ... -- tests/ | grep '^-[^-]'` → only the pack README line 7.
- `git diff --name-only ... -- '*.py'` → only `tests/.../test_infinite_memory_prompts.py`
- `python -I scratchpad/s4-conformance/sentence_diff.py <wt>` → root 8, generator 7, verifier 2, task 2, verifier_task 3, resume 3, launch 1, gen_prompt_desc 2, remember_tool 1 base clauses not verbatim; each checked by hand: rule kept.
- `python scratchpad/measure_seven.py <wt>` → seven rows as above; `23-description per-leaf sums (23 leaves): est 4586  tik 3913`
- `python scratchpad/s4-conformance/readme_figures.py <wt>` → `24-description est sum: 5941`; `README arithmetic ...: 106753`
- `python scratchpad/s4-conformance/per_call.py <wt> origin/feat/infinite-memory-agent | c86005c2` → base 5267/5499/4956/3346; head 6695/7818/6885/4461; `remember_saved 32`
- `python scratchpad/s4-conformance/keep_nudges.py <wt>` → `keep nudges checked: 29; missing: none`
- `python scratchpad/s4-conformance/sentence_counts.py <wt>` → only note_path (6 → 7) and write_note_text (6 → 7) changed.
- `grep -n -i -o -w -E "code|tests?|commit|branch|build|function|script|debug|merge|diff|module|..." *.md` → 7 general-English hits only.
- `grep -o -i "[^.]*\(context\|scarce\|limited\|lean\)[^.]*\."` over the seven assets → see R-C2.
- Code reads: `launch.py:120-380`, `journal.py:93-124`, `agent.py:60-120`, `runtime.py:85-118`, `memory.py:101`, `delegation_limits.py:45-70`.

(Helper scripts live in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7d03425b-8396-4738-89eb-c11a8a3fac1a/scratchpad/s4-conformance/`; all of them only read.)
