"""FILE: vidbyte/agents/codex/failures.py

PURPOSE: Converts Codex adapter errors into canonical Vidbyte failure records.
ROLE IN CODEBASE: agent.py records every failed attempt here; the fallback coordinator
    reads the retry class to decide whether another model could survive the failure.
ARCHITECTURE NOTE: Classification is a table in vidbyte/lib/constants/codex.py, not a
    branch chain, so the supported vocabulary is inspectable and a missing row is loud.
FUNCTION INVENTORY: CodexFailureTranslator.translate(request) builds one record;
    CodexFailureLedger holds the bounded per-turn history the agent exposes.
COMMON MODIFICATION PATTERNS: Add a codex.* code to the classification table, then to
    the coverage test that iterates FailureCode; never widen a default here instead.
WHAT NOT TO DO IN THIS FILE: Do not classify a non-CodexAgentError (inventing a
    classification for an arbitrary exception is the dishonesty this avoids), do not
    default an unknown code to retryable, and do not build details without FailureSafety.
KNOWN EDGE CASES: An unclassified code reports TERMINAL/CRITICAL so one omission cannot
    spend a whole fallback chain; a recovered failure is still recorded, not discarded.
RELATED DOCS: docs/design/codex-failure-recovery.md
TESTS: tests/test_codex_failure_recovery.py; python scripts/run_ci.py.
"""

from __future__ import annotations

from typing import Any

from vidbyte.lib.constants.codex import (
    CODEX_FAILURE_CLASSIFICATION,
    CODEX_FAILURE_SOURCE,
    CODEX_MAX_TURN_FAILURES,
)
from vidbyte.lib.dataclasses.codex import (
    CodexFailureRecord,
    CodexFailureTranslationRequest,
)
from vidbyte.lib.dataclasses.failure import Failure, FailureSafety
from vidbyte.lib.enums.codex import CodexFailureClass
from vidbyte.lib.enums.failure import (
    FailureDisposition,
    FailurePhase,
    FailureSeverity,
)

_UNCLASSIFIED_RULE = (
    CodexFailureClass.TERMINAL.value,
    FailurePhase.UNKNOWN.value,
    FailureSeverity.CRITICAL.value,
    FailureDisposition.RAISE.value,
)


class CodexFailureTranslator:
    """Converts Codex adapter errors into canonical Vidbyte failure records."""

    @classmethod
    def translate(cls, request: CodexFailureTranslationRequest) -> CodexFailureRecord:
        # @intent classify-before-deciding-whether-to-retry
        # A fallback chain that cannot tell a rate limit from a missing SDK extra
        # will retry the unretryable and burn a second turn to fail identically.
        error = request.error
        failure_class, phase, severity, disposition = cls._rule(error.failure_code)
        failure = Failure(
            code=error.failure_code,
            source=CODEX_FAILURE_SOURCE,
            phase=phase,
            severity=severity,
            disposition=disposition,
            summary=str(error),
            details=cls._details(request),
        )
        return CodexFailureRecord(
            failure=failure, failure_class=CodexFailureClass(failure_class)
        )

    @staticmethod
    def _rule(code: str) -> tuple[str, str, str, str]:
        # An unknown code is terminal on purpose: defaulting to retryable would let
        # one missing table row spend the whole chain on every future failure.
        return CODEX_FAILURE_CLASSIFICATION.get(code, _UNCLASSIFIED_RULE)

    @staticmethod
    def _details(request: CodexFailureTranslationRequest) -> dict[str, Any]:
        # @intent bounded-credential-free-diagnostics
        # Details are model-facing, so every value routes through FailureSafety.
        # Attempt and chain index are what make three failed attempts legible as one
        # recovered turn rather than three unrelated failures.
        error = request.error
        return FailureSafety.sanitize_mapping(
            {
                "operation": error.operation,
                "error_type": type(error.__cause__).__name__
                if error.__cause__ is not None
                else "",
                "attempt": request.attempt,
                "chain_index": request.chain_index,
                "classified": error.failure_code in CODEX_FAILURE_CLASSIFICATION,
            }
        )


class CodexFailureLedger:
    """Bounded per-turn record of the failures one agent observed."""

    def __init__(self) -> None:
        # One ledger per agent, reset each turn, mirroring the UsageTracker lifecycle.
        self._records: list[CodexFailureRecord] = []

    def reset(self) -> None:
        """Clear the ledger at the start of a turn."""
        self._records.clear()

    def record(self, record: CodexFailureRecord) -> CodexFailureRecord:
        """Append one classified failure, keeping the most recent within the bound."""
        self._records.append(record)
        del self._records[:-CODEX_MAX_TURN_FAILURES]
        return record

    @property
    def failures(self) -> tuple[Failure, ...]:
        """Return the canonical failure records for the current or most recent turn."""
        return tuple(record.failure for record in self._records)

    @property
    def records(self) -> tuple[CodexFailureRecord, ...]:
        """Return the classified records, including each failure's retry class."""
        return tuple(self._records)


__all__ = ["CodexFailureLedger", "CodexFailureTranslator"]
