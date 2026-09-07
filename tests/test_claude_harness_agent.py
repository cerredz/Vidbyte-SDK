"""FILE: tests/test_claude_harness_agent.py

PURPOSE: Runs the Claude harness agent verification suite under pytest.
ROLE IN CODEBASE: Makes the offline adapter checks part of the repository test gate.
ARCHITECTURE NOTE: Delegates to scripts/test-claude-harness-agent.py to keep one source of truth.
COMMON MODIFICATION PATTERNS: Add a check to the script; this wrapper needs no change.
KNOWN EDGE CASES: The script injects a fake claude_agent_sdk, so no provider install is required.
RELATED DOCS: docs/design/claude-harness-agent.md.
TESTS: python -m pytest tests/test_claude_harness_agent.py
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "test-claude-harness-agent.py"


def _load_suite() -> object:
    """Imports the verification script as a module and returns it."""
    spec = importlib.util.spec_from_file_location("claude_harness_verification", _SCRIPT)
    if spec is None or spec.loader is None:
        raise unittest.SkipTest(f"cannot load {_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ClaudeHarnessAgentSuiteTest(unittest.TestCase):
    """Asserts every design-doc check in the verification script passes."""

    def test_every_registered_check_passes(self) -> None:
        """Runs each check as its own subtest so one failure does not hide the rest."""
        module = _load_suite()
        self.assertTrue(module.SUITE, "the verification suite registered no checks")
        for name, check in module.SUITE:
            with self.subTest(check=name):
                module.reset_fake()
                module.install_fake_sdk()
                check()


if __name__ == "__main__":
    unittest.main()
