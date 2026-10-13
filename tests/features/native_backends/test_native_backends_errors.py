"""FILE: tests/features/native_backends/test_native_backends_errors.py

PURPOSE: The backend-profile error contract as one table: each case is a (function, code) row of spec §6.3.6 reproduced through the fake DeepSeek endpoint and the key variables, asserting the exact FailureCode member, a non-empty next_step that holds the row's required token, and the matching tool's error result (AC-2, EC-147).
ROLE IN CODEBASE: Proves FR-6, FR-7, FR-21 and INV-1/INV-5/INV-8 for the six functions of vidbyte.harnesses.native.backends and the two backend tools that take input (vidbyte.tools.builtins.harness_backends).
ARCHITECTURE NOTE: ROWS is data; CALLS maps a row to the call that reproduces it, and ENDPOINTS to the fake endpoint's answer. RowContext.invoke drives either the function or the matching tool, so a row with a tool runs twice: "host" asserts the raised NativeHostError, "tool" asserts the ToolResult.error built from it (INV-7). Sync functions are called directly and async ones awaited.
FUNCTION INVENTORY: Row describes one case; RowContext runs a call as function or tool; call_* reproduce the triggers; ENDPOINTS configures FakeDeepseekEndpoint; test_backend_error_row runs the table and checks the endpoint saw only what the row allows.
COMMON MODIFICATION PATTERNS: A new §6.3.6 row is one Row entry; add a call_* function only when no existing one reproduces its trigger. Keep one case per (function, code); a distinct trigger the spec lists (EC-132's shapes) is a named variant.
WHAT NOT TO DO IN THIS FILE: 1. Do not assert message wording beyond the names the spec fixes. 2. Do not loosen exact_next_step to a token check: the default not_signed_in text names both variables, so only the exact override proves the backend's own variable came first.
KNOWN EDGE CASES: EC-126 and EC-137 cannot be reached with the declared profiles (both allow CLAUDE_CODE and OPENCODE), and the harness-before-features order of check_backend_compat has no profile that shows it; both are listed as not written in the test plan.
RELATED DOCS: tests/features/native_backends/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.1, §6.3.6, §6.3.7, §9.2
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/native_backends/test_native_backends_errors.py
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

BALANCE_URL = "https://api.deepseek.com/user/balance"
REDIRECT_TARGET = "https://login.example.invalid/next"
FAKE_GLM_VALUE = "fake-glm-value-not-a-key-0001"
FAKE_DEEPSEEK_VALUE = "fake-deepseek-value-not-a-key-0002"
UNKNOWN_BACKEND = "kimi"
GLM_TEXT = "Set GLM_API_KEY in the environment to a valid key."
DEEPSEEK_TEXT = "Set DEEPSEEK_API_KEY in the environment to a valid key."
REJECTED_TEXT = "DeepSeek rejected DEEPSEEK_API_KEY; set a valid key."
ENTRY = {"currency": "CNY", "total_balance": "110.00", "granted_balance": "10.00", "topped_up_balance": "100.00"}


@dataclass(frozen=True)
class Row:
    """One (function, code) row of the §6.3.6 error table."""

    ec: str
    operation: str
    code: str
    token: str
    call: str = ""
    variant: str = ""
    keys: str = "both"
    endpoint: str = "healthy"
    exact_next_step: str | None = None
    default_next_step: bool = False
    message_names: tuple[str, ...] = ()
    context: Mapping[str, str] = field(default_factory=dict)
    context_keys: tuple[str, ...] = ()
    context_mentions: tuple[str, ...] = ()
    http: bool = False
    tool: bool = False


@dataclass
class RowContext:
    """Runs a row's call against the backend function, or against the matching tool."""

    api: SimpleNamespace
    tools_api: SimpleNamespace | None = None

    async def invoke(self, tool_name: str, tool_args: Mapping[str, Any], direct: Callable[[], Any]) -> Any:
        if self.tools_api is None:
            outcome = direct()
            return await outcome if inspect.isawaitable(outcome) else outcome
        tool = {tool.name: tool for tool in self.tools_api.HarnessBackendTools().all()}[tool_name]
        return await tool.execute(self.tools_api.ToolCall(tool_name, dict(tool_args)))


def compat_request(api: SimpleNamespace, harness: str, *features: str) -> Any:
    return api.BackendCompatRequest(harness=api.NativeHarness[harness], features=frozenset(api.BackendFeature[name] for name in features))


