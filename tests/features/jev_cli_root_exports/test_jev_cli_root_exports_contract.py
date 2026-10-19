"""FILE: tests/features/jev_cli_root_exports/test_jev_cli_root_exports_contract.py

PURPOSE: Contract tests for the JevAgent setting root exports: AgentLoopSettings, PermissionPolicy, TextModelMode and JevDynamicComputeOption are each listed exactly once in vidbyte.__all__, are the very objects found at every path in their spec INV-2 row (and through `from vidbyte import`), keep their defaults and validation when reached through the root, are listed by contracts/sdk-public-api.json at the package version, and are named by one root header bullet.
ROLE IN CODEBASE: Covers spec jev-cli-root-exports AC-2, AC-4, AC-8, AC-11, INV-1, INV-2, INV-4, INV-7, INV-10, INV-13, FR-1 to FR-5, T-1, EC-2 and EC-3 for vidbyte/__init__.py and contracts/sdk-public-api.json. vidbyte-cli may import only root names that the vendored contract lists (its lint C028), so these are the names it builds JevAgent settings with.
ARCHITECTURE NOTE: In-process checks against the real root package and the real defining modules; nothing is mocked. The contract check reads the committed JSON and pyproject.toml directly, as the CLI's lint does, so it is red by design between the source commit and the contract commit (spec section 12.6). The header check reads vidbyte/__init__.py's module docstring and nothing under docs/.
FUNCTION INVENTORY: header_bullet returns one bullet with its wrapped lines; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A new path that re-exports one of the four joins EXPORT_PATHS with listed=True. A further root setting name for the CLI is a spec change first, then one SETTING_NAMES entry and one EXPORT_PATHS row.
WHAT NOT TO DO IN THIS FILE: 1. Do not compare against base_commit, origin/main or the merge base, and do not pin an export count, a module hash or a version literal (spec NG-13); later exports must keep this file green. 2. Do not assert that a name is absent from any module, or sweep module attributes; many modules hold these classes for their own use. 3. Do not loosen identity to equality; a copy breaks JevAgentSettings' isinstance checks. 4. Do not read anything under docs/.
KNOWN EDGE CASES: vidbyte.agents.settings.loop and vidbyte.lib.dataclasses.security have no __all__ entry for their class, so every defining module is checked by attribute only. The header bullet may wrap, so it runs until a blank line, the next bullet, or the next header field.
RELATED DOCS: tests/features/jev_cli_root_exports/FEATURE.md; contracts/README.md; docs/spec/jev-cli-root-exports/spec.md (sections 6.1 INV-1, INV-2, INV-4, INV-7, INV-10, 6.2, 8.5)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_cli_root_exports/test_jev_cli_root_exports_contract.py
"""

from __future__ import annotations

import ast
import importlib
import json
import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "contracts" / "sdk-public-api.json"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
ROOT_INIT_PATH = REPO_ROOT / "vidbyte" / "__init__.py"
SETTING_NAMES = (
    "AgentLoopSettings",
    "PermissionPolicy",
    "TextModelMode",
    "JevDynamicComputeOption",
)
HEADER_BULLET = "- Agent setting exports:"
# A header bullet ends at the next bullet, header field, or comment.
PART_BREAK = re.compile(r"^(\s*- |[A-Z][A-Za-z /]*:|#)")
# Spec INV-2, positive pairings only: (name, module path, whether that
# module also lists the name in its __all__). The first row of each
# name is its defining module.
EXPORT_PATHS = (
    ("AgentLoopSettings", "vidbyte.agents.settings.loop", False),
    ("AgentLoopSettings", "vidbyte.agents.settings", True),
    ("AgentLoopSettings", "vidbyte.agents", True),
    ("PermissionPolicy", "vidbyte.lib.dataclasses.security", False),
    ("PermissionPolicy", "vidbyte.lib.dataclasses", True),
    ("PermissionPolicy", "vidbyte.tools.security", True),
    ("PermissionPolicy", "vidbyte.tools.security.permissions", True),
    ("TextModelMode", "vidbyte.lib.enums.text_model", False),
    ("TextModelMode", "vidbyte.lib.enums", True),
    ("TextModelMode", "vidbyte.lib.config", True),
    ("JevDynamicComputeOption", "vidbyte.lib.enums.jev", False),
    ("JevDynamicComputeOption", "vidbyte.lib.enums", True),
)
DEFINING_MODULES = {name: path for name, path, listed in EXPORT_PATHS if not listed}


def header_bullet(docstring: str, prefix: str) -> str:
    # The bullet that starts with prefix, with its wrapped lines.
    lines = docstring.splitlines()
    for start, line in enumerate(lines):
        if line.strip().startswith(prefix):
            picked = [line]
            for following in lines[start + 1 :]:
                if not following.strip() or PART_BREAK.match(following):
                    break
                picked.append(following)
            return "\n".join(picked)
    return ""


