---
spec: loop-spend-cap
title: An optional USD spend cap that every agent's own loop enforces
status: draft            # draft | approved | tests-written | implemented | reviewed | verified | pr-open | abandoned
revision: 1
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-loop-spend-cap
branch: feat/loop-spend-cap
base_commit: 22993b5fcc4c45048fb0d5c5e0e4538601b854d9
created: 2026-10-19
updated: 2026-10-19
pr:                      # filled at S3 (draft) and finalized at S6
---

# Spec: An optional USD spend cap that every agent's own loop enforces

> **TL;DR** — `AgentLoopSettings` gains `max_spend_usd`, an optional USD cap. The shared agent loop checks it against the run's own live ledger (`UsageTracker`) before every model call, every tool call, every finish attempt, and the after-tool-iteration hook. It stops the run with the new stop reason `AgentStopReason.MAX_SPEND`, and stops just as hard when the meter goes blind. A new read-only property, `UsageRollup.cost_measured`, tells a caller such as vidbyte-cli C3 whether the reported `cost_usd` is the whole measured bill or only a lower bound. The decision that matters most: the cap is a metered hard limit with a stated overshoot bound, not a promise that spend never exceeds the number. Spend the meter cannot see is never called capped, and an agent that cannot enforce the cap refuses it before any spend.

## §0 User prompts

### 0.1 Invoking request (verbatim)
/spec-pipeline I like this and I agree with the setup, can you start building it into the vidbyte-cli/.

### 0.2 User replies during the run
_None yet. The orchestrator appends any reply the user sends during the run here verbatim, labeled with the revision it produced._

---

## Part A — Framing

## §1 Goal

The user asked for a universal `max_spend` and said "i want every agent to be tracking usage, figure out the best way to do this" (request.md §A Prompt 3, Q7). The program decided (D-P6, request.md §C.2) that the SDK meters and enforces, and the CLI owns the option. This PR is the SDK half. Today no agent loop can stop itself on money:

- `AgentLoopSettings` (`vidbyte/agents/settings/loop.py:49-67`) has no USD field.
- The runtime's budget stop (`vidbyte/agents/runtime.py:2046-2089`) checks iterations, tokens, tool calls, and wall-clock only.
- The only USD ceiling, `CostBudgetMiddleware` (`vidbyte/middleware/builtins/cost_budget.py:36-84`), multiplies tokens by a caller-supplied flat rate. It never reads the priced ledger the SDK already keeps.

| ID | Goal (outcome) | How we will know | Source |
|---|---|---|---|
| G-1 | A developer, or vidbyte-cli on a user's behalf, sets one USD number on any agent's loop. The run then stops itself once the spend the SDK measured for that run reaches the number. | `AgentLoopSettings(max_spend_usd=x)` stops a priced run with `stop_reason == "max_spend"` (AC-4..AC-7). | request.md §C "This run's scope"; Prompt 3 Q7 "max_spend" |
| G-2 | A caller can read from the run's result that the cap stopped it, what the run spent, and whether that figure is complete. The CLI can then say "your run stopped at $X", and an agent driving the CLI can decide what to do next. | The caller contract in §9.2 holds (AC-1, AC-8, AC-19). | request.md §C "The run's result must also say plainly…"; briefing §1 |
| G-3 | "Every agent" holds. Each agent either enforces the cap, or refuses it before spending anything. No agent accepts the cap and then ignores it. | The per-runtime table in §9.2 holds (AC-11..AC-13). | Prompt 3 Q7 "i want every agent to be tracking usage"; request.md §C "Every agent" |
| G-4 | Unmeasured spend is never presented as capped or complete. A capped run whose meter goes blind stops. | `cost_measured` is False whenever the meter missed something (AC-19). A capped run stops at the next check point after a blind call (AC-8, AC-9). | briefing; request.md §C Q2 |

## §2 Objective

When this PR merges, vidbyte-sdk `main` contains the following:

- An optional `max_spend_usd` field on `AgentLoopSettings`. It is validated as a finite USD amount greater than 0. It is carried into `AgentRuntimeConfig` and through every path that copies loop settings: export and restore, YAML `agent.loop`, `AgentForker`, and the model-facing fork tool (as a guardrail the model cannot override).
- A new focused module, `vidbyte.agents.spend_cap`. Its class `AgentSpendCap` decides, from a `UsageRollup`, whether a capped run must stop and with which text.
- Four thin call sites in `AgentRuntime` that apply that decision.
- The new stop reason `AgentStopReason.MAX_SPEND`. Sessions route it to the existing `FailureCode.RESOURCE_EXHAUSTED`, and the efficiency eval treats it as a budget stop.
- The derived property `UsageRollup.cost_measured`.
- Construction-time or run-start refusals wherever the loop cannot enforce the cap: the four non-linear runtimes, non-text runners, and JevAgent specialists that carry no cap of their own.
- Documentation of all of it in the agents and Jev folder READMEs, the `llms.txt` bundle, the failure vocabulary skill, and the unreleased 0.4.0 release record (§12.3 rows 13–17).

The version stays 0.4.0. No root export, `FailureCode` member, or dependency is added. This is PR R3 of 8. The CLI option `--max-spend` that maps to this field is C3 (NG-1).

## §3 Non-goals

- **NG-1** — Any vidbyte-cli change, including `--max-spend`. — *Why not:* that is PR C3 (request.md §C "Not in this run").
- **NG-2** — Reasoning effort. — *Why not:* PR R2.
- **NG-3** — Backend or gateway-side caps, such as research `max_cost_cents` or the gateway's daily cap. — *Why not:* "backend caps" are excluded (request.md §C "Not in this run"). Bring-your-own-key spend never reaches the backend (D-P6).
- **NG-4** — A pre-call cost estimate or budget reservation, which would refuse a call that *might* cross the cap. — *Why not:* `[scope-adding]` (request.md §C Q5). Output tokens and some rates (tier and time-of-day, `vidbyte/lib/registries/pricing.py:136,162,239`) are unknown before the call. See Q-7.
- **NG-5** — Any change to `CostBudgetMiddleware`, the `cost_spent_usd` contract counter (`runtime.py:2174-2181`), `MinCostSpent` (`vidbyte/agents/contracts/floors.py:144-183`), `UsageRollup.cost_complete`, or the behavior of any existing budget. — *Why not:* "changing what any existing budget does" is excluded (request.md §C).
- **NG-6** — A team-wide cap on `MultiAgent` or `AggregateAgent`, or one budget shared across concurrent children. — *Why not:* neither class accepts loop settings (`vidbyte/agents/multi/agent.py:55-83`, `vidbyte/agents/aggregation.py:225-240`), and the conversation asked for neither. The gap is stated in §6.3 and offered as Q-8.
- **NG-7** — Showing the cap or the running spend to the model. — *Why not:* the runtime already keeps `timeout_seconds` out of the prompt for the same reason (`runtime.py:1679-1701`). A number in a prompt invites the model to argue with it (D-14).
- **NG-8** — A new `FailureCode` member, a new root export, a version change, tagging, or publishing. — *Why not:* the harness pins make a new code red (`tests/features/harness_threads/test_harness_threads_surface.py:218-241`, D-6). The request prefers reusing existing root names (request.md:64). D-P2 fixes the version.
- **NG-9** — A flat `max_spend_usd=` keyword on `BaseAgent` or `Agent`. — *Why not:* `REPO_MAP.md:109` says "A new configurable behavior for agents should be added as a setting here rather than as another constructor parameter."
- **NG-10** — Rewriting `JevUsageAccount.failures()` (`vidbyte/agents/jev/usage.py:73-81`) on top of `cost_measured`. — *Why not:* it is a refactor of working Jev code. Both apply the same three-condition rule, and converging them is a follow-up.
- **NG-11** — Capping drained queued prompts against the primary reply's cap, carrying the cap into the critic and prosecutor-defender-judge reviewer sub-runtimes, or copying JevAgent's cap onto its specialists. — *Why not:* none was requested. Each is a stated limitation (§6.3) with an optional `Q-n` whose default is no.

## §4 Developer usage

```python
from vidbyte import Agent, AgentLoopSettings, AgentStopReason

cap = 0.50
agent = Agent(
    name="researcher",
    system_prompt="Answer directly.",
    provider="openai",
    model_name="gpt-5.4-mini",
    agent_loop_settings=AgentLoopSettings(max_spend_usd=cap),
)
reply = agent.run("Summarize the open issues in this repository.")

usage = agent.get_usage()            # vidbyte.UsageRollup for this run
spent = usage.cost_usd or 0.0        # USD the SDK measured for this run
if reply.metadata["stop_reason"] == AgentStopReason.MAX_SPEND.value:
    if usage.cost_measured:
        print(f"stopped at ${spent:.4f}: reached the ${cap:.2f} cap")
    else:
        print(f"stopped: spend could not be fully measured (at least ${spent:.4f})")
else:
    print(f"finished; spent ${spent:.4f}" + ("" if usage.cost_measured else " or more"))
```

The developer sets one number and reads three things that already exist on every run: `stop_reason`, `cost_usd`, and the new `cost_measured`. They no longer have to estimate spend with a flat token rate, or poll `get_cost_usd()` from outside the loop. A cap the agent cannot enforce fails loudly before spending.

## §5 Flow diagram

```mermaid
flowchart TD
  A["AgentLoopSettings(max_spend_usd)"] -->|RecordFieldValidator.require_number| B["to_runtime_config()"]
  B -->|AgentRuntimeConfig.max_spend_usd| C["BaseAgent.__init__"]
  C -->|non-linear runtime + cap| X1["ConfigurationError"]
  C --> D["generate_reply: ledger scope, tracker reset"]
  D --> E["_run_direct"]
  E -->|non-text runner + cap| X2["ConfigurationError → AgentExecutionError"]
  E --> F["AgentRuntime._arun_once loop"]
  F --> CP1["CP1 _budget_stop → _spend_cap_stop"]
  CP1 -->|pass| M["model call → usage_tracker.record_call"]
  M -->|no tool calls| CP2["CP2 _spend_cap_stop before finish work"]
  M -->|tool calls| CP3["CP3 _enforce_tool_settings → _spend_cap_stop, per call"]
  CP3 -->|pass| T["tool runs; child replies merge into tracker"]
  T --> CP4["CP4 _spend_cap_stop before _after_tool_iteration"]
  CP4 -->|pass| F
  CP1 & CP2 & CP3 & CP4 -->|"AgentSpendCap.stop_output(rollup) is text"| S["_stopped_result(MAX_SPEND)"]
  S --> R["reply.metadata: stop_reason=max_spend, usage_rollup"]
  R --> FR["FailureMetadataNormalizer: resource.exhausted, EXHAUSTED/ROUTE"]
```

```mermaid
sequenceDiagram
  participant P as Parent runtime (cap C)
  participant L as Parent UsageTracker
  participant K as Child agent (own tracker, same cap if inherited)
  P->>L: CP3 rollup() — under C, measured
  P->>K: tool call starts child reply
  K->>K: child loop checks its own tracker against its own cap
  K-->>L: merge(child rollup) once, in finally (base.py:882-886)
  P->>L: next check point rollup() — child spend now visible
  P-->>P: stop with MAX_SPEND if measured ≥ C or not cost_measured
```

Validation happens at the boundary, when `AgentLoopSettings` and `AgentRuntimeConfig` are constructed. Refusals happen at construction for runtimes and Jev specialists, and at run start for non-text runners, because the runner type is resolved only then (`base.py:1659-1674`). State changes only in the existing ledger, through `record_call`, `record_billed_failure`, `record_operation`, and `merge`. The cap code reads `rollup()` and never writes. The runtime catches a stop at the four check points, and the result flows through the same `_finish_result` path (`runtime.py:945-969`) that every budget stop uses. The sequence diagram shows the timing that sets the overshoot bound: a child's spend becomes visible to the parent only when the child's reply finishes.

---

## Part B — Behavior (this is the spec; everything else is framing)

## §6 Behavior

**Terms used below.**
- *Measured spend* is `rollup.cost_usd` from the running agent's own `UsageTracker` at the moment of a check. A `None` value counts as zero spend.
- *The meter is blind* when `rollup.cost_measured` is False.
- *A check point* is one of CP1–CP4, defined in INV-5.
- *A segment* is everything the run spends between one passing check and the next check.

### 6.1 Invariants

**What is measured**

- **INV-1** — Measured spend is the SDK-rated USD cost of the records in the agent's own tracker. That covers:
  - every main model response (`runtime.py:477`);
  - every billed failed attempt (`runtime.py:793`);
  - every context-window side call (`runtime.py:1049`);
  - every priced search or fetch operation (`runtime.py:1388`);
  - every Jev decision call made while the agent's ledger is active (`vidbyte/lib/runners/decision.py:46-55`);
  - reflexion and grader calls (`vidbyte/agents/algorithms/reflexion.py:133`, `multi_provider_agentic_grader.py:164`);
  - the rollup of every child agent reply, merged once when that child's reply finishes (`vidbyte/agents/base.py:882-886`, `vidbyte/agents/pricing/tracker.py:133-166`).

  Nothing else is measured. "Rated" means priced by the SDK pricebook (`PRICING_AS_OF = "2026-10-11"`, `vidbyte/lib/registries/pricing.py:58`) or by a provider-reported cost (OpenRouter, `vidbyte/agents/pricing/openrouter.py:45-56`). It is not the provider's invoice (A-1).
- **INV-2** — `UsageRollup.cost_measured` is True exactly when all four of these hold:
  - `recording_integrity is UsageRecordingIntegrity.INTACT`;
  - `unaccounted_call_count == 0`;
  - every `UsageRecord` in `calls` has `cost_usd is not None`;
  - every `OperationUsageRecord` in `operations` has `cost_usd is not None`.

  An empty ledger is measured (True), because it spent nothing. `cost_measured` is derived from the rollup's own fields, so it can never disagree with them. Adding it never changes `cost_usd`, `cost_complete`, or any other field.
- **INV-3** — Spend the meter cannot see is never reported as measured, and never described in code, docs, or messages as capped. That covers:
  - a tool or MCP server that pays an external API without calling `record_operation`;
  - a non-text runner;
  - a provider charge that differs from the SDK rate.

  The README section (W-9) states this limitation in those words.

**When the run stops**

- **INV-4** — With `max_spend_usd` set, every check point stops the run with `AgentStopReason.MAX_SPEND` when either condition holds:
  - (a) `rollup.cost_usd is not None and rollup.cost_usd >= max_spend_usd` (the cap was reached), or
  - (b) `not rollup.cost_measured` (the meter is blind, so the run fails closed), even when the measured spend is below the cap.

  Condition (a) is evaluated first. A stop that satisfies (a) carries the "reached" text even if the meter is also blind.
- **INV-5** — The check points are:
  - **CP1:** at the top of every loop iteration, before `before_iteration` middleware and the model call. This includes the iteration that follows a fallback-model switch (`runtime.py:459`). It runs as the first clause of `_budget_stop`.
  - **CP2:** on the plain-text finish branch, before the `max_tokens` finish check, contracts, `review_finish`, `after_iteration`, and `_continue_finish_attempt` (`runtime.py:513-598`).
  - **CP3:** before every tool call, internal tools included (isDone, `run_bulk_work`, `launch_swarm`, `launch_subagent`), as the first step of `_enforce_tool_settings` (`runtime.py:1834`).
  - **CP4:** after `after_iteration` middleware on a continuing tool iteration, before `_after_tool_iteration` (`runtime.py:700`), which is JevAgent's compute checkpoint.

  Once a check point stops the run, this runtime starts no further model call, tool call, finish attempt, or compute checkpoint.
