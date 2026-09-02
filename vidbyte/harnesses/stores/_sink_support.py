"""FILE: vidbyte/harnesses/stores/_sink_support.py

PURPOSE:
    Shares the JSON encoding and size-guard logic every TrajectorySink backend
    needs — file, and all three cloud sinks — so the encoding rules live in
    exactly one place instead of four.

ROLE IN CODEBASE:
    FileTrajectorySink, S3TrajectorySink, GcsTrajectorySink, and
    AzureBlobTrajectorySink all call SinkEncoding.encode_record() then
    SinkEncoding.guard_size() before attempting any I/O.

ARCHITECTURE NOTE:
    A static helper class, not a bag of free functions, per this repo's
    Class-Bound Helpers convention. Internal-only: this module is not
    exported from vidbyte/harnesses/stores/__init__.py.

PUBLIC API INVENTORY:
    SinkEncoding.encode_record(record); SinkEncoding.guard_size(payload, run_id=...).

WHAT NOT TO DO IN THIS FILE:
    1. Do not perform any I/O; this module only encodes and measures bytes.
    2. Do not import any vendor SDK; every cloud sink imports this module
       before it lazily imports its own driver.
    3. Do not change the encoding flags (ensure_ascii/sort_keys/separators/
       allow_nan) without confirming every existing FileTrajectorySink
       consumer still parses the result identically.

COMMON MODIFICATION PATTERNS:
    Add a new sink-wide encoding or size rule here, then update every
    consumer (file.py, s3.py, gcs.py, azure_blob.py) rather than duplicating
    the change per backend.

KNOWN EDGE CASES:
    guard_size measures the already-encoded UTF-8 byte length, not the
    in-memory Python object size, so it correctly accounts for multi-byte
    character expansion rather than undercounting non-ASCII content.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/cloud-trajectory-sinks.md

TESTS:
    tests/test_cloud_trajectory_sinks.py.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict

from vidbyte.harnesses.contracts import TrajectoryRecord
from vidbyte.harnesses.errors import HarnessSinkPayloadError
from vidbyte.lib.constants.cloud_sinks import MAX_TRAJECTORY_RECORD_BYTES


class SinkEncoding:
    """Shared record encoding and size-guard logic for every TrajectorySink backend."""

    @staticmethod
    def encode_record(record: TrajectoryRecord) -> bytes:
        # Encodes one record as compact, sorted-key UTF-8 JSON bytes, matching FileTrajectorySink's existing wire format exactly.
        try:
            line = json.dumps(asdict(record), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise HarnessSinkPayloadError("Trajectory record could not be encoded as JSON.", details={"run_id": record.run_id, "error_type": type(exc).__name__}) from exc
        return line.encode("utf-8")

    @staticmethod
    def guard_size(payload: bytes, *, run_id: str) -> None:
        # Rejects an oversized payload before any caller attempts a network call.
        if len(payload) > MAX_TRAJECTORY_RECORD_BYTES:
            raise HarnessSinkPayloadError(
                "Trajectory record exceeds the sink's size guard; multipart upload is not implemented by this sink.",
                details={"run_id": run_id, "actual_bytes": len(payload), "max_bytes": MAX_TRAJECTORY_RECORD_BYTES},
            )

    @staticmethod
    def prepare_payload(record: TrajectoryRecord, *, content_encoding: str | None = None) -> bytes:
        """Encode, guard, and optionally gzip a record before any provider preflight."""
        payload = SinkEncoding.encode_record(record)
        SinkEncoding.guard_size(payload, run_id=record.run_id)
        if content_encoding == "gzip":
            payload = gzip.compress(payload, compresslevel=6, mtime=0)
            SinkEncoding.guard_size(payload, run_id=record.run_id)
        return payload


__all__ = ["SinkEncoding"]
