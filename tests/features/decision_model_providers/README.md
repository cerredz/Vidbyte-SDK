# Decision model provider probes

## Folder Description / Intent

This folder proves the decision-model-providers feature (`docs/spec/decision-model-providers/spec.md`) from the outside: nine providers behind one `DecisionModelRunner`, each with its documented URL, auth scheme, default model, host-named failures, and `UsageKind.DECISION` metering. Only `HttpTransport.request` is replaced; configuration, registry, answer validation, pricing, and the ledger are the real code. Written before the implementation, so every test is red until the spec lands.

## File Index

- `README.md` describes the scope and test ownership.
- `FEATURE.md` states the contract, the observable outcomes, and which spec IDs each file covers.
- `decision_fixtures.py` holds the scripted transport, the section 4 request, response builders, the section 9.1 host table, and the keyed runner factory.
- `test_decision_contract.py` pins the catalog: enum members, registry rows, runner maps, `HOSTS`, `DecisionAuthScheme`, wire records, constants, factory routing, pricebook.
- `test_decision_config.py` pins `DecisionModelConfig` construction and validation rules.
- `test_decision_systemone_wire.py` pins the System One wire for the seven direct hosts plus TypeSafe.
- `test_decision_openai_wire.py` pins the OpenAI Decisions wire.
- `test_decision_failures.py` pins failure mapping, capability refusals, the per-call config guard, and credential hygiene.
- `test_decision_usage_metering.py` pins what reaches the usage ledger and at what price.
- `test_decision_acceptance.py` runs the spec's section 4 snippet over scripted transports.
- `test_decision_regression_typesafe.py` pins what must not change about TypeSafe while binding it to the shared pieces.

## Logs

- 2026-10-10 - Pack created at spec pipeline stage S2 (test author); all tests red for missing symbols, missing modules, or today's one-provider messages.
