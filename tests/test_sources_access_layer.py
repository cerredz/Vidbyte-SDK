"""FILE: tests/test_sources_access_layer.py

PURPOSE: Verifies the Sources access layer end to end: construction contract, budgets, authorization states, resource scoping, and coverage reporting.
ROLE IN CODEBASE: The quality gate for vidbyte/integrations/ and for ResourceScopePolicy, including the assertion that a scoped tool cannot reach an ungranted resource.
ARCHITECTURE NOTE: A FakeAdapter double stands in for every provider, because no concrete provider ships with the access layer; Agent, Tools, and ContextManager are real.
COMMON MODIFICATION PATTERNS: Add a test class here and register it in scripts/test-sources-access-layer.py in the same change so both runners stay in sync.
KNOWN EDGE CASES: The concurrency test asserts a wall-clock bound and is the one case a heavily loaded machine can make flaky.
RELATED DOCS: docs/design/sources-access-layer.md
TESTS: Run with python -m pytest tests/test_sources_access_layer.py or python scripts/test-sources-access-layer.py.
"""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from vidbyte.agents import Agent
from vidbyte.context import ContextManager
from vidbyte.context.primitives.documents import DocumentContextItem
from vidbyte.integrations import (
    AccessState,
    AdapterRegistry,
    AuthorizationResult,
    Connection,
    ConnectionBroker,
    ConnectionRegistry,
    ContextAdmissionBudget,
    Credentials,
    FailurePolicy,
    InMemoryCredentialResolver,
    LoadMode,
    LoadOutcome,
    LoadRequest,
    ProviderOperation,
    ProviderToolset,
    ResourceScope,
    ResourceScopePolicy,
    ResourceSelection,
    SelectionReportEntry,
    Sources,
    SourcesReport,
    ToolBudget,
)
from vidbyte.lib.config.sources import UNTRUSTED_CONTENT_BEGIN, UNTRUSTED_CONTENT_END
from vidbyte.lib.constants.integrations import INTEGRATIONS_MAX_SELECTIONS
from vidbyte.lib.errors import ConfigurationError, SourceAccessError
from vidbyte.tools import Tools
from vidbyte.tools.security import PermissionDecision
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolSpec,
    ToolStatus,
)

_SECRET = "super-secret-token-value"


class FakeAdapter:
    """Configurable ProviderAdapter double standing in for a real provider's network calls."""

    def __init__(self, *, provider: str = "fake", items: tuple[DocumentContextItem, ...] = (), operations: frozenset[ProviderOperation] | None = None, raises: Exception | None = None, output: str = "adapter output", extra_parameters: tuple[ToolParameter, ...] = ()) -> None:
        # Every behavior a real adapter could exhibit is switchable here.
        self._provider = provider
        self._items = items
        self._operations = operations if operations is not None else frozenset({ProviderOperation.READ})
        self._raises = raises
        self._output = output
        self._extra_parameters = extra_parameters
        self.load_calls = 0
        self.invoke_calls: list[tuple[ProviderOperation, ResourceScope, Mapping[str, Any]]] = []

    @property
    def provider(self) -> str:
        """Return this double's provider name."""
        return self._provider

    def capabilities(self) -> frozenset[ProviderOperation]:
        """Return the operations this double exposes as scoped tools."""
        return self._operations

    def describe_operation(self, operation: ProviderOperation) -> ToolSpec:
        """Return a model-facing spec for one operation, optionally with injected parameters."""
        return ToolSpec(
            name=f"{self._provider}_{operation.value}",
            description=(
                "Read bounded content from the resource this tool is permanently bound to. "
                "The operation returns text the agent can quote or summarize in its answer. "
                "The bound resource cannot be changed by any argument supplied to this tool. "
                "Every call is charged against the exploration budget configured for the run."
            ),
            parameters=self._extra_parameters,
            permission=ToolPermission.SAFE,
        )

    async def load(self, request: LoadRequest) -> tuple[DocumentContextItem, ...]:
        """Return the configured items, or raise the configured exception."""
        self.load_calls += 1
        await asyncio.sleep(0)
        if self._raises is not None:
            raise self._raises
        return self._items

    async def invoke(self, operation: ProviderOperation, scope: ResourceScope, credentials: Credentials, arguments: Mapping[str, Any]) -> str:
        """Record the invocation and return the configured output, or raise."""
        self.invoke_calls.append((operation, scope, dict(arguments)))
        await asyncio.sleep(0)
        if self._raises is not None:
            raise self._raises
        return self._output


class RaisingResolver:
    """Credential resolver whose resolve() always raises, standing in for a broken keyring."""

    async def resolve(self, connection: Connection) -> Credentials | None:
        """Raise to exercise the transport-failure authorization path."""
        raise RuntimeError("keyring unavailable")


