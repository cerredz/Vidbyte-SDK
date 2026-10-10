"""FILE: scripts/test-jev-runtime-setup-integration.py

PURPOSE: Runs the focused integration test for the combined Jev runtime setup path.
ROLE IN CODEBASE: Provides the executable verification entrypoint documented by the integration design and test module.
ARCHITECTURE NOTE: Loads the complete offline unittest module and returns a shell-friendly nonzero status when any test fails.
COMMON MODIFICATION PATTERNS: Add integration cases to the single loaded module so this entrypoint remains exhaustive.
KNOWN EDGE CASES: The repository root is inserted before imports so direct execution works from any current directory.
RELATED DOCS: `docs/design/jev-runtime-setup-integration.md` and `tests/test_jev_runtime_setup_integration.py`.
TESTS: `python scripts/test-jev-runtime-setup-integration.py`.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tests import test_jev_runtime_setup_integration


def main() -> int:
    # Runs every combined runtime test and returns a shell-friendly status.
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_jev_runtime_setup_integration)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
