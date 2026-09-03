"""FILE: tests/test_cloud_trajectory_sinks.py

PURPOSE:
    Contract tests for the original S3, GCS, and Azure Blob trajectory sinks,
    including the Harness on_sink_error observability hook.

ROLE IN CODEBASE:
    Protects the PR #393 cloud sink compatibility surface while the expanded
    provider feature pack adds shared lifecycle behavior.

ARCHITECTURE NOTE:
    No real cloud account, network, or optional SDK is required. Each sink
    receives a monkeypatched driver namespace and provider-shaped fake client,
    so tests exercise encoding, request shape, translation, and fail-open
    behavior at the adapter boundary.

COMMON MODIFICATION PATTERNS:
    Extend fakes when a provider request gains a documented option, then add
    a behavior assertion rather than asserting private call order.

KNOWN EDGE CASES:
    Oversized records must make zero provider calls; concurrent first writes
    share one preflight; access denial must remain distinct from authentication.

RELATED DOCS:
    docs/design/cloud-trajectory-sinks.md
    docs/design/cloud-trajectory-provider-expansion.md

TESTS:
    This file is the compatibility suite for the three PR #393 providers.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import asdict
from types import SimpleNamespace
from typing import Any

import pytest

from vidbyte.harnesses.contracts import HARNESS_SCHEMA_VERSION, SinkFailureEvent, TrajectoryRecord
from vidbyte.harnesses.errors import (
    HarnessSinkAuthenticationError,
    HarnessSinkAuthorizationError,
    HarnessSinkError,
    HarnessSinkPayloadError,
    HarnessSinkSetupError,
    HarnessSinkUnavailableError,
)
from vidbyte.harnesses.execution import Harness
from vidbyte.harnesses.stores._sink_support import SinkEncoding
from vidbyte.harnesses.stores.azure_blob import AzureBlobTrajectorySink
from vidbyte.harnesses.stores.gcs import GcsTrajectorySink
from vidbyte.harnesses.stores.s3 import S3TrajectorySink
from vidbyte.lib.constants.cloud_sinks import MAX_TRAJECTORY_RECORD_BYTES
from vidbyte.lib.dataclasses.cloud_sinks import (
    AzureBlobCredentials,
    AzureBlobSinkConfig,
    AzureBlobTier,
    GcsCredentials,
    GcsSinkConfig,
    GcsStorageClass,
    S3Credentials,
    S3SinkConfig,
    S3StorageClass,
    Secret,
)
from vidbyte.lib.errors import ConfigurationError
from vidbyte.sessions.stores.memory import InMemorySessionStore


def _record(run_id: str = "hrun_test", *, output: Any = "ok") -> TrajectoryRecord:
    # Builds a minimal, already-redacted TrajectoryRecord for sink-level tests.
    return TrajectoryRecord(schema_version=HARNESS_SCHEMA_VERSION, run_id=run_id, task="topic", spec={}, agents=(), output=output, status="succeeded", reward=None, created_at="2026-08-31T00:00:00+00:00")


# ---------------------------------------------------------------------------
# Config / Credentials / Secret
# ---------------------------------------------------------------------------
class TestSinkConfigValidation:
    """Stage 1 (local, syntactic) validation on the Config/Credentials dataclasses."""

    def test_s3_config_rejects_empty_bucket(self) -> None:
        with pytest.raises(ConfigurationError):
            S3SinkConfig(bucket="")

    def test_s3_config_rejects_bucket_shorter_than_minimum(self) -> None:
        with pytest.raises(ConfigurationError):
            S3SinkConfig(bucket="ab")

    def test_s3_config_rejects_storage_class_not_enum_member(self) -> None:
        with pytest.raises(ConfigurationError):
            S3SinkConfig(bucket="acme-bucket", storage_class="GLACIER")  # type: ignore[arg-type]

    def test_s3_config_rejects_bool_max_retries(self) -> None:
        with pytest.raises(ConfigurationError):
            S3SinkConfig(bucket="acme-bucket", max_retries=True)  # type: ignore[arg-type]

    def test_s3_config_rejects_kms_sse_without_key_id(self) -> None:
        with pytest.raises(ConfigurationError):
            S3SinkConfig(bucket="acme-bucket", sse="aws:kms")

    def test_gcs_config_rejects_storage_class_not_enum_member(self) -> None:
        with pytest.raises(ConfigurationError):
            GcsSinkConfig(bucket="acme-bucket", storage_class="COLDLINE")  # type: ignore[arg-type]

    def test_azure_config_rejects_empty_container(self) -> None:
        with pytest.raises(ConfigurationError):
            AzureBlobSinkConfig(container="")

    def test_s3_credentials_rejects_access_key_id_without_secret(self) -> None:
        with pytest.raises(ConfigurationError):
            S3Credentials(access_key_id="AKIAEXAMPLE")

    def test_s3_credentials_accepts_all_none_as_default_chain_signal(self) -> None:
        credentials = S3Credentials()
        assert credentials.access_key_id is None
        assert credentials.secret_access_key is None


class TestSecret:
    """The masked credential wrapper — the single highest-value security test in this file."""

    def test_secret_never_renders_value_in_repr_or_str(self) -> None:
        secret = Secret("sk-super-secret-value")
        assert "sk-super-secret-value" not in repr(secret)
        assert "sk-super-secret-value" not in str(secret)

    def test_secret_reveal_returns_the_exact_original_value(self) -> None:
        secret = Secret("sk-super-secret-value")
        assert secret.reveal() == "sk-super-secret-value"

    def test_secret_rejects_empty_value(self) -> None:
        with pytest.raises(ConfigurationError):
            Secret("")

    def test_credentials_dataclass_repr_does_not_leak_the_wrapped_secret(self) -> None:
        # The dataclass auto-repr calls repr() on each field; confirms composition doesn't defeat Secret's masking.
        credentials = S3Credentials(access_key_id="AKIAEXAMPLE", secret_access_key=Secret("sk-super-secret-value"))
        assert "sk-super-secret-value" not in repr(credentials)


# ---------------------------------------------------------------------------
# SinkEncoding
# ---------------------------------------------------------------------------
class TestSinkEncoding:
    def test_encode_record_matches_pre_refactor_file_sink_wire_format(self) -> None:
        import json

        record = _record()
        expected = json.dumps(asdict(record), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        assert SinkEncoding.encode_record(record) == expected

    def test_encode_record_raises_payload_error_not_typeerror(self) -> None:
        record = _record(output=object())  # a bare object() is not JSON-serializable
        with pytest.raises(HarnessSinkPayloadError):
            SinkEncoding.encode_record(record)

    def test_guard_size_accepts_payload_exactly_at_the_limit(self) -> None:
        SinkEncoding.guard_size(b"x" * MAX_TRAJECTORY_RECORD_BYTES, run_id="hrun_test")

    def test_guard_size_rejects_payload_one_byte_over_the_limit(self) -> None:
        with pytest.raises(HarnessSinkPayloadError):
            SinkEncoding.guard_size(b"x" * (MAX_TRAJECTORY_RECORD_BYTES + 1), run_id="hrun_test")


# ---------------------------------------------------------------------------
# S3TrajectorySink test doubles
# ---------------------------------------------------------------------------
class _FakeClientError(Exception):
    """Stand-in for botocore.exceptions.ClientError, carrying a fake .response."""

    def __init__(self, code: str, status_code: int | None = None) -> None:
        self.response = {"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status_code}}
        super().__init__(code)


class _FakeNoCredentialsError(Exception): ...
class _FakeEndpointConnectionError(Exception): ...
class _FakeConnectTimeoutError(Exception): ...


class FakeS3Client:
    """Records every call and raises a configured exception on demand."""

    def __init__(self) -> None:
        self.head_bucket_calls: list[str] = []
        self.put_object_calls: list[dict[str, Any]] = []
        self.head_bucket_error: Exception | None = None
        self.put_object_error: Exception | None = None

    def head_bucket(self, *, Bucket: str) -> None:
        self.head_bucket_calls.append(Bucket)
        if self.head_bucket_error is not None:
            raise self.head_bucket_error

    def put_object(self, **kwargs: Any) -> None:
        self.put_object_calls.append(kwargs)
        if self.put_object_error is not None:
            raise self.put_object_error


class FakeStsClient:
    """Records assume_role calls and raises a configured exception on demand."""

    def __init__(self) -> None:
        self.assume_role_calls: list[dict[str, Any]] = []
        self.assume_role_error: Exception | None = None

    def assume_role(self, **kwargs: Any) -> dict[str, Any]:
        self.assume_role_calls.append(kwargs)
        if self.assume_role_error is not None:
            raise self.assume_role_error
        return {"Credentials": {"AccessKeyId": "ASSUMED_KEY", "SecretAccessKey": "ASSUMED_SECRET", "SessionToken": "ASSUMED_TOKEN"}}


class FakeBoto3:
    """Stand-in for the boto3 module surface this sink touches."""

    def __init__(self, s3_client: FakeS3Client, sts_client: FakeStsClient | None = None) -> None:
        self._s3_client = s3_client
        self._sts_client = sts_client
        self.client_calls: list[tuple[str, dict[str, Any]]] = []

    def client(self, service_name: str, **kwargs: Any) -> Any:
        self.client_calls.append((service_name, kwargs))
        if service_name == "s3":
            return self._s3_client
        if service_name == "sts" and self._sts_client is not None:
            return self._sts_client
        raise AssertionError(f"unexpected boto3 service requested: {service_name}")


def _fake_s3_driver(client: FakeS3Client, sts_client: FakeStsClient | None = None) -> SimpleNamespace:
    # Builds the SimpleNamespace S3TrajectorySink._import_driver() would normally return.
    return SimpleNamespace(
        boto3=FakeBoto3(client, sts_client),
        BotoConfig=lambda **kwargs: kwargs,
        ClientError=_FakeClientError,
        ConnectTimeoutError=_FakeConnectTimeoutError,
        EndpointConnectionError=_FakeEndpointConnectionError,
        NoCredentialsError=_FakeNoCredentialsError,
    )


def _make_s3_sink(monkeypatch: pytest.MonkeyPatch, client: FakeS3Client, *, config: S3SinkConfig | None = None) -> S3TrajectorySink:
    # Constructs a real S3TrajectorySink wired to a fake boto3 driver instead of the real package.
    monkeypatch.setattr(S3TrajectorySink, "_import_driver", staticmethod(lambda: _fake_s3_driver(client)))
    return S3TrajectorySink(config or S3SinkConfig(bucket="acme-bucket", prefix="runs"))


class TestS3TrajectorySink:
    def test_missing_boto3_raises_configuration_error_not_import_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Forces the real `import boto3` line inside _import_driver() to fail, exercising the actual ImportError -> ConfigurationError translation rather than bypassing it.
        monkeypatch.setitem(sys.modules, "boto3", None)
        with pytest.raises(ConfigurationError):
            S3TrajectorySink(S3SinkConfig(bucket="acme-bucket"))

    @pytest.mark.asyncio
    async def test_write_uses_prefixed_key_when_prefix_is_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        sink = _make_s3_sink(monkeypatch, client, config=S3SinkConfig(bucket="acme-bucket", prefix="runs/"))
        await sink.write(_record(run_id="hrun_abc"))
        assert client.put_object_calls[0]["Key"] == "runs/hrun_abc.jsonl"

    @pytest.mark.asyncio
    async def test_write_uses_bare_key_when_prefix_is_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        sink = _make_s3_sink(monkeypatch, client, config=S3SinkConfig(bucket="acme-bucket"))
        await sink.write(_record(run_id="hrun_abc"))
        assert client.put_object_calls[0]["Key"] == "hrun_abc.jsonl"

    @pytest.mark.asyncio
    async def test_write_sends_exactly_one_put_object_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        sink = _make_s3_sink(monkeypatch, client)
        await sink.write(_record())
        assert len(client.put_object_calls) == 1

    @pytest.mark.asyncio
    async def test_write_sets_configured_storage_class(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        sink = _make_s3_sink(monkeypatch, client, config=S3SinkConfig(bucket="acme-bucket", storage_class=S3StorageClass.GLACIER_IR))
        await sink.write(_record())
        assert client.put_object_calls[0]["StorageClass"] == "GLACIER_IR"

    @pytest.mark.asyncio
    async def test_write_overwrites_rather_than_erroring_on_retried_run_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        sink = _make_s3_sink(monkeypatch, client)
        await sink.write(_record(run_id="hrun_retry"))
        await sink.write(_record(run_id="hrun_retry"))  # same run_id, second attempt
        assert len(client.put_object_calls) == 2
        assert client.put_object_calls[0]["Key"] == client.put_object_calls[1]["Key"]

    @pytest.mark.asyncio
    async def test_ensure_ready_runs_head_bucket_only_once_across_concurrent_writes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        sink = _make_s3_sink(monkeypatch, client)
        await asyncio.gather(sink.write(_record(run_id="hrun_a")), sink.write(_record(run_id="hrun_b")))
        assert len(client.head_bucket_calls) == 1

    @pytest.mark.asyncio
    async def test_write_raises_payload_error_and_makes_zero_put_object_calls_for_oversized_record(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        sink = _make_s3_sink(monkeypatch, client)
        with pytest.raises(HarnessSinkPayloadError):
            await sink.write(_record(output="x" * (MAX_TRAJECTORY_RECORD_BYTES + 1)))
        assert client.put_object_calls == []

    @pytest.mark.asyncio
    async def test_translate_error_maps_no_such_bucket_to_setup_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        client.head_bucket_error = _FakeClientError("NoSuchBucket")
        sink = _make_s3_sink(monkeypatch, client)
        with pytest.raises(HarnessSinkSetupError):
            await sink.verify()

    @pytest.mark.asyncio
    async def test_translate_error_maps_access_denied_to_authorization_not_authentication(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        client.put_object_error = _FakeClientError("AccessDenied")
        sink = _make_s3_sink(monkeypatch, client)
        with pytest.raises(HarnessSinkAuthorizationError):
            await sink.write(_record())

    @pytest.mark.asyncio
    async def test_translate_error_maps_no_credentials_to_authentication_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        client.head_bucket_error = _FakeNoCredentialsError()
        sink = _make_s3_sink(monkeypatch, client)
        with pytest.raises(HarnessSinkAuthenticationError):
            await sink.verify()

    @pytest.mark.asyncio
    async def test_translate_error_maps_endpoint_connection_error_to_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        client.head_bucket_error = _FakeEndpointConnectionError()
        sink = _make_s3_sink(monkeypatch, client)
        with pytest.raises(HarnessSinkUnavailableError):
            await sink.verify()

    @pytest.mark.asyncio
    async def test_translate_error_maps_slow_down_to_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        client.put_object_error = _FakeClientError("SlowDown", status_code=503)
        sink = _make_s3_sink(monkeypatch, client)
        with pytest.raises(HarnessSinkUnavailableError):
            await sink.write(_record())

    def test_role_arn_assumption_resolves_temporary_credentials_onto_the_s3_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        sts_client = FakeStsClient()
        driver = _fake_s3_driver(client, sts_client)
        monkeypatch.setattr(S3TrajectorySink, "_import_driver", staticmethod(lambda: driver))
        S3TrajectorySink(S3SinkConfig(bucket="acme-bucket", role_arn="arn:aws:iam::123456789012:role/vidbyte-export", external_id="ext-123"))
        assert len(sts_client.assume_role_calls) == 1
        assert sts_client.assume_role_calls[0]["RoleArn"] == "arn:aws:iam::123456789012:role/vidbyte-export"
        assert sts_client.assume_role_calls[0]["ExternalId"] == "ext-123"
        s3_call_kwargs = next(kwargs for name, kwargs in driver.boto3.client_calls if name == "s3")
        assert s3_call_kwargs["aws_access_key_id"] == "ASSUMED_KEY"
        assert s3_call_kwargs["aws_session_token"] == "ASSUMED_TOKEN"

    def test_role_arn_assumption_failure_raises_authentication_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sts_client = FakeStsClient()
        sts_client.assume_role_error = Exception("AccessDenied assuming role: trust policy does not list this caller")
        driver = _fake_s3_driver(FakeS3Client(), sts_client)
        monkeypatch.setattr(S3TrajectorySink, "_import_driver", staticmethod(lambda: driver))
        with pytest.raises(HarnessSinkAuthenticationError):
            S3TrajectorySink(S3SinkConfig(bucket="acme-bucket", role_arn="arn:aws:iam::123456789012:role/vidbyte-export"))


# ---------------------------------------------------------------------------
# GcsTrajectorySink — representative provider-specific behavior
# ---------------------------------------------------------------------------
class _FakeGcsAuthError(Exception): ...
class _FakeGcsApiError(Exception): ...


class FakeGcsBlob:
    def __init__(self, upload_error: Exception | None) -> None:
        self.storage_class: str | None = None
        self._upload_error = upload_error
        self.uploaded_payload: bytes | None = None

    def upload_from_string(self, payload: bytes, content_type: str, **_: Any) -> None:
        if self._upload_error is not None:
            raise self._upload_error
        self.uploaded_payload = payload

    def upload_from_file(self, stream: Any, **_: Any) -> None:
        if self._upload_error is not None:
            raise self._upload_error
        self.uploaded_payload = stream.read()


class FakeGcsBucket:
    def __init__(self, upload_error: Exception | None) -> None:
        self._upload_error = upload_error
        self.blobs: list[FakeGcsBlob] = []

    def blob(self, key: str, kms_key_name: str | None = None) -> FakeGcsBlob:
        blob = FakeGcsBlob(self._upload_error)
        self.blobs.append(blob)
        return blob


class FakeGcsClient:
    def __init__(self) -> None:
        self.get_bucket_error: Exception | None = None
        self.upload_error: Exception | None = None
        self.bucket_instance: FakeGcsBucket | None = None

    def get_bucket(self, name: str, **_: Any) -> None:
        if self.get_bucket_error is not None:
            raise self.get_bucket_error

    def bucket(self, name: str) -> FakeGcsBucket:
        self.bucket_instance = FakeGcsBucket(self.upload_error)
        return self.bucket_instance


def _fake_gcs_driver(client: FakeGcsClient) -> SimpleNamespace:
    return SimpleNamespace(
        storage=SimpleNamespace(Client=lambda **kwargs: client),
        service_account=SimpleNamespace(Credentials=SimpleNamespace(from_service_account_file=lambda path: SimpleNamespace())),
        DefaultCredentialsError=_FakeGcsAuthError,
        NotFound=type("NotFound", (_FakeGcsApiError,), {}),
        Forbidden=type("Forbidden", (_FakeGcsApiError,), {}),
        Unauthorized=type("Unauthorized", (_FakeGcsApiError,), {}),
        TooManyRequests=type("TooManyRequests", (_FakeGcsApiError,), {}),
        ServiceUnavailable=type("ServiceUnavailable", (_FakeGcsApiError,), {}),
        DeadlineExceeded=type("DeadlineExceeded", (_FakeGcsApiError,), {}),
    )


def _make_gcs_sink(monkeypatch: pytest.MonkeyPatch, client: FakeGcsClient, *, config: GcsSinkConfig | None = None) -> GcsTrajectorySink:
    driver = _fake_gcs_driver(client)
    monkeypatch.setattr(GcsTrajectorySink, "_import_driver", staticmethod(lambda: driver))
    sink = GcsTrajectorySink(config or GcsSinkConfig(bucket="acme-bucket"))
    return sink


class TestGcsTrajectorySink:
    @pytest.mark.asyncio
    async def test_write_sets_configured_storage_class_on_the_blob(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeGcsClient()
        sink = _make_gcs_sink(monkeypatch, client, config=GcsSinkConfig(bucket="acme-bucket", storage_class=GcsStorageClass.COLDLINE))
        await sink.write(_record())
        assert client.bucket_instance is not None
        assert client.bucket_instance.blobs[0].storage_class == "COLDLINE"

    @pytest.mark.asyncio
    async def test_translate_error_maps_not_found_to_setup_error_with_ambiguity_noted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeGcsClient()
        driver = _fake_gcs_driver(client)
        client.get_bucket_error = driver.NotFound()
        monkeypatch.setattr(GcsTrajectorySink, "_import_driver", staticmethod(lambda: driver))
        sink = GcsTrajectorySink(GcsSinkConfig(bucket="acme-bucket"))
        with pytest.raises(HarnessSinkSetupError) as excinfo:
            await sink.verify()
        assert "permission" in str(excinfo.value).lower()

    @pytest.mark.asyncio
    async def test_translate_error_maps_forbidden_to_authorization_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeGcsClient()
        driver = _fake_gcs_driver(client)
        client.upload_error = driver.Forbidden()
        monkeypatch.setattr(GcsTrajectorySink, "_import_driver", staticmethod(lambda: driver))
        sink = GcsTrajectorySink(GcsSinkConfig(bucket="acme-bucket"))
        with pytest.raises(HarnessSinkAuthorizationError):
            await sink.write(_record())

    def test_missing_default_credentials_raises_authentication_error_at_construction(self, monkeypatch: pytest.MonkeyPatch) -> None:
        driver = _fake_gcs_driver(FakeGcsClient())

        def _raise_no_adc(**kwargs: Any) -> None:
            raise driver.DefaultCredentialsError("no Application Default Credentials found")

        driver.storage.Client = _raise_no_adc
        monkeypatch.setattr(GcsTrajectorySink, "_import_driver", staticmethod(lambda: driver))
        with pytest.raises(HarnessSinkAuthenticationError):
            GcsTrajectorySink(GcsSinkConfig(bucket="acme-bucket"))


# ---------------------------------------------------------------------------
# AzureBlobTrajectorySink — representative provider-specific behavior
# ---------------------------------------------------------------------------
class _FakeAzureAuthError(Exception): ...
class _FakeAzureResourceNotFoundError(Exception): ...
class _FakeAzureServiceRequestError(Exception): ...


class _FakeHttpResponseError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"http {status_code}")


class FakeAzureBlobClient:
    def __init__(self, upload_error: Exception | None) -> None:
        self._upload_error = upload_error
        self.upload_calls: list[dict[str, Any]] = []

    async def upload_blob(self, payload: bytes, **kwargs: Any) -> None:
        self.upload_calls.append(kwargs)
        if self._upload_error is not None:
            raise self._upload_error


class FakeAzureContainerClient:
    def __init__(self, preflight_error: Exception | None) -> None:
        self._preflight_error = preflight_error

    async def get_container_properties(self) -> None:
        if self._preflight_error is not None:
            raise self._preflight_error


class FakeAzureBlobServiceClient:
    def __init__(self, preflight_error: Exception | None = None, upload_error: Exception | None = None) -> None:
        self._preflight_error = preflight_error
        self._upload_error = upload_error
        self.last_blob_client: FakeAzureBlobClient | None = None

    @classmethod
    def from_connection_string(cls, connection_string: str, retry_total: int) -> "FakeAzureBlobServiceClient":
        return cls()

    def get_container_client(self, container: str) -> FakeAzureContainerClient:
        return FakeAzureContainerClient(self._preflight_error)

    def get_blob_client(self, *, container: str, blob: str) -> FakeAzureBlobClient:
        self.last_blob_client = FakeAzureBlobClient(self._upload_error)
        return self.last_blob_client


def _fake_azure_driver(preflight_error: Exception | None = None, upload_error: Exception | None = None) -> SimpleNamespace:
    client = FakeAzureBlobServiceClient(preflight_error, upload_error)
    return SimpleNamespace(
        BlobServiceClient=SimpleNamespace(from_connection_string=lambda *a, **k: client),
        ContentSettings=lambda **kwargs: kwargs,
        ClientAuthenticationError=_FakeAzureAuthError,
        HttpResponseError=_FakeHttpResponseError,
        ResourceNotFoundError=_FakeAzureResourceNotFoundError,
        ServiceRequestError=_FakeAzureServiceRequestError,
    ), client


class TestAzureBlobTrajectorySink:
    def test_credentials_is_a_required_argument_not_optional(self, monkeypatch: pytest.MonkeyPatch) -> None:
        driver, _ = _fake_azure_driver()
        monkeypatch.setattr(AzureBlobTrajectorySink, "_import_driver", staticmethod(lambda: driver))
        with pytest.raises(TypeError):
            AzureBlobTrajectorySink(AzureBlobSinkConfig(container="acme-container"))  # type: ignore[call-arg]

    @pytest.mark.asyncio
    async def test_write_passes_overwrite_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        driver, service_client = _fake_azure_driver()
        monkeypatch.setattr(AzureBlobTrajectorySink, "_import_driver", staticmethod(lambda: driver))
        sink = AzureBlobTrajectorySink(AzureBlobSinkConfig(container="acme-container"), credentials=AzureBlobCredentials(account_url="https://acct.blob.core.windows.net", connection_string=Secret("conn-str")))
        await sink.write(_record())
        assert service_client.last_blob_client is not None
        assert service_client.last_blob_client.upload_calls[0]["overwrite"] is True

    @pytest.mark.asyncio
    async def test_write_sets_configured_tier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        driver, service_client = _fake_azure_driver()
        monkeypatch.setattr(AzureBlobTrajectorySink, "_import_driver", staticmethod(lambda: driver))
        sink = AzureBlobTrajectorySink(AzureBlobSinkConfig(container="acme-container", tier=AzureBlobTier.COOL), credentials=AzureBlobCredentials(account_url="https://acct.blob.core.windows.net", connection_string=Secret("conn-str")))
        await sink.write(_record())
        assert service_client.last_blob_client.upload_calls[0]["standard_blob_tier"] == "Cool"

    @pytest.mark.asyncio
    async def test_translate_error_maps_403_to_authorization_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        driver, _ = _fake_azure_driver(upload_error=_FakeHttpResponseError(403))
        monkeypatch.setattr(AzureBlobTrajectorySink, "_import_driver", staticmethod(lambda: driver))
        sink = AzureBlobTrajectorySink(AzureBlobSinkConfig(container="acme-container"), credentials=AzureBlobCredentials(account_url="https://acct.blob.core.windows.net", connection_string=Secret("conn-str")))
        with pytest.raises(HarnessSinkAuthorizationError):
            await sink.write(_record())

    @pytest.mark.asyncio
    async def test_translate_error_maps_service_request_error_to_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        driver, _ = _fake_azure_driver(preflight_error=_FakeAzureServiceRequestError("network unreachable"))
        monkeypatch.setattr(AzureBlobTrajectorySink, "_import_driver", staticmethod(lambda: driver))
        sink = AzureBlobTrajectorySink(AzureBlobSinkConfig(container="acme-container"), credentials=AzureBlobCredentials(account_url="https://acct.blob.core.windows.net", connection_string=Secret("conn-str")))
        with pytest.raises(HarnessSinkUnavailableError):
            await sink.verify()


# ---------------------------------------------------------------------------
# Harness._maybe_collect / on_sink_error observability hook
# ---------------------------------------------------------------------------
class _FailingSink:
    """A sink whose write() always raises, to exercise the fail-open + hook path."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def write(self, record: TrajectoryRecord) -> None:
        raise self._error


