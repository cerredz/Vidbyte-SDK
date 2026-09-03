"""FILE: vidbyte/harnesses/stores/oci.py

PURPOSE:
    Export one redacted trajectory record per JSONL object to Oracle Cloud
    Infrastructure Object Storage, including OCI-native principals, object
    tiers, KMS encryption, checksums, conditional writes, and multipart upload.

ROLE IN CODEBASE:
    This adapter is selected by `HarnessClient.oci_sink()` and implements the
    existing `TrajectorySink` protocol through CloudTrajectorySinkMixin.

ARCHITECTURE NOTE:
    The OCI SDK is synchronous and optional. It is imported only while a sink
    is constructed; every network call is then isolated in `asyncio.to_thread`.
    UploadManager owns multipart retries and parallel part transfer, while the
    adapter owns only request construction and safe error translation.

PUBLIC API INVENTORY:
    OciTrajectorySink.

COMMON MODIFICATION PATTERNS:
    Add object-level settings to OciSinkConfig before threading them into the
    request builder. Keep authentication resolution in `_build_client()` and
    keep OCI status mapping in `_translate_error()`.

WHAT NOT TO DO:
    Do not import `oci` at module import time, expose credential contents in a
    diagnostic, or mutate bucket lifecycle, retention, or replication policy.

KNOWN EDGE CASES:
    OCI resource-principal and OKE workload-identity signers resolve their
    environment at construction time. A write probe requires delete access.
    OCI object tags are represented as reserved `tag-` user metadata because
    the PutObject API has no object-tagging field; bucket tags remain out of
    scope.

RELATED DOCS:
    docs/design/cloud-trajectory-provider-expansion.md

TESTS:
    tests/features/cloud_trajectory_provider_expansion/test_adapters.py
    tests/features/cloud_trajectory_provider_expansion/test_resilience.py
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
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
from vidbyte.lib.constants.cloud_sinks import MIN_PROVIDER_ATTEMPTS
from vidbyte.lib.dataclasses.cloud_sinks import OciAuthMode, OciCredentials, OciSinkConfig, SinkOverwriteMode
from vidbyte.lib.errors import ConfigurationError

_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_NOT_FOUND = 404
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_SERVER_ERROR_THRESHOLD = 500


class OciTrajectorySink(CloudTrajectorySinkMixin):
    """Trajectory sink for OCI Object Storage."""

    def __init__(self, config: OciSinkConfig, *, credentials: OciCredentials | None = None) -> None:
        self._config = config
        self._credentials = credentials or OciCredentials()
        self._driver = self._import_driver()
        self._client = self._build_client()
        self._initialize_cloud_lifecycle("oci")

    async def write(self, record: TrajectoryRecord) -> None:
        """Encode and upload one record through the shared cloud lifecycle."""
        await super().write(record)

    async def write_with_receipt(self, record: TrajectoryRecord) -> SinkWriteReceipt:
        """Return the safe OCI acknowledgement for one uploaded record."""
        return await super().write_with_receipt(record)

    def _build_client(self) -> Any:
        # @intent reveal-secret-only-at-client-construction
        # Secret values cross into OCI exactly once, at signer/provider creation;
        # the sink never stores or logs the revealed private key or token.
        try:
            config, signer = self._authentication_material()
            kwargs: dict[str, Any] = {
                "timeout": (self._config.connect_timeout_seconds, self._config.read_timeout_seconds),
                "retry_strategy": self._retry_strategy(),
            }
            if self._config.endpoint_url is not None:
                kwargs["service_endpoint"] = self._config.endpoint_url
            if signer is not None:
                kwargs["signer"] = signer
            return self._driver.ObjectStorageClient(config, **kwargs)
        except Exception as exc:
            raise self._translate_error(exc, during_setup=True) from exc

    def _authentication_material(self) -> tuple[dict[str, Any], Any | None]:
        # @intent auth-mode-dispatch-keeps-signers-isolated
        # Each credential mode has one focused builder, so key material and
        # workload-identity resolution cannot accidentally share a path.
        config = self._authentication_config()
        builders = {
            OciAuthMode.DEFAULT: self._no_signer,
            OciAuthMode.CONFIG_FILE: self._no_signer,
            OciAuthMode.API_KEY: self._api_key_material,
            OciAuthMode.SESSION_TOKEN: self._session_token_material,
            OciAuthMode.INSTANCE_PRINCIPAL: self._instance_principal_material,
            OciAuthMode.RESOURCE_PRINCIPAL: self._resource_principal_material,
            OciAuthMode.OKE_WORKLOAD_IDENTITY: self._oke_workload_identity_material,
        }
        builder = builders.get(self._credentials.auth_mode)
        if builder is None:
            raise ConfigurationError("Unsupported OCI authentication mode.")
        return builder(config)

    def _authentication_config(self) -> dict[str, Any]:
        mode = self._credentials.auth_mode
        if mode in (OciAuthMode.DEFAULT, OciAuthMode.CONFIG_FILE, OciAuthMode.SESSION_TOKEN):
            config = self._config_from_file()
        else:
            config = {"region": self._config.region or ""}
        if self._config.region is not None:
            config["region"] = self._config.region
        return config

    @staticmethod
    def _no_signer(config: dict[str, Any]) -> tuple[dict[str, Any], Any | None]:
        return config, None

    def _api_key_material(self, config: dict[str, Any]) -> tuple[dict[str, Any], Any]:
        private_key = self._credentials.private_key.reveal() if self._credentials.private_key is not None else None
        passphrase = self._credentials.passphrase.reveal() if self._credentials.passphrase is not None else None
        config.update({"tenancy": self._credentials.tenancy, "user": self._credentials.user, "fingerprint": self._credentials.fingerprint})
        if self._credentials.private_key_path is not None:
            config["key_file"] = self._credentials.private_key_path
        signer = self._driver.Signer(
            self._credentials.tenancy,
            self._credentials.user,
            self._credentials.fingerprint,
            self._credentials.private_key_path,
            pass_phrase=passphrase,
            private_key_content=private_key,
        )
        return config, signer

    def _session_token_material(self, config: dict[str, Any]) -> tuple[dict[str, Any], Any]:
        token = self._credentials.security_token
        if token is None:
            raise ConfigurationError("OCI SESSION_TOKEN auth requires security_token.")
        return config, self._driver.signers.SecurityTokenSigner(token.reveal())

    def _instance_principal_material(self, config: dict[str, Any]) -> tuple[dict[str, Any], Any]:
        return config, self._driver.signers.InstancePrincipalsSecurityTokenSigner()

    def _resource_principal_material(self, config: dict[str, Any]) -> tuple[dict[str, Any], Any]:
        return config, self._driver.signers.get_resource_principals_signer()

    def _oke_workload_identity_material(self, config: dict[str, Any]) -> tuple[dict[str, Any], Any]:
        return config, self._driver.signers.get_oke_workload_identity_resource_principal_signer()

    def _config_from_file(self) -> dict[str, Any]:
        if self._credentials.config_file_path is None:
            return self._driver.config.from_file(profile_name=self._credentials.profile)
        return self._driver.config.from_file(file_location=self._credentials.config_file_path, profile_name=self._credentials.profile)

    def _retry_strategy(self) -> Any:
        # @intent retry-budget-is-provider-owned
        # OCI's retry strategy handles service failures and throttling so the
        # sink does not create a second, unbounded retry policy.
        builder = self._driver.retry.RetryStrategyBuilder()
        return builder.add_max_attempts(max(MIN_PROVIDER_ATTEMPTS, self._config.max_retries + MIN_PROVIDER_ATTEMPTS)).get_retry_strategy()

    async def _run_metadata_preflight(self) -> None:
        """Verify namespace and bucket access without creating an object."""
        try:
            await asyncio.to_thread(self._client.get_bucket, self._config.namespace, self._config.bucket)
        except Exception as exc:
            raise self._translate_error(exc) from exc

    async def _run_write_probe(self) -> None:
        """Exercise write and delete permissions using a unique reserved key."""
        key = f"{self._object_key('preflight')}-{uuid4().hex}.jsonl"
        await self._put_single(key, b"{}\n")
        try:
            await asyncio.to_thread(self._client.delete_object, self._config.namespace, self._config.bucket, key)
        except Exception as exc:
            raise self._translate_error(exc) from exc

    async def _put_record(self, key: str, payload: bytes) -> SinkWriteReceipt:
        if len(payload) >= self._config.multipart_threshold_bytes:
            return await self._put_multipart(key, payload)
        return await self._put_single(key, payload)

    async def _put_single(self, key: str, payload: bytes) -> SinkWriteReceipt:
        # @intent small-payload-stays-single-put
        # A single PutObject preserves conditional-write semantics and avoids
        # creating an incomplete multipart upload for a small record.
        try:
            response = await asyncio.to_thread(
                self._client.put_object,
                self._config.namespace,
                self._config.bucket,
                key,
                BytesIO(payload),
                **self._request_kwargs(payload),
            )
        except Exception as exc:
            raise self._translate_error(exc) from exc
        return make_receipt("oci", key, payload, response)

    async def _put_multipart(self, key: str, payload: bytes) -> SinkWriteReceipt:
        # @intent native-multipart-owns-recovery
        # UploadManager owns part retries, parallelism, and abort behavior;
        # this adapter only supplies the normalized stream and options.
        try:
            manager = self._driver.UploadManager(
                self._client,
                allow_multipart_uploads=True,
                allow_parallel_uploads=True,
                parallel_process_count=self._config.multipart_max_concurrency,
            )
            response = await asyncio.to_thread(
                manager.upload_stream,
                self._config.namespace,
                self._config.bucket,
                key,
                BytesIO(payload),
                part_size=self._config.multipart_part_size_bytes,
                **self._request_kwargs(payload, for_multipart=True),
            )
        except Exception as exc:
            raise self._translate_error(exc) from exc
        return make_receipt("oci", key, payload, response)

    def _request_kwargs(self, payload: bytes, *, for_multipart: bool = False) -> dict[str, Any]:
        metadata = pair_mapping(self._config.metadata)
        metadata.update({f"tag-{name}": value for name, value in self._config.tags})
        kwargs: dict[str, Any] = {
            "content_type": self._config.content_type,
            "storage_tier": self._config.storage_tier.value,
            "opc_meta": metadata or None,
        }
        if self._config.overwrite_mode is SinkOverwriteMode.CREATE_ONLY:
            kwargs["if_none_match"] = "*"
        if self._config.vault_kms_key_id is not None:
            kwargs["opc_sse_kms_key_id"] = self._config.vault_kms_key_id
        if self._config.checksum_algorithm == "SHA256":
            kwargs["opc_checksum_algorithm"] = "SHA256"
        elif self._config.checksum_algorithm == "MD5" and not for_multipart:
            # @intent protocol-md5-is-not-a-security-primitive
            # OCI's Content-MD5 header is a wire-level integrity checksum;
            # mark it explicitly as non-security use for the lint policy.
            kwargs["content_md5"] = base64.b64encode(hashlib.md5(payload, usedforsecurity=False).digest()).decode("ascii")
        return kwargs

    def _translate_error(self, exc: Exception, *, during_setup: bool = False) -> HarnessSinkError:
        """Map OCI auth, setup, transport, and service errors without leaking payloads."""
        if isinstance(exc, (self._driver.ConfigFileNotFound, self._driver.ProfileNotFound, self._driver.InvalidConfig)):
            return HarnessSinkSetupError("OCI configuration could not be loaded or validated.", details={"provider": "oci", "error_type": type(exc).__name__})
        if isinstance(exc, self._driver.ClientError):
            return HarnessSinkAuthenticationError("OCI credential resolution failed.", details={"provider": "oci", "error_type": type(exc).__name__})
        if isinstance(exc, self._driver.ServiceError):
            status = getattr(exc, "status", None)
            if status == _HTTP_UNAUTHORIZED:
                return HarnessSinkAuthenticationError("OCI rejected the configured signer or token.", details={"provider": "oci", "status": status})
            if status == _HTTP_FORBIDDEN:
                return HarnessSinkAuthorizationError("OCI denied access to the configured namespace, bucket, or object.", details={"provider": "oci", "status": status})
            if status == _HTTP_NOT_FOUND:
                return HarnessSinkSetupError("OCI could not resolve the configured namespace or bucket.", details={"provider": "oci", "status": status})
            if status == _HTTP_TOO_MANY_REQUESTS or (status is not None and status >= _HTTP_SERVER_ERROR_THRESHOLD):
                return HarnessSinkUnavailableError("OCI was unavailable after the SDK retry strategy was exhausted.", details={"provider": "oci", "status": status})
            return HarnessSinkError("OCI rejected the object request.", details={"provider": "oci", "status": status, "code": getattr(exc, "code", None)})
        if isinstance(exc, (self._driver.RequestException, self._driver.ConnectTimeout)):
            return HarnessSinkUnavailableError("Could not reach the configured OCI Object Storage endpoint.", details={"provider": "oci", "error_type": type(exc).__name__})
        if during_setup:
            return HarnessSinkSetupError("OCI Object Storage client setup failed.", details={"provider": "oci", "error_type": type(exc).__name__})
        return HarnessSinkError("OCI Object Storage request failed for an unrecognized reason.", details={"provider": "oci", "error_type": type(exc).__name__})

    @staticmethod
    def _import_driver() -> Any:
        """Load OCI SDK symbols lazily and retain only the adapter's needed surface."""
        # @intent optional-sdk-import-is-lazy
        try:
            import oci
            from oci.auth import signers
            from oci.exceptions import ClientError, ConfigFileNotFound, ConnectTimeout, InvalidConfig, ProfileNotFound, RequestException, ServiceError
            from oci.object_storage import ObjectStorageClient
            from oci.object_storage.transfer import UploadManager
        except ImportError as exc:
            raise ConfigurationError("OciTrajectorySink requires the 'oci' package. Install it with `pip install oci`.") from exc
        return SimpleNamespace(
            ClientError=ClientError,
            ConfigFileNotFound=ConfigFileNotFound,
            ConnectTimeout=ConnectTimeout,
            InvalidConfig=InvalidConfig,
            ObjectStorageClient=ObjectStorageClient,
            ProfileNotFound=ProfileNotFound,
            RequestException=RequestException,
            ServiceError=ServiceError,
            Signer=oci.Signer,
            UploadManager=UploadManager,
            auth=oci.auth,
            config=oci.config,
            retry=oci.retry,
            signers=signers,
        )


__all__ = ["OciTrajectorySink"]
