# Durable Sessions

Durable sessions make any agent persistent with `continue`, `resume`, and `fork`
over an append-only checkpoint DAG. The agent stays pure; persistence lives in a
`Session` wrapper, so sessions work for every runtime (linear, MCTS, actor).

## Attach in one line

```python
from vidbyte import Agent, Session

agent = Agent(name="researcher", system_prompt="Investigate carefully.", provider="openai", model_name="gpt-4.1")
session = Session(agent)                 # defaults to InMemorySessionStore
reply = await session.arun("Investigate the failing test")
print(session.id, session.head)
```

`sdk.harnesses.sessions.attach(agent, store=...)` is the namespace-client
equivalent. `session.run(...)` is the synchronous form.

## Stores

| Store | Import | Notes |
|-------|--------|-------|
| `InMemorySessionStore` | `vidbyte.sessions` | default; ephemeral |
| `FileSessionStore(root=...)` | `vidbyte.sessions` | atomic JSON, one dir per session |
| `PostgresSessionStore(dsn=...)` | `vidbyte.lib.providers` | needs `psycopg` |
| `MongoDbSessionStore(uri=...)` | `vidbyte.lib.providers` | needs `pymongo` |
| `SupabaseSessionStore(url=, key=)` | `vidbyte.lib.providers` | needs `supabase` |

All implement one `SessionStore` protocol and are interchangeable. Database
stores import their driver lazily and raise `ConfigurationError` when it is
missing — importing `vidbyte` never pulls a DB driver.

## The verbs

```python
from vidbyte.sessions import FileSessionStore

store = FileSessionStore("./.vidbyte/sessions")
session = Session(agent, store=store)
await session.arun("step one")

# resume / continue / fork re-supply non-serializable parts (rehydration contract)
session = Session.resume(store, session_id, tools=[grep], runner=my_runner)
session = Session.continue_(store, session_id, runner=my_runner)      # resume head
branch  = Session.fork_from(store, checkpoint_id, runner=my_runner)   # new id + lineage

session.rewind(to=checkpoint_id)                 # time-travel the head
session.edit(lambda history: history[:-1])       # state editing -> new checkpoint
cid = session.checkpoint(label="milestone")      # manual checkpoint
session.complete()                               # mark COMPLETED
```

`CheckpointPolicy.PER_TURN` (default) writes a checkpoint after each run;
`MANUAL` writes only on `checkpoint()`. Persistence is fail-open: a store write
failure is recorded in `reply.metadata["__session_error__"]` and never ends the
run.

## Trace capture

A session reads the agent's trace settings and persists the continual-trace
artifact onto each checkpoint. Control with `trace=`:

- `TraceCapture.AUTO` (default) — capture when the agent has tracing enabled.
- `TraceCapture.OFF` — never capture.
- `TraceCapture.ARTIFACT` — always capture the artifact.
- `TraceCapture.FULL` — artifact plus raw span events.

Trace data is a derived observation stored on the checkpoint; it never feeds
`resume`, which always restores raw history as source of truth.

## Agent-facing access

```python
from vidbyte.sessions import SessionTool, SessionScope

tool = SessionTool(store, scope=SessionScope.own_runs())
agent = Agent(name="researcher", system_prompt="...", tools=[tool])
# model-callable: create_checkpoint, fork_current, list_my_runs, read_run
```

`read_run` returns a session's trace artifact (not raw history) and is gated by
scope — own runs only by default. This is the foundation for subagent
"checkpoint before launching, return after" flows; cross-session reads route
through the existing permission/confused-deputy machinery.

## Rules of thumb

- The agent's only session seam is `BaseAgent.export_state()` / `BaseAgent.restore(state, *, tools, runner, middleware)` — pure, no I/O.
- Persist raw history; re-supply tools/runner/middleware at resume.
- Never persist secrets; the serializer scrubs credential-like keys and `api_key`.
- Remote/DB stores are adapters behind `SessionStore`; add new ones under `vidbyte/lib/providers/`.
