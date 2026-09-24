# Tool catalogs

Adapters for public catalogs of existing tools: MCP registries, curated catalogs, and managed tool platforms. Each adapter turns one catalog's API into `ToolCatalogEntry` records (`vidbyte/lib/dataclasses/tool_catalogs.py`), so code above this layer never sees a catalog's payload.

## Role in the SDK

`JevAgentAlignment` uses these adapters for tool alignment (`JevAgentSettings(tool_align=JevToolAlignmentSettings(...))`). It searches every enabled catalog through `ToolCatalogs.search_all()`, reads an entry's tools with `describe()`, resolves managed installs with `connect()`, and runs direct-execute platform tools with `execute()`. `SearchMcpServersTool` uses `SmitheryCatalog` directly.

```python
from vidbyte.providers.tool_catalogs import ToolCatalogs

catalogs = [ToolCatalogs.build(name) for name in ("mcp_registry", "docker_mcp_catalog")]
found = await ToolCatalogs.search_all(catalogs, "linear", limit_per_catalog=8, merged_limit=12, timeout_seconds=10)
```

## Design rules

- Every request goes through `vidbyte.lib.http.HttpTransport`, with a timeout and a byte ceiling. Whole-file indexes use the larger index ceiling and are cached on the adapter for an hour.
- Only GETs are retried. A retried POST could open a second Composio session or run an Arcade tool twice.
- A failing or slow catalog becomes an entry in `ToolCatalogSearch.errors`. It never stops the other catalogs from answering.
- Adapters never derive a command from a catalog name. A package or container install uses the identifier and version the catalog publishes, and an install without a version is marked unpinned.
- Owner credentials go only to the catalog they belong to. The Smithery key, for example, is sent only to `registry.smithery.ai` and never to a server's deployment URL.

## File Index

- `__init__.py`: the `ToolCatalogs` factory, the `search_all()` fan-out, and the interleave-and-dedupe merge.
- `base.py`: the `ToolCatalogProvider` contract, the bounded HTTP helpers, `IndexedToolCatalogProvider`, and local ranking.
- `mcp_registry.py`: the official MCP Registry and GitHub's MCP Registry (`server.json`).
- `smithery.py`: the Smithery registry.
- `glama.py`: Glama connectors.
- `docker.py`: Docker's MCP Catalog (`catalog.yaml`).
- `toolsdk.py`: ToolSDK's package index.
- `composio.py`: Composio tools and tool-router sessions.
- `pipedream.py`: Pipedream Connect apps and remote MCP.
- `arcade.py`: Arcade tools and direct execution.
- `apis_guru.py`: the APIs.guru OpenAPI directory (discovery only).

---

# External Contract

> **retrieved:** 2026-09-23
> **verified_by:** every module in this folder, and `tests/test_tool_catalogs.py`
> **scope:** endpoints, authentication, and the response fields each adapter reads. Rate limits and fields no adapter reads are out of scope.
>
> This section is written in our own words. `vidbyte-sdk` is MIT-licensed, and the catalogs' documentation is not.

| Catalog | Search | Detail / connect | Auth | Install produced |
| --- | --- | --- | --- | --- |
| [Official MCP Registry](https://registry.modelcontextprotocol.io/docs) | `GET /v0.1/servers?search=&limit=&version=latest` (matches server names only) | none; tools come from the live server | none | `remotes[]` of type `streamable-http` (header templates such as `Bearer {TOKEN}` become secrets), plus `packages[]` of type npm (`npx -y id@version`), pypi (`uvx id==version`), and oci (`docker run -i --rm -e VAR image:tag`) with `environmentVariables` |
| [GitHub MCP Registry](https://github.com/mcp) | same API at `api.mcp.github.com`; `search` is ignored, so the adapter pages `cursor` into a cached index | same | none | same as above |
| [Smithery](https://smithery.ai/docs/concepts/registry_search_servers) | `GET registry.smithery.ai/servers?q=&pageSize=` | `GET /servers/{qualifiedName}`: `connections[]` of type `http` with `deploymentUrl` and a `configSchema` whose properties carry `x-from: {query|header}`; `tools[]` | optional `Authorization: Bearer` for registry reads | remote `deploymentUrl` |
| [Glama](https://glama.ai/mcp/reference) ([OpenAPI](https://glama.ai/api/mcp/openapi.json)) | `GET glama.ai/api/mcp/v1/connectors?query=&first=&sort=search-relevance:desc` | `GET /v1/connectors/{namespace}/{slug}`: `tools[]` with `annotations` | `Authorization: Bearer <key>` (required) | remote `connection.url` when `authType` is `none` or `api_key`; `oauth2` and `basic` are not attachable |
| [Docker MCP Catalog](https://docs.docker.com/ai/mcp-catalog-and-toolkit/catalog/) | `desktop.docker.com/mcp/catalog/v3/catalog.yaml`, ranked locally | `toolsUrl` JSON: `name`, `description`, `arguments`, `annotations` | none | `server` entries become `docker run -i --rm` with the image pinned by digest; `remote` entries become remote installs whose `${ENV}` headers are secrets. Entries needing Toolkit `config`, `volumes`, `command`, or templated env are not attachable |
| [ToolSDK](https://github.com/toolsdk-ai/toolsdk-mcp-registry) | `toolsdk-ai.github.io/toolsdk-mcp-registry/indexes/packages-list.json`, ranked locally | `raw.githubusercontent.com/.../packages/{path}`: `runtime`, `env`, `remotes` | none | unpinned `npx`/`uvx` packages (rejected unless the owner allows unpinned packages); remotes only when no env is required |
| [Composio](https://docs.composio.dev/reference/api-reference/tools/getTools) | `GET backend.composio.dev/api/v3.1/tools?query=&limit=`, grouped by toolkit | `POST /api/v3.1/tool_router/session` with `user_id`, `toolkits.enable`, `tools.{toolkit}.enable`, `preload.tools`, `search.enable=false`, and `manage_connections.enable=false` returns `mcp.url` | `x-api-key` | managed: the session's MCP URL with `x-api-key` |
| [Pipedream Connect](https://pipedream.com/docs/connect/mcp/developers) | `GET api.pipedream.com/v1/connect/apps?q=&has_actions=true` | `https://remote.mcp.pipedream.net/v3` with `x-pd-project-id`, `x-pd-environment`, `x-pd-external-user-id`, and `x-pd-app-slug` | `POST /v1/oauth/token` client-credentials grant, then `Authorization: Bearer` | managed: the remote MCP server scoped by those headers |
| [Arcade](https://docs.arcade.dev/en/references/api) ([OpenAPI](https://api.arcade.dev/v1/swagger)) | `GET api.arcade.dev/v1/tools?search=&limit=` (literal substring; every word must match) | `POST /v1/tools/execute` with `tool_name`, `input`, and `user_id` | `Authorization: Bearer <key>` | managed, direct execute (`executes_directly=True`) |
| [APIs.guru](https://apis.guru/api-doc/) | `api.apis.guru/v2/list.json` (~9 MB), ranked locally | none | none | OpenAPI (`swaggerUrl`); reported to the owner, never attached |
