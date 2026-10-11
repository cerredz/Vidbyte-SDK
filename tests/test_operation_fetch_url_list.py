"""FILE: tests/test_operation_fetch_url_list.py

PURPOSE: Prove firecrawl_fetch uses the single url argument when the urls list is empty or blank.
ROLE IN CODEBASE: Drives vidbyte.tools.builtins.operations.fetch.FirecrawlFetchTool and its _url_list helper without a provider client.
ARCHITECTURE NOTE: With no client the tool returns its priced contract stub, whose units equal the URLs it resolved.
COMMON MODIFICATION PATTERNS: Add a case when another fetch tool starts declaring both url and urls.
KNOWN EDGE CASES: A model filling every optional field sends url plus an empty urls list.
RELATED DOCS: none
TESTS: This module; full source gate via scripts/run_ci.py.
"""

from __future__ import annotations

import pytest

from vidbyte.lib.dataclasses import ToolCall
from vidbyte.tools.builtins.operations.fetch import FirecrawlFetchTool, _url_list


@pytest.mark.parametrize("urls", [[], ["", "  "]])
def test_url_list_falls_back_to_url_when_urls_has_no_entries(urls: list[str]) -> None:
    call = ToolCall("firecrawl_fetch", {"url": "https://example.com/a", "urls": urls})
    assert _url_list(call) == ["https://example.com/a"]


def test_url_list_prefers_non_empty_urls_over_url() -> None:
    call = ToolCall("firecrawl_fetch", {"url": "https://example.com/a", "urls": ["https://example.com/b"]})
    assert _url_list(call) == ["https://example.com/b"]


@pytest.mark.asyncio
async def test_firecrawl_fetch_accepts_url_with_empty_urls() -> None:
    result = await FirecrawlFetchTool().execute(
        ToolCall("firecrawl_fetch", {"url": "https://example.com/a", "urls": []})
    )

    assert result.status.value == "success"
    assert "requires a url or urls" not in result.output
    assert result.metadata["operation_usage"]["units"] == 1


@pytest.mark.asyncio
async def test_firecrawl_fetch_still_rejects_missing_urls() -> None:
    result = await FirecrawlFetchTool().execute(ToolCall("firecrawl_fetch", {"urls": []}))

    assert result.status.value == "error"
    assert result.metadata["error"] == "missing_url"
