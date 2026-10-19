# S4 · Findings verifier — infinite-memory-prompts

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-prompts` · branch `feat/infinite-memory-prompts` · HEAD `423ada84`. The diff reviewed is `origin/feat/infinite-memory-agent...c86005c2`. `git diff --stat c86005c2 HEAD -- vidbyte tests` is empty, so the commits after c86005c2 hold only docs. Output: `docs/spec/infinite-memory-prompts/review.md`. I wrote nothing else in the worktree, and `git status --short` was empty after every command. Scratch files are in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7d03425b-8396-4738-89eb-c11a8a3fac1a/scratchpad/s4-verifier/`.

## 1. Outcome

**Verdict: MERGEABLE AFTER FIXES.** There are 1 confirmed Blocker, 5 confirmed Majors and 20 Minors. Three findings are refuted, two are downgraded, and one confirmed Major is routed to follow-up because its fix is a test edit. Each Blocker or Major fix is a short text edit inside D-D. I applied all of them together, with the trivial Minors R-7 to R-10, to a `git archive` copy of the tree. On that copy the seven assets measure root 2,452, generator 1,490, verifier 1,216, task 1,142, verifier_task 1,149, resume 1,137 and launch 1,123 tiktoken. Every estimate is at least 1,000. Every pin, every heading and the digit, brace and newline rules hold. The 23-description sum is 3,906, and the feature pack passes 244.

## 2. Merge map (original IDs → merged IDs)

| Original | Lens | Proposed severity | Merged | Disposition |
|---|---|---|---|---|
| R-E2 | engineering | Major | **R-1** | CONFIRMED, raised to Blocker (it contradicts a field-guide lesson) |
| R-E8 | engineering | Minor | **R-2** | CONFIRMED, raised to Major (FR-10 is P0, and the field-guide lesson applies) |
| R-C2 | conformance | Major | **R-3** | CONFIRMED Major |
| R-E1 | engineering | Major | **R-4** | CONFIRMED Major |
| R-C1, R-E4 | conformance, engineering | Major, Major | **R-5** | CONFIRMED Major (same root cause: the "only" rule at root `:20` against the kept reading rules) |
| R-V1 (resume part), R-C6 (resume `:25` clause) | conventions, conformance | Major, Minor | **R-6** | CONFIRMED Major |
| R-V1 (verifier_task_prompt part) | conventions | Major | — | REFUTED (outline 5.1 and 5.3 ask for those sentences; the floor holds without the one restatement no outline asks for) |
| R-V1 (root `:54`, generator `:11` parts) | conventions | Major | — (root part → R-11, R-13) | REFUTED as repair items |
| R-E3 | engineering | Major | — (residue → R-14) | REFUTED as written |
| R-E5 | engineering | Major | R-7 | DOWNGRADED to Minor (trivial) |
| R-E9 | engineering | Minor | R-8 | Minor (trivial) |
| R-E12, R-V6 | engineering, conventions | Minor, Minor | R-9 | Minor (trivial) |
| R-C5 | conformance | Minor | R-10 | Minor (trivial) |
| R-C4, R-V4 (root `:54` bar) | conformance, conventions | Minor, Minor | R-11 | Minor (trivial), with a corrected fix |
| R-C7 | conformance | Minor | R-12 | Minor (trivial, optional) |
| R-C6 (the rest), R-V1 residue | conformance, conventions | Minor, — | R-13 | Minor follow-up |
| R-V3, R-E3 residue | conventions, engineering | Minor, — | R-14 | Minor follow-up |
| R-V5 | conventions | Minor | R-15 | Minor follow-up |
| R-V7, R-V4 (terms) | conventions | Minor | R-16 | Minor follow-up |
| R-E10 | engineering | Minor | R-17 | Minor follow-up |
| R-E11 | engineering | Minor | R-18 | Minor follow-up (adds scope; interacts with R-6) |
| R-C3 | conformance | Minor | R-19 | Minor follow-up |
| R-V10, R-E13 | conventions, engineering | Minor, Minor | R-20 | Minor follow-up (PR body) |
| R-V8 | conventions | Minor | R-21 | Minor (trivial docs; the docstring needs a grant) |
| R-V9 | conventions | Minor | R-22 | Minor (trivial; needs a grant) |
| R-E6 | engineering | Major | R-23 | DOWNGRADED to Minor follow-up (needs a test change) |
| R-E7 | engineering | Minor | R-24 | Minor follow-up (needs a test change) |
| R-V2 | conventions | Major | R-25 | CONFIRMED fact, routed to follow-up (needs a test change; no spec ID contradicted) |
| — | verifier | — | R-26 | New Minor follow-up (plan-note growth under SPARSE) |

