"""FILE: vidbyte/lib/dataclasses/cloud_sinks.py

PURPOSE:
    Defines the strictly-validated Config/Credentials shapes, provider profiles,
    and storage-tier enums shared by every cloud TrajectorySink (S3-compatible,
    GCS, Azure Blob, OCI, and Alibaba OSS). This file
    owns Stage 1 (local, syntactic) validation only; it must not perform I/O or
    know anything about a vendor SDK.

ROLE IN CODEBASE:
    Imported by vidbyte/harnesses/stores/{s3,gcs,azure_blob,oci,oss}.py and by
    vidbyte/harnesses/client.py's cloud sink factories.
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
    S3/GCS/Azure/OCI/OSS Config and Credentials types; provider, auth,
    checksum, overwrite, preflight, and storage-tier enums; S3 capability
    profiles; and Secret.

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
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/cloud-trajectory-provider-expansion.md

TESTS:
    tests/test_cloud_trajectory_sinks.py.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, ClassVar, Literal

from vidbyte.lib.constants.cloud_sinks import (
    DEFAULT_MULTIPART_MAX_CONCURRENCY,
    DEFAULT_MULTIPART_PART_BYTES,
    DEFAULT_MULTIPART_THRESHOLD_BYTES,
    DEFAULT_SINK_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_SINK_MAX_RETRIES,
    DEFAULT_SINK_READ_TIMEOUT_SECONDS,
    MAX_BUCKET_NAME_LENGTH,
    MAX_MULTIPART_CONCURRENCY,
    MAX_MULTIPART_PART_BYTES,
    MAX_SINK_TIMEOUT_SECONDS,
    MIN_BUCKET_NAME_LENGTH,
    MIN_MULTIPART_PART_BYTES,
    MIN_SINK_TIMEOUT_SECONDS,
)
from vidbyte.lib.errors import ConfigurationError

_NAME_PATTERN = re.compile(r"^[a-z0-9.-]+$")


def _validate_bucket_like_name(value: str, *, field_name: str) -> None:
    # Rejects an empty, over/under-length, or obviously-invalid-character bucket/container name.
    if not isinstance(value, str) or not value.strip():
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


def _validate_prefix(value: str) -> None:
    """Reject prefixes that could escape the sink's intended key namespace."""
    if not isinstance(value, str) or "\x00" in value or value.startswith("/"):
        raise ConfigurationError("prefix must be a relative string without NUL bytes.")
    if any(segment in (".", "..") for segment in value.split("/")):
        raise ConfigurationError("prefix must not contain dot path segments.")


def _normalize_pairs(value: Mapping[str, str] | Sequence[tuple[str, str]], *, field_name: str) -> tuple[tuple[str, str], ...]:
    """Normalize metadata/tag pairs into a deterministic immutable shape."""
    items = tuple(value.items()) if isinstance(value, Mapping) else tuple(value)
    normalized: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ConfigurationError(f"{field_name} must contain (name, value) pairs.", details={"field": field_name})
        name, pair_value = item
        if not isinstance(name, str) or not isinstance(pair_value, str) or not name or "\x00" in name or "\x00" in pair_value:
            raise ConfigurationError(f"{field_name} names and values must be non-empty strings without NUL bytes.", details={"field": field_name})
        normalized.append((name, pair_value))
    names = [name for name, _ in normalized]
    if len(set(names)) != len(names):
        raise ConfigurationError(f"{field_name} names must be unique.", details={"field": field_name})
    return tuple(sorted(normalized))


