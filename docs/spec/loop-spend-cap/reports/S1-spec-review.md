VERDICT: SOUND WITH FIXES — The meter, check points, and stop reason are well placed, but two Blockers would let spend continue after "the cap stopped the run": a root-exported agent class silently accepts the cap and ignores it, and six existing run-ending checks retry or review a cap stop with fresh, uncapped budgets. Both fixes are small additions to §12.3.

WHAT THE SPEC GETS RIGHT
- CP3 runs as the first statement of `_enforce_tool_settings`, before `if tool_is_internal: return None` (`vidbyte/agents/runtime.py:1836`). This binds the internal launch tools and leaves `_process_tool_call` untouched (ruff C901 = 10, measured; adding a call there would break S008).
- Reusing `FailureCode.RESOURCE_EXHAUSTED` (`vidbyte/lib/enums/failure.py:130`, which no code produces today) keeps the `FailureCode` pins and the 733-name contract byte-identical. Only `_STOP_CODES` gains an entry, and `_append_stop_failure` keeps its exact details (`vidbyte/sessions/failure/router.py:112-131`).
- `cost_measured` is a derived property that leaves `cost_complete` and `cost_usd` unchanged (INV-2, INV-19). It treats an empty ledger as measured and makes a blind meter fail closed (INV-4(b)). That is the right shape for a hard limit.
- The fork tool treats the cap as a guardrail the model cannot override (`_inherited_guardrails`, `vidbyte/tools/builtins/fork/fork.py:334-343`). The cap stays out of the schema and out of the prompt (D-12, D-14), which closes the obvious T-2 path.

FINDINGS (ranked)

R-1 [Blocker] [L5/L8] §6.1 INV-13, §9.2 table, §12.3 — `CodexHarnessAgent` accepts `max_spend_usd` and silently never enforces it
  Evidence:
  - `CodexHarnessAgent` is a root export (`contracts/sdk-public-api.json`, 1 match).
  - Its constructor validates `settings.loop` with `CodexContractValidator.validate`. That validator refuses only the names in the fixed tuple `CODEX_UNSUPPORTED_LOOP_FIELDS` (`vidbyte/lib/constants/codex.py:336-349`, iterated at `vidbyte/agents/codex/contracts.py:82-89`). `max_spend_usd` is not in the tuple, and the spec never mentions Codex (a `grep -n "Codex" spec.md` finds only the INV-21 and §13 pins).
  - Probe `scratchpad/r3-s1-review/codexprobe.py` set `max_spend_usd = 1.0` on an `AgentLoopSettings` and ran it through `CodexContractValidator.validate`. It printed `ACCEPTED: max_spend_usd=1.0 passes Codex validation silently`.
  - `tests/test_codex_output_contracts.py:396-411` pins `set(cases) == set(CODEX_UNSUPPORTED_LOOP_FIELDS)`.
  Failure: `CodexHarnessAgent(CodexHarnessAgentSettings(loop=AgentLoopSettings(max_spend_usd=5)))` builds and runs Codex with no spend check at all. This is the worst outcome this review looks for: the caller, and a CLI printing "capped at $5", believe a limit exists. INV-13's sentence "No other agent accepts the setting without enforcing it" is false.
  Smallest fix:
  - Add a §12.3 row that appends `"max_spend_usd"` to `CODEX_UNSUPPORTED_LOOP_FIELDS`. The existing message then names the field, and construction raises `CodexAgentError` (a root name).
  - Add a §9.2 table row: "`CodexHarnessAgent`: refused at construction".
  - Because the set-equality pin would turn red, the same row must add `"max_spend_usd": 1.0` to the `cases` dict at `tests/test_codex_output_contracts.py:396-409`. List it as the one allowed edit to an existing test, and change "Every test file" under "Deliberately not changed" to match. If §14 must forbid every test edit, check `max_spend_usd` explicitly in `CodexContractValidator.validate` instead, next to the tuple, so the constant and its pin stay unchanged.
  - Add an AC that expects the Codex refusal.