async def call_env_unknown(ctx: RowContext) -> Any:
    return await ctx.invoke("", {}, lambda: ctx.api.build_claude_backend_env(UNKNOWN_BACKEND))


async def call_env_wrong_type(ctx: RowContext) -> Any:
    return await ctx.invoke("", {}, lambda: ctx.api.build_claude_backend_env(7))


async def call_env_glm(ctx: RowContext) -> Any:
    return await ctx.invoke("", {}, lambda: ctx.api.build_claude_backend_env(ctx.api.HarnessBackendName.GLM))


async def call_env_deepseek(ctx: RowContext) -> Any:
    return await ctx.invoke("", {}, lambda: ctx.api.build_claude_backend_env(ctx.api.HarnessBackendName.DEEPSEEK))


async def call_env_empty_model(ctx: RowContext) -> Any:
    return await ctx.invoke("", {}, lambda: ctx.api.build_claude_backend_env(ctx.api.HarnessBackendName.GLM, model=""))


async def call_env_long_model(ctx: RowContext) -> Any:
    return await ctx.invoke("", {}, lambda: ctx.api.build_claude_backend_env(ctx.api.HarnessBackendName.GLM, model="m" * 129))


async def call_env_other_backends_model(ctx: RowContext) -> Any:
    # A DeepSeek model asked of GLM: a check against the union of all profiles would wrongly pass.
    return await ctx.invoke("", {}, lambda: ctx.api.build_claude_backend_env(ctx.api.HarnessBackendName.GLM, model="deepseek-flash[1m]"))


async def call_ready_unknown(ctx: RowContext) -> Any:
    return await ctx.invoke("check_backend_ready", {"backend": UNKNOWN_BACKEND}, lambda: ctx.api.check_backend_ready(UNKNOWN_BACKEND))


async def call_ready_glm(ctx: RowContext) -> Any:
    return await ctx.invoke("check_backend_ready", {"backend": "glm"}, lambda: ctx.api.check_backend_ready(ctx.api.HarnessBackendName.GLM))


async def call_ready_deepseek(ctx: RowContext) -> Any:
    return await ctx.invoke("check_backend_ready", {"backend": "deepseek"}, lambda: ctx.api.check_backend_ready(ctx.api.HarnessBackendName.DEEPSEEK))


async def call_balance(ctx: RowContext) -> Any:
    return await ctx.invoke("get_deepseek_balance", {}, lambda: ctx.api.get_deepseek_balance())


async def call_compat_unknown(ctx: RowContext) -> Any:
    request = compat_request(ctx.api, "CLAUDE_CODE")
    return await ctx.invoke("", {}, lambda: ctx.api.check_backend_compat(UNKNOWN_BACKEND, request))


async def call_compat_glm_grok(ctx: RowContext) -> Any:
    request = compat_request(ctx.api, "GROK")
    return await ctx.invoke("", {}, lambda: ctx.api.check_backend_compat(ctx.api.HarnessBackendName.GLM, request))


async def call_compat_glm_muse(ctx: RowContext) -> Any:
    request = compat_request(ctx.api, "MUSE")
    return await ctx.invoke("", {}, lambda: ctx.api.check_backend_compat(ctx.api.HarnessBackendName.GLM, request))


async def call_compat_deepseek_mcp(ctx: RowContext) -> Any:
    request = compat_request(ctx.api, "CLAUDE_CODE", "MCP_SERVERS")
    return await ctx.invoke("", {}, lambda: ctx.api.check_backend_compat(ctx.api.HarnessBackendName.DEEPSEEK, request))


async def call_provider_unknown(ctx: RowContext) -> Any:
    return await ctx.invoke("", {}, lambda: ctx.api.build_opencode_backend_provider(UNKNOWN_BACKEND))


CALLS: dict[str, Callable[[RowContext], Awaitable[Any]]] = {
    "env_unknown": call_env_unknown,
    "env_wrong_type": call_env_wrong_type,
    "env_glm": call_env_glm,
    "env_deepseek": call_env_deepseek,
    "env_empty_model": call_env_empty_model,
    "env_long_model": call_env_long_model,
    "env_other_backends_model": call_env_other_backends_model,
    "ready_unknown": call_ready_unknown,
    "ready_glm": call_ready_glm,
    "ready_deepseek": call_ready_deepseek,
    "balance": call_balance,
    "compat_unknown": call_compat_unknown,
    "compat_glm_grok": call_compat_glm_grok,
    "compat_glm_muse": call_compat_glm_muse,
    "compat_deepseek_mcp": call_compat_deepseek_mcp,
    "provider_unknown": call_provider_unknown,
}


