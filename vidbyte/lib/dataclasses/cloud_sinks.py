"""FILE: vidbyte/lib/dataclasses/cloud_sinks.py

PURPOSE:
    Defines the strictly-validated Config/Credentials shapes and storage-tier
    enums shared by every cloud TrajectorySink (S3, GCS, Azure Blob). This file
    owns Stage 1 (local, syntactic) validation only; it must not perform I/O or
    know anything about a vendor SDK.

ROLE IN CODEBASE:
    Imported by vidbyte/harnesses/stores/{s3,gcs,azure_blob}.py and by
    vidbyte/harnesses/client.py's s3_sink()/gcs_sink()/azure_blob_sink()
    factories. Config and Credentials are deliberately separate types so a
    sink's non-secret settings stay freely loggable while its secret half is
    structurally distinguishable in every constructor signature.

ARCHITECTURE NOTE:
    Follows the same pattern vidbyte/lib/dataclasses/agents.py already uses for
    AgentFallbackConfig/PauseDuration: one frozen, slotted dataclass per shape,
    every validation rule in __post_init__, raising vidbyte.lib.errors
    ConfigurationError. This module sits in vidbyte/lib — a layer beneath
    vidbyte/harnesses — so it must never import from vidbyte.harnesses; remote,
    semantic failures (bucket doesn't exist, access denied) are Stage 2 and
    raise the HarnessSinkError subclasses defined one layer up instead.

PUBLIC API INVENTORY:
    S3StorageClass, GcsStorageClass, AzureBlobTier; Secret; S3SinkConfig,
    S3Credentials; GcsSinkConfig, GcsCredentials; AzureBlobSinkConfig,
    AzureBlobCredentials.

COMMON MODIFICATION PATTERNS:
    Add a new Config/Credentials field here first, validate it in
    __post_init__, then update the matching sink's _build_client()/_put() in
    vidbyte/harnesses/stores/.

WHAT NOT TO DO IN THIS FILE:
    1. Do not import boto3/google-cloud-storage/azure-storage-blob here — this
       module must import cleanly with none of them installed.
    2. Do not import from vidbyte.harnesses (layering: lib is beneath domains).
    3. Do not raise a HarnessSinkError subclass here; only ConfigurationError.
    4. Do not perform the full AWS/GCS/Azure bucket-naming spec (reserved
       prefixes, IP-shaped names). The live preflight check in each sink's
       verify() is the real source of truth for "does this bucket work."

KNOWN EDGE CASES:
    Secret.__repr__/__str__ always return "Secret(<redacted>)" regardless of
    the wrapped value; reveal() is the one explicit escape hatch, called only
    at the point a vendor client is actually constructed.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/cloud-trajectory-sinks.md

TESTS:
    tests/test_cloud_trajectory_sinks.py.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from vidbyte.lib.constants.cloud_sinks import DEFAULT_SINK_MAX_RETRIES, MAX_BUCKET_NAME_LENGTH, MIN_BUCKET_NAME_LENGTH
from vidbyte.lib.errors import ConfigurationError

_NAME_PATTERN = re.compile(r"^[a-z0-9.-]+$")


def _validate_bucket_like_name(value: str, *, field_name: str) -> None:
    # Rejects an empty, over/under-length, or obviously-invalid-character bucket/container name.
    if not value or not value.strip():
        raise ConfigurationError(f"{field_name} must be a non-empty string.", details={"field": field_name})
    if not (MIN_BUCKET_NAME_LENGTH <= len(value) <= MAX_BUCKET_NAME_LENGTH):
        raise ConfigurationError(
            f"{field_name} must be between {MIN_BUCKET_NAME_LENGTH} and {MAX_BUCKET_NAME_LENGTH} characters.",
            details={"field": field_name, "actual_length": len(value)},
        )
    if not _NAME_PATTERN.match(value):
        raise ConfigurationError(
            f"{field_name} contains characters outside the conservative [a-z0-9.-] set.",
            details={"field": field_name, "value": value},
        )


def _validate_max_retries(value: int) -> None:
    # Rejects a non-int, a bool (an int subclass), or a negative retry count.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationError("max_retries must be an integer.", details={"actual_type": type(value).__name__})
    if value < 0:
        raise ConfigurationError("max_retries must be non-negative.", details={"actual_value": value})


class S3StorageClass(str, Enum):
    """AWS S3 storage classes this sink accepts for `PutObject`."""

    STANDARD = "STANDARD"
    STANDARD_IA = "STANDARD_IA"
    INTELLIGENT_TIERING = "INTELLIGENT_TIERING"
    GLACIER_IR = "GLACIER_IR"
    GLACIER = "GLACIER"
    DEEP_ARCHIVE = "DEEP_ARCHIVE"
    ONEZONE_IA = "ONEZONE_IA"


class GcsStorageClass(str, Enum):
    """Google Cloud Storage storage classes this sink accepts."""

    STANDARD = "STANDARD"
    NEARLINE = "NEARLINE"
    COLDLINE = "COLDLINE"
    ARCHIVE = "ARCHIVE"


class AzureBlobTier(str, Enum):
    """Azure Blob Storage access tiers this sink accepts."""

    HOT = "Hot"
    COOL = "Cool"
    COLD = "Cold"
    ARCHIVE = "Archive"


@dataclass(frozen=True, slots=True)
class Secret:
    """Wraps one credential value so repr()/str() never render it."""

    value: str

    def __post_init__(self) -> None:
        """Reject an empty secret value."""
        if not self.value:
            raise ConfigurationError("Secret value must not be empty.")

    def __repr__(self) -> str:
        """Always return the redacted marker, never the wrapped value."""
        return "Secret(<redacted>)"

    def __str__(self) -> str:
        """Always return the redacted marker, never the wrapped value."""
        return "Secret(<redacted>)"

    def reveal(self) -> str:
        """Return the real wrapped value. The one explicit, named escape hatch."""
        return self.value


@dataclass(frozen=True, slots=True)
class S3SinkConfig:
    """Non-secret settings for `S3TrajectorySink` — bucket, tier, encryption, retries."""

    bucket: str
    prefix: str = ""
    region: str | None = None
    endpoint_url: str | None = None
    storage_class: S3StorageClass = S3StorageClass.STANDARD
    sse: Literal["AES256", "aws:kms"] | None = None
    kms_key_id: str | None = None
    role_arn: str | None = None
    external_id: str | None = None
    max_retries: int = DEFAULT_SINK_MAX_RETRIES

    def __post_init__(self) -> None:
        """Validate the bucket name, tier membership, encryption pairing, and retry count."""
        _validate_bucket_like_name(self.bucket, field_name="bucket")
        if not isinstance(self.storage_class, S3StorageClass):
            raise ConfigurationError(
                "storage_class must be an S3StorageClass member.",
                details={"accepted": [member.value for member in S3StorageClass], "actual_type": type(self.storage_class).__name__},
            )
        if self.sse is not None and self.sse not in ("AES256", "aws:kms"):
            raise ConfigurationError('sse must be "AES256", "aws:kms", or None.', details={"actual_value": str(self.sse)})
        if self.sse == "aws:kms" and self.kms_key_id is None:
            raise ConfigurationError('kms_key_id is required when sse="aws:kms".')
        if self.external_id is not None and self.role_arn is None:
            warnings.warn("S3SinkConfig.external_id has no effect without role_arn set.", stacklevel=2)
        _validate_max_retries(self.max_retries)


@dataclass(frozen=True, slots=True)
class S3Credentials:
    """Static AWS credentials for `S3TrajectorySink`. All-None selects boto3's default credential chain."""

    access_key_id: str | None = None
    secret_access_key: Secret | None = None
    session_token: Secret | None = None

    # @intent all-or-nothing-credential-pairing
    # A lone access_key_id with no secret_access_key is a configuration mistake, not a valid
    # "use the default chain" signal — that signal is only both fields left None.
    def __post_init__(self) -> None:
        """Require access_key_id and secret_access_key to be both set or both None."""
        has_key_id = self.access_key_id is not None
        has_secret = self.secret_access_key is not None
        if has_key_id != has_secret:
            raise ConfigurationError("access_key_id and secret_access_key must both be set, or both left None to use the default credential chain.")


