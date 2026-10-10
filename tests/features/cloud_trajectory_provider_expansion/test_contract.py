"""FILE: tests/features/cloud_trajectory_provider_expansion/test_contract.py

PURPOSE:
    Verify public provider profiles, strict configuration contracts, key
    determinism, and credential-shape validation for the expansion.

ROLE IN CODEBASE:
    Executable contract layer for the cloud trajectory provider feature pack.

ARCHITECTURE NOTE:
    These tests stay local and dependency-free. They validate the lib-layer
    dataclasses and the public harness export shims without constructing SDKs.

COMMON MODIFICATION PATTERNS:
    Add a test when a provider capability or public config field changes; keep
    vendor network behavior in the adapter test layer.

KNOWN EDGE CASES:
    Provider-specific options must fail closed when a profile does not
    advertise support, and key prefixes must not contain traversal segments.

RELATED DOCS:
    docs/design/cloud-trajectory-provider-expansion.md

TESTS:
    Run with scripts/test-cloud-trajectory-provider-expansion.py.
"""

from __future__ import annotations

import pytest

from vidbyte.harnesses import (
    OciAuthMode,
    OciCredentials,
    OciSinkConfig,
    OciStorageTier,
    GcsSinkConfig,
    OssAuthMode,
    OssCredentials,
    OssSinkConfig,
    OssStorageClass,
    S3CompatibleProfiles,
    S3CompatibleProvider,
    S3SinkConfig,
    S3StorageClass,
    Secret,
    SinkOverwriteMode,
    SinkPreflightMode,
)
from vidbyte.harnesses.client import HarnessClient
from vidbyte.harnesses.stores._cloud_common import object_key
from vidbyte.lib.errors import ConfigurationError


class TestProviderProfiles:
    """Named S3-compatible providers expose explicit capability contracts."""

    @pytest.mark.parametrize("provider", tuple(S3CompatibleProvider))
    def test_every_profile_builds_a_valid_config(self, provider: S3CompatibleProvider) -> None:
        config = S3SinkConfig(bucket="acme-bucket", provider=provider, endpoint_url=None if provider is S3CompatibleProvider.AWS else "https://objects.example")
        capabilities = S3CompatibleProfiles.get(provider)
        assert config.storage_class in capabilities.supported_storage_classes

    def test_r2_uses_auto_region_and_rejects_unsupported_encryption_or_tags(self) -> None:
        assert S3CompatibleProfiles.get(S3CompatibleProvider.CLOUDFLARE_R2).default_region == "auto"
        with pytest.raises(ConfigurationError):
            S3SinkConfig(bucket="acme-bucket", provider=S3CompatibleProvider.CLOUDFLARE_R2, sse="aws:kms", kms_key_id="key")
        with pytest.raises(ConfigurationError):
            S3SinkConfig(bucket="acme-bucket", provider=S3CompatibleProvider.CLOUDFLARE_R2, sse="AES256")
        with pytest.raises(ConfigurationError):
            S3SinkConfig(bucket="acme-bucket", provider=S3CompatibleProvider.CLOUDFLARE_R2, tags={"team": "eval"})

    def test_b2_rejects_object_tags_because_the_profile_does_not_advertise_them(self) -> None:
        with pytest.raises(ConfigurationError):
            S3SinkConfig(bucket="acme-bucket", provider=S3CompatibleProvider.BACKBLAZE_B2, tags={"team": "eval"})

    def test_gcs_rejects_s3_style_object_tags_and_preserves_metadata_semantics(self) -> None:
        with pytest.raises(ConfigurationError, match="metadata"):
            GcsSinkConfig(bucket="acme-bucket", tags={"team": "eval"})


class TestStrictCloudConfig:
    """Shared object options are immutable, deterministic, and validated locally."""

    def test_metadata_and_tags_are_normalized_for_stable_requests(self) -> None:
        config = S3SinkConfig(bucket="acme-bucket", metadata={"z": "last", "a": "first"}, tags={"env": "test"}, overwrite_mode=SinkOverwriteMode.CREATE_ONLY, preflight_mode=SinkPreflightMode.WRITE_PROBE)
        assert config.metadata == (("a", "first"), ("z", "last"))
        assert config.tags == (("env", "test"),)

    @pytest.mark.parametrize("prefix", ("/absolute", "../escape", "nested/../escape"))
    def test_prefix_cannot_escape_the_object_namespace(self, prefix: str) -> None:
        with pytest.raises(ConfigurationError):
            S3SinkConfig(bucket="acme-bucket", prefix=prefix)

    def test_canonical_key_is_deterministic(self) -> None:
        assert object_key("exports/", "run-123") == "exports/run-123.jsonl"
        assert object_key("", "run-123") == "run-123.jsonl"

    def test_oci_config_carries_tier_and_checksum_features(self) -> None:
        config = OciSinkConfig(bucket="oci-bucket", namespace="namespace", storage_tier=OciStorageTier.ARCHIVE, checksum_algorithm="SHA256", vault_kms_key_id="ocid1.key")
        assert config.storage_tier is OciStorageTier.ARCHIVE
        assert config.checksum_algorithm == "SHA256"

    def test_oss_config_carries_resumable_upload_settings(self) -> None:
        config = OssSinkConfig(bucket="oss-bucket", region="cn-hangzhou", storage_class=OssStorageClass.COLD_ARCHIVE, checkpoint_dir="private-checkpoints")
        assert config.storage_class is OssStorageClass.COLD_ARCHIVE
        assert config.checkpoint_dir == "private-checkpoints"


class TestCredentialShapes:
    def test_oci_api_key_shape_requires_its_signing_material(self) -> None:
        with pytest.raises(ConfigurationError):
            OciCredentials(auth_mode=OciAuthMode.API_KEY, tenancy="tenancy", user="user", fingerprint="fingerprint")

    def test_oss_sts_shape_requires_a_session_token(self) -> None:
        with pytest.raises(ConfigurationError):
            OssCredentials(auth_mode=OssAuthMode.STS, access_key_id="id", access_key_secret=Secret("secret"))


def test_named_factories_are_part_of_the_harness_client_contract() -> None:
    expected = ("r2_sink", "b2_sink", "spaces_sink", "ibm_cos_sink", "wasabi_sink", "minio_sink", "oci_sink", "oss_sink")
    assert all(hasattr(HarnessClient, name) for name in expected)
