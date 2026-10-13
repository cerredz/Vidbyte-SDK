"""FILE: tests/features/native_backends/conftest.py

PURPOSE: Shared offline fixtures for the native_backends feature pack: the lazy imports of the backend functions, records, enums and tools, a recording fake DeepSeek endpoint behind httpx.MockTransport, isolated key variables, and the error-shape checks every row test uses.
ROLE IN CODEBASE: Loaded by pytest for every module in tests/features/native_backends/. The fake endpoint replaces only the network under HttpTransport, the spec §13 seam: httpx.AsyncClient is patched with a factory over the real class, so HttpTransport and the backend code run unmodified.
ARCHITECTURE NOTE: Every vidbyte import happens inside a fixture, so a missing module, record or constant fails each test at setup instead of aborting collection. The fake endpoint is autouse: no test in this pack can reach the network, and a test that must make no call asserts the endpoint's request log stays empty.
FUNCTION INVENTORY: FakeDeepseekEndpoint answers and records each request; deepseek_endpoint installs it for every test; isolated_backend_keys removes the real key variables; backend_keys sets fake ones; backends_api and backend_tools_api return namespaces of the spec §8.5, §9.1 and §9.2 names; check_native_error and check_tool_error assert the INV-7/INV-8 error shapes.
COMMON MODIFICATION PATTERNS: Add an endpoint behaviour as a FakeDeepseekEndpoint method and select it from the test; add a fixture here only when two or more modules in this pack need it.
WHAT NOT TO DO IN THIS FILE: 1. Do not stub HttpTransport, HarnessBackends or the tool classes; a missing feature must stay red. 2. Do not read a real key: the autouse fixture deletes GLM_API_KEY, DEEPSEEK_API_KEY and ZHIPU_API_KEY for every test, and the fake values below are not keys.
KNOWN EDGE CASES: A held request (hold_forever) never answers, so only a test that cancels the call may use it. Context keys are checked against the spec §13 list, so a new key needs a spec change first.
RELATED DOCS: tests/features/native_backends/FEATURE.md; docs/spec/native-grok-opencode-meta-hosts/spec.md §6.3.6, §8.5, §9.1, §13
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/native_backends
"""

from __future__ import annotations

import asyncio
import importlib
import json
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

REAL_ASYNC_CLIENT = httpx.AsyncClient
KEY_VARIABLES = ("GLM_API_KEY", "DEEPSEEK_API_KEY", "ZHIPU_API_KEY")
FAKE_GLM_VALUE = "fake-glm-value-not-a-key-0001"
FAKE_DEEPSEEK_VALUE = "fake-deepseek-value-not-a-key-0002"
HEALTHY_BALANCE = {
    "is_available": True,
    "balance_infos": [
        {"currency": "CNY", "total_balance": "110.00", "granted_balance": "10.00", "topped_up_balance": "100.00"},
        {"currency": "USD", "total_balance": "5.50", "granted_balance": "0.00", "topped_up_balance": "5.50"},
    ],
}
CONTEXT_KEYS = frozenset({
    "reason", "field", "vendor_code", "vendor_error", "vendor_kind", "retryable", "status_code", "version",
    "available_models", "available_providers", "live_turns", "truncated", "session_id", "exit_code", "status",
    "features", "distros", "retry_attempt", "method", "error_type",
})


def member_name(code: str) -> str:
    # Spec §6.3.1: member names are the upper-cased value with "." replaced by "_".
    return code.upper().replace(".", "_")


