# Pricing re-check: C009/C010 and first-party prices for Liquid, Baseten, meraGPT

Read on 2026-10-10 against worktree HEAD `7bfe29e8` (the lint, registry, and pricebook files are unchanged at `9e0d04e9`, which only edits `pipeline.md`). Pages were fetched on 2026-10-10 with `firecrawl scrape --max-age 0` (fresh, no cache), `curl` for `.md`/JSON endpoints, and WebSearch for discovery. Quotes are verbatim; `[...]` marks an elision.

## 1. Lint rules

### 1.1 C009 `default-model-priced` (`lint/rules/c009_default_model_priced.py`)

**Origin and intent.** C009 came in with `4f57d8ed feat(lint): SDK pricing and usage contract rules C009-C012 (#587)` (2026-10-10 14:13 -0400). This is the only `origin/main` commit that touches the file. The sub-commit message says:

> "Every provider whose default model is billed from token rates (text and decision runner types) must resolve that default in PROVIDER_PRICING, using the same exact, alias-normalized and longest-prefix lookup as ModelPricingRegistry.resolve. OpenRouter is declared priced per response because it reports usage.cost. The rule reads source only and fails closed when a contract file or literal is missing.
>
> Baseline 1: ModelProvider.MISTRAL's default mistral-medium-latest has no pricebook block. The repair's vintage step names C010's refresh command, which the next commit adds."

**Scope: which providers and models it checks.**
- It reads only `ProviderModelRegistry.DEFAULT_PROVIDER_MODELS` (`:187`). It never reads `DECISION_DEFAULT_MODELS`. So a decision default is checked only because the same id sits in `DEFAULT_PROVIDER_MODELS` (`models.py:78-80`: `LIQUID: "d1"`, `BASETEN: "inception/mercury-decide"`, `MERAGPT: "sd-1"`).
- The runner types in scope come from `:27`: `_TOKEN_PRICED_RUNNER_CONSTANTS = ("RUNNER_TYPE_TEXT", "RUNNER_TYPE_DECISION")`.
- Each default's runner type is looked up per model first, then per provider (`:252`): `runner_type = qualified.get(f"{members[member]}/{model.lower()}") or by_provider.get(members[member], "")`. All three new defaults resolve to decision: `vidbyte/lib/constants/runners.py:177-179` maps `"liquid/d1"`, `"baseten/inception/mercury-decide"` and `"meragpt/sd-1"` to `RUNNER_TYPE_DECISION`, and `:355-357` maps the providers.
- Audio, image, video, and embedding defaults are out of scope (`:9`).

