# Feature: An optional USD spend cap that every agent's own loop enforces

## High-Level Feature Description

`AgentLoopSettings(max_spend_usd=…)` caps one reply's measured spend. The shared agent loop reads the agent's own priced usage ledger at four check points and stops the run with `stop_reason == "max_spend"` once the measured spend reaches the cap, or once the spend can no longer be fully measured. Every agent that cannot enforce or measure the cap refuses it at construction, before any spend, and a capped stop ends the run: nothing reviews, grades, reflects on, verifies, or retries it, and no queued prompt runs after it.

## Contract

- `AgentLoopSettings.max_spend_usd` and `AgentRuntimeConfig.max_spend_usd` accept only `None` or a finite real number greater than 0 (never a `bool`). Anything else raises `ConfigurationError` naming `<Class>.max_spend_usd`, with `details["field"]` set (INV-14).
- `UsageRollup.cost_measured` is a derived, read-only property. It is True exactly when integrity is INTACT, no call went unaccounted, and every call and operation has a cost. An empty rollup is measured (INV-2).
- At CP1 (loop top), CP2 (plain-text finish, before every finish step), CP3 (before every tool call, internal tools included), and CP4 (after `after_iteration`, before `_after_tool_iteration`), a capped run stops when `cost_usd >= cap` ("reached"), or else when `not cost_measured` ("blind"). The spend cap is checked before any other budget sharing that check point (INV-4, INV-5, INV-8).
- The stop texts are exact: `"Agent runtime stopped after reaching max_spend_usd."`, or `"Agent runtime stopped because max_spend_usd is set and this run's spend could not be fully measured: <causes>."` with the causes in the INV-9 order.
- Construction refuses a capped non-linear runtime, a non-text runner, an unpriced configured primary or fallback model (OpenRouter excepted), a JevAgent specialist without a cap no higher than JevAgent's, and a capped `CodexHarnessAgent` (INV-13).
- Sessions map `max_spend` to `resource.exhausted`, and the efficiency eval counts it as a budget stop (INV-10).
- A cap stop ends the run (INV-23), and the cap survives every copy of the loop settings while staying out of the model's prompt (INV-15, INV-16).

## Actors / Callers

SDK developers who set the cap in Python or YAML; vidbyte-cli PR C3, which reads `stop_reason`, `get_usage().cost_usd`, and `cost_measured` (spec section 9.2); a model that tries to escape the cap through `fork_conversation` or `run_prompts_sequentially`; child agents (tool sub-agents, forks, Jev specialists, InfiniteMemory pairs, MultiAgent workers and manager phases); context-window algorithms (reflexion, independent critic, prosecutor-defender-judge, multi-provider grader).

## Inputs and Preconditions

A cap value; a configured provider and model (priced, unless OpenRouter); scripted model responses that carry `provider`, `model`, and `usage`. Every test runs offline: the only fake is the model wire (a runner bound to the agent, a `RunnerHandle`, `TypeSafeProvider.run_decision`, or `HttpTransport.request` for the section 4 snippet).

## Observable Outcomes

`reply.metadata["stop_reason"]`, the reply's output text, `reply.metadata["usage_rollup"]` and its `cost_measured`, `agent.get_usage()`, `reply.metadata["iteration_outputs"]`, `queued_prompts_truncated` and `queued_prompt_runs`, which tools executed and how many model calls the scripted runner received, construction errors and their messages, `MultiAgentExecutionError.details`, `OutputSchemaViolationError.stop_reason`, the session `Failure` record, and `EfficiencyBehavior.did_not_stop_on_budget()`.

## State Transitions

Running → stopped(`max_spend`) at the first check point where the ledger reached the cap or went blind. A stopped reply then runs only `after_run` middleware and a configured auto-handoff; no further model call, tool call, finish attempt, compute checkpoint, review, reflection, grade, verifier, parse retry, worker retry, or queued prompt follows.

## Invariants

- A run whose measured spend stays below the cap and stays measured behaves exactly like the same run without a cap (INV-8, INV-17).
- Spend equal to the cap stops (`>=`); spend one float step below it does not (EC-25).
- `cost_usd` of a blind run excludes the unpriced call (it stays a lower bound).
- A child's spend counts in the parent only after the child's reply finishes, and each capped child enforces the cap against its own ledger (INV-12).
- The model can neither set, raise, nor clear the cap (T-2).

## External Dependencies

None at test time. Prices come from the live SDK pricebook (`vidbyte.lib.registries.pricing`), read at test time, never copied into a test. The section 4 snippet runs through the real gateway transport with `HttpTransport.request` scripted.

## Known Failure Modes

The failure inventory below lists, for each failure, the input and state, and the wrong output it would produce without the guard.

