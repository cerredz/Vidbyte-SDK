"""FILE: tests/features/onboard_model_provider_skill/test_onboard_skill_acceptance.py

PURPOSE: Prove the person-facing promises of the /onboard-model-provider skill as SKILL.md states them: the invocation line, every pass, STOP, remedy and ledger line form of spec section 9.2, the three user stop conditions, the continue-on-disqualify rule, the rules a person relies on (one session at a time, never merge, never stash, never touch the checkout, closing unmerged skips forever), and what each outcome leaves behind.
ROLE IN CODEBASE: Acceptance layer of tests/features/onboard_model_provider_skill/ (spec AC-1 static half, AC-13, AC-15 positive half; INV-1, INV-7, INV-8; FR-13, FR-15; D-7, D-8, D-18; section 9.2).
ARCHITECTURE NOTE: The skill is Markdown an agent executes, so its acceptance surface is the text a person and the orchestrator read. Each test reads one SKILL.md section through MarkdownDoc and compares it with values spelled from spec r3 in onboard_skill_fixtures.py. The behavior half of AC-1 (running the read-only commands live) is PR-time evidence, never a committed test (spec section 13).
FUNCTION INVENTORY: test_skill_md_carries_the_invocation_as_a_line_of_its_own (A1); test_output_section_holds_every_pass_stop_remedy_and_ledger_line_form (A2); test_intro_names_the_three_user_stops_and_disqualified_vendors_are_skipped_not_stopped (A3); test_rules_section_states_the_promises_a_person_relies_on (A4); test_each_outcome_states_what_it_leaves_behind (A5).
COMMON MODIFICATION PATTERNS: When spec section 9.2 changes a line form, change OUTPUT_GRAMMAR in onboard_skill_fixtures.py, not the assertion here.
WHAT NOT TO DO IN THIS FILE: 1. Do not run the skill, Claude, git, gh or the network. 2. Do not compare against base_commit or a merge-base: these tests run inside every provider PR the skill opens (spec section 13, R-1).
KNOWN EDGE CASES: Lines are compared after collapsing whitespace, so a form may sit in a text fence, a list or a table cell. The rules checks look for one line holding both words, so a rule split across two bullets fails on purpose.
RELATED DOCS: tests/features/onboard_model_provider_skill/FEATURE.md; docs/spec/provider-onboarding-skill/spec.md r3 sections 4, 6.2 (AC-1, AC-13, AC-15), 8.1 (D-7, D-8), 9.2.
TESTS: python -m pytest tests/features/onboard_model_provider_skill/test_onboard_skill_acceptance.py -q
"""

from __future__ import annotations

import re

from tests.features.onboard_model_provider_skill.onboard_skill_fixtures import (
    OUTPUT_GRAMMAR,
    PROVIDER_OUTCOMES,
    SKILL_FILE,
    SKILL_REF,
    read_markdown,
)


def _lines_with_all(text: str, *patterns: str) -> list[str]:
    return [line for line in text.splitlines() if all(re.search(pattern, line, flags=re.IGNORECASE) for pattern in patterns)]


def test_skill_md_carries_the_invocation_as_a_line_of_its_own() -> None:
    # A1 · AC-1 (review r2-5): the command a person types appears as the single line `/onboard-model-provider`.
    skill = read_markdown(SKILL_FILE, SKILL_REF)

    assert [line for line in skill.lines if line.text.strip() == "/onboard-model-provider"], "SKILL.md must hold the invocation as the single line /onboard-model-provider (AC-1)"


def test_output_section_holds_every_pass_stop_remedy_and_ledger_line_form() -> None:
    # A2 · AC-1 / INV-1 / D-18 / section 9.2: a STOP form missing here is a stop the person and the PR-time run cannot parse.
    output = read_markdown(SKILL_FILE, SKILL_REF).section("## Output").squashed()

    missing = [form for form in OUTPUT_GRAMMAR if " ".join(form.split()) not in output]

    assert len(OUTPUT_GRAMMAR) == 12
    assert missing == [], f"## Output lacks these spec 9.2 line forms verbatim: {missing}"


def test_intro_names_the_three_user_stops_and_disqualified_vendors_are_skipped_not_stopped() -> None:
    # A3 · AC-13 / INV-7 / D-7: the user's three stops are named where a person starts reading, and a research-time
    # disqualification continues the loop instead of ending it (only a proof failure stops).
    skill = read_markdown(SKILL_FILE, SKILL_REF)
    intro = skill.section("## What one invocation does").squashed()

    assert [reason for reason in ("NO_CANDIDATE", "BACKPRESSURE", "PROOF_FAILED") if reason not in intro] == [], "## What one invocation does must name the three user stop conditions by their STOP reasons"
    assert re.search(r"\bcontinuous\b", intro, flags=re.IGNORECASE), "## What one invocation does must describe continuous mode"
    assert _lines_with_all(skill.text, r"\bDISQUALIFIED\b", r"continu"), "SKILL.md must say, on one line, that a DISQUALIFIED vendor is skipped and the loop continues"


def test_rules_section_states_the_promises_a_person_relies_on() -> None:
    # A4 · AC-13 / FR-15 / AC-15 / INV-8 / T-1: one session at a time, never merge, never stash, never touch the
    # launcher checkout, and closing a provider PR unmerged skips that vendor forever.
    rules = read_markdown(SKILL_FILE, SKILL_REF).section("## Rules").text

    assert re.search(r"one session at a time", " ".join(rules.split()), flags=re.IGNORECASE), "## Rules must tell the person to run one session at a time"
    assert _lines_with_all(rules, r"\bnever\b", r"\bmerge"), "## Rules must say the skill never merges"
    assert _lines_with_all(rules, r"\bnever\b", r"\bstash"), "## Rules must forbid stashing (phrased without the literal git command, AC-3)"
    assert _lines_with_all(rules, r"\bnever\b", r"\bcheckout\b"), "## Rules must say the launcher checkout is never touched"
    assert _lines_with_all(rules, r"\bclos", r"\bforever\b"), "## Rules must say closing a provider PR unmerged skips that vendor forever"


def test_each_outcome_states_what_it_leaves_behind() -> None:
    # A5 · AC-13 / D-8: verified results are cleaned up; PROOF_FAILED, PUBLISH_FAILED and RESULT_UNVERIFIED keep the
    # worktree, its evidence directory and the branch, so unpushed work is never destroyed.
    behind = read_markdown(SKILL_FILE, SKILL_REF).section("## What each outcome leaves behind").squashed()

    outcomes = (*PROVIDER_OUTCOMES, "RESULT_UNVERIFIED")
    assert [outcome for outcome in outcomes if not re.search(rf"\b{outcome}\b", behind)] == []
    assert re.search(r"\bgit(?:\s+-C\s+\S+)?\s+worktree\s+remove\s+--force\b", behind), "the cleanup must name `git worktree remove --force`"
    assert re.search(r"\bgit(?:\s+-C\s+\S+)?\s+branch\s+-D\b", behind), "the cleanup must name `git branch -D`"
    assert "-evidence" in behind, "D-8: the evidence directory is deleted with the worktree, or kept with it"
    assert re.search(r"\bkeep|\bkept\b", behind, flags=re.IGNORECASE), "D-8: the failing outcomes keep the worktree"
