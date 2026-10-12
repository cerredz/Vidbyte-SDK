"""FILE: tests/features/jev_skills_preload/test_skill_sources_contract.py

PURPOSE: Pin the public contract of skill sources: the nine new names are one object across every export path, SkillDocument stays exported everywhere, SkillFetchStep stays internal, the enum wire values match the spec, and the two result records (JevSkillResult and SkillResolution) refuse every state the spec forbids.
ROLE IN CODEBASE: Covers spec AC-17, INV-17, INV-21, FR-13, FR-15 and section 8.5 for vidbyte/__init__.py, vidbyte/agents/__init__.py, vidbyte/agents/jev/__init__.py, vidbyte/lib/__init__.py, vidbyte/lib/dataclasses/__init__.py, vidbyte/lib/enums/__init__.py, vidbyte/lib/dataclasses/skills.py and vidbyte/lib/dataclasses/jev.py.
ARCHITECTURE NOTE: Pure import and record checks; no agent runs. The contract file itself (contracts/sdk-public-api.json) is checked by lint rule C016 and scripts/generate-sdk-public-api.py --check, not here.
FUNCTION INVENTORY: test_public_names_are_one_object_across_every_export_path; test_enum_values_are_the_documented_wire_values; test_skill_result_carries_a_reason_exactly_when_unavailable; test_resolution_is_either_a_document_or_an_explained_reason.
COMMON MODIFICATION PATTERNS: A new public skill name joins the export table; a new reason joins the enum value table and, if it is transient, the transient case.
WHAT NOT TO DO IN THIS FILE: 1. Do not compare against the generated contract JSON; C016 owns that. 2. Do not loosen the identity checks to equality; two copies of a class break isinstance checks.
KNOWN EDGE CASES: SkillFetchStep is exported from vidbyte.lib.enums only (spec R-17), so its absence from the root is part of the contract.
RELATED DOCS: docs/spec/jev-skill-sources/spec.md (sections 8.5, 9.1, 9.2); contracts/README.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_skills_preload/test_skill_sources_contract.py
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from vidbyte.lib.errors import ConfigurationError

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte import (
        JevSkillStatus,
        SkillDocument,
        SkillSourceType,
        SkillUnavailableReason,
    )
    from vidbyte.lib.dataclasses.jev import JevSkillResult
    from vidbyte.lib.dataclasses.skills import SkillResolution
    from vidbyte.lib.enums import SkillFetchStep
except ImportError as missing:  # red until the feature lands; the rest of the suite must still collect
    FEATURE_MISSING = missing

ENTRY_NAMES = ("SkillEntry", "InlineSkill", "LocalSkill", "SkillsShSkill", "GitHubSkill", "AnthropicSkill", "OpenAISkill")
ENUM_NAMES = ("SkillSourceType", "SkillUnavailableReason")
ENTRY_EXPORTERS = ("vidbyte", "vidbyte.agents", "vidbyte.agents.jev", "vidbyte.lib", "vidbyte.lib.dataclasses")
ENUM_EXPORTERS = ("vidbyte", "vidbyte.agents", "vidbyte.agents.jev", "vidbyte.lib.enums")


@pytest.fixture(autouse=True)
def _feature_present() -> None:
    # Fails every test at setup with the import error until the feature exists, instead of skipping it; the
    # traceback is reset so repeated raises of the one stored error do not grow its traceback test after test.
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


def test_public_names_are_one_object_across_every_export_path() -> None:
    # AC-17, FR-15, INV-21: a second copy of a class breaks isinstance in settings; a name missing from __all__ fails S015.
    for names, exporters in ((ENTRY_NAMES, ENTRY_EXPORTERS), (ENUM_NAMES, ENUM_EXPORTERS), (("SkillDocument",), ENTRY_EXPORTERS)):
        for name in names:
            modules = [importlib.import_module(path) for path in exporters]
            objects = {path: getattr(module, name, None) for path, module in zip(exporters, modules, strict=True)}
            assert len({id(obj) for obj in objects.values()}) == 1 and None not in objects.values(), f"{name}: {objects}"
            for path, module in zip(exporters, modules, strict=True):
                assert name in module.__all__, f"{name} missing from {path}.__all__"
    root = importlib.import_module("vidbyte")
    assert root.SkillDocument is SkillDocument
    assert root.JevSkillStatus is JevSkillStatus
    # R-17: the step enum names fetch steps in details; it is internal, never a root export.
    enums = importlib.import_module("vidbyte.lib.enums")
    assert enums.SkillFetchStep is SkillFetchStep and "SkillFetchStep" in enums.__all__
    assert not hasattr(root, "SkillFetchStep") and "SkillFetchStep" not in root.__all__
    assert not hasattr(importlib.import_module("vidbyte.agents.jev"), "SkillFetchStep")


def test_enum_values_are_the_documented_wire_values() -> None:
    # Sec 8.5: results print reason.value and saved settings carry type.value, so the strings are a contract.
    assert {member.name: member.value for member in SkillSourceType} == {
        "INLINE": "inline", "LOCAL": "local", "SKILLS_SH": "skills_sh", "GITHUB": "github", "ANTHROPIC": "anthropic", "OPENAI": "openai",
    }
    assert {member.name: member.value for member in SkillUnavailableReason} == {
        "NOT_INSTALLED": "not_installed", "NOT_FOUND": "not_found", "AUTH_FAILED": "auth_failed", "RATE_LIMITED": "rate_limited",
        "FETCH_FAILED": "fetch_failed", "INVALID_SKILL": "invalid_skill", "TOO_LARGE": "too_large", "DECISION_FAILED": "decision_failed",
    }
    assert {member.name: member.value for member in SkillFetchStep} == {
        "GITHUB_COMMIT": "github_commit", "GITHUB_TREE": "github_tree", "GITHUB_FILE": "github_file", "VENDOR_CONTENT": "vendor_content", "VENDOR_METADATA": "vendor_metadata",
    }


def _result(**overrides: Any) -> Any:
    fields: dict[str, Any] = {"name": "pdf", "description": "Reads PDFs.", "source": "github:anthropics/skills@0123456789ab/skills/pdf/SKILL.md", "status": JevSkillStatus.SELECTED, "probability": 0.9}
    return JevSkillResult(**{**fields, **overrides})


def test_skill_result_carries_a_reason_exactly_when_unavailable() -> None:
    # INV-17: a result is UNAVAILABLE iff it has a reason, has a reason iff it has a non-blank detail, and only a never-loaded result lacks a description.
    unavailable = {"status": JevSkillStatus.UNAVAILABLE, "probability": None}
    never_loaded = _result(**unavailable, description=None, source=None, reason=SkillUnavailableReason.NOT_INSTALLED, detail="Run npx skills add o/r --skill pdf.")
    assert (never_loaded.reason, never_loaded.description, never_loaded.source) == (SkillUnavailableReason.NOT_INSTALLED, None, None)
    assert _result().reason is None and _result().detail is None
    forbidden = [
        {**unavailable},
        {**unavailable, "reason": SkillUnavailableReason.NOT_FOUND},
        {**unavailable, "reason": SkillUnavailableReason.NOT_FOUND, "detail": "   "},
        {**unavailable, "detail": "A detail without a reason."},
        {"reason": SkillUnavailableReason.DECISION_FAILED, "detail": "Selected skills carry no reason."},
        {"status": JevSkillStatus.SKIPPED, "probability": 0.1, "detail": "Skipped skills carry no detail."},
        {"description": None},
        {**unavailable, "reason": "not_found", "detail": "A reason must be the enum, not its text."},
    ]
    for overrides in forbidden:
        with pytest.raises(ConfigurationError):
            _result(**overrides)


def test_resolution_is_either_a_document_or_an_explained_reason() -> None:
    # Sec 9.1: exactly one of a document, or a reason with a non-blank detail; transient is derived from the reason (C002).
    document = SkillDocument(name="pdf", description="Reads PDFs.", text="Body.", source="inline")
    assert SkillResolution(document=document).transient is False
    transient = {SkillUnavailableReason.RATE_LIMITED, SkillUnavailableReason.FETCH_FAILED}
    for reason in SkillUnavailableReason:
        assert SkillResolution(reason=reason, detail="Explained.").transient is (reason in transient)
    for overrides in ({}, {"document": document, "reason": SkillUnavailableReason.NOT_FOUND, "detail": "Both."}, {"reason": SkillUnavailableReason.NOT_FOUND}, {"reason": SkillUnavailableReason.NOT_FOUND, "detail": " "}, {"detail": "No reason."}):
        with pytest.raises((ConfigurationError, TypeError, ValueError)):
            SkillResolution(**overrides)
