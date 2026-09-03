"""FILE: vidbyte/harnesses/stores/_cloud_common.py

PURPOSE:
    Owns the behavior shared by every cloud trajectory exporter: deterministic
    object keys, encode-before-network ordering, resettable preflight lifecycle,
    safe write receipts, and client cleanup. It is a private adapter seam, not a
    provider client and not a place for bucket policy management.

ROLE IN CODEBASE:
    `s3.py`, `gcs.py`, `azure_blob.py`, `oci.py`, and `oss.py` use the mixin and
    helpers here while retaining ownership of their vendor SDK calls and error
    translations. `Harness._maybe_collect()` calls their public `write()` methods.

ARCHITECTURE NOTE:
    The module is the common shell around a pure encoding guard and imperative
    provider operations. Its lifecycle task deliberately avoids `asyncio.Lock`;
    the task is created before the first await, so concurrent callers share one
    preflight operation and failed tasks are cleared for later recovery.

PUBLIC API INVENTORY:
    SinkWriteReceipt; CloudTrajectorySinkMixin; object_key(); pair_mapping();
    s3_tagging(); make_receipt(); close_resource().

COMMON MODIFICATION PATTERNS:
    Add provider-specific request fields in the provider Config first, then use
    this module only for behavior that truly has identical semantics across
    providers. Keep provider capabilities and control-plane behavior in the
    owning adapter.

WHAT NOT TO DO IN THIS FILE:
    1. Do not import or instantiate a cloud SDK.
    2. Do not add provider-specific error mappings or bucket lifecycle mutations.
    3. Do not move redaction here; the collector owns the redaction boundary.

KNOWN EDGE CASES:
    `write()` must guard payload size before `verify()` so invalid records never
    cause preflight traffic. A close may race with a provider call; close is
    idempotent, while the provider call remains responsible for cancellation and
    typed error translation.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/cloud-trajectory-provider-expansion.md

TESTS:
    tests/features/cloud_trajectory_provider_expansion/test_adapters.py and
    test_resilience.py; compatibility coverage remains in
    tests/test_cloud_trajectory_sinks.py.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from vidbyte.harnesses.contracts import TrajectoryRecord
from vidbyte.harnesses.errors import HarnessSinkSetupError
from vidbyte.harnesses.stores._sink_support import SinkEncoding


@dataclass(frozen=True, slots=True)
class SinkWriteReceipt:
    """Safe provider acknowledgement details for one trajectory object."""

    provider: str
    object_key: str
    bytes_written: int
    etag: str | None = None
    version_id: str | None = None
    checksum: str | None = None
    request_id: str | None = None
    completed_at: datetime = datetime(1970, 1, 1, tzinfo=timezone.utc)


class SinkLifecycle:
    """Owns one memoized, recoverable preflight task and the last receipt."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        # @intent shared-preflight-task-ownership
        # One task is the concurrency boundary; clearing it after failure
        # allows a later caller to recover without duplicate successful checks.
        self.verify_task: asyncio.Task[None] | None = None
        self.last_receipt: SinkWriteReceipt | None = None
        self.closed = False

    async def ensure_ready(self, preflight: Callable[[], Awaitable[None]]) -> None:
        """Share concurrent preflight and clear failures so recovery is possible."""
        # @intent failed-preflight-is-retryable
        # A failed task must not poison the sink for its entire lifetime.
        if self.closed:
            raise HarnessSinkSetupError(
                "The trajectory sink is closed and cannot accept another write.",
                details={"provider": self.provider},
            )
        if self.verify_task is None:
            self.verify_task = asyncio.ensure_future(preflight())
        try:
            await self.verify_task
        except asyncio.CancelledError:
            self.verify_task = None
            raise
        except Exception:
            self.verify_task = None
            raise

    def remember(self, receipt: SinkWriteReceipt) -> None:
        """Retain the latest safe receipt for operator inspection."""
        self.last_receipt = receipt


