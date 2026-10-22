# S4 findings verifier — loop-spend-cap (PR #1192)

Reviewed range: `git diff origin/main...daad59fb` (merge base `22993b5f`, `origin/main` = `22993b5f`). Worktree HEAD is `3b7d51e9`. `git diff --stat daad59fb HEAD -- vidbyte tests lint scripts` is empty, so every probe run in the worktree ran daad59fb's code.

Probes, mutants and scratch trees are all under `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/r3-s4/verifier/`. Below, `V` means that path.
- `tree-base` is a `git archive 22993b5f`.
- `tree-head` is a `git archive daad59fb`, mutated only temporarily and restored after each mutant (`restored: True`).
- `tree-fix` is `daad59fb` with the R-1 and R-2 fixes applied. It has a throwaway `git init`/`git add` index only so that `lint/run.py` can enumerate files.

The worktree was never modified apart from `review.md` and this report. `git status --short` was empty before they were written.

## 1. Merge map

| Original | Lens | Proposed | Merged ID | Verified tier | Disposition |
|---|---|---|---|---|---|
| R-E1 | engineering | Blocker | **R-1** | Blocker | CONFIRMED |
| R-V1 | conventions | Major | **R-2** | Major | CONFIRMED (citation corrected) |
| R-E3 | engineering | Major | **R-3** | Major | CONFIRMED (test coverage) |
| R-C3 | conformance | Minor [scope-adding] | **R-3** | Major | merged into R-3, with the same mutant and root cause; the scope-adding tag is rejected |
| R-E2 | engineering | Major | **R-4** | Major | CONFIRMED (test coverage) |
| R-C1 | conformance | Minor | R-M1 | Minor | passed through, trivial |
| R-C2 | conformance | Minor | R-M2 | Minor | passed through, trivial |
| R-C4 | conformance | Minor | R-M3 | Minor | passed through, trivial |
| R-V2 | conventions | Minor | R-M4 | Minor | passed through, trivial; the verifier adds a fix trap |
| R-E4 | engineering | Minor | R-M5 | Minor | passed through, trivial |

- R-E2 and R-E4 both point at `spend_cap.py` refusal tests, but they fail differently. R-E2's mutants accept a cap that is then never enforced, while R-E4's change only the refusal text. Their merge test fails on "same failure", so they stay separate, though one test edit can close both.
- R-C1, R-C2 and R-C4 all touch the README Spend Cap section but have three different root causes. R-C4's count depends on the other two.

Confirmed findings are ordered by severity, then by how much code the fix touches. R-2 is one source line, R-3 is one new test, and R-4 extends two existing parametrized tests.

## 2. Verifications

### R-1 (R-E1): a capped JevAgent's delegated path has no spend check — CONFIRMED, Blocker

**Code read.**
- `vidbyte/agents/jev/runtime.py:120-130` at daad59fb runs `preflight.pass_` (one combined decision request, `gate/gate.py:60-74`, `:86`) and then `self.usage.require_accounted()`. Under `JevReadOnly.ceiling`, if `self.preflight.specialist is not None`, it returns `await self._delegate(message, context)` before `super().arun` at `:145`.
- `_delegate` (`:215-221`) awaits `self.run_state.begin_delegated(...)` and `require_accounted()`, then `self.preflight.specialist.agent.arun(message)`, then `self.response.delegated(reply, self.usage.settle())`.
- No `_spend_cap_stop` call sits on that path. The only cap-related code for specialists is the construction guard `_require_capped_specialists` (`jev/agent.py:128-144`).

**Which run state spends on the delegated path.** I checked this before trusting the reviewer's "uncapped generative run-state writer":
- `JevRunState.begin_delegated` is a no-op (`done/run_state.py:360-362`, "Leave legacy specialist runs without main-agent run state").
- `JevRunStateRelation.begin_delegated` calls `self.begin(...)` (`done/relation.py:52-55`). When there is no record yet, that is `JevRunState.begin` → `self.arun(...)` (`run_state.py:344`), a generative fixed-prompt agent with `run_state_max_iterations`/`run_state_max_tokens` and no USD cap (`run_state.py:281`).
- `jev/agent.py:53-55` builds `JevRunStateRelation` whenever `JevPreflightPreset.RUN_STATE_RELATION` is enabled, a preset the CLI maps (`--preflight run_state_relation`, request.md §C.0).
- So the reviewer's general claim holds on that preset. Without it, the only spend before delegation is the gate's single decision request.

