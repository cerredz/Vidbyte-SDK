"""Tests for the cloud TrajectorySink backends (S3, GCS, Azure Blob) and the
on_sink_error observability hook added in docs/design/cloud-trajectory-sinks.md.

No real AWS/GCP/Azure account, network access, or installed vendor SDK is
required: every sink test monkeypatches `_import_driver` to return a fake
driver namespace holding stub exception types and a stub client double, so
these tests exercise the sink's own translation/encoding/shape logic only.
"""

from __future__ import annotations

import asyncio
import base64
import gzip
import hashlib
import sys
from dataclasses import asdict
from datetime import datetime, timezone
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

    def test_provider_config_copies_object_maps_and_accepts_retention_controls(self) -> None:
        tags = {"team": "finops"}
        metadata = {"lineage": "run"}
        s3 = S3SinkConfig(bucket="acme-bucket", tags=tags, metadata=metadata)
        tags["mutated"] = "after-construction"
        metadata["mutated"] = "after-construction"
        assert s3.tags == {"team": "finops"}
        assert s3.metadata == {"lineage": "run"}
        gcs = GcsSinkConfig(
            bucket="acme-bucket",
            retention_mode="Unlocked",
            retain_until_time=datetime(2026, 9, 3, tzinfo=timezone.utc),
            if_generation_match=0,
        )
        assert gcs.content_type == "application/x-ndjson"
        azure = AzureBlobSinkConfig(container="acme-container", tags={"team": "finops"})
        assert azure.tags == {"team": "finops"}

    def test_s3_supports_dsse_and_provider_endpoint_controls(self) -> None:
        config = S3SinkConfig(
            bucket="acme-bucket",
            sse="aws:kms:dsse",
            storage_class=S3StorageClass.EXPRESS_ONEZONE,
            use_dualstack_endpoint=True,
        )
        assert config.sse == "aws:kms:dsse"

    def test_sse_c_keys_are_length_checked_and_md5_checked(self) -> None:
        raw_key = b"k" * 32
        md5 = base64.b64encode(hashlib.md5(raw_key, usedforsecurity=False).digest()).decode("ascii")
        credentials = S3Credentials(sse_customer_key=Secret(raw_key), sse_customer_key_md5=md5)
        assert credentials.sse_customer_key is not None
        with pytest.raises(ConfigurationError):
            S3Credentials(sse_customer_key=Secret(b"short"))

    def test_customer_key_and_object_conditions_are_validated_per_provider(self) -> None:
        with pytest.raises(ConfigurationError):
            S3SinkConfig(bucket="acme-bucket", sse="AES256", sse_customer_algorithm="AES256")
        with pytest.raises(ConfigurationError):
            GcsSinkConfig(bucket="acme-bucket", if_generation_match=1, if_generation_not_match=2)
        with pytest.raises(ConfigurationError):
            AzureBlobSinkConfig(container="acme-container", if_match="etag", if_none_match=True)
        with pytest.raises(ConfigurationError):
            AzureBlobCredentials(account_url="http://acct.blob.core.windows.net", customer_provided_key=Secret(base64.b64encode(b"k" * 32).decode("ascii")))


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


