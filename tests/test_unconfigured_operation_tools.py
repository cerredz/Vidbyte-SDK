"""FILE: tests/test_unconfigured_operation_tools.py

PURPOSE: Prove a prebuilt search or fetch tool with no provider client returns an unbilled unconfigured error, and that an agent run calling one records no operation.
ROLE IN CODEBASE: Drives every client-less tool in vidbyte/tools/builtins/operations/ and the AgentRuntime operation meter (_record_operation_usage) that prices tool results.
ARCHITECTURE NOTE: No socket opens. Unit cases call execute() directly; the agent cases run BaseAgent over the loop_spend_cap ScriptedRunner, and the configured control replaces HttpTransport._send_once.
COMMON MODIFICATION PATTERNS: A new prebuilt PricedOperationTool adds one CLIENTLESS_CASES row with valid arguments.
KNOWN EDGE CASES: Linkup, OpenAlex and Semantic Scholar have no SDK client, so they are unconfigured even when some other client is bound. An argument error such as missing_url still wins, because it is reported before the client check.
RELATED DOCS: docs/design/unconfigured-tools-not-billed.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/test_unconfigured_operation_tools.py
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tests.features.loop_spend_cap.loop_spend_cap_fixtures import ScriptedRunner, call_response, done_response, priced_agent, reference_cost, usage
from vidbyte.lib.dataclasses import ToolCall
from vidbyte.lib.http.transport import HttpResponse, HttpTransport
from vidbyte.tools.builtins.operations import (
    BraveSearchTool,
    BrowserbaseFetchTool,
    BrowserbaseSearchTool,
    ExaSearchTool,
    FirecrawlFetchTool,
    LinkupFetchTool,
    LinkupSearchTool,
    OpenAlexSearchTool,
    ParallelExtractTool,
    ParallelSearchTool,
    PricedOperationTool,
    SemanticScholarSearchTool,
    TavilyExtractTool,
    TavilySearchTool,
)
from vidbyte.tools.builtins.operations.clients import ExaClient
from vidbyte.tools.types import ToolStatus

PAGE = "https://example.com/a"
CLIENTLESS_CASES: list[tuple[type[PricedOperationTool], dict[str, Any]]] = [
    (BraveSearchTool, {"query": "vidbyte pricing"}),
    (BrowserbaseSearchTool, {"query": "vidbyte pricing"}),
    (ExaSearchTool, {"query": "vidbyte pricing", "num_results": 25}),
    (TavilySearchTool, {"query": "vidbyte pricing", "search_depth": "advanced"}),
    (LinkupSearchTool, {"query": "vidbyte pricing", "depth": "deep"}),
    (ParallelSearchTool, {"objective": "vidbyte pricing", "processor": "pro"}),
    (OpenAlexSearchTool, {"query": "vidbyte pricing"}),
    (SemanticScholarSearchTool, {"query": "vidbyte pricing"}),
    (FirecrawlFetchTool, {"urls": [PAGE, PAGE + "b"]}),
    (BrowserbaseFetchTool, {"url": PAGE, "proxies": True}),
    (ParallelExtractTool, {"urls": [PAGE]}),
    (TavilyExtractTool, {"urls": [PAGE], "extract_depth": "advanced"}),
    (LinkupFetchTool, {"url": PAGE, "render_js": True}),
]
_EXA_BODY = '{"results": [{"url": "https://example.com", "title": "Example"}]}'


def _call(tool: PricedOperationTool, arguments: dict[str, Any]) -> ToolCall:
    return ToolCall(tool.spec().name, arguments)


@pytest.mark.parametrize(("tool_class", "arguments"), CLIENTLESS_CASES, ids=[case[0].__name__ for case in CLIENTLESS_CASES])
def test_a_tool_without_a_client_is_an_unconfigured_error(tool_class: type[PricedOperationTool], arguments: dict[str, Any]) -> None:
    # [Silent Failure] A priced success here was billed as a real
    # provider operation although no request was ever sent.
    tool = tool_class()

    result = asyncio.run(tool.execute(_call(tool, arguments)))

    assert result.status is ToolStatus.ERROR
    assert result.metadata == {"error": "unconfigured"}
    assert tool_class.declares_usage(result) is False


@pytest.mark.parametrize(("tool_class", "arguments"), CLIENTLESS_CASES, ids=[case[0].__name__ for case in CLIENTLESS_CASES])
def test_the_unconfigured_message_names_the_tool_and_says_nothing_was_sent(tool_class: type[PricedOperationTool], arguments: dict[str, Any]) -> None:
    # [Silent Failure] The model must not be told a search or fetch ran.
    tool = tool_class()

    result = asyncio.run(tool.execute(_call(tool, arguments)))

    assert result.output == f"{tool.spec().name} is not configured: it has no {tool_class.provider} client, so no {tool_class.operation} request was sent."


def test_a_missing_argument_still_wins_over_unconfigured() -> None:
    # [Edge Case] Argument validation runs before the client check, and
    # it declares zero units, so it was never billed either.
    result = asyncio.run(FirecrawlFetchTool().execute(ToolCall("firecrawl_fetch", {"urls": []})))

    assert result.status is ToolStatus.ERROR
    assert result.metadata["error"] == "missing_url"


def test_linkup_ignores_a_foreign_client_and_stays_unconfigured() -> None:
    # [Hidden Assumption] Binding some client is not enough: Linkup has
    # no client path, so it still sends nothing and declares no usage.
    tool = LinkupSearchTool(client=ExaClient("test-key"))

    result = asyncio.run(tool.execute(ToolCall("linkup_search", {"query": "q"})))

    assert result.metadata == {"error": "unconfigured"}
    assert LinkupSearchTool.declares_usage(result) is False


def test_an_agent_calling_an_unconfigured_tool_records_no_operation() -> None:
    # [Silent Failure] Through the real runtime meter: the run's ledger
    # holds the two model calls and no phantom Exa operation.
    responses = (call_response(("exa_search", {"query": "vidbyte pricing"}), usage=usage(1_000, 20)), done_response("done", usage=usage(1_200, 10)))
    runner = ScriptedRunner(*responses)
    agent = priced_agent(runner, tools=[ExaSearchTool()])

    asyncio.run(agent.arun("Find Vidbyte's pricing."))

    rollup = agent.get_usage()
    assert rollup.operation_count == 0
    assert rollup.model_call_count == 2
    assert rollup.cost_usd == pytest.approx(reference_cost(*responses))
    assert "exa_search is not configured: it has no exa client, so no search request was sent." in str(runner.prompts[1:]) + str(runner.options[1:])


def test_a_configured_tool_still_records_its_operation(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Hidden Failure] Control: the fix must not stop billing a search
    # that a bound client really sent.
    sends: list[dict[str, Any]] = []

    async def fake_send(self: HttpTransport, client: object, **kwargs: Any) -> HttpResponse:
        sends.append(kwargs)
        return HttpResponse(status_code=200, body=_EXA_BODY, headers={})

    monkeypatch.setattr(HttpTransport, "_send_once", fake_send)
    responses = (call_response(("exa_search", {"query": "vidbyte pricing"}), usage=usage(1_000, 20)), done_response("done", usage=usage(1_200, 10)))
    agent = priced_agent(ScriptedRunner(*responses), tools=[ExaSearchTool(client=ExaClient("test-key"))])

    asyncio.run(agent.arun("Find Vidbyte's pricing."))

    rollup = agent.get_usage()
    assert len(sends) == 1
    assert rollup.operation_count == 1
    assert [(record.provider, record.operation) for record in rollup.operations] == [("exa", "search")]
    assert rollup.cost_usd == pytest.approx(reference_cost(*responses) + rollup.operations[0].cost_usd)
