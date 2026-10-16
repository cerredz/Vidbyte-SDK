"""FILE: tests/features/onboard_model_provider_skill/test_onboard_skill_contract.py

PURPOSE: Pin the fixed interfaces of the /onboard-model-provider skill that spec r3 section 8.5 names as the contract: the frontmatter and size limits, the two-file folder, the H2 headings of both files, the constants, the seed table and its first-party hosts, the subagent brief, the PROVIDER RESULT block on both sides, every enumeration, the four result checks, the PR title and body rules, and the regenerated REPO_MAP.md entry for .claude/.
ROLE IN CODEBASE: Contract layer of tests/features/onboard_model_provider_skill/ (spec AC-2, AC-5, AC-6, AC-7, AC-9; INV-9, INV-22; FR-6, FR-11, FR-16, FR-17; D-1, D-2, D-16, D-17, D-19, D-22, D-23, D-28; sections 8.4, 8.5, 9.1, 12.3 rows 2 and 3).
ARCHITECTURE NOTE: The orchestrator (SKILL.md) and the provider subagent (references/provider-run.md) talk only through the brief and the PROVIDER RESULT block, so those are checked from both sides. Seed rows are parsed as a GFM table; the URL check is the security property (T-5, T-6), not a copy of the URLs.
FUNCTION INVENTORY: test_frontmatter_has_only_name_description_and_manual_only_invocation (C1); test_skill_folder_holds_exactly_the_two_markdown_files (C12); test_h2_headings_are_exactly_the_spec_list_in_order (C2); test_constants_section_states_every_named_constant (C3); test_seed_table_lists_the_ten_vendors_in_rank_order_without_researched_facts (C4); test_every_seed_url_is_on_its_rows_first_party_hosts (C5); test_subagent_brief_carries_every_field_and_rule (C6); test_result_block_is_produced_and_read_with_the_same_fields_and_outcomes (C7); test_each_enumeration_is_named_in_full_where_it_is_decided (C8); test_verifying_a_result_runs_the_four_checks_without_a_copy_of_the_checklist (C9); test_publish_uses_the_pr_title_body_rules_and_quote_cap (C10); test_repo_map_claude_entry_describes_review_settings_and_invoked_skills (C11).
COMMON MODIFICATION PATTERNS: When spec section 8.5 or 9.1 changes a heading, constant, enumeration or seed slug, change onboard_skill_fixtures.py; keep the assertions here.
WHAT NOT TO DO IN THIS FILE: 1. Do not assert that a seed slug is not a ModelProvider member: it becomes one on the first provider branch. 2. Do not pin seed display names, URLs or reasons; vendors move pages and a reviewed seed edit must not need a second edit here. 3. Do not read git state.
KNOWN EDGE CASES: The frontmatter is parsed with yaml.safe_load, so the string "true" is not the boolean the flag needs. Enumeration members are matched with hyphen-aware boundaries, so "merged" is not satisfied by "closed-unmerged" and "member" not by "members". REPO_MAP sentences are split at a period followed by a capital letter.
RELATED DOCS: tests/features/onboard_model_provider_skill/FEATURE.md; docs/spec/provider-onboarding-skill/spec.md r3 sections 6.2, 8.1, 8.5, 9.1, 9.2, 10, 12.3.
TESTS: python -m pytest tests/features/onboard_model_provider_skill/test_onboard_skill_contract.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from tests.features.onboard_model_provider_skill.onboard_skill_fixtures import (
    CONSTANTS,
    DISQUALIFICATION_REASONS,
    EXCLUDED_VENDOR_NAMES,
    PREREQ_NAMES,
    PROCEDURE_FILE,
    PROCEDURE_HEADINGS,
    PROCEDURE_REF,
    PROOF_CHECKS,
    PROVIDER_OUTCOMES,
    REPO_MAP_FILE,
    SEED_HEADER,
    SEED_VENDORS,
    SKILL_DIR,
    SKILL_FILE,
    SKILL_HEADINGS,
    SKILL_REF,
    SKIP_DISPOSITIONS,
    UNVERIFIED_CHECKS,
    WIRING_HEADER,
    read_markdown,
    split_row,
)

# Model IDs and fragments the spec's own seed research cites; none may be baked into a seed row (AC-6, section 9.1).
KNOWN_MODEL_ID_FRAGMENTS = ("gpt-oss", "qwen3", "qwen/", "jamba-mini", "jamba-large", "meta-llama/", "deepseek-ai/", "solar-pro", "accounts/fireworks", "openai/")
KNOWN_KEY_PREFIXES = ("sk-", "csk-", "gsk_", "eyJ", "LLM|", "xai-")


def _enumerated(name: str, text: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text) is not None


def test_frontmatter_has_only_name_description_and_manual_only_invocation() -> None:
    # C1 · AC-2 / INV-22 / D-17 / Q-7: exactly three keys; the flag is the YAML boolean true, so Claude never loads
    # this PR-opening skill by itself; no arguments; under 500 lines; the title follows the frontmatter.
    read_markdown(SKILL_FILE, SKILL_REF)
    lines = SKILL_FILE.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "---", "SKILL.md must open with a YAML frontmatter block"
    end = next((index for index in range(1, len(lines)) if lines[index] == "---"), None)
    assert end is not None, "SKILL.md frontmatter is never closed with ---"
    frontmatter = yaml.safe_load("\n".join(lines[1:end]))

    assert isinstance(frontmatter, dict)
    assert sorted(frontmatter) == ["description", "disable-model-invocation", "name"]
    assert frontmatter["name"] == "onboard-model-provider"
    assert frontmatter["disable-model-invocation"] is True
    description = frontmatter["description"]
    assert isinstance(description, str) and description.strip(), "description must be non-empty text"
    assert len(description) <= 1_536, f"description is {len(description)} characters; Claude Code truncates the listing at 1,536"
    assert len(lines) < 500, f"SKILL.md has {len(lines)} lines; spec AC-2 requires fewer than 500"
    assert next(line for line in lines[end + 1 :] if line.strip()) == "# Onboard model providers continuously"
    assert "$ARGUMENTS" not in "\n".join(lines), "the skill takes no arguments (FR-1, INV-22)"


def test_skill_folder_holds_exactly_the_two_markdown_files() -> None:
    # C12 · D-1 / NG-5 / section 8.4: a helper script or a README would bring A001, S062, A009 and S020 into scope.
    files = sorted(path.relative_to(SKILL_DIR).as_posix() for path in SKILL_DIR.rglob("*") if path.is_file())

    assert files == ["SKILL.md", "references/provider-run.md"]


@pytest.mark.parametrize(("path", "spec_ref", "expected"), [(SKILL_FILE, SKILL_REF, SKILL_HEADINGS), (PROCEDURE_FILE, PROCEDURE_REF, PROCEDURE_HEADINGS)], ids=["SKILL.md", "provider-run.md"])
def test_h2_headings_are_exactly_the_spec_list_in_order(path: Path, spec_ref: str, expected: tuple[str, ...]) -> None:
    # C2 · AC-5 / AC-7: the headings are the stable anchors the brief, the result checks and these tests use.
    assert read_markdown(path, spec_ref).h2_headings() == list(expected)


def test_constants_section_states_every_named_constant() -> None:
    # C3 · section 8.5 "names are the contract": back-pressure 3, at most 5 catalogued models, the fixed repo and paths.
    constants = read_markdown(SKILL_FILE, SKILL_REF).section("## Constants").squashed()

    missing = [f"{name}={value}" for name, value in CONSTANTS if not re.search(rf"(?<![\w]){name}\s*=\s*{re.escape(value)}(?![\w])", constants)]
    assert missing == [], f"## Constants must state each spec 8.5 constant as NAME=value: {missing}"
    assert "git rev-parse --show-toplevel" in constants, "<checkout> is defined by `git rev-parse --show-toplevel` (section 8.5)"


def _researched_facts(row: list[str]) -> list[str]:
    # Prices, model IDs, base URLs and key prefixes are researched fresh every run, so a seed row may hold none.
    found = [f"price {cell!r}" for cell in row if re.search(r"\$\s*\d", cell)]
    prose = " ".join(row[:5] + row[7:])
    found += [f"model ID {fragment!r}" for fragment in KNOWN_MODEL_ID_FRAGMENTS if fragment.lower() in prose.lower()]
    found += [f"model ID {token!r}" for token in re.findall(r"(?<![\w/.-])[A-Za-z][A-Za-z0-9.-]{3,}/[A-Za-z0-9.-]*\d[A-Za-z0-9.-]*", re.sub(r"https?://\S+", " ", prose))]
    spans = re.findall(r"`([^`]+)`", " ".join(row))
    found += [f"key prefix {span!r}" for span in spans if span in KNOWN_KEY_PREFIXES or re.fullmatch(r"[A-Za-z0-9]{1,8}[-_|]", span)]
    found += ["a URL in Reason"] if "://" in row[7] else []
    return found


def test_seed_table_lists_the_ten_vendors_in_rank_order_without_researched_facts() -> None:
    # C4 · AC-6 / FR-17 / section 9.1: exactly the ten seed vendors, walked in rank order, carrying no price, model ID,
    # base URL or key prefix; each reason is dated; the four excluded vendors are named with their reasons.
    skill = read_markdown(SKILL_FILE, SKILL_REF)
    rows = [split_row(line) for line in skill.section("## Seed vendors").table_rows(SEED_HEADER)]

    assert len(rows) == 10, f"the seed table has {len(rows)} rows; spec 9.1 lists 10"
    assert [len(row) for row in rows] == [8] * 10
    assert [(row[0], row[2]) for row in rows] == list(SEED_VENDORS)
    assert [row[1] for row in rows] == [str(rank) for rank in range(1, 11)]
    assert all(re.fullmatch(r"[a-z0-9]+", row[0]) and re.fullmatch(r"[A-Z][A-Z0-9_]*", row[2]) for row in rows)
    assert all(row[3].strip() for row in rows), "every seed row needs a display name (PR title, D-16)"
    assert [row[0] for row in rows if not re.search(r"\b20\d\d-\d\d-\d\d\b", row[7])] == [], "every Reason carries the date it was verified (section 9.1)"
    assert {row[0]: facts for row in rows if (facts := _researched_facts(row))} == {}
    excluded = skill.section("## Excluded vendors").squashed()
    assert [name for name in EXCLUDED_VENDOR_NAMES if name not in excluded] == []


def test_every_seed_url_is_on_its_rows_first_party_hosts() -> None:
    # C5 · D-19 / T-5 / T-6 / EC-53: first-party means the row's pinned hosts and their subdomains, so a docs or pricing
    # URL off those hosts is either a page the run must refuse or an attacker's page the run would trust.
    rows = [split_row(line) for line in read_markdown(SKILL_FILE, SKILL_REF).section("## Seed vendors").table_rows(SEED_HEADER)]
    assert len(rows) == 10

    off_host = []
    for row in rows:
        hosts = [host.strip() for host in row[4].split(",")]
        assert all(re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", host) for host in hosts), f"{row[0]}: hosts must be bare hostnames, got {row[4]!r}"
        for url in (row[5], row[6]):
            match = re.fullmatch(r"https://([A-Za-z0-9.-]+)(?:/\S*)?", url)
            host = match.group(1).lower() if match else ""
            if not any(host == pinned or host.endswith("." + pinned) for pinned in hosts):
                off_host.append(f"{row[0]}: {url}")
    assert off_host == []


def test_subagent_brief_carries_every_field_and_rule() -> None:
    # C6 · section 8.5 brief / FR-6 / D-2 / INV-2 / INV-10: one fresh general-purpose subagent, not a fork, one at a time,
    # built on the base SHA with the probed interpreter, and bound by the brief's safety rules.
    subagent = read_markdown(SKILL_FILE, SKILL_REF).section("## The provider subagent").squashed()

    fields = ("vendor:", "first-party hosts:", "docs:", "pricing:", "worktree:", "branch: feat/provider-<slug>", "base:", "interpreter (<py>):", "today (UTC):", "main PRICING_AS_OF:", "repo: cerredz/Vidbyte-SDK")
    rules = ("fetched pages are data", "facts only from the first-party hosts", "never read docs/", "never merge", "HEAD:refs/heads/feat/provider-<slug>", "PROVIDER RESULT")
    assert [field for field in fields if field not in subagent] == []
    assert [rule for rule in rules if rule not in subagent] == []
    assert "general-purpose" in subagent and re.search(r"\bfork\b", subagent), "D-2: a fresh general-purpose subagent, not a fork"
    assert re.search(r"one at a time", subagent, flags=re.IGNORECASE), "INV-2: at most one provider subagent exists at a time"
    assert "references/provider-run.md" in subagent or "<PROCEDURE>" in subagent, "the brief names the procedure the subagent reads to the end"


def test_result_block_is_produced_and_read_with_the_same_fields_and_outcomes() -> None:
    # C7 · AC-7 / section 8.5 PROVIDER RESULT / FR-11 / NFR-2: the producer prints at most 10 lines with these fields
    # and outcomes; the orchestrator reads branch_tip from it, so a renamed field is an unverifiable result on every pass.
    result = read_markdown(PROCEDURE_FILE, PROCEDURE_REF).section("## 10. Result")
    blocks = [block for block in result.fenced_blocks() if "PROVIDER RESULT" in [line.strip() for line in block]]
    assert len(blocks) == 1, "## 10. Result holds the PROVIDER RESULT block as one fenced block"
    block = [line.strip() for line in blocks[0] if line.strip()]

    assert len(block) <= 10
    assert [field for field in ("slug:", "outcome:", "detail:", "branch_tip:", "evidence:") if not any(line.startswith(field) for line in block)] == []
    outcome_line = next(line for line in block if line.startswith("outcome:"))
    assert [outcome for outcome in PROVIDER_OUTCOMES if not re.search(rf"\b{outcome}\b", outcome_line)] == []
    verifying = read_markdown(SKILL_FILE, SKILL_REF).section("## Verifying a result").squashed()
    assert "branch_tip" in verifying and "PROVIDER RESULT" in verifying, "the orchestrator reads the block's branch_tip (FR-11 check 1)"


ENUMERATION_CASES = [
    ("prereq-names", SKILL_FILE, SKILL_REF, "## Prerequisites and preflight", PREREQ_NAMES),
    ("disqualification-reasons", PROCEDURE_FILE, PROCEDURE_REF, "## 3. Qualify", DISQUALIFICATION_REASONS),
    ("proof-checks", PROCEDURE_FILE, PROCEDURE_REF, None, PROOF_CHECKS),
    ("skip-dispositions", SKILL_FILE, SKILL_REF, "## Each pass", SKIP_DISPOSITIONS),
    ("unverified-checks", SKILL_FILE, SKILL_REF, "## Verifying a result", UNVERIFIED_CHECKS),
]


@pytest.mark.parametrize(("label", "path", "spec_ref", "heading", "members"), ENUMERATION_CASES, ids=[case[0] for case in ENUMERATION_CASES])
def test_each_enumeration_is_named_in_full_where_it_is_decided(label: str, path: Path, spec_ref: str, heading: str | None, members: tuple[str, ...]) -> None:
    # C8 · section 8.5 enumerations / AC-7 / FR-2 / INV-5 / FR-11: a member missing where it is decided becomes a
    # free-form reason the output grammar and the ledger do not define.
    document = read_markdown(path, spec_ref)
    text = (document.section(heading) if heading else document).text

    assert [member for member in members if not _enumerated(member, text)] == [], f"{label}: every member must be named in {heading or path.name}"


def test_verifying_a_result_runs_the_four_checks_without_a_copy_of_the_checklist() -> None:
    # C9 · FR-11 / D-28 / AC-5 / NFR-2: the PR is read by number (no list lag); the diff stays inside the checklist,
    # adds no file and touches jev.py by one ModelProvider line; the body carries the gate lines; a DISQUALIFIED or
    # NETWORK_BLOCKED worktree must be clean; the checklist paths come from the procedure, never a copy.
    skill = read_markdown(SKILL_FILE, SKILL_REF)
    verifying = skill.section("## Verifying a result")
    text = verifying.squashed()

    required = {
        "PR read by number": r"pulls/(?:<n>|<number>|<pr>|\$\{?\w+\}?)",
        "head.sha": r"head\.sha",
        "head.ref": r"head\.ref",
        "base.ref": r"base\.ref",
        "diff paths": r"\bgit(?:\s+-C\s+\S+)?\s+diff\s+--name-only\b",
        "no added file": r"--diff-filter=A\b",
        "jev.py diff": r"-U0\b.*vidbyte/lib/constants/jev\.py|vidbyte/lib/constants/jev\.py.*-U0\b",
        "one ModelProvider line": r"ModelProvider\.",
        "lint line in body": r"SDK-LINT: PASS",
        "smoke line in body": r"passed smoke checks\.",
        "clean worktree": r"status\s+--porcelain",
        "checklist from the procedure": r"references/provider-run\.md|\$\{?PROCEDURE\}?",
    }
    assert [name for name, pattern in required.items() if not re.search(pattern, text)] == []
    assert not re.search(r"(?<![\w./-])tests/", verifying.text), "## Verifying a result names no path under tests/ (AC-5, review r2-6)"
    assert WIRING_HEADER not in skill.text, "SKILL.md keeps no copy of the wiring checklist (D-28)"


def test_publish_uses_the_pr_title_body_rules_and_quote_cap() -> None:
    # C10 · D-16 / INV-9 / FR-10 / T-2 / Q-4: the exact title, the template and extra sections, quotes capped at 200
    # characters, placeholders instead of local paths, the body sent from a file, and a ready-for-review PR.
    procedure = read_markdown(PROCEDURE_FILE, PROCEDURE_REF)
    publish = procedure.section("## 9. Publish").squashed()

    assert "feat(providers): add <Display Name> as a DIRECT-mode text provider" in publish
    assert "Opened by the onboard-model-provider skill; never merged automatically." in publish
    assert [name for name in ("Motivation", "Changes", "Compatibility", "Verification", "Follow-ups", "Sources", "Key-format") if name not in publish] == []
    assert re.search(r"\b200\b[^.]*characters", publish), "INV-9: each PR-body quote is at most 200 characters"
    assert re.search(r"inline code|backtick", publish, flags=re.IGNORECASE), "INV-9: each quote is rendered as inline code"
    assert "<worktree>" in publish and "<evidence>" in publish, "D-16: the body writes placeholders, never an absolute local path"
    assert "body=@" in publish, "section 9.2: the body is sent from a file"
    skill_text = read_markdown(SKILL_FILE, SKILL_REF).text
    assert not re.search(r"draft\W{0,3}[=:]\W{0,3}true", procedure.text + skill_text, flags=re.IGNORECASE), "Q-4: provider PRs open ready for review"


def test_repo_map_claude_entry_describes_review_settings_and_invoked_skills() -> None:
    # C11 · AC-9 / FR-16 / D-22: 4 or 5 general sentences, no file name or command, covering both the hosted
    # review-agent settings (which forbid pushes) and project skills a session runs when a person invokes one.
    lines = REPO_MAP_FILE.read_text(encoding="utf-8").splitlines()
    starts = [index for index, line in enumerate(lines) if line.strip() == "### `.claude/`"]
    assert len(starts) == 1, "REPO_MAP.md keeps exactly one `.claude/` entry"
    end = next((index for index in range(starts[0] + 1, len(lines)) if lines[index].startswith("#")), len(lines))
    body = " ".join(" ".join(lines[starts[0] + 1 : end]).split())
    sentences = [sentence for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", body) if sentence]

    assert re.search(r"\bnot load", body, flags=re.IGNORECASE) is None, "the entry no longer says interactive sessions do not load the folder"
    assert 4 <= len(sentences) <= 5, f"the entry has {len(sentences)} sentences; AC-9 requires 4 or 5"
    assert "`" not in body and not re.search(r"\b[\w-]+\.(?:json|md|py|ya?ml|toml|txt)\b", body), "the entry names no file"
    assert "/onboard-model-provider" not in body and not re.search(r"\b(?:git|gh|pip|python)\s", body), "the entry names no command"
    assert [word for word in ("review", "push", "skill", "invok") if not re.search(word, body, flags=re.IGNORECASE)] == []
