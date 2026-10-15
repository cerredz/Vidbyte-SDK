---
slug: byok-api-keys
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-12 16:20
flags: none
companion_run: vidbyte (backend), slug byok-fee-relay, worktree C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-byok-fee-relay
---

# Request: Agents take `vidbyte_api_key` and a list of provider `api_keys`, matched to providers automatically, and every text call goes through the Vidbyte gateway with the caller's own key (SDK half)

## 0. This run's scope (orchestrator's summary; §A–§D are the source)

This run builds the SDK half in cerredz/Vidbyte-SDK: §B.2 and §B.4 "Part B", AS AMENDED by Prompt 5 and Prompt 6 (see §C "Changes the user made after the handoffs"), built to the cross-repo wire contract in §C. In short:
- Agents (and the model config they build) take `vidbyte_api_key` and `api_keys`. `api_keys` replaces today's `api_key` (the user: "extend the api_key functionality into the api_keys functionality"); it is a LIST of provider keys in any order, and the SDK assigns each key to its provider deterministically, without the developer naming providers.
- A lib-layer class (new, under `vidbyte/lib/`) classifies each key to its provider from its format, checks the keys against the provider/model the agent and its fallbacks use, and selects the key for each call. The user expects this to be exercised hard ("play with to really make sure this feature works under the hood").
- `TextModelMode.DIRECT` is added (vendor-direct, no Vidbyte key, no fee). AUTO requires a Vidbyte key and goes through the gateway: relay with `X-Vidbyte-Provider-Key` when it holds a key for the call's provider, Vidbyte-paid otherwise. Explicit VIDBYTE_MANAGED stays Vidbyte-paid.
- The gateway transport sends the provider key only in that one header; error wording updated; the streaming runner's refusal names DIRECT; fallback/fork carry the key list so each provider gets its own key.
- No re-vendored platform contract is needed: the route list is unchanged; the header name is mirrored as a constant.

Not in this run: any backend change (the companion run); vidbyte-cli's rename to `api_keys` (the user: "Simply renames for the vidbyte-cli should be easy to fix" — a follow-up after this SDK is released, since the CLI consumes a published SDK); the backend pin bump; relay streaming; stored keys; the Jev `DecisionModelConfig` key. The live end-to-end test with the user's real keys runs after both runs are green, driven by a separate agent.

## A. Every user prompt in this conversation, verbatim and in order

**Prompt 1** (opening question; the session was a /talk design conversation):
````
I have a question for the business model of the vidbyte-sdk/, recently, we made the change of running all requests/routes through the vidbyte/ repo, and the reason we did this was to encur a 2% token markup and then we would have api keys with credits on them. This creates some problems though, I feel as though as a small-scale startup we wouldnt be able to have enough credits for large scale customers, and I feel like I want to revert back to BYOK, but my  question to you is that is there a way to support BYOK AND a token markup, i feel like this would be the ideal. Maybe we require users to have a vidbyte and model key. Maybe we just use the user's api key on the backend and still forward it to vidbyte? how do we go about this, i want to still have our token markup but without making it so that we have to buy all of the credits
````

**Prompt 2** (after the first technical answer):
````
can you explain all of this more briefly and in simpler english, what does all of this really mean, explain in non-technical terms
````

**Prompt 3**:
````
and can you explain, simply, in english, how we are going to acctually implement something like this?
````

**Prompt 4**:
````
you can explain this technically here for this request.  Can you give me like the details step by step high level technical  instructions of things that we have to do and why we have to do them to support BYOK AND the vidbyte markup on all tokens that the user uses through the sdk? go over everything in both repos.
````