def _item(content: str, *, source: str = "fake://doc", fenced: bool = False) -> DocumentContextItem:
    """Build one document context item, optionally wrapped in the untrusted-content fence."""
    body = f"{UNTRUSTED_CONTENT_BEGIN} (source: {source}) -----\n{content}\n{UNTRUSTED_CONTENT_END}" if fenced else content
    return DocumentContextItem(source=source, content=body, title="Doc")


def _selection(*, provider: str = "fake", resource_id: str = "res-1", connection: str = "conn", mode: LoadMode = LoadMode.LOAD, required_scopes: tuple[str, ...] = ()) -> ResourceSelection:
    """Build one resource selection with test-friendly defaults."""
    return ResourceSelection(provider=provider, resource_id=resource_id, connection=connection, mode=mode, required_scopes=required_scopes)


def _wire(adapter: FakeAdapter, *, provider: str = "fake", connection_name: str = "conn", expires_at: datetime | None = None, scopes: tuple[str, ...] = ()) -> tuple[AdapterRegistry, ConnectionRegistry, InMemoryCredentialResolver]:
    """Build the three registries a Sources resolution needs, wired to one adapter."""
    adapters = AdapterRegistry().register(adapter)
    connection = Connection(connection_id=f"{provider}-1", provider=provider)
    connections = ConnectionRegistry().register(connection_name, connection)
    resolver = InMemoryCredentialResolver().add(connection.connection_id, Credentials(connection_id=connection.connection_id, token=_SECRET, scopes=scopes, expires_at=expires_at))
    return adapters, connections, resolver


class SourcesConstructionTests(unittest.TestCase):
    """Covers the positional-array/keyword-only contract and construction-time validation."""

    def test_accepts_positional_list_and_keyword_only_options(self) -> None:
        """[Hidden Assumption] The first argument is positional and every other is keyword-only."""
        sources = Sources([_selection()], max_tokens=100)
        self.assertEqual(len(sources.selections), 1)
        with self.assertRaises(TypeError):
            Sources([_selection()], 100)  # type: ignore[misc]

    def test_empty_selection_list_resolves_to_empty_everything(self) -> None:
        """[Edge Case] A zero-length selection list is valid and must not raise."""
        resolved = asyncio.run(Sources([]).resolve())
        self.assertEqual(resolved.context_items, ())
        self.assertEqual(resolved.tools, ())
        self.assertEqual(resolved.permission_policy.granted_resources, frozenset())
        self.assertTrue(resolved.report.complete)

    def test_rejects_bare_selection_without_a_list(self) -> None:
        """[Hidden Assumption] A single selection passed unwrapped must be rejected, not iterated."""
        with self.assertRaises(ConfigurationError):
            Sources(_selection())  # type: ignore[arg-type]

    def test_rejects_duplicate_selections(self) -> None:
        """[Silent Failure] A duplicate would double-charge the budget and collide on tool name."""
        with self.assertRaises(ConfigurationError):
            Sources([_selection(), _selection()])

    def test_allows_same_resource_in_two_different_modes(self) -> None:
        """[Edge Case] Identity includes the mode, so load and tools on one resource coexist."""
        sources = Sources([_selection(mode=LoadMode.LOAD), _selection(mode=LoadMode.TOOLS)])
        self.assertEqual(len(sources.selections), 2)

    def test_rejects_non_selection_entries(self) -> None:
        """[Hidden Assumption] A stray string in the list must fail at construction."""
        with self.assertRaises(ConfigurationError):
            Sources(["not-a-selection"])  # type: ignore[list-item]

    def test_rejects_selection_count_above_ceiling(self) -> None:
        """[Edge Case] The selection ceiling is enforced at the boundary."""
        too_many = [_selection(resource_id=f"res-{index}") for index in range(INTEGRATIONS_MAX_SELECTIONS + 1)]
        with self.assertRaises(ConfigurationError):
            Sources(too_many)

    def test_coerces_string_on_failure_into_enum(self) -> None:
        """[Hidden Assumption] A raw string policy is coerced once, at the boundary."""
        self.assertIs(Sources([], on_failure="require_all").on_failure, FailurePolicy.REQUIRE_ALL)

    def test_rejects_out_of_range_budgets(self) -> None:
        """[Edge Case] Negative and above-ceiling budgets are refused at construction."""
        with self.assertRaises(ConfigurationError):
            Sources([], max_tokens=-1)
        with self.assertRaises(ConfigurationError):
            Sources([], max_tokens=10**12)


