# Pricing proof: the provider's own API price and documentation link for every decision-model row

All pages were retrieved on **2026-10-10** against worktree HEAD `9cf997af` (branch `feat/decision-model-providers`). `.md` and JSON pages came from `curl` (no cache). JS-rendered pages came from `firecrawl scrape --max-age 0`. WebSearch was used only to find pages. Quotes are verbatim. `[...]` marks an elision. In a quoted Markdown table, `|` separates the cells, and `~~x~~` is a price the page shows struck through.

**What this file covers.** It covers every decision-model row in `vidbyte/lib/registries/pricing.py` on this branch (TYPESAFE, PERPLEXITY, CLOUDFLARE, FOUNDRY, LIQUID, MERAGPT, OPENAI `gpt-6-luna`) and the new BASETEN row priced at Inception's rate. It also covers the OpenRouter decision default (`typesafe/jev-1.13`), which has no row. New providers are out of scope.

**The rule applied** (user, 2026-10-10): each row equals the price the provider serves on its own API, and the comment above each row links the documentation that proves it. Source preference: (1) API pricing page, (2) API model docs or model card, (3) the provider's own dated announcement. Aggregator prices are marked third-party. They are not used as proof, except for the OPENROUTER provider itself.

**Result in one line.** Every existing row matches its provider's documented API price. Baseten gets a new row at 0.02 / 0.0, Inception's published price. Two rows have something to fix: OpenAI's documented long-context multiplier is not in its row (§5), and the Perplexity URL in the code now redirects (§2). Liquid is the only row whose best source is still an announcement, because Liquid has no public API pricing page (§6).

Each paste-ready block below replaces the existing comment and block in `pricing.py`. It keeps the repo's comment style: provider, model, check date, URL, quote. Only the Baseten block and the optional OpenAI change touch rate entries.

---

## 1. TypeSafe: `jev-1.13`, `jev-latest`, `jev-preview` (code: 0.042 / 0.0)

**Best source (2: API model docs).** TypeSafe has no pricing page: `https://typesafe.ai/pricing`, `https://docs.typesafe.ai/pricing` and `https://docs.typesafe.ai/pricing.md` all return 404. The models page in its API docs is where TypeSafe states the price.
- https://docs.typesafe.ai/models.md, under "Current models", in the `jev-1.13.0` table: `| Price (per Btok / per Mtok) | \$42 / \$0.042 |`, and: "**Price:** Charged per input token. Output tokens are free. A Btok is a billion tokens and an Mtok is a million tokens."
- Aliases (same page): "`jev-latest` | `jev-1.13.0`" and "`jev-preview` | `jev-1.13.0`". The page also says "The response's `model` field reports the versioned ID that answered".
- https://docs.typesafe.ai/api.md#response-body: the usage block is `"usage": { "input_tokens": 296, "output_tokens": 20 }`. No cached-token field.

**Rate:** $0.042 per 1M input, $0 per 1M output. **Verdict: MATCH** (0.042 / 0.0, all three keys). Only the comment changes: its "checked 2026-09-21" date moves to 2026-10-10.

```python
    # TypeSafe Jev 1.13 (System One decision model), re-checked 2026-10-10 against TypeSafe's API
    # model docs https://docs.typesafe.ai/models.md (TypeSafe has no separate pricing page):
    # "Price (per Btok / per Mtok) | $42 / $0.042" and "Charged per input token. Output tokens are
    # free." The API reports only input_tokens and output_tokens
    # (https://docs.typesafe.ai/api.md#response-body) and publishes no cached-token rate, so no
    # cache_read rate applies. Responses name the versioned model that answered (jev-1.13.0), which
    # the "jev-1.13" prefix prices; the jev-latest and jev-preview aliases both point to it.
    ModelProvider.TYPESAFE: {
        "jev-1.13": ModelPricing(input_per_million=0.042, output_per_million=0.0),
        "jev-latest": ModelPricing(input_per_million=0.042, output_per_million=0.0),
        "jev-preview": ModelPricing(input_per_million=0.042, output_per_million=0.0),
    },
```

---