class _RaisingCallback:
    def __call__(self, event: SinkFailureEvent) -> None:
        raise RuntimeError("observer itself is broken")


class _NoOpHarness(Harness):
    type = "test-harness"
    version = "1"

    async def run(self, request: Any) -> Any:
        return {"answer": "ok"}


def _loaded_harness(**kwargs: Any) -> _NoOpHarness:
    harness = _NoOpHarness(store=InMemorySessionStore(), collect=True, **kwargs)
    harness.load({"schema_version": 1, "harness": {"type": "test-harness"}, "agents": [{"name": "worker"}]})
    return harness


class TestOnSinkErrorHook:
    @pytest.mark.asyncio
    async def test_default_none_means_no_callback_invocation(self) -> None:
        calls: list[SinkFailureEvent] = []
        harness = _loaded_harness(sink=_FailingSink(RuntimeError("boom")))  # on_sink_error omitted -> None
        await harness.execute({"topic": "x"})
        assert calls == []  # nothing to assert against a callback that was never registered; documents the default

    @pytest.mark.asyncio
    async def test_execute_still_succeeds_when_sink_fails_and_hook_is_set(self) -> None:
        events: list[SinkFailureEvent] = []
        harness = _loaded_harness(sink=_FailingSink(RuntimeError("boom")), on_sink_error=events.append)
        result = await harness.execute({"topic": "x"})
        assert result.run.status.value == "succeeded"
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_execute_still_succeeds_when_the_callback_itself_raises(self) -> None:
        harness = _loaded_harness(sink=_FailingSink(RuntimeError("boom")), on_sink_error=_RaisingCallback())
        result = await harness.execute({"topic": "x"})
        assert result.run.status.value == "succeeded"

    @pytest.mark.asyncio
    async def test_event_message_is_redacted_before_reaching_the_callback(self) -> None:
        events: list[SinkFailureEvent] = []
        harness = _loaded_harness(sink=_FailingSink(RuntimeError("upload failed, api_key=sk-live-abc123")), on_sink_error=events.append)
        await harness.execute({"topic": "x"})
        assert "sk-live-abc123" not in events[0].message

    @pytest.mark.asyncio
    async def test_hook_fires_for_a_collection_failure_not_only_a_sink_write_failure(self) -> None:
        class _BrokenStore(InMemorySessionStore):
            def list_sessions(self, *, agent_name: str | None = None, tag: str | None = None, status: Any = None) -> list[Any]:
                raise RuntimeError("store read failed")

        events: list[SinkFailureEvent] = []
        harness = _NoOpHarness(store=_BrokenStore(), sink=_FailingSink(RuntimeError("unreachable")), collect=True, on_sink_error=events.append)
        harness.load({"schema_version": 1, "harness": {"type": "test-harness"}, "agents": [{"name": "worker"}]})
        result = await harness.execute({"topic": "x"})
        assert result.run.status.value == "succeeded"
        assert len(events) == 1