**The condition a default must meet** (`:200-204`):
```python
# Keep the defaults that are token-priced, not declared priced-per-response, and that resolve to no rate.
for default in defaults:
    if default.member in _PRICED_PER_RESPONSE or lookup.resolves(default.member, default.model):
        continue
```
`PricingLookup.resolves` (`:157-168`) is stated to mirror `ModelPricingRegistry.resolve`:
```python
keys = self.table.get(member, ())
requested = model.strip()
if not requested:
    return False
if requested in keys:
    return True
canonical = self._normalize(member, requested)
if canonical in keys:
    return True
return any(canonical.startswith(key) for key in keys)
```
`_normalize` (`:170-174`) strips only a `"<provider value>/"` prefix, and only to look up an alias in `MODEL_ALIASES`. When no alias matches it returns the raw name. This is the same logic as `ProviderModelRegistry.normalize_model` (`models.py:251-259`) and `ModelPricingRegistry.resolve` (`pricing.py:221-239` on the merged tree; the briefing's `:184-200` is pre-merge). The only aliases on HEAD are OpenAI's (`models.py:143-145`).

What would satisfy C009, key by key:
- **Liquid `d1`.** An exact key `"d1"`. A shorter key that is a prefix of `d1` would also match.
- **Baseten `inception/mercury-decide`.** The `baseten/` strip does not apply and BASETEN has no alias. So it takes the exact key `"inception/mercury-decide"`, or a key that is a prefix of it (`"inception/"`, `"inception/mercury"`). The bare key `"mercury-decide"` would **not** satisfy it, because it is not a prefix of `inception/mercury-decide`.
- **meraGPT `sd-1`.** An exact key `"sd-1"`. A `"decider-1"` or `"state-decider-1"` key would **not** satisfy it.

**Does an empty block count?** No. `:8`: "Do not [...] treat an empty provider table as a declaration." `will_not_work` (`:294`) says: "Adding an empty `ModelProvider.{member}: {}` block: an empty table still resolves to None." On the merged tree, `python lint/run.py --rule C009` reports for Liquid: "The ModelProvider.LIQUID block (vidbyte/lib/registries/pricing.py:196) is empty, and an empty block resolves every model to no rate." Baseten (`:199`) and meraGPT get the same message.

**Guessed or unverified rates.**
- `:8`, WHAT NOT TO DO: "Do not import vidbyte, price runner-catalog siblings (unverifiable rates are deliberately omitted), or treat an empty provider table as a declaration."
- `how_to_fix` step 1 (`:287`): "Open the vendor's own pricing page for `{model}` (not a blog or an aggregator) and read the column headers: input, output, and cached-input rates in USD per 1M tokens, plus any long-context threshold."
- Step 2 (`:288`): "[...] with a comment line above it giving that pricing-page URL and the date you read it."
- `will_not_work` (`:294`): "Guessing a rate or copying a similar provider's numbers: a wrong but present rate keeps cost_complete true and is silent (field-guide operation-pricebook-rates.md)."
- Also in `will_not_work`: "Changing DEFAULT_PROVIDER_MODELS[ModelProvider.{member}] to a different model to dodge the finding: it changes which model every caller runs." and "Raising C009's baseline in lint/baseline.json: each finding is a default model whose runs cannot be billed."

**Sanctioned exemption mechanisms.** There is exactly one, `_PRICED_PER_RESPONSE`, a dict literal inside the rule's source (`:28-31`):
```python
# A provider listed here bills each response with its own reported cost, so a table rate would be a guess.
_PRICED_PER_RESPONSE = {
    "OPENROUTER": "OpenRouter prices each generation in its marketplace and returns usage.cost; OpenRouterUsage (vidbyte/agents/pricing/openrouter.py) prefers that reported cost over table math, and PROVIDER_PRICING keeps ModelProvider.OPENROUTER empty on purpose (docs/design/agent-usage-pricing-expansion.md non-goals).",
}
```
- How it is meant to be used, `:7`: "declare a provider in _PRICED_PER_RESPONSE only with the vendor mechanism that reports its cost".
- `how_to_fix` step 5 (`:291`): "Only if {value} bills each response with a vendor-reported cost (as OpenRouter's usage.cost does), declare it in `_PRICED_PER_RESPONSE` in lint/rules/c009_default_model_priced.py with the parser that reads that cost, instead of steps 1-4."
- Using it means editing the lint rule and shipping an SDK parser that reads the vendor's cost.

There is **no other mechanism**. There is no allowlist file, no inline marker or comment, and no `noqa` support for C009 (`lint/core/*.py` has none; every core module header says "Do not [...] suppress findings"). There is also no documented "no published price" path. `lint/README.md` covers C009 only as the table row `| C009 | default-model-priced | Every token-priced provider default resolves to a pricebook rate |` (`:170`). The baseline is a count ratchet: `lint/baseline.json` has `"C009": 1`, which is the Mistral finding. `lint/README.md:52-53` says: "Existing allowances may never be raised to make a regression pass."

**Relevant facts for each vendor's mechanism** (descriptive only):
- meraGPT's response does report a per-call cost: `"usage": { "input_tokens": 295, "output_tokens": 0, "cost_usd": "$0.0000118" }` (https://meragpt.com/docs/decider). Its shape is a `$`-prefixed string.
- Liquid's documented usage block is only `"input_tokens": 84, "output_tokens": 0` (https://docs.liquid.ai/lfm/models/d1).
- The Baseten Mercury-Decide page shows no usage or cost block.

**Current state.** Run on the merged tree with `python lint/run.py --rule C009` (no `--update-baseline`, so read-only): `C009 default-model-priced 4 1 REGRESSED`. The findings are `models.py:70` (MISTRAL, provider-absent, baselined), `:78` (LIQUID), `:79` (BASETEN), and `:80` (MERAGPT).

### 1.2 C010 `pricebook-vintage-bump` (`lint/rules/c010_pricebook_vintage_bump.py`)

**What it checks.** `summary` (`:325`): "Each SDK pricebook (PROVIDER_PRICING with PRICING_AS_OF, OPERATION_PRICING with OPERATION_PRICING_AS_OF) has a vintage that names the rates in force. When any effective rate entry is added, removed, or changed, the vintage must move to the later date the rates were verified, and lint/pricebook_vintage_lock.json must be refreshed in the same change; a moved vintage with a stale lock, a vintage moved backwards, or a vintage that is not an ISO date also fails."

The rule compares source with the committed lock, not with git (`:5`). The lock stores a per-entry digest keyed `PROVIDER/model`. Empty blocks such as `LIQUID: {}` produce no entries (`_entries`, `:216-225`).

Current finding (read-only run): `pricing.py:54` `PRICING_AS_OF = "2026-10-10"` "moved forward from the locked vintage 2026-07-30, but lint/pricebook_vintage_lock.json was not refreshed. `PROVIDER_PRICING` differs from the rates locked for 2026-07-30 (0 changed, 6 added, 0 removed)." The six added entries are CLOUDFLARE/clef, CLOUDFLARE/clef-flash, FOUNDRY/microsoft-decision-1, OPENAI/gpt-6-luna, PERPLEXITY/pplx-decider-v1-27b, and PERPLEXITY/pplx-decider-v1.1-27b.

**Is `--refresh-lock` the documented procedure or maintainer-only?** It is the documented contributor procedure for a legitimate pricebook update. Nothing restricts it to maintainers.
- `:5`: "only the --refresh-lock command writes the lock, and it refuses when rates changed without a later vintage."
- `:422`, in `main()`: "# Implements the one supported way to update the lock."
- `how_to_fix` for this drift kind (`:387`, `:393-394`):
  - "1. Confirm `PRICING_AS_OF = "2026-10-10"` is the date you re-verified the rates in vidbyte/lib/registries/pricing.py; if it is not, correct it to that date (still later than 2026-07-30)."
  - "2. From the repository root, run `python -m lint.rules.c010_pricebook_vintage_bump --refresh-lock`. It rewrites lint/pricebook_vintage_lock.json with the new vintage and rate digests [...] and refuses while a rate change is still paired with an unchanged, earlier, or non-ISO vintage."
  - "3. Commit vidbyte/lib/registries/pricing.py and lint/pricebook_vintage_lock.json together, naming the vendor pages and the new vintage in the commit message [...]."
- C009's step 3 (`:289`) names the same command, and `lint/README.md:68` says: "written only by `python -m lint.rules.c010_pricebook_vintage_bump --refresh-lock`".
- The only "only when" wording is about a missing lock: "create it with `{REFRESH_COMMAND}` only when bootstrapping a new pricebook" (`:251`).
- `will_not_work` (`:346`): running the command without moving the vintage, hand-editing the lock, back-dating, and raising C010's baseline (0).

**Would refreshing hide any other finding?** No.
- `LockRefresher.refresh` (`:401-418`) writes only when every drift is `lock-not-refreshed`. Any other drift kind is refused.
- The lock is read only by C010. Its `about` field says "the SDK never reads this file".
- C009 does not read the lock, so refreshing leaves C009 at 4/1.
- **Sequencing caveat.** If the lock is refreshed now at vintage 2026-10-10 and more rates are added later under the same vintage, C010 flips to `rates-changed-without-vintage-bump` (`:288-289`), and `--refresh-lock` refuses. Recovery would then need either the lock restored from git or a later vintage. The safe order is to make every rate edit first and refresh once at the end, which matches the implementer's note.

## 2. First-party prices

"First-party" means the company that bills the SDK's API call. All pages below were retrieved on 2026-10-10.

### 2.1 Liquid AI: model `d1`, Liquid API (`https://api.liquid.ai/decisions/v1`)

**Result: one first-party rate statement exists, on a Liquid blog post. Liquid has no public pricing page or docs page with a rate, and the console pricing page needs a login.**

| URL | What it showed |
|---|---|
| https://www.liquid.ai/blog/d1-decision-model (dated "OCT 5, 2026") | **Rate found, in the methodology footnote:** "Costs use list prices, without prompt-cache discounts. d1's costs use $0.04 per million input tokens." The "Availability and pricing" section says: "available on the [Liquid AI API](http://console.liquid.ai/) as `d1`" and "d1 is billed on input tokens only, with no output tokens. Images are counted as input tokens at the same rate as text [...]". It names this exact model id (`d1`) and endpoint (`https://api.liquid.ai/decisions/v1/systemone`). |
| https://www.liquid.ai/pricing | No API per-token rate. It covers open-weight licensing only: "Free to build. Yours to ship." / "free [...] until your company's annual revenue passes $10 million USD"; Enterprise: "Pricing is structured around your deployment scale and support needs." |
| https://docs.liquid.ai/lfm/models/d1 | No rate. It says image tokens are "charged at the model's input token rate" and "`usage.output_tokens`: Always `0`", and that "Vision is available through the Liquid API with the paid `d1` model. `d1:free` is text-only." |
| https://docs.liquid.ai/lfm/models/decision-models, https://docs.liquid.ai/guides/decision-model-guide, https://docs.liquid.ai/lfm/help/faqs, https://docs.liquid.ai/llms.txt (full docs index) | No pricing or billing page and no rate. The guide only contrasts "Output tokens: Billed [...]" with "Zero. No tokens generated." |
| https://console.liquid.ai/pricing, https://console.liquid.ai/ | Login wall ("Don't have an account? Sign up"). Not readable. |
| https://www.liquid.ai/models | No rate. It lists `d1`, `d1-3B`, and `d1-omni-600M` with links. |
| https://d1.liquid.ai/ (playground) | No rate. |

Implied row: input $0.04 / 1M, output $0.00 / 1M, no cached rate published. **Caveats.**
1. The source is a blog post, not a pricing page. C009's repair text says "the vendor's own pricing page [...] (not a blog or an aggregator)", and `operation-pricebook-rates.md` says "not a third-party blog or marketing post".
2. On this branch, the FOUNDRY block already cites a first-party blog (`techcommunity.microsoft.com/...`, `pricing.py:187-188`), so there is a branch precedent for a vendor's own blog.
3. A `"d1"` key would also price `d1:free` by longest prefix, at $0.04, unless a separate `"d1:free"` key exists.

### 2.2 Baseten: model `inception/mercury-decide`, Baseten Model APIs (`https://inference.baseten.co/v1/decisions`)

**Result: none found from Baseten, the billing company.**

| URL | What it showed |
|---|---|
| https://www.baseten.co/pricing/ | The Model APIs table ("Price per 1M tokens: Model / Input / Cache Input / Output") lists only GLM-5.3 Fast, GLM-5.3, GLM-5.3-Flash, GLM-5.2, GLM-5.2 Fast, DeepSeek V4 Flash 0731, DeepSeek V4 Pro 0813, DeepSeek V4.1 Flash, Kimi K3, Nemotron Ultra, gpt-oss-120b, and Whisper. **No Mercury-Decide row.** |
| https://www.baseten.co/library/mercury-decide/ | Names the exact model (`"model": "inception/mercury-decide"`, `Api-Key` auth, `/v1/decisions`), labelled "System one decision / Partner Model", "License: Inception - Proprietary". **No price on the page.** |
| https://docs.baseten.co/inference/model-apis/pricing-and-limits.md | "Model APIs bill per million input and output tokens. Rates vary by model. See the [Model APIs pricing page](https://www.baseten.co/pricing) for current prices." That page has no Mercury-Decide row (above). |
| https://docs.baseten.co/inference/model-apis/overview.md, https://www.baseten.co/products/model-apis/, https://www.baseten.co/library/tag/system-one/, https://www.baseten.co/library/publisher/inception/ | No Mercury-Decide price. |
| https://app.baseten.co/model-apis/inception/mercury-decide | "Sign in to Baseten". Not readable. |
| https://docs.baseten.co/reference/management-api/model-apis/gets-all-model-apis.md | Documents an **authenticated** `GET https://api.baseten.co/v1/model_apis` whose schema has `cost_per_million_input_tokens` / `cost_per_million_output_tokens` ("Null when pricing is unavailable"). I did not call it: it needs a Baseten API key, and it is not a public page. |

**Developer's own-API price. Not first-party for the Baseten route, because Inception does not bill Baseten calls.**
- https://docs.inceptionlabs.ai/get-started/models: `| **Mercury Decide** | ~~\$0.04~~ → **\$0.02** | \$0 | \$0 | `v1/decisions` | [...]`, under the banner "50% off Mercury Decide".
- https://docs.inceptionlabs.ai/capabilities/decisions: "Mercury Decide costs **$0.02 per million input tokens** (50% off the regular $0.04 price). Only input tokens are billed; output tokens are reported in `usage.output_tokens` but are not charged."
- Both pages cover Inception's own API (`https://api.inceptionlabs.ai/v1/decisions`, model id `mercury-decide`, not `inception/mercury-decide`). The page states no end date for the discount.
- S0 reported "no official Inception doc found". These docs pages exist now.

### 2.3 meraGPT: model `sd-1` (`state-decider-1`), `https://meragpt.com/v1`

**Result: first-party rate found. It names this exact model through the documented alias.**

| URL | What it showed |
|---|---|
| https://meragpt.com/docs/models | `| model | alias | context | input | output | status |` / `| `decider-1` | `sd-1` | 4,096 | $0.04 / 1M | $0.00 / 1M | Available |`. "Short aliases" section: "Every model also answers to a short alias — `sd-1` for Decider 1 [...] An alias names exactly the same model as its full name and never moves to a different one. Responses always report the full name [...]. The longer names the models launched under (`state-decider-1`, [...]) also still work." |
| https://meragpt.com/models/decider-1 | "model decider-1 / alias sd-1 / context 4,096 tokens / [...] input price $0.04 / 1M tokens / output price $0.00 / 1M tokens". Also: "`decider-1` always serves the current version of Decider 1: when an improved version ships, every request moves to it [...]. The name it launched under, `state-decider-1`, still works." |
| https://meragpt.com/docs/decider | "Nothing is generated [...] and output is never billed. Input costs $0.04 / 1M tokens." Its sample response has `"model": "decider-1"` and `"usage": { "input_tokens": 295, "output_tokens": 0, "cost_usd": "$0.0000118" }`. |
| https://meragpt.com/#pricing (home page; `/pricing` returns the same page) | "What it costs" table: `| Decider 1decider-1 | $0.04 / 1M | $0.00 / 1M | Available |`. Also: "Metered per token against your balance, at the rate on the model card; a decision bills input only". |
| https://meragpt.com/docs | Overview. Model id `decider-1`, endpoint `/v1/systemone`. No rate on this page; it points to `/docs/models` for "the catalogue, pricing and limits". |

Implied row: input $0.04 / 1M, output $0.00 / 1M, no cached rate published. **Notes.**
1. The primary id is now `decider-1`. `sd-1` is its alias and `state-decider-1` its launch name, so the three ids name one model at one price. In the pricebook, a `"sd-1"` key prices only `sd-1`, because of exact matching and the fact that neither other id starts with `sd-1`.
2. Responses report `decider-1`. That matters for the pricing key only if the adapter prices `response.model` (`model_from_request=False`). Spec §9.1 has meraGPT on `model_from_request=True`, so the key is the id the caller sends.
3. The SDK catalog has `meragpt/sd-1` and `meragpt/state-decider-1` but not `decider-1`.
4. The S0 hub figure of $0.03 does not match the first-party $0.04.

## 3. Third-party figures (for the user's decision only; none satisfies the first-party rule)

| Vendor/model | Third-party source (URL) | Route it prices | Figure (verbatim) |
|---|---|---|---|
| Liquid d1 | https://openrouter.ai/api/v1/models/liquid/d1/endpoints (public JSON, HTTP 200) | OpenRouter → provider "Liquid", endpoint `liquid/d1-20260930`; OpenRouter bills | `"pricing":{"prompt":"0.00000004","completion":"0","input_cache_read":"0.00000004","discount":0}` = $0.04 / 1M input, $0 output; `"context_length":65536` |
| Liquid d1 | https://vercel.com/ai-gateway/models/d1 | Vercel AI Gateway (`liquid/d1`) → provider Liquid AI; Vercel bills | "Input $0.04, Per 1M tokens"; provider row: `66K [...] $0.04/M [...] 09/29/2026` (output cell blank) |
| Liquid d1 | https://systemonemodels.org/ | hub summary | "OpenRouter lists a paid liquid/d1 at $0.04 per million input tokens" |
| Mercury Decide | https://openrouter.ai/api/v1/models/inception/mercury-decide/endpoints (HTTP 200; `-20260930` resolves to the same record) | OpenRouter → provider **Inception** (not Baseten), endpoint `inception/mercury-decide-20260930`; OpenRouter bills | `"pricing":{"prompt":"0.00000002","completion":"0","input_cache_read":"0","discount":0.5}` = $0.02 / 1M input (50% discount), $0 output; `"context_length":65536` |
| Mercury Decide | https://systemonemodels.org/ | hub summary | "It costs $0.02 per million input tokens on Inception's API and OpenRouter, and a free tier stays on OpenRouter." |
| meraGPT Decider 1 | https://systemonemodels.org/models/meragpt-decider-1/ | hub; meraGPT hosted API | "Input price $0.03 per 1M tokens" / "Output price Free". **This conflicts with the first-party $0.04.** |
| meraGPT Decider 1 | https://openrouter.ai/api/v1/models/meragpt/state-decider-1/endpoints and `.../meragpt/decider-1/endpoints` | not listed | HTTP 404. meraGPT's docs say the namespaced id is "reserved for a future OpenRouter listing". |

No third-party source prices Mercury Decide on **Baseten's** route. Every public Mercury Decide figure is for Inception's own API or for OpenRouter's Inception endpoint.
