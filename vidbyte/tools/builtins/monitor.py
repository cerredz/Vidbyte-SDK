"""Context Protocol Header

Description:
    Built-in monitor tools for starting, stopping, listing, and reading
    long-running subprocesses.
Purpose:
    Enables agents to manage background processes such as dev servers,
    build watchers, or data pipelines without blocking the main loop.
Architecture:
    - Uses the @tool decorator with ToolPermission.EXECUTE and ToolPermission.READ.
    - Delegates to SubprocessMonitorBackend for all process management.
    - Returns human-readable strings for agent consumption.
Relations:
    Related to vidbyte.lib.providers.monitor and vidbyte.tools.decorators.
"""

from __future__ import annotations

import json

from vidbyte.lib.providers.monitor.subprocess_backend import SubprocessMonitorBackend
from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission

_backend = SubprocessMonitorBackend()


@tool(permission=ToolPermission.EXECUTE)
async def monitor_start(command: str, label: str = "", workdir: str = ".") -> str:
    """Start a long-running background process and return a monitor ID.

    Args:
        command: The shell command to execute in the background.
        label: Optional human-readable label for this monitor.
        workdir: Working directory for the command.
    """
    try:
        monitor_id = await _backend.start(command, label, workdir)
        return f"Monitor started.\nID: {monitor_id}\nLabel: {label or monitor_id[:8]}"
    except Exception as exc:
        return f"Error starting monitor: {exc}"


@tool(permission=ToolPermission.EXECUTE)
async def monitor_stop(monitor_id: str) -> str:
    """Stop a running monitor process by its ID.

    Args:
        monitor_id: The monitor ID returned by monitor_start.
    """
    try:
        return await _backend.stop(monitor_id)
    except Exception as exc:
        return f"Error stopping monitor: {exc}"


@tool(permission=ToolPermission.READ)
async def monitor_list() -> str:
    """List all currently running and completed monitors.

    Returns a JSON array with id, label, command, status, and line count for each.
    """
    try:
        monitors = await _backend.list_monitors()
        entries = [
            {
                "id": m.id,
                "label": m.label,
                "command": m.command,
                "status": m.status,
                "lines_count": len(m.lines),
            }
            for m in monitors
        ]
        if not entries:
            return "No monitors found."
        return json.dumps(entries, indent=2)
    except Exception as exc:
        return f"Error listing monitors: {exc}"


@tool(permission=ToolPermission.READ)
async def monitor_read(monitor_id: str, since_line: int = 0) -> str:
    """Read new output lines from a monitor since a given line index.

    Args:
        monitor_id: The monitor ID returned by monitor_start.
        since_line: Return only lines starting from this index (0-based).
    """
    try:
        data = await _backend.read_output(monitor_id, since_line)
        if data["status"] == "not_found":
            return f"Monitor {monitor_id} not found."
        lines_out = "\n".join(data["lines"])
        status_line = f"Status: {data['status']} | Total lines: {data['total_lines']} | New lines: {len(data['lines'])}"
        if lines_out:
            return f"{status_line}\n\n{lines_out}"
        return status_line
    except Exception as exc:
        return f"Error reading monitor output: {exc}"
