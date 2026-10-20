LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — the four check points, the blind-meter stop and the construction refusals held under every run-time attack I made, but a capped JevAgent that delegates to a specialist skips every check point and can start the specialist after its own spend has already reached the cap.

Reviewed: `git diff origin/main...daad59fb` (52 files, +6715/−35). The merge base is 22993b5f. HEAD 78f947e0 differs from daad59fb only in `pipeline.md`. Every probe below ran offline on scripted runners or on the patched `HttpTransport`. No real keys were used. Probes live in `scratchpad/r3-s4/engineering/probes/`.

## WHAT THE IMPLEMENTATION GETS RIGHT

- The check points are where INV-5 puts them, and each one is load-bearing. Mutation testing killed 48 of 54 mutants. Removing or moving CP1/CP2/CP3/CP4, changing `>=` to `>`, reading `cost_complete` for the blind check, putting the blind check before the reached check, accepting `max_spend` in the drain, and reverting rows 18–24 each turn the pack red.
- The overshoot stays inside INV-6 on every run-time path I attacked (each line shows spend at stop and C + G):
  - three concurrent capped children in one internal tool: 2.75×C, below 3.70×C;
  - a `review_finish` that spends and then CONTINUEs: 1.95×C, below 2.91×C, with no further model call;
  - four billed failures retried by `ModelRetryMiddleware`: 2.70×C, below 3.70×C, and the lookup tool never ran;
  - a billed Anthropic refusal that reaches C: the run stops at CP1 before the Gemini fallback is called (0 Gemini calls). This is EC-27, which the pack does not test.
- It fails closed, and it says why:
  - A corrupted usage payload gives the stop text "usage recording failed".
  - A response model the pricebook lacks (`gpt-5.4-mini-preview`) gives the stop text naming `openai:gpt-5.4-mini-preview`.
  - When an uncapped child bills `zz` and then `aa`, the parent's stop text sorts them (`aa, zz`).
  - A blind child, capped or uncapped, makes the parent stop before its next tool.
  - In every case `cost_measured` is False and `cost_complete` is False, and no further model or tool call happens.
- The default path is free. The scrubbed JSON dumps of the reply and `get_usage()` for 9 uncapped scenarios (text, tool, isDone, max_iterations, max_tool_calls, max_tokens, blind usage, unpriced response, queued drain) are byte-identical at 22993b5f and daad59fb. The `UsageTracker.rollup()` call counts are identical too (2 per run, 6 for the drain). With a cap of 1e9, every measured scenario is identical to base (INV-8). Only the blind and unpriced scenarios change, and they now fail closed.

## FINDINGS (ranked)

