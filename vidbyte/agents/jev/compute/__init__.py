"""FILE: vidbyte/agents/jev/compute/__init__.py

PURPOSE: Exports JevComputeController, the owner of JevAgent's mid-run compute checkpoint.
ROLE IN CODEBASE: JevAgent builds the controller when JevRuntimeSettings.compute is set, and JevRuntime calls it between the main agent's tool iterations.
ARCHITECTURE NOTE: Mid-run compute lives in this package and the run brief it composes (vidbyte/agents/jev/brief/); the runtime only forwards the hook.
COMMON MODIFICATION PATTERNS: Add a checkpoint step in its own module here and call it from JevComputeController.checkpoint. SWARM lives in swarm.py (helpers), swarm_plan.py (plan reading and checks), and swarm_tool.py (the launch tool).
KNOWN EDGE CASES: With JevRuntimeSettings.compute left None, nothing in this package is built or called.
RELATED DOCS: docs/design/jev-compute-checkpoint.md.
TESTS: tests/test_jev_compute.py.
"""

from __future__ import annotations

from vidbyte.agents.jev.compute.controller import JevComputeController
from vidbyte.agents.jev.compute.facts import JevRunFactsReader
from vidbyte.agents.jev.compute.swarm_tool import JevSwarmTool

__all__ = ["JevComputeController", "JevRunFactsReader", "JevSwarmTool"]
