"""FILE: vidbyte/agents/jev/gate/read_only.py

PURPOSE: Implements JevReadOnly, the step the READ_ONLY preflight case turns on for one run: a SAFE/READ permission ceiling over everything the run starts, and a main-agent catalog that keeps only SAFE and READ tools.
ROLE IN CODEBASE: JevRuntime opens JevReadOnly.ceiling() around every step after the gate when JevPreflightGate.read_only_requested is True, and narrows the main agent's user tools through JevReadOnly.tools() just before the tool selector runs.
ARCHITECTURE NOTE: Hiding tools is the same per-run lever the tool selector uses, keyed on ToolPermission instead of relevance, so the model never sees a tool it may not call. The ceiling (vidbyte/lib/permission_ceiling.py) is what makes the run unable to write: PermissionPolicy.check consults it for every agent the run starts, including a specialist, bulk-work agents, clones, swarm helpers, and forks that carry their own policies and catalogs.
COMMON MODIFICATION PATTERNS: Keep the permission set in PermissionCeiling.READ_ONLY so the hidden catalog and the enforced ceiling can never disagree.
KNOWN EDGE CASES: A run that is not read-only gets nullcontext() and its catalog unchanged. An empty catalog stays empty. A tool whose spec declares no permission is SAFE by ToolSpec's default, so it is kept.
RELATED DOCS: docs/design/jev-read-only-intent.md and skills/jev-agent/SKILL.md.
TESTS: tests/features/jev_read_only/test_jev_read_only.py and scripts/test-jev-read-only.py.
"""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext

from vidbyte.lib.permission_ceiling import PermissionCeiling
from vidbyte.tools.catalog import Tools


class JevReadOnly:
    """The action READ_ONLY's gate case turns on for one run: a SAFE/READ ceiling over every agent the run starts, and a main-agent catalog of only SAFE and READ tools."""

    @staticmethod
    def ceiling(read_only: bool) -> AbstractContextManager[object]:
        # Returns the scope that caps this run, and every agent and task
        # it starts, at SAFE and READ tools, or a no-op scope otherwise.
        return PermissionCeiling.scope(PermissionCeiling.READ_ONLY) if read_only else nullcontext()

    @staticmethod
    def tools(tools: Tools) -> Tools:
        # Returns the catalog with every tool above READ removed, in the
        # original order, so the model is only offered tools it may call.
        return tools.subset(tool.name for tool in tools if tool.spec().permission in PermissionCeiling.READ_ONLY)


__all__ = ["JevReadOnly"]
