---
slug: managed-generative-models
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-10 18:05
flags: none
---

# Request: Vidbyte-managed mode for generative model calls (lib layer)

> This file belongs to the **SDK pipeline** (part 2 of Prompt 5). The sibling backend pipeline's copy lives at `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-generative-model-gateway/docs/spec/generative-model-gateway/request.md` and differs only in this header. The backend spec at `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-generative-model-gateway/docs/spec/generative-model-gateway/spec.md` defines the wire contract this SDK change must speak.

## A. Every user prompt in this conversation, verbatim and in order

**Prompt 1** (opening message):
```
for the vidbyte-sdk/, can you suggest how we might take a 2% markup on all tokens travelled through our sdk? want to make sure that there are no workarounds
```

**Prompt 2** (after the assistant's first answer, reproduced in §E.1):
```
I guess what I am asking is how can we provide the same markup/gateway that we are providing to jev model calls to all of the generative model calls of the sdk?
```

**Prompt 3** (after the assistant's second answer, §E.2):
```
can youo explain in like step by step fashion
```

**Prompt 4** (after the assistant's step-by-step answer, §E.3):
```
so all we have to do is to add 1 endpoint to the vidbyte backend  (wrong url), and then forward the sdk agent request through to our endpoint, and our enndpoint will call the actual model and we simply read the reponse from the model provider when decrementing using?
```

**Prompt 5** (the invoking prompt, after the assistant's confirmation answer, §E.4):
```
great so the way I want to handle this is 1) I want 1 route in the vidbyte/ repo, and then handle the underlying api requests in a orchestrator/server layer for the different routes to the different providers. and then 2) the sdk changes we can handle in the lib layer of the repo. lets achieve this 2% markup on generative tokens
```

## B. Handoff block and decision ledger (verbatim, if present)

none

## C. Structured conversation notes

### This request spans two repositories, run as two linked pipelines
- **Backend pipeline:** repo `C:/Users/422mi/vidbyte-repos/vidbyte` (FastAPI backend under `backend/`), slug `generative-model-gateway`, worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-generative-model-gateway`, branch `feat/generative-model-gateway`. Builds part 1) of Prompt 5.
- **SDK pipeline:** repo `C:/Users/422mi/vidbyte-repos/vidbyte-sdk` (Python package `vidbyte`), slug `managed-generative-models`, worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-managed-generative-models`, branch `feat/managed-generative-models`. Builds part 2) of Prompt 5.
- The two PRs meet at one HTTP wire contract (route path, request shape, headers, response, error statuses). The backend spec defines that contract; the SDK spec consumes it verbatim. Each PR must be independently mergeable and green in its own repo.

### Key decisions
- **Billing is enforced only on the server.** A Vidbyte-controlled gateway holds the provider keys, forwards the call upstream, and bills from the usage block in the provider's own response. — The SDK is MIT-licensed, published on PyPI, bring-your-own-key (BYOK), and forkable, so any client-side metering can be deleted; the SDK's existing managed-gateway design docs already list "prevent a modified SDK from bypassing Vidbyte" as a non-goal. Only tokens that physically pass through the gateway under Vidbyte-held provider keys can be billed with "no workarounds".
- **Mechanism confirmed by the user (Prompt 4 → "great" in Prompt 5):** the SDK sends the generative request to the Vidbyte backend instead of the vendor host; the backend calls the real provider with Vidbyte's own key; the backend reads the provider's response usage to price the call and decrement the user's wallet. This is exactly how the existing Jev (TypeSafe) managed gateway already works; the new work generalizes it to generative providers.
- **Markup: 2% = 200 basis points on generative (text-generation) tokens.** Jev/TypeSafe decision calls keep their existing `MODEL_GATEWAY_MARKUP_BASIS_POINTS = 1_000` (10%); the user did not ask to change Jev's rate.
- **Backend shape (Prompt 5, part 1): exactly ONE new route** in the vidbyte backend. The different upstream provider APIs ("the different routes to the different providers") are handled below the route, in the orchestrator / service layer. This user decision overrides the assistant's earlier proposal of four byte-compatible routes, one per wire dialect (§E.4).
- **SDK shape (Prompt 5, part 2): the SDK changes live in the lib layer** of vidbyte-sdk (`vidbyte/lib/`, the bottom layer of the package).
- **Price only what the gateway observed.** The meter prices from the upstream provider response that the gateway itself received, never from usage the client reports. The existing backend meter (`backend/services/model_gateway/metering.py`) already states this rule in its header; it must stay the only source.
- **First-version scope, as proposed in §E.4 and accepted by the user with "great":**
  - Backend: provider dispatch under the single route; one relay path that swaps the caller's `vb_live_` key for Vidbyte's provider key; a usage extractor per wire dialect (Gemini reports usage under `usageMetadata`, the others under `usage`); the 200 bps generative rate selected by provider (Jev keeps 1,000); an admission check that rejects a call whose worst-case cost exceeds the wallet balance (worst case = the request's output-token cap × the model's output rate + a rough input estimate from body size); idempotent replay on retries reusing the existing replay mechanism (the SDK sends the `Idempotency-Key` header); a daily spend cap per API key ("a number check"); provider secrets in the credential loader.
  - SDK: a Vidbyte-managed mode on the text model config that pins the gateway host and requires a live Vidbyte key (mirroring the existing `DecisionModelConfig` managed mode); a key fall-through so that setting only `VIDBYTE_API_KEY` switches a user to managed mode; one shared header builder the provider adapters use; managed streaming rejected with a clear error.
- **Explicitly deferred to a second pass (not in these PRs):** run ids on generative calls and close-run summaries; per-call fee accrual for runs that mix Jev (10%) and generative (2%) calls; full wallet reservations for concurrent fan-out; a streaming relay; a nightly reconciliation job comparing provider spend to wallet debits; showing marked-up cost in the SDK's local usage tracker.
- **Excluded from managed billing in this version:** the Codex app-server path (never touches SDK HTTP), OpenRouter (empty pricebook, reports its own cost), non-text modalities, and streaming. BYOK traffic stays unbilled by design.

### Rejected alternatives
- **Client-side token counting or enforcement in the SDK** — cannot be enforced in an open-source BYOK SDK; trivially removed by a fork, and the Codex path never touches SDK HTTP.
- **Four byte-compatible routes, one per wire dialect (OpenAI `/responses`, Anthropic `/messages`, Gemini `/models/{model}:generateContent`, chat-completions `/chat/completions`)** — the assistant's proposal in §E.4, replaced by the user's one-route design in Prompt 5. Accepted consequence: only clients that speak the gateway's own request shape (Vidbyte's SDK) can use the route; a third-party vendor SDK pointed at the gateway as its base URL will not work.
- **Changing the session schema to accrue a fee per call** — deferred; only needed once a generative call and a Jev decision share one run id. In this version generative calls send no run id.
- **Full reservations replacing the 1-cent admission floor** — deferred; the cheap worst-case admission check is in scope instead.

### Constraints and assumptions
- Provider keys live only on the server. `backend/lib/credentials/credentials_loader.py` exposes a provider-generic `require_provider_key(provider)` (around line 413); the existing TypeSafe relay client obtains its key that way and resolves the upstream URL through the SDK's provider registry.
- Vidbyte pays the provider before it knows what to charge, so the admission check, idempotent replay, and the per-key daily cap protect Vidbyte's money. A leaked `vb_live_` key must not become an unbounded provider bill.
- Existing backend repo rules seen in the gateway code: never bill client-reported usage; never echo gateway or upstream bodies in managed error messages (they could reflect a bearer key); never log keys; a metering failure after a paid answer is logged, not raised.
- Money math is integer nano-USD. `BasisPointMarkup.of(base, bps) = base * bps // 10_000` (`backend/lib/usage/markup.py`); `quote(provider_cost_nanousd, markup_basis_points, final)` in `backend/lib/usage/model_accumulator.py` floors cents while a session is open and ceils at close.
- Unpriced models are rejected today (`require_priced` → 422). The SDK pricebook (`PRICING_AS_OF = "2026-07-30"`, 41 entries) has no OpenRouter entries.
- Model usage sessions (`backend/database/queries/model_usage_sessions.py`) `$inc` totals, `$setOnInsert` a fixed `provider` and `markup_basis_points`, and `$set` the model. A generative call must therefore never accrue into a session that was created for TypeSafe at 1,000 bps, and a session spanning several providers would carry the wrong provider label.
- Existing backend gateway limits (`backend/lib/config/model_gateway.py`): request cap 2 MB, response cap 16 MB, upstream timeout 60 s, admission floor 1 cent, session idle TTL 3600 s.
- SDK managed key format: `vb_live_[A-Za-z0-9_-]{32,}`. Managed mode rejects a custom endpoint. Existing Jev managed headers: `Authorization: Bearer <vb_live_ key>`, `X-Vidbyte-Run-Id`, `Idempotency-Key`. `HttpTransport` refuses to retry a POST without an `idempotency_key`.
- Both repositories declare `docs/` opaque in AGENTS.md: agents read only the `docs/` files an orchestrator briefing names.

### Clarifications and answers
- Q (user, Prompt 4): "so all we have to do is to add 1 endpoint to the vidbyte backend (wrong url), and then forward the sdk agent request through to our endpoint, and our endpoint will call the actual model and we simply read the reponse from the model provider when decrementing using?" — A (assistant, §E.4): yes; that is the whole mechanism and it is already how the Jev gateway works. Corrections given: the SDK needs two changes (pick the gateway host instead of the vendor host, and send the Vidbyte bearer key instead of the vendor auth header); the remaining items protect Vidbyte's money rather than make the call work. The user answered "great" and chose one route plus orchestrator/service dispatch (Prompt 5).
- Q (user, Prompt 2): provide "the same markup/gateway that we are providing to jev model calls to all of the generative model calls of the sdk" — A: extend the existing Jev managed gateway to generative providers and add a managed text mode to the SDK mirroring `DecisionModelConfig`.

### Terminology
- **Managed mode / `VIDBYTE_MANAGED`** — the SDK sends a model call to the Vidbyte gateway with a Vidbyte API key instead of to the vendor with the user's own key. Today only Jev decision calls have it (`DecisionModelMode.VIDBYTE_MANAGED`).
- **BYOK** — bring your own key: the SDK calls the vendor directly with the user's provider key. Unchanged and unbilled.
- **`vb_live_` key / `VIDBYTE_API_KEY`** — a Vidbyte platform API key; the backend gatekeeper maps it to a user and checks scope `models:invoke`.
- **Generative call** — a non-streaming text-generation call made through the SDK's `TextModelConfig` and text runners, as opposed to a Jev decision call through `DecisionModelConfig`.
- **Wire dialect** — one of the four request/response formats the SDK's text providers speak: OpenAI Responses, Anthropic Messages, Gemini `generateContent`, and the chat-completions family shared by xAI, DeepSeek, GLM, MiniMax, Kimi, Meta, Mistral, and OpenRouter.
- **"orchestrator/server layer" (Prompt 5)** — read as the backend's orchestrator layer (`backend/orchestrators/`) and service layer (`backend/services/`); "server" is taken to mean "service". Assumption, not confirmed by the user.
- **"lib layer" (Prompt 5)** — `vidbyte/lib/` in vidbyte-sdk.
- **Session** — a model usage session document in Mongo that accrues provider cost and settles whole cents against the wallet.
- **bps** — basis points; 200 bps = 2%.

### Implementation hints (from the conversation's reading of the code; verify before relying)
- Backend, existing Jev gateway: `backend/routes/model_gateway.py` (routes `/typesafe/systemone`, `/typesafe/models`, `/runs/{run_id}/close` under `APIRouter(prefix="/api/v1/models")`); `backend/orchestrators/routes/model_gateway.py` (`ModelGatewayOrchestrator.decide()`: require_priced → replay claim → admit on wallet floor → relay under Vidbyte's upstream key → price from upstream usage via the SDK `UsageTracker` → accrue into the run session → settle whole cents; its header says "Add a managed provider by adding a relay client and one decide-shaped method"); `backend/services/model_gateway/metering.py` (`ModelUsageMeter`, `_PROVIDER = ModelProvider.TYPESAFE` hardcoded, `price()` reads `body["usage"]`, `record()` seeds the session with `MODEL_GATEWAY_MARKUP_BASIS_POINTS`); `backend/services/model_gateway/replays.py`; `backend/provider/typesafe/client.py` (`TypeSafeGatewayClient`, 401/403 upstream → `ModelGatewayUpstreamError`); `backend/lib/config/model_gateway.py`; `backend/lib/dtos/model_gateway.py` (`TypeSafeDecisionRequestDto` with extra=forbid, `ModelUsageCallDto`, `ModelUsageSessionDto`); `backend/lib/errors/model_gateway.py`; `backend/lib/enums/api_keys.py`; `backend/lib/app/route_rules.py` (around lines 157-159, the route rules rows carrying the `models:invoke` scope); `backend/lib/api/dependencies.py` (around lines 93-106, `ModelGatewayCaller`); `backend/services/usage/enforcer.py` (reserve/settle/release primitives); `backend/lib/usage/README.md`; tests in `backend/tests/features/model_gateway/` (`FEATURE.md`, `test_model_gateway.py`, `test_model_gateway_replays_mongo.py`).
- SDK, existing managed pattern: `vidbyte/lib/dataclasses/model_configs.py` (`DecisionModelConfig.resolved_api_key()` / `resolved_endpoint()` / `resolved_run_close_url()` in managed mode; `TextModelConfig` with `api_key`, `endpoint`, `timeout_seconds`, `validate()`, `resolved_api_key()`, `resolved_endpoint()`); `vidbyte/lib/registries/models.py` (`ProviderModelRegistry.resolve_api_key`: explicit → provider env var → error; `resolve_endpoint`; `DEFAULT_ENDPOINTS`; `API_KEY_ENV_VARS`); `vidbyte/lib/constants/jev.py` (`VIDBYTE_JEV_GATEWAY_ENDPOINT = https://api.vidbyte.pro/api/v1/models/typesafe`, header-name constants, `VIDBYTE_MANAGED_ACCESS_DENIAL_STATUS_CODES = {401,402,403,429}`); `vidbyte/lib/http/transport.py` (`HttpTransport.request`, `_require_idempotency_guard`); `vidbyte/lib/http/parser.py` (`HttpResponseParser.bearer_headers`); `vidbyte/providers/{openai,anthropic,gemini,compatible,openrouter,typesafe}.py` (URL suffixes and auth headers per dialect; TypeSafe's managed error redaction); `vidbyte/lib/runners/text.py`, `vidbyte/lib/runners/streaming_text.py` (OpenAI/Anthropic only); `vidbyte/lib/usage_ledger.py`; `vidbyte/agents/pricing/tracker.py`.
- SDK key-isolation guards that reject an explicit API key crossing providers live outside `vidbyte/lib/`: `vidbyte/agents/settings/fallback.py` (~142-149), `vidbyte/agents/fork.py` (~85-94), `vidbyte/agents/aggregation.py` (~342-349).
- The assistant suggested that a key with the `vb_live_` prefix implies managed mode, so existing users who set only `VIDBYTE_API_KEY` switch to managed mode without code changes.
- Existing SDK tests to model on: `tests/test_jev_managed_gateway.py`, `tests/test_jev_managed_runs.py` (scripted transport, no network).

### Open questions (the spec authors resolve these from the code or carry them as A-/Q- items with defaults)
- **Single-route request shape.** How the SDK tells the one route which provider (and which upstream operation) to call, and how the native provider body travels with it.
- **SDK redirect inside the lib layer.** The provider adapters in `vidbyte/providers/` append their own dialect path suffixes to `resolved_endpoint()` and build their own auth headers; how managed requests reach one gateway route while keeping SDK edits in `vidbyte/lib/`.
- **Which providers are live in this version.** §E.4 lists four dialects but names three provider secrets to provision (OpenAI, Anthropic, Gemini, per §E.3 step 7). Whether the chat-completions family is dispatched in this version, and what a provider without a configured server key returns.
- **Session bucketing for generative calls that carry no run id.** §E.4 states that calls without a run id fall into a per-key daily bucket; verify that this exists, and keep generative calls out of TypeSafe sessions and out of cross-provider sessions.
- **Where the daily per-key spend cap is configured** (a constant, a per-key field, or something else) — the smallest version that bounds a leaked key.
- **Where the 200 bps constant lives and how it is selected per provider** without changing Jev's 1,000 bps.
- **Whether the SDK key-crossing guards outside `vidbyte/lib/` need any change** when the managed key comes from `VIDBYTE_API_KEY`.

## D. Weighted words

- "all tokens" — Prompt 1: "can you suggest how we might take a 2% markup on all tokens travelled through our sdk?"
- "no workarounds" — Prompt 1: "want to make sure that there are no workarounds"
- "the same" / "all of the generative model calls" — Prompt 2: "how can we provide the same markup/gateway that we are providing to jev model calls to all of the generative model calls of the sdk?"
- "all we have to do" / "simply" — Prompt 4: "so all we have to do is to add 1 endpoint to the vidbyte backend ... and we simply read the reponse from the model provider when decrementing using?"
- "1 route" — Prompt 5: "I want 1 route in the vidbyte/ repo, and then handle the underlying api requests in a orchestrator/server layer for the different routes to the different providers."
- "the lib layer" — Prompt 5: "the sdk changes we can handle in the lib layer of the repo."
- "2% markup" — Prompt 5: "lets achieve this 2% markup on generative tokens"

## E. Assistant answers the user responded to (verbatim, for context)

These are the assistant's substantive answers between the user's prompts. They are proposals, not decisions; where the user's later prompts differ (notably Prompt 5's one route instead of four), the user's prompts win. File paths and line numbers in them were read at the time and must be re-verified.

### E.1 — answer to Prompt 1

`````markdown
The short answer: a markup with genuinely no workarounds is only possible for tokens that physically pass through a server you control, bought with provider keys only you hold. Your backend already has that server for Jev decisions. The work is to extend it to the generative providers and give the SDK a managed text mode that mirrors the managed Jev mode. Tokens a user buys from OpenAI or Anthropic with their own key cannot be metered or billed by an open-source client, and your own design docs already say so.

## Why the client cannot enforce it

- **The SDK is MIT and on PyPI.** Anyone can fork it, delete a metering call, or monkeypatch the transport. Every runner accepts an injected `HttpTransport` by design.
- **It is bring-your-own-key for 14 providers.** The registry resolves `OPENAI_API_KEY` and friends and posts straight to the vendor host. Nothing Vidbyte-owned sits in that path.
- **Endpoint override is a documented feature.** Every model config has an `endpoint` field described as being for proxies and tests.
- **Client-side cost is informational only.** The usage tracker prices calls from a local pricebook for the developer's benefit. If the client reported those numbers to you for billing, a user could report zero.
- **The Codex harness never touches SDK HTTP.** It drives the `openai-codex` app server under the user's own ChatGPT login, and usage arrives afterwards as self-reported counts. That path is structurally unbillable, and the Codex usage design doc says as much.
- **The repo already concedes this.** Both managed-gateway design docs list "prevent a caller who modifies the SDK from bypassing Vidbyte" as a non-goal and state that the server is authoritative for every request it receives.

So "no workarounds" has to mean: no way to obtain Vidbyte-paid tokens without paying Vidbyte's fee. That is fully achievable, and most of it is built.

`★ Insight ─────────────────────────────────────`
The managed Jev design rests on one trick worth reusing: the gateway's request DTO mirrors TypeSafe's body "field for field, so the SDK's adapter switches between direct and managed mode by endpoint and key alone." Your OpenAI, Anthropic and Gemini adapters already emit native vendor payloads, so a generative gateway that is byte-compatible with each upstream path needs no new wire format on either side. Only the host and the auth header change.
`─────────────────────────────────────────────────`

## What exists and what to extend

The backend already has the route, orchestrator, metering, idempotent replays, run-scoped usage sessions, an idle reaper, a wallet admission floor, and the markup formula. All of it is TypeSafe-only today. The relevant constants:

| Constant | Today | For a 2% token markup |
|---|---|---|
| `MODEL_GATEWAY_MARKUP_BASIS_POINTS` | 1,000 (10%, Jev only) | keep, or align |
| generative markup | none | new constant at 200 |
| `MODEL_GATEWAY_ADMISSION_FLOOR_CENTS` | 1 cent | replace with a reservation |

**Server work, in order:**

1. **Generalize the gateway from one TypeSafe path to one path per provider.** Keep each path byte-compatible with upstream so the SDK adapters change only host and header. The route file is `routes/model_gateway.py` and its header already says the modification pattern is one new route plus its rule.
2. **Hold provider keys server-side only.** The TypeSafe client already pulls its key from the server credential store and turns an upstream 401 into a 502, which is the right behaviour to copy.
3. **Price only what the provider's response says.** The meter in `services/model_gateway/metering.py` already does this with the SDK's own usage tracker and explicitly forbids billing client-reported usage. Add the 200 basis-point constant beside the Jev one.
4. **Reserve before forwarding, settle after.** A 1 cent floor is fine when a Jev token costs 42 nano-USD, but a long-context frontier call can cost dollars, so concurrent calls could overdraft the wallet. The reservation primitives already exist in `services/usage/enforcer.py` for research runs.
5. **Handle streaming on the server.** Force usage reporting on OpenAI streams, read Anthropic's final delta usage and Gemini's usage metadata, and if a stream dies before the usage block arrives, bill input from a server-side token count and output from chunks seen so far. Fail closed.
6. **Reject unpriced and uncatalogued models.** The 422 for an unpriced model already exists.
7. **Return the billed cost in response headers** so the SDK can show the marked-up figure to the developer.

**SDK work:**

1. **Add a managed text mode that mirrors the decision one.** The pattern is already in `DecisionModelConfig`: a mode enum, a live-key format check, a pinned host, custom endpoints rejected, run-id and idempotency headers, and run close. The natural trigger is `VIDBYTE_API_KEY` set with no provider key given.
2. **Prefer gateway-reported cost in the usage tracker** when in managed mode, the same way OpenRouter's reported cost already wins over table math.
3. **Keep BYOK and document the fee plainly.** More on that below.

`★ Insight ─────────────────────────────────────`
The money path is integer nano-USD with the markup applied once to the run total, floor cents while a run is open and ceiling at close. The accumulator's header explains why: at $0.042 per million tokens, rounding each call up to a cent would multiply the effective price many times over. A 2% generative markup should ride that same accumulator unchanged. Only the basis-point constant and the provider enum differ.
`─────────────────────────────────────────────────`

## Workaround surface and what stays outside

Within managed mode, these are the attacks that matter and what closes each:

- **Under-reporting usage.** Impossible, since the server reads the provider's response and never the client's numbers.
- **Pointing a live key at another host.** The SDK rejects it in managed mode, and the key only works at Vidbyte anyway.
- **Streaming to dodge the usage block.** Closed by forcing usage on and failing closed on truncation.
- **Concurrent calls to overdraft.** Closed by reserving before forward.
- **Retrying for a free second answer.** Closed by the existing idempotency replay keyed on request hash.
- **A new model with no price.** Rejected at admission.
- **Key sharing or a leaked key.** Token-bucket tiers exist. Add per-key daily spend caps, because with managed mode a stolen key becomes your OpenAI bill.
- **Forking the SDK and hand-rolling a gateway client.** Still billed. The gateway charges every request it serves regardless of what sent it.

What no design closes:

- **BYOK direct calls.** The only lever is product value: one key for every provider, a wallet, run-level cost sessions, idempotent retries, and the fact that JevAgent already requires a live key. You could gate more features on a live key the way JevAgent does, but you cannot verify that a run's generative tokens went through you.
- **The Codex harness.** Exclude it from the markup or charge a flat per-turn fee, knowing the counts are self-reported.
- **Stripping BYOK from the SDK.** I would advise against it. It turns the SDK from an agent framework into a 2% tax on OpenAI, and the vendor SDKs and LangChain are free. Adoption would fall faster than revenue would rise.

Things to decide before building:

- **Two rates or one.** Jev is marked up 10% today. A 2% generative rate means two constants, which is fine but should be deliberate.
- **2% is below card processing cost.** Unless wallet top-ups have a meaningful minimum, Stripe fees alone exceed the margin on small balances.
- **You front the provider spend.** Reservations, spend caps and rate tiers are the mitigations, and they belong in the first release, not a follow-up.
- **Resale terms.** Confirm each provider's terms permit proxying their API under your key to third parties.

I can turn this into a pre-design doc under `docs/pre-design` in the SDK repo if you want it in the normal design-doc workflow.
`````

### E.2 — answer to Prompt 2

`````markdown
Yes. The Jev path is already the template, and the job is to lift it from one provider to the text providers on both sides. Here is the concrete shape.

## How the Jev path works today, in one picture

```
SDK                                        Backend (api.vidbyte.pro)
DecisionModelConfig(VIDBYTE_MANAGED)
  key   = VIDBYTE_API_KEY (vb_live_…)
  host  = /api/v1/models/typesafe (pinned)
  hdrs  = Bearer key, X-Vidbyte-Run-Id, Idempotency-Key
      │ POST /systemone (TypeSafe-native body)
      ▼
                                    gatekeeper: key → user, scope models:invoke, throttle
                                    orchestrator.decide:
                                      require_priced(model)        ← SDK pricebook
                                      replays.begin(idem key)      ← same body? replay
                                      ensure_admissible(wallet)    ← 1 cent floor
                                      client.decide(body)          ← Vidbyte's TYPESAFE key, relay bytes
                                      meter.price(result)          ← SDK UsageTracker on upstream usage
                                      meter.record(run_id, call)   ← $inc nano-USD into run session
                                      settle: markup on run total, debit newly owed cents
JevManagedRun.__aexit__ → POST /runs/{id}/close → ceiling settle
```

Every box in that picture is provider-generic in spirit. Three things are TypeSafe-specific in code: the request DTO, the relay client, and the usage extraction. Everything else is reuse.

## SDK side: a managed mode for text configs

**Mode and constants.** Promote the Jev-only pieces to shared ones. Move the run-id and idempotency header names out of `vidbyte/lib/constants/jev.py` into a gateway constants module, and add the gateway root `https://api.vidbyte.pro/api/v1/models`. The Jev close-URL code already derives that root by stripping the `/typesafe` suffix, so this is just naming what exists.

**TextModelConfig.** Mirror `DecisionModelConfig` exactly in `vidbyte/lib/dataclasses/model_configs.py`: a `mode` field, `repr=False` on the key, a managed `resolved_api_key()` that accepts only the live-key format, and a managed `resolved_endpoint()` that returns the gateway root plus the provider name and rejects any custom endpoint. The adapters already append their own suffixes, so OpenAI resolves to `…/models/openai` and posts to `…/models/openai/responses` with no adapter change to the URL logic.

**Key resolution and auto-managed.** Keep BYOK behaviour unchanged, and add one fall-through in `ProviderModelRegistry.resolve_api_key`: explicit key, then the provider's env var, then `VIDBYTE_API_KEY`. A resolved key with the `vb_live_` prefix flips the config to managed. An existing user with their OpenAI key set sees nothing change. A new user with only a Vidbyte key goes managed with zero configuration. An explicit `mode=VIDBYTE_MANAGED` forces it and skips the provider env var.

**One key for every provider.** Three places deliberately refuse to pass a key across providers: fallback in `vidbyte/agents/settings/fallback.py`, fork, and aggregation. A Vidbyte key is provider-agnostic, so each needs a one-line exception, best expressed as a shared `is_managed_key()` helper on the registry.

**Headers.** Today OpenAI uses bearer, Anthropic uses `x-api-key`, Gemini uses `x-goog-api-key`. Add a small header builder in `vidbyte/lib/http/` that returns the provider's native auth in direct mode and `Authorization: Bearer vb_live_…` plus run-id and idempotency headers in managed mode. Each adapter's header method calls it. Anthropic keeps sending `anthropic-version` so the gateway can forward it.

**Run scope.** Generalize `TypeSafeManagedRunContext` and `JevManagedRun` into a provider-agnostic run context in a lib module that sits below providers. The Jev design doc explains the context var lives in the TypeSafe adapter only to dodge an import cycle, and a module at `vidbyte/lib/` level avoids that. Text adapters read it the same way the TypeSafe one does. `AgentRuntime` opens a run at the start of a managed agent run and closes it at the end, so every generative call, every nested fork and handoff, and any JevAgent decisions all carry one `X-Vidbyte-Run-Id` and settle as one session.

**Idempotency.** The transport already refuses to retry a POST without a key. The runtime's retry and fallback loop should mint one key per logical model call and reuse it across attempts, so the gateway replays a billed answer instead of charging twice.

**Cost transparency.** Have the local tracker apply the same basis points in managed mode so `get_cost_usd()` matches the bill to within rounding, and surface the close-run summary on the final message's metadata. The close response already returns fee and billed cents, and `JevManagedRun` currently discards it.

**Out of scope for phase one.** `StreamingTextModelRunner` is not wired into agents and discards usage, so reject managed mode there until the gateway relays SSE. Image, video, audio and embedding configs follow the same pattern later. OpenRouter has no pricebook rows and is itself a gateway, so exclude it. Codex stays unbillable.

**Tests.** Copy the shape of `tests/test_jev_managed_gateway.py` and the managed-runs test: scripted transport, no network, one test per header, per failure status, per run-scope rule.

`★ Insight ─────────────────────────────────────`
There are eleven text providers but only four wire dialects: OpenAI Responses, Anthropic Messages, Gemini generateContent, and the chat-completions family that xAI, DeepSeek, GLM, MiniMax, Kimi, Meta and Mistral all share through `OpenAICompatibleProvider`. Build the gateway per dialect, not per provider, and the provider name in the path only selects which upstream host and credential the relay uses. That is four relay routes, not eleven.
`─────────────────────────────────────────────────`

## Backend side: generalize the gateway

**Routes.** In `routes/model_gateway.py`, add one byte-compatible route per dialect under the existing prefix, with matching rules in the route table carrying `models:invoke` and the API-key throttle. The paths must equal the gateway root plus provider plus the SDK adapter's own suffix, because the SDK does not know it is talking to a gateway. Gemini's suffix contains a colon, which Starlette path matching handles but should get its own test.

**Relay client.** Generalize `provider/typesafe/client.py` into a provider relay. The credential loader's `require_provider_key` is already written to be provider-generic by intent, so it needs only the extra key fields and deployment secrets. The relay swaps the caller's bearer for the provider's native auth header, forwards an allow-listed set of headers such as the Anthropic version, caps body and response size, sends no retries, and maps an upstream 401 or 403 to a 502 exactly as the TypeSafe client does.

**Request DTO.** Do not model generative bodies field by field. Accept a bounded JSON body, pull `model` from the body or the Gemini path for the price check, and pass the bytes through. The replay service already digests the body, so widening its parameter type is enough.

**Usage extraction.** The meter's `price()` reads `body["usage"]`, which is right for OpenAI, Anthropic and chat-completions but wrong for Gemini, whose usage sits under `usageMetadata`. Add a per-dialect extractor. Pricing itself needs no work, because the SDK tracker dispatches on provider and the backend already imports it.

**Markup and mixed runs.** This is the one real data-model change. A session fixes `provider` and `markup_basis_points` at first insert and applies the markup to the run total at settlement. A generative run with a fallback or a Jev decision mixes providers, and Jev is at 10% while you want 2% here. Two options:

- **Per-call fee accrual, recommended.** Price each call's fee at its own basis points and `$inc` a `fee_nanousd` field beside the provider cost. Settlement rounds the total once, so the no-per-call-rounding property is kept. The session's single rate field becomes informational or goes away.
- **One session per run and provider.** Fold the provider into the session id. Less code, but closing a run then means closing several sessions and the run summary becomes a merge.

**Admission.** The 1 cent floor is fine when a Jev token costs 42 nano-USD. A long-context frontier call costs dollars, and concurrent fan-out can overdraft the wallet. Reserve before forwarding using the reserve, settle and release primitives already in `services/usage/enforcer.py`, estimate from body size and the request's output cap, and settle to actual usage after the response.

**Constants.** Add a generative basis-point constant of 200 next to the Jev one in `lib/config/model_gateway.py` and have the meter select by provider.

**Tests.** The feature pack at `tests/features/model_gateway/` gains one relay test per dialect, Gemini usage extraction, a mixed-provider run accruing two rates, a reservation that blocks a second concurrent call, and a replay across a retried generative call.

`★ Insight ─────────────────────────────────────`
The orchestrator's own header says a metering failure after a successful answer is logged and the answer still returns, because the upstream call is already paid for and failing would only invite a second paid call. That rule matters more for generative traffic than for Jev, since a single retried 100k-token call costs real money. Keep it, and add a reconciliation job comparing Vidbyte's upstream provider invoices against wallet debits so silent metering gaps surface as a number rather than as lost margin.
`─────────────────────────────────────────────────`

Suggested order: backend per-call fee accrual and reservation first, since they change schema, then the OpenAI dialect end to end on both sides, then Anthropic and Gemini, then the chat-completions family, with streaming and other modalities as a second phase. I can write this up as a pre-design doc in each repo so it can go through `/implement-design-doc`.
`````

### E.3 — answer to Prompt 3 (step by step)

`````markdown
Here it is as a sequence. First what a call will look like once it's done, then the build steps in the order I'd do them.

## What one managed OpenAI call will look like

```
1. Developer sets VIDBYTE_API_KEY=vb_live_… and no OPENAI_API_KEY.
2. Agent builds a TextModelConfig. Key resolution finds only the Vidbyte key,
   sees the vb_live_ prefix, and flips the config to managed mode.
3. Managed endpoint resolves to https://api.vidbyte.pro/api/v1/models/openai.
   The OpenAI adapter appends /responses as it always does.
4. Adapter sends the normal OpenAI body with headers:
   Authorization: Bearer vb_live_…   X-Vidbyte-Run-Id: run:…   Idempotency-Key: …
5. Backend gatekeeper turns the key into a user and checks models:invoke.
6. Orchestrator: is the model priced? seen this Idempotency-Key? reserve wallet credit.
7. Relay swaps the bearer for Vidbyte's own OpenAI key and forwards the bytes.
8. OpenAI answers. Relay returns the body unchanged to the SDK.
9. Meter reads the usage block, prices it with the SDK pricebook,
   adds 2 percent as fee_nanousd, accrues both into the run's session, settles cents.
10. Agent run ends. SDK posts /runs/{id}/close. Backend rounds up the last part-cent
    and returns the summary, which lands in the agent's final metadata.
```

The developer's code did not change. Only the key did.

## Build steps, backend first

Backend first because the SDK side can then be tested against a real gateway, and because the two backend steps that touch the database schema should land before anything depends on them.

1. **Make the fee accrue per call instead of per run.** Today a session stores one markup rate at creation and applies it to the run total at settlement. Add a `fee_nanousd` field on the call DTO and the session, compute each call's fee at that call's rate, and increment it alongside provider cost. Settlement then sums instead of multiplying. Done when the existing Jev tests pass unchanged and a new test shows a run with one 10% call and one 2% call accruing the right total.

2. **Add the 2% constant.** One line in `lib/config/model_gateway.py`, 200 basis points, selected by provider in the meter. Jev keeps 1,000.

3. **Reserve before forwarding.** Replace the 1 cent admission floor with a reservation: estimate cost from body size and the request's output cap, reserve it, forward, settle to actual, release the rest. The reserve, settle and release functions already exist in `services/usage/enforcer.py`. Done when two concurrent calls against a wallet that can afford one are admitted one and refused one.

4. **Generalize the relay client.** Turn `provider/typesafe/client.py` into a client that takes a provider name, a path and a body. It looks up the upstream host from the SDK registry, pulls Vidbyte's key for that provider from credentials, builds the native auth header, forwards an allow-list of headers such as the Anthropic version, and keeps the existing size caps and the 401-to-502 rule. Done when unit tests show the right header for OpenAI, Anthropic and Gemini.

5. **Teach the meter where usage lives per dialect.** The meter reads `body["usage"]`, which works for OpenAI, Anthropic and chat-completions but not Gemini, which uses `usageMetadata`. Add a small per-dialect extractor. Done when a sample body from each provider prices to the same figure the SDK tracker gives.

6. **Add the routes.** One route per dialect under the existing `/api/v1/models` prefix, with matching rows in the route rules table carrying the `models:invoke` scope. The orchestrator gains a generic relay method and the Jev `decide` becomes a thin wrapper over it. Done when a `curl` with a live key to the OpenAI route returns an OpenAI answer and the wallet shows a debit.

7. **Add provider keys to the deployment.** New fields in the credential loader for OpenAI, Anthropic and Gemini, plus the secrets themselves.

8. **Add a reconciliation job.** Nightly, compare upstream provider spend to wallet debits for the day. This catches silent metering gaps as a number instead of as lost margin.

`★ Insight ─────────────────────────────────────`
Step 1 is the only step that changes meaning rather than adding surface. Everything downstream, from reservations to routes, assumes a session can hold calls at different rates. Doing it first means every later test runs against the final data model, and the Jev suite acts as a regression net for free.
`─────────────────────────────────────────────────`

## Build steps, SDK side

9. **Create shared gateway constants and a shared run context.** Move the run-id and idempotency header names out of the Jev constants, add the gateway root URL, and lift `TypeSafeManagedRunContext` plus `JevManagedRun` into a provider-neutral module under `vidbyte/lib/`. The Jev adapter switches to the shared one. Done when the Jev managed-run tests pass with the new imports.

10. **Give `TextModelConfig` a managed mode.** Copy the pattern from `DecisionModelConfig` in the same file: a mode field, the key hidden from repr, a managed key resolver that accepts only the live-key format, and a managed endpoint resolver that returns the gateway root plus the provider name and rejects custom endpoints. Done when a managed config resolves to the right URL and refuses an override.

11. **Add the key fall-through.** In the provider registry, resolve an explicit key, then the provider's env var, then `VIDBYTE_API_KEY`. A key with the live prefix means managed. Then relax the three "key never crosses providers" guards in fallback, fork and aggregation so a Vidbyte key is passed to every child. Done when a user with only a Vidbyte key goes managed and a user with an OpenAI key is untouched.

12. **Route all adapters through one header builder.** A helper in `vidbyte/lib/http/` returns native auth in direct mode and bearer plus run-id plus idempotency headers in managed mode. OpenAI, Anthropic, Gemini and the compatible family call it from their existing header methods. Done when each adapter's managed headers match what the backend routes expect.

13. **Open and close the run from the agent runtime.** At the start of a managed run the runtime enters the run context and at the end it posts the close, best-effort, the way the Jev wrapper does. Nested forks, handoffs and JevAgent decisions join the same run. The retry loop mints one idempotency key per logical model call. Done when a test shows every call in a run carrying one run id and exactly one close.

14. **Show the real cost to the developer.** Have the local tracker apply the same basis points in managed mode, and put the close summary into the final message metadata. Done when `get_cost_usd()` is within a cent of the billed figure.

15. **Fence off what is not covered yet.** Streaming raises a clear error in managed mode, OpenRouter is excluded, Codex is documented as unbillable. The README gets a short managed-mode section that states the fee plainly.

16. **Tests.** Mirror the two Jev test files as managed text tests, scripted transport and no network, one case per header, per status code, per run-scope rule.

`★ Insight ─────────────────────────────────────`
Using the key prefix as the mode signal, rather than a separate flag, is what makes step 11 backward compatible. A `vb_live_` key can only ever work at Vidbyte, so seeing one is proof of intent. No existing config, YAML file or environment changes meaning, and the migration for a user is literally one environment variable.
`─────────────────────────────────────────────────`

After both halves ship, phase two is streaming relay with usage on the final chunk, then image, video, audio and embedding configs following step 10's pattern. I can turn steps 1 to 8 and 9 to 16 into two pre-design docs, one per repo, if you want to hand them to implementation sessions.
`````

### E.4 — answer to Prompt 4 (the proposal the user answered "great")

`````markdown
Yes. That is the whole mechanism, and it is why it's enforceable: a reverse proxy that swaps the caller's Vidbyte key for your provider key on the way in, and bills from the provider's own usage block on the way out. The Jev gateway is exactly that already, and its meter has an explicit intent comment saying only gateway-observed usage is ever billed. The proxy itself is a couple of hundred lines.

Two small corrections to the picture:

- **It's four routes, not one, unless you change the SDK's wire format.** The SDK adapters append their own paths, `/responses` for OpenAI, `/messages` for Anthropic, `/models/{m}:generateContent` for Gemini, `/chat/completions` for the compatible family. If the gateway mirrors those paths, the adapters need no body changes, and as a bonus any third-party client works too: the official OpenAI SDK with `base_url` pointed at your gateway and a `vb_live_` key just works. You could instead do one generic `POST /invoke` with a provider field, but then only your SDK can use it.
- **"Forward the SDK agent request" needs two SDK changes, not zero.** The adapter has to pick the gateway host instead of the vendor host, and send `Authorization: Bearer vb_live_…` instead of the vendor's auth header. That is the managed mode on `TextModelConfig` plus the header builder. Everything else on the SDK list was polish.

The other steps in my list exist because you now pay the provider before you know what to charge. Here is what each one protects against and whether it belongs in the first version:

| Concern | What goes wrong without it | First version? |
|---|---|---|
| Worst-case admission check | Empty wallet after you've paid OpenAI for a $3 call | Yes, cheap version |
| Per-dialect usage extraction | Gemini calls bill zero because usage is under `usageMetadata` | Yes |
| Rate per provider | Generative calls billed at Jev's 10% | Yes, one line |
| Idempotency on retries | SDK retries a timed-out call and you pay twice | Reuse existing, send the header |
| Per-call fee accrual | Jev and generative calls in one run get one rate | Only once run ids are shared |
| Full reservations | Concurrent fan-out overdrafts | Later |
| Streaming relay | Usage arrives in the last SSE chunk | Later, reject managed streaming until then |
| Daily spend cap per key | A leaked key becomes your provider bill | Yes, it's a number check |

`★ Insight ─────────────────────────────────────`
The mixed-rate problem only appears when a generative call and a Jev decision share an `X-Vidbyte-Run-Id`. Today Jev always sends a run id and plain calls without one fall into a per-key daily bucket, so if the first version leaves run ids off generative calls, every session has one provider family and one rate, and the schema change can wait.
`─────────────────────────────────────────────────`

So the smallest correct version is:

1. **Backend:** four byte-compatible routes, one relay client that swaps auth and forwards bytes, a usage extractor per dialect, a 200 basis-point constant chosen by provider, and an admission check that rejects a call whose worst-case cost exceeds the balance. Worst case is the request's output cap times the output rate plus a rough input estimate from body size.
2. **SDK:** managed mode on the text config that pins the gateway host and requires a live key, the key fall-through so `VIDBYTE_API_KEY` alone switches a user to managed, and one header builder the adapters call.
3. **Ops:** three provider secrets in the credential loader and a daily spend cap per key.

That ships the 2% on every text call that goes through managed mode. Run ids, close-run summaries, per-call fees, reservations and streaming are the second pass, and none of them change the billing rule you described.
`````
