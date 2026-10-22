# S4 findings verifier: agent-reasoning-effort

Inputs read in full: the three lens reports (`S4-review-conformance.md`, `S4-review-conventions.md`, `S4-review-engineering.md`), spec r3, test-plan.md, request.md, `report-formats.md` ("review.md"), house-style.md, AGENTS.md and the field-guide index (plus `review-scope.md`). Code diff: `git diff 98a5d37b...8e773244`. The worktree HEAD is 4aaf0c25, which adds only the lens reports. All probes and scratch trees are in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/r2e-s4/verifier/`, and no other part of the scratchpad was read. The scratch trees are a `git archive 8e773244` copy (`head/`) plus patched copies (`fix-options/`, `fix-algo-param/`, `fix-algo-method/`, `fix-both/`, `mutant/`). Every probe fakes only `HttpTransport.request` with its own recorder, not the pack's `Wire`, and assembles key-shaped strings at run time. No source, test or git state in the worktree was changed.

## 1. Merge map

| Original | Lens severity | Merged | Final severity | Disposition |
|---|---|---|---|---|
| R-E1 | Blocker | R-1 | Blocker | CONFIRMED (fix shape corrected) |
| R-E4 | Major | R-2 | Major | CONFIRMED, `test-coverage`, route test-addition |
| R-C1 | Major | R-3 | Major | CONFIRMED (same root cause as R-E2) |
| R-E2 | Major | R-3 | Major | CONFIRMED (merged into R-C1) |
| R-E3 | Major | R-4 | Minor | DOWNGRADED, `test-coverage`, follow-up test-addition |
| R-V1 | Minor | R-5 | Minor | passed through, trivial |
| R-V3 | Minor | R-6 | Minor | passed through, trivial |
| R-C2 | Minor | R-7 | Minor | passed through, trivial (spec text) |
| R-V2 | Minor | R-8 | Minor | passed through, follow-up (S6) |
| R-V4 | Minor | R-9 | Minor | passed through, follow-up (spec + test pin) |
| R-V5 | Minor | R-10 | Minor | passed through, follow-up (S6) |

R-C1 and R-E2 share one root cause: the same line, `vidbyte/lib/runners/utility.py:134`, and the same failure. R-E2 adds the AUTO, non-text and survived-mutant evidence, so the merged row keeps both. No other pair shares a root cause. R-E4 and R-3 touch the same condition (`utility.py:137`) but fail differently: one is a missing test, the other wrong code. They stay separate and are linked in the niche facts.

Ordering: R-1 is the only Blocker. Among the Majors, R-2 needs only a test parametrization and R-3 a three-line code change plus tests, so R-2 comes first (smallest fix first within a tier).

## 2. Verification of each Blocker and Major

### R-1 (R-E1): algorithms that build their own runners drop a set effort. CONFIRMED, Blocker

**Code read.** The algorithms build these runners:
- `multi_provider_agentic_grader.py:96`: `p_runner = ModalityDetector.create_runner(modality=ModelModality.TEXT, provider=provider_name, model=model_name, api_keys=handle.api_keys, mode=handle.model_mode)`, swapped in with `handle.with_runner(p_runner, provider_name)` (:98).
- `:152`: the grader runner, built the same way.
- `independent_critic.py:214-220`: built when `reviewer_provider` is set.
- `prosecutor_defender_judge.py:250`: built when a stage sets both provider and model.

`ModalityDetector.create_runner` has no effort parameter, and the diff leaves it unchanged. Two further facts:
- `git grep -n "with_runner(" -- vidbyte` lists exactly these four sites plus `fallback.py:161`, which carries the effort. No other path swaps the agent's runner.
- `git grep` for `create_runner(`, `Runner(` and `TextModelRunner(` outside `vidbyte/lib/runners` finds no other text-runner construction in agents or context.

The guard (`vidbyte/agents/reasoning_effort.py`) reads only `runner_config` and `fallback`. It runs at `base.py:262`, before `self.algorithm` is resolved at `:284`. `ContextWindowAlgorithm.__post_init__` (`vidbyte/context/algorithms/tool_results.py:59-63`) allows at most one algorithm, so the algorithms have no precedence problem.

**Executed** with `probe_algorithms.py`, output in `probe_algorithms.out`. The agent is DIRECT `openai/gpt-5.5` with `high`:

```
[control: no algorithm]   -> https://api.openai.com/v1/responses model=gpt-5.5 effort=('reasoning', {'effort': 'high'})
[MPAG openai/gpt-5.5 + anthropic/claude-sonnet-5, grader openai/gpt-5.5] constructed OK
[MPAG …]   -> https://api.openai.com/v1/responses model=gpt-5.5 effort=None
[MPAG …]   -> https://api.anthropic.com/v1/messages model=claude-sonnet-5 effort=None
[MPAG …]   -> https://api.openai.com/v1/responses model=gpt-5.5 effort=None
[MPAG default grader gpt-4o (a no-row id)]   -> https://api.openai.com/v1/responses model=gpt-4o effort=None
[independent_critic reviewer anthropic/claude-haiku-4-5 (high is a refused cell)] constructed OK
[independent_critic reviewer …]   -> https://api.anthropic.com/v1/messages model=claude-haiku-4-5 effort=None
[independent_critic, no reviewer (reuses the producer handle)]   -> …/responses model=gpt-5.5 effort=('reasoning', {'effort': 'high'})   (×2)
[prosecutor_defender_judge, prosecutor stage anthropic/claude-sonnet-5]   -> https://api.anthropic.com/v1/messages model=claude-sonnet-5 effort=None
```

The critic and PDJ runs end in `AgentExecutionError`, because the probe's plain replies do not satisfy their report schemas. Every request had already been sent and recorded by then.

**Spec reading.**
- **INV-3** (spec.md:165): "A set effort is never silently ignored. It is either sent exactly as the table says, or refused with ConfigurationError." The probe shows a set effort neither sent nor refused, on the agent's own `gpt-5.5`, whose row lists `high`.
- **G-1** (spec.md:48): "Every generative call the agent makes in `TextModelMode.DIRECT` then carries it". Violated.
- **The TL;DR** (spec.md:19) calls "never silently ignored" "the decision that matters most".
- **Part B outranks Part C** (spec.md:157).

**Is the spec claim the lens names false?**
- **A-8** (spec.md:1197) ends: "So actor and algorithm side calls run on the agent's own text runner and model, which the guard has checked." This is **false**. Its proof covers only actor calls (the `model_name` keyword dropped by `_call_with_supported_kwargs`). The probe shows the three algorithms calling `claude-sonnet-5`, `gpt-4o` and `claude-haiku-4-5` on runners they built. The guard never checked those models: `claude-haiku-4-5` at `high` is a refused cell, and `gpt-4o` has no row, yet both constructed.
- **The §9.2 "Every agent" row** (spec.md:453: "context-window side calls and algorithm side calls through the agent's own `RunnerHandle` | yes (same runner)") is **not literally false**. It is true for the calls it names, which my critic-without-reviewer case confirms. But the table is incomplete: it has no row for runners an algorithm builds. Its `ModalityDetector` row (spec.md:463, "no; `Runner` refuses an effort for a non-text type") is justified only for non-text runner types, so it does not settle text runners built by an algorithm. Both rows must be corrected together with A-8.

**Settled decisions and scope.**
- None of the settled decisions covers context-window algorithms: DIRECT only, the table, INV-8, D-6, the Jev exclusions, no new FailureCode, A-4, Q-1..Q-10 at No, row 34.
- NG-10 lists other unsupported agent types, and for each one the spec makes the failure loud (a `TypeError`, or the YAML unknown-key refusal), not silent.
- request.md §C says "Every agent, through the shared path … the user's constraint is only that it reaches every agent's generative model", and D-P9 says "must not silently ignore".
- So the requested behavior is wrong without a fix, and the scope rule's "stated limitation" exit does not apply (briefing §4 item 4).
- JevAgent has no algorithm field (`grep algorithm vidbyte/agents/jev/settings.py vidbyte/agents/jev/agent.py` is empty), so the C5 contract is not affected.

**Is refusal at construction the smallest consistent fix?** Yes in substance, but not in the lens's shape.
- **Refusal versus forwarding.** INV-3 offers exactly two outcomes, sent or refused. INV-4 requires the refusal at construction. D-2 is the precedent for refusing an effort that cannot be sent instead of stripping it. Forwarding the effort into the algorithm runners is larger: a new keyword on `ModalityDetector.create_runner` in lib, an effort carried on `RunnerHandle`, and the guard extended to each algorithm model. It also cannot meet INV-4. The preset `ContextWindow.preset.multi_provider_agentic_grader` has `provider_models=None`, and `ProviderModelRegistry.resolve_active` then picks the models from the environment at run time (`vidbyte/lib/registries/models.py:274-279`, `:418-429`). So forwarding is `[scope-adding]` and belongs in a Q, as the lens says.
- **The lens's shape fails a pinned test.** The lens proposed adding an `algorithm` parameter to `refuse_unsupported`, but the test-plan pins that signature. I applied that shape to a scratch copy (`apply_fix_algorithm.py fix-algo-param param`) and ran the pack:

  ```
  >       assert list(parameters) == ["agent_name", "runner_config", "fallback"]
  FAILED tests/features/agent_reasoning_effort/test_agent_reasoning_effort_contract.py::test_the_guard_is_a_keyword_only_static_method
  1 failed, 702 passed in 3.89s
  ```

  The repair agent may not edit that test.
- **The smaller, test-compatible shape** is a second static method on `AgentReasoningEffortGuard` and one statement after `base.py:284` (`apply_fix_algorithm.py fix-algo-method method`):
  - pack, pins and modality routing: `703 passed in 3.73s`;
  - `probe_algorithms.py` against that tree: the MPAG cases, both critic-with-reviewer cases and the PDJ stage case are `REFUSED at construction`; the control and the critic without a reviewer still send `('reasoning', {'effort': 'high'})`.
- **Budget.** `git diff --numstat 98a5d37b...8e773244 -- vidbyte/agents/base.py` is `13 2`, net +11, so the extra line makes +12, which is within NFR-7 ("at most 12"). There is no new file, class, root name, dependency or FailureCode, so the change stays within the §8.4 budget. INV-18 holds, because the new call sits after the spend-cap refusal.
- **Naming.** Name the algorithm by its fixed key, as the runtime classes' `name` attributes do (`multi_provider_agentic_grader`, `independent_critic`, `prosecutor_defender_judge`), not by `ContextWindowAlgorithm.name`, a required free-form field (`tool_results.py:47`).
- **Copy paths.** Fork passes the algorithm to the child (`fork.py:83`) and restore takes one (`base.py:589`). Both construct through `__init__`, so both are covered.

**Severity.** Blocker. A public, documented configuration gives a wrong result: the agent runs at the vendor default while billed as if the developer's `high` applied, with no signal. That violates the spec's headline invariant.

### R-2 (R-E4): only image runners pin the non-text refusal. CONFIRMED, Major, `test-coverage`

- The test (`test_agent_reasoning_effort_refusals.py:599-621`) builds only `gpt-image-2`.
- My mutant V-N05 (`mutate.py`) on a scratch copy changes `utility.py:137` to `if self.reasoning_effort is not None and runner_type == "image":`. Result: `V-N05 non-text refusal only for image runners: SURVIVED exit=0 703 passed in 3.79s` (control `CONTROL exit=0 703 passed in 3.79s`).
- Today's code is correct: the keyword form is refused for `gpt-image-1` and, through the same branch, for the other types.

AC-16 reads "resolving to a non-text runner type", so the test under-covers its own acceptance criterion. It stays Major rather than Minor because R-3's repair rewrites this exact condition. Without a four-type test, a regression made during that repair would pass the pack.

Route: S2 test author. The repair agent never edits tests.

### R-3 (R-C1 + R-E2): `Runner(options={"reasoning_effort": ...})` drops the effort. CONFIRMED, Major

**Code.**
- `utility.py:134`: `options["reasoning_effort"] = self.reasoning_effort`, written unconditionally inside the text branch.
- `:137`: the refusal reads only `self.reasoning_effort`.
- `:144`: the options are filtered to the config's fields.

**Executed** with `probe_options.py` at HEAD (`probe_options.out`):

```
[options high, DIRECT] BUILT TextModelRunner config.reasoning_effort=None config.temperature=None
[options high, DIRECT]   -> https://api.openai.com/v1/responses 'reasoning' in body=False reasoning=None
[options minimal (refused cell), DIRECT] BUILT TextModelRunner config.reasoning_effort=None …
[options high, AUTO (default mode)] BUILT TextModelRunner config.reasoning_effort=None …
[options high, AUTO (default mode)]   -> https://vidbyte-backend.onrender.com/api/v1/models/generate 'reasoning' in body=False
[keyword high, AUTO (control)] REFUSED: TextModelConfig sets reasoning_effort, but TextModelMode.AUTO sends calls through the Vidbyte gateway, …
[options temperature 0.4 (precedent)] BUILT TextModelRunner config.reasoning_effort=None config.temperature=0.4
[options high, image model gpt-image-1] BUILT ImageModelRunner …
[options high, audio model tts-1] BUILT AudioModelRunner …
```

**Existing guards.** None. `TextModelConfig` receives `None`, and the non-text field filter drops the key. The agent paths are not affected, because their options carry only `timeout_seconds` (`base.py:1688`, `fallback.py:204`).

**Spec reading.**
- INV-3 names `Runner` explicitly: "never dropped by `Runner`".
- Row 9(b) (spec.md:1024) prescribes the unconditional line. Part B outranks Part C, and the row did not consider an effort that arrives through `options`.

**Deviation judged.** The briefing's deviation 5, and S3 report :334, say the line overwrites "as `mode` and `api_keys` already are". This is rejected. Those two always hold a value (`model_mode` defaults to AUTO, and `api_keys` is always the matched record). `None` here means unset, which is the case `temperature` handles at `:142-143` by overwriting only when the keyword is set.

**Fix verified.** I applied `apply_fix_options.py` to a scratch copy. The line moves above the text branch as `if self.reasoning_effort is not None: options["reasoning_effort"] = self.reasoning_effort`, and `:137` reads `options.get("reasoning_effort")`. Results:
- pack, pins and modality routing: `703 passed in 3.67s`;
- `probe_options_fixed.out`: `options high, DIRECT … reasoning={'effort': 'high'}`; `options minimal` REFUSED with the `TextModelConfig` capability text; `options high, AUTO` REFUSED with the mode text; image and audio REFUSED with the Runner text; the keyword control and the `temperature` precedent are unchanged;
- `ruff check vidbyte/lib/runners/utility.py --select C901,PLR0912,PLR0915,I001,F401` gives the same single (single-file) I001 line at head and with the fix, and no complexity finding.

This fix is smaller than the engineering lens's ternary, and in it the keyword still wins over an options key.

**Test pins.** My V-N06 mutant (`options["reasoning_effort"] = self.reasoning_effort if … else options.get(...)`) `SURVIVED … 703 passed`, so no test pins either behavior, and the fix breaks no test.

## 3. Downgrade

**R-4 (R-E3), Major → Minor.** The mutant is real: `V-N22 restore drops the effort when fallback_models is stored: SURVIVED exit=0 703 passed in 3.76s`. Two facts support the downgrade:
- Today's code is correct. `probe_restore_chain.py` printed:

  ```
  checkpoint runtime_config keys: {'reasoning_effort': 'high', 'fallback_models': ['anthropic/claude-sonnet-5'], 'model_mode': 'direct'}
  restored effort: high
  -> https://api.openai.com/v1/responses reasoning= {'effort': 'high'} output_config= None
  -> https://api.anthropic.com/v1/messages reasoning= None output_config= {'effort': 'high'}
  ```

- The restore line (`base.py:612`) is one unconditional expression shared by single and chained restores, so the mutant needs an artificial new branch.

So the gap would change no behavior, and Q-4, the only planned change near it, defaults to No. It stays a confirmed test gap, routed to S2 as a follow-up test addition, but it does not hold the verdict.

## 4. Minors passed through

I checked each Minor's anchor for accuracy only:
- **R-V1:** the header lines at `fallback.py:10-11`, `agents.py:9` and `model_configs.py:6,8` are as quoted.
- **R-V3:** README:89-93 omits grok `xhigh`.
- **R-V4:** my probe prints "resolves to a image runner" and "resolves to a audio runner".
- **R-V2 and R-V5:** these are history and lint-window facts, and I took them as the lens states them.
- **R-C2:** spec.md:1066 against :408, :173 against the §8.5 texts, and :207 against :306 are as quoted.

## 5. Severity blind spots (step 6)

I checked the four places the briefing named:

1. **A payload path with no attach.** `git grep` of `payload = {` and of the `_create_*payload` methods in `vidbyte/providers` finds text payloads only in the four builders (`openai.py:255`, `anthropic.py:57`, `gemini.py:61`, `compatible.py:61`). `openrouter.py:56` calls `super()`, and xai's only override is the image payload. Nothing new.
2. **A silent drop outside D-6.** Found: R-1 (algorithms) and R-3 (options). Nothing else:
   - `TextModelRunner.arun` re-creates the config with `dataclasses.replace` and keeps the effort (`text.py:71-78`).
   - `BaseAgent` takes no developer-supplied runner.
   - JevAgent has no algorithm.
3. **A construction path that bypasses the guard.**
   - Fork (`fork.py:83`) and restore (`base.py:589`) reach `__init__`.
   - A `runner_config` replaced after construction is refused at runner build (engineering's `probe_switched.py`).
   - A `ContextWindowAlgorithm` assigned after construction is a post-construction mutation, the same class as a replaced `runner_config`. Under R-1's fix it would go unguarded, but that is not a supported path, so it is not a finding.
4. **Refusal-text drift.** Conformance checked 24 texts exactly, and the pack's `==` comparisons pass (`703 passed`). R-1 needs a new §8.5 text, which the orchestrator must fix before S2 writes tests.

**Cross-lens interaction.** No convention fix breaks conformance. R-9 (R-V4, the "a image" wording) edits the same message line (`utility.py:139`) that R-3 rewrites at `:137`, and its test pin is the one R-2 parametrizes. If the orchestrator takes R-9, it belongs in the same spec-steer and S2 pass.

I add no `[verifier]` finding. The blind-spot work found nothing new; it changed the R-1 fix shape instead (the pinned-signature trap).

## 6. Disagreements between reviewers, adjudicated

- **Conventions SOUND against conformance and engineering MERGEABLE AFTER FIXES.** These are not in conflict. The conventions lens had no behavioral scope, and its claims (lint, placement, comments) are consistent with the other two lenses.
- **Conformance R-C1 against engineering R-E2 on the fix.** Conformance proposed a temperature-style conditional plus an `or` in the refusal. Engineering proposed a ternary `effort` variable. Both are correct. My version is smaller (one conditional moved above the branch, and the refusal reads `options`), and I verified it in a scratch copy.
- **Engineering R-E1's fix against the test pin.** The lens did not check `test_the_guard_is_a_keyword_only_static_method`. I adjudicated against its shape with the red run in §2.
- **Conformance claimed "every agent, Jev and config path conforms to spec r3".** That is true against the spec's own §9.2 table, which is the incomplete part (see R-1). The conformance lens was not wrong to read the table literally. The gap fell between the lenses, as the briefing predicted.

## 7. Commands run (final lines)

Every Python command uses `py -3.11` with `PYTHONDONTWRITEBYTECODE=1` and an inline `PYTHONPATH` (the worktree, or the scratch tree under test). In this table, S is the verifier scratch folder.

| # | Command | Final lines |
|---|---|---|
| 1 | Worktree: `py -3.11 -m pytest -q -p no:cacheprovider tests/features/agent_reasoning_effort tests/features/sdk_managed_text/test_managed_text_selection.py tests/features/sdk_provider_keys/test_provider_keys_contract.py tests/test_agent_modality_routing.py` | `703 passed in 2.66s` |
| 2 | `py -3.11 S/probe_algorithms.py` (worktree) | see §2 R-1; `MPAG … effort=None` ×3 |
| 3 | `py -3.11 S/probe_options.py` (worktree) | see §2 R-3; `[options high, DIRECT] … 'reasoning' in body=False` |
| 4 | `git archive 8e773244 \| tar -x -C S/head`; `py -3.11 -I S/apply_fix_options.py S/fix-options`; the pack from row 1 in `S/fix-options` | `703 passed in 3.67s` |
| 5 | `py -3.11 S/probe_options.py` (in `S/fix-options`) | `[options high, DIRECT] … reasoning={'effort': 'high'}`; `[options high, audio model tts-1] REFUSED: Runner sets reasoning_effort, …` |
| 6 | `ruff check vidbyte/lib/runners/utility.py --config lint/ruff.toml --select C901,PLR0912,PLR0915,I001,F401 --no-cache` (head and fix-options) | `Found 1 error.` (the same single-file I001) at both |
| 7 | `py -3.11 -I S/apply_fix_algorithm.py S/fix-algo-param param`; the pack | `FAILED …::test_the_guard_is_a_keyword_only_static_method` / `1 failed, 702 passed in 3.89s` |
| 8 | `py -3.11 -I S/apply_fix_algorithm.py S/fix-algo-method method`; the pack | `703 passed in 3.73s` |
| 9 | `py -3.11 S/probe_algorithms.py` (in `S/fix-algo-method`) | 5 own-model cases `REFUSED at construction`; critic without a reviewer `effort=('reasoning', {'effort': 'high'})` ×2 |
| 10 | `py -3.11 -I S/mutate.py` | `CONTROL exit=0 703 passed in 3.79s`; V-N22, V-N05 and V-N06 `SURVIVED exit=0 703 passed` |
| 11 | `py -3.11 S/probe_restore_chain.py` (worktree) | `restored effort: high`; openai hop `{'effort': 'high'}`; anthropic hop `output_config= {'effort': 'high'}` |
| 12 | `git diff --numstat 98a5d37b...8e773244 -- vidbyte/agents/base.py` | `13	2	vidbyte/agents/base.py` |
| 13 | Full test tree on `S/fix-both` (both fixes): `py -3.11 -m pytest -q -p no:cacheprovider tests` | `8340 passed, 20 skipped in 276.39s (0:04:36)`. The scratch tree has no `.git`, so the two inherited merge-base reds skip, as in CI. |
| 14 | `git grep -n "with_runner(" -- vidbyte`; the `create_runner(` and `Runner(` greps; the provider payload greps | 4 algorithm sites + `fallback.py:161`; text payloads only in the 4 builders |
