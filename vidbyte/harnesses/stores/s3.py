"""FILE: vidbyte/harnesses/stores/s3.py

PURPOSE:
    TrajectorySink backed by AWS S3 (and any S3-API-compatible vendor via
    S3SinkConfig.endpoint_url — Cloudflare R2, Backblaze B2, DigitalOcean
    Spaces, MinIO). Writes one JSONL object per finished run, keyed by run_id.

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
    S3TrajectorySink; verify(); write(record).

WHAT NOT TO DO IN THIS FILE:
    1. Do not import boto3 at module level; every symbol comes from the lazy
       _import_driver() so this module imports cleanly with boto3 absent.
    2. Do not hand-roll retry/backoff; botocore.config.Config(retries=...)
       already does this, tuned to S3's actual error/throttling taxonomy.
    3. Do not let a raw ClientError/NoCredentialsError/etc. escape write() or
       verify(); every vendor exception must pass through _translate_error()
       first so callers see a specific HarnessSinkError subclass.
    4. Do not implement multipart upload; SinkEncoding.guard_size() rejects an
       oversized record before any network call instead (see Alternative 4 in
       the design doc).

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
    tests/test_cloud_trajectory_sinks.py.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
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
from vidbyte.harnesses.stores._sink_support import SinkEncoding
from vidbyte.lib.dataclasses.cloud_sinks import S3Credentials, S3SinkConfig
from vidbyte.lib.errors import ConfigurationError

_RETRYABLE_CODES = {"SlowDown", "RequestTimeout"}
_AUTHENTICATION_CODES = {"ExpiredToken", "InvalidAccessKeyId", "SignatureDoesNotMatch"}
_SETUP_CODES = {"NoSuchBucket", "PermanentRedirect"}
_CONDITION_CODES = {"PreconditionFailed", "ConditionalRequestConflict", "412"}
_HTTP_SERVER_ERROR_THRESHOLD = 500


class S3TrajectorySink:
    """TrajectorySink writing one JSONL object per run to an S3(-compatible) bucket."""

    def __init__(self, config: S3SinkConfig, *, credentials: S3Credentials | None = None) -> None:
        # Binds config/credentials, lazily imports boto3, and eagerly builds the client (no network call yet).
        self._config = config
        self._credentials = credentials
        if config.sse_customer_algorithm is not None and (credentials is None or credentials.sse_customer_key is None):
            raise ConfigurationError("sse_customer_algorithm requires credentials.sse_customer_key.")
        if credentials is not None and credentials.sse_customer_key is not None and config.sse_customer_algorithm is None:
            raise ConfigurationError("credentials.sse_customer_key requires config.sse_customer_algorithm=\"AES256\".")
        self._driver = self._import_driver()
        self._client = self._build_client()
        self._verify_task: asyncio.Task[None] | None = None

    async def verify(self) -> None:
        # Explicit, caller-invoked preflight check — call before a long run to fail fast on setup/auth problems.
        await self._ensure_ready()

    async def write(self, record: TrajectoryRecord) -> None:
        # Encodes one record, guards its size, and uploads it as a single object keyed by run_id.
        payload = SinkEncoding.prepare_payload(record, content_encoding=self._config.content_encoding)
        await self._ensure_ready()
        await self._put(self._object_key(record.run_id), payload)

    def _build_client(self) -> Any:
        # @intent reveal-secret-only-at-client-construction
        # Constructs the boto3 S3 client, resolving cross-account role assumption first when configured.
        # Retry/backoff is boto3's own Config, never a hand-rolled loop; .reveal() is called only here,
        # right before the vendor client needs the real value, never logged or stored elsewhere.
        config_kwargs: dict[str, Any] = {"retries": {"max_attempts": self._config.max_retries, "mode": "adaptive"}, "region_name": self._config.region}
        s3_options: dict[str, bool] = {}
        if self._config.use_accelerate_endpoint:
            s3_options["use_accelerate_endpoint"] = True
        if self._config.use_dualstack_endpoint:
            s3_options["use_dualstack_endpoint"] = True
        if s3_options:
            config_kwargs["s3"] = s3_options
        retry_config = self._driver.BotoConfig(**config_kwargs)
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

    async def _ensure_ready(self) -> None:
        # Memoizes the preflight check as one shared task; the synchronous check-and-create between await points needs no lock, since asyncio only yields control at an await.
        if self._verify_task is None:
            self._verify_task = asyncio.ensure_future(self._run_preflight())
        await self._verify_task

    async def _run_preflight(self) -> None:
        # Confirms the bucket exists and is reachable before any write is attempted.
        try:
            await asyncio.to_thread(self._client.head_bucket, Bucket=self._config.bucket)
        except Exception as exc:
            raise self._translate_error(exc) from exc

    def _object_key(self, run_id: str) -> str:
        # Builds "{prefix}/{run_id}.jsonl", or "{run_id}.jsonl" when prefix is empty.
        prefix = self._config.prefix.rstrip("/")
        return f"{prefix}/{run_id}.jsonl" if prefix else f"{run_id}.jsonl"

    # @intent preserve-s3-object-contract
    # Keep every optional PutObject control explicit so tags, retention, and conditions cannot be silently dropped.
    async def _put(self, key: str, payload: bytes) -> None:
        kwargs = self._base_put_kwargs(key, payload)
        kwargs.update(self._retention_put_kwargs())
        kwargs.update(self._encryption_put_kwargs())
        try:
            await asyncio.to_thread(self._client.put_object, **kwargs)
        except Exception as exc:
            raise self._translate_error(exc) from exc

    # @intent preserve-s3-content-contract
    # Omit unset headers so provider defaults remain active on modern and compatible S3 endpoints.
    def _base_put_kwargs(self, key: str, payload: bytes) -> dict[str, Any]:
        optional = {
            "ContentType": self._config.content_type,
            "ContentEncoding": self._config.content_encoding,
            "CacheControl": self._config.cache_control,
            "ContentDisposition": self._config.content_disposition,
            "Metadata": self._config.metadata or None,
            "Tagging": urlencode(self._config.tags) if self._config.tags else None,
            "IfMatch": self._config.if_match,
            "IfNoneMatch": self._config.if_none_match,
            "ACL": self._config.acl,
            "GrantRead": self._config.grant_read,
            "GrantReadACP": self._config.grant_read_acp,
            "GrantWriteACP": self._config.grant_write_acp,
            "ChecksumAlgorithm": self._config.checksum_algorithm,
            "ContentMD5": self._config.content_md5,
            "RequestPayer": self._config.request_payer,
            "Expires": self._config.expires,
            "WebsiteRedirectLocation": self._config.website_redirect_location,
        }
        return {"Bucket": self._config.bucket, "Key": key, "Body": payload, "StorageClass": self._config.storage_class.value, **{name: value for name, value in optional.items() if value is not None}}

    # @intent preserve-s3-retention-contract
    # Keep Object Lock headers together so governance and legal-hold settings travel with the object.
    def _retention_put_kwargs(self) -> dict[str, Any]:
        return {name: value for name, value in {"ObjectLockMode": self._config.object_lock_mode, "ObjectLockRetainUntilDate": self._config.object_lock_retain_until_date, "ObjectLockLegalHoldStatus": self._config.object_lock_legal_hold_status}.items() if value is not None}

    # @intent preserve-s3-encryption-contract
    # Use exactly one encryption mode and never log or place raw customer keys in persistent config.
    def _encryption_put_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if self._config.sse is not None:
            kwargs["ServerSideEncryption"] = self._config.sse
            if self._config.kms_key_id is not None:
                kwargs["SSEKMSKeyId"] = self._config.kms_key_id
            if self._config.kms_encryption_context:
                context = json.dumps(self._config.kms_encryption_context, sort_keys=True, separators=(",", ":")).encode("utf-8")
                kwargs["SSEKMSEncryptionContext"] = base64.b64encode(context).decode("ascii")
            if self._config.bucket_key_enabled is not None:
                kwargs["BucketKeyEnabled"] = self._config.bucket_key_enabled
        if self._config.sse_customer_algorithm is not None:
            credentials = self._credentials
            if credentials is None or credentials.sse_customer_key is None:
                raise ConfigurationError("sse_customer_algorithm requires credentials.sse_customer_key.")
            raw = credentials.sse_customer_key.reveal()
            raw_bytes = raw if isinstance(raw, bytes) else raw.encode("utf-8")
            kwargs["SSECustomerAlgorithm"] = self._config.sse_customer_algorithm
            kwargs["SSECustomerKey"] = raw
            kwargs["SSECustomerKeyMD5"] = credentials.sse_customer_key_md5 or base64.b64encode(hashlib.md5(raw_bytes, usedforsecurity=False).digest()).decode("ascii")
        return kwargs

    def _translate_error(self, exc: Exception, *, during_role_assumption: bool = False) -> HarnessSinkError:
        # Maps a boto3/botocore exception to the specific HarnessSinkError subclass a caller can act on.
        if during_role_assumption:
            return HarnessSinkAuthenticationError(
                "Cross-account role assumption failed; the base identity could not become role_arn.",
                details={"role_arn": self._config.role_arn, "error_type": type(exc).__name__},
            )
        if isinstance(exc, self._driver.NoCredentialsError):
            return HarnessSinkAuthenticationError("No AWS credentials could be resolved (no static keys and the default credential chain is empty).", details={"error_type": type(exc).__name__})
        if isinstance(exc, (self._driver.EndpointConnectionError, self._driver.ConnectTimeoutError)):
            return HarnessSinkUnavailableError("Could not reach the configured S3 endpoint.", details={"endpoint_url": self._config.endpoint_url, "error_type": type(exc).__name__})
        if isinstance(exc, self._driver.ClientError):
            return self._translate_client_error(exc)
        return HarnessSinkError("S3 request failed for an unrecognized reason.", details={"error_type": type(exc).__name__})

    def _translate_client_error(self, exc: Any) -> HarnessSinkError:
        # Maps a botocore ClientError's response Code/HTTPStatusCode to the matching subclass.
        code = str(exc.response.get("Error", {}).get("Code", ""))
        status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in _SETUP_CODES:
            return HarnessSinkSetupError(f"S3 reported the bucket could not be resolved ({code}).", details={"bucket": self._config.bucket, "region": self._config.region, "code": code})
        if code in _AUTHENTICATION_CODES:
            return HarnessSinkAuthenticationError(f"S3 rejected the supplied credentials ({code}).", details={"code": code})
        if code == "AccessDenied":
            return HarnessSinkAuthorizationError(
                "S3 denied this write. If this bucket requires server-side encryption, confirm sse/kms_key_id is set — a missing encryption header surfaces as AccessDenied too.",
                details={"bucket": self._config.bucket, "code": code},
            )
        if code in _CONDITION_CODES:
            return HarnessSinkAuthorizationError(
                "S3 rejected the conditional write because the object's current version did not match the configured condition.",
                details={"bucket": self._config.bucket, "code": code},
            )
        if code in _RETRYABLE_CODES or (status_code is not None and status_code >= _HTTP_SERVER_ERROR_THRESHOLD):
            return HarnessSinkUnavailableError(f"S3 was unavailable after boto3's own retries were exhausted ({code or status_code}).", details={"code": code, "status_code": status_code})
        return HarnessSinkError(f"S3 rejected the request ({code}).", details={"code": code, "status_code": status_code})

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
