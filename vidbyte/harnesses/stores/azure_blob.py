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

COMMON MODIFICATION PATTERNS:
    Add a new Config/Credentials field in
    vidbyte/lib/dataclasses/cloud_sinks.py first, then thread it through
    _build_client()/_put() here; add a new status-code mapping in
    _translate_http_response_error().

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
    tests/test_cloud_trajectory_sinks.py and
    tests/features/cloud_trajectory_provider_expansion/.
"""

from __future__ import annotations

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
from vidbyte.lib.dataclasses.cloud_sinks import AzureBlobCredentials, AzureBlobSinkConfig
from vidbyte.lib.dataclasses.cloud_sinks import SinkOverwriteMode
from vidbyte.lib.constants.cloud_sinks import MIN_SINGLE_PUT_BYTES
from vidbyte.lib.errors import ConfigurationError

_HTTP_FORBIDDEN = 403
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_SERVICE_UNAVAILABLE = 503


class AzureBlobTrajectorySink(CloudTrajectorySinkMixin):
    """TrajectorySink writing one JSONL object per run to an Azure Blob Storage container."""

    def __init__(self, config: AzureBlobSinkConfig, *, credentials: AzureBlobCredentials) -> None:
        # Binds config/credentials, lazily imports azure-storage-blob, and eagerly builds the async client.
        self._config = config
        self._credentials = credentials
        self._driver = self._import_driver()
        self._client = self._build_client()
        self._initialize_cloud_lifecycle("azure_blob")

    async def write(self, record: TrajectoryRecord) -> None:
        # Encodes before preflight so payload failures never trigger provider I/O.
        await super().write(record)

    async def write_with_receipt(self, record: TrajectoryRecord) -> SinkWriteReceipt:
        # Exposes the normalized object acknowledgement while preserving write()'s protocol return type.
        return await super().write_with_receipt(record)

    def _build_client(self) -> Any:
        # @intent client-owns-its-own-retry-policy
        # Constructs the async BlobServiceClient, preferring connection_string, then sas_token, then keyless DefaultAzureCredential.
        # retry_total is handed straight to the vendor client; this sink never loops or backs off on its own.
        retry_total = self._config.max_retries
        timeout_kwargs = {
            "connection_timeout": self._config.connect_timeout_seconds,
            "read_timeout": self._config.read_timeout_seconds,
            "max_single_put_size": max(MIN_SINGLE_PUT_BYTES, self._config.multipart_threshold_bytes),
            "max_block_size": self._config.multipart_part_size_bytes,
        }
        if self._credentials.connection_string is not None:
            return self._driver.BlobServiceClient.from_connection_string(self._credentials.connection_string.reveal(), retry_total=retry_total, **timeout_kwargs)
        if self._credentials.sas_token is not None:
            account_url = f"{self._credentials.account_url}?{self._credentials.sas_token.reveal()}"
            return self._driver.BlobServiceClient(account_url=account_url, retry_total=retry_total, **timeout_kwargs)
        identity_driver = self._import_identity_driver()
        self._credential = identity_driver.DefaultAzureCredential()
        return self._driver.BlobServiceClient(account_url=self._credentials.account_url, credential=self._credential, retry_total=retry_total, **timeout_kwargs)

    async def _run_metadata_preflight(self) -> None:
        # Confirms the container exists and is reachable before any write is attempted.
        try:
            container_client = self._client.get_container_client(self._config.container)
            await container_client.get_container_properties()
        except Exception as exc:
            raise self._translate_error(exc) from exc

    async def _run_write_probe(self) -> None:
        # Uses a reserved marker and deletes it only when the caller explicitly requested a write probe.
        key = self._object_key(f".vidbyte-preflight-{uuid4().hex}")
        await self._put_record(key, b"{}\n")
        try:
            blob_client = self._client.get_blob_client(container=self._config.container, blob=key)
            await blob_client.delete_blob()
        except Exception as exc:
            raise self._translate_error(exc) from exc

    async def _put_record(self, key: str, payload: bytes) -> SinkWriteReceipt:
        # Uses Azure's upload helper, which switches to block upload for larger payloads.
        try:
            blob_client = self._client.get_blob_client(container=self._config.container, blob=key)
            content_settings = self._driver.ContentSettings(content_type=self._config.content_type)
            kwargs: dict[str, Any] = {
                "overwrite": self._config.overwrite_mode is SinkOverwriteMode.OVERWRITE,
                "standard_blob_tier": self._config.tier.value,
                "content_settings": content_settings,
                "metadata": pair_mapping(self._config.metadata),
                "tags": pair_mapping(self._config.tags),
                "max_concurrency": self._config.multipart_max_concurrency,
                "timeout": self._config.read_timeout_seconds,
            }
            response = await blob_client.upload_blob(payload, **kwargs)
        except Exception as exc:
            raise self._translate_error(exc) from exc
        return make_receipt("azure_blob", key, payload, response)

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
            return HarnessSinkUnavailableError("Could not reach the configured Azure Blob endpoint.", details={"error_type": type(exc).__name__})
        return HarnessSinkError("Azure Blob request failed for an unrecognized reason.", details={"error_type": type(exc).__name__})

    def _translate_http_response_error(self, exc: Any) -> HarnessSinkError:
        # Maps an HttpResponseError's status_code to the matching subclass.
        status_code = getattr(exc, "status_code", None)
        if status_code == _HTTP_FORBIDDEN:
            return HarnessSinkAuthorizationError(
                "Azure denied this write (403). This can mean a policy denial, or that a sas_token has expired — Azure reports both the same way.",
                details={"container": self._config.container},
            )
        if status_code in (_HTTP_TOO_MANY_REQUESTS, _HTTP_SERVICE_UNAVAILABLE):
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
