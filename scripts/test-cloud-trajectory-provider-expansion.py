#!/usr/bin/env python3
"""FILE: scripts/test-cloud-trajectory-provider-expansion.py

PURPOSE:
    Provide one executable entry point for every test in the cloud trajectory
    provider expansion feature pack.

ROLE IN CODEBASE:
    Repeatable verification command referenced by the feature pack and design
    document; it does not alter source or cloud resources.

ARCHITECTURE NOTE:
    Delegates to the repository's Python pytest entry point so the same test
    discovery and plugin behavior is used locally and in CI.

COMMON MODIFICATION PATTERNS:
    Update the feature directory in the command only when the pack moves; add
    new cases to the feature tests rather than duplicating pytest logic here.

KNOWN EDGE CASES:
    The script preserves pytest's exit code and must remain usable on Windows
    and POSIX hosts through sys.executable.

RELATED DOCS:
    docs/design/cloud-trajectory-provider-expansion.md

TESTS:
    This script runs tests/features/cloud_trajectory_provider_expansion.
"""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    """Run the feature pack through the repository's pytest entry point."""
    command = [sys.executable, "-m", "pytest", "tests/features/cloud_trajectory_provider_expansion", "-q"]
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
