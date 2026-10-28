# Model usage-integrity probes

## Folder Description / Intent

This folder probes model-token accounting with offline, provider-shaped responses. A malformed token count or non-finite marketplace price must not enter a complete usage ledger. Parsing and accounting live in `vidbyte/agents/pricing/`, not in these tests.

## File Index

- `README.md` describes the scope and test ownership.
- `FEATURE.md` defines valid counters, reported-cost fallback, and fail-closed outcomes.
- `test_usage_contract.py` records malformed and valid model calls through the real usage tracker.
- `test_billed_unusable_replies.py` checks that a billed 200 with no usable text stays on the bill, at the adapter and through an agent fallback.
- `test_nested_usage_bill.py` checks that a top-level agent's bill holds every sub-agent-tool and continual-trace call exactly once.
- `test_in_flight_failure_usage.py` checks that a call that fails with no HTTP status (a timeout) is counted as unmeasured spend, so a capped run fails closed.
- `test_actor_in_flight_failure_usage.py` checks that an actor-model call lost in flight (cancelled when another actor finishes the run, or timed out) counts as unmeasured spend, reaches a parent ledger, and that a billed unusable actor reply is recorded.
- `test_jev_versioned_answer_pricing.py` checks that a Jev decision answered by a release the pricebook lacks is priced as the requested model, and that unpriced requests still fail closed.
- `test_anthropic_price_modifiers.py` checks that an Anthropic call bills at the speed and inference geography its usage reports (fast mode, US-only 1.1x), and that a value the pricebook cannot price stays unpriced.
- `test_anthropic_web_search_pricing.py` checks that each server-side web search an Anthropic call reports bills $0.01 on top of its tokens.

## Logs

- 2026-10-07 - Negative OpenAI input tokens produced a negative, complete rollup; infinite OpenRouter reported cost also produced a complete non-finite rollup.
- 2026-10-12 - A billed Anthropic refusal followed by a Gemini fallback answer reported only the Gemini cost; the refusal is now recorded as a failed call.
- 2026-10-12 - A top-level agent dropped its sub-agent-tool and continual-trace calls from its bill; it now opens the usage ledger over its own tracker for every run.
- 2026-10-25 - TypeSafe began answering with `jev-1.14.0`, which the pricebook could not price, so every JevAgent run failed closed after its billed decision call; the pricebook gained `jev-1.14` and decision calls now fall back to the requested model's price.
- 2026-10-27 - Live Anthropic calls showed fast mode (`usage.speed` "fast") and US-only inference (`usage.inference_geo` "us") billed at standard rates; Opus 5.5 fast cost $0.000344 but the SDK billed $0.000172. Both modifiers are now priced from usage.
- 2026-10-27 - Anthropic's web search fee ($10 per 1,000 searches, `usage.server_tool_use.web_search_requests`) was never billed, so a DIRECT ledger and its spend cap missed $0.01 per search; it is now added to the call's cost.
- 2026-10-27 - A timed-out DIRECT call left the run marked fully measured, so a capped run kept spending; a status-less request failure now counts as an unaccounted call.
- 2026-10-28 - Live broadcast actor runs sent six billed requests but recorded one or two, fully "measured" (Haiku 4.5: $0.005383 billed, $0.000089 on the ledger); cancelled in-flight actor calls now count as unaccounted and the broker waits for them before the run returns.
