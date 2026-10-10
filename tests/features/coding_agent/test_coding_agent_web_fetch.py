"""FILE: tests/features/coding_agent/test_coding_agent_web_fetch.py

PURPOSE: Prove that the fetch key a caller passes picks, authenticates, and is confined to one WebFetch provider, and that the model of a CodingAgent reads the pages a keyed provider fetched.
ROLE IN CODEBASE: Builds vidbyte.CodingAgent with each of the four key parameters and compares its WebFetch tool against the bare priced tool from vidbyte/tools/builtins/operations/fetch.py over the same faked HTTP send.
ARCHITECTURE NOTE: HttpTransport._send_once is the only fake (conftest.py), so the real provider clients build real requests; the comparison with the bare tool proves the view changes the model-visible text and nothing else.
FUNCTION INVENTORY: test_the_supplied_key_picks_* (AC-6, INV-5, INV-6, INV-18); test_keyed_fetch_sends_* (FR-5, FR-6, INV-5, INV-6, INV-16); test_failed_keyed_fetch_* (INV-16, EC-3, AC-23); test_key_is_absent_* (AC-23, INV-17); test_two_fetch_keys_* (AC-4, EC-1); test_blank_or_non_string_* (AC-5, EC-2).
COMMON MODIFICATION PATTERNS: A new keyed provider adds one row to PROVIDERS and, if its client reads a new response field, one field to PROVIDER_PAGE_BODY.
WHAT NOT TO DO IN THIS FILE: 1. Do not use real keys or real hosts' responses; every key here is a placeholder. 2. Do not read private client fields; observe the outgoing request, the tool result, and the agent's exports.
KNOWN EDGE CASES: Provider environment variables are set to a different value on purpose, so a fallback to the environment shows up as the wrong key on the wire. Blank keys cannot be checked for echoing, since an empty string is in every message.
RELATED DOCS: tests/features/coding_agent/FEATURE.md; docs/spec/coding-agent/spec.md (§6.1 INV-5, INV-6, INV-16 to INV-18; §6.2 AC-4 to AC-7, AC-23; §8.5)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/test_coding_agent_web_fetch.py
"""

from __future__ import annotations

import itertools
import os
import socket
import subprocess

import pytest

from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.builtins.operations.clients import BrowserbaseClient, FirecrawlClient, ParallelClient, TavilyClient
from vidbyte.tools.builtins.operations.fetch import BrowserbaseFetchTool, FirecrawlFetchTool, ParallelExtractTool, TavilyExtractTool
from vidbyte.tools.types import ToolCall, ToolStatus

# key parameter -> (model-facing tool name, priced tool class, client class, API origin the request must reach)
PROVIDERS = {
    "firecrawl_api_key": ("firecrawl_fetch", FirecrawlFetchTool, FirecrawlClient, "https://api.firecrawl.dev/"),
    "browserbase_api_key": ("browserbase_fetch", BrowserbaseFetchTool, BrowserbaseClient, "https://api.browserbase.com/"),
    "parallel_api_key": ("parallel_extract", ParallelExtractTool, ParallelClient, "https://api.parallel.ai/"),
    "tavily_api_key": ("tavily_extract", TavilyExtractTool, TavilyClient, "https://api.tavily.com/"),
}
KEY_PARAMETERS = tuple(PROVIDERS)
PROVIDER_ENV_VARS = ("FIRECRAWL_API_KEY", "BROWSERBASE_API_KEY", "PARALLEL_API_KEY", "TAVILY_API_KEY")
ENV_KEY = "env-SECRET-must-not-be-used"