class ContextAdmissionBudgetTests(unittest.TestCase):
    """Covers admission at the token boundary, truncation, fencing, and skipping."""

    def test_admits_item_that_fits_exactly_at_the_boundary(self) -> None:
        """[Edge Case] An item costing exactly the budget must be admitted whole."""
        budget = ContextAdmissionBudget(max_tokens=10)
        admission = budget.admit((_item("x" * 40),))
        self.assertIs(admission.outcome, LoadOutcome.LOADED)
        self.assertEqual(admission.tokens_admitted, 10)
        self.assertEqual(budget.remaining_tokens, 0)

    def test_truncates_item_exceeding_the_remaining_budget(self) -> None:
        """[Silent Failure] Cut content must be reported as truncated, never as fully loaded."""
        budget = ContextAdmissionBudget(max_tokens=100)
        admission = budget.admit((_item("y" * 4000),))
        self.assertIs(admission.outcome, LoadOutcome.TRUNCATED)
        self.assertLess(len(admission.items[0].content), 4000)
        self.assertGreater(admission.tokens_original, admission.tokens_admitted)

    def test_marks_truncated_content_with_metadata_and_marker(self) -> None:
        """[Silent Failure] A truncated item must be identifiable by both metadata and text."""
        admission = ContextAdmissionBudget(max_tokens=100).admit((_item("z" * 4000),))
        item = admission.items[0]
        self.assertTrue(item.metadata["truncated"])
        self.assertEqual(item.metadata["original_chars"], 4000)
        self.assertIn("truncated", item.content)

    def test_preserves_untrusted_fence_when_truncating(self) -> None:
        """[Hidden Failure] Slicing must not leave provider text outside the untrusted fence."""
        admission = ContextAdmissionBudget(max_tokens=100).admit((_item("w" * 4000, fenced=True),))
        content = admission.items[0].content
        self.assertIn(UNTRUSTED_CONTENT_BEGIN, content)
        self.assertIn(UNTRUSTED_CONTENT_END, content)

    def test_skips_remaining_items_once_exhausted(self) -> None:
        """[Silent Failure] Items that do not fit must be reported skipped, not dropped quietly."""
        budget = ContextAdmissionBudget(max_tokens=10)
        admission = budget.admit((_item("a" * 40), _item("b" * 40)))
        self.assertIs(admission.outcome, LoadOutcome.SKIPPED)
        self.assertEqual(len(admission.items), 1)

    def test_zero_budget_admits_nothing_without_raising(self) -> None:
        """[Edge Case] A zero token budget is a valid configuration, not an error."""
        admission = ContextAdmissionBudget(max_tokens=0).admit((_item("content"),))
        self.assertEqual(admission.items, ())
        self.assertIs(admission.outcome, LoadOutcome.SKIPPED)

    def test_empty_document_costs_zero_tokens(self) -> None:
        """[Edge Case] An empty body must not be charged a phantom token."""
        self.assertEqual(ContextAdmissionBudget.estimate_tokens(""), 0)
        admission = ContextAdmissionBudget(max_tokens=0).admit((_item(""),))
        self.assertEqual(len(admission.items), 1)


class ToolBudgetTests(unittest.TestCase):
    """Covers the call ceiling, the byte ceiling, and sticky exhaustion."""

    def test_denies_after_call_ceiling(self) -> None:
        """[Edge Case] The call ceiling denies the call immediately after it is reached."""
        budget = ToolBudget(max_calls=2, max_bytes=10_000)
        self.assertTrue(budget.reserve())
        self.assertTrue(budget.reserve())
        self.assertFalse(budget.reserve())

    def test_charges_the_returned_payload_not_the_request(self) -> None:
        """[Silent Failure] Billing request arguments would leave the byte ceiling inert."""
        budget = ToolBudget(max_calls=100, max_bytes=10)
        budget.reserve()
        self.assertEqual(budget.remaining_bytes(), 10)
        budget.admit_output("abcde")
        self.assertEqual(budget.remaining_bytes(), 5)

    def test_clips_payload_that_overruns_the_byte_ceiling(self) -> None:
        """[Silent Failure] An oversized payload must be clipped and marked, never admitted whole."""
        budget = ToolBudget(max_calls=100, max_bytes=10)
        budget.reserve()
        admission = budget.admit_output("z" * 500)
        self.assertTrue(admission.truncated)
        self.assertLess(len(admission.text), 500)
        self.assertTrue(budget.would_exceed())

    def test_byte_ceiling_accumulates_across_calls(self) -> None:
        """[Hidden Failure] A per-call ceiling would let N calls each spend the full budget."""
        budget = ToolBudget(max_calls=100, max_bytes=10)
        budget.reserve()
        budget.admit_output("abcde")
        budget.reserve()
        admission = budget.admit_output("abcdefghij")
        self.assertTrue(admission.truncated)

    def test_multibyte_payload_is_measured_in_bytes(self) -> None:
        """[Hidden Assumption] A byte ceiling must count bytes, not characters."""
        budget = ToolBudget(max_calls=100, max_bytes=4)
        budget.reserve()
        self.assertTrue(budget.admit_output("ééé").truncated)

    def test_stays_denied_after_first_denial(self) -> None:
        """[Hidden Failure] A resetting budget would allow unbounded exploration after one refusal."""
        budget = ToolBudget(max_calls=1, max_bytes=10)
        budget.reserve()
        self.assertFalse(budget.reserve())
        self.assertFalse(budget.reserve())
        self.assertTrue(budget.would_exceed())


