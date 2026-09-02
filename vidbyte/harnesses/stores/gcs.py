"""FILE: vidbyte/harnesses/stores/gcs.py

PURPOSE:
    TrajectorySink backed by Google Cloud Storage. Writes one JSONL object per
    finished run, keyed by run_id, mirroring vidbyte/harnesses/stores/s3.py.

ROLE IN CODEBASE:
    Bound to a Harness via sink=sdk.harnesses.gcs_sink(...); receives one
    redacted TrajectoryRecord per run.

ARCHITECTURE NOTE:
    Mirrors s3.py exactly except for GCS-specific vocabulary: bucket/blob
    instead of bucket/key, storage_class instead of StorageClass, and
    Application Default Credentials (env var, gcloud login, or the GCE/GKE/
    Cloud Run metadata server — Workload Identity, keyless) as the default
    credential path when no service_account_json_path is given. The
    google-cloud-storage client is synchronous, same as boto3, so network
    calls run via asyncio.to_thread.

PUBLIC API INVENTORY:
    GcsTrajectorySink; verify(); write(record).

WHAT NOT TO DO IN THIS FILE:
    1. Do not import google.cloud.storage at module level; every symbol comes
       from the lazy _import_driver().
    2. Do not treat a NotFound as definitely "bucket does not exist" — GCS
       reports a missing-permission bucket as NotFound too, to avoid leaking
       bucket existence to an unauthorized caller; the raised error says so.
    3. Do not let a raw google.api_core exception escape write()/verify().

COMMON MODIFICATION PATTERNS:
    Add a new Config/Credentials field in
    vidbyte/lib/dataclasses/cloud_sinks.py first, then thread it through
    _build_client()/_put() here; add a new exception mapping in
    _translate_error().

KNOWN EDGE CASES:
    GCS reports NotFound for both a genuinely missing bucket and a
    permission-denied one, by design, to avoid leaking bucket existence to an
    unauthorized caller — _translate_error() names this ambiguity in the
    raised HarnessSinkSetupError rather than asserting which case occurred.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/cloud-trajectory-sinks.md

TESTS:
    tests/test_cloud_trajectory_sinks.py.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from vidbyte.harnesses.contracts import TrajectoryRecord
from vidbyte.harnesses.errors import (
    HarnessSinkAuthenticationError,
    HarnessSinkAuthorizationError,
    HarnessSinkError,
    HarnessSinkSetupError,
    HarnessSinkUnavailableError,
)
from vidbyte.harnesses.stores._sink_support import SinkEncoding
from vidbyte.lib.dataclasses.cloud_sinks import GcsCredentials, GcsSinkConfig
from vidbyte.lib.errors import ConfigurationError


class GcsTrajectorySink:
    """TrajectorySink writing one JSONL object per run to a Google Cloud Storage bucket."""

    def __init__(self, config: GcsSinkConfig, *, credentials: GcsCredentials | None = None) -> None:
        # Binds config/credentials, lazily imports google-cloud-storage, and eagerly builds the client.
        self._config = config
        self._credentials = credentials
        if config.kms_key_name is not None and credentials is not None and credentials.customer_supplied_encryption_key is not None:
            raise ConfigurationError("kms_key_name and customer_supplied_encryption_key are mutually exclusive.")
        self._driver = self._import_driver()
        self._client = self._build_client()
        self._verify_task: asyncio.Task[None] | None = None

    async def verify(self) -> None:
        # Explicit, caller-invoked preflight check — call before a long run to fail fast on setup/auth problems.
        await self._ensure_ready()

    async def write(self, record: TrajectoryRecord) -> None:
        # Encodes one record, guards its size, and uploads it as a single blob keyed by run_id.
        payload = SinkEncoding.prepare_payload(record, content_encoding=self._config.content_encoding)
        await self._ensure_ready()
        await self._put(self._object_key(record.run_id), payload)

    def _build_client(self) -> Any:
        # Constructs the google-cloud-storage client, using explicit service-account credentials when given.
        try:
            if self._credentials is not None and self._credentials.service_account_json_path is not None:
                resolved = self._driver.service_account.Credentials.from_service_account_file(self._credentials.service_account_json_path)
                return self._driver.storage.Client(credentials=resolved)
            return self._driver.storage.Client()
        except self._driver.DefaultCredentialsError as exc:
            raise self._translate_error(exc) from exc

    async def _ensure_ready(self) -> None:
        # Memoizes the preflight check as one shared task; the synchronous check-and-create between await points needs no lock, since asyncio only yields control at an await.
        if self._verify_task is None:
            self._verify_task = asyncio.ensure_future(self._run_preflight())
        await self._verify_task

    async def _run_preflight(self) -> None:
        # Confirms the bucket exists and is reachable before any write is attempted.
        try:
            if self._config.user_project is None:
                bucket = await asyncio.to_thread(self._client.get_bucket, self._config.bucket)
            else:
                bucket = await asyncio.to_thread(self._client.get_bucket, self._config.bucket, user_project=self._config.user_project)
            if self._config.bucket_retention_period is not None and bucket is not None:
                if getattr(bucket, "retention_period", None) != self._config.bucket_retention_period:
                    bucket.retention_period = self._config.bucket_retention_period
                    await asyncio.to_thread(bucket.patch)
        except Exception as exc:
            raise self._translate_error(exc) from exc

    def _object_key(self, run_id: str) -> str:
        # Builds "{prefix}/{run_id}.jsonl", or "{run_id}.jsonl" when prefix is empty.
        prefix = self._config.prefix.rstrip("/")
        return f"{prefix}/{run_id}.jsonl" if prefix else f"{run_id}.jsonl"

    # @intent preserve-gcs-object-contract
    # Keep Blob properties and upload preconditions explicit so warehouse metadata and generation safety survive refactors.
    async def _put(self, key: str, payload: bytes) -> None:
        try:
            blob = self._build_blob(key)
            self._configure_blob(blob)
            await asyncio.to_thread(blob.upload_from_string, payload, **self._upload_kwargs())
        except Exception as exc:
            raise self._translate_error(exc) from exc

    # @intent select-gcs-encryption-and-billing
    # Choose requester billing and exactly one of CMEK/customer-supplied encryption before upload.
    def _build_blob(self, key: str) -> Any:
        bucket_kwargs: dict[str, Any] = {}
        if self._config.user_project is not None:
            bucket_kwargs["user_project"] = self._config.user_project
        bucket = self._client.bucket(self._config.bucket, **bucket_kwargs)
        blob_kwargs: dict[str, Any] = {}
        if self._config.kms_key_name is not None:
            blob_kwargs["kms_key_name"] = self._config.kms_key_name
        if self._credentials is not None and self._credentials.customer_supplied_encryption_key is not None:
            encryption_key = self._credentials.customer_supplied_encryption_key.reveal()
            blob_kwargs["encryption_key"] = encryption_key if isinstance(encryption_key, bytes) else encryption_key.encode("utf-8")
        return bucket.blob(key, **blob_kwargs)

    # @intent preserve-gcs-object-properties
    # Assign metadata, cache headers, holds, and retention before the SDK creates the object.
    def _configure_blob(self, blob: Any) -> None:
        blob.storage_class = self._config.storage_class.value
        if self._config.metadata:
            blob.metadata = dict(self._config.metadata)
        if self._config.cache_control is not None:
            blob.cache_control = self._config.cache_control
        if self._config.content_disposition is not None:
            blob.content_disposition = self._config.content_disposition
        if self._config.content_encoding is not None:
            blob.content_encoding = self._config.content_encoding
        if self._config.event_based_hold is not None:
            blob.event_based_hold = self._config.event_based_hold
        if self._config.temporary_hold is not None:
            blob.temporary_hold = self._config.temporary_hold
        if self._config.retention_mode is not None and self._config.retain_until_time is not None:
            blob.retention.mode = self._config.retention_mode
            blob.retention.retain_until_time = self._config.retain_until_time

    # @intent preserve-gcs-upload-conditions
    # Return only configured upload fields, preserving GCS defaults for an unconfigured sink.
    def _upload_kwargs(self) -> dict[str, Any]:
        upload_kwargs: dict[str, Any] = {}
        if self._config.content_type is not None:
            upload_kwargs["content_type"] = self._config.content_type
        if self._config.checksum is not None:
            upload_kwargs["checksum"] = self._config.checksum
        for name in ("if_generation_match", "if_generation_not_match", "if_metageneration_match", "if_metageneration_not_match", "predefined_acl"):
            value = getattr(self._config, name)
            if value is not None:
                upload_kwargs[name] = value
        return upload_kwargs

    def _translate_error(self, exc: Exception) -> HarnessSinkError:
        # Maps a google-cloud-storage/google-auth exception to the specific HarnessSinkError subclass a caller can act on.
        if isinstance(exc, self._driver.DefaultCredentialsError):
            return HarnessSinkAuthenticationError(
                "No Application Default Credentials could be resolved. Run `gcloud auth application-default login`, set GOOGLE_APPLICATION_CREDENTIALS, or pass service_account_json_path explicitly.",
                details={"error_type": type(exc).__name__},
            )
        if isinstance(exc, self._driver.NotFound):
            return HarnessSinkSetupError(
                "GCS reported the bucket could not be resolved. This can also mean the credentials lack permission on it — GCS reports both cases as NotFound to avoid leaking bucket existence.",
                details={"bucket": self._config.bucket},
            )
        if isinstance(exc, self._driver.PreconditionFailed):
            return HarnessSinkAuthorizationError(
                "GCS rejected the conditional write because the object's generation or metageneration did not match.",
                details={"bucket": self._config.bucket},
            )
        if isinstance(exc, (self._driver.Forbidden, self._driver.Unauthorized)):
            return HarnessSinkAuthorizationError(
                "GCS denied this write. If this bucket uses a customer-managed encryption key, confirm kms_key_name is set and the identity has roles/cloudkms.cryptoKeyEncrypterDecrypter on it.",
                details={"bucket": self._config.bucket, "error_type": type(exc).__name__},
            )
        if isinstance(exc, (self._driver.TooManyRequests, self._driver.ServiceUnavailable, self._driver.DeadlineExceeded)):
            return HarnessSinkUnavailableError("GCS was unavailable after the client library's own retries were exhausted.", details={"error_type": type(exc).__name__})
        return HarnessSinkError("GCS request failed for an unrecognized reason.", details={"error_type": type(exc).__name__})

    @staticmethod
    def _import_driver() -> Any:
        # Lazily imports google-cloud-storage and the exception types this sink translates, raising a helpful error when absent.
        try:
            from google.api_core.exceptions import DeadlineExceeded, Forbidden, NotFound, PreconditionFailed, ServiceUnavailable, TooManyRequests, Unauthorized
            from google.auth.exceptions import DefaultCredentialsError
            from google.cloud import storage
            from google.oauth2 import service_account
        except ImportError as exc:
            raise ConfigurationError("GcsTrajectorySink requires the 'google-cloud-storage' package. Install it with `pip install google-cloud-storage`.") from exc
        return SimpleNamespace(
            storage=storage,
            service_account=service_account,
            DefaultCredentialsError=DefaultCredentialsError,
            NotFound=NotFound,
            Forbidden=Forbidden,
            Unauthorized=Unauthorized,
            PreconditionFailed=PreconditionFailed,
            TooManyRequests=TooManyRequests,
            ServiceUnavailable=ServiceUnavailable,
            DeadlineExceeded=DeadlineExceeded,
        )


__all__ = ["GcsTrajectorySink"]
