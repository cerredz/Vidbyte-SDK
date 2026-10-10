# S3 side-scout report: pricing re-check

Date: 2026-10-10. Output: `docs/spec/decision-model-providers/context/pricing-recheck.md`. I made no commits and no source, lint, or spec edits.

## What I read (repo)
- **Lint rules:**
  - `lint/rules/c009_default_model_priced.py` and `lint/rules/c010_pricebook_vintage_bump.py`, both in full.
  - `lint/README.md`: the baseline ratchet, the file index, and the rule table.
  - `lint/baseline.json` (C009 = 1, C010 = 0) and `lint/pricebook_vintage_lock.json`.
  - The headers of `lint/core/baseline.py` and `lint/core/*.py`, to look for a suppression mechanism. There is none.
- **Commit history:** `git log origin/main -- <C009/C010/lock>` returns only `4f57d8ed` (#587). I read its full message.
- **Registries and catalogs:**
  - `vidbyte/lib/registries/pricing.py`: header, `PRICING_AS_OF`, the provider blocks from line 150 on, and `resolve`.
  - `vidbyte/lib/registries/models.py`: `DEFAULT_PROVIDER_MODELS`, `DECISION_DEFAULT_MODELS`, `MODEL_ALIASES`, and `normalize_model`.
  - `vidbyte/lib/constants/runners.py`: the decision entries and the `mercury-decide` alias note.
  - `vidbyte/providers/README.md` "Adding A Provider".
- **Field guide, outside the repo:** `field-guide/vidbyte-sdk/operation-pricebook-rates.md` and `provider-api-contracts.md`.
- **Docs, named parts only:**
  - From the spec: INV-18, FR-4, D-10, A-15, Q-4, and the §9.1 rows plus the pricing-key note.
  - `provider-research.md`: §2 rows 6-8, §3.6-3.8, §3.18, and §6.
  - `S3-implementer.md`: the "Merge with main" section.

## What I ran (read-only)
- `python lint/run.py --rule C009` and `--rule C010`, with `PYTHONDONTWRITEBYTECODE=1` and no `--update-baseline`, so they wrote nothing. The results match the implementer's: C009 4/1 (Mistral at `:70`, plus `:78-80`) and C010 1/0 (lock-not-refreshed, 6 added entries).
- `git status` was unchanged before and after, apart from the existing untracked `S3-implementer.md`.

## What I searched and fetched (web, all on 2026-10-10)
- **Tools and storage:** `firecrawl scrape --max-age 0` for HTML pages, and `curl` for docs `.md` pages, `llms.txt` indexes, and OpenRouter's public `/api/v1/models/<id>/endpoints` JSON. Everything went to the session scratchpad, not the worktree.
- **WebSearch (extended):** "Liquid AI d1 decision model API price per million input tokens" and "Mercury Decide Inception pricing per million tokens Baseten decisions".
- **Liquid:**
  - liquid.ai/pricing; blog/d1-decision-model; /models.
  - docs.liquid.ai: d1, decision-models, decision-model-guide, faqs, deprecations, llms.txt.
  - console.liquid.ai (/ and /pricing), which shows a login wall.
  - d1.liquid.ai.
- **Baseten:**
  - baseten.co: /pricing/, /library/mercury-decide/, /library/tag/system-one/, /library/publisher/inception/, /products/model-apis/, /library/mercury-25/.
  - docs.baseten.co: llms.txt, the documentation and reference indexes, model-apis pricing-and-limits and overview, and the management-API `GET /v1/model_apis` schema.
  - app.baseten.co model page, which shows a login wall.
- **Inception:** inceptionlabs.ai /pricing (404), /models, llms.txt; docs.inceptionlabs.ai llms.txt, get-started/models, capabilities/decisions, and api-reference create-a-decision.
- **meraGPT:** meragpt.com home (/#pricing), /pricing (same page), /docs, /docs/models, /docs/decider, /models/decider-1.
- **Third-party:**
  - OpenRouter endpoints JSON for liquid/d1, inception/mercury-decide, inception/mercury-decide-20260930, meragpt/state-decider-1 (404), and meragpt/decider-1 (404).
  - vercel.com/ai-gateway/models/d1.
  - systemonemodels.org (home and the meraGPT detail page).

## Findings in one place
- **C009** has exactly one sanctioned exemption: `_PRICED_PER_RESPONSE` in the rule's own source (`c009_default_model_priced.py:28-31`). It is for vendors that bill each response with a reported cost, and it needs a parser. Using it means a lint-rule edit. There is no allowlist, marker, `noqa`, or documented "no published price" path. Empty blocks and guessed rates are explicitly rejected, and so is raising the baseline.
- **C010:** `--refresh-lock` is the documented contributor procedure, and nothing restricts it to maintainers. Refreshing hides nothing else. Run it once, after the final rates are in.
- **First-party rates, by vendor:**
  - **meraGPT:** yes. $0.04 / 1M input and $0.00 / 1M output for `decider-1`, alias `sd-1`, on four meraGPT pages.
  - **Liquid:** a first-party statement exists, $0.04 / 1M input with output not billed, but it is in a blog footnote dated Oct 5, 2026. There is no pricing page, and the console page is login-gated.
  - **Baseten:** none. The Baseten pricing table has no Mercury-Decide row and the library page has no price.

## Surprises
1. **meraGPT now publishes a price, and the model's primary id changed.** On 2026-10-10 the S0 research found neither. The catalogue now names `decider-1` as the model, with `sd-1` as its alias and `state-decider-1` as its launch name. The first-party rate is $0.04, not the hub's $0.03. meraGPT responses also carry `usage.cost_usd` as a `$`-prefixed string.
2. **Inception's own docs now price Mercury Decide.** The rate is $0.02 / 1M input, "50% off the regular $0.04 price", with output $0. S0 found no Inception doc. This price is for Inception's API (`mercury-decide`), not for Baseten's route (`inception/mercury-decide`), so under the briefing's definition it is not first-party for the SDK's BASETEN provider.
3. **OpenRouter's public endpoints API works where its model pages returned 404 to S0.** It gives exact per-token prices: liquid/d1 at $0.04 served by "Liquid", and mercury-decide at $0.02 served by "Inception" with discount 0.5.
4. **C009's repair text excludes blogs, but the branch already cites one.** The text says "vendor's own pricing page [...] (not a blog or an aggregator)". The FOUNDRY block on this branch already cites a Microsoft blog as its first-party source. The orchestrator should decide whether Liquid's blog footnote qualifies on the same basis.
5. **Prefix matching would misprice `d1:free`.** A `"d1"` key would price `d1:free` at the paid rate by longest prefix.
6. **Bare `mercury-decide` would stay unpriced.** A key `"inception/mercury-decide"` would not price the bare catalogued alias `mercury-decide`, because neither normalization nor prefix matching links the two.
7. **HEAD moved under me.** Another session committed `9e0d04e9` (a `pipeline.md` docs change) on top of `7bfe29e8` while I worked. The lint, registry, and pricebook files are identical at both commits.
8. **`origin/main` has moved too.** The local ref is now `d7b25110` (#699), one commit past `77084eb2`. `git diff 77084eb2 origin/main -- lint/ vidbyte/lib/registries/` is empty.
