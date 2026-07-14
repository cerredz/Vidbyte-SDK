"""Context Protocol Header

Path: vidbyte/procedures/serialization.py
Purpose: Canonically hash and schema-safely encode immutable procedure records.
Architecture: ProcedureCodec owns JSON shapes; ProcedureIdentity owns allowlisted ids,
timestamps, deterministic operation ids, and content fingerprints.
Exports: ProcedureCodec and ProcedureIdentity.
Invariants: Fingerprints exclude lifecycle/provenance fields; schema v1 is fail-closed;
serialized mappings are deterministic and JSON-safe.
Do not: Treat fingerprints as correctness proofs or silently coerce future schemas.
Related: vidbyte/procedures/contracts.py and stores/file.py.
Tests: Existing serialization verification plus inline smoke checks only.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from vidbyte.procedures.contracts import (
    ProcedureCandidate, ProcedureCheckResult, ProcedureOutcome, ProcedureRecord,
    ProcedureRef, ProcedureStatus, ProcedureVerificationEvidence,
)
from vidbyte.procedures.errors import ProcedureValidationError, ProcedureVersionError


class ProcedureIdentity:
    """Canonical identifiers and hashes for procedure records."""

    SCHEMA_VERSION = 1
    _SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

    @classmethod
    def validate_id(cls, value: str, *, field_name: str) -> str:
        # Reject unsafe path segments before any store constructs a filesystem path.
        text = str(value).strip()
        if not cls._SAFE_ID.fullmatch(text):
            raise ProcedureValidationError(
                f"{field_name} must match [A-Za-z0-9][A-Za-z0-9._-]{{0,127}}.",
                details={"field": field_name, "value_length": len(text)},
            )
        return text

    @classmethod
    def content_fingerprint(cls, candidate: ProcedureCandidate | ProcedureRecord) -> str:
        # Hash only reusable content so lifecycle/provenance changes do not alter identity.
        payload = {
            "title": candidate.title,
            "summary": candidate.summary,
            "body": candidate.body,
            "applicability": list(candidate.applicability),
            "preconditions": list(candidate.preconditions),
            "expected_outcomes": list(candidate.expected_outcomes),
            "tags": list(candidate.tags),
            "required_tools": list(candidate.required_tools),
            "environment_fingerprint": candidate.environment_fingerprint,
        }
        return cls.hash_mapping(payload)

    @classmethod
    def deterministic_id(cls, prefix: str, *parts: str, length: int = 24) -> str:
        # Derive SDK-owned safe ids without exposing raw prompts or evidence in paths.
        digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:length]
        return f"{prefix}_{digest}"

    @staticmethod
    def hash_mapping(payload: dict[str, Any]) -> str:
        # Produce stable lowercase SHA-256 over canonical compact JSON.
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def utc_now() -> str:
        # Use one timezone-explicit representation for durable audit timestamps.
        return datetime.now(timezone.utc).isoformat()


class ProcedureCodec:
    """Encode and decode schema-v1 procedure records and outcomes."""

    @classmethod
    def record_to_dict(cls, record: ProcedureRecord) -> dict[str, Any]:
        # Convert nested frozen dataclasses and enums into deterministic JSON data.
        return cls._json_safe(asdict(record))

    @classmethod
    def record_from_dict(cls, raw: dict[str, Any]) -> ProcedureRecord:
        # Fail closed on unknown schemas before rebuilding nested verification evidence.
        schema_version = int(raw.get("schema_version", 0))
        if schema_version != ProcedureIdentity.SCHEMA_VERSION:
            raise ProcedureVersionError(
                "Unsupported procedure record schema version.",
                details={"expected": ProcedureIdentity.SCHEMA_VERSION, "actual": schema_version},
            )
        verification_raw = raw.get("verification")
        verification = cls._verification_from_dict(verification_raw) if isinstance(verification_raw, dict) else None
        try:
            return ProcedureRecord(
                schema_version=schema_version,
                procedure_id=str(raw["procedure_id"]),
                version=int(raw["version"]),
                namespace=str(raw["namespace"]),
                learning_operation_id=str(raw["learning_operation_id"]),
                status=ProcedureStatus(str(raw["status"])),
                title=str(raw["title"]), summary=str(raw["summary"]), body=str(raw["body"]),
                applicability=tuple(str(item) for item in raw.get("applicability", ())),
                preconditions=tuple(str(item) for item in raw.get("preconditions", ())),
                expected_outcomes=tuple(str(item) for item in raw.get("expected_outcomes", ())),
                tags=tuple(str(item) for item in raw.get("tags", ())),
                required_tools=tuple(str(item) for item in raw.get("required_tools", ())),
                environment_fingerprint=str(raw.get("environment_fingerprint", "")),
                content_fingerprint=str(raw["content_fingerprint"]),
                source_run_id=str(raw.get("source_run_id", "")),
                source_task_id=str(raw.get("source_task_id", "")),
                source_attempt_id=str(raw.get("source_attempt_id", "")),
                source_evidence_event_ids=tuple(str(item) for item in raw.get("source_evidence_event_ids", ())),
                verification=verification, reason=str(raw.get("reason", "")),
                created_at=str(raw["created_at"]),
                supersedes_version=None if raw.get("supersedes_version") is None else int(raw["supersedes_version"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProcedureVersionError("Procedure record is missing required schema-v1 fields.") from exc

    @classmethod
    def outcome_to_dict(cls, outcome: ProcedureOutcome) -> dict[str, Any]:
        # Encode an exact-version observed outcome without widening the procedure ref.
        return cls._json_safe(asdict(outcome))

    @classmethod
    def outcome_from_dict(cls, raw: dict[str, Any]) -> ProcedureOutcome:
        # Rebuild an immutable outcome and its exact nested ProcedureRef.
        try:
            ref = raw["procedure"]
            return ProcedureOutcome(
                outcome_id=str(raw["outcome_id"]),
                procedure=ProcedureRef(str(ref["namespace"]), str(ref["procedure_id"]), int(ref["version"]), str(ref["content_fingerprint"])),
                run_id=str(raw["run_id"]), task_id=str(raw["task_id"]), attempt_id=str(raw["attempt_id"]),
                succeeded=bool(raw["succeeded"]), suspected_failure=bool(raw["suspected_failure"]),
                reason=str(raw.get("reason", "")), created_at=str(raw["created_at"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProcedureVersionError("Procedure outcome is missing required fields.") from exc

    @classmethod
    def canonical_record(cls, record: ProcedureRecord) -> str:
        # Provide a byte-comparable representation for idempotent replay checks.
        return json.dumps(cls.record_to_dict(record), ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @classmethod
    def _verification_from_dict(cls, raw: dict[str, Any]) -> ProcedureVerificationEvidence:
        # Restore verifier provenance including each deterministic check result.
        return ProcedureVerificationEvidence(
            run_id=str(raw["run_id"]), task_id=str(raw["task_id"]), attempt_id=str(raw["attempt_id"]),
            source_task_verification_event_id=str(raw["source_task_verification_event_id"]),
            source_drift_review_event_id=str(raw["source_drift_review_event_id"]),
            candidate_content_fingerprint=str(raw["candidate_content_fingerprint"]),
            criteria=tuple(str(item) for item in raw.get("criteria", ())),
            observations=tuple(str(item) for item in raw.get("observations", ())),
            source_task_validator_results=tuple(cls._check_from_dict(item) for item in raw.get("source_task_validator_results", ())),
            procedure_fidelity_results=tuple(cls._check_from_dict(item) for item in raw.get("procedure_fidelity_results", ())),
            verifier_name=str(raw["verifier_name"]), verified_at=str(raw["verified_at"]), evidence_hash=str(raw["evidence_hash"]),
        )

    @staticmethod
    def _check_from_dict(raw: dict[str, Any]) -> ProcedureCheckResult:
        # Restore one validator result while keeping evidence immutable.
        return ProcedureCheckResult(
            validator_id=str(raw["validator_id"]), validator_version=str(raw["validator_version"]),
            config_fingerprint=str(raw["config_fingerprint"]), required=bool(raw["required"]), passed=bool(raw["passed"]),
            evidence=tuple(str(item) for item in raw.get("evidence", ())), error_code=str(raw.get("error_code", "")),
            error_message=str(raw.get("error_message", "")), duration_ms=int(raw.get("duration_ms", 0)),
        )

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        # Recursively normalize enums and tuple-like structures for standard JSON.
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, dict):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [cls._json_safe(item) for item in value]
        return value


__all__ = ["ProcedureCodec", "ProcedureIdentity"]
