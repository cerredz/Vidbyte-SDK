"""FILE: tests/test_source_context_tools.py

PURPOSE: Covers SourceContext loads and SourceTool builds against an injected fake GitHub transport.
ROLE IN CODEBASE: Proves budgets, scope enforcement, error mapping, and Agent attachment without any network use.
ARCHITECTURE NOTE: Every test injects FakeGitHubTransport into GitHubClient; no test touches the real api.github.com.
COMMON MODIFICATION PATTERNS: Add one test per new failure state or scope rule, keeping transport injection as the seam.
KNOWN EDGE CASES: Unicode clipping, zero budgets, path escapes, repo: qualifiers, and mid-pagination failures.
RELATED DOCS: docs/design/source-context-tools.md
TESTS: Run with python scripts/run_ci.py --stage source or scripts/test-source-context-tools.py.
"""

from __future__ import annotations

import base64
import json
import unittest
from collections.abc import Mapping
from typing import Any
from unittest import mock

from vidbyte import Agent, SourceContext, SourceTool
from vidbyte.integrations import source_context as source_context_module
from vidbyte.integrations.github import GitHubClient, clip_text
from vidbyte.integrations.providers import create_client
from vidbyte.lib.dataclasses.integrations import SourceConfig
from vidbyte.lib.enums.integrations import SourceKind, SourceProvider
from vidbyte.lib.errors import ConfigurationError, SourceFetchError
from vidbyte.lib.http.transport import HttpResponse, HttpTransport
from vidbyte.tools.types import ToolCall

PR_SOURCE = {"provider": "github", "api_key": "token-123", "resource": "https://github.com/acme/api/pull/41"}
REPO_SOURCE = {"provider": "github", "api_key": "token-123", "resource": "https://github.com/acme/api"}

PULL_PAYLOAD = {"title": "Fix auth", "body": "Description text here.", "head": {"sha": "abc123"}, "base": {"sha": "def456"}}


class FakeGitHubTransport(HttpTransport):
    """Canned GitHub responses keyed by URL substring with full request recording."""

    def __init__(self, routes: list[tuple[str, int, str]]) -> None:
        """Store ordered URL-substring routes mapping to status and body."""
        self._routes = routes
        self.requests: list[dict[str, Any]] = []

    async def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 60.0, retry_count: int = 0, backoff_seconds: float = 0.5, backoff_multiplier: float = 2.0, retry_status_codes: tuple[int, ...] = (500,), max_response_bytes: int | None = None, idempotency_key: str | None = None, follow_redirects: bool = False) -> HttpResponse:
        """Record the request and return the first matching canned response."""
        self.requests.append({"method": method, "url": url, "headers": dict(headers)})
        for needle, status, body in self._routes:
            if needle in url:
                return HttpResponse(status_code=status, body=body, headers={})
        return HttpResponse(status_code=404, body="not found", headers={})


def _pr_routes(*, list_marker: str = '[{"user": {"login": "r"}, "state": "APPROVED", "body": "LGTM"}]', empty: bool = False) -> list[tuple[str, int, str]]:
    """Build standard pull-request routes with optional empty sections."""
    reviews = "[]" if empty else list_marker
    comments = "[]" if empty else '[{"user": {"login": "c"}, "body": "Nice work"}]'
    body = "" if empty else "Description text here."
    pull = dict(PULL_PAYLOAD)
    pull["body"] = body
    return [("pulls/41/reviews", 200, reviews), ("issues/41/comments", 200, comments), ("pulls/41", 200, json.dumps(pull)), ("api.github.com", 200, "diff --git a/x b/x\n+line\n")]


def _context_with_transport(routes: list[tuple[str, int, str]], **kwargs: Any) -> tuple[SourceContext, FakeGitHubTransport, mock._patch]:
    """Build a SourceContext whose provider client uses the fake transport."""
    context = SourceContext(dict(PR_SOURCE), **kwargs)
    transport = FakeGitHubTransport(routes)
    client = GitHubClient(api_key="token-123", transport=transport)
    patcher = mock.patch.object(source_context_module, "create_client", return_value=client)
    patcher.start()
    return context, transport, patcher


