"""FILE: vidbyte/agents/agent_swarm/workplace.py

PURPOSE: Defines AgentSwarmWorkplace, the one shared folder of a swarm: it knows the folder's absolute path, creates the folder with any missing parent folders when a run starts, and reports whether that call created it.
ROLE IN CODEBASE: Built by AgentSwarm.arun (swarm.py) from AgentSwarmSettings.workplace, which prepares it before it builds the run's AgentSwarmRuntime over root and passes on prepare's answer, which the run records in its workplace_prepared event; every agent's file tools and bash are rooted at root. Exported by vidbyte/agents/agent_swarm/__init__.py and vidbyte/agents/__init__.py.
ARCHITECTURE NOTE: One role only: the folder exists when a run needs it. Building the object touches no disk, so settings and swarms can be built freely; prepare is the one place the folder is created, and it never deletes, moves, or empties anything, so a later run sees everything an earlier run or the developer left there.
FUNCTION INVENTORY: AgentSwarmWorkplace.__init__ keeps the resolved path; root returns it; prepare creates the folder and its parents and returns True when it created the folder, False when it already existed, or raises ConfigurationError naming the path.
COMMON MODIFICATION PATTERNS: A new check on the folder belongs in prepare, before or after the one mkdir call, and must leave the folder's contents as they were.
WHAT NOT TO DO IN THIS FILE: 1. Do not add a delete, move, or clean method; the folder belongs to the developer. 2. Do not create anything in __init__. 3. Do not swallow an OSError; it becomes a ConfigurationError chained from it.
KNOWN EDGE CASES: A file that appears at the path after the settings were built is refused by prepare, not overwritten. Two swarms sharing one folder at the same time are not guarded against each other. A folder another process creates between the check and the mkdir call is reported as created. Created means the folder itself was missing; missing parents made with it do not change the answer.
RELATED DOCS: docs/spec/agent-swarm-v2/spec.md (sections 6.1 INV-17 and INV-28, and 8.5); vidbyte/agents/agent_swarm/README.md
TESTS: tests/features/agent_swarm/test_agent_swarm_workplace.py
"""

from __future__ import annotations

from pathlib import Path

from vidbyte.lib.errors import ConfigurationError


class AgentSwarmWorkplace:
    """The one folder every agent of a swarm works in; created when a run starts and never cleaned."""

    def __init__(self, root: Path) -> None:
        # Keep the absolute path; nothing on disk is touched yet.
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        """Return the folder's absolute path."""
        return self._root

    def prepare(self) -> bool:
        """Create the folder and any missing parent folders, keep everything already in it, and return True when this call created it."""
        # @intent the-workplace-is-created-never-cleaned
        # An existing folder is used as it is; a file at the path, or a
        # parent that cannot hold a folder, is refused with the path
        # named and the operating system's error as the cause. Whether
        # the folder was there is read before mkdir, so the run can
        # record which of the two happened.
        existed = self._root.is_dir()
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ConfigurationError(f"The swarm workplace {self._root} could not be created as a folder: {type(exc).__name__}.", details={"field": "AgentSwarmSettings.workplace", "path": str(self._root)}) from exc
        return not existed


__all__ = ["AgentSwarmWorkplace"]