@dataclass(frozen=True, slots=True)
class GcsSinkConfig:
    """Non-secret settings for `GcsTrajectorySink` — bucket, tier, CMEK, retries."""

    bucket: str
    prefix: str = ""
    storage_class: GcsStorageClass = GcsStorageClass.STANDARD
    kms_key_name: str | None = None
    max_retries: int = DEFAULT_SINK_MAX_RETRIES

    def __post_init__(self) -> None:
        """Validate the bucket name, tier membership, and retry count."""
        _validate_bucket_like_name(self.bucket, field_name="bucket")
        if not isinstance(self.storage_class, GcsStorageClass):
            raise ConfigurationError(
                "storage_class must be a GcsStorageClass member.",
                details={"accepted": [member.value for member in GcsStorageClass], "actual_type": type(self.storage_class).__name__},
            )
        _validate_max_retries(self.max_retries)


@dataclass(frozen=True, slots=True)
class GcsCredentials:
    """Service-account credentials for `GcsTrajectorySink`. None selects Application Default Credentials."""

    service_account_json_path: str | None = None

    def __post_init__(self) -> None:
        """Reject an empty (but non-None) service account path."""
        if self.service_account_json_path is not None and not self.service_account_json_path.strip():
            raise ConfigurationError("service_account_json_path must not be an empty string; omit it entirely to use Application Default Credentials.")


@dataclass(frozen=True, slots=True)
class AzureBlobSinkConfig:
    """Non-secret settings for `AzureBlobTrajectorySink` — container, tier, retries."""

    container: str
    prefix: str = ""
    tier: AzureBlobTier = AzureBlobTier.HOT
    max_retries: int = DEFAULT_SINK_MAX_RETRIES

    def __post_init__(self) -> None:
        """Validate the container name, tier membership, and retry count."""
        _validate_bucket_like_name(self.container, field_name="container")
        if not isinstance(self.tier, AzureBlobTier):
            raise ConfigurationError(
                "tier must be an AzureBlobTier member.",
                details={"accepted": [member.value for member in AzureBlobTier], "actual_type": type(self.tier).__name__},
            )
        _validate_max_retries(self.max_retries)


@dataclass(frozen=True, slots=True)
class AzureBlobCredentials:
    """Account address plus optional secret for `AzureBlobTrajectorySink`.

    Both `connection_string` and `sas_token` left None selects the keyless
    `DefaultAzureCredential` path (managed identity / Azure AD) against
    `account_url`. Unlike S3/GCS, this object is required, not optional, since
    `account_url` identifies which storage account to talk to — Azure has no
    implicit default account the way AWS/GCP have an implicit default region
    or project.
    """

    account_url: str
    connection_string: Secret | None = None
    sas_token: Secret | None = None

    def __post_init__(self) -> None:
        """Reject an empty account_url."""
        if not self.account_url or not self.account_url.strip():
            raise ConfigurationError("account_url must be a non-empty string.")


__all__ = [
    "AzureBlobCredentials",
    "AzureBlobSinkConfig",
    "AzureBlobTier",
    "GcsCredentials",
    "GcsSinkConfig",
    "GcsStorageClass",
    "S3Credentials",
    "S3SinkConfig",
    "S3StorageClass",
    "Secret",
]
