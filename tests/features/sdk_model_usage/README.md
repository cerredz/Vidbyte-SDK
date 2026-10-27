# Model usage-integrity probes

## Folder Description / Intent

This folder probes model-token accounting with offline, provider-shaped responses. A malformed token count or non-finite marketplace price must not enter a complete usage ledger. Parsing and accounting live in `vidbyte/agents/pricing/`, not in these tests.

## File Index

- `README.md` describes the scope and test ownership.
- `FEATURE.md` defines valid counters, reported-cost fallback, and fail-closed outcomes.
- `test_usage_contract.py` records malformed and valid model calls through the real usage tracker.
- `test_billed_unusable_replies.py` checks that a billed 200 with no usable text stays on the bill, at the adapter and through an agent fallback.
- `test_nested_usage_bill.py` checks that a top-level agent's bill holds every sub-agent-tool and continual-trace call exactly once.
- `test_jev_versioned_answer_pricing.py` checks that a Jev decision answered by a release the pricebook lacks is priced as the requested model, and that unpriced requests still fail closed.
- `test_anthropic_price_modifiers.py` checks that an Anthropic call bills at the speed and inference geography its usage reports (fast mode, US-only 1.1x), and that a value the pricebook cannot price stays unpriced.

## Logs

- 2026-10-07 - Negative OpenAI input tokens produced a negative, complete rollup; infinite OpenRouter reported cost also produced a complete non-finite rollup.
- 2026-10-12 - A billed Anthropic refusal followed by a Gemini fallback answer reported only the Gemini cost; the refusal is now recorded as a failed call.
- 2026-10-12 - A top-level agent dropped its sub-agent-tool and continual-trace calls from its bill; it now opens the usage ledger over its own tracker for every run.
- 2026-10-25 - TypeSafe began answering with `jev-1.14.0`, which the pricebook could not price, so every JevAgent run failed closed after its billed decision call; the pricebook gained `jev-1.14` and decision calls now fall back to the requested model's price.
- 2026-10-27 - Live Anthropic calls showed fast mode (`usage.speed` "fast") and US-only inference (`usage.inference_geo` "us") billed at standard rates; Opus 5.5 fast cost $0.000344 but the SDK billed $0.000172. Both modifiers are now priced from usage.
