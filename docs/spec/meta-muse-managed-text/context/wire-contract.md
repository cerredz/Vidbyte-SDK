# Wire contract: Run A spec §9.2-§9.4 (verbatim copy)

Source: cerredz/Vidbyte PR https://github.com/cerredz/Vidbyte/pull/710, branch `feat/meta-muse-gateway`, file `docs/spec/meta-muse-gateway/spec.md` r4 at commit `c395349bd`, lines 327-407. Copied by the orchestrator on 2026-10-16 so this run reads a stable text. The live copy: `gh api 'repos/cerredz/Vidbyte/contents/docs/spec/meta-muse-gateway/spec.md?ref=feat/meta-muse-gateway' --jq .content | base64 -d`. Section references below (EC-, A-, Q-, D-, NG-) point into that backend spec, not into this repo.

---

### 9.2 API and interface surface

This is the wire contract that SDK Run B (`meta-muse-managed-text`) cites. It is the existing generative-gateway contract, unchanged, with `meta` added as a seventh provider.

- **Route:** `POST /api/v1/models/generate` (route rule `models.generate`). Access is by API key only, with scope `models:invoke`, and the route is unpriced at the gate. Auth is `Authorization: Bearer vb_live_…` or `x-api-key: vb_live_…`.
- **Envelope:** `{"provider": "meta", "model": "<id>", "body": {…}}`, with `extra="forbid"`. `provider` must be exactly `meta`. `model` must match `^[A-Za-z0-9._:-]+$` and be at most 128 characters, so a `meta/`-prefixed id is a 422 `harness_validation_failed`.
- **Model ids served in production (pin `54a8e1a5`):** `muse-spark-1.1`, plus the gateway's dated-snapshot forms `muse-spark-1.1-YYYY-MM-DD` and `muse-spark-1.1-YYYYMMDD`. Meta's pages list no dated Muse ids. Every other Muse id gets 422 `model_gateway_unsupported_model`, including `muse-spark-1.3`, the id in Meta's own examples. When the pin moves, the served set becomes whatever the new pin's `PROVIDER_PRICING[META]` lists, on both paths.
  - *The Q-1 hotfix* (Standard rows only) adds `muse-spark-1.2` and `muse-spark-1.3`, safely.
  - *Any pin that lists `-contributor` ids*, SDK main included, also serves those under Vidbyte's own key, where Meta may train on the content (EC-29). That must be decided (Q-4) before such a pin is adopted.
- **Relay header:** `X-Vidbyte-Provider-Key: <caller's Meta key>`. The value must be visible ASCII (`^[!-~]+$`) and 1 to 512 characters, and Meta's documented key shape `LLM|<app id>|<secret>` passes. The header present makes the call a relay call. Absent, the call is Vidbyte-paid. A replay ignores the header.
- **Body (Meta Chat Completions):** the top-level fields allowed are `model`, `messages`, `temperature`, `top_p`, `max_tokens`, `max_completion_tokens`, `n`, `stop`, `tools`, `tool_choice`, `response_format`, `metadata`, `frequency_penalty`, `presence_penalty`, `seed`, `user`, `parallel_tool_calls`, `reasoning_effort`, and `stream`. At least one of `max_tokens` or `max_completion_tokens` is required, as a JSON integer of 1 or more. Tools must be `{"type": "function", …}`. `stream` must be absent, false, or null. A body `model`, if present, must equal the envelope's. The SDK's `MetaProvider` body (messages, temperature, top_p, `max_tokens`, stop, tools, tool_choice, response_format, metadata) passes this list, but it sets `max_tokens` only when `max_output_tokens` is configured. Run B must therefore ensure a cap is sent, or every call answers `output_cap_missing`. It should send the cap as `max_completion_tokens`, which Meta documents as counting "both visible output and reasoning tokens", rather than `max_tokens`. Whether `max_tokens` counts reasoning is unverified (A-3). With `max_completion_tokens`, admission and the hold for SDK traffic do not depend on A-3, at no backend cost.
- **Upstream:** one POST to `https://api.meta.ai/v1/chat/completions` (the SDK registry endpoint) with `authorization: Bearer <key>`, no retries, and a total deadline of 600 seconds.
- **Billing:** Vidbyte-paid calls bill TOTAL, which is SDK-priced provider cost plus 200 bps, accrued per key, provider, and UTC day. Relay calls bill FEE_ONLY, the 200 bps fee alone, in a separate session. Both price Meta's own `usage` (`prompt_tokens`, `completion_tokens`, `prompt_tokens_details.cached_tokens`) at the pinned SDK row.

**What a client sees** (the provider-native body is relayed for every row marked "Meta's"):

