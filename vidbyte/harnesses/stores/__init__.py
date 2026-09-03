"""FILE: vidbyte/harnesses/stores/__init__.py

PURPOSE:
    Exposes the TrajectorySink port and its reference backends from one
    namespace: two local, dependency-free ones and cloud ones requiring
    a lazily-imported vendor SDK. Also re-exports each cloud sink's
    Config/Credentials/enum construction types from vidbyte.lib.dataclasses
    .cloud_sinks so a caller importing a sink from here gets everything needed
    to construct one from a single import line. Mirrors
    vidbyte/sessions/stores/__init__.py.

ROLE IN CODEBASE:
    Import site for the harness trajectory export target(s). A sink is the LICENSED,
    redacted export surface, kept deliberately distinct from the operational
    vidbyte.sessions SessionStore.

ARCHITECTURE NOTE:
    Export shims only; this module builds no backend at import time and calls
    no vendor SDK. Each cloud sink lazily imports its own driver inside its
    own constructor, not here.

COMMON MODIFICATION PATTERNS:
    Add a new backend's module under vidbyte/harnesses/stores/, then export
    its sink class (and any Config/Credentials/enum types it needs) here.

KNOWN EDGE CASES:
    Importing this module never requires boto3/google-cloud-storage/
    azure-storage-blob to be installed; only constructing a cloud sink does.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/cloud-trajectory-sinks.md

TESTS:
    tests/test_cloud_trajectory_sinks.py and
    tests/features/cloud_trajectory_provider_expansion/ exercise the cloud
    sinks re-exported here; the two local backends are exercised inline elsewhere.
"""

from __future__ import annotations

from vidbyte.harnesses.stores.azure_blob import AzureBlobTrajectorySink
from vidbyte.harnesses.stores.base import TrajectorySink
from vidbyte.harnesses.stores.file import FileTrajectorySink
from vidbyte.harnesses.stores.gcs import GcsTrajectorySink
from vidbyte.harnesses.stores.memory import InMemoryTrajectorySink
from vidbyte.harnesses.stores.oci import OciTrajectorySink
from vidbyte.harnesses.stores.oss import OssTrajectorySink
from vidbyte.harnesses.stores.s3 import S3TrajectorySink
from vidbyte.harnesses.stores._cloud_common import SinkWriteReceipt
from vidbyte.lib.dataclasses.cloud_sinks import (
    AzureBlobCredentials,
    AzureBlobSinkConfig,
    AzureBlobTier,
    GcsCredentials,
    GcsSinkConfig,
    GcsStorageClass,
    OciAuthMode,
    OciCredentials,
    OciSinkConfig,
    OciStorageTier,
    OssAuthMode,
    OssCredentials,
    OssSinkConfig,
    OssStorageClass,
    S3Credentials,
    S3ChecksumAlgorithm,
    S3CompatibleCapabilities,
    S3CompatibleProfiles,
    S3CompatibleProvider,
    S3SinkConfig,
    S3StorageClass,
    Secret,
    SinkOverwriteMode,
    SinkPreflightMode,
)

__all__ = [
    "AzureBlobCredentials",
    "AzureBlobSinkConfig",
    "AzureBlobTier",
    "AzureBlobTrajectorySink",
    "FileTrajectorySink",
    "GcsCredentials",
    "GcsSinkConfig",
    "GcsStorageClass",
    "GcsTrajectorySink",
    "InMemoryTrajectorySink",
    "OciAuthMode",
    "OciCredentials",
    "OciSinkConfig",
    "OciStorageTier",
    "OciTrajectorySink",
    "OssAuthMode",
    "OssCredentials",
    "OssSinkConfig",
    "OssStorageClass",
    "OssTrajectorySink",
    "S3Credentials",
    "S3ChecksumAlgorithm",
    "S3CompatibleCapabilities",
    "S3CompatibleProfiles",
    "S3CompatibleProvider",
    "S3SinkConfig",
    "S3StorageClass",
    "S3TrajectorySink",
    "Secret",
    "SinkOverwriteMode",
    "SinkPreflightMode",
    "SinkWriteReceipt",
    "TrajectorySink",
]
