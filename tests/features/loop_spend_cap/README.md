# Loop spend-cap probes

## Folder Description / Intent

This folder holds the offline proof that `AgentLoopSettings(max_spend_usd=…)` stops an agent's spend. Each test runs real agents, the real runtime loop and the real usage ledger against scripted model responses, and every expected dollar figure is computed from the live pricebook when the test runs. The tests cover the four check points in the loop, the blind-meter stop, the refusals at construction, every path that copies the loop settings, and each component that must end a run once the cap stops it, rather than review, grade, retry or continue it.

The pack was written from the approved spec (`docs/spec/loop-spend-cap/spec.md` r3) before the feature existed. Read `FEATURE.md` first: it lists the contract, the failure each test catches, and the strategies that were deliberately left out.

## Non-Goals

- Do not add production code here; `vidbyte/agents/runtime.py`, `vidbyte/agents/spend_cap.py` and `vidbyte/agents/pricing/` own enforcement and measurement.
- Do not mock the usage ledger, `AgentRuntime._arun_once`, the ledger scope in `BaseAgent.generate_reply`, or `FailureMetadataNormalizer`; fake only the model wire.
- Do not copy price rates, model counts or version strings into a test; read them from `vidbyte.lib.registries.pricing` at run time.
- Do not test overlapping replies on one agent object (EC-35, R-6) as if they kept separate caps; the spec states this as a limitation.
- Do not add tests for the scope-adding questions Q-7 to Q-14.
- Do not read anything under `docs/` from a test.

## File Index

- `FEATURE.md` records the contract, the failure inventory with spec IDs, the suite map and the omitted strategies.
- `loop_spend_cap_fixtures.py` is the shared offline harness: the scripted runner, priced and unpriced model names, pricebook-derived costs, the stop texts and the agent and runtime builders.
- `test_loop_spend_cap_contract.py` checks the settings and runtime-config validation, `cost_measured`, the `max_spend` stop reason, `AgentSpendCap.stop_output` and the export surface.
- `test_loop_spend_cap_runtime.py` checks the four check points, the blind stop, the tie order with other budgets, and that a cap the run never reaches changes nothing. Open this first when a capped run spends past its cap.
- `test_loop_spend_cap_children.py` checks that a sub-agent tool and concurrent capped children count against the parent's cap.
- `test_loop_spend_cap_refusals.py` checks the construction refusals: non-linear runtimes, non-text runners, unpriced primary and fallback models, forks and Codex.
- `test_loop_spend_cap_copy_paths.py` checks that checkpoints, YAML, `AgentForker` and the fork tool keep the cap, and that the model cannot set it.
- `test_loop_spend_cap_run_ending.py` checks that reflexion, the critic, prosecutor-defender-judge, the grader, MultiAgent, InfiniteMemory, queued prompts and output schemas end the run on a cap stop.
- `test_loop_spend_cap_failure_routing.py` checks the session failure record and the efficiency eval for a cap stop.
- `test_loop_spend_cap_jev.py` checks the JevAgent specialist guard, preflight spend, continuations and the fail-closed unpriced call.
- `test_loop_spend_cap_docs.py` checks that the READMEs, `llms.txt` and the skill guides name the cap.
- `test_loop_spend_cap_acceptance.py` runs the spec's section 4 developer snippet as written and checks that the cap never reaches the model's request.

## Logs

- 2026-10-20 - Pack written before implementation (spec r3, S2). All tests are red on the base commit for the missing names; a throwaway prototype of spec section 12 turned every test green, and 42 single-fault mutants of that prototype were each caught.