PAGE_URL = "https://docs.example.com/guide"
FINAL_URL = "https://docs.example.com/v2/guide"
PAGE_TEXT = "# Guide\n\nInstall the package, create the agent, then call run().\n" + "Guide detail line.\n" * 20
FETCH_ARGUMENTS = {"url": PAGE_URL, "urls": [PAGE_URL]}
# One body every provider client can parse: Firecrawl reads data, Browserbase reads content and url, Parallel and Tavily read results.
PROVIDER_PAGE_BODY = {
    "data": {"markdown": PAGE_TEXT, "metadata": {"sourceURL": FINAL_URL}},
    "content": PAGE_TEXT,
    "url": FINAL_URL,
    "results": [{"url": FINAL_URL, "full_content": PAGE_TEXT, "raw_content": PAGE_TEXT}],
}
OFFLINE_MODEL = {"provider": "openai", "model_name": "gpt-4.1-mini"}


def _secret_key(parameter: str) -> str:
    # A distinctive placeholder, so any echo of it is easy to find.
    return f"{parameter}-SECRET-7f3a91"


def _set_provider_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    # INV-6: the environment offers a different key for every provider; CodingAgent must never use it.
    for name in PROVIDER_ENV_VARS:
        monkeypatch.setenv(name, ENV_KEY)


def _refuse(*args: object, **kwargs: object) -> None:
    raise AssertionError("building a CodingAgent must not open a connection or start a process (INV-18)")


def _forbid_network_and_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    # Any socket connection or process start during construction fails the test immediately.
    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(subprocess, "Popen", _refuse)
    monkeypatch.setattr(os, "system", _refuse)


@pytest.mark.parametrize(
    ("key_parameter", "expected_name"),
    [*((parameter, PROVIDERS[parameter][0]) for parameter in KEY_PARAMETERS), (None, "direct_http_fetch")],
    ids=[*KEY_PARAMETERS, "no-key"],
)
def test_the_supplied_key_picks_the_last_tool_without_network_or_process(coding_agent_cls, tmp_path, monkeypatch, key_parameter, expected_name) -> None:
    # AC-6 / INV-5 / INV-6 / INV-18: one key, or none, decides the seventh tool; provider env vars are ignored.
    _set_provider_env_vars(monkeypatch)
    _forbid_network_and_processes(monkeypatch)
    keys = {} if key_parameter is None else {key_parameter: _secret_key(key_parameter)}

    agent = coding_agent_cls(name="coder", system_prompt="Fetch pages.", root_dir=tmp_path, **keys, **OFFLINE_MODEL)

    assert len(agent.tools.names()) == 7
    assert agent.tools.names()[6] == expected_name


@pytest.mark.parametrize("key_parameter", KEY_PARAMETERS)
@pytest.mark.asyncio
async def test_keyed_fetch_sends_the_parameter_key_to_its_provider_and_shows_the_page(coding_agent_cls, fake_provider_http, tmp_path, monkeypatch, key_parameter) -> None:
    # FR-5 / FR-6 / INV-5 / INV-6 / INV-16: the request carries this parameter's key to this provider, and the model reads the page.
    tool_name, tool_cls, client_cls, api_origin = PROVIDERS[key_parameter]
    sends = fake_provider_http(lambda send: (200, PROVIDER_PAGE_BODY))
    _set_provider_env_vars(monkeypatch)
    key = _secret_key(key_parameter)
    agent = coding_agent_cls(name="coder", system_prompt="Fetch pages.", root_dir=tmp_path, **{key_parameter: key}, **OFFLINE_MODEL)
    view = agent.tools.all()[6]
    bare = tool_cls(client=client_cls(key))
    call = ToolCall(tool_name, FETCH_ARGUMENTS)

    seen = await view.execute(call)
    request = sends[0]
    bare_result = await bare.execute(call)

    # The one outgoing request went to this provider's API, authenticated with the parameter key and never the environment's.
    assert request["url"].startswith(api_origin)
    assert any(key in value for value in request["headers"].values())
    assert ENV_KEY not in repr(sends)
    # The model sees the unchanged provider summary, then the final URL followed by the full page text.
    assert seen.status is ToolStatus.SUCCESS
    assert seen.output.startswith(bare_result.output)
    pages_part = seen.output[len(bare_result.output):]
    assert -1 < pages_part.find(FINAL_URL) < pages_part.find(PAGE_TEXT)
    # Schema, validation target, and billing metadata are the priced tool's own (the runtime prices the unwrapped tool).
    assert isinstance(view.wrapped_tool, tool_cls)
    assert view.spec() == bare.spec()
    assert seen.metadata == bare_result.metadata