**Own probe.** `cd <worktree> && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 $V/probes/v_jev_delegate.py`:
```
[A gate-decision>=C, delegated]   specialist model calls       = 1
[A gate-decision>=C, delegated]   JevAgent stop_reason         = 'max_spend'
[A gate-decision>=C, delegated]   JevAgent measured total      = 0.00987600 = 78.381 x C
[B] run_state type = JevRunStateRelation
[B relation-writer>=C, delegated] cap C=0.05000000
[B relation-writer>=C, delegated]   run-state writer model calls = 1
[B relation-writer>=C, delegated]   specialist model calls       = 1
[B relation-writer>=C, delegated]   JevAgent stop_reason         = 'final_response'
[B relation-writer>=C, delegated]   JevAgent output              = 'migration written'
[B relation-writer>=C, delegated]   JevAgent measured total      = 0.10587600 = 2.118 x C
[C control: same cap, main path]   specialist model calls       = 0
[C control: same cap, main path]   main generative model calls  = 0
[C control: same cap, main path]   JevAgent stop_reason         = 'max_spend'
[C control: same cap, main path]   JevAgent measured total      = 0.00012600 = 1.000 x C
```
- A: the gate decision cost exactly C (`reference_cost` of one 3,000-token `jev-1.13.0` response is $0.000126), and the specialist was capped at C. The specialist still started and made a 10k-token call. The JevAgent stop is the specialist's own CP2 stop, inherited through `response.delegated`.
- B: a $0.05 cap with the `run_state_relation` preset, and a run-state writer whose spend is at least C. The specialist still ran, and the reply is `final_response` at 2.118 x C. By §9.2 rule 1, C3 would tell the user "not stopped by the cap", although measured spend reached the cap before the specialist started.
- C: the same cap with no specialist chosen. CP1 stops before any generative call, which is AC-14/EC-17 working on the main path.

**Spec reading.** The finding rests on a correct reading:
- G-1 (`spec.md:41`): "The run then stops itself once the spend the SDK measured … reaches the number."
- EC-17 (`:336`): pre-loop decision spend reaching C means CP1 at iteration 0 "stops before the first generative call".
- The INV-6 Pre-loop row (`:206`) ends "at the first CP1".
- §8.2: "admit no new metered unit once the balance reaches the limit".
- §9.2 rule 7 is C3's promise.
- The spec's reason for leaving `jev/runtime.py` alone (`:818`, "the pre-loop phases precede CP1") is factually false for `:129-130`. D-13's deciding reason (`:423`, "the only loop that can enforce anything is the specialist's own") is false too, as the 3-line fix shows.
- No settled decision is reversed. D-13's construction refusal stays, and the fix adds one check. This is not scope-adding: INV-12 counts Jev decision spend, and the request is a universal cap on "every agent" (§D weighted words), so the requested behavior is wrong without the check.
- AGENTS.md "New JEV code" forbids preset checks in `JevRuntime`. This is a cap check, not a preset check.

**Existing guard?** None. `_require_capped_specialists` bounds only the specialist's own ledger. `require_accounted()` catches a blind meter, not a reached one. The pack's Jev tests (`test_loop_spend_cap_jev.py:150`, `:187`) only construct agents, and no test runs the delegated path with a cap.

