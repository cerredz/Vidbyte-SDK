# Decision model provider probes

## Folder Description / Intent

This folder proves the decision-model-providers feature (`docs/spec/decision-model-providers/spec.md`) from the outside: sixteen providers behind one `DecisionModelRunner`, each with its documented URL, auth scheme, default model, host-named failures, and `UsageKind.DECISION` metering. Only `HttpTransport.request` is replaced; configuration, registry, answer validation, pricing, and the ledger are the real code. The pack was written before the implementation (spec pipeline stage S2) and is green on the built feature; tests added by a later scoped grant can be red until the matching repair lands, and `docs/spec/decision-model-providers/test-plan.md` ("Test changes after S2") records which ones.

## File Index

- `README.md` describes the scope and test ownership.
- `FEATURE.md` states the contract, the observable outcomes, and which spec IDs each file covers.
- `decision_fixtures.py` holds the scripted transport, the section 4 request, response builders, the section 9.1 host tables (`HOST_ROWS`, `R8_HOST_ROWS`, `ALL_HOST_ROWS`), and the keyed runner factory.
- `test_decision_contract.py` pins the catalog: enum members, registry rows, runner maps, `HOSTS`, `DecisionAuthScheme`, wire records, constants, factory routing, pricebook.
- `test_decision_config.py` pins `DecisionModelConfig` construction and validation rules.
- `test_decision_systemone_wire.py` pins the System One wire for the fourteen direct hosts plus TypeSafe.
- `test_decision_openai_wire.py` pins the OpenAI Decisions wire.
- `test_decision_failures.py` pins failure mapping, capability refusals, the per-call config guard (including the managed per-call refusal), `DecisionHttpCall` validation, and credential hygiene.
- `test_decision_usage_metering.py` pins what reaches the usage ledger and at what price.
- `test_decision_acceptance.py` runs the spec's section 4 snippet over scripted transports.
- `test_decision_regression_typesafe.py` pins what must not change about TypeSafe while binding it to the shared pieces.

## Logs

- 2026-10-10 - Pack created at spec pipeline stage S2 (test author); all tests red for missing symbols, missing modules, or today's one-provider messages.
- 2026-10-10 - Spec r6 grant: Liquid `d1` and meraGPT `sd-1` priced at 0.04 in three tests.
- 2026-10-10 - Spec r8 grant: seven more System One hosts (Celeris, Nace.AI, Upstage, Inception, Hanzo, Vansa, ZooData) in `R8_HOST_ROWS`, Baseten and `gpt-6-luna` pricing, price-proof and Mercury Decide keying tests; 87 tests, 24 red on the r6 implementation.
- 2026-10-10 - Spec r10 grant: EC-34 now expects Baseten's bare alias `mercury-decide` to pass settings and be refused at runner build; 87 passed on the built implementation.
- 2026-10-10 - S4 review grant: OpenRouter one-key noul criteria (R-1), `DecisionHttpCall` validation (R-2, AC-23), the managed per-call refusal (R-3), and the OpenAI duplicate-option guard (R-4); 90 tests, the R-1 cases and the R-2 test red until the repair lands.
