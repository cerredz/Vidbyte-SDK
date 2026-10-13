"""FILE: tests/features/native_backends/test_native_backends_security.py

PURPOSE: The secret rules for the backend profiles: a DeepSeek answer that echoes the exact injected key comes out as <redacted> in the error and never in its message, context, next step, tool output or metadata (AC-5, INV-6); raw exception text from the HTTP layer is never surfaced (T-3); vendor text is capped (INV-6); and no record's repr shows a key.
ROLE IN CODEBASE: Start here for a key leak from vidbyte.harnesses.native.backends or the backend tools. The scrub itself is NativeErrorFactory's; these tests prove the backend registers the key it injected and routes every vendor text through it.
ARCHITECTURE NOTE: The echoed key is placed in free text, not in a "key=value" assignment, so HarnessRedactor's own assignment pattern cannot hide it: only the replacement of the registered injected value can. The fake values are not keys.
FUNCTION INVENTORY: leak_report gathers everything a caller or a model is shown; the test_* functions each pin one leak path.
COMMON MODIFICATION PATTERNS: A new surface that shows vendor text adds one test here that echoes FAKE_DEEPSEEK_VALUE through it.
WHAT NOT TO DO IN THIS FILE: 1. Do not put the echoed key in an assignment form ("api_key=..."); that would pass through the generic redactor and prove nothing about the injected-value replacement. 2. Do not use a real key.
KNOWN EDGE CASES: AC-5 says the message, context, tool output and metadata "contain <redacted>", but EC-130 puts the vendor text only in context["vendor_error"]; these tests require <redacted> there and the key's absence everywhere (see the test plan's spec notes).
RELATED DOCS: tests/features/native_backends/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md AC-5, INV-6, §10 T-3
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/native_backends/test_native_backends_security.py
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

FAKE_DEEPSEEK_VALUE = "fake-deepseek-value-not-a-key-0002"
ECHO = f"The credential {FAKE_DEEPSEEK_VALUE} has no access to this resource."


def leak_report(subject: Any) -> str:
    # Everything a caller (error) or a model (tool result) sees, as one string.
    if hasattr(subject, "failure_code"):
        return " | ".join([str(subject), repr(subject), subject.next_step, json.dumps(dict(subject.context), sort_keys=True)])
    return " | ".join([subject.output, json.dumps(dict(subject.metadata), sort_keys=True, default=str)])


@pytest.mark.asyncio
async def test_error_body_echoing_the_key_is_redacted_in_the_error(backends_api, deepseek_endpoint, monkeypatch: pytest.MonkeyPatch, check_native_error) -> None:
    # AC-5 / EC-130: the injected key, echoed in a 500 body, becomes <redacted> in vendor_error and appears nowhere.
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_DEEPSEEK_VALUE)
    deepseek_endpoint.answer_json({"error": {"message": ECHO, "type": "invalid_request_error"}}, status=500)
    with pytest.raises(backends_api.NativeHostError) as caught:
        await backends_api.get_deepseek_balance()
    check_native_error(caught.value, code="backend.api_error", token="vendor_error", operation="get_deepseek_balance")
    assert "<redacted>" in caught.value.context["vendor_error"]
    assert FAKE_DEEPSEEK_VALUE not in leak_report(caught.value)


@pytest.mark.asyncio
async def test_error_body_echoing_the_key_is_redacted_in_the_tool_result(backend_tool, backend_tools_api, deepseek_endpoint, monkeypatch: pytest.MonkeyPatch, check_tool_error) -> None:
    # AC-5 / INV-7: the tool result built from that error carries no key either.
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_DEEPSEEK_VALUE)
    deepseek_endpoint.answer_json({"error": {"message": ECHO, "type": "invalid_request_error"}}, status=500)
    result = await backend_tool("get_deepseek_balance").execute(backend_tools_api.ToolCall("get_deepseek_balance", {}))
    check_tool_error(result, code="backend.api_error", token="vendor_error", tool_name="get_deepseek_balance")
    assert FAKE_DEEPSEEK_VALUE not in leak_report(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "code"), [(401, "backend.not_signed_in"), (402, "backend.billing_error"), (429, "backend.usage_limited")])
async def test_classified_statuses_never_echo_the_key(status: int, code: str, backends_api, deepseek_endpoint, monkeypatch: pytest.MonkeyPatch) -> None:
    # INV-6: the classified rows (EC-127 to EC-129) carry no key, whatever the body says.
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_DEEPSEEK_VALUE)
    deepseek_endpoint.answer_text(ECHO, status=status)
    with pytest.raises(backends_api.NativeHostError) as caught:
        await backends_api.check_backend_ready(backends_api.HarnessBackendName.DEEPSEEK)
    assert caught.value.failure_code.value == code
    assert FAKE_DEEPSEEK_VALUE not in leak_report(caught.value)


@pytest.mark.asyncio
async def test_unparseable_body_echoing_the_key_is_not_surfaced(backends_api, deepseek_endpoint, monkeypatch: pytest.MonkeyPatch) -> None:
    # EC-132 / INV-6: a 200 body that is not JSON but contains the key yields protocol_mismatch without the key.
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_DEEPSEEK_VALUE)
    deepseek_endpoint.answer_text(ECHO)
    with pytest.raises(backends_api.NativeHostError) as caught:
        await backends_api.get_deepseek_balance()
    assert caught.value.failure_code is backends_api.FailureCode.BACKEND_PROTOCOL_MISMATCH
    assert FAKE_DEEPSEEK_VALUE not in leak_report(caught.value)


@pytest.mark.asyncio
async def test_transport_exception_text_is_never_surfaced(backends_api, deepseek_endpoint, monkeypatch: pytest.MonkeyPatch) -> None:
    # §10 T-3 / EC-131: ProviderRequestError.response_excerpt (here the httpx text, holding the key) is never shown.
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_DEEPSEEK_VALUE)
    deepseek_endpoint.fail_with(httpx.ConnectError(f"proxy refused Bearer {FAKE_DEEPSEEK_VALUE} marker-7731"))
    with pytest.raises(backends_api.NativeHostError) as caught:
        await backends_api.get_deepseek_balance()
    assert caught.value.failure_code is backends_api.FailureCode.BACKEND_SERVER_UNREACHABLE
    report = leak_report(caught.value)
    assert FAKE_DEEPSEEK_VALUE not in report
    assert "marker-7731" not in report, "the raw exception text must not reach the error at all"


@pytest.mark.asyncio
async def test_vendor_text_in_the_error_is_capped(backends_api, deepseek_endpoint, monkeypatch: pytest.MonkeyPatch) -> None:
    # INV-6: surfaced vendor text is capped at NATIVE_VENDOR_MESSAGE_MAX_CHARS characters.
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_DEEPSEEK_VALUE)
    deepseek_endpoint.answer_json({"error": {"message": "overloaded " * 900}}, status=503)
    with pytest.raises(backends_api.NativeHostError) as caught:
        await backends_api.get_deepseek_balance()
    limit = backends_api.constants.NATIVE_VENDOR_MESSAGE_MAX_CHARS
    assert caught.value.failure_code is backends_api.FailureCode.BACKEND_API_ERROR
    assert all(len(value) <= limit for value in caught.value.context.values()), {key: len(value) for key, value in caught.value.context.items()}
    assert len(str(caught.value)) <= limit + len(caught.value.next_step) + 200, "the message carries at most the capped vendor text"


def test_missing_key_error_names_the_variable_and_no_other_key(backends_api, monkeypatch: pytest.MonkeyPatch) -> None:
    # EC-123: the message names the variable and never a value; the other backend's key stays out of it.
    monkeypatch.setenv("GLM_API_KEY", "fake-glm-value-not-a-key-0001")
    with pytest.raises(backends_api.NativeHostError) as caught:
        backends_api.build_claude_backend_env(backends_api.HarnessBackendName.DEEPSEEK)
    assert "DEEPSEEK_API_KEY" in str(caught.value)
    assert "fake-glm-value-not-a-key-0001" not in leak_report(caught.value)


def test_no_backend_record_repr_shows_a_key(backends_api, monkeypatch: pytest.MonkeyPatch) -> None:
    # INV-6: secret fields are repr=False; the profiles and provider records hold names only.
    monkeypatch.setenv("GLM_API_KEY", "fake-glm-value-not-a-key-0001")
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_DEEPSEEK_VALUE)
    shown = [
        repr(backends_api.build_claude_backend_env(backends_api.HarnessBackendName.GLM)),
        repr(backends_api.build_claude_backend_env(backends_api.HarnessBackendName.DEEPSEEK)),
        repr(backends_api.list_harness_backends()),
        repr(backends_api.build_opencode_backend_provider(backends_api.HarnessBackendName.GLM)),
        repr(backends_api.build_opencode_backend_provider(backends_api.HarnessBackendName.DEEPSEEK)),
    ]
    joined = " ".join(shown)
    assert "fake-glm-value-not-a-key-0001" not in joined and FAKE_DEEPSEEK_VALUE not in joined
