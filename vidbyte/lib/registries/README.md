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
| openai | `sk-(?:proj\|svcacct\|admin)-[A-Za-z0-9_-]+` | `sk-proj-`: https://github.com/openai/plugins/blob/main/plugins/openai-developers/skills/openai-platform-api-key/SKILL.md, "an `sk-proj` key". `sk-admin-`: OpenAI's OpenAPI description, https://raw.githubusercontent.com/openai/openai-openapi/master/openapi.yaml, where the `POST /organization/admin_api_keys` example `value` starts with `sk-admin-`. `sk-svcacct-` (opened on 2026-10-15): OpenAI's own Codex lists it among its key prefixes, `OPENAI_API_KEY_PREFIXES = ["sk-proj-", "sk-svcacct-", "sk-admin-", "sk-"]`, in https://github.com/openai/codex/blob/main/codex-rs/network-proxy/src/credential_broker/providers/openai.rs. |
| xai | `xai-[A-Za-z0-9_-]+` | https://docs.x.ai/build/overview and https://docs.x.ai/build/enterprise: `export XAI_API_KEY="xai-..."`. |
| gemini | `AIza[A-Za-z0-9_-]{35}` or `AQ\.[A-Za-z0-9_-]+` | `AIza`: https://docs.cloud.google.com/docs/authentication/api-keys, whose example key is `AIza` plus 35 characters; the length also matches the gitleaks `gcp-api-key` rule (secondary). `AQ.`: https://github.com/google-gemini/cookbook/blob/main/tools/README.md, "legacy `AIza...` and new `AQ.Ab8...` formats", and Google staff on Google's own forum, https://discuss.ai.google.dev/t/gemini-api-key-start-from-aq/171575 and https://discuss.ai.google.dev/t/account-only-generates-aq-prefix-api-keys-aiza-keys-not-available-in-any-project/170415: "AI Studio will now only generate Authentication Key (AQ) keys". No source shows the characters after `AQ.`, so the rule takes the same URL-safe set as the other rows. |
| meta | `LLM\\|[0-9]+\\|[A-Za-z0-9_-]+` | Opened on 2026-10-15. https://dev.meta.ai/docs/authentication, the Meta Model API that serves Muse Spark: "API keys look like this:" an `LLM\|` tag, a numeric app ID, `\|`, then the secret, sent as `Authorization: Bearer`. https://dev.meta.ai/docs/muse-code: Muse Code reads the same key from `META_API_KEY`. No source shows the secret's characters, so the rule takes the same URL-safe set as the other rows. That set agrees with the gitleaks `facebook-access-token` rule (secondary): a 15- or 16-digit app ID, `\|`, then 27 to 40 characters of `[0-9a-z_-]` in either case, the same shape without the `LLM\|` tag. The rule fixes neither length. |

**Table A: which providers take a key that no prefix proves.** Every
rule here only refuses.

| Provider | Takes an unproven key | Source |
|---|---|---|
| anthropic, xai, gemini, openrouter, meta | never | Every key they issue carries their table F prefix (the table F sources, first-party). If that is ever wrong, a real key is refused, never sent to another vendor. |
| openai | only a key that starts with `sk-`, or an access token that starts with `eyJ` | First-party: OpenAI's own key check, `SAFE_OPENAI_API_KEY_PATTERN = /^sk-[A-Za-z0-9_-]+$/`, in https://raw.githubusercontent.com/openai/plugins/main/plugins/openai-developers/scripts/openai-platform-api-key.mjs. Secondary: the gitleaks `openai-api-key` rule. Refuse-only. `eyJ` (opened on 2026-10-15): https://developers.openai.com/api/reference/workload-identity-federation, a workload identity exchange returns `"access_token": "eyJ..."`, "a short-lived bearer token" that "replaces the API key". Refusing it would leave another vendor as its only owner, and unique assignment would then move a second key to openai by elimination. |
| deepseek, kimi, glm, minimax, mistral, elevenlabs, playai, typesafe | any | No sourced key format: their docs show only placeholders. |

**Reserved prefixes.** A key that starts with a reserved prefix is taken by
no other provider, even when it does not fully match a rule. Every table F
prefix is reserved to its provider, from the first-party sources above.
`RESERVED_PREFIXES` adds none: `sk-svcacct-`, once reserved there from
the secondary gitleaks `openai-api-key` rule, now has a first-party
source and proves openai in table F.

The list's order never matters. A key with no proving prefix binds only to
the one configured provider that can take it (unique assignment); when it
is the list's only such key, it binds to the one keyless primary provider
that can take it (the lone-key rule). A key that could belong to more than
one provider, or to none, is refused, and the developer sets it in that
provider's own environment variable instead, which is never matched.

## Browser Tool Sources

