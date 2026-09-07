"""FILE: vidbyte/harnesses/stores/s3.py

PURPOSE:
    TrajectorySink backed by AWS S3 (and any S3-API-compatible vendor via
    S3SinkConfig.endpoint_url — Cloudflare R2, Backblaze B2, DigitalOcean
    Spaces, IBM COS, Wasabi, and MinIO). Writes one JSONL object per finished
    run, keyed by run_id.

ROLE IN CODEBASE:
    Bound to a Harness via sink=sdk.harnesses.s3_sink(...); receives one
    redacted TrajectoryRecord per run, exactly like FileTrajectorySink, but
    lands it inside a customer-owned S3 bucket instead of on local disk.

ARCHITECTURE NOTE:
    S3 has no cheap append primitive, so unlike FileTrajectorySink this sink
    does not grow one shared object — every write() call is one atomic
    PutObject to its own key ("{prefix}/{run_id}.jsonl"), which is also what
    makes a retried write() for the same run_id safely idempotent. boto3 is
    synchronous, so every network call runs via asyncio.to_thread to avoid
    blocking the event loop. Preflight verification (does the bucket exist and
    accept writes) is memoized per instance as one shared asyncio.Task, so two
    concurrent first-writes on one shared sink await the same in-flight check
    rather than double-checking — asyncio.Lock is banned by this repo's
    banned-api-policy (lint S039) with no built replacement yet, and the
    synchronous check-then-create between await points needs no lock in the
    first place, since asyncio only yields control at an await.

PUBLIC API INVENTORY:
    S3TrajectorySink; verify(); write(record); write_with_receipt(); aclose().

WHAT NOT TO DO IN THIS FILE:
    1. Do not import boto3 at module level; every symbol comes from the lazy
       _import_driver() so this module imports cleanly with boto3 absent.
    2. Do not hand-roll retry/backoff; botocore.config.Config(retries=...)
       already does this, tuned to S3's actual error/throttling taxonomy.
    3. Do not let a raw ClientError/NoCredentialsError/etc. escape write() or
       verify(); every vendor exception must pass through _translate_error()
       first so callers see a specific HarnessSinkError subclass.
    4. Keep multipart transfer behind the configured threshold and preserve
       abort-on-failure cleanup; create-only writes must remain single-request
       so their conditional semantics stay atomic.

COMMON MODIFICATION PATTERNS:
    Add a new Config/Credentials field in
    vidbyte/lib/dataclasses/cloud_sinks.py first, then thread it through
    _build_client()/_put() here; add a new error-code mapping to
    _SETUP_CODES/_AUTHENTICATION_CODES/_RETRYABLE_CODES or
    _translate_client_error() rather than a new isinstance branch.

KNOWN EDGE CASES:
    An S3 AccessDenied on a bucket that actually requires server-side
    encryption looks identical to a plain permissions problem on the wire;
    _translate_error() calls this out explicitly in the raised error's
    fix_approaches rather than leaving the caller to guess. AssumeRole
    failures are reported as HarnessSinkAuthenticationError (can't become the
    target identity), distinct from an AccessDenied against S3 itself
    (HarnessSinkAuthorizationError — an established identity lacking
    permission).

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/cloud-trajectory-sinks.md

TESTS:
    tests/test_cloud_trajectory_sinks.py and
    tests/features/cloud_trajectory_provider_expansion/.
"""

from __future__ import annotations

import asyncio
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
from vidbyte.harnesses.stores._cloud_common import (
    CloudTrajectorySinkMixin,
    SinkWriteReceipt,
    make_receipt,
    pair_mapping,
    s3_tagging,
)
from vidbyte.lib.dataclasses.cloud_sinks import (
    S3CompatibleProfiles,
    S3Credentials,
    S3SinkConfig,
    SinkOverwriteMode,
)
from vidbyte.lib.errors import ConfigurationError

_RETRYABLE_CODES = {"SlowDown", "RequestTimeout"}
_AUTHENTICATION_CODES = {"ExpiredToken", "InvalidAccessKeyId", "SignatureDoesNotMatch"}
_SETUP_CODES = {"NoSuchBucket", "PermanentRedirect"}
_HTTP_SERVER_ERROR_THRESHOLD = 500