def _make_s3_sink(monkeypatch: pytest.MonkeyPatch, client: FakeS3Client, *, config: S3SinkConfig | None = None, credentials: S3Credentials | None = None) -> S3TrajectorySink:
    # Constructs a real S3TrajectorySink wired to a fake boto3 driver instead of the real package.
    monkeypatch.setattr(S3TrajectorySink, "_import_driver", staticmethod(lambda: _fake_s3_driver(client)))
    return S3TrajectorySink(config or S3SinkConfig(bucket="acme-bucket", prefix="runs"), credentials=credentials)


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
    async def test_write_maps_s3_object_controls_and_compression(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        config = S3SinkConfig(
            bucket="acme-bucket",
            tags={"team": "fin ops"},
            metadata={"lineage": "trajectory"},
            content_type="application/x-ndjson",
            content_encoding="gzip",
            cache_control="max-age=60",
            content_disposition="attachment; filename=run.jsonl.gz",
            sse="aws:kms",
            kms_key_id="arn:aws:kms:us-east-1:123456789012:key/example",
            bucket_key_enabled=True,
            kms_encryption_context={"purpose": "audit"},
            object_lock_mode="GOVERNANCE",
            object_lock_retain_until_date=datetime(2026, 9, 3, tzinfo=timezone.utc),
            object_lock_legal_hold_status="ON",
            if_none_match="*",
            acl="bucket-owner-full-control",
            grant_read="id=abc",
            grant_read_acp="id=abc",
            grant_write_acp="id=abc",
            checksum_algorithm="SHA256",
            content_md5=base64.b64encode(hashlib.md5(b"content", usedforsecurity=False).digest()).decode("ascii"),
            request_payer="requester",
            use_dualstack_endpoint=True,
            expires=datetime(2026, 9, 4, tzinfo=timezone.utc),
            website_redirect_location="https://example.test/redirect",
        )
        sink = _make_s3_sink(monkeypatch, client, config=config)
        await sink.write(_record(output="repeated " * 100))
        call = client.put_object_calls[0]
        assert call["Tagging"] == "team=fin+ops"
        assert call["Metadata"] == {"lineage": "trajectory"}
        assert call["ContentEncoding"] == "gzip"
        assert gzip.decompress(call["Body"]).startswith(b"{")
        assert call["ServerSideEncryption"] == "aws:kms"
        assert call["BucketKeyEnabled"] is True
        assert base64.b64decode(call["SSEKMSEncryptionContext"]) == b'{"purpose":"audit"}'
        assert call["ObjectLockMode"] == "GOVERNANCE"
        assert call["IfNoneMatch"] == "*"
        assert call["ChecksumAlgorithm"] == "SHA256"
        assert call["WebsiteRedirectLocation"] == "https://example.test/redirect"

    @pytest.mark.asyncio
    async def test_write_maps_s3_dsse(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        sink = _make_s3_sink(
            monkeypatch,
            client,
            config=S3SinkConfig(
                bucket="acme-bucket",
                sse="aws:kms:dsse",
                kms_key_id="arn:aws:kms:us-east-1:123456789012:key/example",
            ),
        )
        await sink.write(_record())
        assert client.put_object_calls[0]["ServerSideEncryption"] == "aws:kms:dsse"

    @pytest.mark.asyncio
    async def test_write_maps_s3_customer_provided_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        sink = _make_s3_sink(
            monkeypatch,
            client,
            config=S3SinkConfig(bucket="acme-bucket", sse_customer_algorithm="AES256"),
            credentials=S3Credentials(sse_customer_key=Secret(b"k" * 32)),
        )
        await sink.write(_record())
        call = client.put_object_calls[0]
        assert call["SSECustomerAlgorithm"] == "AES256"
        assert call["SSECustomerKey"] == b"k" * 32
        assert base64.b64decode(call["SSECustomerKeyMD5"]) == hashlib.md5(b"k" * 32, usedforsecurity=False).digest()

    @pytest.mark.asyncio
    async def test_size_guard_runs_before_s3_preflight(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        sink = _make_s3_sink(monkeypatch, client)
        with pytest.raises(HarnessSinkPayloadError):
            await sink.write(_record(output="x" * (MAX_TRAJECTORY_RECORD_BYTES + 1)))
        assert client.head_bucket_calls == []

    def test_s3_endpoint_flags_reach_botocore_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeS3Client()
        driver = _fake_s3_driver(client)
        monkeypatch.setattr(S3TrajectorySink, "_import_driver", staticmethod(lambda: driver))
        S3TrajectorySink(S3SinkConfig(bucket="acme-bucket", use_accelerate_endpoint=True))
        config = next(kwargs["config"] for name, kwargs in driver.boto3.client_calls if name == "s3")
        assert config["s3"] == {"use_accelerate_endpoint": True}

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
        self.metadata: dict[str, str] | None = None
        self.cache_control: str | None = None
        self.content_disposition: str | None = None
        self.content_encoding: str | None = None
        self.event_based_hold: bool | None = None
        self.temporary_hold: bool | None = None
        self.retention = SimpleNamespace(mode=None, retain_until_time=None)
        self.upload_kwargs: dict[str, Any] = {}

    def upload_from_string(self, payload: bytes, **kwargs: Any) -> None:
        if self._upload_error is not None:
            raise self._upload_error
        self.uploaded_payload = payload
        self.upload_kwargs = kwargs


class FakeGcsBucket:
    def __init__(self, upload_error: Exception | None) -> None:
        self._upload_error = upload_error
        self.blobs: list[FakeGcsBlob] = []
        self.blob_kwargs: list[dict[str, Any]] = []

    def blob(self, key: str, **kwargs: Any) -> FakeGcsBlob:
        blob = FakeGcsBlob(self._upload_error)
        self.blobs.append(blob)
        self.blob_kwargs.append(kwargs)
        return blob


class FakeGcsClient:
    def __init__(self) -> None:
        self.get_bucket_error: Exception | None = None
        self.upload_error: Exception | None = None
        self.bucket_instance: FakeGcsBucket | None = None
        self.preflight_bucket = SimpleNamespace(retention_period=None, patch=lambda: None)
        self.get_bucket_calls: list[str] = []

    def get_bucket(self, name: str, **kwargs: Any) -> Any:
        self.get_bucket_calls.append(name)
        if self.get_bucket_error is not None:
            raise self.get_bucket_error
        return self.preflight_bucket

    def bucket(self, name: str, **kwargs: Any) -> FakeGcsBucket:
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
        PreconditionFailed=type("PreconditionFailed", (_FakeGcsApiError,), {}),
        TooManyRequests=type("TooManyRequests", (_FakeGcsApiError,), {}),
        ServiceUnavailable=type("ServiceUnavailable", (_FakeGcsApiError,), {}),
        DeadlineExceeded=type("DeadlineExceeded", (_FakeGcsApiError,), {}),
    )


def _make_gcs_sink(monkeypatch: pytest.MonkeyPatch, client: FakeGcsClient, *, config: GcsSinkConfig | None = None, credentials: GcsCredentials | None = None) -> GcsTrajectorySink:
    driver = _fake_gcs_driver(client)
    monkeypatch.setattr(GcsTrajectorySink, "_import_driver", staticmethod(lambda: driver))
    sink = GcsTrajectorySink(config or GcsSinkConfig(bucket="acme-bucket"), credentials=credentials)
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
    async def test_write_maps_gcs_metadata_controls_conditions_checksum_and_compression(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeGcsClient()
        config = GcsSinkConfig(
            bucket="acme-bucket",
            metadata={"lineage": "trajectory", "team": "finops"},
            content_encoding="gzip",
            cache_control="no-store",
            content_disposition="attachment; filename=run.jsonl.gz",
            if_generation_match=0,
            if_metageneration_match=1,
            checksum="crc32c",
            predefined_acl="bucketOwnerFullControl",
            user_project="billing-project",
        )
        sink = _make_gcs_sink(monkeypatch, client, config=config)
        await sink.write(_record(output="repeated " * 100))
        assert client.bucket_instance is not None
        blob = client.bucket_instance.blobs[0]
        assert blob.metadata == {"lineage": "trajectory", "team": "finops"}
        assert blob.content_encoding == "gzip"
        assert blob.cache_control == "no-store"
        assert blob.content_disposition == "attachment; filename=run.jsonl.gz"
        assert gzip.decompress(blob.uploaded_payload or b"").startswith(b"{")
        assert blob.upload_kwargs["if_generation_match"] == 0
        assert blob.upload_kwargs["if_metageneration_match"] == 1
        assert blob.upload_kwargs["checksum"] == "crc32c"
        assert blob.upload_kwargs["predefined_acl"] == "bucketOwnerFullControl"

    @pytest.mark.asyncio
    async def test_write_maps_gcs_customer_key_and_bucket_retention(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeGcsClient()
        config = GcsSinkConfig(bucket="acme-bucket", bucket_retention_period=3600)
        credentials = GcsCredentials(customer_supplied_encryption_key=Secret(b"k" * 32))
        sink = _make_gcs_sink(monkeypatch, client, config=config, credentials=credentials)
        await sink.write(_record())
        assert client.preflight_bucket.retention_period == 3600
        assert client.bucket_instance is not None
        assert client.bucket_instance.blob_kwargs[0]["encryption_key"] == b"k" * 32

    @pytest.mark.asyncio
    async def test_size_guard_runs_before_gcs_preflight(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = FakeGcsClient()
        sink = _make_gcs_sink(monkeypatch, client)
        with pytest.raises(HarnessSinkPayloadError):
            await sink.write(_record(output="x" * (MAX_TRAJECTORY_RECORD_BYTES + 1)))
        assert client.get_bucket_calls == []

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
    match_conditions = SimpleNamespace(IfNotModified="IfNotModified", IfMissing="IfMissing")
    return SimpleNamespace(
        BlobServiceClient=SimpleNamespace(from_connection_string=lambda *a, **k: client),
        ContentSettings=lambda **kwargs: kwargs,
        CustomerProvidedEncryptionKey=lambda **kwargs: kwargs,
        ImmutabilityPolicy=lambda **kwargs: kwargs,
        MatchConditions=match_conditions,
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
    async def test_write_maps_azure_metadata_tags_content_conditions_and_immutability(self, monkeypatch: pytest.MonkeyPatch) -> None:
        driver, service_client = _fake_azure_driver()
        monkeypatch.setattr(AzureBlobTrajectorySink, "_import_driver", staticmethod(lambda: driver))
        config = AzureBlobSinkConfig(
            container="acme-container",
            metadata={"lineage": "trajectory"},
            tags={"team": "finops"},
            content_encoding="gzip",
            cache_control="no-store",
            content_disposition="attachment; filename=run.jsonl.gz",
            content_md5=hashlib.md5(b"content", usedforsecurity=False).digest(),
            validate_content=True,
            if_match="etag-1",
            if_tags_match_condition='"team" = \'finops\'',
            immutability_policy_expiry_time=datetime(2026, 9, 3, tzinfo=timezone.utc),
            immutability_policy_mode="Locked",
            legal_hold=True,
        )
        credentials = AzureBlobCredentials(
            account_url="https://acct.blob.core.windows.net",
            connection_string=Secret("conn-str"),
            customer_provided_key=Secret(base64.b64encode(b"k" * 32).decode("ascii")),
        )
        sink = AzureBlobTrajectorySink(config, credentials=credentials)
        await sink.write(_record(output="repeated " * 100))
        call = service_client.last_blob_client.upload_calls[0]
        assert call["metadata"] == {"lineage": "trajectory"}
        assert call["tags"] == {"team": "finops"}
        assert call["overwrite"] is True
        assert call["etag"] == "etag-1"
        assert call["match_condition"] == "IfNotModified"
        assert call["if_tags_match_condition"] == '"team" = \'finops\''
        assert call["legal_hold"] is True
        assert call["validate_content"] is True
        assert call["immutability_policy"]["policy_mode"] == "Locked"
        assert call["cpk"]["key_value"] == base64.b64encode(b"k" * 32).decode("ascii")
        assert call["content_settings"]["content_encoding"] == "gzip"

    @pytest.mark.asyncio
    async def test_write_maps_azure_if_missing_condition(self, monkeypatch: pytest.MonkeyPatch) -> None:
        driver, service_client = _fake_azure_driver()
        monkeypatch.setattr(AzureBlobTrajectorySink, "_import_driver", staticmethod(lambda: driver))
        sink = AzureBlobTrajectorySink(
            AzureBlobSinkConfig(container="acme-container", if_none_match=True),
            credentials=AzureBlobCredentials(account_url="https://acct.blob.core.windows.net", connection_string=Secret("conn-str")),
        )
        await sink.write(_record())
        call = service_client.last_blob_client.upload_calls[0]
        assert call["overwrite"] is False
        assert call["etag"] == "*"
        assert call["match_condition"] == "IfMissing"

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
    async def test_event_attaches_complete_shared_sink_error_packet(self) -> None:
        events: list[SinkFailureEvent] = []
        error = HarnessSinkAuthorizationError("write denied", details={"provider": "s3"})
        harness = _loaded_harness(sink=_FailingSink(error), on_sink_error=events.append)
        await harness.execute({"topic": "x"})
        assert events[0].error["error_type"] == "HarnessSinkAuthorizationError"
        assert "description" in events[0].error
        assert "fix_approaches" in events[0].error
        assert events[0].error["details"] == {"provider": "s3"}

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