def balance_with(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"is_available": True, "balance_infos": [dict(ENTRY)]}
    body.update(changes)
    return body


def entry_with(**changes: Any) -> dict[str, Any]:
    entry = dict(ENTRY)
    for key, value in changes.items():
        if value is None:
            entry.pop(key)
        else:
            entry[key] = value
    return balance_with(balance_infos=[entry])


def configure_endpoint(endpoint: Any, name: str) -> None:
    # One named answer per trigger; "healthy" keeps the conftest default.
    statuses = {"status_401": 401, "status_403": 403, "status_402": 402, "status_429": 429, "status_500": 500}
    shapes = {
        "not_object": [ENTRY],
        "missing_is_available": {"balance_infos": [dict(ENTRY)]},
        "is_available_text": balance_with(is_available="true"),
        "balance_infos_not_list": balance_with(balance_infos=dict(ENTRY)),
        "entry_not_object": balance_with(balance_infos=["CNY 110.00"]),
        "entry_missing_currency": entry_with(currency=None),
        "decimal_number": entry_with(total_balance=110.0),
        "decimal_garbage": entry_with(granted_balance="ten yuan"),
        "unavailable": balance_with(is_available=False),
        "oversize": balance_with(padding="x" * 70000),
    }
    if name in statuses:
        endpoint.answer_json({"error": {"message": "vendor refused the request", "type": "vendor_error"}}, status=statuses[name])
    elif name in shapes:
        endpoint.answer_json(shapes[name])
    elif name == "redirect_302":
        endpoint.answer_text("", status=302, headers={"location": REDIRECT_TARGET})
    elif name == "not_json":
        endpoint.answer_text("<html>maintenance</html>", headers={"content-type": "text/html"})
    elif name == "empty_204":
        endpoint.answer_text("", status=204)
    elif name == "connect_error":
        endpoint.fail_with(httpx.ConnectError("connection refused"))
    elif name == "read_timeout":
        endpoint.fail_with(httpx.ReadTimeout("read timed out"))
    else:
        assert name == "healthy", f"unknown endpoint preset {name}"


IA = "configuration.invalid_argument"
NS = "backend.not_signed_in"
MU = "backend.model_unknown"
FU = "backend.feature_unsupported"
HN = "backend.harness_not_allowed"
BE = "backend.billing_error"
UL = "backend.usage_limited"
AE = "backend.api_error"
SU = "backend.server_unreachable"
PM = "backend.protocol_mismatch"
ENV = "build_claude_backend_env"
READY = "check_backend_ready"
BALANCE = "get_deepseek_balance"
COMPAT = "check_backend_compat"
PROVIDER = "build_opencode_backend_provider"
EC132_SHAPES = (
    "not_json", "empty_204", "not_object", "missing_is_available", "is_available_text", "balance_infos_not_list",
    "entry_not_object", "entry_missing_currency", "decimal_number", "decimal_garbage", "oversize",
)

