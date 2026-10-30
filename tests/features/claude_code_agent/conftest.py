"""FILE: tests/features/claude_code_agent/conftest.py

PURPOSE: Provides the `sandbox` fixture of the offline Claude Code harness agent tests: a ClaudeSandbox whose PATH holds only the `claude` stand-in, with temp folders redirected and credentials cleared.
ROLE IN CODEBASE: Picked up by pytest for every test in this folder; the helpers themselves live in claude_code_support.py, which tests import by module path.
ARCHITECTURE NOTE: The fixture only delegates to make_sandbox, so the environment patching is written once.
COMMON MODIFICATION PATTERNS: A new shared fixture goes here and calls a helper in claude_code_support.py.
KNOWN EDGE CASES: monkeypatch undoes the PATH, temp folder and variable changes after each test.
RELATED DOCS: tests/features/claude_code_agent/FEATURE.md
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/claude_code_agent
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.features.claude_code_agent.claude_code_support import (
    ClaudeSandbox,
    make_sandbox,
)


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ClaudeSandbox:
    """A sandbox with only the claude stand-in on PATH and no credentials in the environment."""
    return make_sandbox(tmp_path, monkeypatch)
