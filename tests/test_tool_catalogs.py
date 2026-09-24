"""FILE: tests/test_tool_catalogs.py

PURPOSE: Verifies every public tool-catalog adapter against recorded payload shapes without network access: search, describe, install normalization, secrets, managed connections, direct execution, and the fan-out merge.
ROLE IN CODEBASE: Covers vidbyte/providers/tool_catalogs/ and vidbyte/lib/dataclasses/tool_catalogs.py for docs/design/jev-tool-alignment.md; scripts/test-jev-tool-alignment.py runs it.
ARCHITECTURE NOTE: A routing fake replaces HttpTransport, answering by URL with bodies shaped like each catalog's real responses (retrieved 2026-09-23), so the adapters' own parsing and request building stay under test.
COMMON MODIFICATION PATTERNS: When a catalog changes its payload, update the fixture here first, then the adapter, then vidbyte/providers/tool_catalogs/README.md.
KNOWN EDGE CASES: Fixtures are minimal but keep every field an adapter reads; unknown fields are ignored by design.
RELATED DOCS: docs/design/jev-tool-alignment.md and vidbyte/providers/tool_catalogs/README.md.
TESTS: python -m pytest tests/test_tool_catalogs.py.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from collections.abc import Mapping
from typing import Any

from vidbyte.lib.dataclasses.tool_catalogs import CatalogTool, ToolCatalogCredentials, ToolCatalogEntry, ToolInstall
from vidbyte.lib.enums.tool_catalogs import ToolCatalogName, ToolInstallKind, ToolSecretLocation
from vidbyte.lib.errors import ConfigurationError, ProviderConfigurationError, ProviderRequestError, ProviderResponseError
from vidbyte.lib.http.transport import HttpResponse
from vidbyte.providers.tool_catalogs import (
    ApisGuruCatalog,
    ArcadeCatalog,
    ComposioCatalog,
    DockerMcpCatalog,
    GitHubMcpRegistryCatalog,
    GlamaCatalog,
    McpRegistryCatalog,
    PipedreamCatalog,
    SmitheryCatalog,
    ToolCatalogProvider,
    ToolCatalogs,
    ToolSdkCatalog,
)


class RoutingHttp:
    """Fake HttpTransport: answers each request with the first route whose key is a substring of the URL."""

    def __init__(self, routes: Mapping[str, object], *, status: int = 200) -> None:
        self.routes = dict(routes)
        self.status = status
        self.requests: list[dict[str, Any]] = []

    async def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, **kwargs: Any) -> HttpResponse:
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "json_body": json_body, **kwargs})
        for key, body in self.routes.items():
            if key in url:
                text = body if isinstance(body, str) else json.dumps(body)
                return HttpResponse(status_code=self.status, body=text, headers={})
        return HttpResponse(status_code=404, body="{}", headers={})


def _registry_server(name: str, **fields: object) -> dict[str, object]:
    return {"server": {"name": name, "description": f"{name} server", "version": "1.2.0", **fields}, "_meta": {"io.modelcontextprotocol.registry/official": {"status": "active"}}}


REGISTRY_PAGE = {
    "servers": [
        _registry_server(
            "app.linear/linear",
            title="Linear",
            remotes=[{"type": "streamable-http", "url": "https://mcp.linear.app/mcp", "headers": [{"name": "Authorization", "value": "Bearer {LINEAR_TOKEN}", "isRequired": True, "isSecret": True}]}],
            repository={"url": "https://github.com/linear/mcp"},
        ),
        _registry_server(
            "io.github.acme/linear-tools",
            remotes=[{"type": "sse", "url": "https://legacy.example/sse"}, {"type": "streamable-http", "url": "https://{tenant}.example/mcp"}],
            packages=[
                {"registryType": "npm", "identifier": "@acme/linear-mcp", "version": "2.0.1", "transport": {"type": "stdio"}, "environmentVariables": [{"name": "LINEAR_PAT", "isRequired": True, "isSecret": True}]},
                {"registryType": "pypi", "identifier": "linear-mcp", "version": "0.3.2", "transport": {"type": "stdio"}},
                {"registryType": "oci", "identifier": "ghcr.io/acme/linear-mcp", "version": "2.0.1", "transport": {"type": "stdio"}, "environmentVariables": [{"name": "LINEAR_PAT", "isRequired": True}]},
                {"registryType": "npm", "identifier": "@acme/needs-arg", "version": "1.0.0", "packageArguments": [{"type": "positional", "isRequired": True}]},
            ],
        ),
        {"server": {"name": "io.github.old/deleted"}, "_meta": {"io.modelcontextprotocol.registry/official": {"status": "deleted"}}},
    ],
    "metadata": {"count": 3},
}


class McpRegistryTests(unittest.IsolatedAsyncioTestCase):
    """The official and GitHub registries share the server.json translation."""

    async def test_server_json_becomes_remote_and_package_installs(self) -> None:
        # [Hidden Failure] every install kind carries its secrets; unconnectable remotes and packages are skipped.
        http = RoutingHttp({"/v0.1/servers": REGISTRY_PAGE})
        entries = await McpRegistryCatalog(transport=http).search("linear", limit=5)  # type: ignore[arg-type]
        by_id = {entry.entry_id: entry for entry in entries}
        self.assertNotIn("io.github.old/deleted", by_id)
        linear = by_id["app.linear/linear"]
        remote = linear.installs[0]
        self.assertEqual((remote.kind, remote.url), (ToolInstallKind.REMOTE_HTTP, "https://mcp.linear.app/mcp"))
        secret = remote.secrets[0]
        self.assertEqual((secret.name, secret.location, secret.target, secret.render("t0k")), ("LINEAR_TOKEN", ToolSecretLocation.HEADER, "Authorization", "Bearer t0k"))
        tools = by_id["io.github.acme/linear-tools"]
        self.assertEqual([install.kind for install in tools.installs], [ToolInstallKind.PACKAGE, ToolInstallKind.PACKAGE, ToolInstallKind.CONTAINER])
        self.assertEqual(tools.installs[0].command, ("npx", "-y", "@acme/linear-mcp@2.0.1"))
        self.assertEqual(tools.installs[1].command, ("uvx", "linear-mcp==0.3.2"))
        self.assertEqual(tools.installs[2].command, ("docker", "run", "-i", "--rm", "-e", "LINEAR_PAT", "ghcr.io/acme/linear-mcp:2.0.1"))
        self.assertTrue(all(install.pinned for install in tools.installs))
        self.assertIn("version=latest", http.requests[0]["url"])
        self.assertEqual(http.requests[0]["max_response_bytes"], 2_000_000)

    async def test_multi_word_query_is_also_searched_word_by_word(self) -> None:
        # [Edge Case] the registry matches names only, so "linear issues" falls back to per-word searches.
        http = RoutingHttp({"search=linear+issues": {"servers": []}, "search=": REGISTRY_PAGE})
        entries = await McpRegistryCatalog(transport=http).search("linear issues", limit=5)  # type: ignore[arg-type]
        self.assertGreaterEqual(len(http.requests), 2)
        self.assertEqual(entries[0].entry_id, "app.linear/linear")

    async def test_github_registry_pages_once_and_caches(self) -> None:
        # [Edge Case] GitHub's registry ignores search, so it is paged into a cached index.
        page_one = {"servers": REGISTRY_PAGE["servers"][:1], "metadata": {"nextCursor": "abc"}}
        page_two = {"servers": REGISTRY_PAGE["servers"][1:2], "metadata": {}}
        http = RoutingHttp({"cursor=abc": page_two, "api.mcp.github.com": page_one})
        catalog = GitHubMcpRegistryCatalog(transport=http)  # type: ignore[arg-type]
        first = await catalog.search("linear", limit=5)
        await catalog.search("linear", limit=5)
        self.assertEqual(len(http.requests), 2)
        self.assertEqual({entry.entry_id for entry in first}, {"app.linear/linear", "io.github.acme/linear-tools"})


class SmitheryTests(unittest.IsolatedAsyncioTestCase):
    async def test_describe_reads_http_connections_and_config_locations(self) -> None:
        # [Security] config goes where x-from says, and the Smithery key is sent only to the registry.
        detail = {
            "displayName": "Browserbase",
            "connections": [
                {"type": "stdio"},
                {"type": "http", "deploymentUrl": "https://browserbase.run.tools", "configSchema": {"required": ["apiKey"], "properties": {"apiKey": {"x-from": {"query": "browserbaseApiKey"}}, "region": {"x-from": {"header": "x-region"}}}}},
            ],
            "tools": [{"name": "browse", "description": "Open a page.", "inputSchema": {"type": "object"}, "annotations": {"readOnlyHint": True}}],
        }
        http = RoutingHttp({"/servers/browserbase": detail, "/servers?": {"servers": [{"qualifiedName": "browserbase", "displayName": "Browserbase", "verified": True}, {"qualifiedName": ""}]}})
        catalog = SmitheryCatalog(credentials=ToolCatalogCredentials(api_key="smithery-key"), transport=http)  # type: ignore[arg-type]
        entries = await catalog.search("browser", limit=5)
        self.assertEqual([entry.entry_id for entry in entries], ["browserbase"])
        described = await catalog.describe(entries[0])
        install = described.installs[0]
        self.assertEqual(install.url, "https://browserbase.run.tools")
        secrets = {secret.name: secret for secret in install.secrets}
        self.assertEqual((secrets["apiKey"].location, secrets["apiKey"].target, secrets["apiKey"].required), (ToolSecretLocation.QUERY, "browserbaseApiKey", True))
        self.assertEqual((secrets["region"].location, secrets["region"].required), (ToolSecretLocation.HEADER, False))
        self.assertTrue(described.tools[0].read_only)
        self.assertEqual(install.static_headers, {})
        self.assertTrue(all(request["headers"].get("Authorization") == "Bearer smithery-key" for request in http.requests))


class GlamaTests(unittest.IsolatedAsyncioTestCase):
    async def test_connectors_become_remote_installs_and_oauth_is_skipped(self) -> None:
        connectors = {
            "connectors": [
                {"namespace": "acme", "slug": "docs", "name": "Acme Docs", "healthy": True, "connection": {"authType": "none", "transport": "streamable_http", "url": "https://docs.acme.dev/mcp"}},
                {"namespace": "acme", "slug": "crm", "name": "Acme CRM", "healthy": True, "connection": {"authType": "api_key", "transport": "streamable_http", "url": "https://crm.acme.dev/mcp"}},
                {"namespace": "acme", "slug": "mail", "name": "Acme Mail", "healthy": True, "connection": {"authType": "oauth2", "transport": "streamable_http", "url": "https://mail.acme.dev/mcp"}},
                {"namespace": "acme", "slug": "old", "name": "Old", "deprecatedAt": "2026-01-01", "connection": {"authType": "none", "transport": "streamable_http", "url": "https://old.acme.dev"}},
            ],
            "pageInfo": {"hasNextPage": False},
        }
        http = RoutingHttp({"/v1/connectors?": connectors})
        entries = await GlamaCatalog(credentials=ToolCatalogCredentials(api_key="g"), transport=http).search("acme", limit=5)  # type: ignore[arg-type]
        by_id = {entry.entry_id: entry for entry in entries}
        self.assertEqual(set(by_id), {"acme/docs", "acme/crm", "acme/mail"})
        self.assertEqual(by_id["acme/docs"].installs[0].secrets, ())
        self.assertEqual(by_id["acme/crm"].installs[0].secrets[0].render("k"), "Bearer k")
        self.assertEqual(by_id["acme/mail"].installs, ())
        self.assertEqual(http.requests[0]["headers"]["Authorization"], "Bearer g")

    async def test_reads_require_a_key(self) -> None:
        with self.assertRaises(ProviderConfigurationError):
            await GlamaCatalog(transport=RoutingHttp({})).search("x", limit=1)  # type: ignore[arg-type]


DOCKER_YAML = """
version: 3
registry:
  brave:
    title: Brave Search
    type: server
    description: Search the web with Brave.
    image: mcp/brave-search@sha256:abc
    toolsUrl: http://desktop.docker.com/mcp/catalog/v3/tools/brave.json
    tools:
      - name: brave_web_search
    secrets:
      - name: brave.api_key
        env: BRAVE_API_KEY
    env:
      - name: BRAVE_MCP_TRANSPORT
        value: stdio
    metadata:
      owner: brave
  context7:
    title: Context7
    type: remote
    description: Library docs.
    remote:
      transport_type: streamable-http
      url: https://mcp.context7.com/mcp
      headers:
        CONTEXT7_API_KEY: ${CONTEXT7_API_KEY}
    tools: []
  couchbase:
    title: Couchbase
    type: server
    description: Couchbase queries.
    image: mcp/couchbase@sha256:def
    config:
      - name: couchbase
    tools: []
