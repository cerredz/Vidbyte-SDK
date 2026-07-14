"""Context Protocol Header

Path: vidbyte/procedures/library.py
Purpose: Own all safe staging, promotion, rejection, retrieval, outcome, and retirement
semantics for reusable procedures.
Architecture: ProcedureLibrary is the command/query boundary; LexicalProcedureRanker
is the dependency-free default; ProcedureStore remains an audit persistence adapter.
Exports: ProcedureLibrary, ProcedureRanker, and LexicalProcedureRanker.
Invariants: Only authority-backed exact candidates become VERIFIED; normal retrieval
shows only compatible active VERIFIED heads; outcome failures remain version-pinned.
Do not: Let tools promote records, infer latest candidates, or treat search cards as use.
Related: docs/design/long-running-paradigm.md sections 6.1-6.3.
Tests: Existing verification plus inline smoke checks only under no-tests approval.
Concurrency: Store-level CAS is authoritative; this service retries bounded stale writes.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace
from typing import Protocol

from vidbyte.procedures.contracts import (
    ProcedureCandidate, ProcedureLimits, ProcedureMatch, ProcedureOutcome,
    ProcedurePromotionAuthority, ProcedureRecord, ProcedureRef, ProcedureStatus,
    ProcedureSummary, ProcedureVerificationEvidence,
)
from vidbyte.procedures.errors import (
    ProcedureNotFoundError, ProcedurePromotionError, ProcedureStoreConflictError,
    ProcedureValidationError, ProcedureVersionError,
)
from vidbyte.procedures.serialization import ProcedureCodec, ProcedureIdentity
from vidbyte.procedures.store import ProcedureStore


class ProcedureRanker(Protocol):
    """Pluggable deterministic ranking boundary for active verified records."""

    def rank(self, query: str, records: Sequence[ProcedureRecord]) -> tuple[ProcedureMatch, ...]:
        # Return compact ranked matches without exposing procedure bodies.
        ...


class LexicalProcedureRanker:
    """Dependency-free lexical ranker with stable tie ordering."""

    _TERM = re.compile(r"[A-Za-z0-9_]+")

    def rank(self, query: str, records: Sequence[ProcedureRecord]) -> tuple[ProcedureMatch, ...]:
        # Score query overlap across the compact retrieval fields only.
        query_terms = self._terms(query)
        matches: list[ProcedureMatch] = []
        for record in records:
            record_terms = self._terms(" ".join((record.title, record.summary, *record.applicability, *record.preconditions, *record.tags)))
            overlap = tuple(sorted(query_terms & record_terms))
            if query_terms and not overlap:
                continue
            denominator = max(1, len(query_terms))
            score = len(overlap) / denominator if query_terms else 0.0
            matches.append(ProcedureMatch(self._summary(record), score, overlap))
        return tuple(sorted(matches, key=lambda match: (-match.score, match.summary.ref.procedure_id, match.summary.ref.version)))

    @classmethod
    def _terms(cls, text: str) -> set[str]:
        # Normalize alphanumeric terms for reproducible offline ranking.
        return {match.group(0).lower() for match in cls._TERM.finditer(text)}

    @staticmethod
    def _summary(record: ProcedureRecord) -> ProcedureSummary:
        # Project only the compact card fields allowed in search results.
        return ProcedureSummary(record.ref, record.title, record.summary, record.applicability, record.preconditions, record.tags, record.required_tools)


class ProcedureLibrary:
    """Sole public service for procedure lifecycle and compatible retrieval."""

    _MAX_CAS_ATTEMPTS = 3

    def __init__(self, store: ProcedureStore, *, limits: ProcedureLimits | None = None, ranker: ProcedureRanker | None = None) -> None:
        # Bind one trusted store and deterministic policy set for all operations.
        self.store = store
        self.limits = limits or ProcedureLimits()
        self.ranker = ranker or LexicalProcedureRanker()
        self._validate_limits()

    def stage(self, candidate: ProcedureCandidate, *, operation_id: str) -> ProcedureRecord:
        # Validate, hash, allocate, and append a non-retrievable candidate version.
        self._validate_candidate(candidate)
        operation_id = ProcedureIdentity.validate_id(operation_id, field_name="operation_id")
        fingerprint = ProcedureIdentity.content_fingerprint(candidate)
        existing = self.store.find_by_operation(candidate.namespace, operation_id)
        replay = self._resolve_stage_replay(existing, fingerprint)
        if replay is not None:
            return replay
        procedure_id = candidate.proposed_procedure_id or ProcedureIdentity.deterministic_id("proc", operation_id)
        ProcedureIdentity.validate_id(procedure_id, field_name="procedure_id")
        return self._append_candidate(candidate, procedure_id, fingerprint, operation_id)

    # @intent authority-gated-procedure-promotion
    # A successful task is necessary but not sufficient learning evidence. Promotion
    # pins the exact staged fingerprint, requires task/drift/fidelity provenance, and
    # delegates the final ledger check to an application authority. Removing any one
    # gate would let stale or merely plausible model text become cross-run memory.
    def promote(self, candidate: ProcedureRef, evidence: ProcedureVerificationEvidence, *, operation_id: str, authority: ProcedurePromotionAuthority) -> ProcedureRecord:
        # Verify the exact candidate and append a VERIFIED version or deduplicate safely.
        operation_id = ProcedureIdentity.validate_id(operation_id, field_name="operation_id")
        record = self._exact_record(candidate)
        self._validate_promotion(record, evidence, authority)
        replay = self._resolve_terminal_replay(record.namespace, operation_id)
        if replay is not None:
            return replay
        duplicate = self._equivalent_active(record.namespace, record.content_fingerprint, exclude_id=record.procedure_id)
        if duplicate is not None:
            self._append_status(record, ProcedureStatus.REJECTED, operation_id, reason=f"duplicate-of:{duplicate.namespace}/{duplicate.procedure_id}/{duplicate.version}", verification=evidence)
            return duplicate
        active = self._active_verified(record.namespace, record.procedure_id)
        return self._append_status(record, ProcedureStatus.VERIFIED, operation_id, verification=evidence, supersedes=active.version if active else None)

    def reject(self, candidate: ProcedureRef, reason: str, *, operation_id: str) -> ProcedureRecord:
        # Close one exact staged candidate with an immutable rejection audit record.
        reason = reason.strip()
        if not reason:
            raise ProcedureValidationError("Procedure rejection requires a non-empty reason.")
        operation_id = ProcedureIdentity.validate_id(operation_id, field_name="operation_id")
        record = self._exact_record(candidate)
        if record.status is not ProcedureStatus.CANDIDATE:
            raise ProcedurePromotionError("Only an exact CANDIDATE record may be rejected.", details={"procedure_id": record.procedure_id, "version": record.version, "status": record.status.value})
        replay = self._resolve_terminal_replay(record.namespace, operation_id)
        return replay or self._append_status(record, ProcedureStatus.REJECTED, operation_id, reason=reason)

    def search(self, query: str, *, namespace: str, environment_fingerprint: str = "", available_tools: Sequence[str] = (), limit: int = 5) -> tuple[ProcedureMatch, ...]:
        # Rank only active heads that the caller can execute in its bound environment.
        namespace = ProcedureIdentity.validate_id(namespace, field_name="namespace")
        if limit < 1:
            raise ProcedureValidationError("Procedure search limit must be positive.", details={"limit": limit})
        records = tuple(record for procedure_id in self.store.list_ids(namespace) if (record := self._active_verified(namespace, procedure_id)) is not None and self._compatible(record, environment_fingerprint, available_tools))
        return self.ranker.rank(query.strip(), records)[:limit]

    def load(self, procedure_id: str, *, version: int | None = None, namespace: str, environment_fingerprint: str = "", available_tools: Sequence[str] = ()) -> ProcedureRecord:
        # Recompute the active compatible head so a stale search handle cannot bypass policy.
        namespace = ProcedureIdentity.validate_id(namespace, field_name="namespace")
        procedure_id = ProcedureIdentity.validate_id(procedure_id, field_name="procedure_id")
        active = self._active_verified(namespace, procedure_id)
        if active is None or (version is not None and active.version != version) or not self._compatible(active, environment_fingerprint, available_tools):
            raise ProcedureNotFoundError("No active compatible verified procedure matched the requested handle.", details={"namespace": namespace, "procedure_id": procedure_id, "requested_version": version})
        return active

    # @intent exact-version-procedure-retirement
    # Suspected failures must never poison a replacement procedure that happens to reuse
    # the same stable id. Count outcomes only for the exact version and fingerprint, then
    # tombstone that active ref without deleting its audit history.
    def record_outcome(self, outcome: ProcedureOutcome, *, retire_after_suspected_failures: int) -> ProcedureRecord | None:
        # Append an idempotent exact-ref outcome and retire only that still-active version.
        if retire_after_suspected_failures < 1:
            raise ProcedureValidationError("retire_after_suspected_failures must be positive.")
        exact = self._exact_record(outcome.procedure)
        if exact.status is not ProcedureStatus.VERIFIED:
            raise ProcedureVersionError("Procedure outcomes require an exact VERIFIED record.", details={"procedure_id": exact.procedure_id, "version": exact.version})
        self.store.append_outcome(outcome)
        failures = sum(1 for item in self.store.outcomes(outcome.procedure) if item.suspected_failure)
        active = self._active_verified(outcome.procedure.namespace, outcome.procedure.procedure_id)
        if failures < retire_after_suspected_failures or active is None or active.ref != outcome.procedure:
            return None
        operation_id = ProcedureIdentity.deterministic_id("retire", outcome.procedure.namespace, outcome.procedure.procedure_id, str(outcome.procedure.version), outcome.procedure.content_fingerprint)
        replay = self._resolve_terminal_replay(outcome.procedure.namespace, operation_id)
        return replay or self._append_status(active, ProcedureStatus.RETIRED, operation_id, reason=f"suspected-failure-threshold:{failures}", supersedes=active.version)

    def active(self, namespace: str) -> tuple[ProcedureRecord, ...]:
        # Expose active heads for trusted diagnostics and promotion deduplication.
        namespace = ProcedureIdentity.validate_id(namespace, field_name="namespace")
        return tuple(record for procedure_id in self.store.list_ids(namespace) if (record := self._active_verified(namespace, procedure_id)) is not None)

    def _append_candidate(self, candidate: ProcedureCandidate, procedure_id: str, fingerprint: str, operation_id: str) -> ProcedureRecord:
        # Retry bounded CAS conflicts while preserving the exact normalized candidate.
        last_error: ProcedureStoreConflictError | None = None
        for _ in range(self._MAX_CAS_ATTEMPTS):
            chain = self.store.versions(candidate.namespace, procedure_id)
            latest = chain[-1].version if chain else None
            record = ProcedureRecord(
                ProcedureIdentity.SCHEMA_VERSION, procedure_id, 1 if latest is None else latest + 1,
                candidate.namespace, operation_id, ProcedureStatus.CANDIDATE, candidate.title,
                candidate.summary, candidate.body, candidate.applicability, candidate.preconditions,
                candidate.expected_outcomes, candidate.tags, candidate.required_tools,
                candidate.environment_fingerprint, fingerprint, candidate.source_run_id,
                candidate.source_task_id, candidate.source_attempt_id, candidate.source_evidence_event_ids,
                None, "", ProcedureIdentity.utc_now(), latest,
            )
            try:
                self.store.put(record, expected_latest_version=latest)
                return record
            except ProcedureStoreConflictError as exc:
                last_error = exc
                replay = self._resolve_stage_replay(self.store.find_by_operation(candidate.namespace, operation_id), fingerprint)
                if replay is not None:
                    return replay
        raise last_error or ProcedureStoreConflictError("Procedure candidate CAS retries were exhausted.")

    def _append_status(self, source: ProcedureRecord, status: ProcedureStatus, operation_id: str, *, reason: str = "", verification: ProcedureVerificationEvidence | None = None, supersedes: int | None = None) -> ProcedureRecord:
        # Retry bounded CAS conflicts while keeping reusable content byte-equivalent.
        last_error: ProcedureStoreConflictError | None = None
        for _ in range(self._MAX_CAS_ATTEMPTS):
            replay = self._resolve_terminal_replay(source.namespace, operation_id)
            if replay is not None:
                return replay
            latest = self.store.latest(source.namespace, source.procedure_id)
            record = replace(
                source, version=latest.version + 1, learning_operation_id=operation_id,
                status=status, verification=verification, reason=reason,
                created_at=ProcedureIdentity.utc_now(), supersedes_version=supersedes if supersedes is not None else source.version,
            )
            try:
                self.store.put(record, expected_latest_version=latest.version)
                return record
            except ProcedureStoreConflictError as exc:
                last_error = exc
        raise last_error or ProcedureStoreConflictError("Procedure lifecycle CAS retries were exhausted.")

    def _active_verified(self, namespace: str, procedure_id: str) -> ProcedureRecord | None:
        # Derive retrieval state from the audit chain without treating latest as active.
        active: ProcedureRecord | None = None
        for record in self.store.versions(namespace, procedure_id):
            if record.status is ProcedureStatus.VERIFIED:
                active = record
            elif record.status is ProcedureStatus.RETIRED and active is not None and record.supersedes_version == active.version:
                active = None
        return active

    def _validate_candidate(self, candidate: ProcedureCandidate) -> None:
        # Reject missing reusable meaning, unsafe ids, and every declared size overflow.
        ProcedureIdentity.validate_id(candidate.namespace, field_name="namespace")
        if candidate.proposed_procedure_id:
            ProcedureIdentity.validate_id(candidate.proposed_procedure_id, field_name="proposed_procedure_id")
        required = {"title": candidate.title, "summary": candidate.summary, "body": candidate.body, "applicability": candidate.applicability, "preconditions": candidate.preconditions, "expected_outcomes": candidate.expected_outcomes}
        missing = tuple(name for name, value in required.items() if not value)
        if missing:
            raise ProcedureValidationError("Procedure candidate is missing required reusable content.", details={"missing_fields": missing})
        limits = (("title", candidate.title, self.limits.max_title_chars), ("summary", candidate.summary, self.limits.max_summary_chars), ("body", candidate.body, self.limits.max_body_chars))
        for name, value, maximum in limits:
            if len(value) > maximum:
                raise ProcedureValidationError("Procedure candidate field exceeds its configured bound.", details={"field": name, "actual_chars": len(value), "max_chars": maximum})
        for name in ("applicability", "preconditions", "expected_outcomes", "tags", "required_tools", "source_evidence_event_ids"):
            values = getattr(candidate, name)
            if len(values) > self.limits.max_list_items or any(len(item) > self.limits.max_list_item_chars for item in values):
                raise ProcedureValidationError("Procedure candidate list exceeds its configured bounds.", details={"field": name, "items": len(values), "max_items": self.limits.max_list_items, "max_item_chars": self.limits.max_list_item_chars})

    def _validate_promotion(self, record: ProcedureRecord, evidence: ProcedureVerificationEvidence, authority: ProcedurePromotionAuthority) -> None:
        # Enforce fail-closed evidence completeness before invoking the ledger authority.
        if record.status is not ProcedureStatus.CANDIDATE:
            raise ProcedurePromotionError("Only an exact CANDIDATE record may be promoted.", details={"procedure_id": record.procedure_id, "version": record.version, "status": record.status.value})
        if evidence.candidate_content_fingerprint != record.content_fingerprint:
            raise ProcedurePromotionError("Promotion evidence fingerprint does not match the staged candidate.", details={"procedure_id": record.procedure_id, "version": record.version})
        if (evidence.run_id, evidence.task_id, evidence.attempt_id) != (record.source_run_id, record.source_task_id, record.source_attempt_id):
            raise ProcedurePromotionError("Promotion evidence source does not match candidate provenance.", details={"procedure_id": record.procedure_id, "version": record.version})
        if not evidence.source_task_verification_event_id or not evidence.source_drift_review_event_id or not evidence.evidence_hash or not evidence.criteria or not evidence.observations or not evidence.procedure_fidelity_results:
            raise ProcedurePromotionError("Promotion requires task, aligned-drift, observation, and fidelity evidence.", details={"procedure_id": record.procedure_id, "version": record.version})
        failed = tuple(result.validator_id for result in evidence.procedure_fidelity_results if result.required and not result.passed)
        if failed:
            raise ProcedurePromotionError("Required procedure-fidelity checks did not pass.", details={"failed_validator_ids": failed})
        authority.authorize(record, evidence)

    def _exact_record(self, reference: ProcedureRef) -> ProcedureRecord:
        # Reject fingerprint aliasing even when namespace/id/version happen to exist.
        record = self.store.get(reference.namespace, reference.procedure_id, reference.version)
        if record.content_fingerprint != reference.content_fingerprint:
            raise ProcedureVersionError("Procedure ref fingerprint does not match the stored version.", details={"procedure_id": reference.procedure_id, "version": reference.version})
        return record

    def _compatible(self, record: ProcedureRecord, environment_fingerprint: str, available_tools: Sequence[str]) -> bool:
        # Require an exact environment or generic record and a complete tool subset.
        requested_environment = environment_fingerprint.strip()
        if not requested_environment and record.environment_fingerprint:
            return False
        if requested_environment and record.environment_fingerprint not in {"", requested_environment}:
            return False
        return set(record.required_tools).issubset({str(tool).strip() for tool in available_tools})

    def _equivalent_active(self, namespace: str, fingerprint: str, *, exclude_id: str) -> ProcedureRecord | None:
        # Find reusable equivalent content already active under another stable identity.
        for record in self.active(namespace):
            if record.procedure_id != exclude_id and record.content_fingerprint == fingerprint:
                return record
        return None

    @staticmethod
    def _resolve_stage_replay(records: Sequence[ProcedureRecord], fingerprint: str) -> ProcedureRecord | None:
        # Accept byte-equivalent stage replay and reject operation-id content conflicts.
        if not records:
            return None
        candidates = tuple(record for record in records if record.status is ProcedureStatus.CANDIDATE)
        if candidates and all(record.content_fingerprint == fingerprint for record in records):
            return candidates[0]
        raise ProcedureStoreConflictError("Learning operation id was reused for different procedure content.", details={"operation_record_count": len(records)})

    def _resolve_terminal_replay(self, namespace: str, operation_id: str) -> ProcedureRecord | None:
        # Reconcile a previously applied terminal mutation after retry or resume.
        records = self.store.find_by_operation(namespace, operation_id)
        if not records:
            return None
        if len(records) == 1:
            return records[0]
        canonical = {ProcedureCodec.canonical_record(record) for record in records}
        if len(canonical) == 1:
            return records[0]
        raise ProcedureStoreConflictError("Terminal learning operation id resolved to conflicting records.", details={"operation_record_count": len(records)})

    def _validate_limits(self) -> None:
        # Fail construction when any candidate bound is non-positive or internally unsafe.
        values = (self.limits.max_title_chars, self.limits.max_summary_chars, self.limits.max_body_chars, self.limits.max_list_items, self.limits.max_list_item_chars)
        if any(value < 1 for value in values):
            raise ProcedureValidationError("Every ProcedureLimits value must be positive.")


__all__ = ["LexicalProcedureRanker", "ProcedureLibrary", "ProcedureRanker"]
