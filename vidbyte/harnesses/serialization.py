"""FILE: vidbyte/harnesses/serialization.py

PURPOSE:
    Owns the single redaction chokepoint for harness data that leaves the box.
    It classifies credential-like mapping keys (shared with config rejection) and
    projects arbitrary captured Python values into JSON-safe, secret-scrubbed data
    without changing the raw output returned to callers.

ROLE IN CODEBASE:
    Called by config security checks and by the trajectory collector before any
    task/output/history reaches a TrajectorySink. It performs no filesystem or
    network I/O. The bespoke spec/run/event record codecs were removed when
    persistence pivoted onto durable Sessions; those records now live in the
    SessionStore and are serialized by the session serializer.

ARCHITECTURE NOTE:
    A sellable trajectory carries free-text PII/secrets in values and tool outputs
    that pure key-based rejection misses, so redaction is a mandatory pass and the
    redactor is pluggable: tenants can supply a callable that adds domain patterns.

PUBLIC API INVENTORY:
    HarnessSecretPolicy.is_secret_key() identifies credential-like mapping keys.
    HarnessRedactor.redact() projects captured values into safe scrubbed data;
    safe() is a back-compatible alias; safe_error_message() redacts common
    credential assignments and bounds persisted failure text.

WHAT NOT TO DO IN THIS FILE:
    1. Do not read or write files; sinks own I/O.
    2. Do not hash configs; HarnessConfigLoader owns identity.
    3. Do not preserve credential-like keys for convenience.

KNOWN EDGE CASES:
    Unsupported objects and recursive references become explicit dropped markers.
    Full free-text secret detection is impossible; key scrubbing and common
    assignment redaction reduce risk but callers still own capture governance and
    may supply a stricter redactor.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    Exercised by repository tests and inline redaction smoke checks; no new test
    file was added under the approved no-tests workflow.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID


class HarnessSecretPolicy:
    """Shared key classifier for configuration rejection and capture scrubbing."""

    _SECRET_KEYS = frozenset({
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "token",
        "secret",
        "client_secret",
        "private_key",
        "secret_key",
        "access_key",
        "access_key_id",
        "session_token",
        "bearer_token",
        "password",
        "credential",
        "credentials",
        "authorization",
        "auth",
    })

    @classmethod
    def is_secret_key(cls, key: str) -> bool:
        # Matches exact normalized credential names without misclassifying words such as author.
        normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
        suffixes = ("_api_key", "_private_key", "_secret_key", "_access_key", "_access_key_id", "_token", "_secret", "_password")
        return normalized in cls._SECRET_KEYS or normalized.endswith(suffixes)


class HarnessRedactor:
    """The single redaction pass applied to every value bound for a TrajectorySink."""

    _ERROR_ASSIGNMENT = re.compile(r"(?i)\b(api[_-]?key|private[_-]?key|secret[_-]?key|access[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|credential|authorization)\s*[:=]\s*([^\s,;]+)")

    def redact(self, value: Any) -> Any:
        # Projects arbitrary capture data into a recursively scrubbed JSON-safe value.
        try:
            return self._safe(value, set())
        except Exception:
            return {"__dropped__": type(value).__name__}

    # Back-compatible alias so existing call sites reading `.safe(...)` keep working.
    safe = redact

    def safe_error_message(self, error: BaseException | str, *, max_chars: int = 1000) -> str:
        # Redacts common credential assignments and bounds persisted failure text.
        try:
            message = str(error)
        except Exception:
            message = ""
        redacted = self._ERROR_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=<redacted>", message)
        fallback = f"{type(error).__name__} raised without a message." if not redacted.strip() else redacted
        return fallback[:max_chars]

    def _safe(self, value: Any, active: set[int]) -> Any:
        # Dispatches one value to a stable primitive, collection, or object projection.
        if value is None or isinstance(value, (str, int, bool)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else {"__dropped__": "non_finite_float"}
        if isinstance(value, Enum):
            return self._safe(value.value, active)
        if isinstance(value, (Path, UUID, date, datetime, time)):
            return str(value) if not hasattr(value, "isoformat") else value.isoformat()
        return self._safe_container_or_object(value, active)

    def _safe_container_or_object(self, value: Any, active: set[int]) -> Any:
        # Detects recursive references before delegating structured values.
        identity = id(value)
        if identity in active:
            return {"__dropped__": "recursive_reference"}
        active.add(identity)
        try:
            return self._project_structured_value(value, active)
        finally:
            active.remove(identity)

    def _project_structured_value(self, value: Any, active: set[int]) -> Any:
        # Converts mappings, sequences, dataclasses, and explicit object exporters.
        if isinstance(value, Mapping):
            return self._safe_mapping(value, active)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [self._safe(item, active) for item in value]
        if isinstance(value, (set, frozenset)):
            return [self._safe(item, active) for item in sorted(value, key=repr)]
        if is_dataclass(value) and not isinstance(value, type):
            return {item.name: self._safe(getattr(value, item.name), active) for item in fields(value)}
        return self._safe_exported_object(value, active)

    def _safe_mapping(self, value: Mapping[Any, Any], active: set[int]) -> dict[str, Any]:
        # Drops credential-like keys and recursively projects the remaining mapping.
        return {str(key): self._safe(item, active) for key, item in value.items() if not HarnessSecretPolicy.is_secret_key(str(key))}

    def _safe_exported_object(self, value: Any, active: set[int]) -> Any:
        # Uses explicit object exporters when present and otherwise records a type marker.
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            try:
                return self._safe(model_dump(mode="json"), active)
            except Exception:
                return {"__dropped__": type(value).__name__}
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            try:
                return self._safe(to_dict(), active)
            except Exception:
                return {"__dropped__": type(value).__name__}
        return {"__dropped__": type(value).__name__}


__all__ = ["HarnessRedactor", "HarnessSecretPolicy"]