# ---------------------------------------------------------------------------
# Integration: real Harness.execute() driving a stub S3 sink end to end
# ---------------------------------------------------------------------------
class TestCloudSinkIntegration:
    @pytest.mark.asyncio
    async def test_end_to_end_run_writes_exactly_one_jsonl_object(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        sink = _make_s3_sink(monkeypatch, client, config=S3SinkConfig(bucket="acme-bucket", prefix="runs"))
        harness = _NoOpHarness(store=InMemorySessionStore(), sink=sink, collect=True)
        harness.load({"schema_version": 1, "harness": {"type": "test-harness"}, "agents": [{"name": "worker"}]})
        result = await harness.execute({"topic": "durable runtimes"})
        assert result.run.status.value == "succeeded"
        assert len(client.put_object_calls) == 1
        assert client.put_object_calls[0]["Key"] == f"runs/{result.run.run_id}.jsonl"

    @pytest.mark.asyncio
    async def test_sink_write_failure_does_not_fail_a_successful_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        client.put_object_error = _FakeClientError("AccessDenied")
        sink = _make_s3_sink(monkeypatch, client)
        harness = _NoOpHarness(store=InMemorySessionStore(), sink=sink, collect=True)
        harness.load({"schema_version": 1, "harness": {"type": "test-harness"}, "agents": [{"name": "worker"}]})
        result = await harness.execute({"topic": "x"})
        assert result.run.status.value == "succeeded"

    @pytest.mark.asyncio
    async def test_collect_true_with_no_sink_invokes_nothing_and_raises_nothing(self) -> None:
        harness = _NoOpHarness(store=InMemorySessionStore(), sink=None, collect=True)
        harness.load({"schema_version": 1, "harness": {"type": "test-harness"}, "agents": [{"name": "worker"}]})
        result = await harness.execute({"topic": "x"})
        assert result.run.status.value == "succeeded"
