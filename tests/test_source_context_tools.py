"""FILE: tests/test_source_context_tools.py

PURPOSE: Verifies CLI-first GitHub source loading, REST fallback, budgets, and tool scope.
ROLE IN CODEBASE: Exercises every public source path offline through fake runners and transports.
ARCHITECTURE NOTE: Tests assert command arguments and environment separation without invoking a real GitHub login.
COMMON MODIFICATION PATTERNS: Add one test for each provider boundary or safety invariant, keeping fakes deterministic.
KNOWN EDGE CASES: Unicode byte clipping, zero budgets, missing CLI, malformed output, traversal, and auth failures.
RELATED DOCS: docs/design/source-context-tools.md
TESTS: Run with pytest or scripts/test-source-context-tools.py.
"""

from __future__ import annotations

import base64
import json
import unittest
from collections.abc import Callable, Mapping
from typing import Any
from unittest import mock

from vidbyte import Agent, SourceContext, SourceTool
from vidbyte.integrations.github import GitHubClient
from vidbyte.integrations.source_context import context as source_context_module
from vidbyte.integrations.source_tool import builder as source_tool_module
from vidbyte.lib import cli as cli_module
from vidbyte.lib.cli import (
    CliCommandError,
    CliRequest,
    CliResult,
    CliRunner,
    CliUnavailableError,
)
from vidbyte.lib.dataclasses.integrations import GitHubClientConfig, SourceConfig
from vidbyte.lib.enums.integrations import SourceKind, SourceProvider
from vidbyte.lib.errors import ConfigurationError, SourceFetchError
from vidbyte.lib.http.transport import HttpResponse, HttpTransport
from vidbyte.lib.integrations_budget import ContextAdmission
from vidbyte.lib.text import TextClipper
from vidbyte.tools.types import ToolCall

TOKEN = "ghp_test_token"
PR_SOURCE = {"provider": "github", "api_key": TOKEN, "resource": "https://github.com/acme/api/pull/41"}
REPO_SOURCE = {"provider": "github", "api_key": TOKEN, "resource": "https://github.com/acme/api"}
PULL_PAYLOAD = {"title": "Fix auth", "body": "Description text here.", "head": {"sha": "abc123"}, "base": {"sha": "def456"}}


class FakeGitHubTransport(HttpTransport):
    """Returns canned responses keyed by URL substring and records every request."""

    def __init__(self, routes: list[tuple[str, int, str]]) -> None:
        """Store ordered route responses and initialize request recording."""
        self._routes = routes
        self.requests: list[dict[str, Any]] = []

    async def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 60.0, retry_count: int = 0, backoff_seconds: float = 0.5, backoff_multiplier: float = 2.0, retry_status_codes: tuple[int, ...] = (408, 409, 425, 429, 500, 502, 503, 504), max_response_bytes: int | None = None, idempotency_key: str | None = None, follow_redirects: bool = False) -> HttpResponse:
        """Record one request and return the first matching canned response."""
        self.requests.append({"method": method, "url": url, "headers": dict(headers)})
        for needle, status, body in self._routes:
            if needle in url:
                return HttpResponse(status_code=status, body=body, headers={})
        return HttpResponse(status_code=404, body="not found", headers={})


class UnavailableCliRunner(CliRunner):
    """Forces the provider's documented REST fallback path."""

    async def run(self, request: CliRequest) -> CliResult:
        """Report a missing CLI without touching a subprocess."""
        raise CliUnavailableError("missing")


class FakeCliRunner(CliRunner):
    """Records fixed command plans and returns handler-provided native output."""

    def __init__(self, handler: Callable[[CliRequest], CliResult]) -> None:
        """Store an offline command response handler."""
        super().__init__()
        self.handler = handler
        self.requests: list[CliRequest] = []

    async def run(self, request: CliRequest) -> CliResult:
        """Record a request before returning its deterministic response."""
        self.requests.append(request)
        return self.handler(request)


def _pr_routes(*, empty: bool = False, review_status: int = 200) -> list[tuple[str, int, str]]:
    """Build standard REST pull-request routes with optional empty sections."""
    reviews = "[]" if empty else '[{"user": {"login": "r"}, "state": "APPROVED", "body": "LGTM"}]'
    comments = "[]" if empty else '[{"user": {"login": "c"}, "body": "Nice work"}]'
    pull = dict(PULL_PAYLOAD)
    pull["body"] = "" if empty else "Description text here."
    return [("pulls/41/reviews", review_status, reviews if review_status == 200 else "rate limit exceeded"), ("issues/41/comments", 200, comments), ("pulls/41", 200, json.dumps(pull)), ("api.github.com", 200, "diff --git a/x b/x\n+line\n")]