class ConnectionBrokerTests(unittest.IsolatedAsyncioTestCase):
    """Covers every authorization state and the guarantee that a denial carries no credential."""

    def _broker(self, *, connections: ConnectionRegistry, resolver: Any) -> ConnectionBroker:
        """Build a broker over one registry and resolver pair."""
        return ConnectionBroker(connections=connections, resolver=resolver)

    async def test_unregistered_connection_requires_auth(self) -> None:
        """[Hidden Assumption] An unknown connection name must never reach a provider."""
        broker = self._broker(connections=ConnectionRegistry(), resolver=InMemoryCredentialResolver())
        result = await broker.authorize(_selection())
        self.assertIs(result.state, AccessState.AUTH_REQUIRED)

    async def test_missing_credentials_requires_auth(self) -> None:
        """[Hidden Assumption] A resolver returning None must not produce an unauthenticated call."""
        connections = ConnectionRegistry().register("conn", Connection(connection_id="c1", provider="fake"))
        broker = self._broker(connections=connections, resolver=InMemoryCredentialResolver())
        result = await broker.authorize(_selection())
        self.assertIs(result.state, AccessState.AUTH_REQUIRED)

    async def test_expired_credentials_require_reauth(self) -> None:
        """[Edge Case] An expired token is a distinct state from a missing one."""
        past = datetime.now(UTC) - timedelta(hours=1)
        _, connections, resolver = _wire(FakeAdapter(), expires_at=past)
        result = await self._broker(connections=connections, resolver=resolver).authorize(_selection())
        self.assertIs(result.state, AccessState.REAUTH_REQUIRED)

    async def test_missing_scope_is_insufficient_scope(self) -> None:
        """[Hidden Assumption] A linked account does not imply the scope a selection needs."""
        _, connections, resolver = _wire(FakeAdapter(), scopes=("read:one",))
        selection = _selection(required_scopes=("read:two",))
        result = await self._broker(connections=connections, resolver=resolver).authorize(selection)
        self.assertIs(result.state, AccessState.INSUFFICIENT_SCOPE)

    async def test_provider_mismatch_is_insufficient_scope(self) -> None:
        """[Silent Failure] A connection for another provider must fail clearly, not downstream."""
        _, connections, resolver = _wire(FakeAdapter(provider="fake"))
        result = await self._broker(connections=connections, resolver=resolver).authorize(_selection(provider="other"))
        self.assertIs(result.state, AccessState.INSUFFICIENT_SCOPE)

    async def test_raising_resolver_is_transport_failed(self) -> None:
        """[Hidden Failure] A broken secret store must not abort the whole resolution."""
        connections = ConnectionRegistry().register("conn", Connection(connection_id="c1", provider="fake"))
        result = await self._broker(connections=connections, resolver=RaisingResolver()).authorize(_selection())
        self.assertIs(result.state, AccessState.TRANSPORT_FAILED)

    async def test_denied_result_never_exposes_credentials(self) -> None:
        """[Hidden Failure] A denial must be structurally unable to carry a usable secret."""
        broker = self._broker(connections=ConnectionRegistry(), resolver=InMemoryCredentialResolver())
        result = await broker.authorize(_selection())
        self.assertIsNone(result.credentials)
        self.assertIsNone(result.connection)
        with self.assertRaises(ConfigurationError):
            result.require_credentials()

    async def test_empty_required_scopes_is_covered(self) -> None:
        """[Edge Case] A selection requiring no scopes is always covered."""
        _, connections, resolver = _wire(FakeAdapter(), scopes=())
        result = await self._broker(connections=connections, resolver=resolver).authorize(_selection())
        self.assertIs(result.state, AccessState.GRANTED)

    async def test_denied_result_cannot_be_constructed_with_credentials(self) -> None:
        """[Hidden Failure] The dataclass itself refuses a denied result that carries a secret."""
        with self.assertRaises(ConfigurationError):
            AuthorizationResult(state=AccessState.AUTH_REQUIRED, connection=Connection(connection_id="c1", provider="fake"))


