"""FILE: scripts/test-jev-multipart-done-criteria.py

PURPOSE: Runs the focused, network-free JevAgent done-check test suite, including multi-part, expert-depth, claims, and required-actions checks.
ROLE IN CODEBASE: Provides a discoverable feature verification entrypoint alongside the repository's broader CI runner.
ARCHITECTURE NOTE: The script loads the unittest module directly and returns a non-zero process code for any failure.
COMMON MODIFICATION PATTERNS: Keep module loading exhaustive when new done-check test classes are added.
KNOWN EDGE CASES: The repository root is inserted for direct script execution from any current working directory.
RELATED DOCS: docs/design/jev-multipart-done-criteria.md, docs/design/jev-expert-depth-done-criteria.md, docs/design/jev-claims-context.md, docs/design/jev-required-actions-done-criteria.md, and skills/jev-continuation/SKILL.md.
TESTS: This script executes tests/test_jev_done.py.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tests import test_jev_done, test_jev_required_sequence


def main() -> int:
    """Run every focused done-check test and return a shell-friendly status."""
    suite = unittest.TestSuite((
        unittest.defaultTestLoader.loadTestsFromModule(test_jev_done),
        unittest.defaultTestLoader.loadTestsFromModule(test_jev_required_sequence),
    ))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