- **INV-6** — The overshoot bound. Let `C = max_spend_usd`. Every check before the stopping one passed, so when the run stops, `measured spend < C + G`. Here `G` is the largest measured spend of any single segment that began after a passing check. The segments are:

  | Segment | Starts after | Ends at | What can spend inside it |
  |---|---|---|---|
  | Model | CP1 | CP2, or CP3 for the first tool | one main model call with its middleware retries and billed failed attempts (`runtime.py:726-839`, `:793`) |
  | Tool | CP3 | the next CP3 or CP4 | one tool call's whole spend: priced operations, and every child agent the tool runs (a sub-agent `as_tool()`, the fork tool's child, `run_bulk_work` workers, `launch_swarm` helpers plus its plan check), concurrent ones included |
  | Finish | CP2, or CP3 before isDone | the next CP1, or the end of the run | `after_iteration` and `review_finish` middleware; for JevAgent, done-check decision calls, the run-state, handoff, and reviewer sub-agents, and a fresh-continuation agent run |
  | Iteration tail | CP4 | the next CP1 | JevAgent's compute checkpoint (compute decision calls, `JevCloneAgent` clones run concurrently) and the next iteration's context-window side calls (`runtime.py:346-366`) |
  | Pre-loop | reply start | the first CP1 | JevAgent's gate, skill preload, run-state writer, and tool-selector calls (`vidbyte/agents/jev/runtime.py:118-145`), and an algorithm's work before its first `_arun_once` |
  | Algorithm step | an attempt's last check | the next attempt's first CP1, or the end of the run | the reflexion reflection call (`reflexion.py:113-133`), the grader call (`multi_provider_agentic_grader.py:149-164`), and an independent-critic or prosecutor-defender-judge reviewer run (`independent_critic.py:103`, `prosecutor_defender_judge.py:507`) |
  | End of run | the stop | the reply returns | `after_run` middleware (`runtime.py:947`) |

  When a segment runs `N` children concurrently and each inherits the same `AgentLoopSettings`, that segment can spend up to `Σᵢ (C + Gᵢ)` plus the tool's own spend, where `Gᵢ` is child `i`'s own largest segment. A child that does not inherit the cap is limited in USD by nothing in this feature: the Jev fixed-prompt agents (`brief/writer.py:60`, `done/handoff.py:161`, `done/reviewer.py:37`, `done/run_state.py:281`, `gate/clarification.py:54`), the critic and judge reviewer sub-runtimes, and a sub-agent with its own settings. Only its own iteration and token limits bound it.

  The overshoot is "at most one model call, with its retries" only when the run has no spending tool calls, no children, no context-window algorithm, no algorithm, no spending finish middleware, and, for JevAgent, no done checks, no compute, and no fresh continuation. The request's Q5 premise, "the run can exceed the cap by at most one call", is therefore false in general (§15 Q-5).
- **INV-7** — Blind-meter containment. Once the meter is blind, the run starts no new segment. Unmeasured spend is confined to the segment in which the meter went blind, plus any blind spend inside children that merge during that segment. This feature puts no USD bound on that unmeasured spend (INV-3).
- **INV-8** — At a check point that another budget shares, the spend cap is checked first. When both are exhausted at the same check, the run stops with `max_spend`. A capped run whose spend stays below the cap and stays measured stops exactly as the same run would without the cap.

**What a cap stop looks like**

- **INV-9** — A cap stop's `AgentResult`, and through `BaseAgent._generate_reply` (`base.py:986-997`) the reply's metadata, carries:
  - `output` equal to the stop text. The text is `"Agent runtime stopped after reaching max_spend_usd."` for condition (a) and `"Agent runtime stopped because max_spend_usd is set and this run's spend could not be fully measured."` for condition (b).
  - `metadata["stop_reason"] == "max_spend"`.
  - `metadata["usage_rollup"]`, the tracker rollup at the moment of the stop. For JevAgent this is replaced by the run total (`vidbyte/agents/jev/response.py:148-154`).
  - The usual `iteration_count`, `tokens_used`, `tool_call_count`, `tool_call_states`, and `tool_calls` (`runtime.py:2111-2127`).
  - No new metadata key.

  On a CP2 stop, the model's plain-text answer stays in `metadata["iteration_outputs"]` (`runtime.py:473-474`, `:971-991`). A cap stop delivers nothing to output connectors (`vidbyte/lib/constants/outputs.py:34-36`).
- **INV-10** — Sessions map `"max_spend"` to `FailureCode.RESOURCE_EXHAUSTED`, with `FailureStatus.EXHAUSTED`, `FailureDisposition.ROUTE`, and details exactly `{"stop_reason", "iteration_count", "tokens_used"}` (`vidbyte/sessions/failure/router.py:112-131`). It never falls through to `RUNTIME_ERROR`. `EfficiencyBehavior` counts `max_spend` as a budget stop (`vidbyte/evals/behavior/efficiency.py:31-43`).

**Scope of one cap**

- **INV-11** — The cap is per reply. It applies to one `generate_reply`, whose tracker resets at reply start (`base.py:923`).
  - Within a reply it spans every `_arun_once` attempt of a context-window algorithm, because they share the tracker. `max_tokens`, by contrast, is per attempt (`runtime.py:300`).
  - Each drained queued prompt (`base.py:1186-1220`) and each prompt of `arun_sequentially` is its own reply with its own cap.
  - A JevAgent continuation's budget extension (`jev/runtime.py:260-275`) never raises, lowers, or removes the cap.
- **INV-12** — A child agent's spend counts toward the parent's measured spend from the moment the child's reply finishes, never earlier. Every child built from the same `AgentLoopSettings` enforces the same cap against its own tracker: JevAgent clones, swarm helpers, bulk workers, and the fresh-continuation agent (`jev/agent.py:76`, `bulk_work.py:60`, `compute/clone.py:45`, `compute/swarm.py:57`), InfiniteMemory subagents (`infinite/agent.py:87`, `infinite/launch.py:311`), and forks.

**Never silently ignored**

- **INV-13** — An agent that cannot enforce the cap refuses it before any spend:
  - `MCTS_SEARCH`, `ACTOR_MODEL`, `ACTOR_MODEL_P2P`, and `ACTOR_MODEL_BROADCAST` refuse it at construction with `ConfigurationError`.
  - A non-text runner refuses it at run start, before any runner request, with `ConfigurationError`. `_generate_reply` raises that as the cause of `AgentExecutionError` (`base.py:965-979`).
  - JevAgent refuses at construction any specialist whose own `agent_loop_settings.max_spend_usd` is missing or greater than JevAgent's, because a delegated run never enters JevAgent's loop (`jev/runtime.py:129-130`).

  No other agent accepts the setting without enforcing it. `MultiAgent` and `AggregateAgent` do not accept loop settings at all.
- **INV-14** — `max_spend_usd` accepts only `None` or a finite real greater than 0, given as an `int` or a `float` but never a `bool`. Anything else raises `ConfigurationError` naming `AgentLoopSettings.max_spend_usd` (or `AgentRuntimeConfig.max_spend_usd`), with `details["field"]` set. NaN, ±inf, `True`, `0`, negative values, and strings are all rejected.
- **INV-15** — The cap survives every copy of the loop settings: `to_runtime_config()`, `__repr__`, `export_state()` and `restore()`, YAML `agent.loop`, `AgentForker` with a `max_iterations` override, and the fork tool with any loop override. Through the fork tool the model can neither set, raise, nor clear it.
- **INV-16** — The model never sees the cap. The rendered system prompt's loop-settings block is unchanged (`runtime.py:1679-1701`).

**Must not regress:**
- **INV-17** — With `max_spend_usd=None`, the default, every run behaves exactly as on `base_commit`. No cap code computes a rollup, and stop reasons, outputs, metadata, and middleware calls are unchanged. The existing stops live at `runtime.py:2046-2089`, `:513-522`, and `:1834-1899`.
- **INV-18** — `CostBudgetMiddleware` still estimates spend at its flat rate and aborts in `before_iteration` as `middleware_abort` (`cost_budget.py:36-84`). `cost_spent_usd` and `MinCostSpent` still read that estimate (`runtime.py:2174-2181`).
- **INV-19** — `UsageRollup.cost_usd` and `cost_complete` keep their meaning (`tracker.py:185-186`).
- **INV-20** — JevAgent still fails closed on usage: `require_accounted()` and `settle()` raise `UsageAccountingError` on a recording error, unreported usage, or an unpriced call (`jev/usage.py:39-81`), including after a cap stop.
- **INV-21** — `FailureCode` membership and order are unchanged, so `test_harness_threads_surface.py:218-241` and the codex slice pins stay green. The root export list stays at 733 names, and `contracts/sdk-public-api.json` is byte-identical.
- **INV-22** — `isDone` still never counts toward `max_tool_calls` (`runtime.py:2071-2073`, `:1866-1869`). The spend check at CP3 does not change which calls count as tool calls.

### 6.2 Acceptance criteria

| ID | Given | When | Then | Priority | Proof |
|---|---|---|---|---|---|
| AC-1 | a clean checkout of this branch, a Vidbyte key in the environment (built at runtime, never a literal), and the model wire scripted through the §13 transport seam | the §4 snippet runs exactly as written | it prints exactly one of its three lines, and that line matches the run: the cap line when the scripted spend reaches $0.50, the "could not be fully measured" line when a scripted call has no usage, and the "finished" line otherwise | P0 | |
| AC-2 | `AgentLoopSettings` | constructed with `max_spend_usd` set to `True`, `float("nan")`, `float("inf")`, `-float("inf")`, `0`, `-1`, or `"5"` | it raises `ConfigurationError` whose message names `AgentLoopSettings.max_spend_usd`; `1`, `0.25`, and `None` are accepted | P0 | |
| AC-3 | `AgentLoopSettings(max_spend_usd=2.5)` | `to_runtime_config()` and `repr()` are called, and `AgentRuntimeConfig(max_spend_usd=…)` is built with each invalid value from AC-2 | the config carries `max_spend_usd == 2.5`; the repr contains `max_spend_usd=2.5`; each invalid value raises `ConfigurationError` naming `AgentRuntimeConfig.max_spend_usd` | P0 | |
| AC-4 | a linear agent capped at C whose scripted priced responses reach measured spend ≥ C after model call k, with call k returning tool calls | the run proceeds | no tool from call k runs, no model call k+1 is sent, and the reply has `stop_reason == "max_spend"`, the reached text as output, `usage_rollup.cost_usd >= C`, and `cost_measured is True` | P0 | |
| AC-5 | the same agent, where the call that reaches C returns a plain-text answer | the run proceeds | the run stops with `max_spend` before `review_finish`, `after_iteration`, or `_continue_finish_attempt` runs; the output is the reached text; the answer is in `metadata["iteration_outputs"]` | P0 | |
| AC-6 | a capped agent whose measured spend is already ≥ C when a response asks for an internal tool (isDone, or a launch tool) | the tool batch is processed | that tool does not execute and the run stops with `max_spend` | P0 | |
| AC-7 | a capped agent whose first tool in a turn spends past C (a priced operation, or a sub-agent run through `as_tool()`) | the turn continues | the next tool call in that turn does not execute; when that tool was the turn's last, `_after_tool_iteration` is not entered; the stop reason is `max_spend` | P0 | |
| AC-8 | a capped agent whose first model response carries no parseable usage (`unaccounted_call_count` becomes 1) | the run proceeds | it stops at the next check point with `max_spend`, the unmeasured text as output, and `cost_measured is False`; the same run without a cap continues as on `base_commit` | P0 | |
| AC-9 | a capped agent on a model the pricebook cannot price, with no provider-reported cost | the first call returns | the run stops at the next check point with `max_spend`; `usage_rollup.cost_usd is None` and `cost_measured is False` | P0 | |
| AC-10 | any agent with `max_spend_usd=None` | it runs any scripted conversation the existing suite covers | stop reasons, outputs, and metadata equal those on `base_commit`; no existing test changes | P0 | |
| AC-11 | `max_spend_usd` set, and a runtime type of `MCTS_SEARCH`, `ACTOR_MODEL`, `ACTOR_MODEL_P2P`, or `ACTOR_MODEL_BROADCAST` | the agent is constructed | it raises `ConfigurationError` naming the runtime and `max_spend_usd`; without the cap it constructs as on `base_commit` | P0 | |
| AC-12 | a capped agent whose model resolves to a non-text runner type | the agent runs | the reply fails with `AgentExecutionError` whose `__cause__` is a `ConfigurationError` naming `max_spend_usd`; no runner request was made and no usage was recorded | P0 | |
| AC-13 | `JevAgentSettings(loop=AgentLoopSettings(max_spend_usd=C), agents=(…))` | `JevAgent` is constructed with a specialist whose loop has no cap, or a cap greater than C | it raises `ConfigurationError` naming the specialist; a specialist capped at ≤ C constructs | P0 | |
| AC-14 | a capped JevAgent whose preflight decision calls alone bring measured spend to ≥ C | the run reaches the main loop | it stops at CP1 of iteration 0 with `max_spend` before any generative model call | P1 | |
| AC-15 | a capped parent whose tool runs a child agent that spends X | the tool returns | the parent's `get_usage()` includes X; the parent's next check point stops the run when the total reaches C | P0 | |
| AC-16 | a capped agent | it goes through `export_state()` and `restore()`; YAML `agent.loop.max_spend_usd`; `AgentForker` with `max_iterations`; and the fork tool with `loop_settings={"max_iterations": 3}` | each resulting agent has the same `max_spend_usd`; a fork-tool call whose `loop_settings` holds `max_spend_usd` is refused with the `ValueError` the tool raises for every unsupported field (`vidbyte/tools/builtins/fork/fork.py:321`) | P0 | |
| AC-17 | a reply with `stop_reason == "max_spend"` | `FailureMetadataNormalizer` reads it | it records exactly one `Failure` with `RESOURCE_EXHAUSTED`, `EXHAUSTED`, `ROUTE`, and details `{"stop_reason": "max_spend", "iteration_count": …, "tokens_used": …}` | P0 | |
| AC-18 | a run that stopped with `max_spend` | `EfficiencyBehavior.did_not_stop_on_budget` evaluates it | it reports a budget stop | P1 | |
| AC-19 | `UsageRollup` values | `cost_measured` is read | it is True for an empty rollup and for all-priced intact records, and False when any one holds: a record or operation has `cost_usd is None`, `unaccounted_call_count > 0`, or `recording_integrity is CORRUPTED` | P0 | |
| AC-20 | a capped JevAgent whose done check grants a continuation with a budget extension | the continuation runs | `runtime.config.max_spend_usd` is unchanged | P1 | |
| AC-21 | a capped agent | its system prompt is rendered for a model call | the cap value and the text `max_spend_usd` do not appear | P1 | |
| AC-22 | a capped agent where `max_iterations` and the cap are both exhausted at the same CP1 | the check runs | the stop reason is `max_spend` | P1 | |
| AC-23 | a capped agent running a context-window algorithm whose first attempt reached C | a second `_arun_once` attempt starts | it stops at its first CP1 with `max_spend` | P1 | |
| AC-24 | this branch | the public API contract check and the `FailureCode` pins run | `scripts/generate-sdk-public-api.py --check` passes unchanged, and `FailureCode` has the same members in the same order as `base_commit` | P0 | |
| AC-25 | a capped JevAgent whose run makes an unpriced generative call | the run proceeds | the loop stops at the next check point and the reply raises `UsageAccountingError` from `settle()`, as on `base_commit` for an unpriced call | P1 | |
| AC-26 | this branch | the agents README, the Jev README, `llms.txt`, the failure vocabulary, and the 0.4.0 release record are read | each names `max_spend_usd`; the agents README states what is and is not measured (INV-1, INV-3), the four check points, the overshoot bound, and the per-runtime answer of §9.2; the release record's quoted before-text (§12.3 row 16) is byte-identical and followed by the new sentence; no added line calls unmeasured spend capped | P1 | |