def _client(routes: list[tuple[str, int, str]], *, runner: CliRunner | None = None) -> tuple[GitHubClient, FakeGitHubTransport]:
    """Build a GitHub client with strict config and an offline transport."""
    transport = FakeGitHubTransport(routes)
    config = GitHubClientConfig(api_key=TOKEN, transport=transport, runner=runner or UnavailableCliRunner())
    return GitHubClient(config), transport


def _context_with_client(client: GitHubClient, **kwargs: Any) -> tuple[SourceContext, mock._patch]:
    """Patch the provider factory for one SourceContext test."""
    context = SourceContext(dict(PR_SOURCE), **kwargs)
    patcher = mock.patch.object(source_context_module.SourceProviderFactory, "create", return_value=client)
    patcher.start()
    return context, patcher


class CliRunnerTests(unittest.IsolatedAsyncioTestCase):
    """Verifies secret separation and the central subprocess boundary."""

    async def test_secret_is_environment_only(self) -> None:
        """The token reaches GH_TOKEN and never appears in command arguments."""

        class Stream:
            """Minimal async stream for the mocked child process."""

            async def read(self, size: int) -> bytes:
                """Return an empty stream while preserving the async contract."""
                return b""

        class Process:
            """Minimal successful child process for runner assertions."""

            stdout = Stream()
            stderr = Stream()
            returncode = 0

            async def wait(self) -> int:
                """Return the configured successful exit code."""
                return self.returncode

            def kill(self) -> None:
                """Satisfy the runner's cancellation contract."""
                self.returncode = -9

        process = Process()
        with mock.patch.object(cli_module.shutil, "which", return_value="gh"), mock.patch.object(cli_module.asyncio, "create_subprocess_exec", new=mock.AsyncMock(return_value=process)) as start:
            result = await CliRunner().run(CliRequest(executable="gh", args=("api", "search/code"), api_key=TOKEN, timeout_seconds=1.0))
        self.assertEqual(result.returncode, 0)
        self.assertNotIn(TOKEN, start.call_args.args)
        self.assertEqual(start.call_args.kwargs["env"]["GH_TOKEN"], TOKEN)
        self.assertEqual(start.call_args.kwargs["stdin"], cli_module.asyncio.subprocess.DEVNULL)


