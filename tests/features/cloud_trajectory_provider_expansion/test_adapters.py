"""FILE: tests/features/cloud_trajectory_provider_expansion/test_adapters.py

PURPOSE:
    Verify provider request mapping, native transfer managers, receipts, and
    optional SDK seams without network access.

ROLE IN CODEBASE:
    Adapter/component layer of the cloud trajectory provider feature pack.

ARCHITECTURE NOTE:
    Provider-shaped fakes model only documented SDK entry points. Assertions
    focus on observable requests and receipts, not incidental implementation
    call order.

COMMON MODIFICATION PATTERNS:
    Extend the relevant fake when adding an object-level provider feature and
    assert its safe request representation or receipt field.

KNOWN EDGE CASES:
    Large payloads select native multipart managers, create-only writes carry
    a conditional request, and optional SDKs remain lazy at module import.

RELATED DOCS:
    docs/design/cloud-trajectory-provider-expansion.md

TESTS:
    Run with scripts/test-cloud-trajectory-provider-expansion.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from vidbyte.harnesses.contracts import HARNESS_SCHEMA_VERSION, TrajectoryRecord
from vidbyte.harnesses.stores.oci import OciTrajectorySink
from vidbyte.harnesses.stores.oss import OssTrajectorySink
from vidbyte.lib.dataclasses.cloud_sinks import (
    OciSinkConfig,
    OssSinkConfig,
    S3CompatibleProvider,
    S3SinkConfig,
    Secret,
    SinkOverwriteMode,
)
from vidbyte.harnesses.stores.s3 import S3TrajectorySink


def _record(run_id: str = "run-adapter") -> TrajectoryRecord:
    return TrajectoryRecord(schema_version=HARNESS_SCHEMA_VERSION, run_id=run_id, task="task", spec={}, agents=(), output={"ok": True}, status="succeeded", reward=None, created_at="2026-09-02T00:00:00+00:00")


class FakeOciClient:
    def __init__(self) -> None:
        self.bucket_calls = 0
        self.put_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.delete_calls: list[tuple[Any, ...]] = []

    def get_bucket(self, *args: Any, **kwargs: Any) -> None:
        self.bucket_calls += 1

    def put_object(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        self.put_calls.append((args, kwargs))
        return SimpleNamespace(etag="oci-etag", headers={"opc-request-id": "oci-request"})

    def delete_object(self, *args: Any, **kwargs: Any) -> None:
        self.delete_calls.append(args)


class FakeOciUploadManager:
    calls: list[dict[str, Any]] = []

    def __init__(self, client: FakeOciClient, **kwargs: Any) -> None:
        self.client = client
        self.kwargs = kwargs

    def upload_stream(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        self.__class__.calls.append({"args": args, "kwargs": kwargs, "manager": self.kwargs})
        return SimpleNamespace(etag="oci-multipart-etag", headers={"opc-request-id": "oci-multipart-request"})


class FakeOciModels:
    class GetBucketInfoRequest:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    class DeleteObjectRequest:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs


class FakeOciRetryBuilder:
    def add_max_attempts(self, attempts: int) -> "FakeOciRetryBuilder":
        self.attempts = attempts
        return self

    def get_retry_strategy(self) -> str:
        return f"retry-{self.attempts}"


def _oci_driver(client: FakeOciClient) -> SimpleNamespace:
    class FakeClient:
        def __new__(cls, config: Any, **kwargs: Any) -> FakeOciClient:
            client.config = config
            client.client_kwargs = kwargs
            return client

        def __init__(self, config: Any, **kwargs: Any) -> None:
            pass

    config = SimpleNamespace(from_file=lambda **kwargs: {"region": "us-phoenix-1", **kwargs})
    retry = SimpleNamespace(RetryStrategyBuilder=FakeOciRetryBuilder)
    signers = SimpleNamespace(
        SecurityTokenSigner=lambda token: ("security-token", token),
        InstancePrincipalsSecurityTokenSigner=lambda: "instance-principal",
        get_resource_principals_signer=lambda: "resource-principal",
        get_oke_workload_identity_resource_principal_signer=lambda: "oke-principal",
    )
    return SimpleNamespace(
        ClientError=type("ClientError", (Exception,), {}),
        ConfigFileNotFound=type("ConfigFileNotFound", (Exception,), {}),
        ConnectTimeout=type("ConnectTimeout", (Exception,), {}),
        InvalidConfig=type("InvalidConfig", (Exception,), {}),
        ObjectStorageClient=FakeClient,
        ProfileNotFound=type("ProfileNotFound", (Exception,), {}),
        RequestException=type("RequestException", (Exception,), {}),
        ServiceError=type("ServiceError", (Exception,), {}),
        Signer=lambda *args, **kwargs: (args, kwargs),
        UploadManager=FakeOciUploadManager,
        config=config,
        retry=retry,
        signers=signers,
    )


@pytest.mark.asyncio
async def test_oci_upload_maps_object_options_and_returns_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeOciClient()
    driver = _oci_driver(client)
    monkeypatch.setattr(OciTrajectorySink, "_import_driver", staticmethod(lambda: driver))
    sink = OciTrajectorySink(OciSinkConfig(bucket="oci-bucket", namespace="namespace", prefix="exports", vault_kms_key_id="kms", checksum_algorithm="SHA256", overwrite_mode=SinkOverwriteMode.CREATE_ONLY, metadata={"team": "eval"}, tags={"env": "test"}))

    receipt = await sink.write_with_receipt(_record())

    assert receipt.provider == "oci"
    assert receipt.etag == "oci-etag"
    request = client.put_calls[0][1]
    assert request["opc_sse_kms_key_id"] == "kms"
    assert request["opc_checksum_algorithm"] == "SHA256"
    assert request["if_none_match"] == "*"
    assert request["opc_meta"] == {"team": "eval", "tag-env": "test"}


@pytest.mark.asyncio
async def test_oci_large_upload_uses_native_upload_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeOciClient()
    driver = _oci_driver(client)
    FakeOciUploadManager.calls.clear()
    monkeypatch.setattr(OciTrajectorySink, "_import_driver", staticmethod(lambda: driver))
    sink = OciTrajectorySink(OciSinkConfig(bucket="oci-bucket", namespace="namespace", multipart_threshold_bytes=0))

    await sink.write(_record())

    assert FakeOciUploadManager.calls[0]["kwargs"]["part_size"] == sink._config.multipart_part_size_bytes
    assert client.put_calls == []


class FakeOssClient:
    def __init__(self, config: Any = None) -> None:
        self.config = config
        self.put_requests: list[Any] = []
        self.bucket_requests: list[Any] = []
        self.delete_requests: list[Any] = []
        self.uploader_kwargs: dict[str, Any] | None = None

    def get_bucket_info(self, request: Any) -> SimpleNamespace:
        self.bucket_requests.append(request)
        return SimpleNamespace()

    def put_object(self, request: Any) -> SimpleNamespace:
        self.put_requests.append(request)
        return SimpleNamespace(etag="oss-etag", version_id="version-1", hash_crc64="crc64", request_id="oss-request")

    def delete_object(self, request: Any) -> None:
        self.delete_requests.append(request)

    def uploader(self, **kwargs: Any) -> "FakeOssUploader":
        self.uploader_kwargs = kwargs
        return FakeOssUploader()


class FakeOssUploader:
    def upload_from(self, request: Any, reader: Any) -> SimpleNamespace:
        return SimpleNamespace(etag="oss-multipart-etag", hash_crc64="crc64-multipart", request_id="oss-multipart-request")


class FakeOssModels:
    class PutObjectRequest:
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

    class GetBucketInfoRequest:
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

    class DeleteObjectRequest:
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)


def _oss_driver(client: FakeOssClient) -> SimpleNamespace:
    class FakeConfig:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    class FakeClient:
        def __new__(cls, config: Any) -> FakeOssClient:
            client.config = config
            return client

    class StaticCredentialsProvider:
        def __init__(self, *args: Any) -> None:
            self.args = args

    base_error = type("BaseError", (Exception,), {})
    return SimpleNamespace(
        Client=FakeClient,
        CredentialsError=type("CredentialsBaseError", (base_error,), {}),
        RequestError=type("RequestError", (base_error,), {}),
        ResponseError=type("ResponseError", (base_error,), {}),
        ServiceError=type("ServiceError", (base_error,), {}),
        config=SimpleNamespace(Config=FakeConfig),
        credentials=SimpleNamespace(StaticCredentialsProvider=StaticCredentialsProvider),
        models=FakeOssModels,
    )


@pytest.mark.asyncio
async def test_oss_upload_maps_encryption_tags_and_crc_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeOssClient()
    driver = _oss_driver(client)
    monkeypatch.setattr(OssTrajectorySink, "_import_driver", staticmethod(lambda: driver))
    sink = OssTrajectorySink(OssSinkConfig(bucket="oss-bucket", region="cn-hangzhou", server_side_encryption="KMS", kms_key_id="kms", metadata={"team": "eval"}, tags={"env": "test"}), credentials=None)

    receipt = await sink.write_with_receipt(_record())

    assert receipt.provider == "oss"
    assert receipt.checksum == "crc64"
    request = client.put_requests[0]
    assert request.server_side_encryption == "KMS"
    assert request.server_side_encryption_key_id == "kms"
    assert request.tagging == "env=test"
    assert request.metadata == {"team": "eval"}


@pytest.mark.asyncio
async def test_oss_large_upload_uses_checkpointed_native_uploader(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeOssClient()
    driver = _oss_driver(client)
    monkeypatch.setattr(OssTrajectorySink, "_import_driver", staticmethod(lambda: driver))
    sink = OssTrajectorySink(OssSinkConfig(bucket="oss-bucket", region="cn-hangzhou", multipart_threshold_bytes=0, checkpoint_dir="private-checkpoints"))

    receipt = await sink.write_with_receipt(_record())

    assert receipt.etag == "oss-multipart-etag"
    assert client.uploader_kwargs == {"part_size": sink._config.multipart_part_size_bytes, "parallel_num": sink._config.multipart_max_concurrency, "leave_parts_on_error": False, "enable_checkpoint": True, "checkpoint_dir": "private-checkpoints"}


class FakeS3MultipartClient:
    def __init__(self) -> None:
        self.create_requests: list[dict[str, Any]] = []
        self.parts: list[int] = []
        self.completed: list[dict[str, Any]] = []
        self.single_requests: list[dict[str, Any]] = []

    def create_multipart_upload(self, **kwargs: Any) -> dict[str, str]:
        self.create_requests.append(kwargs)
        return {"UploadId": "upload-1"}

    def upload_part(self, **kwargs: Any) -> dict[str, str]:
        self.parts.append(kwargs["PartNumber"])
        return {"ETag": f"etag-{kwargs['PartNumber']}"}

    def complete_multipart_upload(self, **kwargs: Any) -> SimpleNamespace:
        self.completed.append(kwargs)
        return SimpleNamespace(etag="multipart-etag")

    def put_object(self, **kwargs: Any) -> SimpleNamespace:
        self.single_requests.append(kwargs)
        return SimpleNamespace(etag="single-etag")


@pytest.mark.asyncio
async def test_s3_multipart_upload_is_bounded_and_returns_ordered_parts() -> None:
    client = FakeS3MultipartClient()
    sink = object.__new__(S3TrajectorySink)
    sink._config = S3SinkConfig(bucket="acme-bucket", multipart_threshold_bytes=0, multipart_part_size_bytes=5 * 1024 * 1024, multipart_max_concurrency=2)
    sink._client = client
    sink._driver = SimpleNamespace()

    receipt = await sink._put_record("exports/run.jsonl", b"x" * (10 * 1024 * 1024 + 1))

    assert receipt.etag == "multipart-etag"
    assert client.parts == [1, 2, 3]
    assert [part["PartNumber"] for part in client.completed[0]["MultipartUpload"]["Parts"]] == [1, 2, 3]


@pytest.mark.asyncio
async def test_s3_create_only_uses_atomic_conditional_put_even_above_threshold() -> None:
    client = FakeS3MultipartClient()
    sink = object.__new__(S3TrajectorySink)
    sink._config = S3SinkConfig(bucket="acme-bucket", multipart_threshold_bytes=0, overwrite_mode=SinkOverwriteMode.CREATE_ONLY)
    sink._client = client
    sink._driver = SimpleNamespace()

    await sink._put_record("run.jsonl", b"record")

    assert client.single_requests[0]["IfNoneMatch"] == "*"
    assert client.create_requests == []
