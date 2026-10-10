# S0 research scout report

Stage: S0 (research scout) for `decision-model-providers`. Date: 2026-10-10. Output: `docs/spec/decision-model-providers/context/provider-research.md`. No commits; no other files touched.

## What I read in the repo (read-only)

- `docs/spec/decision-model-providers/request.md` (allowed).
- `vidbyte/lib/dataclasses/jev.py` (header, `JevProbability`, `JevOption`, `JevQuestion`, `JevDecisionRequest`, `JevAnswer`, `TypeSafeWireQuestion`, `TypeSafeWireRequest`, `JevModelCard`; the file is 377 KB so I read it by line ranges), `vidbyte/providers/typesafe.py` (header, payload builder, JSON body, call builder, failures, answer normalizer), `vidbyte/agents/pricing/typesafe.py` (whole file).
- One grep of `vidbyte/lib/enums/jev.py` for `JevQuestionType` (a fourth file, small deviation from "three files", needed to settle the question-kind vocabulary: `NOUL`, `CHOICE`, `SCORE`). `ls` of `vidbyte/providers/` and `vidbyte/agents/pricing/`.
- Finding that shaped everything: the briefing's "boolean / score / noul = free answer" is wrong; noul *is* the yes/no kind and there is no free-answer kind. The catalog opens with that correction.

## Searches, in order (W = WebSearch, F = WebFetch)

Wave 1 (reference + frontier scan): F typesafe api.md, models.md, confidence.md; W OpenAI logprobs cap; W "calibrated decision model API 2026"; W "TypeSafe Jev competitors"; W Anthropic logprobs; W Gemini logprobs.
Wave 2 (verify the launches the scan surfaced): F the-decoder OpenAI Decisions; F eesel decision-models roundup; F seikodigital Perplexity; F orcarouter Microsoft; F aitools-directory roundup (403); F Bike4Mind issue (403); F decisionsapi.pro; W OpenAI decisions docs; W Perplexity decisions docs; W Microsoft-Decision-1; W Clef; W Strands Decider; W Laya; W Anthropic decision model; W Google DeepMind decision model; W xAI decision/logprobs; W Mistral classifier factory; W Cohere classify deprecation; W Meta/Bedrock decision model; F platform.openai.com chat reference (403).
Wave 3 (primary docs): F OpenAI decisions guide, API reference index, pricing; F Perplexity quickstart, API reference, pricing; F Microsoft Command Line post, tech community post; F Cloudflare Clef model page, blog; F layaai.org, Laya HF card; F Strands blog, GitHub README; F developers.openai.com chat reference; F ai.google.dev generate-content; F docs.claude.com messages (redirect); F docs.x.ai models; W Together Tev1; W OpenRouter Jev; W Bespoke/Kev/Jeeves; W Vercel gateway decisions.
Wave 4 (logprobs fleet + classifiers + judges): F platform.claude.com messages; F ai.google.dev (offset); F Vertex inference; F OpenRouter Jev guide, parameters, microsoft page (404), typesafe page, tev1 page (404); F together.ai Tev1 page, Together chat reference; F Fireworks chat reference; F Groq reference; F DeepSeek chat reference; F Mistral API, classifier factory, pricing; F Cohere deprecations; W Jina classify; W H2O-Lightning; W Azure top_logprobs; W Bedrock logprobs; W Atla; W Patronus; W Galileo/Haize/Flow; W Not Diamond/Martian.
Wave 5 (pricing + remaining providers): F OpenRouter jev model page (404); W OpenRouter decisions reference; W Gemini logprobs range; F Vertex GenerationConfig; F Cloudflare pricing; F HF chat-completion task; F Cerebras chat reference; F SambaNova chat reference (404); F Nebius docs (redirect); F Novita (redirect); W Baseten logprobs; F Writer chat reference; W AI21 logprobs; F Cohere chat reference; F Azure OpenAI reference; F jina.ai/classifier; W Haize; W Flow/Atla; F Vercel changelog; F OpenAI reasoning guide; F DeepSeek pricing; F Gemini pricing; F Claude pricing; F TypeSafe launch blog; F Tev1 HF card; F benchmarkheaven alternatives; F Mistral moderation (404); F Together pricing.
Wave 6 (close gaps): F OpenRouter models JSON; F OpenRouter Go SystemOne README; W OpenRouter decisions reference; W Vertex logprobs range; F Novita chat reference; F Nebius root; W SambaNova logprobs; F Azure v1 chat reference; W AI21 reference; F Baseten chat reference; F Jina launch post; F gpt-6-luna model page; F Responses reference; F the-decoder Jev article; W benchmarkheaven hosted leaderboard; W Mercury Decide; W Fastino; F DeepSeek root; F Fireworks pricing; F Cerebras pricing; F HF pricing; F Baseten pricing; W Microsoft Learn systemone.
Wave 7 (final): F OpenRouter decisions API reference; F OpenRouter mercury page (404); F Baseten Mercury library; W Inception docs; W Fastino docs; F awesome-decision-models README; F systemonemodels.org; F OpenRouter jev compare page; F Vertex inference (offsets 100k, 200k, 300k); F Google logprobs blog; F Perplexity models page; F Clef HF card; F OpenAI decisions create reference (404); W Fireworks pricing; W Cerebras pricing; F AI21 reference; F Nebius llms.txt and chat reference; F LiteLLM decisions; W PostHog Jeeves; W Kev; F Bespoke Nimble HF; F ai.azure.com catalog (no data); F Vercel gateway model page; F Liquid decision-models and d1 pages; F meragpt.com/docs.

