"""FILE: tests/features/agent_output_connectors/conftest.py

PURPOSE: Pytest fixtures for the agent-output-connectors pack: lazy feature imports, a scripted HTTP destination, an in-memory httpx transport, a scripted SMTP server, clean credential environment variables, and destination parametrization.
ROLE IN CODEBASE: Loaded by pytest for every module in tests/features/agent_output_connectors/; wraps factories.py and the HttpTransport._send_once seam used by tests/test_web_operation_client_retry.py.
ARCHITECTURE NOTE: Feature modules are imported inside fixtures, so a missing vidbyte.agents.output or vidbyte.lib.outputs fails each test at setup instead of aborting collection of the whole suite.
FUNCTION INVENTORY: isolated_output_env (autouse) deletes every §9.3 variable; output_api, output_constants, dispatcher_module import feature modules; fake_http installs HttpScript at _send_once and skips the transport backoff sleep; fake_smtp installs scripted smtplib.SMTP and SMTP_SSL on the module delivery.py imports and refuses real sockets; httpx_destination keeps the real _send_once and replaces httpx.AsyncClient with a MockTransport-backed client; http_case and any_case parametrize over CONNECTOR_CASES.
COMMON MODIFICATION PATTERNS: Put data and fakes in factories.py and expose them here only when a test needs per-test state or monkeypatching.
WHAT NOT TO DO IN THIS FILE: 1. Do not stub a feature module; a missing feature must stay red. 2. Do not open sockets; socket.create_connection refuses during SMTP tests. 3. Do not import feature modules at module level.
KNOWN EDGE CASES: The transport sleep patch replaces asyncio.sleep for the whole test, so concurrency tests coordinate with asyncio.Event instead of sleeping. fake_smtp fails with AttributeError if delivery.py imports SMTP by name instead of importing smtplib, because a by-name import would bypass the scripted classes. httpx_destination patches the attribute on the httpx module object itself, so a test's own httpx.AsyncClient() is in-memory too.
RELATED DOCS: tests/features/agent_output_connectors/FEATURE.md; docs/spec/agent-output-connectors/spec.md (§13)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors
"""

from __future__ import annotations

import importlib
import socket
from types import ModuleType
from typing import Any

import httpx
import pytest

from tests.features.agent_output_connectors.factories import (
    ALL_DESTINATION_KEYS,
    CONNECTOR_CASES,
    HTTP_DESTINATION_KEYS,
    OUTPUT_ENV_VARS,
    ConnectorCase,
    HttpScript,
    HttpxRequests,
    ScriptedSmtp,
    ScriptedSmtpSsl,
    SmtpScript,
)
from vidbyte.lib.http import transport as transport_module
from vidbyte.lib.http.transport import HttpResponse, HttpTransport


def _refuse_socket(*args: object, **kwargs: object) -> None:
    raise AssertionError("a test tried to open a real socket")


@pytest.fixture(autouse=True)
def isolated_output_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # A developer's real token or webhook URL must never reach a test, and a missing-credential test must see none.
    for name in OUTPUT_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def output_api() -> ModuleType:
    # Red until vidbyte/agents/output/__init__.py exports the 24 public names (first spec §9.2; follow-ups FR-29).
    return importlib.import_module("vidbyte.agents.output")


@pytest.fixture
def output_constants() -> ModuleType:
    # Red until vidbyte/lib/constants/outputs.py exists (spec §12.3 row 2).
    return importlib.import_module("vidbyte.lib.constants.outputs")


@pytest.fixture
def dispatcher_module() -> ModuleType:
    # Red until vidbyte/agents/output/dispatcher.py exists; tests shorten its OUTPUT_DELIVERY_DEADLINE_SECONDS (spec §13).
    return importlib.import_module("vidbyte.agents.output.dispatcher")


@pytest.fixture
def fake_http(monkeypatch: pytest.MonkeyPatch) -> HttpScript:
    # Replaces the single-attempt send and the backoff sleep, so every connector stays offline and retries do not wait.
    script = HttpScript()

    async def fake_send(self: HttpTransport, client: object, **kwargs: Any) -> HttpResponse:
        return await script.respond(kwargs)

    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(HttpTransport, "_send_once", fake_send)
    monkeypatch.setattr(transport_module.asyncio, "sleep", no_sleep)
    return script


@pytest.fixture
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> SmtpScript:
    # Red until vidbyte/lib/outputs/delivery.py imports smtplib as a module (spec §13); its SMTP classes become scripted ones.
    delivery = importlib.import_module("vidbyte.lib.outputs.delivery")
    script = SmtpScript()
    monkeypatch.setattr(delivery.smtplib, "SMTP", type("ScriptedSMTP", (ScriptedSmtp,), {"script": script}))
    monkeypatch.setattr(delivery.smtplib, "SMTP_SSL", type("ScriptedSMTP_SSL", (ScriptedSmtpSsl,), {"script": script}))
    monkeypatch.setattr(socket, "create_connection", _refuse_socket)
    return script


@pytest.fixture
def httpx_destination(monkeypatch: pytest.MonkeyPatch) -> HttpxRequests:
    # Gives every httpx client an in-memory transport, so the real _send_once, redirect policy, size ceiling, and httpx's own request log run offline.
    requests = HttpxRequests()
    real_client = httpx.AsyncClient

    def client_factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        return real_client(*args, transport=httpx.MockTransport(requests.handle), **kwargs)

    monkeypatch.setattr(transport_module.httpx, "AsyncClient", client_factory)
    return requests


@pytest.fixture(params=HTTP_DESTINATION_KEYS)
def http_case(request: pytest.FixtureRequest) -> ConnectorCase:
    return CONNECTOR_CASES[request.param]


@pytest.fixture(params=ALL_DESTINATION_KEYS)
def any_case(request: pytest.FixtureRequest) -> ConnectorCase:
    return CONNECTOR_CASES[request.param]
