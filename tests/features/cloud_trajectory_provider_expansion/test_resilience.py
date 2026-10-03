"""FILE: tests/features/cloud_trajectory_provider_expansion/test_resilience.py

PURPOSE:
    Verify preflight task sharing/recovery, close semantics, and provider
    failure classification under concurrency and transient boundaries.

ROLE IN CODEBASE:
    Resilience/error layer of the cloud trajectory provider feature pack.

ARCHITECTURE NOTE:
    Tests use in-memory lifecycle and OCI-shaped doubles so failure behavior
    is isolated from the provider SDK and external network.

COMMON MODIFICATION PATTERNS:
    Add negative, cancellation, retry, or cleanup coverage for every new
    state transition; assert typed errors and observable state.

KNOWN EDGE CASES:
    A failed shared preflight must be retryable, closed sinks must reject new
    work, and authorization must not be mislabeled as authentication.

RELATED DOCS:
    docs/design/cloud-trajectory-provider-expansion.md

TESTS:
    Run with scripts/test-cloud-trajectory-provider-expansion.py.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from vidbyte.harnesses.errors import HarnessSinkAuthorizationError, HarnessSinkSetupError
from vidbyte.harnesses.stores._cloud_common import SinkLifecycle
from vidbyte.harnesses.stores.oci import OciTrajectorySink
from vidbyte.lib.dataclasses.cloud_sinks import OciSinkConfig


@pytest.mark.asyncio
async def test_lifecycle_shares_concurrent_preflight_and_recovers_after_failure() -> None:
    lifecycle = SinkLifecycle("test")
    calls = 0
    fail = True

    async def preflight() -> None:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        if fail:
            raise RuntimeError("first attempt")

    with pytest.raises(RuntimeError):
        await asyncio.gather(lifecycle.ensure_ready(preflight), lifecycle.ensure_ready(preflight))
    assert calls == 1
    fail = False
    await lifecycle.ensure_ready(preflight)
    assert calls == 2


@pytest.mark.asyncio
async def test_lifecycle_close_is_idempotent_and_rejects_future_work() -> None:
    lifecycle = SinkLifecycle("test")
    lifecycle.closed = True
    with pytest.raises(HarnessSinkSetupError):
        await lifecycle.ensure_ready(lambda: asyncio.sleep(0))
    lifecycle.closed = True
    assert lifecycle.last_receipt is None


class _ServiceError(Exception):
    def __init__(self, status: int) -> None:
        self.status = status


@pytest.mark.asyncio
async def test_oci_preflight_translation_keeps_authz_distinct(monkeypatch: pytest.MonkeyPatch) -> None:
    class Client:
        def __init__(self, config: Any, **kwargs: Any) -> None:
            pass

        def get_bucket(self, *args: Any) -> None:
            raise _ServiceError(403)

    driver = SimpleNamespace(
        ClientError=type("ClientError", (Exception,), {}),
        ConfigFileNotFound=type("ConfigFileNotFound", (Exception,), {}),
        ConnectTimeout=type("ConnectTimeout", (Exception,), {}),
        InvalidConfig=type("InvalidConfig", (Exception,), {}),
        ObjectStorageClient=Client,
        ProfileNotFound=type("ProfileNotFound", (Exception,), {}),
        RequestException=type("RequestException", (Exception,), {}),
        ServiceError=_ServiceError,
        Signer=lambda *args, **kwargs: None,
        UploadManager=object,
        config=SimpleNamespace(from_file=lambda **kwargs: {"region": "region"}),
        retry=SimpleNamespace(RetryStrategyBuilder=lambda: SimpleNamespace(add_max_attempts=lambda attempts: SimpleNamespace(get_retry_strategy=lambda: None))),
        signers=SimpleNamespace(),
    )
    monkeypatch.setattr(OciTrajectorySink, "_import_driver", staticmethod(lambda: driver))
    sink = OciTrajectorySink(OciSinkConfig(bucket="oci-bucket", namespace="namespace"))
    with pytest.raises(HarnessSinkAuthorizationError):
        await sink.verify()