class ResourceScopePolicyTests(unittest.TestCase):
    """Covers scoped denial, unscoped passthrough, and the inherited permission floor."""

    def _spec(self, *, resource_id: str | None, permission: ToolPermission = ToolPermission.READ) -> ToolSpec:
        """Build a spec with or without the scoped-resource marker."""
        metadata = {"resource_id": resource_id} if resource_id is not None else {}
        return ToolSpec(name="t", description="A tool used only by the scope policy tests.", permission=permission, metadata=metadata)

    def test_allows_tool_without_resource_marker(self) -> None:
        """[Hidden Assumption] Ordinary non-provider tools must keep working under this policy."""
        policy = ResourceScopePolicy(granted_resources=frozenset({"fake:res-1"}))
        self.assertIs(policy.check(self._spec(resource_id=None), ToolCall(tool_name="t")), PermissionDecision.ALLOW)

    def test_denies_ungranted_scoped_tool(self) -> None:
        """[Hidden Failure] The core security assertion: another resource is refused."""
        policy = ResourceScopePolicy(granted_resources=frozenset({"fake:res-1"}))
        self.assertIs(policy.check(self._spec(resource_id="fake:res-2"), ToolCall(tool_name="t")), PermissionDecision.DENY)

    def test_allows_granted_scoped_tool(self) -> None:
        """The granted resource is permitted."""
        policy = ResourceScopePolicy(granted_resources=frozenset({"fake:res-1"}))
        self.assertIs(policy.check(self._spec(resource_id="fake:res-1"), ToolCall(tool_name="t")), PermissionDecision.ALLOW)

    def test_empty_grant_denies_every_scoped_tool(self) -> None:
        """[Edge Case] Sources([]) must produce a policy that grants no resource."""
        policy = ResourceScopePolicy()
        self.assertIs(policy.check(self._spec(resource_id="fake:res-1"), ToolCall(tool_name="t")), PermissionDecision.DENY)

    def test_short_circuits_on_disallowed_permission_level(self) -> None:
        """[Hidden Assumption] The inherited permission floor still applies to scoped tools."""
        policy = ResourceScopePolicy(granted_resources=frozenset({"fake:res-1"}))
        spec = self._spec(resource_id="fake:res-1", permission=ToolPermission.EXECUTE)
        self.assertIs(policy.check(spec, ToolCall(tool_name="t")), PermissionDecision.DENY)


class ProviderToolsetTests(unittest.IsolatedAsyncioTestCase):
    """Covers scope binding, naming, parameter rejection, provenance, and failure mapping."""

    def _scope(self, resource_id: str = "res-1") -> ResourceScope:
        """Build a resource scope for one fake resource."""
        return ResourceScope(provider="fake", resource_id=resource_id, connection_id="c1")

    def _credentials(self) -> Credentials:
        """Build credentials for the fake connection."""
        return Credentials(connection_id="c1", token=_SECRET)

    def _build(self, adapter: FakeAdapter, *, resource_id: str = "res-1", budget: ToolBudget | None = None) -> tuple[Any, ...]:
        """Build the scoped toolset for one adapter and resource."""
        return ProviderToolset.build(adapter=adapter, scope=self._scope(resource_id), credentials=self._credentials(), budget=budget or ToolBudget(max_calls=10, max_bytes=10_000))

    def test_resource_is_not_a_model_fillable_parameter(self) -> None:
        """[Hidden Failure] Exposing the resource as a parameter would collapse the scoping guarantee."""
        tool = self._build(FakeAdapter())[0]
        self.assertEqual(tool.spec().parameters, ())
        self.assertEqual(tool.spec().metadata["resource_id"], "fake:res-1")

    def test_rejects_adapter_spec_declaring_resource_parameter(self) -> None:
        """[Hidden Assumption] A third-party adapter is untrusted input to this layer."""
        adapter = FakeAdapter(extra_parameters=(ToolParameter(name="repo", type="string", description="Repository to read."),))
        with self.assertRaises(ConfigurationError):
            self._build(adapter)

    def test_generates_distinct_names_for_two_resources(self) -> None:
        """[Silent Failure] Colliding tool names would shadow one resource with another."""
        first = self._build(FakeAdapter(), resource_id="acme/api")[0]
        second = self._build(FakeAdapter(), resource_id="acme/web")[0]
        self.assertNotEqual(first.spec().name, second.spec().name)

    def test_sanitizes_resource_id_with_illegal_characters(self) -> None:
        """[Edge Case] A slash-bearing resource id must still produce a legal tool name."""
        tool = self._build(FakeAdapter(), resource_id="acme/api#41")[0]
        self.assertRegex(tool.spec().name, r"^[a-z0-9_]+$")

    def test_forces_read_permission(self) -> None:
        """A scoped provider tool is always a read tool regardless of the adapter's claim."""
        self.assertIs(self._build(FakeAdapter())[0].spec().permission, ToolPermission.READ)

    def test_builds_tools_in_deterministic_order(self) -> None:
        """[Hidden Failure] Non-deterministic ordering would make runs irreproducible."""
        operations = frozenset({ProviderOperation.READ, ProviderOperation.LIST, ProviderOperation.SEARCH})
        first = [tool.spec().name for tool in self._build(FakeAdapter(operations=operations))]
        second = [tool.spec().name for tool in self._build(FakeAdapter(operations=operations))]
        self.assertEqual(first, second)
        self.assertEqual(len(first), 3)

    async def test_returns_failed_result_when_budget_exhausted(self) -> None:
        """[Hidden Failure] Exhaustion must fail the call, never raise out of the agent loop."""
        tool = self._build(FakeAdapter(), budget=ToolBudget(max_calls=0, max_bytes=10_000))[0]
        result = await tool.execute(ToolCall(tool_name=tool.spec().name))
        self.assertIs(result.status, ToolStatus.ERROR)
        self.assertEqual(result.metadata["error"], "budget_exhausted")

    async def test_returns_failed_result_without_raw_provider_text(self) -> None:
        """[Hidden Failure] A provider exception must not leak its message into the model's view."""
        adapter = FakeAdapter(raises=RuntimeError("token abc123 rejected by upstream"))
        tool = self._build(adapter)[0]
        result = await tool.execute(ToolCall(tool_name=tool.spec().name))
        self.assertIs(result.status, ToolStatus.ERROR)
        self.assertNotIn("abc123", result.output)
        self.assertEqual(result.metadata["error_type"], "RuntimeError")

    async def test_clips_and_marks_an_oversized_provider_payload(self) -> None:
        """[Silent Failure] A clipped provider result must be marked so a reader can tell."""
        tool = self._build(FakeAdapter(output="q" * 5_000), budget=ToolBudget(max_calls=10, max_bytes=100))[0]
        result = await tool.execute(ToolCall(tool_name=tool.spec().name))
        self.assertIs(result.status, ToolStatus.SUCCESS)
        self.assertTrue(result.metadata["truncated"])
        self.assertLess(len(result.output), 5_000)

    async def test_marks_an_in_budget_payload_as_untruncated(self) -> None:
        """[Silent Failure] A complete result must be distinguishable from a clipped one."""
        tool = self._build(FakeAdapter(output="short"))[0]
        result = await tool.execute(ToolCall(tool_name=tool.spec().name))
        self.assertFalse(result.metadata["truncated"])

    async def test_stamps_provenance_on_success(self) -> None:
        """[Silent Failure] A result with no provenance cannot be traced back to its source."""
        tool = self._build(FakeAdapter())[0]
        result = await tool.execute(ToolCall(tool_name=tool.spec().name))
        self.assertIs(result.status, ToolStatus.SUCCESS)
        self.assertEqual(result.metadata["provider"], "fake")
        self.assertEqual(result.metadata["resource_id"], "res-1")
        self.assertEqual(result.metadata["connection_id"], "c1")

    async def test_adapter_receives_bound_scope_not_call_arguments(self) -> None:
        """[Hidden Failure] A forged argument must not redirect the adapter to another resource."""
        adapter = FakeAdapter()
        tool = self._build(adapter)[0]
        await tool.execute(ToolCall(tool_name=tool.spec().name, arguments={"resource_id": "res-999"}))
        _, scope, _ = adapter.invoke_calls[0]
        self.assertEqual(scope.resource_id, "res-1")


