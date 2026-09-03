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
    GcsTrajectorySink; verify(); write(record); write_with_receipt(); aclose().

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
    tests/test_cloud_trajectory_sinks.py and
    tests/features/cloud_trajectory_provider_expansion/.
"""

from __future__ import annotations

import asyncio
from io import BytesIO
from types import SimpleNamespace
from typing import Any
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
from vidbyte.lib.constants.cloud_sinks import GCS_CREATE_ONLY_GENERATION, MIN_PROVIDER_ATTEMPTS
from vidbyte.lib.dataclasses.cloud_sinks import GcsCredentials, GcsSinkConfig, SinkOverwriteMode
from vidbyte.lib.errors import ConfigurationError


class GcsTrajectorySink(CloudTrajectorySinkMixin):
    """TrajectorySink writing one JSONL object per run to a Google Cloud Storage bucket."""

    def __init__(self, config: GcsSinkConfig, *, credentials: GcsCredentials | None = None) -> None:
        # Binds config/credentials, lazily imports google-cloud-storage, and eagerly builds the client.
        self._config = config
        self._credentials = credentials
        self._driver = self._import_driver()
        self._client = self._build_client()
        self._initialize_cloud_lifecycle("gcs")

    async def write(self, record: TrajectoryRecord) -> None:
        # Encodes before preflight so payload failures never trigger provider I/O.
        await super().write(record)

    async def write_with_receipt(self, record: TrajectoryRecord) -> SinkWriteReceipt:
        # Exposes the normalized object acknowledgement while preserving write()'s protocol return type.
        return await super().write_with_receipt(record)

    def _build_client(self) -> Any:
        # Constructs the google-cloud-storage client, using explicit service-account credentials when given.
        try:
            if self._credentials is not None and self._credentials.service_account_json_path is not None:
                resolved = self._driver.service_account.Credentials.from_service_account_file(self._credentials.service_account_json_path)
                return self._driver.storage.Client(credentials=resolved)
            return self._driver.storage.Client()
        except self._driver.DefaultCredentialsError as exc:
            raise self._translate_error(exc) from exc

    async def _run_metadata_preflight(self) -> None:
        # Confirms the bucket exists and is reachable before any write is attempted.
        try:
            await asyncio.to_thread(self._client.get_bucket, self._config.bucket, timeout=self._timeout())
        except Exception as exc:
            raise self._translate_error(exc) from exc

    async def _run_write_probe(self) -> None:
        # Uses a reserved marker and deletes it only when the caller explicitly requested a write probe.
        key = self._object_key(f".vidbyte-preflight-{uuid4().hex}")
        await self._put_record(key, b"{}\n")
        try:
            await asyncio.to_thread(self._client.bucket(self._config.bucket).blob(key).delete)
        except Exception as exc:
            raise self._translate_error(exc) from exc

    async def _put_record(self, key: str, payload: bytes) -> SinkWriteReceipt:
        # GCS's upload helper selects its resumable path for large payloads; chunk_size bounds its transfer parts.
        # @intent provider-owns-gcs-retry-and-resume
        # The SDK owns retry/resumable transfer state; this adapter only maps
        # the normalized config into its upload call.
        try:
            bucket = self._client.bucket(self._config.bucket)
            blob = bucket.blob(key, kms_key_name=self._config.kms_key_name) if self._config.kms_key_name is not None else bucket.blob(key)
            blob.storage_class = self._config.storage_class.value
            metadata = pair_mapping(self._config.metadata)
            if metadata:
                blob.metadata = metadata
            if len(payload) >= self._config.multipart_threshold_bytes:
                blob.chunk_size = self._config.multipart_part_size_bytes
                upload = blob.upload_from_file
                upload_kwargs = {"rewind": True, "content_type": self._config.content_type, "timeout": self._timeout(), "retry": self._retry_policy()}
                if self._config.overwrite_mode is SinkOverwriteMode.CREATE_ONLY:
                    upload_kwargs["if_generation_match"] = GCS_CREATE_ONLY_GENERATION
                if self._config.checksum_algorithm is not None:
                    upload_kwargs["checksum"] = self._config.checksum_algorithm.value
                response = await asyncio.to_thread(upload, BytesIO(payload), **upload_kwargs)
            else:
                kwargs: dict[str, Any] = {"content_type": self._config.content_type, "timeout": self._timeout(), "retry": self._retry_policy()}
                if self._config.overwrite_mode is SinkOverwriteMode.CREATE_ONLY:
                    kwargs["if_generation_match"] = GCS_CREATE_ONLY_GENERATION
                if self._config.checksum_algorithm is not None:
                    kwargs["checksum"] = self._config.checksum_algorithm.value
                response = await asyncio.to_thread(blob.upload_from_string, payload, **kwargs)
        except Exception as exc:
            raise self._translate_error(exc) from exc
        return make_receipt("gcs", key, payload, response or blob)

    def _retry_policy(self) -> Any:
        # @intent retry-budget-is-provider-owned
        # Google Retry receives the configured deadline; no outer retry loop
        # may duplicate attempts or distort the caller's budget.
        retry = getattr(self._driver, "Retry", None)
        if not callable(retry):
            return None
        return retry(deadline=self._config.read_timeout_seconds * max(MIN_PROVIDER_ATTEMPTS, self._config.max_retries + MIN_PROVIDER_ATTEMPTS))

    def _timeout(self) -> tuple[float, float]:
        """Return the explicit connect/read timeout pair for GCS calls."""
        return (self._config.connect_timeout_seconds, self._config.read_timeout_seconds)

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
        # @intent optional-sdk-import-is-lazy
        try:
            from google.api_core.exceptions import DeadlineExceeded, Forbidden, NotFound, ServiceUnavailable, TooManyRequests, Unauthorized
            from google.auth.exceptions import DefaultCredentialsError
            from google.cloud import storage
            from google.oauth2 import service_account
            from google.api_core.retry import Retry
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
            Retry=Retry,
        )


__all__ = ["GcsTrajectorySink"]
