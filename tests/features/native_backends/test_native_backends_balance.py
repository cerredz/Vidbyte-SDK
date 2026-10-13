"""FILE: tests/features/native_backends/test_native_backends_balance.py

PURPOSE: The two backend functions that may touch the network: get_deepseek_balance (one GET to the fixed balance URL with a Bearer header, through HttpTransport with BACKEND_HTTP_TIMEOUT_SECONDS) and check_backend_ready (GLM checks the key only; DeepSeek also reads the balance). Covers the success shapes, D-17's no-spend rule, INV-3's deadline and INV-2's cancellation.
ROLE IN CODEBASE: Start here when a readiness check spends money, reaches the wrong host, hangs, or parses a balance wrongly. Covers HarnessBackends.get_deepseek_balance and HarnessBackends.check_backend_ready.
ARCHITECTURE NOTE: The autouse FakeDeepseekEndpoint (conftest.py) answers through httpx.MockTransport and records each request and the options of each AsyncClient HttpTransport built, so the timeout is read from the real client construction, not from a mock of HttpTransport.
FUNCTION INVENTORY: The test_* functions each pin one promise; the error rows for these functions live in test_native_backends_errors.py.
COMMON MODIFICATION PATTERNS: A new balance field is one more key in the conftest's HEALTHY_BALANCE and one more assertion in test_balance_parses_every_entry_as_decimals.
WHAT NOT TO DO IN THIS FILE: 1. Do not let a test reach the real api.deepseek.com; the endpoint fixture is autouse for that reason. 2. Do not compare decimals through float; the spec parses the vendor's strings as Decimal.
KNOWN EDGE CASES: The held request never answers, so the cancellation test cancels it once the endpoint has received it.
RELATED DOCS: tests/features/native_backends/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.6, D-17, INV-2, INV-3
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/native_backends/test_native_backends_balance.py
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

BALANCE_URL = "https://api.deepseek.com/user/balance"
RECEIVED_WITHIN_SECONDS = 10.0


def timeout_of(options: dict) -> object:
    timeout = options.get("timeout")
    return getattr(timeout, "read", timeout)


@pytest.mark.asyncio
async def test_balance_is_one_bearer_get_to_the_fixed_url(backends_api, deepseek_endpoint, backend_keys) -> None:
    # §6.3.6: GET https://api.deepseek.com/user/balance with the key as a Bearer header, never in the URL.
    await backends_api.get_deepseek_balance()
    assert len(deepseek_endpoint.requests) == 1
    sent = deepseek_endpoint.requests[0]
    assert sent.method == "GET"
    assert str(sent.url) == BALANCE_URL
    assert sent.headers["authorization"] == f"Bearer {backend_keys.deepseek}"
    assert backend_keys.deepseek not in str(sent.url)
    assert backend_keys.glm not in str(sent.headers), "only the DeepSeek key goes to DeepSeek"


@pytest.mark.asyncio
async def test_balance_call_uses_the_backend_http_deadline(backends_api, deepseek_endpoint, backend_keys) -> None:
    # INV-3 / NFR-1: the call goes through HttpTransport with BACKEND_HTTP_TIMEOUT_SECONDS (15 s).
    await backends_api.get_deepseek_balance()
    assert deepseek_endpoint.client_options, "HttpTransport built no httpx.AsyncClient"
    assert backends_api.constants.BACKEND_HTTP_TIMEOUT_SECONDS == 15.0
    assert all(timeout_of(options) == 15.0 for options in deepseek_endpoint.client_options), deepseek_endpoint.client_options


@pytest.mark.asyncio
async def test_balance_parses_every_entry_as_decimals(backends_api, backend_keys) -> None:
    # §9.1: DeepseekBalance with one DeepseekBalanceEntry per balance_infos item, decimals parsed from the strings.
    balance = await backends_api.get_deepseek_balance()
    assert isinstance(balance, backends_api.DeepseekBalance)
    assert balance.is_available is True
    assert isinstance(balance.balances, tuple)
    assert [entry.currency for entry in balance.balances] == ["CNY", "USD"]
    first = balance.balances[0]
    assert isinstance(first, backends_api.DeepseekBalanceEntry)
    assert (first.total_balance, first.granted_balance, first.topped_up_balance) == (Decimal("110.00"), Decimal("10.00"), Decimal("100.00"))
    assert all(isinstance(value, Decimal) for entry in balance.balances for value in (entry.total_balance, entry.granted_balance, entry.topped_up_balance))
    assert str(balance.balances[1].total_balance) == "5.50", "the vendor's string is kept exactly, not rounded through float"


@pytest.mark.asyncio
async def test_balance_with_no_usable_funds_is_returned_not_raised(backends_api, deepseek_endpoint, backend_keys) -> None:
    # EC-133 is a check_backend_ready row only: get_deepseek_balance reports is_available=False as data.
    deepseek_endpoint.answer_json({"is_available": False, "balance_infos": []})
    balance = await backends_api.get_deepseek_balance()
    assert balance.is_available is False
    assert balance.balances == ()


@pytest.mark.asyncio
async def test_balance_needs_only_the_deepseek_key(backends_api, deepseek_endpoint, monkeypatch: pytest.MonkeyPatch) -> None:
    # The GLM key is irrelevant to the balance call: DeepSeek's key alone is enough.
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-deepseek-value-not-a-key-0002")
    balance = await backends_api.get_deepseek_balance()
    assert balance.is_available is True
    assert len(deepseek_endpoint.requests) == 1


@pytest.mark.asyncio
async def test_glm_readiness_checks_the_key_and_makes_no_remote_call(backends_api, deepseek_endpoint, monkeypatch: pytest.MonkeyPatch) -> None:
    # D-17: GLM makes no remote call and returns remote_verified=False, which is not an error.
    monkeypatch.setenv("GLM_API_KEY", "fake-glm-value-not-a-key-0001")
    readiness = await backends_api.check_backend_ready(backends_api.HarnessBackendName.GLM)
    assert isinstance(readiness, backends_api.BackendReadiness)
    assert readiness.backend is backends_api.HarnessBackendName.GLM
    assert readiness.remote_verified is False
    assert readiness.balance is None
    assert deepseek_endpoint.requests == [] and deepseek_endpoint.client_options == []


@pytest.mark.asyncio
async def test_deepseek_readiness_verifies_the_key_through_the_balance(backends_api, deepseek_endpoint, monkeypatch: pytest.MonkeyPatch) -> None:
    # D-17: DeepSeek readiness reads GET /user/balance (never a spending call) and reports the balance.
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-deepseek-value-not-a-key-0002")
    readiness = await backends_api.check_backend_ready("deepseek")
    assert readiness.backend is backends_api.HarnessBackendName.DEEPSEEK
    assert readiness.remote_verified is True
    assert isinstance(readiness.balance, backends_api.DeepseekBalance)
    assert readiness.balance.is_available is True
    assert [(item.method, str(item.url)) for item in deepseek_endpoint.requests] == [("GET", BALANCE_URL)], "NG-6: no other call, nothing that spends"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["get_deepseek_balance", "check_backend_ready"])
async def test_cancelling_a_balance_call_propagates(operation: str, backends_api, deepseek_endpoint, backend_keys) -> None:
    # INV-2 / EC-4: CancelledError is never swallowed or turned into a NativeHostError.
    deepseek_endpoint.hold_forever()
    calls = {
        "get_deepseek_balance": lambda: backends_api.get_deepseek_balance(),
        "check_backend_ready": lambda: backends_api.check_backend_ready(backends_api.HarnessBackendName.DEEPSEEK),
    }
    task = asyncio.create_task(calls[operation]())
    await asyncio.wait_for(deepseek_endpoint.received.wait(), timeout=RECEIVED_WITHIN_SECONDS)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