class SourcesResolverTests(unittest.IsolatedAsyncioTestCase):
    """Covers the load path, the tools path, hybrid, concurrency, and the failure policy."""

    def _sources(self, adapter: FakeAdapter, selections: list[ResourceSelection], **options: Any) -> Sources:
        """Build a fully wired Sources over one fake adapter."""
        adapters, connections, resolver = _wire(adapter)
        return Sources(selections, adapters=adapters, connections=connections, credentials=resolver, **options)

    async def test_loads_content_for_load_selection(self) -> None:
        """The load path admits adapter content into the context items."""
        adapter = FakeAdapter(items=(_item("hello"),))
        resolved = await self._sources(adapter, [_selection()]).resolve()
        self.assertEqual(len(resolved.context_items), 1)
        self.assertEqual(adapter.load_calls, 1)

    async def test_tools_selection_performs_no_fetch(self) -> None:
        """[Silent Failure] A tools selection must not consume the token budget by loading."""
        adapter = FakeAdapter(items=(_item("hello"),))
        resolved = await self._sources(adapter, [_selection(mode=LoadMode.TOOLS)]).resolve()
        self.assertEqual(adapter.load_calls, 0)
        self.assertEqual(resolved.context_items, ())
        self.assertEqual(len(resolved.tools), 1)

    async def test_hybrid_selection_produces_items_and_tools(self) -> None:
        """[Edge Case] Hybrid contributes on both paths from one authorization."""
        adapter = FakeAdapter(items=(_item("hello"),))
        resolved = await self._sources(adapter, [_selection(mode=LoadMode.HYBRID)]).resolve()
        self.assertEqual(len(resolved.context_items), 1)
        self.assertEqual(len(resolved.tools), 1)

    async def test_one_failing_adapter_does_not_cancel_siblings(self) -> None:
        """[Hidden Failure] A gather without return_exceptions would lose every sibling result."""
        good = FakeAdapter(provider="good", items=(_item("kept"),))
        bad = FakeAdapter(provider="bad", raises=RuntimeError("boom"))
        adapters = AdapterRegistry().register(good).register(bad)
        connections = ConnectionRegistry()
        resolver = InMemoryCredentialResolver()
        for provider in ("good", "bad"):
            connection = Connection(connection_id=f"{provider}-1", provider=provider)
            connections.register(provider, connection)
            resolver.add(connection.connection_id, Credentials(connection_id=connection.connection_id, token=_SECRET))
        sources = Sources(
            [_selection(provider="good", connection="good"), _selection(provider="bad", connection="bad")],
            adapters=adapters,
            connections=connections,
            credentials=resolver,
        )
        resolved = await sources.resolve()
        self.assertEqual(len(resolved.context_items), 1)
        self.assertEqual(len(resolved.report.failed), 1)

    async def test_hybrid_failure_is_recorded_exactly_once(self) -> None:
        """[Silent Failure] Double-counting a failure would make the report lie about coverage."""
        adapter = FakeAdapter()
        adapters = AdapterRegistry().register(adapter)
        sources = Sources([_selection(mode=LoadMode.HYBRID)], adapters=adapters, connections=ConnectionRegistry(), credentials=InMemoryCredentialResolver())
        resolved = await sources.resolve()
        self.assertEqual(len(resolved.report.entries), 1)
        self.assertEqual(len(resolved.report.failed), 1)

    async def test_require_all_raises_on_any_failure(self) -> None:
        """[Hidden Assumption] require_all must abort rather than silently under-deliver."""
        adapter = FakeAdapter()
        adapters = AdapterRegistry().register(adapter)
        sources = Sources([_selection()], adapters=adapters, connections=ConnectionRegistry(), credentials=InMemoryCredentialResolver(), on_failure=FailurePolicy.REQUIRE_ALL)
        with self.assertRaises(SourceAccessError):
            await sources.resolve()

    async def test_require_all_error_never_contains_the_token(self) -> None:
        """[Hidden Failure] A raised access error must not disclose a credential."""
        _, connections, resolver = _wire(FakeAdapter(), scopes=("read:one",))
        adapters = AdapterRegistry().register(FakeAdapter())
        sources = Sources([_selection(required_scopes=("read:two",))], adapters=adapters, connections=connections, credentials=resolver, on_failure="require_all")
        with self.assertRaises(SourceAccessError) as caught:
            await sources.resolve()
        self.assertNotIn(_SECRET, str(caught.exception))

    async def test_empty_adapter_result_is_loaded_not_failed(self) -> None:
        """[Silent Failure] An empty channel is a valid answer, not a failure to chase."""
        resolved = await self._sources(FakeAdapter(items=()), [_selection()]).resolve()
        self.assertEqual(len(resolved.report.loaded), 1)
        self.assertEqual(resolved.report.loaded[0].item_count, 0)

    async def test_unregistered_provider_raises_typed_error(self) -> None:
        """[Hidden Assumption] A missing adapter fails at resolve time, not mid-run."""
        sources = Sources([_selection(provider="nope")], adapters=AdapterRegistry(), connections=ConnectionRegistry(), credentials=InMemoryCredentialResolver())
        with self.assertRaises(SourceAccessError):
            await sources.resolve()

    async def test_load_selections_resolve_concurrently(self) -> None:
        """[Hidden Failure] Sequential loading would make N selections cost N round trips."""
        adapters = AdapterRegistry()
        connections = ConnectionRegistry()
        resolver = InMemoryCredentialResolver()
        selections = []
        for index in range(4):
            provider = f"p{index}"
            adapters.register(SlowAdapter(provider=provider))
            connection = Connection(connection_id=f"{provider}-1", provider=provider)
            connections.register(provider, connection)
            resolver.add(connection.connection_id, Credentials(connection_id=connection.connection_id, token=_SECRET))
            selections.append(_selection(provider=provider, connection=provider))
        loop = asyncio.get_running_loop()
        started = loop.time()
        await Sources(selections, adapters=adapters, connections=connections, credentials=resolver).resolve()
        self.assertLess(loop.time() - started, 0.4)

    async def test_budget_is_shared_across_selections(self) -> None:
        """[Silent Failure] A per-selection budget would let N selections exceed the ceiling N times."""
        adapters = AdapterRegistry()
        connections = ConnectionRegistry()
        resolver = InMemoryCredentialResolver()
        selections = []
        for index in range(2):
            provider = f"q{index}"
            adapters.register(FakeAdapter(provider=provider, items=(_item("c" * 400),)))
            connection = Connection(connection_id=f"{provider}-1", provider=provider)
            connections.register(provider, connection)
            resolver.add(connection.connection_id, Credentials(connection_id=connection.connection_id, token=_SECRET))
            selections.append(_selection(provider=provider, connection=provider))
        resolved = await Sources(selections, adapters=adapters, connections=connections, credentials=resolver, max_tokens=100).resolve()
        self.assertLessEqual(resolved.report.tokens_admitted(), 100)