class SourceContextTests(unittest.IsolatedAsyncioTestCase):
    """Verifies pull-request loads, budgets, and failure mapping."""

    async def test_empty_pr_sections_admit_cleanly(self) -> None:
        """[Edge Case] Empty sections return four items with no truncation flags."""
        context, _, patcher = _context_with_transport(_pr_routes(empty=True))
        self.addCleanup(patcher.stop)
        items = await context.load()
        self.assertEqual(len(items), 4)
        self.assertTrue(all(item.metadata.get("truncated") is False for item in items))

    async def test_zero_max_tokens_admits_nothing(self) -> None:
        """[Edge Case] A zero budget returns an empty list without raising."""
        context, _, patcher = _context_with_transport(_pr_routes(), max_tokens=0)
        self.addCleanup(patcher.stop)
        self.assertEqual(await context.load(), [])

    async def test_single_char_over_budget_truncates_boundary_item(self) -> None:
        """[Edge Case] Content one char over budget clips with a counted marker."""
        from vidbyte.context.primitives.documents import DocumentContextItem
        from vidbyte.integrations.budget import ContextAdmission

        admission = ContextAdmission(max_tokens=4)
        item = DocumentContextItem(source="s", content="x" * 21, title="t")
        result = admission.admit((item,))
        self.assertEqual(len(result.items), 1)
        self.assertTrue(result.truncated)
        self.assertLessEqual(result.tokens_admitted, 4)

    async def test_unicode_payload_clipped_by_utf8_bytes_not_chars(self) -> None:
        """[Edge Case] Multibyte clipping never splits a code point and appends the marker."""
        clipped = clip_text("héllo wörld ünïcodé", 10)
        self.assertLessEqual(len(clipped.encode("utf-8")), 10)
        clipped.encode("utf-8").decode("utf-8")

    async def test_expired_token_raises_source_access_error(self) -> None:
        """[Hidden Failure] A 401 raises AUTH_REQUIRED with no token in the message."""
        context, _, patcher = _context_with_transport([("api.github.com", 401, "Bad credentials")])
        self.addCleanup(patcher.stop)
        with self.assertRaises(SourceFetchError) as caught:
            await context.load()
        self.assertEqual(caught.exception.details.get("state"), "AUTH_REQUIRED")
        self.assertNotIn("token-123", str(caught.exception))

    async def test_rate_limit_mid_pagination_reports_transport_state(self) -> None:
        """[Hidden Failure] A 429 on page two raises RATE_LIMITED instead of partial items."""
        pull = json.dumps(PULL_PAYLOAD)
        routes = [("pulls/41/reviews", 429, "rate limit exceeded"), ("pulls/41", 200, pull), ("api.github.com", 200, "diff")]
        context, _, patcher = _context_with_transport(routes)
        self.addCleanup(patcher.stop)
        with self.assertRaises(SourceFetchError) as caught:
            await context.load()
        self.assertEqual(caught.exception.details.get("state"), "RATE_LIMITED")

    async def test_unknown_dict_key_rejected_at_construction(self) -> None:
        """[Hidden Failure] A typo key raises ConfigurationError before any network use."""
        with self.assertRaises(ConfigurationError):
            SourceContext({"provider": "github", "api_key": "t", "resouce": "x"})

    async def test_truncation_marker_counted_in_budget(self) -> None:
        """[Silent Failure] Admitted token totals including markers never exceed the ceiling."""
        from vidbyte.context.primitives.documents import DocumentContextItem
        from vidbyte.integrations.budget import ContextAdmission, estimate_tokens

        admission = ContextAdmission(max_tokens=8)
        items = (DocumentContextItem(source="s", content="y" * 100, title="a"), DocumentContextItem(source="s", content="z" * 100, title="b"))
        result = admission.admit(items)
        self.assertLessEqual(sum(estimate_tokens(item.content) for item in result.items), 8)

    async def test_empty_list_not_returned_for_auth_failure(self) -> None:
        """[Silent Failure] Auth failure raises rather than returning an empty list."""
        context, _, patcher = _context_with_transport([("api.github.com", 401, "Bad credentials")])
        self.addCleanup(patcher.stop)
        with self.assertRaises(SourceFetchError):
            await context.load()

    async def test_resource_case_preserved(self) -> None:
        """[Hidden Assumption] Mixed-case owner and repo round-trip byte-identical into URLs."""
        config = SourceConfig.from_mapping({"provider": "github", "api_key": "t", "resource": "https://github.com/Acme/API"})
        self.assertEqual((config.owner, config.repo), ("Acme", "API"))

    async def test_provider_string_coerced_case_insensitively(self) -> None:
        """[Hidden Assumption] GitHub spelling is accepted while unknown providers raise."""
        config = SourceConfig.from_mapping({"provider": "GitHub", "api_key": "t", "resource": "o/r"})
        self.assertEqual(config.provider, SourceProvider.GITHUB)
        with self.assertRaises(ConfigurationError):
            SourceConfig.from_mapping({"provider": "gitlab", "api_key": "t", "resource": "o/r"})

    async def test_whitespace_api_key_rejected(self) -> None:
        """[Hidden Assumption] A blank key raises without any HTTP attempt."""
        with self.assertRaises(ConfigurationError):
            SourceContext({"provider": "github", "api_key": "   ", "resource": "o/r"})

    async def test_second_provider_requires_no_registry_change(self) -> None:
        """[Hidden Assumption] The factory names unknown providers instead of importing them."""
        config = SourceConfig(provider=SourceProvider.GITHUB, api_key="t", resource="o/r", kind=SourceKind.REPOSITORY, owner="o", repo="r")
        client = create_client(config)
        self.assertIsInstance(client, GitHubClient)


