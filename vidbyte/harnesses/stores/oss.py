"""FILE: vidbyte/harnesses/stores/oss.py

PURPOSE:
    Export one redacted trajectory record per JSONL object to Alibaba Cloud
    Object Storage Service with keyless/default or temporary credentials,
    object classes, SSE-KMS, CRC64 integrity, conditional writes, resumable
    multipart upload, and checkpoint recovery.

ROLE IN CODEBASE:
    Selected by `HarnessClient.oss_sink()` and connected to the unchanged
    `TrajectorySink` protocol through CloudTrajectorySinkMixin.

ARCHITECTURE NOTE:
    Alibaba OSS SDK v2 is synchronous and optional. It is imported only while
    constructing a sink; all SDK calls run in worker threads. The SDK's
    Uploader owns multipart concurrency, per-part recovery, and checkpoint
    files. The adapter never implements a second retry loop.

PUBLIC API INVENTORY:
    OssTrajectorySink.

COMMON MODIFICATION PATTERNS:
    Add object settings to OssSinkConfig first, then map them into the SDK
    request model. Keep credential-provider construction in `_build_client()`
    and error classification in `_translate_error()`.

WHAT NOT TO DO:
    Do not import `alibabacloud_oss_v2` at module import time, expose secrets
    in errors, or mutate bucket lifecycle, retention, replication, or policy.

KNOWN EDGE CASES:
    Checkpoint files contain resumable transfer state and must live on a
    private, durable local path. A write probe requires delete permission.
    CRC64 is the SDK's native upload integrity mechanism; the adapter leaves
    it enabled and surfaces the SDK's response checksum in its receipt.

RELATED DOCS:
    docs/design/cloud-trajectory-provider-expansion.md

TESTS:
    tests/features/cloud_trajectory_provider_expansion/test_adapters.py
    tests/features/cloud_trajectory_provider_expansion/test_resilience.py
"""

from __future__ import annotations

import asyncio
from io import BytesIO
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from vidbyte.harnesses.contracts import TrajectoryRecord
from vidbyte.harnesses.errors import (
    HarnessSinkAuthenticationError,
    HarnessSinkAuthorizationError,
    HarnessSinkError,
    HarnessSinkSetupError,
    HarnessSinkUnavailableError,
)
from vidbyte.harnesses.stores._cloud_common import CloudTrajectorySinkMixin, SinkWriteReceipt, make_receipt, pair_mapping
from vidbyte.lib.constants.cloud_sinks import MIN_PROVIDER_ATTEMPTS
from vidbyte.lib.dataclasses.cloud_sinks import OssAuthMode, OssCredentials, OssSinkConfig, SinkOverwriteMode
from vidbyte.lib.errors import ConfigurationError

_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_NOT_FOUND = 404
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_SERVER_ERROR_THRESHOLD = 500


