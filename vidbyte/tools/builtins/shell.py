"""Context Protocol Header

Description:
    Shell command execution tool using the local sandbox backend.
Purpose:
    Provides a class-based tool that runs shell commands with configurable
    timeout and working directory, returning stdout, stderr, and exit code.
Architecture:
    - ShellTool: Extends BaseTool, delegates execution to LocalSandboxBackend.
    - Wraps SandboxResult into a formatted ToolResult string.
Relations:
    Depends on vidbyte.lib.providers.sandbox.local_backend.LocalSandboxBackend.
"""

from __future__ import annotations

from vidbyte.lib.providers.sandbox.local_backend import LocalSandboxBackend
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

MAX_OUTPUT_CHARS: int = 30000


class ShellTool(BaseTool):
    """Execute a shell command and return the output."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="shell",
            description="Execute a shell command and return stdout and stderr. Use for running builds, tests, installations, and system commands.",
            permission=ToolPermission.EXECUTE,
            parameters=(
                ToolParameter(
                    name="command",
                    type="string",
                    description="The shell command to execute.",
                    required=True,
                ),
                ToolParameter(
                    name="timeout_ms",
                    type="integer",
                    description="Timeout in milliseconds (default 120000).",
                    required=False,
                ),
                ToolParameter(
                    name="workdir",
                    type="string",
                    description="Working directory for the command.",
                    required=False,
                ),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        command: str | None = call.arguments.get("command")
        if not command:
            return ToolResult.error(self.name, "command is required")

        raw_timeout = call.arguments.get("timeout_ms", 120000)
        try:
            timeout_ms = int(raw_timeout)
        except (TypeError, ValueError):
            timeout_ms = 120000
        timeout_ms = max(1000, min(timeout_ms, 600000))

        workdir: str = call.arguments.get("workdir", ".") or "."

        backend = LocalSandboxBackend()
        try:
            result = await backend.execute(command, timeout_ms, workdir, {})
        except Exception as exc:
            return ToolResult.error(self.name, f"Execution error: {exc}")
        finally:
            await backend.cleanup()

        parts: list[str] = [f"Exit code: {result.exit_code}"]
        if result.stdout:
            parts.append(result.stdout.rstrip())
        if result.stderr:
            parts.append(f"STDERR:\n{result.stderr.rstrip()}")

        output = "\n\n".join(p for p in parts if p)

        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + "\n... (output truncated)"

        if result.exit_code == 0:
            return ToolResult.success(self.name, output)
        return ToolResult.error(self.name, output)
