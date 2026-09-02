"""Validated configuration and credentials for cloud trajectory sinks."""

from __future__ import annotations

import base64
import hashlib
import re
import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal

from vidbyte.lib.constants.cloud_sinks import (
    DEFAULT_SINK_MAX_RETRIES,
    MAX_BUCKET_NAME_LENGTH,
    MIN_BUCKET_NAME_LENGTH,
)
from vidbyte.lib.errors import ConfigurationError

_NAME_PATTERN = re.compile(r"^[a-z0-9.-]+$")


class CloudSinkConfigValidation:
    """Class-bound validation helpers shared by the immutable config shapes."""

    @staticmethod
    def bucket_like_name(value: str, *, field_name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"{field_name} must be a non-empty string.", details={"field": field_name})
        if not MIN_BUCKET_NAME_LENGTH <= len(value) <= MAX_BUCKET_NAME_LENGTH:
            raise ConfigurationError(
                f"{field_name} must be between {MIN_BUCKET_NAME_LENGTH} and {MAX_BUCKET_NAME_LENGTH} characters.",
                details={"field": field_name, "actual_length": len(value)},
            )
        if not _NAME_PATTERN.match(value):
            raise ConfigurationError(
                f"{field_name} contains characters outside the conservative [a-z0-9.-] set.",
                details={"field": field_name, "value": value},
            )

    @staticmethod
    def max_retries(value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigurationError("max_retries must be an integer.", details={"actual_type": type(value).__name__})
        if value < 0:
            raise ConfigurationError("max_retries must be non-negative.", details={"actual_value": value})

    @staticmethod
    def optional_text(value: str | None, *, field_name: str) -> None:
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ConfigurationError(f"{field_name} must be a non-empty string when provided.", details={"field": field_name})

    @staticmethod
    def string_mapping(
        value: Mapping[str, str],
        *,
        field_name: str,
        max_items: int,
        max_key_length: int = 128,
        max_value_length: int = 8192,
    ) -> dict[str, str]:
        if not isinstance(value, Mapping):
            raise ConfigurationError(f"{field_name} must be a string-to-string mapping.", details={"field": field_name})
        if len(value) > max_items:
            raise ConfigurationError(
                f"{field_name} cannot contain more than {max_items} entries.",
                details={"field": field_name, "actual_count": len(value)},
            )
        normalized: dict[str, str] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > max_key_length:
                raise ConfigurationError(
                    f"{field_name} keys must be non-empty strings of at most {max_key_length} characters.",
                    details={"field": field_name},
                )
            if not isinstance(item, str) or len(item) > max_value_length:
                raise ConfigurationError(
                    f"{field_name} values must be strings of at most {max_value_length} characters.",
                    details={"field": field_name, "key": key},
                )
            normalized[key] = item
        return normalized

    @staticmethod
    def aware_datetime(value: datetime | None, *, field_name: str) -> None:
        if value is not None and (not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None):
            raise ConfigurationError(f"{field_name} must be a timezone-aware datetime when provided.", details={"field": field_name})

    @staticmethod
    def raw_aes256(value: "Secret | None", *, field_name: str) -> None:
        if value is None:
            return
        raw = value.reveal()
        raw_bytes = raw if isinstance(raw, bytes) else raw.encode("utf-8")
        if len(raw_bytes) != 32:
            raise ConfigurationError(
                f"{field_name} must contain exactly 32 bytes for AES-256.",
                details={"field": field_name, "byte_length": len(raw_bytes)},
            )

    @staticmethod
    def base64_aes256(value: "Secret | None", *, field_name: str) -> None:
        if value is None:
            return
        raw = value.reveal()
        if not isinstance(raw, str):
            raise ConfigurationError(f"{field_name} must be a base64 string.", details={"field": field_name})
        try:
            decoded = base64.b64decode(raw, validate=True)
        except (ValueError, TypeError) as exc:
            raise ConfigurationError(f"{field_name} must be valid base64.", details={"field": field_name}) from exc
        if len(decoded) != 32:
            raise ConfigurationError(
                f"{field_name} must decode to exactly 32 bytes for AES-256.",
                details={"field": field_name, "byte_length": len(decoded)},
            )

    @staticmethod
    def strict_bool(value: bool | None, *, field_name: str) -> None:
        if value is not None and not isinstance(value, bool):
            raise ConfigurationError(f"{field_name} must be a boolean when provided.", details={"field": field_name})

    @staticmethod
    def non_negative_int(value: int | None, *, field_name: str) -> None:
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise ConfigurationError(f"{field_name} must be a non-negative integer when provided.", details={"field": field_name})


class S3StorageClass(str, Enum):
    """S3 storage classes accepted by PutObject."""

    STANDARD = "STANDARD"
    STANDARD_IA = "STANDARD_IA"
    INTELLIGENT_TIERING = "INTELLIGENT_TIERING"
    GLACIER_IR = "GLACIER_IR"
    GLACIER = "GLACIER"
    DEEP_ARCHIVE = "DEEP_ARCHIVE"
    ONEZONE_IA = "ONEZONE_IA"
    OUTPOSTS = "OUTPOSTS"
    EXPRESS_ONEZONE = "EXPRESS_ONEZONE"


class GcsStorageClass(str, Enum):
    """Google Cloud Storage classes accepted by this sink."""

    STANDARD = "STANDARD"
    NEARLINE = "NEARLINE"
    COLDLINE = "COLDLINE"
    ARCHIVE = "ARCHIVE"


class AzureBlobTier(str, Enum):
    """Azure Blob access tiers accepted by this sink."""

    HOT = "Hot"
    COOL = "Cool"
    COLD = "Cold"
    ARCHIVE = "Archive"


@dataclass(frozen=True, slots=True)
class Secret:
    """A string or byte secret whose repr/str never reveals its value."""

    value: str | bytes

    def __post_init__(self) -> None:
        if not isinstance(self.value, (str, bytes)) or not self.value:
            raise ConfigurationError("Secret value must be a non-empty string or bytes value.")

    def __repr__(self) -> str:
        return "Secret(<redacted>)"

    def __str__(self) -> str:
        return "Secret(<redacted>)"

    def reveal(self) -> str | bytes:
        return self.value


@dataclass(frozen=True, slots=True)
class S3SinkConfig:
    """S3 object controls; credentials and SSE-C key material live separately."""

    bucket: str
    prefix: str = ""
    region: str | None = None
    endpoint_url: str | None = None
    storage_class: S3StorageClass = S3StorageClass.STANDARD
    sse: Literal["AES256", "aws:kms", "aws:kms:dsse"] | None = None
    kms_key_id: str | None = None
    role_arn: str | None = None
    external_id: str | None = None
    max_retries: int = DEFAULT_SINK_MAX_RETRIES
    metadata: Mapping[str, str] = field(default_factory=dict)
    tags: Mapping[str, str] = field(default_factory=dict)
    content_type: str | None = None
    content_encoding: Literal["gzip"] | None = None
    cache_control: str | None = None
    content_disposition: str | None = None
    sse_customer_algorithm: Literal["AES256"] | None = None
    bucket_key_enabled: bool | None = None
    kms_encryption_context: Mapping[str, str] = field(default_factory=dict)
    object_lock_mode: Literal["GOVERNANCE", "COMPLIANCE"] | None = None
    object_lock_retain_until_date: datetime | None = None
    object_lock_legal_hold_status: Literal["ON", "OFF"] | None = None
    if_match: str | None = None
    if_none_match: str | None = None
    acl: Literal["private", "bucket-owner-full-control"] | None = None
    grant_read: str | None = None
    grant_read_acp: str | None = None
    grant_write_acp: str | None = None
    checksum_algorithm: Literal["CRC32", "CRC32C", "SHA1", "SHA256", "CRC64NVME"] | None = None
    content_md5: str | None = None
    request_payer: Literal["requester"] | None = None
    use_accelerate_endpoint: bool = False
    use_dualstack_endpoint: bool = False
    expires: datetime | None = None
    website_redirect_location: str | None = None

    # @intent validate-s3-object-contract
    # Validate local provider constraints before a sink can make a network call or construct request headers.
    def __post_init__(self) -> None:
        CloudSinkConfigValidation.bucket_like_name(self.bucket, field_name="bucket")
        if not isinstance(self.storage_class, S3StorageClass):
            raise ConfigurationError("storage_class must be an S3StorageClass member.")
        self._validate_encryption()
        self._normalize_mappings()
        self._validate_headers()
        self._validate_policies()
        self._validate_transport()
        CloudSinkConfigValidation.optional_text(self.kms_key_id, field_name="kms_key_id")
        CloudSinkConfigValidation.optional_text(self.role_arn, field_name="role_arn")
        CloudSinkConfigValidation.optional_text(self.external_id, field_name="external_id")
        if self.external_id is not None and self.role_arn is None:
            warnings.warn("S3SinkConfig.external_id has no effect without role_arn set.", stacklevel=2)
        CloudSinkConfigValidation.max_retries(self.max_retries)

    def _validate_encryption(self) -> None:
        if self.sse not in (None, "AES256", "aws:kms", "aws:kms:dsse"):
            raise ConfigurationError('sse must be "AES256", "aws:kms", "aws:kms:dsse", or None.')
        if self.sse == "aws:kms" and self.kms_key_id is None:
            raise ConfigurationError('kms_key_id is required when sse="aws:kms".')
        if self.sse_customer_algorithm not in (None, "AES256"):
            raise ConfigurationError('sse_customer_algorithm must be "AES256" or None.')
        if self.sse_customer_algorithm is not None and self.sse is not None:
            raise ConfigurationError("sse and sse_customer_algorithm are mutually exclusive.")
        if self.bucket_key_enabled is not None and self.sse != "aws:kms":
            raise ConfigurationError("bucket_key_enabled requires sse=aws:kms.")
        if self.kms_encryption_context and self.sse != "aws:kms":
            raise ConfigurationError("kms_encryption_context requires sse=aws:kms.")

    def _normalize_mappings(self) -> None:
        object.__setattr__(self, "metadata", CloudSinkConfigValidation.string_mapping(self.metadata, field_name="metadata", max_items=100, max_value_length=2048))
        object.__setattr__(self, "tags", CloudSinkConfigValidation.string_mapping(self.tags, field_name="tags", max_items=10, max_value_length=256))
        object.__setattr__(self, "kms_encryption_context", CloudSinkConfigValidation.string_mapping(self.kms_encryption_context, field_name="kms_encryption_context", max_items=20, max_value_length=2048))

    # @intent validate-s3-request-headers
    # Reject malformed content, ACL, checksum, and conditional headers before the provider boundary.
    def _validate_headers(self) -> None:
        for value, name in ((self.content_type, "content_type"), (self.content_encoding, "content_encoding"), (self.cache_control, "cache_control"), (self.content_disposition, "content_disposition"), (self.if_match, "if_match"), (self.if_none_match, "if_none_match"), (self.acl, "acl"), (self.grant_read, "grant_read"), (self.grant_read_acp, "grant_read_acp"), (self.grant_write_acp, "grant_write_acp"), (self.content_md5, "content_md5"), (self.request_payer, "request_payer"), (self.website_redirect_location, "website_redirect_location")):
            CloudSinkConfigValidation.optional_text(value, field_name=name)
        if self.content_encoding not in (None, "gzip"):
            raise ConfigurationError('content_encoding currently supports only "gzip".')
        if self.acl not in (None, "private", "bucket-owner-full-control"):
            raise ConfigurationError('acl must be "private", "bucket-owner-full-control", or None.')
        if self.request_payer not in (None, "requester"):
            raise ConfigurationError('request_payer must be "requester" or None.')
        if self.content_md5 is not None:
            try:
                decoded_md5 = base64.b64decode(self.content_md5, validate=True)
            except (ValueError, TypeError) as exc:
                raise ConfigurationError("content_md5 must be valid base64.") from exc
            if len(decoded_md5) != 16:
                raise ConfigurationError("content_md5 must decode to 16 bytes.")

    def _validate_policies(self) -> None:
        if self.if_match is not None and self.if_none_match is not None:
            raise ConfigurationError("if_match and if_none_match are mutually exclusive.")
        if self.object_lock_mode not in (None, "GOVERNANCE", "COMPLIANCE"):
            raise ConfigurationError("object_lock_mode must be GOVERNANCE, COMPLIANCE, or None.")
        if (self.object_lock_mode is None) != (self.object_lock_retain_until_date is None):
            raise ConfigurationError("object_lock_mode and object_lock_retain_until_date must be supplied together.")
        if self.object_lock_legal_hold_status not in (None, "ON", "OFF"):
            raise ConfigurationError("object_lock_legal_hold_status must be ON, OFF, or None.")
        CloudSinkConfigValidation.aware_datetime(self.object_lock_retain_until_date, field_name="object_lock_retain_until_date")
        CloudSinkConfigValidation.aware_datetime(self.expires, field_name="expires")

    def _validate_transport(self) -> None:
        CloudSinkConfigValidation.strict_bool(self.bucket_key_enabled, field_name="bucket_key_enabled")
        CloudSinkConfigValidation.strict_bool(self.use_accelerate_endpoint, field_name="use_accelerate_endpoint")
        CloudSinkConfigValidation.strict_bool(self.use_dualstack_endpoint, field_name="use_dualstack_endpoint")
        if self.use_accelerate_endpoint and self.endpoint_url is not None:
            raise ConfigurationError("use_accelerate_endpoint cannot be combined with endpoint_url.")


@dataclass(frozen=True, slots=True)
class S3Credentials:
    """Static AWS credentials and optional per-request SSE-C material."""

    access_key_id: str | None = None
    secret_access_key: Secret | None = None
    session_token: Secret | None = None
    sse_customer_key: Secret | None = None
    sse_customer_key_md5: str | None = None

    # @intent validate-s3-secret-contract
    # Keep customer-provided key material length- and digest-safe without including key bytes in diagnostics.
    def __post_init__(self) -> None:
        if (self.access_key_id is None) != (self.secret_access_key is None):
            raise ConfigurationError("access_key_id and secret_access_key must both be set, or both left None to use the default credential chain.")
        CloudSinkConfigValidation.optional_text(self.access_key_id, field_name="access_key_id")
        CloudSinkConfigValidation.raw_aes256(self.sse_customer_key, field_name="sse_customer_key")
        CloudSinkConfigValidation.optional_text(self.sse_customer_key_md5, field_name="sse_customer_key_md5")
        if self.sse_customer_key_md5 is not None:
            try:
                decoded = base64.b64decode(self.sse_customer_key_md5, validate=True)
            except (ValueError, TypeError) as exc:
                raise ConfigurationError("sse_customer_key_md5 must be valid base64.") from exc
            if len(decoded) != 16:
                raise ConfigurationError("sse_customer_key_md5 must decode to 16 bytes.")
        if self.sse_customer_key is None and self.sse_customer_key_md5 is not None:
            raise ConfigurationError("sse_customer_key_md5 requires sse_customer_key.")
        if self.sse_customer_key is not None and self.sse_customer_key_md5 is not None:
            raw = self.sse_customer_key.reveal()
            raw_bytes = raw if isinstance(raw, bytes) else raw.encode("utf-8")
            expected = base64.b64encode(hashlib.md5(raw_bytes, usedforsecurity=False).digest()).decode("ascii")
            if expected != self.sse_customer_key_md5:
                raise ConfigurationError("sse_customer_key_md5 does not match sse_customer_key.")


@dataclass(frozen=True, slots=True)
class GcsSinkConfig:
    """GCS object controls plus optional bucket retention and requester project."""

    bucket: str
    prefix: str = ""
    storage_class: GcsStorageClass = GcsStorageClass.STANDARD
    kms_key_name: str | None = None
    max_retries: int = DEFAULT_SINK_MAX_RETRIES
    metadata: Mapping[str, str] = field(default_factory=dict)
    content_type: str | None = "application/x-ndjson"
    content_encoding: Literal["gzip"] | None = None
    cache_control: str | None = None
    content_disposition: str | None = None
    if_generation_match: int | None = None
    if_generation_not_match: int | None = None
    if_metageneration_match: int | None = None
    if_metageneration_not_match: int | None = None
    predefined_acl: str | None = None
    checksum: Literal["auto", "md5", "crc32c"] | None = None
    retention_mode: Literal["Unlocked", "Locked"] | None = None
    retain_until_time: datetime | None = None
    event_based_hold: bool | None = None
    temporary_hold: bool | None = None
    bucket_retention_period: int | None = None
    user_project: str | None = None

    def __post_init__(self) -> None:
        CloudSinkConfigValidation.bucket_like_name(self.bucket, field_name="bucket")
        if not isinstance(self.storage_class, GcsStorageClass):
            raise ConfigurationError("storage_class must be a GcsStorageClass member.")
        object.__setattr__(self, "metadata", CloudSinkConfigValidation.string_mapping(self.metadata, field_name="metadata", max_items=100, max_value_length=8192))
        for text_value, name in ((self.content_type, "content_type"), (self.content_encoding, "content_encoding"), (self.cache_control, "cache_control"), (self.content_disposition, "content_disposition"), (self.predefined_acl, "predefined_acl"), (self.user_project, "user_project"), (self.kms_key_name, "kms_key_name")):
            CloudSinkConfigValidation.optional_text(text_value, field_name=name)
        if self.content_encoding not in (None, "gzip"):
            raise ConfigurationError('content_encoding currently supports only "gzip".')
        for int_value, name in ((self.if_generation_match, "if_generation_match"), (self.if_generation_not_match, "if_generation_not_match"), (self.if_metageneration_match, "if_metageneration_match"), (self.if_metageneration_not_match, "if_metageneration_not_match"), (self.bucket_retention_period, "bucket_retention_period")):
            CloudSinkConfigValidation.non_negative_int(int_value, field_name=name)
        if self.if_generation_match is not None and self.if_generation_not_match is not None:
            raise ConfigurationError("if_generation_match and if_generation_not_match are mutually exclusive.")
        if self.if_metageneration_match is not None and self.if_metageneration_not_match is not None:
            raise ConfigurationError("if_metageneration_match and if_metageneration_not_match are mutually exclusive.")
        if self.retention_mode not in (None, "Unlocked", "Locked"):
            raise ConfigurationError("retention_mode must be Unlocked, Locked, or None.")
        if (self.retention_mode is None) != (self.retain_until_time is None):
            raise ConfigurationError("retention_mode and retain_until_time must be supplied together.")
        CloudSinkConfigValidation.aware_datetime(self.retain_until_time, field_name="retain_until_time")
        CloudSinkConfigValidation.strict_bool(self.event_based_hold, field_name="event_based_hold")
        CloudSinkConfigValidation.strict_bool(self.temporary_hold, field_name="temporary_hold")
        if self.checksum not in (None, "auto", "md5", "crc32c"):
            raise ConfigurationError("checksum must be auto, md5, crc32c, or None.")


@dataclass(frozen=True, slots=True)
class GcsCredentials:
    """Optional service-account file and per-request customer-supplied key."""

    service_account_json_path: str | None = None
    customer_supplied_encryption_key: Secret | None = None

    def __post_init__(self) -> None:
        if self.service_account_json_path is not None and not self.service_account_json_path.strip():
            raise ConfigurationError("service_account_json_path must not be an empty string.")
        CloudSinkConfigValidation.raw_aes256(self.customer_supplied_encryption_key, field_name="customer_supplied_encryption_key")


@dataclass(frozen=True, slots=True)
class AzureBlobSinkConfig:
    """Azure Blob object controls, conditions, and immutability settings."""

    container: str
    prefix: str = ""
    tier: AzureBlobTier = AzureBlobTier.HOT
    max_retries: int = DEFAULT_SINK_MAX_RETRIES
    metadata: Mapping[str, str] = field(default_factory=dict)
    tags: Mapping[str, str] = field(default_factory=dict)
    content_type: str | None = "application/x-ndjson"
    content_encoding: Literal["gzip"] | None = None
    cache_control: str | None = None
    content_disposition: str | None = None
    content_md5: bytes | None = None
    validate_content: bool = False
    if_match: str | None = None
    if_none_match: bool = False
    if_tags_match_condition: str | None = None
    immutability_policy_expiry_time: datetime | None = None
    immutability_policy_mode: Literal["Unlocked", "Locked"] | None = None
    legal_hold: bool | None = None
    encryption_scope: str | None = None

    def __post_init__(self) -> None:
        CloudSinkConfigValidation.bucket_like_name(self.container, field_name="container")
        if not isinstance(self.tier, AzureBlobTier):
            raise ConfigurationError("tier must be an AzureBlobTier member.")
        object.__setattr__(self, "metadata", CloudSinkConfigValidation.string_mapping(self.metadata, field_name="metadata", max_items=100, max_value_length=8192))
        object.__setattr__(self, "tags", CloudSinkConfigValidation.string_mapping(self.tags, field_name="tags", max_items=10, max_key_length=128, max_value_length=256))
        for value, name in ((self.content_type, "content_type"), (self.content_encoding, "content_encoding"), (self.cache_control, "cache_control"), (self.content_disposition, "content_disposition"), (self.if_match, "if_match"), (self.if_tags_match_condition, "if_tags_match_condition"), (self.encryption_scope, "encryption_scope")):
            CloudSinkConfigValidation.optional_text(value, field_name=name)
        if self.content_encoding not in (None, "gzip"):
            raise ConfigurationError('content_encoding currently supports only "gzip".')
        if self.content_md5 is not None and (not isinstance(self.content_md5, bytes) or len(self.content_md5) != 16):
            raise ConfigurationError("content_md5 must be a 16-byte MD5 digest when provided.")
        CloudSinkConfigValidation.strict_bool(self.validate_content, field_name="validate_content")
        CloudSinkConfigValidation.strict_bool(self.if_none_match, field_name="if_none_match")
        CloudSinkConfigValidation.strict_bool(self.legal_hold, field_name="legal_hold")
        if self.if_match is not None and self.if_none_match:
            raise ConfigurationError("if_match and if_none_match are mutually exclusive.")
        if self.immutability_policy_mode not in (None, "Unlocked", "Locked"):
            raise ConfigurationError("immutability_policy_mode must be Unlocked, Locked, or None.")
        if (self.immutability_policy_mode is None) != (self.immutability_policy_expiry_time is None):
            raise ConfigurationError("immutability_policy_mode and immutability_policy_expiry_time must be supplied together.")
        CloudSinkConfigValidation.aware_datetime(self.immutability_policy_expiry_time, field_name="immutability_policy_expiry_time")
        CloudSinkConfigValidation.max_retries(self.max_retries)


@dataclass(frozen=True, slots=True)
class AzureBlobCredentials:
    """Azure account address plus connection/SAS or customer-provided key material."""

    account_url: str
    connection_string: Secret | None = None
    sas_token: Secret | None = None
    customer_provided_key: Secret | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.account_url, str) or not self.account_url.strip():
            raise ConfigurationError("account_url must be a non-empty string.")
        if self.connection_string is not None and self.sas_token is not None:
            raise ConfigurationError("connection_string and sas_token are mutually exclusive.")
        if self.customer_provided_key is not None and not self.account_url.lower().startswith("https://"):
            raise ConfigurationError("customer_provided_key requires an HTTPS account_url.")
        CloudSinkConfigValidation.base64_aes256(self.customer_provided_key, field_name="customer_provided_key")


__all__ = [
    "AzureBlobCredentials",
    "AzureBlobSinkConfig",
    "AzureBlobTier",
    "CloudSinkConfigValidation",
    "GcsCredentials",
    "GcsSinkConfig",
    "GcsStorageClass",
    "S3Credentials",
    "S3SinkConfig",
    "S3StorageClass",
    "Secret",
]