class FakeDeepseekEndpoint:
    """Answers every HTTP request HttpTransport sends, and records it with the client options."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.client_options: list[dict[str, Any]] = []
        self.status = 200
        self.body: bytes = json.dumps(HEALTHY_BALANCE).encode("utf-8")
        self.headers: dict[str, str] = {"content-type": "application/json"}
        self.error: Exception | None = None
        self.hold = False
        self.received = asyncio.Event()

    def answer_json(self, payload: Any, *, status: int = 200) -> None:
        self.status = status
        self.body = json.dumps(payload).encode("utf-8")
        self.headers = {"content-type": "application/json"}

    def answer_text(self, text: str, *, status: int = 200, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self.body = text.encode("utf-8")
        self.headers = dict(headers or {"content-type": "text/plain"})

    def fail_with(self, error: Exception) -> None:
        self.error = error

    def hold_forever(self) -> None:
        self.hold = True

    def handle(self, request: httpx.Request) -> Any:
        # Record the request first, so a test can assert what was sent even when the answer is an error.
        self.requests.append(request)
        self.received.set()
        if self.hold:
            return self._never_answer()
        if self.error is not None:
            raise self.error
        return httpx.Response(self.status, content=self.body, headers=self.headers)

    async def _never_answer(self) -> httpx.Response:
        await asyncio.Event().wait()
        raise AssertionError("unreachable: the held request is only ever cancelled")

    def client_factory(self, *args: Any, **kwargs: Any) -> httpx.AsyncClient:
        # The real AsyncClient, wired to this in-memory endpoint (prior art: tests/test_http_transport_content_type.py).
        self.client_options.append(dict(kwargs))
        kwargs.pop("transport", None)
        return REAL_ASYNC_CLIENT(*args, transport=httpx.MockTransport(self.handle), **kwargs)


@pytest.fixture(autouse=True)
def isolated_backend_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    # Spec §13: backends read the key variables from os.environ on each call; start every test with none.
    for name in KEY_VARIABLES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def deepseek_endpoint(monkeypatch: pytest.MonkeyPatch) -> FakeDeepseekEndpoint:
    # Spec §13: patch vidbyte.lib.http.transport.httpx.AsyncClient with a factory over the saved real class.
    endpoint = FakeDeepseekEndpoint()
    transport_module = importlib.import_module("vidbyte.lib.http.transport")
    monkeypatch.setattr(transport_module.httpx, "AsyncClient", endpoint.client_factory)
    return endpoint


@pytest.fixture
def backend_keys(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    monkeypatch.setenv("GLM_API_KEY", FAKE_GLM_VALUE)
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_DEEPSEEK_VALUE)
    return SimpleNamespace(glm=FAKE_GLM_VALUE, deepseek=FAKE_DEEPSEEK_VALUE)


@pytest.fixture
def backends_api() -> SimpleNamespace:
    # Spec §8.5 and §9.1 names, imported lazily so a missing module fails setup, not collection.
    backends = importlib.import_module("vidbyte.harnesses.native.backends")
    profiles = importlib.import_module("vidbyte.harnesses.native.backends.profiles")
    records = importlib.import_module("vidbyte.lib.dataclasses.harness_backends")
    backend_enums = importlib.import_module("vidbyte.lib.enums.harness_backends")
    native_enums = importlib.import_module("vidbyte.lib.enums.native_hosts")
    errors = importlib.import_module("vidbyte.lib.errors")
    return SimpleNamespace(
        module=backends,
        HarnessBackends=profiles.HarnessBackends,
        list_harness_backends=backends.list_harness_backends,
        build_claude_backend_env=backends.build_claude_backend_env,
        check_backend_ready=backends.check_backend_ready,
        check_backend_compat=backends.check_backend_compat,
        get_deepseek_balance=backends.get_deepseek_balance,
        build_opencode_backend_provider=backends.build_opencode_backend_provider,
        HarnessBackend=records.HarnessBackend,
        ClaudeBackendEnv=records.ClaudeBackendEnv,
        OpencodeBackendProvider=records.OpencodeBackendProvider,
        BackendCompatRequest=records.BackendCompatRequest,
        DeepseekBalanceEntry=records.DeepseekBalanceEntry,
        DeepseekBalance=records.DeepseekBalance,
        BackendReadiness=records.BackendReadiness,
        HarnessBackendName=backend_enums.HarnessBackendName,
        BackendFeature=backend_enums.BackendFeature,
        NativeHarness=native_enums.NativeHarness,
        HARNESS_BACKENDS=importlib.import_module("vidbyte.lib.configs.harness_backends").HARNESS_BACKENDS,
        NativeHostError=errors.NativeHostError,
        ConfigurationError=errors.ConfigurationError,
        FailureCode=importlib.import_module("vidbyte.lib.enums.failure").FailureCode,
        constants=importlib.import_module("vidbyte.lib.constants.native_hosts"),
    )


@pytest.fixture
def backend_tools_api() -> SimpleNamespace:
    tool_types = importlib.import_module("vidbyte.tools.types")
    tool_package = importlib.import_module("vidbyte.tools.builtins.harness_backends")
    return SimpleNamespace(
        HarnessBackendTools=importlib.import_module("vidbyte.tools.toolsets").HarnessBackendTools,
        HarnessBackendTool=importlib.import_module("vidbyte.tools.builtins.harness_backends.tools").HarnessBackendTool,
        ListHarnessBackendsTool=tool_package.ListHarnessBackendsTool,
        CheckBackendReadyTool=tool_package.CheckBackendReadyTool,
        GetDeepseekBalanceTool=tool_package.GetDeepseekBalanceTool,
        ToolCall=tool_types.ToolCall,
        ToolStatus=tool_types.ToolStatus,
        ToolPermission=tool_types.ToolPermission,
        ToolExecutor=importlib.import_module("vidbyte.tools.executor").ToolExecutor,
        PermissionPolicy=importlib.import_module("vidbyte.tools.security").PermissionPolicy,
    )


@pytest.fixture
def check_native_error(backends_api: SimpleNamespace) -> Callable[..., None]:
    def check(error: BaseException, *, code: str, token: str, operation: str | None = None) -> None:
        assert isinstance(error, backends_api.NativeHostError), f"expected NativeHostError, got {type(error).__name__}: {error}"
        assert error.failure_code is backends_api.FailureCode[member_name(code)], f"expected {code}, got {error.failure_code.value}: {error}"
        assert error.next_step.strip(), "INV-8: next_step is never empty"
        assert token in error.next_step, f"next_step {error.next_step!r} lacks the required token {token!r}"
        if operation is not None:
            assert error.operation == operation
        assert all(isinstance(key, str) and isinstance(value, str) for key, value in error.context.items()), "spec §13: every context value is a str"
        assert set(error.context) <= CONTEXT_KEYS, f"unexpected context keys {set(error.context) - CONTEXT_KEYS}"

    return check


@pytest.fixture
def check_tool_error(backend_tools_api: SimpleNamespace) -> Callable[..., None]:
    def check(result: Any, *, code: str, token: str, tool_name: str, harness: str = "backend") -> None:
        assert result.status is backend_tools_api.ToolStatus.ERROR, f"expected an error result, got {result.output!r}"
        metadata = result.metadata
        assert metadata["error"] == code, f"expected {code}, got {metadata.get('error')}: {result.output}"
        assert token in metadata["next_step"], f"next_step {metadata['next_step']!r} lacks {token!r}"
        assert metadata["hint"] == metadata["next_step"], "INV-7: hint repeats next_step"
        assert metadata["operation"] == tool_name
        assert metadata["harness"] == harness, "spec §9.2: backend tools report harness 'backend'"
        assert result.output.startswith(f"{code}: "), result.output
        assert result.output.endswith(f" Next step: {metadata['next_step']}"), result.output

    return check


@pytest.fixture
def backend_tool(backend_tools_api: SimpleNamespace) -> Callable[[str], Any]:
    def find(name: str) -> Any:
        tools = {tool.name: tool for tool in backend_tools_api.HarnessBackendTools().all()}
        assert name in tools, f"HarnessBackendTools lacks {name}: {sorted(tools)}"
        return tools[name]

    return find