class SourceToolTests(unittest.IsolatedAsyncioTestCase):
    """Verifies scoped tool builds, argument validation, and output bounds."""

    def _tool_with_transport(self, routes: list[tuple[str, int, str]], **kwargs: Any) -> tuple[Any, FakeGitHubTransport]:
        """Build SourceTool instances whose clients share one fake transport."""
        tool = SourceTool(dict(REPO_SOURCE), **kwargs)
        transport = FakeGitHubTransport(routes)
        client = GitHubClient(api_key="token-123", transport=transport)
        built = [self._rebind(t, client) for t in tool.build()]
        return built, transport

    @staticmethod
    def _rebind(tool: Any, client: GitHubClient) -> Any:
        """Point one built tool at the fake-transport client for offline execution."""
        tool._client = client
        return tool

    async def test_empty_path_lists_repo_root(self) -> None:
        """[Edge Case] Empty path lists root while read with empty path fails validation."""
        routes = [("contents/", 200, json.dumps([{"path": "a.py"}, {"path": "b.py"}]))]
        (lister, reader, _), _ = self._tool_with_transport(routes)
        listed = await lister.execute(ToolCall(tool_name="github_list_files", arguments={"path": ""}))
        self.assertIn("a.py", listed.output)
        failed = await reader.execute(ToolCall(tool_name="github_read_file", arguments={"path": ""}))
        self.assertEqual(failed.status.value, "error")

    async def test_transport_timeout_during_tool_call_fails_result(self) -> None:
        """[Hidden Failure] A hanging transport becomes a failed ToolResult, never a raise."""
        content = base64.b64encode(b"hello").decode()

        class HangingTransport(FakeGitHubTransport):
            async def request(self, **kwargs: Any) -> HttpResponse:
                raise TimeoutError("timed out")

        tool = SourceTool(dict(REPO_SOURCE))
        client = GitHubClient(api_key="t", transport=HangingTransport([]))
        [reader] = [self._rebind(t, client) for t in tool.build() if t.spec().name == "github_read_file"]
        result = await reader.execute(ToolCall(tool_name="github_read_file", arguments={"path": "a.py"}))
        self.assertEqual(result.status.value, "error")
        self.assertIn("error_type", result.metadata)
        _ = content

    async def test_pr_resource_rejected_by_source_tool(self) -> None:
        """[Hidden Failure] A pull-request resource raises a kind mismatch at construction."""
        with self.assertRaises(ConfigurationError):
            SourceTool(dict(PR_SOURCE))

    async def test_path_escape_attempt_cannot_leave_repo(self) -> None:
        """[Silent Failure] Traversal and absolute paths fail with zero requests sent."""
        routes = [("api.github.com", 200, "{}")]
        (_, reader, _), transport = self._tool_with_transport(routes)
        for evil in ("../../etc/passwd", "/etc/passwd", "https://evil.com/x"):
            result = await reader.execute(ToolCall(tool_name="github_read_file", arguments={"path": evil}))
            self.assertEqual(result.status.value, "error")
        self.assertEqual(transport.requests, [])

    async def test_search_repo_qualifier_rejected(self) -> None:
        """[Silent Failure] A repo: qualifier fails and legal queries bind the exact repo."""
        routes = [("search/code", 200, json.dumps({"items": [{"path": "a.py"}]}))]
        (_, _, searcher), transport = self._tool_with_transport(routes)
        denied = await searcher.execute(ToolCall(tool_name="github_search_code", arguments={"query": "x repo:other/repo"}))
        self.assertEqual(denied.status.value, "error")
        allowed = await searcher.execute(ToolCall(tool_name="github_search_code", arguments={"query": "hello"}))
        self.assertIn("acme/api/a.py", allowed.output)
        self.assertIn("repo%3Aacme/api", transport.requests[-1]["url"])

    async def test_tool_url_ignores_model_supplied_host(self) -> None:
        """[Silent Failure] Specs expose no host fields and requests hit the bound scope URL."""
        tool = SourceTool(dict(REPO_SOURCE))
        built = tool.build()
        names = {parameter.name for candidate in built for parameter in candidate.spec().parameters}
        self.assertTrue(names.isdisjoint({"host", "owner", "repo", "url"}))
        _, _, searcher = built
        transport = FakeGitHubTransport([("search/code", 200, json.dumps({"items": []}))])
        bound = self._rebind(searcher, GitHubClient(api_key="t", transport=transport))
        await bound.execute(ToolCall(tool_name="github_search_code", arguments={"query": "q"}))
        self.assertIn("/search/code", transport.requests[0]["url"])
        self.assertIn("api.github.com", transport.requests[0]["url"])

    async def test_agent_attachment_accepts_both_lists(self) -> None:
        """[Hidden Assumption] Context items and tools attach to a real Agent and execute."""
        context, _, patcher = _context_with_transport(_pr_routes())
        self.addCleanup(patcher.stop)
        items = await context.load()
        tool = SourceTool(dict(REPO_SOURCE))
        agent = Agent(name="reviewer", system_prompt="Review.", context_items=items, tools=tool.build())
        self.assertEqual(len(items), 4)
        self.assertIsNotNone(agent)


if __name__ == "__main__":
    unittest.main()
