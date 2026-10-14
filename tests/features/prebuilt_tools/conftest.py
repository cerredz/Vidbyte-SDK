"""FILE: tests/features/prebuilt_tools/conftest.py

PURPOSE: Shared fixtures for the prebuilt tool feature pack: the two public names under test, the full library built once per session, and a ToolRunner over it.
ROLE IN CODEBASE: Loaded by pytest for every module in tests/features/prebuilt_tools/; builds on prebuilt_tool_harness.ToolRunner and on the public names vidbyte.tools.toolsets.PrebuiltTools and vidbyte.lib.enums.PrebuiltToolCategory (spec §8.5).
ARCHITECTURE NOTE: The feature imports happen inside fixtures, so a missing PrebuiltTools or PrebuiltToolCategory fails each test at setup instead of aborting collection of the whole suite.
FUNCTION INVENTORY: PrebuiltApi holds the two public names; prebuilt_api imports them; prebuilt_library builds PrebuiltTools(PrebuiltToolCategory) once per session; tool_runner wraps that library in a ToolRunner.
COMMON MODIFICATION PATTERNS: Add a fixture here only when two or more modules in this pack need it; keep subprocess helpers in the module that uses them.
WHAT NOT TO DO IN THIS FILE: 1. Do not stub PrebuiltTools or any tool; a missing feature must stay red. 2. Do not reach into vidbyte.tools.builtins.prebuilt; tools are reached through the public toolset (FR-5).
KNOWN EDGE CASES: The session library is shared, which is safe only because tools keep no state (INV-13); tests that need fresh objects build their own PrebuiltTools.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md (§8.5, §13)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

import pytest

from tests.features.prebuilt_tools.prebuilt_tool_harness import ToolRunner


@dataclass(frozen=True, slots=True)
class PrebuiltApi:
    """The two public names the pack binds to: the toolset class and the category enum."""

    tools: Any
    categories: Any


@pytest.fixture(scope="session")
def prebuilt_api() -> PrebuiltApi:
    toolsets = importlib.import_module("vidbyte.tools.toolsets")
    enums = importlib.import_module("vidbyte.lib.enums")
    return PrebuiltApi(tools=toolsets.PrebuiltTools, categories=enums.PrebuiltToolCategory)


@pytest.fixture(scope="session")
def prebuilt_library(prebuilt_api: PrebuiltApi) -> Any:
    return prebuilt_api.tools(prebuilt_api.categories)


@pytest.fixture(scope="session")
def tool_runner(prebuilt_library: Any) -> ToolRunner:
    return ToolRunner(prebuilt_library)
