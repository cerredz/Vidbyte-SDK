"""FILE: tests/features/loop_spend_cap/test_loop_spend_cap_docs.py

PURPOSE: Prove the developer-facing docs the spec names describe the spend cap: the
agents README has a Spend Cap section with the names a caller needs, and the Jev README,
llms.txt, the failure vocabulary and the two skill guides each name the field (and,
where the spec says so, its stop reason and failure code).
ROLE IN CODEBASE: Documentation checks for spec AC-26 (W-9), over files outside docs/.
ARCHITECTURE NOTE: Each check reads one tracked text file from the repository root and
asserts only the names the spec requires, never whole sentences, so ordinary editing of
the prose stays free. The release record under docs/ is deliberately not read here (the
pack never reads docs/); S5 review checks it.
FUNCTION INVENTORY: test_the_agents_readme_has_a_spend_cap_section_naming_what_a_caller_reads;
test_each_named_doc_mentions_the_cap.
COMMON MODIFICATION PATTERNS: A new doc the spec requires adds one parametrized row with
the names it must contain.
WHAT NOT TO DO IN THIS FILE: 1. Do not read anything under docs/. 2. Do not pin prose,
line numbers or character counts; pin only names. 3. Do not add a doc the spec does not
name.
KNOWN EDGE CASES: The Spend Cap section ends at the next level-two heading; it must sit
before Key Modules, which also lists spend_cap.py.
RELATED DOCS: docs/spec/loop-spend-cap/spec.md AC-26, section 12.3 rows 13-17 and 27.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/loop_spend_cap/test_loop_spend_cap_docs.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    # The body under a level-two heading, up to the next level-two heading.
    start = text.index(f"\n{heading}\n")
    end = text.find("\n## ", start + len(heading) + 2)
    return text[start : end if end != -1 else len(text)]


def test_the_agents_readme_has_a_spend_cap_section_naming_what_a_caller_reads() -> None:
    # AC-26 and spec row 13: the section a developer reads before setting the cap.
    readme = _read("vidbyte/agents/README.md")
    assert "\n## Spend Cap\n" in readme
    section = _section(readme, "## Spend Cap")

    for name in (
        "max_spend_usd",
        "max_spend",
        "resource.exhausted",
        "cost_measured",
        "get_usage",
        "CostBudgetMiddleware",
    ):
        assert name in section, f"the Spend Cap section does not name {name}"
    assert readme.index("\n## Spend Cap\n") < readme.index("\n## Key Modules\n")
    assert "spend_cap.py" in _section(readme, "## Key Modules")


@pytest.mark.parametrize(
    ("relative", "names"),
    [
        ("vidbyte/agents/jev/README.md", ("max_spend_usd",)),
        ("llms.txt", ("max_spend_usd", '"max_spend"')),
        ("skills/failure/vocabulary.md", ("max_spend_usd", "resource.exhausted")),
        ("skills/agentic-loop-settings/SKILL.md", ("max_spend_usd", '"max_spend"')),
        ("skills/output-contracts/SKILL.md", ("AgentLoopSettings.max_spend_usd",)),
    ],
)
def test_each_named_doc_mentions_the_cap(relative: str, names: tuple[str, ...]) -> None:
    # AC-26 and spec rows 14, 15, 17 and 27.
    text = _read(relative)

    for name in names:
        assert name in text, f"{relative} does not name {name}"
    if relative == "skills/failure/vocabulary.md":
        assert any(
            "max_spend" in line and "resource.exhausted" in line
            for line in text.splitlines()
        )