## 3. Verification of each Blocker and Major, with my own evidence

### R-1 (R-E2): launch_tool_description `:13` says the verifier sees the card's context. CONFIRMED, Blocker.
- **Code.** In `vidbyte/agents/infinite/launch.py:309`, `_verifier_message` returns `...VERIFIER_TASK_PROMPT).format(instructions=self.card.verifier_prompt, goal=self.card.goal, criteria=self.criteria, status=status.value, summary=summary or "-", staged=staged, files=files, quota=memory.quota())`. That call has no entries and no paths. Only `_task_message` (`:302`) formats `entries=pasted, paths=paths`.
- **Shipped text.** `:13` says "Both agents start fresh: they see their task card, the context it names, the workspace map, and the shared workspace, but not this conversation." The same schema says the opposite in `launch_context_description.md:11` ("Only the generator receives this context…") and `launch_verifier_prompt_description.md:7` ("The verifier does not receive the entries and paths named in context…"). So does root `:32`.
- **Provenance.** `git log -S "they see their task card, the context it names" origin/feat/infinite-memory-agent` → `7efceb55 fix: resolve review comments from PR #1084 (#1113)`. This is #1113 text, kept in the paragraph that S3 rewrote (row 7). INV-19 allows a reword when the text contradicts code truth, and FR-10 (P0) requires one.
- **Why Blocker.** The field guide's `prompt-families.md` "Do" line reads: "Verify each described behavior against the code, for example who sees which context and when a write takes effect." This defect is exactly that example, and the rubric classes a contradicted field-guide lesson as a Blocker. The other three texts mitigate the harm, but every root call and every generator call carries this contradiction, for every pair. Mutants show the pack cannot catch it (R-24).
- **Fix measured** (`whatif.py R3_launch`): 1,139 → 1,149, all checks ok. The engineering alternative (`R3_eng`) measures 1,167, but it restates the Rules sentence of `launch_verifier_prompt_description` in the same schema, so I kept it only as an alternative.

### R-2 (R-E8): task_prompt `:41` says the map "lists every other file". CONFIRMED, raised from Minor to Major.
- **Code.** `workspace.py:219` returns the whole map only `if TokenEstimate.count(rendered) <= INFINITE_MAP_MAX_TOKENS`. Past that, `:225-229` keep the lines that fit and close with `INFINITE_MORE_FILES.format(count=…)`, which is `"… and {count} more files"` (`constants/infinite.py:135`). `INFINITE_MAP_MAX_TOKENS = 8_000` (`:71`).
- **Tier change.** I raised it because FR-10 is P0 and the field-guide lesson above applies. I stopped at Major because the sentence is false only past the cap, and in that state the map's own closing line contradicts it in front of the model. Step 1 of the checklist also searches the workspace.
- **Fix measured** (`M_task_map`): 1,136 → 1,142, ok.

### R-3 (R-C2): neither verifier asset says the verifier's context is limited. CONFIRMED, Major.
- **Command.** `grep -n -i -o "[^.]*\(context\|scarce\|limited\|lean\)[^.]*\." verifier_system_prompt.md verifier_task_prompt.md` → `verifier_system_prompt.md:25: … stand alone for a reader with no context …` and `verifier_task_prompt.md:1: This message stays in your context for the whole check…`. Neither hit states that the context is scarce.
- **Spec.** INV-1 reads "Every asset a model reads as instruction (the seven) states, for its stage, that the model's own context is the scarce resource and names the concrete behavior that protects it." The other five assets do state it (gen `:11` "Your context is limited too", among others).
- **Severity reason.** It is Major, not Blocker, because both assets already name the behavior. It is not Minor, because a principle invariant derived from the user's weighted words ("scarce resource at every stage") fails as written, and the user's planned goal-continuation check will test exactly these invariants.
- **Fix measured** (`R4_verifier_ctx`): verifier 1,209 → 1,216, verifier_task 1,135 → 1,141, ok.

