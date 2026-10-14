"""FILE: tests/features/prebuilt_tools/test_prebuilt_acceptance.py

PURPOSE: Acceptance tests that run in a fresh interpreter: the spec §4 developer snippet must print exactly its documented two lines (AC-1), and importing the SDK must build no tool (AC-5, INV-7).
ROLE IN CODEBASE: Starts sys.executable as a child process with the worktree on PYTHONPATH, the way a developer runs the snippet from a clean checkout; exercises vidbyte.Agent, vidbyte.tools.toolsets.PrebuiltTools, and vidbyte.lib.enums.PrebuiltToolCategory end to end.
ARCHITECTURE NOTE: Child processes keep import side effects and environment changes out of the pytest process. Every *_API_KEY variable is removed from the child's environment, so the snippet also proves that building the agent needs no key.
FUNCTION INVENTORY: run_python runs a script in a child interpreter and returns its completed process; test_developer_snippet_prints_exactly_the_documented_result covers AC-1; test_importing_the_sdk_builds_no_tool covers AC-5 and INV-7.
COMMON MODIFICATION PATTERNS: If spec §4 changes, paste the new snippet and its printed lines verbatim; never edit the snippet to make it pass.
WHAT NOT TO DO IN THIS FILE: 1. Do not import the feature in the pytest process here; the point is a fresh interpreter. 2. Do not give the child an API key or network access; the snippet must work without either.
KNOWN EDGE CASES: Windows prints \r\n, so stdout is compared after normalizing line endings. The child runs in tmp_path so nothing it writes lands in the worktree. sys.setprofile only sees the thread that sets it, which is the importing thread here.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md (§4, §6.2 AC-1 and AC-5)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_acceptance.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CHILD_TIMEOUT_SECONDS = 300

# Spec §4, verbatim.
DEVELOPER_SNIPPET = textwrap.dedent(
    """
    import asyncio

    from vidbyte import Agent
    from vidbyte.lib.enums import PrebuiltToolCategory
    from vidbyte.tools.toolsets import PrebuiltTools
    from vidbyte.tools.types import ToolCall

    # Attach two whole categories to an agent.
    tools = PrebuiltTools([PrebuiltToolCategory.DATES, PrebuiltToolCategory.TEXT_COUNTING])
    agent = Agent(name="assistant", system_prompt="Use tools for exact answers.", provider="openai", model_name="gpt-4.1", tools=tools)

    # Or pick individual tools by name from the full library.
    picked = PrebuiltTools(PrebuiltToolCategory).subset(["days_between_dates", "count_character_occurrences"])
    print(picked.names())

    # Every tool is an ordinary FunctionTool and returns JSON text.
    result = asyncio.run(picked[1].execute(ToolCall("count_character_occurrences", {"text": "strawberry", "character": "r"})))
    print(result.status.value, result.output)
    """
)

# The two lines spec §4 says the snippet prints exactly.
DOCUMENTED_OUTPUT = textwrap.dedent(
    """\
    ('days_between_dates', 'count_character_occurrences')
    success {"count": 3, "positions": [2, 7, 8], "truncated": false}
    """
)

IMPORT_PROBE = textwrap.dedent(
    """
    import json
    import sys

    counts = {"FunctionTool": 0, "Tools": 0}
    owners = {"FunctionTool.__init__": ("FunctionTool", "vidbyte/tools/function_tool.py"), "Tools.__init__": ("Tools", "vidbyte/tools/catalog.py")}

    def observe(frame, event, arg):
        if event != "call" or frame.f_code.co_name != "__init__":
            return
        owner = owners.get(frame.f_code.co_qualname)
        if owner and frame.f_code.co_filename.replace("\\\\", "/").endswith(owner[1]):
            counts[owner[0]] += 1

    sys.setprofile(observe)
    import vidbyte
    import vidbyte.tools.toolsets
    import vidbyte.tools.builtins.prebuilt
    sys.setprofile(None)

    package = sys.modules["vidbyte.tools.builtins.prebuilt"]
    category_classes = sorted(name for name in dir(package) if name.endswith("ToolFunctions"))
    toolsets = sys.modules["vidbyte.tools.toolsets"]
    print(json.dumps({"counts": counts, "has_prebuilt_tools": hasattr(toolsets, "PrebuiltTools"), "category_classes": len(category_classes)}))
    """
)


def child_environment() -> dict[str, str]:
    """The current environment without any API key, with the worktree first on PYTHONPATH and UTF-8 output."""
    environment = {key: value for key, value in os.environ.items() if not key.upper().endswith("_API_KEY")}
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join([str(REPOSITORY_ROOT), existing] if existing else [str(REPOSITORY_ROOT)])
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def run_python(script: str, working_directory: Path) -> subprocess.CompletedProcess[str]:
    """Run a script in a fresh interpreter and capture its text output."""
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=working_directory,
        env=child_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=CHILD_TIMEOUT_SECONDS,
        check=False,
    )


def test_developer_snippet_prints_exactly_the_documented_result(tmp_path: Path) -> None:
    """AC-1: the §4 snippet runs from a clean checkout with no API key and prints exactly the two documented lines."""
    completed = run_python(DEVELOPER_SNIPPET, tmp_path)
    assert completed.returncode == 0, completed.stderr[-3000:]
    assert completed.stdout.replace("\r\n", "\n") == DOCUMENTED_OUTPUT


def test_importing_the_sdk_builds_no_tool(tmp_path: Path) -> None:
    """AC-5 and INV-7: importing vidbyte, vidbyte.tools.toolsets, and the prebuilt package builds no FunctionTool and no Tools."""
    completed = run_python(IMPORT_PROBE, tmp_path)
    assert completed.returncode == 0, completed.stderr[-3000:]
    report = json.loads(completed.stdout.strip().splitlines()[-1])
    assert report["has_prebuilt_tools"] is True
    assert report["category_classes"] == 31
    assert report["counts"] == {"FunctionTool": 0, "Tools": 0}
