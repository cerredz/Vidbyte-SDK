"""FILE: scripts/test-coding-agent-environment-context.py

PURPOSE: Thin verification runner for the CodingAgent environment section: runs its feature test module with -v and prints "X/Y tests passed".
ROLE IN CODEBASE: Phase 5 runner for docs/design/coding-agent-environment-context.md; the tests themselves live in tests/features/coding_agent/test_coding_agent_environment.py.
ARCHITECTURE NOTE: Shells out to pytest in a subprocess with an argv list and parses only pytest's own summary counts.
FUNCTION INVENTORY: main runs pytest, prints the summary, and returns pytest's exit code.
COMMON MODIFICATION PATTERNS: None; add tests to the pytest module, not here.
WHAT NOT TO DO IN THIS FILE: 1. Do not duplicate test logic here. 2. Do not import vidbyte; pytest does.
KNOWN EDGE CASES: Run from the repository root with PYTHONPATH set to it, as the feature pack requires.
RELATED DOCS: docs/design/coding-agent-environment-context.md
TESTS: PYTHONPATH=$(pwd) python scripts/test-coding-agent-environment-context.py
"""

from __future__ import annotations

import re
import subprocess
import sys

TEST_MODULE = "tests/features/coding_agent/test_coding_agent_environment.py"


def main() -> int:
    # Run the feature tests verbosely so each case shows PASSED, FAILED, or SKIPPED.
    completed = subprocess.run([sys.executable, "-m", "pytest", "-v", "-p", "no:cacheprovider", TEST_MODULE], capture_output=True, text=True, check=False)
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    counts = {kind: int(number) for number, kind in re.findall(r"(\d+) (passed|failed|skipped|error)", completed.stdout.splitlines()[-1] if completed.stdout else "")}
    total = sum(counts.values())
    sys.stdout.write(f"{counts.get('passed', 0)}/{total} tests passed\n")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