R-2 [Blocker] [L8/L4/L5] §12.3, §6.1 INV-5/INV-6, EC-21..EC-23, FR-9 — `MAX_SPEND` slips past every existing `@intent middleware-abort-ends-the-run` check, so a cap stop gets reviewed, graded, or retried with fresh budgets
  Evidence: Each of these sites ends the run only for `MIDDLEWARE_ABORT`, and two of the intent comments name "a spend ceiling" as the reason:
  - `vidbyte/context/algorithms/reflexion.py:93-95` (`should_reflect`)
  - `vidbyte/agents/algorithms/independent_critic.py:73-76`
  - `vidbyte/agents/algorithms/prosecutor_defender_judge.py:400-403`
  - `vidbyte/agents/algorithms/multi_provider_agentic_grader.py:63-67`
  - `vidbyte/agents/multi/transfer.py:186-195`
  - `vidbyte/agents/multi/orchestrator.py:207-209`

  The spec adds `MAX_SPEND` only to `_STOP_CODES` and `_BUDGET_STOP_REASONS` (FR-9, §12.3 rows 11-12), and lists `vidbyte/agents/algorithms/*` as deliberately unchanged.
  Failure, per path:
  - **Independent critic:** after the producer stops with `max_spend`, the critic still renders the stop text as the candidate and runs a whole reviewer runtime (`independent_critic.py:80`, `:96-111`). That runtime's `AgentRuntimeConfig` has no cap (`:115-135`). If review normalization then fails and `failure_policy` is not `RETURN_CANDIDATE`, the cap stop surfaces as an `AgentExecutionError` (`:86-89`) instead of `max_spend`.
  - **Prosecutor-defender-judge:** runs its whole debate the same way.
  - **Grader:** grades stop texts.
  - **MultiAgent:** a worker's `max_spend` is not in `OUTPUT_DELIVERABLE_STOP_REASONS`, so it becomes `worker_stopped` with `retryable=True` (`transfer.py:192-196`). `ledger.py:140` then retries it while `attempts < max_attempts`, and every retry is a new reply with a fresh cap. An orchestrator phase that stopped on the cap re-sends the prompt as a parse retry (`orchestrator.py:200-212`), again with a fresh cap.

  The CLI would report "stopped by the cap" while the SDK keeps spending.
  Smallest fix: Add one §12.3 row per site. Each row widens the existing check to `stop_reason in (MIDDLEWARE_ABORT, MAX_SPEND)` (by `.value` where the site compares strings) and adds one line to its `@intent` comment.
  - In `transfer.py`, a `max_spend` worker becomes `TaskStatus.BLOCKED` with a `TaskBlocker(code="max_spend", retryable=False)`, just as the abort branch does.
  - Leave `orchestrator.finalize` alone, because `tests/multi_agent/test_manager_middleware_abort.py:64,228-235` iterates every non-answer stop through it.
  - Rewrite EC-21, EC-22, and EC-23 so that nothing reviews, grades, reflects on, or retries a cap stop.
  - Add `test_worker_stop_report.py`'s explicit `STOPPED_REPLIES` to the S2 facts, because it is a dict and does not pick up new members (A-3 does not cover it).

R-3 [Major] [L1/L5] §15 Q-2/Q-11, D-5, INV-9 — An unpriced model is discovered only after a paid call, and the blind-stop text names no cause the user can act on
  Evidence:
  - request.md:57 recommends refusing a capped run "whose configured model has no price ... before any spend".
  - The provider, model, and fallback chain are all known at construction (`vidbyte/agents/base.py:186-201`), and `ModelPricingRegistry.resolve` is pure (`vidbyte/lib/registries/pricing.py:333-358`). A probe pricing an unknown model returned `None`.
  - D-5's argument covers only what a construction check cannot catch (OpenRouter-reported prices, child models, calls with no usage). It does not show that the check is unsafe.
  - Q-11 labels this check `[scope-adding]`, but the request contained it.
  - The text for condition (b) in INV-9 is a fixed literal. The repo already names causes in this situation: `JevAgentUsage.unpriced` lists `provider:model` (`vidbyte/agents/jev/usage.py:39-91`).
  Failure: A user sets `--max-spend 5` on a model the pricebook lacks. The first model call runs and is paid; its size is bounded only by `max_tokens`. The run then stops with "spend could not be fully measured". The user cannot tell whether the cause was the model, a provider that reported no usage, or a recording fault. Every retry spends again and fails the same way.
  Smallest fix:
  - Remove `[scope-adding]` from Q-11 and make its default **Yes**, in addition to D-5. A capped agent refuses at construction when its primary model or any fallback model resolves to no price and the provider is not OpenRouter. The error is `ConfigurationError` naming `provider:model`. Keep the mid-run fail-closed for everything else.
  - Make the condition-(b) text name the cause, computed from the rollup: the unpriced `provider:model` pairs, "N calls reported no usage", or "usage recording failed". Names only, so T-3 still holds.