### R-4 (R-E1): the generator's chosen reading becomes the verifier's standard. CONFIRMED, Major.
- **Shipped text.** vtask `:35` (new): "When it says it chose one reading of an unclear criterion, judge against that reading if the goal supports it." task `:17` (new): "…take the reading the goal supports and state it in your final answer, so the verifier judges against it." In the same message, vtask `:25` says "Check each criterion as written here, not as the generator restated it", `:61` says "so its claims do not set your standard", and `:17` says "Use it to settle what a criterion means when its wording is unclear".
- **Code path.** The generator's reply is capped and passed as `summary` (`launch.py:218`, `:309`), so the verifier reads the stated reading. Nothing else in the code arbitrates which reading applies.
- **Spec.** Outline 4.2 says only "the reply must say 'whether it is met and where the evidence is'". Outline 5.1 says "the generator's summary is the claim list", and outline 5 has no item about the chosen reading. INV-6 says "the generator's reply is a set of claims". Neither sentence is required: `git log -S` traces them to `8660e374` (task) and `de8012e6` (vtask).
- **Failure, read literally.** Take an ambiguous criterion that the goal supports in two readings, with the generator stating the weaker one. Under `:35` the verifier judges by the weaker reading and passes, and the root counts the deliverable as settled (root `:81`). Under `:25` and `:61` it must not. One message gives both directions, which is the contradiction class the briefing names.
- **Fix measured** (`R2_reading`): task 1,136 → 1,136, vtask 1,135 → 1,143, ok. I rejected the engineering wording ("decide the reading yourself from the goal and your instructions") because it restates vtask `:17` inside the same asset (NFR-4). Measured, it gives the same token counts (`R2_eng`: task 1,129, vtask 1,143).

