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

__all__ = [
    "DEFAULT_SINK_MAX_RETRIES",
    "MAX_BUCKET_NAME_LENGTH",
    "MAX_TRAJECTORY_RECORD_BYTES",
    "MIN_BUCKET_NAME_LENGTH",
]