def test_each_setting_name_is_listed_exactly_once_in_the_root_all() -> None:
    # AC-2, INV-1, EC-2, EC-3: an unlisted name never reaches the
    # contract, so the CLI's C028 rejects it; a repeated one is an S015
    # finding that the contract silently collapses.
    root = importlib.import_module("vidbyte")
    counts = {name: root.__all__.count(name) for name in SETTING_NAMES}
    assert counts == dict.fromkeys(SETTING_NAMES, 1)


@pytest.mark.parametrize(
    ("name", "module_path", "listed"),
    EXPORT_PATHS,
    ids=[f"{name}@{path}" for name, path, _ in EXPORT_PATHS],
)
def test_root_name_is_the_same_object_at_every_path_in_its_inv2_row(
    name: str, module_path: str, listed: bool
) -> None:
    # AC-2, INV-2, INV-13: a copy, subclass or wrapper on the root
    # makes JevAgentSettings reject what the CLI builds, and a dropped
    # sub-package path breaks existing SDK imports.
    root = importlib.import_module("vidbyte")
    module = importlib.import_module(module_path)
    assert getattr(root, name) is getattr(module, name), (
        f"vidbyte.{name} must be {module_path}.{name} itself; bind it in vidbyte/__init__.py from the module it already comes from"
    )
    if listed:
        assert name in module.__all__, f"{module_path}.__all__ lost {name}"


def test_from_vidbyte_import_binds_the_defining_objects() -> None:
    # AC-2, FR-1 to FR-4: the statement form the CLI's adapter writes;
    # it runs here, not at collection, so a missing name fails this
    # test with ImportError instead of stopping the whole run.
    from vidbyte import (
        AgentLoopSettings,
        JevDynamicComputeOption,
        PermissionPolicy,
        TextModelMode,
    )

    imported = {
        "AgentLoopSettings": AgentLoopSettings,
        "PermissionPolicy": PermissionPolicy,
        "TextModelMode": TextModelMode,
        "JevDynamicComputeOption": JevDynamicComputeOption,
    }
    different = [
        name
        for name, path in DEFINING_MODULES.items()
        if imported[name] is not getattr(importlib.import_module(path), name)
    ]
    assert different == []


def test_root_permission_policy_keeps_its_default_and_allow_all_permits_every_level() -> (
    None
):
    # AC-2, AC-8, FR-2, T-1: the CLI allows writes by choosing
    # allow_all() itself; the SDK default must stay SAFE and READ, so
    # exporting the class widens nothing for other SDK users.
    root = importlib.import_module("vidbyte")
    levels = root.ToolPermission
    assert root.PermissionPolicy().allowed == frozenset({levels.SAFE, levels.READ})
    allowed = root.PermissionPolicy.allow_all().allowed
    assert allowed == frozenset(levels)
    assert {levels.WRITE, levels.EXECUTE} <= allowed


def test_jev_settings_take_the_root_text_model_mode_and_still_reject_a_string() -> None:
    # AC-8, INV-7: the validator accepts only the enum, which is why the
    # CLI needs TextModelMode at the root; a bare run keeps AUTO.
    root = importlib.import_module("vidbyte")
    required = {
        "name": "jev",
        "system_prompt": "You are a careful coding agent.",
        "provider": "openai",
        "model_name": "gpt-5-mini",
    }
    assert root.JevAgentSettings(**required).model_mode is root.TextModelMode.AUTO
    direct = root.JevAgentSettings(**required, model_mode=root.TextModelMode.DIRECT)
    assert direct.model_mode is root.TextModelMode.DIRECT
    with pytest.raises(root.ConfigurationError, match="model_mode"):
        root.JevAgentSettings(**required, model_mode="direct")


def test_public_api_contract_lists_the_four_names_at_the_package_version() -> None:
    # AC-4, INV-4, FR-5: vidbyte-cli vendors this file, so it must list
    # the four. A superset check and a version equality keep this green
    # when later PRs add exports or bump the version.
    root = importlib.import_module("vidbyte")
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    missing = sorted(set(SETTING_NAMES) - set(contract["exports"]))
    assert missing == [], (
        "commit vidbyte/__init__.py, then run scripts/generate-sdk-public-api.py; never edit the contract by hand"
    )
    assert contract["version"] == pyproject["project"]["version"] == root.__version__


def test_root_header_has_one_agent_setting_exports_bullet_naming_the_four() -> None:
    # AC-11, INV-10: the header is where a maintainer learns why these
    # four are root names; a second copy of the bullet would drift.
    tree = ast.parse(ROOT_INIT_PATH.read_text(encoding="utf-8"))
    docstring = ast.get_docstring(tree, clean=False) or ""
    starts = [
        line
        for line in docstring.splitlines()
        if line.strip().startswith(HEADER_BULLET)
    ]
    assert len(starts) == 1, f"want one {HEADER_BULLET!r} bullet: {starts}"
    bullet = header_bullet(docstring, HEADER_BULLET)
    unnamed = [name for name in SETTING_NAMES if not re.search(rf"\b{name}\b", bullet)]
    assert unnamed == [], bullet
