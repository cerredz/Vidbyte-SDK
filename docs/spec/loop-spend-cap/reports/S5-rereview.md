LENS: conformance
VERDICT: SOUND — All nine S4 fixes hold against review.md and spec r4. The R-1 check sits exactly where row 28 puts it, and every repair mutant is killed. Uncapped runs, delegated runs included, are byte-identical to base. The only gaps left are two Minor spec and header wording points, and neither changes behavior.

Re-review of `git diff daad59fb eba8bf85` (the repair), with `git diff origin/main...eba8bf85` as the squash. HEAD `3f79f71b` differs from `eba8bf85` only in `docs/spec/loop-spend-cap/pipeline.md`. Base is `22993b5f`.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **R-1's check is placed and shaped exactly as row 28 says, and each part of it is load-bearing.** The order in `vidbyte/agents/jev/runtime.py:219-231` is:
  1. the `begin_delegated`/`require_accounted()` block;
  2. the `@intent a-reached-cap-starts-no-specialist` comment;
  3. `self._spend_cap_stop(iteration_count=0, tokens_used=None, contexts=())`;
  4. `return self.response.finished(spend_stop, self.usage.settle())`;
  5. only then, `specialist.agent.arun`.

  Five R-1 mutants are each killed by AC-33: removing the check, moving it before `begin_delegated`, `iteration_count=1`, `tokens_used=0`, and returning the raw stop without the run total. Do not move the check above the run-state block, and do not bypass `response.finished`.
- **The default path is unchanged, the delegated path included (INV-17, NFR-1).** Scrubbed dumps were taken of the reply, `JevAgent.response`, `get_usage()`, the runner call counts and the `rollup()` call counts. They are byte-identical at `22993b5f` and at the head for five uncapped JevAgent scenarios: delegated with no preset, delegated with `RUN_STATE_RELATION`, delegated with `CLARITY`, main path with `none` chosen, and main path with no specialist. The same holds for the S4 engineering probe's nine BaseAgent scenarios.
- **R-2 is a pure narrowing fix.** mypy gives 346 errors at both trees, with 0 new and 0 gone when keyed on (path, code, message, source line). The refusal outcomes and the `resolve()` call counts are identical at `daad59fb` and at the head across 10 chain shapes: priced, unpriced, missing provider, missing model, OpenRouter, fallback mixes, and neither part set.
- **The README and vocabulary sentences are true of the code** (rows 13 and 17, R-M1, R-M2, R-M4).
  - On a main-path cap stop, `after_run` runs, the output connector gets a SKIPPED receipt, the queued prompt is truncated, and the auto-handoff spends after the stop rollup.
  - On a delegated cap stop:
    - the specialist makes 0 calls;
    - `response.specialist == 'database'`, so the A-8 clause is true;
    - delivery is SKIPPED and the drain is truncated;
    - the rollup equals the run total, at 1.000×C.

