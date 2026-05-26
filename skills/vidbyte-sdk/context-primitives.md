# Context Primitives

Use this guide when adding, modifying, or using durable context primitives in the Vidbyte SDK.

## What Context Primitives Are

Context primitives are typed working-memory objects for agents. They are stored as `ContextItem` objects, collected by `ContextManager`, and rendered near the top of the context window below the system prompt. Use them for durable context that should survive across model calls, such as identity, active tasks, plans, files, progress, memory, and tool-discovered facts.

Prefer `context_primitives` in new agent-facing APIs and docs. Keep `context_items` working as the compatibility name.

## Primitive Metadata

Every built-in primitive can carry:

- `id`: stable identifier used for upsert/remove behavior.
- `placement`: `sticky`, `normal`, or `ephemeral`.
- `priority`: numeric ordering inside the placement group.
- `visibility`: `model`, `metadata_only`, or `hidden`.

Stable IDs matter. Tools and algorithms must update existing primitives by ID instead of appending duplicates.

## Agent Seeding

Agents may receive default primitives:

```python
Agent(
    name="builder",
    system_prompt="Work carefully.",
    context_primitives=[
        IdentityContextItem(role="SDK engineer"),
        TaskContextItem(id="task:current", goal="Ship the feature"),
    ],
)
```

Per-call primitives belong on `AgentInput(context_primitives=...)` and must not mutate agent defaults.

## Tool Sync

Tools should return primitive updates through `ToolResult.context_updates`. Do not give tools direct mutable access to agent context.

```python
return ToolResult.success(
    "inspect",
    "Inspection complete.",
    context_updates=[
        ContextPrimitiveUpdate.upsert(TaskContextItem(id="task:current", goal="Ship", status="in_progress")),
    ],
)
```

The direct agent runtime applies updates after non-internal tool calls and before the next model call.

## Algorithm Admission

`ContextWindowAlgorithm.model_visible_context_primitives()` controls which primitives are rendered. The default policy:

- excludes `hidden` and `metadata_only` primitives from model-visible context,
- sorts `sticky` before `normal` before `ephemeral`,
- sorts by `priority`, then stable primitive ID.

Raw primitive objects remain available in runtime metadata even when hidden from the model.

## Safety Rules

- `IdentityContextItem` is lower authority than the system prompt and must not be used for security policy.
- Hidden and metadata-only primitives must not render into `BaseContext.build_context()`.
- Tool output hidden by a context-window algorithm must not be reintroduced through a model-visible primitive.
- Primitive classes represent data. IO, git inspection, crawling, and network calls belong in tools.
