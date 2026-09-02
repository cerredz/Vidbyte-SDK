"""Context Protocol Header

Description:
    Reduces accepted worker reports into immutable TaskRecord replacements.
Purpose:
    Keeps report-status branching and evidence/blocker merging outside TaskLedger commits.
Architecture:
    TaskLedgerReportReducer dispatches terminal statuses to focused transition methods.
Relations:
    Constructed and used only by TaskLedger.apply_report.
"""

from __future__ import annotations

from dataclasses import replace

from vidbyte.lib.dataclasses.multi_agent import AgentReport, TaskBlocker, TaskEvidence, TaskRecord
from vidbyte.lib.enums.multi_agent import TaskStatus


class TaskLedgerReportReducer:
    """Build one terminal task record from an accepted worker report."""

    def apply(self, record: TaskRecord, report: AgentReport) -> tuple[TaskRecord, bool]:
        # Dataclass validation guarantees exactly one of these terminal status handlers exists.
        handlers = {TaskStatus.COMPLETED: self._complete, TaskStatus.FAILED: self._fail, TaskStatus.BLOCKED: self._block}
        return handlers[report.status](record, report)

    def _complete(self, record: TaskRecord, report: AgentReport) -> tuple[TaskRecord, bool]:
        # Completion retains only non-retryable blockers and always counts as progress.
        evidence = self._merge_evidence(record.evidence, report.evidence)
        existing = tuple(blocker for blocker in record.blockers if not blocker.retryable)
        incoming = tuple(blocker for blocker in report.blockers if not blocker.retryable)
        updated = replace(record, status=TaskStatus.COMPLETED, result=report.result, evidence=evidence, blockers=self._merge_blockers(existing, incoming), next_action=report.next_action)
        return updated, True

    def _fail(self, record: TaskRecord, report: AgentReport) -> tuple[TaskRecord, bool]:
        # Exhausted failures become blocked so the manager must change the plan.
        status = TaskStatus.FAILED if record.attempts < record.max_attempts else TaskStatus.BLOCKED
        return self._terminal(record, report, status)

    def _block(self, record: TaskRecord, report: AgentReport) -> tuple[TaskRecord, bool]:
        # Explicit blockers close the attempt without another retry decision.
        return self._terminal(record, report, TaskStatus.BLOCKED)

    def _terminal(self, record: TaskRecord, report: AgentReport, status: TaskStatus) -> tuple[TaskRecord, bool]:
        # Failed and blocked reports share evidence, blocker, and next-action merging.
        evidence = self._merge_evidence(record.evidence, report.evidence)
        blockers = self._merge_blockers(record.blockers, report.blockers)
        updated = replace(record, status=status, result=report.result, evidence=evidence, blockers=blockers, next_action=report.next_action)
        progress = len(evidence) > len(record.evidence) or len(blockers) > len(record.blockers) or report.next_action != record.next_action
        return updated, progress

    def _merge_evidence(self, existing: tuple[TaskEvidence, ...], incoming: tuple[TaskEvidence, ...]) -> tuple[TaskEvidence, ...]:
        # Deduplicate only when equality is safely decidable as a plain boolean.
        merged = list(existing)
        for candidate in incoming:
            if not any(self._evidence_matches(item, candidate) for item in merged):
                merged.append(candidate)
        return tuple(merged)

    def _evidence_matches(self, left: TaskEvidence, right: TaskEvidence) -> bool:
        # Arbitrary evidence values may raise or return array-like equality results.
        if (left.source, left.kind, left.verified) != (right.source, right.kind, right.verified):
            return False
        try:
            equal = left.value == right.value
        except Exception:
            return False
        return equal if isinstance(equal, bool) else False

    def _merge_blockers(self, existing: tuple[TaskBlocker, ...], incoming: tuple[TaskBlocker, ...]) -> tuple[TaskBlocker, ...]:
        # Retain one safe control record per code/message/retryability identity.
        merged = list(existing)
        seen = {(item.code, item.message, item.retryable) for item in merged}
        for blocker in incoming:
            key = (blocker.code, blocker.message, blocker.retryable)
            if key not in seen:
                merged.append(blocker)
                seen.add(key)
        return tuple(merged)


__all__ = ["TaskLedgerReportReducer"]