class SourceContextTests(unittest.IsolatedAsyncioTestCase):
    """Verifies CLI-first pull loading, REST fallback, budgets, and safe errors."""

    async def test_cli_load_preserves_four_sections(self) -> None:
        """Native pull metadata and diff produce four explicit CLI sections."""
        def handler(request: CliRequest) -> CliResult:
            if request.args[:2] == ("pr", "view"):
                return CliResult(json.dumps({**PULL_PAYLOAD, "headRefOid": "cli123", "reviews": [{"author": {"login": "r"}, "state": "APPROVED", "body": "LGTM"}], "comments": [{"author": {"login": "c"}, "body": "Nice"}]}), "", 0)
            return CliResult("diff --git a/x b/x\n+line\n", "", 0)

        runner = FakeCliRunner(handler)
        client, _ = _client([], runner=runner)
        context, patcher = _context_with_client(client)
        self.addCleanup(patcher.stop)
        items = await context.load()
        self.assertEqual(len(items), 4)
        self.assertTrue(all(item.metadata["transport"] == "cli" for item in items))
        self.assertTrue(all(TOKEN not in arg for request in runner.requests for arg in request.args))
        self.assertEqual(runner.requests[0].args[:5], ("pr", "view", "41", "--repo", "acme/api"))

    async def test_missing_cli_falls_back_to_rest(self) -> None:
        """A missing executable selects REST and records no native request."""
        client, transport = _client(_pr_routes())
        context, patcher = _context_with_client(client)
        self.addCleanup(patcher.stop)
        items = await context.load()
        self.assertEqual(len(items), 4)
        self.assertTrue(all(item.metadata["transport"] == "rest" for item in items))
        self.assertGreaterEqual(len(transport.requests), 4)

    async def test_empty_pr_sections_admit_cleanly(self) -> None:
        """Empty sections return four items with no truncation flags."""
        client, _ = _client(_pr_routes(empty=True))
        context, patcher = _context_with_client(client)
        self.addCleanup(patcher.stop)
        items = await context.load()
        self.assertEqual(len(items), 4)
        self.assertTrue(all(item.metadata.get("truncated") is False for item in items))

    async def test_zero_max_tokens_admits_nothing(self) -> None:
        """A zero budget returns an empty list without raising."""
        client, _ = _client(_pr_routes())
        context, patcher = _context_with_client(client, max_tokens=0)
        self.addCleanup(patcher.stop)
        self.assertEqual(await context.load(), [])

    async def test_single_char_over_budget_truncates_boundary_item(self) -> None:
        """Content one character over budget clips with a counted marker."""
        from vidbyte.context.primitives.documents import DocumentContextItem

        admission = ContextAdmission(max_tokens=4)
        result = admission.admit((DocumentContextItem(source="s", content="x" * 21, title="t"),))
        self.assertEqual(len(result.items), 1)
        self.assertTrue(result.truncated)
        self.assertLessEqual(result.tokens_admitted, 4)

    async def test_unicode_payload_clipped_by_utf8_bytes_not_chars(self) -> None:
        """Multibyte clipping never splits a code point and appends a marker."""
        clipped = TextClipper.clip("héllo wörld ünicodé", 10)
        self.assertLessEqual(len(clipped.encode("utf-8")), 10)
        clipped.encode("utf-8").decode("utf-8")

    async def test_expired_token_raises_source_access_error(self) -> None:
        """A REST 401 raises AUTH_REQUIRED with no token in the message."""
        client, _ = _client([("api.github.com", 401, "Bad credentials")])
        context, patcher = _context_with_client(client)
        self.addCleanup(patcher.stop)
        with self.assertRaises(SourceFetchError) as caught:
            await context.load()
        self.assertEqual(caught.exception.details.get("state"), "AUTH_REQUIRED")
        self.assertNotIn(TOKEN, str(caught.exception))

    async def test_cli_auth_failure_does_not_fallback(self) -> None:
        """An attempted CLI auth failure raises instead of silently switching transports."""
        runner = FakeCliRunner(lambda request: (_ for _ in ()).throw(CliCommandError("AUTH_REQUIRED")))
        client, transport = _client(_pr_routes(), runner=runner)
        context, patcher = _context_with_client(client)
        self.addCleanup(patcher.stop)
        with self.assertRaises(SourceFetchError) as caught:
            await context.load()
        self.assertEqual(caught.exception.details["state"], "AUTH_REQUIRED")
        self.assertEqual(transport.requests, [])

    async def test_rate_limit_mid_pagination_reports_rate_limit(self) -> None:
        """A REST rate limit on reviews raises instead of returning partial context."""
        client, _ = _client(_pr_routes(review_status=429))
        context, patcher = _context_with_client(client)
        self.addCleanup(patcher.stop)
        with self.assertRaises(SourceFetchError) as caught:
            await context.load()
        self.assertEqual(caught.exception.details.get("state"), "RATE_LIMITED")

    async def test_unknown_dict_key_rejected_at_construction(self) -> None:
        """A typo key raises ConfigurationError before any client exists."""
        with self.assertRaises(ConfigurationError):
            SourceContext({"provider": "github", "api_key": TOKEN, "resouce": "x"})

    async def test_truncation_marker_counted_in_budget(self) -> None:
        """Admitted token totals including markers never exceed the ceiling."""
        from vidbyte.context.primitives.documents import DocumentContextItem

        admission = ContextAdmission(max_tokens=8)
        items = (DocumentContextItem(source="s", content="y" * 100, title="a"), DocumentContextItem(source="s", content="z" * 100, title="b"))
        result = admission.admit(items)
        self.assertLessEqual(sum(admission.estimate_tokens(item.content) for item in result.items), 8)

    async def test_empty_list_not_returned_for_auth_failure(self) -> None:
        """Auth failure raises rather than returning an empty list."""
        client, _ = _client([("api.github.com", 401, "Bad credentials")])
        context, patcher = _context_with_client(client)
        self.addCleanup(patcher.stop)
        with self.assertRaises(SourceFetchError):
            await context.load()

    async def test_resource_case_preserved(self) -> None:
        """Mixed-case owner and repo round-trip into validated scope."""
        config = SourceConfig.from_mapping({"provider": "github", "api_key": TOKEN, "resource": "https://github.com/Acme/API"})
        self.assertEqual((config.owner, config.repo), ("Acme", "API"))

    async def test_provider_string_coerced_case_insensitively(self) -> None:
        """GitHub spelling is accepted while unknown providers raise."""
        config = SourceConfig.from_mapping({"provider": "GitHub", "api_key": TOKEN, "resource": "o/r"})
        self.assertEqual(config.provider, SourceProvider.GITHUB)
        with self.assertRaises(ConfigurationError):
            SourceConfig.from_mapping({"provider": "gitlab", "api_key": TOKEN, "resource": "o/r"})

    async def test_whitespace_api_key_rejected(self) -> None:
        """Blank credentials fail before any provider boundary."""
        with self.assertRaises(ConfigurationError):
            SourceContext({"provider": "github", "api_key": "   ", "resource": "o/r"})