**Fix verified.** `py -3.11 $V/probes/apply_re1_fix.py $V/tree-fix` inserts, after the `begin_delegated` block in `_delegate`:
```python
        # @intent a-delegated-run-checks-the-cap-first
        # The gate and the run-state writer already spent into this
        # ledger, and no loop check follows on this path, so a cap they
        # reached stops the run before the specialist starts.
        spend_stop = self._spend_cap_stop(iteration_count=0, tokens_used=None, contexts=())
        if spend_stop is not None:
            return self.response.finished(spend_stop, self.usage.settle())
```
The probe against `tree-fix`:
```
[A gate-decision>=C, delegated]   specialist model calls       = 0
[A gate-decision>=C, delegated]   JevAgent stop_reason         = 'max_spend'
[A gate-decision>=C, delegated]   JevAgent measured total      = 0.00012600 = 1.000 x C
[B relation-writer>=C, delegated]   specialist model calls       = 0
[B relation-writer>=C, delegated]   JevAgent stop_reason         = 'max_spend'
[B relation-writer>=C, delegated]   JevAgent measured total      = 0.09612600 = 1.923 x C
```
B's 1.923 x C is the writer's own pre-loop segment, the same overshoot the main path accepts under INV-6. Regression check on `tree-fix` (pack, codex file, `tests/test_jev*.py` and the full area suite):
```
.....................................................                    [100%]
1277 passed in 12.66s
```
Full lint on `tree-fix`, with the R-2 fix also applied, ends `SDK-LINT: PASS`. The IMPROVED lines are exactly base's: `A002 608/703`, `S001 56/59`, `S009 346/350`, `S010 0/5`, `S025 261/263`, `S061 5/6`, `S063 3/4`. So the new `@intent` block adds no A002 finding and the check adds no S008 finding.
- On the delegated path `require_accounted()` precedes the new check, so a blind meter still raises `UsageAccountingError` (rule 5), and the check can only return the reached text.
- Uncapped, `_spend_cap_stop` returns before computing any rollup, so INV-17 holds.
- Principle 1 note for the conventions re-review: `_arun_metered → _delegate → _spend_cap_stop` (inherited) is two levels, the same inherited depth CP3 already has. If S5 prefers, it can move `begin_delegated` and the check into `_arun_metered` and keep `_delegate` as the hand-off only.

**Spec passages S5 must amend together with the code.** `jev/runtime.py` is outside §12.3, so §14 "Ask first" applies:
1. `spec.md:818`: remove `vidbyte/agents/jev/runtime.py` from "Deliberately not changed" and keep its continuation clause as a note on the new row.
2. New §12.3 row 28, MODIFY `vidbyte/agents/jev/runtime.py`: in `_delegate`, the check above (P3). Governing standards: INV-5, INV-6, EC-17, A002, `comment-format.md`. Also update §12.6 P3 to list row 28.
3. `spec.md:206` (INV-6 Pre-loop row): end it "at the first CP1, or, on JevAgent's delegated path, at the cap check before the chosen specialist starts". Add a "Delegated" segment row: it starts after that check, ends at the end of the run, and holds the specialist's whole run, bounded by its own cap ≤ C plus its own G (D-13).
4. `spec.md:191-197` (INV-5): add "On JevAgent's delegated path, the same check runs once in `JevRuntime._delegate`, before the specialist starts."
5. `spec.md:423` (D-13): the deciding reason becomes "Delegation returns before JevAgent's loop, so JevRuntime checks the cap once before the specialist starts, and the specialist's own cap, no higher than JevAgent's, bounds the specialist run."
6. `spec.md:336` (EC-17): "CP1 at iteration 0, or the check before a chosen specialist, stops before the first generative call".
7. `spec.md:599` (§9.2 JevAgent row): "Pre-loop decision spend is counted at the first CP1, or at the check before a chosen specialist starts."
8. A new AC-33 (P0): a capped JevAgent whose gate decision, or RUN_STATE_RELATION writer, brings measured spend to at least C before a chosen specialist runs → `max_spend`, and the specialist makes no model call. Its test goes in `test_loop_spend_cap_jev.py`, modelled on probe scenarios A and B.
9. Docs: README `:404-405` (row 13) and Jev README `:24` (row 17) say JevAgent checks the cap before handing a run to a specialist.
10. A §17 revision row.

**Severity.** I kept the Blocker. Scenario B is a realistic cap on a shipped preset. The run starts a new paid sub-run after its cap is already reached and reports `final_response`, which is the "wrong result" the Blocker tier names, against the feature's core promise.

### R-2 (R-V1): new mypy `arg-type` error, S009 346 → 347 — CONFIRMED, Major

