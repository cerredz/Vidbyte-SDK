# Web-operation Provider References

## Scope

| Provider | First-party API documentation | Boundary reference |
| --- | --- | --- |
| Brave Search | [Search API](https://brave.com/search/api/) | [Search API dashboard documentation](https://api.search.brave.com/app/documentation/web-search/get-started) |
| Browserbase | [Platform introduction](https://docs.browserbase.com/welcome/introduction) | [REST API reference](https://docs.browserbase.com/reference/api/overview) |
| Exa | [Search reference](https://exa.ai/docs/reference/search) | [Contents reference](https://exa.ai/docs/reference/contents-api-guide) |
| Firecrawl | [v2 API introduction](https://docs.firecrawl.dev/api-reference/v2-introduction) | [Scrape endpoint](https://docs.firecrawl.dev/api-reference/endpoint/scrape) |
| Parallel | [Search quickstart](https://docs.parallel.ai/search/search-quickstart) | [Extract API reference](https://docs.parallel.ai/api-reference/extract/extract) |
| Tavily | [API introduction](https://docs.tavily.com/documentation/api-reference/introduction) | [Extract endpoint](https://docs.tavily.com/documentation/api-reference/endpoint/extract) |

Retrieved 2026-08-29. These links are the provider-owned references for API
shape, authentication, and endpoint semantics; provider version compatibility
still requires runtime verification when an adapter changes.

## Expanded Provider Reading Maps

The two-link matrix is a routing summary. The maps below intentionally keep the
nearby quickstarts, endpoint references, SDKs, limits, integrations, and
operational pages visible for each web provider. They are not a claim that the
SDK implements every listed capability.

### Brave Search

- [Search API overview](https://brave.com/search/api/)
- [API quickstart](https://api-dashboard.search.brave.com/documentation/quickstart)
- [Authentication](https://api-dashboard.search.brave.com/documentation/guides/authentication)
- [Rate limiting](https://api-dashboard.search.brave.com/documentation/guides/rate-limiting)
- [Pricing](https://api-dashboard.search.brave.com/documentation/pricing)
- [Web search GET](https://api-dashboard.search.brave.com/api-reference/web/search/get)
- [Web search POST](https://api-dashboard.search.brave.com/api-reference/web/search/post)
- [News search GET](https://api-dashboard.search.brave.com/api-reference/news/search/get)
- [News search POST](https://api-dashboard.search.brave.com/api-reference/news/search/post)
- [Image search GET](https://api-dashboard.search.brave.com/api-reference/images/search/get)
- [Image search POST](https://api-dashboard.search.brave.com/api-reference/images/search/post)
- [Video search GET](https://api-dashboard.search.brave.com/api-reference/videos/search/get)
- [Video search POST](https://api-dashboard.search.brave.com/api-reference/videos/search/post)
- [Suggest search GET](https://api-dashboard.search.brave.com/api-reference/suggest/search/get)
- [LLM context GET](https://api-dashboard.search.brave.com/api-reference/llm/context/get)
- [Chat completions POST](https://api-dashboard.search.brave.com/api-reference/chat/completions/post)
- [API versioning](https://api-dashboard.search.brave.com/documentation/guides/api-versioning)
- [Query parameters](https://api-dashboard.search.brave.com/documentation/guides/query-parameters)
- [Response formats](https://api-dashboard.search.brave.com/documentation/guides/response-format)
- [Errors](https://api-dashboard.search.brave.com/documentation/guides/errors)
- [Search Goggles](https://api-dashboard.search.brave.com/documentation/guides/goggles)
- [Extra snippets](https://api-dashboard.search.brave.com/documentation/guides/extra-snippets)
- [AI grounding](https://api-dashboard.search.brave.com/app/documentation/ai-grounding/query)
- [Privacy policy](https://api-dashboard.search.brave.com/app/documentation/general/privacy-policy)
- [Terms of service](https://api-dashboard.search.brave.com/app/documentation/general/terms-of-service)

### Browserbase

- [Welcome introduction](https://docs.browserbase.com/welcome/introduction)
- [Getting started](https://docs.browserbase.com/welcome/getting-started)
- [Stagehand quickstart](https://docs.browserbase.com/welcome/quickstarts/stagehand)
- [Skills quickstart](https://docs.browserbase.com/welcome/quickstarts/skills)
- [Integration quickstarts](https://docs.browserbase.com/integrations/get-started)
- [Reference introduction](https://docs.browserbase.com/reference/introduction)
- [Create a session](https://docs.browserbase.com/reference/api/create-a-session)
- [List sessions](https://docs.browserbase.com/reference/api/list-sessions)
- [Update a session](https://docs.browserbase.com/reference/api/update-a-session)
- [Session live URLs](https://docs.browserbase.com/reference/api/session-live-urls)
- [Python SDK](https://docs.browserbase.com/reference/sdk/python)
- [Node.js SDK](https://docs.browserbase.com/reference/sdk/nodejs)
- [Agents overview](https://docs.browserbase.com/platform/agents/overview)
- [How agents work](https://docs.browserbase.com/platform/agents/how-it-works)
- [Browser contexts](https://docs.browserbase.com/platform/browser/core-features/contexts)
- [Create browser session](https://docs.browserbase.com/platform/browser/getting-started/create-browser-session)
- [Manage browser session](https://docs.browserbase.com/platform/browser/getting-started/manage-browser-session)
- [Using a browser session](https://docs.browserbase.com/platform/browser/getting-started/using-browser-session)
- [Remote versus local browser](https://docs.browserbase.com/platform/browser/getting-started/remote-browser-versus-local-browser)
- [Session observability](https://docs.browserbase.com/platform/browser/observability/observability)
- [Session live view](https://docs.browserbase.com/platform/browser/observability/session-live-view)
- [Session recording](https://docs.browserbase.com/platform/browser/observability/session-recording)
- [Session replay](https://docs.browserbase.com/platform/browser/observability/session-replay)
- [Fetch platform](https://docs.browserbase.com/platform/fetch/overview)
- [Identity authentication](https://docs.browserbase.com/platform/identity/authentication)
- [Proxy configuration](https://docs.browserbase.com/platform/identity/proxies)
- [Search platform](https://docs.browserbase.com/platform/search/overview)
- [Runtime](https://docs.browserbase.com/platform/runtime/overview)

### Exa

- [Exa documentation](https://exa.ai/docs)
- [Search API guide](https://exa.ai/docs/reference/search-api-guide)
- [Search reference](https://exa.ai/docs/reference/search)
- [Search for coding agents](https://exa.ai/docs/reference/search-api-guide-for-coding-agents)
- [Contents API guide](https://exa.ai/docs/reference/contents-api-guide)
- [Contents for coding agents](https://exa.ai/docs/reference/contents-api-guide-for-coding-agents)
- [Get contents](https://exa.ai/docs/reference/get-contents)
- [Contents best practices](https://exa.ai/docs/reference/contents-best-practices)
- [Answer API](https://exa.ai/docs/reference/answer)
- [Context API](https://exa.ai/docs/reference/context)
- [OpenAI compatibility](https://exa.ai/docs/reference/openai-compat)
- [Anthropic tool calling](https://exa.ai/docs/reference/anthropic-tool-calling)
- [SDKs](https://exa.ai/docs/.mintlify/skills/build-with-exa/references/sdks)
- [HTTP requests](https://exa.ai/docs/.mintlify/skills/build-with-exa/references/http-requests)
- [Models and modes](https://exa.ai/docs/.mintlify/skills/build-with-exa/references/models-and-modes)
- [Prompting and patterns](https://exa.ai/docs/.mintlify/skills/build-with-exa/references/prompting-and-patterns)
- [Common mistakes](https://exa.ai/docs/.mintlify/skills/build-with-exa/references/common-mistakes)
- [Exa MCP](https://exa.ai/docs/reference/exa-mcp)
- [Agent API overview](https://exa.ai/docs/reference/agent-api/overview)
- [Create an agent run](https://exa.ai/docs/reference/agent-api/create-a-run)
- [Get an agent run](https://exa.ai/docs/reference/agent-api/get-a-run)
- [List run events](https://exa.ai/docs/reference/agent-api/list-run-events)
- [Stop an agent run](https://exa.ai/docs/reference/agent-api/stop-a-run)
- [Monitors API](https://exa.ai/docs/reference/monitors-api-guide)
- [Agent skills](https://exa.ai/docs/reference/agent-skills)
- [Pricing](https://exa.ai/docs/reference/pricing)
- [Rate limits](https://exa.ai/docs/reference/rate-limits)
- [Integrations](https://exa.ai/docs/integrations)

### Firecrawl

- [Introduction](https://docs.firecrawl.dev/introduction)
- [Python quickstart](https://docs.firecrawl.dev/sdks/python)
- [Node.js quickstart](https://docs.firecrawl.dev/sdks/node)
- [API v2 introduction](https://docs.firecrawl.dev/api-reference/v2-introduction)
- [Scrape endpoint](https://docs.firecrawl.dev/api-reference/endpoint/scrape)
- [Map endpoint](https://docs.firecrawl.dev/api-reference/endpoint/map)
- [Crawl POST](https://docs.firecrawl.dev/api-reference/endpoint/crawl-post)
- [Crawl GET](https://docs.firecrawl.dev/api-reference/endpoint/crawl-get)
- [Crawl delete](https://docs.firecrawl.dev/api-reference/endpoint/crawl-delete)
- [Extract endpoint](https://docs.firecrawl.dev/api-reference/endpoint/extract)
- [Extract job status](https://docs.firecrawl.dev/api-reference/endpoint/extract-get)
- [Browser endpoint](https://docs.firecrawl.dev/api-reference/endpoint/browser)
- [Browser execute](https://docs.firecrawl.dev/api-reference/endpoint/browser-execute)
- [Agent endpoint](https://docs.firecrawl.dev/api-reference/endpoint/agent)
- [Agent status](https://docs.firecrawl.dev/api-reference/endpoint/agent-status)
- [Monitor endpoint](https://docs.firecrawl.dev/api-reference/endpoint/monitor)
- [Parse endpoint](https://docs.firecrawl.dev/api-reference/endpoint/parse)
- [Queue status](https://docs.firecrawl.dev/api-reference/endpoint/queue-status)
- [API errors](https://docs.firecrawl.dev/api-reference/errors)
- [Crawl feature](https://docs.firecrawl.dev/features/crawl)
- [Deep research](https://docs.firecrawl.dev/features/alpha/deep-research)
- [PII redaction](https://docs.firecrawl.dev/features/pii-redaction)
- [Proxy configuration](https://docs.firecrawl.dev/features/proxies)
- [MCP server](https://docs.firecrawl.dev/mcp-server)
- [OpenAI integration](https://docs.firecrawl.dev/developer-guides/llm-sdks-and-frameworks/openai)
- [Anthropic integration](https://docs.firecrawl.dev/developer-guides/llm-sdks-and-frameworks/anthropic)
- [LangChain integration](https://docs.firecrawl.dev/developer-guides/llm-sdks-and-frameworks/langchain)
- [AI research assistant cookbook](https://docs.firecrawl.dev/developer-guides/cookbooks/ai-research-assistant-cookbook)
- [Webhook security](https://docs.firecrawl.dev/webhooks/security)

### Parallel

- [Parallel documentation](https://docs.parallel.ai)
- [Developer quickstart](https://docs.parallel.ai/integrations/developer-quickstart)
- [Search quickstart](https://docs.parallel.ai/search/search-quickstart)
- [Search reference](https://docs.parallel.ai/api-reference/search/search)
- [Extract quickstart](https://docs.parallel.ai/extract/extract-quickstart)
- [Extract migration guide](https://docs.parallel.ai/extract/extract-migration-guide)
- [Extract reference](https://docs.parallel.ai/api-reference/extract/extract)
- [FindAll quickstart](https://docs.parallel.ai/findall-api/findall-quickstart)
- [FindAll lifecycle](https://docs.parallel.ai/findall-api/core-concepts/findall-lifecycle)
- [FindAll cancellation](https://docs.parallel.ai/findall-api/features/findall-cancel)
- [FindAll webhook](https://docs.parallel.ai/findall-api/features/findall-webhook)
- [Task API group](https://docs.parallel.ai/task-api/group-api)
- [Task best practices](https://docs.parallel.ai/task-api/best-practices)
- [Create task run](https://docs.parallel.ai/api-reference/tasks/create-task-run)
- [Stream task run events](https://docs.parallel.ai/api-reference/tasks/stream-task-run-events)
- [Retrieve task group run](https://docs.parallel.ai/api-reference/tasks/retrieve-task-group-run)
- [Task webhooks](https://docs.parallel.ai/task-api/webhooks)
- [Monitor migration guide](https://docs.parallel.ai/monitor-api/monitor-migration-guide)
- [Create monitor](https://docs.parallel.ai/api-reference/monitor/create-monitor)
- [Cancel monitor](https://docs.parallel.ai/api-reference/monitor/cancel-monitor)
- [Monitor webhooks](https://docs.parallel.ai/monitor-api/monitor-webhook)
- [Rate limits](https://docs.parallel.ai/getting-started/rate-limits)
- [API keys](https://docs.parallel.ai/service-api/keys/create-key)
- [MCP](https://docs.parallel.ai/mcp)
- [Access research basis](https://docs.parallel.ai/task-api/guides/access-research-basis)
- [OpenAPI schema](https://docs.parallel.ai/docs-latest-openapi.json)
- [Vercel integration](https://docs.parallel.ai/integrations/vercel)
- [OpenRouter integration](https://docs.parallel.ai/integrations/openrouter)
- [Webhook setup](https://docs.parallel.ai/resources/webhook-setup)

### Tavily

- [Tavily documentation](https://docs.tavily.com)
- [Quickstart](https://docs.tavily.com/documentation/quickstart)
- [Python SDK reference](https://docs.tavily.com/sdk/python/reference)
- [JavaScript SDK quickstart](https://docs.tavily.com/sdk/javascript/quick-start)
- [JavaScript SDK reference](https://docs.tavily.com/sdk/javascript/reference)
- [API introduction](https://docs.tavily.com/documentation/api-reference/introduction)
- [Search endpoint](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- [Extract endpoint](https://docs.tavily.com/documentation/api-reference/endpoint/extract)
- [Crawl endpoint](https://docs.tavily.com/documentation/api-reference/endpoint/crawl)
- [Map endpoint](https://docs.tavily.com/documentation/api-reference/endpoint/map)
- [Research endpoint](https://docs.tavily.com/documentation/api-reference/endpoint/research)
- [Research get](https://docs.tavily.com/documentation/api-reference/endpoint/research-get)
- [Research streaming](https://docs.tavily.com/documentation/api-reference/endpoint/research-streaming)
- [Usage endpoint](https://docs.tavily.com/documentation/api-reference/endpoint/usage)
- [Logs endpoint](https://docs.tavily.com/documentation/api-reference/endpoint/logs)
- [API credits](https://docs.tavily.com/documentation/api-credits)
- [Rate limits](https://docs.tavily.com/documentation/rate-limits)
- [API key management](https://docs.tavily.com/documentation/best-practices/api-key-management)
- [Search best practices](https://docs.tavily.com/documentation/best-practices/best-practices-search)
- [Extract best practices](https://docs.tavily.com/documentation/best-practices/best-practices-extract)
- [Crawl best practices](https://docs.tavily.com/documentation/best-practices/best-practices-crawl)
- [Research best practices](https://docs.tavily.com/documentation/best-practices/best-practices-research)
- [MCP](https://docs.tavily.com/documentation/mcp)
- [Agent skills](https://docs.tavily.com/documentation/agent-skills)
- [OpenAI integration](https://docs.tavily.com/documentation/integrations/openai)
- [Anthropic integration](https://docs.tavily.com/documentation/integrations/anthropic)
- [LangChain integration](https://docs.tavily.com/documentation/integrations/langchain)
- [FAQ](https://docs.tavily.com/faq/faq)
