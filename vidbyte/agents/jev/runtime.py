"""FILE: vidbyte/agents/jev/runtime.py

PURPOSE: Provides the dedicated execution seam for the opinionated Jev agent.
ROLE IN CODEBASE: RuntimeRegistry maps AgentRuntimeType.JEV to JevRuntime; JevAgent fixes that runtime type while BaseAgent continues to own runner, usage, speed, tracing, and session wiring.
ARCHITECTURE NOTE: The runtime inherits the linear loop; named Jev capabilities hook in through AgentRuntime seams. Dynamic compaction overrides prepare_iteration_history and keeps one JevCompactionRun per run.
COMMON MODIFICATION PATTERNS: Add fixed preflight, compute, or coordination phases around inherited execution while keeping their policy internal.
KNOWN EDGE CASES: With no capability enabled, running performs no Jev decision call and needs no TypeSafe credential. A plain BaseAgent(runtime="jev") has no JevAgentSettings and is refused here. The compaction run restarts whenever a pass reports zero completed iterations.
RELATED DOCS: docs/design/jev-agent-scaffold.md, docs/design/jev-dynamic-compaction.md, and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_agent.py, tests/test_jev_dynamic_compaction.py, and scripts/test-jev-agent-scaffold.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vidbyte.agents.jev.settings import JevAgentSettings
from vidbyte.agents.runtime import AgentRuntime, BaseAgentRuntimeLoopState
from vidbyte.lib.constants.jev_compaction import JEV_COMPACTION_METADATA_KEY
from vidbyte.lib.enums import AgentRuntimeStateKey
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.jev.compaction import JevCompactionRun, JevDynamicCompaction


class JevRuntime(AgentRuntime):
    """Linear runtime seam reserved for opinionated Jev capabilities."""

    def __init__(self, *, jev_settings: JevAgentSettings | None = None, jev_compaction: JevDynamicCompaction | None = None, **kwargs: Any) -> None:
        # Retains the validated settings by identity and delegates all current behavior to AgentRuntime.
        # @intent jev-runtime-needs-jev-settings
        # AgentRuntimeType.JEV is selectable by string, so a generic BaseAgent can reach this class
        # without settings; refusing here names JevAgent instead of failing later on a None field.
        if not isinstance(jev_settings, JevAgentSettings):
            raise ConfigurationError(
                "The 'jev' runtime is only available through JevAgent; construct JevAgent(JevAgentSettings(...)) instead of BaseAgent(runtime='jev').",
                details={"received_jev_settings": type(jev_settings).__name__},
            )
        self.jev_settings = jev_settings
        self.jev_compaction = jev_compaction
        self._compaction_run: JevCompactionRun | None = None
        super().__init__(**kwargs)

    async def prepare_iteration_history(self, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> None:
        """Let dynamic compaction record the latest step and compact finished units before the next model call."""
        if self.jev_compaction is None:
            return
        if self._compaction_run is None or state.iteration_count == 0:
            self._compaction_run = self.jev_compaction.start_run()
        await self.jev_compaction.prepare(self._compaction_run, state, messages)
        key = AgentRuntimeStateKey.RESULT_METADATA.value
        published = dict(state.run_state.get(key) or {})
        published[JEV_COMPACTION_METADATA_KEY] = self._compaction_run.report()
        state.run_state[key] = published


__all__ = ["JevRuntime"]