### R-5 (R-C1 + R-E4): root `:20` "only" rule against the kept reading rules. CONFIRMED, Major.
- **Shipped text.** `:20` (new, outline 1.3): "Read a file yourself only to decide what a card should say, never to do the work." It conflicts with kept text: `:48` "long text ends with a cut marker, so read the named files for detail"; `:52` "read the files behind anything your final answer depends on … or make a small fix yourself"; `:20` "Do yourself only what costs less context than a task card, such as … a small fix, and the final answer"; `:83` "built from the result cards and the files they name". It also conflicts with `:3` (new): "any other reading is work for a pair".
- **Provenance.** `git log -S` traces `:48` and `:52` to `7efceb55` (#1113), so INV-19 keeps their rules.
- **Matrix cell P1 × parent reading a card.** The cell names "root §Reading result cards", and no sentence in `:42-54` protects the context. The only "small ranges" rule is in §Working within history trimming (`:73`).
- **Adjudication.** Both lenses describe one root cause, so I merged them. Conformance's fix leaves the small-fix permission in conflict with the "only" rule. Engineering's change to `:3` ("belongs to a pair") changes no meaning. My fix lists the three reads the kept text needs at `:20`, puts the "only that part" rule where cards are read (`:48`, which fills the matrix cell), and names small fixes at `:3`. Pinned phrases checked: "more text into your context than its result card" (`:20`, the sentence before the edit) and "a card is not memory" (`:54`) are both untouched.
- **Fix measured** (`R1_root`, three edits): 2,424 → 2,452, ok, under the 2,600 review ceiling.

### R-6 (R-V1, resume part): the floor is met only through restatement. CONFIRMED, Major.
- **Measurement.** `PYTHONPATH=$(pwd) python …/s4-verifier/whatif.py R5_resume_drop_only` → `resume_prompt: est 1310 -> 1280, tik 1123 -> 1098 (-25); checks: ['UNDER FLOOR/BASELINE']`.
- **Restatement 1.** "An interrupted name is not finished, so launching it replays nothing." (`:25`) states the same fact as the kept pin at `:21`, "the same name runs a pair from scratch". It also clashes with the next sentence, under which the same-name relaunch's generator "gets their recorded cards instead of running them again", so something is replayed. Outline 6.3 reads "'the same name runs a pair from scratch' (keep; an interrupted name is not finished, so it does not replay)". The parenthesis explains why the kept phrase is true; it does not ask for a second sentence.
- **Restatement 2.** ", so relaunch only what the deliverables still need" (`:25`) is the third statement of `:21` "Launch them again if their work is still needed" (outline 6.3) and `:31` "Relaunch the interrupted work that still matters" (outline 6.4 checklist). Conformance R-C6 also flagged it as asked for by no outline.
- **Rules broken.** EC-11 names this exact failure, NFR-4 is P0, D-F says "never from repetition", and §14 says "any asset that cannot reach its floor without repeating a rule" means stop and ask first.
- **Replacement rule, verified in code.** `vidbyte/agents/runtime.py:2002-2005` returns `_stopped_result("Agent runtime stopped after reaching max_iterations.", stop_reason=MAX_ITERATIONS)`, and `:371-378` `return await self._finish_result(stop_result, state)`. So the loop returns normally. `vidbyte/agents/infinite/runtime.py:101` then runs `journal.finish(...)` ("The loop returned, so record the run as finished"), and `journal.py:89-90` raises "Run … already finished, so it cannot be resumed". The root sees `- max_iterations: {n}/{limit}` (`runtime.py:1649-1650`), which `_build_system_string` places in the system string (`:1631`).
- **Fix measured** (`R5_resume_turns`): 1,123 → 1,137, ok.
- **Alternative.** `R5_resume_quota` measures 1,132, ok. It rests on a fresh `InfiniteAgentMemory` per run (`infinite/runtime.py:83`) with `accepted = 0` and `created = 0` (`memory.py:51-52`). Use it if R-18 also puts the turn rule in the root prompt.
- **Wording check.** My first replacement wording ended "answer with what is met and what is missing", which restated step 6's own "say what is missing and why". I reworded it to "give your final answer before they run out".

## 4. Refutations and downgrades: the evidence

- **R-V1, verifier_task_prompt part.** Outline 5.1 reads "Preamble — 'nothing below has been checked yet'; the generator's summary is the claim list (P6)". Outline 5.3 reads "Staged entries — every one is reviewed; drop by key exactly as listed". `whatif2.py vtask_conventions_claim` (delete `:1` and `:43`) → `1135 -> 1085 UNDER FLOOR`, which shows the review's fix breaks the floor. `vtask_within_only` (remove the only restatement no outline asks for, the `:25` clause "Only the evidence decides: a criterion is not met because the answer says so") → `1135 -> 1121 ok`, so the floor does not depend on repetition.
- **R-V1, root and generator parts.** Outline 1.6 asks for "keep progress and status in the plan note", and outline 1.8 keeps the #1113 sentences. Root is far above the floor (2,424). Outline 2.2 reads "'read files in small ranges' and only what the task needs", which asks for both statements.
- **R-E3.** Outlines 2.2, 2.7, 4.6, 5.6 and 6.4 and D-1 ("the moment-of-use checklist lives in the briefing template for that stage") design the standing-rule-plus-checklist pairs. The proposed deletion on the system-prompt side removes the pinned phrase `"check each criterion before you reply"`, which `PINNED_PHRASES["generator_system_prompt"]` lists as new, and ver `:9`, which is #1113 text. The cross-asset copies that no outline asks for are small: `whatif.py M_task_deleg` → task `1136 -> 1117 ok`. Vtask without step 1 and the `:25` clause falls to 1,097 (`M_vtask_restate`). Step 1 follows D-1's pattern and now anchors R-4, so I keep it.
- **R-E5.** gen `:29` states the pinned rule "The default is not to remember: stage an entry only when a later agent would be wrong or slower without it". Outline 2.7 reads "stage the few entries a later agent needs before you reply". The flaw is a presupposition, not a broken rule, so it becomes a trivial Minor (`M_gen_ifany`: 1,478 → 1,482, ok).
- **R-E6.** I scanned all 40 leaves for spelled-out numbers. The only hits are structural: "two fresh agents", "two kinds", "two conflicting versions", "one …". No asset tells the verifier to write the verdict inline (ver `:48-54`: "exactly one line, and nothing after it", "at the very end"). AC-5 defines its proof as the digit test. The product text is sound; the test-plan claim is overstated, and that becomes R-23.
- **R-V2.** `grep -n` gives `165:def _is_terminal`, `172:def sentences`, `180: … _is_terminal(stripped, index)`. AGENTS.md §1 applies to new code. The fix is a test edit, and the briefing routes test edits that contradict no spec ID to follow-up. It is real; the orchestrator may grant it as a mechanical edit that changes no behavior.

## 5. Disagreements between reviewers that I settled

1. **"Floor reached only by repeats."** Conventions applied it to resume and verifier_task; engineering to task, launch and verifier_task (cross-asset); conformance called it spec-level. I applied the briefing's test: within one asset, is the restatement asked for by the §12.3.1 outline? Resume fails the test: its two restatements are asked for by no outline, and the asset is 1,098 without them. Verifier_task passes: its restatements are asked for by outlines 5.1 and 5.3, and it is 1,121 without its one unrequested clause. Engineering's cross-asset arithmetic counts the D-1 checklist layering as repetition, and the outlines require that layering. The leftover tension between spec §12.6 ("the briefings must not repeat what the system prompts now state") and D-1 with outlines 4.6, 5.6 and 6.4 needs an orchestrator ruling (R-14). It is not a repair item.
2. **Root contradiction (R-C1 vs R-E4).** These are one root cause, merged into R-5. Neither proposed fix closed every conflict, so I wrote a combined fix (see §3).
3. **R-E2 vs the conformance "VERIFIED CLAIMS".** Conformance checked the new code claims in this asset but not the kept sentence. Engineering found it. The field guide's own example ("who sees which context") settles the severity.
4. **R-C4's fix vs outline 1.6.** Conformance's replacement for root `:54` drops "a decision that a later pair would be wrong without is one decision entry", which outline 1.6 asks for. My R-11 wording keeps it, adds the ban, and aligns the bar with `:60` (R-V4). Measured with `whatif3.py M_root54_v2`: +20, ok.
5. **Engineering's R-E1 wording vs NFR-4.** The proposal "decide the reading yourself from the goal" restates vtask `:17` inside the same asset. I replaced it with a sentence that adds a rule instead ("that choice is a claim too, so name in your review the reading you judged by").
6. **R-V3 (drop root `:38` and the second sentence of `:31`).** Outline 1.5 asks for root `:38`. Launch `:7` serves generators, which never read root `:38`. So the duplication is a cost of the D-1 design, not a defect for repair (R-14).

## 6. Blind spots none of the three lenses covered

- **Fixes that break other requirements.** The conventions fix for verifier_task (R-V1) drops the asset below the floor (1,085). The engineering fix for R-E3 deletes a pinned phrase and #1113 text. The engineering wordings for R-E1 and R-E2 create an NFR-4 restatement and an outline-7.3 duplicate. The conformance fix for R-C4 drops an outline-1.6 rule. All of these are recorded in review.md, so the repair agent does not apply them.
- **R-26 [verifier]: plan-note growth.** The default preset is SPARSE (`vidbyte/agents/infinite/settings.py:68`), and SPARSE grants only remember and write_note (`vidbyte/lib/registries/infinite.py:36-37`). The root therefore cannot edit its plan note, only append to it (note_path: "write_note appends to an existing file"). This PR adds per-card progress appends (root `:13`, `:54`; resume `:30`, `:32`) and whole-note re-reads (root `:16`, `:73`; resume `:29`). The note grows with every card, and every re-read costs more of the root's context. Root `:73` "read files in small ranges" mitigates it. Minor follow-up; the +5 fix is measured in `whatif3.py M_plan_note_read`.
- **Restatement 1 in R-6 also conflicts with the next sentence.** "replays nothing" sits against "gets their recorded cards instead of running them again", which is a second reason to delete it.

## 7. Combined fixes on an exported copy (independent of the worktree)

```
git archive --format=tar HEAD vidbyte tests contracts pyproject.toml | tar -x -C <scratch>/s4-verifier/copy
PYTHONPATH=<worktree> python <scratch>/s4-verifier/apply_to_copy.py <copy> ALL_MAJOR M_task_map M_gen_ifany M_gen_note M_note_path M_launch_dup
cd <copy> && PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider
→ 244 passed in 5.58s
seven (est, tik): root 2843 2452 · generator 1747 1490 · verifier 1434 1216 · task 1349 1142 · verifier_task 1361 1149 · resume 1323 1137 · launch 1338 1123
```
The first export left out `contracts/`. That gave `1 failed, 243 passed`, with `FileNotFoundError … contracts\sdk-public-api.json` in `test_public_names_import_from_every_documented_path`. The cause was the export, not a text change, and the run passed once `contracts/` was included.

## 8. Commands run, with their final lines

- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_prompts.py -q -p no:cacheprovider` → `131 passed in 1.11s`
- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` → `244 passed in 4.45s`
- `… --collect-only | grep -c test_pinned_phrase_is_present_in_its_leaf` → `49`; `… | grep -c test_every_base_heading_survives_in_order` → `30`
- `python <scratch>/measure_seven.py <worktree>` → root 11248/2812/2424 … launch 5418/1355/1139; `23-description per-leaf sums (23 leaves): est 4586  tik 3913`
- `git diff --stat c86005c2 HEAD -- vidbyte tests` → empty; `git diff --stat origin/feat/infinite-memory-agent...c86005c2 -- vidbyte` → 13 files: 12 assets plus `vidbyte/agents/infinite/README.md`
- `git log --oneline -S "<sentence>" origin/feat/infinite-memory-agent -- <asset>` → `7efceb55` for launch `:13`, root `:48` and root `:52`; `git log -S` on c86005c2 → `8660e374` (task `:17`), `de8012e6` (vtask `:35`)
- `PYTHONPATH=$(pwd) python <scratch>/s4-verifier/whatif.py all`, `whatif2.py …`, `whatif3.py …` → the measurements quoted above
- Code reads: `launch.py:120-160`, `:210-320`; `agent.py:60-130`; `infinite/runtime.py:80-120`; `journal.py:80-130`; `memory.py:30-80`, `:182`, `:215`; `agents/runtime.py:366-380`, `:1625-1665`, `:1995-2010`; `workspace.py:205-235`; `tools/toolsets/infinite.py:40-52`; `lib/registries/infinite.py:25-50`; `constants/infinite.py` (`:71`, `:83`, `:135`).
- Docs read (all in the allowed set): request.md, spec.md r4 (all), the three S4 lens reports, the test module (all), FEATURE.md `:17-21`, pack README `:26-34`, test-plan.md (grep), field guide `init.md` and `prompt-families.md`, house-style.md, report-formats.md.

## 9. Notes for S6 (PR body), recorded, not findings

- R-1 and R-5 reword two #1113 sentences (launch `:13`, root `:48`). Name both under INV-19.
- Conformance found the resumed-root per-call row (5,499 → 7,818) missing from the S3 report. §12.5 requires all four §7 rows in the PR body.
- Spec §5 diagrams differ from the code in three places: the failed-generator branch, `entries` uncapped, and depth and parallel refusals that come from `DelegationLimitsMiddleware`. These are diagram notes only.
- Follow-ups for the PR body: R-20 (README `:68` omits the briefing; `constants/infinite.py:5` "about 105,000" drift), R-14 (§12.6 vs D-1 ruling), R-23, R-24 and R-25 (test-pack follow-ups), and the conflict note for feat/infinite-memory-events.