### 6.3 Edge cases and failure modes

| ID | Trigger (input + state) | System behavior | User sees | Guarded by (INV-/D-) |
|---|---|---|---|---|
| EC-1 | `max_spend_usd=float("nan")` | rejected at construction. Without the guard, `x >= nan` is always False and the run is silently uncapped | `ConfigurationError` naming the field | INV-14, D-2 |
| EC-2 | `max_spend_usd=True` | rejected (`bool` is an `int`). Without the guard, True would mean $1 | `ConfigurationError` | INV-14 |
| EC-3 | `max_spend_usd=float("inf")` | rejected. Without the guard, the cap is never reached and the run is silently uncapped | `ConfigurationError` | INV-14 |
| EC-4 | `0`, a negative value, or `"5"` from YAML | rejected | `ConfigurationError` from `AgentLoopSettings(**mapping)` (`vidbyte/lib/dataclasses/config.py:686`) | INV-14 |
| EC-5 | a model the pricebook misses (`ModelPricingRegistry.resolve` → None, `pricing.py:333-358`), including a fallback model or a model with `STRICT_MODEL_VALIDATION` off | the call is recorded with `cost_usd=None`; the next check point stops with the unmeasured text | `max_spend`, `cost_measured=False`, `cost_usd` excluding that call | INV-4(b), D-5 |
| EC-6 | a response with no parseable usage, or an unknown provider (`tracker.py:94-96`) | no record, and `unaccounted_call_count += 1`; the next check point stops | `max_spend`, `cost_measured=False` | INV-4(b) |
| EC-7 | a recording exception (`tracker.py:98-100`), or a failed child merge (`base.py:897-905`) | integrity becomes CORRUPTED; the next check point stops | `max_spend`, `cost_measured=False` | INV-4(b) |
| EC-8 | OpenRouter with a provider-reported cost, against the empty OpenRouter table (`pricing.py:276`) | measured from the reported cost; enforced normally | normal cap behavior | INV-1 |
| EC-9 | OpenRouter without a reported cost | unpriced, so the same as EC-5 | `max_spend`, `cost_measured=False` | INV-4(b) |
| EC-10 | a tool calls a paid external API without `record_operation` (custom or MCP tool) | invisible to the meter; `cost_measured` stays True | spend under-reported; documented as unmeasured, never as capped | INV-3 (accepted limitation: the SDK cannot meter what it never sees) |
| EC-11 | the model-provider charge differs from the SDK rate (stale pricebook, gateway margin, tier or time-of-day selection) | the cap compares SDK-rated spend | stop at the rated amount, which may differ from the invoice | INV-1, A-1 (accepted limitation) |
| EC-12 | the last call before a finish crosses the cap | CP2 stops before any finish work; the output is replaced, as `max_tokens` does at `runtime.py:514-522` | `max_spend`; the answer is in `iteration_outputs` | INV-5, INV-9, D-10, Q-6 |
| EC-13 | measured spend ≥ C when the model calls isDone | CP3 stops before isDone executes; isDone's answer argument is not recorded as output | `max_spend`; the model's text for that turn is in `iteration_outputs` | INV-5, D-11, Q-6 |
| EC-14 | `launch_swarm` with 10 helpers, each inheriting cap C | the tool segment can spend up to about 10 × (C + Gᵢ) before the parent's next check | the parent stops at the next check point with total spend far above C | INV-6, INV-12 (accepted limitation, Q-8) |
| EC-15 | clones launched at the compute checkpoint when the iteration's tools already crossed C | CP4 stops the run before `_after_tool_iteration`, so no clone starts | `max_spend` | INV-5 (CP4) |
| EC-16 | the compute checkpoint itself crosses C | the next iteration's context-window side calls still run before CP1 | overshoot of one iteration-tail segment | INV-6 (accepted) |
| EC-17 | JevAgent's pre-loop decision spend reaches C | CP1 at iteration 0 stops before the first generative call | `max_spend` | INV-5, AC-14 |
| EC-18 | a JevAgent specialist with no cap of its own | refused at construction. Without the guard, a delegated run would never meet JevAgent's loop and would spend uncapped | `ConfigurationError` naming the specialist | INV-13, D-13 |
| EC-19 | a capped JevAgent makes an unpriced call | the cap stops at the next check point; `settle()` then raises (or `require_accounted()` raises first at a phase boundary) | `UsageAccountingError`, not a `max_spend` reply | INV-20, AC-25 |
| EC-20 | queued prompts are pending when a reply stops with `max_spend` | the drain still runs each queued prompt as its own reply with a fresh cap (`base.py:1026-1027`, `:1186-1220`) | `get_usage()` covers every drained reply; the total can exceed C | INV-11 (accepted limitation, Q-9) |
| EC-21 | a reflexion attempt crosses C | the reflection call (an algorithm step) still runs; the next attempt's CP1 stops | `max_spend` | INV-6, INV-11 |
| EC-22 | an independent-critic or prosecutor-defender-judge reviewer sub-runtime | it is built with its own `AgentRuntimeConfig` and no cap (`independent_critic.py:123-127`, `prosecutor_defender_judge.py:242`), and shares the parent tracker | its spend counts; the parent stops at its next check point | INV-6 (accepted, Q-10) |
| EC-23 | the multi-provider grader's concurrent trials share one runtime and tracker | each trial's check points see the combined spend; after the trials stop, the grader call still runs once | `max_spend` on the trials; the final reply carries the grader's outcome | INV-6, INV-11 |
| EC-24 | the cap and `max_iterations` are both exhausted at the same CP1 | the spend cap is checked first | `max_spend` | INV-8, D-9 |
| EC-25 | measured spend equals C exactly | `>=` stops, matching "reaching" for every other budget | `max_spend` | INV-4 |
| EC-26 | float accumulation (`16.499999999998472` for 10,000 calls at $0.00165, measured 2026-10-19) | the comparison and the reported figure use the same sum | the error, about 1e-12 relative, is far below one call's cost | D-2 |
| EC-27 | a fallback switch after billed failed attempts | the billed attempts are recorded (`runtime.py:793`); the switch `continue`s to CP1 before the next model is called | stops before the backup model when C is reached | INV-5 (CP1) |
| EC-28 | the model passes `loop_settings={"max_spend_usd": 1000}` to `fork_conversation` | the schema (`additionalProperties: false`, `vidbyte/tools/builtins/fork/fork.py:484-500`) and `_resolve_loop_settings` (`fork.py:321`) refuse it | the tool error "loop_settings does not support field 'max_spend_usd'." | INV-15, D-12 |
| EC-29 | the model passes `loop_settings={"max_iterations": 3}` | the child is rebuilt with the parent's cap through `_inherited_guardrails` | the child is capped at the parent's C | INV-15 |
| EC-30 | a checkpoint written before this PR is restored | no `max_spend_usd` key, so the restored agent is uncapped | unchanged | INV-17 (the default is `None`); §9.4 |
| EC-31 | a checkpoint of a capped agent is restored by an SDK without this field | `AgentLoopSettings(**values)` raises `TypeError` for the unknown keyword (`base.py:774`) | forward-incompatible checkpoint; an uncapped checkpoint omits the key (`base.py:684`) | accepted limitation: 0.4.0 is unreleased and checkpoints are forward-only (§9.4) |
| EC-32 | a capped agent on a non-text model (image, audio, video, or embedding runner) | refused at run start, before any request | `AgentExecutionError` caused by `ConfigurationError` | INV-13, D-15 |
| EC-33 | a `MultiAgent` or `AggregateAgent` team | there is no team setting; each member enforces its own cap | team spend = Σ of members, with no team ceiling | NG-6 (accepted) |
| EC-34 | a developer binds a `Session` failure rule to `resource.exhausted` that continues the run | the continuation is a new reply with a fresh cap | spend continues by the developer's explicit choice; the SDK binds no such rule by default | INV-10, INV-11 |
| EC-35 | two concurrent `arun()` calls on one agent object share `_usage_tracker` (`base.py:291`) | both resets and both checks read one ledger (pre-existing shared-tracker behavior) | each run's cap sees the combined spend | INV-11 (pre-existing; not changed) |
| EC-36 | `after_run` middleware spends after the stop | that spend lands after the metadata rollup was taken | `get_usage()` includes it, and `reply.metadata["usage_rollup"]` does not | INV-9 (the rollup is taken at the stop); accepted: `after_run` runs after every stop, and the §9.2 contract has C3 read `get_usage()` |
| EC-37 | a ledger of 10,000 records with tool calls checked at CP3 | each check costs one `rollup()`, measured at 2.65 ms for 10,000 records | negligible against model latency | accepted cost, bounded by NFR-2; D-3 (no second meter) |

**Rollback of the user action:** the cap is configuration. Removing `max_spend_usd` (or passing `None`) restores `base_commit` behavior on the next run (INV-17). A run the cap stopped cannot be resumed past the stop, because each reply resets the tracker. Re-running, or continuing through a Session, starts a new reply with a fresh cap. The spend already made stays in `get_usage()` for that reply.

## §7 Requirements

**Functional**
| ID | Requirement | Priority | Source (request.md / G-) |
|---|---|---|---|
| FR-1 | `AgentLoopSettings.__init__` accepts a keyword-only `max_spend_usd: float \| None = None`, validated per INV-14 without any `raise` in the settings class, and stores it as the attribute `max_spend_usd`. | P0 | request.md §C "Give AgentLoopSettings … an optional USD spend cap"; Q1; G-1 |
| FR-2 | `AgentRuntimeConfig` gains `max_spend_usd: float \| None = None`, validated in `__post_init__` per INV-14. `to_runtime_config()` carries it, and `__repr__` shows it when set. | P0 | G-1; AGENTS.md principle 4 |
| FR-3 | `AgentRuntime` enforces the cap at CP1–CP4 per INV-4, INV-5, and INV-8, through one helper, `_spend_cap_stop`, and the policy class `AgentSpendCap`. | P0 | request.md §C "The shared agent runtime must enforce the cap…"; G-1 |
| FR-4 | A blind meter stops a capped run (INV-4(b)). | P0 | request.md §C Q2; G-4 |
| FR-5 | `AgentStopReason.MAX_SPEND = "max_spend"` is the only stop reason the cap produces, and the stop result follows INV-9. | P0 | request.md §C "stops the run the same way it already stops on its other budgets"; G-2 |
| FR-6 | `UsageRollup.cost_measured` (INV-2) is the completeness flag of the caller contract (§9.2). | P0 | briefing §1 item 2; G-2, G-4 |
| FR-7 | Refusals per INV-13: non-linear runtimes at construction, non-text runners at run start, and JevAgent specialists at construction. | P0 | Prompt 3 Q7 "every agent"; briefing "never accept a cap and then silently ignore it"; G-3 |
| FR-8 | The cap survives every copy path in INV-15: `base.py` `_export_loop_settings`, `agents/fork.py` `_loop_settings`, the fork tool's `_inherited_guardrails`, and `config.py` `_LOOP_FIELDS`. | P0 | briefing "A new loop field silently drops unless…"; G-1 |
| FR-9 | Sessions and evals know the new stop reason (INV-10): one `router._STOP_CODES` entry and one `EfficiencyBehavior._BUDGET_STOP_REASONS` entry. | P0 | `router.py:52-54` `@intent stop-codes-cover-agentstopreason`; `efficiency.py:31-32` `@intent budget-stop-covers-every-runtime-budget`; G-2 |
| FR-10 | Documentation per INV-3 and AC-26: the agents README "Spend Cap" section and Key Modules entry; the Jev README specialist sentence; the `llms.txt` `AgentLoopSettings` table, validation, and projection text; the vocabulary note; and the release record sentence. | P1 | AGENTS.md "Repository Map" (folder READMEs, `llms.txt`); request.md §C "Record the change in docs/design/release-0-4-0.md"; G-2 |

**Non-functional**
| ID | Requirement | Priority | Target |
|---|---|---|---|
| NFR-1 | An uncapped run does no extra work for the cap. | P0 | `_spend_cap_stop` returns before calling `rollup()` when `config.max_spend_usd is None` |
| NFR-2 | A capped check is cheap at scale. | P1 | ≤ 10 ms per check for a 10,000-record ledger on the dev machine. `rollup()` was measured at 0.27 ms for 1,000 records and 2.65 ms for 10,000 (2026-10-19, `py -3.11`); `cost_measured` adds two linear passes. Flip: if profiling shows the check above target, add a running total to `UsageTracker` |
| NFR-3 | No lint regression. | P0 | `lint/run.py` prints `SDK-LINT: PASS` with no rule REGRESSED against `lint/baseline.json`. The base commit has 7 rules IMPROVED and none REGRESSED (§11). In particular, C001 stays ≤ 26, C002 ≤ 9, S008 ≤ 19 (`_process_tool_call` is at C901 10 of 10 and must not gain a branch), and A001 gains no finding for the new file |
| NFR-4 | The full local gate passes. | P0 | the source and package stages of `scripts/run_ci.py` pass, apart from the inherited local-only reds named in §11 |
| NFR-5 | The big files grow only by thin call sites. | P0 | `git diff --numstat` against `base_commit` shows ≤ 40 added lines in `vidbyte/agents/runtime.py` and ≤ 20 in `vidbyte/agents/base.py` (S1 estimate with 72-column comments: about 33 and 13) |
| NFR-6 | The weighted words of request.md §D that this run serves hold. "make "max_spend" a universal command in the cli" → FR-1, with the field the CLI maps to. "i want every agent to be tracking usage" → INV-12, INV-13, G-3. "you can just auto merge that applies this change and updates the version" → the version stays 0.4.0 per D-P2, and no version literal changes. The other §D phrases belong to PRs C1, C2, C4, R2, and C5. | P0 | `git grep -n "0.4.0" -- pyproject.toml vidbyte/__init__.py` unchanged |
| NFR-7 | The public repo stays push-clean. | P0 | no key-shaped literal in any file the PR adds or changes. The public repo's GH013 push protection blocks them (pipeline.md niche facts) |

---

## Part C — Design

## §8 Architecture and decisions

The design has three parts:

- a validated field on the existing loop settings object;
- a stateless policy class in the agents domain that turns a `UsageRollup` into "stop with this text" or "continue";
- thin call sites in the one shared loop (`AgentRuntime`), with refusals at the three places that cannot reach that loop.

The meter is the existing agent-owned `UsageTracker`. The cap adds no second meter.