def _validate_common_options(
    *,
    content_type: str,
    metadata: Mapping[str, str] | Sequence[tuple[str, str]],
    tags: Mapping[str, str] | Sequence[tuple[str, str]],
    connect_timeout_seconds: float,
    read_timeout_seconds: float,
    multipart_threshold_bytes: int,
    multipart_part_size_bytes: int,
    multipart_max_concurrency: int,
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    """Validate shared transport and object-attribute settings."""
    if not isinstance(content_type, str) or not content_type.strip() or "\x00" in content_type:
        raise ConfigurationError("content_type must be a non-empty string without NUL bytes.")
    for field_name, value in (("connect_timeout_seconds", connect_timeout_seconds), ("read_timeout_seconds", read_timeout_seconds)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not MIN_SINK_TIMEOUT_SECONDS <= value <= MAX_SINK_TIMEOUT_SECONDS:
            raise ConfigurationError(f"{field_name} must be between {MIN_SINK_TIMEOUT_SECONDS} and {MAX_SINK_TIMEOUT_SECONDS} seconds.")
    if isinstance(multipart_threshold_bytes, bool) or not isinstance(multipart_threshold_bytes, int) or multipart_threshold_bytes < 0:
        raise ConfigurationError("multipart_threshold_bytes must be a non-negative integer.")
    if isinstance(multipart_part_size_bytes, bool) or not isinstance(multipart_part_size_bytes, int) or not MIN_MULTIPART_PART_BYTES <= multipart_part_size_bytes <= MAX_MULTIPART_PART_BYTES:
        raise ConfigurationError("multipart_part_size_bytes is outside the supported provider range.")
    if isinstance(multipart_max_concurrency, bool) or not isinstance(multipart_max_concurrency, int) or not 1 <= multipart_max_concurrency <= MAX_MULTIPART_CONCURRENCY:
        raise ConfigurationError("multipart_max_concurrency must be between 1 and the shared concurrency limit.")
    return _normalize_pairs(metadata, field_name="metadata"), _normalize_pairs(tags, field_name="tags")


def _validate_s3_storage_and_encryption(config: Any) -> None:
    """Validate S3 storage and encryption pairing before profile checks."""
    if not isinstance(config.storage_class, S3StorageClass):
        raise ConfigurationError(
            "storage_class must be an S3StorageClass member.",
            details={"accepted": [member.value for member in S3StorageClass], "actual_type": type(config.storage_class).__name__},
        )
    if config.sse is not None and config.sse not in ("AES256", "aws:kms", "AES256-C"):
        raise ConfigurationError('sse must be "AES256", "aws:kms", "AES256-C", or None.', details={"actual_value": str(config.sse)})
    if config.sse == "aws:kms" and config.kms_key_id is None:
        raise ConfigurationError('kms_key_id is required when sse="aws:kms".')


def _validate_s3_profile_options(config: Any) -> None:
    """Reject object options not advertised by the selected S3 profile."""
    # @intent profile-capabilities-fail-closed
    # Named S3-compatible endpoints are not interchangeable; unsupported
    # encryption, tag, checksum, and tier settings must be rejected locally.
    if not isinstance(config.provider, S3CompatibleProvider):
        raise ConfigurationError("provider must be an S3CompatibleProvider member.")
    if config.endpoint_url is not None and (not isinstance(config.endpoint_url, str) or not config.endpoint_url.strip()):
        raise ConfigurationError("endpoint_url must be a non-empty string when provided.")
    if config.provider is not S3CompatibleProvider.AWS and not config.endpoint_url:
        raise ConfigurationError(f"{config.provider.value} requires endpoint_url because it is not resolved by AWS endpoint discovery.")
    if config.provider is S3CompatibleProvider.CLOUDFLARE_R2 and config.region not in (None, "auto"):
        raise ConfigurationError("Cloudflare R2 requires region='auto' when region is provided.")
    capabilities = S3CompatibleProfiles.get(config.provider)
    if config.storage_class not in capabilities.supported_storage_classes:
        raise ConfigurationError(
            f"{config.provider.value} does not support storage class {config.storage_class.value}.",
            details={"provider": config.provider.value, "storage_class": config.storage_class.value},
        )
    _validate_s3_profile_encryption(config, capabilities)
    if config.checksum_algorithm is not None and not capabilities.supports_checksums:
        raise ConfigurationError(f"{config.provider.value} does not advertise S3 checksum support.")
    if config.tags and not capabilities.supports_tags:
        raise ConfigurationError(f"{config.provider.value} does not advertise object tag support.")


def _validate_s3_profile_encryption(config: Any, capabilities: S3CompatibleCapabilities) -> None:
    # @intent profile-encryption-capabilities-are-explicit
    # Each S3 encryption header has a separate compatibility contract; reject
    # only the unsupported mode instead of silently downgrading encryption.
    if config.sse == "aws:kms" and not capabilities.supports_sse_kms:
        raise ConfigurationError(f"{config.provider.value} does not support aws:kms encryption.")
    if config.sse == "AES256" and not capabilities.supports_sse_s3:
        raise ConfigurationError(f"{config.provider.value} does not support provider-managed SSE-S3 request headers.")
    if config.sse == "AES256-C" and not capabilities.supports_sse_c:
        raise ConfigurationError(f"{config.provider.value} does not support customer-provided encryption keys.")


def _validate_s3_lock_options(config: Any) -> None:
    """Keep object-lock request fields limited to verified AWS semantics."""
    # @intent object-lock-is-not-portable
    # Similar-looking headers have different retention guarantees across
    # vendors, so only the verified AWS profile may receive them.
    if any(value is not None for value in (config.object_lock_mode, config.object_lock_retain_until, config.legal_hold)) and config.provider is not S3CompatibleProvider.AWS:
        raise ConfigurationError("object lock request fields are only enabled for the AWS S3 profile until provider support is verified.")
    if config.object_lock_mode not in (None, "GOVERNANCE", "COMPLIANCE"):
        raise ConfigurationError("object_lock_mode must be GOVERNANCE, COMPLIANCE, or None.")
    if config.legal_hold not in (None, "ON", "OFF"):
        raise ConfigurationError("legal_hold must be ON, OFF, or None.")
    if config.object_lock_retain_until is not None and (not isinstance(config.object_lock_retain_until, datetime) or config.object_lock_retain_until.tzinfo is None):
        raise ConfigurationError("object_lock_retain_until must be timezone-aware.")


def _validate_s3_enum_options(config: Any) -> None:
    """Validate the enum-typed S3 extension fields."""
    enum_fields = (("checksum_algorithm", S3ChecksumAlgorithm), ("overwrite_mode", SinkOverwriteMode), ("preflight_mode", SinkPreflightMode))
    for field_name, enum_type in enum_fields:
        value = getattr(config, field_name)
        if value is not None and not isinstance(value, enum_type):
            raise ConfigurationError(f"{field_name} must be a {enum_type.__name__} member.")


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


class GcsChecksumAlgorithm(str, Enum):
    """Object checksum algorithms supported by the GCS upload API."""

    CRC32C = "crc32c"
    MD5 = "md5"


class AzureBlobTier(str, Enum):
    """Azure Blob Storage access tiers this sink accepts."""

    HOT = "Hot"
    COOL = "Cool"
    COLD = "Cold"
    ARCHIVE = "Archive"


class S3CompatibleProvider(str, Enum):
    """Named endpoint profiles for S3-compatible object stores."""

    AWS = "aws"
    CLOUDFLARE_R2 = "cloudflare_r2"
    BACKBLAZE_B2 = "backblaze_b2"
    DIGITALOCEAN_SPACES = "digitalocean_spaces"
    IBM_COS = "ibm_cos"
    WASABI = "wasabi"
    MINIO = "minio"


class S3ChecksumAlgorithm(str, Enum):
    """Checksum names accepted by modern S3-compatible PutObject APIs."""

    CRC32 = "CRC32"
    CRC32C = "CRC32C"
    SHA1 = "SHA1"
    SHA256 = "SHA256"


class SinkOverwriteMode(str, Enum):
    """Whether a retry may replace an existing object for the same run id."""

    OVERWRITE = "overwrite"
    CREATE_ONLY = "create_only"


class SinkPreflightMode(str, Enum):
    """How a sink verifies destination readiness."""

    METADATA = "metadata"
    WRITE_PROBE = "write_probe"


@dataclass(frozen=True, slots=True)
class S3CompatibleCapabilities:
    """Provider-specific features used to reject unsafe S3 request options."""

    provider: S3CompatibleProvider
    default_region: str | None
    supported_storage_classes: tuple[S3StorageClass, ...]
    supports_sse_kms: bool
    supports_sse_s3: bool
    supports_sse_c: bool
    supports_tags: bool
    supports_checksums: bool
    supports_multipart: bool


class S3CompatibleProfiles:
    """Class-bound registry for named S3-compatible provider capabilities."""

    _PROFILES: ClassVar[Mapping[S3CompatibleProvider, S3CompatibleCapabilities]] = MappingProxyType({
        S3CompatibleProvider.AWS: S3CompatibleCapabilities(
            provider=S3CompatibleProvider.AWS,
            default_region=None,
            supported_storage_classes=tuple(S3StorageClass),
            supports_sse_kms=True,
            supports_sse_s3=True,
            supports_sse_c=True,
            supports_tags=True,
            supports_checksums=True,
            supports_multipart=True,
        ),
        S3CompatibleProvider.CLOUDFLARE_R2: S3CompatibleCapabilities(
            provider=S3CompatibleProvider.CLOUDFLARE_R2,
            default_region="auto",
            supported_storage_classes=(S3StorageClass.STANDARD, S3StorageClass.STANDARD_IA),
            supports_sse_kms=False,
            supports_sse_s3=False,
            supports_sse_c=True,
            supports_tags=False,
            supports_checksums=True,
            supports_multipart=True,
        ),
        S3CompatibleProvider.BACKBLAZE_B2: S3CompatibleCapabilities(
            provider=S3CompatibleProvider.BACKBLAZE_B2,
            default_region=None,
            supported_storage_classes=(S3StorageClass.STANDARD,),
            supports_sse_kms=False,
            supports_sse_s3=True,
            supports_sse_c=True,
            supports_tags=False,
            supports_checksums=True,
            supports_multipart=True,
        ),
        S3CompatibleProvider.DIGITALOCEAN_SPACES: S3CompatibleCapabilities(
            provider=S3CompatibleProvider.DIGITALOCEAN_SPACES,
            default_region=None,
            supported_storage_classes=(S3StorageClass.STANDARD,),
            supports_sse_kms=False,
            supports_sse_s3=False,
            supports_sse_c=True,
            supports_tags=False,
            supports_checksums=False,
            supports_multipart=True,
        ),
        S3CompatibleProvider.IBM_COS: S3CompatibleCapabilities(
            provider=S3CompatibleProvider.IBM_COS,
            default_region=None,
            supported_storage_classes=(S3StorageClass.STANDARD,),
            supports_sse_kms=False,
            supports_sse_s3=True,
            supports_sse_c=False,
            supports_tags=True,
            supports_checksums=False,
            supports_multipart=True,
        ),
        S3CompatibleProvider.WASABI: S3CompatibleCapabilities(
            provider=S3CompatibleProvider.WASABI,
            default_region=None,
            supported_storage_classes=(S3StorageClass.STANDARD,),
            supports_sse_kms=False,
            supports_sse_s3=True,
            supports_sse_c=False,
            supports_tags=True,
            supports_checksums=False,
            supports_multipart=True,
        ),
        S3CompatibleProvider.MINIO: S3CompatibleCapabilities(
            provider=S3CompatibleProvider.MINIO,
            default_region=None,
            supported_storage_classes=(S3StorageClass.STANDARD,),
            supports_sse_kms=True,
            supports_sse_s3=True,
            supports_sse_c=True,
            supports_tags=True,
            supports_checksums=True,
            supports_multipart=True,
        ),
    })

    @classmethod
    def get(cls, provider: S3CompatibleProvider) -> S3CompatibleCapabilities:
        """Return the immutable capability record for one provider profile."""
        # @intent capability-registry-is-class-bound
        # A single named registry keeps profile behavior discoverable and avoids
        # duplicated capability branches across factories and adapters.
        return cls._PROFILES[provider]


@dataclass(frozen=True, slots=True)
class Secret:
    """Wraps one credential value so repr()/str() never render it."""

    value: str

    def __post_init__(self) -> None:
        """Reject an empty secret value."""
        if not isinstance(self.value, str) or not self.value:
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
    sse: Literal["AES256", "aws:kms", "AES256-C"] | None = None
    kms_key_id: str | None = None
    role_arn: str | None = None
    external_id: str | None = None
    max_retries: int = DEFAULT_SINK_MAX_RETRIES
    provider: S3CompatibleProvider = S3CompatibleProvider.AWS
    checksum_algorithm: S3ChecksumAlgorithm | None = None
    overwrite_mode: SinkOverwriteMode = SinkOverwriteMode.OVERWRITE
    preflight_mode: SinkPreflightMode = SinkPreflightMode.METADATA
    content_type: str = "application/x-ndjson"
    metadata: Mapping[str, str] | Sequence[tuple[str, str]] = ()
    tags: Mapping[str, str] | Sequence[tuple[str, str]] = ()
    connect_timeout_seconds: float = DEFAULT_SINK_CONNECT_TIMEOUT_SECONDS
    read_timeout_seconds: float = DEFAULT_SINK_READ_TIMEOUT_SECONDS
    multipart_threshold_bytes: int = DEFAULT_MULTIPART_THRESHOLD_BYTES
    multipart_part_size_bytes: int = DEFAULT_MULTIPART_PART_BYTES
    multipart_max_concurrency: int = DEFAULT_MULTIPART_MAX_CONCURRENCY
    object_lock_mode: Literal["GOVERNANCE", "COMPLIANCE"] | None = None
    object_lock_retain_until: datetime | None = None
    legal_hold: Literal["ON", "OFF"] | None = None

    def __post_init__(self) -> None:
        """Validate the bucket name, tier membership, encryption pairing, and retry count."""
        _validate_bucket_like_name(self.bucket, field_name="bucket")
        _validate_prefix(self.prefix)
        _validate_s3_storage_and_encryption(self)
        if self.external_id is not None and self.role_arn is None:
            warnings.warn("S3SinkConfig.external_id has no effect without role_arn set.", stacklevel=2)
        _validate_max_retries(self.max_retries)
        _validate_s3_profile_options(self)
        _validate_s3_lock_options(self)
        _validate_s3_enum_options(self)
        metadata, tags = _validate_common_options(
            content_type=self.content_type,
            metadata=self.metadata,
            tags=self.tags,
            connect_timeout_seconds=self.connect_timeout_seconds,
            read_timeout_seconds=self.read_timeout_seconds,
            multipart_threshold_bytes=self.multipart_threshold_bytes,
            multipart_part_size_bytes=self.multipart_part_size_bytes,
            multipart_max_concurrency=self.multipart_max_concurrency,
        )
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(self, "tags", tags)


@dataclass(frozen=True, slots=True)
class S3Credentials:
    """Static AWS credentials for `S3TrajectorySink`. All-None selects boto3's default credential chain."""

    access_key_id: str | None = None
    secret_access_key: Secret | None = None
    session_token: Secret | None = None
    customer_encryption_key: Secret | None = None

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
    checksum_algorithm: GcsChecksumAlgorithm | None = None
    overwrite_mode: SinkOverwriteMode = SinkOverwriteMode.OVERWRITE
    preflight_mode: SinkPreflightMode = SinkPreflightMode.METADATA
    content_type: str = "application/x-ndjson"
    metadata: Mapping[str, str] | Sequence[tuple[str, str]] = ()
    tags: Mapping[str, str] | Sequence[tuple[str, str]] = ()
    connect_timeout_seconds: float = DEFAULT_SINK_CONNECT_TIMEOUT_SECONDS
    read_timeout_seconds: float = DEFAULT_SINK_READ_TIMEOUT_SECONDS
    multipart_threshold_bytes: int = DEFAULT_MULTIPART_THRESHOLD_BYTES
    multipart_part_size_bytes: int = DEFAULT_MULTIPART_PART_BYTES
    multipart_max_concurrency: int = DEFAULT_MULTIPART_MAX_CONCURRENCY

    def __post_init__(self) -> None:
        """Validate the bucket name, tier membership, and retry count."""
        _validate_bucket_like_name(self.bucket, field_name="bucket")
        _validate_prefix(self.prefix)
        if not isinstance(self.storage_class, GcsStorageClass):
            raise ConfigurationError(
                "storage_class must be a GcsStorageClass member.",
                details={"accepted": [member.value for member in GcsStorageClass], "actual_type": type(self.storage_class).__name__},
            )
        if self.tags:
            raise ConfigurationError("GCS does not expose S3-style object tags; use metadata instead.")
        _validate_max_retries(self.max_retries)
        for field_name, enum_type in (("checksum_algorithm", GcsChecksumAlgorithm), ("overwrite_mode", SinkOverwriteMode), ("preflight_mode", SinkPreflightMode)):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, enum_type):
                raise ConfigurationError(f"{field_name} must be a {enum_type.__name__} member.")
        metadata, tags = _validate_common_options(
            content_type=self.content_type,
            metadata=self.metadata,
            tags=self.tags,
            connect_timeout_seconds=self.connect_timeout_seconds,
            read_timeout_seconds=self.read_timeout_seconds,
            multipart_threshold_bytes=self.multipart_threshold_bytes,
            multipart_part_size_bytes=self.multipart_part_size_bytes,
            multipart_max_concurrency=self.multipart_max_concurrency,
        )
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(self, "tags", tags)


@dataclass(frozen=True, slots=True)
class GcsCredentials:
    """Service-account credentials for `GcsTrajectorySink`. None selects Application Default Credentials."""

    service_account_json_path: str | None = None

    def __post_init__(self) -> None:
        """Reject an empty (but non-None) service account path."""
        if self.service_account_json_path is not None and (not isinstance(self.service_account_json_path, str) or not self.service_account_json_path.strip()):
            raise ConfigurationError("service_account_json_path must not be an empty string; omit it entirely to use Application Default Credentials.")


@dataclass(frozen=True, slots=True)
class AzureBlobSinkConfig:
    """Non-secret settings for `AzureBlobTrajectorySink` — container, tier, retries."""

    container: str
    prefix: str = ""
    tier: AzureBlobTier = AzureBlobTier.HOT
    max_retries: int = DEFAULT_SINK_MAX_RETRIES
    overwrite_mode: SinkOverwriteMode = SinkOverwriteMode.OVERWRITE
    preflight_mode: SinkPreflightMode = SinkPreflightMode.METADATA
    content_type: str = "application/x-ndjson"
    metadata: Mapping[str, str] | Sequence[tuple[str, str]] = ()
    tags: Mapping[str, str] | Sequence[tuple[str, str]] = ()
    connect_timeout_seconds: float = DEFAULT_SINK_CONNECT_TIMEOUT_SECONDS
    read_timeout_seconds: float = DEFAULT_SINK_READ_TIMEOUT_SECONDS
    multipart_threshold_bytes: int = DEFAULT_MULTIPART_THRESHOLD_BYTES
    multipart_part_size_bytes: int = DEFAULT_MULTIPART_PART_BYTES
    multipart_max_concurrency: int = DEFAULT_MULTIPART_MAX_CONCURRENCY

    def __post_init__(self) -> None:
        """Validate the container name, tier membership, and retry count."""
        _validate_bucket_like_name(self.container, field_name="container")
        _validate_prefix(self.prefix)
        if not isinstance(self.tier, AzureBlobTier):
            raise ConfigurationError(
                "tier must be an AzureBlobTier member.",
                details={"accepted": [member.value for member in AzureBlobTier], "actual_type": type(self.tier).__name__},
            )
        _validate_max_retries(self.max_retries)
        for field_name, enum_type in (("overwrite_mode", SinkOverwriteMode), ("preflight_mode", SinkPreflightMode)):
            value = getattr(self, field_name)
            if not isinstance(value, enum_type):
                raise ConfigurationError(f"{field_name} must be a {enum_type.__name__} member.")
        metadata, tags = _validate_common_options(
            content_type=self.content_type,
            metadata=self.metadata,
            tags=self.tags,
            connect_timeout_seconds=self.connect_timeout_seconds,
            read_timeout_seconds=self.read_timeout_seconds,
            multipart_threshold_bytes=self.multipart_threshold_bytes,
            multipart_part_size_bytes=self.multipart_part_size_bytes,
            multipart_max_concurrency=self.multipart_max_concurrency,
        )
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(self, "tags", tags)


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
        if not isinstance(self.account_url, str) or not self.account_url.strip():
            raise ConfigurationError("account_url must be a non-empty string.")


class OciStorageTier(str, Enum):
    """OCI Object Storage tiers that can be attached to an object upload."""

    STANDARD = "Standard"
    INFREQUENT_ACCESS = "InfrequentAccess"
    ARCHIVE = "Archive"


class OciAuthMode(str, Enum):
    """Credential resolution modes exposed by the OCI adapter."""

    DEFAULT = "default"
    CONFIG_FILE = "config_file"
    API_KEY = "api_key"
    SESSION_TOKEN = "session_token"
    INSTANCE_PRINCIPAL = "instance_principal"
    RESOURCE_PRINCIPAL = "resource_principal"
    OKE_WORKLOAD_IDENTITY = "oke_workload_identity"


@dataclass(frozen=True, slots=True)
class OciSinkConfig:
    """Non-secret OCI namespace, bucket, object, and upload settings."""

    namespace: str
    bucket: str
    prefix: str = ""
    region: str | None = None
    endpoint_url: str | None = None
    max_retries: int = DEFAULT_SINK_MAX_RETRIES
    storage_tier: OciStorageTier = OciStorageTier.STANDARD
    vault_kms_key_id: str | None = None
    checksum_algorithm: str | None = None
    overwrite_mode: SinkOverwriteMode = SinkOverwriteMode.OVERWRITE
    preflight_mode: SinkPreflightMode = SinkPreflightMode.METADATA
    content_type: str = "application/x-ndjson"
    metadata: Mapping[str, str] | Sequence[tuple[str, str]] = ()
    tags: Mapping[str, str] | Sequence[tuple[str, str]] = ()
    connect_timeout_seconds: float = DEFAULT_SINK_CONNECT_TIMEOUT_SECONDS
    read_timeout_seconds: float = DEFAULT_SINK_READ_TIMEOUT_SECONDS
    multipart_threshold_bytes: int = DEFAULT_MULTIPART_THRESHOLD_BYTES
    multipart_part_size_bytes: int = DEFAULT_MULTIPART_PART_BYTES
    multipart_max_concurrency: int = DEFAULT_MULTIPART_MAX_CONCURRENCY

    def __post_init__(self) -> None:
        """Validate OCI names, object options, and shared upload limits."""
        _validate_bucket_like_name(self.namespace, field_name="namespace")
        _validate_bucket_like_name(self.bucket, field_name="bucket")
        _validate_prefix(self.prefix)
        _validate_max_retries(self.max_retries)
        if not isinstance(self.storage_tier, OciStorageTier):
            raise ConfigurationError("storage_tier must be an OciStorageTier member.")
        if self.checksum_algorithm not in (None, "MD5", "SHA256"):
            raise ConfigurationError("checksum_algorithm must be None, MD5, or SHA256.")
        if not isinstance(self.overwrite_mode, SinkOverwriteMode) or not isinstance(self.preflight_mode, SinkPreflightMode):
            raise ConfigurationError("overwrite_mode and preflight_mode must use their enum types.")
        metadata, tags = _validate_common_options(
            content_type=self.content_type,
            metadata=self.metadata,
            tags=self.tags,
            connect_timeout_seconds=self.connect_timeout_seconds,
            read_timeout_seconds=self.read_timeout_seconds,
            multipart_threshold_bytes=self.multipart_threshold_bytes,
            multipart_part_size_bytes=self.multipart_part_size_bytes,
            multipart_max_concurrency=self.multipart_max_concurrency,
        )
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(self, "tags", tags)


@dataclass(frozen=True, slots=True)
class OciCredentials:
    """OCI credentials for config-file, API-key, token, or principal auth."""

    auth_mode: OciAuthMode = OciAuthMode.DEFAULT
    config_file_path: str | None = None
    profile: str = "DEFAULT"
    tenancy: str | None = None
    user: str | None = None
    fingerprint: str | None = None
    private_key: Secret | None = None
    private_key_path: str | None = None
    passphrase: Secret | None = None
    security_token: Secret | None = None

    def __post_init__(self) -> None:
        """Validate the selected OCI authentication shape without I/O."""
        if not isinstance(self.auth_mode, OciAuthMode):
            raise ConfigurationError("auth_mode must be an OciAuthMode member.")
        if not isinstance(self.profile, str) or not self.profile.strip():
            raise ConfigurationError("profile must not be empty.")
        if self.private_key is not None and self.private_key_path is not None:
            raise ConfigurationError("Provide private_key or private_key_path, not both.")
        if self.auth_mode is OciAuthMode.API_KEY:
            required = (self.tenancy, self.user, self.fingerprint, self.private_key or self.private_key_path)
            if any(value is None or (isinstance(value, str) and not value.strip()) for value in required):
                raise ConfigurationError("OCI API_KEY auth requires tenancy, user, fingerprint, and a private key or path.")
        if self.auth_mode is OciAuthMode.SESSION_TOKEN and self.security_token is None:
            raise ConfigurationError("OCI SESSION_TOKEN auth requires security_token.")


class OssStorageClass(str, Enum):
    """Alibaba OSS storage classes attachable to an object."""

    STANDARD = "Standard"
    IA = "IA"
    ARCHIVE = "Archive"
    COLD_ARCHIVE = "ColdArchive"
    DEEP_COLD_ARCHIVE = "DeepColdArchive"


class OssAuthMode(str, Enum):
    """Alibaba OSS credential resolution modes."""

    DEFAULT = "default"
    STATIC = "static"
    STS = "sts"


@dataclass(frozen=True, slots=True)
class OssSinkConfig:
    """Non-secret Alibaba OSS bucket and upload settings."""

    bucket: str
    region: str
    prefix: str = ""
    endpoint_url: str | None = None
    max_retries: int = DEFAULT_SINK_MAX_RETRIES
    storage_class: OssStorageClass = OssStorageClass.STANDARD
    server_side_encryption: Literal["AES256", "KMS"] | None = None
    kms_key_id: str | None = None
    checksum_algorithm: Literal["CRC64"] | None = None
    overwrite_mode: SinkOverwriteMode = SinkOverwriteMode.OVERWRITE
    preflight_mode: SinkPreflightMode = SinkPreflightMode.METADATA
    content_type: str = "application/x-ndjson"
    metadata: Mapping[str, str] | Sequence[tuple[str, str]] = ()
    tags: Mapping[str, str] | Sequence[tuple[str, str]] = ()
    connect_timeout_seconds: float = DEFAULT_SINK_CONNECT_TIMEOUT_SECONDS
    read_timeout_seconds: float = DEFAULT_SINK_READ_TIMEOUT_SECONDS
    multipart_threshold_bytes: int = DEFAULT_MULTIPART_THRESHOLD_BYTES
    multipart_part_size_bytes: int = DEFAULT_MULTIPART_PART_BYTES
    multipart_max_concurrency: int = DEFAULT_MULTIPART_MAX_CONCURRENCY
    checkpoint_dir: str | None = None
    object_worm_retain_until: datetime | None = None
    object_worm_mode: Literal["COMPLIANCE"] | None = None
    object_worm_legal_hold: Literal["ON", "OFF"] | None = None

    def __post_init__(self) -> None:
        """Validate OSS names, encryption pairing, and shared upload limits."""
        # @intent oss-config-validates-before-sdk
        # Local policy errors should be deterministic and must not require the
        # optional SDK or a network call.
        _validate_bucket_like_name(self.bucket, field_name="bucket")
        _validate_prefix(self.prefix)
        _validate_max_retries(self.max_retries)
        if not isinstance(self.region, str) or not self.region.strip():
            raise ConfigurationError("region must be a non-empty string.")
        if not isinstance(self.storage_class, OssStorageClass):
            raise ConfigurationError("storage_class must be an OssStorageClass member.")
        if self.server_side_encryption == "KMS" and not self.kms_key_id:
            raise ConfigurationError("kms_key_id is required when server_side_encryption=KMS.")
        if self.server_side_encryption is not None and self.server_side_encryption not in ("AES256", "KMS"):
            raise ConfigurationError("server_side_encryption must be AES256, KMS, or None.")
        if self.object_worm_retain_until is not None and self.object_worm_retain_until.tzinfo is None:
            raise ConfigurationError("object_worm_retain_until must be timezone-aware.")
        if self.object_worm_mode not in (None, "COMPLIANCE") or self.object_worm_legal_hold not in (None, "ON", "OFF"):
            raise ConfigurationError("OSS WORM mode must be COMPLIANCE and legal hold must be ON, OFF, or None.")
        if not isinstance(self.overwrite_mode, SinkOverwriteMode) or not isinstance(self.preflight_mode, SinkPreflightMode):
            raise ConfigurationError("overwrite_mode and preflight_mode must use their enum types.")
        metadata, tags = _validate_common_options(
            content_type=self.content_type,
            metadata=self.metadata,
            tags=self.tags,
            connect_timeout_seconds=self.connect_timeout_seconds,
            read_timeout_seconds=self.read_timeout_seconds,
            multipart_threshold_bytes=self.multipart_threshold_bytes,
            multipart_part_size_bytes=self.multipart_part_size_bytes,
            multipart_max_concurrency=self.multipart_max_concurrency,
        )
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(self, "tags", tags)


@dataclass(frozen=True, slots=True)
class OssCredentials:
    """Alibaba OSS credentials with optional static or STS secrets."""

    auth_mode: OssAuthMode = OssAuthMode.DEFAULT
    access_key_id: str | None = None
    access_key_secret: Secret | None = None
    security_token: Secret | None = None
    role_arn: str | None = None
    role_session_name: str | None = None

    def __post_init__(self) -> None:
        """Require complete explicit credential pairs for static auth."""
        # @intent credential-pairing-is-local
        # Reject partial key material before the optional OSS SDK can inspect
        # or use it, preserving the default-chain signal when both are absent.
        if not isinstance(self.auth_mode, OssAuthMode):
            raise ConfigurationError("auth_mode must be an OssAuthMode member.")
        has_id = self.access_key_id is not None
        has_secret = self.access_key_secret is not None
        if has_id != has_secret:
            raise ConfigurationError("access_key_id and access_key_secret must both be set or both omitted.")
        if self.auth_mode is OssAuthMode.STATIC and not has_id:
            raise ConfigurationError("STATIC auth requires access_key_id and access_key_secret.")
        if self.auth_mode is OssAuthMode.STS and (not has_id or self.security_token is None):
            raise ConfigurationError("STS auth requires access_key_id, access_key_secret, and security_token.")
        if self.role_arn is not None and (self.auth_mode is not OssAuthMode.STS or self.security_token is None):
            raise ConfigurationError("role_arn identifies an externally assumed STS session and requires OssAuthMode.STS with security_token.")


__all__ = [
    "AzureBlobCredentials",
    "AzureBlobSinkConfig",
    "AzureBlobTier",
    "GcsCredentials",
    "GcsChecksumAlgorithm",
    "GcsSinkConfig",
    "GcsStorageClass",
    "OciAuthMode",
    "OciCredentials",
    "OciSinkConfig",
    "OciStorageTier",
    "OssAuthMode",
    "OssCredentials",
    "OssSinkConfig",
    "OssStorageClass",
    "S3Credentials",
    "S3ChecksumAlgorithm",
    "S3CompatibleCapabilities",
    "S3CompatibleProfiles",
    "S3CompatibleProvider",
    "S3SinkConfig",
    "S3StorageClass",
    "Secret",
    "SinkOverwriteMode",
    "SinkPreflightMode",
]
