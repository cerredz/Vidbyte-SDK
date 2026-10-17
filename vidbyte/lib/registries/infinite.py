"""FILE: vidbyte/lib/registries/infinite.py

PURPOSE: Defines InfiniteMemoryToolRegistry, the one table of which memory tools an InfiniteMemory agent holds: the tools its workspace's memory preset gives every agent, then the tools its role adds, then recall when the recall mode grants it; and which preset workspace tools the recall mode withholds.
ROLE IN CODEBASE: Read by InfiniteAgentMemory.tools (vidbyte/agents/infinite/memory.py), which builds the tools this registry names for the root, each generator, and each verifier, and by InfiniteMemoryAgent (agent.py) and InfinitePair (launch.py), which leave out the workspace tools withheld_tool_names names. The feature tests read it to check every preset and role.
ARCHITECTURE NOTE: Policy lives here as data and construction stays in the agents layer, as in JevPreflightRegistry (vidbyte/lib/jev/preflight/preflight.py): this lib module names the tools by their model-facing names from vidbyte/lib/constants/infinite.py and never imports the tool classes. Every table is a read-only mapping keyed by every member of its enum, the recall tables by the recall mode and then the role.
FUNCTION INVENTORY: tool_names(preset, role, recall_mode) -> the memory tool names the agent holds, preset tools first and recall last; withheld_tool_names(recall_mode, role) -> the workspace tool names the agent does not get.
COMMON MODIFICATION PATTERNS: A new preset or role adds its member to vidbyte/lib/enums/infinite.py and one row here; a new memory tool adds its name constant and its name to the rows that grant it, and a builder in InfiniteAgentMemory.tools.
WHAT NOT TO DO IN THIS FILE: 1. Do not import from vidbyte.agents or vidbyte.tools; name tools by their constants. 2. Do not grant launch_subagent here; the runtime and InfinitePair add it, because it depends on the run, not on the preset.
KNOWN EDGE CASES: The root and a generator hold the same memory tools; they differ in whether a remember commits at once or is staged. Under DIRECT, the default, both recall tables add and withhold nothing, so every agent holds exactly what it held before recall existed. A verifier never gets recall and keeps grep in every mode, because it checks work against exact text. A key missing from either table raises KeyError, which the tests guard against by checking every enum member.
RELATED DOCS: vidbyte/agents/infinite/README.md (presets and tools); vidbyte/lib/registries/README.md
TESTS: tests/features/infinite_memory_agent/test_infinite_memory_contract.py (test_root_is_offered_exactly_the_preset_tools_plus_its_extra and the registry coverage test)
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from vidbyte.lib.constants.infinite import (
    INFINITE_DROP_ENTRY_TOOL_NAME,
    INFINITE_EDIT_FILE_TOOL_NAME,
    INFINITE_RECALL_TOOL_NAME,
    INFINITE_REMEMBER_TOOL_NAME,
    INFINITE_WRITE_NOTE_TOOL_NAME,
)
from vidbyte.lib.enums.infinite import (
    InfiniteAgentRole,
    InfiniteMemoryPreset,
    InfiniteRecallMode,
)


class InfiniteMemoryToolRegistry:
    """Which memory tools an InfiniteMemory agent holds, by its workspace's memory preset and its role."""

    # @intent memory-tools-follow-role-and-preset
    # Only FULL may change written text, and only a verifier judges
    # staged entries, so each agent gets exactly the tools of INV-6.
    _by_preset: Mapping[InfiniteMemoryPreset, tuple[str, ...]] = MappingProxyType(
        {
            InfiniteMemoryPreset.SPARSE: (INFINITE_REMEMBER_TOOL_NAME, INFINITE_WRITE_NOTE_TOOL_NAME),
            InfiniteMemoryPreset.FULL: (INFINITE_REMEMBER_TOOL_NAME, INFINITE_WRITE_NOTE_TOOL_NAME, INFINITE_EDIT_FILE_TOOL_NAME),
        }
    )
    _by_role: Mapping[InfiniteAgentRole, tuple[str, ...]] = MappingProxyType(
        {
            InfiniteAgentRole.ROOT: (),
            InfiniteAgentRole.GENERATOR: (),
            InfiniteAgentRole.VERIFIER: (INFINITE_DROP_ENTRY_TOOL_NAME,),
        }
    )

    # @intent delegated-recall-replaces-grep-for-the-askers
    # Under DELEGATED the root and generators ask a retriever through
    # recall instead of grepping themselves, so they get recall and lose
    # grep while keeping read_lines and search_memory; a verifier checks
    # exact text, so it keeps grep and never gets recall.
    _no_role_tools: Mapping[InfiniteAgentRole, tuple[str, ...]] = MappingProxyType({role: () for role in InfiniteAgentRole})
    _recall_by_mode: Mapping[InfiniteRecallMode, Mapping[InfiniteAgentRole, tuple[str, ...]]] = MappingProxyType(
        {
            InfiniteRecallMode.DIRECT: _no_role_tools,
            InfiniteRecallMode.DELEGATED: MappingProxyType(
                {
                    InfiniteAgentRole.ROOT: (INFINITE_RECALL_TOOL_NAME,),
                    InfiniteAgentRole.GENERATOR: (INFINITE_RECALL_TOOL_NAME,),
                    InfiniteAgentRole.VERIFIER: (),
                }
            ),
        }
    )
    _withheld_by_mode: Mapping[InfiniteRecallMode, Mapping[InfiniteAgentRole, tuple[str, ...]]] = MappingProxyType(
        {
            InfiniteRecallMode.DIRECT: _no_role_tools,
            InfiniteRecallMode.DELEGATED: MappingProxyType(
                {
                    InfiniteAgentRole.ROOT: ("grep",),
                    InfiniteAgentRole.GENERATOR: ("grep",),
                    InfiniteAgentRole.VERIFIER: (),
                }
            ),
        }
    )

    @classmethod
    def tool_names(cls, preset: InfiniteMemoryPreset, role: InfiniteAgentRole, recall_mode: InfiniteRecallMode = InfiniteRecallMode.DIRECT) -> tuple[str, ...]:
        """Return the memory tools an agent holds: its preset's tools, then the tools its role adds, then recall when the recall mode grants it to the role."""
        return (*cls._by_preset[preset], *cls._by_role[role], *cls._recall_by_mode[recall_mode][role])

    @classmethod
    def withheld_tool_names(cls, recall_mode: InfiniteRecallMode, role: InfiniteAgentRole) -> tuple[str, ...]:
        """Return the workspace tools an agent of this role does not get under this recall mode: grep for the root and generators under DELEGATED, otherwise none."""
        return cls._withheld_by_mode[recall_mode][role]


__all__ = ["InfiniteMemoryToolRegistry"]
