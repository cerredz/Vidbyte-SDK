"""FILE: vidbyte/lib/jev/done/done.py

PURPOSE: Defines JevDoneRegistry, the registry over every done check's fixed question and threshold, plus validation of the done checks a user enables.
ROLE IN CODEBASE: JevContinualSettings calls JevDoneRegistry.validate at construction, and JevRunState (vidbyte/agents/jev/done/run_state.py) reads each enabled check's question and threshold from here when it asks Jev whether the main agent may finish.
ARCHITECTURE NOTE: Questions are dataclasses in this folder, the check vocabulary is JevDoneCheck in vidbyte/lib/enums/jev.py, and the records live in vidbyte/lib/dataclasses/jev.py; this lib module never imports the agents layer and never calls Jev.
COMMON MODIFICATION PATTERNS: Register a new done check by adding its question to _questions and its threshold constant to _thresholds; keep answer scoring in DecisionModelHelper and the actions taken on answers in JevRunState, not here.
KNOWN EDGE CASES: A bare string is rejected rather than iterated character by character, and enabling the same check twice is an error because it would ask Jev every question twice.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-report-action-alignment.md, skills/jev-agent/SKILL.md, skills/jev-continuation/SKILL.md, and skills/asking-jev-questions/SKILL.md.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-claims-done-criteria.md, docs/design/jev-target-outcome-done-check.md, skills/jev-agent/SKILL.md, skills/jev-continuation/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_done.py.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from vidbyte.lib.constants.jev import (
    JEV_CLAIMS_THRESHOLD,
    JEV_MULTI_PART_THRESHOLD,
    JEV_PROBLEMS_RESOLVED_THRESHOLD,
    JEV_REPORT_ACTION_ALIGNMENT_THRESHOLD,
    JEV_TARGET_OUTCOME_THRESHOLD,
)
from vidbyte.lib.dataclasses.jev import JevDoneQuestion
from vidbyte.lib.enums.jev import JevDoneCheck
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev.done.claims import ClaimsSupportedQuestion
from vidbyte.lib.jev.done.multi_part import MultiPartDeliveredQuestion
from vidbyte.lib.jev.done.problems_resolved import ProblemsResolvedQuestion
from vidbyte.lib.jev.done.report_action_alignment import ReportActionAlignmentQuestion
from vidbyte.lib.jev.done.target_outcome import TargetOutcomeDemonstratedQuestion


class JevDoneRegistry:
    """Registry over every done check's fixed question and the P(yes) every answer to it must reach."""

    _questions: Mapping[JevDoneCheck, JevDoneQuestion] = MappingProxyType({
        JevDoneCheck.MULTI_PART: MultiPartDeliveredQuestion(),
        JevDoneCheck.CLAIMS: ClaimsSupportedQuestion(),
        JevDoneCheck.REPORT_ACTION_ALIGNMENT: ReportActionAlignmentQuestion(),
        JevDoneCheck.TARGET_OUTCOME: TargetOutcomeDemonstratedQuestion(),
        JevDoneCheck.PROBLEMS_RESOLVED: ProblemsResolvedQuestion(),
    })
    _thresholds: Mapping[JevDoneCheck, float] = MappingProxyType({
        JevDoneCheck.MULTI_PART: JEV_MULTI_PART_THRESHOLD,
        JevDoneCheck.CLAIMS: JEV_CLAIMS_THRESHOLD,
        JevDoneCheck.REPORT_ACTION_ALIGNMENT: JEV_REPORT_ACTION_ALIGNMENT_THRESHOLD,
        JevDoneCheck.TARGET_OUTCOME: JEV_TARGET_OUTCOME_THRESHOLD,
        JevDoneCheck.PROBLEMS_RESOLVED: JEV_PROBLEMS_RESOLVED_THRESHOLD,
    })

    @classmethod
    def question(cls, check: JevDoneCheck) -> JevDoneQuestion:
        """Return the fixed question one done check asks about each item it checks."""
        found = cls._questions.get(check)
        if found is None:
            raise ConfigurationError(f"Jev done check {check!r} has no registered question.", details={"check": str(check), "registered": [item.value for item in cls._questions]})
        return found

    @classmethod
    def threshold(cls, check: JevDoneCheck) -> float:
        """Return the P(yes) every one of the check's answers must reach for the run to finish."""
        found = cls._thresholds.get(check)
        if found is None:
            raise ConfigurationError(f"Jev done check {check!r} has no registered threshold.", details={"check": str(check), "registered": [item.value for item in cls._thresholds]})
        return found

    @classmethod
    def resolve(cls, value: object) -> JevDoneCheck:
        """Convert one user-supplied check (enum member or its string value) to a JevDoneCheck."""
        try:
            return value if isinstance(value, JevDoneCheck) else JevDoneCheck(value)
        except ValueError as exc:
            raise ConfigurationError(
                f"Unsupported Jev done check: {value!r}.",
                details={"received": repr(value), "available": [item.value for item in JevDoneCheck]},
            ) from exc

    @classmethod
    def validate(cls, values: Iterable[object]) -> tuple[JevDoneCheck, ...]:
        """Convert the user's enabled done checks to a tuple of unique checks, each with a registered question and threshold."""
        # @intent done-checks-fail-before-any-jev-call
        # Settings construction calls this, so a typo, a bare string, or a repeated check fails when the
        # agent is built instead of silently asking Jev the wrong (or duplicated) questions at every finish.
        if isinstance(values, (str, bytes)):
            raise ConfigurationError("JevContinualSettings.checks must be an iterable of Jev done checks, not a string.", details={"received": repr(values)})
        try:
            checks = tuple(cls.resolve(value) for value in values)
        except TypeError as exc:
            raise ConfigurationError("JevContinualSettings.checks must be an iterable of Jev done checks.", details={"received": type(values).__name__}) from exc
        if len(set(checks)) != len(checks):
            raise ConfigurationError("JevContinualSettings.checks cannot enable the same check twice.", details={"received": [check.value for check in checks]})
        for check in checks:
            cls.question(check)
            cls.threshold(check)
        return checks


__all__ = ["JevDoneRegistry"]