FINDINGS (ranked, most severe first, max 15)
R-C1 [Minor] [snippet-and-diagram / INV-6 escape hunt] docs/spec/loop-spend-cap/spec.md:208 (and :603) — r4's Delegated segment claims the specialist's run stays "below Cₛ + Gₛ", but a specialist that drains queued prompts spends 3.2×C with no JevAgent check
  Evidence:
  - spec.md:208 reads "so this segment's measured spend is below `Cₛ + Gₛ ≤ C + Gₛ`".
  - spec.md:603 reads "A specialist must carry its own cap ≤ JevAgent's, which bounds the specialist's own run on its own ledger."
  - Probe `scratchpad/r3-rereview/probe_specialist_drain.py`, run at the head. Setup: JevAgent capped at C. Its specialist is capped at C and has 3 queued prompts. Each specialist reply costs 0.8×C.
  - Output: `specialist calls=4 jev stop_reason='final_response' queued_prompt_runs=3` / `JevAgent measured total = 3.201 x C (Delegated-row bound Cs+Gs = 1.8 x C)`.
  - The specialist's 3rd and 4th replies start after JevAgent's measured spend has reached C. No check stops them, because each drained reply resets the specialist's own ledger (INV-11, `base.py:1195-1218`).
  Failure: a capped JevAgent and a specialist with queued prompts (from `enqueue_prompts`, or from the opt-in `RunPromptsSequentiallyTool`) give a reply that ends `final_response` at 3.2×C. INV-6's segment table does not list this escape. It follows from two accepted rules, Q-9/EC-41 (each drained prompt has its own cap) and the specialist's own cap. But spec :208 and :603 state a per-run bound that does not hold here. §9.2 rule 8 then reads as if a specialist cap at or below C were sufficient. The same per-reply caveat applies to the specialist's own End-of-run segment (EC-36). That is smaller, and it is also unstated.
  Smallest fix: docs only, and a stated limitation per the briefing's scope rule.
  - In spec :208, change "below `Cₛ + Gₛ`" to "below `Cₛ + Gₛ` per specialist reply. Queued prompts the specialist drains each carry their own cap Cₛ (EC-41, Q-9), and its own End-of-run steps spend after its stop (EC-36)."
  - Add the same clause to the :603 sentence.
  - Optionally, add a half-sentence to §9.2 rule 8 for C3.
  - Refusing a capped JevAgent whose specialist has queued prompts or the queue tool is `[scope-adding]`. That is a follow-up, not a fix.
  Spec IDs: INV-6 (Delegated row), §9.2 JevAgent row and rule 8, EC-41, Q-9

R-C2 [Minor] [snippet-and-diagram] docs/spec/loop-spend-cap/spec.md:106-121; vidbyte/agents/spend_cap.py:5 — The delegated path's CP1 (r4) is missing from the two places that list where the cap is checked
  Evidence:
  - The §5 flowchart (spec.md:106-121) shows CP1 only as `F["AgentRuntime._arun_once loop"] --> CP1["CP1 _budget_stop → _spend_cap_stop"]`. It has no `JevRuntime._delegate` node.
  - The `spend_cap.py:5` ARCHITECTURE NOTE says: "The runtime checks the cap at the top of every iteration, on the plain-text finish branch, before every tool call (internal tools included), and before the compute checkpoint of a continuing tool iteration."
  - At the head, `JevRuntime._delegate` (`jev/runtime.py:227`) is a fifth call site of `_spend_cap_stop`, and INV-5 (spec.md:192) defines it as CP1 on the delegated path.
  Failure: a reader who follows the §5 diagram or the module header learns that CP1 is only "the top of every iteration". They miss that a delegated JevAgent run is checked once before its specialist starts. That is the r4 behavior the agents README (`:406-407`) and INV-5 now promise. Behavior is correct, and only these two descriptions lag. Row 28's "not the module header" applies to `jev/runtime.py`, not to `spend_cap.py`, whose row 1 header lists the check points.
  Smallest fix:
  - spec §5: add one edge, `C --> DL["JevRuntime._delegate: CP1 before the specialist"]`.
  - `spend_cap.py:5`: change "at the top of every iteration," to "at the top of every iteration (and, on JevAgent's delegated path, once before the chosen specialist starts),".
  Spec IDs: INV-5 (r4), §12.3 row 1 (header), §5

No Blocker or Major. Each briefing candidate for an unlisted escape was checked against INV-6's segment table:

| Candidate | Result |
|---|---|
| JevAgent-as-specialist | Bounded: P3b gives 2.000×Cₛ, stopped at its own CP1. This is the A-8 look-alike. |
| Bulk work | Tool row; CP3 runs first. |
| Clone | Iteration-tail row; CP4 runs first. |
| Swarm | Tool row. |
| Fresh continuation | Finish row. |
| `FRESH_AGENT`/`FORK_AGENT`/`SUBAGENT` compute options | Observe-only (`compute/controller.py:5`). |
| Output delivery | No model spend. Skipped on `max_spend` (`output/connector.py:53`). |
| Auto-handoff | End-of-run row. |
| Skill preload, tool selector | Never run on the delegated path (`jev/runtime.py:129-131`). |

The only escape found is R-C1's specialist drain.

