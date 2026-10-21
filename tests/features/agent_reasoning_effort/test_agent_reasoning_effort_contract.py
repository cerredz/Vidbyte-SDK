"""FILE: tests/features/agent_reasoning_effort/test_agent_reasoning_effort_contract.py

PURPOSE: Contract tests for the public shapes the reasoning effort adds: the
ReasoningEffort enum (six StrEnum members in order), the three root names and their
identities, a fresh-interpreter import, contracts/sdk-public-api.json, the one root
header bullet, the package exports of the table and the registry, the keyword-only
parameters of section 8.5, REASONING_EFFORT_AS_OF, and the registries README section
the no-row refusal points to.
ROLE IN CODEBASE: Covers spec AC-13, FR-1, FR-3, FR-10, INV-11 (the sources pointer
resolves), INV-12, INV-19 (keyword-only additions) and D-17 for vidbyte/__init__.py,
vidbyte/lib/enums, vidbyte/lib/configs, vidbyte/lib/registries and the agent
signatures. vidbyte-cli C4 and C5 may import only root names the vendored contract
lists, so these are the names they build JevAgent with.
ARCHITECTURE NOTE: In-process checks against the real packages, plus one subprocess
with a clean environment for the fresh-interpreter import. The contract check reads
the committed JSON and pyproject.toml, so it is red by design between the source
commit and the contract commit (spec section 12.6). Nothing under docs/ is read.
FUNCTION INVENTORY: header_bullet returns one header bullet with its wrapped lines;
the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: A further root name is a spec change first, then one
ROOT_NAMES entry. A new carrier of the effort adds one SIGNATURES row.
WHAT NOT TO DO IN THIS FILE: 1. Do not pin an export count, a version literal or the
REASONING_EFFORT_AS_OF value; later releases and table checks must keep this green.
2. Do not loosen identity to equality. 3. Do not read anything under docs/.
4. Do not import a feature name at module level outside the FEATURE_MISSING guard.
KNOWN EDGE CASES: The header bullet wraps, so it runs until a blank line, the next
bullet or the next header field. vidbyte.lib.configs is dependency-light, so its
names are checked by import, not by reading the file.
RELATED DOCS: docs/spec/agent-reasoning-effort/spec.md sections 6.2 AC-13, 7 FR-1,
FR-3, FR-10, 8.5 and 12.3 rows 1-3a, 27-29; tests/features/agent_reasoning_effort/FEATURE.md.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/agent_reasoning_effort/test_agent_reasoning_effort_contract.py
"""

from __future__ import annotations

import ast
import datetime
import enum
import importlib
import inspect
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from tests.features.agent_reasoning_effort.agent_reasoning_effort_fixtures import (
    ENUM_ORDER,
)
from vidbyte.agents.base import BaseAgent
from vidbyte.agents.fallback import AgentFallback
from vidbyte.agents.settings.fallback import AgentFallbackSettings
from vidbyte.lib.runners.utility import Runner

FEATURE_MISSING: ImportError | None = None
try:
    from vidbyte.lib.configs import (
        GEMINI_THINKING_BUDGET_OFF,
        REASONING_EFFORT_AS_OF,
        REASONING_EFFORT_FORMS,
        REASONING_EFFORT_SUPPORT,
    )
    from vidbyte.lib.enums import ModelProvider, ReasoningEffort
    from vidbyte.lib.registries import ReasoningEffortRegistry
