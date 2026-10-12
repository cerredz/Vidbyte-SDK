"""FILE: vidbyte/agents/coding_context/environment_probe.py

PURPOSE: Defines EnvironmentProbe, which runs the environment section's one `bash -c` probe with the bash tool's own executable and parses its raw records into an EnvironmentProbeResult: the bash version, uname, the system package managers and tools on bash's PATH, and why the probe failed, if it did.
ROLE IN CODEBASE: Called once per CodingAgent by EnvironmentLoader (vidbyte/agents/coding_context/environment.py); reads its script and limits from vidbyte/lib/constants/coding.py and returns EnvironmentProbeResult (vidbyte/lib/dataclasses/coding.py), whose fields EnvironmentContextItem (vidbyte/context/primitives/documents.py) formats.
ARCHITECTURE NOTE: The probe writes to a temporary file, not a pipe, so on Windows a killed launcher whose child still holds the output cannot hang the read. Each result is cached for the process by bash path and PATH value, because neither the tools nor their versions depend on the root folder. Only finished lines are parsed, so output cut by a timeout or the byte cap never yields half a record.
FUNCTION INVENTORY: EnvironmentProbe.run is the narrated main function; _execute runs the script into the temporary file and says why it failed; _read_output reads that file up to the cap; _parse turns the finished tab-separated lines into an EnvironmentProbeResult.
COMMON MODIFICATION PATTERNS: A new tool or system package manager is one more name in CODING_ENVIRONMENT_PROBE_SCRIPT, with no change here. A new kind of record adds one case in _parse and one field on EnvironmentProbeResult and EnvironmentContextItem.
WHAT NOT TO DO IN THIS FILE: 1. Do not read the probe's output through a pipe. 2. Do not raise for a failed probe; the result's error says what failed. 3. Do not format text for the model here; EnvironmentContextItem owns the wording. 4. Do not run a second command; everything bash reports comes from the one script.
KNOWN EDGE CASES: On a timeout, subprocess.run kills bash and the records printed so far are kept; on Windows only Git's launcher is killed, so a hanging tool may keep running. A failed probe is cached too, so a hanging tool costs the time limit once per process. A relative PATH entry is resolved against the root folder of the first agent that ran the probe.
RELATED DOCS: docs/design/coding-agent-environment-context.md; vidbyte/agents/coding_context/README.md
TESTS: tests/features/coding_agent/test_coding_agent_environment.py
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import IO

from vidbyte.lib.constants.coding import (
    CODING_ENVIRONMENT_PROBE_MAX_BYTES,
    CODING_ENVIRONMENT_PROBE_SCRIPT,
    CODING_ENVIRONMENT_PROBE_TIMEOUT_SECONDS,
)
from vidbyte.lib.dataclasses.coding import EnvironmentProbeResult
from vidbyte.lib.dataclasses.context import EnvironmentTool

# Probe results by (bash path, PATH value), so one probe serves every
# agent in the process.
_PROBE_RESULTS: dict[tuple[str, str], EnvironmentProbeResult] = {}


class EnvironmentProbe:
    """Runs the bash probe once per bash and PATH and returns what bash reported."""

    @classmethod
    def run(cls, bash: str | None, root: Path) -> EnvironmentProbeResult:
        """Return what bash reported from root, or an empty result when there is no bash."""
        # With no bash there is nothing to ask; the environment section
        # says so through its shell line instead.
        if bash is None:
            return EnvironmentProbeResult()

        # Reuse an earlier answer from this same bash and PATH, since
        # tools do not change during a run.
        key = (bash, os.environ.get("PATH", ""))
        if key in _PROBE_RESULTS:
            return _PROBE_RESULTS[key]

        # @intent probe-output-goes-to-a-file
        # After a timeout, subprocess.run waits for a pipe to close with
        # no limit. On Windows only Git's launcher is killed and its
        # child keeps a pipe open, so the probe writes to a file.
        with tempfile.TemporaryFile() as output:
            error = cls._execute(bash, root, output)
            text = cls._read_output(output)

        # Turn the raw records into typed facts, keep the failure next
        # to what was printed before it, and remember the answer.
        _PROBE_RESULTS[key] = cls._parse(text, error)
        return _PROBE_RESULTS[key]

    @staticmethod
    def _execute(bash: str, root: Path, output: IO[bytes]) -> str | None:
        """Run the probe script in root with its output going to output, and return why it failed, or None."""
        try:
            completed = subprocess.run([bash, "-c", CODING_ENVIRONMENT_PROBE_SCRIPT], cwd=root, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.DEVNULL, timeout=CODING_ENVIRONMENT_PROBE_TIMEOUT_SECONDS, check=False)
        except subprocess.TimeoutExpired:
            return f"bash did not finish within {CODING_ENVIRONMENT_PROBE_TIMEOUT_SECONDS:g} seconds"
        except OSError as exc:
            return f"bash could not start ({type(exc).__name__})"
        return f"bash exited with code {completed.returncode}" if completed.returncode else None

    @staticmethod
    def _read_output(output: IO[bytes]) -> str:
        """Return what the probe wrote to output, up to the cap, decoded as UTF-8."""
        output.seek(0)
        return output.read(CODING_ENVIRONMENT_PROBE_MAX_BYTES).decode("utf-8", errors="replace")

    @staticmethod
    def _parse(text: str, error: str | None) -> EnvironmentProbeResult:
        """Return the bash, package-manager, and tool records from the finished lines of text, with error kept."""
        bash_version = uname = None
        managers: list[str] = []
        tools: list[EnvironmentTool] = []
        # The last piece after the final newline is unfinished output,
        # cut by a timeout or the cap, so it is dropped.
        for line in text.replace("\r", "").split("\n")[:-1]:
            kind, _, rest = line.partition("\t")
            name, _, detail = rest.partition("\t")
            match kind:
                case "bash":
                    bash_version, uname = name.strip() or None, detail.strip() or None
                case "package-manager" if name.strip():
                    managers.append(name.strip())
                case "tool" if name.strip() and detail.rpartition("\t")[2].strip():
                    # The path is the last field, so a tab inside a
                    # version line stays in the version.
                    version, _, path = detail.rpartition("\t")
                    tools.append(EnvironmentTool(name=name.strip(), version=version.strip(), path=path.strip()))
        return EnvironmentProbeResult(bash_version=bash_version, uname=uname, tools=tuple(tools), package_managers=tuple(managers), error=error)


__all__ = ["EnvironmentProbe"]
