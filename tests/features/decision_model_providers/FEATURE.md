# Feature: Decision model providers

## High-Level Feature Description

`DecisionModelRunner` answers the same `JevDecisionRequest` through nine providers instead of one: TypeSafe (existing), Perplexity, OpenRouter, Liquid AI, Baseten, meraGPT, Cloudflare, Microsoft Foundry (all on the System One wire through `SystemOneProvider`) and OpenAI (its Decisions wire through `OpenAIDecisionsProvider`). The developer changes `provider` (and `endpoint` for the two tenant-scoped hosts) and nothing else; the model defaults per provider, the key comes from a per-provider environment variable, vendor errors are rewritten with the host's name, and every call is metered with `UsageKind.DECISION`. Spec: `docs/spec/decision-model-providers/spec.md` r3.

## Contract

- `DecisionModelConfig(provider=P)` accepts exactly the nine members of `DECISION_SUPPORTED_PROVIDERS = frozenset(ProviderModelRegistry.DECISION_DEFAULT_MODELS)`; any other member raises `UnsupportedProviderError` listing the nine values sorted. `model=None` fills from `DECISION_DEFAULT_MODELS` and `resolved_model()` is the typed reader. `VIDBYTE_MANAGED` mode is TypeSafe-only. `validate()` resolves key and endpoint before any HTTP call; Cloudflare and Foundry have no default endpoint.
- Every System One host receives the TypeSafe body `{model, state, questions}` byte for byte, with OpenRouter additionally always carrying noul `criteria: {"true", "false"}`. The key travels only as `authorization: <scheme> <key>` (`Bearer`, or `Api-Key` for Baseten). OpenAI receives `{model, input, questions: [{type, name, instructions, choices?|levels?}]}` in request order with noul mapped to `predicate`.
- Every success returns one `JevAnswer` per requested question; noul normalizes identically on every wire; `DecisionModelResponse.model` is the pricebook key: the echo for TypeSafe and Perplexity, `config.resolved_model()` for every other host and OpenAI.
- HTTP failures are rewritten by one shared status table naming the host and its env var; normalization failures carry `details["usage"]`; unexpected exceptions become `ProviderResponseError`; cancellation propagates; `list_models` / `close_run` raise `ProviderConfigurationError` without a network call; an adapter refuses a per-call config for another provider.
- The usage ledger records every success and billed failure exactly once through `DecisionModelRunner.arun`; adapters never touch it. Priced rows exist only for Perplexity, Cloudflare, Foundry, OpenAI and TypeSafe; Liquid, Baseten and meraGPT record `cost_usd=None`.
- Nothing about TypeSafe changes: default config, wire bodies, messages, `_TypeSafeCallBuilder.decision`, `JevRuntimeSettings`'s managed-only rule, and `DecisionModelHelper` behave as today.

## Actors / Callers

`DecisionModelRunner` (and `DecisionModelHelper` above it), `ModelProviders.decision`, `DecisionModelConfig`, `ProviderModelRegistry`, `UsageTracker` through `active_usage_ledger()`, `JevRuntimeSettings` / `JevAgentSettings` / `Runner.build` as negative callers.

## Inputs and Preconditions

Offline only: a `ScriptedTransport` replaces `HttpTransport.request`; keys are placeholders passed explicitly or through `patch.dict(os.environ, ...)`; Cloudflare and Foundry tests pass a tenant `endpoint`. Everything else (config validation, registry resolution, `JevAnswer` validation, JSON parsing, pricing, ledger arithmetic) is the real code.

## Observable Outcomes

The transport's recorded `method`, `url`, `headers`, `json_body`, retry and idempotency kwargs; the returned `DecisionModelResponse` (`provider`, `model`, `answers`, `usage`); typed errors with their exact messages, `provider`, `status_code`, `response_excerpt`, and `details["usage"]`; `UsageTracker.records` and `rollup()` inside `usage_ledger_scope`; the catalog constants (`DECISION_DEFAULT_MODELS`, `SystemOneProvider.HOSTS`, runner maps, `PROVIDER_PRICING`, `PRICING_AS_OF`).

## State Transitions

None outside the ledger: a success appends one `UsageRecord(kind=DECISION, failed=False)`; a billed normalization failure appends one with `failed=True`; a call whose response has no usage increments `unaccounted_call_count`; transport failures and cancellation append nothing.

## Invariants