class SlowAdapter(FakeAdapter):
    """Adapter whose load sleeps, used to prove selections resolve concurrently."""

    async def load(self, request: LoadRequest) -> tuple[DocumentContextItem, ...]:
        """Sleep before returning so sequential resolution would be measurably slower."""
        await asyncio.sleep(0.1)
        return (_item("slow"),)


class SourcesReportTests(unittest.TestCase):
    """Covers completeness accounting and redaction in the rendered summary."""

    def _entry(self, outcome: LoadOutcome) -> SelectionReportEntry:
        """Build one report entry with a given outcome."""
        return SelectionReportEntry(selection=_selection(), outcome=outcome, state=AccessState.GRANTED)

    def test_complete_only_when_nothing_was_lost(self) -> None:
        """[Silent Failure] A truncated or skipped selection must not read as complete."""
        self.assertTrue(SourcesReport(entries=(self._entry(LoadOutcome.LOADED),)).complete)
        self.assertFalse(SourcesReport(entries=(self._entry(LoadOutcome.TRUNCATED),)).complete)
        self.assertFalse(SourcesReport(entries=(self._entry(LoadOutcome.SKIPPED),)).complete)
        self.assertFalse(SourcesReport(entries=(self._entry(LoadOutcome.FAILED),)).complete)

    def test_empty_report_summarizes_readably(self) -> None:
        """[Edge Case] An empty report must not render as an empty string."""
        self.assertEqual(SourcesReport().summary(), "no sources requested")
        self.assertTrue(SourcesReport().complete)

    def test_summary_never_includes_a_credential(self) -> None:
        """[Hidden Failure] The report is developer-facing output and must stay secret-free."""
        entry = SelectionReportEntry(selection=_selection(), outcome=LoadOutcome.FAILED, state=AccessState.AUTH_REQUIRED, detail="No credentials are available.")
        self.assertNotIn(_SECRET, SourcesReport(entries=(entry,)).summary())


class SourcesIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Covers the real seams: Agent construction, the Tools catalog, and ContextManager."""

    async def _resolve_both_paths(self) -> Any:
        """Resolve one load selection and one tools selection over a single adapter."""
        adapter = FakeAdapter(items=(_item("body"),))
        adapters, connections, resolver = _wire(adapter)
        sources = Sources(
            [_selection(resource_id="res-1", mode=LoadMode.LOAD), _selection(resource_id="res-2", mode=LoadMode.TOOLS)],
            adapters=adapters,
            connections=connections,
            credentials=resolver,
        )
        return await sources.resolve()

    async def test_resolved_output_constructs_a_real_agent(self) -> None:
        """The single assumption the design rests on: Agent accepts all three outputs unchanged."""
        resolved = await self._resolve_both_paths()
        agent = Agent(
            name="reviewer",
            system_prompt="Review the provided sources.",
            context_items=resolved.context_items,
            tools=list(resolved.tools),
            permission_policy=resolved.permission_policy,
        )
        self.assertEqual(agent.name, "reviewer")
        self.assertIs(agent.permission_policy, resolved.permission_policy)

    async def test_tools_catalog_accepts_both_selections_without_collision(self) -> None:
        """[Hidden Assumption] Only integration surfaces a name collision between two selections."""
        adapter = FakeAdapter(items=())
        adapters, connections, resolver = _wire(adapter)
        sources = Sources(
            [_selection(resource_id="acme/api", mode=LoadMode.TOOLS), _selection(resource_id="acme/web", mode=LoadMode.TOOLS)],
            adapters=adapters,
            connections=connections,
            credentials=resolver,
        )
        resolved = await sources.resolve()
        catalog = Tools(list(resolved.tools))
        self.assertEqual(len(catalog.names()), 2)

    async def test_admitted_items_reach_a_real_context_manager(self) -> None:
        """[Silent Failure] A reported item that never reaches context would overstate coverage."""
        resolved = await self._resolve_both_paths()
        manager = ContextManager(context_items=resolved.context_items)
        self.assertEqual(len(manager.context_items), len(resolved.context_items))
        self.assertEqual(len(manager.context_items), sum(entry.item_count for entry in resolved.report.loaded))

    async def test_scope_denial_on_the_runtime_permission_path(self) -> None:
        """[Hidden Failure] Denial must hold on the same call the AgentRuntime makes."""
        resolved = await self._resolve_both_paths()
        tool = resolved.tools[0]
        self.assertIs(resolved.permission_policy.check(tool.spec(), ToolCall(tool_name=tool.spec().name)), PermissionDecision.ALLOW)
        foreign = ToolSpec(name="foreign", description="A tool bound to a resource this run was never granted.", permission=ToolPermission.READ, metadata={"resource_id": "fake:res-999"})
        self.assertIs(resolved.permission_policy.check(foreign, ToolCall(tool_name="foreign")), PermissionDecision.DENY)


if __name__ == "__main__":
    unittest.main()