ROWS: tuple[Row, ...] = (
    # build_claude_backend_env: EC-122, EC-123, EC-124, EC-125 (EC-126 is unreachable with the declared profiles).
    Row("EC-122", ENV, IA, "backend", call="env_unknown", variant="unknown_name", message_names=("backend",)),
    Row("EC-122", ENV, IA, "backend", call="env_wrong_type", variant="wrong_type", message_names=("backend",)),
    Row("EC-123", ENV, NS, "GLM_API_KEY", call="env_glm", variant="glm_unset", keys="none", exact_next_step=GLM_TEXT, message_names=("GLM_API_KEY",)),
    Row("EC-123", ENV, NS, "DEEPSEEK_API_KEY", call="env_deepseek", variant="deepseek_unset", keys="none", exact_next_step=DEEPSEEK_TEXT, message_names=("DEEPSEEK_API_KEY",)),
    Row("EC-123", ENV, NS, "DEEPSEEK_API_KEY", call="env_deepseek", variant="deepseek_blank", keys="blank", exact_next_step=DEEPSEEK_TEXT),
    Row("EC-124", ENV, IA, "model", call="env_empty_model", variant="empty", message_names=("model",)),
    Row("EC-124", ENV, IA, "model", call="env_long_model", variant="too_long", message_names=("model",)),
    Row("EC-125", ENV, MU, "list_harness_backends", call="env_other_backends_model", default_next_step=True, context_mentions=("glm-5.3[1m]", "glm-5.3-flash[1m]")),
    # check_backend_ready: EC-122, EC-123, EC-133, and the balance rows EC-127 to EC-132 for DeepSeek.
    Row("EC-122", READY, IA, "backend", call="ready_unknown", message_names=("backend",), tool=True),
    Row("EC-123", READY, NS, "GLM_API_KEY", call="ready_glm", variant="glm_unset", keys="none", exact_next_step=GLM_TEXT, tool=True),
    Row("EC-123", READY, NS, "DEEPSEEK_API_KEY", call="ready_deepseek", variant="deepseek_unset", keys="none", exact_next_step=DEEPSEEK_TEXT, tool=True),
    Row("EC-127", READY, NS, "DEEPSEEK_API_KEY", call="ready_deepseek", variant="rejected_401", endpoint="status_401", exact_next_step=REJECTED_TEXT, http=True, tool=True),
    Row("EC-129", READY, UL, "reset", call="ready_deepseek", endpoint="status_429", default_next_step=True, http=True, tool=True),
    Row("EC-130", READY, AE, "vendor_error", call="ready_deepseek", endpoint="status_500", default_next_step=True, context={"status_code": "500"}, context_keys=("vendor_error",), http=True, tool=True),
    Row("EC-131", READY, SU, "network", call="ready_deepseek", endpoint="connect_error", default_next_step=True, http=True, tool=True),
    Row("EC-132", READY, PM, "API status", call="ready_deepseek", endpoint="not_json", default_next_step=True, http=True, tool=True),
    Row("EC-133", READY, BE, "balance", call="ready_deepseek", endpoint="unavailable", default_next_step=True, context_mentions=("CNY",), http=True, tool=True),
    # get_deepseek_balance: EC-123, EC-127 to EC-132.
    Row("EC-123", BALANCE, NS, "DEEPSEEK_API_KEY", call="balance", variant="unset", keys="none", exact_next_step=DEEPSEEK_TEXT, message_names=("DEEPSEEK_API_KEY",), tool=True),
    Row("EC-123", BALANCE, NS, "DEEPSEEK_API_KEY", call="balance", variant="blank", keys="blank", exact_next_step=DEEPSEEK_TEXT, tool=True),
    Row("EC-127", BALANCE, NS, "DEEPSEEK_API_KEY", call="balance", variant="rejected_401", endpoint="status_401", exact_next_step=REJECTED_TEXT, http=True, tool=True),
    Row("EC-127", BALANCE, NS, "DEEPSEEK_API_KEY", call="balance", variant="rejected_403", endpoint="status_403", exact_next_step=REJECTED_TEXT, http=True, tool=True),
    Row("EC-128", BALANCE, BE, "balance", call="balance", endpoint="status_402", default_next_step=True, http=True, tool=True),
    Row("EC-129", BALANCE, UL, "reset", call="balance", endpoint="status_429", default_next_step=True, http=True, tool=True),
    Row("EC-130", BALANCE, AE, "vendor_error", call="balance", variant="status_500", endpoint="status_500", default_next_step=True, context={"status_code": "500"}, context_keys=("vendor_error",), http=True, tool=True),
    Row("EC-130", BALANCE, AE, "vendor_error", call="balance", variant="redirect_not_followed", endpoint="redirect_302", default_next_step=True, context={"status_code": "302"}, http=True, tool=True),
    Row("EC-131", BALANCE, SU, "network", call="balance", variant="connect_error", endpoint="connect_error", default_next_step=True, http=True, tool=True),
    Row("EC-131", BALANCE, SU, "network", call="balance", variant="read_timeout", endpoint="read_timeout", default_next_step=True, http=True, tool=True),
    *(Row("EC-132", BALANCE, PM, "API status", call="balance", variant=shape, endpoint=shape, default_next_step=True, http=True, tool=shape == "not_json") for shape in EC132_SHAPES),
    # check_backend_compat: EC-122, EC-135, EC-136 (EC-134 is a record row, in test_native_backends_records.py).
    Row("EC-122", COMPAT, IA, "backend", call="compat_unknown", message_names=("backend",)),
    Row("EC-135", COMPAT, HN, "allowed_harnesses", call="compat_glm_grok", variant="glm_grok", keys="none", default_next_step=True),
    Row("EC-135", COMPAT, HN, "allowed_harnesses", call="compat_glm_muse", variant="glm_muse", keys="none", default_next_step=True),
    Row("EC-136", COMPAT, FU, "features", call="compat_deepseek_mcp", keys="none", default_next_step=True, context={"features": "mcp_servers"}),
    # build_opencode_backend_provider: EC-122 (EC-137 is unreachable with the declared profiles).
    Row("EC-122", PROVIDER, IA, "backend", call="provider_unknown", message_names=("backend",)),
)


