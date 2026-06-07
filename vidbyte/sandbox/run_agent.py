"""Context Protocol Header

Description:
    In-box entrypoint that runs a full agent loop inside a sandbox (Architecture B).
Purpose:
    Loads an AgentManifest, rebuilds the agent from SDK catalogs by resolving
    names, runs the loop, and streams JSONL events to stdout for the host runner.
Architecture:
    - AgentManifestLoader: Rebuilds a BaseAgent from a manifest (names -> tools).
    - main(): CLI that loads, rebuilds, runs (or dry-runs), and emits events.
Relations:
    Launched by vidbyte.lib.runners.sandbox.SandboxAgentRunner via
    `python -m vidbyte.sandbox.run_agent`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence

from vidbyte.lib.dataclasses.sandbox import AgentManifest


class AgentManifestLoader:
    """Rebuilds a BaseAgent from a manifest by resolving names against catalogs."""

    def __init__(self, tool_registry: object | None = None) -> None:
        # Accept an optional pre-populated tool registry for custom tools.
        self._tool_registry = tool_registry

    def rebuild(self, manifest: AgentManifest) -> object:
        # Resolve tools and construct a BaseAgent from the manifest configuration.
        from vidbyte.agents.base import BaseAgent

        tools = self._resolve_tools(manifest.tools)
        return BaseAgent(name=manifest.name, system_prompt=manifest.system_prompt, runtime=manifest.runtime, tools=tools)

    def _resolve_tools(self, names: Sequence[str]) -> list[object]:
        # Map each tool name to an instance, raising clearly on an unknown name.
        catalog = self._catalog()
        resolved: list[object] = []
        for name in names:
            tool = catalog.get(name) if name in catalog else None
            if tool is None:
                raise ValueError(f"Tool '{name}' is not available in this sandbox; install the package that provides it.")
            resolved.append(tool)
        return resolved

    def _catalog(self) -> object:
        # Use the injected registry or build a best-effort builtin catalog.
        if self._tool_registry is not None:
            return self._tool_registry
        return self._default_builtin_catalog()

    def _default_builtin_catalog(self) -> object:
        # Build a registry of zero-argument builtin tools, skipping any that need config.
        from vidbyte.lib.registries.tools import ToolRegistry
        from vidbyte.tools.builtins.calculator import CalculatorTool

        registry = ToolRegistry()
        for tool_cls in (CalculatorTool,):
            try:
                registry.register(tool_cls())
            except Exception:
                continue
        return registry


class SandboxAgentSession:
    """Runs the rebuilt agent in-box and emits JSONL lifecycle events."""

    def __init__(self, manifest: AgentManifest, task: str, *, dry_run: bool) -> None:
        # Bind the session to its manifest, task, and execution mode.
        self._manifest = manifest
        self._task = task
        self._dry_run = dry_run

    async def run(self) -> int:
        # Rebuild the agent, emit a ready event, then run or dry-run the loop.
        try:
            agent = AgentManifestLoader().rebuild(self._manifest)
        except Exception as exc:
            self._emit({"event": "error", "type": type(exc).__name__, "message": str(exc)})
            return 1
        self._emit({"event": "ready", "agent": self._manifest.name, "tools": list(self._manifest.tools), "runtime": self._manifest.runtime})
        if self._dry_run:
            self._emit({"event": "result", "output": f"reconstructed agent '{self._manifest.name}' with {len(self._manifest.tools)} tool(s)", "dry_run": True})
            return 0
        return await self._run_live(agent)

    async def _run_live(self, agent: object) -> int:
        # Execute the agent loop on the task and emit its final output.
        try:
            message = await agent.arun(self._task)
            self._emit({"event": "result", "output": getattr(message, "content", str(message)), "dry_run": False})
            return 0
        except Exception as exc:
            self._emit({"event": "error", "type": type(exc).__name__, "message": str(exc)})
            return 1

    def _emit(self, event: dict[str, object]) -> None:
        # Write one JSON event line to stdout for the host runner to stream.
        sys.stdout.write(json.dumps(event) + "\n")
        sys.stdout.flush()


def main(argv: Sequence[str] | None = None) -> int:
    # Parse arguments, load the manifest and task, and run the in-box session.
    parser = argparse.ArgumentParser(description="Run a Vidbyte agent inside a sandbox.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--task-file", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    with open(args.manifest, encoding="utf-8") as handle:
        manifest = AgentManifest.from_dict(json.load(handle))
    with open(args.task_file, encoding="utf-8") as handle:
        task = handle.read()
    session = SandboxAgentSession(manifest, task, dry_run=args.dry_run)
    return asyncio.run(session.run())


if __name__ == "__main__":
    sys.exit(main())
