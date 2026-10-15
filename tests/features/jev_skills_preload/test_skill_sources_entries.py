"""FILE: tests/features/jev_skills_preload/test_skill_sources_entries.py

PURPOSE: Pin construction of the six declarative skill entries and of JevAlignmentSettings.skills: each class has a fixed read-only type, rejects fields it does not have, validates every field at construction naming the class and field, pins relative paths to the working folder, and the settings accept entries beside strings and SkillDocument values with names unique across all of them.
ROLE IN CODEBASE: Covers spec INV-1 to INV-3, INV-20, FR-1 to FR-3 and EC-1 to EC-8, EC-10, EC-13 to EC-15, EC-37, EC-38, EC-48 to EC-51, EC-75 for vidbyte/lib/dataclasses/skills.py and vidbyte/agents/jev/settings.py.
ARCHITECTURE NOTE: Everything here is real construction; nothing is patched. The feature imports are guarded so a missing class fails each test at setup instead of stopping collection of the suite.
FUNCTION INVENTORY: test_entry_type_is_fixed_by_its_class_and_cannot_be_passed; test_source_without_text_rejects_text_and_description; test_base_entry_cannot_be_constructed; test_invalid_field_is_rejected_naming_class_and_field; test_valid_repo_ref_and_path_shapes_are_accepted; test_relative_paths_are_pinned_to_the_working_folder_at_construction; test_settings_keep_entries_beside_documents_and_strings_in_order; test_duplicate_names_across_every_kind_are_rejected_with_the_names; test_settings_reject_values_that_are_not_entries_documents_or_strings.
COMMON MODIFICATION PATTERNS: A new entry field adds rows to the invalid-field and valid-shape tables; a new source class adds a row to the type table.
WHAT NOT TO DO IN THIS FILE: 1. Do not stub or subclass the entries to make a case pass. 2. Do not assert exact error wording beyond the class.field name and the hints the spec requires.
KNOWN EDGE CASES: Windows drive-relative names such as "C:x" would replace the skills folder when joined, so a colon is rejected in one-segment names. Validation must not touch the filesystem, so a missing folder is never an error here.
RELATED DOCS: docs/spec/jev-skill-sources/spec.md (sections 6.1, 6.3, 9.1); tests/features/jev_skills_preload/FEATURE.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_skills_preload/test_skill_sources_entries.py
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import vidbyte
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
        SkillEntry,
        SkillSourceType,
        SkillsShSkill,
        SkillUnavailableReason,
    )
    from vidbyte.lib.dataclasses.skills import SkillResolution
except ImportError as missing:  # red until the feature lands; the rest of the suite must still collect
    FEATURE_MISSING = missing

FULL_SHA = "0123456789abcdef0123456789abcdef01234567"
VALID_KWARGS: dict[str, dict[str, Any]] = {
    "InlineSkill": {"name": "house-review", "description": "Our PR review checklist.", "text": "Read every edited function first."},
    "LocalSkill": {"name": "sql-migrations", "path": "skills/sql-migrations"},
    "SkillsShSkill": {"name": "react-best-practices", "source": "vercel-labs/agent-skills"},
    "GitHubSkill": {"name": "webapp-testing", "repo": "anthropics/skills"},
    "AnthropicSkill": {"name": "release-notes", "skill_id": "skill_01AbCd"},
    "OpenAISkill": {"name": "spreadsheets", "skill_id": "skill_abc"},
}


@pytest.fixture(autouse=True)
def _feature_present() -> None:
    # Fails every test at setup with the import error until the feature exists, instead of skipping it; the
    # traceback is reset so repeated raises of the one stored error do not grow its traceback test after test.
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def _entry(class_name: str, **overrides: Any) -> Any:
    return getattr(vidbyte, class_name)(**{**VALID_KWARGS[class_name], **overrides})


@pytest.mark.parametrize(
    ("class_name", "expected_type"),
    [("InlineSkill", "inline"), ("LocalSkill", "local"), ("SkillsShSkill", "skills_sh"), ("GitHubSkill", "github"), ("AnthropicSkill", "anthropic"), ("OpenAISkill", "openai")],
)
def test_entry_type_is_fixed_by_its_class_and_cannot_be_passed(class_name: str, expected_type: str) -> None:
    # FR-2, EC-2: without init=False an InlineSkill could claim type=GITHUB and reach the wrong resolver.
    entry = _entry(class_name)
    assert isinstance(entry, SkillEntry)
    assert entry.type is SkillSourceType(expected_type)
    with pytest.raises(TypeError):
        _entry(class_name, type=SkillSourceType.GITHUB)


@pytest.mark.parametrize(
    ("class_name", "foreign_field"),
    [("GitHubSkill", "text"), ("SkillsShSkill", "text"), ("SkillsShSkill", "description"), ("LocalSkill", "text"), ("AnthropicSkill", "text"), ("OpenAISkill", "description")],
)
def test_source_without_text_rejects_text_and_description(class_name: str, foreign_field: str) -> None:
    # EC-1: a text field the source never reads would be silently ignored.
    with pytest.raises(TypeError):
        _entry(class_name, **{foreign_field: "ignored guidance"})


def test_base_entry_cannot_be_constructed() -> None:
    # EC-3: a typeless entry would reach no resolver in the middle of a run.
    with pytest.raises(ConfigurationError) as raised:
        SkillEntry(name="orphan")
    for class_name in VALID_KWARGS:
        assert class_name in str(raised.value)


INVALID_FIELDS = [
    ("InlineSkill", {"name": ""}, "name"),
    ("InlineSkill", {"name": "   "}, "name"),
    ("InlineSkill", {"name": 42}, "name"),
    ("InlineSkill", {"description": ""}, "description"),
    ("InlineSkill", {"text": "  \n "}, "text"),
    ("LocalSkill", {"path": ""}, "path"),
    ("LocalSkill", {"path": "skills/pdf/SKILL.md"}, "path"),
    ("LocalSkill", {"path": "skills/pdf/skill.md"}, "path"),
    ("LocalSkill", {"path": 7}, "path"),
    ("SkillsShSkill", {"name": "../escape"}, "name"),
    ("SkillsShSkill", {"name": "nested/name"}, "name"),
    ("SkillsShSkill", {"name": "back\\slash"}, "name"),
    ("SkillsShSkill", {"name": "C:drive-relative"}, "name"),
    ("SkillsShSkill", {"name": "nul\x00byte"}, "name"),
    ("SkillsShSkill", {"name": "."}, "name"),
    ("SkillsShSkill", {"name": ".."}, "name"),
    ("SkillsShSkill", {"source": ""}, "source"),
    ("SkillsShSkill", {"directory": ""}, "directory"),
    ("GitHubSkill", {"repo": "https://github.com/anthropics/skills"}, "repo"),
    ("GitHubSkill", {"repo": "anthropics"}, "repo"),
    ("GitHubSkill", {"repo": "anthropics/skills/extra"}, "repo"),
    ("GitHubSkill", {"repo": "anthropics/.."}, "repo"),
    ("GitHubSkill", {"repo": "anthropics/."}, "repo"),
    ("GitHubSkill", {"repo": "user:ghp_pasted@anthropics/skills"}, "repo"),
    ("GitHubSkill", {"repo": "anthropics/skills@main"}, "repo"),
    ("GitHubSkill", {"name": "nested/name"}, "name"),
    ("GitHubSkill", {"name": ".."}, "name"),
    ("GitHubSkill", {"path": "."}, "path"),
    ("GitHubSkill", {"path": "skills/../secrets"}, "path"),
    ("GitHubSkill", {"path": "skills//pdf"}, "path"),
    ("GitHubSkill", {"path": "/skills/pdf"}, "path"),
    ("GitHubSkill", {"path": "skills\\pdf"}, "path"),
    ("GitHubSkill", {"path": "./skills/pdf"}, "path"),
    ("GitHubSkill", {"path": "skills/pdf/SKILL.md"}, "path"),
    ("GitHubSkill", {"ref": ""}, "ref"),
    ("GitHubSkill", {"token": ""}, "token"),
    ("AnthropicSkill", {"skill_id": ""}, "skill_id"),
    ("AnthropicSkill", {"version": ""}, "version"),
    ("AnthropicSkill", {"api_key": " "}, "api_key"),
    ("OpenAISkill", {"skill_id": "  "}, "skill_id"),
    ("OpenAISkill", {"api_key": ""}, "api_key"),
]


@pytest.mark.parametrize(("class_name", "overrides", "field_name"), INVALID_FIELDS, ids=[f"{c}.{f}={o[f]!r}" for c, o, f in INVALID_FIELDS])
def test_invalid_field_is_rejected_naming_class_and_field(class_name: str, overrides: dict[str, Any], field_name: str) -> None:
    # INV-2: a bad field fails where it enters, at construction, and the message names <Class>.<field>.
    with pytest.raises(ConfigurationError) as raised:
        _entry(class_name, **overrides)
    assert f"{class_name}.{field_name}" in str(raised.value)


@pytest.mark.parametrize("class_name", ["AnthropicSkill", "OpenAISkill"])
def test_integer_version_is_rejected_with_a_hint_to_pass_text(class_name: str) -> None:
    # EC-75: version=2 is a common slip; the error says to pass "2".
    with pytest.raises(ConfigurationError) as raised:
        _entry(class_name, version=2)
    message = str(raised.value)
    assert f"{class_name}.version" in message
    assert '"2"' in message or "'2'" in message


VALID_SHAPES: list[tuple[str, dict[str, Any]]] = [
    ("GitHubSkill", {"repo": "vercel-labs/agent-skills"}),
    ("GitHubSkill", {"repo": "octo-org/repo.js"}),
    ("GitHubSkill", {"repo": "Octo-Org2/my_repo.v2"}),
    ("GitHubSkill", {"ref": "release/v1"}),
    ("GitHubSkill", {"ref": FULL_SHA}),
    ("GitHubSkill", {"path": "skills/webapp-testing"}),
    ("GitHubSkill", {"path": "webapp-testing", "token": "ghp_test_only_token"}),
    ("LocalSkill", {"path": Path("skills") / "sql-migrations"}),
    ("SkillsShSkill", {"directory": Path("vendor") / "skills"}),
    ("AnthropicSkill", {"version": "1759178010641129", "api_key": "sk-ant-test-only"}),
    ("OpenAISkill", {"version": "2"}),
]


@pytest.mark.parametrize(("class_name", "overrides"), VALID_SHAPES, ids=[f"{c}:{sorted(o)}" for c, o in VALID_SHAPES])
def test_valid_repo_ref_and_path_shapes_are_accepted(class_name: str, overrides: dict[str, Any]) -> None:
    # INV-2 / sec 9.1: an over-strict pattern (no dots or underscores in a repo, no slash in a ref) rejects real sources.
    entry = _entry(class_name, **overrides)
    for field_name, value in overrides.items():
        if isinstance(value, Path):
            assert Path(getattr(entry, field_name)).is_absolute()
        else:
            assert getattr(entry, field_name) == value


def test_relative_paths_are_pinned_to_the_working_folder_at_construction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # EC-15, D-15, INV-1: a later chdir must not move the skills, and pinning reads nothing (the folders do not exist).
    project, elsewhere = tmp_path / "project", tmp_path / "elsewhere"
    project.mkdir()
    elsewhere.mkdir()
    monkeypatch.chdir(project)
    local = LocalSkill(name="sql-migrations", path="skills/sql-migrations")
    installed = SkillsShSkill(name="react-best-practices", source="vercel-labs/agent-skills")
    monkeypatch.chdir(elsewhere)
    assert Path(local.path) == project / "skills" / "sql-migrations"
    assert Path(installed.directory) == project / ".agents" / "skills"
    assert not (project / "skills").exists()


def test_settings_keep_entries_beside_documents_and_strings_in_order() -> None:
    # FR-1, INV-20, EC-7: strings still become inline_skill_<position> counted over the whole list; entries pass unchanged.
    inline = InlineSkill(name="house-review", description="Our PR review checklist.", text="Read every edited function first.")
    remote = GitHubSkill(name="webapp-testing", repo="anthropics/skills", ref="v1.2.0")
    document = SkillDocument(name="caller-doc", description="Resolved by the caller.", text="Exact body.")
    settings = JevAlignmentSettings(skills=[" first text ", inline, document, remote, "fifth text\n"])  # type: ignore[arg-type]
    assert isinstance(settings.skills, tuple)
    assert [skill.name for skill in settings.skills] == ["inline_skill_1", "house-review", "caller-doc", "webapp-testing", "inline_skill_5"]
    assert settings.skills[1] is inline
    assert settings.skills[2] is document
    assert settings.skills[3] is remote
    assert settings.skills[0].text == " first text "
    assert settings.skills[4].source == "inline"


DUPLICATES: list[tuple[str, Callable[[], tuple[Any, ...]], list[str]]] = [
    ("local-and-github", lambda: (LocalSkill(name="pdf", path="skills/pdf"), GitHubSkill(name="pdf", repo="anthropics/skills")), ["pdf"]),
    ("entry-named-like-a-string", lambda: ("one", "two", InlineSkill(name="inline_skill_2", description="d", text="t")), ["inline_skill_2"]),
    ("document-and-vendor", lambda: (SkillDocument(name="notes", description="d", text="t"), AnthropicSkill(name="notes", skill_id="skill_1")), ["notes"]),
    ("two-vendors", lambda: (OpenAISkill(name="sheets", skill_id="skill_1"), OpenAISkill(name="sheets", skill_id="skill_2")), ["sheets"]),
]


@pytest.mark.parametrize(("label", "build", "names"), DUPLICATES, ids=[d[0] for d in DUPLICATES])
def test_duplicate_names_across_every_kind_are_rejected_with_the_names(label: str, build: Callable[[], tuple[Any, ...]], names: list[str]) -> None:
    # INV-3, EC-5: two results with one name would be indistinguishable to the caller.
    with pytest.raises(ConfigurationError) as raised:
        JevAlignmentSettings(skills=build())
    assert raised.value.details == {"names": names}


@pytest.mark.parametrize("bad_value", ["dict", "path", "resolution"])
def test_settings_reject_values_that_are_not_entries_documents_or_strings(bad_value: str) -> None:
    # EC-8, D-4: the error lists the accepted kinds, which now include SkillEntry.
    value = {
        "dict": {"name": "pdf", "type": "github"},
        "path": Path("skills/pdf"),
        "resolution": SkillResolution(reason=SkillUnavailableReason.NOT_FOUND, detail="No SKILL.md at the path checked."),
    }[bad_value]
    with pytest.raises(ConfigurationError) as raised:
        JevAlignmentSettings(skills=(value,))  # type: ignore[arg-type]
    assert "SkillEntry" in str(raised.value)
