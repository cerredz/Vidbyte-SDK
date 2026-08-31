"""FILE: vidbyte/harnesses/stores/azure_blob.py

PURPOSE:
    TrajectorySink backed by Azure Blob Storage. Writes one JSONL object per
    finished run, keyed by run_id, mirroring vidbyte/harnesses/stores/s3.py.

ROLE IN CODEBASE:
    Bound to a Harness via sink=sdk.harnesses.azure_blob_sink(...); receives
    one redacted TrajectoryRecord per run.

ARCHITECTURE NOTE:
    Unlike s3.py/gcs.py, azure-storage-blob ships a first-party asyncio
    surface (azure.storage.blob.aio), so this sink calls it directly instead
    of wrapping a synchronous client in asyncio.to_thread. credentials is a
    required constructor argument here, not optional like S3/GCS, because
    account_url (which storage account to talk to) lives on Credentials —
    Azure has no implicit default account the way AWS/GCP have an implicit
    default region/project. Both connection_string and sas_token left None
    selects the keyless DefaultAzureCredential path (managed identity / AAD).

PUBLIC API INVENTORY:
    AzureBlobTrajectorySink; verify(); write(record).

WHAT NOT TO DO IN THIS FILE:
    1. Do not import azure.storage.blob/azure.identity at module level; every
       symbol comes from the lazy _import_driver()/_import_identity_driver().
    2. Do not wrap this sink's async client calls in asyncio.to_thread — that
       would double up an already-async client with a redundant thread hop.
    3. Do not let a raw azure.core exception escape write()/verify().

KNOWN EDGE CASES:
    Azure reports an expired SAS token as a 403 HttpResponseError, the same
    status a plain policy denial produces — the raised
    HarnessSinkAuthorizationError names this ambiguity explicitly. A write to
    the Archive tier succeeds even though the blob cannot be read back until
    manually rehydrated; this sink cannot catch that at write time, so
    AzureBlobSinkConfig's docstring warns about it instead.

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
from vidbyte.lib.dataclasses.cloud_sinks import AzureBlobCredentials, AzureBlobSinkConfig
from vidbyte.lib.errors import ConfigurationError


class AzureBlobTrajectorySink:
    """TrajectorySink writing one JSONL object per run to an Azure Blob Storage container."""

    def __init__(self, config: AzureBlobSinkConfig, *, credentials: AzureBlobCredentials) -> None:
        # Binds config/credentials, lazily imports azure-storage-blob, and eagerly builds the async client.
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
        # Constructs the async BlobServiceClient, preferring connection_string, then sas_token, then keyless DefaultAzureCredential.
        retry_total = self._config.max_retries
        if self._credentials.connection_string is not None:
            return self._driver.BlobServiceClient.from_connection_string(self._credentials.connection_string.reveal(), retry_total=retry_total)
        if self._credentials.sas_token is not None:
            account_url = f"{self._credentials.account_url}?{self._credentials.sas_token.reveal()}"
            return self._driver.BlobServiceClient(account_url=account_url, retry_total=retry_total)
        identity_driver = self._import_identity_driver()
        return self._driver.BlobServiceClient(account_url=self._credentials.account_url, credential=identity_driver.DefaultAzureCredential(), retry_total=retry_total)

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
        # Confirms the container exists and is reachable before any write is attempted.
        try:
            container_client = self._client.get_container_client(self._config.container)
            await container_client.get_container_properties()
        except Exception as exc:
            raise self._translate_error(exc) from exc

    def _object_key(self, run_id: str) -> str:
        # Builds "{prefix}/{run_id}.jsonl", or "{run_id}.jsonl" when prefix is empty.
        prefix = self._config.prefix.rstrip("/")
        return f"{prefix}/{run_id}.jsonl" if prefix else f"{run_id}.jsonl"

    async def _put(self, key: str, payload: bytes) -> None:
        # Issues one atomic, overwriting upload carrying the configured access tier.
        try:
            blob_client = self._client.get_blob_client(container=self._config.container, blob=key)
            content_settings = self._driver.ContentSettings(content_type="application/x-ndjson")
            await blob_client.upload_blob(payload, overwrite=True, standard_blob_tier=self._config.tier.value, content_settings=content_settings)
        except Exception as exc:
            raise self._translate_error(exc) from exc

    def _translate_error(self, exc: Exception) -> HarnessSinkError:
        # Maps an azure.core exception to the specific HarnessSinkError subclass a caller can act on.
        if isinstance(exc, self._driver.ResourceNotFoundError):
            return HarnessSinkSetupError("Azure reported the container could not be resolved.", details={"container": self._config.container})
        if isinstance(exc, self._driver.ClientAuthenticationError):
            return HarnessSinkAuthenticationError(
                "No usable Azure credential could be resolved. Supply a connection_string or sas_token, or run where DefaultAzureCredential can resolve one (managed identity, az login, or environment variables).",
                details={"error_type": type(exc).__name__},
            )
        if isinstance(exc, self._driver.HttpResponseError):
            return self._translate_http_response_error(exc)
        if isinstance(exc, self._driver.ServiceRequestError):
            return HarnessSinkUnavailableError("Could not reach the configured Azure Blob endpoint.", details={"account_url": self._credentials.account_url, "error_type": type(exc).__name__})
        return HarnessSinkError("Azure Blob request failed for an unrecognized reason.", details={"error_type": type(exc).__name__})

    def _translate_http_response_error(self, exc: Any) -> HarnessSinkError:
        # Maps an HttpResponseError's status_code to the matching subclass.
        status_code = getattr(exc, "status_code", None)
        if status_code == 403:
            return HarnessSinkAuthorizationError(
                "Azure denied this write (403). This can mean a policy denial, or that a sas_token has expired — Azure reports both the same way.",
                details={"container": self._config.container},
            )
        if status_code in (429, 503):
            return HarnessSinkUnavailableError(f"Azure was unavailable after the client's own retries were exhausted ({status_code}).", details={"status_code": status_code})
        return HarnessSinkError(f"Azure Blob rejected the request ({status_code}).", details={"status_code": status_code})

    @staticmethod
    def _import_driver() -> Any:
        # Lazily imports azure-storage-blob and the exception types this sink translates, raising a helpful error when absent.
        try:
            from azure.core.exceptions import ClientAuthenticationError, HttpResponseError, ResourceNotFoundError, ServiceRequestError
            from azure.storage.blob import ContentSettings
            from azure.storage.blob.aio import BlobServiceClient
        except ImportError as exc:
            raise ConfigurationError("AzureBlobTrajectorySink requires the 'azure-storage-blob' package. Install it with `pip install azure-storage-blob`.") from exc
        return SimpleNamespace(
            BlobServiceClient=BlobServiceClient,
            ContentSettings=ContentSettings,
            ClientAuthenticationError=ClientAuthenticationError,
            HttpResponseError=HttpResponseError,
            ResourceNotFoundError=ResourceNotFoundError,
            ServiceRequestError=ServiceRequestError,
        )

    @staticmethod
    def _import_identity_driver() -> Any:
        # Lazily imports azure-identity, only needed for the keyless DefaultAzureCredential path.
        try:
            from azure.identity.aio import DefaultAzureCredential
        except ImportError as exc:
            raise ConfigurationError(
                "AzureBlobTrajectorySink requires the 'azure-identity' package for keyless auth (no connection_string or sas_token was given). Install it with `pip install azure-identity`."
            ) from exc
        return SimpleNamespace(DefaultAzureCredential=DefaultAzureCredential)


__all__ = ["AzureBlobTrajectorySink"]
