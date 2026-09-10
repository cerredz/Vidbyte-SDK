# Integrations

`vidbyte.integrations` connects an external provider resource — a pull request, a
channel, a document, a repository — to an agent, either as content placed in the
context window or as tools the agent calls during a run.

## Role In The SDK

`Sources` is the front door. It takes a list of `ResourceSelection` objects and
compiles them into the exact three arguments `Agent.__init__` already accepts:
`context_items`, `tools`, and `permission_policy`. Nothing in the agent layer,
the context layer, or the tool layer changes to support this.

```python
access = await Sources(
    [selection_one, selection_two],
    max_tokens=20_000,
).resolve()

agent = Agent(
    name="reviewer",
    system_prompt="...",
    context_items=access.context_items,
    tools=access.tools,
    permission_policy=access.permission_policy,
)
print(access.report.summary())
```

## Two Access Paths

Each selection declares a `LoadMode`:

| Mode | When the fetch happens | Who decides what to read |
|---|---|---|
| `LOAD` | During `resolve()`, before the first model call | The developer |
| `TOOLS` | During the run, on each tool call | The agent |
| `HYBRID` | Both, from one resolved connection | Both |

`LOAD` is bounded by a token budget. `TOOLS` is bounded by a call count and a
cumulative byte ceiling. Neither path can quietly exceed its bound: whatever did
not fit appears in `ResolvedSources.report`.

## Resource Scoping

A tool built for a selection is bound to that selection's resource at
construction. The resource is never a model-fillable parameter, so an agent
granted one repository cannot reach another by changing an argument.
`ResourceScopePolicy` is the second, auditable layer — it reads the resource from
the tool's own spec metadata and denies anything outside the granted set before
the adapter is invoked.

## Adding A Provider

No concrete provider ships with this layer; `DEFAULT_ADAPTERS` starts empty. A
provider is added by implementing the `ProviderAdapter` protocol — `capabilities`,
`describe_operation`, `load`, and `invoke` — and registering it:

```python
DEFAULT_ADAPTERS.register(MyProviderAdapter())
```

An adapter must not declare a resource-addressing parameter (`resource_id`,
`repo`, `channel`, and similar) on any operation spec; `ProviderToolset` rejects
one, because accepting it would make an out-of-scope call expressible.

## Credentials

`CredentialResolver` is a protocol, so a CLI keyring or a hosted backend can
supply secrets without this package importing either. `InMemoryCredentialResolver`
is the built-in implementation. `ConnectionBroker` turns a resolution into a typed
`AccessState` — `AUTH_REQUIRED`, `REAUTH_REQUIRED`, `INSUFFICIENT_SCOPE`,
`TRANSPORT_FAILED` — rather than a generic failure, and a denied result is
structurally incapable of carrying a credential.

## File Index

- `__init__.py` — public surface of the layer.
- `adapters.py` — the `ProviderAdapter` protocol and `AdapterRegistry`.
- `budget.py` — `ContextAdmissionBudget` admission and `ToolBudget` exploration limits.
- `connections.py` — connection registry, credential resolution, authorization.
- `report.py` — `SourcesReport` coverage record.
- `sources.py` — `Sources`, `SourcesResolver`, and `ResolvedSources`.
- `toolsets.py` — `ScopedProviderTool` and `ProviderToolset`.
