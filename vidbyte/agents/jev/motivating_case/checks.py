"""FILE: vidbyte/agents/jev/motivating_case/checks.py

PURPOSE: Verifies handoff refs and quotes against the event ledger and computes the exact facts Jev must not judge.
ROLE IN CODEBASE: MotivatingCasePolicy calls ScenarioEvidenceChecker once per scenario before building any Jev question.
ARCHITECTURE NOTE: Ordering, success, staleness, and verbatim matching are code; only verified excerpts ever reach Jev.
COMMON MODIFICATION PATTERNS: Add a fact here, use it in MotivatingCasePolicy's combination, and pin it with a labeled test.
KNOWN EDGE CASES: A fabricated ref or non-verbatim quote silently drops that evidence pair; the literal-input recovery can still find a setup the builder forgot to link.
RELATED DOCS: docs/design/jev-motivating-case.md.
TESTS: tests/test_jev_motivating_case.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from vidbyte.agents.jev.motivating_case.evidence import RunEvent, RunEventLedger
from vidbyte.agents.jev.motivating_case.handoff import ScenarioExercise
from vidbyte.agents.jev.motivating_case.state import MotivatingScenario, VerbatimText
from vidbyte.lib.constants.jev import (
    JEV_MOTIVATING_CASE_EXCERPT_CHARS,
    JEV_MOTIVATING_CASE_LITERAL_WINDOW_CHARS,
)
from vidbyte.lib.dataclasses.tools import ToolPermission


@dataclass(frozen=True, slots=True)
class ScenarioEvidence:
    """Verified excerpts and code-computed facts for one scenario at one finish attempt."""

    scenario_id: str
    setup_excerpt: str | None = None
    setup_event_id: str | None = None
    outcome_excerpt: str | None = None
    outcome_event_id: str | None = None
    case_name: str | None = None
    inspection_excerpt: str | None = None
    blocker_excerpt: str | None = None
    run_ok: bool = False
    stale: bool = False
    recovered_by_literal: bool = False

    def facts(self) -> dict[str, object]:
        # Returns the code facts for metadata and debugging; Jev never receives these.
        return {
            "setup_event": self.setup_event_id,
            "outcome_event": self.outcome_event_id,
            "run_ok": self.run_ok,
            "stale": self.stale,
            "recovered_by_literal": self.recovered_by_literal,
        }


class ScenarioEvidenceChecker:
    """Resolves one scenario's handoff claims into verified evidence."""

    def __init__(self, ledger: RunEventLedger) -> None:
        # Binds the finish attempt's immutable event ledger.
        self._ledger = ledger

    def check(self, scenario: MotivatingScenario, exercise: ScenarioExercise) -> ScenarioEvidence:
        # Verifies each claimed ref/quote pair, recovers a setup from literal inputs, then computes run facts.
        # @intent evidence-verified-before-jev
        # Only pairs that survive ref, permission, and verbatim checks reach Jev, so the generative handoff can point but never assert.
        setup = self._verified(exercise.setup_ref, exercise.setup_quote, (ToolPermission.WRITE, ToolPermission.EXECUTE, ToolPermission.READ))
        outcome = self._verified(exercise.outcome_ref, exercise.outcome_quote, (ToolPermission.EXECUTE,))
        recovered = False
        if setup is None:
            setup = self._recover_setup(scenario)
            recovered = setup is not None
        if outcome is None and setup is not None and setup[0].permission is ToolPermission.EXECUTE:
            # An executed setup, such as an inline script with the empty input, is its own outcome.
            outcome = (setup[0], self._tail(setup[0].output))
        case_name = self._verified_case_name(exercise.case_name, setup, outcome)
        run_ok, stale = self._run_facts(setup, outcome, case_name)
        inspection = self._verified(exercise.inspection_ref, exercise.inspection_quote, (ToolPermission.READ, ToolPermission.WRITE))
        blocker = self._verified(exercise.blocker_ref, exercise.blocker_quote, None)
        return ScenarioEvidence(
            scenario_id=scenario.id,
            setup_excerpt=setup[1] if setup else None,
            setup_event_id=setup[0].event_id if setup else None,
            outcome_excerpt=outcome[1] if outcome else None,
            outcome_event_id=outcome[0].event_id if outcome else None,
            case_name=case_name,
            inspection_excerpt=inspection[1] if inspection else None,
            blocker_excerpt=blocker[1] if blocker else None,
            run_ok=run_ok,
            stale=stale,
            recovered_by_literal=recovered,
        )

    def _verified(self, ref: str | None, quote: str | None, permissions: tuple[ToolPermission, ...] | None) -> tuple[RunEvent, str] | None:
        # Keeps a ref/quote pair only when the event exists, has an allowed permission, and contains the quote verbatim.
        # @intent permission-decides-event-role
        # The tool's declared permission, not its name or the builder's claim, decides whether an event can be a run, a setup, or an inspection.
        event = self._ledger.get(ref)
        if event is None or not quote:
            return None
        if permissions is not None and event.permission not in permissions:
            return None
        if not RunEventLedger.quote_is_verbatim(event, quote):
            return None
        return event, quote

    def _recover_setup(self, scenario: MotivatingScenario) -> tuple[RunEvent, str] | None:
        # Finds a setup the builder did not link by searching for the user's exact values, and cuts an excerpt around it.
        match = self._ledger.first_literal_match(scenario.literal_inputs)
        if match is None:
            return None
        event, literal = match
        text = event.searchable_text()
        position = text.find(literal)
        start = max(0, position - JEV_MOTIVATING_CASE_LITERAL_WINDOW_CHARS)
        end = min(len(text), position + len(literal) + JEV_MOTIVATING_CASE_LITERAL_WINDOW_CHARS)
        return event, text[start:end]

    @staticmethod
    def _verified_case_name(case_name: str | None, setup: tuple[RunEvent, str] | None, outcome: tuple[RunEvent, str] | None) -> str | None:
        # Keeps the test name only when it literally appears in the setup or outcome event.
        if not case_name:
            return None
        for pair in (setup, outcome):
            if pair is not None and case_name in pair[0].searchable_text():
                return case_name
        return None

    def _run_facts(self, setup: tuple[RunEvent, str] | None, outcome: tuple[RunEvent, str] | None, case_name: str | None) -> tuple[bool, bool]:
        # Decides in code whether the outcome is a successful, ordered, covering, and current run of the setup.
        if setup is None or outcome is None:
            return False, False
        setup_event, outcome_event = setup[0], outcome[0]
        stale = self._ledger.has_write_after(outcome_event.index)
        ordered = outcome_event.index >= setup_event.index
        run_ok = outcome_event.succeeded() and ordered and self._covers(setup_event, outcome_event, case_name) and not stale
        return run_ok, stale

    @staticmethod
    def _covers(setup_event: RunEvent, outcome_event: RunEvent, case_name: str | None) -> bool:
        # An outcome covers the setup when it is the same event, names the case or a setup file, or runs a whole suite.
        if setup_event.event_id == outcome_event.event_id:
            return True
        outcome_text = outcome_event.searchable_text()
        if case_name and case_name in outcome_text:
            return True
        if any(VerbatimText.contains(outcome_text, path) for path in setup_event.paths()):
            return True
        return outcome_event.selects_no_file()

    @staticmethod
    def _tail(text: str) -> str:
        # Keeps the end of an output, where runners report results; an empty output is shown as such to Jev.
        return text[-JEV_MOTIVATING_CASE_EXCERPT_CHARS:] if text.strip() else "(the command produced no output)"


__all__ = ["ScenarioEvidence", "ScenarioEvidenceChecker"]
