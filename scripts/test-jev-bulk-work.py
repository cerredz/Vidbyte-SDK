"""FILE: scripts/test-jev-bulk-work.py

PURPOSE: Runs the focused offline Jev bulk-work feature test pack.
ROLE IN CODEBASE: Provides the executable verification entrypoint documented by tests/features/jev_bulk_work/README.md.
ARCHITECTURE NOTE: The script loads the full feature test module and returns a nonzero status when any test fails.
COMMON MODIFICATION PATTERNS: Add tests to the single loaded module so this entrypoint remains exhaustive.
KNOWN EDGE CASES: The repository root is inserted for direct script execution from any current directory.
RELATED DOCS: `docs/design/jev-bulk-work.md` and `tests/features/jev_bulk_work/FEATURE.md`.
TESTS: `python scripts/test-jev-bulk-work.py`.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tests.features.jev_bulk_work import test_jev_bulk_work


def main() -> int:
    # Runs every feature test and turns unittest's result into the script exit status.
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_jev_bulk_work)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