VERIFIED CLAIMS:
1. **R-1 placement (row 28, INV-5, AC-33): held.**
   - Code at `jev/runtime.py:215-231`, quoted in order: the lead comment "…and checks the spend cap before the specialist starts."; `if self.run_state is not None: await self.run_state.begin_delegated(...); self.usage.require_accounted()`; the 5-line `@intent a-reached-cap-starts-no-specialist` block; `spend_stop = self._spend_cap_stop(iteration_count=0, tokens_used=None, contexts=())`; `if spend_stop is not None: return self.response.finished(spend_stop, self.usage.settle())`; `reply = await self.preflight.specialist.agent.arun(message)`.
   - `git diff daad59fb eba8bf85 -- vidbyte/agents/jev/runtime.py` has one hunk, in `_delegate` only. `_arun_metered`, `_continue_finish_attempt` and the module header are untouched.
   - Row 28 fact (ii) holds. A blind meter cannot reach the check, because `require_accounted()` runs at `:122` (and at `:221` with a run state), and nothing spends between that call and the check.
2. **The orchestrator's R-1 probe result: held, independently.**
   - My P2 gives `stop_reason='max_spend' iteration_count=0 specialist_calls=0 main_calls=0`, `rollup==run_total=True cost/C=1.000`.
   - The AC-33 writer case is covered by the test, and by mutant R1b being killed by `[run_state_relation_writer]`.
3. **R-2: held.**
   - `mypy --config-file lint/mypy.ini vidbyte` gives 346 errors at the head and 346 at the pristine `22993b5f`.
   - Keyed on (path, code, message with line numbers masked, source text): NEW 0, GONE 0.
   - The only raw pair is `runtime.py no-redef "already defined on line 1128"` (base) versus `"…1139"` (head), as the repair agent said.
   - `grep spend_cap` on the head output is empty.
   - Behavior: `probe_r2_refusal.py` output is identical at `daad59fb` and at the head (`diff` exit 0). Missing provider → `?:gpt-5.4-mini` with 0 `resolve()` calls; missing model → `openai:?` with 0 calls; priced → constructs with 1 call; unpriced → refused with 1 call.
4. **R-3, R-4, R-M5 (S2b tests; no source change): held.** S2b's M1–M6, re-run on a scratch copy of `eba8bf85` without the AC-33 deselect, are all KILLED by their intended tests:
   - M1 by `slug…[image]`;
   - M2 by `chain…[unpriced_primary_priced_fallback]`;
   - M3 by `test_an_uncapped_run_computes_no_spend_cap_rollup_or_price[tool_then_text]`;
   - M4 by `[duplicate_unpriced_fallback]`;
   - M5 and M6 by `[missing_provider]`.

   The unmutated sanity run gives `1302 passed`, and the scratch files were restored identical.
5. **R-M1: held.** The README `:412-415` claims that no SDK step continues the stopped work, and that only `after_run` and the auto-handoff still run.
   - P1 (main path) prints `hooks=['after_run']`, `deliveries=[('slack','skipped')]`, `queued_prompts_truncated=1`, and `handoff_spent_after_stop=True`.
   - Delivery skips `max_spend`, because `OUTPUT_DELIVERABLE_STOP_REASONS = {final_response, is_done}` (`lib/constants/outputs.py:34`) is read by `OutputShaping.is_deliverable` (`output/connector.py:53`).
   - The drain stops through `last_stop != MAX_SPEND` (`base.py:1211`).
   - Two notes, neither a finding:
     - On the delegated stop, JevAgent's own `after_run` does not run. That is row 28 fact (i), and JevAgentSettings exposes no middleware.
     - G-3's third item, a session rule bound to `resource.exhausted`, is a new reply with a fresh cap (EC-34), so the sentence's "only" is right for the reply itself.
6. **R-M2: held.**
   - `independent_critic.py:126-130` and `prosecutor_defender_judge.py:242` build `AgentRuntimeConfig` with iterations, tokens and tool calls only.
   - No `jev/done`, `jev/brief` or `jev/gate` module names `max_spend`.