class SourceToolTests(unittest.IsolatedAsyncioTestCase):
    """Verifies split GitHub tools, command planning, scope, and output bounds."""

    def _tool_with_transport(self, routes: list[tuple[str, int, str]], **kwargs: Any) -> tuple[list[Any], FakeGitHubTransport]:
        """Build SourceTool instances and rebind them to one offline client."""
        tool = SourceTool(dict(REPO_SOURCE), **kwargs)
        client, transport = _client(routes)
        built = [self._rebind(candidate, client) for candidate in tool.build()]
        return built, transport

    @staticmethod
    def _rebind(tool: Any, client: GitHubClient) -> Any:
        """Point one built tool at the fake-transport client for offline execution."""
        tool._client = client
        return tool

    async def test_cli_repository_operations_use_fixed_commands(self) -> None:
        """List, read, and search use CLI plans with no model-controlled scope fields."""
        def handler(request: CliRequest) -> CliResult:
            if request.args[0:2] == ("api", "search/code"):
                return CliResult(json.dumps({"items": [{"path": "a.py"}]}), "", 0)
            if request.args[1].endswith("contents/a.py"):
                return CliResult(json.dumps({"type": "file", "content": base64.b64encode(b"hello").decode()}), "", 0)
            return CliResult(json.dumps([{"path": "a.py"}, {"path": "b.py"}]), "", 0)

        runner = FakeCliRunner(handler)
        client, _ = _client([], runner=runner)
        source_tool = SourceTool(dict(REPO_SOURCE))
        with mock.patch.object(source_tool_module.SourceProviderFactory, "create", return_value=client):
            built = source_tool.build()
        listed = await built[0].execute(ToolCall(tool_name="github_list_files", arguments={"path": ""}))
        read = await built[1].execute(ToolCall(tool_name="github_read_file", arguments={"path": "a.py"}))
        searched = await built[2].execute(ToolCall(tool_name="github_search_code", arguments={"query": "hello"}))
        self.assertEqual(listed.status.value, "success")
        self.assertEqual(read.output, "hello")
        self.assertIn("acme/api/a.py", searched.output)
        self.assertTrue(all(TOKEN not in arg for request in runner.requests for arg in request.args))

    async def test_empty_path_lists_repo_root(self) -> None:
        """Empty path lists root while read with empty path fails validation."""
        routes = [("contents", 200, json.dumps([{"path": "a.py"}, {"path": "b.py"}]))]
        (lister, reader, _), _ = self._tool_with_transport(routes)
        listed = await lister.execute(ToolCall(tool_name="github_list_files", arguments={"path": ""}))
        self.assertIn("a.py", listed.output)
        failed = await reader.execute(ToolCall(tool_name="github_read_file", arguments={"path": ""}))
        self.assertEqual(failed.status.value, "error")

    async def test_unicode_output_is_clipped_by_utf8_bytes(self) -> None:
        """Tool output clipping respects UTF-8 bytes and stays within the bound."""
        routes = [("contents", 200, json.dumps({"type": "file", "content": base64.b64encode("héllo".encode()).decode()}))]
        (_, reader, _), _ = self._tool_with_transport(routes, max_output_bytes=5)
        result = await reader.execute(ToolCall(tool_name="github_read_file", arguments={"path": "a.py"}))
        self.assertLessEqual(len(result.output.encode()), 5)

    async def test_transport_timeout_during_tool_call_fails_result(self) -> None:
        """A hanging REST transport becomes a failed ToolResult, never a raise."""

        class HangingTransport(FakeGitHubTransport):
            """Raises a timeout for every request."""

            async def request(self, **kwargs: Any) -> HttpResponse:
                """Raise a safe timeout sentinel."""
                raise TimeoutError("timed out")

        tool = SourceTool(dict(REPO_SOURCE))
        client = GitHubClient(GitHubClientConfig(api_key=TOKEN, transport=HangingTransport([]), runner=UnavailableCliRunner()))
        [reader] = [self._rebind(candidate, client) for candidate in tool.build() if candidate.spec().name == "github_read_file"]
        result = await reader.execute(ToolCall(tool_name="github_read_file", arguments={"path": "a.py"}))
        self.assertEqual(result.status.value, "error")
        self.assertIn("error_type", result.metadata)

    async def test_pr_resource_rejected_by_source_tool(self) -> None:
        """A pull-request resource raises a kind mismatch at construction."""
        with self.assertRaises(ConfigurationError):
            SourceTool(dict(PR_SOURCE))

    async def test_path_escape_attempt_cannot_leave_repo(self) -> None:
        """Traversal, absolute paths, and URLs fail before transport requests."""
        routes = [("api.github.com", 200, "{}")]
        (_, reader, _), transport = self._tool_with_transport(routes)
        for evil in ("../../etc/passwd", "/etc/passwd", "https://evil.com/x", "C:/etc/passwd"):
            result = await reader.execute(ToolCall(tool_name="github_read_file", arguments={"path": evil}))
            self.assertEqual(result.status.value, "error")
        self.assertEqual(transport.requests, [])

    async def test_search_repo_qualifier_rejected(self) -> None:
        """A repo qualifier fails while a legal query stays bound to the exact repo."""
        routes = [("search/code", 200, json.dumps({"items": [{"path": "a.py"}]}))]
        (_, _, searcher), transport = self._tool_with_transport(routes)
        denied = await searcher.execute(ToolCall(tool_name="github_search_code", arguments={"query": "x repo:other/repo"}))
        self.assertEqual(denied.status.value, "error")
        allowed = await searcher.execute(ToolCall(tool_name="github_search_code", arguments={"query": "hello"}))
        self.assertIn("acme/api/a.py", allowed.output)
        self.assertIn("repo%3Aacme/api", transport.requests[-1]["url"])

    async def test_tool_url_ignores_model_supplied_host(self) -> None:
        """Specs expose no host fields and requests use only bound scope."""
        tool = SourceTool(dict(REPO_SOURCE))
        built = tool.build()
        names = {parameter.name for candidate in built for parameter in candidate.spec().parameters}
        self.assertTrue(names.isdisjoint({"host", "owner", "repo", "url", "command", "route"}))
        transport = FakeGitHubTransport([("search/code", 200, json.dumps({"items": []}))])
        client = GitHubClient(GitHubClientConfig(api_key=TOKEN, transport=transport, runner=UnavailableCliRunner()))
        searcher = self._rebind(built[2], client)
        await searcher.execute(ToolCall(tool_name="github_search_code", arguments={"query": "q"}))
        self.assertIn("/search/code", transport.requests[0]["url"])
        self.assertIn("api.github.com", transport.requests[0]["url"])

    async def test_agent_attachment_accepts_both_lists(self) -> None:
        """Context items and tools attach to a real Agent without network execution."""
        client, _ = _client(_pr_routes())
        context, patcher = _context_with_client(client)
        self.addCleanup(patcher.stop)
        items = await context.load()
        tools = SourceTool(dict(REPO_SOURCE)).build()
        agent = Agent(name="reviewer", system_prompt="Review.", context_items=items, tools=tools)
        self.assertEqual(len(items), 4)
        self.assertIsNotNone(agent)

    async def test_strict_github_client_config(self) -> None:
        """Token prefixes, timeout bounds, and transport types are validated."""
        with self.assertRaises(ConfigurationError):
            GitHubClientConfig(api_key="token", runner=UnavailableCliRunner())
        with self.assertRaises(ConfigurationError):
            GitHubClientConfig(api_key=TOKEN, timeout_seconds=121.0, runner=UnavailableCliRunner())
        with self.assertRaises(ConfigurationError):
            GitHubClientConfig(api_key=TOKEN, transport=object(), runner=UnavailableCliRunner())  # type: ignore[arg-type]

    async def test_source_provider_factory_uses_concrete_switch(self) -> None:
        """The factory returns GitHubClient without exposing a shared protocol."""
        from vidbyte.integrations.providers import SourceProviderFactory

        config = SourceConfig(provider=SourceProvider.GITHUB, api_key=TOKEN, resource="o/r", kind=SourceKind.REPOSITORY, owner="o", repo="r")
        self.assertIsInstance(SourceProviderFactory.create(config), GitHubClient)


if __name__ == "__main__":
    unittest.main()