| Situation | Status | `code` in the gateway error body | Billed |
|---|---|---|---|
| Meta answers (any 2xx, or a 4xx/5xx other than a Vidbyte-paid 401/402/403) | Meta's | none: Meta's own JSON, never `"error": true` at top level | 2xx with usage: TOTAL or FEE_ONLY; otherwise nothing |
| `provider` not exactly `meta` (and not another managed provider) | 422 | `model_gateway_unsupported_model` | nothing |
| Model not in the pinned pricebook | 422 | `model_gateway_unsupported_model` | nothing |
| Streaming, unlisted field, non-function tool, missing or invalid cap, invalid `n`, model mismatch | 422 | `model_gateway_unbillable_request` | nothing |
| Malformed envelope or malformed relay header | 422 | `harness_validation_failed` | nothing |
| Forwarded body over 2,000,000 bytes | 413 | `model_gateway_request_too_large` | nothing |
| Wallet below the worst case under the call's basis | 402 | `model_gateway_payment_required` | nothing |
| Vidbyte-paid call over the key's daily spend cap | 429 | `model_gateway_daily_spend_cap_reached` | nothing |
| Vidbyte-paid call with no Vidbyte Meta key configured | 502 | `model_gateway_upstream_failed`, with the missing-key copy below | nothing |
| Vidbyte-paid call that Meta refuses with 401, 402, or 403 | 502 | `model_gateway_upstream_failed` | nothing |
| Meta unreachable or over 600 s | 502 | `model_gateway_upstream_failed` | nothing |
| Meta answered a body that is not JSON, or JSON that is not an object | 502 | `model_gateway_upstream_failed` | nothing (a Vidbyte-paid hold is kept) |
| Relay call that Meta refuses with 401, 402, or 403 | Meta's | none: Meta's own JSON | nothing |
| Wallet, counter, or session store failure | 503 | `model_gateway_unavailable` | nothing |
| Same `Idempotency-Key` still in flight, or reused for another body | 409 or 422 | `model_gateway_idempotency_in_progress` or `model_gateway_idempotency_key_reused` | nothing |

**Which row answers when several apply.** The checks run in a fixed order, and the first one that fails answers; nothing after it runs. The order is:
1. the envelope and header validation (422 `harness_validation_failed`);
2. the provider (422 `model_gateway_unsupported_model`);
3. the body rules (422 `model_gateway_unbillable_request`);
4. the forwarded size (413);
5. Vidbyte's own key, on a Vidbyte-paid call only (502 with the missing-key copy);
6. the pinned pricebook (422 `model_gateway_unsupported_model`);
7. the `Idempotency-Key` claim (409 or 422; a completed claim returns its saved answer here);
8. the wallet (402), then the daily spend cap on a Vidbyte-paid call (429); a wallet or counter store failure is the 503;
9. the call to Meta.

So a Vidbyte-paid call that names an unlisted model while Vidbyte holds no Meta key answers 502, not 422 (EC-11). Steps 2 to 5 are `GenerativeModelClient.plan`, and steps 6 to 9 are `GenerativeModelGatewayOrchestrator.generate`.

**Missing-key copy** (`ModelGatewayProviderKeyUnconfiguredError.public_payload()`; the same for every managed generative provider):

| Field | Value |
|---|---|
| `title` | `Vidbyte-paid access not configured` |
| `subtitle` | `Send your own key for this provider in the X-Vidbyte-Provider-Key header, or use another provider; nothing was billed for this call.` |
| `description` | `Vidbyte has no key of its own configured for this model provider, so it cannot make Vidbyte-paid calls to it until an operator adds one.` |
| `code` | `model_gateway_upstream_failed` (unchanged) |

Every other 502 in this table keeps today's copy: "Model provider unavailable" / "Retry after a short delay; nothing was billed for this call."

**Who sees the missing-key copy.** Two consumers read only the status.
- *The SDK.* Its transport at SDK main (`vidbyte/lib/http/vidbyte_gateway.py`, with wording from `docs/spec/byok-api-keys/spec.md` §9.2 table G) ignores the body and the code ("the remedy comes from the status alone"). It re-sends every 502 twice and words a Vidbyte-paid 502 as "… unavailable or refused Vidbyte's own account (HTTP 502), and the cause is not known …".
- *The public status page.* It counts every 5xx against the route (EC-30).

So today the copy reaches direct HTTP callers and agents that read the body, not SDK users.

**Recommendation for the SDK follow-up, not an obligation.** Run B decides its own scope under its own rules. When a 502 body carries top-level `"error": true`, append its `subtitle` to the SDK's message. That surfaces the missing-key remedy with no new code. Re-sending this particular 502 is harmless, because it does no I/O and bills nothing.

**Not listed here:** API-key authentication, `models:invoke` scope, and request-quota throttling answer before this route runs. They are identical for every provider, and table G of the same SDK spec states how the SDK words them. A Meta 401, 402, or 403 on a relay call reaches the caller as Meta's own status and body (the first row).

### 9.3 Configuration and flags
| Variable / key | Required | Default | Purpose | Lives in |
|---|---|---|---|---|
| `META_API_KEY` | no | unset (a blank value counts as unset) | Vidbyte's own Meta Model API key, sent on Vidbyte-paid `meta` calls only | The backend service environment (Render, set by ops); loaded only by `AgenticMarketplaceCredentialsLoader.meta_api_key`; documented in the backend `.env.example` |

No new constant or flag. The markup (200 bps), the daily cap (10,000 cents), the header bounds, and the timeout are the existing `lib.config.model_gateway` values.

### 9.4 Migrations and compatibility
N/A — no stored data changes shape, and the change is purely additive. One previously refused value of an existing field is now accepted. No public contract changes: route, header, envelope, and error codes stay the same, and the platform contract is not regenerated. A client can observe two behavior changes:
1. `{"provider": "meta"}` with `muse-spark-1.1` now answers instead of returning 422.
2. For every managed generative provider, a Vidbyte-paid call while Vidbyte holds no key for that provider still answers 502 `model_gateway_upstream_failed`, but with the missing-key copy (§9.2) instead of "Retry after a short delay".

A client that keys on status and code sees no difference.
