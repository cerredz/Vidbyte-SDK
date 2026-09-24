"""FILE: vidbyte/agents/jev/scope_coverage/questions.py

PURPOSE: Builds the three fixed Jev recognition requests of the scope-coverage done check and the minimal state each one sees.
ROLE IN CODEBASE: ScopeBreadthReview asks the breadth question; ScopeCoverageDoneCheck asks the unit-coverage and coverage-statement questions.
ARCHITECTURE NOTE: Instructions are prompt assets; option rubrics (what / not_for / examples) live here beside the options they describe.
COMMON MODIFICATION PATTERNS: Keep each question a single recognition step per skills/asking-jev-questions/SKILL.md; move counting and combining to code.
KNOWN EDGE CASES: Each state holds only the named fields its question needs; user text never sits beside the rules.
RELATED DOCS: docs/design/jev-scope-coverage-done-criteria.md and skills/asking-jev-questions/SKILL.md.
TESTS: tests/test_jev_agent.py.
"""

from __future__ import annotations

from vidbyte.agents.jev.scope_coverage.enums import JevScopeBreadth
from vidbyte.agents.jev.scope_coverage.handoff import JevScopeUnitRecord
from vidbyte.agents.jev.scope_coverage.state import JevScopeDimension
from vidbyte.lib.dataclasses.jev import JevDecisionRequest, JevOption, JevQuestion
from vidbyte.lib.enums import JevQuestionType
from vidbyte.lib.enums.prompts import Prompt
from vidbyte.prompts.catalog import Prompts

SCOPE_BREADTH_QUESTION: str = "scope_breadth"
UNIT_COVERAGE_QUESTION: str = "unit_coverage"
COVERAGE_STATEMENT_QUESTION: str = "coverage_statement"

UNIT_APPLIED: str = "applied"
UNIT_ATTEMPTED: str = "attempted"
UNIT_EXAMINED_ONLY: str = "examined_only"
UNIT_NONE: str = "none"

STATEMENT_CLAIMS_ALL: str = "claims_all"
STATEMENT_REPORTS_PARTIAL: str = "reports_partial"
STATEMENT_SILENT: str = "silent"