class OssTrajectorySink(CloudTrajectorySinkMixin):
    """Trajectory sink for Alibaba Cloud OSS."""

    def __init__(self, config: OssSinkConfig, *, credentials: OssCredentials | None = None) -> None:
        self._config = config
        self._credentials = credentials or OssCredentials()
        self._driver = self._import_driver()
        self._client = self._build_client()
        self._initialize_cloud_lifecycle("oss")

    async def write(self, record: TrajectoryRecord) -> None:
        """Encode and upload one record through the shared cloud lifecycle."""
        await super().write(record)

    async def write_with_receipt(self, record: TrajectoryRecord) -> SinkWriteReceipt:
        """Return the safe OSS acknowledgement for one uploaded record."""
        return await super().write_with_receipt(record)

    def _build_client(self) -> Any:
        # @intent reveal-secret-only-at-client-construction
        # Secret values are handed directly to the SDK credential provider;
        # they are never copied into a config repr or diagnostic context.
        try:
            provider = self._credentials_provider()
            sdk_config = self._driver.config.Config(
                region=self._config.region,
                endpoint=self._config.endpoint_url,
                credentials_provider=provider,
                retry_max_attempts=max(MIN_PROVIDER_ATTEMPTS, self._config.max_retries + MIN_PROVIDER_ATTEMPTS),
                connect_timeout=self._config.connect_timeout_seconds,
                readwrite_timeout=self._config.read_timeout_seconds,
                disable_upload_crc64_check=False,
            )
            return self._driver.Client(sdk_config)
        except Exception as exc:
            raise self._translate_error(exc, during_setup=True) from exc

    def _credentials_provider(self) -> Any:
        # @intent secret-enters-oss-provider-once
        # The SDK receives a secret provider, while the sink keeps only the
        # masked Secret wrapper and never places values in diagnostics.
        mode = self._credentials.auth_mode
        if mode is OssAuthMode.DEFAULT:
            return None
        if mode in (OssAuthMode.STATIC, OssAuthMode.STS):
            access_key_secret = self._credentials.access_key_secret
            if self._credentials.access_key_id is None or access_key_secret is None:
                raise ConfigurationError("Alibaba OSS explicit auth requires access_key_id and access_key_secret.")
            return self._driver.credentials.StaticCredentialsProvider(
                self._credentials.access_key_id,
                access_key_secret.reveal(),
                self._credentials.security_token.reveal() if self._credentials.security_token is not None else None,
            )
        raise ConfigurationError("Unsupported Alibaba OSS authentication mode.")

    async def _run_metadata_preflight(self) -> None:
        """Verify that the configured bucket can be resolved and read."""
        # @intent metadata-preflight-does-not-mutate
        # GetBucketInfo detects setup and authorization errors without leaving
        # a marker object behind.
        try:
            request = self._driver.models.GetBucketInfoRequest(bucket=self._config.bucket)
            await asyncio.to_thread(self._client.get_bucket_info, request)
        except Exception as exc:
            raise self._translate_error(exc) from exc

    async def _run_write_probe(self) -> None:
        """Exercise write and delete permissions using a unique reserved key."""
        # @intent write-probe-is-explicit
        # Probe mode is opt-in because it requires both write and delete grant.
        key = f"{self._object_key('preflight')}-{uuid4().hex}.jsonl"
        await self._put_single(key, b"{}\n")
        try:
            request = self._driver.models.DeleteObjectRequest(bucket=self._config.bucket, key=key)
            await asyncio.to_thread(self._client.delete_object, request)
        except Exception as exc:
            raise self._translate_error(exc) from exc

    async def _put_record(self, key: str, payload: bytes) -> SinkWriteReceipt:
        if len(payload) >= self._config.multipart_threshold_bytes:
            return await self._put_multipart(key, payload)
        return await self._put_single(key, payload)

    async def _put_single(self, key: str, payload: bytes) -> SinkWriteReceipt:
        # @intent oss-single-put-is-atomic
        # The native PutObject call is the smallest operation that preserves
        # the requested overwrite and encryption semantics.
        try:
            request = self._request(key, BytesIO(payload))
            response = await asyncio.to_thread(self._client.put_object, request)
        except Exception as exc:
            raise self._translate_error(exc) from exc
        return make_receipt("oss", key, payload, response)

    async def _put_multipart(self, key: str, payload: bytes) -> SinkWriteReceipt:
        # @intent oss-uploader-owns-recovery
        # Alibaba's Uploader owns parallel parts, retries, cleanup, and the
        # optional checkpoint journal.
        try:
            request = self._request(key, None)
            kwargs: dict[str, Any] = {
                "part_size": self._config.multipart_part_size_bytes,
                "parallel_num": self._config.multipart_max_concurrency,
                "leave_parts_on_error": False,
            }
            if self._config.checkpoint_dir is not None:
                kwargs.update({"enable_checkpoint": True, "checkpoint_dir": self._config.checkpoint_dir})
            uploader = self._client.uploader(**kwargs)
            response = await asyncio.to_thread(uploader.upload_from, request, BytesIO(payload))
        except Exception as exc:
            raise self._translate_error(exc) from exc
        return make_receipt("oss", key, payload, response)

    def _request(self, key: str, body: Any) -> Any:
        # @intent request-model-is-the-credential-boundary
        # This model contains object metadata only; credentials stay on the
        # client provider and never enter request diagnostics.
        metadata = pair_mapping(self._config.metadata)
        kwargs: dict[str, Any] = {
            "bucket": self._config.bucket,
            "key": key,
            "storage_class": self._config.storage_class.value,
            "metadata": metadata or None,
            "content_type": self._config.content_type,
            "tagging": urlencode(pair_mapping(self._config.tags)) or None,
            "forbid_overwrite": self._config.overwrite_mode is SinkOverwriteMode.CREATE_ONLY,
            "body": body,
        }
        if self._config.server_side_encryption is not None:
            kwargs["server_side_encryption"] = self._config.server_side_encryption
        if self._config.kms_key_id is not None:
            kwargs["server_side_encryption_key_id"] = self._config.kms_key_id
        if self._config.object_worm_retain_until is not None:
            kwargs["object_worm_retain_until_date"] = self._config.object_worm_retain_until.isoformat()
        if self._config.object_worm_mode is not None:
            kwargs["object_worm_mode"] = self._config.object_worm_mode
        if self._config.object_worm_legal_hold is not None:
            kwargs["object_worm_legal_hold"] = self._config.object_worm_legal_hold
        return self._driver.models.PutObjectRequest(**kwargs)

    def _translate_error(self, exc: Exception, *, during_setup: bool = False) -> HarnessSinkError:
        """Map Alibaba OSS exceptions without exposing request bodies or secrets."""
        if isinstance(exc, self._driver.CredentialsError):
            return HarnessSinkAuthenticationError("Alibaba OSS credentials could not be resolved.", details={"provider": "oss", "error_type": type(exc).__name__})
        if isinstance(exc, self._driver.ServiceError):
            status = getattr(exc, "status_code", None)
            if status == _HTTP_UNAUTHORIZED:
                return HarnessSinkAuthenticationError("Alibaba OSS rejected the configured credentials.", details={"provider": "oss", "status_code": status})
            if status == _HTTP_FORBIDDEN:
                return HarnessSinkAuthorizationError("Alibaba OSS denied access to the configured bucket or object.", details={"provider": "oss", "status_code": status})
            if status == _HTTP_NOT_FOUND:
                return HarnessSinkSetupError("Alibaba OSS could not resolve the configured bucket.", details={"provider": "oss", "status_code": status})
            if status == _HTTP_TOO_MANY_REQUESTS or (status is not None and status >= _HTTP_SERVER_ERROR_THRESHOLD):
                return HarnessSinkUnavailableError("Alibaba OSS was unavailable after the SDK retry policy was exhausted.", details={"provider": "oss", "status_code": status})
            return HarnessSinkError("Alibaba OSS rejected the object request.", details={"provider": "oss", "status_code": status, "code": getattr(exc, "code", None)})
        if isinstance(exc, (self._driver.RequestError, self._driver.ResponseError)):
            return HarnessSinkUnavailableError("Could not reach or parse the configured Alibaba OSS endpoint.", details={"provider": "oss", "error_type": type(exc).__name__})
        if during_setup:
            return HarnessSinkSetupError("Alibaba OSS client setup failed.", details={"provider": "oss", "error_type": type(exc).__name__})
        return HarnessSinkError("Alibaba OSS request failed for an unrecognized reason.", details={"provider": "oss", "error_type": type(exc).__name__})

    @staticmethod
    def _import_driver() -> Any:
        """Load Alibaba OSS SDK symbols lazily."""
        try:
            import alibabacloud_oss_v2 as oss
            from alibabacloud_oss_v2 import credentials, exceptions, models
        except ImportError as exc:
            raise ConfigurationError("OssTrajectorySink requires the 'alibabacloud-oss-v2' package. Install it with `pip install alibabacloud-oss-v2`.") from exc
        return SimpleNamespace(
            Client=oss.Client,
            ClientError=exceptions.BaseError,
            CredentialsError=exceptions.CredentialsBaseError,
            RequestError=exceptions.RequestError,
            ResponseError=exceptions.ResponseError,
            ServiceError=exceptions.ServiceError,
            config=oss.config,
            credentials=credentials,
            models=models,
        )


__all__ = ["OssTrajectorySink"]
