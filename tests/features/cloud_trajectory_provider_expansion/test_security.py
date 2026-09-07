"""FILE: tests/features/cloud_trajectory_provider_expansion/test_security.py

PURPOSE:
    Verify secret masking, immutable config boundaries, safe prefixes, and
    object-lock time validation for the expanded providers.

ROLE IN CODEBASE:
    Security/policy layer of the cloud trajectory provider feature pack.

ARCHITECTURE NOTE:
    Tests inspect only safe repr/config surfaces and local validation; secrets
    are never sent to a real or simulated network endpoint.

COMMON MODIFICATION PATTERNS:
    Add a negative assertion whenever a new credential or policy field is
    introduced, especially if the field can reach a provider request.

KNOWN EDGE CASES:
    Dataclass-generated repr must remain masked and retention timestamps must
    be timezone-aware before they reach an object-lock API.

RELATED DOCS:
    docs/design/cloud-trajectory-provider-expansion.md

TESTS:
    Run with scripts/test-cloud-trajectory-provider-expansion.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from vidbyte.harnesses import OciCredentials, OssCredentials, S3Credentials, Secret
from vidbyte.lib.dataclasses.cloud_sinks import OssSinkConfig, S3SinkConfig
from vidbyte.lib.errors import ConfigurationError


def test_all_new_credential_repr_paths_mask_secrets() -> None:
    private_key = "-----BEGIN PRIVATE KEY-----secret-----END PRIVATE KEY-----"
    credentials = OciCredentials(private_key=Secret(private_key))
    oss = OssCredentials(access_key_id="access-id", access_key_secret=Secret("access-secret"))
    s3 = S3Credentials(access_key_id="access-id", secret_access_key=Secret("access-secret"))
    rendered = repr((credentials, oss, s3))
    assert private_key not in rendered
    assert "access-secret" not in rendered


@pytest.mark.parametrize("config", (S3SinkConfig(bucket="acme-bucket", prefix="safe"), OssSinkConfig(bucket="oss-bucket", region="cn-hangzhou", prefix="safe")))
def test_configs_are_frozen_and_do_not_expose_mutable_metadata(config: object) -> None:
    with pytest.raises((AttributeError, TypeError)):
        config.prefix = "mutated"  # type: ignore[misc]
    assert isinstance(config.metadata, tuple)
    assert isinstance(config.tags, tuple)


def test_oss_worm_requires_timezone_aware_retention() -> None:
    with pytest.raises(ConfigurationError):
        OssSinkConfig(bucket="oss-bucket", region="cn-hangzhou", object_worm_retain_until=datetime(2030, 1, 1))
    valid = OssSinkConfig(bucket="oss-bucket", region="cn-hangzhou", object_worm_retain_until=datetime(2030, 1, 1, tzinfo=timezone.utc), object_worm_mode="COMPLIANCE", object_worm_legal_hold="ON")
    assert valid.object_worm_mode == "COMPLIANCE"
