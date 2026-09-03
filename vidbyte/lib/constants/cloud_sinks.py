"""FILE: vidbyte/lib/constants/cloud_sinks.py

PURPOSE:
    Owns the numeric bounds every cloud TrajectorySink's Config dataclass and the
    shared encoding guard reference. This module stores stable configuration
    values only; it does not validate input or perform I/O.

ROLE IN CODEBASE:
    `vidbyte/lib/dataclasses/cloud_sinks.py` imports the bucket-name-length bounds
    and the default retry count into each Config dataclass's `__post_init__`.
    `vidbyte/harnesses/stores/_sink_support.py` imports the record-size guard.

ARCHITECTURE NOTE:
    Centralizing these values under `vidbyte.lib` keeps the bound discoverable
    and widenable in one place instead of hidden as a private literal inside a
    dataclass, matching how `vidbyte/lib/constants/cot_events.py` centralizes
    the deep chain-of-thought tool bounds.

PUBLIC API INVENTORY:
    This module exports constants only; it defines no public functions and
    raises no runtime errors.

COMMON MODIFICATION PATTERNS:
    Change a shared bound here, then inspect every Config `__post_init__` and
    the `_sink_support.py` guard that consumes it.

WHAT NOT TO DO IN THIS FILE:
    1. Do not add validation logic; that belongs to the consuming dataclasses.
    2. Do not add vendor-specific bounds that only one provider needs (e.g. an
       S3-only multipart threshold) — this file is for bounds shared across
       every cloud sink.

KNOWN EDGE CASES:
    MAX_TRAJECTORY_RECORD_BYTES is a shared guard, not a per-vendor ceiling —
    it stays well below any single provider's real single-PUT limit on
    purpose, so raising it requires confirming every consuming sink's provider
    can still hold the new size in one PUT before doing so.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/cloud-trajectory-sinks.md

TESTS:
    tests/test_cloud_trajectory_sinks.py exercises every consumer of these
    bounds; this module itself defines no logic to test directly.
"""

from __future__ import annotations

# 100 MiB single-PUT guard. S3's hard single-PUT ceiling is 5 GiB, but a
# redacted JSONL TrajectoryRecord is normally KB to low-single-digit-MB, so
# this stays conservative rather than chasing each vendor's real limit.
MAX_TRAJECTORY_RECORD_BYTES: int = 100 * 1024 * 1024

MIN_BUCKET_NAME_LENGTH: int = 3
MAX_BUCKET_NAME_LENGTH: int = 63

DEFAULT_SINK_MAX_RETRIES: int = 3
MIN_PROVIDER_ATTEMPTS: int = 1
DEFAULT_SINK_CONNECT_TIMEOUT_SECONDS: float = 10.0
DEFAULT_SINK_READ_TIMEOUT_SECONDS: float = 60.0
GCS_CREATE_ONLY_GENERATION: int = 0

MIN_SINK_TIMEOUT_SECONDS: float = 0.1
MAX_SINK_TIMEOUT_SECONDS: float = 900.0
MIN_MULTIPART_PART_BYTES: int = 5 * 1024 * 1024
MAX_MULTIPART_PART_BYTES: int = 5 * 1024 * 1024 * 1024
MIN_SINGLE_PUT_BYTES: int = 1
DEFAULT_MULTIPART_THRESHOLD_BYTES: int = 100 * 1024 * 1024
DEFAULT_MULTIPART_PART_BYTES: int = 8 * 1024 * 1024
DEFAULT_MULTIPART_MAX_CONCURRENCY: int = 4
MAX_MULTIPART_CONCURRENCY: int = 32

__all__ = [
    "DEFAULT_SINK_MAX_RETRIES",
    "DEFAULT_SINK_CONNECT_TIMEOUT_SECONDS",
    "DEFAULT_SINK_READ_TIMEOUT_SECONDS",
    "DEFAULT_MULTIPART_MAX_CONCURRENCY",
    "DEFAULT_MULTIPART_PART_BYTES",
    "DEFAULT_MULTIPART_THRESHOLD_BYTES",
    "MAX_BUCKET_NAME_LENGTH",
    "MAX_MULTIPART_CONCURRENCY",
    "MAX_MULTIPART_PART_BYTES",
    "MAX_SINK_TIMEOUT_SECONDS",
    "MAX_TRAJECTORY_RECORD_BYTES",
    "GCS_CREATE_ONLY_GENERATION",
    "MIN_BUCKET_NAME_LENGTH",
    "MIN_MULTIPART_PART_BYTES",
    "MIN_SINGLE_PUT_BYTES",
    "MIN_SINK_TIMEOUT_SECONDS",
    "MIN_PROVIDER_ATTEMPTS",
]