### 8.1 Decisions
| ID | Decision | Deciding reason | Runner-up | Flips if |
|---|---|---|---|---|
| D-1 | The field is named `max_spend_usd`, on `AgentLoopSettings` and `AgentRuntimeConfig`. | Every USD amount in the SDK names its unit: `CostBudgetMiddleware(max_spend_usd=…)` (`cost_budget.py:36`), `max_cost_usd` (`vidbyte/lib/dataclasses/context.py:58`), `cost_usd` (`records.py:68-89`). The CLI flag `--max-spend` maps to it one-to-one. | `max_spend`, the user's word | the user asks for the exact word `max_spend` on the SDK field |
| D-2 | A `float` USD amount, validated by `RecordFieldValidator.require_number(value, "<Class>.max_spend_usd", maximum=sys.float_info.max)` in both classes (Q-1). | Every USD value in the repo is a float. The canonical validator rejects bool, NaN, ±inf, and ≤ 0, and raises `ConfigurationError` with `details["field"]` (`vidbyte/lib/dataclasses/validation.py:96-103`). Using it keeps C001, C002, C006, and C008 at baseline (field guide `strict-config-dataclasses.md:61-67`). The same `maximum` is already used at `vidbyte/lib/dataclasses/infinite.py:319`. | `Decimal`, which would mean converting every record's float cost | a caller needs sub-cent exactness beyond about 1e-12 relative error |
| D-3 | Enforce inside `AgentRuntime`, at four check points, using the policy class `AgentSpendCap`. | This is the shared loop of `LINEAR`, `JEV`, and `INFINITE_MEMORY` (`base.py:83`). Every existing loop budget stops there (`runtime.py:2046-2089`). It sees internal tool calls and the compute checkpoint, which middleware hooks do not bracket. | A priced middleware (a ledger-reading `CostBudgetMiddleware` variant) | the user wants the cap as an opt-in middleware instead of a loop setting. Rejected because a middleware cannot be set through `AgentLoopSettings`, `MiddlewareContext` carries no cumulative cost (`vidbyte/lib/dataclasses/middleware.py:164-191`), and a stop would end as `middleware_abort` (TERMINAL/STOP), not a budget stop |
| D-4 | Coexist with `CostBudgetMiddleware`, unchanged. | They are different meters with different contracts. The middleware is a caller-chosen flat estimate (`cost_budget.py:60-70`) that aborts as middleware. The cap is the priced ledger, stopping as a budget. Changing the middleware is out of scope (NG-5). The field-guide entry against duplication (`runtime-boundaries.md:24-29`) targets a sub-runtime's own `Params` copying a general setting. This change *is* the general loop setting. | Reuse: re-point the middleware at the ledger | the user later wants one USD mechanism. The follow-up then deprecates the flat estimate |
| D-5 | A blind meter fails closed at the next check point. There is no construction-time pricebook refusal (Q-2). | A construction check is neither necessary nor sufficient. The pricebook cannot see provider-reported prices (OpenRouter, `openrouter.py:45-56`). Fallback models (`base.py:191`), Jev children, and tool sub-agents use models a check of the main model never covers (`brief/writer.py:55-64`). A call with no usage is blind whatever its price. The repo's precedent fails closed at run boundaries (`jev/usage.py:39-58`). | Refuse a capped agent whose configured model has no price (the request's default) | the user wants zero unmeasured calls for the configured main model. Q-11 then adds the construction check *in addition* |
| D-6 | A new stop reason, `MAX_SPEND = "max_spend"`, mapped to the existing `FailureCode.RESOURCE_EXHAUSTED`. | `resource.exhausted` exists (`vidbyte/lib/enums/failure.py:130`), has no producer (`git grep` finds only its definition and `skills/failure/vocabulary.md:103`), and sits in "Runtime and resources" (`vocabulary.md:98-108`). The vocabulary rule is "Use the most specific existing code". Any new `FailureCode` member is red: appending fails CI (`test_harness_threads_surface.py:224-227`), and inserting fails locally (`:228-236`). | New `RUNTIME_MAX_SPEND = "runtime.max_spend"` inserted after `RUNTIME_MAX_TOOL_CALLS`, accepted as a local-only red that clears on merge | a Session rule must route spend differently from other resource exhaustion |
| D-7 | Completeness is `UsageRollup.cost_measured`, a derived `@property`. `cost_complete` is unchanged. | `cost_complete` ignores `unaccounted_call_count` and `recording_integrity`, and is False for an empty ledger (`tracker.py:186`). Changing it breaks INV-19. A derived flag cannot contradict its fields (field guide `blocking-lint-invariants.md:46-52`). It lives on the root-exported type C3 already reads (`vidbyte.UsageRollup`, contract line 646), so C3 imports nothing new. | A `metadata["spend_measured"]` key on stop results | C3 needs completeness on a type other than `UsageRollup` |
| D-8 | The cap is per reply. It spans algorithm attempts, and each child is capped against its own tracker. No budget is shared across concurrent children (Q-3). | The tracker resets per reply (`base.py:923`), attempts share it (`runtime.py:300`), and each child records into its own tracker and merges once (`base.py:852-890`). A shared budget needs new plumbing into every spawn path. | Hand each child the parent's remaining budget at launch | Q-8 is answered yes |
| D-9 | At every check point the spend cap is checked first. | At CP3 the existing code returns early for internal tools before any budget (`runtime.py:1836-1837`), so the cap must come first there to bind internal tools without a second branch. One rule everywhere is easier to state and test. Ties only occur when the cap is set and reached, so INV-17 holds. | Check spend after the existing budgets | a reviewer shows a tie case where `max_spend` misleads a caller |
| D-10 | A CP2 stop replaces the output with the stop text, as `max_tokens` does on the same branch (`runtime.py:514-522`). The answer stays in `iteration_outputs`. | It follows the existing finish-branch budget exactly. Finish work after it (review, done checks, continuation) can spend, so it must not start. | Return the paid-for answer as the output with `max_spend` | Q-6 is answered yes |
| D-11 | CP3 binds internal tools too, unlike `max_tool_calls`. | Internal launch tools start agents that spend money (`vidbyte/agents/jev/bulk_work.py:116-137`, `vidbyte/agents/jev/compute/swarm_tool.py:101-122`), and internal tools skip `_enforce_tool_settings`'s budgets (`runtime.py:1836-1837`). | Bind developer tools only | never; an exempt launch tool would make the cap advisory |
| D-12 | In the fork tool, the cap is a non-overridable guardrail (`_inherited_guardrails`). It is not in `_LOOP_SETTING_FIELDS` or the schema. | The model must not be able to raise or clear its own budget (T-2). The existing guardrails already carry `tool_settings` and `output_contracts` the same way (`fork.py:334-343`, pinned by `tests/test_fork_tool.py:319-338`). | Overridable but capped at the parent's value, like `max_iterations` (`fork.py:328-331`) | the user wants the model able to *lower* a child's cap |
| D-13 | A capped JevAgent refuses, at construction, a specialist whose own cap is missing or greater. | Delegation returns before JevAgent's loop (`jev/runtime.py:129-130`, `:215-221`), so the only loop that can enforce anything is the specialist's own. Refusing beats silently running uncapped. The neighbouring guard `_require_metered_specialists` (`jev/agent.py:113-125`) is the pattern. | Copy JevAgent's cap onto the specialist at delegation, which would mutate a user-owned agent | the user prefers automatic inheritance (NG-11) |
| D-14 | The cap stays out of the model-visible prompt. | Precedent: `timeout_seconds` "is enforced at the budget check but kept out of model-visible prompt text" (`runtime.py:1679-1701`). The field guide keeps limits in code and behavior in prompts (`runtime-boundaries.md`, "Enforce a deterministic tool-call cap in middleware; the prompt carries only behavior"). | Render "spent/limit" like `max_tokens` | the user asks the model to budget its own spend |
| D-15 | Non-linear runtimes refuse at construction. A non-text runner refuses at run start. | Neither reads any loop budget: a `grep` of `vidbyte/agents/runtimes/` finds no `max_iterations`, `max_tokens`, `max_tool_calls`, or `timeout_seconds`, and `_run_non_text_runner` records no usage (`base.py:1333-1368`). The runtime type is known at construction (`base.py:233-247` pattern). The runner type is resolved only in `_runner_for_model` at run time (`base.py:1659-1674`). | A stated limitation | a non-text runner gains usage recording and loop budgets |
| D-16 | `AgentSpendCap` lives in the module `vidbyte.agents.spend_cap`. It is exported from neither `vidbyte.agents` nor the root. | Runtime helpers live beside the runtime (`fallback.py`, `contract.py`, `context_algorithms.py`). The only caller is `AgentRuntime`, and C3 needs only existing root names (C028 in the CLI). `runtime.py` and `base.py` are already 2,304 and 1,830 lines (AGENTS.md principle 3). | Inline the policy in `runtime.py` | the policy grows past one method and belongs in `vidbyte/lib/` as a shared helper |
| D-17 | No new metadata key on stop results. | C3's two questions are answered by `stop_reason` and the rollup, which every result already carries (`runtime.py:2111-2127`). A key in `_runtime_metadata` would appear on every result. The session details dict is pinned (`tests/test_session_failures.py:430-435`). | Add `metadata["max_spend_usd"]` on a cap stop | C3 must read the cap from the result rather than from its own input |

### 8.2 Patterns inherited
- **Metered hard limit with a check-before-start rule.** This is the usage-billing pattern: rate each event, keep a running ledger, and admit no new metered unit once the balance reaches the limit. The overshoot is bounded by the largest unit in flight. Stating that bound (INV-6) is the honest version of "stop at $X". The repo already meters every model call into one agent-owned ledger (`vidbyte/agents/pricing/tracker.py:55-200`).
- **Fail closed on an incomplete ledger.** The cap copies JevAgent's rule that unreported or unpriced usage stops the run (`jev/usage.py:39-81`). The three conditions are the same (INV-2).
- **Loop budget stop.** `_stopped_result(text, stop_reason=…)` returned through `_finish_result`, as at `runtime.py:2063-2070` and `:1862-1870`.
- **Validated field through the canonical validator.** `RecordFieldValidator.require_number` (`validation.py:96-103`), as `AllowedToolNames` keeps `AgentLoopSettings` free of raises for `allowed_tools` (`vidbyte/lib/dataclasses/agents.py:169-184`, `loop.py:79-80`).
- **Construction refusal for features a runtime cannot run.** The pattern is at `base.py:243-247` (output contracts on non-linear runtimes).
- **Non-overridable inherited guardrail.** The pattern is the fork tool's `_inherited_guardrails` (`fork.py:334-343`).
- **Derived flag instead of a stored bool.** The field guide's C002 lesson (`blocking-lint-invariants.md:46-52`).

### 8.3 Smaller design rejected
The smallest design is one clause in `_budget_stop`: `if cap and tracker.rollup().cost_usd >= cap: return stopped(...)`. It is about 5 lines and no new file. It fails these requirements:
- **INV-5 and INV-6.** Every tool call in a response still runs after the cap is reached, including `launch_swarm`, `run_bulk_work`, and sub-agents. The whole finish attempt still runs: Jev done checks and a full fresh-continuation run. The compute checkpoint still launches clones. The true overshoot becomes "one whole iteration with every child it starts".
- **INV-4(b).** `cost_usd` sums only priced records (`tracker.py:185`, `:251-260`), so an unpriced or usage-less run would look cheap and never stop. That is "capped" unmeasured spend, which G-4 forbids.
- **INV-13.** MCTS and actor runtimes, non-text runners, and JevAgent specialists would accept the cap and silently ignore it.

The next smallest design, the clause plus CP3 inside `_process_tool_call`, fails NFR-3. `_process_tool_call` is at C901 10 of 10, so one more branch is a new S008 finding.

### 8.4 Complexity budget
| Item | Count | Justification for each |
|---|---|---|
| New files | 1 | `vidbyte/agents/spend_cap.py`. It keeps the policy out of the 2,304-line runtime (AGENTS.md principle 3) and gives the metering contract one documented home. Test files are the S2 test author's and do not count. |
| New classes/modules | 1 | `AgentSpendCap`, a stateless policy class with one static method. |
| New dependencies | 0 | — |
| New config keys | 1 | `max_spend_usd`, one key carried by `AgentLoopSettings`, `AgentRuntimeConfig`, and YAML `agent.loop`. |
| New collections/tables | 0 | — |
| New public endpoints/commands | 0 | Public surface additions: one enum member (`AgentStopReason.MAX_SPEND`), one property (`UsageRollup.cost_measured`), and one keyword (`AgentLoopSettings(max_spend_usd=)`). No root name. |

_The implementer may not exceed this budget without stopping and reporting BLOCKED._

### 8.5 Key interfaces

```python
# vidbyte.agents.settings.loop.AgentLoopSettings  (root: vidbyte.AgentLoopSettings)
class AgentLoopSettings:
    def __init__(self, *, ..., timeout_seconds: float | None = None,
                 max_spend_usd: float | None = None, ...) -> None: ...
    max_spend_usd: float | None          # stored attribute; None means uncapped

# vidbyte.lib.dataclasses.agents.AgentRuntimeConfig  (frozen, slots)
@dataclass(frozen=True, slots=True)
class AgentRuntimeConfig:
    ...                                   # existing fields unchanged
    allowed_tools: frozenset[str] | None = None
    max_spend_usd: float | None = None    # appended last

# vidbyte.lib.dataclasses.agents.AgentStopReason  (root: vidbyte.AgentStopReason)
class AgentStopReason(str, Enum):
    ...
    TIMEOUT = "timeout"
    MAX_SPEND = "max_spend"               # new, placed after TIMEOUT
    MIDDLEWARE_ABORT = "middleware_abort"
    ...

# vidbyte.agents.pricing.records.UsageRollup  (root: vidbyte.UsageRollup)
@dataclass(frozen=True, slots=True)
class UsageRollup:
    ...
    @property
    def cost_measured(self) -> bool: ...  # INV-2

# vidbyte.agents.spend_cap.AgentSpendCap  (new module; not exported)
class AgentSpendCap:
    @staticmethod
    def stop_output(max_spend_usd: float, rollup: UsageRollup) -> str | None: ...
    # returns "Agent runtime stopped after reaching max_spend_usd."
    #   when rollup.cost_usd is not None and rollup.cost_usd >= max_spend_usd;
    # else "Agent runtime stopped because max_spend_usd is set and this run's
    #   spend could not be fully measured." when not rollup.cost_measured;
    # else None.

# vidbyte.agents.runtime.AgentRuntime  (private helper)
def _spend_cap_stop(self, *, iteration_count: int, tokens_used: int | None,
                    contexts: Sequence[ToolCallContext]) -> AgentResult | None: ...
    # None when self.config.max_spend_usd is None (no rollup computed);
    # else AgentSpendCap.stop_output(cap, self.usage_tracker.rollup()) and,
    # when that is text, self._stopped_result(text, stop_reason=AgentStopReason.MAX_SPEND, ...)

# vidbyte.agents.jev.agent.JevAgent  (private guard)
@staticmethod
def _require_capped_specialists(settings: JevAgentSettings) -> None: ...
    # no-op when settings.loop.max_spend_usd is None; else ConfigurationError for any
    # specialist whose agent.agent_loop_settings.max_spend_usd is None or greater

# Session routing (existing class, one new entry)
FailureMetadataNormalizer._STOP_CODES["max_spend"] == FailureCode.RESOURCE_EXHAUSTED
```

## §9 Data, API, configuration, migration

### 9.1 Data model
Everything here is in memory, per process. Nothing is persisted except through the existing run-state checkpoint.

- `AgentLoopSettings.max_spend_usd: float | None`, default `None`. Optional, mutable attribute on a plain class (as its siblings are). Validated once at construction.
- `AgentRuntimeConfig.max_spend_usd: float | None = None`. Frozen. Validated in `__post_init__`, so `dataclasses.replace` re-validates it.
- `AgentStopReason.MAX_SPEND = "max_spend"`. One member added to an existing `str` Enum. `REPO_MAP.md:199` calls extending an enum an interface change. Its exhaustive consumers are updated in FR-9. `OUTPUT_DELIVERABLE_STOP_REASONS` deliberately excludes it.
- `UsageRollup.cost_measured: bool`. A derived property: not a dataclass field, not serialized, not settable.
- The checkpoint key `RunState.loop_settings["max_spend_usd"]` holds a float, written by `_export_loop_settings` only when it is not `None` (`base.py:684`).
- Volume: one float per agent. `cost_measured` is O(records + operations) per read, and so is the existing `rollup()`. The ledger is the existing one. The cap adds no growth.