Roughly 150 tool calls across seven waves.

## Searches that came back empty or off-target

- Anthropic calibrated decision model 2026: only pricing blogs.
- Google DeepMind decision model 2026: only forecasting papers and robotics news.
- Meta decision model / Bedrock decision model: only Llama-on-Bedrock catalog pages.
- Atla Selene 2026 status: unrelated "Atlas" results; one undated Chinese product page.
- Haize Labs judge API pricing: legal-tech and Judge.me results only.
- Flow AI / Atla docs: only Hugging Face Space commits.
- AI21 logprobs: only OpenAI cookbook results; settled by fetching AI21's reference (no logprobs).
- Microsoft Learn "systemone" quickstart: generic Foundry quickstarts only.
- Gemini API `logprobs` range: found only via Vertex docs and Google's blog, not ai.google.dev.

## Pages that failed to load

- 403: https://www.aitools-directory.com/blog/decision-models-two-speed-stack-ai-weekly-017/ ; https://github.com/Bike4Mind/bike4mind/issues/4115 ; https://platform.openai.com/docs/api-reference/chat/create.
- 404: https://openrouter.ai/typesafe/jev-1.13 ; https://openrouter.ai/microsoft/microsoft-decision-1 ; https://openrouter.ai/togethercomputer/tev1-4b-experimental ; https://openrouter.ai/inception/mercury-decide-20260930 ; https://openrouter.ai/jaredpalmer/kev-4b ; https://developers.openai.com/api/reference/resources/decisions/methods/create ; https://docs.sambanova.ai/cloud/api-reference/endpoints/chat ; https://docs.mistral.ai/capabilities/guardrailing/moderation.
- Rendered without data: https://ai.azure.com/catalog/models/microsoft-decision-1 (JS app); https://www.cerebras.ai/pricing (empty table); https://fireworks.ai/pricing (no serverless table).
- Truncated beyond the fetcher's window (read in parts or partially): ai.google.dev generate-content; Vertex inference reference (needed offset 300000 to reach the logprobs text); platform.claude.com messages; OpenAI chat and responses references; Perplexity pricing/models pages; Cohere chat reference.
- Redirects followed: docs.claude.com → platform.claude.com; docs.nebius.com/studio → docs.tokenfactory.nebius.com; novita.ai/docs → docs.novita.ai.

## Providers considered and dropped (reason)

- Cohere Classify: `/v1/classify` deprecated 2025-09-15, fine-tuning retired.
- Mistral Classifier Factory: deprecated; Mistral moderation: fixed categories.
- Jina Classifier: embedding-similarity softmax over labels, not a question-over-context probability; listed as a near-miss with its endpoint and limits.
- Atla, Patronus, Galileo Luna-2, Haize Labs, Flow AI: no 2026 primary evidence of a public API returning calibrated probabilities for arbitrary questions; Luna-2 enterprise-only.
- Not Diamond, Martian: routers.
- Chrome DecisionModel API: browser feature behind a flag, not a provider.
- Voyage AI: not searched (budget went to the decision-model launches); embeddings/rerank vendor.
- Upstage Solar Decide, Respan Span-01, Nace Drex, Hanzo Kai, Celeris, Clef-omni, Fastino hosted API: kept in §6 as "unverified" because only third-party hubs name them; not given catalog rows.
- xAI, Groq, SambaNova, Mistral, AI21, Anthropic, Bedrock: kept as class 3 rows (self-reported only) so the spec author sees why they do not qualify as calibrated sources.
- Writer, Cohere chat: kept as degraded class 2 (chosen-token logprobs only).

## Judgement calls worth knowing

- I counted OpenRouter, Vercel AI Gateway and Baseten (for Mercury Decide) as providers because each has its own auth, base URL and billing even though the models are someone else's.
- Together Tev1 is catalogued as a class-1 model behind a chat wire; its probabilities depend on logprobs working for that model, which I could not verify.
- Prices for class-2 providers were captured only where an official page rendered; third-party aggregator prices are marked unverified rather than copied into the table.

## Time

Started after the request capture at 01:32 on 2026-10-10 (request.md header). Seven research waves plus writing; the session was interrupted once by a usage limit before the catalog was written, and resumed from captured facts without re-running searches. Precise wall-clock not measured.