class S3TrajectorySink(CloudTrajectorySinkMixin):
    """TrajectorySink writing one JSONL object per run to an S3(-compatible) bucket."""

    def __init__(self, config: S3SinkConfig, *, credentials: S3Credentials | None = None) -> None:
        # Binds config/credentials, lazily imports boto3, and eagerly builds the client (no network call yet).
        # @intent client-is-built-without-network
        # Construction resolves local credential material but defers bucket
        # access until verify()/the first write.
        self._config = config
        self._credentials = credentials
        self._driver = self._import_driver()
        if config.sse == "AES256-C" and (credentials is None or credentials.customer_encryption_key is None):
            raise ConfigurationError("S3 SSE-C requires credentials.customer_encryption_key.")
        self._client = self._build_client()
        self._initialize_cloud_lifecycle(config.provider.value)

    async def verify(self) -> None:
        # Explicit, caller-invoked preflight check — call before a long run to fail fast on setup/auth problems.
        await super().verify()

    async def write(self, record: TrajectoryRecord) -> None:
        # Encodes before preflight so payload failures never trigger provider I/O.
        await super().write(record)

    async def write_with_receipt(self, record: TrajectoryRecord) -> SinkWriteReceipt:
        # Exposes the normalized object acknowledgement while preserving write()'s protocol return type.
        return await super().write_with_receipt(record)

    def _build_client(self) -> Any:
        # @intent reveal-secret-only-at-client-construction
        # Constructs the boto3 S3 client, resolving cross-account role assumption first when configured.
        # Retry/backoff is boto3's own Config, never a hand-rolled loop; .reveal() is called only here,
        # right before the vendor client needs the real value, never logged or stored elsewhere.
        profile = S3CompatibleProfiles.get(self._config.provider)
        region = self._config.region or profile.default_region
        retry_config = self._driver.BotoConfig(
            retries={"max_attempts": self._config.max_retries, "mode": "adaptive"},
            region_name=region,
            connect_timeout=self._config.connect_timeout_seconds,
            read_timeout=self._config.read_timeout_seconds,
        )
        client_kwargs: dict[str, Any] = {"config": retry_config}
        if self._config.endpoint_url is not None:
            client_kwargs["endpoint_url"] = self._config.endpoint_url
        credentials = self._credentials
        if credentials is not None and credentials.access_key_id is not None and credentials.secret_access_key is not None:
            client_kwargs["aws_access_key_id"] = credentials.access_key_id
            client_kwargs["aws_secret_access_key"] = credentials.secret_access_key.reveal()
            if credentials.session_token is not None:
                client_kwargs["aws_session_token"] = credentials.session_token.reveal()
        if self._config.role_arn is not None:
            client_kwargs = self._assume_role_if_configured(client_kwargs)
        return self._driver.boto3.client("s3", **client_kwargs)

    def _assume_role_if_configured(self, base_client_kwargs: dict[str, Any]) -> dict[str, Any]:
        # Exchanges the base credentials (static or boto3's default chain) for temporary role-assumed credentials via STS.
        sts_kwargs = {key: value for key, value in base_client_kwargs.items() if key != "endpoint_url"}
        sts_client = self._driver.boto3.client("sts", **sts_kwargs)
        assume_kwargs: dict[str, Any] = {"RoleArn": self._config.role_arn, "RoleSessionName": f"vidbyte-{uuid4().hex[:8]}"}
        if self._config.external_id is not None:
            assume_kwargs["ExternalId"] = self._config.external_id
        try:
            response = sts_client.assume_role(**assume_kwargs)
        except Exception as exc:
            raise self._translate_error(exc, during_role_assumption=True) from exc
        temp_credentials = response["Credentials"]
        resolved = dict(base_client_kwargs)
        resolved["aws_access_key_id"] = temp_credentials["AccessKeyId"]
        resolved["aws_secret_access_key"] = temp_credentials["SecretAccessKey"]
        resolved["aws_session_token"] = temp_credentials["SessionToken"]
        return resolved

    async def _run_metadata_preflight(self) -> None:
        # Confirms the bucket exists and is reachable before any write is attempted.
        try:
            await asyncio.to_thread(self._client.head_bucket, Bucket=self._config.bucket)
        except Exception as exc:
            raise self._translate_error(exc) from exc

    async def _run_write_probe(self) -> None:
        # Uses an explicit reserved marker only when the caller accepts the delete permission requirement.
        probe_key = self._object_key(f".vidbyte-preflight-{uuid4().hex}")
        await self._put_single(probe_key, b"{}\n")
        try:
            await asyncio.to_thread(self._client.delete_object, Bucket=self._config.bucket, Key=probe_key)
        except Exception as exc:
            raise self._translate_error(exc) from exc

    async def _put_record(self, key: str, payload: bytes) -> SinkWriteReceipt:
        # Uses multipart only after the configured threshold and when the profile advertises support.
        capabilities = S3CompatibleProfiles.get(self._config.provider)
        # @intent conditional-write-is-atomic
        # CreateMultipartUpload has no portable If-None-Match guarantee across
        # S3-compatible implementations, so create-only writes stay on the
        # atomic PutObject path even when the payload crosses the multipart
        # threshold.
        if self._config.overwrite_mode is not SinkOverwriteMode.CREATE_ONLY and len(payload) >= self._config.multipart_threshold_bytes and capabilities.supports_multipart:
            return await self._put_multipart(key, payload)
        return await self._put_single(key, payload)

    async def _put_single(self, key: str, payload: bytes) -> SinkWriteReceipt:
        # @intent s3-single-put-is-atomic
        # PutObject preserves conditional-write and object-lock headers as one
        # provider operation.
        try:
            response = await asyncio.to_thread(self._client.put_object, **self._request_kwargs(key, payload))
        except Exception as exc:
            raise self._translate_error(exc) from exc
        return make_receipt(self._config.provider.value, key, payload, response)

    def _request_kwargs(self, key: str, payload: bytes) -> dict[str, Any]:
        # @intent request-options-are-capability-validated
        # Config validation rejects unsupported profile features before these
        # fields can reach a vendor endpoint.
        kwargs: dict[str, Any] = {
            "Bucket": self._config.bucket,
            "Key": key,
            "Body": payload,
            "ContentType": self._config.content_type,
            "StorageClass": self._config.storage_class.value,
        }
        metadata = pair_mapping(self._config.metadata)
        if metadata:
            kwargs["Metadata"] = metadata
        tagging = s3_tagging(self._config.tags)
        if tagging:
            kwargs["Tagging"] = tagging
        if self._config.checksum_algorithm is not None:
            kwargs["ChecksumAlgorithm"] = self._config.checksum_algorithm.value
        if self._config.overwrite_mode is SinkOverwriteMode.CREATE_ONLY:
            kwargs["IfNoneMatch"] = "*"
        kwargs.update(self._encryption_kwargs())
        kwargs.update(self._object_lock_kwargs())
        return kwargs

    def _encryption_kwargs(self) -> dict[str, Any]:
        """Build the selected S3 server-side encryption headers."""
        if self._config.sse in ("AES256", "aws:kms"):
            kwargs: dict[str, Any] = {"ServerSideEncryption": self._config.sse}
            if self._config.kms_key_id is not None:
                kwargs["SSEKMSKeyId"] = self._config.kms_key_id
            return kwargs
        if self._config.sse == "AES256-C":
            credentials = self._credentials
            if credentials is None or credentials.customer_encryption_key is None:
                raise ConfigurationError("S3 SSE-C requires credentials.customer_encryption_key.")
            return {"SSECustomerAlgorithm": "AES256", "SSECustomerKey": credentials.customer_encryption_key.reveal()}
        return {}

    def _object_lock_kwargs(self) -> dict[str, Any]:
        """Build the optional AWS object-lock headers."""
        kwargs: dict[str, Any] = {}
        if self._config.object_lock_mode is not None:
            kwargs["ObjectLockMode"] = self._config.object_lock_mode
        if self._config.object_lock_retain_until is not None:
            kwargs["ObjectLockRetainUntilDate"] = self._config.object_lock_retain_until
        if self._config.legal_hold is not None:
            kwargs["ObjectLockLegalHoldStatus"] = self._config.legal_hold
        return kwargs

    async def _put_multipart(self, key: str, payload: bytes) -> SinkWriteReceipt:
        # @intent s3-multipart-aborts-on-failure
        # The upload ID is retained until completion so every failed transfer
        # can attempt best-effort cleanup.
        upload_id = ""
        try:
            create_kwargs = self._request_kwargs(key, b"")
            create_kwargs.pop("Body", None)
            create_kwargs.pop("IfNoneMatch", None)
            response = await asyncio.to_thread(self._client.create_multipart_upload, **create_kwargs)
            upload_id = response["UploadId"]
            parts = await self._upload_parts(key, payload, upload_id)
            completed = await asyncio.to_thread(self._client.complete_multipart_upload, Bucket=self._config.bucket, Key=key, UploadId=upload_id, MultipartUpload={"Parts": parts})
            return make_receipt(self._config.provider.value, key, payload, completed)
        except Exception as exc:
            if upload_id:
                await self._abort_multipart(key, upload_id)
            if isinstance(exc, HarnessSinkError):
                raise
            raise self._translate_error(exc) from exc

    async def _upload_parts(self, key: str, payload: bytes, upload_id: str) -> list[dict[str, Any]]:
        part_size = self._config.multipart_part_size_bytes
        chunks = [(number, payload[start : start + part_size]) for number, start in enumerate(range(0, len(payload), part_size), start=1)]
        parts: list[dict[str, Any]] = []
        for start in range(0, len(chunks), self._config.multipart_max_concurrency):
            batch = chunks[start : start + self._config.multipart_max_concurrency]
            responses = await asyncio.gather(*(self._upload_part(key, upload_id, number, chunk) for number, chunk in batch))
            parts.extend(responses)
        return parts

    async def _upload_part(self, key: str, upload_id: str, part_number: int, chunk: bytes) -> dict[str, Any]:
        response = await asyncio.to_thread(self._client.upload_part, Bucket=self._config.bucket, Key=key, UploadId=upload_id, PartNumber=part_number, Body=chunk)
        return {"ETag": response.get("ETag", ""), "PartNumber": part_number}

    async def _abort_multipart(self, key: str, upload_id: str) -> None:
        try:
            await asyncio.to_thread(self._client.abort_multipart_upload, Bucket=self._config.bucket, Key=key, UploadId=upload_id)
        except Exception:
            return

    # @intent typed-errors-hide-provider-exceptions
    # Every SDK exception becomes a stable sink error before it crosses the
    # adapter boundary, while details remain limited to safe identifiers.
    def _translate_error(self, exc: Exception, *, during_role_assumption: bool = False) -> HarnessSinkError:
        # Maps a boto3/botocore exception to the specific HarnessSinkError subclass a caller can act on.
        if during_role_assumption:
            return HarnessSinkAuthenticationError(
                "Cross-account role assumption failed; the base identity could not become role_arn.",
                details={"role_arn": self._config.role_arn, "error_type": type(exc).__name__},
            )
        if isinstance(exc, self._driver.NoCredentialsError):
            return HarnessSinkAuthenticationError("No AWS credentials could be resolved (no static keys and the default credential chain is empty).", details={"provider": self._config.provider.value, "error_type": type(exc).__name__})
        if isinstance(exc, (self._driver.EndpointConnectionError, self._driver.ConnectTimeoutError)):
            return HarnessSinkUnavailableError("Could not reach the configured S3 endpoint.", details={"provider": self._config.provider.value, "error_type": type(exc).__name__})
        if isinstance(exc, self._driver.ClientError):
            return self._translate_client_error(exc)
        return HarnessSinkError("S3 request failed for an unrecognized reason.", details={"error_type": type(exc).__name__})

    # @intent status-code-drives-actionable-error
    # S3-compatible providers expose botocore-shaped response codes, so this
    # helper retains only the category needed for caller remediation.
    def _translate_client_error(self, exc: Any) -> HarnessSinkError:
        # Maps a botocore ClientError's response Code/HTTPStatusCode to the matching subclass.
        code = str(exc.response.get("Error", {}).get("Code", ""))
        status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in _SETUP_CODES:
            return HarnessSinkSetupError(f"S3 reported the bucket could not be resolved ({code}).", details={"provider": self._config.provider.value, "bucket": self._config.bucket, "region": self._config.region, "code": code})
        if code in _AUTHENTICATION_CODES:
            return HarnessSinkAuthenticationError(f"S3 rejected the supplied credentials ({code}).", details={"provider": self._config.provider.value, "code": code})
        if code == "AccessDenied":
            return HarnessSinkAuthorizationError(
                "S3 denied this write. If this bucket requires server-side encryption, confirm sse/kms_key_id is set — a missing encryption header surfaces as AccessDenied too.",
                details={"provider": self._config.provider.value, "bucket": self._config.bucket, "code": code},
            )
        if code in _RETRYABLE_CODES or (status_code is not None and status_code >= _HTTP_SERVER_ERROR_THRESHOLD):
            return HarnessSinkUnavailableError(f"S3 was unavailable after boto3's own retries were exhausted ({code or status_code}).", details={"provider": self._config.provider.value, "code": code, "status_code": status_code})
        return HarnessSinkError(f"S3 rejected the request ({code}).", details={"provider": self._config.provider.value, "code": code, "status_code": status_code})

    @staticmethod
    def _import_driver() -> Any:
        # Lazily imports boto3 and the botocore exception types this sink translates, raising a helpful error when absent.
        try:
            import boto3
            from botocore.config import Config as BotoConfig
            from botocore.exceptions import ClientError, ConnectTimeoutError, EndpointConnectionError, NoCredentialsError
        except ImportError as exc:
            raise ConfigurationError("S3TrajectorySink requires the 'boto3' package. Install it with `pip install boto3`.") from exc
        return SimpleNamespace(
            boto3=boto3,
            BotoConfig=BotoConfig,
            ClientError=ClientError,
            ConnectTimeoutError=ConnectTimeoutError,
            EndpointConnectionError=EndpointConnectionError,
            NoCredentialsError=NoCredentialsError,
        )


__all__ = ["S3TrajectorySink"]
