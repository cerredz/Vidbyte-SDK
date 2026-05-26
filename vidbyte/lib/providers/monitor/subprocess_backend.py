"""Context Protocol Header

Description:
    Subprocess-based monitor backend using asyncio subprocess management.
Purpose:
    Provides a concrete implementation of BaseMonitorBackend that spawns,
    tracks, and terminates OS-level subprocesses while capturing their output.
Architecture:
    - Maintains a dict of running MonitorInfo entries keyed by UUID.
    - start() uses asyncio.create_subprocess_shell with background line reader.
    - stop() terminates the process and marks status as "completed".
    - read_output() returns lines since a given index with total_lines and status.
Relations:
    Implements vidbyte.lib.providers.monitor.base.BaseMonitorBackend.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from vidbyte.lib.providers.monitor.base import BaseMonitorBackend, MonitorInfo


class SubprocessMonitorBackend(BaseMonitorBackend):
    """Concrete monitor backend powered by asyncio.create_subprocess_shell."""

    def __init__(self) -> None:
        self._monitors: dict[str, MonitorInfo] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    async def start(self, command: str, label: str, workdir: str) -> str:
        """Spawn a subprocess and begin capturing its stdout lines."""
        monitor_id = uuid4().hex

        info = MonitorInfo(
            id=monitor_id,
            label=label or f"monitor-{monitor_id[:8]}",
            command=command,
            status="running",
        )
        self._monitors[monitor_id] = info

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=workdir or ".",
        )
        self._processes[monitor_id] = process
        self._tasks[monitor_id] = asyncio.create_task(
            self._read_lines(monitor_id, process)
        )

        return monitor_id

    async def stop(self, monitor_id: str) -> str:
        """Kill the subprocess and mark the monitor as completed."""
        info = self._monitors.get(monitor_id)
        if info is None:
            return f"Monitor {monitor_id} not found."

        process = self._processes.get(monitor_id)
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass

        task = self._tasks.pop(monitor_id, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        info.status = "completed"
        return f"Monitor {monitor_id} ({info.label}) stopped. Status: {info.status}"

    async def list_monitors(self) -> list[MonitorInfo]:
        """Return a snapshot list of all known monitors."""
        return list(self._monitors.values())

    async def read_output(self, monitor_id: str, since_line: int) -> dict:
        """Return output lines since a given index."""
        info = self._monitors.get(monitor_id)
        if info is None:
            return {"lines": [], "total_lines": 0, "status": "not_found"}

        lines = info.lines[since_line:]
        return {
            "lines": lines,
            "total_lines": len(info.lines),
            "status": info.status,
        }

    async def _read_lines(
        self, monitor_id: str, process: asyncio.subprocess.Process
    ) -> None:
        """Background task that reads stdout lines into MonitorInfo.lines."""
        if process.stdout is None:
            return
        try:
            while True:
                line_bytes = await process.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").rstrip("\n")
                info = self._monitors.get(monitor_id)
                if info is not None:
                    info.lines.append(line)
        except (asyncio.CancelledError, Exception):
            pass
        finally:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            info = self._monitors.get(monitor_id)
            if info is not None and info.status == "running":
                info.status = "error" if process.returncode != 0 else "completed"


__all__ = ["SubprocessMonitorBackend"]
