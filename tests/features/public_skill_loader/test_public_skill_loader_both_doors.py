"""FILE: tests/features/public_skill_loader/test_public_skill_loader_both_doors.py

PURPOSE: Pin that the Jev door (JevAlignmentSettings.skills) and the public door (SkillLoader) apply one name rule: for every tuple or list of entries and documents, both accept, or both raise ConfigurationError with equal details, on a curated table and on a seeded sweep of generated collections.
ROLE IN CODEBASE: Covers spec AC-18, INV-18, FR-12, D-4 and NG-10 for SkillEntries.__post_init__ (vidbyte/lib/dataclasses/skills.py) against JevAlignmentSettings._normalized_skills (vidbyte/agents/jev/settings.py), which keeps its own copy of the rule.
ARCHITECTURE NOTE: Pure construction, no load and no I/O. ConfigurationError is caught from its defining module so this file isolates INV-18 from the root-export identity, which the contract module pins. The sweep uses a fixed seed, so every run sees the same collections.
FUNCTION INVENTORY: test_both_doors_agree_on_repeated_and_unique_names; test_both_doors_agree_across_a_seeded_sweep_of_collections.
COMMON MODIFICATION PATTERNS: A new entry class joins entry_factories(); a new curated collision joins CURATED with the names both doors must report.
WHAT NOT TO DO IN THIS FILE: 1. Do not add plain strings: the Jev door turns them into inline_skill_<n> documents while the public door rejects them at their position (spec section 13), so INV-18 does not cover them. 2. Do not compare messages; the two doors name different classes on purpose (NG-10).
KNOWN EDGE CASES: The curated collisions local-and-github, document-and-vendor, and two-vendors are the three reusable rows of DUPLICATES in tests/features/jev_skills_preload/test_skill_sources_entries.py. Names compare exactly, so the name pool includes case, trailing-space, and Unicode-form variants that must never collide.
RELATED DOCS: docs/spec/public-skill-loader/spec.md (sections 6.1 INV-18, 6.2 AC-18, 11 Conflicts, 13 Both doors)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/public_skill_loader/test_public_skill_loader_both_doors.py
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from vidbyte.lib.errors import ConfigurationError

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte import (
        AnthropicSkill,
        GitHubSkill,
        InlineSkill,
        JevAlignmentSettings,
        LocalSkill,
        OpenAISkill,
        SkillDocument,
        SkillLoader,
        SkillsShSkill,
    )
except ImportError as missing:  # red until the feature lands; the rest of the suite must still collect
    FEATURE_MISSING = missing

SWEEP_SEED = 1088
SWEEP_CASES = 300
NAME_POOL = ("pdf", "PDF", "pdf ", "notes", "café", "café")


@pytest.fixture(autouse=True)
def _feature_present() -> None:
    # Fails every test at setup with the import error until the feature exists, instead of skipping it; the
    # traceback is reset so repeated raises of the one stored error do not grow its traceback test after test.
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def outcome(build: Callable[[], object]) -> tuple[object, ...]:
    # What one door answered: accepted, or rejected with the error's details.
    try:
        build()
    except ConfigurationError as error:
        return ("rejected", error.details)
    return ("accepted",)


def doors(collection: tuple[Any, ...] | list[Any]) -> tuple[tuple[object, ...], tuple[object, ...]]:
    return outcome(lambda: JevAlignmentSettings(skills=collection)), outcome(lambda: SkillLoader(collection))


# (case, collection builder, repeated names both doors must report, or None when both must accept)
CURATED: list[tuple[str, Callable[[], tuple[Any, ...]], list[str] | None]] = [
    ("local-and-github", lambda: (LocalSkill(name="pdf", path="skills/pdf"), GitHubSkill(name="pdf", repo="anthropics/skills")), ["pdf"]),
    ("document-and-vendor", lambda: (SkillDocument(name="notes", description="d", text="t"), AnthropicSkill(name="notes", skill_id="skill_1")), ["notes"]),
    ("two-vendors", lambda: (OpenAISkill(name="sheets", skill_id="skill_1"), OpenAISkill(name="sheets", skill_id="skill_2")), ["sheets"]),
    ("same-entry-twice", lambda: (SkillsShSkill(name="react", source="acme/skills"), SkillsShSkill(name="react", source="acme/skills")), ["react"]),
    (
        "unique-across-every-kind",
        lambda: (
            InlineSkill(name="review", description="d", text="t"),
            LocalSkill(name="pdf", path="skills/pdf"),
            SkillsShSkill(name="react", source="acme/skills"),
            GitHubSkill(name="webapp", repo="anthropics/skills"),
            AnthropicSkill(name="notes", skill_id="skill_1"),
            OpenAISkill(name="sheets", skill_id="skill_2"),
            SkillDocument(name="caller", description="d", text="t"),
        ),
        None,
    ),
    ("empty", lambda: (), None),
]


@pytest.mark.parametrize("container", [tuple, list], ids=["tuple", "list"])
@pytest.mark.parametrize(("case", "build", "names"), CURATED, ids=[row[0] for row in CURATED])
def test_both_doors_agree_on_repeated_and_unique_names(case: str, build: Callable[[], tuple[Any, ...]], names: list[str] | None, container: type) -> None:
    # AC-18, INV-18: the expected answer is pinned too, so two doors that agree on a wrong answer still fail.
    expected = ("accepted",) if names is None else ("rejected", {"names": names})
    assert doors(container(build())) == (expected, expected)


def entry_factories(root: Path) -> list[Callable[[str, int], Any]]:
    # One builder per kind the doors accept; index keeps otherwise-equal entries apart unless a case repeats one.
    return [
        lambda name, index: InlineSkill(name=name, description="d", text=f"t{index}"),
        lambda name, index: LocalSkill(name=name, path=root / f"local-{index}"),
        lambda name, index: SkillsShSkill(name=name, source="acme/skills"),
        lambda name, index: GitHubSkill(name=name, repo="acme/skills", ref=f"v{index}"),
        lambda name, index: AnthropicSkill(name=name, skill_id=f"skill_{index}"),
        lambda name, index: OpenAISkill(name=name, skill_id=f"skill_{index}"),
        lambda name, index: SkillDocument(name=name, description="d", text=f"t{index}"),
    ]


def test_both_doors_agree_across_a_seeded_sweep_of_collections(tmp_path: Path) -> None:
    # INV-18 as a property: any drift between the two copies of the rule (case folding, stripping,
    # Unicode normalization, unsorted or repeated names) shows up as a disagreement on some collection.
    rng = random.Random(SWEEP_SEED)
    factories = entry_factories(tmp_path)
    answers: Counter[object] = Counter()
    for case in range(SWEEP_CASES):
        items = [rng.choice(factories)(rng.choice(NAME_POOL), index) for index in range(rng.randrange(0, 5))]
        if items and rng.random() < 0.2:
            # The same entry object again, the shape that crashed the old loader (EC-4).
            items.insert(rng.randrange(len(items) + 1), rng.choice(items))
        collection = tuple(items) if rng.random() < 0.5 else list(items)
        jev, public = doors(collection)
        assert public == jev, f"case {case}: {collection!r}"
        answers[jev[0]] += 1
    # Non-vacuity: the sweep exercises both answers many times.
    assert answers["accepted"] >= 60 and answers["rejected"] >= 60, answers