class ScopeCoverageQuestions:
    """Builds one-question Jev requests over the smallest state that answers each one."""

    @staticmethod
    def breadth_request(dimension: JevScopeDimension) -> JevDecisionRequest:
        """Ask how much of the group the request wording asks the change to reach."""
        # @intent breadth-state-is-quote-only
        # Jev sees only the quote and the unit noun, never the full request, so surrounding user text cannot argue for a label.
        question = JevQuestion(
            name=SCOPE_BREADTH_QUESTION,
            question_type=JevQuestionType.CHOICE,
            instructions=Prompts().get(Prompt.JEV_SCOPE_BREADTH),
            options=(
                JevOption(JevScopeBreadth.EVERY_MEMBER.value, {"what": "The change must reach the whole group.", "not_for": "A request that names its members one by one.", "examples": ["add CSV export to all our model providers", "fix the typo in every README"]}),
                JevOption(JevScopeBreadth.NAMED_LIST.value, {"what": "The request spells out two or more specific members.", "not_for": "A whole group described without naming its members.", "examples": ["support the web, CLI, and API", "update the OpenAI and Anthropic adapters"]}),
                JevOption(JevScopeBreadth.ONE_EXAMPLE.value, {"what": "One sample or starting member is enough.", "not_for": "A request that asks for the whole group.", "examples": ["show an example provider", "start with one endpoint"]}),
                JevOption(JevScopeBreadth.SINGLE_TARGET.value, {"what": "Exactly one named item is to change.", "not_for": "A request that names several items.", "examples": ["fix login.py", "rename the billing table"]}),
            ),
        )
        return JevDecisionRequest(state={"request_quote": dimension.request_quote, "unit_noun": dimension.unit_noun}, questions=(question,))

    @staticmethod
    def unit_request(dimension: JevScopeDimension, record: JevScopeUnitRecord) -> JevDecisionRequest:
        """Ask how far the cited work on one unit carries out the requested change."""
        # @intent one-unit-per-request
        # The state holds one unit and its own cited work; adding other units or the run would turn recognition into cross-unit reasoning.
        question = JevQuestion(
            name=UNIT_COVERAGE_QUESTION,
            question_type=JevQuestionType.CHOICE,
            instructions=Prompts().get(Prompt.JEV_SCOPE_UNIT_COVERAGE),
            options=(
                JevOption(UNIT_APPLIED, {"what": "A write, edit, or successful result for `unit` that makes `requested_change`.", "not_for": "A plan, a read, a listing, or a note that `unit` follows the same pattern.", "examples": ["wrote csv_export() into providers/anthropic.py", "tests for the anthropic export passed"]}),
                JevOption(UNIT_ATTEMPTED, {"what": "An edit or command for `unit` that failed, was reverted, or was left partway.", "not_for": "Reading or listing `unit` without trying to change it.", "examples": ["edit to anthropic.py failed: file not found", "started the anthropic change, then stopped"]}),
                JevOption(UNIT_EXAMINED_ONLY, {"what": "`unit` was read, listed, searched, or discussed, with no change made.", "not_for": "Any write or edit that makes the change.", "examples": ["read providers/anthropic.py", "anthropic follows the same pattern as openai"]}),
                JevOption(UNIT_NONE, {"what": "Nothing in `work_record` concerns `unit`.", "not_for": "Any action that names `unit`.", "examples": ["only openai.py was edited"]}),
            ),
        )
        state = {
            "requested_change": dimension.requested_change,
            "unit_noun": dimension.unit_noun,
            "unit": record.unit,
            "work_record": [item.to_payload() for item in record.work],
        }
        return JevDecisionRequest(state=state, questions=(question,))

    @staticmethod
    def statement_request(dimension: JevScopeDimension, final_answer: str) -> JevDecisionRequest:
        """Ask what the final answer tells the user about how much of the group changed."""
        # @intent final-answer-is-the-only-disclosure
        # Disclosure is judged from the final answer alone because that is what the user reads; earlier narration does not count as telling the user.
        question = JevQuestion(
            name=COVERAGE_STATEMENT_QUESTION,
            question_type=JevQuestionType.CHOICE,
            instructions=Prompts().get(Prompt.JEV_SCOPE_COVERAGE_STATEMENT),
            options=(
                JevOption(STATEMENT_CLAIMS_ALL, {"what": "Says every member, all of them, or the whole group was changed.", "not_for": "An answer that also says some members were not done.", "examples": ["Added CSV export to all providers.", "Every endpoint now validates input."]}),
                JevOption(STATEMENT_REPORTS_PARTIAL, {"what": "Tells the user some members are not done, or names what is left.", "not_for": "An answer that only lists what was done.", "examples": ["OpenAI is done; Anthropic and Gemini still need the change.", "I only updated the web client so far."]}),
                JevOption(STATEMENT_SILENT, {"what": "Describes what was done without saying anything about the rest of the group.", "not_for": "An answer that claims all or reports what is left.", "examples": ["Added CSV export to the OpenAI provider."]}),
            ),
        )
        state = {"request_quote": dimension.request_quote, "unit_noun": dimension.unit_noun, "final_answer": final_answer or "(empty final answer)"}
        return JevDecisionRequest(state=state, questions=(question,))


__all__ = [
    "COVERAGE_STATEMENT_QUESTION",
    "SCOPE_BREADTH_QUESTION",
    "STATEMENT_CLAIMS_ALL",
    "STATEMENT_REPORTS_PARTIAL",
    "STATEMENT_SILENT",
    "UNIT_APPLIED",
    "UNIT_ATTEMPTED",
    "UNIT_COVERAGE_QUESTION",
    "UNIT_EXAMINED_ONLY",
    "UNIT_NONE",
    "ScopeCoverageQuestions",
]
