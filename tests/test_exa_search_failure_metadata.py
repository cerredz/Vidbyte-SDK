"""Tests safe provider diagnostics retained by the Exa search tool."""

from __future__ import annotations

import pytest

from vidbyte.lib.dataclasses import ToolCall
from vidbyte.lib.dataclasses.operations import SearchPayload
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.tools.builtins.operations.clients import ExaClient
from vidbyte.tools.builtins.operations.search import ExaSearchTool


class FailingExaClient(ExaClient):
    """Provider client double that fails without making a network request."""

    async def search(self, query: str, *, num_results: int = 10, search_type: str = "auto") -> SearchPayload:
        raise ProviderRequestError("provider rejected the request", provider="exa", status_code=401)


@pytest.mark.asyncio
async def test_exa_failure_retains_only_safe_provider_diagnostics() -> None:
    result = await ExaSearchTool(client=FailingExaClient("test-key")).execute(
        ToolCall("exa_search", {"query": "private research question"})
    )

    assert result.metadata["error"] == "search_failed"
    assert result.metadata["error_type"] == "ProviderRequestError"
    assert result.metadata["error_status_code"] == 401
    assert "private research question" not in repr(result.metadata)
