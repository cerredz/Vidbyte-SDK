# Decision-model provider research (S0 scout)

Written 2026-10-10 for the `decision-model-providers` spec. Every fact below carries the URL it came from and the date it was read; all pages were read on **2026-10-10** unless a row says otherwise. "Unverified" means the only evidence is a secondary source or a page that would not load. This document records facts and groupings only; it does not design adapters or pick providers.

Reference code read (read-only): `vidbyte/lib/dataclasses/jev.py`, `vidbyte/providers/typesafe.py`, `vidbyte/agents/pricing/typesafe.py`, plus one grep of the `JevQuestionType` enum in `vidbyte/lib/enums/jev.py` to confirm the question-type vocabulary.

> **Correction to the briefing's vocabulary (read first).** The briefing describes the three question kinds as "boolean / score / noul (free answer, no confidence)". Neither the SDK nor TypeSafe's API has a free-answer kind. `JevQuestionType` is `NOUL`, `CHOICE`, `SCORE` (`vidbyte/lib/enums/jev.py`). **Noul is the yes/no kind**: it returns a single P(yes) with *no confidence field* (`JevAnswer.noul`; `_TypeSafeAnswerNormalizer._noul`). **Choice** returns a probability per named option plus `confidence`. **Score** returns a probability per ordered level, a probability-weighted `score`, a `legend`, and `confidence`. Throughout this document "boolean" means noul, and the third kind is choice.

---

## 1. Reference capability: TypeSafe Jev

Sources: https://docs.typesafe.ai/api.md, https://docs.typesafe.ai/models.md, https://docs.typesafe.ai/confidence.md (all read 2026-10-10), and the SDK files above.

**Endpoint and auth**
- `POST https://api.typesafe.ai/v1/systemone`, `Content-Type: application/json`, `Authorization: Bearer <API_KEY>` (api.md). The SDK builds `config.resolved_endpoint() + JEV_SYSTEMONE_PATH` with `bearer_headers(...)` (`vidbyte/providers/typesafe.py`, `_TypeSafeCallBuilder.decision`) and sends an idempotency-key header (`JEV_IDEMPOTENCY_KEY_HEADER`).
- `GET /v1/models` returns model cards `{name, description, release_date}` (`JevModelCard`; `_TypeSafeCallBuilder.models`).
- Env var in the SDK: `TYPESAFE_API_KEY` (named in the 401 message of `_TypeSafeFailures.transport_error`). TypeSafe's docs name no env var (api.md).

**Request body** (api.md; SDK `TypeSafeWireRequest` / `TypeSafeWireQuestion`)
- `model` (string, e.g. `jev-latest`), `state` (string | object | array), `questions` (map of caller-chosen name → question). Answers return under the same keys.
- Question = `{type, instructions, criteria?}`:
  - `noul`: yes/no; `criteria` optional, `{true: …, false: …}` descriptions. The SDK omits `criteria` when a noul question has no options (`_TypeSafePayloadBuilder.criteria`).
  - `choice`: `criteria` required, map option → description or `null`; maximum 255 options.
  - `score`: `criteria` required, ordered array of level descriptions; minimum 2, maximum 10 levels.

**Response body** (api.md; SDK `_TypeSafeAnswerNormalizer`)
- `model`, `answers` (map), `usage: {input_tokens, output_tokens}`.
- noul answer `{type:"noul", noul: P(yes) in [0,1]}`, no confidence. SDK expands to `{true: p, false: 1-p}`; `choice` = `true` when `p >= JEV_NOUL_YES_THRESHOLD`.
- choice answer `{type, choice, probabilities: {option: p}, confidence}`; probabilities sum to 1.
- score answer `{type, score, legend: {"0": desc, …}, probabilities: {"0": p, …}, confidence}`; `score` is the probability-weighted level index and may fall between levels. SDK re-keys probabilities by level label and rejects any missing or unexpected key.
- `confidence` (confidence.md) is a fixed statistic of the distribution, not a calibration guarantee. Choice: `(p_max − 1/n) / (1 − 1/n)`. Score: `max(0, 1 − Σ p_i |i − m| / MAD_unif)` with `MAD_unif = (1/n) Σ |i − (n−1)/2|`. Noul has none; the page suggests `|2p − 1|` if one is wanted. No numeric calibration claim; "one reasonable way to summarize a distribution, not the only one".

**Models and pricing** (models.md)
- Versioned ID `jev-1.13.0`; aliases `jev-latest` → `jev-1.13.0` (SDK default) and `jev-preview` → `jev-1.13.0` ("no preview build available right now"). Aliases move on release; pin `jev-1.13.0` if thresholds were tuned.
- Input **$0.042 per 1M tokens** ("$42 per Btok"); **output free**. The SDK prices output at the table's 0.0 rate (`vidbyte/agents/pricing/typesafe.py`, `@intent jev-output-is-free`) and has no cache tier (`@intent jev-has-no-cache-tier`).
- Context: 64k tokens per request (state + all questions); 32k per question (state + longest question). Text only.
- Calibration claim: "trained with RLCD to return calibrated decisions"; no numeric metrics.