- **Code.** `spend_cap.py:111` reads `priced = bool(runner.provider and runner.model_name) and registry.resolve(ModelProvider(runner.provider), runner.model_name) is not None`. `bool(...)` stops mypy narrowing `model_name: str | None`.
- **Command.** S009 runs exactly `sys.executable -m mypy --config-file lint/mypy.ini vidbyte` from the repo root (`lint/core/mypy.py:56`). I ran it on `tree-base` and `tree-head` in parallel. Both exit 1 (findings). `grep -c ": error:"` gives `346` and `347`.
- **Stable-key diff.** `py -3.11 $V/probes/mypy_diff.py` keys on (path, code, message with `line N` normalized, stripped source line):
  ```
  base errors=346 head errors=347
  ONLY AT HEAD: ('vidbyte/agents/spend_cap.py', 'arg-type', 'Argument 2 to "resolve" of "ModelPricingRegistry" has incompatible type "str | None"; expected "str"', 'priced = bool(runner.provider and runner.model_name) and registry.resolve(ModelProvider(runner.provider), runner.model_name) is not None')
  ```
  The HEAD output line is `vidbyte\agents\spend_cap.py:111:119: error: … [arg-type]`. The `runtime.py` `no-redef` entry (`_runner_model_name already defined on line 1139`) normalizes to the base finding, so it is not new.
- **Is consuming slack a defect?**
  - `lint/README.md:46`: exit 0 means CLEAN, RATCHETED or IMPROVED, so the gate passes and NFR-3's literal target holds.
  - The rule's own documentation is binding. `lint/rules/s009_staged_mypy_contracts.py:26` says "any increase is treated as a new defect in the SDK interface or implementation", and `:27` says "The debt count is therefore a guard against new contract drift, not permission to leave newly introduced errors unresolved."
  - Spec `:671` says the IMPROVED slack "is not this PR's", and `:857` calls it pre-existing slack.
  - The reviewer's field-guide citation (`blocking-lint-invariants.md:13`) is about A003 at zero slack and does not say "even under the baseline", so I replaced it with the rule text.
  - S3's report (`S3-implementer.md:138`) lists the IMPROVED rules "with the same counts as base" but omits S001 and S009. That is why S3 missed it.
- **Tier.** Major. It would draw a review comment ("new file, new mypy error"), and the next `--update-baseline` would lock in 347. It is not a Blocker: the gate passes, behavior is correct (the `bool()` guard already ensures a truthy model at run time), and no AGENTS.md or field-guide text is contradicted verbatim.
- **Fix verified.** `apply_rv1_fix.py` gives `priced = bool(runner.provider and runner.model_name and registry.resolve(ModelProvider(runner.provider), runner.model_name) is not None)`. Package mypy on `tree-fix`: `346`, and `mypy_diff.py` reports `base errors=346 head errors=346` with no ONLY lines. `v_refusal_probe.py` output on `tree-fix` matches `tree-head` byte for byte (`diff` empty), so the two forms behave the same. Full lint on `tree-fix`: `S009 staged-mypy-contracts 346 350 IMPROVED … SDK-LINT: PASS`.

### R-3 (R-E3 + R-C3): NFR-1 / INV-17 "no cap code computes a rollup" unpinned — CONFIRMED, Major (test coverage)