`BrowserToolRegistry` in `browser_tools.py` holds one row per tool that the
harness browser functions (`run_<harness>_with_browser`) can mount; the
values live in `vidbyte/lib/constants/browser_tools.py`, one place per fact.
Every stdio row was checked on 2026-10-16: the pinned package was installed
with `npm install` on Node 22.12.0, its entry was started with `node` under a
minimal environment (first with no key), and a `tools/list` probe, run once
without and once with each server-flag group, gave the tool names in the
row's capability tuples. The remote rows come from the vendor's own docs.
The source comment above each row repeats its evidence.

| Tool | Pin or URL (entry) | Key | Evidence |
|---|---|---|---|
| playwright | `@playwright/mcp@0.0.83` (`cli.js`) | none | installed README (`--caps`); `tools/list` without and with each `--caps` group |
| chromedevtools | `chrome-devtools-mcp@1.11.0` (`build/src/bin/chrome-devtools-mcp.js`) | none | installed README (`--no-usage-statistics`, `CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS`); `tools/list`; a network watch at start, quiet with both |
| firecrawl | `firecrawl-mcp@3.30.2` (`dist/index.js`) | optional `FIRECRAWL_API_KEY` | installed README.md:40-72; `tools/list`; starts without a key |
| exa | `exa-mcp-server@3.4.2` (`dist/stdio.cjs`) | optional `EXA_API_KEY` | installed README:25-30, 105-130; `tools/list`; starts without a key |
| tavily | `tavily-mcp@0.2.22` (`build/index.js`) | required `TAVILY_API_KEY` | installed README:20-30, 54-62; `tools/list`; starts without the key but answers no call without it (spec A-10) |
| brave | `@brave/brave-search-mcp-server@2.1.4` (`dist/index.js`) | required `BRAVE_API_KEY` | installed README; `tools/list`; exits at start without the key |
| perplexity | `@perplexity-ai/mcp-server@1.3.0` (`dist/index.js`) | required `PERPLEXITY_API_KEY` | installed README; `tools/list`; exits at start without the key |
| brightdata | `@brightdata/mcp@3.1.0` (`server.js`) | required `API_TOKEN` | installed README; `tools/list` (the 14 `scraping_browser_*` tools); calls api.brightdata.com at start |
| apify | `@apify/actors-mcp-server@0.18.4` (`dist/stdio.js`) | required `APIFY_TOKEN` | installed README; `tools/list`; calls api.apify.com and Sentry at start |
| linkup | `linkup-mcp-server@3.4.0` (`bin/linkup-mcp-server.js`) | required `LINKUP_API_KEY` | installed README:44-50, 72-80; `tools/list` |
| browserbase | `https://mcp.browserbase.com/mcp` | required, as a Bearer header | Browserbase MCP README.md:15-47, 66-85 (six tools) |
| jina | `https://mcp.jina.ai/v1` | optional, as a Bearer header | Jina MCP README.md:15-17, 64-80, 122-136 |
| parallel | `https://search.parallel.ai/mcp` | optional, as a Bearer header | https://docs.parallel.ai/integrations/mcp/search-mcp ("free to use, no API key required") |

Names a caller may expect but that the registry refuses each carry their
reason in `BROWSER_TOOL_EXCLUSION_REASONS`: browserstack (two credentials),
searxng (needs a running instance), wdio (fails to start on Node 22.12),
fetch and duckduckgo (an unpinned uvx runtime and a start slower than
Grok's grace), agentbrowser, playwrightcli, midscene and devbrowser (a CLI
plus a skill, no server), crawl4ai (Docker only), browseruse (its own LLM),
kernel and cloudflare (OAuth only), puppeteer (archived), hyperbrowser
(unmaintained), and scrapling, steel and browserless (not yet verified).

**To bump a stdio tool:** install `<package>@<version>` into an empty folder
with `npm install --prefix <folder>` on Node 22.12.0, start its entry with
`node` and no key, and run `tools/list` once per server-flag group. Then
change the tool's `_VERSION` (and `_ENTRY` if the bin moved) and its
capability tuples in the constants module, and update the row's source
comment and this table. Pin an exact version, never a range or `latest`. A
bump installs into a new `~/.vidbyte/tools/<tool>-<version>` folder; the old
one stays until the user deletes it.

**To add a tool:** add a `BrowserTool` member, the tool's constants under
its own prefix, a row in `BrowserTool` order with its source comment, and a
row here. A tool that cannot answer a call without a key is `REQUIRED`;
one that works without a key but takes one is `OPTIONAL`. A remote tool
takes its key only as a Bearer header. The registry tests in
`tests/features/harness_threads/test_harness_threads_browser_registry.py`
pin every row against the vendor facts, so they change with it.