**Prompt 5** (the /spec-pipeline invocation):
````
great, just to be clear. I want the agents iin our vidbyte-sdk/ param to have both a vidbyte_api_key and an api_keys param in the paramter of the model. under the hood we shoul have a lib class that makes sure that the user is inputting the correct api key that matches the provider/model that they are inputting (can prob be matches with the pricebook, api keys that start with "sk-" can be matches with antrhopic, etc. This you are probably going to have to play with to really make sure this feature works under the hood, dont want developers to have to worry about this. Then we pass the api key to our vidbyte endpoint where we route the request through to the model using the user's api key. We should then make sure that either throughout the run or after the run we take the token markup however you see fit, and make sure that whatever we talked about in this converation that relates to this request is implemented. When testing, I have a grok_api_key that you can use to test out this feature (coding your own grok agents, make sure to put the max spend/tokens only at a few cents) and a vidbyte api key, to make sure that the api key does not run out of credits. Do not stop until this feature is perfect, if you need to ask any clarifynng questions before creating the spec feel free to do so
````

**Prompt 6** (the user's answers to three clarifying questions the orchestrator asked before the spec; question text abbreviated, answers verbatim):

- Q: "What shape should the new `api_keys` agent parameter take? ... OpenAI, DeepSeek and Kimi keys all start with `sk-`." Options offered: "List or dict (Recommended)", "List only", "Dict only".
  A: selected **"List only"** (preview `api_keys=["xai-…", "sk-ant-…"]`), with this note, verbatim:
  ````
  Note, we can under the hood deterministically match the api keys to the provider so we dont actually need  the user to define the provider, make sure to take this into account during impleeplementation
  ````
- Q: "How should I run the live Grok test with your real Vidbyte key? The backend change has to be running somewhere for the test to go through Vidbyte." Options offered: "Local backend (Recommended)" — run the backend branch on this machine using backend/.env, which points at the Atlas "Vidbyte" database (probably production); real wallet debited a few cents; nothing deployed or merged. "Merge and deploy". "No live calls".
  A: selected **"Local backend (Recommended)"**.
- Q: "What should happen to the existing single `api_key` parameter that agents and model configs take today?" Options offered: "Keep it working (Recommended)", "Remove it".
  A: (free text, verbatim):
  ````
  can you just extend the api_key functionality into the api_keys functionality. I presume we already have some important logic that can be carried over into the api_keys param. Simply renames for the vidbyte-cli should be easy to fix for the agents that we already have
  ````

## B. Handoff blocks and decision ledger (verbatim)

These were written by the assistant during the /talk conversation, BEFORE Prompt 5 and Prompt 6. Where Prompt 5 or Prompt 6 contradicts them, Prompt 5/6 wins (see §C "Changes the user made after the handoffs").

### B.1 Handoff — backend (answer to Prompt 1)

````markdown
Goal: POST /api/v1/models/generate relays a call under the caller's own provider key when the request carries one and bills the wallet only Vidbyte's 2% fee on the SDK-priced provider cost; a request without the key behaves exactly as today.
Repo / base: cerredz/Vidbyte; branch off origin/main in a fresh worktree; open the PR against main, never a feature branch
Scope: route header; orchestrator branch; provider client credential source; meter fee-only basis; session id scope; Sentry header scrubbing; tests; folder READMEs and file headers
Non-goals: streaming; stored provider keys; the Jev route; the Vidbyte-paid markup rate; the SDK (separate PR after this merges)
Approach: the route declares an optional provider-key header; GenerativeModelClient.plan sets GenerativeCallPlan.credential (new enum ModelGatewayCredentialSource: VIDBYTE, CALLER) from its presence; send(plan, caller_key) builds the dialect auth header from the caller key under CALLER and skips the _VIDBYTE_REFUSALS remap; the orchestrator under CALLER admits on the fee-only worst case, takes no daily-spend hold, and records with basis FEE_ONLY; ModelUsageSessionDto gains billing_basis (new enum ModelUsageBillingBasis: TOTAL, FEE_ONLY; default TOTAL) and settle, summary, and _ledger_write owe ceil(fee) under FEE_ONLY; the session id adds the basis as a fifth part. Rejected: key in the envelope body, because it enters the replay hash and the DTO; stored keys, because of secrets at rest.
Patterns to follow: backend/orchestrators/routes/model_gateway.py GenerativeModelGatewayOrchestrator for the sequence and the logged-not-raised billing rule; backend/provider/generative_models/client.py _key for last-moment credential fetch; backend/services/model_gateway/metering.py record_generative and settle for accrual and claim-then-debit; backend/lib/dataclasses/model_gateway.py for the validated plan field; backend/lib/enums/model_gateway.py for the two enums; backend/lib/config/model_gateway.py for the header name constant; backend/tests/features/model_gateway/test_generative_gateway_money.py for money tests.
Files to touch: backend/routes/model_gateway.py: header param on generate; backend/orchestrators/routes/model_gateway.py: CALLER branch in generate, _admit, _send, _bill; backend/provider/generative_models/client.py: credential on the plan, caller key in send, refusal remap only under VIDBYTE; backend/services/model_gateway/metering.py: admit_generative fee-only option, record_generative basis, settle and summary and _ledger_write owe fee under FEE_ONLY, _session_id fifth part; backend/lib/dtos/model_gateway.py: billing_basis on ModelUsageSessionDto; backend/lib/dataclasses/model_gateway.py: credential field and check; backend/lib/enums/model_gateway.py: two enums; backend/lib/config/model_gateway.py: header name; backend/lib/observability/sentry.py: drop the header by name; backend/lib/app/route_rules.py: unchanged unless the rule table encodes headers; READMEs and file headers in each touched folder.
Data / index decisions: additive billing_basis on model_usage_sessions, read as TOTAL when absent, no backfill; no new index, the unique session-id index serves the new id; ledger metadata gains billing_basis.
Failure modes to handle: provider 401/403/402 under CALLER: relay status and body unchanged, never ModelGatewayUpstreamRefusedError; key leakage: never in the plan, a log line, an error message, a replay document, or a session document, and the Sentry callback drops the header by name with a test proving it; mixed sessions: basis in the id; wallet short: 402 against the fee-only requirement with the 1-cent floor; billing failure after a relayed answer: logged, never raised, as today; empty header value: 422 via Header(min_length=1).
Pre-answered questions:
- If the header arrives on the Jev route, ignore it; that route does not declare it. Do not ask.
- If the caller key is present but the provider is outside _DIALECTS, refuse 422 as today. Do not ask.
- Keep every dialect rule (allowed fields, output cap, no stream, unpriced prefixes) identical under CALLER. Do not ask.
- No daily-spend hold under CALLER; document why in daily_spend.py's header. Do not ask.
- No feature flag: a bug on this path costs fee revenue, not provider money. Do not ask.
Decide yourself: the header name (prefer one Sentry's default header filter already drops; otherwise extend the callback); ledger description wording; whether ModelChargeQuoteDto gains an owed_fee_cents field or settle computes it inline.
Stop and ask only if: fee-only settlement cannot reuse claim_cents without a schema change beyond the one field; or the route-rule table needs a new throttle class.
Acceptance criteria:
- A generate call with the header and a scripted provider answer debits ceil(2% of SDK-priced cost) cents and writes nothing to the daily-spend counter.
- The same call without the header passes every existing test unchanged.
- A scripted provider 401 under CALLER reaches the client as 401 with the provider body; under VIDBYTE it stays a typed 502.
- A Vidbyte-paid call and a relay call on one key, provider, and UTC day settle in two sessions with different bases.
- No log capture, replay document, session document, or error message in the test run contains the caller key.
- A Sentry event built from a request carrying the header does not contain the key.
Verification: python lint/run.py; python -m pytest backend/tests/features/model_gateway -q; python scripts/run_ci.py
````

### B.2 Handoff — SDK (answer to Prompt 1)

````markdown
Goal: TextModelRunner sends every text call through the Vidbyte gateway, relaying the caller's provider key when one is configured and running Vidbyte-paid when not; AUTO without a Vidbyte key fails at construction; an explicit TextModelMode.DIRECT keeps the vendor-direct path for self-hosted use.
Repo / base: cerredz/Vidbyte-SDK; branch off origin/main in a fresh worktree; open the PR against main; first re-vendor the backend contract from the backend PR's merge commit (lint C017-C020 do not catch a stale copy).
Scope: TextModelMode.DIRECT; TextModelConfig.vidbyte_api_key; the key fall-through; the gateway transport's provider-key header; error wording; README and folder docs; tests under tests/features/sdk_managed_text/.
Non-goals: streaming through the gateway (the streaming runner keeps refusing gateway state and now names DIRECT as the way forward); DecisionModelConfig and Jev; vidbyte-cli; the backend harness's switch to DIRECT, which happens when the backend bumps its SDK pin.
Approach: TextModelConfig gains vidbyte_api_key; find_vidbyte_api_key becomes a resolver returning the pair (provider key or None, Vidbyte key or None) so AUTO means: provider key and Vidbyte key relay; Vidbyte key alone Vidbyte-paid; a vb_live_ value in api_key stays Vidbyte-paid for back-compat; no Vidbyte key ConfigurationError naming VIDBYTE_API_KEY; mode DIRECT resolves the provider key as today and never reads a Vidbyte key. VidbyteGatewayTransport takes provider_api_key and adds the header; adapters keep seeing VIDBYTE_MANAGED_KEY_PLACEHOLDER in gateway state. Rejected: putting the provider key in the envelope, because the backend hashes the envelope for replays.
Patterns to follow: vidbyte/lib/http/vidbyte_gateway.py for header construction and credential-safe errors; vidbyte/lib/dataclasses/model_configs.py is_vidbyte_managed and resolved_vidbyte_api_key for state resolution; vidbyte/lib/registries/models.py find_vidbyte_api_key for the fall-through; vidbyte/lib/enums/text_model.py for the enum; tests/features/sdk_managed_text/test_managed_text_selection.py for selection tests.
Files to touch: vidbyte/lib/enums/text_model.py: DIRECT; vidbyte/lib/dataclasses/model_configs.py: vidbyte_api_key, resolution, validate, resolved_api_key; vidbyte/lib/registries/models.py: resolver; vidbyte/lib/http/vidbyte_gateway.py: header, 402 wording without "set your own provider key"; vidbyte/lib/runners/text.py: pass the provider key to the transport; vidbyte/lib/runners/streaming_text.py: refusal names DIRECT; vidbyte/lib/constants/jev.py: header name constant matching the vendored contract; contracts/: re-vendored; README.md and folder READMEs; tests.
Data / index decisions: none
Failure modes to handle: the provider key appears only in the gateway transport's header, never in an error, a log, or the adapter's headers; a VIDBYTE_API_KEY that does not match VIDBYTE_API_KEY_PATTERN fails at construction as today; a relayed provider 401 is worded as the provider rejecting the caller's key through the gateway; agents-layer fallback to another provider (PR #884 rule) relays when that provider's key is configured and falls back to Vidbyte-paid when it is not.
Pre-answered questions:
- If both api_key holds a vb_live_ key and vidbyte_api_key is set, prefer vidbyte_api_key and treat api_key as absent. Do not ask.
- If mode is VIDBYTE_MANAGED and a provider key is also configured, ignore the provider key; explicit managed stays Vidbyte-paid. Do not ask.
- Keep the 630 s timeout floor and the 32,768 default output cap for relay state. Do not ask.
Decide yourself: the resolver's return type name and placement in vidbyte/lib/dataclasses/; exact error strings; whether the README's quickstart shows relay or Vidbyte-paid first.
Stop and ask only if: the re-vendored contract disagrees with the backend PR on the header name; or the agents layer needs more than the fallback rule above.
Acceptance criteria:
- AUTO with OPENAI_API_KEY and VIDBYTE_API_KEY sends one POST to the generate endpoint carrying the bearer Vidbyte key and the provider-key header, and the adapter's own headers are absent.
- AUTO with only VIDBYTE_API_KEY sends no provider-key header.
- AUTO with only OPENAI_API_KEY raises ConfigurationError naming VIDBYTE_API_KEY before any request.
- mode=DIRECT with OPENAI_API_KEY posts to the vendor endpoint and never reads VIDBYTE_API_KEY.
- The streaming runner in gateway state raises at construction with a message naming DIRECT.
- No captured error message or log line in the suite contains a provider key.
Verification: python scripts/run_ci.py
````

### B.3 Latest Re-entry `Decided:` ledger (verbatim, from the answer to Prompt 4)

````
Decided: relay the caller's provider key via a request header through the existing generate gateway; per-call credential label and per-session billing basis as two new enums; fee-only admission and settlement; no daily hold on relay; AUTO requires a Vidbyte key with explicit DIRECT as the unbilled path; backend PR, then SDK PR, then backend pin bump and CLI switch.
Open: relay streaming; Vidbyte-paid tier rate; stored keys later.
Needs you: 1. AUTO requires a Vidbyte key, DIRECT explicit? — default: yes. 2. Raise the Vidbyte-paid rate? — default: leave at 200 bps. 3. Accept the streaming gap until the follow-up? — default: yes. *Reply "go" to accept all defaults.*
````

The user's next message (Prompt 5) began "great, just to be clear." and did not contest any default; the orchestrator treats all three defaults as accepted (see §C).

### B.4 The step-by-step technical plan the user asked for in Prompt 4 (verbatim)

````markdown
**The invariant we are building.** Every text call the SDK makes goes through `POST /api/v1/models/generate`. The gateway reads token usage from the provider's reply, prices it from the SDK pricebook, and debits 2% of that to the caller's wallet. Who pays the provider is a per-call label: Vidbyte's key (today) or the caller's key (new). The only unbilled path is an explicit `TextModelMode.DIRECT`, which exists because Vidbyte's own backend and CLI consume the SDK.

**Part A: backend (cerredz/Vidbyte), steps in request order**

1. **Constants.** `backend/lib/config/model_gateway.py` gains the provider-key header name, its max length, and its pattern. Why: house style keeps strings out of code, and the SDK mirrors the exact header name.

2. **Enums.** `backend/lib/enums/model_gateway.py` gains `ModelGatewayCredentialSource` (VIDBYTE, CALLER) and `ModelUsageBillingBasis` (TOTAL, FEE_ONLY). Why: two closed sets that every later branch reads; AGENTS.md §4 forbids plain strings for these.

3. **Route reads the key from a header.** `backend/routes/model_gateway.py` `generate()` gains an optional `Header` parameter, same `Annotated` shape as `Idempotency-Key`, and passes it to the orchestrator as its own argument. Why: `GenerativeModelRequestDto` is `extra="forbid"` and `ModelGatewayReplays._request_hash` canonicalizes `wire_body()`; a header keeps the secret out of the DTO, the replay hash, and every persisted document without touching any of them.

4. **The plan carries the label, never the key.** `backend/lib/dataclasses/model_gateway.py` `GenerativeCallPlan` gains `credential: ModelGatewayCredentialSource` with its `__post_init__` check. Why: the relay, the quote, and the meter read one validated label; the file's own rule that no credential enters the plan still holds.

5. **Provider client plans and sends under either key.** `backend/provider/generative_models/client.py`: `plan()` sets the label from whether a caller key arrived and skips the `_key(provider)` precheck under CALLER; `send(plan, caller_key)` builds the dialect auth header from the caller key under CALLER; `_relay()` applies the `_VIDBYTE_REFUSALS` remap only under VIDBYTE. Why: today a provider 401 becomes a typed 502 "Vidbyte's credential failed"; under CALLER the 401 is the customer's and must pass through with the provider's own body so the SDK's direct-mode handling applies. Every dialect rule (allowed fields, output cap, no stream, unpriced prefixes) stays identical, because the fee is still computed from the pricebook.

6. **Admission checks fee-only worst case.** `backend/services/model_gateway/metering.py` `admit_generative()` takes the basis; under FEE_ONLY the requirement is `ceil(quote.fee_nanousd)` cents, floor 1 cent. `UsageAuthorizer.model_worst_case_nanousd` is unchanged. Why: the wallet never pays provider cost on a relay call, so demanding a $5 balance for a $0.10 fee would refuse paying customers.

7. **No daily-spend hold under CALLER.** `GenerativeModelGatewayOrchestrator._admit` returns `ModelGatewaySpendHold | None`; `_send` and `_bill` skip release and settle when it is None. `daily_spend.py` itself is untouched. Why: the cap bounds Vidbyte's own provider exposure from a leaked key; on a relay call that exposure is zero.

8. **Sessions get a billing basis.** `backend/lib/dtos/model_gateway.py` `ModelUsageSessionDto.billing_basis` defaulting to TOTAL; `metering.record_generative()` seeds it and `_session_id()` adds `basis.value` as a fifth part; `database/queries/model_usage_sessions.py` puts it in `$setOnInsert` and the projection. Why: `accrue` fixes identity and rate by the first call of the day; without the fifth id part a Vidbyte-paid call at 09:00 would seed a TOTAL session that a relay call at 10:00 accrues into, charging the customer provider cost twice. Existing documents read as TOTAL, so no migration; the unique session-id index already serves the new id.

9. **Settlement owes the fee only.** `metering.settle()`, `summary()`, and `_ledger_write()` compute owed cents from `quote.fee_nanousd` under FEE_ONLY instead of `quote.owed_cents`. Claim-then-debit through `claim_cents` and `ApiBillingCoordinator.record_usage` is unchanged. Why: the crash-safe cent accounting is already correct; only the amount changes.

10. **Ledger labels the revenue type.** `_ledger_write` gives relay sessions their own description and puts `billing_basis` in metadata. Why: resale revenue and fee revenue must be separable for accounting and for the Stripe-fee problem.

11. **Orchestrator threads the label.** `backend/orchestrators/routes/model_gateway.py` `generate(user_id, api_key_id, body, idempotency_key, caller_key)` passes the label to `_admit`, `_send`, `_bill`. Replays are untouched: a retry with the same body replays the paid answer regardless of header. Why: one main function plus helpers, AGENTS.md §1 and §2.

12. **Scrub the header from error telemetry.** `backend/lib/observability/sentry.py` `_scrubber` only replaces Vidbyte's own secret values from `settings.secret_values()`; a customer key in request headers would ship on an error event. Drop the header by name in `before_send`, or pick a name Sentry's default header filter already removes, and prove it with a test. Why: this is the one confirmed leak path.

13. **Contract regeneration.** No new RouteRule, since the route already exists, but run `scripts/generate-platform-contract.py` so `lint/contracts/vidbyte-platform-contract.json` is current for the SDK to re-vendor.

14. **Tests in `backend/tests/features/model_gateway/`.** Extend `generative_gateway_fakes.py` with a provider fake that records which auth header it saw. Add cases to `test_generative_gateway_money.py` (fee-only admission, no hold, two sessions on one key, provider, and day), `test_generative_gateway_refusals.py` (401 passes through under CALLER, stays 502 under VIDBYTE), `test_generative_gateway_contract.py` (header validation, plan field), `test_generative_gateway_replays.py` (header excluded from the hash), `test_generative_gateway_acceptance.py` (end to end), plus the Sentry scrub test. Assert no fixture capture contains the key. Update `FEATURE.md`.

15. **Docs and gate.** File headers (PURPOSE, EDGE CASES, WHAT NOT TO DO) and folder READMEs in every touched folder. Then `python lint/run.py`, `python -m pytest backend/tests/features/model_gateway -q`, `python scripts/run_ci.py`. Merge and deploy. Old SDK versions send no header and behave exactly as before.

**Part B: SDK (cerredz/Vidbyte-SDK), after the backend is live**

1. **Re-vendor the contract** from the backend merge commit into `lint/contracts/vidbyte-platform-contract.json`. Why: C017 proves every SDK request names a route the backend serves. The contract does not carry header names, so the header is mirrored by hand in step 2 and must match step A1 exactly.

2. **Constant.** `vidbyte/lib/constants/jev.py` gains the provider-key header name beside the route and key-format constants.

3. **Enum.** `vidbyte/lib/enums/text_model.py` gains `TextModelMode.DIRECT`. Why: the explicit unbilled path for the backend harness, the CLI's local use, and forks. Keeping it explicit is what makes the fee default-on instead of opt-in.

4. **Config resolves both keys.** `vidbyte/lib/dataclasses/model_configs.py` `TextModelConfig` gains `vidbyte_api_key`; a new frozen `TextCredentials` record in the same domain module holds the resolved mode, provider key or None, and Vidbyte key or None. Resolution: DIRECT resolves the provider key as today and reads no Vidbyte key; VIDBYTE_MANAGED resolves only the Vidbyte key and ignores any provider key; AUTO requires a Vidbyte key (explicit `vidbyte_api_key`, a `vb_live_` value in `api_key` for back-compat, or `VIDBYTE_API_KEY`) and takes a provider key if one is configured (non-Vidbyte `api_key`, or the provider's env var). `validate()` raises `ConfigurationError` naming `VIDBYTE_API_KEY` for AUTO without one. `resolved_api_key()` keeps returning `VIDBYTE_MANAGED_KEY_PLACEHOLDER` in gateway state. Why: adapters build vendor auth from that value, so the real provider key never sits in adapter headers even though the transport discards them.

5. **Registry.** `vidbyte/lib/registries/models.py`: replace `find_vidbyte_api_key` with the pair resolver that step 4 calls; `resolve_vidbyte_api_key` and `vidbyte_key_follows_provider` stay. Why: one place owns the fall-through, as today.

6. **Transport adds the header.** `vidbyte/lib/http/vidbyte_gateway.py` `VidbyteGatewayTransport.__init__` takes `provider_api_key: str | None` and adds the header when present. Reword the 402 remedy, which today ends "or set your own provider key", and add a relayed-401 hint that the provider rejected the configured key. Why: this class is already the only place the Vidbyte key becomes a header; the provider key joins it there and nowhere else, and its errors already never echo bodies.

7. **Runners.** `vidbyte/lib/runners/text.py` pins both keys at construction and passes the provider key to each per-call transport. `vidbyte/lib/runners/streaming_text.py` keeps refusing gateway state and names DIRECT as the way forward. Why: the gateway cannot bill a stream yet.

8. **Agents layer.** `vidbyte/agents/fork.py` and `vidbyte/agents/settings/fallback.py` (PR #884's rule): when a fallback switches provider, carry the Vidbyte key and look up that provider's own key; relay if found, Vidbyte-paid if not. Why: fallback chains degrade to Vidbyte-paid instead of failing on a missing vendor key.

9. **Tests in `tests/features/sdk_managed_text/`.** Selection matrix in `test_managed_text_selection.py` (both keys, Vidbyte only, provider only, DIRECT, explicit managed plus provider key); `test_managed_text_wire_contract.py` asserts the header is present or absent and adapter headers are gone; `test_managed_text_failures.py` covers the relayed 401 wording and that no message contains a key; acceptance updated. `FEATURE.md` and the folder README updated.

10. **Docs and gate.** Root README quickstart shows the two-key setup, folder READMEs and file headers updated, `llms.txt` if it lists modes. `python scripts/run_ci.py`. Bump version, publish.

**Part C: rollout and in-house consumers**

1. **Backend pin bump.** `backend/requirements.txt` moves to the new SDK; `backend/services/harnesses/research/agents/factory.py` sets `mode=TextModelMode.DIRECT` so Vidbyte does not pay itself. Verify the harness tests still pass.

2. **CLI.** vidbyte-cli already holds a Vidbyte key in the keyring; its SDK configs set `vidbyte_api_key` from it and keep the user's provider key, so CLI model calls relay by default. Same change in cli-internal and the public mirror.

3. **Follow-ups, each its own PR.** Relay streaming: the gateway pipes SSE and bills from the terminal usage chunk, feasible now because Vidbyte has no exposure on relay calls. Stored keys: resolution order header, then stored, then Vidbyte's own, once an encryption primitive exists. The Vidbyte-paid tier's rate.

**What deliberately does not change.** The replay store, the Jev route and its 10% rate, the wallet and ledger code, the dialect table, the daily-spend repository, and every existing test.
````

## C. Structured conversation notes

This request spans TWO repositories and runs as TWO pipelines in parallel, each in its own worktree:

| Run | Repo | Worktree | Branch | Slug |
|---|---|---|---|---|
| backend | C:/Users/422mi/vidbyte-repos/vidbyte (cerredz/Vidbyte) | C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-byok-fee-relay | feat/byok-fee-relay | byok-fee-relay |
| SDK | C:/Users/422mi/vidbyte-repos/vidbyte-sdk (cerredz/Vidbyte-SDK) | C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-byok-api-keys | feat/byok-api-keys | byok-api-keys |

Each run's spec covers only its own repo. They meet at the wire contract below, which the orchestrator fixed so both runs can proceed at once. Neither run may change the contract alone; a needed change is reported BLOCKED to the orchestrator.

### Cross-repo wire contract (settled; both runs build to it)

- Route unchanged: `POST https://vidbyte-backend.onrender.com/api/v1/models/generate`, envelope `{provider, model, body}` unchanged (`GenerativeModelRequestDto`, `extra="forbid"`), `Authorization: Bearer vb_live_…` unchanged, optional `Idempotency-Key` unchanged.
- **New optional request header `X-Vidbyte-Provider-Key`** carrying the caller's own provider API key for the envelope's provider. Chosen because `X-Api-Key` is already a Vidbyte-key auth header in the backend (`backend/lib/enums/api_keys.py:42`, `backend/lib/discovery.py:176`), and Sentry's default header filter (sentry-sdk 2.32.0 `_wsgi_common.SENSITIVE_ENV_KEYS`: REMOTE_ADDR, X-Forwarded-For, Set-Cookie, Cookie, Authorization, X-Api-Key, X-Real-Ip) does NOT drop a custom name, so the backend must scrub `X-Vidbyte-Provider-Key` explicitly.
- Header present → **relay**: the backend calls the provider with the caller's key, Vidbyte pays nothing to the provider, and the wallet is billed only Vidbyte's fee, 200 basis points of the SDK-priced provider cost. Header absent → **Vidbyte-paid**: exactly today's behavior (Vidbyte's key, cost + 200 bps, daily-spend cap).
- Under relay, a provider 401/403/402 is relayed with the provider's own status and JSON body (it is the caller's key or account), not remapped to the typed 502 `ModelGatewayUpstreamRefusedError` used for Vidbyte's own key.
- Gateway-owned statuses keep their meaning in both modes: 401 bad Vidbyte key; 402 wallet below the admission requirement (under relay: the fee-only worst case, 1-cent floor); 403 key lacks `models:invoke`; 409 same Idempotency-Key still in flight; 413 body over 2,000,000 bytes; 422 unbillable/unsupported request (dialect rules identical in both modes); 429 API-key request quota (and, Vidbyte-paid only, the daily spend cap); 502 upstream unreachable / non-JSON.
- An empty header value is a 422 (route validation), never silently Vidbyte-paid.
- The six gateway providers are unchanged: openai, anthropic, gemini, xai, deepseek, kimi (SDK `VIDBYTE_MANAGED_TEXT_PROVIDERS`, backend `_DIALECTS`).

### Key decisions
- Support BYOK AND the markup by relaying the caller's own provider key through the existing generate gateway and billing only the fee — the gateway still reads usage from the provider's own reply (`ModelUsageMeter.price`, `only-gateway-observed-usage-is-billed`), so the fee basis is provider-reported, while the money flows customer → provider directly. Reason (Prompt 1 answer): Vidbyte-paid resale at 200 bps loses money after card fees — on $1,000 of provider spend the customer tops up $1,020, Stripe takes ≈$29.88, Vidbyte nets ≈ −$9.88; under relay the top-up is $20, fee ≈$0.88, net ≈$19.12 — and Vidbyte never pre-buys provider credit or shares one provider org's rate limits across customers.
- Vidbyte-paid mode stays for callers who have no provider key; its rate stays 200 bps (user accepted the default "leave at 200 bps").
- Markup is taken per call as usage arrives, through the existing session accrual + whole-cent claim-then-debit settlement; the final part-cent settles when the session closes (idle reaper after `MODEL_USAGE_SESSION_IDLE_TTL_SECONDS` = 3,600 s). Prompt 5: "either throughout the run or after the run we take the token markup however you see fit" — the existing mechanism satisfies "throughout"; no new billing loop.
- In the SDK, AUTO mode requires a Vidbyte key; vendor-direct survives only as an explicit `TextModelMode.DIRECT` (needed because Vidbyte's own backend research harness and vidbyte-cli consume the SDK and must not bill themselves). The fee is therefore default-on, not unavoidable — the most an MIT package can enforce. User accepted the default "AUTO requires a Vidbyte key, DIRECT explicit? — default: yes".
- User accepted "the streaming gap until the follow-up": the SDK streaming runner keeps refusing gateway state (the gateway cannot bill a stream), and its error names DIRECT as the way forward.
- Relay calls take no daily-spend hold: the cap bounds Vidbyte's own provider exposure from a leaked key, which is zero on relay.
- Session billing basis is a fifth session-id part plus an additive `billing_basis` field defaulting to TOTAL, so a Vidbyte-paid call and a relay call on the same key, provider, and UTC day never share a session (sharing would charge provider cost twice).

### Changes the user made after the handoffs (Prompt 5 and Prompt 6 win over §B)
- **Agents take `vidbyte_api_key` and `api_keys`.** Prompt 5: "I want the agents iin our vidbyte-sdk/ param to have both a vidbyte_api_key and an api_keys param in the paramter of the model."
- **`api_key` is folded into `api_keys`, not kept beside it.** Prompt 6: "can you just extend the api_key functionality into the api_keys functionality. I presume we already have some important logic that can be carried over into the api_keys param. Simply renames for the vidbyte-cli should be easy to fix for the agents that we already have". So the public provider-key parameter becomes `api_keys`; today's `api_key` resolution logic (explicit key, then the provider's env var) carries over. The §B.2 handoff's "a vb_live_ value in api_key stays Vidbyte-paid for back-compat" is superseded: the Vidbyte key has its own `vidbyte_api_key` parameter.
- **`api_keys` is a LIST of provider keys in any order, never a dict.** Prompt 6 selected "List only" and added: "we can under the hood deterministically match the api keys to the provider so we dont actually need  the user to define the provider". The developer never says which key belongs to which provider.
- **A lib class matches each key to its provider and checks it against the provider/model in use.** Prompt 5: "under the hood we shoul have a lib class that makes sure that the user is inputting the correct api key that matches the provider/model that they are inputting (can prob be matches with the pricebook, api keys that start with "sk-" can be matches with antrhopic, etc. This you are probably going to have to play with to really make sure this feature works under the hood, dont want developers to have to worry about this."
- **Live test** with the user's real keys, through the backend branch run locally (see Constraints).

### Rejected alternatives
- Provider key in the envelope body — it would enter `GenerativeModelRequestDto` (`extra="forbid"`) and the replay hash (`ModelGatewayReplays._request_hash` canonicalizes `wire_body()`).
- Storing customer provider keys in the Vidbyte dashboard (OpenRouter-style) — Vidbyte would become a custodian of customer secrets at rest and the backend has no encryption primitive (no Fernet/KMS/NaCl outside vendored packages). Deferred; it would layer on later as header → stored → Vidbyte's own.
- Client-side usage receipts (SDK calls the vendor directly and reports usage) — unenforceable.
- Stripe metered postpaid billing of the fee — the wallet already settles cents idempotently; nothing metered exists in the repo.
- Vidbyte-paid only (today) — negative margin at 200 bps after card fees; provider-tier ceilings shared by all customers.
- A dict form of `api_keys` — the user chose list only.
- Keeping `api_key` beside `api_keys` — the user chose to fold it into `api_keys`.

### Constraints and assumptions
- The Jev route (`/api/v1/models/typesafe/*`), its 1,000 bps rate, the replay store, the wallet/ledger repositories, the dialect table's rules, and the daily-spend repository do not change.
- No feature flag (a bug on the relay path costs fee revenue, not provider money).
- Old SDK versions send no `X-Vidbyte-Provider-Key` and must behave exactly as before against the new backend.
- The SDK provider key must never appear in an error message, log line, trace, the adapter's own headers, or anywhere but the gateway transport's one header. The backend must never put it in the plan, a log line, an error, a replay document, a session document, a ledger entry, or a Sentry event.
- **Live test (both runs feed it; it runs after both reach green):** the backend branch is started locally (uvicorn) from its worktree using the environment of the main checkout's `C:/Users/422mi/vidbyte-repos/vidbyte/backend/.env`, whose `MONGODB_URI` points at an Atlas cluster, database `Vidbyte` — treat it as PRODUCTION. The SDK branch's agents are pointed at `http://127.0.0.1:<port>/api/v1/models/generate` by a scratch script (the SDK hard-codes the production gateway URL and refuses custom endpoints in gateway mode, so the script patches the constant at runtime; nothing in the repo changes for this). Keys: the user's Windows user-scope environment variables `GROK_API_KEY` (an xAI key, `xai-` prefix) and `VIDBYTE_API_KEY` (`vb_live_` key). They are NOT in process environments by default; read with PowerShell `[Environment]::GetEnvironmentVariable('<NAME>','User')`. Never print, log, commit, or paste either value anywhere. Spend: "make sure to put the max spend/tokens only at a few cents" — the cheapest grok model the backend's pinned pricebook and `require_catalogued` accept, small `max_output_tokens` (≤ 64), a handful of calls; total provider cost well under $0.05 and Vidbyte fee well under 1 cent of usage.
- Live-test hazard the orchestrator found: the DEPLOYED backend's idle reaper (old code) closes open `model_usage_sessions` after 3,600 s idle and settles them with the old formula (cost + fee), and it does not know `billing_basis`. A FEE_ONLY session the local test leaves open in production would later be over-billed by the old reaper. The live test must close and settle every session it creates with the NEW code before it finishes. (The reaper only scans OPEN sessions.)
- vidbyte-sdk PRs get no automatic checks: CI runs only via `gh workflow run CI --ref <branch>` and `gh workflow run "Static policy" --ref <branch>`; required checks are `Source / Python 3.11`, `Source / Python 3.12`, `Package`.
- The pipeline does not merge or mark either PR ready; the user does.

### Clarifications and answers
- Q: shape of `api_keys`? — A: "List only" + "we can under the hood deterministically match the api keys to the provider so we dont actually need  the user to define the provider, make sure to take this into account during impleeplementation".
- Q: how to run the live Grok test? — A: "Local backend (Recommended)".
- Q: what happens to `api_key`? — A: "can you just extend the api_key functionality into the api_keys functionality. ... Simply renames for the vidbyte-cli should be easy to fix for the agents that we already have".
- Q (from the /talk ledger): AUTO requires a Vidbyte key, DIRECT explicit? — A: accepted default, yes. Raise the Vidbyte-paid rate? — A: accepted default, no (200 bps). Accept the streaming gap? — A: accepted default, yes.

### Terminology
- **Relay** (also "BYOK relay", "caller-paid"): a gateway call carrying `X-Vidbyte-Provider-Key`; the provider bills the caller directly; Vidbyte bills only its fee.
- **Vidbyte-paid** (also "managed", today's mode): a gateway call without the header; Vidbyte's own provider key; the wallet pays cost + fee.
- **Fee**: 200 basis points (2%) of the SDK-priced provider cost of a call (`MODEL_GATEWAY_GENERATIVE_MARKUP_BASIS_POINTS`); money is integer nano-USD until settlement in whole cents.
- **DIRECT**: new SDK `TextModelMode` member; the SDK calls the vendor directly with the caller's key; no Vidbyte key, no gateway, no fee.
- **AUTO**: the SDK's default mode; after this change it requires a Vidbyte key and goes through the gateway, relaying when it holds a provider key for the call's provider and Vidbyte-paid otherwise.
- **Key matching / classification**: deterministically deciding which provider a raw API key string belongs to from its format, so a list of keys can be assigned to providers without the developer saying which is which.

### Implementation hints
- Backend files (read at /talk time): `backend/routes/model_gateway.py` (`generate()`), `backend/orchestrators/routes/model_gateway.py` (`GenerativeModelGatewayOrchestrator.generate/_admit/_send/_bill`), `backend/provider/generative_models/client.py` (`GenerativeModelClient.plan/send/_key/_relay`, `_VIDBYTE_REFUSALS`, `_DIALECTS`), `backend/services/model_gateway/metering.py` (`admit_generative`, `record_generative`, `settle`, `summary`, `_ledger_write`, `_session_id`), `backend/services/model_gateway/daily_spend.py`, `backend/services/model_gateway/replays.py`, `backend/lib/{config,enums,dtos,dataclasses}/model_gateway.py`, `backend/lib/usage/model_accumulator.py` (`ModelUsageAccumulator.quote`), `backend/database/queries/model_usage_sessions.py` (`accrue` upsert: `$setOnInsert` fixes identity and rate), `backend/lib/observability/sentry.py` (`_scrubber` replaces only Vidbyte's own secret values), `backend/lib/api/dependencies.py` (`get_generative_model_gateway_orchestrator`), `backend/lib/app/route_rules.py` (`models.generate` rule: API_KEY access, `models:invoke`, `API_KEY_STANDARD` throttle), tests in `backend/tests/features/model_gateway/` (fakes in `generative_gateway_fakes.py`, money tests in `test_generative_gateway_money.py`, `FEATURE.md`).
- SDK files: `vidbyte/lib/http/vidbyte_gateway.py` (`VidbyteGatewayTransport`, `_GatewayAnswer.gateway_reason` 402 text ends "or set your own provider key"), `vidbyte/lib/enums/text_model.py` (`TextModelMode` AUTO, VIDBYTE_MANAGED), `vidbyte/lib/dataclasses/model_configs.py` (`TextModelConfig.api_key`, `mode`, `is_vidbyte_managed`, `resolved_vidbyte_api_key`, `resolved_api_key` → `VIDBYTE_MANAGED_KEY_PLACEHOLDER`, `_require_managed_shape`), `vidbyte/lib/registries/models.py` (`resolve_api_key`, `find_vidbyte_api_key`, `vidbyte_key_follows_provider`, `resolve_vidbyte_api_key`, provider env-var table e.g. XAI → `XAI_API_KEY`, KIMI → `MOONSHOT_API_KEY`), `vidbyte/lib/constants/jev.py` (`VIDBYTE_GENERATIVE_GATEWAY_ENDPOINT`, `VIDBYTE_MANAGED_TEXT_PROVIDERS`, `VIDBYTE_API_KEY_PREFIX` = `vb_live_`, `VIDBYTE_API_KEY_PATTERN`), `vidbyte/lib/runners/text.py`, `vidbyte/lib/runners/streaming_text.py` (`_refuse_managed_streaming`), `vidbyte/agents/base.py` (`BaseAgent.__init__(…, api_key, provider, model_name, …, fallback)` → `AgentRunnerConfig(api_key=…)`; `restore(…, api_key=…)`), `vidbyte/agents/settings/fallback.py` (`_inherited_api_key`), `vidbyte/agents/fork.py`, `vidbyte/agents/fallback.py`, tests in `tests/features/sdk_managed_text/`.
- SDK `ModelProvider` members: openai, anthropic, gemini, xai, deepseek, glm, minimax, kimi, meta, mistral, openrouter, elevenlabs, playai, typesafe. Only six are gateway-served.
- Key formats to verify (orchestrator's starting knowledge, UNVERIFIED — the SDK run must confirm against first-party docs and real key shapes before relying on any): Anthropic `sk-ant-…`; OpenAI `sk-proj-…`, `sk-svcacct-…`, `sk-admin-…`, legacy `sk-` + 48 chars, OpenAI keys carry the substring `T3BlbkFJ`; xAI `xai-…`; Gemini (Google API key) `AIza` + 35 chars; DeepSeek `sk-` + 32 lowercase hex; Kimi/Moonshot `sk-` + ~48 alphanumerics; OpenRouter `sk-or-v1-` + 64 hex; Vidbyte `vb_live_` + ≥ 32 chars. The `sk-` family is where determinism is hard; Prompt 5's example ("sk-" → anthropic) is imprecise (Anthropic is `sk-ant-`).
- Repo memory: backend generative gateway merged as cerredz/Vidbyte#672; SDK managed mode merged as cerredz/Vidbyte-SDK#759 (2026-10-12).

### Open questions (resolve from the code, or carry as Q-n with the stated default)
- What does the SDK do when a key in `api_keys` cannot be classified, or matches more than one provider? Default: raise `ConfigurationError` at construction naming the key by provider-guess and a redacted fingerprint (never the key), unless the configured provider set makes the assignment unique.
- What happens when `api_keys` holds two keys for the same provider? Default: raise at construction.
- What happens when a key's format contradicts the provider/model the agent uses (e.g. an `xai-` key and provider `openai`, and no openai key in the list)? Default: AUTO goes Vidbyte-paid for that provider (no provider key for it) — or raise? The user's words ("makes sure that the user is inputting the correct api key that matches the provider/model") favor an explicit error when the list holds keys but none matches the model's provider. Spec author decides, with reasoning.
- AUTO with a provider the gateway does not serve (glm, minimax, meta, mistral, openrouter): default raise a `ConfigurationError` naming DIRECT, because a silent direct path would be an unbilled route to any model (OpenRouter reaches almost every model).
- Should a missing `provider` be inferred from `model_name` via the pricebook? Default: no (not asked for; Prompt 6's "we dont actually need the user to define the provider" refers to mapping keys to providers).
- Does `api_keys` accept a bare string? Default: decide from the codebase's existing coercion conventions; never silently iterate a string's characters.
- Does the rename reach `TextModelConfig` (lib layer) as well as the agents? Default: yes where `api_key` is a public provider-key parameter, since Prompt 5 says "in the paramter of the model"; the Jev `DecisionModelConfig.api_key` (TypeSafe/Vidbyte key for decisions) is out of scope.

## D. Weighted words

- "i want to still have our token markup but without making it so that we have to buy all of the credits" — Prompt 1
- "support BYOK AND the vidbyte markup on all tokens that the user uses through the sdk" — Prompt 4
- "go over everything in both repos" — Prompt 4
- "a lib class that makes sure that the user is inputting the correct api key that matches the provider/model that they are inputting" — Prompt 5
- "This you are probably going to have to play with to really make sure this feature works under the hood, dont want developers to have to worry about this." — Prompt 5
- "make sure that either throughout the run or after the run we take the token markup" — Prompt 5
- "make sure that whatever we talked about in this converation that relates to this request is implemented" — Prompt 5
- "make sure to put the max spend/tokens only at a few cents" — Prompt 5
- "to make sure that the api key does not run out of credits" — Prompt 5
- "Do not stop until this feature is perfect" — Prompt 5
- "we can under the hood deterministically match the api keys to the provider so we dont actually need  the user to define the provider" — Prompt 6
- "Simply renames for the vidbyte-cli should be easy to fix" — Prompt 6
