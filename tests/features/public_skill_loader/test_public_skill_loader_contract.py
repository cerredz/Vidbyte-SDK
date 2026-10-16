"""FILE: tests/features/public_skill_loader/test_public_skill_loader_contract.py

PURPOSE: Pin the public contract of the root door: SkillLoader, SkillResolution, and ConfigurationError are root exports that are the defining-module objects and that a consumer can catch entry errors with; the three names and SkillEntries are exported nowhere else new; the constructor takes one Sequence of entries and documents with load() still async; and SkillEntries, the internal record behind the constructor, accepts only a tuple.
ROLE IN CODEBASE: Covers spec AC-10 (exports half), INV-1, INV-2 (SkillEntries is tuple-only), INV-15, FR-1 to FR-3, D-2, D-5, D-6, D-14, NG-13, NFR-6 and EC-24 for vidbyte/__init__.py, vidbyte/agents/skills/__init__.py, vidbyte/agents/skills/loader.py, and vidbyte/lib/dataclasses/skills.py.
ARCHITECTURE NOTE: Pure import, signature, and record checks; nothing loads. The contract file itself (contracts/sdk-public-api.json) is checked by lint rule C016 and scripts/generate-sdk-public-api.py --check, not here, because it is committed after the source on purpose (spec section 12.6).
FUNCTION INVENTORY: test_three_new_names_are_root_exports_and_the_defining_objects; test_new_names_are_exported_from_the_root_only; test_constructor_takes_one_sequence_of_entries_and_load_stays_async; test_skill_entries_record_accepts_only_a_tuple.
COMMON MODIFICATION PATTERNS: A further public skill name joins NEW_ROOT_NAMES with its defining module; a new export path that may carry the names joins OTHER_EXPORTERS.
WHAT NOT TO DO IN THIS FILE: 1. Do not compare against the generated contract JSON; C016 owns it. 2. Do not loosen identity to equality; a second copy of a class breaks isinstance and except clauses. 3. Do not assert the exact annotation object; typing.Sequence and collections.abc.Sequence are both correct, so check the origin and the union members.
KNOWN EDGE CASES: ConfigurationError is defined in vidbyte/lib/errors/base.py and already exported from vidbyte.lib.errors, its defining package, which stays. vidbyte.agents.skills must keep an empty __all__ and gain no import (its header forbids exports there).
RELATED DOCS: docs/spec/public-skill-loader/spec.md (sections 6.1 INV-1, INV-2, INV-15, 8.1 D-6, D-14, 8.5, 9.2, 12.4)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/public_skill_loader/test_public_skill_loader_contract.py
"""

from __future__ import annotations

import collections.abc
import importlib
import inspect
import typing

import pytest

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte import (
        ConfigurationError,
        GitHubSkill,
        InlineSkill,
        SkillDocument,
        SkillEntry,
        SkillLoader,
        SkillResolution,
    )
    from vidbyte.lib.dataclasses.skills import SkillEntries
except ImportError as missing:  # red until the feature lands; the rest of the suite must still collect
    FEATURE_MISSING = missing

# Root name -> the module that defines it (spec INV-1).
NEW_ROOT_NAMES = {
    "SkillLoader": "vidbyte.agents.skills.loader",
    "SkillResolution": "vidbyte.lib.dataclasses.skills",
    "ConfigurationError": "vidbyte.lib.errors",
}
OTHER_EXPORTERS = ("vidbyte.agents", "vidbyte.agents.jev", "vidbyte.lib", "vidbyte.lib.dataclasses", "vidbyte.agents.skills")


@pytest.fixture(autouse=True)
def _feature_present() -> None:
    # Fails every test at setup with the import error until the feature exists, instead of skipping it; the
    # traceback is reset so repeated raises of the one stored error do not grow its traceback test after test.
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def test_three_new_names_are_root_exports_and_the_defining_objects() -> None:
    # AC-10, INV-1, FR-1 to FR-3: vidbyte-cli may import only names in vidbyte.__all__ (its C028), so each must be listed once.
    root = importlib.import_module("vidbyte")
    for name, path in NEW_ROOT_NAMES.items():
        assert root.__all__.count(name) == 1, f"{name} must appear once in vidbyte.__all__"
        assert getattr(root, name) is getattr(importlib.import_module(path), name), name
    # D-5, EC-24: an entry constructor's own error is caught by the root name.
    with pytest.raises(ConfigurationError):
        GitHubSkill(name="pdf", repo="https://github.com/anthropics/skills")


def test_new_names_are_exported_from_the_root_only() -> None:
    # D-6, NG-13, INV-15, NFR-6: the public surface grows by exactly the three root names; SkillEntries stays internal.
    for path in OTHER_EXPORTERS:
        exported = getattr(importlib.import_module(path), "__all__", ())
        for name in (*NEW_ROOT_NAMES, "SkillEntries"):
            assert name not in exported, f"{name} must not be exported from {path}"
    skills_package = importlib.import_module("vidbyte.agents.skills")
    assert skills_package.__all__ == [] and not hasattr(skills_package, "SkillLoader")
    records = importlib.import_module("vidbyte.lib.dataclasses.skills")
    assert "SkillEntries" in records.__all__ and records.SkillEntries is SkillEntries
    root = importlib.import_module("vidbyte")
    assert "SkillEntries" not in root.__all__ and not hasattr(root, "SkillEntries")


def test_constructor_takes_one_sequence_of_entries_and_load_stays_async() -> None:
    # D-14, NFR-6, D-2: the CLI type-checks with mypy --strict, so a tuple-only annotation would make it wrap every list;
    # no byte-limit or credential parameter joins the constructor (D-7, D-8).
    assert list(inspect.signature(SkillLoader).parameters) == ["entries"]
    # Sequence is supplied in case the module imports it for type checking only; typing.Sequence has the same origin.
    hint = typing.get_type_hints(SkillLoader.__init__, localns={"Sequence": collections.abc.Sequence})["entries"]
    assert typing.get_origin(hint) is collections.abc.Sequence, hint
    (element,) = typing.get_args(hint)
    assert set(typing.get_args(element)) == {SkillEntry, SkillDocument}, hint
    assert inspect.iscoroutinefunction(SkillLoader.load)
    assert not inspect.iscoroutinefunction(SkillLoader.documents)


def test_skill_entries_record_accepts_only_a_tuple() -> None:
    # INV-2, D-3, D-14: the constructor converts; the record checks a concrete tuple and keeps each element as given.
    first = InlineSkill(name="house-review", description="Our review checklist.", text="Read the tests first.\n")
    second = SkillDocument(name="caller-notes", description="Resolved by the caller.", text="Caller text.\n")
    record = SkillEntries(entries=(first, second))
    assert record.entries == (first, second) and record.entries[0] is first and record.entries[1] is second
    assert SkillEntries(entries=()).entries == ()
    with pytest.raises(ConfigurationError) as raised:
        SkillEntries(entries=[first, second])  # type: ignore[arg-type]
    assert raised.value.details == {"entries_type": "list"}