- **Mutant M3** (`v_mutate.py`) adds `rollup = self.usage_tracker.rollup()` before `if self.config.max_spend_usd is None: return None` in `_spend_cap_stop` (`runtime.py:1886-1888`). Against the pack, the codex file and the 13 area paths: `SURVIVED M3_rollup_when_uncapped | 855 passed in 9.93s`.
- **Runner sanity.** `v_with_mutant.py $V/tree-head M0_sanity_gt pytest -q -p no:cacheprovider tests/features/loop_spend_cap` (`>=` → `>` in `stop_output`) gives `28 failed, 95 passed in 2.57s`, and `2.59s` on a re-run. So the harness can kill a mutant.
- **Determinism.** `v_nfr1_count.py` counts `UsageTracker.rollup` calls on uncapped runs. It was run from each tree with `PYTHONPATH` set to that tree. The M3 run is `v_with_mutant.py $V/tree-head M3_rollup_when_uncapped $V/probes/v_nfr1_count.py`.
  ```
  == tree-base
  tool_then_text               rollup_calls=  1 stop='final_response' out='Paris is in France.'
  is_done                      rollup_calls=  1 stop='is_done' out='done'
  drain_three_queued           rollup_calls=  8 stop='final_response' out='a'
  == tree-head
  tool_then_text               rollup_calls=  1 stop='final_response' out='Paris is in France.'
  is_done                      rollup_calls=  1 stop='is_done' out='done'
  drain_three_queued           rollup_calls=  8 stop='final_response' out='a'
  ### mutant M3_rollup_when_uncapped (exit 0)
  tool_then_text               rollup_calls=  6 stop='final_response' out='Paris is in France.'
  is_done                      rollup_calls=  3 stop='is_done' out='done'
  drain_three_queued           rollup_calls= 16 stop='final_response' out='a'
  ```
  The counts depend on the scenario: the engineering reviewer measured 2 per run and 6 for its drain on different shapes. So the test should pin the caller, not a number.
- **Verified test design.** `v_nfr1_frame.py` records `sys._getframe(1).f_code.co_name` for each rollup call:
  ```
  == tree-head
  uncapped    stop='final_response' rollup_from_spend_cap_stop=0 stop_output_calls=0 all_callers=['_runtime_metadata']
  capped_1e9  stop='final_response' rollup_from_spend_cap_stop=5 stop_output_calls=5 all_callers=['_runtime_metadata', '_spend_cap_stop']
  ### mutant M3_rollup_when_uncapped (exit 0)
  uncapped    stop='final_response' rollup_from_spend_cap_stop=5 stop_output_calls=0 all_callers=['_runtime_metadata', '_spend_cap_stop']
  ```
  The reviewer's "assert `stop_output` is never called" alone would NOT kill M3, because it stays 0. The assertion must be on rollup calls from `_spend_cap_stop`.
- **Spec reading.** NFR-1 is P0, and its target names exactly this early return (`spec.md:385`). test-plan.md:69 skipped a test on the premise "Wall-clock assertions are nondeterministic … NFR-1 is shown by the metamorphic AC-10 test, and S4 can mutate the early return". S4 did, and the mutant survives. AC-10 compares outputs, which a wasted rollup does not change.
- **Adjudication: Major (engineering) vs Minor [scope-adding] (conformance).** A test that pins a P0 spec requirement adds no behavior, so it is not scope-adding. The briefing routes surviving mutants to S5 as confirmed coverage findings. The behavior at HEAD is correct, so no source change is needed.

### R-4 (R-E2): two refusal mutants re-open "accept the cap and ignore it" — CONFIRMED, Major (test coverage)

- **Mutants** (`v_mutate.py`, 855 tests):
  ```
  SURVIVED M1_providerless_skips_all_checks     | 855 passed in 9.91s
  SURVIVED M2_chain_skips_primary               | 855 passed in 9.99s
  ```
  M1 is `not (runner_config.provider or runner_config.model_name)` → `and` (`spend_cap.py:60`). M2 is `fallback.models` → `fallback.models[1:]` (`:98`).
