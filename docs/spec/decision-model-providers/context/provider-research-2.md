# Decision-model provider research, round 2 (S1 scout)

Written 2026-10-10 for the `decision-model-providers` spec (draft PR #697). It answers the user's follow-up request: find more decision-model providers ("gemini has released one, same with openai"), and price each one at the rate it serves on its own API, with documentation links as proof.

**Scope.** This file covers only providers that the SDK does not support after this PR. Spec §9.1 already lists TypeSafe, Perplexity, OpenRouter, Liquid, Baseten, meraGPT, Cloudflare, Microsoft Foundry, and OpenAI. The file also re-checks OpenAI's decision models. It does not repeat round 1 (`context/provider-research.md`); it cites that file as "r1 §x". The parallel pricing scout re-verifies existing pricebook rows, so this file does not.

**Rules used.**
- Every page was read on **2026-10-10** unless a line says otherwise.
- A quote in "double quotes" is verbatim. Most quotes were checked against the raw page (curl of the HTML or `.md`). §6 marks the facts that came only from a summarising fetch, or from a helper's read that was not re-checked.
- A price counts as first-party only when it appears on the provider's own site or docs. A price seen only on OpenRouter, benchlm.ai, systemonemodels.org, or another hub is labelled **THIRD-PARTY**.
- A provider counts as a decision model only if it returns probabilities over typed questions (at least P(true) for a yes/no question, the SDK's `JevQuestionType.NOUL`) through a documented hosted HTTP API.
- **Ship candidate** means first-party docs, a first-party price, and a documented wire. **Not shippable** gives the reason.

**Wire names** (from r1 §4):
- **System One** is TypeSafe's body, `{model, state, questions:{name:{type: noul|choice|score, instructions, criteria?}}}` → `{model, answers:{name:…}, usage:{input_tokens, output_tokens}}`. In the SDK it is `SystemOneProvider` plus one `SystemOneHost` row: `display_name`, `path`, `auth_scheme`, `noul_criteria_required`, `model_from_request` (spec §8.5).
- **OpenAI Decisions** is `POST /v1/decisions` with `input` + `questions[]` (`predicate|choice|score`) → `answers[]`. In the SDK it is `OpenAIDecisionsProvider`.

---

## 1. Google Gemini

### 1.1 Verdict

**Google has not released a hosted decision model or decision endpoint as of 2026-10-10.** This holds for the Gemini Developer API and for Vertex AI (now "Gemini Enterprise Agent Platform").

What Google released on 2026-10-06 is an **on-device** decision task, the **MediaPipe Decision Maker**, launched together with the open **EmbeddingGemma 2** model. It answers boolean, choice, and score questions with probabilities. But it runs locally from a downloaded model file, and it has no HTTP endpoint, no API key, and no price. The SDK cannot call it as a provider, so it is **not shippable**. This is very likely the release the user means by "gemini has released one".

### 1.2 What Google released: MediaPipe Decision Maker + EmbeddingGemma 2 (on-device)

- **Identity.** Google AI Edge "MediaPipe Decision Maker" task ("Decision Task" in the launch post).
  - The task page says it "evaluates structured decision questions".
  - Its comparison table gives the execution target as "On-Device Edge" (Android, iOS, WebGPU/Wasm, Desktop, Python).
  - The page reads "Last updated 2026-10-06 UTC".
  - https://developers.google.com/edge/mediapipe/solutions/decision/decision_maker
- **Launch post** (Google Developers Blog, 2026-10-06):
  - "Today, Google DeepMind launched EmbeddingGemma 2."
  - "Most notably, EmbeddingGemma 2 can act as an ultra-low-latency on-device decision engine."
  - The chess demo ran "fully on-device".
  - https://developers.googleblog.com/google-ai-edge-with-embeddinggemma-2/
- **Google blog, same day.** EmbeddingGemma 2 is an open embedding model of about 740M parameters, Apache-2.0, built on Gemma 4. Weights are on Hugging Face and Kaggle. The post says "Gemini Enterprise Agent Platform Model Garden availability coming soon". It gives no Gemini API model id, endpoint, or price. https://blog.google/innovation-and-ai/technology/developers-tools/embeddinggemma-2/
- **Models the task can load** (task page):
  - EmbeddingGemma 2 (`embedding_gemma2` 270M, `embedding_gemma2_text_vision` 440M) and EmbeddingGemma 1.
  - Gemma 4 E2B / E4B (int4).
  - Laya (`laya_s256`, `laya_s512`).
  - GLiNER2.5-Decide (`gliner_s256`, `gliner_s512`).
  - The best-practices page groups these as bi-encoders, autoregressive generative models (Gemma 4 E2B/E4B), and cross-encoders (Laya 149M, GLiNER2.5-Decide 166M). https://developers.google.com/edge/mediapipe/solutions/decision/decision_maker/best-practices
- **How it is called** (Python guide):
  - `DecisionMaker.create_from_options(options)`, then `evaluate_boolean(query, question)`, `evaluate_choice(…)`, `evaluate_score(…)`, and `evaluate_batch(contexts, questions)`.
  - The model is a local file. The guide says to "Download `embeddinggemma-2-270m-it.litertlm` and specify its path" (`BaseOptions.model_asset_path`).
  - No network call or API key is described.
  - https://developers.google.com/edge/mediapipe/solutions/decision/decision_maker/python
- **Question kinds and result fields** (task page and Python guide):
  - `BooleanQuestion(condition, threshold, normalize_prior)` returns `value` / `is_satisfied`, `probability_true` (0.0–1.0), and `confidence`. This would map to NOUL, with P(yes) = `probability_true`.
  - `ChoiceQuestion(instructions, criteria, normalize_prior)` returns `selected_key`, `probabilities` (summing to 1.0), `confidence`, and `prediction_set` (a 90% conformal set). This would map to CHOICE.
  - `ScoreQuestion(instructions, rubric)` returns `expected_score`, `selected_key`, `level_probabilities`, and `confidence`. This would map to SCORE.
- **Limits.**
  - The default `maxNumTokens` is 4096 (task page).
  - Cross-encoders handle "typically 8 or fewer options" per pass.
  - EmbeddingGemma chunks long documents ("> 256 tokens, up to 2,048 tokens") into 512-token spans (best-practices page).
  - No question or level cap is stated.
- **Price.** None. It is not on the Gemini API pricing page (§1.4).
- **SDK compatibility.** None. There is no HTTP wire, so neither `SystemOneProvider` nor `OpenAIDecisionsProvider` can reach it. A new adapter would have to run a local MediaPipe runtime, a native dependency the SDK does not take today. **Not shippable.**

**Related, also on-device, also not shippable:** Chrome's `window.DecisionModel` web API, from the Chrome Built-in AI team.
- The Google explainer says it "has not been approved to ship in Chrome" and that "Inference runs locally on the user's device" (https://github.com/explainers-by-googlers/decisions-api).
- A code-review write-up (secondary) says the first code landed in Chromium on 6–8 October 2026, behind a desktop flag. It names EmbeddingGemma as the planned engine and gives limits of 1–16 questions per schema, 2–26 choice options, and 2–9 rating levels (https://dejan.ai/blog/chrome-decisions-api-decisionmodel/).

### 1.3 What the hosted Gemini API offers instead (checked; nothing qualifies)

- **Changelog.** The latest entries are 2026-10-08 (requests routed to `gemini-3.8-flash` / `gemini-3.6-flash`; a Deep Research preview shutdown) and 2026-10-06 (`gemini-nano-banana-2.1` GA). No recent entry mentions a decision model, decisions endpoint, classifier, judge, or calibrated probabilities. https://ai.google.dev/gemini-api/docs/changelog
- **Model list.** Every id on the models page is a chat, live, TTS, image, video, music, embedding, agent, or robotics model. None contains "decide", "decision", or "judge". https://ai.google.dev/gemini-api/docs/models
- **REST methods.**
  - `models.*` has `generateContent`, `streamGenerateContent`, `embedContent`, `batchEmbedContents`, `countTokens`, `predict`, `predictLongRunning`, and batch variants.
  - Other resources are `interactions`, `agents`, `webhooks`, `triggers`, `environments`, `fileSearchStores`, `cachedContents`, `files`, and `batches`.
  - There is no `decide`, `decisions`, or `classify` method.
  - https://ai.google.dev/api/all-methods
- **OpenAI-compatibility layer** (`https://generativelanguage.googleapis.com/v1beta/openai/`).
  - It documents chat completions, images, videos, embeddings, batches, and models.
  - It has no `/decisions` or Responses API, and it does not mention logprobs.
  - So Gemini is **not reachable on the OpenAI Decisions wire**.
  - https://ai.google.dev/gemini-api/docs/openai (raw `.md.txt` grep for "decision" and "logprob": no hits).
- **Logprobs (r1 group D) are now gone on current models.**
  - r1 §3.13 recorded `responseLogprobs` as deprecated for 3.x.
  - In a Google AI Developers Forum thread about Gemini 3.1 Pro and 3.6 Flash, a reply dated 2026-08-05 says: "This is currently WAI, logprobs are no longer returned for 3.X models" (https://discuss.ai.google.dev/t/missing-logprobs-support-in-the-newest-gemini-models-3-1-pro-3-6-flash-on-vertex-ai-and-ai-studio/176557; the page does not label the poster as Google staff).
  - The Interactions API also lacks the fields (https://discuss.ai.google.dev/t/missing-logprobs-support-in-next-gen-interactions-api-generationconfig-2/144837).
  - This strengthens NG-3.
- **Vertex AI / Gemini Enterprise Agent Platform.**
  - Release notes from 2026-09-15 to 2026-10-07 (the latest entry) list Claude Haiku/Sonnet/Opus 5.5, Grok 4.6/4.7, Muse Spark 1.3, Gemini 3.8 Live/TTS, Nano Banana 2.1, and CodeMender releases.
  - None is a decision model from Google or a partner: no Jev, Clef, pplx-decider, or Decision-1.
  - https://docs.cloud.google.com/gemini-enterprise-agent-platform/release-notes
- **Vercel AI SDK `google.decisionModel('gemini-3.5-flash-lite')`** is not a Google product.
  - The AI SDK page says "Anthropic and Google adapt structured language-model output for all three types".
  - It adds: "Their Boolean answers contain prompted estimates of P(true), and Choice and Score answers omit probability distributions."
  - That is self-reported confidence (r1 group F), which NG-3 excludes.
  - https://ai-sdk.dev/docs/ai-sdk-core/decisions
- **Auth, for the record** (relevant only if Google ships an endpoint later).
  - Current Gemini REST examples send `x-goog-api-key: $GEMINI_API_KEY` (https://ai.google.dev/gemini-api/docs/gemini-3).
  - The SDK's registry already maps `ModelProvider.GEMINI` to `GEMINI_API_KEY` and `https://generativelanguage.googleapis.com/v1beta` (`vidbyte/lib/registries/models.py:86,109`).

### 1.4 Gemini prices (for completeness; there is no decision product to price)

Gemini Developer API pricing page, paid tier, per 1M tokens in USD:
- "Gemini 3.8 Flash" Standard: input "$0.75 through December 31, 2026. $1.50 starting January 1, 2027."; output "$3.75 through December 31, 2026. $7.50 starting January 1, 2027."
- "Gemini 3.5 Flash-Lite" Standard: input "$0.30 (text / image / video / audio)"; output "$2.50".
- "Gemini 3.1 Flash-Lite" Standard: input "$0.25 (text / image / video) $0.50 (audio)"; output "$1.50".

The page has no decision, classifier, or per-decision product. https://ai.google.dev/gemini-api/docs/pricing (raw: https://ai.google.dev/gemini-api/docs/pricing.md.txt)

---

## 2. OpenAI

### 2.1 Models on `/v1/decisions`

**There is still exactly one: `gpt-6-luna`.** OpenAI has released no decision model after it, and there are no dated snapshots.
- **Guide:** "`gpt-6-luna` is the only model currently available." https://developers.openai.com/api/docs/guides/decisions (raw `.md`)
- **Changelog:** the only decisions entry is dated 2026-10-06 and tagged gpt-6-luna and v1/decisions. It says the Decisions API launched in beta: "Turn text and images into typed answers 10x faster than the Responses API." The later entries are not about decisions: 2026-10-07 (`chat-latest`) and 2026-10-08 (Ultrafast mode for `gpt-6.1-sol`). https://developers.openai.com/api/docs/changelog
- **Model page:** it lists only the snapshot `gpt-6-luna`. Its endpoint table still does not list `v1/decisions`. https://developers.openai.com/api/docs/models/gpt-6-luna
- **Community announcement**, 2026-10-06: "Decisions API is now available in Public Beta", powered by `gpt-6-luna`. https://community.openai.com/t/decisions-api-is-now-available-in-public-beta/1403877
- **Status:** "The Decisions API is in public beta, and we expect to GA in the coming weeks." (guide)

### 2.2 Price (OpenAI's own pages)

- **Decisions guide** (raw `.md`, lines 855–857):
  - "With `gpt-6-luna`, input costs **$0.10 per 1M tokens**. You pay only for input tokens: there are no cache-read, cache-write, or output-token charges."
  - "Regional processing premiums and long-context input pricing multipliers apply. These rates apply to `/v1/decisions`; other requests using `gpt-6-luna` follow the applicable [model and processing-tier pricing]."
  - Source: https://developers.openai.com/api/docs/guides/decisions
  - So the SDK row `gpt-6-luna: 0.10 / 0.0` is correct (spec §9.1, D-12).
- **General pricing page.** It has no decisions row. Its `gpt-6-luna` Standard row is "| gpt-6-luna | $0.10 | $0.01 | $0.125 | $0.50 |" (input, cached input, cache writes, output). That is the Responses/Chat rate; the guide says it does not apply on `/v1/decisions`. https://developers.openai.com/api/docs/pricing
- **Long-context multiplier** (model page): "Prompts with more than 272K input tokens are priced at 2x input and cache rates and 1.5x output for the full request." The SDK pricebook has one input rate, so it records half the true cost of a decision over 272K tokens. https://developers.openai.com/api/docs/models/gpt-6-luna
- **Data residency** (guide): "Data residency and regional processing are supported in the United States and Europe (EEA + Switzerland)." Regional premiums are not represented in the pricebook either.

### 2.3 API reference: now found (r1's URL still returns 404)

- These URLs return **404**: r1's `https://developers.openai.com/api/reference/resources/decisions/methods/create` and `https://developers.openai.com/api/reference/resources/decisions`.
- The decisions resource is also missing from `https://developers.openai.com/api/reference/llms.txt` and from `https://developers.openai.com/api/docs/api-reference/decisions`.
- The **language-specific references do exist**. Adding `.md` to a URL returns its text.
  - TypeScript: https://developers.openai.com/api/reference/typescript/resources/decisions/methods/create (resource page: https://developers.openai.com/api/reference/typescript/resources/decisions)
  - Python: https://developers.openai.com/api/reference/python/resources/decisions/methods/create
  - Ruby: https://developers.openai.com/api/reference/ruby/resources/decisions
  - Admin usage, `GET /organization/usage/decisions`: https://developers.openai.com/api/reference/typescript/resources/admin/subresources/organization/subresources/usage/methods/decisions
- These are the right links for schema proof in code comments. The guide stays the price proof.

### 2.4 Wire facts the reference adds

These change or confirm r1 §3.1 and spec assumptions A-2, A-8, and A-11. Source: the TypeScript create page, raw `.md`.

- **Endpoint.** "**post** `/decisions`" on base `https://api.openai.com/v1`, called as `client.decisions.create(DecisionCreateParams…)`, returning `Decision`. The `Decision` object has `answers`, `model`, and `usage`. No `id` or `object` field is documented.
- **`model` is now a documented response field** (`model: string`, no description). r1 and spec §9.1 recorded the echo as undocumented. The adapter's choice to report `config.resolved_model()` still works, and the echo is now available if the spec wants it.
- **`usage` shape** (names and types only):
  - `input_tokens`
  - `input_tokens_details{cache_write_tokens, cached_tokens}`
  - `output_tokens`
  - `output_tokens_details{reasoning_tokens}`
  - `total_tokens`

  These are the Responses-style keys. A-2 holds.
- **`name` is optional** on every question (`name?: string`). Answers carry `name: string | null`.
  - "Sometimes a question returns a refusal instead of an answer. The result has type `refusal` and includes the question's name, or `null` if you didn't give it one."
  - The SDK always sends names, so nothing changes.
- **Choice values.**
  - "Provide between 2 and 255 choices. Each choice must be unique."
  - `value: string | boolean`: "Choice values are typed: a string and a boolean with the same text are distinct."
  - The SDK sends strings, so nothing changes. The 2–255 bound is new.
- **Score levels.**
  - Each level has `label` (required) and `description?` (optional). No minimum or maximum count is stated.
  - Score answer `probabilities[]` items are `{label, probability, value: number}`. A-8 holds.
- **Choice and level `description` are optional** (`description?: string`). A-11 holds: omit the field when there is no description.
- **Refusal answer.** `{name, type: "refusal"}` only. "The model declined to answer this question. Other questions in the same request can still receive answers."
- **`safety_identifier?: string | null`.** "Opaque caller-provided end-user identifier, scoped by the verified org." It is not part of `JevDecisionRequest`, so nothing changes.
- **Images.** "up to 128 images per request"; `detail` is one of `low|high|auto|original`.
  - The two OpenAI pages **conflict** on hosted URLs:
    - Reference: "Images can be base64 data URLs or publicly accessible HTTP(S) URLs. File IDs aren't accepted."
    - Guide: "Hosted HTTP or HTTPS image URLs and `file_id` inputs aren't supported by this endpoint."
  - Images are out of scope (NG-5).
- **Not supported in `input`:** "Other message roles, function calls, files, audio, and item references aren't supported."
- **Limits.** These are still undocumented: maximum question count, maximum level count, and a decisions-specific rate limit. No OpenAI page read states them.
- **Community-reported issues** (not first-party; thread in §2.1, 2026-10-07):
  - The Decisions API has no prompt caching yet.
  - One user saw a choice question return about 98% for an outcome whose predicate probability was about 70%.
  - The same user saw choice order change the probabilities.
- **Other clouds.** OpenAI's `/v1/decisions` is not on Azure OpenAI or Bedrock:
  - A Microsoft moderator wrote on 2026-10-07: "we could not find an official Microsoft announcement or documentation confirming when the newly released OpenAI Decisions API will be available in Microsoft Foundry" (https://learn.microsoft.com/en-in/answers/questions/6029135/open-ai-decisions-api-availability-inquiry).
  - Bedrock's `openai.gpt-6-luna` model card lists Responses, Chat Completions, Converse, and Invoke only (https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-6-luna.html).

### 2.5 OpenAI verdict

There is nothing new to add. This PR already ships `gpt-6-luna` on `/v1/decisions` at `0.10 / 0.0`. The spec author may want to:
- link the TypeScript or Python reference (§2.3) in code comments as the schema proof, and keep the guide link as the price proof;
- note the documented `model` echo and `usage` keys.

---

## 3. Other new hosted decision APIs

These candidates came from first-party docs, OpenRouter's decisions catalog (used only to discover publishers), and the hubs named in r1. They fall into four groups:
- **§3.1** vendors that serve **their own** decision model (the most useful group);
- **§3.2** hosts and gateways that **resell models the SDK already reaches** (TypeSafe Jev, Cloudflare Clef, and others);
- **§3.3** a new model on an existing provider;
- **§3.4–3.5** rejections.

Every §3.1–§3.2 candidate except Requesty's chat route speaks **System One**, so each fits the existing `SystemOneProvider` as one `SystemOneHost` row. Some send the System One body to a `/decisions` path, as Perplexity and Baseten already do. Celeris also serves the OpenAI Decisions wire.

The "**`model_from_request`**" lines below say whether the response's `model` echo is documented and equal to the request id. If it is, the echo can be the pricing key (False). If not, record the request id (True). This follows INV-27 / D-17.

### 3.1 Ship candidates: vendors serving their own decision model

#### 3.1.1 Celeris: `celeris-1-decision` (System One **and** OpenAI Decisions). Ship candidate.

- **What it is.** "Celeris-1-decision is a diffusion language model built for typed decisions." The post is dated October 8, 2026 (https://celeris.ai/celeris-1-decision; dated per a helper's fetch). Decisions docs: https://docs.celeris.ai/decisions.md. Models page: https://docs.celeris.ai/models.md.
- **Endpoints** (same model, price, and limits on both):
  - System One: `POST https://inference.celeris.ai/celeris-1-decision/v1/systemone`. "It implements TypeSafe's System One API".
  - OpenAI Decisions: `POST https://inference.celeris.ai/celeris-1-decision/v1/decisions` (`predicate|choice|score`, `choices[{value,description}]`, `levels[{label,description}]`).
  - **The base URL contains the model name**: "https://inference.celeris.ai/<model>/v1". The Jev-SDK recipe sets `TYPESAFE_BASE_URL=https://inference.celeris.ai/celeris-1-decision`. If a caller overrides `model`, the endpoint must change too.
- **Auth.** "Every API request is authenticated with a bearer key: `Authorization: Bearer ck_your_key_here`" (https://docs.celeris.ai/authentication.md). The curl examples use `$CELERIS_API_KEY`, so the env var is **`CELERIS_API_KEY`**. → `DecisionAuthScheme.BEARER`.
- **Model.** `celeris-1-decision`, the only decision model. The response echoes `"model": "celeris-1-decision"`, so `model_from_request` = False works.
- **Answers.**
  - System One: noul `{"type":"noul","noul":0.95}`; choice and score in the standard shapes (score has `legend` and index-keyed `probabilities`). "Probabilities are rounded to two decimal places and sum to 1."
  - OpenAI wire: predicate `{"type":"predicate","name":"refund","probability":0.95}`.
- **Usage.**
  - System One: `{"input_tokens": 122, "output_tokens": 0}`.
  - OpenAI wire: "`usage` also includes `total_tokens` … Its cache and reasoning token detail fields are present and set to zero."
  - With the optional `x_celeris.explain` extension, `output_tokens` is non-zero (15 in the example) but free.
- **Limits** ("Request limits"):
  - "Up to 512 questions per request, or 64 with `x_celeris.explain: true`. Up to 512 options per `choice` question. Up to 64 levels per `score` question. Up to 8 images per request".
  - "The maximum request body size is 8 MiB".
  - Context window: "131,072 tokens. A fixed part is reserved for the answers, so the input limit is slightly lower."
  - Going over a limit returns 400 on `/v1/decisions` and 422 on `/v1/systemone`.
  - "`safety_identifier` accepts a string or `null` and has no effect on the request. Unknown fields, including `stream`, return a validation error."
- **Price** (https://docs.celeris.ai/pricing.md, table columns Input / Cached input / Output):
  - "| [`celeris-1-decision`](/models#celeris-1-decision) | US$0.04 per million | US$0.04 per million | Free |"
  - Billing is prepaid credit. "Credit granted to your workspace expires **30 days** after it is granted."
  - → `celeris-1-decision: 0.04 / 0.0`.
- **SDK row.** `SystemOneHost("Celeris", path="/systemone", BEARER)`. Default endpoint `https://inference.celeris.ai/celeris-1-decision/v1`. Env var `CELERIS_API_KEY`. Default `celeris-1-decision`. A route through `OpenAIDecisionsProvider` would need that adapter to accept a non-OpenAI provider (today `provider = ModelProvider.OPENAI`), so System One is the cheap route.

#### 3.1.2 Nace.AI: Drex (`drex-v1.5`, `drex-v1.0`, alias `drex-latest`). Ship candidate.

- **Docs.** https://console.nace.ai/docs/drex/quickstart, https://console.nace.ai/docs/drex/reference/models, https://console.nace.ai/docs/drex/reference/pricing, https://console.nace.ai/docs/drex/reference/limits, https://console.nace.ai/docs/drex/guides/authentication. The `.md` variants return a 500 error page; the plain pages work.
- **Endpoint.** `POST https://console.nace.ai/v1/systemone` (quickstart curl). Nace also documents a model list at `GET https://console.nace.ai/v1/models`; the authentication page shows a 401 captured from it. This makes Nace the only new host with a model-list endpoint.
- **Auth.** "Pass a nace_sk_ key as `Authorization: Bearer <key>`." Quickstart: `export NACE_API_KEY = "nace_sk_..."`, and "The SDKs and the CLI read the key from `NACE_API_KEY`". → BEARER, env var **`NACE_API_KEY`**.
- **Models** (models page):
  - "Drex 1.0 drex-v1.0 2026-09-24 $ 0.04 32,768 32,768" and "Drex 1.5 drex-v1.5 2026-09-28 $ 0.05 131,072 139,264". The columns are released date, price per 1M input tokens, state limit, and row limit.
  - "drex-latest is an alias. It currently points to drex-v1.5."
  - "The response model reports the pinned version that answered, never the alias."
  - `drex-v1.1` is retired: "Requests that name it are served by drex-v1.5 (Drex 1.5) at its price."
- **Wire.** Standard System One. Example noul answer: `{"type":"noul","noul":0.8401}`. Usage is `{input_tokens, output_tokens}`.
- **Limits** (limits page):
  - "Max questions per request 512".
  - "Max serialized body (state + questions) 1,048,576 bytes".
  - State limit 131,072 tokens on v1.5 and 32,768 on v1.0.
  - Rate limits: "free 120 8 / paid 600 16" (RPM / in-flight).
  - No maximum is stated for options or levels.
- **Price** (pricing page): "Per 1M input tokens, drex-v1.0 $ 0.04" and "Per 1M input tokens, drex-v1.5 $ 0.05". "There is no per-request fee and no charge per question."
- **SDK row.** `SystemOneHost("Nace.AI", path="/systemone", BEARER)`. Default endpoint `https://console.nace.ai/v1`. Env var `NACE_API_KEY`.
  - **Recommend default `drex-v1.5`**, not `drex-latest`. The echo is always the pinned version, so `model_from_request` = False prices correctly with rows `drex-v1.5: 0.05 / 0.0` and `drex-v1.0: 0.04 / 0.0`.
  - A `drex-latest` default would need its own pricebook row to satisfy C009, and that row moves whenever the alias moves.
- THIRD-PARTY: OpenRouter lists `nace-ai/drex-v1.5`, served via DeepInfra, at $0.04/M.

#### 3.1.3 Upstage: Solar Decide (`solar-decide`). Ship candidate (beta).

- **Docs.** Model page https://console.upstage.ai/docs/models/solar-decide. API page https://console.upstage.ai/api/systemone (`.md`: https://console.upstage.ai/api/systemone.md).
- **What it is.** "Solar Decide uses the same /v1/systemone schema as Jev". Status "Beta", "Released on 2026-09-22", "512K context length".
- **Endpoint.** `POST https://api.upstage.ai/v1/systemone`. "Solar Decide is in beta. The `/v1/systemone` schema may change before general availability."
- **Auth.** The example uses `headers = { "Authorization": "Bearer UPSTAGE_API_KEY" }`, a literal placeholder. No env var is documented. **`UPSTAGE_API_KEY`** follows the placeholder.
- **Model.** "Currently, the only available model is 'solar-decide'" (per a helper's fetch). The response `model` is "A string indicating the version of the model that was utilized for the request." Because a versioned echo would still start with `solar-decide`, `model_from_request` = False works with a `solar-decide` row; True is the safe choice.
- **Answers.** Standard System One. Upstage also states that "A `noul` answer carries no separate confidence field — the probability itself is the answer." `usage.output_tokens`: "Solar Decide writes no prose, so this is one token per question and is not billed."
- **Limits.**
  - "A `choice` question takes **2 to 26 options**. This endpoint reads the decision from the logits of single-token labels `A` through `Z`". Going over returns 422 `validation_failed`.
  - No maximum is documented for questions or levels.
- **Price** (model page): "$ 0.1 /1M tokens Input Token", "Free Output Token", "$ 0.1 /1M tokens Cached Token". → `solar-decide: 0.10 / 0.0`.
  - THIRD-PARTY conflict: OpenRouter lists `upstage/solar-decide` at $0.05/M, apparently with a 0.5 discount. Upstage's own $0.10 is the price to record.
- **Not shippable: Solar Decide Flash.** `upstage/solar-decide-flash` appears only on OpenRouter (created 2026-10-08, $0.05/M, THIRD-PARTY). Upstage's docs do not document it.

#### 3.1.4 Inception: Mercury Decide on Inception's own API (`mercury-decide`). Ship candidate.

- **Docs.** https://docs.inceptionlabs.ai/capabilities/decisions.md, https://docs.inceptionlabs.ai/get-started/models.md, and the API reference https://docs.inceptionlabs.ai/api-reference/decisions/create-a-decision.md.
- **Endpoint.** `POST https://api.inceptionlabs.ai/v1/decisions`. The body is **System One** (`state` plus a `questions` map of `noul|choice|score`). It is not the OpenAI Decisions wire.
- **Auth.** "Set `INCEPTION_API_KEY` to your API key"; requests send `-H "Authorization: Bearer $INCEPTION_API_KEY"`. → BEARER, env var **`INCEPTION_API_KEY`**.
- **Model.** `mercury-decide`. The response echoes `"model": "mercury-decide"`, so `model_from_request` = False works.
- **Limits.** Choice takes "A map of 1–255 option names to descriptions; descriptions may be `null`". Score takes "An ordered array of 1–10 level descriptions, starting at level 0". No question maximum is documented.
- **Price.**
  - "Mercury Decide costs **$0.02 per million input tokens** (50% off the regular $0.04 price). Only input tokens are billed; output tokens are reported in `usage.output_tokens` but are not charged."
  - Models table: "| **Mercury Decide** | ~~\$0.04~~ → **\$0.02** | \$0 | \$0 | `v1/decisions` |".
  - → `mercury-decide: 0.02 / 0.0`. The rate is **promotional** and will return to $0.04 at some point.
- **Relevance to the Baseten row.** The user ruled that Baseten is priced at Inception's published API rate. Today that rate is $0.02 per 1M input tokens, discounted from $0.04, so the Baseten row needs to choose one. The pricing scout owns that row.
- **SDK row.** `SystemOneHost("Inception", path="/decisions", BEARER)`. Default endpoint `https://api.inceptionlabs.ai/v1`. Env var `INCEPTION_API_KEY`. Default `mercury-decide`, which already maps to the decision runner (`runners.py:320,388`).
  - **Catalog overlap:** a member valued `"inception"` would form the qualified key `inception/mercury-decide`. That key is the same string as Baseten's bare model id (`runners.py:319`). Both map to decision, so behaviour does not change, but the spec author should know about it.

#### 3.1.5 Hanzo: Kai (`kai`). Ship candidate (small context).

- **Docs.** https://docs.hanzo.ai/docs/decisions and https://docs.hanzo.ai/docs/models/kai. Pricing: https://hanzo.ai/pricing.
- **Endpoint.** `POST https://api.hanzo.ai/v1/decisions`. The body is **System One** on a `/decisions` path. The same route also proxies `typesafe/jev-1.13` and `~typesafe/jev-latest` through OpenRouter's Decisions API.
- **Auth.** `-H "Authorization: Bearer $HANZO_API_KEY"`. → BEARER, env var **`HANZO_API_KEY`**. Only secret `sk-` keys work; per a helper's read, a `pk-` key returns 403.
- **Model.** `model` is required: "`kai`, `typesafe/jev-1.13` or `~typesafe/jev-latest`". The error text also accepts `hanzo/kai`. The response echoes `model`, e.g. "kai", plus `provider` and `routing`.
- **Answers.** System One, with extra fields that the SDK ignores. Noul example: `{"type":"noul","noul":0.12,"confidence":0.76,"answer_confidence":0.88}`. The doc defines "answer_confidence on each answer: p_max, the calibrated probability of the reported answer".
- **Limits.**
  - Questions are "required; 1 to 100". Going over returns 422: "'questions' takes at most 100 questions, got 101".
  - **State plus each question must be "at most 1,024 tokens together"** for Kai. That is far below the SDK's `JEV_MAX_STATE_CHARS`, so long states will fail with 4xx.
- **Price.**
  - Docs: "kai $0.021 per million input tokens ( usage.input_tokens ); output is free".
  - Pricing page: "Kai starter Hanzo's decision model. $0.021 per million input tokens, half of Jev's $0.042. Output is free."
  - → `kai: 0.021 / 0.0`.
- **SDK row.** `SystemOneHost("Hanzo", path="/decisions", BEARER)`. Default endpoint `https://api.hanzo.ai/v1`. Env var `HANZO_API_KEY`. Default `kai`. `model_from_request` = False works with the documented echo. True is safer, because a caller who sends `hanzo/kai` may get `kai` back.

#### 3.1.6 Vansa: `vansa-3.4`. Ship candidate (no SLA).

- **Docs.** https://docs.vansa.org/skills/vansa-api/references/api.md and https://docs.vansa.org/llms.txt. Pricing: https://vansa.org/pricing.
- **Endpoint.** `POST https://api.vansa.org/v1/systemone`. "Jev-compatible: the same `state` + `questions` format as TypeSafe's Jev `/v1/systemone`" (per a helper's fetch).
- **Auth.** `Authorization: Bearer <VANSA_KEY>`. → BEARER, env var **`VANSA_KEY`**. Note that the name is not `…_API_KEY`.
  - The docs ask for a descriptive `User-Agent`. Per a helper's fetch, "Cloudflare answers 403 'error code: 1010' to Python-urllib's default one".
  - The SDK's async transport uses httpx (`vidbyte/lib/http/transport.py`), whose default UA is not Python-urllib's. Whether Vansa accepts it is unverified.
- **Model.** `vansa-3.4` is the default. `vansa`, `vansa-latest`, `vansa-1`, `vansa-2`, `vansa-3`, and `vansa-3.0`–`vansa-3.3` all resolve to it. Responses say `"model": "vansa-3.4"`, so use `model_from_request` = False with a `vansa-3.4` row.
- **Response.** Top level is `id`, `object` ("systemone.result"), `model`, `created`, `answers`, `usage`, `latency_ms`. Noul answers add `probabilities` and `confidence`, which the SDK ignores. `usage` is `input_tokens` plus `output_tokens` (always 0), and optionally `state_tokens` and `truncated`.
- **Limits.**
  - "32 questions per request, 255 options per choice, 32 levels per score, 4,000 characters per instruction, 512 KiB per request body".
  - "16,384 tokens per question's full prompt". Over-limit prompts get a 400 and are not truncated.
  - Noul criteria are an "optional object with `true` and/or `false` string keys".
- **Price** (pricing page): "$0.034" per 1 million input tokens; output-token cost "None"; prepaid credit is "$0.034/1M input tokens" for "Any amount from $1 to $1,000". The monthly plans give lower effective rates, which the SDK cannot represent (Starter $5 for 150M tokens, Growth $25 for 800M, Scale $99 for 3.5B). The page says "Checked 27 September 2026". → `vansa-3.4: 0.034 / 0.0` (the prepaid list rate).
- **Caveats.** Per a helper's read, the docs say "No SLA". The pricing footer names only "Vansa.org", with no separate legal operator.

#### 3.1.7 ZooData / ZooWork: Instinct (`instinct`, `instinct-dual-4b`, `instinct-tuned-4b`). Ship candidate.

- **Docs.** https://instinct.zoowork.ai/docs/. The page needs JavaScript for its code tabs, but the static text was read. Open weights (Apache-2.0): https://github.com/SerendipityOneInc/instinct.
- **Endpoint.** "The paid endpoint is https://api.zoodata.ai/v1/systemone ; the free preview is https://api.zoowork.ai/v1/systemone". The page also says "POST /v1/systemone Bearer authentication".
- **Auth.** "Set ZOODATA_API_KEY in your environment. Requests use Authorization: Bearer YOUR_API_KEY". → BEARER, env var **`ZOODATA_API_KEY`**.
- **Models and price.**
  - "instinct US$0.03 per million input tokens Dense 27B · single order"
  - "instinct-dual-4b US$0.01 per million input tokens Frozen 4B · dual order"
  - "instinct-tuned-4b US$0.01 per million input tokens Fine-tuned 4B · single order"
  - "Output tokens are free on all models. No subscription fee. Top up your USD balance from US$20".
  - The three models "use the same request and response schema, support Noul, Choice and Score, and return zero generated output tokens."
- **Limits.** The static page documents none. The repo README's 64-question cap applies to the self-hosted reference server only.
- **Response `model` echo.** Not verified. → `model_from_request` = True.
- **SDK row.** `SystemOneHost("ZooData", path="/systemone", BEARER)`. Default endpoint `https://api.zoodata.ai/v1`. Env var `ZOODATA_API_KEY`. Default `instinct` → `0.03 / 0.0`. Optional rows `instinct-dual-4b` and `instinct-tuned-4b` at `0.01 / 0.0`.

#### 3.1.8 Fastino: GLiDE (`fastino/GLiDE`). Ship candidate, with a score-field quirk.

- **Docs.** https://docs.fastino.ai/inference/systemone.md. Pricing: https://docs.fastino.ai/pricing.md.
- **Endpoint.** "POST https://api.fastino.ai/v1/systemone".
- **Auth.** The examples send `X-API-Key: $FASTINO_API_KEY`, but "Fastino also accepts the Bearer header if retaining that style makes a direct HTTP migration simpler." → BEARER works. Env var **`FASTINO_API_KEY`** ("Read API keys from FASTINO_API_KEY").
- **Model.** `fastino/GLiDE`, which is required: "Omitting it returns `422 'model' must be provided`". The docs say to "Expect `model: "glide"` in the response". The echo differs from the request id, so use **`model_from_request` = True** with the pricing key `fastino/GLiDE`.
- **Response differences from System One** (Fastino's own migration notes):
  - "TypeSafe's `score` is a probability-weighted float. Its GLiDE equivalent is `expected_level`. GLiDE's `score` is instead the integer index of the most probable level."
  - **Impact:** the SDK's `_score` copies `raw["score"]` into `JevAnswer.score`, so GLiDE answers would carry the argmax index instead of the weighted score. Exact semantics need either a host flag that names the score field, or acceptance of the difference.
  - Noul answers add `confidence`, which the SDK ignores.
  - `usage.output_tokens` is non-zero (for example 252) and free. A top-level `token_usage` field is added.
  - "Unsupported top-level fields return `422`".
  - Noul criteria "are optional, but their `true` and `false` values must be strings". The SDK sends `null` for a noul option that has no description (`systemone.py:89`), so Fastino may reject it.
- **Limits.** "Each rendered question prompt (`state` plus that question) must fit within **40,000** tokens". "Choice requires **2 to 255 options** … Score accepts at most **255 levels**." No question maximum is documented.
- **Price.** "| GLiDE | \$0.15 | \$0 |" (per 1M input / output tokens). "GLiDE responses report `usage.output_tokens` for their structured answers, but those output tokens are priced at \$0; only input tokens are billed at the listed rate." → `fastino/GLiDE: 0.15 / 0.0`.
- **Not shippable: Fastino GLiNER-2.5-Decide** ($0.03 on the same page). It is served only on `/v1/chat/completions` with a `classifications` schema and returns `{label, confidence}` inside a chat message. There is no distribution and no noul (https://docs.fastino.ai/concepts/gliner-2-5-decide-call, per a helper's read).

#### 3.1.9 Alibaba Cloud Model Studio: `decision-model-preview`. Ship candidate, but **free and preview**, with a tenant-scoped host.

- **Docs.** https://www.alibabacloud.com/help/en/model-studio/decision-model-api.md (Chinese: https://help.aliyun.com/zh/model-studio/decision-model-api.md). Model page: https://www.alibabacloud.com/help/en/model-studio/decision-model-preview.md.
- **Endpoint.**
  - Singapore: "https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/systemone"
  - China (Beijing): "https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/systemone"
  - Protocol: "TypeSafe System One (`POST /compatible-mode/v1/systemone`)".
  - **The host includes the caller's WorkspaceId**, so there is no shared default. It is tenant-scoped like Cloudflare and Foundry: `DEFAULT_ENDPOINTS` would be `""` and the caller passes `endpoint`.
- **Auth.** "API key, in the format: `Bearer $DASHSCOPE_API_KEY`". → BEARER, env var **`DASHSCOPE_API_KEY`**.
- **Model.** "decision-model-preview". The response `model` is "Model name echoed back.", so `model_from_request` = False works.
- **Answers.** Standard System One. "For `noul`: P(yes), where 0 = no and 1 = yes"; "confidence … (returned for `choice` / `score`)". The response adds `request_id` and `latency_ms`.
- **Usage.** Only `input_tokens` is documented. The SDK's `JevUsage.from_usage_payload` accepts a missing `output_tokens` (`vidbyte/agents/pricing/typesafe.py:42-47`); `total_tokens` is then None.
- **Limits.**
  - Choice takes "1–255 items".
  - Score is documented two ways: "2–10 levels" in the criteria section and "2–255 (3–7 recommended)" in the limits section. The page does not reconcile them.
  - "No hard limit on the number of questions (recommended: ≤ 16…)".
  - "Context: maximum 65536 tokens; overlong `state` is rejected or truncated."
  - Per a helper's read, rate limits are 1,200 RPM and 2,000,000 TPM (model page).
- **Price** (https://www.alibabacloud.com/help/en/model-studio/model-pricing.md, section "Decision model", verified in the raw `.md`):
  - "You are charged for input tokens."
  - The table row reads `decision-model-preview | Limited-time free` in both the Singapore and Beijing tabs.
  - **No paid rate or end date is published.** A `0.0 / 0.0` row would match today's price and satisfy C009, but it goes stale silently when billing starts. A user decision is needed.

#### 3.1.10 Decision Models (decisionmodels.io, formerly "System1 Models"): `s1-fast`, `s1-pro`. Conditional.

- **Docs.** https://decisionmodels.io/docs/quickstart and https://decisionmodels.io/docs/api. Pricing: https://decisionmodels.io/pricing. Per a helper's fetch of the home page, the operator is "a brand of productivity-boost.com Betriebs UG (haftungsbeschränkt) & Co. KG".
- **Endpoint.** `POST https://api.decisionmodels.io/v1/systemone`, plus `/v1/multimodal` for images. Optional region header `S1-Region: eu`.
- **Auth.** `-H "Authorization: Bearer $SYSTEM1_API_KEY"`. → BEARER, env var **`SYSTEM1_API_KEY`**.
- **Response.** `usage: { "input_tokens": 328, "output_tokens": 0, "decisions": 1 }`. Every example is labelled "illustrative".
- **Limits** (these make it a poor fit):
  - "s1-fast and s1-vision accept one question."
  - s1-pro bundles at most 3 questions (per a helper's read).
  - Maximum input is "up to 4,096 (s1-fast), 32,000 (s1-pro) and 32,000 (s1-vision) input tokens".
- **Price** (launch rates per 1M input tokens, before taxes; "Output tokens are free"). The price depends on the processing tier chosen per key:
  - "s1-fast Plumb-4B · text $0.032 $0.034" (Peer-to-Peer / EU).
  - s1-pro "$0.038" / "$0.040".
  - s1-vision with image "$0.217" / "$0.228".
  - Peer-to-Peer is an "Elastic capacity · per-key opt-in" tier, and EU is "EU-only inference · DPA". The SDK has one rate per model, so it cannot follow the key's tier.
- **Verdict: conditional.** The docs, price, and wire are first-party. But s1-fast's one-question limit breaks multi-question requests, the price depends on account settings, and the examples are "illustrative". If shipped, the default should be `s1-pro` (EU `0.040 / 0.0`).

#### 3.1.11 milliseconds.ai (CloudRaker): `decision-machine-1`. Conditional: the vendor disclaims calibration.

- **Docs.** https://docs.milliseconds.ai/typesafe/overview.md and https://milliseconds.ai/llms.txt. Auth: https://docs.milliseconds.ai/authentication.md.
- **Endpoint.** "`decision-machine-1` serves `POST https://api.milliseconds.ai/v1/systemone`. The request and response follow the wire format of TypeSafe's `/v1/systemone`."
- **Auth.** `authorization: Bearer $MS_API_KEY`. → BEARER, env var **`MS_API_KEY`**.
- **Model.** `decision-machine-1`, which is optional. "The response echoes that name", so `model_from_request` = False works.
- **Limits.** "`choice` accepts 2 to 64 options. `score` accepts 2 to 10 levels. One call carries at most 32 questions." State is "At most 20,000 characters once rendered". Validation errors return 400, not 422.
- **Price.** "Production keys (prod_sk): purchased credits only at $0.04 per million input tokens; output tokens cost $0." → `decision-machine-1: 0.04 / 0.0`.
- **Why conditional.** The docs say: "**They are not measured accuracy.** A probability of 0.94 is the model's score for that decision. It is not a promise that 94 of 100 such decisions are correct." (https://docs.milliseconds.ai/concepts/decisions-and-probabilities.md). The wire is complete. Whether this counts as "calibrated" is for the user to decide; TypeSafe itself publishes no calibration metric either (r1 §1).

### 3.2 Ship candidates: hosts and gateways reselling models the SDK already reaches

Each of these is cheap to add (one `SystemOneHost` row). None adds a new model. The spec author should weigh whether a second route to Jev or Clef is worth a `ModelProvider` member.

#### 3.2.1 DigitalOcean Inference: TypeSafe Jev pass-through (`typesafe-jev-1.13.0`). Ship candidate.

- **Docs.** https://docs.digitalocean.com/products/inference/how-to/use-system-one-api/index.html.md. Models: https://docs.digitalocean.com/products/inference/details/models/index.html.md. Pricing: https://docs.digitalocean.com/products/inference/details/pricing/index.html.md.
- **Endpoint.** "Send a `POST` request to `https://inference.do-ai.run/v1/systemone`". The models table calls it a "passthrough to TypeSafe AI" that is "not OpenAI-compatible".
- **Auth.** `Authorization: Bearer $MODEL_ACCESS_KEY`; "The examples below read it from a `MODEL_ACCESS_KEY` environment variable." → BEARER, env var **`MODEL_ACCESS_KEY`**. That name is generic and may clash with other tools.
- **Model.** "Use `typesafe-jev-1.13.0`". The response example echoes `"model": "typesafe-jev-1.13.0"`.
- **Limits.** "64K tokens per request total and separately 32K for the state plus the single longest question". Access may require a higher tier: "If a request returns `this model is not available for your subscription tier`, raise your tier".
- **Price** ("TypeSafe AI Models" table): "| [Jev](https://docs.typesafe.ai/models) | USD per 1 million tokens. Standard, All prompts: Input $0.042; Output N/A. |" → `typesafe-jev-1.13.0: 0.042 / 0.0`.

#### 3.2.2 sference (Neural Compute Ltd, EU host): Cloudflare Clef (`Cloudflare/clef`). Ship candidate.

- **Docs.** https://sference.com/docs/guides/decisions. Model page: https://sference.com/models/Cloudflare/clef.
- **Endpoint.** `curl https://api.sference.com/v1/decisions`, with a System One body on a `/decisions` path ("questions : 1–64 named questions").
- **Auth.** `-H "Authorization: Bearer $SFERENCE_API_KEY"`; "client = SferenceClient() # reads SFERENCE_API_KEY". → BEARER, env var **`SFERENCE_API_KEY`**.
- **Limits.** Choice takes an "Object of 1–256 labels → descriptions". Score takes an "Ordered list of 1–256 levels". Per a helper's read, the whole request is limited to 1 MiB and the model has a 64K-token context.
- **Price.**
  - Guide: "Only successful decisions are billed, at $0.24 per 1M input tokens."
  - FAQ: "On input tokens only: $0.24 per 1M tokens, and only for successful responses. There is no output rate because decisions models generate no text".
  - Caveat on the models table: "Serverless rates per 1M tokens at realtime priority, confirmed per model when your account is provisioned."
  - → `Cloudflare/clef: 0.24 / 0.0`.
- **Response `model` echo.** Not verified. → `model_from_request` = True.

#### 3.2.3 Vercel AI Gateway: Jev, d1, Decision-1, gpt-6-luna, Laya on **both** wires. Ship candidate (revisits Q-3 / NG-9).

- **System One** (new since r1). https://vercel.com/docs/ai-gateway/sdks-and-apis/typesafe.md
  - Base URL `https://ai-gateway.vercel.sh/typesafe`; "`POST /typesafe/v1/systemone` answers typed questions about state".
  - The response example has `"model": "typesafe-ai/jev"` and `"usage": { "input_tokens": 275, "output_tokens": 20 }`, plus `provider_metadata.gateway.cost` ("0.00001155"). That is a per-response USD cost, like OpenRouter's `usage.cost`.
- **OpenAI Decisions.** https://vercel.com/docs/ai-gateway/sdks-and-apis/openai-decisions.md
  - "Set `model` to any decision model slug, such as `openai/gpt-6-luna-decisions` or `typesafe-ai/jev`."
  - Choice takes "between 1 and 255 `choices`"; at most 128 images.
  - `usage` is `{input_tokens, output_tokens, total_tokens}`. Refusals come back as `{ "type": "refusal", "name": ... }`.
  - So A-7 holds, and Vercel also routes non-OpenAI models over this wire.
- **Auth.** `Authorization: Bearer $AI_GATEWAY_API_KEY`. → BEARER, env var **`AI_GATEWAY_API_KEY`**.
- **Prices** (Vercel's own catalog, `GET https://ai-gateway.vercel.sh/v1/models`, `type: "evaluation"`, USD per token):

  | Model | Vercel price |
  |---|---|
  | `typesafe-ai/jev` | `{'input': '0.000000042', 'output': '0'}` ($0.042/M) |
  | `liquid/d1` | `{'input': '0.00000004', 'output': '0'}` ($0.04/M) |
  | `microsoft/microsoft-decision-1` | `{'input': '0.000000042', 'output': '0'}` ($0.042/M) |
  | `openai/gpt-6-luna-decisions` | `{'input': '0.0000001'}` ($0.10/M) |
  | `convaiinnovations/laya` and `convaiinnovations/laya-free` | `{'input': '0', 'output': '0'}` |

  - Laya is free "through October 31, 2026", after which billing starts at an unstated price (changelog https://vercel.com/changelog/laya-decision-model-now-available-on-ai-gateway-free-through-october-31, per a helper's read).
- **Markup.** "**AI Gateway charges no markup and no platform fee on tokens.** You pay the provider's list price" (https://vercel.com/docs/ai-gateway/pricing.md). So Vercel's rows equal each provider's own price.
- **SDK fit.**
  - D-8 / NG-9 chose an endpoint-override recipe on the OpenAI Decisions adapter.
  - New facts: (a) Vercel now also serves the System One wire; (b) it carries four or five decision models, not one; (c) the per-response cost sits in `provider_metadata.gateway.cost`.
  - A first-class member would be `SystemOneHost("Vercel AI Gateway", path="/systemone", BEARER)` with default endpoint `https://ai-gateway.vercel.sh/typesafe/v1`. The echo is the gateway slug, so `model_from_request` = False works with slug-keyed rows.
  - The spec author decides whether Q-3 flips.

#### 3.2.4 LLM Gateway (llmgateway.io): Jev. Ship candidate, with a fee outside the token rate.

- **Docs.** Changelog dated Sept 20, 2026: https://llmgateway.io/changelog/system-one-typed-decisions. Feature docs: https://docs.llmgateway.io/features/system-one.
- **Endpoint.** "POST https://api.llmgateway.io/v1/systemone".
- **Auth.** `-H "Authorization: Bearer $LLM_GATEWAY_API_KEY"`. → BEARER, env var **`LLM_GATEWAY_API_KEY`**.
- **Models.** "The first decision model is typesafe/jev-1.13.0 from TypeSafe AI". Per a helper's read, `https://api.llmgateway.io/v1/models` adds the aliases `jev`, `jev-latest`, and `jev-preview`, and the response echo carries the provider prefix (`"typesafe/jev-1.13.0"`). → `model_from_request` = True, or rows keyed by the prefixed echo.
- **Limits.** "Choice questions take up to 255 options; score questions take two to ten ordered levels." Also "a per-organization rate limit of 600 requests per minute."
- **Price.** The changelog says "Jev 1.13, billed on input only … at $0.042". The pricing page adds "Pay per token + 5% fee" and "Platform Fees 5% on credit usage" ("Non-US cards: +1.5% intl fee").
  - The token rate passes through TypeSafe's $0.042. The 5% is charged on credits, and the SDK cannot represent it.

#### 3.2.5 Eden AI: Jev (alpha). Ship candidate (alpha).

- **Docs.** https://www.edenai.co/docs/v3/llms/decisions.
- **Endpoint.** `POST https://api.edenai.run/v3/alpha/decisions` (System One body), plus `GET https://api.edenai.run/v3/alpha/decisions/models`.
- **Model.** "provider/model , for example typesafe/jev-latest".
- **Auth.** Per a helper's read, `Authorization: Bearer YOUR_API_KEY`. No env var is named.
- **Price.** "Decision models are billed on input only . Output is free". The table row reads "1,000,000 any $0.042".
- **Caveat.** Per a helper's read, the docs warn of breaking changes "without a deprecation period".

#### 3.2.6 AI/ML API (aimlapi.com): Jev at a markup. Ship candidate (marked up).

- **Docs.** https://docs.aimlapi.com/api-references/decision-models.
- **Endpoint.** `https://api.aimlapi.com/v1/decisions`, POST implied by curl `-d`, System One body. Header `Authorization: Bearer <YOUR_AIMLAPI_KEY>`. No env var is named.
- **Model.** `typesafe/jev`. The example response echoes `"typesafe/jev-1.13-20260917"`. The request id is a prefix of the echo, so longest-prefix pricing on `typesafe/jev` works either way.
- **Price** (https://aimlapi.com/models/typesafe-jev, schema.org offer): `"price": "0.0577668"`, `"unitText": "per 1M input tokens"`. Output is free. That is about 37.5% above TypeSafe's own $0.042.

#### 3.2.7 Requesty: Jev, Clef, pplx-decider. Ship candidate (experimental).

- **Docs.** https://docs.requesty.ai/features/decisions.md and https://docs.requesty.ai/api-reference/endpoint/decisions-create.md.
- **Status.** "**Experimental.** Decision model support is new and the `questions` response format is not yet stable. The request and response shapes documented here may change in a future release without a deprecation period."
- **Two routes.**
  - (a) `POST https://router.requesty.ai/v1/systemone`, the System One wire. Answers may be `{"type": "refusal"}`, an extension the System One normalizer would reject.
  - (b) Chat Completions, Messages, or Responses with `response_format: {"type":"questions", …}`, which returns the answers as JSON inside the assistant message. This is a new wire.
- **Models.** `typesafe/jev-latest`, `cloudflare/clef`, `perplexity/pplx-decider-v1-27b`. Auth is `Authorization: Bearer YOUR_REQUESTY_API_KEY`. No env var is named.
- **Price** (per a helper's read):
  - The models API gives `typesafe/jev-1.13.0` `"input_price": 4.2e-08` ($0.042/M) and `cloudflare/clef` 2.4e-07.
  - The model pages show "$0.04" for Jev and pplx-decider.
  - Billing adds "A 5% service fee is added to every top-up".
- **Note.** Requesty's pplx-decider is v1 ($0.04 per its page), while Perplexity's own API lists $0.02 (r1). That is another sign that a gateway's rate can differ from the vendor's.

### 3.3 New model on an existing provider: Cloudflare `clef-omni`

- Cloudflare's Workers AI pricing page now lists "| @cf/cloudflare/clef-omni | $0.150 per M input tokens | 13636 neurons per M input tokens |" between clef ($0.240) and clef-flash ($0.038). https://developers.cloudflare.com/workers-ai/platform/pricing/ (raw `index.md`).
- Model page: "Clef-omni is a multimodal decision model built on a 30B-parameter mixture-of-experts (3B active) backbone … reads the state as text, JSON, images, audio, or video". Each request accepts up to 4 audio clips and 2 videos. https://developers.cloudflare.com/workers-ai/models/clef-omni/
- **Wire difference.** Its curl path is `/ai/run/@cf/cloudflare/clef-omni` with body `model: "clef-omni"`. The SDK's Cloudflare row uses the constant path `/run/@cf/cloudflare/clef` (`CLOUDFLARE_CLEF_PATH`). Calling `clef-omni` would need either that path to accept `model:"clef-omni"` (unverified) or a per-model path.
- Text use matches the existing Cloudflare row. If added, the pricing row is `clef-omni: 0.15 / 0.0`. THIRD-PARTY: OpenRouter lists `cloudflare/clef-omni` at $0.15, created 2026-10-09.

### 3.4 Not shippable (with reason)

| Candidate | What exists | Why not shippable | Evidence |
|---|---|---|---|
| Google MediaPipe Decision Maker / Chrome DecisionModel | on-device decision task (§1.2) | no hosted HTTP API, no price | §1.2 URLs |
| Telnyx Decision Models (beta) | `POST https://api.telnyx.com/v2/ai/typesafe/v1/systemone`, `telnyx/decision-flash` ($0.035) and `telnyx/decision-pro` ($0.20), env `TELNYX_API_KEY` | own FAQ: "Are the scores calibrated probabilities?" "No. Option scores are relative preferences across the options you supply"; "Telnyx manages the underlying models behind these public aliases" | https://developers.telnyx.com/docs/inference/decision-models.md ; https://telnyx.com/products/decision-models |
| Respan Span-01 / Span-01 Lite | `POST https://api.respan.ai/api/v1/scores`; `span-01-pro` $0.02/M, `span-01-free` free (blog) | own wire (a conversation `span` plus `behaviors[]` → `p_present/p_absent/p_not_observable`); no choice or score kinds; no arbitrary state | https://www.respan.ai/blog/introducing-span-1 ; https://www.respan.ai/docs/apis/gateway/run-span-01 |
| Upstage Solar Decide Flash | OpenRouter slug only | no first-party docs or price | §3.1.3 |
| Fastino GLiNER-2.5-Decide | chat route, label plus confidence | no distribution, no noul | §3.1.8 |
| Swarms API | `POST https://api.swarms.world/v1/systemone` in its openapi.json; Jev $0.0483, clef $0.276, clef-flash $0.1035 | prices only in an open GitHub docs issue, not on a docs or pricing page | https://api.swarms.world/openapi.json ; https://github.com/The-Swarm-Corporation/swarms-api-docs/issues/107 |
| SiliconFlow | `POST https://api.siliconflow.com/v1/systemone`, model `Kev-4B` | "[Alpha]… Free of charge until 2026-10-08 (inclusive); if charging starts after that, it will be announced separately." No price announced | https://docs.siliconflow.com/en/api-reference/systemone/create-systemone.md |
| Databricks | `POST https://<workspace_host>/ai-gateway/typesafe/v1/systemone`, `system.ai.openjev-qwen35-4b`; `ai_decide` SQL (beta) | no first-party per-token price for OpenJev; Basic auth with a workspace token; per-workspace host | https://docs.databricks.com/aws/en/machine-learning/model-serving/query-systemone-models ; https://www.databricks.com/product/pricing/foundation-model-serving |
| DeepInfra | openapi `POST https://api.deepinfra.com/v1/decisions` (System One schema) | no model id, no guide, no price; unannounced | https://docs.deepinfra.com/api-reference/decisions/systemone.md |
| Laya (Convai) | open weights; `laya-serve` self-host | no first-party hosted API (the home page links a third-party reseller); free on Vercel only until 2026-10-31 | https://layaai.org/ ; §3.2.3 |
| Together AI Tev1 | `together/Tev1-4B-experimental` on chat | NG-4 (a letter answer over chat, experimental) | https://docs.together.ai/docs/serverless-models |
| Ollama | `POST http://localhost:11434/v1/systemone` (Nimble, Tev1, Clef, Clef Flash) | local only: "Cloud models are rejected."; no price | https://docs.ollama.com/api/systemone.md |
| Portkey, TrueFoundry, LiteLLM | `/v1/decisions` or `/v1/systemone` proxies | bring-your-own TypeSafe key, so no first-party price (TrueFoundry: "cost tracking is unavailable") | https://portkey.ai/docs/product/ai-gateway/decisions-api.md ; https://www.truefoundry.com/docs/ai-gateway/jev.md ; https://docs.litellm.ai/docs/decisions |
| ZenMux | lists `typesafe/jev-1.13` at $0.042 | no endpoint path documented | https://zenmux.ai/typesafe/jev-1.13 |
| Snowflake Decision | `AI_COMPLETE(model => 'snowflake-decision', …)` | private preview; no REST path, no price | https://www.snowflake.com/en/blog/snowflake-decision-cortex-ai-functions/ |
| Featherless "Simple Jev" | demo API | logit-derived (r1 group C), demo only, no price (secondary source) | https://alphasignal.ai/news/featherless-ai-s-simple-jev-turns-open-hugging-face-models-into-classifier-apis |
| Jared Palmer Kev-4B | open weights; served on OpenRouter via SiliconFlow (THIRD-PARTY $0.042) | no first-party hosted API | OpenRouter models API |
| Anthropic | none; Vercel's `anthropic.decisionModel()` is a "language-model adapter" with "prompted estimates of P(true)" | group F (NG-3) | https://platform.claude.com/docs/en/release-notes/overview ; https://ai-sdk.dev/providers/ai-sdk-providers/anthropic.md |

### 3.5 Checked; no decision product found

Each was checked on the docs index (`llms.txt` where one exists), the release notes, and the pricing page, as the helpers recorded:
- **Clouds:** Amazon Bedrock (model cards; GPT-6 Luna on Bedrock has no decisions path); Azure OpenAI / Foundry for OpenAI decisions (§2.4).
- **Labs:** xAI, Mistral, Cohere, Meta Llama API, DeepSeek, Moonshot, Zhipu.
- **Inference hosts:** Fireworks, Groq, Novita, Hugging Face Inference Providers, Nebius Token Factory, SambaNova, Cerebras, Scaleway, OVHcloud.
- **Gateways:** Helicone, Cloudflare AI Gateway (it only lists Workers AI Clef), Kong (its "Decision API" is NVIDIA Switchyard model routing, not typed questions).

---

## 4. Summary table

Prices are USD per 1M tokens (input / output), read 2026-10-10. Base URL means the `DEFAULT_ENDPOINTS` value; the path is appended. All auth headers are `Authorization: Bearer <key>` unless the row says otherwise.

| # | Provider | Model id (default) | Wire | Auth header | Base URL + path | Env var | Price in / out | Price URL | Ship candidate |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Google Gemini | none (MediaPipe Decision Maker is on-device) | none | — | — | — | — | https://ai.google.dev/gemini-api/docs/pricing | **no** (no hosted API) |
| 2 | OpenAI (already shipped) | `gpt-6-luna` (only model) | OpenAI Decisions | Bearer | `https://api.openai.com/v1` + `/decisions` | `OPENAI_API_KEY` | 0.10 / 0.0 | https://developers.openai.com/api/docs/guides/decisions | already in PR |
| 3 | Celeris | `celeris-1-decision` | System One (+ OpenAI Decisions) | Bearer | `https://inference.celeris.ai/celeris-1-decision/v1` + `/systemone` | `CELERIS_API_KEY` | 0.04 / 0.0 | https://docs.celeris.ai/pricing.md | **yes** |
| 4 | Nace.AI | `drex-v1.5` (also `drex-v1.0`) | System One | Bearer | `https://console.nace.ai/v1` + `/systemone` | `NACE_API_KEY` | 0.05 / 0.0 (v1.0: 0.04 / 0.0) | https://console.nace.ai/docs/drex/reference/pricing | **yes** |
| 5 | Upstage | `solar-decide` | System One (beta) | Bearer | `https://api.upstage.ai/v1` + `/systemone` | `UPSTAGE_API_KEY` (from the placeholder) | 0.10 / 0.0 | https://console.upstage.ai/docs/models/solar-decide | **yes** (beta; choice ≤ 26) |
| 6 | Inception (direct) | `mercury-decide` | System One body at `/decisions` | Bearer | `https://api.inceptionlabs.ai/v1` + `/decisions` | `INCEPTION_API_KEY` | 0.02 / 0.0 (promo; regular 0.04) | https://docs.inceptionlabs.ai/get-started/models.md | **yes** |
| 7 | Hanzo | `kai` | System One body at `/decisions` | Bearer | `https://api.hanzo.ai/v1` + `/decisions` | `HANZO_API_KEY` | 0.021 / 0.0 | https://hanzo.ai/pricing | **yes** (1,024-token state + question) |
| 8 | Vansa | `vansa-3.4` | System One | Bearer (+ User-Agent) | `https://api.vansa.org/v1` + `/systemone` | `VANSA_KEY` | 0.034 / 0.0 | https://vansa.org/pricing | **yes** (no SLA) |
| 9 | ZooData (ZooWork Instinct) | `instinct` (also `-dual-4b`, `-tuned-4b`) | System One | Bearer | `https://api.zoodata.ai/v1` + `/systemone` | `ZOODATA_API_KEY` | 0.03 / 0.0 (4B: 0.01 / 0.0) | https://instinct.zoowork.ai/docs/ | **yes** |
| 10 | Fastino | `fastino/GLiDE` | System One (score quirk) | `X-API-Key` (Bearer accepted) | `https://api.fastino.ai/v1` + `/systemone` | `FASTINO_API_KEY` | 0.15 / 0.0 | https://docs.fastino.ai/pricing.md | **yes**, with a score-field flag |
| 11 | Alibaba Model Studio | `decision-model-preview` | System One | Bearer | `https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1` + `/systemone` (tenant-scoped) | `DASHSCOPE_API_KEY` | 0.0 / 0.0 ("Limited-time free") | https://www.alibabacloud.com/help/en/model-studio/model-pricing.md | **yes, needs a user decision** (free preview) |
| 12 | Decision Models (decisionmodels.io) | `s1-pro` (`s1-fast` takes 1 question) | System One | Bearer | `https://api.decisionmodels.io/v1` + `/systemone` | `SYSTEM1_API_KEY` | s1-pro 0.040 / 0.0 (EU tier; Peer-to-Peer tier 0.038); s1-fast 0.034 EU / 0.032 Peer-to-Peer | https://decisionmodels.io/pricing | conditional (question caps, per-key tier pricing) |
| 13 | milliseconds.ai | `decision-machine-1` | System One | Bearer | `https://api.milliseconds.ai/v1` + `/systemone` | `MS_API_KEY` | 0.04 / 0.0 | https://milliseconds.ai/llms.txt | conditional (disclaims calibration) |
| 14 | DigitalOcean (Jev) | `typesafe-jev-1.13.0` | System One | Bearer | `https://inference.do-ai.run/v1` + `/systemone` | `MODEL_ACCESS_KEY` | 0.042 / 0.0 | https://docs.digitalocean.com/products/inference/details/pricing/index.html.md | **yes** (reseller) |
| 15 | sference (Clef) | `Cloudflare/clef` | System One body at `/decisions` | Bearer | `https://api.sference.com/v1` + `/decisions` | `SFERENCE_API_KEY` | 0.24 / 0.0 | https://sference.com/docs/guides/decisions | **yes** (reseller) |
| 16 | Vercel AI Gateway | `typesafe-ai/jev` (+ `liquid/d1`, `microsoft/microsoft-decision-1`, `openai/gpt-6-luna-decisions`, `convaiinnovations/laya`) | System One and OpenAI Decisions | Bearer | `https://ai-gateway.vercel.sh/typesafe/v1` + `/systemone` (or `https://ai-gateway.vercel.sh/v1` + `/decisions`) | `AI_GATEWAY_API_KEY` | jev 0.042 / 0.0; d1 0.04 / 0.0; decision-1 0.042 / 0.0; luna 0.10 / —; laya 0 / 0 | https://vercel.com/docs/ai-gateway/pricing.md + `https://ai-gateway.vercel.sh/v1/models` | **yes** (gateway; reopens Q-3) |
| 17 | LLM Gateway | `typesafe/jev-1.13.0` | System One | Bearer | `https://api.llmgateway.io/v1` + `/systemone` | `LLM_GATEWAY_API_KEY` | 0.042 / 0.0 (+5% fee on credits) | https://llmgateway.io/changelog/system-one-typed-decisions ; https://llmgateway.io/pricing | **yes** (gateway) |
| 18 | Eden AI | `typesafe/jev-latest` | System One body at `/decisions` | Bearer | `https://api.edenai.run/v3/alpha` + `/decisions` | not named | 0.042 / 0.0 | https://www.edenai.co/docs/v3/llms/decisions | yes (alpha) |
| 19 | AI/ML API | `typesafe/jev` | System One body at `/decisions` | Bearer | `https://api.aimlapi.com/v1` + `/decisions` | not named | 0.0577668 / 0.0 | https://aimlapi.com/models/typesafe-jev | yes (marked up about 37.5%) |
| 20 | Requesty | `typesafe/jev-latest` | System One (+ a chat `response_format` wire) | Bearer | `https://router.requesty.ai/v1` + `/systemone` | not named | 0.042 / 0.0 (+5% top-up fee) | https://docs.requesty.ai/features/decisions.md | weak (experimental; `refusal` answers) |
| 21 | Cloudflare (new model) | `clef-omni` | System One | Bearer | existing row; path `/run/@cf/cloudflare/clef-omni` | `CLOUDFLARE_API_TOKEN` | 0.15 / 0.0 | https://developers.cloudflare.com/workers-ai/platform/pricing/ | optional row for an existing member |
| 22 | Telnyx | `telnyx/decision-flash` | System One subset | Bearer | `https://api.telnyx.com/v2/ai/typesafe/v1` + `/systemone` | `TELNYX_API_KEY` | 0.035 / 0.0 | https://telnyx.com/products/decision-models | **no** (scores are "relative preferences") |
| 23 | Respan | `span-01-pro` | own `/api/v1/scores` | Bearer | `https://api.respan.ai/api/v1` | `RESPAN_API_KEY` | 0.02 / 0.0 (blog) | https://www.respan.ai/blog/introducing-span-1 | **no** (own wire, behaviors only) |
| 24 | Swarms | `jev-latest` | System One | Bearer or `x-api-key` | `https://api.swarms.world/v1` + `/systemone` | `SWARMS_API_KEY` | 0.0483 / 0.0 (GitHub issue only) | https://github.com/The-Swarm-Corporation/swarms-api-docs/issues/107 | **no** (no first-party price page) |
| 25 | SiliconFlow | `Kev-4B` | System One | Bearer | `https://api.siliconflow.com/v1` + `/systemone` | not named | none published | https://docs.siliconflow.com/en/api-reference/systemone/create-systemone.md | **no** (no price) |
| 26 | Databricks | `system.ai.openjev-qwen35-4b` | System One | Basic (`token:$DATABRICKS_TOKEN`) | `https://<workspace_host>/ai-gateway/typesafe/v1` + `/systemone` | `DATABRICKS_TOKEN` | none published | https://www.databricks.com/product/pricing/foundation-model-serving | **no** (no price) |

---

## 5. Facts the spec author needs across candidates

1. **No new wire is needed for any ship candidate.**
   - Every row 3–20 in §4 accepts the System One body, so each fits `SystemOneProvider` as one `SystemOneHost` row plus registry, catalog, and pricing rows.
   - Five send the System One body to a `/decisions` path (Inception, Hanzo, sference, Eden AI, AI/ML API), the same pattern as Perplexity and Baseten.
   - Celeris also serves the OpenAI Decisions wire, but `OpenAIDecisionsProvider` is pinned to `ModelProvider.OPENAI`.
2. **Two candidates need small `SystemOneHost` extensions:**
   - Fastino's `score` is an argmax index, with the weighted value in `expected_level` (§3.1.8).
   - Requesty's System One route can return `{"type":"refusal"}`, which the System One normalizer rejects today.
3. **Answer extras are harmless.** Hanzo (`answer_confidence`), Vansa (noul `probabilities`/`confidence`), Fastino (noul `confidence`), Vansa's top-level `id`/`object`/`created`/`latency_ms`, and Alibaba's `request_id`/`latency_ms` are ignored. The normalizer reads only `noul`, or `choice`/`probabilities`/`confidence`/`score`/`legend` (`vidbyte/providers/systemone.py:172-205`).
4. **Noul criteria with `null` values may be rejected.** Fastino says "their `true` and `false` values must be strings". Vansa takes "string keys". The SDK sends `null` for a noul option that has no description (`systemone.py:89`).
5. **Tenant-scoped hosts.** Alibaba (`{WorkspaceId}` in the host) and Databricks (`<workspace_host>`) need a caller-supplied `endpoint`, like Cloudflare and Foundry. Celeris's base URL embeds the model name.
6. **Pricing shapes the pricebook cannot represent.**
   - No ship candidate prices only per request; all charge per input token with free output.
   - The following cannot be represented:
     - Vansa's monthly plans (lower effective rates);
     - decisionmodels.io's per-key tier (Peer-to-Peer vs EU);
     - LLM Gateway's and Requesty's 5% fees on credits or top-ups;
     - Inception's promotional $0.02 (regular $0.04);
     - Alibaba's "Limited-time free" with no end date;
     - OpenAI's 2x input rate above 272K tokens and its regional premiums.
   - Per-image prices exist (milliseconds.ai, decisionmodels.io `s1-vision`) but images are out of scope (NG-5).
7. **C009 (every default needs a pricing row).**
   - Every ship candidate has a first-party rate except Alibaba, whose rate is "Limited-time free".
   - Swarms, SiliconFlow, and Databricks have no first-party price page and cannot ship as members without a user decision.
   - Nace's alias default `drex-latest` would need its own row, so use `drex-v1.5`.
8. **Text-prefix collisions (spec D-8).**
   - No candidate default starts with `gpt-` or with any other text prefix in `MODEL_PREFIX_RUNNER_TYPE_MAP` (`runners.py:360-420`). That includes the bare prefixes `o1`, `o3`, `o4`, and `qwen`.
   - Inception's `mercury-decide` already resolves to the decision runner (`runners.py:320,388`).
   - Vercel's `openai/gpt-6-luna-decisions` starts with `openai/`, not `gpt-`.
   - No new `ModelProvider` value would clash with an existing one (`vidbyte/lib/enums/model_provider.py:32-50`).
9. **Env-var oddities.** Vansa uses `VANSA_KEY`, DigitalOcean uses `MODEL_ACCESS_KEY`, milliseconds.ai uses `MS_API_KEY`, and decisionmodels.io uses `SYSTEM1_API_KEY`. Upstage documents no env var. Eden AI, AI/ML API, and Requesty name none.

---

## 6. Sources

Read 2026-10-10. "(raw)" means checked by curl against the HTML or `.md` page. "(fetch)" means only a summarising fetch was read. "(helper)" means a research helper read the page and this scout did not re-check it.

**Google.**
- https://developers.google.com/edge/mediapipe/solutions/decision/decision_maker (fetch)
- …/decision_maker/python (fetch)
- …/decision_maker/best-practices (fetch)
- https://developers.googleblog.com/google-ai-edge-with-embeddinggemma-2/ (fetch)
- https://blog.google/innovation-and-ai/technology/developers-tools/embeddinggemma-2/ (fetch)
- https://github.com/explainers-by-googlers/decisions-api (fetch)
- https://dejan.ai/blog/chrome-decisions-api-decisionmodel/ (fetch, secondary)
- https://ai.google.dev/gemini-api/docs/changelog (fetch)
- https://ai.google.dev/gemini-api/docs/models (fetch)
- https://ai.google.dev/api/all-methods (fetch)
- https://ai.google.dev/gemini-api/docs/openai (raw `.md.txt`)
- https://ai.google.dev/gemini-api/docs/pricing (raw `.md.txt`)
- https://ai.google.dev/gemini-api/docs/gemini-3 (fetch)
- https://discuss.ai.google.dev/t/missing-logprobs-support-in-the-newest-gemini-models-3-1-pro-3-6-flash-on-vertex-ai-and-ai-studio/176557 (fetch)
- https://discuss.ai.google.dev/t/missing-logprobs-support-in-next-gen-interactions-api-generationconfig-2/144837 (search snippet)
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/release-notes (fetch)
- https://ai-sdk.dev/docs/ai-sdk-core/decisions (fetch)

**OpenAI.**
- https://developers.openai.com/api/docs/guides/decisions (raw `.md`)
- https://developers.openai.com/api/reference/typescript/resources/decisions/methods/create (raw `.md`)
- https://developers.openai.com/api/reference/python/resources/decisions/methods/create.md (fetch)
- …/admin/…/usage/methods/decisions (fetch)
- https://developers.openai.com/api/docs/pricing (fetch)
- https://developers.openai.com/api/docs/models/gpt-6-luna (fetch)
- https://developers.openai.com/api/docs/changelog (fetch)
- https://community.openai.com/t/decisions-api-is-now-available-in-public-beta/1403877 (fetch)
- https://learn.microsoft.com/en-in/answers/questions/6029135/open-ai-decisions-api-availability-inquiry (helper)
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-6-luna.html (helper)
- Failed with 404: https://developers.openai.com/api/reference/resources/decisions/methods/create and https://developers.openai.com/api/reference/resources/decisions. No decisions entry in https://developers.openai.com/llms.txt, https://developers.openai.com/api/llms.txt, or https://developers.openai.com/api/reference/llms.txt.

**Ship candidates (§3.1–3.3).**
- Celeris (raw): https://docs.celeris.ai/pricing.md, /decisions.md, /models.md, /authentication.md. Launch post https://celeris.ai/celeris-1-decision (helper).
- Nace (raw): https://console.nace.ai/docs/drex/quickstart, /guides/authentication, /reference/models, /reference/pricing, /reference/limits.
- Upstage (raw): https://console.upstage.ai/docs/models/solar-decide, https://console.upstage.ai/api/systemone (+ `.md`), https://console.upstage.ai/llms.txt.
- Inception (raw): https://docs.inceptionlabs.ai/capabilities/decisions.md, /get-started/models.md.
- Hanzo (raw): https://docs.hanzo.ai/docs/decisions, https://hanzo.ai/pricing.
- Vansa (fetch): https://vansa.org/pricing, https://docs.vansa.org/skills/vansa-api/references/api.md. The "No SLA" line and the User-Agent quote are helper reads.
- ZooData (raw): https://instinct.zoowork.ai/docs/.
- Fastino (raw): https://docs.fastino.ai/pricing.md, /inference/systemone.md. GLiNER-2.5-Decide call page (helper).
- Alibaba: https://www.alibabacloud.com/help/en/model-studio/decision-model-api.md (fetch); https://www.alibabacloud.com/help/en/model-studio/model-pricing.md (raw, "Decision model" section); decision-model-preview.md (helper).
- decisionmodels.io (raw): https://decisionmodels.io/pricing, /docs/quickstart, /docs/api. Operator line and s1-pro 3-question cap (helper).
- milliseconds.ai (raw): https://milliseconds.ai/llms.txt, https://docs.milliseconds.ai/typesafe/overview.md, /concepts/decisions-and-probabilities.md, /authentication.md.
- DigitalOcean (raw): use-system-one-api, pricing, and models `index.html.md` pages (URLs in §3.2.1).
- sference (raw): https://sference.com/docs/guides/decisions, https://sference.com/models/Cloudflare/clef.
- Vercel (raw): https://vercel.com/docs/ai-gateway/sdks-and-apis/typesafe.md, /openai-decisions.md, /pricing.md, https://ai-gateway.vercel.sh/v1/models. Laya changelog (helper).
- LLM Gateway (raw): https://llmgateway.io/changelog/system-one-typed-decisions, https://llmgateway.io/pricing. Models API and echo (helper).
- Eden AI (raw): https://www.edenai.co/docs/v3/llms/decisions.
- AI/ML API: https://docs.aimlapi.com/api-references/decision-models (fetch); https://aimlapi.com/models/typesafe-jev (raw).
- Requesty (raw): https://docs.requesty.ai/features/decisions.md, /api-reference/endpoint/decisions-create.md. Prices and fee (helper).
- Cloudflare clef-omni (raw): https://developers.cloudflare.com/workers-ai/platform/pricing/index.md, https://developers.cloudflare.com/workers-ai/models/clef-omni/index.md.

**Rejections (§3.4–3.5).**
- Telnyx (raw): https://developers.telnyx.com/docs/inference/decision-models.md, https://telnyx.com/products/decision-models.
- All other rejection rows (Respan, Swarms, SiliconFlow, Databricks, DeepInfra, Laya, Together, Ollama, Portkey, TrueFoundry, LiteLLM, ZenMux, Snowflake, Featherless, Kev-4B, Anthropic, and every §3.5 vendor) are helper reads at the URLs given in those rows.
- Discovery only, THIRD-PARTY: `https://openrouter.ai/api/v1/models?output_modalities=decisions` (19 decision models; new publishers since early October: `nace-ai/drex-v1.5`, `upstage/solar-decide(-flash)`, `respan/span-01(-lite)`, `cloudflare/clef-omni`, `microsoft/microsoft-decision-1`, `jaredpalmer/kev-4b`); https://github.com/AnotiaWang/awesome-decision-models; https://befailproof.ai/jev/news/decision-model-launches-october-2026/; https://benchlm.ai/decision-models; https://systemonemodels.org/.

**Failed or empty (selection).**
- 404: https://openrouter.ai/upstage/solar-decide-flash; https://docs.hanzo.ai/docs/decisions.md; https://deepinfra.com/nace-ai/drex-v1.5; https://docs.swarms.ai/docs/documentation/capabilities/decision-models.
- 500 error page: https://console.nace.ai/docs/drex/*.md.
- 429: https://platform.inceptionlabs.ai/pricing.
- No Solar Decide line: https://www.upstage.ai/pricing.
- JavaScript-only or not parsed: https://celeris.ai/pricing (the docs page was used instead).
- Not followed: https://docs.databricks.com/aws/en/resources/pricing redirects to www.databricks.com.
- Article body truncated: https://thenewstack.io/openai-decision-models-deployment.
