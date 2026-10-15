# Registries

Registry implementations resolving agent, provider/model, pricing, runtime,
prompt, tool, actor, and declarable-component lookups for the SDK, and the
provider key formats that match a developer's API keys to their providers.

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

## Provider Key Format Sources

`ProviderKeyMatcher` in `provider_keys.py` matches a developer's
`api_keys` list to providers. Each source below was opened on 2026-10-13.
A rule that routes a key to a provider (table F, `KEY_FORMATS`) rests on a
first-party source: the vendor's own docs or the vendor's own GitHub
organization. A rule that only refuses a key (table A and the reserved
prefixes) may rest on a secondary source. No example key is copied here.

**Table F: prefixes that prove a provider.** The rules are tried in this
order, and the first full match against the stripped key wins.

| Provider | Pattern | Source (first-party) |
|---|---|---|
| anthropic | `sk-ant-[A-Za-z0-9_-]+` | https://platform.claude.com/docs/en/manage-claude/authentication: an API key is a "Static `sk-ant-api...` secret". https://platform.claude.com/docs/en/api/administration-api: an Admin API key starts "with `sk-ant-admin...`". |
| openrouter | `sk-or-[A-Za-z0-9_-]+` | https://openrouter.ai/docs/cookbook/coding-agents/codex-cli.md: "Copy your key (starts with `sk-or-...`)". https://openrouter.ai/docs/cookbook/coding-agents/claude-desktop-integration.md: "Your OpenRouter API key (e.g. `sk-or-v1-...`)". |
| openai | `sk-(?:proj\|admin)-[A-Za-z0-9_-]+` | `sk-proj-`: https://github.com/openai/plugins/blob/main/plugins/openai-developers/skills/openai-platform-api-key/SKILL.md, "an `sk-proj` key". `sk-admin-`: OpenAI's OpenAPI description, https://raw.githubusercontent.com/openai/openai-openapi/master/openapi.yaml, where the `POST /organization/admin_api_keys` example `value` starts with `sk-admin-`. |
| xai | `xai-[A-Za-z0-9_-]+` | https://docs.x.ai/build/overview and https://docs.x.ai/build/enterprise: `export XAI_API_KEY="xai-..."`. |
| gemini | `AIza[A-Za-z0-9_-]{35}` or `AQ\.[A-Za-z0-9_-]+` | `AIza`: https://docs.cloud.google.com/docs/authentication/api-keys, whose example key is `AIza` plus 35 characters; the length also matches the gitleaks `gcp-api-key` rule (secondary). `AQ.`: https://github.com/google-gemini/cookbook/blob/main/tools/README.md, "legacy `AIza...` and new `AQ.Ab8...` formats", and Google staff on Google's own forum, https://discuss.ai.google.dev/t/gemini-api-key-start-from-aq/171575 and https://discuss.ai.google.dev/t/account-only-generates-aq-prefix-api-keys-aiza-keys-not-available-in-any-project/170415: "AI Studio will now only generate Authentication Key (AQ) keys". No source shows the characters after `AQ.`, so the rule takes the same URL-safe set as the other rows. |
| meta | `LLM\\|[0-9]+\\|[A-Za-z0-9_-]+` | Opened on 2026-10-15. https://dev.meta.ai/docs/authentication, the Meta Model API that serves Muse Spark: "API keys look like this:" an `LLM\|` tag, a numeric app ID, `\|`, then the secret, sent as `Authorization: Bearer`. https://dev.meta.ai/docs/muse-code: Muse Code reads the same key from `META_API_KEY`. No source shows the secret's characters, so the rule takes the same URL-safe set as the other rows. That set agrees with the gitleaks `facebook-access-token` rule (secondary): a 15- or 16-digit app ID, `\|`, then 27 to 40 characters of `[0-9a-z_-]` in either case, the same shape without the `LLM\|` tag. The rule fixes neither length. |

**Table A: which providers take a key that no prefix proves.** Every
rule here only refuses.

| Provider | Takes an unproven key | Source |
|---|---|---|
| anthropic, xai, gemini, openrouter, meta | never | Every key they issue carries their table F prefix (the table F sources, first-party). If that is ever wrong, a real key is refused, never sent to another vendor. |
| openai | only a key that starts with `sk-` | First-party: OpenAI's own key check, `SAFE_OPENAI_API_KEY_PATTERN = /^sk-[A-Za-z0-9_-]+$/`, in https://raw.githubusercontent.com/openai/plugins/main/plugins/openai-developers/scripts/openai-platform-api-key.mjs. Secondary: the gitleaks `openai-api-key` rule. Refuse-only. |
| deepseek, kimi, glm, minimax, mistral, elevenlabs, playai, typesafe | any | No sourced key format: their docs show only placeholders. |

**Reserved prefixes.** A key that starts with a reserved prefix is taken by
no other provider, even when it does not fully match a rule. Every table F
prefix is reserved to its provider, from the first-party sources above.
`RESERVED_PREFIXES` adds only `sk-svcacct-` for openai. Its source is
secondary, the gitleaks `openai-api-key` rule
(https://raw.githubusercontent.com/gitleaks/gitleaks/master/config/gitleaks.toml),
so it is refuse-only: it keeps such a key from every other provider and
never proves one.

The list's order never matters. A key with no proving prefix binds only to
the one configured provider that can take it (unique assignment); when it
is the list's only such key, it binds to the one keyless primary provider
that can take it (the lone-key rule). A key that could belong to more than
one provider, or to none, is refused, and the developer sets it in that
provider's own environment variable instead, which is never matched.