7. **Row 17 / A-8: held.** The clause is verbatim, placed right after the "names the specialist that ran" sentence (`jev/README.md:24`). P2 shows `response.specialist='database'` with 0 specialist calls.
8. **R-M3: the deviation is forced.**
   - The section runs from `:386` to `:431`, which is 46 lines including the heading.
   - It has 4 blank lines and a 9-line example (≤ 12 allowed). Every prose line maps to a row 13 clause, row 28's delegated check (`:406-407`), R-M1 (`:412-415`) or R-M2 (`:422-424`):
     - measured and unmeasured, `:388-392`;
     - the check points, `:404-405`;
     - threshold and overshoot, `:408-410`;
     - `max_spend` and `resource.exhausted`, `:410-411`;
     - the blind stop, `:411-412`;
     - INV-23, `:412-414`;
     - reading spend, `:415-417`;
     - per reply, hidden from the model, and the fork tool, `:419`;
     - the per-runtime prose, `:420-428`;
     - EC-35, `:428-429`;
     - `CostBudgetMiddleware`, `:430-431`.
   - Two ragged lines come from minimal-diff inserts: `:407` is 69 columns and ends "…starts no specialist. It", and `:424` is 61 columns. A reflow could recover at most about one line per paragraph (about 1,133 and 1,081 characters at an 88-column limit). It cannot reach "about 36" without dropping a required clause. No cut is warranted. The reflow of `:404-408` is optional polish.
9. **R-M4: held.**
   - The wrap is 73/63/70/63 columns at `vocabulary.md:106-109`, and the word diff against `daad59fb` is empty.
   - The file's maximum width is 81 columns.
   - Against base, the only change is that paragraph: row 15's words are inserted after the `:106` sentence, and the existing middleware sentence is rewrapped.
   - `test_loop_spend_cap_docs.py` gives `6 passed`.
10. **The S5 scope claim: held.** `git diff --name-only dbe84114 eba8bf85` lists only `jev/runtime.py`, `spend_cap.py`, the two READMEs, `skills/failure/vocabulary.md`, and 5 `docs/spec` records. `git diff --stat b3796d74 eba8bf85 -- tests` is empty.
11. **§14 "Never" and the budget: held.**
    - `git diff origin/main...eba8bf85 -- lint/baseline.json contracts vidbyte/lib/enums/failure.py vidbyte/__init__.py vidbyte/agents/__init__.py pyproject.toml` is empty.
    - Tests against base: 0 deleted lines. The only pre-existing test file touched is `tests/test_codex_output_contracts.py`, with `1 0` (row 26).
    - §8.4: 1 new file (`vidbyte/agents/spend_cap.py`) and 28 modified files, matching r4's "28". Each one is a §12.3 row.
    - NFR-5: `runtime.py` +37 (≤ 40), `base.py` +20 (≤ 25).
    - No `noqa`, `pragma` or `xfail` was added to source. The one `# type: ignore[misc]` is in an S2 test that asserts `cost_measured` is read-only, and tests are outside S009.
    - No key-shaped literal is in the added lines.
    - No added line calls unmeasured spend "capped".
12. **AC-1 / §4: held.**
    - The snippet extracted from spec.md is byte-identical to the test constant.
    - cap → "stopped at $0.7500: reached the $0.50 cap"; blind → "stopped: spend could not be fully measured (at least $0.0000)"; finished → "finished; spent $0.0008". At $0.4999995 it finishes; at $0.50000025 it stops. The wire is called once per case.
    - The S4 probe's sixth case, an "unpriced response model" over the gateway wire, prints "finished". This is not a defect. The AUTO gateway path records the configured model `gpt-5.4-mini`, whatever the body says, and does so identically at base (`probe_wire_model.py`: `[('openai','gpt-5.4-mini',0.000795)]` at both trees). AC-9 covers a bound runner that names an unpriced model.
