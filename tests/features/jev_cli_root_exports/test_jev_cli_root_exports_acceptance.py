"""FILE: tests/features/jev_cli_root_exports/test_jev_cli_root_exports_acceptance.py

PURPOSE: Acceptance test for the JevAgent setting root exports: the spec section 4 snippet, which builds JevAgentSettings, JevComputeSettings and a JevAgent from top-level vidbyte names alone (AgentLoopSettings, PermissionPolicy, TextModelMode and JevDynamicComputeOption among them), runs as written in a fresh interpreter with no provider or Vidbyte key in its environment and prints exactly its four documented lines.
ROLE IN CODEBASE: Covers spec jev-cli-root-exports AC-1, G-1, FR-1 to FR-4 and the user's "I dont want writes to be denied" for vidbyte/__init__.py. It is the workflow vidbyte-cli's services/jev/sdk.py adapter runs, which may import only root names (CLI lint C028).
ARCHITECTURE NOTE: The snippet runs in a child interpreter started with sys.executable, PYTHONPATH set to this checkout, and every environment variable whose name contains API_KEY removed, so a key in the developer's shell cannot hide a construction that needs one. Nothing calls a model.
FUNCTION INVENTORY: test_spec_snippet_builds_jev_settings_from_root_names_alone_with_no_key.
COMMON MODIFICATION PATTERNS: If spec section 4 changes, copy the new snippet and its exact stdout here verbatim; never edit one without the other.
WHAT NOT TO DO IN THIS FILE: 1. Do not change the snippet's imports to sub-package paths to make it pass; root-only imports are the promise under test. 2. Do not loosen the stdout check to a substring or a prefix. 3. Do not add the four names' members or the export count to the expected output.
KNOWN EDGE CASES: The third line is ['fresh_agent', 'clone'] although CLONE is given first, because JevComputeSettings puts options in tie-break order; that is existing behavior this feature must not change. Windows environment names are case-insensitive, so the key filter compares in upper case.
RELATED DOCS: tests/features/jev_cli_root_exports/FEATURE.md; docs/spec/jev-cli-root-exports/spec.md (sections 4, 6.2 AC-1)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/jev_cli_root_exports/test_jev_cli_root_exports_acceptance.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
# Spec section 4, verbatim: what a caller limited to root names writes.
SECTION_4_SNIPPET = """\
import vidbyte
from vidbyte import AgentLoopSettings, JevAgent, JevAgentSettings, JevComputeSettings
from vidbyte import JevDynamicComputeOption, JevRuntimeSettings, PermissionPolicy, TextModelMode

settings = JevAgentSettings(
    name="jev",
    system_prompt="You are a careful coding agent.",
    provider="openai",
    model_name="gpt-5-mini",
    permission_policy=PermissionPolicy.allow_all(),
    loop=AgentLoopSettings(max_iterations=40, max_tool_calls=200, timeout_seconds=900),
    model_mode=TextModelMode.DIRECT,
)
compute = JevComputeSettings(dynamic_compute=(JevDynamicComputeOption.CLONE, JevDynamicComputeOption.FRESH_AGENT))
agent = JevAgent(settings, JevRuntimeSettings(compute=compute))

print(sorted(level.value for level in settings.permission_policy.allowed))
print(settings.loop.max_iterations, settings.model_mode.value)
print([option.value for option in compute.dynamic_compute])
print({"AgentLoopSettings", "PermissionPolicy", "TextModelMode", "JevDynamicComputeOption"} <= set(vidbyte.__all__))
"""
SECTION_4_STDOUT = [
    "['execute', 'read', 'safe', 'write']",
    "40 direct",
    "['fresh_agent', 'clone']",
    "True",
]


def test_spec_snippet_builds_jev_settings_from_root_names_alone_with_no_key() -> None:
    # AC-1: a key left in the shell would hide a construction that
    # needs one, and the CLI's offline commands read no key.
    environment = {
        name: value
        for name, value in os.environ.items()
        if "API_KEY" not in name.upper()
    }
    environment["PYTHONPATH"] = str(REPO_ROOT)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    finished = subprocess.run(
        [sys.executable, "-c", SECTION_4_SNIPPET],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        stdin=subprocess.DEVNULL,
        env=environment,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr[-2000:]
    assert finished.stdout.splitlines() == SECTION_4_STDOUT