- **Behavioral consequence.** At HEAD (`v_refusal_probe.py` run from `tree-head`, saved as `$V/refusal-head.txt`), all five edges are refused:
  ```
  slug normalization: openai gpt-image-2 image
  slug image primary, no provider        | uncapped constructs (runner_config.provider=None)
                                         | capped -> REFUSED: Agent researcher sets max_spend_usd, but its image runner runs outside the agent loop, which is the only place the spend cap is enforced.
  slug unpriced primary, no provider     | uncapped constructs (runner_config.provider=None)
                                         | capped -> REFUSED: Agent researcher sets max_spend_usd, but the pricebook has no price for openai:gpt-unpriced-spend-cap-probe, so its spend could not be measured.
  unpriced primary + priced fallback     | uncapped constructs (runner_config.provider='openai')
                                         | capped -> REFUSED: … no price for openai:gpt-unpriced-spend-cap-probe, …
  image primary + text fallback          | uncapped constructs (runner_config.provider='openai')
                                         | capped -> REFUSED: … its image runner runs outside the agent loop, …
  duplicate unpriced fallback            | uncapped constructs (runner_config.provider='openai')
                                         | capped -> REFUSED: … no price for openai:gpt-unpriced-spend-cap-probe, …
  ```
  `v_with_mutant.py $V/tree-head <M> $V/probes/v_refusal_probe.py | grep -E "^###|capped -> "` gives the capped results in that same row order (rows 1–5):
  ```
  ### mutant M1_providerless_skips_all_checks (exit 0)
                                         | capped -> ACCEPTED
                                         | capped -> ACCEPTED
                                         | capped -> REFUSED: … no price for openai:gpt-unpriced-spend-cap-probe, …
                                         | capped -> REFUSED: … its image runner runs outside the agent loop, …
                                         | capped -> REFUSED: … no price for openai:gpt-unpriced-spend-cap-probe, …
  ### mutant M2_chain_skips_primary (exit 0)
                                         | capped -> REFUSED: … its image runner runs outside the agent loop, …
                                         | capped -> REFUSED: … no price for openai:gpt-unpriced-spend-cap-probe, …
                                         | capped -> ACCEPTED
                                         | capped -> ACCEPTED
                                         | capped -> REFUSED: … no price for openai:gpt-unpriced-spend-cap-probe, …
  ### mutant M4_no_dedupe (exit 0)
  (rows 1-4 as HEAD)
                                         | capped -> REFUSED: … no price for openai:gpt-unpriced-spend-cap-probe, openai:gpt-unpriced-spend-cap-probe, so its spend could not be measured.
  ```
  ("…" marks where the full refusal text shown in the HEAD block was shortened.) M1 accepts rows 1–2, and M2 accepts rows 3–4.
  - The slug form is a real configuration: the uncapped agent constructs with `runner_config.provider=None`, and `Runner` normalizes it to an image runner.
  - INV-13 and §8.5 skip the checks only when a config has neither a provider nor a model, and the slug form has a model.
  - Under M1 or M2, a capped image agent constructs and runs outside the loop (`base.py:1307`, `:1333-1368`), so the cap is accepted and never checked. G-3 forbids exactly this.
- **Existing guard?** None. The pack's refusal cases (`test_loop_spend_cap_refusals.py:119-175`) always pass `provider=` and use `PRICED_MODEL` as the primary in every chain case (`:146-152`, `:181-186`).
- **Tier.** Major. It is a P0 safety property (INV-13) whose regression ships green.

### Minors (passed through)

- **R-M1 (R-C1).** Confirmed by reading `README.md:410-412` against `spec.md:269` and `:43`. The conformance probe's `hooks_after_stop=['after_run']` matches `_finish_result` (`runtime.py:956-958`).
- **R-M2 (R-C2).** Confirmed by reading `README.md:416-417` against `spec.md:607`. The reviewer configs have no cap (`independent_critic.py:126`, `prosecutor_defender_judge.py:242`), as D-18 intends.
- **R-M3 (R-C4).** My own listing `git show daad59fb:vidbyte/agents/README.md | awk 'NR>=384 && NR<=427'` shows `386: ## Spend Cap`, last text line `424: stops with …`, `425:` blank, and `426: ## Key Modules`. That makes 39 lines with the heading.
  - The conventions lens repeated S3's "38 lines". I adjudicated for conformance's 39.
- **R-M4 (R-V2).** `awk` gives `106` for line 107, and every other line in the file is 81 columns or less.
  - [verifier] Fix trap: `test_loop_spend_cap_docs.py:80-83` needs one line holding both `max_spend` and `resource.exhausted`. `py -3.11 -I $V/probes/v_wrap_trap.py $V/vocab-head.md`, where `vocab-head.md` is `git show daad59fb:skills/failure/vocabulary.md`, gives:
    ```
    107: 106 | A run that `AgentLoopSettings.max_spend_usd` stops (stop reason `max_spend`) reports `resource.exhausted`.
    width 80: docs-test line check = False, widths [79, 78, 68, 44]
    width 79: docs-test line check = False, widths [79, 78, 68, 44]
    width 76: docs-test line check = False, widths [75, 74, 76, 44]
    width 72: docs-test line check = True, widths [63, 66, 62, 69, 8]
    hand wrap: docs-test line check = True, widths [73, 63, 70, 63], same words = True
    ```
    The hand wrap in review.md passes and keeps row 15's words unchanged.