"""


class DockerTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_yaml_becomes_container_and_remote_installs(self) -> None:
        # [Hidden Failure] images are pinned by digest, and Toolkit-templated servers are not attachable.
        tools_json = [{"name": "brave_web_search", "description": "Search the web.", "arguments": [{"name": "query", "type": "string", "desc": "Query."}], "annotations": {"readOnlyHint": True}}]
        http = RoutingHttp({"https://desktop.docker.com/mcp/catalog/v3/tools/brave.json": tools_json, "catalog.yaml": DOCKER_YAML})
        catalog = DockerMcpCatalog(transport=http)  # type: ignore[arg-type]
        entries = {entry.entry_id: entry for entry in await catalog.entries()}
        brave = entries["brave"].installs[0]
        self.assertEqual(brave.command, ("docker", "run", "-i", "--rm", "-e", "BRAVE_MCP_TRANSPORT=stdio", "-e", "BRAVE_API_KEY", "mcp/brave-search@sha256:abc"))
        self.assertTrue(brave.pinned)
        remote = entries["context7"].installs[0]
        self.assertEqual((remote.url, remote.secrets[0].name, remote.secrets[0].target), ("https://mcp.context7.com/mcp", "CONTEXT7_API_KEY", "CONTEXT7_API_KEY"))
        self.assertEqual(entries["couchbase"].installs, ())
        described = await catalog.describe(entries["brave"])
        self.assertEqual(described.tools[0].input_schema["properties"], {"query": {"type": "string", "description": "Query."}})
        self.assertTrue(described.tools[0].read_only)
        self.assertTrue(http.requests[-1]["url"].startswith("https://"))


class ToolSdkTests(unittest.IsolatedAsyncioTestCase):
    async def test_packages_are_unpinned_and_remotes_with_env_are_skipped(self) -> None:
        index = {"linear-mcp": {"category": "project-management", "path": "pm/linear.json", "validated": True, "tools": {"create_issue": {"name": "create_issue", "description": "Create a Linear issue."}}}}
        package = {"packageName": "linear-mcp", "name": "Linear MCP", "description": "Linear tools.", "runtime": "node", "env": {"LINEAR_API_KEY": {"required": True}}, "remotes": [{"type": "streamable-http", "url": "https://x.example/mcp"}]}
        http = RoutingHttp({"packages/pm/linear.json": package, "packages-list.json": index})
        catalog = ToolSdkCatalog(transport=http)  # type: ignore[arg-type]
        entry = (await catalog.search("linear issue", limit=3))[0]
        self.assertTrue(entry.verified)
        described = await catalog.describe(entry)
        self.assertEqual(len(described.installs), 1)
        install = described.installs[0]
        self.assertEqual((install.kind, install.command, install.pinned), (ToolInstallKind.PACKAGE, ("npx", "-y", "linear-mcp"), False))
        self.assertEqual(install.required_secrets[0].name, "LINEAR_API_KEY")


class ComposioTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_groups_by_toolkit_and_connect_exposes_only_judged_tools(self) -> None:
        # [Security] the session allowlist, preload list, and disabled search expose only the given tools.
        tools = {"items": [
            {"slug": "GITHUB_CREATE_ISSUE", "description": "Create an issue.", "toolkit": {"slug": "github", "name": "GitHub"}, "input_parameters": {"type": "object"}, "tags": ["destructiveHint"]},
            {"slug": "GITHUB_GET_ISSUE", "description": "Get an issue.", "toolkit": {"slug": "github", "name": "GitHub"}, "tags": ["readOnlyHint"]},
            {"slug": "OLD", "toolkit": {"slug": "github"}, "is_deprecated": True},
        ]}
        http = RoutingHttp({"/api/v3.1/tools": tools, "/tool_router/session": {"session_id": "s1", "mcp": {"type": "http", "url": "https://backend.composio.dev/tool_router/s1/mcp"}}})
        catalog = ComposioCatalog(credentials=ToolCatalogCredentials(api_key="ck"), transport=http)  # type: ignore[arg-type]
        (entry,) = await catalog.search("github issue", limit=3)
        self.assertEqual([tool.name for tool in entry.tools], ["GITHUB_CREATE_ISSUE", "GITHUB_GET_ISSUE"])
        self.assertTrue(entry.tools[0].destructive)
        self.assertTrue(entry.tools[1].read_only)
        connection = await catalog.connect(entry, entry.installs[0], tool_names=["GITHUB_GET_ISSUE"], user_id="user-1")
        body = http.requests[-1]["json_body"]
        self.assertEqual(body["tools"], {"github": {"enable": ["GITHUB_GET_ISSUE"]}})
        self.assertEqual(body["search"], {"enable": False})
        self.assertEqual(http.requests[-1]["retry_count"], 0)
        self.assertEqual(connection.url, "https://backend.composio.dev/tool_router/s1/mcp")
        self.assertEqual(dict(connection.headers), {"x-api-key": "ck"})
        with self.assertRaises(ProviderConfigurationError):
            await catalog.connect(entry, entry.installs[0], tool_names=["GITHUB_GET_ISSUE"], user_id=None)


class PipedreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_token_is_exchanged_once_and_connect_scopes_the_endpoint(self) -> None:
        http = RoutingHttp({"/v1/oauth/token": {"access_token": "pd-token", "expires_in": 3600}, "/v1/connect/apps": {"data": [{"name_slug": "notion", "name": "Notion", "description": "Notes."}]}})
        credentials = ToolCatalogCredentials(client_id="cid", client_secret="cs", project_id="proj_1", environment="production")
        catalog = PipedreamCatalog(credentials=credentials, transport=http)  # type: ignore[arg-type]
        (entry,) = await catalog.search("notion", limit=3)
        await catalog.search("notion", limit=3)
        self.assertEqual(sum(1 for request in http.requests if "oauth/token" in request["url"]), 1)
        connection = await catalog.connect(entry, entry.installs[0], tool_names=(), user_id="user-1")
        self.assertEqual(connection.url, "https://remote.mcp.pipedream.net/v3")
        self.assertEqual(connection.headers["x-pd-app-slug"], "notion")
        self.assertEqual(connection.headers["x-pd-external-user-id"], "user-1")
        self.assertEqual(connection.headers["Authorization"], "Bearer pd-token")


class ArcadeTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_builds_schemas_and_execute_maps_errors(self) -> None:
        tool = {"fully_qualified_name": "Github.CreateIssue@1.0.0", "description": "Create an issue.", "toolkit": {"name": "Github"}, "input": {"parameters": [{"name": "title", "required": True, "value_schema": {"val_type": "string"}}]}, "metadata": {"behavior": {"read_only": False, "destructive": False}}}
        http = RoutingHttp({"/v1/tools/execute": {"success": True, "output": {"authorization": {"url": "https://auth.arcade.dev/x"}}}, "/v1/tools?": {"items": [tool]}})
        catalog = ArcadeCatalog(credentials=ToolCatalogCredentials(api_key="ak"), transport=http)  # type: ignore[arg-type]
        (entry,) = await catalog.search("github issue", limit=3)
        self.assertEqual(entry.tools[0].input_schema["required"], ["title"])
        self.assertFalse(entry.tools[0].read_only)
        output, is_error = await catalog.execute(entry, entry.tools[0], {"title": "x"}, user_id="u1")
        self.assertTrue(is_error)
        self.assertIn("https://auth.arcade.dev/x", output)
        self.assertEqual(http.requests[-1]["json_body"], {"tool_name": "Github.CreateIssue@1.0.0", "input": {"title": "x"}, "user_id": "u1"})


class ApisGuruTests(unittest.IsolatedAsyncioTestCase):
    async def test_entries_carry_an_openapi_install(self) -> None:
        listing = {"ably.net:control": {"preferred": "1.0", "versions": {"1.0": {"info": {"title": "Ably Control API", "description": "Manage apps."}, "swaggerUrl": "https://api.apis.guru/v2/specs/ably.json"}}}}
        entries = await ApisGuruCatalog(transport=RoutingHttp({"list.json": listing})).search("ably control", limit=3)  # type: ignore[arg-type]
        self.assertEqual(entries[0].installs[0].kind, ToolInstallKind.OPENAPI)


class FanOutTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_all_interleaves_dedupes_and_isolates_failures(self) -> None:
        # [Hidden Failure] a broken or slow catalog is its own error; the others still answer, without duplicates.
        remote = ToolInstall(kind=ToolInstallKind.REMOTE_HTTP, url="https://mcp.linear.app/mcp")

        class Fixed(ToolCatalogProvider):
            def __init__(self, name: ToolCatalogName, entries: tuple[ToolCatalogEntry, ...], *, delay: float = 0.0, fail: bool = False) -> None:
                super().__init__()
                self.name = name  # type: ignore[misc]
                self.fixed, self.delay, self.fail = entries, delay, fail

            async def search(self, query: str, *, limit: int) -> tuple[ToolCatalogEntry, ...]:
                await asyncio.sleep(self.delay)
                if self.fail:
                    raise ProviderResponseError("bad body", provider=self.name.value)
                return self.fixed

        def entry(catalog: ToolCatalogName, entry_id: str, install: ToolInstall | None = None) -> ToolCatalogEntry:
            return ToolCatalogEntry(catalog=catalog, entry_id=entry_id, name=entry_id, description="", installs=(install,) if install else ())

        official = Fixed(ToolCatalogName.MCP_REGISTRY, (entry(ToolCatalogName.MCP_REGISTRY, "linear", remote), entry(ToolCatalogName.MCP_REGISTRY, "jira")))
        docker = Fixed(ToolCatalogName.DOCKER_MCP_CATALOG, (entry(ToolCatalogName.DOCKER_MCP_CATALOG, "linear", remote), entry(ToolCatalogName.DOCKER_MCP_CATALOG, "notion")))
        broken = Fixed(ToolCatalogName.GLAMA, (), fail=True)
        slow = Fixed(ToolCatalogName.SMITHERY, (entry(ToolCatalogName.SMITHERY, "late"),), delay=1.0)
        result = await ToolCatalogs.search_all((official, docker, broken, slow), "linear", limit_per_catalog=5, merged_limit=10, timeout_seconds=0.2)
        self.assertEqual([item.key for item in result.entries], ["mcp_registry:linear", "mcp_registry:jira", "docker_mcp_catalog:notion"])
        self.assertEqual(result.errors[ToolCatalogName.GLAMA], "bad body")
        self.assertIn("did not answer", result.errors[ToolCatalogName.SMITHERY])

    async def test_http_errors_are_typed(self) -> None:
        with self.assertRaises(ProviderRequestError):
            await McpRegistryCatalog(transport=RoutingHttp({"/v0.1/servers": {}}, status=503)).search("x", limit=1)  # type: ignore[arg-type]
        with self.assertRaises(ProviderResponseError):
            await McpRegistryCatalog(transport=RoutingHttp({"/v0.1/servers": "<html>"})).search("x", limit=1)  # type: ignore[arg-type]

    def test_build_refuses_unknown_catalogs(self) -> None:
        with self.assertRaises(ConfigurationError):
            ToolCatalogs.build("nope")
        self.assertIsInstance(ToolCatalogs.build("smithery"), SmitheryCatalog)
        self.assertEqual(CatalogTool(name="t", description="").input_schema, {})


if __name__ == "__main__":
    unittest.main()