R-4 [Major] [L7/L1] §6.1 INV-3, EC-11, A-1, §9.2 rule 3 — A billed call that failed without a usage payload leaves `cost_measured` True, so C3 would call an incomplete bill complete
  Evidence:
  - The runtime records a failed attempt only when the error carries `details["usage"]` (`vidbyte/agents/runtime.py:787-793`). A timeout, a network failure, or an edge 5xx calls neither `_record` nor the unaccounted counter (`vidbyte/agents/pricing/tracker.py:87-96`).
  - The gateway's own messages say "no response arrived ... and Vidbyte may already have billed the call" (`vidbyte/lib/http/vidbyte_gateway.py:86-90`). They also say "Under relay the wallet pays only Vidbyte's fee" (`:112`), and that fee is never metered (the file contains no usage handling).
  - INV-3's list has three items and contains neither of these. Rule 3 tells C3 that a True value means "the whole SDK-rated spend of every call ... the meter can see".
  Failure: A capped run with retried timeouts reports `cost_measured=True` and a figure below what was billed. The CLI then prints a complete-looking total that understates the bill. The cap also stops later than its number implies.
  Smallest fix:
  - Add to INV-3's list, and to the README wording W-9: "a failed model call whose error carried no usage (timeout, network failure, gateway 5xx), which a provider or Vidbyte may still have billed; Vidbyte's relay fee".
  - Reword rule 3 to say "as rated by the SDK at list price; excludes failed calls that returned no usage and any Vidbyte fee".
  - Restate A-1 as a known limitation, not as "not verified".
  - Optionally add Q-13 `[scope-adding]`, default No: count a model error with no usage as an unaccounted call, so the cap fails closed on it.

R-5 [Major] [L1/L10/L4] §9.2 "Caller contract for vidbyte-cli C3", D-15, Q-12 — Using only root names, C3 cannot apply the contract as written, and the contract misses two stop shapes
  Evidence:
  (a) Rule 6 names `AgentExecutionError`, which is not in `contracts/sdk-public-api.json`. The CLI's lint C028 allows root names only (`vidbyte-cli/lint/rules/c028_sdk_public_surface_only.py`). D-15 says the runner type "is resolved only in `_runner_for_model` at run time". In fact `resolve_runner_type` reads only `runner_config.provider` and `model_name` (`vidbyte/lib/runners/utility.py:54-70`, `vidbyte/agents/base.py:1659-1674`), so the type is known at construction.
  (b) Rules 5 and Q-12 classify by `type(exc).__name__`. The CLI's own convention is "Only the closed code is read" (`vidbyte-cli/src/vidbyte_cli/services/resolve/sdk.py:34-73`). `UsageAccountingError` already carries a closed code, `error_kind = "usage_accounting"` (`vidbyte/lib/errors/base.py:564`).
  (c) For an agent with `output_schema`, a cap stop leaves `structured` as None, and `_assert_schema_satisfied` raises `OutputSchemaViolationError(stop_reason="max_spend")` (`base.py:1060-1076`, a root export). The spec never mentions it, so rule 1 never fires.
  (d) Rule 4 classifies the stop with `get_usage()`, which also includes drained replies and `after_run` spend (EC-20, EC-36). A drained reply that goes blind turns a "reached" stop into "meter went blind".
  (e) No rule tells C3 what it may promise.
  (f) A capped JevAgent refuses any specialist without its own cap (D-13), but C3's obligation to set each specialist's cap never appears in the contract.
  Failure: C3 either imports a non-root name and fails C028, or misses cap stops in schema runs and misclassifies blind stops. It might also print "max spend $X" as a ceiling on the bill, which INV-6 explicitly does not guarantee (EC-14: 10 swarm helpers, each up to C).
  Smallest fix:
  - Move the non-text refusal to `BaseAgent.__init__`, beside the runtime refusal, so that rule 6 reduces to "`ConfigurationError` from the constructor".
  - Rule 5: classify by `getattr(exc, "error_kind", None) == "usage_accounting"`, and close Q-12 as not needed.
  - Rule 1: add "or `OutputSchemaViolationError` with `.stop_reason == "max_spend"`".
  - Rule 4: classify by `reply.metadata["usage_rollup"]`, not by `get_usage()`.
  - Add rule 7: "describe the flag as a threshold checked between steps, never as a maximum bill; concurrent children can each spend up to the cap (INV-6)".
  - Add rule 8: "when building a capped JevAgent with specialists, set each specialist's `max_spend_usd` ≤ the cap".