13. **Every AC's proof test exists: held.** All 33 AC rows were checked against `--collect-only`. AC-27's unittest class path resolves as `ContractValidationTests::test_rejects_every_field_the_constant_lists`. AC-33 maps to `test_a_reached_cap_starts_no_specialist_the_gate_chose[gate_decision, run_state_relation_writer]` (test-plan.md:56).
14. **The r4 IDs: held, apart from R-C1 and R-C2.**
    - INV-5's delegated CP1: held.
    - INV-9 on the delegated stop: held. The reached text, `iteration_count` 0, `tokens_used` None, 0 tool calls and the run-total rollup are asserted by AC-33. No new key is added; there are fewer keys (no `middleware` or `iteration_outputs`), as on every delegated reply.
    - INV-10: held. AC-33 routes one RESOURCE_EXHAUSTED/EXHAUSTED/ROUTE failure.
    - INV-20: held.
    - D-13 (amended), EC-17, FR-3 and W-5: held.
    - §9.2 JevAgent row: held, except its last sentence (R-C1).
    - The other FR, NFR, INV, AC and EC items and rows 2–12, 14, 16 and 18–27 are untouched since `daad59fb`. Their S4 walk stands, and their proofs are green: 188 for the pack plus codex, 1302 for the area suite.
15. **Remote checks: held.** `gh run view 39422105237` gives `{"conclusion":"success","headSha":"eba8bf85…","name":"CI","status":"completed"}`. `gh run view 39422108655` gives the same for "Static policy".
16. **Bookkeeping (not a finding).** The spec frontmatter is still `status: implemented`. r4 §17 says "the repair stage moves it on", and S5 did not. S6 can set it.

COMMANDS RUN:
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider <pack> tests/test_codex_output_contracts.py <briefing area list> tests/test_jev*.py` → `1302 passed in 11.63s`
- The same command for the pack plus codex only → `188 passed in 1.53s`. `test_loop_spend_cap_docs.py` → `6 passed in 0.09s`
- `PYTHONPATH=… py -3.11 -m mypy --config-file lint/mypy.ini --cache-dir <scratch> vidbyte`, at the head and at the pristine `22993b5f` → both `exit 1`, with 346 `error:` lines each. `mypy_keyed_diff.py` → `head errors: 346  base errors: 346 / NEW at head: 0 / GONE at head: 0`, plus the single no-redef 1128/1139 pair
- `probe_r2_refusal.py`, at the `daad59fb` archive and at the `eba8bf85` archive → `diff` exit 0 (`IDENTICAL`)
- `mutate_rereview.py <scratch eba8bf85 copy>` with sanity, M1–M6 and R1a–R1e → `SURVIVED NONE_sanity_unmutated | 1302 passed` / 11 × `KILLED` / `restored: True`
- `probe_readme_claims.py` (P1, P2, P3) and `probe_p3b.py` → the lines quoted in claims 2, 5 and 7. P3b gives `stop_reason='max_spend' iteration_count=0 inner_model_calls=0 … total/innerC=2.000`
- `probe_specialist_drain.py` → `specialist calls=4 jev stop_reason='final_response' queued_prompt_runs=3` / `JevAgent measured total = 3.201 x C`
- `probe_inv17_jev.py`, at the pristine base and at the head → `diff` exit 0 (`JEV UNCAPPED IDENTICAL`). The rollup counts are 8/11/8/8/8 at both trees
- `r3-s4/engineering/probes/probe_inv17.py`, at base and at the head → `UNCAPPED IDENTICAL`. With `capped-high` (1e9), every measured scenario is the SAME as base, and only `blind_usage` and `unpriced_response` differ (INV-4(b))
- `r3-s4/conformance/probe_snippet.py <eba8bf85 copy>` → 5 of 5 AC-1 lines match (see claim 12)
- `probe_wire_model.py`, at the head and at base → `[('openai', 'gpt-5.4-mini', 0.000795)]` at both
- `PYTHONPATH=$(pwd) py -3.11 scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 731f094c… (vidbyte-sdk 0.4.0, 733 exports).`
- The `git diff --stat/--numstat/--name-only/--word-diff` checks quoted in claims 9–11
- `gh run view 39422105237 --json …` and `gh run view 39422108655 --json …` → `completed` and `success` on `eba8bf85`
- `git worktree add --detach …/r3-rereview-pristine 22993b5f`, then `git worktree remove` → `REMOVED`. The worktree's `git status --short` is empty.

All probes and outputs are under `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/r3-rereview/`.