- **R-M5 (R-E4).** `SURVIVED M4_no_dedupe`, `M5_question_mark_dropped` and `M6_openrouter_exemption_widened`, each with `855 passed`.
  - Under M4 the refusal names `openai:gpt-unpriced-spend-cap-probe, openai:gpt-unpriced-spend-cap-probe`.
  - All three change only refusal text or reject a config later in `Runner.build()`. No spend follows, so they stay Minor.

## 3. Blind-spot sweep (between the lenses)

1. **A spend path that reaches no check point.**
   - Runtime subclasses that extend the loop: `git grep "class .*(AgentRuntime)"` finds only `JevRuntime` and `InfiniteMemoryRuntime`.
   - `InfiniteMemoryRuntime.arun` (`infinite/runtime.py:90-125`) spends nothing outside `super().arun`.
   - JevRuntime's only path without a check is R-1. The main path's gate, preload, run-state and selector spend precede CP1. Continuations and done checks sit in the Finish segment before the next CP1.
   - Algorithm drivers: only reflexion, the critic, PDJ and the grader run `_arun_once` attempts (`vidbyte/agents/algorithms/`), and rows 18–21 cover them. The `context/algorithms/` policies run inside the loop.
2. **A `middleware_abort` consumer outside rows 18–24.**
   - `git grep "MIDDLEWARE_ABORT\|\"middleware_abort\""` finds only rows 18–23, `MagenticOneOrchestrator.finalize` (`orchestrator.py:169`, which raises for every non-answer stop and must stay untouched), the router, Codex middleware (unrelated) and the producer at `runtime.py:1224`.
   - No default Session rule routes `RESOURCE_EXHAUSTED`: `git grep RESOURCE_EXHAUSTED` finds only the enum and the router entry, which matches EC-34.
3. **A copy path that drops the field.**
   - Every `AgentLoopSettings(` construction in `vidbyte/` either passes through (`base.py:342` flat params with no cap keyword, by NG-9; `base.py:785` restore; `config.py:687` `**mapping`; `loader.py:216` `**loop_raw`; fork tool `:332` with guardrails), carries the field (`fork.py:157`), or is a Jev fixed-prompt agent (`brief/writer.py:60`, `done/handoff.py:161`, `done/reviewer.py:37`, `done/run_state.py:281`, `gate/clarification.py:54`).
   - Every `agent_loop_settings=settings.loop` child carries it (`jev/agent.py:77`, `:98`, `bulk_work.py:60`, `compute/clone.py:45`, `compute/swarm.py:57`, `infinite/agent.py:87`, `infinite/launch.py:311`).
   - Of the files naming both `max_tool_calls` and `timeout_seconds`, the only ones without the cap are PDJ (`:242`, reviewer, D-18), `contracts/floors.py` (NG-5) and the PDJ policy record. None is a copy path.
4. **A convention fix that breaks a conformance requirement.** R-V2's suggested rewrap breaks the docs test (R-M4 trap above). R-2's fix is behavior-identical (refusal probe `diff` empty).

No new Blocker-class finding beyond R-1 was found.

## 4. Disagreements adjudicated

- **NFR-1 severity.** Engineering said Major and conformance said Minor [scope-adding]. I chose Major, not scope-adding (§2, R-3).
- **README length.** Conformance said 39, while conventions and S3 said 38. I chose 39 (§2, R-M3).
- **R-E1's pre-delegation spend.** The engineering reviewer described it as including an uncapped generative writer. That holds only with RUN_STATE_RELATION; otherwise it is one decision call (§2, R-1). The Blocker is upheld on the preset path with a realistic $0.05 cap.
- **R-V1's authority.** I replaced the field-guide citation with the S009 rule's own text and kept the tier at Major (§2, R-2).
- **Orchestrator note on R-E3/R-C3 counts** ("2 calls per uncapped run, 6 for a 3-prompt drain"). The counts depend on the scenario (mine are 1/1/8). The recommended assertion is on the caller frame, not an absolute count.