@pytest.mark.parametrize("key_parameter", KEY_PARAMETERS)
@pytest.mark.asyncio
async def test_failed_keyed_fetch_passes_through_unchanged_and_never_carries_the_key(coding_agent_cls, fake_provider_http, tmp_path, key_parameter) -> None:
    # INV-16 / EC-3 / AC-23: a rejected key is the bare tool's own failed (and billed) result, with no key in it.
    tool_name, tool_cls, client_cls, _ = PROVIDERS[key_parameter]
    fake_provider_http(lambda send: (401, {"error": "invalid api key"}))
    key = _secret_key(key_parameter)
    agent = coding_agent_cls(name="coder", system_prompt="Fetch pages.", root_dir=tmp_path, **{key_parameter: key}, **OFFLINE_MODEL)
    call = ToolCall(tool_name, FETCH_ARGUMENTS)

    failed = await agent.tools.all()[6].execute(call)
    bare_failed = await tool_cls(client=client_cls(key)).execute(call)

    assert failed.status is ToolStatus.ERROR
    assert failed.metadata["error"] == "fetch_failed"
    assert (failed.output, failed.metadata) == (bare_failed.output, bare_failed.metadata)
    assert key not in repr(failed)


@pytest.mark.parametrize("key_parameter", KEY_PARAMETERS)
def test_key_is_absent_from_exported_state_and_agent_card(coding_agent_cls, tmp_path, key_parameter) -> None:
    # AC-23 / INV-17 / T-3: checkpoints and agent cards travel; the key must stay inside the provider client.
    key = _secret_key(key_parameter)
    agent = coding_agent_cls(name="coder", system_prompt="Fetch pages.", root_dir=tmp_path, **{key_parameter: key}, **OFFLINE_MODEL)

    assert key not in repr(agent.export_state())
    assert key not in repr(agent.card())


@pytest.mark.parametrize("supplied", list(itertools.combinations(KEY_PARAMETERS, 2)), ids=lambda pair: "+".join(pair))
def test_two_fetch_keys_are_rejected_naming_both_parameters_but_neither_key(coding_agent_cls, tmp_path, supplied) -> None:
    # AC-4 / EC-1 / D-3: no hidden precedence that would bill the wrong vendor.
    keys = {parameter: _secret_key(parameter) for parameter in supplied}

    with pytest.raises(ConfigurationError) as caught:
        coding_agent_cls(name="coder", system_prompt="Fetch pages.", root_dir=tmp_path, **keys, **OFFLINE_MODEL)

    reported = f"{caught.value} {caught.value.details!r}"
    for parameter, key in keys.items():
        assert parameter in reported
        assert key not in reported


@pytest.mark.parametrize("key_parameter", KEY_PARAMETERS)
@pytest.mark.parametrize(
    ("bad_key", "echo_marker"),
    [("", None), ("   ", None), ("\t\n", None), (12345, "12345"), (b"bytes-SECRET-7f3a91", "bytes-SECRET-7f3a91")],
    ids=["empty", "spaces", "whitespace", "integer", "bytes"],
)
def test_blank_or_non_string_fetch_key_is_rejected_without_echoing_it(coding_agent_cls, tmp_path, key_parameter, bad_key, echo_marker) -> None:
    # AC-5 / EC-2 / FR-5: an unset environment variable read into a key must fail at construction, not as a 401 on every fetch.
    with pytest.raises(ConfigurationError) as caught:
        coding_agent_cls(name="coder", system_prompt="Fetch pages.", root_dir=tmp_path, **{key_parameter: bad_key}, **OFFLINE_MODEL)

    reported = f"{caught.value} {caught.value.details!r}"
    assert key_parameter in reported
    if echo_marker is not None:
        assert echo_marker not in reported