| Spec ID | Input + state | Wrong output without the guard |
|---|---|---|
| EC-1, EC-2, EC-3, EC-4 | `max_spend_usd` = `nan`, `True`, `inf`, `0`, `-1`, `"5"`, in Python or YAML | `x >= nan` is always False, so the run is silently uncapped; `True` means $1; `"5"` raises a raw `TypeError` mid-run |
| T-3 | a long or secret-looking string as the cap | the error message echoes the value |
| AC-4 (CP3) | call k reaches the cap and asks for tools | every tool of call k still runs, including launch tools that start spending agents |
| AC-5 (CP2), EC-12 | the call that reaches the cap is a plain-text answer | review, done checks, `after_iteration`, and a continuation all still spend |
| AC-6, D-11 | spend ≥ cap when the model calls isDone or an internal launch tool | the internal tool is exempt (it skips `_enforce_tool_settings`'s budgets), so it runs |
| AC-7, EC-15 | a tool (priced search or sub-agent) crosses the cap mid-turn | the next tool in the turn runs; the compute checkpoint starts clones |
| AC-8, AC-9, EC-5, EC-6, EC-9 | a response with no usage, or naming an unpriced model, or OpenRouter without a cost | `cost_usd` sums only priced records, so the run looks cheap and never stops |
| AC-22, EC-24, INV-8 | the cap and another budget are both exhausted at one check point | the run reports `max_iterations` / `max_tokens` / `max_tool_calls` and the caller never learns that money stopped it |
| EC-25 | measured spend equals the cap exactly | `>` instead of `>=` lets one more segment spend |
| AC-11, AC-12, AC-30, EC-32 | a capped MCTS or actor runtime, an image model, or an unpriced primary or fallback model | the cap is accepted and never enforced, or the meter is blind from the first call |
| AC-13, EC-18 | a capped JevAgent delegates to an uncapped specialist | a delegated run never enters JevAgent's loop and spends uncapped |
| AC-27, EC-39 | a capped `CodexHarnessAgent` | Codex owns its loop, so nothing checks the cap |
| AC-14, EC-17 | Jev preflight decision calls alone reach the cap | the first generative call still happens |
| AC-15, INV-12, EC-14 | a tool runs child agents, alone or concurrently | child spend is invisible to the parent, or a child ignores the inherited cap |
| AC-16, INV-15, EC-28, EC-29 | export/restore, YAML, `AgentForker` with `max_iterations`, the fork tool with a loop override or a `max_spend_usd` argument | the cap silently drops, or the model raises or clears its own budget |
| AC-21, INV-16, D-14 | the system prompt is rendered | the model reads its budget and spends up to it deliberately |
| AC-23, AC-28, AC-29, INV-23 | a capped stop under reflexion, critic, PDJ, grader, MultiAgent, InfiniteMemory | the stopped attempt is reflected on, reviewed, graded, verified, or retried with a fresh cap |
| AC-31, AC-32, EC-20, EC-40, T-2 | queued prompts (from code or from the model) after a capped stop | each queued prompt runs as a new reply with a fresh cap |
| AC-17, AC-18, INV-10 | a session or eval reads a `max_spend` reply | the stop falls through to `runtime.error`, or the eval reports no budget stop |
| AC-25, INV-20, EC-19 | a capped JevAgent records an unpriced call | the cap stop hides the fail-closed `UsageAccountingError` |
| AC-20 | a Jev continuation grants a budget extension | the extension drops or replaces the cap |
| AC-1 | the section 4 snippet run as written | it prints the wrong line, or more than one |
| AC-26, FR-10 | the READMEs, `llms.txt`, and skills | the docs never name the cap or call unmeasured spend capped |

## Historical Regressions

None yet: this pack was written before the feature existed (spec r3, S2 stage), from the approved spec alone.

## Test Suite Map

- `test_loop_spend_cap_acceptance.py`: AC-1 (the section 4 snippet, run as written, for each of its three lines) and AC-21 (the cap never reaches the wire).
- `test_loop_spend_cap_contract.py`: AC-2, AC-3, AC-19, T-3, the `AgentStopReason.MAX_SPEND` value, `AgentSpendCap.stop_output` boundaries and cause text, and the export surface (D-16, AC-24's names).
- `test_loop_spend_cap_runtime.py`: AC-4 to AC-9, AC-22, EC-25, INV-8 ties at CP2 and CP3, and the capped-below-the-cap equals uncapped metamorphic check.
- `test_loop_spend_cap_children.py`: AC-15, AC-7 through a sub-agent, and concurrent capped children (EC-14, INV-12).
- `test_loop_spend_cap_refusals.py`: AC-11, AC-12, AC-27, AC-30, and the refusal on a child fork (INV-12).
- `test_loop_spend_cap_copy_paths.py`: AC-16, EC-4 through YAML, EC-28, EC-29, EC-30.
- `test_loop_spend_cap_run_ending.py`: AC-23, AC-28, AC-29, AC-31, AC-32.
- `test_loop_spend_cap_failure_routing.py`: AC-17, AC-18.
- `test_loop_spend_cap_jev.py`: AC-13, AC-14, AC-20, AC-25.
- `test_loop_spend_cap_docs.py`: AC-26 (everything outside `docs/`).
- `loop_spend_cap_fixtures.py`: the shared offline harness.

Run with `PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/loop_spend_cap`.

## Omitted Testing Strategies

- No timing or performance test for NFR-2 (≤ 10 ms per check): wall-clock assertions are nondeterministic on shared CI machines, and the spec measured it.
- No test pins `10**400` raising `OverflowError` (INV-14): that is a documented quirk of the shared validator, not a promise, and pinning it would block a later fix.
- No test asks for two overlapping replies on one agent object to keep separate caps (EC-35, R-6, Q-14): the spec states it as an accepted limitation.
- No test for Q-7 to Q-14: they are scope-adding, and their default answer is No.
- No property-based library: Hypothesis is not installed, so the algebraic `cost_measured` rule is checked exhaustively over all sixteen combinations plus the empty rollup.
- The public-API contract file and the `FailureCode` order (AC-24) are already checked by lint C016, `scripts/generate-sdk-public-api.py --check`, and the harness-threads pins; this pack only checks that `AgentSpendCap` is not exported and that no spend-named `FailureCode` appears.
- The 0.4.0 release record lives under `docs/`, which these tests must not read; AC-26's release-record clause is left to review.
- No network: every model call is scripted.
