# S1 spec author report: loop-spend-cap, revision 1

- **Spec:** `docs/spec/loop-spend-cap/spec.md`, committed as `a246ef08` on `feat/loop-spend-cap`. The parent is `6db4207e`, which sits on `base_commit` `22993b5f`.
- **Stage:** S1 spec author, run R3 (PR 3 of 8).
- **Date:** 2026-10-20.

## 1. What I read

**Pipeline inputs**
- `request.md` (§A–§D), `pipeline.md`, `context/code-map.md` (all four sections), `reports/S0-scout.md`.
- `docs/design/release-0-4-0.md`. This is the only file under `docs/` that I read outside this spec folder.

**Repo rules**
- `AGENTS.md`, in full.
- `REPO_MAP.md:109`, `:199` and `:203`.
- `vidbyte/agents/README.md`, read to the end (30,375 characters).
- `vidbyte/agents/jev/README.md`, around `:24` (17,723 characters).
- `llms.txt:728-751`.
- `skills/failure/vocabulary.md:98-108`.

**Field guide** (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`)
- `init.md`, then the entries that apply:
  - `strict-config-dataclasses.md`
  - `blocking-lint-invariants.md`
  - `runtime-boundaries.md`
  - `comment-format.md`
  - `jev-capability-layout.md`
  - `local-ci-verification.md`
- I checked the remaining entries against the change and set them aside, because the fork tool's schema does not change and no fallback trigger is added: `model-facing-tool-contracts.md`, `fallback-coordination.md`, `priced-operation-execution.md`.

**Code, read at the symbol level**

The meter:
- `vidbyte/agents/pricing/tracker.py`: `record_call`, `_record`, `merge`, `rollup`, `reset`.
- `vidbyte/agents/pricing/records.py`: `UsageRollup`, `UsageRecord`, `OperationUsageRecord`, `UsageRecordingIntegrity`.
- `vidbyte/lib/registries/pricing.py`: rates, tiers, Jev rates, `resolve`.
- `vidbyte/agents/pricing/openrouter.py`.
- `vidbyte/lib/runners/decision.py`.
- `vidbyte/lib/usage_ledger.py`.

The loop:
- `vidbyte/agents/runtime.py`, all of these:
  - `_arun_once` from `:297` to `:700`, and the retry loop `:726-839`;
  - `_finish_result`, `_with_run_state_metadata`;
  - `_render_loop_settings_block`;
  - `_process_tool_call`, `_enforce_tool_settings`, `_tool_settings_budget_stop`;
  - `_budget_stop`, `_stopped_result`, `_runtime_metadata`, `_cost_spent_usd`.
- `vidbyte/agents/base.py`, all of these:
  - `__init__` refusals `:216-248`;
  - `_export_loop_settings`, `_restore_loop_settings`;
  - `generate_reply`, `_generate_reply`, `_merge_usage_into`;
  - the drain `:1186-1220`;
  - `_run_direct`, `_run_non_text_runner`, `_runner_for_model`.

Settings and records:
- `vidbyte/agents/settings/loop.py`.
- `vidbyte/lib/dataclasses/agents.py`: `AgentRuntimeConfig`, `AgentStopReason`, `AllowedToolNames`.
- `vidbyte/lib/dataclasses/validation.py`: `require_number`, `_received`, imports.
- `vidbyte/lib/dataclasses/config.py`: `_LOOP_FIELDS`, `:686`.
- `vidbyte/lib/config/loader.py:204-221`.
- `vidbyte/lib/dataclasses/model_configs.py`: `credentials()`.

Jev:
- `vidbyte/agents/jev/runtime.py`, `agent.py`, `usage.py`, `response.py`, `settings.py`, `bulk_work.py`.
- `vidbyte/agents/jev/compute/`: `clone.py`, `swarm.py`, `swarm_tool.py`.
- The fixed-prompt helpers: `brief/writer.py`, `done/handoff.py`, `done/reviewer.py`, `done/run_state.py`, `gate/clarification.py`.

Other agents and algorithms:
- `vidbyte/agents/infinite/agent.py`, `launch.py`.
- `vidbyte/agents/multi/agent.py`, `aggregation.py`.
- `vidbyte/agents/fork.py`, `vidbyte/tools/builtins/fork/fork.py`.
- `vidbyte/agents/algorithms/`: `independent_critic.py`, `prosecutor_defender_judge.py`, `reflexion.py`, `multi_provider_agentic_grader.py`.
- `vidbyte/agents/runtimes/search.py`, `actor/broker.py`.

Routing, evals and contracts:
- `vidbyte/sessions/failure/router.py`.
- `vidbyte/lib/enums/failure.py`.
- `vidbyte/evals/behavior/efficiency.py`, `stop.py`.
- `vidbyte/lib/constants/outputs.py`.
- `vidbyte/middleware/builtins/cost_budget.py`.
- `vidbyte/agents/contracts/floors.py`.
- `contracts/sdk-public-api.json`.

Lint rules:
- A001, A002, A006, A007, C001, C002, C006, C008, C019, S008, S024.
- How the baseline gate works (`lint/run.py`, `lint/baseline.json`).

**Tests read for seams and pins**
- `tests/features/harness_threads/test_harness_threads_surface.py`, `tests/test_session_failures.py`, `tests/test_fork_tool.py`, `tests/test_agent_runtime.py`, `tests/test_jev_usage_ledger.py`.
- `tests/features/sdk_loop_settings/test_contract.py`.
- `tests/features/sdk_model_usage/test_nested_usage_bill.py`, `test_usage_contract.py`.
- `tests/agent_test_support.py`.
- The three tests that iterate `AgentStopReason`, and the codex_host `FailureCode` slice pins.

**What I ran on the base** (`22993b5f`, with `origin/main` at the same commit)
- `lint/run.py`: `SDK-LINT: PASS`. No rule REGRESSED, and seven were IMPROVED from pre-existing slack.
- Seven focused test targets: 350 passed.
- The harness pins, manager-abort, output-connector and grader tests: 92 passed.
- `rollup()` cost: 0.27 ms at 1,000 records and 2.65 ms at 10,000.
- A C019 simulation on `"max_spend"` and `"max_spend_usd"`: no finding.
- Ruff C901 for every host function the design touches.

I did not run the full `run_ci.py`.

## 2. Approaches weighed

### Chosen design

`AgentLoopSettings.max_spend_usd`, carried into `AgentRuntimeConfig.max_spend_usd`, enforced by a stateless `AgentSpendCap.stop_output(cap, rollup)` in a new module `vidbyte/agents/spend_cap.py`. Four thin call sites in `AgentRuntime` apply it:

| Check point | Where |
|---|---|
| CP1 | `_budget_stop` |
| CP2 | the plain-text finish branch |
| CP3 | `_enforce_tool_settings`, before the early return for internal tools |
| CP4 | before `_after_tool_iteration` |

The rest of the design:
- A run stops with `AgentStopReason.MAX_SPEND` when measured spend is at or above the cap, or when the meter is blind.
- Blindness is defined by the derived property `UsageRollup.cost_measured`.
- Sessions route the stop to the existing `RESOURCE_EXHAUSTED` code.
- Agents that cannot enforce the cap refuse it: non-linear runtimes and Jev specialists at construction, non-text runners at run start.

### Rejected alternatives

1. **One clause in `_budget_stop`**, about 5 lines with no new file. This is the smaller design I rejected. It runs every tool in the response after the cap is reached (swarm, bulk work, sub-agents), plus the whole finish attempt (Jev done checks, a fresh-continuation run) and the compute checkpoint. Because `cost_usd` sums only priced records (`tracker.py:185`, `:251-260`), it also never stops an unpriced run. And it leaves MCTS, actor runtimes, non-text runners and specialists silently ignoring the cap. It fails INV-4(b), INV-5, INV-6 and INV-13.
2. **That clause plus a check inside `_process_tool_call`.** Ruff measures `_process_tool_call` at C901 10, exactly at the S008 limit, so one more branch adds an S008 finding and the lint gate fails. I moved the check into `_enforce_tool_settings`, which is at C901 6, ahead of its early return for internal tools. That is why the spend check runs first at every check point (D-9).
3. **A ledger-reading middleware**, for example a priced variant of `CostBudgetMiddleware`. A middleware cannot be set through `AgentLoopSettings`. `MiddlewareContext` carries no cumulative cost. A stop would end as `middleware_abort`, which the router maps to TERMINAL/STOP, not to a budget stop. No middleware hook brackets internal tools or the compute checkpoint.
4. **Re-pointing `CostBudgetMiddleware` at the ledger.** This changes an existing budget's behavior, which hard rule NG-5 forbids. I kept the two meters side by side (D-4).
5. **A new `FailureCode.RUNTIME_MAX_SPEND`.** Appending it fails `test_harness_threads_surface.py:224-227` in CI. Inserting it mid-enum fails `:228-236` locally. `RESOURCE_EXHAUSTED` already exists in the right vocabulary section and has no producer (D-6).
6. **A construction-time refusal when the main model has no pricebook entry** (the request's Q2 default). It is not necessary: OpenRouter reports its own price. It is not sufficient either: fallback models, child models and calls with no usage all escape it. I chose fail-closed at run time instead (D-5). A construction check stays available as the optional Q-11.
7. **A `metadata["spend_measured"]` key** in place of `cost_measured`. It would appear on every result, the session-details pin forbids growing that dict, and C3 already reads `UsageRollup` (D-7, D-17).
8. **`Decimal` in place of `float`.** Every USD figure in the repo is a float. The measured accumulation error is about 1e-12 relative (D-2).

### Lint-driven placement, verified on the base

- `AgentLoopSettings` may not contain `raise ConfigurationError` (C001, baseline 26). The field is therefore validated at assignment through `RecordFieldValidator.require_number`, the way `allowed_tools` uses `AllowedToolNames`.
- The new file needs the A001-complete header in the shape of `validation.py`. The "Context Protocol Header" style of `loop.py` and `records.py` is existing debt and should not be copied.
- C002 rules out a second bool guard, so completeness is a derived `@property`.

## 3. Disagreements with the request, with evidence

1. **Wrong `UsageRollup`.** `request.md:46` and D-P6 (`request.md:155`) cite `UsageRollup.cost` in `vidbyte/lib/dataclasses/sessions.py:127-135`. That is the after-the-fact session rollup, built from history with caller-supplied flat prices (`vidbyte/sessions/usage.py:15-24`). The live, priced ledger the cap must read is `vidbyte/agents/pricing/records.py:68-89`, `UsageRollup.cost_usd`, produced by `UsageTracker.rollup()`. D-P6 itself stands. Only its citation is wrong.
2. **The Q3 premise.** The `per_agent` breakdown exists only on the session rollup (`sessions.py:135`). Child spend reaches the parent through `UsageTracker.merge`, once, when the child's reply finishes (`base.py:882-886`).
3. **The Q4 premise is false.** "Billed by the Vidbyte gateway, not priced by the SDK's provider rates" (`request.md:59`) is wrong:
   - The SDK prices `jev-1.13`, `jev-latest` and `jev-preview` (`pricing.py:304-314`).
   - `DecisionModelRunner` records every decision call as `UsageKind.DECISION` into the active ledger (`decision.py:46-55`).
   - Inside a JevAgent run, that ledger is the agent's own tracker (`jev/usage.py:33-37`).

   So decision calls count immediately. Whether the gateway charges exactly that rate is assumption A-1.
4. **The Q5 premise is false.** "A run can exceed the cap by at most one call" (`request.md:60`) holds only for a run with no tools, no children, no context algorithm and no algorithm. Spend also lands in these places:
   - inside one tool call (a whole child-agent tree, concurrent ones included);
   - inside one finish attempt (Jev done checks, run-state, handoff and reviewer agents, a fresh continuation);
   - at the compute checkpoint (clones);
   - in the Jev pre-loop phases;
   - in algorithm steps (reflexion, the grader, critic and judge sub-runtimes);
   - in `after_run` middleware.

   The true bound is in spec INV-6: the cap plus the largest single segment, and the sum over N concurrent capped children.
5. **The Q2 default was replaced.** Counting unknown spend as 0 is exactly "capped" unmeasured spend, which the briefing forbids. Refusing at construction is neither necessary nor sufficient (point 6 of §2). The spec fails closed at the next check point instead (D-5).
6. **"Every loop that enforces `max_tokens`/`max_tool_calls`"** (`request.md:53`, which names `fork.py`, `jev/runtime.py` and `floors.py`). None of those three enforces anything:
   - `fork.py` copies settings, so it is a silent-drop site and is fixed in §12.3 row 7.
   - `jev/runtime.py` widens limits with `replace(self.config, **limits)` (`:274`), which keeps the cap.
   - `floors.py` is a contract floor that reads the middleware estimate.

   Enforcement exists only in `runtime.py`, which code-map §2B agrees with.
7. **"`loop.py:11`"** (`request.md:56`) is docstring text. The validators are at `loop.py:102-118`. On top of that, C001 forbids adding another validator of that kind to the settings class.
8. **The failure code.** `request.md:40` says the stop works "with failure code `RUNTIME_MAX_TOKENS` in `failure.py:120`". The runtime sets only `AgentStopReason`. The session router assigns the `FailureCode` later (`router.py:36-51`, `:118`), and an unmapped reason silently becomes `RUNTIME_ERROR`. The spec adds the router entry (row 11).

## 4. Disagreements with the scout, with evidence

1. **`stop.py` predicates.** code-map.md:182 says `vidbyte/evals/behavior/stop.py` "has one predicate per reason". It has predicates for only three reasons (`:55-65`: max_iterations, max_tool_calls, max_tokens), with none for timeout or any other reason. No `did_not_hit_max_spend` is needed. The budget set the eval must learn about is `efficiency._BUDGET_STOP_REASONS` (`efficiency.py:31-43`).
2. **The C019 question is resolved.** The scout left it open (S0-scout.md:154). The rule's own header (`c019_platform_error_code_contract.py:9`) places two-token codes below its three-token shape, and my simulation on both literals found nothing. This is kept as assumption A-4, with a fallback.
3. **Lint traps the scout missed:**
   - C001 forbids raising in `AgentLoopSettings`.
   - `_process_tool_call` is exactly at C901 10, so the obvious place for CP3 regresses S008.
   - The new module must carry the A001 header, not the house "Context Protocol Header" style.

   These three decided the placement of CP3, the shape of the validation, and the header.
4. **Silent-drop sites the scout did not list:** the fork tool's `_inherited_guardrails`, chosen over `_LOOP_SETTING_FIELDS` so the model cannot raise its own cap, and `config.py` `_LOOP_FIELDS`. The scout's list (code-map §4.3) covered `to_runtime_config`, `__repr__`, `_export_loop_settings` and `AgentForker`.

## 5. Assumptions I am least sure of

1. **A-1: the SDK rate equals the charge.** The pricebook dates from `PRICING_AS_OF = "2026-10-11"`, and OpenRouter reports its own cost. I have not verified that the gateway (default `TextModelMode.AUTO`) bills exactly the pricebook rate. If it does not, C3 must say "as measured by the SDK", not "billed". This affects the CLI's user-facing wording, not the cap's behavior.
2. **A-5: the S008 complexities hold after the edit.** Ruff gives `_enforce_tool_settings` 6, `_budget_stop` 5, `_run_direct` 3 and `AgentRuntimeConfig.__post_init__` 4. Each gains one branch, which stays under the limit of 10 if ruff counts as I expect.
3. **A-2: no import cycle** from `vidbyte/lib/dataclasses/agents.py` importing `RecordFieldValidator`. `validation.py` imports only three lib modules, and `lib/dataclasses/middleware.py` already imports it. The package `__init__` order has not been exercised.
4. **Line budget (NFR-5).** My estimate is about 33 added lines in `runtime.py` and 13 in `base.py` once 72-column comments are included. I set the targets at 40 and 20 rather than 30 and 15.
5. **AC-1 seam.** The §4 snippet runs in AUTO mode, which needs `VIDBYTE_API_KEY` and goes through `VidbyteGatewayTransport`. The S2 test author must script gateway-shaped responses on the `HttpTransport.request` seam. That is feasible, but no existing test does it for a plain `Agent`.
6. **Template rule on file paths.** The template says file paths appear only in §11 and §12, but the user's brief asks for a `path:line` citation on every claim. I kept every *design* location in §8 and §9 as a dotted module name. I kept the `path:line` *evidence* citations throughout, as the brief asks. A reviewer may read the template more strictly.

## 6. Counts

| Item | Count |
|---|---|
| Goals and non-goals | G 4, NG 11 |
| Invariants | INV 22 |
| Acceptance criteria | AC 26 |
| Edge cases | EC 37 |
| Requirements | FR 10, NFR 7 |
| Decisions | D 17 |
| Threats | T 4 |
| Work items | W 9 |
| Assumptions | A 7 |
| Questions | Q 12, 0 blocking (6 marked `[scope-adding]`, all defaulting to no) |
| §12.3 rows | 17 (1 CREATE, 16 MODIFY) |

**Complexity budget:**

| Item | Count |
|---|---|
| New files | 1 |
| New classes | 1 |
| New dependencies | 0 |
| New config keys | 1 |
| New tables | 0 |
| New endpoints | 0 |
| Public additions | 1 enum member, 1 property, 1 keyword. No root name. |

---

## Addendum: r2 (review round 1), 2026-10-20

**Commit:** `d49469ee` "docs(spec): revise loop-spend-cap spec to r2 (review round 1)". It changes only `spec.md` (frontmatter `revision: 2`, `updated: 2026-10-20`).

**Dispositions** (full rows in spec §16):

| Finding | Disposition | Where it landed |
|---|---|---|
| R-1 Blocker (Codex ignores the cap) | accepted | `CODEX_UNSUPPORTED_LOOP_FIELDS` gains `max_spend_usd` (row 25). The set-equality pin `tests/test_codex_output_contracts.py:411` forces a one-entry `cases` edit, assigned to the S2 test author (row 26). The validator has no special case. INV-13, EC-39, AC-27. |
| R-2 Blocker (cap stop gets reviewed, graded, retried) | accepted, plus one site the review missed | Rows 18–23 widen every `@intent middleware-abort-ends-the-run` site. Row 24 adds `InfinitePair._status` (`infinite/launch.py:335-344`): a cap-stopped generator was PARTIAL, so its verifier ran. `finalize` is untouched. INV-23, FR-11, D-19, AC-28, AC-29, EC-42. |
| R-3 Major (unpriced model found after a paid call) | accepted | `AgentSpendCap.model_refusal` runs in `BaseAgent.__init__`. It refuses non-text runners and unpriced configured primary or fallback models; OpenRouter is exempt. The run-time blind stop stays as the fallback and names `provider:model`. Q-11 is answered Yes. |
| R-4 Major (usage-less failed calls) | accepted | INV-3, rule 3, A-1 (now a known limitation), EC-38. Q-13 `[scope-adding]`, default No. |
| R-5 Major (C3 contract uses non-root names, misses stop shapes) | accepted | Rules 1–9 rewritten: `OutputSchemaViolationError.stop_reason`, `usage_rollup` for the stop reason, `error_kind == "usage_accounting"`, constructor-only refusals, threshold-not-a-bill, specialist caps, one agent object per concurrent run. Q-12 closed. |
| R-6 Major (concurrent reset fails the cap open) | accepted as a stated limitation | EC-35, T-4, INV-11, rule 9, README row. Q-14 `[scope-adding]`, default No. |
| R-7 Major (queued prompts after a cap stop) | accepted (orchestrator: in scope) | The drain's `while` gains one condition (`base.py:1195`); `_generate_reply` (C901 10) is untouched. EC-20, EC-41, AC-31, T-2. Q-9 reworded. |
| R-8 Minor (Q-10 label) | label accepted; capping reviewers declined on code | D-18: a reviewer's cap stop becomes a parsed review or a stage failure (`independent_critic.py:80-89`, `:111`; `prosecutor_defender_judge.py:513-522`), never a `max_spend` result. Q-10 struck through. |
| R-9 Minor (DeepSeek) | accepted | Always rated at the peak rate (`pricing.py:131-135`). §13, NG-4, and EC-11 are fixed. |
| R-10 Minor (validator claims) | accepted | INV-14 states both measured results. §9.2 tells C3 to validate `--max-spend` itself. |

**What I measured for r2** (ruff C901/PLR0912/PLR0915, thresholds 10/12/50, on `base_commit`):
- `_structured_phase` 6/6/20; `default_report_parser` 4/3/10; `InfinitePair._status` 3/3/4; `should_reflect` 2; critic `arun` 4; grader `arun` 3 and `_run_provider_trial` 2; `_drain_queued_prompts` 6/7/29.
- `BaseAgent.__init__` (17/17/87) and `AgentRuntime._arun_once` (45/44/167) are already flagged, so lines added there add no finding.
- Baseline tests over the r2 files: `429 passed in 8.23s`. The files were `tests/test_codex_output_contracts.py`, `tests/multi_agent`, `tests/test_algorithms_honor_middleware_abort.py`, `tests/features/infinite_memory_agent`, `tests/test_reflexion_algorithm.py`, and `tests/test_independent_critic_algorithm.py`.

**Counts after r2:**
- INV 23, AC 32, EC 42, FR 11, NFR 7, D 19, Q 14 (Q-10 withdrawn), and W 10.
- §12.3 has 26 rows: 1 CREATE, 24 MODIFY by the implementer, and 1 test edit by S2.
- The §8.4 budget is unchanged.

**Self-check:**
- The ID cross-reference script finds no undefined ID, and every AC is served by a W row.
- The spec contains no key-shaped literal.
- Every table has a consistent column count under GFM rules. A pre-existing raw pipe in row 14 was rewritten.
- There is exactly 1 CREATE row.

**Notes for the round-2 reviewer:**
- `MultiAgentOrchestrator` is a Protocol. The class edited in row 23 is `MagenticOneOrchestrator`.
- The auto-handoff still runs after a cap stop, by design (INV-23 last paragraph). It writes a handoff note about the stopped run.
- A capped test agent now needs a priced configured model to construct (§13).
