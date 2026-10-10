# S1 research scout, round 2: report

Date: 2026-10-10. Output: `docs/spec/decision-model-providers/context/provider-research-2.md`. No commits. No files other than these two were created or changed.

## What I searched

- **Google, Gemini first.**
  - Gemini API changelog, models page, REST method index, OpenAI-compatibility page (raw `.md.txt`), pricing page (raw), and the Gemini 3 guide.
  - Vertex AI / Gemini Enterprise Agent Platform release notes.
  - Google Developers Blog and blog.google posts from 2026-10-06.
  - The MediaPipe Decision Maker task pages (overview, Python, best practices).
  - The Chrome `DecisionModel` explainer.
  - Google AI Developers Forum threads on logprobs.
  - The Vercel AI SDK decisions page, for its `google.decisionModel` adapter.
- **OpenAI.**
  - Decisions guide (raw `.md`), changelog, `gpt-6-luna` model page, and pricing page.
  - The community beta announcement.
  - The API reference: the generic URL from round 1, the `llms.txt` indexes, and the TypeScript, Python, and Ruby reference pages plus the admin usage endpoint.
  - Azure (Microsoft Q&A) and Bedrock (the `openai.gpt-6-luna` model card), for availability on other clouds.
- **Other hosted decision APIs.**
  - Discovery sources:
    - OpenRouter's `models?output_modalities=decisions` list (THIRD-PARTY, discovery only);
    - the awesome-decision-models list;
    - befailproof, benchlm.ai, and systemonemodels.org;
    - web searches for "`/v1/systemone`", "decision model API", and "typed decisions".
  - For each candidate I then read its first-party docs, pricing page, and auth page. Prices and wire lines were raw-checked with curl and grep wherever the page allowed it.
  - The 26 rows in §4 cover Celeris, Nace, Upstage, Inception, Hanzo, Vansa, ZooData, Fastino, Alibaba, decisionmodels.io, milliseconds.ai, DigitalOcean, sference, Vercel, LLM Gateway, Eden AI, AI/ML API, Requesty, Cloudflare clef-omni, Telnyx, Respan, Swarms, SiliconFlow, and Databricks. §3.4–3.5 add the hosts and labs I checked and rejected.
- **The SDK, read only.**
  - `systemone.py` (criteria encoding and the answer normalizer), `agents/pricing/typesafe.py` (`JevUsage`), `lib/registries/models.py`, `lib/constants/runners.py`, `lib/constants/jev.py`, `lib/enums/model_provider.py`, `lib/enums/jev.py`, and `lib/http/transport.py`.
  - I read these to check whether each candidate fits the existing `SystemOneHost` row and clears the prefix and C009 rules.

## What failed

- **OpenAI reference.** Round 1's `developers.openai.com/api/reference/resources/decisions/methods/create` still returns 404, and so does `/api/reference/resources/decisions`. Decisions is missing from all three `llms.txt` indexes.
  - Fix: the language-specific pages work, and `.md` returns their text, for example `/api/reference/typescript/resources/decisions/methods/create`.
- **Alibaba pricing page.** It is about 610K characters, and a summarising fetch truncated it before the decision section. Fix: a raw curl plus grep found the "Decision model" section and the "Limited-time free" row.
- **Nace.** Every `console.nace.ai/docs/drex/*.md` URL returns a 500 error page. The plain HTML pages work.
- **404s:**
  - `docs.hanzo.ai/docs/decisions.md` (the plain page works);
  - `openrouter.ai/upstage/solar-decide-flash`;
  - `deepinfra.com/nace-ai/drex-v1.5`;
  - the Swarms decision-models docs page.
- **429:** `platform.inceptionlabs.ai/pricing`. The docs models table and the decisions page carry the same price.
- **JavaScript-only or not parsable:**
  - `celeris.ai/pricing` (I used `docs.celeris.ai/pricing.md` instead);
  - the ZooWork docs code tabs (I read the static text only);
  - the body of the thenewstack article.
- **Fetch only, not raw-checked:**
  - Vansa: one WebFetch summary. The "No SLA" line and the User-Agent / Cloudflare 1010 quote came from a helper and were not re-checked.
  - The rejection rows other than Telnyx, the §3.5 "nothing found" list, and a few single facts marked "(helper)" in §6. All of these are helper reads.
- **A 429 usage limit** interrupted the turn partway through verification. I resumed from the same point and did not repeat any search.

## What was surprising

1. **Gemini has no hosted decision model.** What Google released on 2026-10-06 is the on-device MediaPipe Decision Maker with EmbeddingGemma 2. It has probabilistic boolean, choice, and score answers, but no endpoint and no price. Google also confirmed that Gemini 3.x no longer returns logprobs ("logprobs are no longer returned for 3.X models"), which closes the logprob route too.
2. **OpenAI still has only `gpt-6-luna`.** The reference, newly found, documents a `model` echo and Responses-style `usage` keys, which round 1 had marked as undocumented. The reference and the guide contradict each other on hosted image URLs.
3. **A wave of System One clones in two to three weeks.** At least 18 vendors and gateways now accept TypeSafe's System One body. Eleven serve their own model (Celeris, Nace Drex, Upstage Solar Decide, Inception, Hanzo Kai, Vansa, ZooData Instinct, Fastino GLiDE, Alibaba, decisionmodels.io, milliseconds.ai). The rest resell Jev or Clef. All of them would fit the existing `SystemOneProvider` with one host row each, so no new adapter is needed.
4. **"System One body on a `/decisions` path" is common.** Inception, Hanzo, sference, Eden AI, and AI/ML API all do it, like Perplexity and Baseten. A path segment says nothing about which wire a host speaks.
5. **Celeris is the only first-party vendor that also serves the OpenAI Decisions wire.** But `OpenAIDecisionsProvider` is pinned to `ModelProvider.OPENAI`.
6. **Vercel AI Gateway now serves System One as well as OpenAI Decisions.** It carries five decision models at list price with no markup, which reopens spec Q-3 / NG-9.
7. **Pricing traps:**
   - Alibaba is "Limited-time free" with no announced rate.
   - Inception's $0.02 is a 50% promotion off $0.04, which also affects the Baseten row the user tied to Inception's rate.
   - AI/ML API marks Jev up to $0.0577668.
   - LLM Gateway and Requesty add 5% outside the token rate.
   - decisionmodels.io prices by a per-key region tier.
   - Upstage's own price ($0.10) is double OpenRouter's ($0.05). This is a live example of why aggregator prices must not stand in for a provider's own price.
8. **Semantic traps:**
   - Fastino's `score` is the argmax index; its weighted score is in `expected_level`.
   - Telnyx says its scores are "relative preferences", not calibrated probabilities.
   - milliseconds.ai says its probabilities "are not measured accuracy".
   - Hanzo Kai caps state plus question at 1,024 tokens.
   - Upstage caps choice options at 26 (logits over the letters A–Z).
9. **Catalog overlap.** A new INCEPTION member would build the qualified key `inception/mercury-decide`, the same string as Baseten's bare model id. Both map to the decision runner, so it is harmless but ambiguous.
