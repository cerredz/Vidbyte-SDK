"""FILE: tests/features/public_skill_loader/test_public_skill_loader_docs.py

PURPOSE: Pin that the maintainer-facing texts describe the public door: no map, README, or header still calls JevAgent's preload the loader's only consumer, says the constructor only stores its entries, or ties the loader's memory to an agent without saying that is JevAgent's case; the skills README states the public-door contract and keeps Notes for agents last, and the root header's error line names ConfigurationError.
ROLE IN CODEBASE: Covers spec AC-16, FR-10 and W-4 for REPO_MAP.md, vidbyte/agents/README.md, vidbyte/agents/skills/README.md, vidbyte/agents/skills/__init__.py, vidbyte/agents/skills/loader.py and vidbyte/__init__.py (spec section 12.3 rows 2(d), 3(f), 12, 13, 14, 15).
ARCHITECTURE NOTE: Each case reads one file of this checkout and checks only the part the spec row names: stale phrases that must be gone, and the few words the row requires. Any rewording that drops the stale phrase and keeps the required words passes.
FUNCTION INVENTORY: test_docs_describe_the_public_door.
COMMON MODIFICATION PATTERNS: A text that starts naming the loader's callers adds a DOC_RULES row with the part it covers.
WHAT NOT TO DO IN THIS FILE: 1. Do not pin whole sentences; pin the stale phrase and the required names only. 2. Do not read anything under docs/.
KNOWN EDGE CASES: A header field or bullet may wrap, so a part runs from its first line until a blank line, the next bullet, or the next header field. The skills README must keep "## Notes for agents" as its last section (AGENTS.md Repository Map).
RELATED DOCS: docs/spec/public-skill-loader/spec.md (sections 6.2 AC-16, 12.3 rows 2, 3, 12 to 15)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/public_skill_loader/test_public_skill_loader_docs.py
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PART_BREAK = re.compile(r"^(\s*- |[A-Z][A-Za-z /]*:|#)")


def part(prefix: str) -> Callable[[str], str]:
    # The field or bullet that starts with prefix, with any wrapped continuation lines.
    def pick(text: str) -> str:
        lines = text.splitlines()
        for start, line in enumerate(lines):
            if line.strip().startswith(prefix):
                picked = [line]
                for following in lines[start + 1 :]:
                    if not following.strip() or PART_BREAK.match(following):
                        break
                    picked.append(following)
                return "\n".join(picked)
        return ""

    return pick


def repo_map_skills_entry(text: str) -> str:
    # The File Index entry for vidbyte/agents/skills/, up to the next
    # heading; empty when the heading is gone, so the guard fails.
    _, found, entry = text.partition("##### `vidbyte/agents/skills/`")
    return entry.split("\n#", 1)[0] if found else ""


def intro_paragraph(text: str) -> str:
    # The paragraph under the README's title.
    return text.split("\n\n")[1]


def whole(text: str) -> str:
    return text


@dataclass(frozen=True)
class DocRule:
    """One spec row's demand on one part of one file: phrases that must be gone, and words it must hold."""

    path: str
    section: Callable[[str], str]
    absent: tuple[str, ...] = ()
    present: tuple[str, ...] = ()


DOC_RULES: dict[str, DocRule] = {
    # Row 14: the map entry stops calling JevAgent the only consumer and the agent's lifetime the memory's.
    "REPO_MAP skills entry": DocRule("REPO_MAP.md", repo_map_skills_entry, absent=("only consumer", "for the agent's lifetime", "until the first run")),
    # Row 13: the Key Modules line also names callers that import SkillLoader from the package root.
    "agents README skills line": DocRule("vidbyte/agents/README.md", part("- `skills/`:"), present=("SkillLoader", "from the package root")),
    # Row 12(a): the intro names any caller that imports SkillLoader from the package root.
    "skills README intro": DocRule("vidbyte/agents/skills/README.md", intro_paragraph, present=("SkillLoader", "package root")),
    # Row 12(b): the Public door bullet states the contract, including one loader per tenant or credential set.
    "skills README public door bullet": DocRule(
        "vidbyte/agents/skills/README.md",
        part("- **Public door.**"),
        present=("SkillLoader", "SkillResolution", "ConfigurationError", "contracts/sdk-public-api.json", "tenant"),
    ),
    # Row 12(c), (d): the constructor now checks its entries, and memory lives per loader.
    "skills README stale wording": DocRule("vidbyte/agents/skills/README.md", whole, absent=("only stores them", "inside `load()`, on the first run", "lives per agent")),
    # Row 15: the package header names the root re-export.
    "skills package header role": DocRule("vidbyte/agents/skills/__init__.py", part("ROLE IN CODEBASE:"), present=("vidbyte/__init__.py",)),
    # Row 2(d): the loader header names the public door and qualifies per-agent memory as JevAgent's case.
    "loader header role": DocRule("vidbyte/agents/skills/loader.py", part("ROLE IN CODEBASE:"), present=("vidbyte.SkillLoader",)),
    "loader header architecture note": DocRule("vidbyte/agents/skills/loader.py", part("ARCHITECTURE NOTE:"), absent=("(per agent)",), present=("JevAgent",)),
    # Row 3(f): the root header's error line names the general ConfigurationError.
    "root header error exports": DocRule("vidbyte/__init__.py", part("- Error exports:"), present=("ConfigurationError",)),
}


@pytest.mark.parametrize("rule_name", list(DOC_RULES))
def test_docs_describe_the_public_door(rule_name: str) -> None:
    # AC-16, FR-10: a maintainer reading these must not conclude the loader is JevAgent's alone.
    rule = DOC_RULES[rule_name]
    text = (REPO_ROOT / rule.path).read_text(encoding="utf-8")
    section = rule.section(text)
    assert section.strip(), f"{rule_name}: the part this rule checks is missing from {rule.path}"
    for phrase in rule.absent:
        assert phrase not in section, f"{rule_name}: stale {phrase!r} in {rule.path}: {section}"
    for phrase in rule.present:
        assert phrase in section, f"{rule_name}: {phrase!r} missing from {rule.path}: {section}"
    if rule.path.endswith("skills/README.md"):
        headings = [line for line in text.splitlines() if line.startswith("## ")]
        assert headings[-1] == "## Notes for agents", headings