R-E1 [Blocker] [pre-mortem / spec-wrong] vidbyte/agents/jev/runtime.py:129-130 — A capped JevAgent that delegates runs no check point, so it starts a specialist after its own spend has already reached the cap.

  Evidence: `_arun_metered` returns `await self._delegate(message, context)` (:129-130) before `super().arun` (:145). `_delegate` (:215-221) runs `run_state.begin_delegated` (an uncapped fixed-prompt agent run) and then `specialist.agent.arun(message)`. Nothing between the gate and the specialist calls `_spend_cap_stop`.

  The specialist's own cap (`jev/agent.py:129-144`) starts at $0 on the specialist's own ledger. It never sees JevAgent's pre-loop spend.

  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<worktree> py -3.11 probes/probe_jev_delegation.py`:
  - Setup: one gate decision costs exactly C. The specialist cap is C.
  - Variant 1 (one specialist turn, $0.0135):
    ```
    pre-delegation decision spend = 0.016800  (>= C: True)
    specialist model calls        = 1
    JevAgent stop_reason          = 'final_response'
    JevAgent measured total       = 0.030300  = 1.804 x C
    ```
  - Variant 2 (two specialist turns of 0.95 C each):
    ```
    specialist spend              = 0.031920
    JevAgent stop_reason          = 'max_spend'
    JevAgent measured total       = 0.048720  = 2.900 x C
    ```

  On the non-delegated path, the same pre-loop spend stops at CP1 of iteration 0 (AC-14, EC-17).

  Failure: a JevAgent capped at C chooses a specialist (capped at C, as D-13 requires), and the gate decisions plus the run-state writer already spent at least C.
  - Variant 1: the run starts a new segment (a whole specialist run) and returns `final_response`. So the run "ends without stopping" after reaching the cap.
  - Variant 2: spend at stop is 2.9×C. G here is the largest segment: the pre-loop at C, or the whole specialist run at 1.9×C. So C + G is 2.9×C at most, and spend reaches C + G.
  - In general, total spend on the delegated path is D_pre + C_s + G_s, where D_pre includes an uncapped generative run-state writer.
  - This violates G-1 ("stops itself once the spend … reaches the number"), the briefing's Blocker rule, and §9.2 rule 7. Rule 7 is what C3 will tell users: "stops the run once measured spend reaches $X".

  Why the spec is wrong:
  - spec.md:818 keeps `jev/runtime.py` unchanged "because … the pre-loop phases precede CP1".
  - The INV-6 Pre-loop row (spec.md:204) ends "at the first CP1".
  - D-13 (spec.md:423) says "the only loop that can enforce anything is the specialist's own".

  All three assume a CP1 follows the pre-loop phases. On the delegated path no CP1 ever runs, and the specialist's loop cannot see the parent's ledger. The pack's Jev tests check the specialist guard only at construction (`test_loop_spend_cap_jev.py:186`).

  Smallest fix: in `_delegate`, right after `begin_delegated` and its `require_accounted()` and before `specialist.agent.arun`, add:
  ```python
  stop = self._spend_cap_stop(iteration_count=0, tokens_used=None, contexts=())
  if stop is not None:
      return self.response.finished(stop, self.usage.settle())
  ```
  A blind meter already raises through `require_accounted()`, as rule 5 says. Add a test like the probe: decision cost equals C and a specialist is chosen. Assert `stop_reason == "max_spend"` and `specialist_runner.calls == 0`.

  Fix verified on a scratch copy of daad59fb with these three lines applied. In both probe variants, `specialist model calls = 0`, `JevAgent stop_reason = 'max_spend'`, and `JevAgent measured total = 0.016800 = 1.000 x C`. The pack, `test_codex_output_contracts.py` and every `tests/test_jev*.py` give `618 passed in 5.24s`.

  Amend the spec:
  - spec.md:818 (row for `jev/runtime.py`);
  - the INV-6 Pre-loop row: the delegated path ends at this check, and the specialist run is then one segment;
  - D-13.

  Spec IDs: G-1, INV-5, INV-6, D-13, EC-17, AC-14, §9.2 rule 7, §12.3 "Deliberately not changed".

R-E2 [Major] [test quality] vidbyte/agents/spend_cap.py:60 and :98 — Two surviving mutants re-open "accepts the cap and silently ignores it", and no test in the pack or the area suite catches them.

  Evidence: `py -3.11 probes/mutate.py head <ids> --area` ran the pack plus 15 area files (1051 tests):
  ```
  SURVIVED  refusal_skips_primary_in_chain   ... | 1051 passed in 6.06s
  SURVIVED  providerless_skips_all_checks    ... | 1051 passed in 5.97s
  ```
  With each mutant applied, `probe_construction.py` and `probe_slug_refusal.py` report:
  ```
  ### mutant providerless_skips_all_checks
     openai/gpt-image-1                       ACCEPTED
     openai/gpt-unpriced-spend-cap-probe      ACCEPTED
  ### mutant refusal_skips_primary_in_chain
     unpriced primary + priced fallback       -> ACCEPTED
     image primary + text fallback            -> ACCEPTED
  ```
  The unmutated head refuses all four.

  The pack's refusal cases (`test_loop_spend_cap_refusals.py:119-175`) always pass `provider=` explicitly. They never combine a fallback chain with a bad primary.

  Failure: a later refactor of `model_refusal` ships green in either of two ways:
  - it changes `or` to `and` at :60;
  - it builds the chain from `fallback.models[1:]` at :98.

  Then `BaseAgent(model_name="openai/gpt-image-1", agent_loop_settings=AgentLoopSettings(max_spend_usd=1))` constructs. That form is runnable, because `Runner` reads the slug prefix. Its image runner runs outside the loop, with the cap set and never checked. This is the outcome `@intent spend-cap-is-never-silently-unenforced` (base.py:249) and the weighted words "every agent to be tracking usage" (NFR-6 → INV-13, G-3) forbid.

  Smallest fix: add parametrized cases to `test_a_capped_non_text_model_is_refused_naming_its_runner_type` and `test_a_capped_agent_with_an_unpriced_configured_model_is_refused_naming_each_one`:
  - (a) `provider=None, model_name="openai/" + IMAGE_MODEL`, and `provider=None, model_name="openai/" + UNPRICED_MODEL`;
  - (b) an image or unpriced primary with `fallback=[FallbackModel(*PRICED_FALLBACK)]`.

  Spec IDs: INV-13, FR-7, AC-12, AC-30, G-3, NFR-6.

R-E3 [Major] [test quality] vidbyte/agents/runtime.py:1886-1888 — NFR-1 (P0) has no test. The test plan's reason for skipping one rests on a false premise.

  Evidence:
  ```
  SURVIVED  nfr1_rollup_always   ... | 174 passed (pack)
  SURVIVED  nfr1_rollup_always   ... | 1051 passed in 5.94s (pack + area)
  ```
  The mutant computes `self.usage_tracker.rollup()` before the `max_spend_usd is None` return.

  test-plan.md:69 says "NFR-1 is shown by the metamorphic AC-10 test, and S4 can mutate the early return". The AC-10 test compares outputs, which a wasted rollup does not change, so it cannot detect this mutant. The premise "wall-clock assertions are nondeterministic" is also wrong: a call count is deterministic. `probe_inv17.py` counts rollups (2 per uncapped run at both base and head) without any timing.

  Failure: every check on every uncapped run in the SDK pays an O(records) rollup. I measured 0.28 ms at 1,000 records and 2.9 ms at 10,000 records per check, with four checks per iteration. This contradicts NFR-1 and INV-17 ("No cap code computes a rollup") and ships green.

  Smallest fix: one test in `test_loop_spend_cap_runtime.py`. Patch `AgentSpendCap.stop_output` and `UsageTracker.rollup` with counters. Run an uncapped scripted tool-then-text run. Assert that `stop_output` is never called and that the rollup count equals the count the same run makes with no cap code. Equivalently, assert the count is 2, as the probe measured at base.

  Spec IDs: NFR-1, INV-17.

R-E4 [Minor] [test quality] vidbyte/agents/spend_cap.py:109-113 — Three message-shape mutants survive the pack and the area suite.

  Evidence:
  ```
  SURVIVED  refusal_no_dedupe ...
  SURVIVED  openrouter_exemption_widened_to_providerless ...
  SURVIVED  question_mark_dropped ...
  ```
  All three show `| 1051 passed`.

  Failure:
  - With `refusal_no_dedupe`, a chain naming the same unpriced model twice prints it twice.
  - With `question_mark_dropped`, a missing part prints as `None:gpt-5.4-mini` instead of `?:gpt-5.4-mini`, the §9.2 shape C3 is told to surface "as it is".
  - With `openrouter_exemption_widened_to_providerless`, a providerless entry is accepted at construction instead of refused. It fails later in `Runner.build()`, so nothing is spent.

  Smallest fix: one parametrized refusal case with a duplicated unpriced fallback, plus one with `provider=None, model_name=PRICED_MODEL`. Both assert the exact message `"…no price for ?:gpt-5.4-mini…"`.

  Spec IDs: INV-13 (the "?" rule), §9.2 rule 6.

## VERIFIED CLAIMS

- The check points are at runtime.py:517 (CP2), :707 (CP4), :1852 (CP3, before `if tool_is_internal` at :1855) and :2087 (CP1, the first clause of `_budget_stop`, called at :368). A fallback switch `continue`s to that same CP1 (:459), and the probe confirms it stops before the backup model.
- Tool calls run one at a time. `max_parallel_tool_calls` is never read in runtime.py (grep is empty). Concurrency comes only from children inside one tool segment. EC-14 accepts this, and the fan-out probe stays inside Σᵢ(C + Gᵢ).
- Construction refusals (probe_construction.py):
  - Refused: image, whisper, tts, sora, embedding and `jev-` primaries; lettered suffixes; unpriced at fallback index 3; image or embedding models as fallbacks; an unpriced or image primary with a priced fallback; MCTS and the three actor runtimes.
  - Accepted: dated and `-latest` suffixes, OpenRouter with a known slug, and `jev` or `infinite_memory` runtimes.
  - `acme` gives `ConfigurationError: Unsupported model provider`. `Runner` normalizes to the `ModelProvider` enum first, so `ModelProvider(runner.provider)` at spend_cap.py:111 cannot raise a raw ValueError.
- The fork tool cannot drop or raise the cap: `max_spend_usd` is in `_inherited_guardrails` (fork.py:345) and not in `_LOOP_SETTING_FIELDS`. A model-chosen `runtime="mcts_search"`, image model or unpriced model on a capped fork is refused at child construction, through the same refusal.
- Every `AgentLoopSettings(` call site in vidbyte/ either carries the cap (base.py:342 and :785, fork.py:157, fork tool :332, loader `**loop_raw`, config.py:687) or is a Jev fixed-prompt agent left uncapped by design (D-18).
- Jev fails closed on a blind or unpriced pre-loop: `require_accounted()` (jev/usage.py:39-58) runs at runtime.py:122 and :219 before delegation. Only the reached case in R-E1 escapes.
- Scale: one `rollup()` plus `cost_measured` costs 0.033 ms at 100 records, 0.28 ms at 1k, 2.9 ms at 10k and 14 ms at 50k. That is negligible against model latency for capped runs.
- Pins: dollar figures are derived through `reference_cost` (which asserts that every reference response is priced) and `assert_price_preconditions`. `JEV_MODEL = "jev-1.13.0"` fails loudly if the pricebook stops pricing it. No count or price is hard-coded in a way a pricebook PR would silently break.
- Security:
  - The added lines contain no key-shaped literal. The only hits are runtime-built `"vb_live_" + "a" * 32` and docs text.
  - New error messages name only agent, provider, model, runtime and counts.
  - Blind causes never include prompt, key or amount (spend_cap.py:72-88).
  - The model never sees the cap (AC-21 test).
  - A tool result cannot change settings.
  - The validator quotes a short string verbatim, including one shaped like a key. That behavior is pre-existing (`validation.py:188-196`, last touched in #1147) and is not this PR's.
- Squash-merge safety: local `origin/main` is 22993b5f, the merge base, so the squash tree equals daad59fb. The full suite on a `git archive` of daad59fb is green: 7671 passed and 20 skipped, with only the settled inherited red deselected.
- `git status --short` in the worktree is empty apart from this report.

## COMMANDS RUN

- `git diff --stat origin/main...daad59fb` → `52 files changed, 6715 insertions(+), 35 deletions(-)`
- `git merge-base origin/main daad59fb; git rev-parse origin/main HEAD` → `22993b5f…`, `22993b5f…`, `78f947e0…`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/loop_spend_cap tests/test_codex_output_contracts.py` → `174 passed in 1.45s`
- Area suite (`probes/area-paths.txt`, 15 paths) on the head archive → `877 passed in 5.09s`
- `py -3.11 probes/mutate.py head` (54 mutants against the pack) → `54 mutants; 48 killed; ['nfr1_rollup_always', 'refusal_skips_primary_in_chain', 'refusal_no_dedupe', 'openrouter_exemption_widened_to_providerless', 'question_mark_dropped', 'providerless_skips_all_checks']`
- `AREA=… py -3.11 probes/mutate.py head <6 survivors> --area` → `{"nfr1_rollup_always": true, "refusal_skips_primary_in_chain": true, "refusal_no_dedupe": true, "openrouter_exemption_widened_to_providerless": true, "question_mark_dropped": true, "providerless_skips_all_checks": true}` (each `1051 passed`)
- `py -3.11 probes/probe_jev_delegation.py` → `JevAgent stop_reason = 'final_response'` / `1.804 x C`; then `'max_spend'` / `2.900 x C`
- `py -3.11 probes/probe_runtime_attacks.py` →
  ```
  OK children_fanout_internal  C=0.009000 spent=0.024720 (2.75xC) stop='max_spend' C+G=0.033300 lookup_ran=False
  OK child_goes_blind[capped]  stop='max_spend' … text="…could not be fully measured: 1 model calls reported no usage."
  OK child_goes_blind[uncapped] stop='max_spend' … unaccounted=2 … "2 model calls reported no usage."
  OK finish_attempt_continuation C=0.009045 spent=0.017670 (1.95xC) stop='max_spend' C+G=0.026295 model_calls=1
  OK retry_after_billed_errors C=0.011250 spent=0.030420 (2.70xC) stop='max_spend' C+G=0.041670 model_calls=5 lookup_ran=False
  OK fallback_switch_after_billed C=0.002030 spent=0.002030 (1.00xC) stop='max_spend' anthropic_calls=1 gemini_calls=0
  ```
- `py -3.11 probes/probe_fail_closed.py` →
  ```
  integrity=corrupted text="…usage recording failed."
  "…no price for openai:gpt-5.4-mini-preview."
  "…no price for openai:gpt-aa-unpriced, openai:gpt-zz-unpriced."
  ```
  Every line shows `lookup_ran=False measured=False complete=False`.
- `py -3.11 probes/probe_construction.py` → see VERIFIED CLAIMS. Final line: `runtime=infinite_memory -> ACCEPTED`
- `py -3.11 probes/probe_slug_refusal.py`, with the two mutants applied and then restored → `restored: True`
- `PYTHONPATH=base|head py -3.11 probes/probe_inv17.py`, then `diff inv17-base.txt inv17-head.txt` → `BASE==HEAD (uncapped): identical`. With `capped-high`, the only differences are in `blind_usage` and `unpriced_response`.
- `py -3.11 probes/probe_rollup_scale.py` → `records= 10000 rollup+cost_measured= 2.874 ms`
- `git diff origin/main...daad59fb | grep "^+" | grep -E "sk-[A-Za-z0-9]|vb_live_|AKIA…"` → only `"vb_live_" + "a" * 32`, `"vb_live_" + "x" * 32`, and two docs lines
- Full suite on the daad59fb archive (deselecting the settled inherited red `test_harness_threads_surface.py::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them`) → `7671 passed, 20 skipped in 256.13s (0:04:16)`, `exit=0`
- R-E1 fix check: the three-line `_delegate` patch on a scratch copy of daad59fb, then `probe_jev_delegation.py` → `JevAgent stop_reason = 'max_spend'`, `specialist model calls = 0`, both variants. The pack, `test_codex_output_contracts.py` and `tests/test_jev*.py` → `618 passed in 5.24s`
- `git status --short` (worktree) → empty before this report was written