class CloudTrajectorySinkMixin:
    """Adds the common cloud sink lifecycle without changing TrajectorySink."""

    _lifecycle: SinkLifecycle
    _config: Any

    def _initialize_cloud_lifecycle(self, provider: str) -> None:
        # @intent lifecycle-is-created-after-client
        # Construction errors remain synchronous setup failures, while the
        # memoized task begins only when the first record needs the endpoint.
        self._lifecycle = SinkLifecycle(provider)

    async def verify(self) -> None:
        """Run the adapter's memoized metadata or explicit write probe."""
        await self._lifecycle.ensure_ready(self._run_preflight)

    async def _ensure_ready(self) -> None:
        """Retain the PR #393 private helper for existing adapter tests."""
        await self.verify()

    async def write(self, record: TrajectoryRecord) -> None:
        """Write one record while preserving the original protocol return type."""
        await self.write_with_receipt(record)

    async def write_with_receipt(self, record: TrajectoryRecord) -> SinkWriteReceipt:
        """Encode, size-check, preflight, and upload one trajectory record."""
        payload = SinkEncoding.encode_record(record)
        SinkEncoding.guard_size(payload, run_id=record.run_id)
        await self.verify()
        receipt = await self._put_record(self._object_key(record.run_id), payload)
        self._lifecycle.remember(receipt)
        return receipt

    @property
    def last_receipt(self) -> SinkWriteReceipt | None:
        """Return the latest safe provider acknowledgement, if any."""
        return self._lifecycle.last_receipt

    async def aclose(self) -> None:
        """Close the provider client once and make future writes fail clearly."""
        if self._lifecycle.closed:
            return
        self._lifecycle.closed = True
        await close_resource(getattr(self, "_client", None))
        await close_resource(getattr(self, "_credentials", None))
        await close_resource(getattr(self, "_credential", None))

    async def __aenter__(self) -> "CloudTrajectorySinkMixin":
        """Return the sink for use as an async context manager."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Close the sink when an async context manager exits."""
        await self.aclose()

    def _object_key(self, run_id: str) -> str:
        """Build a stable prefix/run-id JSONL object key."""
        return object_key(self._config.prefix, run_id)

    async def _run_preflight(self) -> None:
        """Delegate preflight and optional write-probe behavior to the adapter."""
        await self._run_metadata_preflight()
        preflight_mode = getattr(self._config, "preflight_mode", None)
        if preflight_mode is not None and preflight_mode.value == "write_probe":
            await self._run_write_probe()

    async def _run_metadata_preflight(self) -> None:
        raise NotImplementedError

    async def _run_write_probe(self) -> None:
        raise NotImplementedError

    async def _put_record(self, key: str, payload: bytes) -> SinkWriteReceipt:
        raise NotImplementedError


def object_key(prefix: str, run_id: str) -> str:
    """Return the canonical JSONL key without permitting prefix traversal."""
    normalized = prefix.rstrip("/")
    return f"{normalized}/{run_id}.jsonl" if normalized else f"{run_id}.jsonl"


def pair_mapping(pairs: Mapping[str, str] | Sequence[tuple[str, str]]) -> dict[str, str]:
    """Convert validated immutable pairs to a vendor request mapping."""
    return dict(pairs.items()) if isinstance(pairs, Mapping) else dict(pairs)


def s3_tagging(pairs: Mapping[str, str] | Sequence[tuple[str, str]]) -> str | None:
    """Encode validated tag pairs into the S3 request's query-string form."""
    mapping = pair_mapping(pairs)
    return urlencode(mapping) if mapping else None


def make_receipt(provider: str, key: str, payload: bytes, response: Any) -> SinkWriteReceipt:
    """Extract only stable, non-secret acknowledgement fields from a response."""
    # @intent receipt-is-safe-to-observe
    # SDK response objects may carry headers and metadata, so select only
    # documented acknowledgement fields and never serialize the whole object.
    metadata = _response_mapping(response)
    headers = _response_mapping(metadata.get("ResponseMetadata"))
    if not headers:
        headers = _response_mapping(_response_value(response, "headers"))
    return SinkWriteReceipt(
        provider=provider,
        object_key=key,
        bytes_written=len(payload),
        etag=_safe_string(metadata.get("ETag") or metadata.get("etag") or _response_value(response, "etag")),
        version_id=_safe_string(metadata.get("VersionId") or metadata.get("version_id") or _response_value(response, "version_id")),
        checksum=_safe_string(metadata.get("ChecksumSHA256") or metadata.get("checksum") or _response_value(response, "crc32c") or _response_value(response, "md5_hash") or _response_value(response, "hash_crc64") or _response_value(response, "crc64_ecma")),
        request_id=_safe_string(headers.get("RequestId") or headers.get("request-id") or headers.get("opc-request-id") or headers.get("x-amz-request-id") or headers.get("x-oss-request-id") or _response_value(response, "request_id")),
        completed_at=datetime.now(timezone.utc),
    )


async def close_resource(resource: Any) -> None:
    """Close a sync or async provider resource without blocking the event loop."""
    close = getattr(resource, "close", None)
    if not callable(close):
        return
    result = await asyncio.to_thread(close)
    if inspect.isawaitable(result):
        await result


def _response_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _response_value(value: Any, name: str) -> Any:
    """Read one documented response attribute without serializing the object."""
    return getattr(value, name, None)


def _safe_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


__all__ = [
    "CloudTrajectorySinkMixin",
    "SinkWriteReceipt",
    "close_resource",
    "make_receipt",
    "object_key",
    "pair_mapping",
    "s3_tagging",
]
