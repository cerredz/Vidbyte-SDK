# Agent reasoning effort probes

## Folder Description / Intent

This folder holds the offline proof that `reasoning_effort` does what the spec promises on the real HTTP wire. Every "sent" cell of the spec's section 9.2 table must reach the vendor body as exactly its fragment, deep-merged, with the URL, headers and key unchanged. Every effort the SDK cannot send must be refused at construction with the section 8.5 text and no request. The effort must reach JevAgent's main agent and its eight children, but never the brief writer, specialists or decision calls. Leaving it unset must change nothing. The tests drive real agents, runners, adapters and JevAgent; only the network is faked.

The pack was written from the approved spec (`docs/spec/agent-reasoning-effort/spec.md` r3) before the feature existed, and extended for spec r4 after the S4 review (algorithm-built runners, the `options` channel, every non-text runner type, a restored chain). Read `FEATURE.md` first: it lists the contract, the failure each test catches, and the strategies that were deliberately left out.

## Non-Goals

- Do not add production code here. `vidbyte/lib/configs/reasoning_effort.py` owns the table, `vidbyte/lib/registries/reasoning_effort.py` the lookup and texts, `vidbyte/agents/reasoning_effort.py` the construction guard, and the four payload builders the attach.
- Do not bind a `ScriptedRunner` to observe a body: it bypasses the adapters, so the fragment never shows. Fake only `HttpTransport.request` or a runner's transport.
- Do not copy the production table, `REASONING_EFFORT_AS_OF`, prices, export counts or versions into a test. The oracles are the spec's section 9.2 and 8.5 text, kept in `agent_reasoning_effort_fixtures.py`.
- Do not pin the table's size or key set, so a later sourced row keeps the pack green.
- Do not test that a per-hop effort survives restore (D-6), the scope-adding questions Q-1 to Q-11 (Q-11: forwarding the effort into an algorithm's own runners), assumption A-4, or a refusal of an `agent.algorithm` assigned after construction (EC-34).
- Do not read anything under `docs/` from a test.

## File Index

- `FEATURE.md` records the contract, the failure inventory with spec IDs, the suite map and the omitted strategies.
- `agent_reasoning_effort_fixtures.py` is the shared offline harness: the section 9.2 oracle tables, the section 8.5 text builders, the context-window algorithm configurations and non-text models the r4 tests share, the `Wire` and `StreamWire` recorders, run-time provider keys and the agent builders.
- `test_agent_reasoning_effort_acceptance.py` runs the spec's section 4 developer snippet as written.
- `test_agent_reasoning_effort_contract.py` checks the enum, the three root names, the public-API contract, the root header bullet, the package exports, the keyword-only signatures (both guard methods included), the table date and the README sources section.
- `test_agent_reasoning_effort_registry.py` checks every table line, the ids with no row, the table's structure, the wire forms, normalization, the registry texts and their order, and that `attach` deep-merges a private copy.
- `test_agent_reasoning_effort_wire.py` checks every sent cell's body on the wire, through the config, an agent, a stream, `Runner` (keyword and `options`), a fallback chain and an algorithm on the agent's own runner, beside structured output, temperature and a disjoint `extra_body`. Open this first when a vendor receives the wrong body.
- `test_agent_reasoning_effort_refusals.py` checks every construction refusal and its exact text: refused cells, ids with no row, gateway modes, fallback chains, `thinking_config` and `extra_body` overlaps, bad values, every non-text runner type, `options` efforts, algorithms that build their own runners, a missing identity, and the refusal order.
- `test_agent_reasoning_effort_copy_paths.py` checks checkpoints, restore (a fallback chain included), forks, the fork tool and the side agents.
- `test_agent_reasoning_effort_jev.py` checks each JevAgent child on the main model, and that the brief writer, specialists and decisions are excluded.
- `test_agent_reasoning_effort_unset.py` checks that an unset effort changes no request in any provider, mode or algorithm configuration, and no checkpoint.
- `test_agent_reasoning_effort_usage.py` checks that billed reasoning tokens reach `UsageRollup` for each vendor's usage shape.

## Logs

- 2026-10-20 - Pack written before implementation (spec r3, S2). Every test is red on the base commit because the feature's names and fields do not exist yet; see `docs/spec/agent-reasoning-effort/test-plan.md` for the red run.
- 2026-10-21 - Spec r4 additions (S2b) after the S4 review findings R-1, R-2, R-3, R-4 and R-9: the algorithm refusal, the `options` channel, four non-text runner types and a restored chain. The algorithm, `options` and non-text refusals are red until the S5 repair; `test-plan.md` has the red set and the mutation results.
