# Codex agent integration

This folder translates Vidbyte inputs and outputs around Codex-owned execution.
Live observation uses the native turn stream and invokes awaited callbacks in
arrival order. It does not pause Codex between internal model calls.

```python
from vidbyte import CodexHarnessAgent, CodexHarnessAgentSettings, CodexObservationSettings, Trace

agent = CodexHarnessAgent(CodexHarnessAgentSettings(
    name="observed", system_prompt="Complete the task.",
    observation=CodexObservationSettings(tracer=Trace.langsmith_default()),
))
```

Supply `observers=(async_callback,)` to consume reviewed native item events.
Callbacks are awaited and failures abort collection. Unknown notifications retain
their method and identity only. Reasoning content is excluded before callbacks;
reviewed item fields can still contain task data, so callbacks own storage policy.
Tracing exports identity metadata only and remains fail-open. No model-call spans
are inferred from assistant messages. Forks inherit settings; an empty observation
settings override disables them.

## File Index

- `agent.py`: Public facade and middleware/metrics orchestration.
- `config.py`: Shared settings resolution and native argument serialization.
- `context.py`: Context zone and native input placement translation.
- `fork.py`: Validated child construction and native lineage.
- `metrics.py`: Usage snapshot and local cost accounting.
- `middleware.py`: Enforceable outer lifecycle hooks.
- `observation.py`: Reviewed event translation and optional tracing.
- `stream.py`: One-consumer native streaming and result collection.
- `result.py`: Native snapshot serialization and output validation.
- `transport.py`: Native client lifecycle, lazy imports, and error boundaries.
- `__init__.py`: Public facade exports.

## Non-Goals

Generic tool execution belongs in `vidbyte/tools`; provider trace export belongs in
`vidbyte/providers`; shared records belong in `vidbyte/lib/dataclasses`. This
adapter does not replace native context management or expose private reasoning.

## Logs

- 2026-09-08 - Added optional native streaming - awaited event callbacks do not establish a native execution barrier.
