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
        self._driver = self._import_driver()
        self._client = self._build_client()
        self._verified = False
        self._verify_lock = asyncio.Lock()

    async def verify(self) -> None:
        # Explicit, caller-invoked preflight check — call before a long run to fail fast on setup/auth problems.
        await self._run_preflight()
        self._verified = True

    async def write(self, record: TrajectoryRecord) -> None:
        # Encodes one record, guards its size, and uploads it as a single blob keyed by run_id.
        await self._ensure_ready()
        payload = SinkEncoding.encode_record(record)
        SinkEncoding.guard_size(payload, run_id=record.run_id)
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
        # Runs the preflight check once per instance, guarded so concurrent first-writes don't double-check.
        if self._verified:
            return
        async with self._verify_lock:
            if self._verified:
                return
            await self._run_preflight()
            self._verified = True

    async def _run_preflight(self) -> None:
        # Confirms the bucket exists and is reachable before any write is attempted.
        try:
            await asyncio.to_thread(self._client.get_bucket, self._config.bucket)
        except Exception as exc:
            raise self._translate_error(exc) from exc

    def _object_key(self, run_id: str) -> str:
        # Builds "{prefix}/{run_id}.jsonl", or "{run_id}.jsonl" when prefix is empty.
        prefix = self._config.prefix.rstrip("/")
        return f"{prefix}/{run_id}.jsonl" if prefix else f"{run_id}.jsonl"

    async def _put(self, key: str, payload: bytes) -> None:
        # Issues one atomic upload carrying the configured storage class and CMEK settings.
        try:
            bucket = self._client.bucket(self._config.bucket)
            blob = bucket.blob(key, kms_key_name=self._config.kms_key_name) if self._config.kms_key_name is not None else bucket.blob(key)
            blob.storage_class = self._config.storage_class.value
            await asyncio.to_thread(blob.upload_from_string, payload, content_type="application/x-ndjson")
        except Exception as exc:
            raise self._translate_error(exc) from exc

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
            from google.api_core.exceptions import DeadlineExceeded, Forbidden, NotFound, ServiceUnavailable, TooManyRequests, Unauthorized
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
            TooManyRequests=TooManyRequests,
            ServiceUnavailable=ServiceUnavailable,
            DeadlineExceeded=DeadlineExceeded,
        )


__all__ = ["GcsTrajectorySink"]