### 9.2 API and interface surface

**Public library surface.**
- `AgentLoopSettings(max_spend_usd=…)`, reachable as `vidbyte.AgentLoopSettings` and `vidbyte.agents.settings.AgentLoopSettings`. It is also reachable through `JevAgentSettings(loop=…)` (`vidbyte/agents/jev/settings.py:144`), `InfiniteMemoryAgentSettings.loop`, and YAML `agent.loop.max_spend_usd`.
- `AgentStopReason.MAX_SPEND`.
- `UsageRollup.cost_measured`.
- Validation errors, all `ConfigurationError` with `details["field"]`. Messages come from `RecordFieldValidator.require_number`, for example `"AgentLoopSettings.max_spend_usd must be a finite number greater than 0 and at most 1.7976931348623157e+308; got nan."`. The value is quoted only as a short scalar (`validation.py:186-196`).
- Refusal errors, all `ConfigurationError`:
  - non-linear runtime: `"Agent {name} uses non-linear runtime {runtime}, which does not enforce max_spend_usd."`, copying the wording of `base.py:229-247`;
  - non-text runner: `"Agent {name} sets max_spend_usd, but its {runner_type} runner runs outside the agent loop, which is the only place the spend cap is enforced."`, with `details={"agent", "runner_type"}`;
  - Jev specialist: `"JevAgent specialist {title!r} must set agent_loop_settings.max_spend_usd no higher than this JevAgent's {cap}, because a delegated run never enters JevAgent's loop."`, with `details={"specialist", "max_spend_usd", "specialist_max_spend_usd"}`.

**Caller contract for vidbyte-cli C3.** C3 relies on exactly these rules. All names are root exports C3 may import: `AgentLoopSettings`, `AgentStopReason`, `UsageRollup`.
1. **The cap stopped the run** if and only if `reply.metadata["stop_reason"] == AgentStopReason.MAX_SPEND.value` (`"max_spend"`). A run that ends `final_response` or `is_done` was not stopped by the cap, even if its last segment pushed spend past the cap (INV-6).
2. **What the run spent** is `usage = agent.get_usage()`, read after the call returns (`base.py:1116-1118`). It is the whole `arun()`, including drained queued prompts (`base.py:1212-1219`) and `after_run` spend. The figure is `usage.cost_usd`, in USD as the SDK rated it. `None` means no priced record exists: report $0 if `usage.cost_measured`, otherwise "unknown". `reply.metadata["usage_rollup"]` is the ledger the runtime compared at the moment it stopped.
3. **Whether the figure is complete** is `usage.cost_measured`. When True, `cost_usd` is the whole SDK-rated spend of every call and operation the meter can see (INV-1, INV-3). When False, `cost_usd` is a lower bound, to be reported as "at least $X".
4. **Why it stopped.** `max_spend` with `cost_measured` True means the measured spend reached the cap. `max_spend` with `cost_measured` False and `cost_usd < cap` (or `None`) means the meter went blind.
5. **JevAgent fails closed.** A run with unmeasured usage raises `UsageAccountingError` (`jev/usage.py:39-58`) instead of returning a `max_spend` reply. That error is not a root export (Q-12).
6. **Refusals.** A construction refusal raises `ConfigurationError` from the constructor. A non-text-runner refusal surfaces as `AgentExecutionError` from `run()`/`arun()`, with `__cause__` a `ConfigurationError`.

**"Every agent", per runtime.**

| Agent / runtime | Cap behavior | Where |
|---|---|---|
| `Agent` / `BaseAgent` / `CodingAgent` (`LINEAR`) | enforced at CP1–CP4 | `vidbyte.agents.runtime.AgentRuntime` |
| `JevAgent` (`JEV`) | enforced in the inherited loop. Pre-loop decision spend is counted at the first CP1. Children built from `settings.loop` are capped individually. A specialist must carry its own cap ≤ JevAgent's. | `vidbyte.agents.jev.agent.JevAgent`, `AgentRuntime` |
| `InfiniteMemoryAgent` (`INFINITE_MEMORY`) | enforced in its root loop. Subagents built from `settings.loop` are capped individually. | `AgentRuntime` |
| `MCTS_SEARCH`, `ACTOR_MODEL`, `ACTOR_MODEL_P2P`, `ACTOR_MODEL_BROADCAST` | refused at construction | `vidbyte.agents.base.BaseAgent.__init__` |
| Any agent whose model resolves to a non-text runner | refused at run start, before any request | `BaseAgent._run_direct` |
| `MultiAgent`, `AggregateAgent` | no setting exists. Each member enforces its own cap. No team ceiling (NG-6). | — |
| Jev fixed-prompt agents, critic and judge reviewer sub-runtimes | built by the SDK with their own loop limits and no cap. Their spend counts in the parent at the parent's next check point (INV-6). | — |

### 9.3 Configuration and flags
| Variable / key | Required | Default | Purpose | Lives in |
|---|---|---|---|---|
| `max_spend_usd` | no | `None` (uncapped) | USD cap on one reply's measured spend | `AgentLoopSettings` keyword; `AgentRuntimeConfig` field; YAML `agent.loop.max_spend_usd` (`vidbyte/lib/dataclasses/config.py:92-98`); `JevAgentSettings.loop` |

There is no environment variable and no new constant, because the validator's maximum is `sys.float_info.max`.

### 9.4 Migrations and compatibility
The change is additive, with no data migration.
- **Old checkpoints** carry no `max_spend_usd` key and restore uncapped (EC-30).
- **New checkpoints of uncapped agents** omit the key (`base.py:684`), so an older SDK restores them unchanged.
- **New checkpoints of capped agents** cannot be restored by an SDK without this field: `AgentLoopSettings(**values)` raises `TypeError` (EC-31). This is accepted, because 0.4.0 is unreleased and checkpoints are forward-only.
- **`_export_runtime_config`** (`base.py:624-659`), the pre-`loop_settings` legacy fallback, is deliberately unchanged. It does not carry `timeout_seconds` either.

Public contracts:
- `contracts/sdk-public-api.json` records names only and is unchanged (request.md:64).
- `AgentStopReason` gains a member. Code that matches it exhaustively sees one more value. In-repo consumers are updated (FR-9). The three tests that iterate the enum pick it up generically (A-3).
- `UsageRollup` gains a read-only property. Its constructor and its fields are unchanged.

## §10 Security and tenancy
| ID | Attacker | Shortest path to harm | Control | Where the control sits |
|---|---|---|---|---|
| T-1 | Careless user | A config file sets `max_spend_usd: .nan`, `"5"`, or `inf`, and the run is silently uncapped while the CLI says "capped at $X". | `RecordFieldValidator.require_number` rejects every non-finite, non-positive, bool, or non-number value at construction (INV-14). | In the SDK process, at `AgentLoopSettings.__init__` and `AgentRuntimeConfig.__post_init__`, before any run. |
| T-2 | Hostile user, or a prompt-injected model | The model calls `fork_conversation` with `loop_settings={"max_spend_usd": 1e9}` or `{"max_iterations": 1}` (which rebuilds settings) to escape the cap. Or the model reads the cap in its prompt and spends up to it deliberately. | The cap is a non-overridable guardrail: it is not in `_LOOP_SETTING_FIELDS` or the schema, and is re-applied by `_inherited_guardrails` (D-12). It never appears in the prompt (D-14). CP3 binds internal launch tools (D-11). Residual: the model can still choose a spending tool before the next check, which is bounded by INV-6. | In the runtime and the fork tool's code, not in the prompt. |
| T-3 | Compromised teammate or leaked credential | Someone with code access sets `max_spend_usd=None`, or reads a key from a refusal message. | The cap is a cost control, not an authorization boundary: code access already implies full control, so no control against removing it is claimed. The control this feature owns is that its errors leak nothing: `_received` refuses to echo secret-named fields and long values (`validation.py:186-196`), and the refusal messages in §9.2 name only numbers, agent and specialist titles, and runner types. | In the SDK process, inside `RecordFieldValidator` and the refusal code paths. |
| T-4 | Another tenant | Spend from one agent's run counts against another tenant's cap. | Each agent owns one `UsageTracker` (`base.py:291`). The active ledger is a `ContextVar` that asyncio tasks copy at creation (`vidbyte/lib/usage_ledger.py:7`, `:42-54`), so concurrent runs of different agents never share a ledger. Pre-existing and unchanged: two concurrent runs of the *same* agent object share its tracker (EC-35). | In the SDK process (the per-agent tracker and the ledger `ContextVar`). |

There is no new endpoint, command, credential, or persisted secret. Keys keep flowing through `ProviderKeys` unchanged. The public repo forbids key-shaped literals (NFR-7). Fixtures that need a key build it at runtime (`tests/test_jev_usage_ledger.py:78`).

## §11 Codebase grounding

- **Rules read:**
  - AGENTS.md in full:
    - Repository Map: `docs/` is opaque except named files; run the full gate; read folder READMEs to the end.
    - Style principles 1–5. Principle 3 is the 1,000-line rule against `runtime.py` (2,304) and `base.py` (1,830). Principle 4 is validated dataclasses. Principle 5 is canonical `lib/` helpers.
    - Placement Rules: no new dataclass or enum. Adding a member or field in place is allowed under "Existing code".
  - `REPO_MAP.md:109` (a setting, not a constructor parameter), `:199` (enum extension is an interface change), `:203` (reuse an error type).
  - Folder READMEs read: `vidbyte/agents/README.md` (30,375 characters; sections at `:185`, `:349`, `:386`; no `## File Index`, so S020 does not apply), `vidbyte/agents/jev/README.md` (17,723 characters; specialists at `:24`).
  - Folders with no README: `vidbyte/agents/settings/`, `vidbyte/agents/pricing/`, `vidbyte/sessions/failure/`, `vidbyte/tools/builtins/fork/` (code-map §1.1).
- **Field-guide entries applied** (all under `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`, index `init.md`):
  - `strict-config-dataclasses.md:3-9`, `:61-67`: no `raise ConfigurationError` in a settings class; validate through `RecordFieldValidator.require_*` with a qualified field name.
  - `blocking-lint-invariants.md:46-52`: expose a derived `@property`, not a second bool guard (C002).
  - `runtime-boundaries.md:10-15`: usage accounting stays agent-owned. The cap reads the agent's `UsageTracker` and records nothing.
  - `runtime-boundaries.md:24-29`: no duplicate sub-runtime cost ceiling. D-4 explains why this general loop setting is not that.
  - `comment-format.md:3-8`: multi-line comments are blocks of at most 72 columns directly above the code, with `# @intent <name>` on its own first line within 20 lines of the `def`.
  - `local-ci-verification.md:3-9`: `PYTHONPATH=<worktree>` on the source stage only.
  - `local-ci-verification.md:10-16`: `git add` before semgrep.
  - `local-ci-verification.md:38-44`: check S051 import sorting over the whole `vidbyte` tree.
  - `local-ci-verification.md:45-50`: the `harness_threads` branch-scoped tests are red locally when `vidbyte/tools` changes.
- **Stack (from manifests):** Python 3.11 (`py -3.11`); pytest (`pyproject.toml:78-81`, `testpaths=["tests"]`), with many `unittest.TestCase`/`IsolatedAsyncioTestCase` files collected by pytest; ruff behind S008 and S051; mypy staged behind S009 (`lint/mypy.ini`). No DB.
- **Commands (exact, from `context/code-map.md` §1.2/§3 and AGENTS.md, with the workspace rule `py -3.11` for `python`):**
  - Install: `py -3.11 -m pip install -e ".[dev]"`
  - Lint: `PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) py -3.11 lint/run.py` · one rule: `PYTHONPATH=$(pwd) py -3.11 lint/run.py --rule <ID>` · findings: `… --rule <ID> --all`
  - Typecheck: inside lint as S009 (`lint/rules/s009_staged_mypy_contracts.py`); no separate command
  - Test (focused): `PYTHONPATH=$(pwd) py -3.11 -m pytest -q <file-or-folder>`
  - Test (full): `PYTHONPATH=$(pwd) py -3.11 -m pytest`
  - Full local gate: `PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source`, then `env -u PYTHONPATH py -3.11 scripts/run_ci.py --stage package`
  - Public API contract: `PYTHONPATH=$(pwd) py -3.11 scripts/generate-sdk-public-api.py --check` (must pass unchanged)
  - Import order: `py -3.11 -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`, filtered to the touched paths
  - Semgrep: `git add -A`, then `PATH="$(cygpath -u C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/s3-semgrep-venv)/Scripts:$PATH" semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`
  - Remote-only checks: `gh workflow run ci.yml --ref feat/loop-spend-cap` and `gh workflow run static-policy.yml --ref feat/loop-spend-cap`. Dispatch-only, so `gh pr checks` shows nothing (pipeline.md).
- **Baseline on clean `origin/main` (run by S1 at `6db4207e`, a docs-only commit on `22993b5f`, 2026-10-19):**
  - `lint/run.py` prints `SDK-LINT: PASS`, exit 0. No rule is REGRESSED. Seven rules are IMPROVED from pre-existing slack: A002 608/703, S001 56/59, S009 346/350, S010 0/5, S025 261/263, S061 5/6, S063 3/4. Leave `lint/baseline.json` alone; that slack is not this PR's.
  - `pytest -q` over `tests/features/sdk_loop_settings`, `tests/features/sdk_model_usage`, `tests/test_agent_runtime.py`, `tests/test_session_failures.py`, `tests/test_fork_tool.py`, `tests/test_jev_usage_ledger.py`, and `tests/test_new_middleware_builtins.py`: `350 passed in 2.62s`.
  - The full `run_ci.py` was not re-run by S1.
  - Inherited local-only reds, all skipped in CI because a shallow clone has no `origin/main` (`test_harness_threads_surface.py:131-142`):
    - `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` (`:270-278`) turns red locally once `vidbyte/tools/builtins/fork/fork.py` changes (§12.3 row 8), and clears on merge;
    - `tests/test_mcp_stdio_transport.py::test_cancelled_waiter_does_not_break_transport` is a known flake (`local-ci-verification.md:17-23`).
  - No root export changes, so the `__all__` merge-base clause (`:303-309`) stays green.
- **Directory layout relevant to this change:**
  ```
  vidbyte/
    agents/
      spend_cap.py            # NEW  AgentSpendCap
      runtime.py              # CP1–CP4 call sites, _spend_cap_stop
      base.py                 # refusals, _export_loop_settings
      fork.py                 # AgentForker._loop_settings
      README.md               # Spend Cap section, Key Modules
      settings/loop.py        # AgentLoopSettings.max_spend_usd
      pricing/records.py      # UsageRollup.cost_measured
      jev/agent.py            # _require_capped_specialists
      jev/README.md
    lib/dataclasses/agents.py # AgentRuntimeConfig.max_spend_usd, AgentStopReason.MAX_SPEND
    lib/dataclasses/config.py # _LOOP_FIELDS
    sessions/failure/router.py
    evals/behavior/efficiency.py
    tools/builtins/fork/fork.py
  llms.txt
  skills/failure/vocabulary.md
  docs/design/release-0-4-0.md
  ```
