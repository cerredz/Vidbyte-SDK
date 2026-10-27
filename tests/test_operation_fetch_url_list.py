"""FILE: tests/test_operation_fetch_url_list.py

PURPOSE: Prove firecrawl_fetch uses the single url argument when the urls list is empty or blank.
ROLE IN CODEBASE: Drives vidbyte.tools.builtins.operations.fetch.FirecrawlFetchTool and its _url_list helper through a recording FirecrawlClient.
ARCHITECTURE NOTE: The recording client keeps the URLs the tool resolved and answers without a socket; with no client at all the tool returns an unbilled unconfigured error, so the client is what proves the URL reached the provider.
COMMON MODIFICATION PATTERNS: Add a case when another fetch tool starts declaring both url and urls.
KNOWN EDGE CASES: A model filling every optional field sends url plus an empty urls list.
RELATED DOCS: none
TESTS: This module; full source gate via scripts/run_ci.py.
"""

from __future__ import annotations

import pytest

from collections.abc import Sequence

from vidbyte.lib.dataclasses import ToolCall
from vidbyte.lib.dataclasses.operations import FetchedPage, FetchPayload
from vidbyte.tools.builtins.operations.clients import FirecrawlClient
from vidbyte.tools.builtins.operations.fetch import FirecrawlFetchTool, _url_list


class RecordingFirecrawlClient(FirecrawlClient):
    """A FirecrawlClient that records the URLs it was asked to scrape and answers without a socket."""

    def __init__(self) -> None:
        super().__init__("fc-test-key")
        self.scraped: list[list[str]] = []

    async def scrape(self, urls: Sequence[str]) -> FetchPayload:
        self.scraped.append(list(urls))
        pages = tuple(FetchedPage(url=url, final_url=url, content="page", content_type="text/markdown") for url in urls)
        return FetchPayload(provider="firecrawl", pages=pages, billable_units=len(pages))


@pytest.mark.parametrize("urls", [[], ["", "  "]])
def test_url_list_falls_back_to_url_when_urls_has_no_entries(urls: list[str]) -> None:
    call = ToolCall("firecrawl_fetch", {"url": "https://example.com/a", "urls": urls})
    assert _url_list(call) == ["https://example.com/a"]


def test_url_list_prefers_non_empty_urls_over_url() -> None:
    call = ToolCall("firecrawl_fetch", {"url": "https://example.com/a", "urls": ["https://example.com/b"]})
    assert _url_list(call) == ["https://example.com/b"]


@pytest.mark.asyncio
async def test_firecrawl_fetch_accepts_url_with_empty_urls() -> None:
    client = RecordingFirecrawlClient()
    result = await FirecrawlFetchTool(client=client).execute(
        ToolCall("firecrawl_fetch", {"url": "https://example.com/a", "urls": []})
    )

    assert result.status.value == "success"
    assert "requires a url or urls" not in result.output
    assert client.scraped == [["https://example.com/a"]]
    assert result.metadata["operation_usage"]["units"] == 1


@pytest.mark.asyncio
async def test_firecrawl_fetch_still_rejects_missing_urls() -> None:
    result = await FirecrawlFetchTool().execute(ToolCall("firecrawl_fetch", {"urls": []}))

    assert result.status.value == "error"
    assert result.metadata["error"] == "missing_url"