def row_id(row: Row) -> str:
    suffix = f"-{row.variant}" if row.variant else ""
    return f"{row.ec}-{row.operation}-{row.code}{suffix}"


CASES = [pytest.param(row, "host", id=f"{row_id(row)}-host") for row in ROWS] + [
    pytest.param(row, "tool", id=f"{row_id(row)}-tool") for row in ROWS if row.tool
]


def set_keys(monkeypatch: pytest.MonkeyPatch, keys: str) -> None:
    # "both" sets fake values for both backends, "none" leaves them unset, "blank" makes them whitespace only.
    if keys == "both":
        monkeypatch.setenv("GLM_API_KEY", FAKE_GLM_VALUE)
        monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_DEEPSEEK_VALUE)
    elif keys == "blank":
        monkeypatch.setenv("GLM_API_KEY", "   ")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "   ")
    else:
        assert keys == "none"


def shown_text(subject: Any) -> str:
    # Everything a row exposes to a caller or a model, as one string for the secret check (INV-6).
    if hasattr(subject, "failure_code"):
        return " ".join([str(subject), subject.next_step, json.dumps(dict(subject.context), sort_keys=True)])
    return " ".join([subject.output, json.dumps(dict(subject.metadata), sort_keys=True, default=str)])


@pytest.mark.asyncio
@pytest.mark.parametrize(("row", "mode"), CASES)
async def test_backend_error_row(row: Row, mode: str, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, backends_api, deepseek_endpoint, check_native_error) -> None:
    set_keys(monkeypatch, row.keys)
    configure_endpoint(deepseek_endpoint, row.endpoint)
    call = CALLS[row.call]
    if mode == "host":
        with pytest.raises(backends_api.NativeHostError) as caught:
            await call(RowContext(backends_api))
        error = caught.value
        check_native_error(error, code=row.code, token=row.token, operation=row.operation)
        if row.exact_next_step is not None:
            assert error.next_step == row.exact_next_step
        if row.default_next_step:
            assert error.next_step == backends_api.constants.NATIVE_HOST_NEXT_STEPS[row.code], "the row's *default* next step"
        for name in row.message_names:
            assert name in str(error), f"the message names {name!r}: {error}"
        for key, value in row.context.items():
            assert error.context.get(key) == value, f"context[{key!r}] should be {value!r}: {dict(error.context)}"
        for key in row.context_keys:
            assert error.context.get(key), f"context should carry {key!r}: {dict(error.context)}"
        for value in row.context_mentions:
            assert any(value in text for text in error.context.values()), f"context should mention {value!r}: {dict(error.context)}"
        exposed = shown_text(error)
    else:
        tools_api = request.getfixturevalue("backend_tools_api")
        result = await call(RowContext(backends_api, tools_api))
        request.getfixturevalue("check_tool_error")(result, code=row.code, token=row.token, tool_name=row.operation)
        if row.exact_next_step is not None:
            assert result.metadata["next_step"] == row.exact_next_step
        exposed = shown_text(result)
    assert FAKE_GLM_VALUE not in exposed and FAKE_DEEPSEEK_VALUE not in exposed, "INV-6: no key value reaches an error or a tool result"
    assert_endpoint_saw(row, deepseek_endpoint)


def assert_endpoint_saw(row: Row, endpoint: Any) -> None:
    # INV-5: argument and key checks make no request; a balance call is one GET to the fixed URL, redirects not followed.
    if not row.http:
        assert endpoint.requests == [], f"{row.ec} must fail before any HTTP request; sent {[str(item.url) for item in endpoint.requests]}"
        return
    assert endpoint.requests, f"{row.ec} is reproduced by the endpoint's answer, so a request was expected"
    assert all(item.method == "GET" and str(item.url) == BALANCE_URL for item in endpoint.requests), [f"{item.method} {item.url}" for item in endpoint.requests]