- **Nearest sibling feature (the template to copy):**
  - `max_tokens`. Its field and validation are at `loop.py:32-43` and `:102-110`. Its runtime config is at `vidbyte/lib/dataclasses/agents.py:126-152`. Its top-of-iteration stop is at `runtime.py:2063-2070`, its finish-branch stop at `:514-522`, its routing at `router.py:38`, and its eval at `efficiency.py:36`.
  - The validation shape is `allowed_tools`: validated at assignment through a `lib` validator, with no raise in the settings class (`loop.py:79-80`, `agents.py:169-184`).
  - The fail-closed rule is `JevUsageAccount` (`jev/usage.py:39-81`).
  - Copy the module-header shape from `vidbyte/lib/dataclasses/validation.py:1-14`, which is A001-complete.
- **Reusable pieces:**
  - `vidbyte/agents/pricing/tracker.py:UsageTracker.rollup` is the live ledger read at each check.
  - `vidbyte/lib/dataclasses/validation.py:RecordFieldValidator.require_number` is the field validator.
  - `vidbyte/agents/runtime.py:AgentRuntime._stopped_result` builds the stop result.
  - `vidbyte/agents/base.py:_LINEAR_LOOP_RUNTIMES` drives the refusal test.
  - `vidbyte/tools/builtins/fork/fork.py:_inherited_guardrails` carries the cap in the fork tool.
  - `vidbyte/lib/enums/failure.py:FailureCode.RESOURCE_EXHAUSTED` is the failure code.
  - `vidbyte/agents/base.py:BaseAgent.get_usage` is how callers read spend.
- **Code-style exemplar** (`vidbyte/agents/runtime.py:1862-1870`):
  ```python
  def _tool_settings_budget_stop(self, settings: ToolSettings | None, call_contexts: list[ToolCallContext], *, iteration_count: int, tokens_used: int | None) -> AgentResult | None:
      # Stops the run before executing a call that would exceed the total tool-call budget mid-iteration.
      # The budget is ToolSettings.max_calls or AgentRuntimeConfig.max_tool_calls (AgentLoopSettings.max_tool_calls), whichever is lower.
      limits = [limit for limit in (self.config.max_tool_calls, settings.max_calls if settings is not None else None) if limit is not None]
      # @intent internal-tools-never-spend-the-tool-budget
      # Loop-control calls such as isDone are the runtime's own, so only developer tool calls spend the budget.
      if not limits or len(self._non_internal_tool_contexts(call_contexts)) < min(limits):
          return None
      return self._stopped_result("Agent runtime stopped after reaching max_tool_calls.", stop_reason=AgentStopReason.MAX_TOOL_CALLS, iteration_count=iteration_count, tokens_used=tokens_used, contexts=call_contexts)
  ```
- **Domain glossary:**
  - *Live rollup*: `vidbyte.agents.pricing.records.UsageRollup`, from `UsageTracker.rollup()`. It is **not** `vidbyte.lib.dataclasses.sessions.UsageRollup`, which is built after the fact from session history with caller flat prices (`vidbyte/sessions/usage.py:27-41`).
  - *Unaccounted call*: a call that reached the ledger with no parseable usage or provider (`tracker.py:94-96`).
  - *Internal tool*: `metadata={"internal": True}`, such as isDone, `run_bulk_work`, or `launch_swarm`. It never counts toward `max_tool_calls`.
  - *Linear loop runtimes*: `LINEAR`, `JEV`, `INFINITE_MEMORY` (`base.py:83`).
  - *Decision call*: a Jev TypeSafe call recorded as `UsageKind.DECISION` (`decision.py:55`).
  - *Reply*: one `generate_reply`.
- **Prior specs / design docs / ADRs that constrain this:** `docs/design/release-0-4-0.md`, the unreleased 0.4.0 record (D-P2). This PR edits it (§12.3 row 16). No other `docs/` file was read (AGENTS.md; briefing §7).
- **Conflicts between house style and AGENTS.md:**
  - House style says functions take dataclasses. The existing budget helpers take keyword primitives (`_budget_stop`, `_tool_settings_budget_stop`). `_spend_cap_stop` follows the sibling. `AgentSpendCap.stop_output` takes the `UsageRollup` dataclass.
  - House style puts meaningful strings in constants. The sibling stop texts are inline literals (`runtime.py:2056-2084`). The new texts follow the sibling, and each appears once.
  - AGENTS.md wins in both cases, as the repo's own grain.

## §12 Work breakdown — everything this PR has to do

### 12.1 Feature list
| ID | Feature (capability this PR adds) | Serves | Visible to |
|---|---|---|---|
| W-1 | `AgentLoopSettings.max_spend_usd`, validated, shown in `repr`, carried to `AgentRuntimeConfig.max_spend_usd` | FR-1, FR-2, AC-2, AC-3 | developer |
| W-2 | `AgentStopReason.MAX_SPEND` | FR-5, AC-4..AC-9 | developer, CLI |
| W-3 | `UsageRollup.cost_measured` | FR-6, AC-19, AC-1 | developer, CLI |
| W-4 | `AgentSpendCap.stop_output`, the stop policy | FR-3, FR-4, AC-4..AC-9 | — (internal) |
| W-5 | Runtime enforcement at CP1–CP4 through `_spend_cap_stop` | FR-3, FR-4, AC-1, AC-4..AC-10, AC-14, AC-15, AC-21..AC-23, AC-25 | developer, end user |
| W-6 | Refusals: non-linear runtimes, non-text runners, Jev specialists | FR-7, AC-11..AC-13 | developer |
| W-7 | Copy paths: export/restore, AgentForker, fork tool guardrail, YAML loop fields | FR-8, AC-16, AC-20 | developer, model (refused) |
| W-8 | Session routing and eval budget membership, reusing an existing `FailureCode` | FR-9, AC-17, AC-18, AC-24 | developer, operator |
| W-9 | Documentation and the release record | FR-10, G-2, AC-26 | developer, CLI author |

### 12.2 Folder and module map
| Folder | Kind of code (per repo rules) | New? | README / header obligation | May import from |
|---|---|---|---|---|
| `vidbyte/agents/` | agent domain: runtime and its helpers | no (adds `spend_cap.py`) | `README.md` Key Modules entry plus the "Spend Cap" section. The new file needs an A001-complete header. | `vidbyte/agents/pricing/`, `vidbyte/lib/` |
| `vidbyte/agents/settings/` | agent settings objects (Placement exception 1) | no | none (no README); keep the `loop.py` header's Architecture bullet true | `vidbyte/lib/` |
| `vidbyte/agents/pricing/` | usage records and the tracker | no | none (no README); keep the `records.py` header's Architecture bullet true | `vidbyte/lib/` |
| `vidbyte/agents/jev/` | JevAgent | no | `README.md` specialist sentence | `vidbyte/agents/`, `vidbyte/lib/` |
| `vidbyte/lib/dataclasses/` | dataclasses (Placement rule) | no | none | only `vidbyte/lib/` (AGENTS.md principle 3) |
| `vidbyte/sessions/failure/` | failure normalization | no | none | `vidbyte/lib/` |
| `vidbyte/evals/behavior/` | behavior predicates | no | none | `vidbyte/lib/` |
| `vidbyte/tools/builtins/fork/` | model-facing fork tool | no | none (no README) | `vidbyte/agents/`, `vidbyte/lib/` |
| `skills/failure/`, repo root, `docs/design/` | human docs | no | — | — |

### 12.3 File-by-file actions
| # | Action | Path | Kind of code | What exactly changes (symbols, signatures, exports, registrations) | Governing standard (AGENTS.md § / placement rule / field-guide file / lint rule ID) | Serves | Phase |
|---|---|---|---|---|---|---|---|
| 1 | CREATE | `vidbyte/agents/spend_cap.py` | service (stateless policy) | `class AgentSpendCap` with `@staticmethod stop_output(max_spend_usd: float, rollup: UsageRollup) -> str \| None`, behaving exactly as §8.5 and INV-4 (reached before blind). It has no numeric literal and no I/O, and imports only `UsageRollup` (`from vidbyte.agents.pricing.records import UsageRollup`, or under `TYPE_CHECKING`) plus `__future__` annotations. `__all__ = ["AgentSpendCap"]`. Module header fields: FILE, PURPOSE, ROLE IN CODEBASE (called by `AgentRuntime._spend_cap_stop`), ARCHITECTURE NOTE (what is measured; the four check points; reached before blind), FUNCTION INVENTORY, COMMON MODIFICATION PATTERNS (a new check point calls `_spend_cap_stop`, never this class directly), WHAT NOT TO DO (no ledger writes; never treat `cost_usd is None` as unmeasured by itself), KNOWN EDGE CASES (an empty ledger is measured; `cost_usd` is a lower bound when not measured; children count only after they finish), RELATED DOCS (`vidbyte/agents/README.md` "Spend Cap"), TESTS (the S2 pack path). `stop_output` carries `# @intent spend-cap-fails-closed-on-a-blind-meter`, giving the INV-4(b) reason. | A001 (all seven fields, `lint/rules/a001_agent_readable_file_headers.py:24-32`); A002 (`@intent` within 20 lines of the `def`); A006 (agents → agents.pricing only); A007 (no literal near budget or limit names); field guide `comment-format.md` (72 columns); D-16 placement beside `fallback.py`/`contract.py` | FR-3, FR-4, W-4 | P2 |
| 2 | MODIFY | `vidbyte/agents/settings/loop.py` | settings class | (a) Add `max_spend_usd: float \| None = None` to `__init__`, right after `timeout_seconds`. (b) Store it with `self.max_spend_usd = RecordFieldValidator.require_number(max_spend_usd, "AgentLoopSettings.max_spend_usd", maximum=sys.float_info.max) if max_spend_usd is not None else None`, plus a one-line comment above it, mirroring `allowed_tools` at `:79-80`. (c) `to_runtime_config()` passes `max_spend_usd=self.max_spend_usd`. (d) Add `"max_spend_usd"` to the `__repr__` name tuple right after `"timeout_seconds"`. (e) Imports: `import sys`; `from vidbyte.lib.dataclasses.validation import RecordFieldValidator`. (f) Header Architecture bullet: "…rejecting non-integral budgets, non-finite timeouts, and an invalid USD spend cap…". There is no new method and no `raise` in the class. | C001 (no `raise ConfigurationError` in a plain `*Settings` class; baseline 26); C006 (the guard delegates to the validator); C008 (no new primitive validator); field guide `strict-config-dataclasses.md:61-67`; `REPO_MAP.md:109`; S051 import order | FR-1, FR-2, W-1 | P1 |
| 3 | MODIFY | `vidbyte/lib/dataclasses/agents.py` | enum member + dataclass field | (a) `AgentStopReason`: add `MAX_SPEND = "max_spend"` right after `TIMEOUT = "timeout"`. (b) `AgentRuntimeConfig`: append `max_spend_usd: float \| None = None` after `allowed_tools`. (c) `AgentRuntimeConfig.__post_init__`: after the existing checks, `if self.max_spend_usd is not None: RecordFieldValidator.require_number(self.max_spend_usd, "AgentRuntimeConfig.max_spend_usd", maximum=sys.float_info.max)`. (d) Imports: `import sys`; `from vidbyte.lib.dataclasses.validation import RecordFieldValidator`. Existing members, fields, and `ValueError` checks are unchanged. | AGENTS.md Placement "Existing code" (editing in place is allowed); AGENTS.md principle 4; `REPO_MAP.md:199`; C002/C006 (no inline bool guard); A006 (lib → lib only); S008 (`__post_init__` C901 4 → 5, ≤ 10) | FR-2, FR-5, W-1, W-2 | P1 |
| 4 | MODIFY | `vidbyte/agents/pricing/records.py` | dataclass (derived property) | Add `UsageRollup.cost_measured` as a `@property` returning `bool`, exactly per INV-2. Its docstring contrasts it with `cost_complete`. It carries `# @intent unmeasured-spend-is-never-reported-as-measured`. Extend the class docstring with one sentence naming `cost_measured`. Header Architecture bullet for `UsageRollup` adds "…and `cost_measured`, whether `cost_usd` is the whole measured spend". There is no new field, and the constructor is unchanged. | AGENTS.md Placement "Existing code"; field guide `blocking-lint-invariants.md:46-52` (derived property); A002 (`@intent`, since the policy vocabulary "price" may appear); S008 | FR-6, W-3 | P1 |
| 5 | MODIFY | `vidbyte/agents/runtime.py` | runtime (thin call sites) | (a) Import `from vidbyte.agents.spend_cap import AgentSpendCap`. (b) Add `_spend_cap_stop(self, *, iteration_count: int, tokens_used: int \| None, contexts: Sequence[ToolCallContext]) -> AgentResult \| None` beside `_tool_settings_budget_stop`: return `None` when `self.config.max_spend_usd is None`; else `output = AgentSpendCap.stop_output(self.config.max_spend_usd, self.usage_tracker.rollup())`; return `None` if `output is None`, else `self._stopped_result(output, stop_reason=AgentStopReason.MAX_SPEND, iteration_count=…, tokens_used=…, contexts=contexts)`. It carries `# @intent spend-cap-reads-the-live-ledger`, saying the cap reads the agent-owned tracker, including merged children, and never records. (c) **CP1:** the first statement of `_budget_stop`: `spend_stop = self._spend_cap_stop(iteration_count=iteration_count, tokens_used=tokens_used, contexts=contexts)`; `if spend_stop is not None: return spend_stop`. Update its lead comment to "the spend cap, any countable budget, or the wall-clock deadline". (d) **CP2:** in `_arun_once`, the first statements inside `if not tool_calls:` (`:513`), before the `max_tokens` check: `spend_stop = self._spend_cap_stop(…)`; `if spend_stop is not None: return await self._finish_result(spend_stop, state)`, with one narration comment ("Stop before any finish work once this run's measured spend reached its cap or can no longer be measured."). (e) **CP3:** the first statements of `_enforce_tool_settings`, before `if tool_is_internal: return None` (`:1836`): `spend_stop = self._spend_cap_stop(…, contexts=call_contexts)`; `if spend_stop is not None: return spend_stop`, with `# @intent spend-cap-binds-internal-tools` (launch tools start spending agents). Update its lead comment to name the spend cap first. (f) **CP4:** in `_arun_once`, after the `after_iteration` abort check and before `catalog = self.tools` / `await self._after_tool_iteration(state, messages)` (`:699-700`): the same three lines returning `await self._finish_result(spend_stop, state)`, with one narration comment ("Stop before the compute checkpoint and the next iteration's side calls once the spend cap is reached."). (g) **Do not touch** `_process_tool_call` (C901 10 of 10), `_render_loop_settings_block`, `_runtime_metadata`, `_cost_spent_usd`, or `_contract_counters`. | AGENTS.md principle 2 (narrate new steps in `_arun_once`); principle 3 (thin call sites, NFR-5 ≤ 40 lines); principle 1 (`_spend_cap_stop` calls only `AgentSpendCap` and `_stopped_result`, the shape of `_tool_settings_budget_stop`); S008 (`_enforce_tool_settings` C901 6 → 7, `_budget_stop` 5 → 6, `_process_tool_call` unchanged; `_arun_once` already counted); S024 (CP2 nests at depth 3, CP4 at 2, both ≤ 3); A002; field guide `comment-format.md`, `runtime-boundaries.md:10-15` | FR-3, FR-4, FR-5, W-5 | P2 |
| 6 | MODIFY | `vidbyte/agents/base.py` | agent (thin call sites) | (a) In `__init__`, right after the output-contract refusal (`:243-247`): `if self.agent_loop_settings.max_spend_usd is not None and self.runtime_type not in _LINEAR_LOOP_RUNTIMES: raise ConfigurationError(f"Agent {name} uses non-linear runtime {self.runtime_type.value}, which does not enforce max_spend_usd.")`. (b) In `_run_direct`, inside `if runner_type != RUNNER_TYPE_TEXT:` (`:1307`) and before the `return`: `if self.runtime_config.max_spend_usd is not None: raise ConfigurationError(<§9.2 non-text text>, details={"agent": self.name, "runner_type": runner_type})`, with `# @intent spend-cap-is-never-silently-unenforced` above it (a non-text runner has no loop and records no usage, `:1333-1368`). (c) `_export_loop_settings`: add `"max_spend_usd"` to the field tuple right after `"timeout_seconds"` (`:663-675`). (d) **Do not touch** `_export_runtime_config`, `_restore_loop_settings` (which passes keys through, `:774`), `_resolve_loop_settings`, or the constructor signature. | AGENTS.md principle 3 (NFR-5 ≤ 20 lines); `REPO_MAP.md:109` and `:203`; pattern `base.py:243-247`; S008 (`__init__` already counted; `_run_direct` C901 3 → 4); S024 (depth 2); A002 | FR-7, FR-8, W-6, W-7 | P3 |
| 7 | MODIFY | `vidbyte/agents/fork.py` | agent utility | `AgentForker._loop_settings` (`:157-173`): pass `max_spend_usd=base.max_spend_usd` in the rebuilt `AgentLoopSettings(...)`, right after `timeout_seconds=base.timeout_seconds`. | silent-drop list (briefing; code-map §4.3) | FR-8, W-7 | P3 |
| 8 | MODIFY | `vidbyte/tools/builtins/fork/fork.py` | model-facing tool | `_inherited_guardrails` (`:334-343`): add `"max_spend_usd": parent.max_spend_usd`. Update its comment to "…cannot drop denied tools, contracts, or the spend cap". **Do not** add it to `_LOOP_SETTING_FIELDS` (`:52-63`) or the JSON schema (`:484-500`). | D-12; field guide `local-ci-verification.md:45-50` (the inherited local-only red from `test_harness_threads_surface.py:270-278`, classified pre-existing; do not edit that test); S008 (`_inherited_guardrails` has no branch; `_resolve_loop_settings` unchanged, already counted) | FR-8, W-7 | P3 |
| 9 | MODIFY | `vidbyte/lib/dataclasses/config.py` | config loader dataclass | `_LOOP_FIELDS` (`:92-98`): add `"max_spend_usd"`. | silent-drop list; its comment says it "Mirrors the AgentLoopSettings keyword arguments" (`:90`); C019 (the literal is not platform-attributed; S1 simulated no finding) | FR-8, W-7 | P3 |
| 10 | MODIFY | `vidbyte/agents/jev/agent.py` | agent (construction guard) | Add `@staticmethod _require_capped_specialists(settings: JevAgentSettings) -> None` right after `_require_metered_specialists`, per §8.5 and the §9.2 message. It carries `# @intent a-delegated-run-keeps-the-spend-cap`. Call it in `__init__` right after `self._require_metered_specialists(settings)` (`:41`). | pattern `jev/agent.py:113-125`; AGENTS.md "New JEV code" (the logic stays in `vidbyte/agents/jev/`); A002; field guide `jev-capability-layout.md:51-62` (the specialist runs its own agent linearly) | FR-7, W-6 | P3 |
| 11 | MODIFY | `vidbyte/sessions/failure/router.py` | failure normalizer | `FailureMetadataNormalizer._STOP_CODES`: add `"max_spend": FailureCode.RESOURCE_EXHAUSTED,` right after `"timeout": FailureCode.RUNTIME_TIMEOUT,`. `_append_stop_failure` is unchanged, so the details stay exact. | `@intent stop-codes-cover-agentstopreason` (`:52-54`); `tests/test_session_failures.py:430-435` (pinned details, untouched); `skills/failure/vocabulary.md` "Use the most specific existing code" | FR-9, W-8 | P2 |
| 12 | MODIFY | `vidbyte/evals/behavior/efficiency.py` | eval predicate | `_BUDGET_STOP_REASONS`: add `AgentStopReason.MAX_SPEND.value`. Update the `@intent budget-stop-covers-every-runtime-budget` second line to "The runtime's _budget_stop, its spend cap, and the ToolSettings hard budgets all end runs on these reasons." | its own `@intent` (`:31-32`) | FR-9, W-8 | P2 |
| 13 | MODIFY | `vidbyte/agents/README.md` | folder README | (a) A new `## Spend Cap` section, placed before `## Key Modules`, of at most about 30 lines including one ≤ 12-line example (a subset of §4). It must state: what is measured (INV-1) and not measured (INV-3); the four check points in plain words; that a stop reports `stop_reason` `max_spend` and sessions report `resource.exhausted`; that a blind meter stops a capped run; the overshoot bound in one sentence, naming concurrent children; the per-runtime table of §9.2 in prose; how to read spend (`get_usage().cost_usd`, `.cost_measured`); that the cap is per reply, hidden from the model, and not overridable through the fork tool; and how it differs from `CostBudgetMiddleware`. (b) In Key Modules, after the `fallback.py` bullet: "- `spend_cap.py`: `AgentSpendCap`, which decides from the live usage rollup whether a run with `AgentLoopSettings.max_spend_usd` must stop." | AGENTS.md Repository Map (folder READMEs); A009 (≤ 40,000 characters, currently 30,375); never say "capped" for unmeasured spend (INV-3) | FR-10, G-2, W-9 | P4 |
| 14 | MODIFY | `llms.txt` | doc bundle | (a) In the validation sentence (`:728-731`), add "`max_spend_usd` must be a finite USD amount greater than zero;". (b) Add a table row after `max_parallel_tool_calls…` (`:737`): `| \`max_spend_usd\` | Optional USD cap on one reply's measured spend; stop reason \`"max_spend"\` |`. (c) In the projection sentence (`:744-746`), add `max_spend_usd` to the fields `to_runtime_config()` projects. | AGENTS.md Repository Map ("for the code-heavy documentation bundle, read llms.txt"); the table lists every field | FR-10, W-9 | P4 |
| 15 | MODIFY | `skills/failure/vocabulary.md` | failure catalogue | After "Limit failures normally stop cleanly or route to a continuation strategy." (`:106`), add: "A run that `AgentLoopSettings.max_spend_usd` stops (stop reason `max_spend`) reports `resource.exhausted`." | the file's own rule "Use the most specific existing code" | FR-9, FR-10, W-9 | P4 |
| 16 | MODIFY | `docs/design/release-0-4-0.md` | release record | In the "**Later changes on `main`.**" bullet (`:17`), after the exact before-text "…choose the text-model mode, and name compute options without a deep import; the four classes and their defaults are unchanged.", append: " The loop spend cap adds `AgentLoopSettings.max_spend_usd`, an optional USD cap the shared agent loop checks against the run's live priced usage before every model call, tool call, finish attempt, and compute checkpoint; a run it stops ends with the new stop reason `AgentStopReason.MAX_SPEND`, which sessions report as the existing `resource.exhausted`, and `UsageRollup` gains the read-only `cost_measured`. No root name, `FailureCode` member, or default changes, so the contract still lists 733 exports." S6 inserts the PR number as "(#NNNN)" after "The loop spend cap". The closing paragraph (`:19`) is unchanged. | request.md §C "Version (D-P2)… Record the change in docs/design/release-0-4-0.md"; briefing §4 "Release record"; AGENTS.md (`docs/` read only when named; this file is named) | FR-10, W-9 | P4 |
| 17 | MODIFY | `vidbyte/agents/jev/README.md` | folder README | In the specialists paragraph (`:24`), add: "When `JevAgentSettings.loop.max_spend_usd` is set, every specialist must set its own `agent_loop_settings.max_spend_usd` no higher than it, because a delegated run never enters JevAgent's loop; clones, swarm helpers, bulk workers, and the fresh-continuation agent each enforce the same cap against their own spend." | AGENTS.md Repository Map (folder README documents the folder); A009 (17,723 characters, ≤ 40,000) | FR-10, FR-7, W-9 | P4 |