## 2. Perplexity: `pplx-decider-v1.1-27b`, `pplx-decider-v1-27b` (code: 0.02 / 0.0)

**Best source (1: API pricing page).**
- https://docs.perplexity.ai/docs/getting-started/pricing, section "## Decisions API Pricing":
  `| Model | Price (\$/1M input tokens) | Output tokens | Per-request fee |`
  `| `pplx-decider-v1.1-27b` | \$0.02 | Free | None |`
  `| `pplx-decider-v1-27b` | \$0.02 | Free | None |`
  It also says: "**Billing unit:** you pay for input tokens only. [...] A request with 600 input tokens costs \$0.000012." The page's calculator data agrees: `"decisions": { [...] "input": 0.02 }` with unit "$ per 1,000,000 input tokens (output tokens are free; no per-request fee)".
- **The URL has moved.** The code cites `https://docs.perplexity.ai/getting-started/pricing`, which now returns a 301 redirect to `/docs/getting-started/pricing`. The comment should cite the canonical URL.
- API reference https://docs.perplexity.ai/api-reference/decisions-post: "Input tokens are billed at $0.02 per million; output tokens are free."
- Quickstart https://docs.perplexity.ai/docs/decisions/quickstart, "## Pricing": "The Decisions API costs \$0.02 per million input tokens. Output tokens are free, and there is no per-request fee."

**Rate:** $0.02 per 1M input, $0 output, for both models. **Verdict: MATCH.** Only the comment URL changes.

```python
    # Perplexity Decisions API (System One wire), checked 2026-10-10 against the API pricing page
    # https://docs.perplexity.ai/docs/getting-started/pricing ("Decisions API Pricing", columns
    # $/1M input tokens | output tokens | per-request fee: "pplx-decider-v1.1-27b | $0.02 | Free |
    # None" and "pplx-decider-v1-27b | $0.02 | Free | None") and the API reference
    # https://docs.perplexity.ai/api-reference/decisions-post ("Input tokens are billed at $0.02 per
    # million; output tokens are free").
    ModelProvider.PERPLEXITY: {
        "pplx-decider-v1.1-27b": ModelPricing(input_per_million=0.02, output_per_million=0.0),
        "pplx-decider-v1-27b": ModelPricing(input_per_million=0.02, output_per_million=0.0),
    },
```

---

## 3. Cloudflare: `clef` (code: 0.24 / 0.0), `clef-flash` (code: 0.038 / 0.0)

**Best source (1: API pricing page)**, "Last updated Oct 9, 2026".
- https://developers.cloudflare.com/workers-ai/platform/pricing/, table "Other model pricing" (`| Model | Price in Tokens | Price in Neurons |`):
  `| @cf/cloudflare/clef | $0.240 per M input tokens | 21818 neurons per M input tokens |`
  `| @cf/cloudflare/clef-flash | $0.038 per M input tokens | 3455 neurons per M input tokens |`
  The same page says: "Workers AI [...] is priced at **$0.011 per 1,000 Neurons**". So 21818 × 0.011 / 1000 = $0.240 and 3455 × 0.011 / 1000 = $0.038. The token price and the neuron price are the same charge.
- Model cards: https://developers.cloudflare.com/workers-ai/models/clef/ shows "Unit Pricing | $0.24 per M input tokens" and says "Clef models do not charge for output tokens." https://developers.cloudflare.com/workers-ai/models/clef-flash/ shows "Unit Pricing | $0.038 per M input tokens".

**Rates:** clef $0.240, clef-flash $0.038 per 1M input, $0 output. **Verdict: MATCH, both rows.**

(Not in scope, for the spec author: the same table also lists `@cf/cloudflare/clef-omni | $0.150 per M input tokens`. It is a separate model with its own route, `@cf/cloudflare/clef-omni`, and the SDK does not support it.)