Spec INV-1 through INV-28 (section 6.1). The ones this pack can observe directly: nine-member support set, default fill, managed guard, key/endpoint resolution before any call, key only in the authorization header, byte-identical System One bodies, OpenAI body order, one answer per question, noul normalization, billed usage on errors, exactly-once metering, host-named failures, transport kwargs, fresh idempotency key, cancellation passthrough, `list_models`/`close_run` refusal, pricebook-keyed `response.model`, per-call config guard, and the TypeSafe must-not-regress set.

## External Dependencies

None at test time. The real boundaries (Perplexity, OpenRouter, Liquid, Baseten, meraGPT, Cloudflare, Foundry, OpenAI HTTP APIs) are represented by literal wire bodies copied from the spec's section 9.1 answer-kind matrix and `docs/spec/decision-model-providers/context/provider-research.md`.

## Known Failure Modes

Posting `Api-Key <perplexity key>` to Perplexity because an adapter accepted another provider's config; silently dropping noul option descriptions on OpenAI; pricing a Cloudflare call on the echoed `@cf/cloudflare/clef` id and recording `cost_usd=None`; a Perplexity user reading "TypeSafe rejected the API key"; a tenant host 404-ing after construction because an empty default endpoint was accepted; a partial answers map returned as success; a retried POST without an idempotency key; a billed failure that never reaches the ledger.

## Historical Regressions

None yet; this pack is written before the feature exists (spec pipeline stage S2, 2026-10-10) and is red until the implementation lands.

## Test Suite Map

- `decision_fixtures.py` — scripted transport, the section 4 request, System One and OpenAI response builders, the section 9.1 host table (`HOST_ROWS`), keyed runner factory.
- `test_decision_contract.py` — enum members, registry maps, runner catalogs, usage classes, `HOSTS` rows, `DecisionAuthScheme`, wire records, wire constants, factory routing, pricebook (INV-1, INV-20, FR-1, FR-2, FR-4, FR-10, FR-12, FR-13, section 9.1).
- `test_decision_config.py` — `DecisionModelConfig` fill, blank model, unsupported provider message, managed guard, tenant endpoints, missing key, explicit key/endpoint precedence, TypeSafe defaults (INV-1 to INV-4, INV-21, AC-7, AC-8, AC-9, AC-14, EC-1 to EC-5, EC-24).
- `test_decision_systemone_wire.py` — URL/auth/body per host, byte-equal Perplexity body, OpenRouter criteria, transport kwargs and idempotency key, noul/score/choice normalization, model echo rule, mismatch messages (INV-5, INV-6, INV-8, INV-9, INV-14, INV-15, INV-27, AC-2, AC-3, AC-4, AC-11, AC-18, EC-6, EC-9, EC-19, EC-27).
- `test_decision_openai_wire.py` — Decisions body, answers by name, JSON-text content, noul-description refusal, refusal answers, drift, label fallback, request-id model, 64-question order (INV-7, INV-8, INV-9, INV-27, AC-5, AC-6, AC-17, EC-7, EC-8, EC-10, EC-11, D-8).
- `test_decision_failures.py` — status table per host, non-JSON excerpt, unexpected wrap and cancellation, `list_models`/`close_run`, per-call config guard, `SystemOneProvider` construction, key never leaks, shared `DecisionFailures` (INV-5, INV-13, INV-16, INV-17, INV-28, AC-10, AC-13, AC-19, EC-12 to EC-14, EC-20, EC-23, EC-25, EC-28).
- `test_decision_usage_metering.py` — pricing per host, OpenRouter cost precedence and System One usage keys, billed failures, unaccounted calls, nothing recorded on transport failure, two providers in one scope, adapters never touch the ledger (INV-10, INV-11, INV-12, INV-18, INV-19, AC-4, AC-6, AC-12, EC-17, EC-18, EC-21).
- `test_decision_acceptance.py` — the section 4 snippet and the "change provider and nothing else" property over all nine providers (AC-1, section 4).
- `test_decision_regression_typesafe.py` — TypeSafe defaults, shared message template, `_TypeSafeCallBuilder` returns `DecisionHttpCall`, adapter signature parity, `JevRuntimeSettings` managed-only rule, `Runner.build` refusal for decision providers, `DecisionModelHelper` over Perplexity answers (INV-21 to INV-25, AC-14, AC-15, EC-22).

Run: `python -m pytest tests/features/decision_model_providers -q`.

## Omitted Testing Strategies

No network, no timing, no concurrency beyond one `asyncio.gather` of two scripted runners, no property-based library (not a dev dependency). The TypeSafe managed gateway for other providers is out of scope (spec Q-1, NG). `vidbyte.__all__` is pinned by lint C016, not here. Cloudflare's silent state truncation (EC-16) has no SDK-observable behaviour and is not tested. Documentation rows (FR-15) are reviewed, not tested.
