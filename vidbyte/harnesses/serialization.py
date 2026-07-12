"""FILE: vidbyte/harnesses/serialization.py

PURPOSE:
    Converts harness specifications, runs, and events to and from one versioned,
    secret-scrubbed JSON payload shape. It also projects arbitrary captured Python
    values into safe data without changing the raw output returned to callers.

ROLE IN CODEBASE:
    Called by config security checks, all HarnessStore implementations, the
    execution envelope, and dataset export. It depends on harness contracts and
    typed serialization/version errors but performs no filesystem or network I/O.

ARCHITECTURE NOTE:
    Serialization is the canonical persistence boundary. Store adapters must use
    this codec rather than inventing provider-specific shapes. See the approved
    harness execution-contract design document.

PUBLIC API INVENTORY:
    HarnessSecretPolicy.is_secret_key() identifies credential-like mapping keys.
    HarnessSerializer serializes/deserializes specs, runs, and events; safe()
    projects captured values; safe_error_message() redacts common assignments.

COMMON MODIFICATION PATTERNS:
    Add contract fields symmetrically to encode/decode methods and increment the
    schema version only with an explicit compatibility design.

WHAT NOT TO DO IN THIS FILE:
    1. Do not read or write files; local stores own I/O.
    2. Do not hash configs; HarnessConfigLoader owns identity.
    3. Do not preserve credential-like keys for convenience.

KNOWN EDGE CASES:
    Unsupported objects and recursive references become explicit dropped markers.
    Full string-content secret detection is impossible; key scrubbing and common
    assignment redaction reduce risk but callers still own capture governance.
    Unknown record versions fail on both encoding and decoding.

COMMON ERRORS:
    HarnessSerializationError for malformed fields; HarnessVersionError for an
    absent or unsupported schema version.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    Exercised by repository tests and inline round-trip/file-store smoke checks;
    no new test file was added under the approved no-tests workflow.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID

from vidbyte.harnesses.contracts import (
    HARNESS_SCHEMA_VERSION,
    HarnessArtifactRef,
    HarnessCaptureLevel,
    HarnessCaptureScope,
    HarnessErrorRecord,
    HarnessEvent,
    HarnessRun,
    HarnessRunStatus,
    HarnessSpec,
)
from vidbyte.harnesses.errors import HarnessSerializationError, HarnessVersionError

E = TypeVar("E", bound=Enum)


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
        return normalized in cls._SECRET_KEYS or normalized.endswith(("_api_key", "_token", "_secret", "_password"))


class HarnessSerializer:
    """Versioned JSON-safe codec shared by harness stores and dataset exports."""

    _ERROR_ASSIGNMENT = re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|credential|authorization)\s*[:=]\s*([^\s,;]+)")

    def spec_to_dict(self, spec: HarnessSpec) -> dict[str, Any]:
        # Serializes one exact behavior specification inside a versioned envelope.
        self._assert_contract_version(spec.schema_version, "spec")
        return {
            "schema_version": HARNESS_SCHEMA_VERSION,
            "spec": {
                "schema_version": spec.schema_version,
                "spec_id": spec.spec_id,
                "harness_type": spec.harness_type,
                "harness_version": spec.harness_version,
                "agents": self.safe(list(spec.agents)),
                "params": self.safe(spec.params),
                "requested_config": self.safe(spec.requested_config),
                "resolved_config": self.safe(spec.resolved_config),
            },
        }

    def spec_from_dict(self, payload: Mapping[str, Any]) -> HarnessSpec:
        # Reconstructs one specification and rejects malformed or unsupported payloads.
        body = self._versioned_body(payload, "spec")
        agents = self._mapping_sequence(body.get("agents", ()), "agents")
        return HarnessSpec(
            schema_version=self._record_version(body, "spec"),
            spec_id=self._string(body, "spec_id"),
            harness_type=self._string(body, "harness_type"),
            harness_version=self._string(body, "harness_version"),
            agents=agents,
            params=self._mapping(body, "params"),
            requested_config=self._mapping(body, "requested_config"),
            resolved_config=self._mapping(body, "resolved_config"),
        )

    def run_to_dict(self, run: HarnessRun) -> dict[str, Any]:
        # Serializes one running or terminal execution snapshot.
        self._assert_contract_version(run.schema_version, "run")
        return {
            "schema_version": HARNESS_SCHEMA_VERSION,
            "run": {
                "schema_version": run.schema_version,
                "run_id": run.run_id,
                "spec_id": run.spec_id,
                "status": run.status.value,
                "started_at": run.started_at,
                "ended_at": run.ended_at,
                "capture_level": run.capture_level.value,
                "capture_scope": run.capture_scope.value,
                "request": self.safe(run.request),
                "response": self.safe(run.response),
                "error": self._error_to_dict(run.error),
                "metadata": self.safe(run.metadata),
                "artifacts": [self._artifact_to_dict(item) for item in run.artifacts],
                "session_ids": list(run.session_ids),
                "event_count": run.event_count,
                "persistence_errors": list(run.persistence_errors),
            },
        }

    def run_from_dict(self, payload: Mapping[str, Any]) -> HarnessRun:
        # Reconstructs one run and its nested error and artifact records.
        body = self._versioned_body(payload, "run")
        artifacts = tuple(self._artifact_from_dict(item) for item in self._mapping_sequence(body.get("artifacts", ()), "artifacts"))
        return HarnessRun(
            schema_version=self._record_version(body, "run"),
            run_id=self._string(body, "run_id"),
            spec_id=self._string(body, "spec_id"),
            status=self._enum(HarnessRunStatus, body.get("status"), "status"),
            started_at=self._string(body, "started_at"),
            ended_at=self._optional_string(body.get("ended_at"), "ended_at"),
            capture_level=self._enum(HarnessCaptureLevel, body.get("capture_level"), "capture_level"),
            capture_scope=self._enum(HarnessCaptureScope, body.get("capture_scope"), "capture_scope"),
            request=body.get("request"),
            response=body.get("response"),
            error=self._error_from_value(body.get("error")),
            metadata=self._mapping(body, "metadata"),
            artifacts=artifacts,
            session_ids=self._string_sequence(body.get("session_ids", ()), "session_ids"),
            event_count=self._integer(body, "event_count"),
            persistence_errors=self._string_sequence(body.get("persistence_errors", ()), "persistence_errors"),
        )

    def event_to_dict(self, event: HarnessEvent) -> dict[str, Any]:
        # Serializes one ordered event inside a versioned envelope.
        self._assert_contract_version(event.schema_version, "event")
        return {
            "schema_version": HARNESS_SCHEMA_VERSION,
            "event": {
                "schema_version": event.schema_version,
                "event_id": event.event_id,
                "run_id": event.run_id,
                "sequence": event.sequence,
                "event_type": event.event_type,
                "created_at": event.created_at,
                "payload": self.safe(event.payload),
            },
        }

    def event_from_dict(self, payload: Mapping[str, Any]) -> HarnessEvent:
        # Reconstructs one ordered event and validates required fields.
        body = self._versioned_body(payload, "event")
        return HarnessEvent(
            schema_version=self._record_version(body, "event"),
            event_id=self._string(body, "event_id"),
            run_id=self._string(body, "run_id"),
            sequence=self._integer(body, "sequence"),
            event_type=self._string(body, "event_type"),
            created_at=self._string(body, "created_at"),
            payload=self._mapping(body, "payload"),
        )

    def safe(self, value: Any) -> Any:
        # Projects arbitrary capture data into a recursively scrubbed JSON-safe value.
        return self._safe(value, set())

    def safe_error_message(self, error: BaseException | str, *, max_chars: int = 1000) -> str:
        # Redacts common credential assignments and bounds persisted failure text.
        message = str(error)
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

    def _artifact_to_dict(self, artifact: HarnessArtifactRef) -> dict[str, Any]:
        # Serializes one external artifact reference without loading its content.
        return {
            "artifact_id": artifact.artifact_id,
            "uri": artifact.uri,
            "media_type": artifact.media_type,
            "sha256": artifact.sha256,
            "metadata": self.safe(artifact.metadata),
        }

    def _artifact_from_dict(self, payload: Mapping[str, Any]) -> HarnessArtifactRef:
        # Reconstructs one external artifact reference.
        return HarnessArtifactRef(
            artifact_id=self._string(payload, "artifact_id"),
            uri=self._string(payload, "uri"),
            media_type=self._optional_string(payload.get("media_type"), "media_type"),
            sha256=self._optional_string(payload.get("sha256"), "sha256"),
            metadata=self._mapping(payload, "metadata"),
        )

    def _error_to_dict(self, error: HarnessErrorRecord | None) -> dict[str, str] | None:
        # Serializes a safe persisted execution failure when present.
        if error is None:
            return None
        return {"exception_type": error.exception_type, "message": self.safe_error_message(error.message)}

    def _error_from_value(self, value: Any) -> HarnessErrorRecord | None:
        # Reconstructs an optional execution failure record.
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise HarnessSerializationError("Harness run error must be an object.", details={"field": "error", "actual_type": type(value).__name__})
        return HarnessErrorRecord(exception_type=self._string(value, "exception_type"), message=self._string(value, "message"))

    def _versioned_body(self, payload: Mapping[str, Any], field: str) -> Mapping[str, Any]:
        # Validates the schema envelope and returns the named nested record.
        if not isinstance(payload, Mapping):
            raise HarnessSerializationError("Harness payload must be an object.", details={"field": field, "actual_type": type(payload).__name__})
        version = payload.get("schema_version")
        if version != HARNESS_SCHEMA_VERSION:
            raise HarnessVersionError("Unsupported harness payload schema version.", details={"found": version, "expected": HARNESS_SCHEMA_VERSION, "record": field})
        body = payload.get(field)
        if not isinstance(body, Mapping):
            raise HarnessSerializationError("Harness payload is missing its record object.", details={"field": field})
        return body

    def _mapping(self, payload: Mapping[str, Any], field: str) -> dict[str, Any]:
        # Returns a copied mapping field or raises a typed shape error.
        value = payload.get(field, {})
        if not isinstance(value, Mapping):
            raise HarnessSerializationError("Harness field must be an object.", details={"field": field, "actual_type": type(value).__name__})
        return {str(key): item for key, item in value.items()}

    def _mapping_sequence(self, value: Any, field: str) -> tuple[dict[str, Any], ...]:
        # Returns a tuple of copied mapping items for an array field.
        if not isinstance(value, list):
            raise HarnessSerializationError("Harness field must be an array of objects.", details={"field": field, "actual_type": type(value).__name__})
        if any(not isinstance(item, Mapping) for item in value):
            raise HarnessSerializationError("Harness array contains a non-object item.", details={"field": field})
        return tuple({str(key): child for key, child in item.items()} for item in value)

    def _string_sequence(self, value: Any, field: str) -> tuple[str, ...]:
        # Returns a tuple of string values for an array field.
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise HarnessSerializationError("Harness field must be an array of strings.", details={"field": field})
        return tuple(value)

    def _string(self, payload: Mapping[str, Any], field: str) -> str:
        # Returns a required non-empty string field.
        value = payload.get(field)
        if not isinstance(value, str) or not value:
            raise HarnessSerializationError("Harness field must be a non-empty string.", details={"field": field, "actual_type": type(value).__name__})
        return value

    def _optional_string(self, value: Any, field: str) -> str | None:
        # Returns an optional string field while rejecting other shapes.
        if value is None:
            return None
        if not isinstance(value, str):
            raise HarnessSerializationError("Harness field must be a string or null.", details={"field": field, "actual_type": type(value).__name__})
        return value

    def _integer(self, payload: Mapping[str, Any], field: str) -> int:
        # Returns a required integer field without accepting booleans.
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            raise HarnessSerializationError("Harness field must be an integer.", details={"field": field, "actual_type": type(value).__name__})
        return value

    def _record_version(self, payload: Mapping[str, Any], record: str) -> int:
        # Requires the nested record version to agree with its supported envelope.
        version = self._integer(payload, "schema_version")
        self._assert_contract_version(version, record)
        return version

    def _assert_contract_version(self, version: Any, record: str) -> None:
        # Rejects caller-constructed records that cannot be written and read as schema one.
        if isinstance(version, bool) or not isinstance(version, int) or version != HARNESS_SCHEMA_VERSION:
            raise HarnessVersionError("Unsupported harness record schema version.", details={"found": version, "expected": HARNESS_SCHEMA_VERSION, "record": record})

    def _enum(self, enum_type: type[E], value: Any, field: str) -> E:
        # Converts one persisted string into the requested enum with a typed error.
        try:
            return enum_type(value)
        except (TypeError, ValueError) as exc:
            raise HarnessSerializationError("Harness field has an unsupported enum value.", details={"field": field, "value": str(value)}) from exc


__all__ = ["HarnessSecretPolicy", "HarnessSerializer"]
