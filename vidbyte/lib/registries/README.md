# Registries

Registry implementations resolving agent, provider/model, pricing, runtime,
prompt, tool, actor, and declarable-component lookups for the SDK.

## Cache Pricing Source Citations

Per-provider first-party documentation for cache-pricing mechanics behind
`PROVIDER_PRICING`'s `cache_read_per_million` / `cache_write_per_million`
rates in `pricing.py`, checked 2026-08-29.

`ModelProvider.META` is deliberately absent: no first-party Meta Model API
documentation page could be located for Muse Spark's cache pricing despite
the `$0.15/M` `cache_read_per_million` rate in `PROVIDER_PRICING` being
corroborated by multiple independent third-party sources. Omitted rather
than guessed, per the same discipline `docs/design/openai-gpt-5-6-catalog-pricing.md`
applies to the rate table itself.

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
| OpenRouter | https://openrouter.ai/docs/guides/best-practices/prompt-caching |
