"""Verification script for configurable isDone activity annotations.

Runs the feature-focused SDK test cases from the design document and exits
non-zero when any contract fails.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "tests/test_agent_base.py",
    "tests/test_agent_runtime.py",
    "tests/test_provider_tool_schema_translation.py",
)


def main() -> int:
    """Run the focused test files with the repository interpreter."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *TESTS, "-q"],
        cwd=ROOT,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