## 5. Not findings (checked and dismissed)

- **Conformance M16** (an unsorted set in `_blind_causes`) survived one run but is killed under 5 of 6 hash seeds, and its deterministic twin M40 is killed. The order test still catches the regression on most runs. Not raised; S5 may add a third unpriced model to the order test if it touches that file.
- **The inherited red** `test_harness_threads_surface.py::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` and the row-16 "(#NNNN)" are settled.

## 6. Commands run (final lines)

- `git diff --stat daad59fb HEAD -- vidbyte tests lint scripts` → empty; `git status --short` → empty (before writing outputs).
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 $V/probes/v_jev_delegate.py` (worktree) → see R-1; on `tree-fix` → see R-1.
- `cd $V/tree-fix && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$V/tree-fix py -3.11 -m pytest -q -p no:cacheprovider tests/features/loop_spend_cap tests/test_codex_output_contracts.py tests/test_jev*.py tests/features/sdk_loop_settings tests/features/sdk_model_usage tests/test_agent_runtime.py tests/test_session_failures.py tests/test_fork_tool.py tests/test_algorithms_honor_middleware_abort.py tests/multi_agent tests/test_queued_prompt_usage.py tests/features/infinite_memory_agent tests/test_reflexion_algorithm.py tests/test_independent_critic_algorithm.py tests/test_multi_provider_agentic_grader.py`, with both fixes present (`grep` finds `jev/runtime.py:220` `@intent a-delegated-run-checks-the-cap-first` and the `spend_cap.py:111` fixed form) → `1277 passed in 12.66s`, and `1277 passed in 12.70s` on a re-run.
- Mutant restore: `diff --strip-trailing-cr <(git show daad59fb:<file>) $V/tree-head/<file>` is clean for `runtime.py` and `spend_cap.py` after every mutant. The archive has CRLF line endings, so a plain `diff` differs only in CR.
- `py -3.11 -m mypy --config-file lint/mypy.ini vidbyte` on `tree-base`/`tree-head`/`tree-fix` → `346`/`347`/`346` errors, `exit=1` each.
- `PYTHONIOENCODING=utf-8 PYTHONPATH=$V/tree-fix py -3.11 lint/run.py` (`tree-fix`) →
  ```
  S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline
  SDK-LINT: PASS
  ```
  (`exit=0`; the IMPROVED set equals spec §11's base set).
- `py -3.11 $V/probes/v_mutate.py $V/tree-head` (the timings quoted above come from the first run). The re-run gave:
  ```
  SURVIVED M1_providerless_skips_all_checks     | 855 passed in 9.84s
  SURVIVED M2_chain_skips_primary               | 855 passed in 9.89s
  SURVIVED M3_rollup_when_uncapped              | 855 passed in 9.89s
  SURVIVED M4_no_dedupe                         | 855 passed in 9.86s
  SURVIVED M5_question_mark_dropped             | 855 passed in 10.34s
  SURVIVED M6_openrouter_exemption_widened      | 855 passed in 9.87s
  restored: True
  ```
- `py -3.11 $V/probes/v_with_mutant.py $V/tree-head M0_sanity_gt pytest -q -p no:cacheprovider tests/features/loop_spend_cap` → `28 failed, 95 passed in 2.57s`.
- `v_refusal_probe.py` under NONE/M1/M2/M4 → see R-4 and R-M5; `diff refusal-head.txt refusal-fix.txt` → empty.
- `v_nfr1_count.py` (base/head/M3) and `v_nfr1_frame.py` (head/M3) → see R-3.
- `v_wrap_trap.py` over `skills/failure/vocabulary.md:106-109` → see R-M4.
- `git status --short` (after writing outputs) → `?? docs/spec/loop-spend-cap/reports/S4-findings-verifier.md` and `?? docs/spec/loop-spend-cap/review.md` only.