```python
    # Cloudflare Workers AI Clef decision models, checked 2026-10-10 against the Workers AI pricing
    # page https://developers.cloudflare.com/workers-ai/platform/pricing/ ("@cf/cloudflare/clef |
    # $0.240 per M input tokens" and "@cf/cloudflare/clef-flash | $0.038 per M input tokens") and the
    # model page https://developers.cloudflare.com/workers-ai/models/clef/ ("Clef models do not
    # charge for output tokens"). Workers AI bills these as neurons (21818 and 3455 per M input
    # tokens at $0.011 per 1,000 neurons), which is the same charge as the token price.
    ModelProvider.CLOUDFLARE: {
        "clef": ModelPricing(input_per_million=0.24, output_per_million=0.0),
        "clef-flash": ModelPricing(input_per_million=0.038, output_per_million=0.0),
    },
```

---

## 4. Microsoft Foundry: `microsoft-decision-1` (code: 0.042 / 0.0)

**Best source: Microsoft's own price list (the Azure Retail Prices API).** This replaces the blog as the primary proof.
- The Azure pricing **web page** for Foundry Models sold by Microsoft (https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/microsoft/, "MAI" tab) lists MAI-* and Phi-* models only. It has **no Microsoft-Decision-1 row** on 2026-10-10. The Microsoft Learn catalog page (https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure, updated 2026-10-08) describes the model but gives no price. The Foundry catalog (https://ai.azure.com/catalog/models/microsoft-decision-1) renders no price without sign-in.
- **Azure Retail Prices API** is Microsoft's public, unauthenticated price list for Azure meters, documented at https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices.
  Query: `https://prices.azure.com/api/retail/prices?$filter=productName%20eq%20%27Microsoft%20Decision%20Models%27` returns `"Count": 37`. Every item has `"meterName":"Microsoft Decision 1 1M Tokens"`, `"productName":"Microsoft Decision Models"`, `"skuName":"Microsoft Decision 1"`, `"serviceName":"Foundry Models"`, `"retailPrice":0.042`, `"unitOfMeasure":"1M"`, `"type":"Consumption"`, `"effectiveStartDate":"2026-10-01T00:00:00Z"`. There is one price in all 37 regions and no separate output meter.
- **Microsoft's own announcement**, kept as the human-readable table: https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/introducing-microsoft-decision-1-in-microsoft-foundry-for-decision-and-classific/4562742, section "**Pricing**":
  `| **Model** | **Deployment Type** | **Input Tokens (#/1M)** | **Output tokens (#/1M)** |`
  `| Microsoft-Decision-1 | US Datazone | $0.042 | N/A |`
  `| EU Datazone | $0.042 | N/A |`
  The post also says: "Now available in public preview".

**Rate:** $0.042 per 1M input. Output is not metered ("N/A"; no output meter). **Verdict: MATCH.** Only the comment source changes.

```python
    # Microsoft-Decision-1 on Microsoft Foundry, checked 2026-10-10 against Microsoft's Azure Retail
    # Prices API (https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices):
    # https://prices.azure.com/api/retail/prices?$filter=productName%20eq%20%27Microsoft%20Decision%20Models%27
    # returns one meter, "Microsoft Decision 1 1M Tokens", at retailPrice 0.042 USD per "1M" in all
    # 37 regions (effective 2026-10-01), with no output meter; Microsoft's announcement
    # https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/introducing-microsoft-decision-1-in-microsoft-foundry-for-decision-and-classific/4562742
    # lists "Input Tokens (#/1M) $0.042 | Output tokens (#/1M) N/A" for the US and EU Datazones. The
    # request `model` is the caller's deployment name, so this row prices only a deployment named
    # microsoft-decision-1.
    ModelProvider.FOUNDRY: {
        "microsoft-decision-1": ModelPricing(input_per_million=0.042, output_per_million=0.0),
    },
```

---

## 5. OpenAI: `gpt-6-luna` on `/v1/decisions` (code: 0.10 / 0.0, no threshold)

**Best source (2: API docs).** The general API pricing page has no Decisions section ("decision" appears 0 times on https://developers.openai.com/api/docs/pricing.md). The rate is on the Decisions guide.
- https://developers.openai.com/api/docs/guides/decisions, "## Pricing and availability":
  > "With `gpt-6-luna`, input costs **$0.10 per 1M tokens**. You pay only for input tokens: there are no cache-read, cache-write, or output-token charges."
  >
  > "Regional processing premiums and long-context input pricing multipliers apply. These rates apply to `/v1/decisions`; other requests using `gpt-6-luna` follow the applicable [model and processing-tier pricing](https://developers.openai.com/api/docs/pricing)."
- The gpt-6-luna model page https://developers.openai.com/api/docs/models/gpt-6-luna gives the multipliers in general terms: "Prompts with more than 272K input tokens are priced at 2x input and cache rates and 1.5x output for the full request." and "Regional processing adds a 10% premium where available."
- For contrast, the chat rate on the pricing page is `| gpt-6-luna | $0.10 | $0.01 | $0.125 | $0.50 | $0.20 | $0.02 | $0.25 | $0.75 |`: short and long context for input, cached input, cache writes and output. This is **not** the Decisions rate. The guide says other requests follow it.

**Rate:** $0.10 per 1M input, $0 output, for prompts up to 272K input tokens. **Verdict: MATCH on the base rate.** There is **one gap**: the guide says long-context multipliers apply to `/v1/decisions`, and the documented multiplier is 2x input above 272K input tokens. The current row has no threshold, so a prompt over 272K is priced at $0.10 where OpenAI charges $0.20. The $0.20 is derived: 2x the Decisions rate. No page prints "$0.20" for Decisions. Model context: 922,000 max input, from the research §3.1.

Two notes for the spec author:
- **Cache read.** Keep `cache_read_per_million` unset (None). With None, `ProviderUsage.effective_rates` bills any cached input at the input rate (`vidbyte/agents/pricing/base.py`). That fits "You pay only for input tokens". Setting it to 0.0 would make cached input free. The current comment's paraphrase "cache read [...] are $0" could be misread as 0.0, so the paste-ready comment quotes the guide word for word.
- **Regional premium.** The 10% regional premium is not modeled for any OpenAI row in the pricebook. Leave it out here too.

Option A, which keeps today's row (base rate only):
```python
        # gpt-6-luna through the Decisions API (/v1/decisions), checked 2026-10-10 against the
        # Decisions guide https://developers.openai.com/api/docs/guides/decisions ("With `gpt-6-luna`,
        # input costs $0.10 per 1M tokens. You pay only for input tokens: there are no cache-read,
        # cache-write, or output-token charges." and "These rates apply to `/v1/decisions`"); the API
        # pricing page lists only gpt-6-luna's chat rate ($0.10 in / $0.50 out), not this one. The
        # model is reached only through the decisions adapter (it is not in the text runner catalog),
        # so the decision rate is the one this row carries (spec decision D-12).
        "gpt-6-luna": ModelPricing(input_per_million=0.10, output_per_million=0.0),
```

Option B, which adds the long-context tier the guide says applies (the spec author decides):
```python
        # gpt-6-luna through the Decisions API (/v1/decisions), checked 2026-10-10 against the
        # Decisions guide https://developers.openai.com/api/docs/guides/decisions ("With `gpt-6-luna`,
        # input costs $0.10 per 1M tokens. You pay only for input tokens: there are no cache-read,
        # cache-write, or output-token charges." and "Regional processing premiums and long-context
        # input pricing multipliers apply. These rates apply to `/v1/decisions`"). The multiplier is
        # on the model page https://developers.openai.com/api/docs/models/gpt-6-luna: "Prompts with
        # more than 272K input tokens are priced at 2x input [...] for the full request", so input
        # over 272K is 0.20. The model is reached only through the decisions adapter (it is not in
        # the text runner catalog), so the decision rate is the one this row carries (spec D-12).
        "gpt-6-luna": ModelPricing(input_per_million=0.10, output_per_million=0.0, threshold_tokens=272_000, input_over_threshold_per_million=0.20, output_over_threshold_per_million=0.0),
```
Option B uses the same strict `>` 272K boundary as the other OpenAI rows (`threshold_inclusive=False` is the default). `effective_rates` switches tiers only when both over-threshold fields are set, which is why the row also sets `output_over_threshold_per_million=0.0`.

---

## 6. Liquid AI: `d1` (code: 0.04 / 0.0)

**Best source (3: the provider's own dated announcement). Liquid has no API pricing page and no rate in its API docs.** Checked on 2026-10-10:
- https://www.liquid.ai/pricing covers open-weight licensing only. Its only API mention is a "Try our API" link to console.liquid.ai.
- https://console.liquid.ai/pricing redirects (403) to `https://accounts.console.liquid.ai/sign-in?...`. **It needs a login.**
- https://docs.liquid.ai/llms.txt is the full docs index. It has no pricing or billing page. `https://docs.liquid.ai/pricing` and `/lfm/help/pricing` return 404.
- https://docs.liquid.ai/lfm/models/d1 gives no rate. It says image tokens are "charged at the model's input token rate", "`usage.output_tokens`: Always `0`", and "Vision is available through the Liquid API with the paid `d1` model. `d1:free` is text-only."
- `GET https://api.liquid.ai/decisions/v1/models` (public, no auth) returns `{"models":[{"name":"d1:free","description":"","release_date":"2026-09-22","input_modalities":["text"]}]}`. It has no price field, and it lists only `d1:free`.
- **The rate:** https://www.liquid.ai/blog/d1-decision-model, dated "OCT 5, 2026". Methodology footnote: "Costs use list prices, without prompt-cache discounts. d1's costs use $0.04 per million input tokens." Section "Availability and pricing": "available on the [Liquid AI API](http://console.liquid.ai/) as `d1`" and "d1 is billed on input tokens only, with no output tokens."

**Rate:** $0.04 per 1M input, $0 output. **Verdict: MATCH.** The source is still an announcement, because no stronger first-party page exists. Third-party figures agree (§10).

**Open point (not a mismatch):** the `"d1"` key also prices `d1:free` at $0.04 by longest prefix. No Liquid page states a price for `d1:free`; the name suggests it is free. INV-18 does not allow a guessed `"d1:free"` row at 0.0, so the row stays as it is.

```python
    # Liquid AI d1 (System One wire), retrieved 2026-10-10. Liquid publishes no API pricing page
    # (https://www.liquid.ai/pricing covers open-weight licensing only, https://console.liquid.ai/pricing
    # needs a login, and https://docs.liquid.ai/lfm/models/d1 states no rate), so the first-party
    # source is the methodology footnote of Liquid's own d1 announcement, dated 2026-10-05
    # (https://www.liquid.ai/blog/d1-decision-model): "d1's costs use $0.04 per million input
    # tokens"; its "Availability and pricing" section adds "d1 is billed on input tokens only, with no
    # output tokens". Output tokens are always 0 (https://docs.liquid.ai/lfm/models/d1). The
    # longest-prefix match also prices an explicit `d1:free` here.
    ModelProvider.LIQUID: {
        "d1": ModelPricing(input_per_million=0.04, output_per_million=0.0),
    },
```

---

## 7. meraGPT: `sd-1` (code: 0.04 / 0.0)

**Best source (1 and 2: a models-and-pricing table plus a model card, plus a public JSON catalogue).**
- https://meragpt.com/docs/models: `model | alias | context | input | output | status` / `decider-1 | sd-1 | 4,096 | $0.04 / 1M | $0.00 / 1M | Available`. Under "Short aliases": "Every model also answers to a short alias — `sd-1` for Decider 1 [...]".
- https://meragpt.com/models/decider-1: "model decider-1 alias sd-1 context 4,096 tokens [...] input price $0.04 / 1M tokens output price $0.00 / 1M tokens".
- https://meragpt.com/#pricing (`/pricing` serves the same page), under "What it costs": `model input output status` / `Decider 1 decider-1 $0.04 / 1M $0.00 / 1M Available`.
- `GET https://meragpt.com/v1/models` (public, no auth): `"id":"decider-1" [...] "pricing":{"input_usd_per_million_tokens":0.04,"output_usd_per_million_tokens":0},"openrouter_id":"meragpt/state-decider-1","aliases":["sd-1","state-decider-1"]`.
- https://meragpt.com/docs/decider: "output is never billed. Input costs $0.04 / 1M tokens."

**Rate:** $0.04 per 1M input, $0 output. **Verdict: MATCH.**

```python
    # meraGPT Decider 1 (System One wire), retrieved 2026-10-10 from the models and pricing table
    # https://meragpt.com/docs/models ("decider-1 | sd-1 | 4,096 | $0.04 / 1M | $0.00 / 1M |
    # Available"), the model card https://meragpt.com/models/decider-1 ("input price $0.04 / 1M
    # tokens", "output price $0.00 / 1M tokens"), https://meragpt.com/#pricing, and the public
    # catalogue https://meragpt.com/v1/models ("input_usd_per_million_tokens":0.04,
    # "output_usd_per_million_tokens":0, "aliases":["sd-1","state-decider-1"]). sd-1 is the
    # documented alias of decider-1 and is the id the SDK sends and records.
    ModelProvider.MERAGPT: {
        "sd-1": ModelPricing(input_per_million=0.04, output_per_million=0.0),
    },
```

---

## 8. Baseten: `inception/mercury-decide` (code: empty block → new row 0.02 / 0.0)

**Baseten, the company that bills this route, publishes no price for it.**
- https://www.baseten.co/pricing/: the Model APIs table (`Input | Cache Input | Output` per 1M) covers GLM-5.3-Fast, GLM-5.3, GLM-5.3-Flash, GLM-5.2, GLM-5.2-Fast, DeepSeek-V4-Flash-0731, DeepSeek-V4.1-Flash, deepseek-v4-pro-0813, Kimi-K3, NVIDIA-Nemotron-3-Ultra, gpt-oss-120b, and Whisper. **No Mercury Decide row.**
- https://www.baseten.co/library/mercury-decide/ states no price. Prior check: `https://app.baseten.co/model-apis/inception/mercury-decide` needs sign-in, and the management API's `cost_per_million_input_tokens` needs an API key (`pricing-recheck.md` §2.2).

**The source the user chose: Inception's published price for Mercury Decide on Inception's own API.**
- https://docs.inceptionlabs.ai/get-started/models is Inception's "Models & Pricing" page ("Compare models, capabilities, and pricing"). Its banner reads "50% off Mercury Decide". Table header: `| Model | Input Price (1M Tokens) | Cached Input Price (1M Tokens) | Output Price (1M Tokens) | Supported Endpoints | [...]`. Row: `| **Mercury Decide** | ~~\$0.04~~ → **\$0.02** | \$0 | \$0 | `v1/decisions` | — | — | `Classification`<br />`Scoring` | `Text / JSON` |`.
- https://docs.inceptionlabs.ai/capabilities/decisions, "## Pricing and limits": "Mercury Decide costs **$0.02 per million input tokens** (50% off the regular $0.04 price). Only input tokens are billed; output tokens are reported in `usage.output_tokens` but are not charged."
- Both pages describe Inception's own endpoint (`https://api.inceptionlabs.ai/v1/decisions`, model id `mercury-decide`). Neither gives an **end date for the discount**. The two Inception pages agree, so nothing conflicts. The current rate is $0.02 and the regular rate is $0.04.
- Cached input is $0 per the table. This does not matter here, because Baseten responses are parsed by `JevUsage` (`{input_tokens, output_tokens}`), which has no cached-token field.

**Rate (Inception's API):** $0.02 per 1M input, $0 output. **Verdict: NEW ROW at 0.02 / 0.0.** Key: exactly `inception/mercury-decide`. That key satisfies C009, while a bare `mercury-decide` key would not (`pricing-recheck.md` §1.1). The runner catalog's bare `mercury-decide` alias (D-16) exists only for strict-validation `_catalog_name` and is not a wire id, so it needs no row.

```python
    # Baseten Mercury Decide (inception/mercury-decide). Baseten publishes no price for this model:
    # its Model APIs pricing page https://www.baseten.co/pricing/ has no Mercury Decide row and the
    # model page https://www.baseten.co/library/mercury-decide/ states none (both checked
    # 2026-10-10). By the user's decision (2026-10-10), this row uses Inception's published price for
    # Mercury Decide on Inception's own API, retrieved 2026-10-10 from
    # https://docs.inceptionlabs.ai/get-started/models ("Mercury Decide | ~~$0.04~~ → $0.02 | $0 |
    # $0 | v1/decisions", columns input / cached input / output per 1M tokens) and
    # https://docs.inceptionlabs.ai/capabilities/decisions ("Mercury Decide costs $0.02 per million
    # input tokens (50% off the regular $0.04 price). Only input tokens are billed"). Inception states
    # no end date for the discount (the regular price is $0.04), and Baseten may bill its route at a
    # different rate.
    ModelProvider.BASETEN: {
        "inception/mercury-decide": ModelPricing(input_per_million=0.02, output_per_million=0.0),
    },
```

---

## 9. OpenRouter: decision default `typesafe/jev-1.13` (code: `ModelProvider.OPENROUTER: {}`, no row)

**Is there a row?** No. `PROVIDER_PRICING[ModelProvider.OPENROUTER]` is empty on purpose. `OpenRouterUsage.cost_usd` returns OpenRouter's `usage.cost` when present (`vidbyte/agents/pricing/openrouter.py:74-78`) and falls back to table math otherwise, and the table here is empty, so the fallback gives None. Lint C009 lists OPENROUTER in `_PRICED_PER_RESPONSE`, so the empty block is legal.

**OpenRouter's own price.** OpenRouter is the billing provider for this route, so this is first-party for the OPENROUTER provider.
- https://openrouter.ai/typesafe/jev-1.13/pricing (title "Jev 1.13 - API Pricing & Providers | OpenRouter"): "$0.042 per million input tokens, $0 per million output tokens."
- `GET https://openrouter.ai/api/v1/models/typesafe/jev-1.13/endpoints` (public JSON): one endpoint, provider "TypeSafe", `typesafe/jev-1.13-20260917`, `"pricing":{"prompt":"0.000000042","completion":"0","discount":0}`, `context_length` 64000.

**Verdict:** there is no row to match. OpenRouter's price ($0.042 / $0) equals TypeSafe's own rate. **Recommendation: keep the block empty.** Adding a row would go against the C009 rationale ("PROVIDER_PRICING keeps ModelProvider.OPENROUTER empty on purpose"). It would only take effect when OpenRouter omits `usage.cost`. An optional comment-only addition:

```python
    # OpenRouter models are priced per-generation by the marketplace; the SDK
    # prefers the provider-reported usage.cost over table math for this provider.
    # For reference, the decision default typesafe/jev-1.13 is listed at "$0.042 per million input
    # tokens, $0 per million output tokens" on https://openrouter.ai/typesafe/jev-1.13/pricing
    # (retrieved 2026-10-10); no row is kept because usage.cost is authoritative (lint C009 declares
    # OPENROUTER priced per response).
    ModelProvider.OPENROUTER: {},
```

---

## 10. Third-party figures (context only; none is used as proof)

| Model | Third-party source | Route it prices | Figure (verbatim) |
|---|---|---|---|
| Liquid d1 | https://openrouter.ai/api/v1/models/liquid/d1/endpoints | OpenRouter → provider "Liquid", `liquid/d1-20260930` | `"pricing":{"prompt":"0.00000004","completion":"0","input_cache_read":"0.00000004","discount":0}` = $0.04 / $0 |
| Liquid d1 | https://openrouter.ai/liquid/d1 | OpenRouter | "$0.04 per million input tokens, $0 per million output tokens" |
| Mercury Decide | https://openrouter.ai/api/v1/models/inception/mercury-decide/endpoints | OpenRouter → provider **Inception** (not Baseten), `inception/mercury-decide-20260930` | `"pricing":{"prompt":"0.00000002","completion":"0","input_cache_read":"0","discount":0.5}` = $0.02 (50% discount) / $0 |
| Mercury Decide | https://openrouter.ai/inception/mercury-decide | OpenRouter | "$0.02 per million input tokens, $0 per million output tokens" |
| Microsoft-Decision-1 | WebSearch results (fourweekmba.com, cellcog.ai, windowsforum.com, others) | press coverage | "$0.042 per million input tokens"; windowsforum says it could not find the rate on an official Foundry pricing page. The Retail Prices API (§4) now settles this. |

No third-party source prices Mercury Decide on **Baseten's** route.

---

## 11. Notes for the spec author and implementer

- **Vintage and lock.** `PRICING_AS_OF` is already `"2026-10-10"`, and every row above was checked on that date, so the vintage does not move. `lint/pricebook_vintage_lock.json` is still locked at `2026-07-30`: it contains no `gpt-6-luna`, PERPLEXITY, LIQUID, MERAGPT or BASETEN entries. Add the Baseten row (and the Option B gpt-6-luna change, if chosen) **before** the single `python -m lint.rules.c010_pricebook_vintage_bump --refresh-lock` (§12.5). Comment-only edits do not affect C010's digests.
- **C009.** With `"inception/mercury-decide"` priced, the BASETEN finding clears. The `MISTRAL` finding stays baselined (`"C009": 1`).
- **Spec text that the Baseten decision makes stale:** INV-18 (Baseten "the one remaining unpriced default"), FR-4 ("an empty block [...] for Baseten only"), D-10 (the rejected alternative is "Inception's own-API $0.02 for Baseten's route"), the §9.1 BASETEN pricing cell, §12.3 row 8 (the Baseten comment text), AC-12 (Baseten → `cost_usd is None`), A-15, and Q-4. AC-12's Baseten expectation becomes `cost_usd == 0.02` for 1,000,000 input tokens.
- **§9.1 pricing cells to refresh:** Perplexity URL → `/docs/getting-started/pricing`. Foundry → add the Retail Prices API URL beside the blog. Baseten → 0.02 / 0.0 with the two Inception URLs. Cloudflare → optionally add the model-card URL.

## 12. Summary

| Provider | Key | Value in code (in / out per 1M) | Documented value (in / out per 1M) | Best URL | Match |
|---|---|---|---|---|---|
| TypeSafe | `jev-1.13`, `jev-latest`, `jev-preview` | 0.042 / 0.0 | 0.042 / 0 | https://docs.typesafe.ai/models.md | MATCH |
| Perplexity | `pplx-decider-v1.1-27b` | 0.02 / 0.0 | 0.02 / 0 (free) | https://docs.perplexity.ai/docs/getting-started/pricing | MATCH (URL in code redirects; update) |
| Perplexity | `pplx-decider-v1-27b` | 0.02 / 0.0 | 0.02 / 0 (free) | https://docs.perplexity.ai/docs/getting-started/pricing | MATCH |
| Cloudflare | `clef` | 0.24 / 0.0 | 0.240 / 0 | https://developers.cloudflare.com/workers-ai/platform/pricing/ | MATCH |
| Cloudflare | `clef-flash` | 0.038 / 0.0 | 0.038 / 0 | https://developers.cloudflare.com/workers-ai/platform/pricing/ | MATCH |
| Microsoft Foundry | `microsoft-decision-1` | 0.042 / 0.0 | 0.042 / N/A (no output meter) | https://prices.azure.com/api/retail/prices?$filter=productName%20eq%20%27Microsoft%20Decision%20Models%27 (+ techcommunity post) | MATCH (source upgraded from blog) |
| OpenAI | `gpt-6-luna` (decisions) | 0.10 / 0.0, no threshold | 0.10 / 0; long-context multiplier applies (2x input above 272K → 0.20, derived) | https://developers.openai.com/api/docs/guides/decisions | MATCH on base rate; long-context tier missing (Option B) |
| Liquid AI | `d1` | 0.04 / 0.0 | 0.04 / 0 | https://www.liquid.ai/blog/d1-decision-model (announcement; no pricing page exists) | MATCH (weak source class) |
| meraGPT | `sd-1` | 0.04 / 0.0 | 0.04 / 0.00 | https://meragpt.com/docs/models | MATCH |
| Baseten (Inception rate) | `inception/mercury-decide` | none (empty block) | 0.02 / 0 (Inception API; regular 0.04, no end date) | https://docs.inceptionlabs.ai/get-started/models | NEW ROW 0.02 / 0.0 |
| OpenRouter | `typesafe/jev-1.13` (decision default) | no row (empty block by design) | 0.042 / 0 (OpenRouter's own price) | https://openrouter.ai/typesafe/jev-1.13/pricing | n/a: keep empty; `usage.cost` wins |