# Red until the feature lands; the rest of the suite must still collect.
except ImportError as missing:
    FEATURE_MISSING = missing

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "contracts" / "sdk-public-api.json"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
ROOT_INIT_PATH = REPO_ROOT / "vidbyte" / "__init__.py"
REGISTRIES_README_PATH = REPO_ROOT / "vidbyte" / "lib" / "registries" / "README.md"
# Spec INV-12: each root name and the module that defines it.
ROOT_NAMES = {
    "ReasoningEffort": "vidbyte.lib.enums",
    "DecisionModelConfig": "vidbyte.lib.dataclasses.model_configs",
    "DecisionModelMode": "vidbyte.lib.enums",
}
HEADER_BULLET = "- Agent setting exports:"
# A header bullet ends at the next bullet, header field, or comment.
PART_BREAK = re.compile(r"^(\s*- |[A-Z][A-Za-z /]*:|#)")
TABLE_NAMES = (
    "REASONING_EFFORT_AS_OF",
    "REASONING_EFFORT_FORMS",
    "REASONING_EFFORT_SUPPORT",
)
# Spec section 8.5: every carrier takes reasoning_effort keyword-only, default None.
SIGNATURES = (
    ("BaseAgent.__init__", BaseAgent.__init__),
    ("Runner.__init__", Runner.__init__),
    ("AgentFallback.__init__", AgentFallback.__init__),
    ("AgentFallbackSettings.to_fallback", AgentFallbackSettings.to_fallback),
)


@pytest.fixture(autouse=True)
def _feature_present() -> None:
    if FEATURE_MISSING is not None:
        raise FEATURE_MISSING.with_traceback(None)


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


def test_reasoning_effort_is_a_str_enum_with_the_six_values_in_order() -> None:
    # FR-1, D-11: the order is the order every refusal lists; StrEnum
    # makes str() and f-strings give the value on the wire and in texts.
    text_model = importlib.import_module("vidbyte.lib.enums.text_model")
    enums = importlib.import_module("vidbyte.lib.enums")

    assert issubclass(ReasoningEffort, enum.StrEnum)
    assert tuple(member.value for member in ReasoningEffort) == ENUM_ORDER
    assert [member.name for member in ReasoningEffort] == [
        value.upper() for value in ENUM_ORDER
    ]
    assert f"{ReasoningEffort.XHIGH}" == str(ReasoningEffort.XHIGH) == "xhigh"
    assert text_model.ReasoningEffort is enums.ReasoningEffort is ReasoningEffort
    assert enums.__all__.count("ReasoningEffort") == 1


def test_each_root_name_is_the_defining_object_and_listed_once() -> None:
    # AC-13, INV-12: a copy would break isinstance checks in
    # JevRuntimeSettings; an unlisted name never reaches the CLI.
    root = importlib.import_module("vidbyte")

    for name, module_path in ROOT_NAMES.items():
        assert getattr(root, name) is getattr(
            importlib.import_module(module_path), name
        ), name
        assert root.__all__.count(name) == 1, name


def test_a_fresh_interpreter_imports_the_three_root_names() -> None:
    # AC-13: `from vidbyte import ...` works with nothing else imported
    # first, as it will in vidbyte-cli.
    code = """
from vidbyte import ReasoningEffort, DecisionModelConfig, DecisionModelMode
import vidbyte.lib.enums as e
import vidbyte.lib.dataclasses.model_configs as m
assert ReasoningEffort is e.ReasoningEffort and DecisionModelMode is e.DecisionModelMode
assert DecisionModelConfig is m.DecisionModelConfig
print(','.join(member.value for member in ReasoningEffort))
"""
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.endswith("_API_KEY")
    }
    environment["PYTHONPATH"] = str(REPO_ROOT)
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == ",".join(ENUM_ORDER)


def test_the_public_api_contract_lists_the_three_names_at_the_package_version() -> None:
    # AC-13, FR-10: vidbyte-cli vendors this file; a superset check and a
    # version equality keep this green as later PRs add exports.
    root = importlib.import_module("vidbyte")
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))

    missing = sorted(set(ROOT_NAMES) - set(contract["exports"]))
    assert missing == [], (
        "commit vidbyte/__init__.py, then run scripts/generate-sdk-public-api.py; never edit the contract by hand"
    )
    assert set(contract["exports"]) == set(root.__all__)
    assert contract["version"] == pyproject["project"]["version"] == root.__version__


