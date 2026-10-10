# S1 scout report: pricing proof

Date: 2026-10-10. Output: `docs/spec/decision-model-providers/context/pricing-proof.md`. I made no commits and changed no source, test, lint, spec, or pipeline file. `git status` shows only my two new files, plus two untracked files that were already there: `S3-implementer.md` and the parallel scout's `provider-research-2.md`.

## What I read (repo)
- `vidbyte/lib/registries/pricing.py`: the header, `PRICING_AS_OF`, the OPENAI `gpt-6-luna` row, every decision block (TYPESAFE through MERAGPT), the empty OPENROUTER block, and `ModelPricingRegistry.resolve`.
- `vidbyte/lib/registries/models.py`: `DEFAULT_PROVIDER_MODELS`, `DECISION_DEFAULT_MODELS`, and `normalize_model`.
- `vidbyte/agents/pricing/base.py` (`effective_rates`: a None cache-read rate falls back to the input rate, and the threshold tier needs both over-threshold fields) and `vidbyte/agents/pricing/openrouter.py` (`usage.cost` wins, then table math).
- `lint/rules/c009_default_model_priced.py` (repair text) and `lint/pricebook_vintage_lock.json`. The lock is still at vintage 2026-07-30 and has no decision entries.
- `vidbyte/lib/constants/runners.py`: the `mercury-decide` alias.
- Docs, named parts only:
  - `context/pricing-recheck.md` (all of it).
  - `context/provider-research.md` §2, §3.1-3.9, §6, and §7.
  - `spec.md` §9.1, INV-18, FR-4, D-10, AC-12, D-16, and the §12.3 row 8 text.

## What I fetched (web, all on 2026-10-10)
Downloads went to the session scratchpad. I used `curl` for `.md`, `llms.txt` and JSON endpoints, `firecrawl scrape --max-age 0` for JS pages, and WebSearch only to find pages.

**Per provider:**
- **TypeSafe:** `docs.typesafe.ai/models.md`, `api.md`, and `llms.txt`. I probed `typesafe.ai/pricing` and `docs.typesafe.ai/pricing(.md)`; all returned 404.
- **Perplexity:** `docs.perplexity.ai` pricing, decisions-post, and the quickstart, all as `.md`. The old `/getting-started/pricing` URL now returns a 301 redirect to `/docs/getting-started/pricing`.
- **Cloudflare:** the Workers AI pricing page and the model pages for clef, clef-flash, and clef-omni, all through `index.md`.
- **Microsoft:**
  - Azure pricing pages: `ai-foundry-models/microsoft/` and `microsoft-foundry/`.
  - The Microsoft Learn page "models sold directly by Azure".
  - The Foundry catalog page, through firecrawl.
  - The techcommunity post, through firecrawl.
  - **The Azure Retail Prices API** (`prices.azure.com`, public and unauthenticated), queried two ways: `contains(meterName,'Decision')` and `productName eq 'Microsoft Decision Models'`.
- **OpenAI:** the `developers.openai.com` Decisions guide, the pricing page, and the gpt-6-luna model page, all as `.md`.
- **Liquid:**
  - `docs.liquid.ai/llms.txt`, plus the d1, decision-models, and guide pages as `.md`.
  - The blog post, through firecrawl.
  - `liquid.ai/pricing` and `console.liquid.ai/pricing`.
  - `api.liquid.ai/decisions/v1/models` (public JSON).
- **meraGPT:** `/docs/models`, `/models/decider-1`, `/docs/decider`, `/pricing`, and `GET /v1/models` (public JSON).
- **Inception:** `docs.inceptionlabs.ai` get-started/models, capabilities/decisions, and llms.txt. I probed `inceptionlabs.ai/pricing` (404) and `platform.inceptionlabs.ai/pricing` (429).
- **Baseten:** the pricing page and the Mercury Decide library page, both through firecrawl.
- **OpenRouter:**
  - Endpoint JSON for `typesafe/jev-1.13`, `liquid/d1`, and `inception/mercury-decide`.
  - Model and pricing HTML pages. These now load; the S0 scout got 404 for them.

**WebSearch:**
- "Microsoft-Decision-1 Foundry pricing [...]" (extended).
- "\"Microsoft-Decision-1\" learn.microsoft.com".
- "Liquid AI API pricing d1 [...]" (extended).
- "Inception Labs \"Mercury Decide\" pricing $0.02 50% off announcement".

## Pages that needed login or did not render
- **Needed login:**
  - `console.liquid.ai/pricing`: 403, redirects to sign-in.
  - Baseten `app.baseten.co/model-apis/...`: from the prior check, not refetched.
- **Did not render:**
  - The Foundry catalog `ai.azure.com/catalog/models/microsoft-decision-1` renders no price without sign-in.
  - `platform.inceptionlabs.ai/pricing` returned 429 (rate-limited).

## Results
- **All seven existing decision rows match their providers' documented API prices:** TypeSafe 0.042, Perplexity 0.02 ×2, Cloudflare 0.24 and 0.038, Foundry 0.042, OpenAI 0.10, Liquid 0.04, and meraGPT 0.04, all with output 0.
- **Baseten** gets a new row, `"inception/mercury-decide": 0.02 / 0.0`, from Inception's Models & Pricing page and Decisions page, with the comment the briefing asked for.
- **Foundry's source is upgraded** from the blog to Microsoft's Azure Retail Prices API. The meter "Microsoft Decision 1 1M Tokens" is $0.042 in all 37 regions, effective 2026-10-01, with no output meter. The Azure pricing web page does not list the model yet.
- **Liquid is the only weak source left.** Its best source is still the dated announcement footnote, because Liquid has no API pricing page and its docs state no rate.

## Surprising findings
1. **OpenAI long-context tier.** The Decisions guide says "long-context input pricing multipliers apply" to `/v1/decisions`. The model page says prompts over 272K input tokens cost 2x input. The `gpt-6-luna` row has no threshold, so it under-prices prompts over 272K (0.10 instead of the derived 0.20). `pricing-proof.md` §5 gives Option A (as is) and Option B (with the tier) for the spec author to choose.
2. **Inception's discount has no stated end date.** A search result says Inception's earlier Mercury 2.5 promo was due to end on 2026-09-08, yet Inception's docs still show that model discounted. So the Inception docs may not move promptly when a promo ends. The comment names the regular $0.04.
3. **Cloudflare clef-omni.** Cloudflare now lists `@cf/cloudflare/clef-omni` at $0.150 per M input, on its own route. The SDK does not support it (out of scope).
4. **Liquid's public model list.** `GET api.liquid.ai/decisions/v1/models` lists only `d1:free`. The `"d1"` key also prices `d1:free` at $0.04 by prefix. No page states a price for `d1:free`, so no row can be added for it.
5. **Out of scope (not a decision row).** On the OpenAI pricing page, `gpt-5.6-sol` Standard is `$4.00 | $0.40 | $5.00 | $20.00` short-context and `$8.00 | $0.80 | $10.00 | $30.00` long-context. The pricebook has 5.0 / 0.5 / 6.25 / 30.0 and 10.0 / 1.0 / 12.5 / 45.0. `gpt-5.6-terra` and `gpt-5.6-luna` match. Someone should re-check this outside this PR.
6. **Stale spec text.** The Baseten decision makes INV-18, FR-4, D-10, the §9.1 Baseten cell, §12.3 row 8, AC-12 (Baseten becomes `cost_usd == 0.02`), A-15, and Q-4 out of date. The list is in `pricing-proof.md` §11.
