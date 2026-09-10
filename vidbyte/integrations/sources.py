"""FILE: vidbyte/integrations/sources.py

PURPOSE: Defines Sources, the developer-facing object that compiles resource selections into the context items, tools, and permission policy an Agent already accepts.
ROLE IN CODEBASE: The front door of the integrations layer; nothing else in the SDK needs to change for an agent to read an external resource.
ARCHITECTURE NOTE: Sources.__init__ is a thin adapter that coerces loose arguments into validated dataclasses, and SourcesResolver owns the four-step resolution.
COMMON MODIFICATION PATTERNS: Add a resolution concern as one more named step composed inside resolve(); keep __init__ free of any logic beyond coercion and registry defaults.
KNOWN EDGE CASES: An empty selection list resolves cleanly, a hybrid failure is reported exactly once, and one failing adapter never cancels its siblings.
RELATED DOCS: docs/design/sources-access-layer.md
TESTS: tests/test_sources_access_layer.py and scripts/test-sources-access-layer.py.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from vidbyte.context.primitives.documents import DocumentContextItem
from vidbyte.integrations.adapters import (
    DEFAULT_ADAPTERS,
    AdapterRegistry,
    ProviderAdapter,
)
from vidbyte.integrations.budget import ContextAdmissionBudget, ToolBudget
from vidbyte.integrations.connections import (
    ConnectionBroker,
    ConnectionRegistry,
    CredentialResolver,
    InMemoryCredentialResolver,
)
from vidbyte.integrations.report import SourcesReport
from vidbyte.integrations.toolsets import ProviderToolset, ScopedProviderTool
from vidbyte.lib.constants.integrations import (
    INTEGRATIONS_DEFAULT_MAX_TOKENS,
    INTEGRATIONS_DEFAULT_MAX_TOOL_BYTES,
    INTEGRATIONS_DEFAULT_MAX_TOOL_CALLS,
    INTEGRATIONS_MAX_SELECTIONS,
)
from vidbyte.lib.dataclasses.integrations import (
    AuthorizationResult,
    ContextBudgetPlan,
    LoadRequest,
    ResourceScope,
    ResourceSelection,
    SelectionReportEntry,
)
from vidbyte.lib.dataclasses.security import ResourceScopePolicy
from vidbyte.lib.enums.integrations import AccessState, FailurePolicy, LoadOutcome
from vidbyte.lib.errors import ConfigurationError, SourceAccessError


@dataclass(frozen=True, slots=True)
class ResolvedSources:
    """Everything one resolution produced, shaped exactly as an Agent constructor accepts it."""

    context_items: tuple[DocumentContextItem, ...]
    tools: tuple[ScopedProviderTool, ...]
    permission_policy: ResourceScopePolicy
    report: SourcesReport


class Sources:
    """Compiles external resource selections into agent context items, scoped tools, and a scope policy."""

    def __init__(
        self,
        selections: Sequence[ResourceSelection],
        *,
        max_tokens: int = INTEGRATIONS_DEFAULT_MAX_TOKENS,
        max_tool_calls: int = INTEGRATIONS_DEFAULT_MAX_TOOL_CALLS,
        max_tool_bytes: int = INTEGRATIONS_DEFAULT_MAX_TOOL_BYTES,
        on_failure: FailurePolicy | str = FailurePolicy.REPORT,
        connections: ConnectionRegistry | None = None,
        credentials: CredentialResolver | None = None,
        adapters: AdapterRegistry | None = None,
    ) -> None:
        # Coerces loose arguments into validated dataclasses; every rule lives on those.
        self._selections = self._normalize_selections(selections)
        self._budget = ContextBudgetPlan(max_tokens=max_tokens, max_tool_calls=max_tool_calls, max_tool_bytes=max_tool_bytes)
        self._on_failure = FailurePolicy(on_failure)
        self._connections = connections if connections is not None else ConnectionRegistry()
        self._credentials = credentials if credentials is not None else InMemoryCredentialResolver()
        self._adapters = adapters if adapters is not None else DEFAULT_ADAPTERS

    @property
    def selections(self) -> tuple[ResourceSelection, ...]:
        """Return the validated selections this object will resolve."""
        return self._selections

    @property
    def budget(self) -> ContextBudgetPlan:
        """Return the validated numeric ceilings this resolution runs under."""
        return self._budget

    @property
    def on_failure(self) -> FailurePolicy:
        """Return whether a failing selection aborts resolution or is recorded and survived."""
        return self._on_failure

    async def resolve(self) -> ResolvedSources:
        """Authorize, load, and build tools for every selection, returning agent-ready arguments."""
        resolver = SourcesResolver(
            selections=self._selections,
            budget=self._budget,
            on_failure=self._on_failure,
            broker=ConnectionBroker(connections=self._connections, resolver=self._credentials),
            adapters=self._adapters,
        )
        return await resolver.resolve()

    @staticmethod
    def _normalize_selections(selections: Sequence[ResourceSelection]) -> tuple[ResourceSelection, ...]:
        """Coerce the positional selection argument into a validated, duplicate-free tuple."""
        if isinstance(selections, (ResourceSelection, str, bytes)):
            raise ConfigurationError("Sources() takes a sequence of ResourceSelection as its first argument, not a single value.")
        normalized = tuple(selections)
        if len(normalized) > INTEGRATIONS_MAX_SELECTIONS:
            raise ConfigurationError(f"Sources() accepts at most {INTEGRATIONS_MAX_SELECTIONS} selections.")
        Sources._reject_duplicates(normalized)
        return normalized

    @staticmethod
    def _reject_duplicates(selections: tuple[ResourceSelection, ...]) -> None:
        """Raise when two selections address the same provider, resource, and mode."""
        seen: set[tuple[str, str, str]] = set()
        for selection in selections:
            if not isinstance(selection, ResourceSelection):
                raise ConfigurationError(f"Sources() selections must be ResourceSelection instances, got {type(selection).__name__}.")
            identity = selection.identity()
            if identity in seen:
                raise ConfigurationError(f"Duplicate selection for {identity[0]}:{identity[1]} in mode '{identity[2]}'.")
            seen.add(identity)


class SourcesResolver:
    """Runs the four ordered phases that turn selections into agent constructor arguments."""

    def __init__(self, *, selections: tuple[ResourceSelection, ...], budget: ContextBudgetPlan, on_failure: FailurePolicy, broker: ConnectionBroker, adapters: AdapterRegistry) -> None:
        # Collaborators are injected so a resolution is fully testable without any network.
        self._selections = selections
        self._budget = budget
        self._on_failure = on_failure
        self._broker = broker
        self._adapters = adapters
        self._entries: list[SelectionReportEntry] = []

    async def resolve(self) -> ResolvedSources:
        """Authorize every selection, load content, build scoped tools, and assemble the result."""
        self._require_registered_providers()
        granted = await self._authorize_all()
        items = await self._load_content(granted)
        tools, resources = self._build_tools(granted)
        return self._assemble(items, tools, resources)

    def _require_registered_providers(self) -> None:
        """Fail at resolve time when any selection names a provider with no adapter."""
        # @intent provider
        # Checking every provider up front means a missing adapter is one clear error
        # before authorization, never a confusing per-selection transport failure.
        for selection in self._selections:
            self._adapters.get(selection.provider)

    async def _authorize_all(self) -> tuple[tuple[ResourceSelection, AuthorizationResult], ...]:
        """Authorize every selection concurrently and record each denial as a failed entry."""
        # @intent permissions
        # Authorization runs for every selection before any content is fetched, so a
        # denied selection never reaches its provider even once.
        results = await asyncio.gather(*(self._broker.authorize(selection) for selection in self._selections), return_exceptions=True)
        granted: list[tuple[ResourceSelection, AuthorizationResult]] = []
        for selection, result in zip(self._selections, results, strict=True):
            if isinstance(result, BaseException):
                self._record_failure(selection, AccessState.TRANSPORT_FAILED, f"Authorization raised {type(result).__name__}.")
                continue
            if not result.granted:
                self._record_failure(selection, result.state, result.detail)
                continue
            granted.append((selection, result))
        return tuple(granted)

    async def _load_content(self, granted: tuple[tuple[ResourceSelection, AuthorizationResult], ...]) -> tuple[DocumentContextItem, ...]:
        """Fetch every loading selection concurrently and admit the results against the token budget."""
        # @intent external boundaries
        # Every provider fetch for the run is gathered here with return_exceptions, so
        # one unreachable remote system degrades to a report entry, not a cancelled run.
        loading = tuple((selection, result) for selection, result in granted if selection.loads)
        if not loading:
            return ()
        payloads = await asyncio.gather(*(self._load_one(selection, result) for selection, result in loading), return_exceptions=True)
        budget = ContextAdmissionBudget(max_tokens=self._budget.max_tokens)
        admitted: list[DocumentContextItem] = []
        for (selection, _), payload in zip(loading, payloads, strict=True):
            if isinstance(payload, BaseException):
                self._record_failure(selection, AccessState.TRANSPORT_FAILED, f"The provider load raised {type(payload).__name__}.")
                continue
            admission = budget.admit(payload)
            admitted.extend(admission.items)
            self._entries.append(
                SelectionReportEntry(
                    selection=selection,
                    outcome=admission.outcome,
                    state=AccessState.GRANTED,
                    item_count=len(admission.items),
                    tokens_loaded=admission.tokens_admitted,
                    tokens_original=admission.tokens_original,
                )
            )
        return tuple(admitted)

    async def _load_one(self, selection: ResourceSelection, result: AuthorizationResult) -> tuple[DocumentContextItem, ...]:
        """Await one adapter's load for an authorized selection."""
        # @intent external boundaries
        # This is the only place provider content is fetched. The caller gathers with
        # return_exceptions so one failing provider cannot cancel its siblings.
        adapter = self._require_adapter(selection)
        request = LoadRequest(selection=selection, connection=result.require_connection(), credentials=result.require_credentials())
        return tuple(await adapter.load(request))

    def _build_tools(self, granted: tuple[tuple[ResourceSelection, AuthorizationResult], ...]) -> tuple[tuple[ScopedProviderTool, ...], frozenset[str]]:
        """Build scoped tools for every tool-exposing selection and collect the granted resource ids."""
        budget = ToolBudget(max_calls=self._budget.max_tool_calls, max_bytes=self._budget.max_tool_bytes)
        tools: list[ScopedProviderTool] = []
        resources: set[str] = set()
        for selection, result in granted:
            if not selection.exposes_tools:
                continue
            scope = self._scope_for(selection, result)
            adapter = self._require_adapter(selection)
            tools.extend(ProviderToolset.build(adapter=adapter, scope=scope, credentials=result.require_credentials(), budget=budget))
            resources.add(scope.qualified_id())
            self._record_tools_only(selection)
        return tuple(tools), frozenset(resources)

    def _assemble(self, items: tuple[DocumentContextItem, ...], tools: tuple[ScopedProviderTool, ...], resources: frozenset[str]) -> ResolvedSources:
        """Build the final result, first enforcing the run's failure policy."""
        report = SourcesReport(entries=tuple(self._entries))
        self._enforce_failure_policy(report)
        return ResolvedSources(
            context_items=items,
            tools=tools,
            permission_policy=ResourceScopePolicy(granted_resources=resources),
            report=report,
        )

    def _enforce_failure_policy(self, report: SourcesReport) -> None:
        """Raise a typed access error when require_all is set and any selection failed."""
        # @intent permissions
        # require_all is the caller's statement that partial provider coverage is not
        # acceptable, so an incomplete resolution must raise instead of returning.
        if self._on_failure is not FailurePolicy.REQUIRE_ALL:
            return
        failures = report.failed
        if not failures:
            return
        first = failures[0]
        raise SourceAccessError(first.selection.provider, first.selection.resource_id, first.state.value, first.detail)

    def _require_adapter(self, selection: ResourceSelection) -> ProviderAdapter:
        """Return the registered adapter for a selection's provider, raising when absent."""
        # @intent external boundaries
        # The single lookup point from a selection to the remote system that serves it.
        return self._adapters.get(selection.provider)

    def _scope_for(self, selection: ResourceSelection, result: AuthorizationResult) -> ResourceScope:
        """Build the immutable resource boundary a selection's tools are bound to."""
        # @intent permissions
        # This scope is the authorization boundary every tool built for the selection
        # is closed over, so it is derived from the granted connection, never the call.
        return ResourceScope(provider=selection.provider, resource_id=selection.resource_id, connection_id=result.require_connection().connection_id)

    def _record_failure(self, selection: ResourceSelection, state: AccessState, detail: str) -> None:
        """Record one selection that could not be authorized or loaded."""
        self._entries.append(SelectionReportEntry(selection=selection, outcome=LoadOutcome.FAILED, state=state, detail=detail))

    def _record_tools_only(self, selection: ResourceSelection) -> None:
        """Record a tools-mode selection, which contributes capability rather than content."""
        if selection.loads:
            return
        self._entries.append(SelectionReportEntry(selection=selection, outcome=LoadOutcome.TOOLS_ONLY, state=AccessState.GRANTED))


__all__ = [
    "ResolvedSources",
    "Sources",
    "SourcesResolver",
]