def test_the_root_header_has_one_agent_setting_exports_bullet_naming_the_three() -> (
    None
):
    # AC-13: one bullet explains every root setting name; a second copy
    # would drift from the first.
    tree = ast.parse(ROOT_INIT_PATH.read_text(encoding="utf-8"))
    docstring = ast.get_docstring(tree, clean=False) or ""
    starts = [
        line
        for line in docstring.splitlines()
        if line.strip().startswith(HEADER_BULLET)
    ]

    assert len(starts) == 1, f"want one {HEADER_BULLET!r} bullet: {starts}"
    bullet = header_bullet(docstring, HEADER_BULLET)
    assert [
        name for name in ROOT_NAMES if not re.search(rf"\b{name}\b", bullet)
    ] == [], bullet


def test_the_tables_and_the_registry_are_exported_where_the_spec_puts_them() -> None:
    # FR-3, D-17: the registry re-exports the very table objects, so a
    # second copy can never drift from the one the adapters read.
    configs = importlib.import_module("vidbyte.lib.configs")
    registries = importlib.import_module("vidbyte.lib.registries")
    table_module = importlib.import_module("vidbyte.lib.configs.reasoning_effort")

    for name in (*TABLE_NAMES, "GEMINI_THINKING_BUDGET_OFF"):
        assert configs.__all__.count(name) == 1, name
        assert getattr(configs, name) is getattr(table_module, name), name
    for name in TABLE_NAMES:
        assert registries.__all__.count(name) == 1, name
        assert getattr(registries, name) is getattr(table_module, name), name
    registry_module = importlib.import_module("vidbyte.lib.registries.reasoning_effort")
    assert (
        registries.ReasoningEffortRegistry
        is registry_module.ReasoningEffortRegistry
        is ReasoningEffortRegistry
    )
    assert registries.__all__.count("ReasoningEffortRegistry") == 1
    # The Gemini off form uses the named budget, which is zero (G15).
    assert GEMINI_THINKING_BUDGET_OFF == 0
    assert REASONING_EFFORT_FORMS[ModelProvider.GEMINI][ReasoningEffort.NONE] == {
        "generationConfig": {
            "thinkingConfig": {"thinkingBudget": GEMINI_THINKING_BUDGET_OFF}
        }
    }
    assert all(
        isinstance(provider, ModelProvider)
        for provider in (*REASONING_EFFORT_FORMS, *REASONING_EFFORT_SUPPORT)
    )


@pytest.mark.parametrize(
    ("label", "function"), SIGNATURES, ids=[label for label, _ in SIGNATURES]
)
def test_each_carrier_takes_the_effort_keyword_only_with_default_none(
    label: str, function: object
) -> None:
    # Section 8.5, INV-19: a keyword-only addition keeps every existing
    # positional call working; the default None means "send nothing".
    parameter = inspect.signature(function).parameters.get("reasoning_effort")

    assert parameter is not None, label
    assert (parameter.kind, parameter.default) == (
        inspect.Parameter.KEYWORD_ONLY,
        None,
    ), label


def test_the_guard_is_a_keyword_only_static_method() -> None:
    # Section 8.5, D-5: BaseAgent calls the guard by keyword with the
    # agent name, its runner config and its fallback.
    guard = importlib.import_module(
        "vidbyte.agents.reasoning_effort"
    ).AgentReasoningEffortGuard
    raw = inspect.getattr_static(guard, "refuse_unsupported")
    parameters = inspect.signature(guard.refuse_unsupported).parameters

    assert isinstance(raw, staticmethod)
    assert list(parameters) == ["agent_name", "runner_config", "fallback"]
    assert {parameter.kind for parameter in parameters.values()} == {
        inspect.Parameter.KEYWORD_ONLY
    }


def test_the_table_date_is_an_iso_date_and_its_sources_section_exists() -> None:
    # INV-11, EC-10, NFR-4: the no-row text names this date and points
    # to "Reasoning Effort Sources"; the pointer must lead somewhere.
    as_of = datetime.date.fromisoformat(REASONING_EFFORT_AS_OF)
    readme = REGISTRIES_README_PATH.read_text(encoding="utf-8")

    assert as_of.isoformat() == REASONING_EFFORT_AS_OF
    assert re.search(r"^## Reasoning Effort Sources\s*$", readme, flags=re.MULTILINE), (
        "vidbyte/lib/registries/README.md lacks the section the no-row refusal names"
    )