**Rate limits** (models.md): 100K tokens/second and 80 requests/second; 429 on excess; SDKs retry with backoff honouring `retry-after`; limits "can change without notice". (A secondary roundup quotes 1,200 requests/minute, https://openrouter.ai/blog/insights/what-is-jev/; the official figure is 80 rps.)

**Errors** (api.md): 401 missing/invalid key; 422 validation failure naming the field; 429 rate limit; 529 overloaded. The SDK retries `JEV_RETRY_STATUS_CODES` with `JEV_RETRY_BACKOFF_SECONDS`.

**Abstraction-shaping facts**
- Many questions per call against one `state`, keyed by caller names; the SDK validates `1..JEV_MAX_QUESTIONS` questions and `JEV_MAX_STATE_CHARS` (`JevDecisionRequest.__post_init__`).
- Score probabilities are index-keyed on the wire and label-keyed in `JevAnswer`.
- Billed usage rides on `ProviderResponseError.details["usage"]` when normalization fails (`@intent billed-calls-stay-billable-on-bad-answers`).
- Launch timeline (for §5): the-decoder article dated Sep 16, 2026 says TypeSafe "has introduced" Jev behind a waitlist (https://the-decoder.com/former-openai-researcher-builds-an-ai-model-that-judges-options-instead-of-writing-text/); eesel.ai dates the launch Sep 15, 2026 and the waitlist removal Sep 27 (secondary). TypeSafe's own launch post carries an "Oct 9, 2026, 10:46 PM UTC" timestamp (https://typesafe.ai/blog/introducing-system-one-models-and-jev), which looks like an edit date; see §6.

---

## 2. Catalog table

Capability class: **1** native calibrated decision endpoint; **2** log-probability-derived; **3** structured-output / self-reported confidence. "System One wire" = TypeSafe's `{model?, state, questions{name→{type,instructions,criteria}}}` → `{answers{name→…}, usage}` with `noul/choice/score`. "SDK text adapter" names an existing file under `vidbyte/providers/`. Prices are USD per 1M tokens unless stated. All rows read 2026-10-10.

| # | Provider | Product / endpoint | Class | Answer kinds served (how) | Auth (header; env-var convention) | Base URL | OpenAI-compatible wire | Pricing (model, URL) | Documented rate limits | Copies Jev? |
|---|---|---|---|---|---|---|---|---|---|---|
| R | TypeSafe (reference) | `POST /v1/systemone`; `GET /v1/models` | 1 | noul = `noul` P(yes); choice = `probabilities` + `confidence`; score = `probabilities` + `score` + `legend` + `confidence` | `Authorization: Bearer`; `TYPESAFE_API_KEY` (SDK) | `https://api.typesafe.ai` | no (System One wire) | jev-1.13.0: $0.042 in / $0 out (https://docs.typesafe.ai/models.md) | 100K tok/s, 80 rps (models.md) | — |
| 1 | OpenAI | Decisions API `POST /v1/decisions` (public beta) | 1 | predicate = `probability` scalar; choice = `probabilities[{value,probability}]` + `confidence`; score = `score` + `probabilities[{value,label,probability}]` + `confidence`; extra `refusal` answer type | `Authorization: Bearer`; `OPENAI_API_KEY` | `https://api.openai.com/v1` | no (own Decisions wire, not chat) | gpt-6-luna on /v1/decisions: $0.10 in; output, cache read, cache write $0 (https://developers.openai.com/api/docs/guides/decisions) | not documented for /v1/decisions; the gpt-6-luna model page lists tier RPM/TPM and does **not** list /v1/decisions (https://developers.openai.com/api/docs/models/gpt-6-luna) | **yes**: same three primitives, input-only pricing, launched after Jev (§5). SDK text adapter `vidbyte/providers/openai.py` |
| 2 | Perplexity | Decisions API `POST /v1/decisions` | 1 | System One answers: `noul`; `choice` + `probabilities` + `confidence`; `score` + `legend` + `probabilities` + `confidence` | `Authorization: Bearer` only (`x-api-key` → 401); docs use `PERPLEXITY_API_KEY` | `https://api.perplexity.ai` | no (System One body at a `/v1/decisions` path) | pplx-decider-v1.1-27b / v1-27b: **$0.02 in** / $0 out, no per-request fee (https://docs.perplexity.ai/api-reference/decisions-post); launch tweet said $0.04 (§6) | 10 rps per org on every plan + token burst limit; 429 with `Retry-After`; `x-ratelimit-*` headers (https://docs.perplexity.ai/docs/decisions/quickstart) | **yes**: Jev-shaped body, benchmarks vs Jev; open weights Apache-2.0 |
| 3 | Microsoft (Foundry) | Microsoft-Decision-1 `POST {AZURE_ENDPOINT}/providers/microsoft/v1/systemone` | 1 | System One answers (official sample shows `choice`; blog lists yes/no, multiple-choice, rating) | `Authorization: Bearer` (Entra `DefaultAzureCredential`, scope `https://cognitiveservices.azure.com/.default`) or `FOUNDRY_API_KEY` per prose (page inconsistent) | per-resource Foundry endpoint | no (System One wire) | $0.042 in / output N/A, US and EU datazones (https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/introducing-microsoft-decision-1-in-microsoft-foundry-for-decision-and-classific/4562742) | not stated | **yes**: endpoint path is literally `systemone`; Microsoft's post targets Jev-style decision workloads |
| 4 | Cloudflare | Workers AI Clef / Clef-flash `POST /client/v4/accounts/{ACCOUNT_ID}/ai/run/@cf/cloudflare/clef`, body `model: "clef"` or `"clef-flash"` | 1 | System One answers; `images[]` (≤4) extension; `usage` fields undocumented | `Authorization: Bearer {CLOUDFLARE_AUTH_TOKEN}` + account id in path | `https://api.cloudflare.com` | no (System One wire + `images`) | clef $0.240 in (21,818 neurons/M); clef-flash **$0.038 in** (3,455 neurons/M); no output charge; $0.011 per 1,000 neurons; 10,000 free neurons/day (https://developers.cloudflare.com/workers-ai/platform/pricing/) | not on model page | **yes**: blog says "fully Jev-API compatible" (https://blog.cloudflare.com/clef-decision-models/) |
| 5 | OpenRouter | Decisions API `POST /api/alpha/decisions`; System One `POST /api/v1/systemone` | 1 (aggregator) | System One answers for `typesafe/jev-1.13`, `~typesafe/jev-latest`, `typesafe/jev-router`, `inception/mercury-decide*`; third-party lists add `liquid/d1`, `jaredpalmer/kev-4b`, `upstage/solar-decide`, `respan/span-01` (§6); `usage.cost` in USD | `Authorization: Bearer`; `OPENROUTER_API_KEY` | `https://openrouter.ai/api` | no for decisions; yes for its chat API | typesafe/jev-1.13: $0.042 in / $0 out (https://openrouter.ai/compare/typesafe/jev-1.13); mercury-decide $0.02 in (search snippet, unverified) | not stated; errors 402 (credits), 413, 429, 524, 529 (API reference) | **yes**: resells Jev and Jev-compatible models. SDK text adapter `vidbyte/providers/openrouter.py`; pricing parser `vidbyte/agents/pricing/openrouter.py` |
| 6 | Liquid AI | d1 `POST /decisions/v1/systemone` | 1 | System One answers; `images[]` (≤8) extension; `usage.output_tokens` always 0 | `Authorization: Bearer`; `LIQUID_API_KEY` (keys prefixed `liquid_`) | `https://api.liquid.ai` | no (System One wire) | not on docs page; $0.04 in per third-party hub (unverified, §6) | not stated | **yes**: page says TypeSafe SDKs can call it |
| 7 | Inception Labs (via Baseten / OpenRouter) | Mercury Decide; Baseten `POST /v1/decisions`, model `inception/mercury-decide`; OpenRouter `inception/mercury-decide-20260930` and `:free` | 1 | System One answers (Baseten library page) | Baseten: **`Authorization: Api-Key <BASETEN_API_KEY>`** (not Bearer); OpenRouter: Bearer | `https://inference.baseten.co` / `https://openrouter.ai/api` | no | not on Baseten page; OpenRouter $0.02 in and a free tier of 200 req/day (search snippets, unverified); no official Inception doc found | OpenRouter free route rate-limited | **yes**: System One schema per listings; released 2026-09-30 (secondary) |
| 8 | meraGPT | Decider 1 `POST /v1/systemone`, model `state-decider-1` (alias `sd-1`) | 1 | System One answers (page shows noul, score) | `Authorization: Bearer $MERAGPT_API_KEY` | `https://meragpt.com/v1` | no | $0.03 in per third-party hub; 4,096-token request cap and 10 choice labels per awesome-list (all unverified) | not fetched (`/docs/errors`) | **yes**: "speaks the System One schema, so the typesafe-sdk works against it unchanged" (https://meragpt.com/docs) |
| 9 | Vercel AI Gateway | `POST /v1/decisions`, model `openai/gpt-6-luna-decisions` | 1 (aggregator) | OpenAI Decisions answers ("same request and response format as OpenAI") | `Authorization: Bearer`; `AI_GATEWAY_API_KEY` | `https://ai-gateway.vercel.sh/v1` | no (OpenAI Decisions wire) | $0.10 in; output not listed (https://vercel.com/ai-gateway/models/gpt-6-luna-decisions) | not stated | yes (resells OpenAI's Jev-like product); third-party lists also name `typesafe-ai/jev` and Liquid d1 on the gateway (unverified) |
| 10 | Together AI | Tev1-4B-experimental via `POST /v1/chat/completions`, model `together/Tev1-4B-experimental` | 1 model behind a **chat** wire (effectively 2) | Returns one option letter (A–X) for 2–24 options; probabilities only if `logprobs` works on this model (unverified); noul = 2-option choice; score = ordered options | `Authorization: Bearer`; `TOGETHER_API_KEY` | `https://api.together.ai/v1` | yes | $0.04 in / output free (https://www.together.ai/models/tev1-4b-experimental; https://www.together.ai/pricing) | not stated | yes in spirit (decision fine-tune) but "experimental", calibration "not comprehensively evaluated", license "being finalized" |
| 11 | Self-hosted System One servers (Laya, Strands Decider 2B, H2O-Lightning-4B, Kev, PostHog Jeeves, Clef weights, pplx-decider weights) | `POST http://<host>/v1/systemone` | 1 (self-host) | System One answers | none by default; Laya: `Authorization: Bearer` when `LAYA_API_KEY` is set | caller's | no | $0 (own hardware) | none | **yes**: all advertise Jev / System One compatibility |
| 12 | OpenAI (chat) | `POST /v1/chat/completions` with `logprobs: true`, `top_logprobs ≤ 20` | 2 | noul from P("yes") vs P("no") in `choices[0].logprobs.content[0].top_logprobs`; choice/score over ≤20 single-token labels | Bearer; `OPENAI_API_KEY` | `https://api.openai.com/v1` | yes | gpt-6-luna $0.10/$0.50; gpt-6-sol $2/$10; gpt-6.1-sol $2/$10; gpt-6-astra $10/$50 (https://developers.openai.com/api/docs/pricing) | tier RPM/TPM per model page (gpt-6-luna Build 5,000 RPM / 2M TPM) | no. SDK text adapter exists |
| 13 | Google Gemini API / Vertex AI | `generateContent` with `generationConfig.responseLogprobs: true`, `logprobs: 1..20` | 2 (**deprecated for Gemini 3.x**) | noul/choice/score from `logprobsResult.topCandidates[0].candidates[]{token,logProbability}` | Gemini API: `?key=` / `GEMINI_API_KEY`; Vertex: OAuth Bearer | `https://generativelanguage.googleapis.com/v1beta` | no (Gemini wire) | gemini-2.5-flash $0.30/$2.50; gemini-2.5-flash-lite $0.10/$0.40; gemini-3.1-flash-lite $0.25/$1.50; gemini-3.8-flash $0.75/$3.75 (https://ai.google.dev/gemini-api/docs/pricing) | not fetched | no. "deprecated for Gemini 3.x models and will soon be completely deprecated" (Vertex inference reference). SDK text adapter `vidbyte/providers/gemini.py` |
| 14 | DeepSeek | `POST /chat/completions`, `logprobs`, `top_logprobs ≤ 20` | 2 | as row 12 | Bearer; `DEEPSEEK_API_KEY` | `https://api.deepseek.com` | yes | deepseek-flash $0.15 in (cache miss, off-peak) / $0.60 out; peak $0.30/$1.20; deepseek-v4-pro $0.66/$1.98 off-peak, $1.32/$3.96 peak (https://api-docs.deepseek.com/quick_start/pricing) | not fetched | no |
| 15 | Together AI (chat, any model) | `POST /v1/chat/completions`; **`logprobs` is an integer 0–20** (no `top_logprobs` request param) | 2 | as row 12 but the response is the legacy `{tokens, token_logprobs, top_logprobs}` shape | Bearer; `TOGETHER_API_KEY` | `https://api.together.ai/v1` | mostly (logprobs param differs) | Qwen3.5 9B $0.17/$0.25; Llama 3.3 70B $1.04/$1.04; gpt-oss-120B $0.15/$0.60 (https://www.together.ai/pricing) | not fetched | no |
| 16 | Fireworks AI | `POST /inference/v1/chat/completions`; `logprobs` int or bool; `top_logprobs` 0..`--max-logprobs` (**5 by default**) | 2 | as row 12, ≤5 labels by default | Bearer; `FIREWORKS_API_KEY` (convention, not on page) | `https://api.fireworks.ai/inference/v1` | yes | official page lists no serverless per-token table (https://fireworks.ai/pricing); third-party tiers unverified | not fetched | no |
| 17 | Cerebras | `POST /v1/chat/completions`; `logprobs`; `top_logprobs` 0–20 | 2 | as row 12 | Bearer; `CEREBRAS_API_KEY` (convention) | `https://api.cerebras.ai/v1` | yes | pricing table did not render (https://www.cerebras.ai/pricing); third-party gpt-oss-120b $0.35/$0.75 unverified | not fetched | no |
| 18 | Baseten Model APIs | `POST /v1/chat/completions`; `logprobs`; `top_logprobs` 0–20; "support varies by model" | 2 | as row 12 | `Authorization: Bearer` or `Api-Key`; `BASETEN_API_KEY` | `https://inference.baseten.co/v1` | yes | GPT OSS 120B $0.10/$0.50; GLM-5.3-Flash $0.15/$0.50; DeepSeek V4.1 Flash $0.30/$1.20 (https://www.baseten.co/pricing) | not fetched | no (but hosts Mercury Decide, row 7) |
| 19 | Hugging Face Inference Providers | `POST /v1/chat/completions`; `logprobs`; **`top_logprobs` 0–5** | 2 | as row 12, ≤5 labels; provider-dependent | `Authorization: Bearer hf_…`; `HF_TOKEN` | `https://router.huggingface.co/v1` | yes | pass-through at provider rates, no markup (https://huggingface.co/docs/inference-providers/pricing) | not fetched | no |
| 20 | Novita AI | chat completions; `logprobs`; `top_logprobs` 0–20 | 2 | as row 12 | Bearer; `NOVITA_API_KEY` (convention) | not stated on page (unverified) | yes | not fetched | not fetched | no |
| 21 | Nebius Token Factory (ex-AI Studio) | `POST /v1/chat/completions`; `logprobs`; `top_logprobs` ≥ 0 (max 20 per a 400 example) | 2 | as row 12 | Bearer; `NEBIUS_API_KEY` | `https://api.tokenfactory.nebius.com/v1` | yes | not fetched | not fetched | no |
| 22 | Azure OpenAI (Foundry) | `{endpoint}/openai/v1/chat/completions`; `logprobs`; `top_logprobs` (range not stated in v1 reference) | 2 | as row 12 | `api-key` header or Entra Bearer | per-resource | yes | not fetched | not fetched | no |
| 23 | Writer | `POST /v1/chat`; `logprobs` bool; **no top-k request param** | 2 (degraded: chosen-token probability only) | noul ≈ P(chosen) only; choice/score not honest | Bearer; `WRITER_API_KEY` (convention) | `https://api.writer.com` | partly | not fetched; palmyra-x4/x5 deprecated 2026-12-14 | not fetched | no |
| 24 | Cohere | `POST /v2/chat`; `logprobs` bool, chosen tokens only | 2 (degraded) | as row 23 | Bearer; `COHERE_API_KEY` (convention) | `https://api.cohere.com` | no (Cohere wire) | not fetched; `/v1/classify` deprecated 2025-09-15 | not fetched | no |
| 25 | Anthropic | Messages API `POST /v1/messages` (no logprobs; `output_config` structured output) | 3 | self-reported confidence in a JSON field | **`x-api-key`** + `anthropic-version`; `ANTHROPIC_API_KEY` | `https://api.anthropic.com` | no | Haiku 5.5 $0.10/$0.50 (≤100k prompt); Sonnet 5.5 $2/$10; Opus 5.5 $4/$20; Fable 5.1 $10/$50 (https://platform.claude.com/docs/en/about-claude/pricing) | not fetched | no Jev-like product found. SDK text adapter `vidbyte/providers/anthropic.py` |
| 26 | xAI | `POST /v1/chat/completions`; `logprobs`/`top_logprobs` **silently ignored on grok-4.20 and newer** | 3 | self-reported | Bearer; `XAI_API_KEY` | `https://api.x.ai/v1` | yes | grok-4.7 $2/$6; grok-4.3 $1.25/$2.50 (https://docs.x.ai/developers/models) | not fetched | no. SDK text adapter `vidbyte/providers/xai.py` |
| 27 | Groq | `POST /openai/v1/chat/completions`; `logprobs`/`top_logprobs` "not yet supported by any of our models" | 3 | self-reported | Bearer; `GROQ_API_KEY` | `https://api.groq.com/openai/v1` | yes | not fetched | not fetched | no |
| 28 | SambaNova | chat completions; `logprobs`/`top_logprobs` "not yet supported … will be ignored" | 3 | self-reported | Bearer | not fetched | yes | not fetched | not fetched | no |
| 29 | Mistral | `POST /v1/chat/completions` (no logprobs params); Classifier Factory **deprecated** | 3 | self-reported | Bearer; `MISTRAL_API_KEY` | `https://api.mistral.ai/v1` | yes | only "Mistral Large $0.5/$1.5" visible (https://mistral.ai/pricing) | not fetched | no |
| 30 | AI21 | `POST /studio/v1/chat/completions` (no logprobs params) | 3 | self-reported | Bearer | `https://api.ai21.com` | partly | not fetched | not fetched | no |
| 31 | AWS Bedrock | Converse API (no logprobs found); InvokeModel `return_logprobs` only for Custom Model Import | 3 (2 only for imported models) | self-reported | SigV4 (not an API key) | regional | no | not fetched | not fetched | no hosted Jev-like product; AWS Strands Decider 2B is open weights only |

Honestly qualifying hosted providers (can return P(true) without self-report): rows 1–9 (class 1: nine distinct vendors or aggregators), row 10 (class 1 model whose probabilities need logprobs), rows 12–22 (class 2: eleven endpoints with top-k logprobs). That is well over ten. Rows 23–31 qualify weakly or not at all; §6 lists the near-misses and the reasons.

**Pricebook shape**: every class-1 row prices per input token with output free or zero; none of the qualifying providers prices per request or per classification. Second-order shapes the spec author should know: Cloudflare also meters in neurons; OpenRouter returns `usage.cost` in USD; DeepSeek has peak/off-peak and cache-hit/miss tiers; Hugging Face passes provider rates through; Mercury Decide has a free route with a daily request cap (unverified).

---

## 3. Per-provider detail

Each subsection: boolean (noul) call sketch, where the probability lives, model IDs and caps, how choice/score map, failure modes, and the doc URLs an implementer opens. All read 2026-10-10.

### 3.1 OpenAI Decisions API (class 1)
- **Boolean call**: `POST https://api.openai.com/v1/decisions`, `Authorization: Bearer $OPENAI_API_KEY`, body `{"model":"gpt-6-luna","input":"<state text>","questions":[{"type":"predicate","name":"q1","instructions":"Is the ticket urgent?"}]}`. `input` is a string or an array of `role:"user"` messages with `input_text` / `input_image` parts; images must be inline base64 data URLs (hosted URLs and `file_id` are not supported).
- **Probability field**: `answers[i].probability` (0–1) for `type:"predicate"`. Answers are an **array in question order**, each echoing `name`; an answer may be `type:"refusal"`.
- **Choice**: `{"type":"choice","name","instructions","choices":[{"value","description"}]}` → `choice`, `probabilities:[{value,probability}]`, `confidence`.
- **Score**: `{"type":"score","name","instructions","levels":[{"label","description"}]}` (lowest first, index 0) → `score` (probability-weighted index, may fall between levels), `probabilities:[{value,label,probability}]`, `confidence`.
- **Models and price**: `gpt-6-luna` only. $0.10 in; output, cache read, cache write $0; regional-processing and long-context multipliers apply (guide). Model page: 1,050,000 context, 922,000 max input, knowledge cutoff May 18, 2026; its endpoint table does **not** list `/v1/decisions` (§6).
- **Limits**: none on the official guide. Third parties claim up to 50 choices and 4 images (https://decisionsapi.pro/, unverified).
- **Failure modes**: `usage` not described in the guide; a GitHub issue reports live `usage.output_tokens` = 0 and model id `gpt-6-luna` with no versioned id (https://github.com/Bike4Mind/bike4mind/issues/4115). Standard OpenAI error envelope; 403 "not enabled for this user" was reported during the limited-preview window (https://www.eesel.ai/blog/decision-models). `x-ratelimit-*` headers exist on the API generally.
- **Docs**: https://developers.openai.com/api/docs/guides/decisions ; https://developers.openai.com/api/docs/pricing ; https://developers.openai.com/api/docs/models/gpt-6-luna. The reference URL Vercel links (`https://developers.openai.com/api/reference/resources/decisions/methods/create`) returned 404 on 2026-10-10.

### 3.2 Perplexity Decisions API (class 1)
- **Boolean call**: `POST https://api.perplexity.ai/v1/decisions`, `Authorization: Bearer <PERPLEXITY_API_KEY>`, body `{"model":"pplx-decider-v1.1-27b","state":"…","questions":{"defect":{"type":"noul","instructions":"Does the review report a product defect?"}}}`. Noul needs `instructions` or `criteria{true,false}` (at least one). `state` may be string/object/array; arrays may carry OpenAI-style `image_url` parts with PNG/JPEG/WebP data URLs.
- **Probability field**: `answers.defect.noul` (0–1). Response also has `model` and `usage{input_tokens, output_tokens}`.
- **Choice**: `criteria` map of 1–255 options (description or `null`) → `choice`, `confidence`, `probabilities{option: p}`.
- **Score**: `criteria` ordered array of 1–10 levels ("use at least two") → `score`, `confidence`, `legend{"0":…}`, `probabilities{"0":…}`; index-keyed exactly like TypeSafe.
- **Models and caps**: `pplx-decider-v1.1-27b` (default), `pplx-decider-v1-27b`. Input < 262,144 tokens; body ≤ 32 MiB; 1–128 questions; images ≤ 2,048 tiles of 32×32 px (≈1,000 tokens/MP).
- **Failure modes**: 400 (bad model, unknown field, over limit, http(s) image URL), 401 (missing key **or key sent in `x-api-key`**), 404 (trailing slash), 405, 413, 429 with `Retry-After`, 500/502/503, 504 after about a minute (body may be HTML). Error body `{"error":{"message","type","code","param"}}`; use `message`/`type`, not `code`. Rate limit 10 rps/org; headers `x-ratelimit-limit/remaining/used/reset`, `x-request-id` (absent on 401/404/504). Latency tests on the page: <2 s for a few hundred tokens, ~23 s near the input limit.
- **Docs**: https://docs.perplexity.ai/docs/decisions/quickstart ; https://docs.perplexity.ai/api-reference/decisions-post ; https://docs.perplexity.ai/getting-started/pricing ; weights https://huggingface.co/perplexity-ai/pplx-decider-v1-27b.

### 3.3 Microsoft-Decision-1 on Microsoft Foundry (class 1)
- **Boolean call**: `POST {AZURE_ENDPOINT}/providers/microsoft/v1/systemone`, headers `Authorization: Bearer <token>`, `Content-Type: application/json`, `Accept: application/json`; body `{"model":"<deployment name>","state":"…","questions":{"team":{"type":"choice","instructions":"…","criteria":{"billing":"…"}}}}`. The official sample shows only `choice`; the Command Line post lists "yes/no, multiple-choice, and rating options" plus rubric grading, so noul/score are expected but their exact wire is **unverified**.
- **Probability field**: by System One shape (`answers.<name>.noul` etc.); the official sample validates only `answers.team.type` and `.choice`.
- **Auth**: sample uses `DefaultAzureCredential` with scope `https://cognitiveservices.azure.com/.default`; prose mentions `FOUNDRY_BASE_URL` / `FOUNDRY_API_KEY`; the page itself says "Confirm the route and authentication header before running it".
- **Models and price**: catalog slug `microsoft-decision-1`; Qwen3.5-9B post-train, to be rebased on MAI/OpenAI models later; $0.042 in, output N/A (US/EU datazones). Status: "public preview" (tech community post) vs "GA on Oct 8, 2026" (OrcaRouter, secondary); 32,768-token context per secondary sources; no images, batch disabled (secondary).
- **Failure modes**: not documented; sample uses a 60 s client timeout.
- **Docs**: https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/introducing-microsoft-decision-1-in-microsoft-foundry-for-decision-and-classific/4562742 ; https://commandline.microsoft.com/microsoft-decision-1-model-foundry/ ; catalog https://ai.azure.com/catalog/models/microsoft-decision-1 (JS app; rendered "No Data Available" to the fetcher). OpenRouter `microsoft/microsoft-decision-1` returned 404 on 2026-10-10.

### 3.4 Cloudflare Workers AI Clef / Clef-flash (class 1)
- **Boolean call**: `POST https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/@cf/cloudflare/clef`, `Authorization: Bearer {CLOUDFLARE_AUTH_TOKEN}`, body `{"model":"clef-flash","state":"…","questions":{"urgent":{"type":"noul","instructions":"Is this request urgent?"}}}`. Question IDs: letters, digits, `_ . -`, ≤100 chars; 1–64 questions.
- **Probability field**: `answers.urgent.noul`. Response `{answers, model, usage}`; `usage` fields not described.
- **Choice/score**: `criteria` object / ordered array as System One; option and level caps not stated.
- **Extension**: optional `images[]` (≤4; PNG/JPEG/WebP; 4 MiB and 16 MP each; 8 MiB decoded total; 13 MiB body; each image capped at 1,024 tokens; remote URLs rejected).
- **Caps and truncation**: 65,536-token window shared by media and questions; **long `state` is silently truncated** ("Long text state is truncated to fit the model's token limit"); if media alone exceeds the window the request fails.
- **Pricing**: clef $0.240 in, clef-flash $0.038 in, no output charge; neurons 21,818 / 3,455 per M input; $0.011 per 1,000 neurons; 10,000 free neurons/day.
- **Failure modes**: not on the model page; no rate limits on the page.
- **Docs**: https://developers.cloudflare.com/workers-ai/models/clef/ ; https://developers.cloudflare.com/workers-ai/platform/pricing/ ; https://blog.cloudflare.com/clef-decision-models/ ; weights https://huggingface.co/Cloudflare/clef (Apache-2.0; local SGLang serve answers `/v1/systemone`; default `max_length` 16,384).

### 3.5 OpenRouter Decisions / System One (class 1 aggregator)
- **Boolean call**: `POST https://openrouter.ai/api/alpha/decisions` (or `POST https://openrouter.ai/api/v1/systemone` for TypeSafe-SDK users), `Authorization: Bearer $OPENROUTER_API_KEY`, body `{"model":"typesafe/jev-1.13","state":"…","questions":{"q":{"type":"noul","instructions":"…","criteria":{"true":"…","false":"…"}}}}`. **The API reference says noul `criteria` "must contain both `true` and `false` keys"**, stricter than TypeSafe where criteria are optional; the SDK's optionless noul (`_TypeSafePayloadBuilder.criteria` returns `None`) may be rejected here. Optional `provider` (routing prefs: `order`, `only`, `ignore`, `sort`, `max_price{prompt,completion,request,…}`, `zdr`, …), `session_id`/`user` (≤256 chars), `trace`.
- **Probability field**: `answers.q.noul`; choice → `choice`, `confidence`, `probabilities`; score → `score`, `confidence`, `legend`, `probabilities`. Response adds `id` (`gen-dec-…`), `provider`, and **`usage.cost` (USD)** beside `input_tokens`/`output_tokens`.
- **Models**: `typesafe/jev-1.13`, `~typesafe/jev-latest`, `typesafe/jev-router` (https://openrouter.ai/typesafe); `inception/mercury-decide-20260930`, `inception/mercury-decide:free`; third-party lists add `jaredpalmer/kev-4b`, `liquid/d1`, `upstage/solar-decide`, `respan/span-01`, `openai/gpt-6-luna-decisions` (unverified; every OpenRouter model page except the compare page returned 404 to the fetcher). Jev context 32,000 tokens on OpenRouter (guide). Jev sent to chat completions is rejected with 400 (guide).
- **Failure modes**: 400, 401 "Missing Authentication header", 402 "Insufficient credits", 403 management-key, 404, 413 "payload exceeds size limits", 429, 500, 502 provider error, 503, 524 "Request timed out", 529 provider overloaded.
- **Docs**: https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request ; https://openrouter.ai/docs/guides/community/jev ; https://openrouter.ai/docs/client-sdks/go/sdks/systemone/README ; https://openrouter.ai/docs/api-reference/parameters (chat `top_logprobs` 0–20).

### 3.6 Liquid AI d1 (class 1)
- **Boolean call**: `POST https://api.liquid.ai/decisions/v1/systemone`, `Authorization: Bearer $LIQUID_API_KEY`, body `{"model":"d1","state":"…","questions":{"q":{"type":"noul","instructions":"…"}}}`; optional `images[]` (base64 data URLs or `{content_type, base64}`; ≤8; body < 4.5 MB; ≤10,000 32×32 patches; tokens `ceil(patches×1.5)`). `d1:free` is text-only.
- **Probability field**: `answers.q.noul`; choice/score as System One; `usage.output_tokens` "Always `0`".
- **Models**: `d1` hosted; weights d1-3B (LFM2.5-VL-3B) and d1-omni-600M listed; pricing not on the docs page.
- **Failure modes**: not documented on the fetched pages.
- **Docs**: https://docs.liquid.ai/lfm/models/d1 ; https://docs.liquid.ai/lfm/models/decision-models.

### 3.7 Inception Mercury Decide via Baseten and OpenRouter (class 1)
- **Boolean call (Baseten)**: `POST https://inference.baseten.co/v1/decisions`, **`Authorization: Api-Key <BASETEN_API_KEY>`**, body `{"model":"inception/mercury-decide","state":"…","questions":{"q":{"type":"noul","instructions":"…"}}}` → `answers.q.noul`; choice/score as System One (the page calls noul "Checks" but uses the `noul` type name). Labelled a "Partner Model"; pricing not on page.
- **Via OpenRouter**: `inception/mercury-decide-20260930` ($0.02 in per search snippet) and `:free` (200 req/day per snippet); context 65,536 or 32,768 depending on listing (§6).
- **Official Inception docs**: none found; `https://inceptionlabs.ai/llms.txt` lists only Mercury 2 pricing ($0.25/$0.75).
- **Docs**: https://www.baseten.co/library/mercury-decide/ ; https://docs.baseten.co/reference/inference-api/chat-completions (auth schemes) ; https://openrouter.ai/inception/mercury-decide-20260930 (404 to the fetcher).

### 3.8 meraGPT Decider 1 (class 1)
- **Boolean call**: `POST https://meragpt.com/v1/systemone`, `Authorization: Bearer $MERAGPT_API_KEY`, body `{"model":"sd-1","state":{…},"questions":{"q":{"type":"noul","instructions":"…"}}}`; score takes a `criteria` list. "speaks the System One schema, so the typesafe-sdk works against it unchanged".
- **Unverified**: $0.03 in (https://systemonemodels.org/), 4,096-token request cap and 10-label choice cap (https://github.com/AnotiaWang/awesome-decision-models), response shape, rate limits (linked `/docs/errors` not fetched).
- **Docs**: https://meragpt.com/docs.

### 3.9 Vercel AI Gateway decisions (class 1 aggregator)
- **Boolean call**: `POST https://ai-gateway.vercel.sh/v1/decisions`, `Authorization: Bearer $AI_GATEWAY_API_KEY`, OpenAI Decisions body with `model:"openai/gpt-6-luna-decisions"`. Answers in question order tagged by `name`, as OpenAI. $0.10 in; output not listed; context 1,050,000.
- **Docs**: https://vercel.com/changelog/openai-decisions-api-now-available-on-ai-gateway (dated Oct 7, 2026) ; https://vercel.com/ai-gateway/models/gpt-6-luna-decisions.

### 3.10 Together AI Tev1-4B-experimental (class 1 model, chat wire)
- **Call**: `POST https://api.together.ai/v1/chat/completions`, `Authorization: Bearer $TOGETHER_API_KEY`, `model:"together/Tev1-4B-experimental"`, `temperature:0`, `max_tokens:8`, `chat_template_kwargs:{"enable_thinking":false}` (caller must set these; "not injected automatically"). User message is a JSON string `{state, question, options:[{label:"A", key, description}, …]}` with 2–24 options; system prompt "Select exactly one listed option. Return only its letter". The model returns one letter.
- **Probability**: none in the documented output. Together's chat API accepts `logprobs` (integer 0–20) and returns `top_logprobs`; whether Tev1 honours it is **unverified**. Noul = two options; score = ordered options (≤24).
- **Pricing and status**: $0.04 in / free out; 32.8K context; 4.7B params; license "being finalized before public conversion"; "calibration … not comprehensively evaluated"; "Experimental release intended for evaluation".
- **Docs**: https://www.together.ai/models/tev1-4b-experimental ; https://huggingface.co/togethercomputer/Tev1-4B-experimental ; https://docs.together.ai/reference/chat-completions-1 ; OpenRouter mirror `togethercomputer/tev1-4b-experimental` (page 404 to the fetcher).

### 3.11 Self-hosted System One servers (class 1, own hardware)
All answer `POST /v1/systemone` with the TypeSafe body and `{model, answers, usage{input_tokens,output_tokens}}`:
- **Laya** (Convai Innovations; 421M ModernBERT-large root, 322M multilingual; Apache-2.0): `pip install "laya[serve]"`, `laya-serve` binds `0.0.0.0:8000`; no auth unless `LAYA_API_KEY` is set (then `Authorization: Bearer`). 512-token English context (multilingual 1,024 default, `max_len=8192`). Malformed question → 422. Known issues: noul label bias (#156), `act_probability` unusable (#185), ships over-confident (mean ECE 0.466 → 0.081 after per-type temperature refit). https://huggingface.co/convaiinnovations/laya ; https://layaai.org/.
- **Strands Decider 2B** (AWS Strands Labs; Apache-2.0): `pip install strands-decider`; `strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --port 8000`; response adds `latency_ms`; no auth. https://github.com/strands-labs/strands-decider ; https://strandsagents.com/blog/introducing-strands-decider/ (Oct 1, 2026).
- **H2O-Lightning-4B** (H2O.ai; Apache-2.0): stock vLLM 0.30.0 + `h2o_lightning_shim.py`; decision endpoint `/v1/systemone` (shim on :8741 in the reported setup). https://huggingface.co/h2oai/h2o-lightning-4b.
- **Kev** (Jared Palmer; Apache-2.0; 0.8B/4B/9B, 27B per one source): `/v1/systemone`, `kev-latest` model name; Kev-4B listed on OpenRouter (`jaredpalmer/kev-4b`, 404 to the fetcher). Secondary: https://thenewstack.io/kev-skips-text-generation/.
- **PostHog Jeeves** (9B, reasons before deciding; license reported as MIT and as Apache-2.0 by different sources): System One request format; secondary only (https://www.eesel.ai/blog/posthog-jeeves).
- **Bespoke Nimble 9B v2** (Apache-2.0 adapter on Qwen3.5-9B): Python `ParallelScorer`; no HTTP endpoint documented; "isn't deployed by any Inference Provider". https://huggingface.co/bespokelabs/Bespoke-Nimble-9B-v2.
- **Clef weights** (SGLang, `/v1/systemone`; see 3.4) and **pplx-decider weights** (see 3.2).
- LiteLLM's gateway maps `strands_decider/…`, `hosted_vllm/…` (choice only), `/laya/v1/systemone`, `/bespoke/v1/systemone` (https://docs.litellm.ai/docs/decisions.md).

### 3.12 OpenAI Chat Completions with logprobs (class 2)
- **Boolean call**: `POST https://api.openai.com/v1/chat/completions`, body `{"model":"gpt-6-sol","reasoning_effort":"none","messages":[… state + "Answer yes or no." …],"max_tokens":1,"logprobs":true,"top_logprobs":20}`.
- **Probability field**: `choices[0].logprobs.content[0].top_logprobs[] {token, logprob, bytes}`; P(true) is derived from the "yes"/"no" entries, renormalised over the two. `top_logprobs` is "an integer between 0 and 20"; `logprobs` must be true. The reference's logprobs example uses `gpt-6-sol` with `reasoning_effort:"none"`; the page says parameter support "can differ depending on the model used", especially for reasoning models; the reasoning guide does not list logprobs among unsupported parameters; the gpt-6-luna model page's feature list does not mention logprobs.
- **Choice/score**: single-token labels (e.g. `A`–`T`) at one position, ≤20 entries; Jev's 255 choice options cannot be matched, its 10 score levels fit.
- **Responses API**: `include:["message.output_text.logprobs"]` and a `top_logprobs` request field exist; the range was not visible in the fetched chunk.
- **Failure modes**: standard OpenAI errors; tier RPM/TPM (gpt-6-luna: Build 5,000 RPM / 2M TPM, Launch 10,000 / 10M, Grow 30,000 / 180M).
- **Docs**: https://developers.openai.com/api/docs/api-reference/chat/create ; https://developers.openai.com/api/docs/pricing ; https://developers.openai.com/api/docs/api-reference/responses/create.

### 3.13 Google Gemini API and Vertex AI logprobs (class 2, deprecated for 3.x)
- **Boolean call**: `POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=$GEMINI_API_KEY` with `generationConfig:{"responseLogprobs":true,"logprobs":20,"maxOutputTokens":1}`.
- **Probability field**: `candidates[0].logprobsResult.topCandidates[0].candidates[]{token, tokenId, logProbability}` (sorted descending); also `chosenCandidates[]` and `logProbabilitySum`. `logprobs` is "an integer value in the range of 1-20" and requires `responseLogprobs` (Vertex reference; Google blog of July 16, 2025).
- **Deprecation**: "The `responseLogprobs` parameter is deprecated for Gemini 3.x models and will soon be completely deprecated." Same note for `logprobs` (https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/inference). The Gemini API reference (ai.google.dev) did not surface its GenerationConfig text to the fetcher; the field names are confirmed by the Vertex schema and SDK docs.
- **Auth**: Gemini API examples use `?key=` / `GEMINI_API_KEY`; Vertex uses OAuth Bearer. `x-goog-api-key` was not seen on the fetched page (unverified).
- **Docs**: https://ai.google.dev/api/generate-content ; https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/inference ; https://developers.googleblog.com/unlock-gemini-reasoning-with-logprobs-on-vertex-ai/ ; https://ai.google.dev/gemini-api/docs/pricing.

### 3.14 DeepSeek (class 2)
- `POST https://api.deepseek.com/chat/completions`, `Authorization: Bearer $DEEPSEEK_API_KEY`, `logprobs:true`, `top_logprobs` ≤ 20; models `deepseek-flash`, `deepseek-v4-pro` (legacy `deepseek-v4-flash*` names still accepted, served by V4.1-Flash). Response has `logprobs` and `reasoning_content`; which models return logprobs is not stated. Pricing has off-peak/peak and cache-hit/miss tiers (table row 14): a pricebook with one input rate under-prices peak hours.
- Docs: https://api-docs.deepseek.com/api/create-chat-completion ; https://api-docs.deepseek.com/quick_start/pricing ; https://api-docs.deepseek.com/.

### 3.15 Together AI chat (class 2)
- `POST https://api.together.ai/v1/chat/completions` (alternate `https://api-inference.together.ai/v2`), `Authorization: Bearer $TOGETHER_API_KEY`. **`logprobs` is an integer 0–20** ("top k tokens to return log probabilities for at each generation step"); no `top_logprobs` request parameter. Response `choices[].logprobs{token_ids[], tokens[], token_logprobs[], top_logprobs{}}` (legacy shape); streaming chunks type `logprobs` as a number.
- Docs: https://docs.together.ai/reference/chat-completions-1 ; https://www.together.ai/pricing.

### 3.16 Fireworks AI (class 2)
- `POST https://api.fireworks.ai/inference/v1/chat/completions`, Bearer. `logprobs` int|bool|null; `top_logprobs` 0..deployment `--max-logprobs` (**5 by default**). Two response shapes: legacy `LogProbs{tokens, token_logprobs, top_logprobs, text_offset}` and `NewLogProbs{content[]{token, logprob, sampling_logprob, bytes, token_id, text_offset, top_logprobs[]}}`.
- Pricing: official page shows no serverless per-token table; third-party tier numbers unverified.
- Docs: https://docs.fireworks.ai/api-reference/post-chatcompletions ; https://fireworks.ai/pricing.

### 3.17 Cerebras (class 2)
- `POST https://api.cerebras.ai/v1/chat/completions`, Bearer; `logprobs` bool (default false), `top_logprobs` 0–20 (requires `logprobs:true`); model ids on the page `qwen-3.8-27b`, `kimi-k2.7-code`, `gpt-oss-120b`, `gemma-4-31b`. Pricing table did not render; third-party $0.35/$0.75 for gpt-oss-120b unverified.
- Docs: https://inference-docs.cerebras.ai/api-reference/chat-completions ; https://www.cerebras.ai/pricing.

### 3.18 Baseten Model APIs (class 2; also hosts Mercury Decide)
- `POST https://inference.baseten.co/v1/chat/completions`, `Authorization: Bearer $BASETEN_API_KEY` or `Authorization: Api-Key <key>`; `logprobs` bool, `top_logprobs` 0–20, "Log probability support varies by model"; `n` must be 1. Self-deployed models use `https://model-{id}.api.baseten.co/v1/chat/completions`.
- Docs: https://docs.baseten.co/reference/inference-api/chat-completions ; https://www.baseten.co/pricing.

### 3.19 Hugging Face Inference Providers router (class 2)
- `POST https://router.huggingface.co/v1/chat/completions`, `Authorization: Bearer hf_…` (token needs "Inference Providers" permission); `logprobs` bool; **`top_logprobs` "between 0 and 5"**; response `choices[].logprobs.content[]{token, logprob, top_logprobs[]}`. Billing is pass-through at provider rates with no markup; `X-HF-Bill-To` for org billing. The provider behind a model varies (`baseten`, `cerebras`, `groq`, `together`, …), so logprobs support is per provider.
- Docs: https://huggingface.co/docs/inference-providers/tasks/chat-completion ; https://huggingface.co/docs/inference-providers/pricing.

### 3.20 Novita AI (class 2)
- Chat completions: `logprobs` bool (default false), `top_logprobs` "0 <= x <= 20"; `Authorization: Bearer {{API Key}}`. Base URL not on the page (unverified). Docs: https://docs.novita.ai/api-reference/model-apis-llm-create-chat-completion.

### 3.21 Nebius Token Factory (class 2)
- `POST https://api.tokenfactory.nebius.com/v1/chat/completions`, `Authorization: Bearer $NEBIUS_API_KEY`; `logprobs` bool; `top_logprobs` integer ≥ 0 (schema sets no maximum; a 400 example says "Requested sample logprobs of 100, which is greater than max allowed: 20"). Product renamed from "Nebius AI Studio" (the old docs URL redirects to docs.tokenfactory.nebius.com).
- Docs: https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion.md ; https://docs.tokenfactory.nebius.com/.

### 3.22 Azure OpenAI in Microsoft Foundry (class 2)
- Server `{endpoint}/openai/v1` (v1 data plane); `api-key` header or Entra `Authorization: Bearer`; chat `logprobs` boolean|null; `top_logprobs` integer|null with no range text in the v1 reference (OpenAI's own range is 0–20). Docs: https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/chat?view=rest-microsoft-foundry-v1 ; https://learn.microsoft.com/en-us/azure/ai-foundry/openai/reference.

### 3.23 Writer and Cohere (class 2, degraded)
- **Writer** `POST https://api.writer.com/v1/chat`, Bearer; `logprobs` bool only; response `logprobs_token{token, logprob, top_logprobs[]}` exists but there is no request-side top-k; models `palmyra-x5`, `palmyra-x6` (`palmyra-x4`/`x5` deprecated 2026-12-14). https://dev.writer.com/api-reference/completion-api/chat-completion.
- **Cohere** `POST https://api.cohere.com/v2/chat`, Bearer; `logprobs` bool → `logprobs[]{token_ids, text, logprobs}` for chosen tokens only; `command-a-plus-05-2026`. `/v1/classify` deprecated 2025-09-15 and classify fine-tuning retired. https://docs.cohere.com/reference/chat ; https://docs.cohere.com/docs/deprecations.
- Honest mapping: only P(chosen token) is available; P(true) is exact only when the chosen token is the "yes" token; choice/score distributions cannot be recovered.

### 3.24 Class 3 providers (self-reported confidence only)
- **Anthropic** Messages API `POST https://api.anthropic.com/v1/messages`, headers `x-api-key` and `anthropic-version`; request params include `output_config`, `tools`, `thinking`; no logprobs parameter or field. https://platform.claude.com/docs/en/api/messages ; pricing https://platform.claude.com/docs/en/about-claude/pricing.
- **xAI** `https://api.x.ai/v1`: "`logprobs` and `top_logprobs` are not supported by models `grok-4.20` and newer. These fields will be silently ignored if set." https://docs.x.ai/developers/models.
- **Groq** `https://api.groq.com/openai/v1`: `logprobs`/`top_logprobs` "not yet supported by any of our models". https://console.groq.com/docs/api-reference.
- **SambaNova**: `logprobs`/`top_logprobs` listed as not yet supported and ignored (https://docs-prod.sambanova.ai/docs/en/features/openai-compatibility via search; the endpoint reference page returned 404).
- **Mistral** `https://api.mistral.ai/v1/chat/completions`: no logprobs params; Classifier Factory "deprecated and is no longer actively supported" ($4 minimum fine-tune fee, $2/month storage); moderation page 404. https://docs.mistral.ai/api/ ; https://docs.mistral.ai/capabilities/finetuning/classifier_factory.
- **AI21** `https://api.ai21.com/studio/v1/chat/completions`, `jamba-large` / `jamba-mini`: no logprobs params. https://docs.ai21.com/reference/jamba-1-6-api-ref.
- **AWS Bedrock**: `return_logprobs: true` in InvokeModel only for Custom Model Import (July 31, 2025); no Converse logprobs found; SigV4 auth. https://aws.amazon.com/blogs/machine-learning/unlock-model-insights-with-log-probability-support-for-amazon-bedrock-custom-model-import.

---

## 4. Groupings (wire shapes)

Grouped by what an HTTP client has to send and parse. Not a design; the spec author decides how many adapters this implies.

**A. System One wire (TypeSafe's body and answers, `noul/choice/score`)**
Members: TypeSafe `/v1/systemone`; Perplexity `/v1/decisions`; Microsoft Foundry `/providers/microsoft/v1/systemone`; Cloudflare `/ai/run/@cf/cloudflare/clef` (+ `model` in body, + `images`); OpenRouter `/api/v1/systemone` and `/api/alpha/decisions` (+ `provider`, `session_id`, `usage.cost`; noul criteria mandatory); Liquid `/decisions/v1/systemone` (+ `images`, `output_tokens` = 0); Baseten `/v1/decisions` for Mercury Decide (`Api-Key` auth); meraGPT `/v1/systemone`; every self-hosted server in 3.11 (Laya, Strands, H2O-Lightning, Kev, Jeeves, Clef, pplx-decider via vLLM/SGLang).
What varies inside the group: path, base URL, auth header name (`Bearer` vs `Api-Key` vs Azure Entra token), whether `model` is required, image extensions, caps (questions 64/128, options 255, levels 10, context 32k/64k/262k/4,096), and silent truncation (Cloudflare). Score probabilities are index-keyed everywhere in the group, matching the SDK's existing `_score` normalizer.

**B. OpenAI Decisions wire (`input` + `questions[]` with `predicate/choice/score`; answers array; `probability` scalar; `probabilities` arrays of objects; `refusal` type)**
Members: OpenAI `/v1/decisions`; Vercel AI Gateway `/v1/decisions`. LiteLLM translates between A and B (https://docs.litellm.ai/docs/decisions.md): text parts of `input` join into `state`; OpenAI requires `instructions` on every question and at least 2 choices or levels.

**C. OpenAI-compatible chat completions with `logprobs: bool` + `top_logprobs: int`**
Members and caps: OpenAI (0–20), DeepSeek (≤20), Cerebras (0–20), Baseten (0–20, model-dependent), Novita (0–20), Nebius (≤20), Azure OpenAI (range unstated), Hugging Face router (0–5), Fireworks (0–5 by default; `logprobs` may also be an int). Response path `choices[0].logprobs.content[0].top_logprobs[]`. The SDK's `vidbyte/providers/compatible.py` already speaks this wire for text.
Sub-variant **C′**: Together (`logprobs` integer 0–20, legacy `{tokens, token_logprobs, top_logprobs}` response); Fireworks' legacy shape is the same.

**D. Gemini `generateContent` logprobs** (`responseLogprobs` + `logprobs` 1–20; `logprobsResult.topCandidates[].candidates[]`)
Members: Gemini API, Vertex AI. Deprecated for Gemini 3.x; usable on 2.5-generation models while they last.

**E. Chosen-token-only logprobs** (no top-k): Writer `/v1/chat`, Cohere `/v2/chat`. Only P(chosen) is observable.

**F. Structured-output / self-reported confidence** (no logprobs): Anthropic Messages (`x-api-key`), xAI (grok-4.20+), Groq, SambaNova, Mistral, AI21, Bedrock Converse.

**G. Decision fine-tune behind a chat wire**: Together Tev1 (letter output; probabilities only through C′ logprobs, unverified).

Answer-kind mapping per group: A and B deliver all three kinds natively (B renames noul → predicate and keys answers by position). C/C′/D deliver noul from two label tokens and choice/score from ≤N single-token labels where N is the provider's top-k cap (20, or 5 for HF/Fireworks defaults); TypeSafe's confidence formulas in §1 are documented and could be recomputed from any distribution. E delivers noul only approximately. F delivers whatever the model reports.

---

## 5. What the frontier labs shipped

Dated evidence for the user's claim that "frontier labs" have copied Jev. Jev itself: early access announced mid-September 2026 (the-decoder, Sep 16, 2026; eesel.ai says Sep 15). Order is by launch date.

| Lab / company | Jev-like product? | Date | Evidence |
|---|---|---|---|
| Convai Innovations (startup) | Laya, open System One model, `/v1/systemone` | Sep 18, 2026 (secondary; dates conflict) | https://layaai.org/ ; https://huggingface.co/convaiinnovations/laya |
| Jared Palmer (individual) | Kev 0.8B/4B/9B, Jev-compatible | Sep 20–25, 2026 (secondary, conflicting) | https://thenewstack.io/kev-skips-text-generation/ |
| Fastino Labs (startup) | GLiNER2.5-Decide, 340M open weights; hosted via Fastino API (endpoint/pricing unverified) | Sep 24, 2026 (MarkTechPost) | https://www.marktechpost.com/2026/09/24/fastino-releases-gliner2-5-decide-a-340m-open-weight-decision-model-that-runs-on-cpu/ |
| PostHog | Jeeves 9B, Jev-compatible, reasons first | Sep 29, 2026 (secondary) | https://www.eesel.ai/blog/posthog-jeeves |
| **OpenAI** | **Decisions API, `/v1/decisions`, gpt-6-luna**: predicate/choice/score, input-only pricing $0.10/M, output free, ~10× faster than Responses | Limited preview at DevDay Sep 29, 2026; public beta Oct 6–7, 2026 | https://developers.openai.com/api/docs/guides/decisions ; https://the-decoder.com/openai-launches-decisions-api-that-reduces-complex-evaluations-to-yes-no-or-pick-one/ (Oct 7, 2026); https://vercel.com/changelog/openai-decisions-api-now-available-on-ai-gateway (Oct 7, 2026) |
| Inception Labs | Mercury Decide, System One schema; on OpenRouter and Baseten | Sep 30, 2026 (listings) | https://www.baseten.co/library/mercury-decide/ |
| **Cloudflare** | Clef 27B / Clef-flash 9B on Workers AI, "fully Jev-API compatible", Apache-2.0 weights | Oct 1, 2026 | https://blog.cloudflare.com/clef-decision-models/ |
| **Perplexity** | Decisions API, pplx-decider-v1(.1)-27b, Jev body, $0.02/M in | Oct 1, 2026 (secondary date; official docs undated) | https://docs.perplexity.ai/docs/decisions/quickstart |
| **Amazon (AWS Strands Labs)** | Strands Decider 2B, open weights, local `/v1/systemone`; **no hosted API, not on Bedrock** | Oct 1, 2026 | https://strandsagents.com/blog/introducing-strands-decider/ |
| Together AI | Tev1-4B/0.8B experimental decision fine-tunes (letter output via chat) | undated on official pages | https://www.together.ai/models/tev1-4b-experimental |
| **Microsoft** | Microsoft-Decision-1 in Foundry, `/providers/microsoft/v1/systemone`, $0.042/M in, output free | Oct 8–9, 2026 (public preview per Microsoft; "GA Oct 8" per secondary) | https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/introducing-microsoft-decision-1-in-microsoft-foundry-for-decision-and-classific/4562742 ; https://commandline.microsoft.com/microsoft-decision-1-model-foundry/ |
| Liquid AI | d1 hosted decision model, System One wire | undated on docs | https://docs.liquid.ai/lfm/models/d1 |
| meraGPT, Upstage (Solar Decide), Respan (Span-01), Nace.AI (Drex), Hanzo (Kai), Celeris | named as hosted System One APIs by third-party hubs | — | https://github.com/AnotiaWang/awesome-decision-models ; https://systemonemodels.org/ (unverified except meraGPT docs) |
| **Google DeepMind** | **None found.** No Gemini decision product; Gemini logprobs deprecated for 3.x | — | searches on 2026-10-10 returned nothing; https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/inference |
| **Anthropic** | **None found.** No decision product; Messages API has no logprobs | — | https://platform.claude.com/docs/en/api/messages |
| **Meta** | **None found** | — | search returned only Llama-on-Bedrock pages |
| **Mistral** | **None found**; Classifier Factory deprecated; moderation is fixed-category | — | https://docs.mistral.ai/capabilities/finetuning/classifier_factory |
| **xAI** | **None found**; logprobs removed on grok-4.20+ | — | https://docs.x.ai/developers/models |
| **Cohere** | **None**; `/v1/classify` deprecated 2025-09-15 | — | https://docs.cohere.com/docs/deprecations |
| **Amazon Bedrock** (hosted) | **None found** | — | search returned catalog/pricing pages only |

Verdict: the claim holds for OpenAI (official docs), Microsoft (official posts), Perplexity (official docs), Cloudflare (official blog and docs), and Amazon only in open-weights form (Strands Decider). It does not hold for Google DeepMind, Anthropic, Meta, Mistral, xAI, or Cohere as of 2026-10-10. Independent cross-model note: for the same text and predicate, gpt-6-luna returned 0.50 and jev-1.13.0 returned 0.82, so probabilities are not comparable across vendors (https://github.com/Bike4Mind/bike4mind/issues/4115, via summary; the page itself returned 403 to the fetcher).

---

## 6. Unverified and contradictory facts

**Contradictions**
1. Perplexity price: official docs say **$0.02** per 1M input (quickstart, API reference, pricing page); the launch tweet and several articles say $0.04 (https://x.com/perplexitydevs/status/2105725598882832414 via search; https://www.seikodigital.com/blog/perplexity-decisions-api). The docs may reflect a cut with v1.1; trust the docs and re-check at implementation time.
2. Cloudflare clef-flash price: official pricing page **$0.038**/M; eesel.ai said $0.09/M.
3. Microsoft-Decision-1 status: "public preview" (Microsoft tech community, Oct 9) vs "generally available on October 8, 2026" (OrcaRouter) vs catalog "GA" (search snippet). Pricing: $0.042 (Microsoft) vs $0.42 (GuruFocus, likely a typo).
4. Microsoft-Decision-1 auth: official sample uses Entra Bearer; prose mentions `FOUNDRY_API_KEY`; the page tells readers to confirm the route and header.
5. OpenAI Decisions availability: "public beta, GA in coming weeks" (official guide) vs "limited preview, standard key gets 403" (eesel.ai, written before Oct 6). The gpt-6-luna model page's endpoint table omits `/v1/decisions` while the guide says only gpt-6-luna is supported (also reported by https://mixed-news.com/en/openai-decisions-api-beta-gpt-6-luna-endpoint-table/).
6. Jev launch date: Sep 15, 2026 (eesel.ai), "has introduced" in a Sep 16, 2026 article (the-decoder), vs "Oct 9, 2026" timestamp on TypeSafe's own launch post (likely an edit).
7. Mercury Decide context: 65,536 vs 32,768 tokens across OpenRouter listings; paid price "$0.04 struck through to $0.02".
8. Kev sizes and dates: 0.8B/4B/9B (The New Stack) vs four sizes up to 27B (pyshine); released Sep 20 vs Sep 25, 2026.
9. PostHog Jeeves license: MIT vs Apache-2.0 depending on source.
10. OpenAI chat `top_logprobs` cap: current reference says 0–20; older mirrors say 0–5. The current value is 20.
11. Tev1 pricing: $0.04/M on Together's own pages vs $0.042 on systemonemodels.org.

**Unverified (no primary source reached)**
- OpenAI Decisions limits (max questions, choices, levels, images) and `usage` schema; its API reference URL 404s. Rate limits for `/v1/decisions`.
- OpenRouter per-model prices and context for `inception/mercury-decide*`, `jaredpalmer/kev-4b`, `liquid/d1`, `upstage/solar-decide`, `respan/span-01`, `openai/gpt-6-luna-decisions`, `togethercomputer/tev1-4b-experimental`: every model page returned 404 to the fetcher; only the Jev compare page and the API reference loaded. The public models JSON (`/api/v1/models`) returned ten entries without pricing.
- Microsoft-Decision-1 on OpenRouter (`microsoft/microsoft-decision-1`): 404.
- Liquid d1 price ($0.04/M per systemonemodels.org), caps, rate limits.
- meraGPT price ($0.03/M), 4,096-token cap, 10-label cap, response shape.
- Mercury Decide official pricing and endpoint on Inception's own API; Baseten pricing for it.
- Fastino hosted GLiNER2.5-Decide: endpoint, auth, price ($0.03 vs $0.042 across aggregators).
- Upstage Solar Decide ($0.1/M), Respan Span-01 ($0.02/M, noul-only), Nace.AI Drex ($0.05/M), Hanzo Kai ($0.021/M), Celeris-1 ($0.04/M), Cloudflare "Clef-omni" ($0.15/M): all from https://systemonemodels.org/ only.
- Vercel AI Gateway output price for `gpt-6-luna-decisions`; whether `typesafe-ai/jev` and `liquid/d1` are on the gateway.
- Whether Together's `logprobs` works on Tev1; Tev1 license.
- Gemini API (ai.google.dev) GenerationConfig text for `logprobs` (confirmed only via Vertex); `x-goog-api-key` header.
- Azure OpenAI `top_logprobs` maximum (v1 reference shows no range).
- Novita base URL; Nebius, Novita, Cerebras, Fireworks, Azure, Groq, SambaNova, Mistral (small models), AI21, Writer, Cohere pricing (not fetched or page did not render).
- Bedrock Converse logprobs (absence inferred from search, not from the API reference).
- Jina classifier pricing rate and response for the full distribution (see near-misses).
- Atla Selene, Patronus Evaluate, Galileo Luna-2, Haize Labs, Flow AI: no 2026 primary evidence of a probability-returning public API.
- Voyage AI was **not searched** (budget went to the decision-model wave); it is an embeddings/rerank vendor with no classify product known to this scout.

**Near-misses (dropped from the qualifying list, with reason)**
- **Jina AI Classifier** `POST https://api.jina.ai/v1/classify` (Bearer `JINA_API_KEY`; `model`, `input[]`, `labels[]`; zero-shot ≤256 labels, few-shot ≤16; 1,024 inputs/request; 8,192 tokens/input; token-based pricing, rate not listed; rate limits 100/500/5,000 RPM by tier): returns `prediction` + `score` per input where score is a softmax over cosine similarities between input and label embeddings. It scores label similarity, not the truth of a question about a context, so it cannot honestly answer "is X true of this state"; the documented response shows only the top label. https://jina.ai/classifier ; https://jina.ai/news/jina-classifier-for-high-performance-zero-shot-and-few-shot-classification.
- **Cohere Classify**: deprecated 2025-09-15; classify fine-tuning retired. https://docs.cohere.com/docs/deprecations.
- **Mistral Classifier Factory**: deprecated. Mistral moderation: fixed category list (page 404 on 2026-10-10).
- **Judge/eval vendors** (Atla, Patronus, Galileo Luna-2, Haize, Flow AI): pass/fail or rubric scores for RAG/safety, no documented calibrated P(true) for arbitrary questions; Luna-2 is enterprise-only; no 2026 primary docs found.
- **Not Diamond, Martian**: model routers, not decision models.
- **Chrome DecisionModel API**: browser-side, behind a flag (https://dejan.ai/blog/chrome-decisions-api-decisionmodel/); not a provider.
- **xAI, Groq, SambaNova, Mistral, AI21, Anthropic, Bedrock**: class 3 only (no logprobs).
- **Writer, Cohere chat**: chosen-token logprobs only.

---

## 7. Sources

All read 2026-10-10. Format: URL — what it supported. "(failed)" = did not load; "(partial)" = truncated.

**TypeSafe**
- https://docs.typesafe.ai/api.md — endpoint, auth, body, answer shapes, errors.
- https://docs.typesafe.ai/models.md — jev-1.13.0, aliases, $0.042/M, context, 100K tok/s and 80 rps.
- https://docs.typesafe.ai/confidence.md — confidence formulas, no calibration claim.
- https://typesafe.ai/blog/introducing-system-one-models-and-jev — launch claims, RLCD, 255 cardinality, Oct 9 timestamp.
- https://the-decoder.com/former-openai-researcher-builds-an-ai-model-that-judges-options-instead-of-writing-text/ — Sep 16, 2026 article; founder Diogo Almeida; waitlist.
- https://openrouter.ai/blog/insights/what-is-jev/ (search snippet) — 1,200 rpm secondary figure.

**OpenAI**
- https://developers.openai.com/api/docs/guides/decisions — Decisions API full shape, pricing, beta status.
- https://developers.openai.com/api/docs/pricing — gpt-6 family prices.
- https://developers.openai.com/api/docs/models/gpt-6-luna — context, rate tiers, endpoint table without decisions.
- https://developers.openai.com/api/docs/api-reference/chat/create (partial) — logprobs/top_logprobs 0–20, gpt-6-sol example.
- https://developers.openai.com/api/docs/api-reference/responses/create (partial) — include logprobs option.
- https://developers.openai.com/api/docs/guides/reasoning — no logprobs restriction text.
- https://developers.openai.com/api/docs/api-reference/decisions (overview only); https://developers.openai.com/api/reference/resources/decisions/methods/create (failed 404); https://platform.openai.com/docs/api-reference/chat/create (failed 403).
- https://the-decoder.com/openai-launches-decisions-api-that-reduces-complex-evaluations-to-yes-no-or-pick-one/ — Oct 7, 2026 beta coverage.
- https://vercel.com/changelog/openai-decisions-api-now-available-on-ai-gateway — Oct 7, 2026; gateway model id and format.
- https://vercel.com/ai-gateway/models/gpt-6-luna-decisions — $0.10 in, 1,050,000 context.
- https://decisionsapi.pro/ — third-party; 50 choices / 4 images claims (unverified).
- https://github.com/Bike4Mind/bike4mind/issues/4115 (failed 403; content via search summary) — cross-model 0.50 vs 0.82, usage.output_tokens 0.
- https://mixed-news.com/en/openai-decisions-api-beta-gpt-6-luna-endpoint-table/ (search snippet) — endpoint-table omission.

**Perplexity**
- https://docs.perplexity.ai/docs/decisions/quickstart — endpoint, auth quirk, limits, rate limits, errors, latency, $0.02.
- https://docs.perplexity.ai/api-reference/decisions-post — schema, example response, error table.
- https://docs.perplexity.ai/getting-started/pricing (partial) — $0.02 in, output free.
- https://docs.perplexity.ai/docs/getting-started/models (partial) — model ids and price.
- https://www.seikodigital.com/blog/perplexity-decisions-api — secondary; $0.04 claim; Oct 1, 2026 date; benchmarks.
- https://x.com/perplexitydevs/status/2105725598882832414 (search snippet) — $0.04 launch claim.

**Microsoft**
- https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/introducing-microsoft-decision-1-in-microsoft-foundry-for-decision-and-classific/4562742 — systemone path, sample, pricing, preview status.
- https://commandline.microsoft.com/microsoft-decision-1-model-foundry/ — $0.042, question formats, benchmark claims, OpenRouter link.
- https://www.orcarouter.ai/blog/microsoft-decision-1-explained — secondary; GA Oct 8, 32,768 context.
- https://ai.azure.com/catalog/models/microsoft-decision-1 (failed: JS app, no data).
- https://openrouter.ai/microsoft/microsoft-decision-1 (failed 404).
- https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/chat?view=rest-microsoft-foundry-v1 — Azure chat logprobs params, server pattern.
- https://learn.microsoft.com/en-us/azure/ai-foundry/openai/reference — `api-key` header, Entra Bearer.

**Cloudflare**
- https://developers.cloudflare.com/workers-ai/models/clef/ — endpoint, body, limits, truncation, images.
- https://developers.cloudflare.com/workers-ai/platform/pricing/ — $0.240 / $0.038, neurons.
- https://blog.cloudflare.com/clef-decision-models/ — Oct 1, 2026; Jev-compatible; benchmarks; latency.
- https://huggingface.co/Cloudflare/clef — Apache-2.0, SGLang serve, max_length.
- https://www.eesel.ai/blog/decision-models — secondary roundup; $0.09 clef-flash claim; DevDay preview 403 note.

**OpenRouter**
- https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request — schema, noul criteria rule, usage.cost, errors.
- https://openrouter.ai/docs/guides/community/jev — two endpoints, model ids, 32k context.
- https://openrouter.ai/docs/client-sdks/go/sdks/systemone/README — SDK shape, error list, namespace mapping.
- https://openrouter.ai/docs/api-reference/parameters — chat top_logprobs 0–20.
- https://openrouter.ai/typesafe — model ids.
- https://openrouter.ai/compare/typesafe/jev-1.13 — $0.042 in / $0 out.
- https://openrouter.ai/api/v1/models — ten entries, no pricing.
- https://openrouter.ai/typesafe/jev-1.13 ; https://openrouter.ai/togethercomputer/tev1-4b-experimental ; https://openrouter.ai/inception/mercury-decide-20260930 ; https://openrouter.ai/jaredpalmer/kev-4b (all failed 404).

**Liquid, meraGPT, Inception, Baseten, Together, Fastino and hubs**
- https://docs.liquid.ai/lfm/models/d1 — endpoint, auth, body, images, output_tokens 0.
- https://docs.liquid.ai/lfm/models/decision-models — model family.
- https://meragpt.com/docs — Decider 1 endpoint, auth, schema statement.
- https://www.baseten.co/library/mercury-decide/ — Baseten decisions endpoint, Api-Key auth, shape.
- https://docs.baseten.co/reference/inference-api/chat-completions — logprobs 0–20, auth schemes.
- https://www.baseten.co/pricing — Model API prices.
- https://inceptionlabs.ai/llms.txt (search snippet) — only Mercury 2 pricing.
- https://www.together.ai/models/tev1-4b-experimental — Tev1 call format, price, settings.
- https://huggingface.co/togethercomputer/Tev1-4B-experimental — license status, calibration caveat.
- https://docs.together.ai/reference/chat-completions-1 — integer logprobs 0–20, response shape.
- https://www.together.ai/pricing — serverless prices incl. Tev1.
- https://github.com/AnotiaWang/awesome-decision-models (raw README) — hosted/open model list.
- https://systemonemodels.org/ — hub prices (unverified).
- https://benchmarkheaven.com/jev-models/alternatives (partial) — JevBench leaderboard names.
- https://docs.litellm.ai/docs/decisions.md — provider routes and format translation.
- https://www.marktechpost.com/2026/09/24/fastino-releases-gliner2-5-decide-a-340m-open-weight-decision-model-that-runs-on-cpu/ (search) — Fastino date.

**Self-hosted models**
- https://layaai.org/ ; https://huggingface.co/convaiinnovations/laya — Laya serving, limits, issues.
- https://strandsagents.com/blog/introducing-strands-decider/ ; https://github.com/strands-labs/strands-decider — Strands serve command, response, license.
- https://huggingface.co/h2oai/h2o-lightning-4b (search) — vLLM + shim.
- https://huggingface.co/bespokelabs/Bespoke-Nimble-9B-v2 — adapter, no endpoint.
- https://www.eesel.ai/blog/posthog-jeeves ; https://thenewstack.io/kev-skips-text-generation/ (search) — Jeeves, Kev.
- https://arxiv.org/pdf/2609.28940 (search) — Laya and Jev as pentest decision layers.

**Logprobs references (class 2 / 3)**
- https://ai.google.dev/api/generate-content (partial) — base URL, `?key=`, LogprobsResult structure.
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/inference (partial, offset 300000) — responseLogprobs/logprobs text, 1–20, Gemini 3.x deprecation.
- https://developers.googleblog.com/unlock-gemini-reasoning-with-logprobs-on-vertex-ai/ — July 16, 2025; 1–20; response fields.
- https://ai.google.dev/gemini-api/docs/pricing — Gemini prices.
- https://platform.claude.com/docs/en/api/messages (partial) — no logprobs; headers.
- https://platform.claude.com/docs/en/about-claude/pricing — Claude prices.
- https://docs.x.ai/developers/models — logprobs ignored on grok-4.20+; prices.
- https://console.groq.com/docs/api-reference — logprobs unsupported.
- https://docs-prod.sambanova.ai/docs/en/features/openai-compatibility (search) — logprobs ignored; https://docs.sambanova.ai/cloud/api-reference/endpoints/chat (failed 404).
- https://api-docs.deepseek.com/api/create-chat-completion ; https://api-docs.deepseek.com/quick_start/pricing ; https://api-docs.deepseek.com/ — DeepSeek params, prices, base URL.
- https://docs.fireworks.ai/api-reference/post-chatcompletions — max-logprobs 5 default, shapes; https://fireworks.ai/pricing — no serverless table.
- https://inference-docs.cerebras.ai/api-reference/chat-completions — 0–20; https://www.cerebras.ai/pricing (empty render).
- https://huggingface.co/docs/inference-providers/tasks/chat-completion — top_logprobs 0–5; https://huggingface.co/docs/inference-providers/pricing — pass-through.
- https://docs.novita.ai/api-reference/model-apis-llm-create-chat-completion — 0–20.
- https://docs.tokenfactory.nebius.com/ ; https://docs.tokenfactory.nebius.com/llms.txt ; https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion.md — base URL, max 20.
- https://dev.writer.com/api-reference/completion-api/chat-completion — logprobs bool, deprecations.
- https://docs.cohere.com/reference/chat (partial) — logprobs chosen tokens; https://docs.cohere.com/docs/deprecations — classify deprecation.
- https://docs.mistral.ai/api/ — no logprobs; https://docs.mistral.ai/capabilities/finetuning/classifier_factory — deprecated; https://mistral.ai/pricing — Large price only; https://docs.mistral.ai/capabilities/guardrailing/moderation (failed 404).
- https://docs.ai21.com/reference/jamba-1-6-api-ref — no logprobs; endpoint.
- https://aws.amazon.com/blogs/machine-learning/unlock-model-insights-with-log-probability-support-for-amazon-bedrock-custom-model-import (search) — Custom Model Import logprobs.

**Near-misses**
- https://jina.ai/classifier ; https://jina.ai/news/jina-classifier-for-high-performance-zero-shot-and-few-shot-classification — classify endpoint, response, limits.
- https://docs.galileo.ai/concepts/luna/luna (search) — Luna-2 enterprise-only.
- https://patronus.ai/announcements/patronus-ai-launches-industry-first-self-serve-api-for-ai-evaluation-and-guardrails (search) — evaluate API, no probability doc.
- https://docs.notdiamond.ai/docs (search) — router.
- https://dejan.ai/blog/chrome-decisions-api-decisionmodel/ (search) — Chrome DecisionModel.

**Other secondary coverage used for dates only**
- https://www.aitools-directory.com/blog/decision-models-two-speed-stack-ai-weekly-017/ (failed 403).
- https://www.unite.ai/openai-releases-decisions-api-in-public-beta-powered-by-gpt-6-luna/ ; https://venturebeat.com/technology/amazon-unveils-a-free-fast-open-source-jev-killer-strands-decider-2b-makes-decisions-in-fractions-of-a-second ; https://dealroom.co/news/158476-cloudflare-launches-clef-as-typesafes-decision-model-idea-spreads-across/ (search snippets).
