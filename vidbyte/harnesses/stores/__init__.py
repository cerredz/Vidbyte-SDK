"""FILE: vidbyte/harnesses/stores/__init__.py

PURPOSE:
    Exposes the TrajectorySink port and its reference backends from one
    namespace: two local, dependency-free ones and three cloud ones requiring
    a lazily-imported vendor SDK. Also re-exports each cloud sink's
    Config/Credentials/enum construction types from vidbyte.lib.dataclasses
    .cloud_sinks so a caller importing a sink from here gets everything needed
    to construct one from a single import line. Mirrors
    vidbyte/sessions/stores/__init__.py.

ROLE IN CODEBASE:
    Import site for the harness trajectory export target(s). A sink is the LICENSED,
    redacted export surface, kept deliberately distinct from the operational
    vidbyte.sessions SessionStore.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/cloud-trajectory-sinks.md
"""

from __future__ import annotations

from vidbyte.harnesses.stores.azure_blob import AzureBlobTrajectorySink
from vidbyte.harnesses.stores.base import TrajectorySink
from vidbyte.harnesses.stores.file import FileTrajectorySink
from vidbyte.harnesses.stores.gcs import GcsTrajectorySink
from vidbyte.harnesses.stores.memory import InMemoryTrajectorySink
from vidbyte.harnesses.stores.s3 import S3TrajectorySink
from vidbyte.lib.dataclasses.cloud_sinks import (
    AzureBlobCredentials,
    AzureBlobSinkConfig,
    AzureBlobTier,
    GcsCredentials,
    GcsSinkConfig,
    GcsStorageClass,
    S3Credentials,
    S3SinkConfig,
    S3StorageClass,
    Secret,
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
    "S3Credentials",
    "S3SinkConfig",
    "S3StorageClass",
    "S3TrajectorySink",
    "Secret",
    "TrajectorySink",
]