R-6 [Major] [L5] §6.3 EC-35, §10 T-4 — A second concurrent reply on one agent object erases the first reply's spend and its blind state, so the first cap fails open
  Evidence: Every reply calls `self._usage_tracker.reset()` at its start (`vidbyte/agents/base.py:923`). `reset()` clears the records, the operations, `_recording_corrupted`, and `_unaccounted_calls` (`vidbyte/agents/pricing/tracker.py:195-200`).
  Failure: Run A spends 0.9 C, then run B starts on the same object. Run A's next check sees about 0 and keeps spending. If run A's meter had gone blind, B's reset makes it read as measured. EC-35's claim, "each run's cap sees the combined spend", is false. Only the spend since the most recent reset by either run is visible.
  Smallest fix:
  - Correct EC-35 and T-4 to describe the reset behavior.
  - State "use one capped agent object per concurrent run" as a limitation in the README section (W-9) and §9.2.
  - Optionally add Q-14 `[scope-adding]`, default No: a capped agent refuses a second concurrent reply.

R-7 [Major] [L7/L5] §10 T-2, EC-20, Q-9 — The model can enqueue prompts that run after a cap stop, each with a fresh cap
  Evidence: `vidbyte/tools/builtins/run_prompts_sequentially.py:67` is a model-facing tool that calls `agent.enqueue_prompts`. After the primary reply returns, even with `max_spend`, `_drain_queued_prompts` runs every queued prompt as its own reset reply (`vidbyte/agents/base.py:1026-1027`, `:1186-1220`). T-2 traces only the fork tool.
  Failure: A prompt-injected model on an agent with that tool queues N prompts. After the cap stops the primary reply, the run spends up to N × (C + G), and C3's `get_usage()` reports a total above the cap that the user set.
  Smallest fix:
  - Add this path to T-2 and to §9.2 rule 7 (R-5).
  - Split Q-9 so that "skip the drain when the primary reply stopped with `max_spend`" is its own `[scope-adding]` question with default No. It is one condition at `base.py:1026`, and a reviewer recommends Yes.

R-8 [Minor] [L1] §15 Q-10, NG-11 — Q-10 answers a question the request delegated to the author, but labels it `[scope-adding]`
  Evidence:
  - request.md:53 asks the author to find "every loop that enforces `max_tokens` and `max_tool_calls`" and to "decide, citing the code, which of those loops must also enforce the cap".
  - The critic and PDJ reviewer runtimes are such loops (`independent_critic.py:115-135`, `prosecutor_defender_judge.py:242`), and both share `usage_tracker=self.runtime.usage_tracker`.
  Failure: The decision is recorded as a user scope choice. A reviewer started below the cap can run its whole loop past it.
  Smallest fix: Drop the label and decide on the evidence. Passing `max_spend_usd=self.runtime.config.max_spend_usd` into each reviewer config is one keyword per site, and exact, because the tracker is shared. If the author still declines, keep the limitation as written.

R-9 [Minor] [L10] §13 (line 772), NG-4, EC-11 — The ledger rates DeepSeek at one rate; there is no time-of-day pricing
  Evidence:
  - `vidbyte/lib/registries/pricing.py:131-135` says "The cost formulas have no clock, so PROVIDER_PRICING carries the peak rate".
  - Nothing outside that entry reads `tier_rates`.
  - A probe rated deepseek-v4-flash at 1M input plus 1M output tokens: $1.50 under any clock.
  Failure: S2 is told that "a threshold check on DeepSeek must cross the cap at both rates". That leads to clock-dependent tests that cannot fail. NG-4's argument that the rate is "unknown before the call" is also wrong for the ledger.
  Smallest fix: §13: "always rated at the peak rate (`pricing.py:131-135`)". Drop "time-of-day" from NG-4, and in EC-11 say that an off-peak invoice is lower than the rated figure, so the cap is conservative.