**Deliberately not changed:**
- `vidbyte/lib/enums/failure.py`, `contracts/sdk-public-api.json`, `vidbyte/__init__.py`, `vidbyte/agents/__init__.py`, and every version literal (INV-21, NG-8).
- `vidbyte/middleware/builtins/cost_budget.py`, `vidbyte/agents/contracts/floors.py`, and `vidbyte/lib/constants/outputs.py` (NG-5, INV-9).
- `vidbyte/lib/config/loader.py`, which passes `**loop_raw` through (`:204-221`).
- `vidbyte/agents/jev/runtime.py`. The continuation's `replace(self.config, **limits)` keeps `max_spend_usd` (`:274`), and the pre-loop phases precede CP1.
- `vidbyte/agents/algorithms/*` (Q-10).
- `lint/baseline.json`, which is never raised.
- Every test file.

### 12.4 Standards checklist for this change
- [ ] The new module opens with a docstring carrying non-empty `PURPOSE:`, `ROLE IN CODEBASE:`, `ARCHITECTURE NOTE:`, `COMMON MODIFICATION PATTERNS:`, `KNOWN EDGE CASES:`, `RELATED DOCS:`, and `TESTS:` fields. The "Context Protocol Header" style of `loop.py` and `records.py` is pre-existing A001 debt, not a pattern to copy. — *source:* `lint/rules/a001_agent_readable_file_headers.py:24-32`; exemplar `vidbyte/lib/dataclasses/validation.py:1-14`
- [ ] Every new policy-bearing function (`AgentSpendCap.stop_output`, `AgentRuntime._spend_cap_stop`, `UsageRollup.cost_measured`, `JevAgent._require_capped_specialists`, and the `_run_direct` refusal) has a `# @intent <name>` block within 20 lines of its `def`, stating the invariant and its failure mode. — *source:* `lint/rules/a002_intent_comments.py:23-24,76-82`
- [ ] Every multi-line `#` comment you write is a block of at most 72 columns directly above the code it explains. — *source:* field guide `comment-format.md:3-8`
- [ ] `AgentLoopSettings` gains no `raise` statement. Validation goes through `RecordFieldValidator.require_number`, and C001 stays at 26. — *source:* `lint/rules/c001_settings_class_configuration_error_placement.py`; field guide `strict-config-dataclasses.md:3-9,61-67`
- [ ] No new `isinstance(<named field>, bool)` guard anywhere, so C002 stays at 9. — *source:* `lint/rules/c002_duplicate_inline_bool_guard_validation.py`; field guide `blocking-lint-invariants.md:46-52`
- [ ] No new numeric range guard that admits True, NaN, or ±inf (C006), and no new primitive validator function outside `validation.py` (C008). — *source:* `lint/rules/c006_finite_numeric_guards.py`, `lint/rules/c008_shared_validator_owner.py`
- [ ] No numeric literal next to `budget`, `limit`, or `token` names in new code (A007). The cap comparison uses `rollup.cost_usd is not None and rollup.cost_usd >= max_spend_usd`, with no `0.0`. — *source:* `lint/rules/a007_operational_constants.py:23-38`
- [ ] `_process_tool_call` is not edited. `_enforce_tool_settings`, `_budget_stop`, `_run_direct`, and `AgentRuntimeConfig.__post_init__` stay at C901 ≤ 10, branches ≤ 12, and statements ≤ 50. S008 stays at 19. — *source:* `lint/rules/s008_bounded_function_complexity.py:23`; measured with ruff by S1
- [ ] No new `if` nested deeper than 3. — *source:* `lint/rules/s024_maximum_control_flow_nesting.py:22`
- [ ] Imports stay sorted when checked over the whole tree. — *source:* field guide `local-ci-verification.md:38-44` (S051)
- [ ] The new steps in `_arun_once` each get one plain-English narration comment, and the lead comments of `_budget_stop` and `_enforce_tool_settings` describe the spend check. — *source:* AGENTS.md "2. Narrate Main Functions in Plain English"
- [ ] `runtime.py` adds ≤ 40 lines and `base.py` adds ≤ 20. The policy lives in `spend_cap.py`. — *source:* AGENTS.md "3. Build in Layers…" ("Keep files well below 1,000 lines")
- [ ] No new dataclass or enum is defined. The enum member and the dataclass field are edits in place. — *source:* AGENTS.md "Placement Rules → Existing code"
- [ ] `vidbyte/lib/` imports nothing above `vidbyte/lib/`: `agents.py` imports only `vidbyte.lib.dataclasses.validation` (A006). — *source:* AGENTS.md principle 3; `lint/rules/a006_directed_dependency_graph.py`
- [ ] Every exhaustive consumer of `AgentStopReason` in `vidbyte/` is updated or deliberately left alone: `router._STOP_CODES` (updated), `efficiency._BUDGET_STOP_REASONS` (updated), and `OUTPUT_DELIVERABLE_STOP_REASONS` (deliberately excluded). — *source:* `REPO_MAP.md:199`; `router.py:52-54`
- [ ] No new error class. Only `ConfigurationError` is raised. — *source:* `REPO_MAP.md:203`
- [ ] `FailureCode` is untouched, and `contracts/sdk-public-api.json` stays unchanged (`generate-sdk-public-api.py --check`). — *source:* `test_harness_threads_surface.py:218-241`; request.md:63-64; `contracts/README.md`
- [ ] Before editing inside a folder, read its README to the end (`vidbyte/agents/README.md`, `vidbyte/agents/jev/README.md`), and keep both ≤ 40,000 characters. — *source:* AGENTS.md Repository Map; A009
- [ ] No file under `docs/` is read or grepped except `docs/spec/loop-spend-cap/*` and `docs/design/release-0-4-0.md`. — *source:* AGENTS.md Repository Map; briefing §7
- [ ] No key-shaped literal in any changed file. — *source:* pipeline.md niche facts (GH013)
- [ ] The version stays 0.4.0, with no tag and no publish. — *source:* request.md §C.2 D-P2
- [ ] Every docstring, comment, README line, and message says "measured", never "capped", for spend the meter may not see. — *source:* INV-3; briefing

### 12.5 Non-code actions
- Folder README updates: `vidbyte/agents/README.md` (row 13) and `vidbyte/agents/jev/README.md` (row 17). — AGENTS.md Repository Map
- `llms.txt` `AgentLoopSettings` table, validation, and projection text (row 14). — AGENTS.md Repository Map
- The failure vocabulary sentence (row 15). — `skills/failure/vocabulary.md` rule
- The release record sentence, with the PR number added by S6 (row 16). — request.md §C (D-P2)
- No `__init__` export, no registration line, no `.env.example`, no changelog file (the repo keeps none beside the release record), and no `REPO_MAP.md` change, because `vidbyte/agents/` is mapped at folder level.
- Lint baseline: do **not** run `--update-baseline`. The base commit's seven IMPROVED rules are pre-existing slack. If this PR's own edits lower a rule further, note it in the PR body, and S6 decides.

### 12.6 Phases and dependency order
**P1 — Data contracts** (ships: the validated field reaches the runtime config and the repr; the stop reason and the completeness flag exist; nothing enforces yet, so behavior is unchanged): rows 2, 3, 4.
**P2 — Enforcement and routing** (ships: capped linear, Jev, and InfiniteMemory runs stop per INV-4..INV-9; sessions and evals classify the stop): rows 1, 5, 11, 12.
**P3 — Never silently ignored, and copy paths** (ships: refusals per INV-13 and survival per INV-15): rows 6, 7, 8, 9, 10.
**P4 — Documentation and release record** (ships: the caller contract written down for C3): rows 13, 14, 15, 16, 17.

