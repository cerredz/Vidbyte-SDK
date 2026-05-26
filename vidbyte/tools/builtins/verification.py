"""Context Protocol Header

Description:
    Built-in verification tools for running tests and linters.
Purpose:
    Enables agents to verify code changes by running test suites and linting
    tools, returning diagnostics for agent analysis.
Architecture:
    - Uses the @tool decorator with ToolPermission.EXECUTE.
    - verify_run_tests runs a test command with a 120-second timeout.
    - verify_run_lint runs a linter command with a 60-second timeout.
    - Both tools capture stdout and stderr with size limits.
Relations:
    Related to vidbyte.tools.decorators and vidbyte.tools.types.
"""

from __future__ import annotations

import asyncio
import os

from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission


@tool(permission=ToolPermission.EXECUTE)
async def verify_run_tests(test_command: str, workdir: str = ".") -> str:
    """Run tests and return results. Failures are reported for agent analysis.

    Args:
        test_command: The shell command to execute (e.g. 'pytest tests/').
        workdir: Working directory for the command.
    """
    process = await asyncio.create_subprocess_shell(
        test_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=workdir,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
    except asyncio.TimeoutError:
        process.kill()
        return "Tests timed out after 120 seconds."

    output = stdout.decode("utf-8", errors="replace")[:20000]
    if stderr:
        output += "\n\nSTDERR:\n" + stderr.decode("utf-8", errors="replace")[:5000]
    return f"Exit code: {process.returncode}\n\n{output}"


@tool(permission=ToolPermission.EXECUTE)
async def verify_run_lint(
    lint_command: str | None = None,
    file_paths: list[str] | None = None,
) -> str:
    """Run linter and return diagnostics.

    Args:
        lint_command: Optional lint command (defaults to 'python -m flake8').
        file_paths: Optional list of file paths to lint.
    """
    if not lint_command:
        cmd = "python -m flake8"
        if file_paths:
            cmd += " " + " ".join(file_paths)
        else:
            cmd += " ."
        lint_command = cmd

    process = await asyncio.create_subprocess_shell(
        lint_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
    except asyncio.TimeoutError:
        process.kill()
        return "Lint timed out after 60 seconds."

    output = stdout.decode("utf-8", errors="replace")[:10000]
    if not output and process.returncode == 0:
        return "No lint errors found."
    if stderr:
        output += "\n\n" + stderr.decode("utf-8", errors="replace")[:5000]
    return output if output else f"Lint completed with exit code {process.returncode}."
