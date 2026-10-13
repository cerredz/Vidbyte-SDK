# Registries

Registry implementations resolving agent, provider/model, pricing, runtime,
prompt, tool, actor, and declarable-component lookups for the SDK.

## Cache Pricing Source Citations

Per-provider first-party documentation for cache-pricing mechanics behind
`PROVIDER_PRICING`'s `cache_read_per_million` / `cache_write_per_million`
rates in `pricing.py`, checked 2026-08-29; the Meta and Mistral rows were
added 2026-10-11.

Meta's cached-input rates come from its own pricing page,
https://dev.meta.ai/docs/pricing-rate-limits, which replaced the
third-party corroboration this section used to rely on. Mistral publishes a
cached rate only on some model pages (Mistral Large 4); its other rows
leave `cache_read_per_million` unset, so cached tokens bill at the input
rate. Each rate's own source URL is cited in the comment above its block in
`pricing.py`.

| Provider | Source |
|---|---|
| OpenAI | https://developers.openai.com/api/docs/guides/prompt-caching |
| Anthropic | https://platform.claude.com/docs/en/build-with-claude/prompt-caching |
| Gemini | https://ai.google.dev/gemini-api/docs/caching |
| xAI | https://docs.x.ai/developers/advanced-api-usage/prompt-caching |
| DeepSeek | https://api-docs.deepseek.com/guides/kv_cache/ |
| GLM | https://docs.z.ai/guides/capabilities/cache |
| MiniMax | https://platform.minimax.io/docs/api-reference/text-prompt-caching |
| Kimi | https://platform.moonshot.ai/docs/guide/use-context-caching-feature-of-kimi-api |
| Meta | https://dev.meta.ai/docs/prompt-caching |
| Mistral | https://docs.mistral.ai/studio/conversations/advanced/prompt-caching |
| OpenRouter | https://openrouter.ai/docs/guides/best-practices/prompt-caching |