**Dependency order:** row 3 (`AgentRuntimeConfig.max_spend_usd`, `MAX_SPEND`) → row 2 (`to_runtime_config` passes the field) → rows 4 and 1 (`cost_measured`, then `AgentSpendCap`, which reads it) → row 5 → rows 6–10. Rows 11 and 12 need only row 3. Rows 13–17 need the names to be final.

**Independent:** rows 7, 8, and 9 are independent of each other. Rows 11 and 12 are independent of rows 4–10. Rows 14, 15, and 16 are independent of each other.

## §13 Test seams (facts for the test author — no tests here)

- **Framework:** pytest. `testpaths=["tests"]` (`pyproject.toml:78-81`). Many files are `unittest.TestCase`/`IsolatedAsyncioTestCase`, collected by pytest. The narrow `scripts/test-*.py` scripts are not run by `run_ci.py` (`scripts/run_ci.py:79-93`).
- **Layout and naming:** feature packs live in `tests/features/<pack>/`. Each pack has a `README.md` (Folder Description / Intent, Non-Goals, File Index, Logs), a `FEATURE.md` (Contract, Actors, Inputs, Observable Outcomes, State Transitions, Invariants, External Dependencies, Known Failure Modes, Historical Regressions, Test Suite Map, Omitted Testing Strategies), and `test_*.py` files with the FILE/PURPOSE/ROLE… header. Existing sibling packs: `tests/features/sdk_loop_settings/`, `tests/features/sdk_model_usage/`, `tests/features/sdk_middleware_limits/`. The `sdk_loop_settings/test_contract.py` header says "Add an invalid value when a new public count or timeout field is introduced".
- **Prior art to copy:**
  - `tests/features/sdk_model_usage/test_nested_usage_bill.py`: a scripted `HttpTransport.request` wire (`_Wire`, `:54-79`); DeepSeek DIRECT with fake keys (`_kw`, `:34-36`); the priced model `deepseek-v4-flash` (`pricing.py:238`); it counts wire calls against `get_usage()` (`:97-110`). This is the closest end-to-end shape for a priced run and for the §4 snippet.
  - `tests/test_agent_runtime.py:606-633` (an `AgentRuntime` with `AgentRuntimeConfig(max_tokens=1)`) and `:879-894` (`AgentLoopSettings(max_tool_calls=2).to_runtime_config()`).
  - `tests/features/sdk_loop_settings/test_contract.py:24-41`: the parametrized invalid-value probes (bool, NaN, inf) with `pytest.raises(ConfigurationError, match=field)`.
  - `tests/test_session_failures.py:422-435`: stop-reason mapping and the exact details dict.
  - `tests/test_fork_tool.py:319-338`: guardrail inheritance.
  - `tests/test_jev_usage_ledger.py`: the Jev ledger and fail-closed behavior.
- **Fixtures / factories:**
  - `tests/agent_test_support.py:62-65` `bind_test_runner`.
  - `tests/test_jev_usage_ledger.py:41-50` `ScriptedGenerativeRunner`, returning `TextModelResponse(provider=OPENAI, model="gpt-5.4-mini", usage=…)`. Its decision calls are faked at `TypeSafeProvider.run_decision` (`:33`, `:65-73`). Its Vidbyte key fixture is concatenated at runtime (`:78`), so never write a key literal.
  - `SimpleNamespace(provider=…, model=…, usage={…})` responses feed `UsageTracker.record_call` directly (`tests/features/sdk_model_usage/test_usage_contract.py:47-65`). `UsageTracker(pricing=registry)` accepts a custom `ModelPricingRegistry` (`tracker.py:58-60`) for a known price. An agent's own tracker always uses the default pricebook (`base.py:291`).
  - `UsageRollup(...)` is a plain frozen dataclass and can be constructed directly with `calls`, `operations`, `unaccounted_call_count`, and `recording_integrity`.
- **Real seams (do not mock):**
  - The ledger itself (`UsageTracker`): it is what the cap reads.
  - `AgentRuntime._arun_once`.
  - `BaseAgent.generate_reply`'s ledger scope and merge (`base.py:852-905`).
  - `FailureMetadataNormalizer`.
  - Fake only the model wire (`HttpTransport.request`, a fake runner, or `TypeSafeProvider.run_decision`).
  - A `FakeResponse` in `tests/test_agent_runtime.py` has no `provider`/`model`, so `record_call` counts it as **unaccounted** (`tracker.py:80-96`). With a cap set, that alone trips the blind-meter stop. A priced runtime test needs a response that carries `provider`, `model`, and `usage`.
  - Priced models available offline: `gpt-5.4-mini` (OpenAI) at one flat rate (`vidbyte/lib/registries/pricing.py:168`), and `deepseek-v4-flash` (DeepSeek), whose rate depends on peak or off-peak time of day (`pricing.py:136-146`, `:238`). A threshold check on DeepSeek must cross the cap at both rates. `ModelProvider.OPENROUTER` with an unknown model and no `cost` is unpriced.
  - The §4 snippet passes no `api_keys` and no `model_mode`, so it runs in the default `TextModelMode.AUTO` (`vidbyte/agents/base.py:108`). AUTO needs a Vidbyte key, read from the `VIDBYTE_API_KEY` environment variable (`vidbyte/lib/constants/jev.py:68`), and sends each call through `VidbyteGatewayTransport` (`vidbyte/lib/http/vidbyte_gateway.py:150`). That transport is a decorator over `HttpTransport` whose inner `request` is the same seam `test_nested_usage_bill.py` patches with `monkeypatch.setattr(HttpTransport, "request", wire)` (`:88-92`). A test that runs the snippet as written sets the key in the environment, built at runtime, and answers gateway-shaped requests.
  - A non-text runner type is resolved by `Runner.resolve_runner_type()` from the provider and model (`base.py:1659-1674`).
- **Per-area config:** none beyond `pyproject.toml`. The source stage needs `PYTHONPATH=$(pwd)` in a worktree. Never export it, and never set it for the package stage.
- **Tests that pick up the new enum member automatically:** `tests/features/agent_output_connectors/test_output_connectors_dispatch.py:41`, `tests/multi_agent/test_manager_middleware_abort.py:64`, `tests/test_multi_provider_agentic_grader.py:793`. Their generic handling must keep passing (A-3).
- **Pins this change must leave green without edits:** `tests/features/harness_threads/test_harness_threads_surface.py:218-241` (`FailureCode`), `tests/test_session_failures.py:141-143` (every code has a category prefix) and `:430-435` (exact details), `tests/features/codex_host/test_codex_host_helper_surface.py:252-264`, and `tests/features/codex_host/test_codex_host_records.py:424-430`.
- **Run one file:** `PYTHONPATH=$(pwd) py -3.11 -m pytest -q <file>` · **Run all:** `PYTHONPATH=$(pwd) py -3.11 -m pytest`

## §14 Agent boundaries
- **Always:**
  - Work only in `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-loop-spend-cap`.
  - Use `py -3.11`, with `PYTHONPATH=$(pwd)` inline only, for lint, pytest, and the source stage.
  - Run the S2 pack plus `tests/features/sdk_loop_settings`, `tests/features/sdk_model_usage`, `tests/test_agent_runtime.py`, `tests/test_session_failures.py`, `tests/test_fork_tool.py`, and `tests/test_jev_usage_ledger.py` after each phase.
  - Run `lint/run.py` after each phase and confirm no rule is REGRESSED.
  - Run the full source and package stages before pushing.
  - Cite FR, AC, and W IDs in commit messages.
- **Ask first (stop and report BLOCKED):**
  - modifying **any** test file, including the S2 pack and the harness pins;
  - exceeding the §8.4 budget;
  - touching a file outside §12.3;
  - adding a `FailureCode` member, a root export, or a dependency;
  - changing `CostBudgetMiddleware`, `cost_complete`, or an existing budget's behavior;
  - adding a branch to `_process_tool_call`;
  - any lint rule REGRESSED that the §12.4 measures cannot fix;
  - reading any other file under `docs/`.
- **Never:**
  - commit secrets or a key-shaped literal;
  - delete, skip, xfail, or weaken a test;
  - raise `lint/baseline.json` or add a suppression or `noqa`;
  - change the version, tag, or publish;
  - push to `main`;
  - show the cap to the model;
  - describe unmeasured spend as capped;
  - implement anything not in §12, including any `Q-n` marked `[scope-adding]`.

## §15 Assumptions and open questions
**Assumptions** (stand unless the user corrects them):
- **A-1** — The SDK's rated cost (pricebook `PRICING_AS_OF = "2026-10-11"`, `pricing.py:58`, or the provider-reported cost) is the "spend" the user means. Whether the Vidbyte gateway (`TextModelMode.AUTO`) charges exactly the pricebook rate was not verified; the same adapters parse its responses (`vidbyte/lib/runners/text.py:3-5`). — *If wrong:* the cap still stops on rated spend, and C3 must label its figure "as measured by the SDK", not "billed".
- **A-2** — Importing `RecordFieldValidator` into `vidbyte/lib/dataclasses/agents.py` creates no import cycle. `validation.py` imports only `vidbyte.lib.constants.native_threads`, `vidbyte.lib.errors`, and `vidbyte.lib.util.credential_keys` (`validation.py:19-36`), and `vidbyte/lib/dataclasses/middleware.py` already imports it. — *If wrong:* validate `AgentRuntimeConfig.max_spend_usd` with an inline guard on a local `value` variable (C002 and C006 safe), and report it.
- **A-3** — The three tests that iterate `AgentStopReason` (§13) treat `max_spend` generically and pass unchanged. — *If wrong:* BLOCKED. Never edit them.
- **A-4** — Lint C019 does not flag the literals `"max_spend"` or `"max_spend_usd"`. `"max_spend"` is below the three-token shape (`c019_platform_error_code_contract.py:9`), and S1's simulation of the rule on both literals produced no finding. — *If wrong:* `lint/run.py --rule C019` names the site. Reuse the enum's `.value` there instead of the literal.
- **A-5** — ruff's C901 does not count the boolean operators in `cost_measured`, and the measured complexities (`_enforce_tool_settings` 6, `_budget_stop` 5, `_run_direct` 3, `AgentRuntimeConfig.__post_init__` 4, `_process_tool_call` 10) are as of `base_commit`. — *If wrong:* split `cost_measured` into a helper-free expression across two properties only if S008 regresses, and report it.
- **A-6** — No caller constructs `AgentRuntimeConfig` positionally. Every construction site in `vidbyte/` uses keywords or none (`vidbyte/agents/algorithms/independent_critic.py:123`, `vidbyte/agents/algorithms/prosecutor_defender_judge.py:242`, `vidbyte/agents/settings/loop.py:199`, `vidbyte/agents/runtime.py:199`, `vidbyte/agents/runtimes/search.py:63`, `vidbyte/agents/runtimes/actor/broker.py:70`). — *If wrong:* appending the field still breaks nothing, because it is last with a default.
- **A-7** — JevAgent's fresh-continuation agent, clones, swarm helpers, and bulk workers are `BaseAgent`s whose replies merge into JevAgent's tracker through `generate_reply` (`base.py:852-890`), as `_require_metered_specialists` requires of specialists. — *If wrong:* their spend would be invisible to the parent's cap; C011 (agent-owned usage) would flag an unrecorded call path.

**Open questions** (max 5 blocking):
| ID | Question | Blocking? | Default if unanswered |
|---|---|---|---|
| Q-1 | Value type (request.md §C Q1): USD float or Decimal, and is a non-positive or non-finite value rejected at construction? | non-blocking (answered) | **float**, validated by `RecordFieldValidator.require_number`, which rejects bool, NaN, ±inf, ≤ 0, and non-numbers with `ConfigurationError` at construction (D-2). The request's pointer "loop.py:11" is docstring text; the validators are at `loop.py:102-118`. |
| Q-2 | Unpriced calls (request.md §C Q2): refuse at construction, or count unknown spend as 0? | non-blocking (answered; request default replaced) | **Neither. Fail closed mid-run.** The next check point stops with `max_spend` and `cost_measured=False` (D-5). Counting unknown spend as 0 is exactly the "capped unmeasured spend" G-4 forbids. Construction refusal is neither necessary nor sufficient (OpenRouter-reported prices, fallback and child models, usage-less calls). |
| Q-3 | Child agents (request.md §C Q3): does child spend count? | non-blocking (answered; premise corrected) | **Yes, when each child's reply finishes** (`base.py:882-886`). The premise "`UsageRollup.per_agent`" is wrong: that field exists only on the after-the-fact sessions rollup (`vidbyte/lib/dataclasses/sessions.py:126-140`). Children built from the same loop settings are each capped against their own tracker. Concurrent children can together spend N × the cap within one segment (INV-6, EC-14). |
| Q-4 | Decision calls (request.md §C Q4): do Jev decision calls count? | non-blocking (premise false) | **They count, immediately.** The premise "billed by the gateway, not priced by the SDK" is false. The SDK prices `jev-1.13`, `jev-latest`, and `jev-preview` (`pricing.py:304-314`), and `DecisionModelRunner` records each call as `UsageKind.DECISION` into the active ledger (`decision.py:46-55`), which inside a JevAgent run is the agent's tracker (`jev/usage.py:33-37`, `jev/runtime.py:84`). Whether the gateway charges exactly that rate is A-1. |
| Q-5 | Overshoot (request.md §C Q5): "a run can exceed the cap by at most one call"? | non-blocking (premise false) | **The true bound is INV-6:** measured spend at the stop is below the cap plus the largest single segment. That is one model call only for a tool-free, child-free, algorithm-free run; one tool's whole child-agent tree for tool runs; and N concurrent capped children for swarm, bulk, or clone. A pre-call estimate is Q-7. |
| Q-6 | On a cap stop at a finish (CP2, or CP3 before isDone), return the model's paid-for answer as the output instead of the stop text? | non-blocking | **No.** Mirror `max_tokens` (`runtime.py:514-522`); the answer stays in `iteration_outputs` (D-10). |
| Q-7 | `[scope-adding]` Add a pre-call cost estimate that refuses a call likely to cross the cap? | non-blocking | **No** (NG-4). |
| Q-8 | `[scope-adding]` Give each child only the parent's remaining budget at launch (one budget shared across concurrent children)? | non-blocking | **No** (NG-6, D-8). |
| Q-9 | `[scope-adding]` Make drained queued prompts share the primary reply's cap, and skip the drain after a cap stop? | non-blocking | **No** (NG-11, EC-20). |
| Q-10 | `[scope-adding]` Carry the cap into the independent-critic and prosecutor-defender-judge reviewer sub-runtimes? | non-blocking | **No** (NG-11, EC-22). |
| Q-11 | `[scope-adding]` Also refuse at construction a capped agent whose configured main model has no pricebook entry (in addition to D-5)? | non-blocking | **No** (D-5). |
| Q-12 | `[scope-adding]` Root-export `UsageAccountingError` so C3 can catch JevAgent's fail-closed error by name? | non-blocking | **No.** request.md:64 prefers no new root names; C3 can classify by `type(exc).__name__`. |

Blocking questions: 0.

## §16 Review log
| Round | ID | Severity | Section | Finding (one line) | Disposition | Change made / reason |
|---|---|---|---|---|---|---|

## §17 Revision history
| Revision | Date | Stage | Summary |
|---|---|---|---|
| r1 | 2026-10-19 | S1 spec | Initial spec |