R-10 [Minor] [L10] §6.1 INV-14, §9.2 messages — Two claims about the validator are inaccurate
  Evidence: A probe of `RecordFieldValidator.require_number` (`vidbyte/lib/dataclasses/validation.py:96-103`) showed:
  - `10**400` raises `OverflowError` from `math.isfinite`, not `ConfigurationError`;
  - `5e-324` is accepted.

  The §9.2 sample message shows users "at most 1.7976931348623157e+308".
  Failure: INV-14's sentence "Anything else raises `ConfigurationError`" is false, so a test written from it would fail. A CLI that echoes the message shows a meaningless maximum.
  Smallest fix:
  - INV-14: "an `int` beyond float range raises `OverflowError`".
  - §9.2: accept the message as it is, or note that C3 should validate `--max-spend` itself before it builds the settings.

VERIFIED CLAIMS
- Check-point lines are correct:
  - `_budget_stop` is called at `runtime.py:367` and defined at `:2046`;
  - `if not tool_calls:` is at `:513`, with the `max_tokens` stop at `:514-522`;
  - the fallback `continue` is at `:459`;
  - `record_call` is at `:477`, `after_iteration` at `:690-698`, and `_after_tool_iteration` at `:699-700`;
  - `_enforce_tool_settings` is at `:1834`, with the internal early return at `:1836`.
- The context-window hook runs before CP1 (`:350-366`), as the "Iteration tail" segment states.
- A-5 holds. ruff C901 measures `_enforce_tool_settings` 6, `_budget_stop` 5, `_run_direct` 3, `AgentRuntimeConfig.__post_init__` 4, and `_process_tool_call` 10. A scratchpad probe (`c901probe.py`) confirmed that boolean operators add nothing.
- A-2 holds (no import cycle in `validation.py`). A-4 holds (C019 does not match the `max_spend` literals).
- The root contract has 733 exports. `RESOURCE_EXHAUSTED` exists and no code produces it. `AgentExecutionError`, `VidbyteSdkError`, and `UsageAccountingError` are not root exports; `ConfigurationError`, `OutputSchemaViolationError`, and `CodexAgentError` are.
- The before-text in `docs/design/release-0-4-0.md:17` matches verbatim, with exactly 1 match.
- The fork details are as stated: `_LOOP_SETTING_FIELDS` (`fork.py:52-63`), `_inherited_guardrails` (`:334-343`), and `AgentForker._loop_settings` (`vidbyte/agents/fork.py:150-173`). `_LOOP_FIELDS` is at `vidbyte/lib/dataclasses/config.py:92-98`.
- Jev delegation returns before the loop (`jev/runtime.py:129-130`, `:215-221`). The continuation keeps the config (`:274`). `_require_metered_specialists` is the right pattern (`jev/agent.py:113-125`).
- INV-18 holds: `CostBudgetMiddleware` coexists unchanged.
- The pricebook's gpt-5.4-mini rate is 0.75 / 4.5 / 0.075 (`pricing.py:168`). A probe priced 1M input plus 1M output tokens at $5.25.
- `tests/features/harness_threads/test_harness_threads_surface.py:270-278` is the inherited local red, as described.
- Baselines:
  - `PYTHONPATH=$(pwd) py -3.11 lint/run.py` printed `SDK-LINT: PASS`;
  - the earlier focused suite: 350 passed;
  - the pinned files (codex contracts, session failures, manager abort, grader, fork tool, worker stop report): `163 passed in 2.13s`.
- Found false or incomplete:
  - INV-13's "no other agent" (R-1);
  - EC-35 (R-6);
  - D-15's "only at run time" (R-5a);
  - the DeepSeek claims in §13 and NG-4 (R-9);
  - INV-14's "anything else" (R-10);
  - INV-3's completeness (R-4).
