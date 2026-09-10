"""FILE: vidbyte/integrations/__init__.py

PURPOSE: Public surface of the Sources access layer that connects external provider resources to an agent.
ROLE IN CODEBASE: The single import point for Sources, selections, connections, adapters, and the scope policy they produce.
ARCHITECTURE NOTE: This package composes vidbyte.context, vidbyte.tools, and vidbyte.lib, so it sits above all three rather than inside any of them.
COMMON MODIFICATION PATTERNS: Export a new public type here and add it to the root vidbyte namespace in the same change.
KNOWN EDGE CASES: No concrete provider adapter ships here; the adapter registry starts empty by design.
RELATED DOCS: docs/design/sources-access-layer.md
TESTS: tests/test_sources_access_layer.py and scripts/test_sources_access_layer.py.
"""

from __future__ import annotations

from vidbyte.integrations.adapters import (
    DEFAULT_ADAPTERS,
    AdapterRegistry,
    ProviderAdapter,
)
from vidbyte.integrations.budget import (
    BudgetAdmission,
    ContextAdmissionBudget,
    ToolBudget,
)
from vidbyte.integrations.connections import (
    ConnectionBroker,
    ConnectionRegistry,
    CredentialResolver,
    InMemoryCredentialResolver,
)
from vidbyte.integrations.report import SourcesReport
from vidbyte.integrations.sources import ResolvedSources, Sources, SourcesResolver
from vidbyte.integrations.toolsets import ProviderToolset, ScopedProviderTool
from vidbyte.lib.dataclasses.integrations import (
    AuthorizationResult,
    Connection,
    ContextBudgetPlan,
    Credentials,
    LoadRequest,
    ResourceScope,
    ResourceSelection,
    SelectionReportEntry,
)
from vidbyte.lib.dataclasses.security import ResourceScopePolicy
from vidbyte.lib.enums.integrations import (
    AccessState,
    FailurePolicy,
    LoadMode,
    LoadOutcome,
    ProviderOperation,
)

__all__ = [
    "DEFAULT_ADAPTERS",
    "AccessState",
    "AdapterRegistry",
    "AuthorizationResult",
    "BudgetAdmission",
    "Connection",
    "ConnectionBroker",
    "ConnectionRegistry",
    "ContextAdmissionBudget",
    "ContextBudgetPlan",
    "CredentialResolver",
    "Credentials",
    "FailurePolicy",
    "InMemoryCredentialResolver",
    "LoadMode",
    "LoadOutcome",
    "LoadRequest",
    "ProviderAdapter",
    "ProviderOperation",
    "ProviderToolset",
    "ResolvedSources",
    "ResourceScope",
    "ResourceScopePolicy",
    "ResourceSelection",
    "ScopedProviderTool",
    "SelectionReportEntry",
    "Sources",
    "SourcesReport",
    "SourcesResolver",
    "ToolBudget",
]
