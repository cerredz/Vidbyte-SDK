"""Context Protocol Header

Description:
    Host-side runner that runs a full agent loop inside a sandbox (Architecture B).
Purpose:
    Serializes an agent into a manifest, ships it into the box, launches the
    in-box entrypoint, streams JSONL events back, and assembles an AgentResult.
Architecture:
    - SandboxAgentRunner: serialize -> upload -> launch+stream -> assemble.
Relations:
    Uses vidbyte.lib.dataclasses.sandbox.Sandbox and AgentManifest; launches
    vidbyte.sandbox.run_agent in the box.
"""

from __future__ import annotations

import json
from typing import Any

from vidbyte.lib.dataclasses.sandbox import AgentManifest, Sandbox
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.lib.errors import AgentExecutionError

_MANIFEST_PATH = ".vidbyte_agent.json"
_TASK_PATH = ".vidbyte_task.txt"


class SandboxAgentRunner:
    """Runs an agent's full loop inside a sandbox and returns its result."""

    def __init__(self, sandbox: Sandbox, *, python_executable: str = "python") -> None:
        # Bind the runner to a live sandbox and the in-box interpreter name.
        self._sandbox = sandbox
        self._python = python_executable

    async def run(self, agent: object, task: str, *, dry_run: bool = False) -> AgentResult:
        # Ship the agent into the box, run its loop there, and return the result.
        manifest = self._serialize_agent(agent)
        await self._upload_inputs(manifest, task)
        events = await self._launch_and_stream(dry_run)
        return self._assemble_result(events, manifest)

    def _serialize_agent(self, agent: object) -> AgentManifest:
        # Build a manifest from the agent, naming tools rather than serializing code.
        tools = self._tool_names(agent)
        runtime = self._runtime_name(agent)
        return AgentManifest(name=getattr(agent, "name", "agent"), system_prompt=getattr(agent, "system_prompt", ""), runtime=runtime, model=self._first_attr(agent, ("model", "_model")), provider=self._first_attr(agent, ("provider", "_provider")), tools=tools)

    async def _upload_inputs(self, manifest: AgentManifest, task: str) -> None:
        # Write the manifest JSON and task text into the box working directory.
        await self._sandbox.write_file(_MANIFEST_PATH, json.dumps(manifest.to_dict()))
        await self._sandbox.write_file(_TASK_PATH, task)

    async def _launch_and_stream(self, dry_run: bool) -> list[dict[str, Any]]:
        # Run the in-box entrypoint and parse its stdout as JSONL events.
        command = [self._python, "-m", "vidbyte.sandbox.run_agent", "--manifest", _MANIFEST_PATH, "--task-file", _TASK_PATH]
        if dry_run:
            command.append("--dry-run")
        result = await self._sandbox.exec(command)
        events = self._parse_events(result.stdout)
        if not events and result.exit_code != 0:
            raise AgentExecutionError("In-box agent produced no events.", details={"exit_code": result.exit_code, "stderr": result.stderr[:500]})
        return events

    def _parse_events(self, stdout: str) -> list[dict[str, Any]]:
        # Parse newline-delimited JSON events, ignoring non-JSON noise lines.
        events: list[dict[str, Any]] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def _assemble_result(self, events: list[dict[str, Any]], manifest: AgentManifest) -> AgentResult:
        # Fold the event stream into an AgentResult, raising on a streamed error.
        error = next((event for event in events if event.get("event") == "error"), None)
        if error is not None:
            raise AgentExecutionError(error.get("message", "In-box agent failed."), details={"type": error.get("type"), "agent": manifest.name})
        final = next((event for event in reversed(events) if event.get("event") == "result"), None)
        if final is None:
            raise AgentExecutionError("In-box agent did not return a result.", details={"agent": manifest.name})
        return AgentResult(output=str(final.get("output", "")), strategy_name="sandbox", metadata={"events": events, "dry_run": bool(final.get("dry_run"))})

    def _tool_names(self, agent: object) -> tuple[str, ...]:
        # Extract tool names from the agent's tools catalog when available.
        tools = getattr(agent, "tools", None)
        if tools is None:
            return ()
        if hasattr(tools, "names"):
            return tuple(tools.names())
        return tuple(getattr(tool, "name", str(tool)) for tool in tools)

    def _runtime_name(self, agent: object) -> str:
        # Resolve the agent's runtime to a lowercase string name.
        runtime = getattr(agent, "runtime_type", None)
        value = getattr(runtime, "value", runtime)
        return str(value) if value is not None else "linear"

    def _first_attr(self, agent: object, names: tuple[str, ...]) -> Any:
        # Return the first present, non-None attribute value among candidates.
        for name in names:
            value = getattr(agent, name, None)
            if value is not None:
                return value if isinstance(value, str) else getattr(value, "value", str(value))
        return None


__all__ = [
    "SandboxAgentRunner",
]
